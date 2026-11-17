"""Pipeline czyszczenia zapisany w pliku JSON.

Plik konfiguracji opisuje decyzje (reguły, strategie) i kolejność kroków, więc da się
go pokazać, uzasadnić i zmienić bez ruszania kodu.

Zamiast listy kolumn można wpisać nazwę grupy:
    "numeric" - wszystkie kolumny liczbowe,
    "text"    - wszystkie kolumny tekstowe.
Grupy są rozwijane w chwili wykonania kroku, więc ta sama konfiguracja działa
dla dowolnego pliku CSV (np. config/domyslna.json).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from .cleaning import OPERATIONS
from .profiling import numeric_columns, numeric_like_columns, text_columns
from .rules import RangeRule
from .session import AuditEntry, DataSession

COLUMN_GROUPS = ["numeric", "text"]


@dataclass
class PipelineConfig:
    missing_tokens: list[str] = field(default_factory=list)
    range_rules: list[RangeRule] = field(default_factory=list)
    outlier_columns: str | list[str] = "numeric"
    iqr_factor: float = 1.5
    steps: list[dict] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> PipelineConfig:
        rules = []
        for rule_data in data.get("range_rules", []):
            rules.append(RangeRule.from_dict(rule_data))

        outliers = data.get("outliers", {})
        return cls(
            missing_tokens=list(data.get("missing_tokens", [])),
            range_rules=rules,
            outlier_columns=outliers.get("columns", "numeric"),
            iqr_factor=float(outliers.get("factor", 1.5)),
            steps=list(data.get("steps", [])),
        )

    @classmethod
    def from_json(cls, path: str | Path) -> PipelineConfig:
        try:
            text = Path(path).read_text(encoding="utf-8")
            data = json.loads(text)
        except OSError as error:
            raise ValueError(f"Nie można odczytać konfiguracji {path}: {error}") from error
        except json.JSONDecodeError as error:
            raise ValueError(f"Błąd składni JSON w {path}: {error}") from error
        return cls.from_dict(data)


def resolve_columns(spec: str | list[str], frame: pd.DataFrame) -> list[str]:
    """Zamienia "numeric" / "text" na listę kolumn. Listę zwraca bez zmian."""
    if spec == "numeric":
        return numeric_columns(frame)
    if spec == "text":
        return text_columns(frame)
    if isinstance(spec, str):
        raise ValueError(f"Nieznana grupa kolumn '{spec}'. Dostępne: {', '.join(COLUMN_GROUPS)} albo lista nazw.")
    return list(spec)


def outlier_columns_for_diagnosis(config: PipelineConfig, frame: pd.DataFrame) -> list[str]:
    """Kolumny do sprawdzenia metodą IQR w diagnozie.

    W danych surowych kolumna z wtrętem "?" jest jeszcze tekstowa, dlatego "numeric"
    obejmuje tu także kolumny liczbowe z tekstowymi wtrętami.
    """
    if config.outlier_columns == "numeric":
        return numeric_like_columns(frame)
    return resolve_columns(config.outlier_columns, frame)


def columns_used_by_config(config: PipelineConfig) -> list[str]:
    """Nazwy kolumn wpisane wprost w konfiguracji (bez grup "numeric"/"text")."""
    used = []
    for rule in config.range_rules:
        used.append(rule.column)
    if isinstance(config.outlier_columns, list):
        used.extend(config.outlier_columns)
    for step in config.steps:
        columns = step.get("params", {}).get("columns")
        if isinstance(columns, list):
            used.extend(columns)
    return used


def check_config_matches_data(config: PipelineConfig, frame: pd.DataFrame) -> None:
    """Sprawdza przed startem, czy kolumny z konfiguracji istnieją w pliku."""
    missing = []
    for column in columns_used_by_config(config):
        if column not in frame.columns and column not in missing:
            missing.append(column)
    if missing:
        raise ValueError(
            f"Konfiguracja odwołuje się do kolumn, których nie ma w pliku: {', '.join(missing)}. "
            "Użyj konfiguracji przygotowanej dla tego pliku albo domyślnej (config/domyslna.json)."
        )


def run_pipeline(session: DataSession, config: PipelineConfig) -> list[AuditEntry]:
    """Wykonuje kroki z konfiguracji po kolei. Zwraca wpisy dziennika."""
    check_config_matches_data(config, session.current)

    entries = []
    for step in config.steps:
        new_entries = run_step(session, config, step)
        entries.extend(new_entries)
    return entries


def run_step(session: DataSession, config: PipelineConfig, step: dict) -> list[AuditEntry]:
    """Jeden krok z pliku konfiguracji. Kroki zbiorcze dają kilka wpisów dziennika (np. jeden na kolumnę)."""
    operation = step["op"]
    params = dict(step.get("params", {}))
    reason = step.get("why", "")
    entries = []

    if operation == "missing_tokens":
        entry = session.apply("normalize_missing_tokens", reason, tokens=config.missing_tokens)
        entries.append(entry)

    elif operation == "range_rules":
        for rule in config.range_rules:
            entry = session.apply("apply_range_rule", reason, rule=rule)
            entries.append(entry)

    elif operation == "fill_missing":
        columns = columns_to_fill(params.pop("columns"), session.current)
        for column in columns:
            entry = session.apply("fill_missing", reason, column=column, **params)
            entries.append(entry)

    elif operation == "outliers":
        action = params.get("action", "flag")
        for column in resolve_columns(config.outlier_columns, session.current):
            entry = session.apply("handle_outliers", reason, column=column, action=action, factor=config.iqr_factor)
            entries.append(entry)

    elif operation in OPERATIONS:
        entry = session.apply(operation, reason, **params)
        entries.append(entry)

    else:
        raise ValueError(f"Nieznany krok w konfiguracji: '{operation}'.")

    return entries


def columns_to_fill(spec: str | list[str], frame: pd.DataFrame) -> list[str]:
    """Kolumny do uzupełnienia braków.

    Przy grupie ("numeric"/"text") bierzemy tylko kolumny, które mają braki, ale nie są całe puste
    (z pustej kolumny nie da się policzyć mediany ani dominanty). Jawną listę zwracamy bez zmian.
    """
    columns = resolve_columns(spec, frame)
    if not isinstance(spec, str):
        return columns

    result = []
    for column in columns:
        missing = frame[column].isna().sum()
        if 0 < missing < len(frame):
            result.append(column)
    return result
