import numpy as np
import pandas as pd
import pytest

from studio.cleaning import (
    apply_range_rule,
    drop_duplicates,
    drop_missing,
    fill_missing,
    handle_outliers,
    normalize_missing_tokens,
)
from studio.profiling import find_text_tokens, profile_frame
from studio.rules import RangeRule, iqr_mask


@pytest.fixture
def frame():
    return pd.DataFrame(
        {
            "miasto": ["A", "B", None, "A", "A"],
            "wiek": [30.0, np.nan, 40.0, 30.0, -5.0],
            "dochod": [5.0, 4.0, 6.0, 5.0, 100.0],
        }
    )


def age_rule(action="flag"):
    return RangeRule("wiek", minimum=0, maximum=120, action=action)


def assert_columns_unchanged(before, after, columns):
    """Wartości w podanych kolumnach (dla zachowanych wierszy) są takie same jak przed operacją."""
    for column in columns:
        pd.testing.assert_series_equal(before.loc[after.index, column], after[column])


# --- profil -------------------------------------------------------------------------------


def test_profile_counts(frame):
    profile = profile_frame(frame)
    assert profile.n_rows == 5
    assert profile.n_cols == 3
    assert profile.duplicate_rows == 1
    assert profile.columns.loc["wiek", "missing"] == 1
    assert profile.columns.loc["wiek", "missing_pct"] == 20.0
    assert profile.columns.loc["miasto", "unique"] == 2
    assert list(profile.stats.index) == ["wiek", "dochod"]


def test_find_text_tokens_only_in_numeric_like_columns():
    data = pd.DataFrame({
        "x": ["1", "2", "?", "4", "5", "6", "7", "8", "9", "10"],
        "imie": ["Ala"] * 10,
    })
    assert find_text_tokens(data) == {"x": {"?": 1}}


# --- duplikaty ------------------------------------------------------------------------------


def test_drop_duplicates_removes_only_full_duplicates(frame):
    result = drop_duplicates(frame)
    assert result.rows_removed == 1
    assert list(result.frame.index) == [0, 1, 2, 4]  # zostaje pierwsze wystąpienie


def test_drop_duplicates_by_key(frame):
    result = drop_duplicates(frame, subset=["miasto"])
    assert result.rows_removed == 2  # dwa kolejne "A"


def test_input_frame_is_not_modified(frame):
    copy = frame.copy()
    drop_duplicates(frame)
    fill_missing(frame, "wiek", "median")
    apply_range_rule(frame, age_rule("nan"))
    handle_outliers(frame, "dochod", "clip")
    pd.testing.assert_frame_equal(frame, copy)


# --- braki --------------------------------------------------------------------------------


def test_normalize_missing_tokens_converts_to_numbers():
    data = pd.DataFrame({"x": ["1.5", "?", " Brak ", "3"], "y": ["a", "b", "?", "d"]})
    result = normalize_missing_tokens(data, ["?", "brak"])
    assert result.changed_cells == {"x": 2, "y": 1}
    assert result.affected_rows == 2  # wiersz 2 ma token w obu kolumnach
    assert result.frame["x"].tolist()[0] == 1.5
    assert result.frame["x"].isna().sum() == 2
    assert pd.api.types.is_numeric_dtype(result.frame["x"])
    assert not pd.api.types.is_numeric_dtype(result.frame["y"])


def test_fill_numeric_median(frame):
    result = fill_missing(frame, "wiek", "median")
    assert result.affected_rows == 1
    assert result.frame.loc[1, "wiek"] == 30.0  # mediana z [30, 40, 30, -5]
    assert_columns_unchanged(frame, result.frame, ["miasto", "dochod"])


def test_fill_text_mode_and_constant(frame):
    mode = fill_missing(frame, "miasto", "mode")
    assert mode.frame.loc[2, "miasto"] == "A"

    constant = fill_missing(frame, "miasto", "constant", value="nieznane")
    assert constant.frame.loc[2, "miasto"] == "nieznane"
    assert constant.changed_cells == {"miasto": 1}


def test_mean_on_text_column_is_rejected(frame):
    with pytest.raises(ValueError, match="liczbowej"):
        fill_missing(frame, "miasto", "mean")


def test_constant_without_value_is_rejected(frame):
    with pytest.raises(ValueError):
        fill_missing(frame, "miasto", "constant")


def test_fill_empty_column_is_rejected():
    data = pd.DataFrame({"x": [np.nan, np.nan]})
    with pytest.raises(ValueError, match="nie ma żadnych wartości"):
        fill_missing(data, "x", "median")


def test_drop_missing(frame):
    result = drop_missing(frame, ["wiek"])
    assert result.rows_removed == 1
    assert 1 not in result.frame.index
    assert_columns_unchanged(frame, result.frame, ["miasto", "wiek", "dochod"])


# --- reguły zakresu -------------------------------------------------------------------------


def test_range_rule_detects_without_changing(frame):
    mask = age_rule().violations(frame)
    assert mask.tolist() == [False, False, False, False, True]  # NaN nie jest naruszeniem


def test_range_rule_flag_keeps_values(frame):
    result = apply_range_rule(frame, age_rule("flag"))
    assert result.frame.loc[4, "wiek"] == -5.0
    assert result.frame["wiek_poza_zakresem"].sum() == 1
    assert result.changed_cells == {}


def test_range_rule_nan_changes_only_its_column(frame):
    result = apply_range_rule(frame, age_rule("nan"))
    assert np.isnan(result.frame.loc[4, "wiek"])
    assert result.changed_cells == {"wiek": 1}
    assert_columns_unchanged(frame, result.frame, ["miasto", "dochod"])


def test_range_rule_drop_and_clip(frame):
    assert apply_range_rule(frame, age_rule("drop")).rows_removed == 1
    clipped = apply_range_rule(frame, age_rule("clip"))
    assert clipped.frame.loc[4, "wiek"] == 0


def test_clip_needs_closed_bounds():
    with pytest.raises(ValueError, match="clip"):
        RangeRule("wiek", minimum=0, include_min=False, action="clip")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"column": "x"},                                # brak granic
        {"column": "x", "minimum": 5, "maximum": 1},    # min > max
        {"column": "x", "minimum": "zero"},             # granica nie jest liczbą
        {"column": "x", "minimum": 0, "action": "usun_wszystko"},
    ],
)
def test_invalid_rule_parameters(kwargs):
    with pytest.raises(ValueError):
        RangeRule(**kwargs)


def test_rule_on_missing_column(frame):
    with pytest.raises(ValueError, match="Brak kolumn"):
        RangeRule("nie_ma", minimum=0).violations(frame)


# --- wartości odstające --------------------------------------------------------------------


def test_iqr_flags_outlier(frame):
    result = handle_outliers(frame, "dochod", "flag")
    assert result.frame["dochod_outlier"].tolist() == [False, False, False, False, True]
    assert result.frame.loc[4, "dochod"] == 100.0  # oznaczenie nie zmienia wartości


def test_iqr_constant_column_has_no_outliers():
    data = pd.Series([3.0] * 10)
    assert not iqr_mask(data).any()


def test_iqr_report_and_clip(frame):
    assert handle_outliers(frame, "dochod", "report").affected_rows == 1

    clipped = handle_outliers(frame, "dochod", "clip")
    assert clipped.frame.loc[4, "dochod"] < 100.0
    assert clipped.changed_cells == {"dochod": 1}


def test_unknown_outlier_action(frame):
    with pytest.raises(ValueError, match="Dostępne"):
        handle_outliers(frame, "dochod", "usun_wszystko")
