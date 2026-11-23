"""Raport Markdown z wykresami (lab 7): wykresy przed/po, analiza korelacji, zablokowane wykresy."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from .chart_set import ChartSet, PlannedChart
from .charts import CHART_KINDS, ChartSpec
from .correlation import (
    CAUSATION_WARNING,
    METHODS,
    biggest_changes,
    correlation_columns,
    correlation_matrix,
    describe_pair,
    strength_label,
    strongest_pairs,
)
from .report import markdown_table

# Różnica Pearson - Spearman większa niż ta sugeruje zależność nieliniową albo wpływ wartości odstających.
METHOD_DIFFERENCE_NOTE = 0.15


@dataclass
class ChartResult:
    planned: PlannedChart
    image_path: str = ""  # ścieżka względem raportu, np. "wykresy/histogram_MedInc.png"
    error: str = ""  # komunikat walidacji, gdy wykresu nie dało się narysować


@dataclass
class CorrelationSummary:
    pearson_before: pd.DataFrame | None = None
    pearson_after: pd.DataFrame | None = None
    spearman_after: pd.DataFrame | None = None
    error: str = ""


def summarize_correlation(before: pd.DataFrame, after: pd.DataFrame) -> CorrelationSummary:
    if len(correlation_columns(after)) < 2:
        return CorrelationSummary(error="W danych są mniej niż dwie niestałe kolumny liczbowe.")

    summary = CorrelationSummary(
        pearson_after=correlation_matrix(after, "pearson"),
        spearman_after=correlation_matrix(after, "spearman"),
    )
    if len(correlation_columns(before)) >= 2:
        summary.pearson_before = correlation_matrix(before, "pearson")
    return summary


# --- sekcje -------------------------------------------------------------------------------------


def describe_spec(spec: ChartSpec) -> str:
    """Parametry wykresu w jednej linijce, np. 'histogram; x = MedInc; skala logarytmiczna'."""
    parts = [CHART_KINDS[spec.kind]]
    if spec.x:
        parts.append(f"x = `{spec.x}`")
    if spec.y:
        parts.append(f"y = `{spec.y}`")
    if spec.by:
        parts.append(f"grupy wg `{spec.by}`")
    if spec.bins:
        parts.append(f"przedziały: {spec.bins}")
    if spec.log_scale:
        parts.append("skala logarytmiczna")
    if spec.kind == "correlation":
        parts.append(f"metoda {METHODS[spec.method]}")
    return "; ".join(parts)


def chart_section(number: int, result: ChartResult) -> str:
    planned = result.planned
    spec = planned.spec
    title = spec.title or spec.default_title()
    if planned.compare:
        title += " (przed i po)"

    lines = [f"### {number}. {title}", "", f"![{title}]({result.image_path})", ""]
    lines.append(f"*Parametry:* {describe_spec(spec)}.")
    if planned.comment:
        lines.append("")
        lines.append(f"**Wniosek:** {planned.comment}")
    return "\n".join(lines)


def blocked_section(results: list[ChartResult]) -> str:
    rows = []
    for result in results:
        if result.error:
            rows.append([describe_spec(result.planned.spec), result.error])
    if not rows:
        return "Wszystkie zaplanowane wykresy przeszły walidację kolumn."
    return markdown_table(["Wykres", "Powód blokady"], rows)


def strongest_pairs_table(summary: CorrelationSummary, top: int) -> str:
    rows = []
    for pair in strongest_pairs(summary.pearson_after, top):
        spearman = summary.spearman_after.loc[pair.first, pair.second]
        before = "–"
        if summary.pearson_before is not None and pair.first in summary.pearson_before.columns \
                and pair.second in summary.pearson_before.columns:
            before = f"{summary.pearson_before.loc[pair.first, pair.second]:.2f}"
        rows.append([
            f"{pair.first} – {pair.second}",
            f"{pair.value:.2f}",
            f"{spearman:.2f}",
            strength_label(pair.value),
            before,
        ])
    headers = ["Para kolumn", "Pearson (po)", "Spearman (po)", "Siła (Pearson)", "Pearson (przed)"]
    return markdown_table(headers, rows)


def changes_table(summary: CorrelationSummary, top: int) -> str:
    rows = []
    for change in biggest_changes(summary.pearson_before, summary.pearson_after, top):
        rows.append([
            f"{change.first} – {change.second}",
            f"{change.before:.2f}",
            f"{change.after:.2f}",
            f"{change.difference():+.2f}",
        ])
    return markdown_table(["Para kolumn", "Pearson przed", "Pearson po", "Zmiana"], rows)


def correlation_conclusions(summary: CorrelationSummary, top: int) -> str:
    lines = []
    for pair in strongest_pairs(summary.pearson_after, top):
        line = f"- {describe_pair(pair)}"
        spearman = summary.spearman_after.loc[pair.first, pair.second]
        if abs(pair.value - spearman) > METHOD_DIFFERENCE_NOTE:
            line += (f" Spearman = {spearman:.2f} wyraźnie różni się od Pearsona: zależność jest nieliniowa "
                     "albo wartości odstające mocno wpływają na wynik.")
        lines.append(line)
    return "\n".join(lines)


def correlation_section(summary: CorrelationSummary, chart_set: ChartSet) -> str:
    if summary.error:
        return f"Analiza korelacji pominięta: {summary.error}"

    top = chart_set.correlation_top
    parts = [
        "Współczynnik Pearsona mierzy zależność liniową, Spearmana zależność monotoniczną (liczony na "
        "rangach, więc mniej czuły na wartości odstające). Wartości od -1 do 1; 0 = brak takiej zależności. "
        "Siła wg umownej skali |r|: ≥ 0,8 bardzo silna, ≥ 0,6 silna, ≥ 0,4 umiarkowana, ≥ 0,2 słaba.",
        "",
        f"**Najsilniej skorelowane pary po czyszczeniu (top {top}):**",
        "",
        strongest_pairs_table(summary, top),
    ]
    if summary.pearson_before is not None:
        parts += [
            "",
            "**Jak czyszczenie zmieniło korelację** (największe zmiany współczynnika Pearsona):",
            "",
            changes_table(summary, top),
        ]
    parts += ["", "**Opis zależności (wygenerowany):**", "", correlation_conclusions(summary, top)]
    if chart_set.correlation_comment:
        parts += ["", f"**Interpretacja:** {chart_set.correlation_comment}"]
    parts += ["", f"> **Korelacja to nie przyczynowość.** {CAUSATION_WARNING}"]
    return "\n".join(parts)


def build_chart_report(source_name: str, before: pd.DataFrame, after: pd.DataFrame, results: list[ChartResult],
                       missing_image: str, summary: CorrelationSummary, chart_set: ChartSet) -> str:
    drawn = []
    for result in results:
        if not result.error:
            drawn.append(result)

    sections = [
        "# Raport wykresów (lab 7)",
        "",
        f"- Źródło: `{source_name}`",
        f"- Rekordy: {len(before)} przed czyszczeniem, {len(after)} po czyszczeniu",
        f"- Wykresy: {len(drawn)} narysowanych, {len(results) - len(drawn)} zablokowanych przez walidację",
        f"- Wygenerowano: {datetime.now().isoformat(timespec='seconds')}",
        "",
        "## Jak czytać wykresy",
        "",
        "- *Przed czyszczeniem* to dane surowe z pliku. Teksty w kolumnach liczbowych (np. `?`, `brak`) i puste "
        "komórki nie dają się narysować, więc są pominięte; ich liczba jest w tytule wykresu (`pominięto`).",
        "- *Po czyszczeniu* to dane z `cleaned.csv`.",
        "- Wykres pudełkowy: pudełko = kwartyle Q1–Q3, kreska = mediana, wąsy sięgają do 1,5 × IQR, "
        "a punkty poza wąsami to wartości odstające według tej samej reguły, którą wykrywa pipeline.",
        "- Skala logarytmiczna (tam, gdzie zaznaczono) pokazuje tylko wartości dodatnie.",
        "",
        "## 1. Braki danych przed i po czyszczeniu",
        "",
        f"![Braki danych]({missing_image})",
        "",
        "## 2. Wykresy",
        "",
    ]
    for number, result in enumerate(drawn, start=1):
        sections.append(chart_section(number, result))
        sections.append("")

    sections += [
        "## 3. Korelacja",
        "",
        correlation_section(summary, chart_set),
        "",
        "## 4. Wykresy zablokowane przez walidację",
        "",
        blocked_section(results),
        "",
    ]
    return "\n".join(sections)
