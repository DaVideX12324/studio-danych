"""Raport przed/po czyszczeniu w formacie Markdown."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from .pipeline import PipelineConfig
from .profiling import DataProfile, Diagnosis
from .session import AuditEntry, DataSession

SEPARATOR_NAMES = {",": "przecinek", ";": "średnik", "\t": "tabulator"}


# --- pomocnicze -------------------------------------------------------------------------


def format_cell(value: object) -> str:
    if isinstance(value, float):
        text = f"{value:.4g}"
    else:
        text = str(value)
    # "|" rozbiłby tabelę Markdown
    return text.replace("|", "\\|").replace("\n", " ")


def markdown_table(headers: list[str], rows: list[list]) -> str:
    lines = []
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("|" + " --- |" * len(headers))
    for row in rows:
        cells = []
        for value in row:
            cells.append(format_cell(value))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


# --- sekcje raportu ---------------------------------------------------------------------


def source_section(session: DataSession, cleaned_name: str, cleaned_sha256: str) -> str:
    lines = []
    info = session.source
    if info is not None:
        separator = SEPARATOR_NAMES.get(info.separator, repr(info.separator))
        lines.append(
            f"- Źródło: `{Path(info.path).name}` (kodowanie {info.encoding}, separator: {separator}, "
            f"separator dziesiętny '{info.decimal}', pominięte wadliwe wiersze: {info.skipped_lines})"
        )
    lines.append(f"- Wynik: `{cleaned_name}` (SHA-256 `{cleaned_sha256}`)")
    lines.append(f"- Wygenerowano: {datetime.now().isoformat(timespec='seconds')}")
    return "\n".join(lines)


def summary_section(before: Diagnosis, after: Diagnosis, columns_before: int, columns_after: int) -> str:
    flagged = sum(after.flagged_outliers.values())
    rows = [
        ["Rekordy", before.rows, after.rows],
        ["Kolumny", columns_before, columns_after],
        ["Pełne duplikaty", before.duplicate_rows, after.duplicate_rows],
        ["Puste komórki (NaN)", before.missing_total(), after.missing_total()],
        ["Tekstowe oznaczenia braku w kolumnach liczbowych", before.tokens_total(), after.tokens_total()],
        ["Wartości spoza zakresu (suma po regułach)", before.violations_total(), after.violations_total()],
        ["Wartości odstające IQR (suma po kolumnach)", before.outliers_total(), after.outliers_total()],
        ["Oznaczone jako odstające (kolumny *_outlier)", "-", flagged],
    ]
    return markdown_table(["Miara", "Przed", "Po"], rows)


def missing_table(before: Diagnosis, after: Diagnosis) -> str:
    rows = []
    for column, count in before.missing.items():
        rows.append([column, count, after.missing.get(column, "-")])
    return markdown_table(["Kolumna", "Przed", "Po"], rows)


def tokens_table(before: Diagnosis) -> str:
    if not before.text_tokens:
        return "Nie wykryto."
    rows = []
    for column, tokens in before.text_tokens.items():
        parts = []
        for token, count in tokens.items():
            parts.append(f"'{token}': {count}")
        rows.append([column, ", ".join(parts), sum(tokens.values())])
    return markdown_table(["Kolumna", "Wartości (liczba wystąpień)", "Razem"], rows)


def rules_table(before: Diagnosis, after: Diagnosis, config: PipelineConfig) -> str:
    if not config.range_rules:
        return "Brak reguł zakresu dla tego pliku (można je dodać w konfiguracji albo opcją --range)."
    rows = []
    for rule in config.range_rules:
        name = rule.describe()
        rows.append([name, rule.action, rule.reason, before.range_violations.get(name, "-"),
                     after.range_violations.get(name, "-")])
    return markdown_table(["Reguła", "Akcja", "Uzasadnienie", "Naruszeń przed", "Po"], rows)


def outliers_table(before: Diagnosis, after: Diagnosis) -> str:
    if not before.outliers:
        return "Brak kolumn liczbowych do sprawdzenia."
    rows = []
    for column, info in before.outliers.items():
        if info.bounds is None:
            bounds_text = "- (IQR = 0)"
        else:
            bounds_text = f"[{info.bounds[0]:.4g}, {info.bounds[1]:.4g}]"

        if column in after.outliers:
            count_after = after.outliers[column].count
        else:
            count_after = "-"
        flagged = after.flagged_outliers.get(f"{column}_outlier", "-")

        rows.append([column, bounds_text, info.count, info.extreme_count, count_after, flagged])
    headers = ["Kolumna", "Granice przed", "Przed: IQR x 1,5", "Przed: IQR x 3", "Po: IQR x 1,5", "Oznaczone"]
    return markdown_table(headers, rows)


def operations_table(entries: list[AuditEntry]) -> str:
    rows = []
    for entry in entries:
        changes = []
        for column, count in entry.changed_cells.items():
            changes.append(f"{column}: {count}")
        if entry.added_columns:
            changes.append("nowe: " + ", ".join(entry.added_columns))
        changes_text = "; ".join(changes) if changes else "-"

        rows.append([
            entry.step,
            entry.operation,
            f"{entry.rows_before} → {entry.rows_after}",
            entry.affected_rows,
            changes_text,
            entry.details,
        ])
    headers = ["#", "Operacja", "Rekordy", "Dotknięte rekordy", "Zmienione komórki", "Szczegóły"]
    return markdown_table(headers, rows)


def reasons_list(entries: list[AuditEntry]) -> str:
    """Uzasadnienia decyzji. Kolejne kroki z tym samym uzasadnieniem łączy w jeden punkt, np. "3-11"."""
    lines = []
    index = 0
    while index < len(entries):
        first = entries[index]
        last_index = index
        while last_index + 1 < len(entries) and entries[last_index + 1].reason == first.reason:
            last_index += 1
        last = entries[last_index]

        if first.reason:
            if first is last:
                steps = str(first.step)
            else:
                steps = f"{first.step}-{last.step}"
            lines.append(f"- **{steps}. {first.operation}**: {first.reason}")

        index = last_index + 1
    return "\n".join(lines)


def changed_columns_table(entries: list[AuditEntry], columns: list) -> str:
    totals = {}
    for column in columns:
        totals[column] = 0
    for entry in entries:
        for column, count in entry.changed_cells.items():
            totals[column] = totals.get(column, 0) + count

    rows = []
    for column, total in totals.items():
        rows.append([column, total])
    return markdown_table(["Kolumna", "Zmienione komórki (wszystkie operacje)"], rows)


def profile_table(before: DataProfile, after: DataProfile) -> str:
    rows = []
    for column in after.columns.index:
        new = after.columns.loc[column]
        if column in before.columns.index:
            old = before.columns.loc[column]
            rows.append([
                column, old["dtype"], new["dtype"],
                f"{old['missing']} ({old['missing_pct']}%)", f"{new['missing']} ({new['missing_pct']}%)",
                old["unique"], new["unique"],
            ])
        else:
            rows.append([column, "(nowa)", new["dtype"], "-", f"{new['missing']} ({new['missing_pct']}%)",
                         "-", new["unique"]])
    headers = ["Kolumna", "Typ przed", "Typ po", "Braki przed", "Braki po", "Unikalne przed", "Unikalne po"]
    return markdown_table(headers, rows)


def stats_table(profile: DataProfile) -> str:
    if profile.stats.empty:
        return "Brak kolumn liczbowych."
    headers = ["Kolumna"]
    for name in profile.stats.columns:
        headers.append(str(name))
    rows = []
    for column, values in profile.stats.iterrows():
        row = [column]
        for value in values:
            row.append(float(value))
        rows.append(row)
    return markdown_table(headers, rows)


def preview_table(frame: pd.DataFrame, rows_count: int = 5) -> str:
    headers = []
    for column in frame.columns:
        headers.append(str(column))
    rows = []
    for _, row in frame.head(rows_count).iterrows():
        rows.append(list(row))
    return markdown_table(headers, rows)


# --- cały raport ------------------------------------------------------------------------


def build_report(
    session: DataSession,
    config: PipelineConfig,
    before: Diagnosis,
    after: Diagnosis,
    cleaned_name: str,
    cleaned_sha256: str,
) -> str:
    profile_before = session.raw_profile()
    profile_after = session.profile()
    entries = session.audit_log

    sections = [
        "# Raport jakości danych: przed i po czyszczeniu",
        source_section(session, cleaned_name, cleaned_sha256),

        "## 1. Podsumowanie",
        summary_section(before, after, profile_before.n_cols, profile_after.n_cols),

        "## 2. Wykryte problemy (dane surowe) i stan po czyszczeniu",
        "### Braki (NaN) według kolumn",
        missing_table(before, after),
        "### Tekstowe oznaczenia braku",
        tokens_table(before),
        "### Reguły zakresu",
        "Wykrycie nie zmienia danych. Co zrobić z naruszeniem, mówi akcja reguły (decyzja użytkownika).",
        rules_table(before, after, config),
        "### Wartości odstające (IQR)",
        outliers_table(before, after),

        "## 3. Ślad zmian: operacje w kolejności",
        operations_table(entries),
        "**Uzasadnienia decyzji:**",
        reasons_list(entries),

        "## 4. Kontrola: zmiany w kolumnach",
        "Każda operacja zmienia tylko kolumnę, której dotyczy. Usuwanie rekordów zmienia tylko liczbę wierszy, "
        "a kolumny `*_outlier` / `*_poza_zakresem` są dodawane bez zmiany istniejących wartości.",
        changed_columns_table(entries, list(profile_before.columns.index)),

        "## 5. Profil danych",
        "### Podgląd danych surowych (pierwsze wiersze)",
        preview_table(session.raw),
        "### Typy, braki i unikalność przed / po",
        profile_table(profile_before, profile_after),
        "### Statystyki opisowe przed",
        "Kolumny z tekstowymi wtrętami są przed czyszczeniem tekstowe, więc nie mają tu statystyk.",
        stats_table(profile_before),
        "### Statystyki opisowe po",
        stats_table(profile_after),

        "## 6. Powtarzalność",
        "Pipeline nie używa losowości, a kolejność i parametry kroków są w pliku konfiguracji. "
        "Ponowne uruchomienie na tym samym pliku daje identyczny wynik (ta sama suma SHA-256).",
    ]
    return "\n\n".join(sections) + "\n"
