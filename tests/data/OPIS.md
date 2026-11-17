# Dane testowe i oczekiwane wyniki

| Plik | Co sprawdza | Oczekiwany wynik |
|---|---|---|
| `przecinek.csv` | separator `,`, UTF-8, brak liczbowy, para duplikatów | 4 rekordy × 3 kolumny (`miasto`, `cena`, `powierzchnia`); `cena` w wierszu Kraków = NaN; 1 pełny duplikat (Gdańsk) |
| `srednik_cp1250.csv` | separator `;`, przecinek dziesiętny, kodowanie Windows-1250 | te same dane co `przecinek.csv` (test porównuje oba DataFrame); `450000,5` → 450000.5; „Łódź” odczytane poprawnie |
| `wadliwy_wiersz.csv` | wiersz z nadmiarową kolumną (`4,5,6,7`) | domyślnie kontrolowany `LoadError` „Wadliwy wiersz…”; z `skip_bad_lines=True` 2 rekordy i `skipped_lines = 1` |
| `brudne.csv` | wszystkie typy problemów naraz, na 8 rekordach | patrz niżej |

## `brudne.csv` (konfiguracja jak w `tests/test_session_pipeline.py`)

| Problem | Gdzie | Diagnoza | Po pipeline |
|---|---|---|---|
| pełny duplikat | dwa wiersze `id = 6` | 1 duplikat | usunięty, zostaje 7 rekordów |
| tekstowy brak liczbowy | `wiek = ?` (id 2), `dochod = brak` (id 5) | `{"wiek": {"?": 1}, "dochod": {"brak": 1}}` | NaN → mediana kolumny |
| brak tekstowy | pusta `miasto` (id 3) | 1 brak w `miasto` | stała `"nieznane"` |
| wartość poza zakresem | `wiek = -5` (id 4), reguła `0 ≤ wiek ≤ 120` | 1 naruszenie, dane bez zmian | akcja `nan` → mediana |
| wartość odstająca | `dochod = 95.0` (id 7) | 1 outlier (IQR×1,5) | wartość zostaje, `dochod_outlier = True` |
| kolumna niezwiązana | `id` | — | bez zmian: `[1, 2, 3, 4, 5, 6, 7]` |
