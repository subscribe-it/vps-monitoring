# Stan wyjściowy (rozpoznanie z 2026-09-21)

Zapis faktów zebranych **przed** wdrożeniem stacku — punkt odniesienia dla porównań
i materiał do oceny, czy monitoring faktycznie coś zmienił.

## Host `ovh-vps-1` (57.129.41.248)

| Parametr | Wartość |
| --- | --- |
| CPU / RAM | 8 vCPU / 22,9 GiB (ok. 16 GiB wolne) |
| Dysk | 193 GB, zajęte 49 GB (25%), wolne 145 GB |
| I-węzły | 7% zajęte |
| System | Ubuntu 25.04, kernel 6.14, Docker 29.2.1 |
| Swarm | single-node, manager `ovh-vps-1` |
| Uptime w dniu rozpoznania | 74 dni |
| Swap | **0 B** (brak — presja pamięci kończy się OOM bez ostrzeżenia) |
| Strefa czasowa hosta | **UTC** (kontenery: `Europe/Warsaw`) |
| `smartd` | **nieaktywny** |
| Logging driver Dockera | **`local`** (dlatego Promtail używa Docker API, nie plików `*-json.log`) |
| Metryki demona Dockera | włączone, ale tylko na `127.0.0.1:9323` |
| Cockpit | publicznie na `:9090` (panel z uprawnieniami roota) |
| fail2ban | aktywny; jail `sshd` + `cockpit` |
| Śmieci | obrazy 11,8 GB (8,9 GB dangling), wolumeny 17 GB (7,3 GB odłączone) |

## Stacki i usługi (10 stacków, 37 usług)

`bugsink`, `jpolski_na6_pl_prod`, `kosmetix-staging`, `portainer-edge-gateway`,
`portainer`, `staging_mdi-studio`, `star-sign`, `traefik` (pozostałość),
`ventiplan-prod`, oraz wolumeny po starym `monitoring`.

## Problemy widoczne już w chwili rozpoznania (bez monitoringu nikt o nich nie wiedział)

| Problem | Szczegóły |
| --- | --- |
| `jpolski_na6_pl_prod_wp-cron` | **0/1**, pętla `Exited (137)` co ~3 minuty |
| `traefik_cloudflared` | **0/1** |
| `traefik_modsecurity` | **0/1** |
| Atak na SSH | 14 adresów zbanowanych „w tej chwili", 53 łącznie, 416 nieudanych prób |
| Wolumeny-sieroty | `jpolski_na6_pl_staging_*`, `procesy_pielegnowania_prod_*`, stare `monitoring_*` |

## Publiczne adresy obsługiwane przez Traefika (potwierdzone sondami)

| Adres | Kod na `/` | Stack |
| --- | --- | --- |
| `app.ventiplan.pl` | 200 | ventiplan-prod |
| `api.ventiplan.pl` | 404 (`/api/health` → 200) | ventiplan-prod |
| `bugsink.subscribeit.pl` | 302 | bugsink |
| `portainer.subscribeit.pl` | 200 | portainer |
| `traefik.subscribeit.pl` | 404 (dashboard ukryty — dobrze) | edge |
| `star-sign.pl` | 200 | star-sign |
| `api.star-sign.pl` | 302 | star-sign |
| `jpolskina6.pl` | 200 | jpolski_na6_pl_prod |
| `www.jpolskina6.pl` | 404 | jpolski_na6_pl_prod |
| `staging-kosmetix.duckdns.org` | 200 | kosmetix-staging |
| `mailpit-staging-kosmetix.duckdns.org` | 401 (auth) | kosmetix-staging |
| `mdi-studio.duckdns.org` | 200 | staging_mdi-studio |

Adresy zwracające 404/401 na `/` są **poprawne** — sondy muszą znać oczekiwany kod
(patrz `monitoring.io/expected` w `docs/ONBOARDING-APP.md`).

## Ślady starego wdrożenia monitoringu

Wolumeny `monitoring_prometheus_data` (286 MB), `monitoring_loki_data` (2,37 GB),
`monitoring_grafana_data` (42 MB), `monitoring_uptime_kuma_data`, `monitoring_alertmanager_data`,
`monitoring_duplicati_*`. Usług nie ma. **Nowy stack tworzy wolumeny `*_v2`**, więc
te dane zostają nietknięte jako archiwum do czasu Twojej decyzji.
