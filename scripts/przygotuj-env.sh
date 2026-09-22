#!/usr/bin/env bash
# Przygotowuje KOMPLETNY blok zmiennych środowiskowych dla stacku `monitoring`
# w Portainerze i wypisuje go w formacie KLUCZ=WARTOŚĆ do wklejenia.
#
# Skąd bierze listę kluczy: z `env.portainer.paste.txt` (jedno źródło prawdy),
# więc nie może się rozjechać z tym, czego wymaga docker-compose.yml.
#
# Użycie:
#   scripts/przygotuj-env.sh                 # tryb interaktywny (pyta o wszystko)
#   scripts/przygotuj-env.sh --plik /tmp/env.txt
#   scripts/przygotuj-env.sh --nieinteraktywny   # wartości z ENV: HASLO_PANEL, HASLO_GRAFANA, …
#
# Uwaga bezpieczeństwa: wypisany blok zawiera SEKRETY (hasła, tokeny). Nie wklejaj
# go na czacie, w zgłoszeniu ani w repo — wklejasz go tylko w Portainera.

set -euo pipefail

SZABLON="env.portainer.paste.txt"
PLIK_WYJSCIOWY=""
INTERAKTYWNY=1

while [ $# -gt 0 ]; do
  case "$1" in
    --plik) PLIK_WYJSCIOWY="${2:-}"; shift 2 ;;
    --nieinteraktywny) INTERAKTYWNY=0; shift ;;
    -h|--help) sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Nieznany argument: $1" >&2; exit 2 ;;
  esac
done

KATALOG="$(cd "$(dirname "$0")/.." && pwd)"
cd "$KATALOG"
[ -f "$SZABLON" ] || { echo "✗ nie widzę $SZABLON (uruchamiasz z repo?)" >&2; exit 1; }

if [ -t 1 ]; then
  B=$'\033[1m'; Z=$'\033[32m'; C=$'\033[31m'; Y=$'\033[33m'; N=$'\033[0m'
else
  B=""; Z=""; C=""; Y=""; N=""
fi
krok()  { echo; echo "${B}== $* ==${N}"; }
ok()    { echo "  ${Z}✓${N} $*"; }
uwaga() { echo "  ${Y}!${N} $*"; }
blad()  { echo "  ${C}✗${N} $*" >&2; }

# --------------------------------------------------------------------------
# Pytanie o wartość. W trybie nieinteraktywnym bierze zmienną środowiskową.
# $1 = nazwa zmiennej, $2 = opis, $3 = wartość domyślna ("" = brak), $4 = "tajne"
# --------------------------------------------------------------------------
pytaj() {
  local nazwa="$1" opis="$2" domyslna="${3:-}" tajne="${4:-}"
  local odp
  if [ "$INTERAKTYWNY" -eq 0 ]; then
    odp="${!nazwa:-$domyslna}"
    printf '  %-22s %s\n' "$nazwa" "$([ -n "$odp" ] && echo '(ustawione)' || echo '(puste)')"
  elif [ "$tajne" = "tajne" ]; then
    read -r -s -p "  $opis: " odp; echo
  else
    if [ -n "$domyslna" ]; then
      read -r -p "  $opis [$domyslna]: " odp || true
      odp="${odp:-$domyslna}"
    else
      read -r -p "  $opis: " odp || true
    fi
  fi
  printf -v "$nazwa" '%s' "$odp"
}

losowe() {  # długi losowy ciąg (litery+cyfry), bezpieczny w URL i w env
  # Bez `tr | head`: head zamyka rurę i przy `set -e` ubija cały skrypt.
  local n="${1:-40}"
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 32 | cut -c1-"$n"
  else
    od -An -tx1 /dev/urandom 2>/dev/null | tr -d ' \n' | cut -c1-"$n" || true
  fi
}

# --------------------------------------------------------------------------
krok "1/6  Hasło do panelu (PANEL_AUTH_PASSWORD_HTPASSWD)"

pytaj HASLO_PANEL "Hasło do panelu (Enter = wygeneruję losowe)" "" tajne
WYGENEROWANE_PANEL=""
if [ -z "$HASLO_PANEL" ]; then
  HASLO_PANEL="$(losowe 20)"
  WYGENEROWANE_PANEL="$HASLO_PANEL"
  uwaga "wygenerowałem hasło panelu — zapisz je, pokażę je na końcu"
fi

zahashuj() {  # $1 = hasło -> linia "admin:<hash>"
  local haslo="$1" wynik=""
  if command -v htpasswd >/dev/null 2>&1; then
    wynik="$(htpasswd -nbB admin "$haslo" 2>/dev/null || true)"
  fi
  if [ -z "$wynik" ] && command -v docker >/dev/null 2>&1; then
    wynik="$(docker run --rm httpd:2.4-alpine htpasswd -nbB admin "$haslo" 2>/dev/null || true)"
  fi
  if [ -z "$wynik" ] && command -v python3 >/dev/null 2>&1; then
    wynik="$(python3 - "$haslo" <<'PY' 2>/dev/null || true
import sys
try:
    import crypt
    print("admin:" + crypt.crypt(sys.argv[1], crypt.mksalt(crypt.METHOD_BLOWFISH)))
except Exception:
    pass
PY
)"
  fi
  if [ -z "$wynik" ] && command -v openssl >/dev/null 2>&1; then
    wynik="admin:$(openssl passwd -apr1 "$haslo")"
    uwaga "użyłem openssl (apr1) — słabszy hash niż bcrypt; zalecany htpasswd albo docker"
  fi
  printf '%s' "$wynik"
}

HASH="$(zahashuj "$HASLO_PANEL")"
if [ -z "$HASH" ]; then
  blad "nie umiem wygenerować hasha (brak htpasswd, dockera, pythona i openssl)"
  exit 1
fi
# Weryfikacja: hash musi pasować do hasła (sprawdzamy kryptograficznie, nie „na oko").
if command -v python3 >/dev/null 2>&1; then
  if python3 - "$HASLO_PANEL" "$HASH" <<'PY' 2>/dev/null
import sys
try:
    import crypt
except Exception:
    sys.exit(0)  # brak modułu = nie umiemy sprawdzić, nie blokujemy
haslo, hash_ = sys.argv[1], sys.argv[2].split(":", 1)[1]
sys.exit(0 if crypt.crypt(haslo, hash_) == hash_ else 1)
PY
  then ok "hash wygenerowany i sprawdzony (pasuje do hasła)"
  else blad "hash nie pasuje do hasła — przerywam"; exit 1; fi
else
  ok "hash wygenerowany"
fi
# Portainer rozwija `$` w wartościach, więc każdy `$` musi być podwojony.
HASHPASS="${HASH//\$/\$\$}"
ok "podwoiłem \$ w hashu (Portainer rozwija \$ w wartościach env)"

# --------------------------------------------------------------------------
krok "2/6  Hasło administratora Grafany (GRAFANA_ADMIN_PASSWORD)"

pytaj HASLO_GRAFANA "Hasło do Grafany (Enter = wygeneruję losowe)" "" tajne
WYGENEROWANE_GRAFANA=""
if [ -z "$HASLO_GRAFANA" ]; then
  HASLO_GRAFANA="$(losowe 20)"
  WYGENEROWANE_GRAFANA="$HASLO_GRAFANA"
  uwaga "wygenerowałem hasło Grafany — pokażę je na końcu"
fi
[ "${#HASLO_GRAFANA}" -ge 12 ] || uwaga "hasło Grafany jest krótsze niż 12 znaków"

# --------------------------------------------------------------------------
krok "3/6  Powiadomienia na telefon (ntfy.sh)"

NTFY_DOMYSLNY="mon-$(losowe 24)"
pytaj NTFY_TOPIC "Temat ntfy (Enter = wygeneruję)" "$NTFY_DOMYSLNY"
pytaj NTFY_TOKEN "Token ntfy (ntfy.sh → Access tokens; Enter = pomiń)" ""
[ -n "$NTFY_TOKEN" ] || uwaga "bez tokenu temat jest publiczny dla znających nazwę"

# --------------------------------------------------------------------------
krok "4/6  E-mail (SMTP OVH — wartości domyślne już pasują)"

pytaj SMTP_USERNAME "Login SMTP (pełny adres e-mail)" ""
pytaj SMTP_PASSWORD "Hasło SMTP" "" tajne
pytaj ALERT_EMAIL_FROM "Nadawca (From)" "${SMTP_USERNAME:-}"
pytaj ALERT_EMAIL_TO "Odbiorca (To, przecinek = kilku)" "${SMTP_USERNAME:-}"

# --------------------------------------------------------------------------
krok "5/6  Watchdog healthchecks.io, token notifiera, GID Dockera"

pytaj HC_PING_ALL_OK "Ping URL checku 'vps-all-ok'" ""
pytaj HC_PING_MONITORING "Ping URL checku 'monitoring-alive'" ""
pytaj HC_PING_BACKUP "Ping URL checku 'backup-ventiplan'" ""

for zmienna in HC_PING_ALL_OK HC_PING_MONITORING HC_PING_BACKUP; do
  wartosc="${!zmienna}"
  [ -z "$wartosc" ] && continue
  case "$wartosc" in
    http*) ok "$zmienna wygląda jak URL" ;;
    *) uwaga "$zmienna nie zaczyna się od http — sprawdź, czy to na pewno ping URL" ;;
  esac
done

NOTIFIER_DOMYSLNY="$(losowe 40)"
pytaj NOTIFIER_TOKEN "NOTIFIER_TOKEN (Enter = wygeneruję)" "$NOTIFIER_DOMYSLNY"

echo "  GID grupy Dockera na VPS — sprawdź: ssh <vps> 'stat -c %g /var/run/docker.sock'"
pytaj DOCKER_GID "DOCKER_GID" "999"
case "$DOCKER_GID" in
  ''|*[!0-9]*) blad "DOCKER_GID musi być liczbą (jest: '$DOCKER_GID')"; exit 1 ;;
  *) [ "$DOCKER_GID" = "999" ] && uwaga "zostawiłem 999 — jeśli na VPS jest inny GID, discovery i promtail nie odczytają Dockera" ;;
esac

# --------------------------------------------------------------------------
krok "6/6  Cloudflare R2 (opcjonalne — Enter pomija)"

pytaj R2_ENDPOINT "R2 endpoint (Enter = pomiń)" ""
if [ -n "$R2_ENDPOINT" ]; then
  pytaj R2_ACCESS_KEY "R2 access key (tylko odczyt)" ""
  pytaj R2_SECRET_KEY "R2 secret key" "" tajne
else
  R2_ACCESS_KEY=""; R2_SECRET_KEY=""
  uwaga "bez R2 kontrola backupu zejdzie na logi usługi backupu"
fi

# --------------------------------------------------------------------------
# Składanie wyniku: klucze i wartości domyślne bierzemy z szablonu w repo.
# --------------------------------------------------------------------------
declare -A NADPISZ=(
  [PANEL_AUTH_PASSWORD_HTPASSWD]="$HASHPASS"
  [GRAFANA_ADMIN_PASSWORD]="$HASLO_GRAFANA"
  [NTFY_TOPIC]="$NTFY_TOPIC"
  [NTFY_TOKEN]="$NTFY_TOKEN"
  [SMTP_USERNAME]="$SMTP_USERNAME"
  [SMTP_PASSWORD]="$SMTP_PASSWORD"
  [ALERT_EMAIL_FROM]="$ALERT_EMAIL_FROM"
  [ALERT_EMAIL_TO]="$ALERT_EMAIL_TO"
  [HC_PING_ALL_OK]="$HC_PING_ALL_OK"
  [HC_PING_MONITORING]="$HC_PING_MONITORING"
  [HC_PING_BACKUP]="$HC_PING_BACKUP"
  [NOTIFIER_TOKEN]="$NOTIFIER_TOKEN"
  [DOCKER_GID]="$DOCKER_GID"
  [R2_ENDPOINT]="$R2_ENDPOINT"
  [R2_ACCESS_KEY]="$R2_ACCESS_KEY"
  [R2_SECRET_KEY]="$R2_SECRET_KEY"
)

WYNIK=""
BRAKUJE=()
while IFS= read -r linia; do
  case "$linia" in
    ''|'#'*) continue ;;
    *=*)
      klucz="${linia%%=*}"
      wartosc="${linia#*=}"
      if [ -n "${NADPISZ[$klucz]+x}" ]; then
        wartosc="${NADPISZ[$klucz]}"
      fi
      # Szablon trzyma placeholdery „>>> …" — jeśli został taki, znaczy że nikt
      # nie podał wartości w tym przebiegu.
      case "$wartosc" in
        *'>>>'*) BRAKUJE+=("$klucz"); wartosc="" ;;
      esac
      WYNIK+="$klucz=$wartosc"$'\n'
      ;;
  esac
done < "$SZABLON"

echo
echo "${B}================= DO WKLEJENIA W PORTAINERA =================${N}"
echo "${B}(Stacks → Add stack → Environment variables → Bulk edit)${N}"
echo
printf '%s' "$WYNIK"
echo "${B}=============================================================${N}"

if [ -n "$PLIK_WYJSCIOWY" ]; then
  (umask 077; printf '%s' "$WYNIK" > "$PLIK_WYJSCIOWY")
  ok "zapisałem też do $PLIK_WYJSCIOWY (uprawnienia 600)"
fi

# Co nie zadziała, jeśli zostało puste — żeby dowiedzieć się TERAZ, a nie po awarii.
# (Te same zależności opisuje DEPLOY.md; bez tych wartości monitoring wstanie niemy.)
wartosc() { printf '%s' "$1" | sed -n "s/^$2=//p"; }
ZDANIE=()
[ -n "$(wartosc "$WYNIK" NTFY_TOPIC)" ] && [ -n "$(wartosc "$WYNIK" NTFY_TOKEN)" ] \
  || ZDANIE+=("powiadomienia na telefon (ntfy): brak tematu lub tokenu — zostanie tylko e-mail")
[ -n "$(wartosc "$WYNIK" SMTP_USERNAME)" ] && [ -n "$(wartosc "$WYNIK" SMTP_PASSWORD)" ] \
  && [ -n "$(wartosc "$WYNIK" ALERT_EMAIL_TO)" ] \
  || ZDANIE+=("e-mail: brak loginu, hasła SMTP lub odbiorcy — nie dostaniesz żadnego maila")
for klucz in HC_PING_ALL_OK HC_PING_MONITORING HC_PING_BACKUP; do
  [ -n "$(wartosc "$WYNIK" "$klucz")" ] || ZDANIE+=("watchdog: $klucz pusty — nie zauważysz, gdy monitoring sam padnie")
done
[ -n "$(wartosc "$WYNIK" NOTIFIER_TOKEN)" ] || ZDANIE+=("NOTIFIER_TOKEN pusty — endpoint /status/alert odrzuci powiadomienia z Akcji")
[ "$(wartosc "$WYNIK" DOCKER_GID)" = "999" ] \
  && ZDANIE+=("DOCKER_GID=999 to domyślna wartość — jeśli na VPS jest inny GID, discovery i promtail nie odczytają Dockera")

echo
if [ "${#BRAKUJE[@]}" -gt 0 ]; then
  uwaga "pole zostało z placeholderem (nie podano wartości): ${BRAKUJE[*]}"
fi
if [ "${#ZDANIE[@]}" -gt 0 ]; then
  echo "${Y}Co NIE zadziała przy tych wartościach:${N}"
  for pozycja in "${ZDANIE[@]}"; do echo "  - $pozycja"; done
else
  ok "komplet: telefon, e-mail, watchdog i GID Dockera są ustawione"
fi
if [ -n "$WYGENEROWANE_PANEL" ] || [ -n "$WYGENEROWANE_GRAFANA" ]; then
  echo
  echo "${B}ZAPISZ TE HASŁA — pokazuję je tylko tutaj:${N}"
  [ -n "$WYGENEROWANE_PANEL" ]   && echo "  panel  (admin): $WYGENEROWANE_PANEL"
  [ -n "$WYGENEROWANE_GRAFANA" ] && echo "  Grafana(admin): $WYGENEROWANE_GRAFANA"
fi
echo
echo "${Y}To nie jest tajne, ale ten blok zawiera sekrety — nie wklejaj go na czacie.${N}"
echo "Dalej: Stacks → Add stack → Repository → ${B}Compose path: docker-compose.yml${N} → wklej blok → Deploy."
