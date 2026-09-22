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

Routing opiera się na zdarzeniu `hashchange`, więc przycisk wstecz/dalej
przeglądarki działa, a widok odtwarza się po odświeżeniu strony.

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
   ├─ lib/icons.ts                 # lista ikon narzędzi + zamiennik
   └─ components/
      ├─ StatusHeader.astro  HostStat.astro  StatBlock.astro
      ├─ ToolGrid.astro      ToolTile.astro  IframeView.astro
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
