"""Wykresy: histogram, punktowy, pudełkowy, słupkowy i mapa korelacji.

Wykres opisuje obiekt ChartSpec (rodzaj + kolumny + opcje), a build_figure(frame, spec) buduje
z niego wykres. Wynikiem jest matplotlib Figure (bez pyplot), więc ten sam wykres można zapisać
do pliku albo osadzić w oknie Tkinter przez FigureCanvasTkAgg.

Przed rysowaniem kolumny są sprawdzane. Zły typ kolumny, kolumna stała, pusta albo z za dużą
liczbą kategorii kończą się wyjątkiem ChartError z komunikatem, co wybrać zamiast.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, fields

import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from pandas.api.types import is_bool_dtype

from .correlation import METHODS, check_method, correlation_matrix
from .profiling import is_numeric_column, numeric_like_columns, text_tokens_in_column

CHART_KINDS = {
    "histogram": "histogram",
    "scatter": "wykres punktowy",
    "box": "wykres pudełkowy",
    "bar": "wykres słupkowy",
    "correlation": "mapa korelacji",
}

# Wykres słupkowy z większą liczbą kategorii przestaje być czytelny.
MAX_CATEGORIES = 20

# Domyślna liczba słupków histogramu: pierwiastek z liczby wartości, ale w granicach 10-60.
# (Automatyczne reguły numpy przy długim ogonie potrafią dać dziesiątki tysięcy słupków).
MIN_BINS = 10
MAX_BINS = 60

# Powyżej tylu kolumn liczby w komórkach mapy korelacji robią się nieczytelne.
MAX_ANNOTATED_COLUMNS = 12

MAIN_COLOR = "#3b6ea5"
BEFORE_COLOR = "#c8553d"
AFTER_COLOR = "#3b6ea5"


class ChartError(ValueError):
    """Wykresu nie da się narysować dla wybranych kolumn lub parametrów."""


# --- opis wykresu -------------------------------------------------------------------------------


@dataclass(frozen=True)
class ChartSpec:
    """Parametry jednego wykresu.

    x       histogram / box: kolumna liczbowa; bar: kolumna z kategoriami; scatter: oś X
    y       scatter: oś Y; bar: kolumna, której średnia jest wysokością słupka (brak = liczba rekordów)
    by      box: osobne pudełko dla każdej kategorii tej kolumny
    bins    histogram: liczba słupków; bar / box: podział liczbowej kolumny x / by na przedziały
    log_scale  skala logarytmiczna osi wartości (wartości <= 0 są wtedy pomijane)
    method  correlation: pearson albo spearman
    """

    kind: str
    x: str | None = None
    y: str | None = None
    by: str | None = None
    bins: int | None = None
    log_scale: bool = False
    method: str = "pearson"
    title: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in CHART_KINDS:
            raise ChartError(f"Nieznany rodzaj wykresu '{self.kind}'. Dostępne: {', '.join(CHART_KINDS)}.")
        if self.bins is not None:
            if isinstance(self.bins, bool) or not isinstance(self.bins, int) or self.bins < 2:
                raise ChartError(f"Liczba przedziałów (bins) musi być liczbą całkowitą >= 2, podano {self.bins!r}.")
        if self.kind == "correlation":
            try:
                check_method(self.method)
            except ValueError as error:
                raise ChartError(str(error)) from None
        self.check_required_columns()

    def check_required_columns(self) -> None:
        name = CHART_KINDS[self.kind]
        if self.kind in ("histogram", "box", "bar", "scatter") and not self.x:
            raise ChartError(f"Wybierz kolumnę dla wykresu: {name}.")
        if self.kind == "scatter":
            if not self.y:
                raise ChartError("Wykres punktowy wymaga dwóch kolumn: wybierz kolumnę dla osi Y.")
            if self.x == self.y:
                raise ChartError("Na osiach X i Y wykresu punktowego wybierz dwie różne kolumny.")

    @classmethod
    def from_dict(cls, data: dict) -> ChartSpec:
        known = set()
        for spec_field in fields(cls):
            known.add(spec_field.name)
        unknown = set(data) - known
        if unknown:
            raise ChartError(f"Nieznane parametry wykresu: {', '.join(sorted(unknown))}. "
                             f"Dostępne: {', '.join(sorted(known))}.")
        if "kind" not in data:
            raise ChartError("W opisie wykresu brakuje rodzaju (kind).")
        return cls(**data)

    def to_dict(self) -> dict:
        return asdict(self)

    def default_title(self) -> str:
        if self.kind == "histogram":
            return f"Rozkład wartości: {self.x}"
        if self.kind == "scatter":
            return f"{self.y} względem {self.x}"
        if self.kind == "box":
            if self.by:
                return f"Rozkład {self.x} w grupach {self.by}"
            return f"Rozkład i wartości odstające: {self.x}"
        if self.kind == "bar":
            if self.y:
                return f"Średnia {self.y} w grupach {self.x}"
            return f"Liczba rekordów w grupach {self.x}"
        return f"Korelacja {METHODS[self.method]}"

    def file_name(self) -> str:
        """Nazwa pliku bez rozszerzenia, np. 'scatter_MedInc_MedHouseVal'."""
        parts = [self.kind]
        for part in (self.x, self.y, self.by):
            if part:
                parts.append(part)
        if self.kind == "correlation":
            parts.append(self.method)
        if self.log_scale:
            parts.append("log")
        name = "_".join(parts)
        return re.sub(r"[^\w\-]+", "-", name)


# --- dobór kolumn -------------------------------------------------------------------------------


def numeric_chart_columns(frame: pd.DataFrame) -> list[str]:
    """Kolumny, które mogą być osią wartości: liczbowe (także z tekstowymi wtrętami) i niestałe."""
    result = []
    for column in numeric_like_columns(frame):
        values = pd.to_numeric(frame[column], errors="coerce")
        if values.nunique() >= 2:
            result.append(column)
    return result


def category_chart_columns(frame: pd.DataFrame) -> list[str]:
    """Kolumny, które mogą być kategoriami wykresu słupkowego bez dzielenia na przedziały."""
    result = []
    for column in frame.columns:
        count = frame[column].nunique(dropna=True)
        if 2 <= count <= MAX_CATEGORIES:
            result.append(column)
    return result


def require_column(frame: pd.DataFrame, column: str | None) -> pd.Series:
    if not column:
        raise ChartError("Nie wybrano kolumny.")
    if column not in frame.columns:
        available = ", ".join(str(name) for name in frame.columns)
        raise ChartError(f"Kolumny '{column}' nie ma w danych. Dostępne kolumny: {available}.")
    return frame[column]


def numeric_values(frame: pd.DataFrame, column: str | None, chart_name: str) -> pd.Series:
    """Liczbowe wartości kolumny (bez NaN). Błąd, jeśli kolumna nie nadaje się do wykresu."""
    series = require_column(frame, column)
    suggestion = ", ".join(numeric_chart_columns(frame)) or "brak"

    if is_bool_dtype(series):
        raise ChartError(
            f"Kolumna '{column}' ma tylko wartości prawda/fałsz, a {chart_name} wymaga kolumny liczbowej. "
            f"Dla takiej kolumny wybierz wykres słupkowy. Kolumny liczbowe: {suggestion}."
        )
    if not is_numeric_column(series) and not text_tokens_in_column(series):
        raise ChartError(
            f"Kolumna '{column}' jest tekstowa, a {chart_name} wymaga kolumny liczbowej. "
            f"Kolumny liczbowe: {suggestion}."
        )

    values = pd.to_numeric(series, errors="coerce").dropna()
    if values.empty:
        raise ChartError(f"Kolumna '{column}' nie ma żadnych wartości liczbowych.")
    if values.nunique() == 1:
        raise ChartError(
            f"Kolumna '{column}' jest stała (każda wartość = {values.iloc[0]:g}), więc {chart_name} "
            f"niczego nie pokaże. Wybierz inną kolumnę: {suggestion}."
        )
    return values


def positive_only(values: pd.Series, column: str) -> pd.Series:
    """Na skali logarytmicznej da się pokazać tylko wartości dodatnie."""
    positive = values[values > 0]
    if positive.nunique() < 2:
        raise ChartError(
            f"Kolumna '{column}' nie ma co najmniej dwóch różnych wartości dodatnich, "
            "więc skala logarytmiczna nie ma sensu. Wyłącz skalę logarytmiczną."
        )
    return positive


def category_values(frame: pd.DataFrame, column: str | None, bins: int | None) -> tuple[pd.Series, list[str]]:
    """Kategorie (jako tekst) dla każdego rekordu oraz ich kolejność na osi.

    Kolumna liczbowa z dużą liczbą różnych wartości musi zostać podzielona na przedziały (bins).
    """
    series = require_column(frame, column)
    if bins is not None:
        values = numeric_values(frame, column, "podział na przedziały")
        return split_into_bins(values, bins)

    present = series.dropna()
    count = present.nunique()
    if count < 2:
        raise ChartError(f"Kolumna '{column}' ma tylko jedną kategorię, więc nie ma czego porównywać.")
    if count > MAX_CATEGORIES:
        if is_numeric_column(series):
            raise ChartError(
                f"Kolumna liczbowa '{column}' ma {count} różnych wartości. Podaj liczbę przedziałów (bins), "
                "np. 5, albo wybierz kolumnę z kategoriami."
            )
        raise ChartError(
            f"Kolumna '{column}' ma {count} kategorii, a wykres jest czytelny do {MAX_CATEGORIES}. "
            f"Wybierz kolumnę z mniejszą liczbą kategorii: {', '.join(category_chart_columns(frame)) or 'brak'}."
        )

    if is_bool_dtype(series):
        labels = present.map({True: "tak", False: "nie"})
        return labels, ["nie", "tak"]

    if is_numeric_column(series):
        order = []
        for value in sorted(present.unique()):
            order.append(f"{value:g}")
        return present.map(lambda value: f"{value:g}"), order

    labels = present.astype(str)
    # Kategorie tekstowe od najliczniejszej.
    order = list(labels.value_counts().index)
    return labels, order


def split_into_bins(values: pd.Series, bins: int) -> tuple[pd.Series, list[str]]:
    """Dzieli wartości na przedziały równej szerokości, np. '1–11.2', '11.2–21.4'."""
    edges = np.linspace(values.min(), values.max(), bins + 1)
    order = bin_labels(edges)
    labels = pd.cut(values, bins=edges, labels=order, include_lowest=True).astype(str)
    return labels, order


def bin_labels(edges: np.ndarray) -> list[str]:
    """Etykiety przedziałów z 3 cyframi znaczącymi; więcej cyfr, gdy przy 3 etykiety by się powtórzyły."""
    for digits in (3, 6, 12):
        labels = []
        for position in range(len(edges) - 1):
            labels.append(f"{edges[position]:.{digits}g}–{edges[position + 1]:.{digits}g}")
        if len(set(labels)) == len(labels):
            return labels
    return labels


def default_bin_count(values: pd.Series) -> int:
    count = int(np.sqrt(len(values)))
    return max(MIN_BINS, min(MAX_BINS, count))


def format_count(number: int) -> str:
    """20244 -> '20 244'."""
    return f"{number:,}".replace(",", " ")


def sample_info(frame: pd.DataFrame, used: int) -> str:
    """Ile wartości jest na wykresie i ile pominięto (puste, tekstowe, niedodatnie na skali log)."""
    skipped = len(frame) - used
    if skipped == 0:
        return f"n = {format_count(used)}"
    return f"n = {format_count(used)}, pominięto {format_count(skipped)}"


# --- rysowanie na osiach ------------------------------------------------------------------------
# Każda funkcja draw_* sprawdza kolumny, rysuje na podanych osiach i zwraca krótki opis próbki
# (np. "n = 20 244"). Dzięki temu ten sam kod rysuje pojedynczy wykres i porównanie przed/po.


def draw_histogram(ax: Axes, frame: pd.DataFrame, spec: ChartSpec, color: str = MAIN_COLOR) -> str:
    values = numeric_values(frame, spec.x, "histogram")
    if spec.log_scale:
        values = positive_only(values, spec.x)

    bins = spec.bins or default_bin_count(values)
    sns.histplot(x=values, bins=bins, log_scale=spec.log_scale, color=color, ax=ax)
    ax.set_xlabel(axis_label(spec.x, spec.log_scale))
    ax.set_ylabel("Liczba rekordów")
    return sample_info(frame, len(values))


def draw_scatter(ax: Axes, frame: pd.DataFrame, spec: ChartSpec, color: str = MAIN_COLOR) -> str:
    x_values = numeric_values(frame, spec.x, "wykres punktowy")
    y_values = numeric_values(frame, spec.y, "wykres punktowy")
    if spec.log_scale:
        x_values = positive_only(x_values, spec.x)
        y_values = positive_only(y_values, spec.y)

    # Tylko rekordy, które mają obie wartości.
    points = pd.DataFrame({"x": x_values, "y": y_values}).dropna()
    if len(points) < 2:
        raise ChartError(f"Za mało rekordów z wartościami w obu kolumnach ({spec.x}, {spec.y}).")

    # Przy tysiącach punktów: małe, półprzezroczyste znaczniki (gęstość widać po kolorze).
    # rasterized=True: w PDF/SVG punkty są obrazkiem, więc plik nie ma 20 tysięcy obiektów.
    ax.scatter(points["x"], points["y"], s=6, alpha=0.3, color=color, edgecolors="none", rasterized=True)
    if spec.log_scale:
        ax.set_xscale("log")
        ax.set_yscale("log")
    ax.set_xlabel(axis_label(spec.x, spec.log_scale))
    ax.set_ylabel(axis_label(spec.y, spec.log_scale))

    r = points["x"].corr(points["y"])
    ax.text(0.02, 0.97, f"r Pearsona = {r:.2f}", transform=ax.transAxes, va="top",
            bbox={"boxstyle": "round", "facecolor": "white", "alpha": 0.8})
    return sample_info(frame, len(points))


def draw_boxes(ax: Axes, groups: dict[str, pd.Series], value_label: str, log_scale: bool,
               colors: list[str] | None = None) -> None:
    """Pudełka obok siebie, po jednym na grupę. Wąsy sięgają do 1,5 x IQR, jak metoda wykrywania outlierów."""
    labels = []
    data = []
    for name, values in groups.items():
        labels.append(f"{name}\n(n = {format_count(len(values))})")
        data.append(values.to_numpy())

    boxes = ax.boxplot(data, tick_labels=labels, whis=1.5, patch_artist=True,
                       flierprops={"marker": ".", "markersize": 3, "alpha": 0.4})
    for position, box in enumerate(boxes["boxes"]):
        color = MAIN_COLOR if colors is None else colors[position % len(colors)]
        box.set_facecolor(color)
        box.set_alpha(0.6)
    for median in boxes["medians"]:
        median.set_color("black")

    if log_scale:
        ax.set_yscale("log")
    ax.set_ylabel(axis_label(value_label, log_scale))


def draw_box(ax: Axes, frame: pd.DataFrame, spec: ChartSpec, color: str = MAIN_COLOR) -> str:
    values = numeric_values(frame, spec.x, "wykres pudełkowy")
    if spec.log_scale:
        values = positive_only(values, spec.x)

    if not spec.by:
        draw_boxes(ax, {spec.x: values}, spec.x, spec.log_scale, [color])
        return sample_info(frame, len(values))

    categories, order = category_values(frame, spec.by, spec.bins)
    # Tylko rekordy, które mają i wartość, i kategorię.
    joined = pd.DataFrame({"category": categories, "value": values}).dropna()
    groups = {}
    for name in order:
        in_group = joined.loc[joined["category"] == name, "value"]
        if not in_group.empty:
            groups[name] = in_group
    draw_boxes(ax, groups, spec.x, spec.log_scale, [color])
    ax.set_xlabel(category_label(spec.by, spec.bins))
    return sample_info(frame, len(joined))


def draw_bar(ax: Axes, frame: pd.DataFrame, spec: ChartSpec, color: str = MAIN_COLOR) -> str:
    categories, order = category_values(frame, spec.x, spec.bins)

    if spec.y:
        values = numeric_values(frame, spec.y, "wykres słupkowy (średnia)")
        joined = pd.DataFrame({"category": categories, "value": values}).dropna()
        heights = joined.groupby("category")["value"].mean()
        y_label = f"Średnia {spec.y}"
        used = len(joined)
    else:
        heights = categories.value_counts()
        y_label = "Liczba rekordów"
        used = len(categories)

    # Kolejność słupków jak w `order`; brak rekordów w kategorii = słupek 0 / pusty.
    heights = heights.reindex(order)
    positions = np.arange(len(order))
    bars = ax.bar(positions, heights.fillna(0).to_numpy(), color=color)
    ax.bar_label(bars, labels=bar_value_labels(heights), fontsize=8, padding=2)
    ax.set_xticks(positions, order, rotation=30 if len(order) > 6 else 0, ha="right" if len(order) > 6 else "center")
    ax.set_xlabel(category_label(spec.x, spec.bins))
    ax.set_ylabel(y_label)
    return sample_info(frame, used)


def bar_value_labels(heights: pd.Series) -> list[str]:
    labels = []
    for value in heights:
        if pd.isna(value):
            labels.append("")
        elif float(value).is_integer():
            labels.append(format_count(int(value)))
        else:
            labels.append(f"{value:.3g}")
    return labels


def draw_correlation(ax: Axes, frame: pd.DataFrame, spec: ChartSpec, color: str = MAIN_COLOR) -> str:
    try:
        matrix = correlation_matrix(frame, spec.method)
    except ValueError as error:
        raise ChartError(str(error)) from None

    annotate = len(matrix.columns) <= MAX_ANNOTATED_COLUMNS
    sns.heatmap(matrix, vmin=-1, vmax=1, center=0, cmap="RdBu_r", annot=annotate, fmt=".2f",
                annot_kws={"fontsize": 7}, square=True, linewidths=0.5, ax=ax,
                cbar_kws={"label": "współczynnik korelacji", "shrink": 0.8})
    ax.tick_params(axis="x", labelrotation=45)
    ax.tick_params(axis="y", labelrotation=0)
    return f"{len(matrix.columns)} kolumn liczbowych"


DRAWERS = {
    "histogram": draw_histogram,
    "scatter": draw_scatter,
    "box": draw_box,
    "bar": draw_bar,
    "correlation": draw_correlation,
}


def axis_label(column: str, log_scale: bool) -> str:
    if log_scale:
        return f"{column} (skala logarytmiczna)"
    return column


def category_label(column: str, bins: int | None) -> str:
    if bins:
        return f"{column} (przedziały)"
    return column


# --- gotowe wykresy (Figure) ----------------------------------------------------------------------


def build_figure(frame: pd.DataFrame, spec: ChartSpec) -> Figure:
    """Główna funkcja: wykres z parametrów. Błąd walidacji -> ChartError (nic nie jest rysowane)."""
    size = (8, 7) if spec.kind == "correlation" else (8, 4.8)
    figure = Figure(figsize=size, dpi=100, layout="constrained")
    ax = figure.add_subplot()

    info = DRAWERS[spec.kind](ax, frame, spec)
    ax.set_title(info, fontsize=9, color="dimgray")
    figure.suptitle(spec.title or spec.default_title(), fontsize=13)
    return figure


def build_comparison_figure(before: pd.DataFrame, after: pd.DataFrame, spec: ChartSpec) -> Figure:
    """Ten sam wykres dla danych przed i po czyszczeniu, obok siebie.

    Wykres pudełkowy bez grupowania rysuje oba pudełka na jednych osiach (wspólna skala).
    """
    if spec.kind == "box" and not spec.by:
        return box_comparison_figure(before, after, spec)

    size = (14, 6.5) if spec.kind == "correlation" else (13, 4.8)
    figure = Figure(figsize=size, dpi=100, layout="constrained")
    left, right = figure.subplots(1, 2)

    drawer = DRAWERS[spec.kind]
    info_before = drawer(left, before, spec, BEFORE_COLOR)
    info_after = drawer(right, after, spec, AFTER_COLOR)
    left.set_title(f"Przed czyszczeniem ({info_before})", fontsize=10)
    right.set_title(f"Po czyszczeniu ({info_after})", fontsize=10)
    figure.suptitle(spec.title or spec.default_title(), fontsize=13)
    return figure


def box_comparison_figure(before: pd.DataFrame, after: pd.DataFrame, spec: ChartSpec) -> Figure:
    values_before = numeric_values(before, spec.x, "wykres pudełkowy")
    values_after = numeric_values(after, spec.x, "wykres pudełkowy")
    if spec.log_scale:
        values_before = positive_only(values_before, spec.x)
        values_after = positive_only(values_after, spec.x)

    figure = Figure(figsize=(8, 4.8), dpi=100, layout="constrained")
    ax = figure.add_subplot()
    groups = {"przed czyszczeniem": values_before, "po czyszczeniu": values_after}
    draw_boxes(ax, groups, spec.x, spec.log_scale, [BEFORE_COLOR, AFTER_COLOR])

    skipped = len(before) - len(values_before)
    if skipped:
        ax.set_title(f"przed: pominięto {format_count(skipped)} wartości (puste, tekstowe"
                     f"{', niedodatnie' if spec.log_scale else ''})", fontsize=9, color="dimgray")
    figure.suptitle(spec.title or spec.default_title(), fontsize=13)
    return figure


def missing_values_figure(before: pd.DataFrame, after: pd.DataFrame) -> Figure:
    """Wykres słupkowy braków w każdej kolumnie: przed (NaN + teksty typu '?') i po czyszczeniu."""
    columns = []
    counts_before = []
    counts_after = []
    for column in before.columns:
        columns.append(str(column))
        missing = int(before[column].isna().sum())
        missing += sum(text_tokens_in_column(before[column]).values())
        counts_before.append(missing)
        if column in after.columns:
            counts_after.append(int(after[column].isna().sum()))
        else:
            counts_after.append(0)

    figure = Figure(figsize=(9, 4.8), dpi=100, layout="constrained")
    ax = figure.add_subplot()
    positions = np.arange(len(columns))
    width = 0.4
    bars_before = ax.bar(positions - width / 2, counts_before, width, label="przed czyszczeniem", color=BEFORE_COLOR)
    bars_after = ax.bar(positions + width / 2, counts_after, width, label="po czyszczeniu", color=AFTER_COLOR)
    ax.bar_label(bars_before, fontsize=8, padding=2)
    ax.bar_label(bars_after, fontsize=8, padding=2)

    rotate = len(columns) > 6
    ax.set_xticks(positions, columns, rotation=30 if rotate else 0, ha="right" if rotate else "center")
    ax.set_xlabel("Kolumna")
    ax.set_ylabel("Liczba brakujących wartości")
    # Miejsce nad słupkami na legendę.
    highest = max(counts_before + counts_after)
    ax.set_ylim(0, max(highest * 1.3, 1))
    ax.legend(loc="upper right", ncols=2)
    figure.suptitle("Braki danych w kolumnach przed i po czyszczeniu", fontsize=13)
    ax.set_title("przed: puste komórki i tekstowe oznaczenia braku (np. '?', 'brak')", fontsize=9, color="dimgray")
    return figure
