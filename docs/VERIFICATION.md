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
| Każda gałąź każdego regexu logowego | `tests/integration/verify_log_patterns.py` — 52 przypadki, regex czytany z plików reguł | 52/52 reaguje na swoją linię (przed poprawkami 8 gałęzi martwych) |
| Ruler faktycznie wczytał reguły | `scripts/ci/check_ruler_loaded.py` przeciw działającemu Loki | 15 reguł w 4 grupach = dokładnie tyle, ile w plikach |
| Potok access logu Traefika | prawdziwy plik → promtail (`| json`) → Loki | zapytanie reguły zwraca 4 błędy z 7 wpisów (kontrola negatywna OK) |
| Journald → Loki | promtail z realnym journalem | strumienie `{job="journald", transport="kernel"}`, `unit=…` |
| Kanał ntfy | atrapa serwera ntfy | temat i tytuł w treści JSON, `priority` jako liczba, `Authorization: Bearer`, treść grupowa |
| Kanał ntfy — **prawdziwy ntfy.sh** | `tests/integration/verify_ntfy_real.py`: notifier publikuje, test czyta wiadomości z powrotem i porównuje | 4/4 dotarło, priorytety 5/2/1 dokładnie jak w konfiguracji, tytuły bez zniekształceń (także `Baza—zażółćłóśźż`) |
| Tytuł ntfy z znakami spoza latin-1 | realny ntfy.sh, tytuł z „—" i „ł" | **przed poprawką**: `UnicodeEncodeError` przed wysłaniem → alert nie dochodził; po: `HTTP 200` |
| Serwer SMTP (OVH) | surowy `EHLO` na `ssl0.ovh.net:465` i `:587` | `8BITMIME`, `AUTH LOGIN PLAIN`, `SIZE 100 MB`; TLS 1.3 (465) / 1.2 (587) — treść 8bit i polskie znaki są poprawne |
| Temat e-maila z polskimi znakami | serializacja jak `smtplib.send_message` i odczyt z powrotem | `Subject` jako RFC 2047 (`=?utf-8?b?…?=`), po odczytaniu **znak w znak** równy oryginałowi |
| API Portainera (sterowanie stackiem) | żywy Portainer 2.33 lokalnie: `--check`, `--start`, `--redeploy`, złe ścieżki | stack znaleziony, `Env` (2 zmienne) przekazane do redeployu, stop → `--start` → HTTP 200 i status 1, zła ścieżka compose → kod 2 z instrukcją |
| Trasy API Portainera 2.33 | źródła Portainera (rejestracja tras) + próby na żywym API | start/stop wymagają `?endpointId`; webhooka **stacka** nie da się utworzyć przez API (tylko UI); `/api/webhooks` dotyczy usług Swarm, nie stacków; ścieżka compose jest niezmienialna po utworzeniu |
| Kontrakt healthchecks.io | `POST` na `hc-ping.com/<losowy-uuid>` | `HTTP 400 invalid url format` → literówka w UUID zawodzi głośno, a nie cicho |
| Watchdog healthchecks.io | atrapa hc.io | `POST /ping/<uuid>` z treścią |
| Blackbox: moduły sond | `probe?module=…` na żywym eksporterze | `http_expect_auth` 401→sukces, 200→porażka; `tcp_connect`; certyfikaty |
| Grafana: provisioning | uruchomiona Grafana | 4 dashboardy, `database: ok` |
| Panel w przeglądarce | Chrome DevTools na zbudowanym obrazie | 0 błędów w konsoli, 7 sekcji, iframe 704/800 px, 375 px bez przewijania |
| Kontrakt panel ↔ discovery | prawdziwy `/status/api.json` → parser panelu | `isStatusSnapshot` = true, formatowanie pl-PL |
| Klient S3 (SigV4) dla R2 | **prawdziwy serwer S3** (MinIO): poprawne poświadczenia, zły sekret, zły klucz, pusty prefiks | obiekt odczytany; złe poświadczenia odrzucone (`SignatureDoesNotMatch`) |
| Weryfikacja backupu przez R2 | watchdog w kontenerze przeciwko MinIO; trzy stany | patrz macierz niżej |
| Zapytania z dashboardów | Prometheus + Loki: wszystkie `expr` z 4 dashboardów | 56 PromQL + 10 LogQL — poprawne |
| Logowanie do Grafany przez nagłówek | `curl` z i bez `X-User` | bez nagłówka 401 (bezpieczny fallback), z nagłówkiem zalogowany jako **Org Admin** |
| Testy progów alertów | `promtool test rules`, 6 plików | wszystkie grupy reguł pokryte (44 reguły) |
| Auto-discovery | atrapa Docker API (`tests/integration/`) | wykrywa `Host(...)` i `PathPrefix`, pomija `skip`, tryb global, zadanie padnięte jako 1/2 |
| Serwisy Pythona | 200 testów jednostkowych | wszystkie przechodzą |
| Walidacja przed wdrożeniem | `docker stack config` (schemat Swarma) | przechodzi |
| Reguły wyciszania (inhibit) | 2 sztuczne alerty (`EdgeNotAcceptingTraffic` + 2× `AppDown`) wysłane do żywego Alertmanagera | `AppDown` → `suppressed`, `inhibitedBy` = alert edge'a; sam alert edge'a pozostał `active` |
| Priorytety ntfy | atrapa ntfy + żywy notifier | `critical` → `urgent` (brzęczy), `warning` → `low`, `info` → `min` (cicho) |

### Macierz stanów kontroli backupu (zmierzona, nie założona)

| Przypadek | `state` | `source` | obiektów | `monitoring_backup_age_seconds` | `check_ok{check="backup"}` |
| --- | --- | --- | --- | --- | --- |
| świeży obiekt w buckecie | `ok` | `r2` | 1 | wiek w sekundach | 1 |
| złe poświadczenia / brak sieci (ślepota) | `unknown` | `r2` | 0 | **brak serii** | 0 |
| bucket nie istnieje (fakt) | `critical` | `r2` | 0 | **-1** | 0 |
| brak sukcesu w logach usługi backupu | `critical` | `logs` | 0 | **-1** | 0 |
| brak Dockera i brak R2 (ślepota) | `unknown` | `logs` | 0 | **brak serii** | 0 |
| R2 nieskonfigurowane, logi pokazują sukces | `ok` | `logs` | 0 | wiek w sekundach | 1 |

Reguły czyta się z tego tak: `BackupNeverSucceeded` (`< 0`) łapie **potwierdzony**
brak kopii, a `BackupVerificationUnavailable` (`absent`) łapie **ślepotę**.
Rozróżnienie powstało po błędzie, w którym złe poświadczenia R2 udawały
krytyczny alert o braku backupu.

### Reguły logowe: trzy ciche awarie znalezione uruchomieniem

Wszystkie trzy przeszły `-verify-config`, walidację YAML i przegląd kodu. Każda
oznaczała alert, który **nigdy by nie zadzwonił** — a to reguły od dokładnie tych
sygnałów, dla których ten stack powstał (korupcja bazy, błędy dysku).

| Co było zepsute | Dlaczego cicho | Skala | Wykryte przez |
| --- | --- | --- | --- |
| `PgConnectionRefused` — cała reguła | wzorzec `FATAL:.*(a\|b\|c)` w Loki nie dopasowuje NICZEGO | 3 gałęzie | `verify_log_patterns.py` |
| `PgPageVerificationFailed` — gałąź uszkodzenia WAL | to samo: `WAL.*(corrupt\|invalid)` | 2 gałęzie | `verify_log_patterns.py` |
| `KernelDiskErrors` — gałęzie `nvme…` i `ata…` | `.*(a\|b)` oraz podwójny backslash `\\.` | 3 gałęzie | `verify_log_patterns.py` |
| `KernelDiskErrors` — cały plik reguł | pojedynczy `\.` to błąd składni LogQL, więc ruler odrzuca PLIK | 1 plik, 2 reguły | log rulera + `check_ruler_loaded.py` |

Zmierzone zachowanie Loki 3.6.17 (ten sam obraz, który idzie na produkcję):

- `X.*(a|b)` → **zero dopasowań**, także dla linii zawierającej `a`. Obejście:
  `X.{0,80}(a|b)` albo cokolwiek między `.*` a grupę (np. `X.* (a|b)`).
- W `|~ "…"` escape `\.` **nie istnieje** (ruler odrzuca cały plik), a `\\.` trafia
  do silnika regexów dosłownie (czyli wymaga backslasha w logu). Na kropkę: `[.]`,
  na cyfry: `[0-9]`.
- Loki nie zgłasza przy tym żadnego błędu przy pierwszym przypadku: reguła się
  ładuje i po prostu milczy.

Dlatego reguł logowych pilnują trzy kontrole: `scripts/ci/check_loki_regex.py`
(wzorce — bez infrastruktury), `tests/integration/verify_log_patterns.py`
(52 gałęzie, każda przeciw własnej linii logu, regex brany z plików reguł)
i `scripts/ci/check_ruler_loaded.py` (porównuje liczbę reguł w plikach z liczbą
faktycznie wczytaną przez ruler).

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
