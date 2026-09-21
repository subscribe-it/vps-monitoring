# Sekrety GitHub Actions

Skonfiguruj w: **Settings → Secrets and variables → Actions → Repository secrets**.

| Sekret | Wymagany | Do czego |
| --- | --- | --- |
| `PORTAINER_MONITORING_WEBHOOK` | **tak** | wywołanie redeployu stacku `monitoring` po zbudowaniu obrazów |
| `NOTIFIER_TOKEN` | nie | powiadomienie na telefon (ntfy), gdy deploy się nie powiedzie |

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

## Czego tu NIE ma (i nie powinno być)

Hasło Grafany, hash htpasswd, temat i token ntfy, dane SMTP, ping URL-e
healthchecks.io ani klucze R2. Wszystkie te wartości żyją **wyłącznie** w zmiennych
środowiskowych stacku w Portainerze — nigdy w repozytorium, nigdy w Actions.
