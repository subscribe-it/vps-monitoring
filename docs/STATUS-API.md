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
          "restarts_1h": 0, "replicas_text": "1/1" }
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
  "security": { "ssh_failed_24h": 203, "ssh_bans_24h": null, "logins_24h": [], "state": "ok" },
  "tools": [
    { "id": "grafana", "name": "Grafana", "url": "/grafana", "embed": true,
      "embed_query": "kiosk", "state": "ok", "kind": "internal", "icon": "chart-line",
      "description": "…" }
  ]
}
```

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
- Sekcja `security` liczy się z Loki (`LOKI_URL`), bo promtail zbiera journald
  hosta: `ssh_failed_24h` to `count_over_time` linii „Failed password"
  z jednostki `ssh.service`, a `logins_24h` to ostatnie 20 linii „Accepted"
  (użytkownik, IP, czas). Gdy Loki nie odpowiada, `state` = `unknown`,
  a liczniki są `null` — panel pokazuje wtedy „—", żeby nie udawać zera.
  Bany (`ssh_bans_24h`) są `null`, bo fail2ban pisze do journala tylko
  start/stop; pełne dane da zewnętrzny `SECURITY_JSON_URL` (ma pierwszeństwo).
