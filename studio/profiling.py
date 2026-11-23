"""Profil danych i diagnoza problemów jakości. Tylko odczyt, nic nie zmienia."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from pandas.api.types import is_bool_dtype, is_numeric_dtype

from .rules import RangeRule, iqr_bounds, iqr_mask

# Kolumna tekstowa jest traktowana jako "liczbowa z wtrętami" (np. "?", "brak"),
# jeśli co najmniej taka część jej niepustych wartości to liczby.
NUMERIC_SHARE_THRESHOLD = 0.8


# --- typy kolumn ------------------------------------------------------------------------


def is_numeric_column(series: pd.Series) -> bool:
    # Kolumny True/False (np. oznaczenia *_outlier) nie są dla nas liczbowe.
    return is_numeric_dtype(series) and not is_bool_dtype(series)


def numeric_columns(frame: pd.DataFrame) -> list[str]:
    """Kolumny, które już mają typ liczbowy."""
    result = []
    for column in frame.columns:
        if is_numeric_column(frame[column]):
            result.append(column)
    return result


def text_columns(frame: pd.DataFrame) -> list[str]:
    """Kolumny tekstowe (bez kolumn True/False)."""
    result = []
    for column in frame.columns:
        series = frame[column]
        if not is_numeric_dtype(series) and not is_bool_dtype(series):
            result.append(column)
    return result


def text_tokens_in_column(series: pd.Series) -> dict[str, int]:
    """Teksty w kolumnie, która poza nimi zawiera liczby. Zwraca {tekst: liczba wystąpień}.

    Pusty słownik, jeśli kolumna jest liczbowa albo to zwykła kolumna tekstowa.
    """
    if is_numeric_dtype(series) or is_bool_dtype(series):
        return {}

    present = series.dropna()
    if present.empty:
        return {}

    as_numbers = pd.to_numeric(present, errors="coerce")
    numeric_share = as_numbers.notna().mean()
    if numeric_share < NUMERIC_SHARE_THRESHOLD or numeric_share == 1:
        return {}

    not_numbers = present[as_numbers.isna()].astype(str)
    tokens = {}
    for token, count in not_numbers.value_counts().items():
        tokens[token] = int(count)
    return tokens


def find_text_tokens(frame: pd.DataFrame) -> dict[str, dict[str, int]]:
    """Dla każdej kolumny "liczbowej z wtrętami": {kolumna: {tekst: liczba wystąpień}}."""
    found = {}
    for column in frame.columns:
        tokens = text_tokens_in_column(frame[column])
        if tokens:
            found[column] = tokens
    return found


IDENTIFIER_NAMES = {"id", "lp", "nr", "index", "unnamed: 0"}


def looks_like_identifier(column: object) -> bool:
    """Kolumna z numerem rekordu (id, lp, klient_id, ...). Rozpoznawana tylko po nazwie.

    Takie liczby niczego nie mierzą, więc automatycznie dobierane wykresy i analiza korelacji je pomijają.
    """
    name = str(column).strip().lower()
    return name in IDENTIFIER_NAMES or name.endswith("_id") or name.startswith("id_")


def numeric_like_columns(frame: pd.DataFrame) -> list[str]:
    """Kolumny liczbowe oraz liczbowe z tekstowymi wtrętami (np. w danych surowych)."""
    result = []
    for column in frame.columns:
        series = frame[column]
        if is_numeric_column(series) or text_tokens_in_column(series):
            result.append(column)
    return result


# --- profil -----------------------------------------------------------------------------


@dataclass
class DataProfile:
    n_rows: int
    n_cols: int
    duplicate_rows: int
    columns: pd.DataFrame  # jeden wiersz na kolumnę: dtype, missing, missing_pct, unique
    stats: pd.DataFrame  # statystyki opisowe kolumn liczbowych


def profile_frame(frame: pd.DataFrame) -> DataProfile:
    columns = pd.DataFrame(
        {
            "dtype": frame.dtypes.astype(str),
            "missing": frame.isna().sum(),
            "missing_pct": (frame.isna().mean() * 100).round(2),
            "unique": frame.nunique(dropna=True),
        }
    )

    numeric_part = frame[numeric_columns(frame)]
    if numeric_part.columns.empty:
        stats = pd.DataFrame()
    else:
        stats = numeric_part.describe().T

    return DataProfile(
        n_rows=len(frame),
        n_cols=frame.shape[1],
        duplicate_rows=int(frame.duplicated().sum()),
        columns=columns,
        stats=stats,
    )


# --- diagnoza ---------------------------------------------------------------------------


@dataclass
class OutlierInfo:
    bounds: tuple[float, float] | None
    count: int  # poza granicami IQR x 1.5 (albo innym współczynnikiem)
    extreme_count: int  # poza granicami IQR x 3


@dataclass
class Diagnosis:
    rows: int
    duplicate_rows: int
    missing: dict[str, int]  # liczba NaN w każdej kolumnie
    text_tokens: dict[str, dict[str, int]]
    range_violations: dict[str, int]  # opis reguły -> liczba rekordów
    outliers: dict[str, OutlierInfo]
    flagged_outliers: dict[str, int]  # kolumny *_outlier dodane przy czyszczeniu -> liczba True

    def missing_total(self) -> int:
        return sum(self.missing.values())

    def tokens_total(self) -> int:
        total = 0
        for tokens in self.text_tokens.values():
            total += sum(tokens.values())
        return total

    def violations_total(self) -> int:
        return sum(self.range_violations.values())

    def outliers_total(self) -> int:
        total = 0
        for info in self.outliers.values():
            total += info.count
        return total


def diagnose(
    frame: pd.DataFrame,
    rules: list[RangeRule],
    outlier_columns: list[str],
    factor: float = 1.5,
) -> Diagnosis:
    """Zbiera wszystkie wykryte problemy. Reguły dla nieistniejących kolumn są pomijane."""
    range_violations = {}
    for rule in rules:
        if rule.column in frame.columns:
            range_violations[rule.describe()] = int(rule.violations(frame).sum())

    outliers = {}
    for column in outlier_columns:
        if column in frame.columns:
            values = frame[column]
            outliers[column] = OutlierInfo(
                bounds=iqr_bounds(values, factor),
                count=int(iqr_mask(values, factor).sum()),
                extreme_count=int(iqr_mask(values, 3.0).sum()),
            )

    flagged_outliers = {}
    for column in frame.columns:
        if str(column).endswith("_outlier") and is_bool_dtype(frame[column]):
            flagged_outliers[column] = int(frame[column].sum())

    missing = {}
    for column, count in frame.isna().sum().items():
        missing[column] = int(count)

    return Diagnosis(
        rows=len(frame),
        duplicate_rows=int(frame.duplicated().sum()),
        missing=missing,
        text_tokens=find_text_tokens(frame),
        range_violations=range_violations,
        outliers=outliers,
        flagged_outliers=flagged_outliers,
    )
