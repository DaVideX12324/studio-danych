"""Korelacja między kolumnami liczbowymi i jej słowny opis.

Korelacja mówi tylko tyle, że dwie wielkości zmieniają się razem. Nie mówi, która z nich wpływa
na drugą ani czy którakolwiek wpływa: obie mogą zależeć od trzeciego czynnika, związek może wynikać
ze sposobu zebrania danych albo z przypadku. Dlatego opisy z tego modułu mówią o współwystępowaniu,
nigdy o przyczynie.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .profiling import looks_like_identifier, numeric_like_columns

METHODS = {
    "pearson": "Pearsona (zależność liniowa)",
    "spearman": "Spearmana (zależność monotoniczna, odporna na wartości odstające)",
}

CAUSATION_WARNING = (
    "Korelacja opisuje współzmienność, a nie przyczynę. Silna korelacja dwóch kolumn nie oznacza, "
    "że jedna wpływa na drugą: obie mogą zależeć od trzeciego czynnika (np. położenia dzielnicy), "
    "a związek może też wynikać z definicji kolumn albo ze sposobu zebrania danych. "
    "Żeby mówić o przyczynie, potrzebny jest eksperyment albo model uwzględniający inne czynniki."
)

# Progi siły zależności (|r|). To umowna, często stosowana skala, a nie twarda reguła.
STRENGTH_LEVELS = [
    (0.8, "bardzo silna"),
    (0.6, "silna"),
    (0.4, "umiarkowana"),
    (0.2, "słaba"),
    (0.0, "bardzo słaba lub brak"),
]


@dataclass
class CorrelationPair:
    first: str
    second: str
    value: float


@dataclass
class CorrelationChange:
    first: str
    second: str
    before: float
    after: float

    def difference(self) -> float:
        return self.after - self.before


def check_method(method: str) -> None:
    if method not in METHODS:
        raise ValueError(f"Nieznana metoda korelacji '{method}'. Dostępne: {', '.join(METHODS)}.")


def correlation_columns(frame: pd.DataFrame) -> list[str]:
    """Kolumny, dla których korelacja ma sens: liczbowe (także z tekstowymi wtrętami), niestałe
    i niebędące identyfikatorem rekordu (id, lp, ...)."""
    result = []
    for column in numeric_like_columns(frame):
        if looks_like_identifier(column):
            continue
        values = pd.to_numeric(frame[column], errors="coerce")
        if values.nunique() >= 2:
            result.append(column)
    return result


def correlation_matrix(frame: pd.DataFrame, method: str = "pearson") -> pd.DataFrame:
    """Macierz korelacji kolumn liczbowych. Teksty w kolumnach liczbowych są pomijane (NaN)."""
    check_method(method)
    columns = correlation_columns(frame)
    if len(columns) < 2:
        raise ValueError(
            "Do korelacji potrzebne są co najmniej dwie kolumny liczbowe, które nie są stałe. "
            f"W danych są: {', '.join(columns) or 'brak'}."
        )

    numbers = pd.DataFrame(index=frame.index)
    for column in columns:
        numbers[column] = pd.to_numeric(frame[column], errors="coerce")
    return numbers.corr(method=method)


def all_pairs(matrix: pd.DataFrame) -> list[CorrelationPair]:
    """Każda para kolumn raz (bez przekątnej i bez powtórzeń A-B / B-A)."""
    pairs = []
    columns = list(matrix.columns)
    for position, first in enumerate(columns):
        for second in columns[position + 1:]:
            value = matrix.loc[first, second]
            if pd.notna(value):
                pairs.append(CorrelationPair(first, second, float(value)))
    return pairs


def strongest_pairs(matrix: pd.DataFrame, top: int = 5) -> list[CorrelationPair]:
    pairs = all_pairs(matrix)
    pairs.sort(key=lambda pair: abs(pair.value), reverse=True)
    return pairs[:top]


def biggest_changes(before: pd.DataFrame, after: pd.DataFrame, top: int = 5) -> list[CorrelationChange]:
    """Pary kolumn, których korelacja najbardziej zmieniła się po czyszczeniu."""
    changes = []
    for pair in all_pairs(after):
        if pair.first in before.columns and pair.second in before.columns:
            value_before = before.loc[pair.first, pair.second]
            if pd.notna(value_before):
                changes.append(CorrelationChange(pair.first, pair.second, float(value_before), pair.value))
    changes.sort(key=lambda change: abs(change.difference()), reverse=True)
    return changes[:top]


def strength_label(value: float) -> str:
    size = abs(value)
    for threshold, label in STRENGTH_LEVELS:
        if size >= threshold:
            return label
    return STRENGTH_LEVELS[-1][1]


def describe_pair(pair: CorrelationPair) -> str:
    """Opis jednej pary bez sugerowania przyczyny, np. 'MedInc i MedHouseVal: r = 0.69, silna dodatnia...'"""
    strength = strength_label(pair.value)
    text = f"{pair.first} i {pair.second}: r = {pair.value:.2f}, zależność {strength}"

    if abs(pair.value) < 0.2:
        return text + "; wartości tych kolumn praktycznie nie zmieniają się razem."
    if pair.value > 0:
        return text + f" dodatnia; rekordy z wyższym {pair.first} mają zwykle także wyższe {pair.second}."
    return text + f" ujemna; rekordy z wyższym {pair.first} mają zwykle niższe {pair.second}."
