# Co zostało zweryfikowane (i jak)

Ten dokument odróżnia **udowodnione uruchomieniem** od **założonego**. Powstał, bo
w trakcie prac pięć błędów tej samej klasy przeszło walidację statyczną i wyszło
dopiero przy uruchomieniu: plik konfiguracyjny był w repo, ale nie działał.

Zasada: jeśli czegoś tu nie ma, nie zakładaj, że działa — sprawdź.

## Zweryfikowane uruchomieniem (z dowodem)

| Co | Jak sprawdzone | Wynik |
| --- | --- | --- |
| Stack wstaje w całości | `make up` (12 usług lokalnie) | 12/12 zdrowych |
| Prometheus: config + reguły | `promtool check config/rules` + uruchomiony Prometheus | 44 reguły w 6 grupach |
| Progi alertów faktycznie działają | `promtool test rules` (13 przypadków) | zapalają się i **nie** zapalają na szum |
| Loki: config + 15 reguł | `loki -verify-config` + API rulera | 15 reguł w 4 grupach |
| Alert logowy → Alertmanager | wstrzyknięty log „page verification failed" | alert `PgPageVerificationFailed` z `stack`/`service` |
| Dalsze reguły logowe | wstrzyknięte zdarzenia (25× 5xx, ACME, SSH, jądro, Cockpit) | `AcmeCertificateRenewalFailed`, `SshLoginAccepted`, `KernelDiskErrors`, `CockpitLogin` |
| Potok access logu Traefika | prawdziwy plik → promtail (`| json`) → Loki | zapytanie reguły zwraca 4 błędy z 7 wpisów (kontrola negatywna OK) |
| Journald → Loki | promtail z realnym journalem | strumienie `{job="journald", transport="kernel"}`, `unit=…` |
| Kanał ntfy | atrapa serwera ntfy | `Title`, `Priority: urgent`, `Authorization: Bearer`, treść grupowa |
| Watchdog healthchecks.io | atrapa hc.io | `POST /ping/<uuid>` z treścią |
| Blackbox: moduły sond | `probe?module=…` na żywym eksporterze | `http_expect_auth` 401→sukces, 200→porażka; `tcp_connect`; certyfikaty |
| Grafana: provisioning | uruchomiona Grafana | 4 dashboardy, `database: ok` |
| Panel w przeglądarce | Chrome DevTools na zbudowanym obrazie | 0 błędów w konsoli, 7 sekcji, iframe 704/800 px, 375 px bez przewijania |
| Kontrakt panel ↔ discovery | prawdziwy `/status/api.json` → parser panelu | `isStatusSnapshot` = true, formatowanie pl-PL |
| Logowanie do Grafany przez nagłówek | `curl` z i bez `X-User` | bez nagłówka 401 (bezpieczny fallback), z nagłówkiem zalogowany jako **Org Admin** |
| Testy progów alertów | `promtool test rules`, 6 plików | wszystkie grupy reguł pokryte (44 reguły) |
| Auto-discovery | atrapa Docker API (`tests/integration/`) | wykrywa `Host(...)` i `PathPrefix`, pomija `skip`, tryb global, zadanie padnięte jako 1/2 |
| Serwisy Pythona | 191 testów jednostkowych | wszystkie przechodzą |
| Walidacja przed wdrożeniem | `docker stack config` (schemat Swarma) | przechodzi |

## Zmierzone (nie zgadywane)

- `/containers/<id>/stats?stream=false` trwa **~1,9 s** na wywołanie. Przy 32
  kontenerach i 8 wątkach cykl odświeżania `discovery` to **~8–12 s** — mieści się
  w interwale 30 s, ale gdyby kontenerów zrobiło się 3× więcej, trzeba podnieść
  `DISCOVERY_REFRESH_SECONDS` albo ograniczyć liczbę próbkowanych kontenerów.
- Certyfikat `app.ventiplan.pl`: **67,4 dnia** do wygaśnięcia (stan na 2026-09-22).

## Znane kruchości (świadome, z obejściem)

1. **Promtail nie wstaje, jeśli katalog journala nie istnieje.** Brak
   `/var/log/journal` kończy start CAŁEGO procesu, nie tylko celu journald —
   czyli tracisz wszystkie logi. Compose montuje oba możliwe katalogi
   (`/var/log/journal` i `/run/log/journal`); objaw widać jako crash-loop
   i alert `PromtailDown`.
2. **Pierwsze uruchomienie promtaila odrzuca stare logi** (`reject_old_samples_max_age: 168h`).
   To poprawne zachowanie, ale w logach pojawią się błędy 400, dopóki nie
   dogoni bieżącego ogona.
3. **Nazwa middleware w Swarmie dostaje prefiks stacku** (`monitoring-mon-auth@swarm`).
   Jeśli po wdrożeniu wszystkie ścieżki zwracają 404, zmień odwołanie na
   `mon-auth@swarm` — smoke test w CI to wykryje (oczekuje 401).

## Czego NIE da się sprawdzić bez wdrożenia

- faktyczne trasowanie Traefika (reguły, priorytety, certyfikat dla nowej domeny),
- pełny łańcuch ForwardAuth w przeglądarce (sam mechanizm nagłówka Grafany jest
  sprawdzony, brakuje przejścia basic-auth → Traefik → iframe w realnej domenie),
- zachowanie `discovery` na prawdziwym menedżerze Swarma (na atrapie tak,
  ale `/services` z prawdziwego roju to inny kod po stronie demona),
- realne dostarczenie powiadomienia na telefon i do skrzynki.
