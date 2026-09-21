#!/usr/bin/env bash
# =============================================================================
#  Pre-flight stacku `monitoring` — WYŁĄCZNIE ODCZYT.
#
#  Sprawdza, czy wdrożenie NIE koliduje z tym, co już działa na hoście:
#    - nazwy usług, wolumenów i sieci
#    - publikowane porty (stack nie publikuje żadnego — to ma potwierdzić skrypt)
#    - domeny w routerach Traefika (kolizja = przejęcie ruchu cudzej aplikacji)
#    - limity zasobów vs wolne zasoby hosta
#
#  Uruchomienie:  ./scripts/preflight.sh            (na hoście, wymaga docker)
#                 ssh … 'bash -s' < scripts/preflight.sh
# =============================================================================
set -uo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE="${REPO_DIR}/docker-compose.yml"
DOMAIN="${MONITORING_DOMAIN:-monitoring.subscribeit.pl}"
FAIL=0

ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$1"; }
bad()  { printf '  \033[31m✗\033[0m %s\n' "$1"; FAIL=1; }
head_() { printf '\n\033[1m%s\033[0m\n' "$1"; }

command -v docker >/dev/null || { echo "brak dockera — uruchom na hoście VPS"; exit 2; }

head_ "1. Usługi Swarma"
collisions=$(docker service ls --format '{{.Name}}' | grep -E '^monitoring_' || true)
[ -z "$collisions" ] && ok "brak usług monitoring_* (nic nie nadpiszemy)" \
                     || bad "istnieją usługi o naszych nazwach: $collisions"

head_ "2. Wolumeny"
for v in prometheus_data_v2 grafana_data_v2 loki_data_v2 alertmanager_data_v2; do
  if docker volume ls --format '{{.Name}}' | grep -qx "monitoring_${v}"; then
    warn "wolumen monitoring_${v} już istnieje — zostanie użyty ponownie"
  else
    ok "wolumen monitoring_${v} zostanie utworzony"
  fi
done
for v in prometheus_data grafana_data loki_data alertmanager_data uptime_kuma_data duplicati_data; do
  docker volume ls --format '{{.Name}}' | grep -qx "monitoring_${v}" && \
    warn "stary wolumen monitoring_${v} zostaje NIETKNIĘTY (archiwum)"
done
docker volume ls --format '{{.Name}}' | grep -qx "portainer-edge-gateway_traefik-logs" \
  && ok "wolumen logów Traefika istnieje (montujemy go tylko :ro)" \
  || warn "brak wolumenu portainer-edge-gateway_traefik-logs — promtail nie zbierze access logów"

head_ "3. Sieci"
docker network ls --format '{{.Name}}' | grep -qx 'traefik-public' \
  && ok "sieć traefik-public istnieje" || bad "brak sieci traefik-public (edge!)"
docker network ls --format '{{.Name}}' | grep -qx 'monitoring' \
  && warn "sieć monitoring już istnieje (zostanie użyta)" || ok "sieć monitoring zostanie utworzona"

head_ "4. Porty"
if grep -qE '^\s+ports:' "$COMPOSE"; then
  bad "compose zawiera 'ports:' — stack nie może publikować portów"
else
  ok "stack nie publikuje żadnego portu (zero ryzyka kolizji, m.in. z Cockpitem na 9090)"
fi

head_ "5. Domeny Traefika"
routers=$(grep -oE 'Host\(`[^`]+`\)' "$COMPOSE" | sed 's/Host(`//;s/`)//;s/\${MONITORING_DOMAIN:-'"$DOMAIN"'}/'"$DOMAIN"'/' | sort -u)
ours=$(docker service ls --format '{{.Name}}' | while read -r s; do
  docker service inspect "$s" --format '{{range $k,$v := .Spec.Labels}}{{$k}}={{$v}}{{"\n"}}{{end}}' 2>/dev/null
done | grep -oE 'Host\(`[^`]+`\)' | sed 's/Host(`//;s/`)//' | sort -u)
for d in $routers; do
  if printf '%s\n' "$ours" | grep -qx "$d"; then
    bad "domena $d jest JUŻ obsługiwana przez inny stack — kolizja!"
  else
    ok "domena $d jest wolna"
  fi
done

head_ "6. Zasoby"
cpus=$(nproc 2>/dev/null || echo '?'); mem=$(free -m | awk '/^Mem:/{print $2}')
avail=$(free -m | awk '/^Mem:/{print $7}')
echo "  host: ${cpus} CPU, ${mem} MiB RAM (dostępne ${avail} MiB)"
if [ "$avail" != "?" ] && [ "$avail" -lt 2048 ]; then
  warn "mniej niż 2 GiB wolnej pamięci — sprawdź, czy monitoring się zmieści"
else
  ok "wolnej pamięci wystarczy dla stacku (limity: ok. 3,7 GiB)"
fi
swap=$(free -m | awk '/^Swap:/{print $2}')
[ "$swap" = "0" ] && warn "swap = 0 B — presja pamięci skończy się OOM bez ostrzeżenia (alerty to pokrywają)" \
                  || ok "swap aktywny: ${swap} MiB"

head_ "7. Dostęp do gniazda Dockera"
if [ -S /var/run/docker.sock ]; then
  gid=$(stat -c %g /var/run/docker.sock)
  echo "  gniazdo /var/run/docker.sock należy do grupy o GID: ${gid}"
  if [ "${gid}" = "${DOCKER_GID:-999}" ]; then
    ok "DOCKER_GID=${gid} zgadza się z ustawieniem stacku"
  else
    warn "ustaw w env stacku DOCKER_GID=${gid} (obecnie: ${DOCKER_GID:-999}) — inaczej discovery nie odczyta usług"
  fi
else
  bad "brak /var/run/docker.sock"
fi

head_ "8. DNS monitoringu"
if command -v dig >/dev/null; then
  ip=$(dig +short "$DOMAIN" A | head -1)
  if [ -z "$ip" ]; then bad "$DOMAIN nie rozwiązuje się — certyfikat się nie wystawi"
  else ok "$DOMAIN → $ip"; fi
else
  warn "brak dig — pomijam sprawdzenie DNS"
fi

head_ "WYNIK"
if [ "$FAIL" = 0 ]; then
  printf '  \033[32mPre-flight zaliczony — wdrożenie nie koliduje z istniejącymi stackami.\033[0m\n'
else
  printf '  \033[31mPre-flight wykrył problemy (patrz ✗ powyżej) — NIE wdrażaj do czasu ich usunięcia.\033[0m\n'
fi
exit "$FAIL"
