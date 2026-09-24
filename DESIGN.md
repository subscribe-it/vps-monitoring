---
name: Monitoring VPS — panel operatorski
description: Konsola operatorska jednego VPS-a — uczciwy stan usług, ruch, logi i diagnostyka w dwóch motywach systemowych.
colors:
  void-slate: "oklch(17% 0.014 255)"
  panel-slate: "oklch(21.5% 0.016 255)"
  edge-slate: "oklch(27% 0.018 255)"
  pale-ink: "oklch(93% 0.008 255)"
  instrument-cyan: "oklch(76% 0.13 218)"
  chart-violet: "oklch(72% 0.09 268)"
  gauge-teal: "oklch(80% 0.13 195)"
  signal-green: "oklch(79% 0.16 155)"
  signal-amber: "oklch(85% 0.14 85)"
  signal-red: "oklch(73% 0.18 22)"
  signal-blue: "oklch(79% 0.11 235)"
  quiet-slate: "oklch(72% 0.012 255)"
  paper-cool: "oklch(98.5% 0.004 255)"
  paper-shade: "oklch(96% 0.006 255)"
  paper-edge: "oklch(91.5% 0.008 255)"
  ink-slate: "oklch(24% 0.02 255)"
  instrument-blue: "oklch(52% 0.15 240)"
  day-violet: "oklch(50% 0.13 275)"
  day-teal: "oklch(52% 0.12 200)"
  day-green: "oklch(47% 0.13 155)"
  day-amber: "oklch(52% 0.13 75)"
  day-red: "oklch(50% 0.19 25)"
  day-blue: "oklch(50% 0.13 240)"
typography:
  display:
    fontFamily: "system-ui, -apple-system, Segoe UI, Roboto, Noto Sans, Ubuntu, Cantarell, Helvetica Neue, Arial, sans-serif"
    fontSize: "1rem"
    fontWeight: 600
  title:
    fontFamily: "system-ui, -apple-system, Segoe UI, Roboto, Noto Sans, Ubuntu, Cantarell, Helvetica Neue, Arial, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 600
  body:
    fontFamily: "system-ui, -apple-system, Segoe UI, Roboto, Noto Sans, Ubuntu, Cantarell, Helvetica Neue, Arial, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 400
  label:
    fontFamily: "system-ui, -apple-system, Segoe UI, Roboto, Noto Sans, Ubuntu, Cantarell, Helvetica Neue, Arial, sans-serif"
    fontSize: "0.6875rem"
    fontWeight: 500
    letterSpacing: "0.04em"
  mono:
    fontFamily: "ui-monospace, SFMono-Regular, SF Mono, Menlo, Consolas, Liberation Mono, monospace"
    fontSize: "0.75rem"
    fontWeight: 400
rounded:
  selector: "0.5rem"
  field: "0.5rem"
  box: "0.75rem"
  pill: "9999px"
spacing:
  tight: "4px"
  row: "8px"
  section: "12px"
  card: "16px"
components:
  pill-state:
    backgroundColor: "{colors.edge-slate}"
    textColor: "{colors.pale-ink}"
    rounded: "{rounded.pill}"
    padding: "2px 8px"
  card-section:
    backgroundColor: "{colors.panel-slate}"
    textColor: "{colors.pale-ink}"
    rounded: "{rounded.box}"
    padding: "16px"
  button-ops:
    backgroundColor: "{colors.panel-slate}"
    textColor: "{colors.pale-ink}"
    rounded: "{rounded.selector}"
    height: "32px"
  chart-card:
    backgroundColor: "{colors.panel-slate}"
    textColor: "{colors.pale-ink}"
    rounded: "{rounded.box}"
    padding: "16px"
---

# Design System: Monitoring VPS — panel operatorski

## Overview

**Creative North Star: „Pulpit sterowniczy, nie kokpit samolotu”**

Panel jest **instrumentem pomiarowym**: ciemna (albo jasna, zależnie od pory
i pokoju) powierzchnia, na niej dyskretna siatka danych i jeden akcent, który
niesie znaczenie. Nic nie konkuruje z liczbami — kolor pojawia się tylko tam,
gdzie coś znaczy (stan, seria wykresu, próg), a nie po to, żeby ożywić ekran.

Gęstość jest świadoma: operator patrzy na ~47 usług i kilkanaście bloków
diagnostycznych, więc wiersze są ciasne, a separacje hojne — „ciasne grupy,
hojne separacje” jest tu regułą mierzalną (4 / 8 / 12 / 16 px), nie zapisem
intencji. Typografia jest mała i precyzyjna (11–14 px), bo panel czyta się
z bliska, na 13-calowym ekranie, a nie z drugiego końca pokoju.

Świat wizualny nie zmienia się między motywami: zmienia się **tylko paleta**.
Hierarchia, rytm, kształty i komponenty są identyczne w dzień i w nocy, więc
panel pokazany klientowi wygląda tak samo znajomo o 9:00 i o 23:00.

**Key Characteristics:**
- dwa motywy systemowe (`prefers-color-scheme`), jedna tożsamość;
- jeden akcent + kolory wyłącznie semantyczne;
- powierzchnie płaskie, głębia z tonalnego podziału, nie z cieni;
- dane zawsze z jednostką i kontekstem (limit, próg, czas);
- uczciwe stany: `unknown` wygląda jak brak wiedzy, nie jak zero.

## Colors

Paleta jest chłodna i „instrumentowa”: neutralne slate'y jako powierzchnie,
jeden kolor akcentu niosący interakcję i cztery kolory stanów.

### Primary
- **Instrument Cyan** (oklch(76% 0.13 218), motyw ciemny): akcent interakcji —
  fokus, aktywna kontrolka, pierwsza seria wykresu, pasek postępu.
- **Instrument Blue** (oklch(52% 0.15 240), motyw jasny): ten sam obowiązek na
  jasnym tle; ciemniejszy, bo cyan na bieli nie osiąga 3:1 dla cienkich linii.

### Secondary
- **Chart Violet** (oklch(72% 0.09 268) / oklch(50% 0.13 275)): druga seria
  wykresu (tx wobec rx, zapis wobec odczytu) — zawsze linia przerywana, żeby
  rozróżnienie nie zależało od koloru.

### Tertiary
- **Gauge Teal** (oklch(80% 0.13 195) / oklch(52% 0.12 200)): akcent poboczny
  (podświetlenia w tle, obramowania stanów informacyjnych).

### Neutral
- **Void Slate** (oklch(17% 0.014 255)) / **Paper Cool** (oklch(98.5% 0.004 255)):
  tło strony w motywie ciemnym i jasnym.
- **Panel Slate** (oklch(21.5% 0.016 255)) / **Paper Shade** (oklch(96% 0.006 255)):
  karty sekcji i wiersze danych.
- **Edge Slate** (oklch(27% 0.018 255)) / **Paper Edge** (oklch(91.5% 0.008 255)):
  obramowania, separatory, tła pigułek.
- **Pale Ink** (oklch(93% 0.008 255)) / **Ink Slate** (oklch(24% 0.02 255)):
  tekst podstawowy (kontrast ≥ 12:1 wobec własnego tła).
- **Quiet Slate** (oklch(72% 0.012 255) / oklch(45% 0.012 255)): stan `unknown`
  — celowo najcichszy kolor w systemie.

### Stany (semantyczne, w obu motywach)
- **Signal Green** — `ok`; **Signal Amber** — `warning`; **Signal Red** —
  `critical`; **Signal Blue** — `info`; **Quiet Slate** — `unknown`.
  Motyw jasny używa tych samych odcieni w jasności ~47–52%, żeby tekst na
  pigułce i cienkie linie wykresów miały ≥ 4,5:1 (tekst) i ≥ 3:1 (linia).

### Named Rules
**The One Voice Rule.** Kolor akcentu zajmuje mniej niż ~10% powierzchni
ekranu; jeśli akcentów jest więcej, któryś przestał coś znaczyć.

**The No-Decoration Rule.** Żaden kolor nie występuje „dla ożywienia”. Kolor
wchodzi wyłącznie jako stan, seria danych, próg albo interakcja.

## Typography

**Body Font:** system-ui (fallback: Segoe UI, Roboto, Noto Sans, Ubuntu, Arial)
**Label/Mono Font:** ui-monospace (fallback: SF Mono, Menlo, Consolas)

**Character:** typografia jest narzędziem, nie głosem — czcionki systemowe,
zero webfontów (panel działa bez internetu), liczby zawsze tabularne
(`font-variant-numeric: tabular-nums`), żeby kolumny wartości się nie ruszały
przy odświeżeniu.

### Hierarchy
- **Display** (600, 1rem): tytuł strony i nazwa aktywnego widoku.
- **Title** (600, 0.875rem): nagłówki sekcji i kart.
- **Body** (400, 0.75rem): dane, opisy, treści logów; dominujący stopień panelu.
- **Control** (500, 0.8125rem): przyciski, chipsy filtrów, kontrolki selectora.
- **Label** (500, 0.6875rem, tracking 0.04em): podpisy pól, nagłówki kolumn,
  osie wykresów — zawsze wersalikami, gdy pełnią rolę etykiety.

### Named Rules
**The Tabular Rule.** Każda liczba, która się odświeża, jest monospace albo
tabularna — inaczej odświeżanie co 10 s „tańczy” na ekranie.

**The One Step Rule.** Między sąsiadującymi poziomami hierarchii jest dokładnie
jeden krok (11 → 12 → 13 → 14 px). Nie ma stopni „prawie takich samych”.

## Layout

Siatka jest płynna, oparta na szerokości kontenera, z jednym progiem gęstości:
płynny `.shell` (marginesy rosnące z viewportem) i siatki kart
`grid-template-columns: repeat(auto-fill, minmax(...))`.

- wykresy: 1 kolumna < 900 px, **2 kolumny od 900 px (13” = 1280×800)**,
  3 od 1800 px, 4 od 2400 px — więcej kolumn nigdy nie zmniejsza wykresu;
- kafelek statystyk: `minmax(11rem, 1fr)` (9,5 rem poniżej 700 px);
- rytm odstępów: 4 px wewnątrz pigułek, 8 px w wierszach i kafelkach,
  12 px między kartami, 16 px padding karty;
- sticky pasek stanu (filtry + nawigacja widoków) trzyma kontekst przy
  przewijaniu; na ≤ 700 px pasek zawija się do dwóch rzędów, bez przewijania
  w poziomie.

## Elevation & Depth

System jest **płaski z tonalną głębią**: kolejne poziomy to coraz jaśniejsza
(ciemny motyw) albo ciemniejsza (jasny) powierzchnia — `base-100` → `base-200`
→ `base-300`. Cień występuje w dwóch rolach i nigdy jako dekoracja:

- **sticky/overlay** (`0 2px 10px oklch(30% 0.02 255 / 0.18)` w dzień,
  `0 6px 18px -12px oklch(0% 0 0 / 0.75)` w nocy): pasek przyklejony i ramki
  narzędzi, żeby odciąć się od przewijanej treści;
- **focus halo** (`0 0 0 3px color-mix(var(--state) 22%, transparent)`):
  odpowiedź na stan, nie ozdoba.

**The Flat-By-Default Rule.** Powierzchnie są płaskie w spoczynku; cień
pojawia się wyłącznie jako odpowiedź na stan (sticky, focus, hover).

## Shapes

Język form jest miękki i zdyscyplinowany: `0.75rem` dla kart i ramek
(`--radius-box`), `0.5rem` dla kontrolek i pigułek prostokątnych
(`--radius-field`, `--radius-selector`), pełny okrąg dla pigułek stanu i
kropek. Obramowania mają **1 px** — nigdy grubsza krawędź boczna jako
ozdobnik. Wykresy są prostokątne z zaokrągleniem karty; nic nie jest
przycinane w nietypowy sposób.

## Components

### Buttons
- **Shape:** `0.5rem`, wysokość 32 px (tap target ≥ 24 px wymuszony
  negatywnym marginesem, nie mniejszym przyciskiem).
- **Primary (`.btn-ops`):** powierzchnia `base-200`, obramowanie `base-300`,
  tekst `base-content`; 13 px, waga 500.
- **Hover / Focus:** tło `base-300`, `:focus-visible` z 2 px obwódką akcentu
  i offsetem 2 px.
- **Ghost:** bez tła, tekst `subtle`; używany w nawigacji widoków.

### Chips (filtry, przełączniki zakresu)
- **Style:** pigułka `base-200` + 1 px `base-300`; aktywna: tło akcentu
  zmieszane z tłem (`color-mix`), tekst `base-content`, `aria-pressed=true`.
- **State:** zaznaczona/niezaznaczona różni się tłem i wagą, nigdy samym
  kolorem tekstu.

### Cards / Containers
- **Corner Style:** `0.75rem`.
- **Background:** `base-200` (sekcje), `base-100` + obramowanie (wiersze list).
- **Shadow Strategy:** tylko sticky/overlay (patrz Elevation).
- **Border:** 1 px `base-300`.
- **Internal Padding:** 16 px (nagłówek karty 12 px 16 px).

### Inputs / Fields
- **Style:** tło `base-100`, obramowanie 1 px `base-300`, promień `0.5rem`,
  wysokość 32 px, 13 px tekstu.
- **Focus:** obwódka akcentu (bez zewnętrznego cienia), kursor w kolorze akcentu.
- **Disabled:** tekst `subtle` + `--state-disabled`.

### Navigation
Poziomy pasek w karcie: nazwa widoku + przełączniki (Stan / Wykresy / Logi).
Aktywny widok oznaczony tłem i wagą 600 oraz `aria-current`; na ≤ 700 px pasek
zawija się, zachowując kolejność.

### Signature Component — karta wykresu
Wykres jest **kartą z tytułem nad rysunkiem**: tytuł mówi, co to za pomiar
(„CPU — cała maszyna”, „Sieć (rx / tx) — api”), pod nim rysunek 240 px
wysokości, pod nim statystyki (teraz / maks. / średnia) i linia limitu
przerywaną kreską. Osie mają 4–6 „ładnych” wartości z jednostką; etykiety czasu
dobierają gęstość do szerokości karty, a przy 7 dniach pokazują datę.
Najechanie daje pionową linię i wartości wszystkich serii (nie sam kolor).

## Do's and Don'ts

### Do:
- **Do** używaj tokenów motywu (`var(--color-*)`, `color-mix(... base-content ...)`)
  — każdy kolor musi przetrwać zmianę `prefers-color-scheme`.
- **Do** nadawaj każdej liczbie jednostkę i kontekst (limit, próg, zakres czasu).
- **Do** rozróżniaj serie wykresu kolorem **i** stylem linii (przerywana/dash).
- **Do** utrzymuj kontrast ≥ 4,5:1 dla tekstu i ≥ 3:1 dla linii/osobnych
  elementów graficznych w **obu** motywach (zmierzone, nie założone).
- **Do** trzymaj tap targety ≥ 24 px, także w ciasnych nagłówkach.
- **Do** ustawiaj `color-scheme` zgodnie z motywem, żeby kontrolki przeglądarki
  (scrollbar, pola, kursor) nie odstawały.

### Don't:
- **Don't** wpisuj kolorów na sztywno w komponentach ani w skryptach —
  wykresy i tooltipy rysują się z tokenów motywu.
- **Don't** dodawaj grubszej niż 1 px kolorowej krawędzi bocznej jako ozdobnika.
- **Don't** animuj `width`/`height` w pętli odświeżania; animacje tylko
  `transform`/`opacity` i wyłącznie przy `prefers-reduced-motion: no-preference`.
- **Don't** udawaj danych: brak serii to pusty wykres z komunikatem, nie linia
  na zerze, a brak pomiaru to „—”, nie `0`.
- **Don't** zmieniaj układu przy odświeżeniu danych co 5–10 s (żadnej przebudowy
  listy, żadnego skoku przewijania).
