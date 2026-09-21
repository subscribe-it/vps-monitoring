# Zakres i zasada nadrzędna

## Zasada nadrzędna (twarda)

> **Ten stack wyłącznie obserwuje. Nie modyfikuje żadnej innej aplikacji na tym VPS.**

Na tym hoście działa produkcja kilku projektów. Monitoring nie może być przyczyną
awarii, którą ma wykrywać, i nie może zmieniać cudzego stanu. Zasada nie opiera się
na dobrej woli — wynika z konstrukcji stacku.

## Co stack robi (dozwolone)

| Działanie | Jak |
| --- | --- |
| Sondy HTTP/TCP | wyłącznie żądania odczytowe do publicznych adresów |
| Metryki kontenerów i usług | Docker API przez `/var/run/docker.sock` zamontowany **`:ro`**, kod wykonuje wyłącznie `GET` |
| Metryki hosta | `node-exporter` z `/proc`, `/sys`, `/` zamontowanymi **`:ro`** |
| Logi kontenerów | Docker API (odczyt strumienia logów) |
| Logi hosta | journald zamontowany **`:ro`** |
| Logi Traefika | cudzy wolumen `portainer-edge-gateway_traefik-logs` zamontowany **`:ro`** |
| Powiadomienia | ruch **wychodzący** do ntfy.sh, SMTP i healthchecks.io |

## Czego stack NIGDY nie robi

- nie wywołuje `docker service update/scale/restart/rm`, `docker stack rm`, `docker prune`, `volume rm`;
- nie zmienia zmiennych środowiskowych ani konfiguracji innych stacków;
- nie dotyka Traefika, Portainera, CrowdSeca, firewall-a hosta ani `/etc/docker/daemon.json`;
- nie publikuje **żadnego** portu na hoście (co eliminuje kolizje, m.in. z Cockpitem na 9090);
- nie tworzy ani nie modyfikuje cudzych sieci, wolumenów i konfiguracji Swarma;
- nie usuwa starych wolumenów `monitoring_*` z poprzedniego wdrożenia (zostają jako archiwum).

## Granice wiedzy (świadome kompromisy)

1. **Monitoring na tym samym hoście nie zgłosi śmierci hosta.** Dlatego kanał
   zewnętrzny (healthchecks.io) jest warunkiem, nie dodatkiem: cisza po stronie
   zewnętrznej = alarm.
2. **Docker daemon metrics** (`127.0.0.1:9323`) są niedostępne z wnętrza kontenerów.
   Wystawienie ich na `172.17.0.1` wymagałoby zmiany `daemon.json` — świadomie
   odłożone, bo to zmiana hosta dotykająca wszystkich kontenerów.
3. **SMART** może nie przechodzić przez wirtualizację OVH. Jeśli `smartctl` nie
   zwraca danych, rolę czujnika sprzętowego przejmują alerty z logów jądra
   (`KernelDiskErrors`).
4. **Metryki bazy** nie są zbierane przez `postgres_exporter`, bo to wymagałoby
   założenia roli w produkcyjnej bazie. Zamiast tego czytamy **logi** bazy
   (`PgPageVerificationFailed`, `PgPanic`) — bez dotykania aplikacji.
5. **Aplikacje bez trasy w Traefiku** (workery, bazy) mają monitoring kontenerowy
   (replikacje, zadania, zasoby, logi), ale nie mają sondy HTTP.

## Jak dodać wyjątek

Każde odstępstwo od tej zasady wymaga **Twojej wyraźnej zgody** i wpisu tutaj,
wraz z powodem i zakresem. Domyślnie: nie.
