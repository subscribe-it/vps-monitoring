# Dostęp

Wszystko stoi pod **jedną domeną** i za **jednym logowaniem** (ForwardAuth).
To celowe: iframe'y w panelu są wtedy tym samym origin, więc nie ma problemów
z ciasteczkami ani z drugim logowaniem.

| Adres | Co |
| --- | --- |
| `https://monitoring.subscribeit.pl/` | **panel** — kafelki i żywy stan (strona startowa) |
| `https://monitoring.subscribeit.pl/grafana` | Grafana — dashboardy i przeglądanie logów |
| `https://monitoring.subscribeit.pl/prometheus` | Prometheus — metryki, targety, reguły |
| `https://monitoring.subscribeit.pl/alertmanager` | Alertmanager — aktywne alerty, wyciszenia |
| `https://monitoring.subscribeit.pl/status/api.json` | dane stanu (to samo, co widzi panel) |

Poza tą domeną:

| Adres | Co |
| --- | --- |
| `https://healthchecks.io/checks` | zewnętrzny watchdog (tu sprawdzasz, czy VPS się odezwał) |
| `https://portainer.subscribeit.pl` | Portainer — zarządzanie stackami |
| `https://57.129.41.248:9090` | Cockpit — terminal i administracja hostem |
| aplikacja ntfy na telefonie | push z alertami krytycznymi |

## Logowanie

- do paneli: użytkownik i hasło ustawione w `PANEL_AUTH_USER` / `PANEL_AUTH_PASSWORD_HTPASSWD`,
- do Grafany: sesja jest zakładana automatycznie na podstawie nagłówka z ForwardAuth
  (`GRAFANA_AUTH_PROXY=true`); konto administracyjne Grafany istnieje awaryjnie
  (`GRAFANA_ADMIN_USER` / `GRAFANA_ADMIN_PASSWORD`),
- do Cockpita: konto systemowe `ubuntu` na hoście.

## Gdy zapomnisz hasła do paneli

Wygeneruj nowy hash i podmień `PANEL_AUTH_PASSWORD_HTPASSWD` w env stacku:

```bash
docker run --rm httpd:2.4-alpine htpasswd -nbB admin 'NOWE_HASLO'
```

Pamiętaj o podwojeniu znaków `$` w Portainerze. Po zapisaniu stacku `auth`
podniesie się z nowym plikiem `htpasswd` — bez przebudowy obrazów.
