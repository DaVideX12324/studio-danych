# Studio jakości i wizualizacji danych

Projekt 2 z Programowania V (laboratoria 6–9). Aplikacja prowadzi od wczytania pliku CSV przez diagnozę
i czyszczenie danych do wizualizacji i eksportu, a każda zmiana zbioru jest zapisana w raporcie.

**Stan: lab 6 gotowy**: profil danych, wykrywanie problemów, pipeline czyszczenia, raport przed/po, `cleaned.csv`.
Lab 7 (wykresy), 8 (GUI Tkinter) i 9 (eksport, dokumentacja końcowa) w przygotowaniu.

## Wymagania i instalacja

Python 3.10+ (testowane na 3.14, pandas 3.1, numpy 2.5).

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows; Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
```

## Uruchomienie (lab 6)

```bash
python run_lab6.py                                  # zbiór referencyjny + config/california.json
python run_lab6.py dane.csv                         # dowolny CSV + config/domyslna.json
python run_lab6.py dane.csv --range wiek 0 120      # reguła zakresu: tylko oznacza rekordy
python run_lab6.py dane.csv --range wiek 0 - --range-action nan   # '-' = brak granicy; akcja nan/drop/clip
python run_lab6.py dane.csv --config moja.json --out wyniki
python run_lab6.py dane.csv --skip-bad-lines        # pomija wadliwe wiersze (ich liczba trafia do raportu)
```

Wyniki w `output/` (albo w katalogu z `--out`):

- `cleaned.csv`: dane po czyszczeniu (+ kolumny `*_outlier` / `*_poza_zakresem` z oznaczeniami),
- `raport_lab6.md`: raport przed/po (wykryte problemy, każda operacja z liczbą dotkniętych rekordów
  i uzasadnieniem, kontrola zmienionych kolumn, profil i statystyki przed/po, suma SHA-256 wyniku),
- `audit_log.json`: dziennik operacji (parametry, czas, rekordy przed/po, zmienione komórki).

### Dowolny plik CSV

- Separator (`,` `;` tabulator), przecinek dziesiętny i kodowanie (UTF-8 / Windows-1250) są wykrywane same.
- `config/domyslna.json` nie zawiera nazw kolumn, tylko grupy `"numeric"` i `"text"`, rozwijane
  dla każdego pliku osobno: braki liczbowe uzupełnia medianą, tekstowe najczęstszą wartością,
  wartości odstające (IQR) oznacza we wszystkich kolumnach liczbowych.
- Reguł zakresu nie da się zgadnąć bez wiedzy o danych, więc podaje się je opcją `--range` albo we własnej
  konfiguracji. Domyślna akcja `flag` niczego nie zmienia, tylko oznacza rekordy.
- Konfiguracja z nazwami kolumn, których nie ma w pliku, kończy się czytelnym błędem jeszcze przed czyszczeniem.

## Struktura

```
studio/                 logika (bez GUI)
  loader.py             wczytywanie CSV: kodowanie, separator, przecinek dziesiętny, błędy
  profiling.py          profil (rozmiar, typy, statystyki, braki i %, duplikaty, unikalność) + diagnoza
  rules.py              reguły zakresu (RangeRule) i metoda IQR, tylko wykrywanie
  cleaning.py           operacje czyszczenia: dostają DataFrame, zwracają nową kopię + opis zmian
  session.py            DataSession: dane surowe / bieżące, dziennik operacji, reset
  pipeline.py           kroki czyszczenia z pliku JSON
  report.py             raport Markdown przed/po
config/california.json  reguły i decyzje dla zbioru referencyjnego
config/domyslna.json    konfiguracja dla dowolnego CSV
run_lab6.py             skrypt lab 6
tests/                  testy pytest (opis danych testowych: tests/data/OPIS.md)
```

Założenia: operacje nie zmieniają wejściowego DataFrame, więc dane surowe w sesji zostają nietknięte,
a operacja zakończona błędem nie zmienia danych. `DataSession.reset()` wraca do danych surowych bez ponownego
wczytywania pliku. Brak zmiennych globalnych. Ta sama sesja posłuży jako model dla GUI w lab 8.

## Pipeline dla zbioru California Housing

Wykryte w danych surowych (20 840 rekordów, 9 kolumn):

| Problem | Ile |
|---|---|
| pełne duplikaty | 200 |
| puste komórki (NaN) | 120 w każdej kolumnie |
| tekstowe oznaczenia braku (`?`, `--`, `brak`, `nieznane`, `error`, `do sprawdzenia`) | 24 (MedInc, HouseAge, Population, MedHouseVal) |
| wartości spoza zakresu | 110 (ujemne, Latitude = 95, Longitude = 190, MedInc > 15.0001) |
| wartości odstające IQR x 1,5 | 4 639 w 5 kolumnach (w tym ekstremalne: AveRooms do 553, AveOccup do 4849) |

Kroki i decyzje (pełne uzasadnienia w `config/california.json` i w raporcie):

1. **Duplikaty**: usunięcie pełnych duplikatów (identyczne wszystkie kolumny), zostaje pierwszy.
2. **Tekstowe braki**: zamiana na NaN; kolumny stają się liczbowe.
3. **Reguły zakresu**: wykrycie jest oddzielone od akcji. Wybrana akcja `nan`: wartość niemożliwa to brak
   informacji. Dostępne też `flag`, `drop`, `clip`.
4. **Braki, strategia 1: usunięcie** rekordów bez `MedHouseVal` (zmienna objaśniana) lub bez współrzędnych.
5. **Braki, strategia 2: imputacja medianą** pozostałych kolumn (rozkłady prawoskośne, mediana jest odporna
   na wartości odstające). Dostępne też `mean`, `mode`, `constant`.
6. **Wartości odstające**: tylko oznaczenie (`<kolumna>_outlier`), bez usuwania, bo wysokie średnie pokoi czy
   mieszkańców bywają prawdziwe (ośrodki wypoczynkowe, akademiki). Dostępne też `report`, `clip`, `drop`.

Wynik: 20 244 rekordy, 0 duplikatów, 0 braków, 0 naruszeń reguł. Każda kolumna jest zmieniana tylko przez
operacje, które jej dotyczą (tabela w sekcji 4 raportu). Wynik jest powtarzalny: bez losowości, ta sama suma
SHA-256 przy każdym uruchomieniu.

## Testy

```bash
python -m pytest
```

Pokrywają macierz testów z instrukcji (część logiki): CSV z przecinkiem i średnikiem (też cp1250 i przecinek
dziesiętny), wadliwy wiersz, złe kodowanie, pusty plik; braki liczbowe i tekstowe z liczbą zmian; duplikaty
na kontrolowanej parze rekordów; reguła zakresu wykrywa bez zmiany danych; IQR na kolumnie stałej; reset sesji;
operacja z błędem nie zmienia danych; powtarzalność; ponowny odczyt zapisanego CSV; cały skrypt na kilku
różnych plikach CSV i z regułą z linii poleceń.

## Znane ograniczenia

- Separator jest wykrywany z wiersza nagłówka (najczęstszy z `,` `;` tabulator).
- Kodowanie: UTF-8, a gdy się nie da, Windows-1250; inne trzeba podać jawnie (`load_csv(..., encoding=...)`).
- Granice IQR są liczone na bieżących danych, więc zależą od wcześniejszych kroków (kolejność jest w konfiguracji).
- Daty zostają tekstem (nie są rozpoznawane jako typ daty).

## Źródła, biblioteki i narzędzia AI

- pandas (`read_csv`, braki danych, duplikaty): https://pandas.pydata.org/docs/
- Opis zbioru California Housing (obcięcia MedInc 15.0001, HouseAge 52, MedHouseVal 5.00001):
  https://scikit-learn.org/stable/datasets/real_world.html#california-housing-dataset
- Wzorzec `DataSession` z instrukcji projektu (kod inspiracyjny).
- Narzędzie AI: Claude (Anthropic), pomoc przy projekcie struktury, kodzie i testach; kod został przejrzany
  i jest rozumiany przez autora.
