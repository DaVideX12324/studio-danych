# Raport jakości danych: przed i po czyszczeniu

- Źródło: `california_housing_projekt2.csv` (kodowanie utf-8-sig, separator: przecinek, separator dziesiętny '.', pominięte wadliwe wiersze: 0)
- Wynik: `cleaned.csv` (SHA-256 `3f63b46f7eb8526c92e0fa37329626e924ed273188fde958548a70ee1cfee307`)
- Wygenerowano: 2026-11-17T12:34:04

## 1. Podsumowanie

| Miara | Przed | Po |
| --- | --- | --- |
| Rekordy | 20840 | 20244 |
| Kolumny | 9 | 14 |
| Pełne duplikaty | 200 | 0 |
| Puste komórki (NaN) | 1080 | 0 |
| Tekstowe oznaczenia braku w kolumnach liczbowych | 24 | 0 |
| Wartości spoza zakresu (suma po regułach) | 110 | 0 |
| Wartości odstające IQR (suma po kolumnach) | 4639 | 4551 |
| Oznaczone jako odstające (kolumny *_outlier) | - | 4551 |

## 2. Wykryte problemy (dane surowe) i stan po czyszczeniu

### Braki (NaN) według kolumn

| Kolumna | Przed | Po |
| --- | --- | --- |
| MedInc | 120 | 0 |
| HouseAge | 120 | 0 |
| AveRooms | 120 | 0 |
| AveBedrms | 120 | 0 |
| Population | 120 | 0 |
| AveOccup | 120 | 0 |
| Latitude | 120 | 0 |
| Longitude | 120 | 0 |
| MedHouseVal | 120 | 0 |

### Tekstowe oznaczenia braku

| Kolumna | Wartości (liczba wystąpień) | Razem |
| --- | --- | --- |
| MedInc | '--': 1, 'do sprawdzenia': 1, '?': 1, 'error': 1, 'nieznane': 1, 'brak': 1 | 6 |
| HouseAge | 'brak': 1, 'error': 1, '--': 1, 'do sprawdzenia': 1, 'nieznane': 1, '?': 1 | 6 |
| Population | 'do sprawdzenia': 1, '?': 1, 'error': 1, 'brak': 1, 'nieznane': 1, '--': 1 | 6 |
| MedHouseVal | '?': 1, 'do sprawdzenia': 1, 'nieznane': 1, '--': 1, 'brak': 1, 'error': 1 | 6 |

### Reguły zakresu

Wykrycie nie zmienia danych. Co zrobić z naruszeniem, mówi akcja reguły (decyzja użytkownika).

| Reguła | Akcja | Uzasadnienie | Naruszeń przed | Po |
| --- | --- | --- | --- | --- |
| 0 < MedInc ≤ 15.0001 | nan | Dochód w dziesiątkach tys. USD musi być dodatni; w źródle (California Housing) obcięty od góry na 15.0001, więc wyższa wartość nie może pochodzić z tego zbioru. | 30 | 0 |
| 1 ≤ HouseAge ≤ 52 | nan | Mediana wieku budynków w latach; w źródle obcięta na 52. | 10 | 0 |
| 0 < AveRooms | nan | Średnia liczba pokoi na gospodarstwo musi być dodatnia. | 10 | 0 |
| 0 < AveBedrms | nan | Średnia liczba sypialni musi być dodatnia. | 10 | 0 |
| 1 ≤ Population | nan | Liczba mieszkańców grupy bloków: co najmniej 1. | 10 | 0 |
| 0 < AveOccup | nan | Średnia liczba osób na gospodarstwo musi być dodatnia. | 10 | 0 |
| 32.5 ≤ Latitude ≤ 42 | nan | Kalifornia leży między 32,5° a 42,0° N. | 10 | 0 |
| -124.5 ≤ Longitude ≤ -114.1 | nan | Kalifornia leży między 124,5° a 114,1° W. | 10 | 0 |
| 0 < MedHouseVal ≤ 5.00001 | nan | Wartość domu w setkach tys. USD musi być dodatnia; w źródle obcięta na 5.00001. | 10 | 0 |

### Wartości odstające (IQR)

| Kolumna | Granice przed | Przed: IQR x 1,5 | Przed: IQR x 3 | Po: IQR x 1,5 | Oznaczone |
| --- | --- | --- | --- | --- | --- |
| MedInc | [-0.7105, 8.018] | 706 | 158 | 682 | 682 |
| AveRooms | [2.024, 8.469] | 542 | 209 | 529 | 529 |
| AveBedrms | [0.8659, 1.24] | 1439 | 738 | 1411 | 1411 |
| Population | [-623.4, 3136] | 1205 | 427 | 1190 | 1190 |
| AveOccup | [1.15, 4.562] | 747 | 162 | 739 | 739 |

## 3. Ślad zmian: operacje w kolejności

| # | Operacja | Rekordy | Dotknięte rekordy | Zmienione komórki | Szczegóły |
| --- | --- | --- | --- | --- | --- |
| 1 | drop_duplicates | 20840 → 20640 | 200 | - | klucz: wszystkie kolumny; usunięto 200 |
| 2 | normalize_missing_tokens | 20640 → 20640 | 24 | MedInc: 6; HouseAge: 6; Population: 6; MedHouseVal: 6 | tokeny: ['', '--', '?', 'brak', 'do sprawdzenia', 'error', 'n/a', 'na', 'nieznane', 'null']; zamienione na liczby: MedInc, HouseAge, Population, MedHouseVal |
| 3 | apply_range_rule | 20640 → 20640 | 30 | MedInc: 30 | 0 < MedInc ≤ 15.0001: naruszeń 30, akcja nan |
| 4 | apply_range_rule | 20640 → 20640 | 10 | HouseAge: 10 | 1 ≤ HouseAge ≤ 52: naruszeń 10, akcja nan |
| 5 | apply_range_rule | 20640 → 20640 | 10 | AveRooms: 10 | 0 < AveRooms: naruszeń 10, akcja nan |
| 6 | apply_range_rule | 20640 → 20640 | 10 | AveBedrms: 10 | 0 < AveBedrms: naruszeń 10, akcja nan |
| 7 | apply_range_rule | 20640 → 20640 | 10 | Population: 10 | 1 ≤ Population: naruszeń 10, akcja nan |
| 8 | apply_range_rule | 20640 → 20640 | 10 | AveOccup: 10 | 0 < AveOccup: naruszeń 10, akcja nan |
| 9 | apply_range_rule | 20640 → 20640 | 10 | Latitude: 10 | 32.5 ≤ Latitude ≤ 42: naruszeń 10, akcja nan |
| 10 | apply_range_rule | 20640 → 20640 | 10 | Longitude: 10 | -124.5 ≤ Longitude ≤ -114.1: naruszeń 10, akcja nan |
| 11 | apply_range_rule | 20640 → 20640 | 10 | MedHouseVal: 10 | 0 < MedHouseVal ≤ 5.00001: naruszeń 10, akcja nan |
| 12 | drop_missing | 20640 → 20244 | 396 | - | kolumny: MedHouseVal, Latitude, Longitude; usunięto 396 |
| 13 | fill_missing | 20244 → 20244 | 156 | MedInc: 156 | median = 3.5417; uzupełniono 156 |
| 14 | fill_missing | 20244 → 20244 | 136 | HouseAge: 136 | median = 29; uzupełniono 136 |
| 15 | fill_missing | 20244 → 20244 | 130 | AveRooms: 130 | median = 5.23333; uzupełniono 130 |
| 16 | fill_missing | 20244 → 20244 | 130 | AveBedrms: 130 | median = 1.04863; uzupełniono 130 |
| 17 | fill_missing | 20244 → 20244 | 136 | Population: 136 | median = 1167; uzupełniono 136 |
| 18 | fill_missing | 20244 → 20244 | 130 | AveOccup: 130 | median = 2.819; uzupełniono 130 |
| 19 | handle_outliers | 20244 → 20244 | 682 | nowe: MedInc_outlier | IQR x 1.5: granice [-0.6694, 7.979], wykryto 682, akcja flag |
| 20 | handle_outliers | 20244 → 20244 | 529 | nowe: AveRooms_outlier | IQR x 1.5: granice [2.039, 8.46], wykryto 529, akcja flag |
| 21 | handle_outliers | 20244 → 20244 | 1411 | nowe: AveBedrms_outlier | IQR x 1.5: granice [0.8676, 1.238], wykryto 1411, akcja flag |
| 22 | handle_outliers | 20244 → 20244 | 1190 | nowe: Population_outlier | IQR x 1.5: granice [-605.5, 3118], wykryto 1190, akcja flag |
| 23 | handle_outliers | 20244 → 20244 | 739 | nowe: AveOccup_outlier | IQR x 1.5: granice [1.17, 4.542], wykryto 739, akcja flag |

**Uzasadnienia decyzji:**

- **1. drop_duplicates**: Pełne duplikaty (identyczne wszystkie kolumny) to powtórzone rekordy; zostaje pierwsze wystąpienie. Robione na danych surowych, żeby nie scalać rekordów różniących się tylko zapisem braku.
- **2. normalize_missing_tokens**: Teksty typu '?', 'brak', 'error' w kolumnach liczbowych oznaczają brak wartości; zamiana na NaN pozwala potraktować kolumnę jako liczbową.
- **3-11. apply_range_rule**: Akcja nan: wartość fizycznie niemożliwa to błąd zapisu, więc traktujemy ją jak brak informacji i obsługujemy jak pozostałe braki, zamiast usuwać cały rekord.
- **12. drop_missing**: Strategia 1, usunięcie: MedHouseVal to zmienna objaśniana (imputacja wymyśliłaby wynik), a uzupełnienie współrzędnych medianą przeniosłoby rekord w inne miejsce.
- **13-18. fill_missing**: Strategia 2, imputacja medianą: rozkłady są prawoskośne z wartościami odstającymi, a mediana jest na nie odporna (średnia nie).
- **19-23. handle_outliers**: Wartości odstające (IQR x 1,5) tylko oznaczamy kolumną <nazwa>_outlier: w tych danych duże średnie pokoi czy mieszkańców bywają prawdziwe (ośrodki wypoczynkowe, akademiki), więc o usunięciu decyduje analiza, nie automat.

## 4. Kontrola: zmiany w kolumnach

Każda operacja zmienia tylko kolumnę, której dotyczy. Usuwanie rekordów zmienia tylko liczbę wierszy, a kolumny `*_outlier` / `*_poza_zakresem` są dodawane bez zmiany istniejących wartości.

| Kolumna | Zmienione komórki (wszystkie operacje) |
| --- | --- |
| MedInc | 192 |
| HouseAge | 152 |
| AveRooms | 140 |
| AveBedrms | 140 |
| Population | 152 |
| AveOccup | 140 |
| Latitude | 10 |
| Longitude | 10 |
| MedHouseVal | 16 |

## 5. Profil danych

### Podgląd danych surowych (pierwsze wiersze)

| MedInc | HouseAge | AveRooms | AveBedrms | Population | AveOccup | Latitude | Longitude | MedHouseVal |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1.7548 | 30.0 | 4.228 | 1.179 | 1200.0 | 3.419 | 36.21 | -121.1 | 0.958 |
| 3.0354 | 23.0 | 4.327 | 1.008 | 1554.0 | 2.376 | 37.96 | -121.3 | 1.137 |
| 2.25 | 50.0 | 4.207 | 1.157 | 1149.0 | 2.769 | 37.8 | -122.2 | 1.235 |
| 3.7043 | 12.0 | 6.387 | 1.107 | 1502.0 | 2.781 | 34.49 | -117.9 | 1.508 |
| 1.8897 | 43.0 | 4.484 | 1.152 | 820.0 | 4.457 | 33.97 | -118.2 | 1.743 |

### Typy, braki i unikalność przed / po

| Kolumna | Typ przed | Typ po | Braki przed | Braki po | Unikalne przed | Unikalne po |
| --- | --- | --- | --- | --- | --- | --- |
| MedInc | str | float64 | 120 (0.58%) | 0 (0.0%) | 12884 | 12670 |
| HouseAge | str | float64 | 120 (0.58%) | 0 (0.0%) | 59 | 52 |
| AveRooms | float64 | float64 | 120 (0.58%) | 0 (0.0%) | 19279 | 18921 |
| AveBedrms | float64 | float64 | 120 (0.58%) | 0 (0.0%) | 14162 | 13970 |
| Population | str | float64 | 120 (0.58%) | 0 (0.0%) | 3890 | 3867 |
| AveOccup | float64 | float64 | 120 (0.58%) | 0 (0.0%) | 18738 | 18391 |
| Latitude | float64 | float64 | 120 (0.58%) | 0 (0.0%) | 863 | 861 |
| Longitude | float64 | float64 | 120 (0.58%) | 0 (0.0%) | 845 | 839 |
| MedHouseVal | str | float64 | 120 (0.58%) | 0 (0.0%) | 3844 | 3827 |
| MedInc_outlier | (nowa) | bool | - | 0 (0.0%) | - | 2 |
| AveRooms_outlier | (nowa) | bool | - | 0 (0.0%) | - | 2 |
| AveBedrms_outlier | (nowa) | bool | - | 0 (0.0%) | - | 2 |
| Population_outlier | (nowa) | bool | - | 0 (0.0%) | - | 2 |
| AveOccup_outlier | (nowa) | bool | - | 0 (0.0%) | - | 2 |

### Statystyki opisowe przed

Kolumny z tekstowymi wtrętami są przed czyszczeniem tekstowe, więc nie mają tu statystyk.

| Kolumna | count | mean | std | min | 25% | 50% | 75% | max |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AveRooms | 2.072e+04 | 5.823 | 13.31 | -2 | 4.441 | 5.231 | 6.052 | 553.4 |
| AveBedrms | 2.072e+04 | 1.095 | 0.4746 | -1 | 1.006 | 1.049 | 1.099 | 34.07 |
| AveOccup | 2.072e+04 | 6.604 | 116.4 | -4 | 2.429 | 2.819 | 3.282 | 4849 |
| Latitude | 2.072e+04 | 35.66 | 2.503 | 32.54 | 33.93 | 34.26 | 37.72 | 95 |
| Longitude | 2.072e+04 | -119.4 | 7.088 | -124.3 | -121.8 | -118.5 | -118 | 190 |

### Statystyki opisowe po

| Kolumna | count | mean | std | min | 25% | 50% | 75% | max |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| MedInc | 2.024e+04 | 3.871 | 1.891 | 0.4999 | 2.574 | 3.542 | 4.736 | 15 |
| HouseAge | 2.024e+04 | 28.61 | 12.55 | 1 | 18 | 29 | 37 | 52 |
| AveRooms | 2.024e+04 | 5.839 | 13.46 | 0.8462 | 4.446 | 5.233 | 6.052 | 553.4 |
| AveBedrms | 2.024e+04 | 1.096 | 0.4764 | 0.3333 | 1.006 | 1.049 | 1.099 | 34.07 |
| Population | 2.024e+04 | 1425 | 1130 | 3 | 791 | 1167 | 1722 | 3.568e+04 |
| AveOccup | 2.024e+04 | 6.692 | 117.8 | 0.6923 | 2.435 | 2.819 | 3.278 | 4849 |
| Latitude | 2.024e+04 | 35.63 | 2.137 | 32.54 | 33.93 | 34.26 | 37.72 | 41.95 |
| Longitude | 2.024e+04 | -119.6 | 2.004 | -124.3 | -121.8 | -118.5 | -118 | -114.3 |
| MedHouseVal | 2.024e+04 | 2.07 | 1.154 | 0.15 | 1.198 | 1.799 | 2.649 | 5 |

## 6. Powtarzalność

Pipeline nie używa losowości, a kolejność i parametry kroków są w pliku konfiguracji. Ponowne uruchomienie na tym samym pliku daje identyczny wynik (ta sama suma SHA-256).
