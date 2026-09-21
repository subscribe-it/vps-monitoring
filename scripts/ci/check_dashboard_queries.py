#!/usr/bin/env python3
"""Sprawdza składnię WSZYSTKICH zapytań z dashboardów Grafany.

Dashboard z literówką w PromQL/LogQL jest poprawnym JSON-em i przechodzi każdą
statyczną walidację — a użytkownik widzi „error" w panelu. Ten skrypt wysyła
każde zapytanie do działającego Prometheusa i Loki i raportuje odrzucone.

Uruchomienie (wymaga wystawionych PROMETHEUS_URL i LOKI_URL):
    PROMETHEUS_URL=http://127.0.0.1:9090 LOKI_URL=http://127.0.0.1:3100 \
        python3 scripts/ci/check_dashboard_queries.py
"""
import glob
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

PROM = os.environ.get("PROMETHEUS_URL", "").rstrip("/")
LOKI = os.environ.get("LOKI_URL", "").rstrip("/")

# Zapytania specyficzne dla Grafany — nie są PromQL-em, więc walidujemy ich
# wewnętrzny selektor (pierwszy argument), a nie całość.
GRAFANAOWE = re.compile(r"^(label_values|query_result|metrics|label_names)\s*\((.*)\)\s*$", re.S)


def pierwszy_argument(argumenty: str) -> str:
    """Pierwszy argument listy, ale przecinki wewnątrz {…} i cudzysłowów nie liczą się."""
    glebokosc, w_cudzyslowie = 0, False
    for i, znak in enumerate(argumenty):
        if znak == '"' and (i == 0 or argumenty[i - 1] != "\\"):
            w_cudzyslowie = not w_cudzyslowie
        elif not w_cudzyslowie:
            if znak in "{[":
                glebokosc += 1
            elif znak in "}]":
                glebokosc -= 1
            elif znak == "," and glebokosc == 0:
                return argumenty[:i].strip()
    return argumenty.strip()


def zapytanie_ok(url, params, timeout=15):
    dane = urllib.parse.urlencode(params).encode()
    try:
        with urllib.request.urlopen(url + "?" + dane.decode(), timeout=timeout) as r:
            body = json.loads(r.read())
        return body.get("status") != "error", body.get("error") or ""
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read())
            return False, body.get("error") or f"HTTP {e.code}"
        except Exception:  # noqa: BLE001
            return False, f"HTTP {e.code}"
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"


def zbierz_zapytania():
    prom, loki = [], []
    for plik in sorted(glob.glob("config/grafana/dashboards/*.json")):
        d = json.load(open(plik, encoding="utf-8"))

        def z_paneli(panele):
            for p in panele or []:
                if p.get("type") == "row":
                    z_paneli(p.get("panels"))
                    continue
                for t in p.get("targets") or []:
                    expr = (t.get("expr") or "").strip()
                    if not expr:
                        continue
                    typ = (t.get("datasource") or {}).get("type", "prometheus")
                    (loki if typ == "loki" else prom).append((plik, p.get("title", "?"), expr))
                z_paneli(p.get("panels"))

        z_paneli(d.get("panels"))

        for v in d.get("templating", {}).get("list", []) or []:
            surowe = v.get("query")
            if isinstance(surowe, dict):
                q = (surowe.get("query") or "").strip()
            else:
                q = (surowe or "").strip()
            if not q:
                continue
            typ = v.get("datasource", {}).get("type", "prometheus") if isinstance(v.get("datasource"), dict) else "prometheus"
            m = GRAFANAOWE.match(q)
            if m:
                wewn = pierwszy_argument(m.group(2))
                (loki if wewn.startswith("{") or "|" in wewn else prom).append((plik, f"zmienna {v.get('name')}", wewn))
            else:
                (loki if typ == "loki" else prom).append((plik, f"zmienna {v.get('name')}", q))
    return prom, loki


def main() -> int:
    prom, loki = zbierz_zapytania()
    bledy = []
    if PROM:
        for plik, tytul, expr in prom:
            ok, err = zapytanie_ok(PROM + "/api/v1/query", {"query": expr})
            if not ok:
                bledy.append(f"PROMQL {plik} / {tytul}: {err}\n      {expr[:110]}")
    if LOKI:
        for plik, tytul, expr in loki:
            # UWAGA: Loki odrzuca zapytania LOGOWE jako instant
            # ("log queries are not supported as an instant query type"),
            # dlatego walidujemy je przez query_range — to NIE jest błąd zapytania.
            teraz = int(time.time() * 1_000_000_000)
            ok, err = zapytanie_ok(
                LOKI + "/loki/api/v1/query_range",
                {"query": expr, "start": str(teraz - 300_000_000_000), "end": str(teraz), "limit": "10"},
            )
            if not ok:
                bledy.append(f"LOGQL  {plik} / {tytul}: {err}\n      {expr[:110]}")

    print(f"  zapytań PromQL: {len(prom)} | LogQL: {len(loki)}")
    if bledy:
        for b in bledy:
            print(f"  ✗ {b}")
        return 1
    print("  ✓ wszystkie zapytania z dashboardów są poprawne składniowo")
    return 0


if __name__ == "__main__":
    sys.exit(main())
