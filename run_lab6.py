"""Lab 6: profil danych, diagnoza, czyszczenie, raport przed/po i cleaned.csv.

Przykłady:
    python run_lab6.py                              # zbiór referencyjny + config/california.json
    python run_lab6.py dane.csv                     # dowolny CSV + config/domyslna.json
    python run_lab6.py dane.csv --range wiek 0 120  # dodatkowa reguła zakresu
    python run_lab6.py dane.csv --config moja.json --out wyniki
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

from studio.loader import LoadError
from studio.pipeline import PipelineConfig, outlier_columns_for_diagnosis, run_pipeline
from studio.profiling import Diagnosis, diagnose
from studio.report import build_report
from studio.rules import RANGE_ACTIONS, RangeRule
from studio.session import DataSession

PROJECT_DIR = Path(__file__).resolve().parent
REFERENCE_DATA = PROJECT_DIR / "data" / "california_housing_projekt2.csv"
REFERENCE_CONFIG = PROJECT_DIR / "config" / "california.json"
DEFAULT_CONFIG = PROJECT_DIR / "config" / "domyslna.json"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Czyszczenie pliku CSV z raportem przed/po (lab 6).")
    parser.add_argument("input", nargs="?", type=Path,
                        help="plik CSV (bez podania: zbiór referencyjny California Housing)")
    parser.add_argument("--config", type=Path,
                        help="plik konfiguracji JSON (domyślnie config/domyslna.json, "
                             "a dla zbioru referencyjnego config/california.json)")
    parser.add_argument("--out", type=Path, default=PROJECT_DIR / "output", help="katalog na wyniki")
    parser.add_argument("--range", nargs=3, action="append", default=[], metavar=("KOLUMNA", "MIN", "MAX"),
                        help="reguła zakresu, np. --range wiek 0 120; '-' = brak granicy; można powtarzać")
    parser.add_argument("--range-action", choices=RANGE_ACTIONS, default="flag",
                        help="co zrobić z wartościami spoza zakresu z --range (domyślnie: tylko oznaczyć)")
    parser.add_argument("--skip-bad-lines", action="store_true", help="pomijaj wadliwe wiersze zamiast przerywać")
    return parser.parse_args(argv)


def choose_input_and_config(args: argparse.Namespace) -> tuple[Path, Path]:
    if args.input is None:
        input_path = REFERENCE_DATA
        config_path = REFERENCE_CONFIG
    else:
        input_path = args.input
        config_path = DEFAULT_CONFIG

    if args.config is not None:
        config_path = args.config
    return input_path, config_path


def parse_bound(text: str) -> float | None:
    if text == "-":
        return None
    try:
        return float(text.replace(",", "."))
    except ValueError:
        raise ValueError(f"Granica zakresu musi być liczbą albo '-', podano '{text}'.") from None


def rules_from_command_line(args: argparse.Namespace) -> list[RangeRule]:
    rules = []
    for column, minimum, maximum in args.range:
        rule = RangeRule(
            column=column,
            minimum=parse_bound(minimum),
            maximum=parse_bound(maximum),
            action=args.range_action,
            reason="reguła podana w linii poleceń",
        )
        rules.append(rule)
    return rules


def run_diagnosis(frame: pd.DataFrame, config: PipelineConfig) -> Diagnosis:
    columns = outlier_columns_for_diagnosis(config, frame)
    return diagnose(frame, config.range_rules, columns, config.iqr_factor)


def save_results(session: DataSession, config: PipelineConfig, before: Diagnosis, after: Diagnosis,
                 out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    cleaned_path = out_dir / "cleaned.csv"
    session.current.to_csv(cleaned_path, index=False, lineterminator="\n")
    cleaned_sha256 = hashlib.sha256(cleaned_path.read_bytes()).hexdigest()

    report = build_report(session, config, before, after, cleaned_path.name, cleaned_sha256)
    (out_dir / "raport_lab6.md").write_text(report, encoding="utf-8")

    log = []
    for entry in session.audit_log:
        log.append(entry.to_dict())
    log_text = json.dumps(log, ensure_ascii=False, indent=2)
    (out_dir / "audit_log.json").write_text(log_text, encoding="utf-8")


def print_summary(session: DataSession, before: Diagnosis, after: Diagnosis, out_dir: Path) -> None:
    print(f"Rekordy: {before.rows} -> {after.rows}, kolumny: {session.raw.shape[1]} -> {session.current.shape[1]}")
    print(f"Duplikaty: {before.duplicate_rows} -> {after.duplicate_rows}")
    print(f"Braki (NaN): {before.missing_total()} -> {after.missing_total()}")
    print(f"Tekstowe oznaczenia braku: {before.tokens_total()} -> {after.tokens_total()}")
    print(f"Wartości spoza zakresu: {before.violations_total()} -> {after.violations_total()}")
    print("Operacje:")
    for entry in session.audit_log:
        print(f"  {entry.step:2}. {entry.operation:<24} {entry.rows_before:>6} -> {entry.rows_after:<6} "
              f"dotknięte: {entry.affected_rows:<5} {entry.details}")
    print(f"Wyniki w {out_dir}: cleaned.csv, raport_lab6.md, audit_log.json")


def main(argv: list[str] | None = None) -> int:
    # Konsola Windows (cp1250) nie ma np. znaku "≤" - zamiast błędu wypisz "?".
    sys.stdout.reconfigure(errors="replace")
    sys.stderr.reconfigure(errors="replace")

    args = parse_args(argv)
    input_path, config_path = choose_input_and_config(args)

    try:
        config = PipelineConfig.from_json(config_path)
        config.range_rules.extend(rules_from_command_line(args))
        session = DataSession.from_csv(input_path, skip_bad_lines=args.skip_bad_lines)
        before = run_diagnosis(session.raw, config)
        run_pipeline(session, config)
    except (LoadError, ValueError) as error:
        print(f"Błąd: {error}", file=sys.stderr)
        return 1

    after = run_diagnosis(session.current, config)

    try:
        save_results(session, config, before, after, args.out)
    except OSError as error:
        print(f"Błąd zapisu do {args.out}: {error}. Sprawdź, czy plik nie jest otwarty w innym programie.",
              file=sys.stderr)
        return 1

    print(f"Plik: {input_path.name}, konfiguracja: {config_path.name}")
    print_summary(session, before, after, args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
