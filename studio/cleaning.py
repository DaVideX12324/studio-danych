"""Operacje czyszczenia danych.

Każda operacja:
- dostaje DataFrame i NIE zmienia go (pracuje na kopii),
- zwraca OpResult: nowe dane + opis, co i ile zmieniono.

Dzięki temu dane surowe zostają nietknięte, a operacja zakończona błędem
nie zostawia danych zmienionych w połowie.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .profiling import is_numeric_column, text_columns
from .rules import RangeRule, iqr_bounds, require_columns

FILL_STRATEGIES = ["mean", "median", "mode", "constant"]

# Co zrobić z wartościami odstającymi:
#   report - tylko policz, dane bez zmian
#   flag   - dodaj kolumnę <kolumna>_outlier z True/False
#   clip   - przytnij do granic IQR
#   drop   - usuń rekordy
OUTLIER_ACTIONS = ["report", "flag", "clip", "drop"]


@dataclass
class OpResult:
    frame: pd.DataFrame
    affected_rows: int  # ile rekordów operacja zmieniła, usunęła albo oznaczyła
    rows_removed: int = 0
    changed_cells: dict[str, int] = field(default_factory=dict)  # tylko istniejące kolumny
    added_columns: list[str] = field(default_factory=list)
    details: str = ""


def format_value(value: object) -> str:
    if isinstance(value, (float, np.floating)):
        return f"{value:.6g}"
    return repr(value)


# --- duplikaty ---------------------------------------------------------------------------


def drop_duplicates(frame: pd.DataFrame, subset: list[str] | None = None) -> OpResult:
    """Usuwa duplikaty i zostawia pierwsze wystąpienie.

    subset=None: tylko pełne duplikaty (wszystkie kolumny identyczne).
    subset=[...]: duplikaty względem podanego klucza.
    """
    if subset is None:
        key_description = "wszystkie kolumny"
    else:
        require_columns(frame, subset)
        key_description = ", ".join(subset)

    result = frame.drop_duplicates(subset=subset, keep="first").copy()
    removed = len(frame) - len(result)
    return OpResult(
        frame=result,
        affected_rows=removed,
        rows_removed=removed,
        details=f"klucz: {key_description}; usunięto {removed}",
    )


# --- tekstowe oznaczenia braku -------------------------------------------------------------


def normalize_missing_tokens(frame: pd.DataFrame, tokens: list[str]) -> OpResult:
    """Zamienia tekstowe oznaczenia braku (np. "?", "brak") na NaN.

    Porównanie ignoruje wielkość liter i spacje na brzegach.
    Jeśli po zamianie wszystkie niepuste wartości kolumny są liczbami,
    kolumna dostaje typ liczbowy.
    """
    wanted = set()
    for token in tokens:
        wanted.add(token.strip().lower())

    result = frame.copy()
    changed_cells = {}
    converted_columns = []
    affected_rows = pd.Series(False, index=frame.index)

    for column in text_columns(frame):
        series = result[column]
        normalized = series.astype("string").str.strip().str.lower()
        is_token = normalized.isin(wanted).fillna(False).astype(bool)
        if is_token.any():
            result[column] = series.mask(is_token)  # mask: True -> NaN
            changed_cells[column] = int(is_token.sum())
            affected_rows = affected_rows | is_token

        if all_values_are_numbers(result[column]):
            result[column] = pd.to_numeric(result[column])
            converted_columns.append(column)

    converted_text = ", ".join(converted_columns) if converted_columns else "brak"
    return OpResult(
        frame=result,
        affected_rows=int(affected_rows.sum()),
        changed_cells=changed_cells,
        details=f"tokeny: {sorted(wanted)}; zamienione na liczby: {converted_text}",
    )


def all_values_are_numbers(series: pd.Series) -> bool:
    present = series.dropna()
    if present.empty:
        return False
    as_numbers = pd.to_numeric(present, errors="coerce")
    return bool(as_numbers.notna().all())


# --- reguły zakresu ------------------------------------------------------------------------


def apply_range_rule(frame: pd.DataFrame, rule: RangeRule) -> OpResult:
    """Wykonuje akcję z reguły (flag / nan / drop / clip) na rekordach spoza zakresu."""
    column = rule.column
    is_bad = rule.violations(frame)
    count = int(is_bad.sum())
    details = f"{rule.describe()}: naruszeń {count}, akcja {rule.action}"
    result = frame.copy()

    if rule.action == "flag":
        flag_column = f"{column}_poza_zakresem"
        result[flag_column] = is_bad
        return OpResult(result, count, added_columns=[flag_column], details=details)

    if rule.action == "drop":
        result = result[~is_bad].copy()
        return OpResult(result, count, rows_removed=count, details=details)

    if rule.action == "nan":
        result.loc[is_bad, column] = np.nan
    else:  # clip
        numbers = pd.to_numeric(result[column], errors="coerce")
        result[column] = numbers.clip(lower=rule.minimum, upper=rule.maximum)

    changed = {column: count} if count > 0 else {}
    return OpResult(result, count, changed_cells=changed, details=details)


# --- braki -------------------------------------------------------------------------------


def drop_missing(frame: pd.DataFrame, columns: list[str]) -> OpResult:
    """Strategia braków 1: usuwa rekordy, które mają brak w którejkolwiek z podanych kolumn."""
    require_columns(frame, columns)
    has_missing = frame[columns].isna().any(axis=1)
    count = int(has_missing.sum())
    result = frame[~has_missing].copy()
    return OpResult(
        frame=result,
        affected_rows=count,
        rows_removed=count,
        details=f"kolumny: {', '.join(columns)}; usunięto {count}",
    )


def fill_missing(frame: pd.DataFrame, column: str, strategy: str, value: object = None) -> OpResult:
    """Strategia braków 2: uzupełnia braki w jednej kolumnie.

    mean, median - tylko kolumny liczbowe,
    mode         - najczęstsza wartość (liczby albo tekst),
    constant     - podana wartość `value`.
    """
    if strategy not in FILL_STRATEGIES:
        raise ValueError(f"Nieznana strategia uzupełniania '{strategy}'. Dostępne: {', '.join(FILL_STRATEGIES)}.")
    require_columns(frame, [column])
    series = frame[column]

    if strategy in ["mean", "median"] and not is_numeric_column(series):
        raise ValueError(
            f"Strategia '{strategy}' wymaga kolumny liczbowej, a '{column}' ma typ {series.dtype}. "
            "Użyj 'mode' albo 'constant'."
        )

    if strategy == "mean":
        fill_value = series.mean()
    elif strategy == "median":
        fill_value = series.median()
    elif strategy == "mode":
        most_common = series.mode(dropna=True)
        fill_value = most_common.iloc[0] if not most_common.empty else np.nan
    else:  # constant
        if value is None:
            raise ValueError("Strategia 'constant' wymaga podania wartości.")
        fill_value = value

    if pd.isna(fill_value):
        raise ValueError(f"Kolumna '{column}' nie ma żadnych wartości, nie da się wyznaczyć '{strategy}'.")

    count = int(series.isna().sum())
    result = frame.copy()
    result[column] = series.fillna(fill_value)
    changed = {column: count} if count > 0 else {}
    return OpResult(
        frame=result,
        affected_rows=count,
        changed_cells=changed,
        details=f"{strategy} = {format_value(fill_value)}; uzupełniono {count}",
    )


# --- wartości odstające --------------------------------------------------------------------


def handle_outliers(frame: pd.DataFrame, column: str, action: str = "flag", factor: float = 1.5) -> OpResult:
    """Wykrywa wartości odstające metodą IQR (granice liczone na bieżących danych) i wykonuje akcję."""
    if action not in OUTLIER_ACTIONS:
        raise ValueError(f"Nieznana akcja dla wartości odstających '{action}'. Dostępne: {', '.join(OUTLIER_ACTIONS)}.")
    require_columns(frame, [column])

    bounds = iqr_bounds(frame[column], factor)
    if bounds is None:
        # Np. kolumna stała: nie da się wyznaczyć granic, więc nic nie robimy.
        return OpResult(frame.copy(), 0, details="IQR = 0 albo brak liczb, pominięto")

    lower, upper = bounds
    numbers = pd.to_numeric(frame[column], errors="coerce")
    is_outlier = (numbers < lower) | (numbers > upper)
    count = int(is_outlier.sum())
    details = f"IQR x {factor:g}: granice [{lower:.4g}, {upper:.4g}], wykryto {count}, akcja {action}"
    result = frame.copy()

    if action == "report":
        return OpResult(result, count, details=details)

    if action == "flag":
        flag_column = f"{column}_outlier"
        result[flag_column] = is_outlier
        return OpResult(result, count, added_columns=[flag_column], details=details)

    if action == "drop":
        result = result[~is_outlier].copy()
        return OpResult(result, count, rows_removed=count, details=details)

    # clip
    result[column] = numbers.clip(lower=lower, upper=upper)
    changed = {column: count} if count > 0 else {}
    return OpResult(result, count, changed_cells=changed, details=details)


# Nazwy operacji dostępnych w sesji i w pliku konfiguracji.
OPERATIONS = {
    "drop_duplicates": drop_duplicates,
    "normalize_missing_tokens": normalize_missing_tokens,
    "apply_range_rule": apply_range_rule,
    "drop_missing": drop_missing,
    "fill_missing": fill_missing,
    "handle_outliers": handle_outliers,
}
