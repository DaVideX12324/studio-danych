"""Wczytywanie plików CSV.

Obsługiwane:
- separator pól: przecinek, średnik albo tabulator (wykrywany z nagłówka),
- przecinek dziesiętny (np. "12,5"), gdy separatorem pól nie jest przecinek,
- kodowanie UTF-8, a jeśli się nie da, Windows-1250 (polskie pliki z Excela).

Każdy problem kończy się wyjątkiem LoadError z komunikatem dla użytkownika.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

ENCODINGS = ["utf-8-sig", "cp1250"]
SEPARATORS = [",", ";", "\t"]


class LoadError(Exception):
    """Pliku nie dało się wczytać. Treść błędu można pokazać użytkownikowi."""


@dataclass
class LoadInfo:
    """Jak plik został wczytany (trafia do raportu)."""

    path: str
    encoding: str
    separator: str
    decimal: str
    skipped_lines: int


def read_text(path: Path, encoding: str | None = None) -> tuple[str, str]:
    """Czyta plik jako tekst. Zwraca parę (tekst, użyte kodowanie)."""
    if not path.exists():
        raise LoadError(f"Nie znaleziono pliku: {path}")
    try:
        data = path.read_bytes()
    except OSError as error:
        raise LoadError(f"Nie można odczytać pliku {path}: {error}") from error

    if encoding is None:
        encodings_to_try = ENCODINGS
    else:
        encodings_to_try = [encoding]

    for current_encoding in encodings_to_try:
        try:
            return data.decode(current_encoding), current_encoding
        except UnicodeDecodeError:
            continue  # spróbuj następnego kodowania
        except LookupError:
            raise LoadError(f"Nieznane kodowanie: {current_encoding}") from None

    tried = ", ".join(encodings_to_try)
    raise LoadError(
        f"Nie udało się odczytać pliku {path.name} w kodowaniu {tried}. "
        "Zapisz plik jako UTF-8 albo podaj właściwe kodowanie."
    )


def detect_separator(header_line: str) -> str:
    """Wybiera separator, który najczęściej występuje w wierszu nagłówka.

    Nazwy kolumn rzadko zawierają przecinki czy średniki, więc nagłówek dobrze to pokazuje.
    Gdy żadnego separatora nie ma (jedna kolumna), zwraca przecinek.
    """
    best_separator = ","
    best_count = 0
    for separator in SEPARATORS:
        count = header_line.count(separator)
        if count > best_count:
            best_separator = separator
            best_count = count
    return best_separator


def detect_decimal(text: str, separator: str) -> str:
    """Zwraca "," jeśli w pierwszych wierszach danych są liczby typu "12,5", w przeciwnym razie "."."""
    if separator == ",":
        return "."  # przecinek jest już separatorem pól

    first_rows = text.splitlines()[1:51]
    for row in first_rows:
        if re.search(r"\d,\d", row):
            return ","
    return "."


def load_csv(
    path: str | Path,
    encoding: str | None = None,
    separator: str | None = None,
    skip_bad_lines: bool = False,
) -> tuple[pd.DataFrame, LoadInfo]:
    """Wczytuje plik CSV i zwraca (dane, informacje o wczytaniu).

    skip_bad_lines=False: wiersz z nadmiarową liczbą pól przerywa wczytywanie z błędem.
    skip_bad_lines=True: takie wiersze są pomijane, a ich liczba trafia do LoadInfo.
    """
    path = Path(path)
    text, used_encoding = read_text(path, encoding)
    if text.strip() == "":
        raise LoadError(f"Plik {path.name} jest pusty.")

    header_line = text.lstrip().splitlines()[0]
    if separator is None:
        separator = detect_separator(header_line)
    decimal = detect_decimal(text, separator)

    skipped_lines = []

    def skip_line(bad_line: list[str]) -> None:
        skipped_lines.append(bad_line)
        return None  # pandas: None oznacza "pomiń ten wiersz"

    if skip_bad_lines:
        bad_line_handling = skip_line
    else:
        bad_line_handling = "error"

    try:
        frame = pd.read_csv(
            io.StringIO(text),
            sep=separator,
            decimal=decimal,
            engine="python",
            on_bad_lines=bad_line_handling,
        )
    except pd.errors.ParserError as error:
        raise LoadError(
            f"Wadliwy wiersz w pliku {path.name}: {error}. "
            "Popraw plik albo wczytaj go z pomijaniem wadliwych wierszy."
        ) from error
    except pd.errors.EmptyDataError:
        raise LoadError(f"Plik {path.name} nie zawiera danych.") from None

    if frame.empty:
        raise LoadError(f"Plik {path.name} ma tylko nagłówek, bez rekordów.")

    info = LoadInfo(
        path=str(path),
        encoding=used_encoding,
        separator=separator,
        decimal=decimal,
        skipped_lines=len(skipped_lines),
    )
    return frame, info
