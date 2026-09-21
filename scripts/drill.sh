#!/usr/bin/env bash
# =============================================================================
#  Drille alertów — dowód, że alerty faktycznie dzwonią.
#
#  Każdy drill dotyka WYŁĄCZNIE stacku `monitoring` (nigdy cudzych aplikacji).
#  Uruchomienie:  ./scripts/drill.sh [kanal|repliki|wszystko]
# =============================================================================
set -uo pipefail

AM="${ALERTMANAGER_URL:-https://monitoring.subscribeit.pl/alertmanager}"
AUTH="${DRILL_AUTH:-}"   # np. admin:haslo (ForwardAuth przed Alertmanagerem)
MODE="${1:-wszystko}"

curl_am() { curl -sS -u "$AUTH" -H 'Content-Type: application/json' "$@"; }
head_() { printf '\n\033[1m%s\033[0m\n' "$1"; }

drill_channel() {
  head_ "DRILL 1 — kanał powiadomień (alert syntetyczny → ntfy + e-mail)"
  echo "  Wysyłam alert testowy do Alertmanagera…"
  now="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  payload=$(cat <<JSON
[{"labels":{"alertname":"DrillTest","severity":"warning","stack":"monitoring","source":"drill"},
  "annotations":{"summary":"Drill: test kanału powiadomień","description":"Jeśli to widzisz, kanał działa. Alert wygaśnie sam po ok. 5 minutach.","runbook":"#notifications"},
  "startsAt":"$now"}]
JSON
)
  if curl_am -X POST "$AM/api/v2/alerts" -d "$payload"; then
    echo "  ✓ wysłane — sprawdź telefon (ntfy) i skrzynkę e-mail"
    echo "    aby zakończyć wcześniej: curl -X DELETE …/api/v2/alerts (albo poczekaj na resolve)"
  else
    echo "  ✗ nie udało się wysłać (sprawdź AUTH i adres Alertmanagera)"
  fi
}

drill_replicas() {
  head_ "DRILL 2 — repliki (skaluję WŁASNĄ usługę do zera)"
  echo "  Skaluję monitoring_health-ping 1 → 0 (to nasz stack, nic więcej)"
  docker service scale monitoring_health-ping=0 >/dev/null 2>&1 || {
    echo "  ✗ nie udało się (brak dostępu do dockera?)"; return 1; }
  echo "  ✓ alert SwarmServiceReplicasMismatch powinien pojawić się w ~5 minut"
  echo "    i zniknąć po przywróceniu repliki. Przywracam za 20 s…"
  sleep 20
  docker service scale monitoring_health-ping=1 >/dev/null 2>&1
  echo "  ✓ replika przywrócona — sprawdź w Alertmanagerze stan 'resolved'"
}

case "$MODE" in
  kanal)    drill_channel ;;
  repliki)  drill_replicas ;;
  wszystko) drill_channel; drill_replicas ;;
  *) echo "użycie: $0 [kanal|repliki|wszystko]"; exit 2 ;;
esac

cat <<'INFO'

Po drillu sprawdź:
  1. telefon — push ntfy z alertem,
  2. skrzynkę — e-mail z Alertmanagera,
  3. https://monitoring.subscribeit.pl/alertmanager — czy alert się pojawił i wygasił,
  4. https://healthchecks.io — czy heartbeat "vps-all-ok" był zielony (jeśli nie, sprawdź /status/api.json).
INFO
