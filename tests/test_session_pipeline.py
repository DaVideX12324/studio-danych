from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from studio.loader import load_csv
from studio.pipeline import PipelineConfig, outlier_columns_for_diagnosis, run_pipeline
from studio.profiling import diagnose
from studio.session import DataSession

DATA = Path(__file__).parent / "data"
ROOT = Path(__file__).parent.parent

CONFIG = {
    "missing_tokens": ["?", "brak"],
    "range_rules": [{"column": "wiek", "min": 0, "max": 120, "action": "nan", "reason": "wiek w latach"}],
    "outliers": {"factor": 1.5, "columns": ["dochod"]},
    "steps": [
        {"op": "drop_duplicates"},
        {"op": "missing_tokens"},
        {"op": "range_rules"},
        {"op": "fill_missing", "params": {"columns": ["miasto"], "strategy": "constant", "value": "nieznane"}},
        {"op": "fill_missing", "params": {"columns": ["wiek", "dochod"], "strategy": "median"}},
        {"op": "outliers", "params": {"action": "flag"}},
    ],
}


@pytest.fixture
def session():
    return DataSession.from_csv(DATA / "brudne.csv")


def test_diagnosis_finds_prepared_problems(session):
    config = PipelineConfig.from_dict(CONFIG)
    found = diagnose(session.raw, config.range_rules, ["dochod"])
    assert found.duplicate_rows == 1
    assert found.text_tokens == {"wiek": {"?": 1}, "dochod": {"brak": 1}}
    assert found.missing["miasto"] == 1
    assert found.range_violations == {"0 ≤ wiek ≤ 120": 1}
    assert found.outliers["dochod"].count == 1


def test_pipeline_on_controlled_file(session):
    entries = run_pipeline(session, PipelineConfig.from_dict(CONFIG))
    result = session.current

    operations = []
    for entry in entries:
        operations.append(entry.operation)
    assert operations == [
        "drop_duplicates", "normalize_missing_tokens", "apply_range_rule",
        "fill_missing", "fill_missing", "fill_missing", "handle_outliers",
    ]
    assert len(result) == 7
    assert result.isna().sum().sum() == 0
    assert entries[1].changed_cells == {"wiek": 1, "dochod": 1}
    assert entries[2].changed_cells == {"wiek": 1}
    assert result.loc[result["id"] == 3, "miasto"].item() == "nieznane"
    assert result.loc[result["id"] == 7, "dochod_outlier"].item()
    # kolumny id nie dotyka żadna operacja
    assert result["id"].tolist() == [1, 2, 3, 4, 5, 6, 7]
    # dane surowe bez zmian
    assert len(session.raw) == 8
    assert session.raw.loc[3, "wiek"] == "-5"


def test_reset_restores_raw_data(session):
    run_pipeline(session, PipelineConfig.from_dict(CONFIG))
    entry = session.reset()
    pd.testing.assert_frame_equal(session.current, session.raw)
    assert entry.operation == "reset"
    assert entry.rows_after == 8


def test_failed_operation_leaves_data_unchanged(session):
    before = session.current.copy()
    with pytest.raises(ValueError):
        session.apply("fill_missing", column="miasto", strategy="mean")
    pd.testing.assert_frame_equal(session.current, before)
    assert session.audit_log == []


def test_unknown_operation(session):
    with pytest.raises(ValueError, match="Nieznana operacja"):
        session.apply("magia")


def test_empty_frame_is_rejected():
    with pytest.raises(ValueError):
        DataSession(pd.DataFrame())


def test_audit_entry_counts(session):
    entry = session.apply("drop_duplicates")
    assert entry.rows_before == 8
    assert entry.rows_after == 7
    assert entry.affected_rows == 1
    assert entry.step == 1


def test_results_are_repeatable():
    config = PipelineConfig.from_dict(CONFIG)
    first = DataSession.from_csv(DATA / "brudne.csv")
    second = DataSession.from_csv(DATA / "brudne.csv")
    run_pipeline(first, config)
    run_pipeline(second, config)
    pd.testing.assert_frame_equal(first.current, second.current)


def test_cleaned_csv_can_be_read_back(session, tmp_path):
    run_pipeline(session, PipelineConfig.from_dict(CONFIG))
    path = tmp_path / "cleaned.csv"
    session.current.to_csv(path, index=False)
    reread, _ = load_csv(path)
    assert reread.shape == session.current.shape
    np.testing.assert_allclose(reread["dochod"], session.current["dochod"])


# --- konfiguracja i dowolne pliki CSV ----------------------------------------------------------


def test_project_configs_are_valid():
    california = PipelineConfig.from_json(ROOT / "config" / "california.json")
    assert len(california.range_rules) == 9
    default = PipelineConfig.from_json(ROOT / "config" / "domyslna.json")
    assert default.range_rules == []
    assert default.outlier_columns == "numeric"


def test_default_config_works_on_other_file(session):
    config = PipelineConfig.from_json(ROOT / "config" / "domyslna.json")
    run_pipeline(session, config)
    result = session.current
    assert result.isna().sum().sum() == 0
    assert result.loc[result["id"] == 3, "miasto"].item() == "Gdańsk"  # dominanta
    assert "dochod_outlier" in result.columns
    assert "wiek_outlier" in result.columns


def test_default_config_on_text_only_file():
    session = DataSession(pd.DataFrame({"imie": ["Ala", None, "Ola", "Ala"]}))
    config = PipelineConfig.from_json(ROOT / "config" / "domyslna.json")
    run_pipeline(session, config)
    assert session.current["imie"].tolist() == ["Ala", "Ala", "Ola"]  # duplikat usunięty, brak = dominanta


def test_default_config_skips_completely_empty_column():
    session = DataSession(pd.DataFrame({"x": [1.0, np.nan, 3.0], "pusta": [np.nan, np.nan, np.nan]}))
    config = PipelineConfig.from_json(ROOT / "config" / "domyslna.json")
    run_pipeline(session, config)
    assert session.current["x"].isna().sum() == 0
    assert session.current["pusta"].isna().all()


def test_config_for_other_file_gives_clear_error(session):
    config = PipelineConfig.from_json(ROOT / "config" / "california.json")
    with pytest.raises(ValueError, match="nie ma w pliku"):
        run_pipeline(session, config)
    pd.testing.assert_frame_equal(session.current, session.raw)


def test_diagnosis_columns_include_numbers_with_text_tokens(session):
    config = PipelineConfig.from_json(ROOT / "config" / "domyslna.json")
    columns = outlier_columns_for_diagnosis(config, session.raw)
    assert columns == ["id", "wiek", "dochod"]
