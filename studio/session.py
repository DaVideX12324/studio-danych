"""Sesja pracy z danymi.

Sesja trzyma:
- raw:       dane surowe, dokładnie takie jak w pliku (nigdy nie są zmieniane),
- current:   dane po dotychczasowych operacjach,
- audit_log: dziennik operacji (ślad zmian).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

import pandas as pd

from .cleaning import OPERATIONS
from .loader import LoadInfo, load_csv
from .profiling import DataProfile, profile_frame
from .rules import RangeRule


@dataclass
class AuditEntry:
    """Jeden wpis dziennika: co zrobiono, z jakimi parametrami i ile rekordów to dotknęło."""

    step: int
    operation: str
    params: dict
    timestamp: str
    rows_before: int
    rows_after: int
    affected_rows: int = 0
    changed_cells: dict = field(default_factory=dict)
    added_columns: list = field(default_factory=list)
    details: str = ""
    reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DataSession:
    raw: pd.DataFrame
    source: LoadInfo | None = None
    current: pd.DataFrame = field(init=False)
    audit_log: list[AuditEntry] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.raw.empty:
            raise ValueError("Zbiór danych jest pusty.")
        # Własne kopie: zmiany w DataFrame przekazanym z zewnątrz nie dotkną sesji.
        self.raw = self.raw.copy(deep=True)
        self.current = self.raw.copy(deep=True)

    @classmethod
    def from_csv(cls, path: str | Path, **load_options) -> DataSession:
        frame, info = load_csv(path, **load_options)
        return cls(frame, info)

    def profile(self) -> DataProfile:
        return profile_frame(self.current)

    def raw_profile(self) -> DataProfile:
        return profile_frame(self.raw)

    def apply(self, operation: str, reason: str = "", **params) -> AuditEntry:
        """Wykonuje operację na danych bieżących i dopisuje ją do dziennika.

        Jeśli operacja zgłosi błąd, dane bieżące i dziennik zostają bez zmian.
        """
        if operation not in OPERATIONS:
            raise ValueError(f"Nieznana operacja '{operation}'. Dostępne: {', '.join(OPERATIONS)}.")

        function = OPERATIONS[operation]
        rows_before = len(self.current)
        result = function(self.current, **params)
        self.current = result.frame

        entry = self._new_entry(operation, params_for_log(params), rows_before)
        entry.affected_rows = result.affected_rows
        entry.changed_cells = result.changed_cells
        entry.added_columns = result.added_columns
        entry.details = result.details
        entry.reason = reason
        self.audit_log.append(entry)
        return entry

    def reset(self) -> AuditEntry:
        """Wraca do danych surowych bez ponownego wczytywania pliku."""
        rows_before = len(self.current)
        self.current = self.raw.copy(deep=True)

        entry = self._new_entry("reset", {}, rows_before)
        entry.details = "przywrócono dane surowe"
        self.audit_log.append(entry)
        return entry

    def _new_entry(self, operation: str, params: dict, rows_before: int) -> AuditEntry:
        return AuditEntry(
            step=len(self.audit_log) + 1,
            operation=operation,
            params=params,
            timestamp=datetime.now().isoformat(timespec="seconds"),
            rows_before=rows_before,
            rows_after=len(self.current),
        )


def params_for_log(params: dict) -> dict:
    """Parametry w postaci, którą da się zapisać do JSON (reguła -> słownik)."""
    result = {}
    for name, value in params.items():
        if isinstance(value, RangeRule):
            result[name] = value.to_dict()
        else:
            result[name] = value
    return result
