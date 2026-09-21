# Blackbox exporter z modułami sond wypalonymi w obrazie.
# Moduły są NIESTANDARDOWE (http_expect_auth, http_2xx_3xx, http_alive), więc
# domyślna konfiguracja z obrazu bazowego NIE WYSTARCZY — bez tego pliku
# Prometheus dostawałby 400 "Unknown module" i alerty o łańcuchu monitoringu
# dzwoniłyby fałszywie.
FROM prom/blackbox-exporter:v0.28.0
USER root
COPY config/blackbox/blackbox.yml /etc/blackbox_exporter/config.yml
USER nobody
