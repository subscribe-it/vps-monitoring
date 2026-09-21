# notifier

Jedyne wyjście alertów. Odbiera webhooki Alertmanagera, zdarzenia zewnętrzne
(np. nieudane GitHub Actions) oraz pingi watchdoga i rozsyła powiadomienia dwoma
niezależnymi kanałami: **ntfy** i **e-mail**. Błąd jednego kanału nigdy nie
przerywa drugiego.

## Endpointy (domyślnie port 8080)

| Endpoint | Opis |
| --- | --- |
| `GET /health` | status serwisu, informacja o skonfigurowanych kanałach i ostrzeżenia konfiguracji |
| `GET /metrics` | Ekspozycja Prometheusa (`text/plain; version=0.0.4`) |
| `POST /webhook` | odbiornik Alertmanagera (format webhooka, `version: "4"`) |
| `POST /watchdog` | ping dead-man's switch samego monitoringu (`HC_PING_MONITORING`) |
| `POST /alert` | zdarzenia zewnętrzne; wymaga nagłówka `X-Auth-Token: $NOTIFIER_TOKEN` |

`GET`/`HEAD` na trasach POST zwraca 405, nieznane trasy 404, a `SIGTERM` zamyka
serwis czysto.

### Kody odpowiedzi

| Sytuacja | Kod |
| --- | --- |
| cokolwiek wysłano | `200` |
| oba kanały nieskonfigurowane (wszystko `skipped`) | `200` — ponawianie nic nie da |
| kanał(y) próbowały wysłać i wszystkie zawiodły | `500` |
| `POST /alert` bez/złym tokenem | `403` |
| nieprawidłowy JSON / pusty webhook | `400` |

### Format wiadomości ntfy

- Tytuł: `[CRITICAL] <alertname> · <stack>`; dla grupy z wieloma alertami
  `[CRITICAL] <alertname> (+N) · <stack>`; dla wygaszenia `[RESOLVED] ...`.
- Priorytet: `NTFY_PRIORITY_CRITICAL` (`urgent`) dla critical,
  `NTFY_PRIORITY_WARNING` (`default`) dla warning, `low` dla info.
- Treść: `summary` + `description` z adnotacji, lista grupy (maks. 10 pozycji,
  potem `…i N więcej`) i link do `ALERT_BASE_URL`.
- Nagłówki żądania: `Title`, `Priority`, `Tags`, a przy ustawionym tokenie
  `Authorization: Bearer <NTFY_TOKEN>`. Adres: `<NTFY_URL>/<NTFY_TOPIC>`.

### Grupowanie

Alertmanager wysyła wiele alertów w jednym webhooku — wysyłane jest **jedno**
powiadomienie ntfy i **jeden** e-mail na grupę, z listą alertów w treści
(maks. 10 pozycji + „…i N więcej").

### E-mail

Tylko dla `severity >= EMAIL_MIN_SEVERITY` (domyślnie `warning`) — dla `info`
kanał jest pomijany ze statusem `skipped`. Temat:
`[monitoring] <status> <alertname> (<stack>)`. Wysyłka przez `smtplib.SMTP_SSL`
gdy `SMTP_SECURE=true`, inaczej `SMTP` + `starttls()`. Gdy brak `SMTP_HOST`
lub `ALERT_EMAIL_TO` — `skipped`.

## Metryki

`notifier_notifications_total{channel="ntfy|email",status="sent|failed|skipped"}`,
`notifier_last_notification_timestamp_seconds{channel}`,
`notifier_watchdog_pings_total{status="sent|failed"}`,
`notifier_last_watchdog_ping_timestamp_seconds`, `notifier_up`.

## Zmienne środowiskowe

| Zmienna | Domyślnie | Opis |
| --- | --- | --- |
| `NTFY_URL` | `https://ntfy.sh` | baza ntfy |
| `NTFY_TOPIC` | puste | temat; puste → kanał `skipped` |
| `NTFY_TOKEN` | puste | token Bearer (opcjonalny) |
| `NTFY_PRIORITY_CRITICAL` | `urgent` | priorytet dla critical |
| `NTFY_PRIORITY_WARNING` | `default` | priorytet dla warning |
| `SMTP_HOST` | puste | serwer SMTP; puste → e-mail `skipped` |
| `SMTP_PORT` | `587` | port SMTP |
| `SMTP_SECURE` | `false` | `true` → `SMTP_SSL`, `false` → `starttls()` |
| `SMTP_USERNAME` / `SMTP_PASSWORD` | puste | logowanie do SMTP |
| `ALERT_EMAIL_FROM` | puste | nadawca (domyślnie `SMTP_USERNAME`) |
| `ALERT_EMAIL_TO` | puste | adresaci (lista po przecinku) |
| `EMAIL_MIN_SEVERITY` | `warning` | minimalna severity dla e-maila |
| `ALERT_BASE_URL` | puste | link do panelu doklejany do treści |
| `HC_PING_MONITORING` | puste | URL dead-man's switch monitoringu |
| `WATCHDOG_PING` | puste | `0/false` wyłącza watchdog; pełny URL nadpisuje `HC_PING_MONITORING` |
| `NOTIFIER_TOKEN` | puste | token wymagany przez `POST /alert` (puste → zawsze 403) |
| `PORT` | `8080` | port HTTP |

## Zachowanie przy braku zależności

Serwis nie ma lokalnych zależności — awaria ntfy lub SMTP nie zatrzymuje procesu,
tylko zwiększa `notifier_notifications_total{status="failed"}` i zwraca 500 (gdy
nic nie zostało wysłane). `notifier_up` opisuje sam proces.

## Ustalenia i odstępstwa

- Gdy **oba** kanały są nieskonfigurowane, `/webhook` zwraca `200`, a nie `500`:
  Alertmanager ponawiałby wtedy żądania bez szansy na sukces. Sytuacja jest
  widoczna w `notifier_notifications_total{status="skipped"}` i w `/health`.
- `WATCHDOG_PING` przyjmowany jest jako flaga (`0/false` wyłącza watchdog) albo
  jako pełny URL; domyślnym celem jest `HC_PING_MONITORING`.
- Porównanie tokenu w `/alert` odbywa się na skrótach SHA-256 (`hashlib`), żeby
  nie porównywać sekretów znak po znaku.
- `POST /alert` bez skonfigurowanego `NOTIFIER_TOKEN` zawsze zwraca `403`
  (fail-closed).

## Uruchomienie

```bash
docker build -t monitoring/notifier services/notifier
docker run --rm -p 8080:8080 \
  -e NTFY_TOPIC=moj-monitoring -e NTFY_TOKEN=tk_xxx \
  -e SMTP_HOST=smtp.example.com -e ALERT_EMAIL_TO=ja@example.com \
  -e NOTIFIER_TOKEN=sekret \
  monitoring/notifier
```

Kontener działa jako UID 10001 i nie zapisuje niczego poza `/tmp`.
