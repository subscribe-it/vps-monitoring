# notifier — jedyne wyjście alertów (ntfy + e-mail).
#
# Nie potrzebuje gniazda Dockera ani wolumenów — cały stan trzyma w pamięci,
# a jedyne zapisy (jeśli w ogóle) idą do /tmp.
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
