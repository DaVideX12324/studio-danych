"""Reguły jakości danych: zakres poprawnych wartości i wartości odstające (metoda IQR).

Funkcje z tego pliku tylko WYKRYWAJĄ problemy i zwracają maski (True = problem).
Niczego w danych nie zmieniają.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

# Co zrobić z wartością spoza zakresu:
#   flag - tylko oznacz w nowej kolumnie <kolumna>_poza_zakresem, dane bez zmian
#   nan  - zamień błędną wartość na brak (potem zajmą się nią strategie braków)
#   drop - usuń cały rekord
#   clip - przytnij wartość do granicy zakresu
RANGE_ACTIONS = ["flag", "nan", "drop", "clip"]


def require_columns(frame: pd.DataFrame, columns: list[str]) -> None:
    """Zgłasza czytelny błąd, jeśli którejś z kolumn nie ma w danych."""
    missing = []
    for column in columns:
        if column not in frame.columns:
            missing.append(column)
    if missing:
        available = ", ".join(str(column) for column in frame.columns)
        raise ValueError(f"Brak kolumn w danych: {', '.join(missing)}. Dostępne: {available}.")


def is_number(value: object) -> bool:
    # bool to w Pythonie podklasa int, a True jako granica zakresu nie ma sensu
    return isinstance(value, (int, float)) and not isinstance(value, bool)


@dataclass(frozen=True)
class RangeRule:
    """Zakres poprawnych wartości jednej kolumny i decyzja, co zrobić z wartościami spoza niego.

    include_min / include_max mówią, czy granica należy do zakresu (≤) czy nie (<).
    """

    column: str
    minimum: float | None = None
    maximum: float | None = None
    include_min: bool = True
    include_max: bool = True
    action: str = "flag"
    reason: str = ""

    def __post_init__(self) -> None:
        if self.minimum is not None and not is_number(self.minimum):
            raise ValueError(f"Reguła dla '{self.column}': min musi być liczbą, a jest {self.minimum!r}.")
        if self.maximum is not None and not is_number(self.maximum):
            raise ValueError(f"Reguła dla '{self.column}': max musi być liczbą, a jest {self.maximum!r}.")
        if self.minimum is None and self.maximum is None:
            raise ValueError(f"Reguła dla '{self.column}' musi mieć co najmniej jedną granicę (min albo max).")
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError(f"Reguła dla '{self.column}': min ({self.minimum}) jest większe niż max ({self.maximum}).")
        if self.action not in RANGE_ACTIONS:
            raise ValueError(
                f"Reguła dla '{self.column}': nieznana akcja '{self.action}'. Dostępne: {', '.join(RANGE_ACTIONS)}."
            )
        if self.action == "clip" and not self.has_closed_bounds():
            raise ValueError(f"Reguła dla '{self.column}': przycinanie (clip) wymaga granic z ≤, a nie <.")

    @classmethod
    def from_dict(cls, data: dict) -> RangeRule:
        """Tworzy regułę z wpisu w pliku konfiguracji (klucze: column, min, max, include_min, ...)."""
        if "column" not in data:
            raise ValueError(f"Reguła zakresu bez nazwy kolumny: {data}")
        return cls(
            column=data["column"],
            minimum=data.get("min"),
            maximum=data.get("max"),
            include_min=data.get("include_min", True),
            include_max=data.get("include_max", True),
            action=data.get("action", "flag"),
            reason=data.get("reason", ""),
        )

    def to_dict(self) -> dict:
        return {
            "column": self.column,
            "min": self.minimum,
            "max": self.maximum,
            "include_min": self.include_min,
            "include_max": self.include_max,
            "action": self.action,
        }

    def has_closed_bounds(self) -> bool:
        min_ok = self.minimum is None or self.include_min
        max_ok = self.maximum is None or self.include_max
        return min_ok and max_ok

    def describe(self) -> str:
        """Opis do raportu, np. "0 < MedInc ≤ 15.0001"."""
        text = self.column
        if self.minimum is not None:
            sign = "≤" if self.include_min else "<"
            text = f"{self.minimum:g} {sign} {text}"
        if self.maximum is not None:
            sign = "≤" if self.include_max else "<"
            text = f"{text} {sign} {self.maximum:g}"
        return text

    def violations(self, frame: pd.DataFrame) -> pd.Series:
        """Maska rekordów z wartością spoza zakresu.

        Braki (NaN) i tekst, którego nie da się zamienić na liczbę, NIE są naruszeniem
        (to osobne problemy, obsługiwane innymi krokami).
        """
        require_columns(frame, [self.column])
        values = pd.to_numeric(frame[self.column], errors="coerce")

        too_low = pd.Series(False, index=frame.index)
        if self.minimum is not None:
            if self.include_min:
                too_low = values < self.minimum
            else:
                too_low = values <= self.minimum

        too_high = pd.Series(False, index=frame.index)
        if self.maximum is not None:
            if self.include_max:
                too_high = values > self.maximum
            else:
                too_high = values >= self.maximum

        return too_low | too_high


def iqr_bounds(values: pd.Series, factor: float = 1.5) -> tuple[float, float] | None:
    """Granice metody IQR: [Q1 - factor * IQR, Q3 + factor * IQR], gdzie IQR = Q3 - Q1.

    Zwraca None, gdy w kolumnie nie ma liczb albo IQR = 0 (np. kolumna stała).
    Wtedy nie da się sensownie wskazać wartości odstających.
    """
    if factor <= 0:
        raise ValueError(f"Współczynnik IQR musi być dodatni, podano {factor}.")

    numbers = pd.to_numeric(values, errors="coerce").dropna()
    if numbers.empty:
        return None

    q1 = numbers.quantile(0.25)
    q3 = numbers.quantile(0.75)
    iqr = q3 - q1
    if iqr == 0:
        return None

    lower = q1 - factor * iqr
    upper = q3 + factor * iqr
    return float(lower), float(upper)


def iqr_mask(values: pd.Series, factor: float = 1.5) -> pd.Series:
    """Maska wartości odstających (True = poza granicami IQR). Braki nie są odstające."""
    bounds = iqr_bounds(values, factor)
    if bounds is None:
        return pd.Series(False, index=values.index)

    lower, upper = bounds
    numbers = pd.to_numeric(values, errors="coerce")
    return (numbers < lower) | (numbers > upper)
