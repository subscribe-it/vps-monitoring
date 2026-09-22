# Sekrety GitHub Actions

Skonfiguruj w: **Settings → Secrets and variables → Actions → Repository secrets**.

| Sekret | Wymagany | Do czego |
| --- | --- | --- |
| `PORTAINER_URL` | **tak** (zalecane) | `https://portainer.subscribeit.pl` (albo `https://57.129.41.248:9443`) |
| `PORTAINER_API_KEY` | **tak** (zalecane) | sprawdzenie i start stacku oraz redeploy z Gita (Portainer → My account → Access tokens) |
| `PORTAINER_MONITORING_WEBHOOK` | nie | tryb zapasowy: wywołanie redeployu publicznym webhookiem stacku |
| `NOTIFIER_TOKEN` | nie | powiadomienie na telefon (ntfy), gdy deploy się nie powiedzie |
| `GHCR_ADMIN_TOKEN` | nie | ustawienie widoczności obrazów w ghcr.io (workflow `Package visibility`) |

## `PORTAINER_URL` i `PORTAINER_API_KEY`

Zalecana droga: klucz API pozwala z Akcji **sprawdzić, na jaki plik compose
wskazuje stack, wystartować go i wymusić redeploy z Gita**. Publiczny webhook
stacka umie tylko to ostatnie — i w dodatku da się go utworzyć wyłącznie w UI
(API Portainera 2.33 nie ma trasy tworzącej webhook stacka).

1. Portainer → **My account → Access tokens → Add access token** → skopiuj token.
2. GitHub → Settings → Secrets and variables → Actions → dodaj `PORTAINER_URL`
   (`https://portainer.subscribeit.pl`) i `PORTAINER_API_KEY`.
3. Sprawdź: workflow **Portainer (stack monitoring)** → akcja `check`.

## `PORTAINER_MONITORING_WEBHOOK` (tryb zapasowy)

1. Portainer → **Stacks** → `monitoring` → zakładka **Webhooks** → **Add webhook**
2. Skopiuj URL (format `http://<host>:9000/api/stacks/webhooks/<uuid>`)
3. GitHub → Settings → Secrets and variables → Actions → **New repository secret**

Używany tylko wtedy, gdy nie ma `PORTAINER_URL`/`PORTAINER_API_KEY`.

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
| **C. Rejestr w Portainerze — zalecane** | Portainer → **Registries → Add registry → Custom**: URL `ghcr.io`, użytkownik `DawidXXX`, hasło = PAT (wystarczy `read:packages`, wystarczy też `write:packages`). Portainer przekazuje te poświadczenia przy deployu stacka w Swarmie (`DeploySwarmStack(..., registries, ...)` — sprawdzone w źródłach 2.33) | zostają prywatne |
| **B. UI** | organizacja → **Packages** → pakiet → **Package settings** → Danger Zone → **Change visibility** (11 pakietów, ręcznie) | stają się publiczne |
| **A. Ten sekret** | klasyczny PAT z `write:packages` → sekret `GHCR_ADMIN_TOKEN` → workflow `Package visibility` | **nie zadziałało** (patrz niżej) |

**Zmierzone (2026-09-22):** `GET /orgs/subscribe-it/packages/container/<nazwa>`
zwraca **200** (token widzi pakiet), ale `PATCH` na tym samym adresie zwraca
**404 bez informacji o zakresach** — i to zarówno dla tokenu z `repo, write:packages`
od właściciela organizacji, jak i dla tokenu z `admin:org`. Kontrolny `PATCH`
tokenem bez `read:packages` też daje 404 (a `GET` tym samym tokenem daje czytelne
403 o brakującym zakresie), więc endpoint odrzuca żądanie, zanim sprawdzi zakresy.
Wniosek praktyczny: **zmiana widoczności pakietów organizacji przez API nie działa**
— zostaje UI (B) albo rejestr w Portainerze (C).

## Czego tu NIE ma (i nie powinno być)

Hasło Grafany, hash htpasswd, temat i token ntfy, dane SMTP, ping URL-e
healthchecks.io ani klucze R2. Wszystkie te wartości żyją **wyłącznie** w zmiennych
środowiskowych stacku w Portainerze — nigdy w repozytorium, nigdy w Actions.
