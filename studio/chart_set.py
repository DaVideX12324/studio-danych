"""Zestaw wykresów do raportu: z pliku JSON albo dobrany automatycznie dla dowolnego CSV."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from .charts import ChartSpec, category_chart_columns, numeric_chart_columns
from .correlation import correlation_columns, correlation_matrix, strongest_pairs
from .profiling import is_numeric_column, looks_like_identifier

# Przy automatycznym doborze: histogram i wykres pudełkowy dla najwyżej tylu kolumn liczbowych.
MAX_AUTO_COLUMNS = 8
MAX_AUTO_SCATTERS = 3
MAX_AUTO_BARS = 3


@dataclass
class PlannedChart:
    spec: ChartSpec
    compare: bool = False  # True: dane przed i po czyszczeniu obok siebie
    comment: str = ""  # opis / wniosek, który trafia do raportu pod wykresem

    @classmethod
    def from_dict(cls, data: dict) -> PlannedChart:
        spec_data = dict(data)
        compare = spec_data.pop("compare", False)
        comment = spec_data.pop("comment", "")
        return cls(ChartSpec.from_dict(spec_data), bool(compare), str(comment))


@dataclass
class ChartSet:
    charts: list[PlannedChart] = field(default_factory=list)
    correlation_top: int = 5  # ile najsilniej skorelowanych par opisać w raporcie
    correlation_comment: str = ""  # własna interpretacja korelacji do raportu

    @classmethod
    def from_dict(cls, data: dict) -> ChartSet:
        charts = []
        for position, chart_data in enumerate(data.get("charts", []), start=1):
            try:
                charts.append(PlannedChart.from_dict(chart_data))
            except (ValueError, TypeError) as error:
                raise ValueError(f"Wykres nr {position} w konfiguracji: {error}") from None
        return cls(
            charts=charts,
            correlation_top=int(data.get("correlation_top", 5)),
            correlation_comment=str(data.get("correlation_comment", "")),
        )

    @classmethod
    def from_json(cls, path: str | Path) -> ChartSet:
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise ValueError(f"Nie znaleziono pliku z wykresami: {path}") from None
        except json.JSONDecodeError as error:
            raise ValueError(f"Plik {path} nie jest poprawnym JSON-em: {error}") from None
        return cls.from_dict(data)


def default_chart_set(before: pd.DataFrame, after: pd.DataFrame) -> ChartSet:
    """Zestaw dla dowolnego pliku: dobór kolumn wynika tylko z ich typów w danych."""
    # Kolumny dodane przy czyszczeniu (np. *_outlier) nie mają wersji "przed",
    # a numer rekordu (id, lp) nie jest wielkością, którą warto rysować.
    numeric = []
    for column in numeric_chart_columns(after):
        if column in before.columns and not looks_like_identifier(column):
            numeric.append(column)
    numeric = numeric[:MAX_AUTO_COLUMNS]

    charts = []
    for column in numeric:
        charts.append(PlannedChart(ChartSpec("histogram", x=column), compare=True))
    for column in numeric:
        charts.append(PlannedChart(ChartSpec("box", x=column), compare=True))

    pairs = []
    if len(correlation_columns(after)) >= 2:
        pairs = strongest_pairs(correlation_matrix(after), MAX_AUTO_SCATTERS)
    for pair in pairs:
        charts.append(PlannedChart(ChartSpec("scatter", x=pair.first, y=pair.second), compare=True))

    charts.extend(default_bar_charts(before, after, numeric, pairs))

    if pairs:
        charts.append(PlannedChart(ChartSpec("correlation", method="pearson"), compare=True))
        charts.append(PlannedChart(ChartSpec("correlation", method="spearman")))
    return ChartSet(charts=charts)


def default_bar_charts(before: pd.DataFrame, after: pd.DataFrame, numeric: list[str], pairs: list) -> list[PlannedChart]:
    """Słupki dla kolumn z kategoriami; gdy ich nie ma, średnia jednej kolumny w przedziałach drugiej."""
    charts = []
    for column in category_chart_columns(after):
        is_original_text = column in before.columns and not is_numeric_column(after[column])
        if is_original_text and len(charts) < MAX_AUTO_BARS:
            charts.append(PlannedChart(ChartSpec("bar", x=column)))
    if charts:
        return charts

    if pairs:
        pair = pairs[0]
        return [PlannedChart(ChartSpec("bar", x=pair.first, y=pair.second, bins=5))]
    if numeric:
        return [PlannedChart(ChartSpec("bar", x=numeric[0], bins=5))]
    return []
