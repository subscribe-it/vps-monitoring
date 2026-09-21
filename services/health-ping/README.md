# health-ping

Watchdog wychodzący do healthchecks.io. Co `INTERVAL_SECONDS` (domyślnie 120 s)
ocenia stan całego stacku monitoringu i **pinguje healthchecks.io tylko wtedy, gdy
wszystko jest zielone**. Przy problemie wysyła ping na `<ping_url>/fail` z powodem
w treści — czyli brak pingu oznacza, że watchdog padł, a ping `/fail` oznacza, że
padło coś, co monitorujemy.

## Endpointy (domyślnie port 8080)

| Endpoint | Opis |
| --- | --- |
| `GET /health` | status serwisu, `all_ok` oraz mapa `checks` (0/1) z opisami |
| `GET /metrics` | Ekspozycja Prometheusa (`text/plain; version=0.0.4`) |
| `GET /backup.json` | `{"state":"ok\|warning\|critical\|unknown","last_success_at":...,"age_hours":16.5,"size_bytes":0,"objects_in_r2":0,"restore_test_days":12}` |

Tylko `GET`/`HEAD`; pozostałe metody → 405. `SIGTERM` zamyka serwis czysto.

## Sprawdzane warunki

| `check` | Warunek zielony |
| --- | --- |
| `disk` | wolne miejsce na `/` > `DISK_MIN_FREE_PERCENT` (15%) |
| `inodes` | wolne i-węzły > `INODES_MIN_FREE_PERCENT` (10%) |
| `services` | brak usługi z `running < desired` (poza `SERVICES_IGNORE_STACKS`) |
| `http` | żaden `checks[].state` w `/status/api.json` discovery nie jest `critical` |
| `certs` | `min(discovery_cert_days_left) > CERT_MIN_DAYS` (14) |
| `backup` | wiek najświeższego poprawnego backupu < `BACKUP_MAX_AGE_HOURS` (26) |
| `restore_test` | dni od ostatniego testu odtworzenia < `RESTORE_TEST_MAX_DAYS` (45); brak danych → 0 (czerwone) |
| `alertmanager` | `GET <ALERTMANAGER_URL>/-/healthy` zwraca 200 |

Metryki: `monitoring_all_ok`, `monitoring_check_ok{check}`,
`monitoring_backup_age_seconds`, `monitoring_backup_size_bytes`,
`monitoring_restore_test_age_days`,
`monitoring_last_hc_ping_timestamp_seconds{target="all_ok|backup"}`,
`monitoring_hc_ping_failures_total{target}`, `monitoring_last_run_timestamp_seconds`,
`monitoring_up`.

## Ustalanie wieku backupu (WAŻNE — wymaga dostrojenia)

1. `GET /containers/json?all=1` → kontener, którego
   `com.docker.swarm.service.name` == `BACKUP_SERVICE` (domyślnie
   `ventiplan-prod_db-backup`),
2. `GET /containers/<id>/logs?stdout=1&stderr=1&tail=2000` — Docker zwraca strumień
   z 8-bajtowymi nagłówkami ramek, które są odfiltrowywane,
3. z logów wyciągany jest znacznik ostatniego **sukcesu**:
   - jeśli `BACKUP_SUCCESS_REGEX` jest ustawiony — używane jest to wyrażenie,
   - inaczej szukane są typowe znaczniki (`backup ok`, `backup complete`,
     `backup successful`, `uploaded`, `dump ok`, `zakonczony sukcesem`,
     `zakończony`, `sukces`, `backup done`) i — jako słabszy sygnał — obecność
     nazwy pliku `.dump`/`.age`,
4. czas zdarzenia: znacznik czasu z dopasowanej linii, a gdy go nie ma —
   najnowszy znacznik czasu w całym logu. Gdy nie ma żadnego, check jest czerwony
   (serwis nie zgaduje).

> **Dostrojenie po wdrożeniu**: dopasowanie znaczników sukcesu trzeba potwierdzić na
> realnych logach usługi backupu. Najlepiej ustawić `BACKUP_SUCCESS_REGEX`
> (szukany w każdej linii, bez rozróżniania wielkości liter), np.
> `-e BACKUP_SUCCESS_REGEX='(backup|dump) (ok|complete|zakończony)'`.
> Gdy dopasowanie pochodzi wyłącznie z nazwy pliku `.dump`/`.age`, w logach serwisu
> pojawia się ostrzeżenie „dopasowanie słabe".

Rozmiar backupu wyciągany jest z tej samej linii (`512.4 MB`, `2 GiB`, ...).
Jeśli nie zostanie wykryty, kryterium `BACKUP_MIN_SIZE_MB` jest pomijane
(w logach pojawia się stosowna informacja).

Stan testu odtworzenia czytany jest z pliku `/data/restore-test.json`
(`{"last_test_at":"2026-09-01T10:00:00Z"}`) — montowanego tylko do odczytu.
Brak pliku → `monitoring_restore_test_age_days 0` i check `restore_test` = 0
(czerwone, bo „nigdy nie testowano").

## Zmienne środowiskowe

| Zmienna | Domyślnie | Opis |
| --- | --- | --- |
| `HC_PING_ALL_OK` | – | URL pingu healthchecks.io dla stanu całego stacku |
| `HC_PING_BACKUP` | – | URL pingu healthchecks.io dla stanu backupu |
| `INTERVAL_SECONDS` | `120` | odstęp między przebiegami |
| `PROMETHEUS_URL` | `http://prometheus:9090` | źródło danych o dysku i i-węzłach |
| `DISCOVERY_URL` | `http://discovery:8080` | źródło metryk i `/status/api.json` |
| `ALERTMANAGER_URL` | `http://alertmanager:9093` | źródło `/-/healthy` |
| `BACKUP_SERVICE` | `ventiplan-prod_db-backup` | nazwa usługi backupu w Swarmie |
| `BACKUP_SUCCESS_REGEX` | puste | własne wyrażenie sukcesu backupu |
| `BACKUP_MAX_AGE_HOURS` | `26` | maksymalny wiek backupu |
| `BACKUP_MIN_SIZE_MB` | `0` | minimalny rozmiar backupu (0 = nie sprawdzaj) |
| `DISK_MIN_FREE_PERCENT` | `15` | próg wolnego miejsca |
| `INODES_MIN_FREE_PERCENT` | `10` | próg wolnych i-węzłów |
| `CERT_MIN_DAYS` | `14` | minimalna ważność certyfikatów |
| `RESTORE_TEST_MAX_DAYS` | `45` | maksymalny wiek testu odtworzenia |
| `SERVICES_IGNORE_STACKS` | `monitoring,kosmetix-staging,staging_mdi-studio` | stacki wyłączone z checku `services` |
| `RESTORE_TEST_FILE` | `/data/restore-test.json` | plik ze stanem testu odtworzenia |
| `DOCKER_HOST` | `/var/run/docker.sock` | wyłącznie gniazdo unix |
| `PORT` | `8080` | port HTTP |

## Zachowanie przy braku zależności

Serwis nigdy nie przestaje działać z powodu braku Prometheusa, Dockera, discovery
czy Alertmanagera — odpowiedni check staje się czerwony (`monitoring_check_ok{...} 0`),
`monitoring_all_ok` spada do 0, a healthchecks.io dostaje ping `/fail` z powodem.
`monitoring_up` opisuje sam serwis (czy pętla kontrolna działa), a nie zależności.

## Ustalenia i odstępstwa

- Dysk i i-węzły liczone są najpierw z Prometheusa (mountpoint `/` **hosta**), a gdy
  Prometheus nie odpowiada — z lokalnego `os.statvfs("/")` (z ostrzeżeniem w logach,
  bo wewnątrz kontenera to system plików kontenera, nie hosta).
- `monitoring_backup_age_seconds` i `monitoring_backup_size_bytes` pojawiają się
  tylko wtedy, gdy wartość jest znana — brak serii jest czytelniejszy niż zero,
  które wyglądałoby jak „świeży backup". Sygnał problemu niesie
  `monitoring_check_ok{check="backup"}` (0).
- `objects_in_r2` w `/backup.json` jest zawsze `0` — ten serwis nie ma dostępu do
  R2; pole istnieje dla zgodności ze schematem panelu.
- Gdy oba kanały pingów są nieskonfigurowane, serwis tylko loguje ostrzeżenie
  (nie da się pingować donikąd), a `monitoring_hc_ping_failures_total` pozostaje 0.

## Uruchomienie

```bash
docker build -t monitoring/health-ping services/health-ping
docker run --rm -p 8080:8080 \
  -v /var/run/docker.sock:/var/run/docker.sock:ro \
  -v /data/restore-test.json:/data/restore-test.json:ro \
  -e HC_PING_ALL_OK=https://hc-ping.com/xxxxxxxx \
  monitoring/health-ping
```

Kontener działa jako UID 10001 i nie zapisuje niczego poza `/tmp`.
