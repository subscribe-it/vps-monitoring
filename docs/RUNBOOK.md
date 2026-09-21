# Runbook — co robić, gdy alert dzwoni

Zasada: **alert bez procedury jest gorszy niż brak alertu.** Każda reguła w tym
stacku ma `runbook:` wskazujący na sekcję poniżej. Jeśli dodajesz alert bez sekcji
tutaj — nie wdrażaj go.

Oznaczenia: 🔴 krytyczny (push + e-mail) · 🟡 ostrzeżenie (e-mail) · ⚪ informacja.

Wszystkie komendy są **odczytowe**. Nic w tym runbooku nie modyfikuje innych stacków.

---

## <a name="appdown"></a>🔴 AppDown — aplikacja nie odpowiada
**Co to znaczy:** sonda HTTP nie przeszła przez 2 minuty dla adresu wykrytego automatycznie.
**Sprawdź:**
```bash
curl -sS -o /dev/null -w '%{http_code} %{time_total}s\n' https://<adres>/
docker service ls | grep <stack>
docker service ps <stack>_<usługa> --no-trunc | head -20
docker service logs --tail 200 <stack>_<usługa>
```
**Działaj:** jeśli usługa ma `0/N`, sprawdź politykę restartu (`rejected` = wyczerpane próby) i logi ostatniego zadania. Nie restartuj „w kółko" — najpierw ustal przyczynę.
**Eskaluj:** gdy w logach widać błąd bazy lub uszkodzenie danych → patrz [#pgcorruption](#pgcorruption).

## <a name="appslow"></a>🟡 AppSlow — aplikacja odpowiada wolno
**Co to znaczy:** czas odpowiedzi > 3 s przez 10 minut.
**Sprawdź:** `probe_duration_seconds` w Prometheusie, zużycie CPU/RAM kontenera w panelu, liczbę połączeń do bazy.
**Działaj:** porównaj z wykresem w Grafanie (`/grafana` → aplikacje). Jeśli wzrost jest skokowy — sprawdź, czy nie ma pętli zapytań albo braku indeksu.

## <a name="monitoringchainbroken"></a>🔴 MonitoringChainBroken — ścieżka monitoringu nie działa
**Co to znaczy:** nasza własna domena nie zwraca oczekiwanego 401 (usługa żyje, wymaga logowania). Czyli padł DNS, certyfikat, Traefik, ForwardAuth albo sama usługa.
**Sprawdź:**
```bash
dig +short monitoring.subscribeit.pl
curl -sS -o /dev/null -w '%{http_code}\n' https://monitoring.subscribeit.pl/
docker service ls | grep monitoring
docker service logs --tail 100 monitoring_auth
docker service logs --tail 100 monitoring_panel
```
**Działaj:** jeśli 502 → sprawdź `monitoring_auth` (bez niego Traefik nie wpuszcza nikogo — fail-closed). Jeśli brak certyfikatu → patrz [#tlscert](#tlscert).

## <a name="edgedown"></a>🔴 EdgeNotAcceptingTraffic / ManyPublicAppsDown — Traefik nie przyjmuje ruchu
**Co to znaczy:** to awaria **wszystkich** domen na tym hoście, nie jednej aplikacji.
**Sprawdź:**
```bash
docker service ps portainer-edge-gateway_traefik
docker service logs --tail 200 portainer-edge-gateway_traefik
ss -tlnp | grep -E ':80|:443'
```
**Działaj:** to stack edge — **nie zmieniaj go bez świadomej decyzji**. Sprawdź, czy nie ma niedawnego deployu, i rozważ rollback obrazu (`latest-working@sha256:…`).
**Eskaluj:** natychmiast, to najpoważniejszy alert w całym systemie.

## <a name="tlscert"></a>🔴/🟡 TlsCertExpiringSoon / TlsCertExpiringCritical / AcmeCertificateRenewalFailed
**Co to znaczy:** certyfikat Let's Encrypt wygasa w ciągu 14 (lub 3) dni, albo Traefik nie może go odnowić.
**Sprawdź:**
```bash
echo | openssl s_client -connect <domena>:443 -servername <domena> 2>/dev/null | openssl x509 -noout -dates
docker service logs --since 24h portainer-edge-gateway_traefik | grep -i acme | tail -20
```
**Działaj:** najczęstsze przyczyny: rekord DNS nie wskazuje na VPS, port 80 zablokowany (challenge HTTP-01), albo wyczerpany limit Let's Encrypt. Po naprawie wymuś ponowienie, usuwając wpis w `acme.json`… **nie rób tego bez kopii** — najpierw zapytaj.

## <a name="disk"></a>🔴/🟡 HostDiskSpaceLow / HostDiskSpaceCritical / HostDiskWillFillIn24h / HostInodesLow / HostFilesystemReadonly / KernelDiskErrors
**Sprawdź:**
```bash
df -h; df -i
docker system df -v | head -40
sudo du -xh --max-depth=1 /var/lib/docker/volumes 2>/dev/null | sort -h | tail -15
sudo journalctl -k -n 200 | grep -iE 'i/o error|ext4-fs error|blk_update'
sudo smartctl -a /dev/sda | head -30
```
**Działaj:**
- miejsce: najpierw **dangling images** (`docker image prune` — ale to zmiana na hoście, wymaga Twojej zgody i nie dotyka działających kontenerów),
- `FilesystemReadonly` lub błędy I/O jądra: **traktuj jak awarię sprzętową**. Zabezpiecz backup, zgłoś do OVH, nie restartuj bazy w pętli.
**Uwaga:** `docker system prune` NIE jest tu dozwolone — usuwa rzeczy należące do innych stacków.

## <a name="memory"></a>🔴/🟡 HostMemoryPressure / HostOomKill / KernelOomKill / SwarmContainerHighMemory
**Co to znaczy:** swap = 0, więc presja pamięci kończy się natychmiastowym zabiciem procesu.
**Sprawdź:**
```bash
free -m
docker stats --no-stream --format 'table {{.Name}}\t{{.MemUsage}}\t{{.CPUPerc}}' | sort -k2 -h | tail -15
grep -i 'Out of memory' /var/log/kern.log 2>/dev/null | tail -5
```
**Działaj:** znajdź kontener, który urósł (panel → stacki), i ustal, czy to wyciek. Świadomie rozważ mały swap/zram — to zmiana hosta i Twoja decyzja.

## <a name="load"></a>🟡 HostLoadHigh
**Sprawdź:** `uptime`, `docker stats`, obciążenie w Grafanie. Szukaj kontenera z wysokim CPU, nie „całego hosta".

## <a name="reboot"></a>🟡 HostRebooted
**Sprawdź:** `last reboot | head -5`, `sudo journalctl --list-boots | tail -5`.
**Działaj:** ustal, czy restart był planowany (OVH maintenance) czy nie. Po nieplanowanym restarcie sprawdź integralność bazy ([#pgcorruption](#pgcorruption)).

## <a name="clock"></a>🟡 HostClockSkew
**Sprawdź:** `timedatectl`, `chronyc tracking` (jeśli zainstalowane).
**Działaj:** rozjechany zegar psuje ACME i znaczniki czasu backupów.

## <a name="replicas"></a>🔴 SwarmServiceReplicasMismatch / SwarmServiceTasksFailing
**Co to znaczy:** dokładnie scenariusz z 21.09.2026 — usługa zeszła z `N/N`.
**Sprawdź:**
```bash
docker service ls | grep <stack>
docker service ps <stack>_<usługa> --no-trunc | head -20
docker service logs --tail 200 <stack>_<usługa>
```
**Działaj:** `rejected` = polityka restartu wyczerpana (`max_attempts`), czyli problem jest trwały. Znajdź przyczynę w logach, nie zwiększaj limitów.

## <a name="unhealthy"></a>🔴 SwarmContainerUnhealthy
**Sprawdź:** `docker inspect --format '{{json .State.Health}}' <kontener> | head -c 2000`.
**Działaj:** healthcheck mówi prawdę o zależności (baza, Redis, wolumen) — ustal, czego brakuje.

## <a name="deploy"></a>⚪ SwarmServiceUpdated
**Co to znaczy:** wdrożono nową wersję na stacku krytycznym. To potwierdzenie, nie awaria.
**Działaj:** sprawdź w panelu, czy repliki wróciły do `N/N`, i czy sonda HTTP jest zielona.

## <a name="onboarding"></a>⚪ SwarmNewServiceDiscovered
**Co to znaczy:** auto-discovery wykryło nową usługę i objęło ją monitoringiem.
**Działaj:** jeśli czegoś **nie** chcesz monitorować, dodaj label `monitoring.io/skip=true`. Jeśli aplikacja ma dedykowany healthcheck, dodaj `monitoring.io/health-path=/health`.

## <a name="selfhealth"></a>🔴/🟡 AlertmanagerDown / NotifierDown / GrafanaDown / LokiDown / PromtailDown / DiscoveryDown / HealthPingDown / ScrapeTargetDown / PrometheusConfigReloadFailed / PrometheusRuleEvaluationFailing / PrometheusNoTargets
**Co to znaczy:** problem z samym monitoringiem. Najgroźniejszy jest `NotifierDown` — wtedy alerty **nie docierają**.
**Sprawdź:**
```bash
docker service ls | grep monitoring
docker service logs --tail 100 monitoring_notifier
docker service logs --tail 100 monitoring_alertmanager
curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:9093/-/healthy || true
```
**Działaj:** odtwórz usługę przez redeploy stacku w Portainerze (Webhook / Update the stack). **Healthchecks.io i tak Cię powiadomi**, jeśli stack padnie w całości.

## <a name="watchdog"></a>🔴 Watchdog
**Co to znaczy:** ten alert jest **zawsze aktywny** — to dowód, że stack żyje i potrafi wysyłać alerty. Nie jest awarią. Jeśli przestanie docierać do healthchecks.io, dostaniesz e-mail z zewnątrz.

## <a name="backup"></a>🔴 BackupTooOld / BackupNeverSucceeded
**Co to znaczy:** nie ma świeżego, poprawnego dumpu.
**Sprawdź:**
```bash
docker service ps ventiplan-prod_db-backup
docker service logs --tail 300 ventiplan-prod_db-backup
```
oraz stan obiektów w Cloudflare R2 (konsola → bucket `ventiplan-backups`).
**Działaj:** jeśli `BACKUP_SUCCESS_REGEX` nie pasuje do logów, dopasuj go w env stacku — dopóki to nie działa, watchdog nie potwierdzi sukcesu.

## <a name="restoretest"></a>🟡 RestoreTestOverdue
**Co to znaczy:** minęło > 45 dni od testu odtworzenia. Kopia, której nie odtworzono, nie jest kopią.
**Procedura (miesięczna, ręczna — klucz age jest offline):**
1. pobierz najnowszy dump z R2,
2. odszyfruj kluczem prywatnym age (klucz trzyma: _uzupełnij — kto i gdzie_),
3. odtwórz do **nowej** bazy tymczasowej,
4. sprawdź liczbę tabel i kilka rekordów,
5. zapisz datę w `/data/restore-test.json` (wolumen health-ping) — alert zniknie sam.

## <a name="allok"></a>🟡 MonitoringAllOkFailing / HealthchecksPingFailing
**Co to znaczy:** watchdog nie może potwierdzić, że wszystko jest zielone (albo nie może pingować healthchecks.io).
**Sprawdź:** `/status/api.json` (pole `checks`) pokaże, który warunek jest czerwony; logi `monitoring_health-ping`.

## <a name="notifications"></a>🔴 NotificationDeliveryFailing
**Co to znaczy:** alerty powstają, ale nie są dostarczane (ntfy lub SMTP odrzuca).
**Sprawdź:** `docker service logs --tail 200 monitoring_notifier`.
**Działaj:** sprawdź `NTFY_TOPIC`/`NTFY_TOKEN` oraz SMTP. Do czasu naprawy polegaj na healthchecks.io.

## <a name="pgcorruption"></a>🔴 PgPageVerificationFailed / PgPanic / PgConnectionRefused
**Co to znaczy:** baza zgłasza uszkodzenie stron albo WAL — **to był sygnał, który 21.09.2026 przeszedł niezauważony.**
**Sprawdź (odczyt):**
```bash
docker service logs --tail 500 ventiplan-prod_postgres
docker service ps ventiplan-prod_postgres
```
**Działaj — kolejność ma znaczenie:**
1. **Nie restartuj w pętli** — każde przejście przez WAL zwiększa ryzyko.
2. Zabezpiecz wolumen (`ventiplan-prod_ventiplan_postgres_data`) — kopia, nie kasowanie.
3. Ustal ostatni poprawny checkpoint; sprawdź logi jądra ([#disk](#disk)) — uszkodzenie bywa sprzętowe.
4. Odtworzenie z dumpu: patrz [#restoretest](#restoretest).
5. Po wyzdrowieniu: zapisz wniosek w dokumentacji i sprawdź, czy alert zadziałał na czas.

## <a name="http5xx"></a>🟡 Traefik5xxRateHigh
**Sprawdź:** Grafana → Logi (filtr `DownstreamStatus >= 500`), logi aplikacji z tego hosta.
**Działaj:** jeśli 5xx korelują z błędami bazy → [#pgcorruption](#pgcorruption).

## <a name="logs"></a>🟡 TraefikNoAccessLogs
**Co to znaczy:** brak nowych wpisów w access logu edge — analiza po fakcie będzie niemożliwa.
**Sprawdź:** `docker service logs --tail 50 portainer-edge-gateway_traefik`, `docker volume inspect portainer-edge-gateway_traefik-logs`.

## <a name="security"></a>⚪/🟡 SshLoginAccepted / SshAuthFailuresSpike / Fail2banBanSpike / CockpitLogin
**Co to znaczy:** ktoś loguje się (albo próbuje) do hosta lub do panelu Cockpit.
**Sprawdź:**
```bash
sudo last -n 20
sudo fail2ban-client status sshd
sudo journalctl -u ssh --since '24 hours ago' | grep -E 'Accepted|Failed' | tail -30
```
**Działaj:** jeśli to nie Ty — natychmiast sprawdź `~/.ssh/authorized_keys`, procesy i klucze API. Cockpit (9090) jest publiczny: rozważ ograniczenie go firewallem do swojego IP.

---

## Czego ten runbook nie robi

Nie zawiera kroków modyfikujących cudze stacki. Każda taka operacja wymaga
Twojej decyzji i jest wykonywana przez Ciebie — patrz `docs/SCOPE.md`.
