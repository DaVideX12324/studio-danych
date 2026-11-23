"""Lab 7: wykresy dla danych przed i po czyszczeniu, analiza korelacji i raport.

Przykłady:
    python run_lab7.py                       # zbiór referencyjny + config/wykresy_california.json
    python run_lab7.py dane.csv              # dowolny CSV: wykresy dobrane według typów kolumn
    python run_lab7.py dane.csv --charts moje_wykresy.json
    python run_lab7.py --chart kind=scatter x=MedInc y=MedHouseVal compare=tak
    python run_lab7.py dane.csv --chart kind=bar x=miasto --chart kind=histogram x=wiek bins=10
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from matplotlib.figure import Figure

from run_lab6 import PROJECT_DIR, choose_input_and_config
from studio.chart_report import ChartResult, build_chart_report, summarize_correlation
from studio.chart_set import ChartSet, PlannedChart, default_chart_set
from studio.charts import ChartError, build_comparison_figure, build_figure, missing_values_figure
from studio.loader import LoadError
from studio.pipeline import PipelineConfig, run_pipeline
from studio.session import DataSession

REFERENCE_CHARTS = PROJECT_DIR / "config" / "wykresy_california.json"
IMAGES_DIR_NAME = "wykresy"

YES_WORDS = {"tak", "true", "1", "yes"}
NO_WORDS = {"nie", "false", "0", "no"}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Wykresy przed/po czyszczeniu i analiza korelacji (lab 7).")
    parser.add_argument("input", nargs="?", type=Path,
                        help="plik CSV (bez podania: zbiór referencyjny California Housing)")
    parser.add_argument("--config", type=Path, help="konfiguracja czyszczenia (jak w run_lab6.py)")
    parser.add_argument("--charts", type=Path,
                        help="plik JSON z listą wykresów (bez podania: zestaw dobrany automatycznie, "
                             "a dla zbioru referencyjnego config/wykresy_california.json)")
    parser.add_argument("--chart", nargs="+", action="append", default=[], metavar="PARAM=WARTOŚĆ",
                        help="jeden wykres z parametrów, np. --chart kind=box x=MedInc log_scale=tak; "
                             "można powtarzać; zastępuje zestaw z pliku")
    parser.add_argument("--out", type=Path, default=PROJECT_DIR / "output", help="katalog na wyniki")
    parser.add_argument("--skip-bad-lines", action="store_true", help="pomijaj wadliwe wiersze zamiast przerywać")
    return parser.parse_args(argv)


# --- wykres z linii poleceń ---------------------------------------------------------------------


def parse_flag(name: str, text: str) -> bool:
    if text.lower() in YES_WORDS:
        return True
    if text.lower() in NO_WORDS:
        return False
    raise ValueError(f"Parametr {name} przyjmuje tak/nie, podano '{text}'.")


def chart_from_command_line(parts: list[str]) -> PlannedChart:
    """['kind=box', 'x=MedInc', 'log_scale=tak'] -> PlannedChart."""
    data = {}
    for part in parts:
        if "=" not in part:
            raise ValueError(f"Parametr wykresu zapisz jako nazwa=wartość, np. x=MedInc (podano '{part}').")
        name, value = part.split("=", 1)
        if name == "bins":
            try:
                data[name] = int(value)
            except ValueError:
                raise ValueError(f"bins musi być liczbą całkowitą, podano '{value}'.") from None
        elif name in ("log_scale", "compare"):
            data[name] = parse_flag(name, value)
        else:
            data[name] = value
    return PlannedChart.from_dict(data)


def choose_chart_set(args: argparse.Namespace, session: DataSession) -> ChartSet:
    if args.chart:
        charts = []
        for parts in args.chart:
            charts.append(chart_from_command_line(parts))
        return ChartSet(charts=charts)
    if args.charts is not None:
        return ChartSet.from_json(args.charts)
    if args.input is None:
        return ChartSet.from_json(REFERENCE_CHARTS)
    return default_chart_set(session.raw, session.current)


# --- rysowanie i zapis --------------------------------------------------------------------------


def draw_planned_chart(session: DataSession, planned: PlannedChart) -> Figure:
    if planned.compare:
        return build_comparison_figure(session.raw, session.current, planned.spec)
    return build_figure(session.current, planned.spec)


def save_figure(figure: Figure, images_dir: Path, name: str) -> str:
    """Zapisuje PNG i zwraca ścieżkę względem katalogu z raportem."""
    figure.savefig(images_dir / f"{name}.png", dpi=110)
    return f"{IMAGES_DIR_NAME}/{name}.png"


def unique_name(name: str, used: set[str]) -> str:
    """Ten sam wykres raz przed/po i raz tylko po nie może nadpisać pliku."""
    candidate = name
    number = 2
    while candidate in used:
        candidate = f"{name}_{number}"
        number += 1
    used.add(candidate)
    return candidate


def draw_all(session: DataSession, chart_set: ChartSet, images_dir: Path) -> list[ChartResult]:
    """Rysuje każdy wykres. Wykres, który nie przejdzie walidacji, trafia do raportu z powodem blokady."""
    results = []
    used_names = set()
    for planned in chart_set.charts:
        try:
            figure = draw_planned_chart(session, planned)
        except ChartError as error:
            results.append(ChartResult(planned, error=str(error)))
            continue

        name = planned.spec.file_name()
        if planned.compare:
            name += "_przed_po"
        image_path = save_figure(figure, images_dir, unique_name(name, used_names))
        results.append(ChartResult(planned, image_path=image_path))
    return results


def remove_old_images(images_dir: Path) -> None:
    """Stare wykresy z poprzedniego uruchomienia (np. dla innego pliku) nie mogą zostać w katalogu."""
    for old_image in images_dir.glob("*.png"):
        old_image.unlink()


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(errors="replace")
    sys.stderr.reconfigure(errors="replace")

    args = parse_args(argv)
    input_path, config_path = choose_input_and_config(args)

    try:
        config = PipelineConfig.from_json(config_path)
        session = DataSession.from_csv(input_path, skip_bad_lines=args.skip_bad_lines)
        run_pipeline(session, config)
        chart_set = choose_chart_set(args, session)
    except (LoadError, ValueError) as error:
        print(f"Błąd: {error}", file=sys.stderr)
        return 1

    images_dir = args.out / IMAGES_DIR_NAME
    try:
        images_dir.mkdir(parents=True, exist_ok=True)
        remove_old_images(images_dir)
        missing_image = save_figure(missing_values_figure(session.raw, session.current), images_dir, "braki_danych")
        results = draw_all(session, chart_set, images_dir)
        summary = summarize_correlation(session.raw, session.current)
        report = build_chart_report(input_path.name, session.raw, session.current, results, missing_image,
                                    summary, chart_set)
        (args.out / "raport_lab7.md").write_text(report, encoding="utf-8")
    except OSError as error:
        print(f"Błąd zapisu do {args.out}: {error}. Sprawdź, czy plik nie jest otwarty w innym programie.",
              file=sys.stderr)
        return 1

    print(f"Plik: {input_path.name}, konfiguracja czyszczenia: {config_path.name}")
    for result in results:
        if result.error:
            print(f"  zablokowany: {result.planned.spec.file_name()}: {result.error}")
        else:
            print(f"  {result.image_path}")
    print(f"Raport: {args.out / 'raport_lab7.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
