# health-ping — watchdog wychodzący do healthchecks.io.
#
# Wymaga zamontowanego gniazda Dockera (tylko do odczytu, do czytania logów backupu):
#   /var/run/docker.sock:/var/run/docker.sock:ro
# Oraz pliku ze stanem testu odtworzenia (opcjonalnie, tylko do odczytu):
#   /data/restore-test.json:/data/restore-test.json:ro
FROM python:3.13-alpine

# Użytkownik nieuprzywilejowany (UID 10001); serwis pisze wyłącznie do /tmp.
RUN adduser -D -H -u 10001 -s /sbin/nologin monitoring \
    && mkdir -p /app \
    && chown -R 10001:10001 /app

WORKDIR /app
COPY main.py /app/main.py
RUN chmod 0644 /app/main.py && chown 10001:10001 /app/main.py

USER 10001
EXPOSE 8080

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080

CMD ["python3", "/app/main.py"]
