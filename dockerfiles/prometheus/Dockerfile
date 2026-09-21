# Prometheus z konfiguracją i regułami wypalonymi w obrazie.
# Konfiguracja nie zawiera sekretów, więc nie ma tu żadnego renderowania z env.
FROM prom/prometheus:v3.14.0
USER root
COPY config/prometheus/prometheus.yml /etc/prometheus/prometheus.yml
COPY config/prometheus/alerts /etc/prometheus/alerts
USER nobody
