# Sekrety GitHub Actions

Skonfiguruj w: **Settings → Secrets and variables → Actions → Repository secrets**.

| Sekret | Wymagany | Do czego |
| --- | --- | --- |
| `PORTAINER_MONITORING_WEBHOOK` | **tak** | wywołanie redeployu stacku `monitoring` po zbudowaniu obrazów |
| `NOTIFIER_TOKEN` | nie | powiadomienie na telefon (ntfy), gdy deploy się nie powiedzie |
| `GHCR_ADMIN_TOKEN` | nie | ustawienie widoczności obrazów w ghcr.io (workflow `Package visibility`) |

## `PORTAINER_MONITORING_WEBHOOK`

1. Portainer → **Stacks** → `monitoring` → zakładka **Webhooks** → **Add webhook**
2. Skopiuj URL (format `http://<host>:9000/api/stacks/webhooks/<uuid>`)
3. GitHub → Settings → Secrets and variables → Actions → **New repository secret**

> **Uwaga bezpieczeństwa:** URL webhooka jest **sekretem** — kto go zna, ten może
> wywołać redeploy stacku. Nie zapisuj go w plikach repozytorium, w dokumentacji ani
> w komentarzach. Jeśli kiedykolwiek trafił do repo lub do czatu — usuń webhook
> w Portainerze i utwórz nowy.

## `NOTIFIER_TOKEN`

Dowolny długi losowy ciąg, **ten sam** co zmienna `NOTIFIER_TOKEN` w env stacku.
Używany przez workflow `deploy.yml` do wysłania alertu, gdy wdrożenie się nie powiedzie.

## `GHCR_ADMIN_TOKEN` (opcjonalny)

Portainer pobiera obrazy z `ghcr.io`, więc rejestr musi być dla niego dostępny.
Zmierzone: **token Actions nie ma dostępu do pakietów** (PATCH zwraca 404), a przy
prywatnych pakietach anonimowy pull kończy się `authentication required`. Trzy
wyjścia — wybierz jedno:

| Wyjście | Co zrobić | Pakiety |
| --- | --- | --- |
| **A. Ten sekret** | klasyczny PAT z zakresem `write:packages` → sekret `GHCR_ADMIN_TOKEN` → uruchom workflow `Package visibility` | stają się publiczne |
| **B. UI** | organizacja → **Packages** → pakiet → **Package settings** → Danger Zone → **Change visibility** (11 pakietów) | stają się publiczne |
| **C. Zostaw prywatne** | Portainer → **Registries** → `ghcr.io` + PAT z `read:packages` → wskaż rejestr w stacku | zostają prywatne |

A i B są wygodne w utrzymaniu (zero danych logowania w Portainerze, obrazy nie
zawierają sekretów — wszystko wrażliwe idzie zmiennymi środowiskowymi).
C jest najbezpieczniejsze, jeśli wolisz nie publikować obrazów.

## Czego tu NIE ma (i nie powinno być)

Hasło Grafany, hash htpasswd, temat i token ntfy, dane SMTP, ping URL-e
healthchecks.io ani klucze R2. Wszystkie te wartości żyją **wyłącznie** w zmiennych
środowiskowych stacku w Portainerze — nigdy w repozytorium, nigdy w Actions.
