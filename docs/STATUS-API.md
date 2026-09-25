# Kontrakt `/status/api.json`

Panel pobiera ten dokument co 30 s (ten sam origin, za ForwardAuth). Serwis
`discovery` może go wygenerować częściowo nawet wtedy, gdy Prometheus nie odpowiada —
w takim przypadku pola uzupełniane są zerami, a `overall` degraduje się do `warning`.

```json
{
  "generated_at": "2026-09-21T19:45:00Z",
  "overall": "ok | warning | critical",
  "host": {
    "cpu_percent": 12.3, "load1": 0.87, "load5": 0.97, "load15": 0.83,
    "mem_total_bytes": 0, "mem_used_bytes": 0, "mem_used_percent": 31.4,
    "swap_total_bytes": 0,
    "disk_total_bytes": 0, "disk_used_bytes": 0, "disk_used_percent": 25.1,
    "inodes_used_percent": 7.0, "uptime_seconds": 6470100, "time_utc": "…"
  },
  "checks": [
    { "id": "public:app.ventiplan.pl", "name": "VentiPlan — aplikacja", "group": "Produkcja",
      "kind": "http", "state": "ok", "detail": "HTTP 200 · 0,21 s",
      "url": "https://app.ventiplan.pl", "since": "…", "latency_ms": 209 }
  ],
  "stacks": [
    { "name": "ventiplan-prod", "state": "ok", "services_running": 7, "services_desired": 7,
      "services": [
        { "name": "api", "full_name": "ventiplan-prod_api", "state": "ok",
          "desired": 1, "running": 1, "image": "ghcr.io/…:prod",
          "cpu_percent": 1.2, "mem_bytes": 125829120,
          "cpu_limit_cores": 0.25, "mem_limit_bytes": 536870912,
          "restarts_1h": 0, "replicas_text": "1/1",
          "updated_at": "2026-09-22T19:09:51Z",
          "last_task_state": "rejected",
          "last_task_error": "No such image: coreruleset/modsecurity-crs:4.26.0-nginx-alpine" }
      ] }
  ],
  "certs": [
    { "host": "app.ventiplan.pl", "days_left": 61.5, "expires_at": "…", "state": "ok" }
  ],
  "backup": { "state": "ok", "last_success_at": "…", "age_hours": 16.5,
              "size_bytes": 0, "objects_in_r2": 0, "restore_test_days": 12 },
  "alerts": [
    { "name": "AppDown", "severity": "critical", "stack": "ventiplan-prod",
      "summary": "…", "since": "…" }
  ],
  "security": { "ssh_failed_24h": 203, "ssh_bans_24h": 12,
                "ssh_failed_ips": [ { "ip": "45.148.10.10", "count": 41 } ],
                "ssh_failed_sources": 7, "logins_24h": [], "state": "ok" },
  "ataki": {
    "state": "ok", "zrodlo_aktywne": true, "zdarzenia_24h": 21,
    "wzorce": [ { "klucz": "xss", "nazwa": "XSS (wstrzyknięcie skryptu)", "ile": 7 } ],
    "top_ip": [ { "ip": "45.148.10.10", "ile": 19, "wzorce": ["xss", "skaner"] } ],
    "top_sciezki": [ { "sciezka": "/.env", "ile": 12 } ],
    "skanowanie_10m": 1, "ostatnie": "2026-09-21T14:13:20Z"
  },
  "tools": [
    { "id": "grafana", "name": "Grafana", "url": "/grafana", "embed": true,
      "embed_query": "kiosk", "state": "ok", "kind": "internal", "icon": "chart-line",
      "description": "…" }
  ]
}
```

## `GET /status/logs` — logi dla panelu

Panel nie woła Loki'ego wprost: pyta naszą usługę discovery, a ta buduje LogQL
z parametrów strukturalnych. Powody: (1) tekst użytkownika **nigdy** nie trafia do
zapytania ( filtr jest podciągiem po stronie panelu), (2) działa niezależnie od
tego, czy edge wystawia `/loki` na tym samym originie — `/status/*` jest trasowane
na pewno, bo panel już z niego czyta stan.

Parametry (wszystkie nieobowiązkowe, śmieci → wartości domyślne):

| Parametr | Dozwolone wartości | Domyślnie |
| --- | --- | --- |
| `zrodlo` | `usluga` \| `host` \| `traefik` | `usluga` |
| `stack`, `usluga` | nazwy z Dockera (czyszczone do `[A-Za-z0-9_.:/-]`) | — |
| `zakres` | `15m` \| `1h` \| `24h` | `1h` |
| `limit` | `200` \| `500` \| `1000` | `200` |

Odpowiedź `200`:

```json
{ "zrodlo": "usluga", "zakres": "1h", "limit": 200,
  "zapytanie": "{job=\"docker\", stack=\"monitoring\", service=\"monitoring_panel\"}",
  "linie": [ { "czas": 1758567060.123, "tekst": "…", "strumien": "monitoring_panel" } ] }
```

Linie są posortowane malejąco po czasie. `400` = brak usługi przy źródle `usluga`,
`503` = brak `LOKI_URL` albo Loki nie odpowiedziało (pole `error` ma czytelny powód).
Etykieta `service` w Loki ma **prefiks stacka** (`<stack>_<usługa>`), bo tak ustawia
ją promtail z `com.docker.swarm.service.name`.

- Sekcja `ataki` („Ataki i skanowanie") liczy się z **access logu Traefika** w Loki:
  `zdarzenia_24h` to suma dopasowań pięciu wzorców (XSS, SQL injection, path
  traversal, Log4Shell, skanowanie ścieżek), `wzorce` rozbija to na kategorie,
  `top_ip` to adresy z liczbą prób i listą kategorii, `top_sciezki` — najczęściej
  zaczepiane ścieżki, a `skanowanie_10m` mówi, ilu adresów przekroczyło próg
  40 odpowiedzi 4xx w 10 minut (detekcja behawioralna: łapie też payloady, których
  nie ma na liście wzorców).
- **`zrodlo_aktywne: false` znaczy „access log nie płynie"** (albo nie ma ruchu) —
  wtedy `state` = `unknown`, a panel pokazuje „brak danych", NIE zero zdarzeń.
  Zmierzone 25.09.2026: log edge'a nie powstawał od 17.08.2026, więc sekcja jest
  w tym stanie do czasu przywrócenia `--accesslog` w Traefiku (`docs/RUNBOOK.md` → `#logs`).

## Zasady

- `state`: `ok` | `warning` | `critical` | `unknown` | `disabled`.
- Kod 401/403 w sondzie = `ok` (usługa żyje, wymaga logowania).
- `overall`: `critical`, gdy dowolny check jest `critical` lub dowolny stack ma
  `running < desired`; `warning`, gdy cokolwiek jest `warning` lub `discovery_up == 0`.
- Kafelki `embed: true` ładują się w iframe (ten sam origin → jedno logowanie);
  `embed: false` otwierają nową kartę (zewnętrzne serwisy blokują osadzanie).
- `tools[].embed_query` (opcjonalne) to parametry dokładane do adresu podglądu —
  Grafana jedzie z `kiosk`, więc w ramce panelu nie pokazuje własnego menu
  (pomiar na produkcji: 319 px szerokości odzyskane dla wykresów).
- Pole `tools[].url` wewnętrznych narzędzi jest **względne** (`/grafana`) — dzięki temu
  panel działa niezależnie od domeny.
- Limity per usługa pochodzą ze spec usługi Swarm
  (`Spec.TaskTemplate.Resources.Limits`): `cpu_limit_cores` = `NanoCPUs / 1e9`
  (np. 250000000 → 0.25 vCPU), `mem_limit_bytes` = `MemoryBytes`. **Brak limitu
  to `null`, nigdy `0`** — panel odróżnia „limit nieustawiony" (pisze wprost
  „limit: brak w API") od „limit zero", którym nie da się liczyć procentu.
  Panel używa `mem_limit_bytes` jako pierwszego źródła limit RAM, a metrykę
  `swarm_container_memory_limit_bytes` (z `docker stats`) tylko jako fallback;
  limit CPU ma wyłącznie tutaj (metryki go nie wystawiają).
- `updated_at` (ISO Z, `null` gdy brak) to czas ostatniej aktualizacji usługi,
  a `last_task_state` / `last_task_error` opisują **najnowsze zadanie, które
  padło** (`failed` albo `rejected`) — treść `Status.Err` z Dockera, czyli
  dosłowną przyczynę („No such image: …", „task: non-zero exit (137):
  dockerexec: unhealthy container"). Bez danych oba pola są `null`; sam stan bez
  treści też jest możliwy (puste `Err` zamieniamy na `null`, żeby panel pokazał
  „brak danych", a nie pusty prostokąt).
- Sekcja `security` liczy się z Loki (`LOKI_URL`), bo promtail zbiera journald
  hosta: `ssh_failed_24h` to `count_over_time` linii „Failed password"
  z jednostki `ssh.service`, a `logins_24h` to ostatnie 20 linii „Accepted"
  (użytkownik, IP, czas). Gdy Loki nie odpowiada, `state` = `unknown`,
  a liczniki są `null` — panel pokazuje wtedy „—", żeby nie udawać zera.
  Bany (`ssh_bans_24h`) są `null`, bo fail2ban pisze do journala tylko
  start/stop; pełne dane da zewnętrzny `SECURITY_JSON_URL` (ma pierwszeństwo).

## Ścieżka sondy i podpowiedź etykiety

Każdy check w `checks[]` niesie trzy pola, które odróżniają „aplikacja padła" od
„aplikacja żyje, ale nie obsługuje tej ścieżki":

| Pole | Typ | Znaczenie |
| --- | --- | --- |
| `probe_path` | `string` | Ścieżka, którą NAPRAWDĘ sondujemy (np. `/`, `/api`). |
| `path_source` | `string` | Skąd ścieżka: `label` (`monitoring.io/health-path`), `probe` (`monitoring.io/probe`), `rule` (`PathPrefix` z reguły Traefika), `default` (`DEFAULT_PROBE_PATH` albo `/`). |
| `health_label` | `string \| null` | Gotowa linia do wklejenia (`monitoring.io/health-path=/health`), gdy ścieżki nikt nie ustawił świadomie. `null`, jeśli etykieta już jest. |

Panel pokazuje podpowiedź tylko dla stanu `warning` z kodem 4xx i tylko wtedy,
gdy `health_label` istnieje — nigdy nie zgaduje ścieżki za użytkownika.

## Sekcja `security` — źródła nieudanych prób SSH

- `ssh_failed_ips`: do 5 najaktywniejszych adresów (`{ "ip": …, "count": … }`),
  liczone w usłudze discovery po stronie Pythona (etykieta `ip` w promtailu
  oznaczałaby eksplozję liczności w Loki),
- `ssh_failed_sources`: liczba RÓŻNYCH adresów w 24 h (`null`, gdy Loki nie
  odpowiedziało — panel pokazuje wtedy „—", nie zero),
- `ssh_bans_24h`: bany fail2bana z pliku `/var/log/fail2ban.log` (job `fail2ban`).
  Wcześniej liczone z journala, gdzie fail2ban pisze tylko start/stop, więc
  zawsze było `0`/`null`.
