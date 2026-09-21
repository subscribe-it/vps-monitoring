# Wdrożenie krok po kroku

## 0. Wymagania wstępne

- rekord DNS: `monitoring` **A** → `57.129.41.248` (i opcjonalnie `www.monitoring`),
- sieć `traefik-public` istnieje (jest — używana przez edge),
- na hoście działa edge `portainer-edge-gateway` z resolverem ACME `letsencrypt`,
- dostęp do Portainera z prawem tworzenia stacków.

## 1. Widoczność obrazów w ghcr.io

Repozytorium jest prywatne, więc **paczki ghcr są domyślnie prywatne**. Wybierz jedną drogę:

- **A (prościej):** po pierwszym udanym buildzie ustaw każdą paczkę
  `vps-monitoring-*` na **Public** (GitHub → Packages → wybrana paczka → Package settings → Change visibility),
- **B:** dodaj w Portainerze **Registry** dla `ghcr.io` (użytkownik GitHub + PAT z `read:packages`).

Bez tego Portainer nie pobierze obrazów i usługi utkną w `preparing`.

## 2. Token do repozytorium (dla stacku z Git)

GitHub → Settings → Developer settings → **Fine-grained token**:
- Repository access: tylko `subscribe-it/vps-monitoring`
- Permissions: **Contents: Read-only**

## 3. Utworzenie stacku w Portainerze

1. **Stacks → Add stack**, nazwa: **`monitoring`**
2. Build method: **Repository**
   - Repository URL: `https://github.com/subscribe-it/vps-monitoring`
   - Repository reference: `main`
   - Compose path: `docker-compose.yml`
   - Credentials: token z punktu 2
3. **Environment variables** → wklej kompletną listę z `env.portainer.example`
   i uzupełnij wartości (patrz niżej, co musisz zdobyć).
4. **Deploy the stack**.

## 4. Skąd wziąć wartości env

| Zmienna | Skąd |
| --- | --- |
| `PANEL_AUTH_PASSWORD_HTPASSWD` | `docker run --rm httpd:2.4-alpine htpasswd -nbB admin 'HASŁO'` → w Portainerze podwój każdy `$` |
| `GRAFANA_ADMIN_PASSWORD` | Twoje hasło (min. 12 znaków) |
| `NTFY_TOPIC`, `NTFY_TOKEN` | konto na ntfy.sh → *Access tokens*; temat to długi losowy ciąg |
| `SMTP_*`, `ALERT_EMAIL_TO` | Twój SMTP (OVH: `ssl0.ovh.net:465`, `SMTP_SECURE=true`) |
| `HC_PING_ALL_OK`, `HC_PING_MONITORING`, `HC_PING_BACKUP` | healthchecks.io → trzy checki typu **Simple**: `vps-all-ok` (5 min/5 min), `monitoring-alive` (5 min/5 min), `backup-ventiplan` (1 dzień/2 h) → skopiuj ping URL-e |
| `NOTIFIER_TOKEN` | dowolny długi losowy ciąg |

## 5. Webhook deployu

1. Portainer → stack `monitoring` → **Webhooks → Add webhook** → skopiuj URL.
2. GitHub → repo → Settings → Secrets → Actions → **`PORTAINER_MONITORING_WEBHOOK`**.
3. Opcjonalnie dodaj `NOTIFIER_TOKEN` (ten sam co w env), żeby dostawać powiadomienie o nieudanym deployu.

Od tego momentu **każdy push do `main`** przechodzi przez:
`validate` → `build images` → `webhook Portainera` → `smoke test (oczekiwany kod 401)`.

## 6. Weryfikacja po wdrożeniu

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://monitoring.subscribeit.pl/          # oczekiwane 401
docker service ls | grep monitoring                                                  # 12 usług, wszystkie 1/1
docker service logs --tail 50 monitoring_discovery
```
I w przeglądarce: `https://monitoring.subscribeit.pl/` → login z punktu 4 → panel
powinien pokazać zielone kafelki.

## 7. Pierwsza doba

1. Sprawdź, czy przyszedł e-mail z healthchecks.io, gdy tymczasowo zatrzymasz
   `health-ping` (`docker service scale monitoring_health-ping=0` — **własny stack**,
   nic innego to nie dotyka). Po teście wróć do `1`.
2. Wyślij testowy alert na telefon (Alertmanager API) — procedura w `docs/RUNBOOK.md`.
3. Dostosuj `BACKUP_SUCCESS_REGEX` do realnych logów `ventiplan-prod_db-backup`.

## 8. Typowe problemy

| Objaw | Przyczyna | Rozwiązanie |
| --- | --- | --- |
| Usługi w `preparing`, `no suitable node` | prywatne obrazy ghcr | patrz punkt 1 |
| Wszystkie ścieżki zwracają 404 | middleware `monitoring-mon-auth@swarm` nie istnieje | sprawdź logi `monitoring_auth`; w razie potrzeby zmień odwołanie na `mon-auth@swarm` |
| Panel zwraca 502 | `auth` nie wstał (brak/niepoprawny hash) | `docker service logs monitoring_auth` |
| Brak certyfikatu | rekord DNS jeszcze się nie propaguje | `dig +short monitoring.subscribeit.pl` |
