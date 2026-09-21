# Alertmanager z konfiguracją routingu (bez sekretów — powiadomienia robi `notifier`).
FROM prom/alertmanager:v0.34.1
USER root
COPY config/alertmanager/alertmanager.yml /etc/alertmanager/alertmanager.yml
USER nobody
