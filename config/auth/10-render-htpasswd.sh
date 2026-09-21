#!/bin/sh
# Renderuje plik htpasswd dla ForwardAuth ze zmiennej środowiskowej stacka.
#
# Obsługiwane są CZTERY warianty wartości (bo tak różnie ludzie wklejają):
#   1) admin:$2y$05$...          (pełna linia z `htpasswd -nbB`)
#   2) admin:$$2y$$05$$...       (to samo po przejściu przez Portainera)
#   3) $2y$05$...                (sam hash — doklejamy AUTH_USER)
#   4) $$2y$$05$$...             (sam hash, podwójne $)
# Wariant z INNĄ nazwą użytkownika niż AUTH_USER też jest respektowany (z ostrzeżeniem).
set -eu

: "${AUTH_USER:=admin}"
if [ -z "${AUTH_PASSWORD_HTPASSWD:-}" ]; then
  echo "[auth] BŁĄD: brak zmiennej PANEL_AUTH_PASSWORD_HTPASSWD — przerywam," \
       "żeby nie wystawić paneli bez uwierzytelnienia (fail-closed)." >&2
  exit 1
fi

value="${AUTH_PASSWORD_HTPASSWD}"

# Portainer potrafi przekazać podwójne $$ — normalizujemy PRZED wykryciem prefiksu.
case "${value}" in
  *'$$'*)
    value="$(printf '%s' "${value}" | sed 's/\$\$/$/g')"
    echo "[auth] uwaga: wykryto podwójne \$\$ w hashu — znormalizowano do pojedynczych"
    ;;
esac

case "${value}" in
  "${AUTH_USER}:"*)
    line="${value}"
    echo "[auth] wykryto pełną linię htpasswd dla użytkownika ${AUTH_USER}"
    ;;
  *:*)
    line="${value}"
    echo "[auth] OSTRZEŻENIE: wartość zawiera ':' — traktuję ją jako pełną linię htpasswd" \
         "(użytkownik z tej linii, nie AUTH_USER=${AUTH_USER})" >&2
    ;;
  *)
    line="${AUTH_USER}:${value}"
    echo "[auth] wykryto sam hash — doklejono użytkownika ${AUTH_USER}"
    ;;
esac

case "${line}" in
  *':$2y$'*|*':$2a$'*|*':$2b$'*|*':$apr1$'*|*':$1$'*|*':$5$'*|*':$6$'*)
    ;;
  *)
    echo "[auth] OSTRZEŻENIE: to nie wygląda na hash htpasswd. Wygeneruj go tak:" \
         "docker run --rm httpd:2.4-alpine htpasswd -nbB ${AUTH_USER} 'HASLO'" >&2
    ;;
esac

printf '%s\n' "${line}" > /etc/nginx/htpasswd
chown nginx:nginx /etc/nginx/htpasswd
chmod 0640 /etc/nginx/htpasswd
echo "[auth] htpasswd gotowy: $(printf '%s' "${line}" | cut -d: -f1) (długość linii: $(printf '%s' "${line}" | wc -c) znaków)"
