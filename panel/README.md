# Panel monitoringu

Statyczny panel (landing page) monitoringu VPS — strona startowa pod
`https://monitoring.subscribeit.pl/`. Pokazuje żywy stan infrastruktury i pozwala
przechodzić do narzędzi (Grafana, Prometheus, Alertmanager, Portainer…) bez
opuszczania widoku głównego.

Panel jest w całości statyczny: HTML + jeden mały skrypt. Nie ma backendu, CDN,
frameworków JS w przeglądarce ani żadnych zapytań do internetu w czasie działania.
Dane pochodzą wyłącznie z `GET /status/api.json` na tym samym originie.

## Szybki start (lokalnie)

```bash
cd panel
pnpm install
pnpm dev        # http://localhost:4321
```

Podgląd produkcyjnego builda:

```bash
pnpm build      # wynik w panel/dist
pnpm preview
```

Kontrola typów (włącznie ze skryptami w plikach `.astro`):

```bash
pnpm exec astro check
```

Wymagania: Node.js >= 22.12 (obrazy używają `node:24-alpine`) oraz pnpm 10.

### Praca lokalna bez danych

`/status/api.json` nie istnieje w trybie `dev`, więc panel pokaże banner
„brak danych” i puste stany sekcji — to zachowanie poprawne, nie błąd. Żeby
zobaczyć panel z danymi, podstaw plik pod ten adres (np. przez proxy w
`astro.config.mjs`) albo uruchom go za reverse proxy, które trasuje `/status/`.

## Docker

```bash
cd panel
docker build -t vps-monitoring-panel .
docker run --rm -p 8080:80 vps-monitoring-panel
# http://localhost:8080
```

Obraz jest dwuetapowy: `node:24-alpine` + pnpm budują `dist/`, a wynik trafia do
`nginx:alpine`. Kontener nasłuchuje na porcie **80** i wystawia `/healthz` na
potrzeby healthchecka.

W obrazie nie ma nic poza statycznymi plikami i konfiguracją nginx. `nginx.conf`
ustawia:

- `server_tokens off` — brak wycieku wersji w nagłówku `Server`,
- `index.html` i nieznane ścieżki: `Cache-Control: no-store`,
- `/assets/*`: `Cache-Control: public, max-age=31536000, immutable` (nazwy mają hash),
- poprawne typy MIME (`include /etc/nginx/mime.types`),
- `X-Content-Type-Options`, `Referrer-Policy`, `X-Frame-Options`,
  `Content-Security-Policy: frame-ancestors 'self'`.

> Uwaga: w nginx `add_header` **nie dziedziczy się** do bloku `location`, który ma
> własny `add_header`. Dlatego nagłówki bezpieczeństwa są powtórzone w każdym
> miejscu, które ustawia własne nagłówki — to celowe, nie duplikacja przypadkowa.

### Reverse proxy i basic auth

Ten kontener serwuje **wyłącznie** statyczny panel. `/status/api.json`, Grafana,
Prometheus itd. są trasowane przez zewnętrzny reverse proxy na tym samym
originie (i tam jest basic auth). Dzięki temu panel czyta dane i osadza narzędzia
w `<iframe>` bez CORS i bez drugiego logowania.

Jeżeli kiedyś panel ma być jedynym wejściem, w `nginx.conf` jest zakomentowany
blok `location /status/` do proxowania API statusu.

## Kontrakt danych: `GET /status/api.json`

To samo pochodzenie (same-origin), ciasteczka wysyłane domyślnie
(`credentials: 'same-origin'`), odpytywane co **30 s**. Odpowiedź:

```json
{
  "generated_at": "2026-09-21T19:45:00Z",
  "overall": "ok",
  "host": {
    "cpu_percent": 12.3, "load1": 0.87, "load5": 0.97, "load15": 0.83,
    "mem_total_bytes": 24583045120, "mem_used_bytes": 7728000000, "mem_used_percent": 31.4,
    "swap_total_bytes": 0,
    "disk_total_bytes": 207000000000, "disk_used_bytes": 52000000000, "disk_used_percent": 25.1,
    "inodes_used_percent": 7.0,
    "uptime_seconds": 6470100,
    "time_utc": "2026-09-21T19:45:00Z"
  },
  "checks": [
    { "id": "public:app.ventiplan.pl", "name": "VentiPlan — aplikacja", "group": "Produkcja",
      "kind": "http", "state": "ok", "detail": "HTTP 200 · 0,21 s", "url": "https://app.ventiplan.pl",
      "since": "2026-09-21T18:00:00Z", "latency_ms": 209 }
  ],
  "stacks": [
    { "name": "ventiplan-prod", "state": "ok", "services_running": 7, "services_desired": 7,
      "services": [ { "name": "api", "full_name": "ventiplan-prod_api", "state": "ok", "desired": 1, "running": 1,
                      "image": "ghcr.io/subscribe-it/stropio-api:prod", "cpu_percent": 1.2, "mem_bytes": 125829120,
                      "restarts_1h": 0, "replicas_text": "1/1" } ] }
  ],
  "certs": [ { "host": "app.ventiplan.pl", "days_left": 61.5, "expires_at": "2026-11-22T00:00:00Z", "state": "ok" } ],
  "backup": { "state": "ok", "last_success_at": "2026-09-21T03:15:00Z", "age_hours": 16.5, "size_bytes": 12345678, "objects_in_r2": 30, "restore_test_days": 12 },
  "alerts": [ { "name": "AppDown", "severity": "critical", "stack": "ventiplan-prod", "summary": "brak odpowiedzi 200", "since": "2026-09-21T18:30:00Z" } ],
  "security": { "ssh_failed_24h": 416, "ssh_bans_24h": 53, "logins_24h": [ { "service": "cockpit", "ip": "1.2.3.4", "at": "2026-09-21T12:00:00Z" } ], "state": "warning" },
  "tools": [
    { "id": "status", "name": "Stan usług", "url": null, "embed": false, "state": "ok", "kind": "internal", "icon": "activity", "description": "Widok domyślny" },
    { "id": "grafana", "name": "Grafana", "url": "/grafana", "embed": true, "embed_query": "kiosk", "state": "ok", "kind": "internal", "icon": "chart-line", "description": "Dashboardy i logi" },
    { "id": "prometheus", "name": "Prometheus", "url": "/prometheus", "embed": true, "state": "ok", "kind": "internal", "icon": "database", "description": "Metryki i targety" },
    { "id": "alertmanager", "name": "Alertmanager", "url": "/alertmanager", "embed": true, "state": "ok", "kind": "internal", "icon": "bell", "description": "Aktywne alerty" },
    { "id": "healthchecks", "name": "Healthchecks.io", "url": "https://healthchecks.io/checks", "embed": false, "state": "ok", "kind": "external", "icon": "heart-pulse", "description": "Watchdog zewnętrzny" },
    { "id": "portainer", "name": "Portainer", "url": "https://portainer.subscribeit.pl", "embed": false, "state": "ok", "kind": "external", "icon": "container", "description": "Zarządzanie stackami" }
  ]
}
```

### Stany

`state` / `overall` / `severity` przyjmują wartości:
`"ok"` · `"warning"` · `"critical"` · `"unknown"` · `"disabled"`.

Wartość spoza tej listy (albo brak pola) jest traktowana jako `"unknown"` —
panel nigdy nie wywala się na nieoczekiwanym stanie.

### Pola opcjonalne i tolerancja danych

`src/lib/status.ts` parsuje odpowiedź **bez rzucania wyjątków**: brakujące lub
błędne pole staje się `null`, pustą tablicą albo stanem `unknown`, a widok pokazuje
kreskę (`—`). Pola, które mogą być `null`: `url`, `detail`, `since`, `latency_ms`,
`stack`, `summary`, `expires_at`, `backup`, `security`, całe `host`.

`overall` jest używane wprost; jeśli go brak, panel liczy stan ogólny jako
najgorszy ze stanów `checks`, `stacks`, `certs`, `alerts`, `backup`, `security`.

`tools[].icon` to nazwa ikony lucide (np. `chart-line`). Ikona spoza wbudowanej
listy dostaje bezpieczny zamiennik (`box`) — kafelek nigdy nie zostaje pusty.

## Jak działa panel

### Odświeżanie i odporność na brak danych

- pobranie co 30 s, „cicho”, bez przeładowania strony; dodatkowo odświeżenie po
  powrocie do karty, jeśli dane są nieaktualne,
- równoległe pobrania nie nakładają się, request ma limit 12 s,
- **błąd pobrania nie czyści widoku** — ostatnie dane zostają, pojawia się banner
  `role="alert"`: „Ostatnia udana aktualizacja o … (… temu)”, a znacznik świeżości
  przy nagłówku zmienia się na ostrzegawczy po 3 nieudanych cyklach,
- gdy nie udało się pobrać nic od startu, każda sekcja pokazuje jawny komunikat
  „Brak danych o …”, a nie pustą kartę,
- w kodzie nie ma `console.error`; awaria sieci nie zaśmieca konsoli.

### Routing po hashu

| Adres | Widok |
| --- | --- |
| `#/` | widok stanu (domyślny) |
| `#/tool/<id>` | podgląd narzędzia w `<iframe>` |
| `#/wykresy` | wykresy per usługa (własne, bez ramki Grafany) + ranking „Top 10 usług" |
| `#/wykresy/<stack>/<usługa>?zakres=1h\|6h\|24h\|7d` | szczegóły usługi: cztery duże wykresy, diagnostyka |
| `#/logi` | logi: źródło (usługa / host / Traefik), filtr, limit linii |
| `#/logi/<stack>/<usługa>?zakres=15m\|1h\|24h&zrodlo=usluga\|host\|traefik` | logi jednej usługi |

Routing opiera się na zdarzeniu `hashchange`, więc przycisk wstecz/dalej
przeglądarki działa, a widok odtwarza się po odświeżeniu strony.

### Widok „Wykresy" (bez ramki Grafany)

Po co: żeby ocenić zużycie nie trzeba wchodzić do Grafany — osadzona ramka oddaje
wykresy razem z cudzą nawigacją i nie da się w niej przeskoczyć „ta usługa, ale
w 24 h".

**Układ (wymagania użytkownika):**

- **Podmiot wybiera się na górze** (wzorzec z widoku „Logi"): `Cały VPS
  (node-exporter)`, `Wszystkie usługi (CPU i RAM)` oraz każda usługa jako
  `stack / usługa`. Domyślnie **cały VPS**. Wybór siedzi w haszu, więc link
  „ta usługa w 24 h, co 5 s" działa i przeżywa odświeżenie.
- **Maksymalnie dwa wykresy w wierszu**, karta do **800 px** szerokości
  (`WYKRES_SZEROKOSC`), rysunek **240 px** wysokości (na ekranie ≤700 px —
  220 px). Na 1980 px karty mają dokładnie 800 px i układają się 2 / 2 / 1.
- **Nad każdym wykresem tytuł**: `CPU — cały VPS`, `RAM — grafana`,
  `Sieć (rx / tx) — na6_pl_prod_wordpress`, `Dysk (odczyt / zapis) — …`.
- **Sekcja = podmiot**: nagłówek z nazwą, stackiem, stanem i replikami oraz
  wyraźny separator (lewa krawędź + własne tło), żeby nie było wątpliwości, gdzie
  kończy się jedna usługa.
- **Tooltip**: najechanie na wykres (albo `Tab` + strzałki) pokazuje pionową
  linię, kropkę na każdej serii oraz czas (UTC, przy 7 d z datą) i wartości
  z jednostkami; przy wykresach dwuseriowych widać nazwy (`rx (odbiór)`,
  `tx (wysyłka)`, `odczyt`, `zapis`). `Esc` zamyka tooltip.

**Co pokazują wykresy:**

| Podmiot | Wykresy |
| --- | --- |
| Cały VPS | CPU, RAM (linia = pamięć całkowita), Sieć rx/tx, Dysk (linia = pojemność `/`), Obciążenie (linia = liczba rdzeni) |
| Jedna usługa | CPU (linia = limit z API), RAM (linia = limit), Sieć rx/tx, Dysk odczyt/zapis + diagnostyka usługi |
| Wszystkie usługi | CPU i RAM każdej usługi (dwa wykresy na sekcję — 47 usług × 4 wykresy co 10 s byłoby zbyt ciężkie) |

**Odświeżanie „na żywo":** przełącznik `5 s / 10 s (domyślnie) / 30 s /
Wyłączone`. Timer odświeża **dane w miejscu** — podmieniane są tylko atrybuty
`points` i teksty, więc lista nie jest przebudowywana, przewijanie i stan
kontrolek zostają (zmierzone: ten sam węzeł w DOM i `scrollY` zachowany po
cyklu). Gdy karta przeglądarki jest w tle (`document.hidden`), nie leci **żadne**
zapytanie; po powrocie na kartę dane dociąga `visibilitychange`. „Wyłączone"
to zero zapytań w tle (zmierzone: 0 przez 12 s).

**Dane:** wartości bieżące i limity z `/status/api.json`, przebiegi z
`/prometheus/api/v1/query_range` (ten sam origin, przez proxy panelu).
Zapytań jest **16 na pełny cykl** — 7 metryk usług (`sum by (stack, service) (…)`)
i 9 metryk `node_*` dla VPS-a — a nie 3 na usługę (przy 47 usługach byłoby
~200 żądań). Cache: 60 s przy wejściu w widok, 2 s przy odświeżaniu na żywo.

**Limity:** CPU i RAM z API (`cpu_limit_cores`, `mem_limit_bytes` — discovery
czyta je ze spec usługi Swarm), a gdy API ich nie zna, RAM schodzi na metrykę
`swarm_container_memory_limit_bytes`. Gdy limitu nie ma, interfejs pisze wprost
„limit: brak w API" — **nie zgadujemy progu**. Sieć i dysk limitu nie mają.

**Rysowanie:** własne `<polyline>` w SVG, zero zewnętrznych bibliotek; każdy
wykres ma `role="img"` i `aria-label` z podsumowaniem (teraz / maksimum).

**Czysta logika** (zakresy, odświeżanie, trasa z podmiotem, formatowanie,
procenty limitów, osie, geometria, tooltip) siedzi w `src/lib/wykresy.ts`
i jest testowana Node'em: `node scripts/ci/check_wykresy.mts`
(**203 sprawdzenia** w CI, krok „Testy logiki wykresów" w jobie `panel`).

Kafelek z `"embed": true` ładuje narzędzie w tym samym widoku; kafelek z
`"embed": false` otwiera nową kartę (`target="_blank" rel="noopener"`). Kafelek
bez `url` (np. `status`) prowadzi do widoku stanu.

W widoku podglądu kafelki zamieniają się w zwarty, poziomy pasek przełączania,
nagłówek i sekcje stanu znikają, a `iframe` zajmuje całą pozostałą wysokość.
W ramce trzymane jest **jedno** osadzenie naraz: przełączenie narzędzia ładuje
nowe, a powrót do widoku stanu nie usuwa ramki (dzięki temu narzędzie nie traci
swojego stanu przy skoku do stanu i z powrotem).

### Zero zależności w runtime

- brak CDN, brak Google Fonts, brak `@font-face` — wyłącznie systemowy stos fontów,
- ikony interfejsu są kompilowane do SVG na etapie budowania (`astro-icon`),
- ikony narzędzi z `tools[].icon` przychodzą w danych runtime, więc nie mogą być
  kompilowane przez `astro-icon` — dla nich build generuje mały sprite SVG
  (`IconSprite.astro`, lista nazw w `src/lib/icons.ts`), a klient używa
  `<use href="#i-…">`,
- jedyne „zewnętrzne” adresy w `dist/` to komentarz licencyjny TailwindCSS
  i przestrzeń nazw SVG (`http://www.w3.org/2000/svg`, nie jest pobierana).

### Widok „Logi" (`#/logi`)

Po co: przy incydencie najpierw czyta się linie, a dopiero potem idzie w narzędzia.
Wcześniej jedyną drogą były ramka Grafany (z jej nawigacją) albo `docker service logs`
po SSH.

- **Źródła**: kontenery wybranej usługi (`job="docker"`), journal hosta
  (`job="journald"`, m.in. sshd i jądro) oraz access log Traefika (`job="traefik"`).
- **Zapytanie buduje serwer** (`GET /status/logs` w usłudze discovery) z parametrów
  `zrodlo`, `stack`, `usluga`, `zakres`, `limit` — tekst użytkownika **nigdy** nie
  trafia do LogQL, a filtr jest zwykłym podciągiem (bez rozróżniania wielkości liter,
  kilka słów = AND).
- **Zakres**: 15 min / 1 h / 24 h; **limit linii**: 200 / 500 / 1000 (Loki bez limitu
  potrafi oddać dziesiątki tysięcy linii).
- **Akcje**: kopiowanie widocznych linii, pobranie `.log`, deep link „Otwórz w Grafanie"
  (Explore z tym samym zapytaniem), licznik „widoczne z pobranych".
- Pusty wynik tłumaczy się wprost: dla Traefika przypomina, że access log edge’a bywa
  wyłączony (alert `TraefikNoAccessLogs`), a brak linii nie znaczy „brak ruchu".
- Trasa i filtry siedzą w `src/lib/logi.ts` (testy: `node scripts/ci/check_logi.mts`),
  a panel używa wyłącznie `textContent` — logi to dane z zewnątrz, więc zero `innerHTML`.

### Diagnostyka usługi (oba widoki)

W szczegółach usługi (widok stanu **i** widok wykresów) panel pokazuje: obraz bez
digestu + skrót `sha256:…`, czas ostatniej aktualizacji („2 h temu · data UTC"),
restarty z ostatniej godziny oraz **powód padnięcia zadania** prosto z Dockera
(`last_task_state` + `last_task_error`, np. „No such image: …" albo „unhealthy
container"). Do tego trzy przyciski kopiowania gotowych komend
(`docker service ps --no-trunc`, `docker service logs --tail 200`,
`docker service inspect`) i link do Portainera.

**Panel jest tylko do odczytu** — nie restartuje, nie skaluje i nie usuwa niczego.
Komendy są do wklejenia na hoście, świadomie, po SSH. Test pilnuje, żeby wśród
komend nie pojawiła się żadna operacja zmieniająca
(`node scripts/ci/check_usluga.mts`).

## Dostępność

- kontrast tekstu zgodny z WCAG AA — zmierzone dla 48 stylów tekstu w panelu,
  najniższy wynik **4,97:1** (próg 4,5:1); najciemniejszy stan (`disabled`) jest
  dobrany pod ten próg,
- `aria-label` na kafelkach narzędzi, wskaźniku stanu ogólnego, zwijanych
  wskaźnikach sekcji i paskach zużycia (`role="progressbar"` + `aria-valuenow`
  i `aria-valuetext`),
- banner błędu ma `role="alert"`; tabele usług mają `caption` i nagłówki `th[scope]`,
- widoczny focus (`:focus-visible`), link „Przejdź do treści”,
- `prefers-reduced-motion: reduce` wyłącza przejścia i pulsowanie wskaźnika.

## Progi wizualne (tylko prezentacja)

API zwraca gotowe stany dla sekcji, więc panel ich nie wymyśla. Progi stosowane
są wyłącznie do pokolorowania wartości, które stanu nie mają:

| Wartość | Ostrzeżenie | Krytyczny |
| --- | --- | --- |
| CPU / RAM / dysk / inody | >= 75 % | >= 90 % |
| dni do wygaśnięcia certyfikatu (wyróżnienie liczby) | <= 30 dni | <= 14 dni |

Stan wiersza certyfikatu bierze się z API (`state`), a progi dotyczą tylko
koloru samej liczby dni.

## Struktura

```
panel/
├─ astro.config.mjs        # output: static, Tailwind przez plugin Vite, astro-icon
├─ Dockerfile              # node:24-alpine (build) -> nginx:alpine (runtime)
├─ nginx.conf              # port 80, cache, MIME, server_tokens off
├─ public/favicon.svg
└─ src/
   ├─ layouts/Base.astro           # powłoka HTML, sprite, style
   ├─ pages/index.astro            # widok + cały skrypt klienta
   ├─ styles/global.css            # Tailwind v4 + daisyUI 5 + motyw "ops"
   ├─ lib/status.ts                # typy, formatowanie, parser z walidacją
   ├─ lib/filtry.ts                # filtr, fokus, sortowanie per stack, hasz, CSV
   ├─ lib/wykresy.ts               # zakresy, osie, limity, geometria wykresów, trasa #/wykresy
   ├─ lib/icons.ts                 # lista ikon narzędzi + zamiennik
   └─ components/
      ├─ StatusHeader.astro  HostStat.astro  StatBlock.astro
      ├─ ToolGrid.astro      ToolTile.astro  IframeView.astro
      ├─ FiltersBar.astro    ChangesSection.astro SortableTh.astro
      ├─ WykresyView.astro   # widok „Wykresy": selektor podmiotu, zakresy, odświeżanie, szablony
      ├─ ChecksSection.astro StacksSection.astro CertsSection.astro
      ├─ BackupSection.astro SecuritySection.astro AlertsSection.astro
      ├─ SectionCard.astro   ErrorBanner.astro     IconSprite.astro
```

Komponenty renderują **strukturę** (karty, nagłówki, liczniki) i wzorce wierszy
w `<template>`. Skrypt klienta klonuje wzorce i wypełnia je przez `textContent`,
więc dane z API nigdy nie trafiają do DOM jako HTML.

### Kolejność warstw CSS

Tailwind v4 układa warstwy `theme, base, components, utilities` — klasa
narzędziowa wygrywa z regułą z `@layer components` niezależnie od
specyficzności. Dlatego:

- układ, który ma być nadpisywany przez stan widoku (np. `.tools-grid`), jest
  zdefiniowany w CSS, a nie klasami `grid`/`flex` na tym samym elemencie,
- przełączanie widoków odbywa się atrybutem `hidden` (`display: none !important`),
  a nie klasami ukrywającymi.

## Weryfikacja

```bash
cd panel
pnpm install
pnpm build
pnpm exec astro check
grep -rE "https://fonts|cdn\." dist || echo "brak zewnętrznych odwołań"
du -sh dist
```
