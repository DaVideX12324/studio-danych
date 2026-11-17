"""Testy całego skryptu lab 6 na różnych plikach CSV."""

from pathlib import Path

import pandas as pd
import pytest

from run_lab6 import main
from studio.loader import load_csv

DATA = Path(__file__).parent / "data"


@pytest.mark.parametrize("file_name", ["przecinek.csv", "srednik_cp1250.csv", "brudne.csv"])
def test_runs_on_different_csv_files(tmp_path, file_name):
    exit_code = main([str(DATA / file_name), "--out", str(tmp_path)])
    assert exit_code == 0

    cleaned, _ = load_csv(tmp_path / "cleaned.csv")
    assert cleaned.isna().sum().sum() == 0
    assert (tmp_path / "raport_lab6.md").exists()
    assert (tmp_path / "audit_log.json").exists()


def test_range_from_command_line(tmp_path):
    exit_code = main([str(DATA / "brudne.csv"), "--out", str(tmp_path), "--range", "wiek", "0", "120"])
    assert exit_code == 0
    cleaned = pd.read_csv(tmp_path / "cleaned.csv")
    assert cleaned["wiek_poza_zakresem"].sum() == 1  # domyślnie tylko oznaczenie
    assert cleaned["wiek"].min() == -5  # wartość nie zmieniona bez decyzji użytkownika


def test_range_action_from_command_line(tmp_path):
    arguments = [str(DATA / "brudne.csv"), "--out", str(tmp_path),
                 "--range", "wiek", "0", "-", "--range-action", "nan"]
    assert main(arguments) == 0
    cleaned = pd.read_csv(tmp_path / "cleaned.csv")
    assert cleaned["wiek"].min() >= 0


def test_bad_file_gives_error_code(tmp_path, capsys):
    exit_code = main([str(DATA / "wadliwy_wiersz.csv"), "--out", str(tmp_path)])
    assert exit_code == 1
    assert "Wadliwy wiersz" in capsys.readouterr().err


def test_range_on_missing_column_gives_error_code(tmp_path, capsys):
    exit_code = main([str(DATA / "brudne.csv"), "--out", str(tmp_path), "--range", "nie_ma", "0", "1"])
    assert exit_code == 1
    assert "nie_ma" in capsys.readouterr().err
