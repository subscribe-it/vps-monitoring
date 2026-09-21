# Testy integracyjne

## Atrapa Docker API (`fake_docker_api.py`)

Serwis `discovery` czyta **Docker Swarm API**. Na zwykłym demonie (bez Swarma)
`/services` zwraca 503, więc funkcji nie da się sprawdzić „na żywo" bez stawiania
kolejnego roju. Ta atrapa udostępnia realistyczne payloady Swarma na gnieździe
unix — wystarczy podać je kontenerowi zamiast prawdziwego gniazda.

Po co: sprawdzenie **auto-discovery** (wykrywanie tras z labeli Traefika,
klasyfikacja istotności, pomijanie usług oznaczonych `monitoring.io/skip`,
tryb global, metryki replik) bez dotykania żadnego działającego środowiska.

```bash
# 1) atrapa
python3 tests/integration/fake_docker_api.py &      # gniazdo: /tmp/fake-docker.sock

# 2) discovery przeciwko atrapie (UID 10001 z grupą gniazda)
docker run --rm -d --name disc-fake \
  --user "10001:$(stat -c %g /var/run/docker.sock)" \
  -v /tmp/fake-docker.sock:/var/run/docker.sock \
  -e REFRESH_SECONDS=5 -e CRITICAL_STACKS=ventiplan-prod,star-sign \
  local/discovery:test

# 3) co wykrył
docker run --rm --network container:disc-fake curlimages/curl -s http://127.0.0.1:8080/sd/http.json
docker run --rm --network container:disc-fake curlimages/curl -s http://127.0.0.1:8080/metrics | grep swarm_service
docker run --rm --network container:disc-fake curlimages/curl -s http://127.0.0.1:8080/status/api.json
```

Oczekiwany wynik (stan na 2026-09-22): dwa cele w HTTP SD
(`https://api.ventiplan.pl`, `https://star-sign.pl/app`), usługi z `skip`
nieobecne w metrykach, tryb global z `desired=1`, usługa z padniętym zadaniem
jako `1/2`.

**Uwaga:** atrapa jest wyłącznie do użytku lokalnego. Nigdy nie uruchamiaj jej
na hoście produkcyjnym i nie podłączaj jej do działającego stacku.
