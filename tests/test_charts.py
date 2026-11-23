"""Testy wykresów i korelacji na małych, ręcznie przygotowanych danych."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from matplotlib.figure import Figure

from run_lab7 import chart_from_command_line, main
from studio.chart_set import ChartSet, default_chart_set
from studio.charts import (
    ChartError,
    ChartSpec,
    build_comparison_figure,
    build_figure,
    category_chart_columns,
    missing_values_figure,
    numeric_chart_columns,
)
from studio.correlation import correlation_matrix, describe_pair, strength_label, strongest_pairs

DATA = Path(__file__).parent / "data"
ROOT = Path(__file__).parent.parent


@pytest.fixture
def frame():
    return pd.DataFrame({
        "wiek": [20.0, 30.0, 40.0, 50.0, 60.0, 35.0],
        "dochod": [2.0, 3.0, 4.0, 5.0, 6.0, 3.5],
        "miasto": ["Kraków", "Gdańsk", "Kraków", "Gdańsk", "Łódź", "Kraków"],
        "stala": [7.0] * 6,
        "flaga": [True, False, False, True, False, False],
    })


def texts_of(figure: Figure) -> list[str]:
    """Tytuł figury oraz tytuły i opisy osi pierwszych osi."""
    ax = figure.axes[0]
    return [figure.get_suptitle(), ax.get_xlabel(), ax.get_ylabel()]


# --- cztery typy wykresów ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "spec",
    [
        ChartSpec("histogram", x="wiek"),
        ChartSpec("scatter", x="wiek", y="dochod"),
        ChartSpec("box", x="dochod"),
        ChartSpec("box", x="dochod", by="miasto"),
        ChartSpec("bar", x="miasto"),
        ChartSpec("bar", x="miasto", y="dochod"),
        ChartSpec("bar", x="wiek", y="dochod", bins=3),
    ],
)
def test_chart_has_title_and_axis_labels(frame, spec):
    figure = build_figure(frame, spec)
    assert isinstance(figure, Figure)
    title, x_label, y_label = texts_of(figure)
    assert title
    assert y_label
    if spec.kind != "box" or spec.by:
        assert x_label


def test_correlation_chart(frame):
    figure = build_figure(frame, ChartSpec("correlation"))
    assert "Pearsona" in figure.get_suptitle()


def test_bar_counts_records_in_categories(frame):
    figure = build_figure(frame, ChartSpec("bar", x="miasto"))
    heights = []
    for bar in figure.axes[0].patches:
        heights.append(bar.get_height())
    assert heights == [3, 2, 1]  # Kraków, Gdańsk, Łódź (od najliczniejszej)


def test_custom_title(frame):
    figure = build_figure(frame, ChartSpec("histogram", x="wiek", title="Wiek klientów"))
    assert figure.get_suptitle() == "Wiek klientów"


# --- walidacja kolumn -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("spec", "message"),
    [
        (ChartSpec("histogram", x="miasto"), "tekstowa"),
        (ChartSpec("histogram", x="stala"), "stała"),
        (ChartSpec("box", x="flaga"), "prawda/fałsz"),
        (ChartSpec("scatter", x="wiek", y="stala"), "stała"),
        (ChartSpec("histogram", x="nie_ma"), "nie ma w danych"),
        (ChartSpec("bar", x="stala"), "jedną kategorię"),
        (ChartSpec("bar", x="miasto", y="miasto"), "tekstowa"),
    ],
)
def test_wrong_column_is_blocked_with_message(frame, spec, message):
    with pytest.raises(ChartError, match=message):
        build_figure(frame, spec)


def test_error_message_suggests_columns(frame):
    with pytest.raises(ChartError) as error:
        build_figure(frame, ChartSpec("histogram", x="miasto"))
    assert "wiek" in str(error.value)
    assert "stala" not in str(error.value)  # stałej kolumny nie podpowiadamy


def test_numeric_column_with_many_values_needs_bins():
    data = pd.DataFrame({"x": np.arange(30.0)})
    with pytest.raises(ChartError, match="przedziałów"):
        build_figure(data, ChartSpec("bar", x="x"))
    build_figure(data, ChartSpec("bar", x="x", bins=4))


def test_log_scale_needs_positive_values():
    data = pd.DataFrame({"x": [-1.0, 0.0, 5.0, 5.0]})
    with pytest.raises(ChartError, match="logarytmiczna"):
        build_figure(data, ChartSpec("histogram", x="x", log_scale=True))


@pytest.mark.parametrize(
    "kwargs",
    [
        {"kind": "kolowy", "x": "wiek"},
        {"kind": "histogram"},  # brak kolumny
        {"kind": "scatter", "x": "wiek"},  # brak osi Y
        {"kind": "scatter", "x": "wiek", "y": "wiek"},
        {"kind": "histogram", "x": "wiek", "bins": 1},
        {"kind": "correlation", "method": "kendall-magia"},
    ],
)
def test_invalid_spec_parameters(kwargs):
    with pytest.raises(ChartError):
        ChartSpec(**kwargs)


def test_spec_from_dict_rejects_unknown_parameter():
    with pytest.raises(ChartError, match="kolor"):
        ChartSpec.from_dict({"kind": "histogram", "x": "wiek", "kolor": "red"})


def test_column_lists_for_choosing(frame):
    assert numeric_chart_columns(frame) == ["wiek", "dochod"]
    # Kolumna liczbowa z kilkoma wartościami też może być kategorią; stała nie.
    assert category_chart_columns(frame) == ["wiek", "dochod", "miasto", "flaga"]


def test_raw_column_with_text_tokens_is_drawn_without_them():
    raw = pd.DataFrame({"x": ["1", "2", "?", "3", "4", "5", "6", "7", "8", "9"]})
    figure = build_figure(raw, ChartSpec("histogram", x="x"))
    assert "pominięto 1" in figure.axes[0].get_title()


def test_chart_does_not_modify_data(frame):
    copy = frame.copy()
    build_figure(frame, ChartSpec("bar", x="wiek", y="dochod", bins=3))
    build_figure(frame, ChartSpec("box", x="dochod", by="miasto"))
    pd.testing.assert_frame_equal(frame, copy)


# --- przed / po -------------------------------------------------------------------------------


def test_comparison_has_two_panels(frame):
    after = frame.iloc[:4]
    figure = build_comparison_figure(frame, after, ChartSpec("histogram", x="wiek"))
    titles = []
    for ax in figure.axes:
        titles.append(ax.get_title())
    assert titles[0].startswith("Przed")
    assert titles[1].startswith("Po")


def test_box_comparison_uses_one_axis(frame):
    figure = build_comparison_figure(frame, frame.iloc[:4], ChartSpec("box", x="wiek"))
    assert len(figure.axes) == 1
    assert len(figure.axes[0].get_xticklabels()) == 2


def test_missing_values_chart_counts_text_tokens():
    before = pd.DataFrame({"x": ["1", "?", None, "4", "5", "6", "7", "8", "9", "10"]})
    after = pd.DataFrame({"x": [1.0, 4.0, 5.0]})
    figure = missing_values_figure(before, after)
    heights = []
    for bar in figure.axes[0].patches:
        heights.append(bar.get_height())
    assert heights == [2, 0]  # przed: NaN + "?", po: 0


def test_figure_can_be_saved(tmp_path, frame):
    figure = build_figure(frame, ChartSpec("scatter", x="wiek", y="dochod"))
    for extension in ("png", "svg", "pdf"):
        path = tmp_path / f"wykres.{extension}"
        figure.savefig(path)
        assert path.stat().st_size > 0
    assert (tmp_path / "wykres.png").read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


# --- korelacja --------------------------------------------------------------------------------


def test_correlation_matrix_uses_only_numeric_non_constant_columns(frame):
    matrix = correlation_matrix(frame)
    assert list(matrix.columns) == ["wiek", "dochod"]
    assert matrix.loc["wiek", "dochod"] == pytest.approx(1.0)


def test_identifier_column_is_skipped_in_correlation_and_default_charts(frame):
    data = frame.copy()
    data.insert(0, "id", range(1, 7))
    assert "id" not in correlation_matrix(data).columns

    for planned in default_chart_set(data, data).charts:
        assert planned.spec.x != "id"
        assert planned.spec.y != "id"


def test_correlation_needs_two_columns():
    with pytest.raises(ValueError, match="co najmniej dwie"):
        correlation_matrix(pd.DataFrame({"x": [1.0, 2.0, 3.0], "t": ["a", "b", "c"]}))


def test_spearman_is_robust_to_outlier():
    data = pd.DataFrame({"x": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0], "y": [1.0, 2.0, 3.0, 4.0, 5.0, -100.0]})
    pearson = correlation_matrix(data, "pearson").loc["x", "y"]
    spearman = correlation_matrix(data, "spearman").loc["x", "y"]
    assert pearson < 0  # jeden punkt odwraca znak Pearsona
    assert spearman > pearson


def test_strongest_pairs_sorted_by_absolute_value():
    data = pd.DataFrame({
        "a": [1.0, 2.0, 3.0, 4.0, 5.0],
        "b": [5.0, 4.0, 3.0, 2.0, 1.0],  # a-b: -1
        "c": [1.0, 3.0, 2.0, 5.0, 4.0],
    })
    pairs = strongest_pairs(correlation_matrix(data), top=2)
    assert (pairs[0].first, pairs[0].second) == ("a", "b")
    assert pairs[0].value == pytest.approx(-1.0)


@pytest.mark.parametrize(("value", "label"), [(0.9, "bardzo silna"), (-0.65, "silna"), (0.45, "umiarkowana"),
                                              (0.25, "słaba"), (0.05, "bardzo słaba lub brak")])
def test_strength_labels(value, label):
    assert strength_label(value) == label


def test_pair_description_does_not_claim_causation():
    data = pd.DataFrame({"a": [1.0, 2.0, 3.0, 4.0], "b": [2.0, 4.0, 5.0, 8.0]})
    text = describe_pair(strongest_pairs(correlation_matrix(data), 1)[0])
    for word in ("powoduje", "wpływa", "dlatego", "skutek"):
        assert word not in text


# --- zestaw wykresów i skrypt -----------------------------------------------------------------


def test_reference_chart_config_is_valid():
    chart_set = ChartSet.from_json(ROOT / "config" / "wykresy_california.json")
    kinds = set()
    for planned in chart_set.charts:
        kinds.add(planned.spec.kind)
    assert {"histogram", "scatter", "box", "bar", "correlation"} <= kinds


def test_default_chart_set_has_all_kinds(frame):
    chart_set = default_chart_set(frame, frame)
    kinds = set()
    for planned in chart_set.charts:
        kinds.add(planned.spec.kind)
    assert {"histogram", "scatter", "box", "bar", "correlation"} <= kinds


def test_chart_from_command_line():
    planned = chart_from_command_line(["kind=histogram", "x=wiek", "bins=10", "log_scale=tak", "compare=nie"])
    assert planned.spec == ChartSpec("histogram", x="wiek", bins=10, log_scale=True)
    assert planned.compare is False
    with pytest.raises(ValueError):
        chart_from_command_line(["kind=histogram", "x"])


@pytest.mark.parametrize("file_name", ["przecinek.csv", "srednik_cp1250.csv", "brudne.csv"])
def test_script_on_different_files(tmp_path, file_name):
    assert main([str(DATA / file_name), "--out", str(tmp_path)]) == 0
    report = (tmp_path / "raport_lab7.md").read_text(encoding="utf-8")
    assert "Korelacja to nie przyczynowość" in report or "Analiza korelacji pominięta" in report
    images = list((tmp_path / "wykresy").glob("*.png"))
    assert len(images) >= 3


def test_script_reports_blocked_chart(tmp_path):
    arguments = [str(DATA / "brudne.csv"), "--out", str(tmp_path), "--chart", "kind=histogram", "x=miasto"]
    assert main(arguments) == 0
    report = (tmp_path / "raport_lab7.md").read_text(encoding="utf-8")
    assert "tekstowa" in report
    assert not (tmp_path / "wykresy" / "histogram_miasto.png").exists()
