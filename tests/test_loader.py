from pathlib import Path

import pandas as pd
import pytest

from studio.loader import LoadError, detect_separator, load_csv

DATA = Path(__file__).parent / "data"


def test_comma_file_loads_into_three_columns():
    frame, info = load_csv(DATA / "przecinek.csv")
    assert list(frame.columns) == ["miasto", "cena", "powierzchnia"]
    assert len(frame) == 4
    assert info.separator == ","
    assert frame.loc[0, "cena"] == pytest.approx(450000.5)


def test_semicolon_file_with_decimal_comma_and_cp1250():
    frame, info = load_csv(DATA / "srednik_cp1250.csv")
    assert list(frame.columns) == ["miasto", "cena", "powierzchnia"]
    assert info.separator == ";"
    assert info.decimal == ","
    assert info.encoding == "cp1250"
    assert frame.loc[0, "cena"] == pytest.approx(450000.5)
    assert frame.loc[3, "miasto"] == "Łódź"


def test_both_separators_give_same_data():
    comma, _ = load_csv(DATA / "przecinek.csv")
    semicolon, _ = load_csv(DATA / "srednik_cp1250.csv")
    pd.testing.assert_frame_equal(comma, semicolon)


def test_bad_line_raises_controlled_error():
    with pytest.raises(LoadError, match="Wadliwy wiersz"):
        load_csv(DATA / "wadliwy_wiersz.csv")


def test_bad_line_can_be_skipped():
    frame, info = load_csv(DATA / "wadliwy_wiersz.csv", skip_bad_lines=True)
    assert len(frame) == 2
    assert info.skipped_lines == 1


def test_wrong_encoding_raises_controlled_error():
    with pytest.raises(LoadError, match="kodowaniu"):
        load_csv(DATA / "srednik_cp1250.csv", encoding="utf-8")


def test_undecodable_bytes_raise_controlled_error(tmp_path):
    path = tmp_path / "zly.csv"
    path.write_bytes(b"a,b\n\x81,\x98\n")  # bajty niepoprawne w UTF-8 i w cp1250
    with pytest.raises(LoadError):
        load_csv(path)


@pytest.mark.parametrize("content", ["", "   \n", "a,b,c\n"])
def test_empty_file_or_header_only_raise(tmp_path, content):
    path = tmp_path / "pusty.csv"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(LoadError):
        load_csv(path)


def test_missing_file_raises():
    with pytest.raises(LoadError, match="Nie znaleziono"):
        load_csv(DATA / "nie_ma_takiego.csv")


@pytest.mark.parametrize(
    ("header", "expected"),
    [("a,b,c", ","), ("a;b;c", ";"), ("a\tb", "\t"), ("jedna_kolumna", ",")],
)
def test_detect_separator(header, expected):
    assert detect_separator(header) == expected
