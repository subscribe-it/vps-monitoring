#!/usr/bin/env python3
"""
discovery — automatyczne wykrywanie usług Docker Swarm dla stacku monitoringu.

Serwis czyta Docker Swarm API (WYŁĄCZNIE GET przez unix socket), parsuje trasy
Traefika z labeli usług, buduje listę celów dla Prometheus HTTP SD (blackbox),
wykonuje własne sondy HTTP/TLS i wystawia metryki Prometheusa oraz zagregowany
JSON dla panelu.

Zero zależności zewnętrznych — tylko biblioteka standardowa Pythona.
"""

from __future__ import annotations

import json
import math
import os
import re
import signal
import socket
import ssl
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

NAME = "discovery"
DEFAULT_PORT = 8080
DEFAULT_DOCKER_SOCKET = "/var/run/docker.sock"
DEFAULT_PROMETHEUS_URL = "http://prometheus:9090"
DEFAULT_ALERTMANAGER_URL = "http://alertmanager:9093"
DEFAULT_HEALTH_PING_URL = "http://health-ping:8080"
DEFAULT_MONITORING_DOMAIN = "monitoring.subscribeit.pl"

CERT_CACHE_TTL_SECONDS = 3600.0
PROM_CACHE_TTL_SECONDS = 10.0
JSON_BODY_LIMIT = 512 * 1024
READ_CHUNK = 65536

LABEL_SKIP = "monitoring.io/skip"
LABEL_PROBE = "monitoring.io/probe"
LABEL_HEALTH_PATH = "monitoring.io/health-path"
LABEL_SEVERITY = "monitoring.io/severity"
LABEL_MODULE = "monitoring.io/module"
LABEL_NAME = "monitoring.io/name"
LABEL_EXPECT = "monitoring.io/expect"
LABEL_APP = "monitoring.io/app"


# --------------------------------------------------------------------------
# Logowanie (stderr, prefiks [discovery])
# --------------------------------------------------------------------------
def log(msg, *args):
    if args:
        msg = msg % args
    sys.stderr.write("[%s] %s\n" % (NAME, msg))
    sys.stderr.flush()


def log_error(msg, *args):
    log("ERROR: " + (msg % args if args else msg))


# --------------------------------------------------------------------------
# Konfiguracja
# --------------------------------------------------------------------------
class ConfigError(RuntimeError):
    pass


class Config:
    """Konfiguracja czytana ze zmiennych środowiskowych."""

    def __init__(self, env=None):
        env = dict(os.environ if env is None else env)
        self.env = env
        self.docker_socket = _normalize_docker_host(env.get("DOCKER_HOST", ""))
        self.refresh_seconds = _env_float(env, "REFRESH_SECONDS", 30.0, minimum=1.0)
        self.skip_stacks = _env_csv(env, "SKIP_STACKS")
        self.skip_services = _env_csv(env, "SKIP_SERVICES")
        self.critical_stacks = set(_env_csv(env, "CRITICAL_STACKS"))
        self.warn_stacks = set(_env_csv(env, "WARN_STACKS"))
        self.default_probe_path = _normalize_path(env.get("DEFAULT_PROBE_PATH", ""))
        self.blackbox_module = (env.get("BLACKBOX_MODULE", "http_2xx") or "http_2xx").strip()
        self.probe_timeout = _env_float(env, "PROBE_TIMEOUT_SECONDS", 5.0, minimum=0.5)
        self.prometheus_url = (env.get("PROMETHEUS_URL", DEFAULT_PROMETHEUS_URL) or "").rstrip("/")
        self.alertmanager_url = (
            env.get("ALERTMANAGER_URL", DEFAULT_ALERTMANAGER_URL) or ""
        ).rstrip("/")
        self.health_ping_url = (env.get("HEALTH_PING_URL", DEFAULT_HEALTH_PING_URL) or "").rstrip("/")
        self.monitoring_domain = (
            env.get("MONITORING_DOMAIN", DEFAULT_MONITORING_DOMAIN) or ""
        ).strip()
        self.security_json_url = (env.get("SECURITY_JSON_URL", "") or "").strip()
        # Loki jest źródłem sekcji „Bezpieczeństwo", gdy nie ma zewnętrznego
        # JSON-a: promtail zbiera journald hosta, więc nieudane logowania SSH
        # są już w Loki (patrz `sekcja_z_loki`).
        self.loki_url = (env.get("LOKI_URL", "") or "").strip().rstrip("/")
        self.port = _env_int(env, "PORT", DEFAULT_PORT)

    @property
    def base_url(self):
        if not self.monitoring_domain:
            return ""
        return "https://" + self.monitoring_domain.rstrip("/")


def _env_float(env, key, default, minimum=None):
    raw = env.get(key, "")
    if raw is None or str(raw).strip() == "":
        return float(default)
    try:
        value = float(str(raw).strip())
    except (TypeError, ValueError):
        log("Ostrzeżenie: %s=%r nie jest liczbą, używam %s", key, raw, default)
        return float(default)
    if minimum is not None and value < minimum:
        log("Ostrzeżenie: %s=%s poniżej minimum %s, używam %s", key, value, minimum, minimum)
        return float(minimum)
    return value


def _env_int(env, key, default):
    return int(_env_float(env, key, default))


def _env_csv(env, key):
    raw = env.get(key, "") or ""
    return [item.strip() for item in str(raw).split(",") if item.strip()]


def _normalize_docker_host(raw):
    """Akceptujemy wyłącznie gniazdo unix — inne transporty są błędem."""
    value = (raw or "").strip()
    if not value:
        return DEFAULT_DOCKER_SOCKET
    if value.startswith("unix://"):
        path = value[len("unix://") :]
        return path or DEFAULT_DOCKER_SOCKET
    if value.startswith("/"):
        return value
    raise ConfigError(
        "DOCKER_HOST=%r nie jest obsługiwany: dozwolone jest wyłącznie gniazdo unix "
        "(np. unix:///var/run/docker.sock)" % value
    )


def _normalize_path(path):
    """'' i '/' -> ''; '/x/' -> '/x'; 'x' -> '/x'."""
    value = (path or "").strip()
    if not value or value == "/":
        return ""
    if not value.startswith("/"):
        value = "/" + value
    if len(value) > 1 and value.endswith("/"):
        value = value.rstrip("/")
    return value or ""


def iso_z(ts):
    """Unix timestamp -> 'YYYY-MM-DDTHH:MM:SSZ' (UTC)."""
    if ts is None:
        return None
    return datetime.fromtimestamp(float(ts), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_rfc3339(value):
    """RFC3339 (z nanosekundami) -> datetime UTC lub None."""
    if not value:
        return None
    text = str(value).strip()
    if text.endswith("Z") or text.endswith("z"):
        text = text[:-1] + "+00:00"
    match = re.match(r"^(.*\.\d{6})\d*(.*)$", text)
    if match:
        text = match.group(1) + match.group(2)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def format_latency_pl(seconds):
    """0.209 -> '0,21' (polski przecinek dziesiętny)."""
    return ("%.2f" % float(seconds)).replace(".", ",")


def as_list(value, what="dane"):
    """Zewnętrzne API może zwrócić cokolwiek — my chcemy listę albo nic."""
    if isinstance(value, list):
        return value
    if value is None:
        return []
    log("Ostrzeżenie: %s nie jest listą (%s) — pomijam", what, type(value).__name__)
    return []


def as_dict(value, what="dane"):
    if isinstance(value, dict):
        return value
    if value is None:
        return {}
    log("Ostrzeżenie: %s nie jest obiektem (%s) — pomijam", what, type(value).__name__)
    return {}


# --------------------------------------------------------------------------
# Proste klienty HTTP (stdlib, tylko GET)
# --------------------------------------------------------------------------
def http_get_json(url, timeout=5.0, headers=None):
    """GET + parsowanie JSON. Podnosi wyjątek przy błędzie."""
    request = urllib.request.Request(url, method="GET")
    request.add_header("Accept", "application/json")
    request.add_header("User-Agent", "monitoring-%s/1.0" % NAME)
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read(JSON_BODY_LIMIT)
    return json.loads(raw.decode("utf-8", "replace") or "null")


def http_get_text(url, timeout=5.0):
    """GET zwracający tekst (używane do /metrics discovery)."""
    request = urllib.request.Request(url, method="GET")
    request.add_header("User-Agent", "monitoring-%s/1.0" % NAME)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", "replace")


class ProbeResult:
    __slots__ = ("state", "status", "latency", "error")

    def __init__(self, state, status=None, latency=0.0, error=None):
        self.state = state  # ok | warning | critical | unknown
        self.status = status
        self.latency = float(latency or 0.0)
        self.error = error

    @property
    def success(self):
        return 1 if self.state == "ok" else 0

    def detail_pl(self):
        if self.status is None:
            return "Brak odpowiedzi (%s)" % (self.error or "nieznany błąd")
        if self.state == "ok":
            return "HTTP %d · %s s" % (self.status, format_latency_pl(self.latency))
        return "HTTP %d · %s s" % (self.status, format_latency_pl(self.latency))


def coerce_probe(value, url=""):
    """
    Zamienia cokolwiek w bezpieczny ProbeResult.

    Wynik sondy może pochodzić z wstrzykniętej funkcji albo z przyszłej zmiany —
    żadna sekcja api.json nie może się przez niego wywrócić.
    """
    if isinstance(value, ProbeResult):
        return value
    if value is None:
        return ProbeResult("unknown", None, 0.0, "brak danych sondy")
    state = getattr(value, "state", None)
    if state in ("ok", "warning", "critical", "unknown"):
        try:
            status = getattr(value, "status", None)
            latency = float(getattr(value, "latency", 0.0) or 0.0)
            error = getattr(value, "error", None)
        except (TypeError, ValueError):
            status, latency, error = None, 0.0, "nieprawidłowe dane sondy"
        return ProbeResult(state, status, latency, error)
    log(
        "Ostrzeżenie: nieoczekiwany wynik sondy (%s) dla %s — traktuję jako unknown",
        type(value).__name__, url or "-",
    )
    return ProbeResult("unknown", None, 0.0, "nieoczekiwany wynik sondy")


def _probe_ssl_context():
    """
    Bez weryfikacji łańcucha (self-signed certy nie mogą psuć sondy), ale
    handshake TLS MUSI się udać — odróżniamy 'cert wygasł' od 'nie ma TLS'.
    """
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context


def http_probe(url, timeout=5.0):
    """Własna sonda HTTP(S). 2xx/3xx -> ok, 401/403 -> ok, 4xx -> warning, 5xx -> critical."""
    request = urllib.request.Request(url, method="GET")
    request.add_header("User-Agent", "monitoring-%s/1.0" % NAME)
    request.add_header("Accept", "*/*")
    started = time.monotonic()
    try:
        with urllib.request.urlopen(
            request, timeout=timeout, context=_probe_ssl_context()
        ) as response:
            response.read(4096)
            status = int(getattr(response, "status", 0) or 0)
    except urllib.error.HTTPError as exc:
        status = int(exc.code or 0)
        try:
            exc.read(4096)
        except Exception:  # noqa: BLE001 - odczyt treści błędu jest best-effort
            pass
    except Exception as exc:  # noqa: BLE001 - każdy błąd sieci/TLS => critical
        latency = time.monotonic() - started
        return ProbeResult("critical", None, latency, "%s: %s" % (type(exc).__name__, exc))
    latency = time.monotonic() - started
    if 200 <= status < 400 or status in (401, 403):
        state = "ok"
    elif 400 <= status < 500:
        state = "warning"
    else:
        state = "critical"
    return ProbeResult(state, status, latency)


# --------------------------------------------------------------------------
# Docker API — wyłącznie GET przez unix socket, ręczne HTTP/1.1 + chunked
# --------------------------------------------------------------------------
class DockerError(RuntimeError):
    pass


def _split_http_response(raw):
    """(status, headers, body) z surowej odpowiedzi HTTP/1.1."""
    if not raw:
        raise DockerError("pusta odpowiedź z Docker API")
    index = raw.find(b"\r\n\r\n")
    separator = 4
    if index < 0:
        index = raw.find(b"\n\n")
        separator = 2
    if index < 0:
        raise DockerError("nieprawidłowa odpowiedź HTTP z Docker API (brak nagłówków)")
    head = raw[:index].decode("iso-8859-1", "replace")
    body = raw[index + separator :]
    lines = head.split("\n")
    status_line = lines[0].strip()
    parts = status_line.split(" ", 2)
    if len(parts) < 2 or not parts[1].isdigit():
        raise DockerError("nieprawidłowa linia statusu HTTP: %r" % status_line)
    status = int(parts[1])
    headers = {}
    for line in lines[1:]:
        line = line.strip("\r")
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        headers[key.strip().lower()] = value.strip()
    if headers.get("transfer-encoding", "").lower().find("chunked") >= 0:
        body = decode_chunked(body)
    return status, headers, body


def decode_chunked(body):
    """Dekodowanie Transfer-Encoding: chunked (Docker tak odpowiada na /logs)."""
    out = bytearray()
    pos = 0
    while True:
        end = body.find(b"\r\n", pos)
        if end < 0:
            break
        size_line = body[pos:end].split(b";")[0].strip()
        if not size_line:
            break
        try:
            size = int(size_line, 16)
        except ValueError as exc:
            raise DockerError("nieprawidłowy rozmiar chunku: %r" % size_line) from exc
        if size == 0:
            break
        start = end + 2
        out += body[start : start + size]
        pos = start + size + 2
    return bytes(out)


class DockerClient:
    """
    Minimalny klient Docker Engine API po unix socket.

    Cały ruch to GET — klasa nie posiada żadnej metody wysyłającej inną metodę
    HTTP (wymóg bezpieczeństwa: monitoring nie może modyfikować hosta).
    """

    def __init__(self, socket_path=DEFAULT_DOCKER_SOCKET, timeout=10.0, fetcher=None):
        self.socket_path = socket_path
        self.timeout = float(timeout)
        self._fetcher = fetcher  # wstrzykiwane w testach (path -> surowa odpowiedź)

    # -- transport ---------------------------------------------------------
    def _unix_get(self, path):
        """Surowa odpowiedź na GET <path> przez socket.AF_UNIX."""
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        try:
            sock.connect(self.socket_path)
            request = (
                "GET %s HTTP/1.1\r\n"
                "Host: docker\r\n"
                "Accept: application/json\r\n"
                "User-Agent: monitoring-%s/1.0\r\n"
                "Connection: close\r\n\r\n" % (path, NAME)
            )
            sock.sendall(request.encode("iso-8859-1"))
            chunks = []
            while True:
                data = sock.recv(READ_CHUNK)
                if not data:
                    break
                chunks.append(data)
            return b"".join(chunks)
        except OSError as exc:
            raise DockerError(
                "brak połączenia z Docker API (%s): %s" % (self.socket_path, exc)
            ) from exc
        finally:
            try:
                sock.close()
            except OSError:
                pass

    # -- API ---------------------------------------------------------------
    def get_raw(self, path):
        fetcher = self._fetcher or self._unix_get
        try:
            return fetcher(path)
        except DockerError:
            raise
        except Exception as exc:  # noqa: BLE001 - transport wstrzyknięty w testach
            raise DockerError("błąd transportu Docker API: %s" % exc) from exc

    def get_bytes(self, path):
        status, headers, body = _split_http_response(self.get_raw(path))
        if status >= 400:
            raise DockerError("Docker API zwróciło HTTP %d dla %s" % (status, path))
        return body

    def get_json(self, path):
        body = self.get_bytes(path)
        try:
            return json.loads(body.decode("utf-8", "replace") or "null")
        except ValueError as exc:
            raise DockerError("nieprawidłowy JSON z Docker API dla %s" % path) from exc

    # Wysokopoziomowe odczyty (wszystkie GET)
    def services(self):
        return self.get_json("/services") or []

    def tasks(self):
        return self.get_json("/tasks") or []

    def containers(self):
        return self.get_json("/containers/json?all=1") or []

    def container_inspect(self, container_id):
        return self.get_json("/containers/%s/json" % container_id) or {}

    def container_stats(self, container_id):
        return self.get_json("/containers/%s/stats?stream=false" % container_id) or {}

    def container_logs(self, container_id, tail=2000):
        return self.get_bytes(
            "/containers/%s/logs?stdout=1&stderr=1&tail=%d" % (container_id, int(tail))
        )

    def system_df(self):
        return self.get_json("/system/df") or {}


# --------------------------------------------------------------------------
# Parsowanie tras Traefika
# --------------------------------------------------------------------------
_QUOTED = r"""(?:`(?P<bt>[^`]*)`|'(?P<sq>[^']*)'|"(?P<dq>[^"]*)")"""
_HOST_RE = re.compile(r"Host\s*\(\s*" + _QUOTED + r"\s*\)", re.IGNORECASE)
_PATH_RE = re.compile(r"PathPrefix\s*\(\s*" + _QUOTED + r"\s*\)", re.IGNORECASE)
_ROUTER_RULE_RE = re.compile(r"^traefik\.http\.routers\.([^.]+)\.rule$")


def _quoted_value(match):
    if match is None:
        return ""
    return match.group("bt") or match.group("sq") or match.group("dq") or ""


def parse_traefik_rule(rule):
    """
    'Host(`a.pl`) && PathPrefix(`/x`)' -> ('a.pl', '/x')

    Obsługuje backticki, apostrofy i cudzysłowy. Zwraca None, gdy reguła nie
    zawiera Host(). Gdy nie ma PathPrefix — ścieżka jest pustą wartością.
    """
    if not rule:
        return None
    host_match = _HOST_RE.search(rule)
    if host_match is None:
        return None
    host = _quoted_value(host_match).strip()
    if not host:
        return None
    path_match = _PATH_RE.search(rule)
    path = _normalize_path(_quoted_value(path_match))
    return host, path


def router_rules(labels):
    """Lista (nazwa_routera, reguła) dla labeli traefik.http.routers.<r>.rule."""
    found = []
    for key, value in sorted((labels or {}).items()):
        match = _ROUTER_RULE_RE.match(key)
        if match:
            found.append((match.group(1), value))
    return found


def build_traefik_url(host, path):
    """https://<host><path>; przy pustej ścieżce sam host (bez końcowego slasha)."""
    base = "https://" + (host or "").strip()
    normalized = _normalize_path(path)
    return base + normalized if normalized else base


# --------------------------------------------------------------------------
# Klasyfikacja usług
# --------------------------------------------------------------------------
SEVERITY_RANK = {"skip": 0, "info": 1, "warning": 2, "critical": 3}
EXPECT_MODULE_MAP = {"200": "http_2xx", "401": "http_expect_auth"}
TASK_STATES = (
    "running",
    "failed",
    "rejected",
    "shutdown",
    "preparing",
    "starting",
    "complete",
    "other",
)


def split_stack_service(full_name):
    """'ventiplan-prod_api' -> ('ventiplan-prod', 'api')."""
    name = (full_name or "").strip()
    if "_" in name:
        stack, service = name.split("_", 1)
        return stack, service
    return name, name


def classify_severity(stack, labels, critical_stacks, warn_stacks):
    """label monitoring.io/severity > CRITICAL_STACKS > WARN_STACKS > warning."""
    labels = labels or {}
    raw = (labels.get(LABEL_SEVERITY) or "").strip().lower()
    if raw in SEVERITY_RANK:
        return raw
    if stack in (critical_stacks or ()):
        return "critical"
    if stack in (warn_stacks or ()):
        return "warning"
    return "warning"


def resolve_module(labels, default_module):
    """label module > mapowanie monitoring.io/expect > BLACKBOX_MODULE."""
    labels = labels or {}
    explicit = (labels.get(LABEL_MODULE) or "").strip()
    if explicit:
        return explicit
    expect = (labels.get(LABEL_EXPECT) or "").strip()
    if expect:
        code = re.split(r"[\s,;]+", expect)[0].strip()
        return EXPECT_MODULE_MAP.get(code, "http_alive")
    return (default_module or "http_2xx").strip() or "http_2xx"


def _is_true(value):
    return str(value or "").strip().lower() in ("1", "true", "yes", "tak", "on")


class Target:
    """Cel monitoringu (jeden URL do sondy i do HTTP SD)."""

    __slots__ = ("url", "host", "path", "stack", "service", "app", "module", "severity", "router")

    def __init__(self, url, host, path, stack, service, app, module, severity, router):
        self.url = url
        self.host = host
        self.path = path
        self.stack = stack
        self.service = service
        self.app = app
        self.module = module
        self.severity = severity
        self.router = router

    def sd_labels(self):
        """
        Etykiety HTTP SD. Zgodnie z ustaleniem ze stackiem wystawiamy OBA klucze:
        `module` (czytelny) oraz `__param_module` (parametr sondy dla Prometheusa).
        """
        return {
            "stack": self.stack,
            "service": self.service,
            "app": self.app,
            "module": self.module,
            "__param_module": self.module,
            "severity": self.severity,
            "source": "discovery",
        }


def build_targets(services, config):
    """
    Buduje cele monitoringu z listy usług Docker Swarm.

    Pomija: stacki z SKIP_STACKS, usługi z SKIP_SERVICES, traefik.enable=false,
    monitoring.io/skip=true oraz severity=skip.
    """
    targets = []
    skipped_services = 0
    for service in as_list(services, "GET /services"):
        if not isinstance(service, dict):
            continue
        spec = as_dict(service.get("Spec"), "Spec usługi")
        full_name = str(spec.get("Name") or "").strip()
        if not full_name:
            continue
        labels = as_dict(spec.get("Labels"), "Labels usługi")
        stack, service_name = split_stack_service(full_name)
        if stack in config.skip_stacks or full_name in config.skip_stacks:
            skipped_services += 1
            continue
        if full_name in config.skip_services or service_name in config.skip_services:
            skipped_services += 1
            continue
        if str(labels.get("traefik.enable", "")).strip().lower() == "false":
            skipped_services += 1
            continue
        if _is_true(labels.get(LABEL_SKIP)):
            skipped_services += 1
            continue
        severity = classify_severity(stack, labels, config.critical_stacks, config.warn_stacks)
        if severity == "skip":
            skipped_services += 1
            continue
        display_name = (labels.get(LABEL_NAME) or "").strip() or service_name
        app = (labels.get(LABEL_APP) or "").strip() or stack.split("-")[0] or display_name
        module = resolve_module(labels, config.blackbox_module)
        health_path = _normalize_path(labels.get(LABEL_HEALTH_PATH))
        probe_override = (labels.get(LABEL_PROBE) or "").strip()

        urls = []
        if probe_override:
            # monitoring.io/probe NADPISUJE adresy z reguł Traefika (nie dokłada kolejnego).
            parsed = urllib.parse.urlsplit(probe_override)
            urls.append(
                (
                    "monitoring.io/probe",
                    parsed.hostname or "",
                    parsed.path or "",
                    probe_override,
                )
            )
        else:
            for router, rule in router_rules(labels):
                parsed = parse_traefik_rule(rule)
                if parsed is None:
                    log("Pomijam router %s usługi %s: reguła bez Host() (%r)", router, full_name, rule)
                    continue
                host, path = parsed
                path = health_path or path or config.default_probe_path
                urls.append((router, host, path, build_traefik_url(host, path)))
        seen_urls = set()
        for router, host, path, url in urls:
            if url in seen_urls:
                continue
            seen_urls.add(url)
            targets.append(
                Target(url, host, _normalize_path(path), stack, display_name, app, module, severity, router)
            )
    if skipped_services:
        log("Pominięto %d usług (SKIP_* / monitoring.io/skip / traefik.enable=false)", skipped_services)
    return targets


# --------------------------------------------------------------------------
# Certyfikaty TLS (bez zależności zewnętrznych: PEM -> DER -> notAfter)
# --------------------------------------------------------------------------
def _der_read_tlv(buf, offset):
    """(tag, wartość, następny offset) dla jednego elementu DER."""
    if offset + 2 > len(buf):
        raise ValueError("obcięty nagłówek DER")
    tag = buf[offset]
    length = buf[offset + 1]
    offset += 2
    if length & 0x80:
        count = length & 0x7F
        if count == 0 or offset + count > len(buf):
            raise ValueError("nieprawidłowa długość DER")
        length = int.from_bytes(buf[offset : offset + count], "big")
        offset += count
    if offset + length > len(buf):
        raise ValueError("obcięta wartość DER")
    return tag, buf[offset : offset + length], offset + length


def _parse_asn1_time(tag, raw):
    text = raw.decode("ascii", "replace").strip()
    if text.endswith("Z"):
        text = text[:-1]
    if tag == 0x17:  # UTCTime YYMMDDHHMMSS
        if len(text) < 12:
            raise ValueError("nieprawidłowy UTCTime: %r" % text)
        year = int(text[0:2])
        year += 2000 if year < 50 else 1900
        rest = text[2:]
    elif tag == 0x18:  # GeneralizedTime YYYYMMDDHHMMSS
        if len(text) < 14:
            raise ValueError("nieprawidłowy GeneralizedTime: %r" % text)
        year = int(text[0:4])
        rest = text[4:]
    else:
        raise ValueError("oczekiwano czasu ASN.1, otrzymano tag 0x%02x" % tag)
    month, day = int(rest[0:2]), int(rest[2:4])
    hour, minute, second = int(rest[4:6]), int(rest[6:8]), int(rest[8:10])
    return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)


def parse_cert_not_after(der):
    """Wyciąga notAfter z DER certyfikatu X.509 (własny mini-parser ASN.1)."""
    tag, certificate, _ = _der_read_tlv(der, 0)
    if tag != 0x30:
        raise ValueError("to nie jest certyfikat X.509 (brak zewnętrznego SEQUENCE)")
    tag, tbs, _ = _der_read_tlv(certificate, 0)
    if tag != 0x30:
        raise ValueError("to nie jest certyfikat X.509 (brak TBSCertificate)")
    offset = 0
    fields = []
    while offset < len(tbs):
        field_tag, value, offset = _der_read_tlv(tbs, offset)
        fields.append((field_tag, value))
    for field_tag, value in fields:
        if field_tag != 0x30:
            continue
        inner = 0
        times = []
        valid = True
        while inner < len(value):
            try:
                time_tag, time_value, inner = _der_read_tlv(value, inner)
            except ValueError:
                valid = False
                break
            if time_tag not in (0x17, 0x18):
                valid = False
                break
            times.append((time_tag, time_value))
        if valid and len(times) == 2:
            return _parse_asn1_time(times[1][0], times[1][1])
    raise ValueError("nie znaleziono pola notAfter w certyfikacie")


def fetch_cert_not_after(host, port=443, timeout=5.0):
    """notAfter certyfikatu serwera (PEM -> DER -> data), bez weryfikacji łańcucha."""
    pem = ssl.get_server_certificate((host, port), timeout=timeout)
    der = ssl.PEM_cert_to_DER_cert(pem)
    return parse_cert_not_after(der)


def cert_state(days_left):
    """<7 dni -> critical, <14 -> warning, inaczej ok (spójne z CERT_MIN_DAYS=14)."""
    if days_left is None:
        return "unknown"
    if days_left < 7:
        return "critical"
    if days_left < 14:
        return "warning"
    return "ok"


# --------------------------------------------------------------------------
# Stan usługi: śledzenie nowych usług, zmian stanu, cache TTL
# --------------------------------------------------------------------------
class NewServiceTracker:
    """Liczy usługi widziane pierwszy raz w życiu tego procesu."""

    def __init__(self):
        self._seen = set()
        self._count = 0

    def observe(self, keys):
        new_keys = [key for key in keys if key not in self._seen]
        for key in new_keys:
            self._seen.add(key)
        self._count += len(new_keys)
        return self._count

    @property
    def count(self):
        return self._count

    @property
    def seen(self):
        return len(self._seen)


class StateTracker:
    """Zapamiętuje, od kiedy dany klucz ma ten sam stan (pole `since`)."""

    def __init__(self, clock=time.time):
        self._clock = clock
        self._states = {}

    def observe(self, key, state, now=None):
        now = self._clock() if now is None else now
        previous = self._states.get(key)
        if previous is None or previous[0] != state:
            self._states[key] = (state, now)
            return now
        return previous[1]

    def since(self, key):
        entry = self._states.get(key)
        return entry[1] if entry else None


class TTLCache:
    """Prosty cache z TTL (Prometheus: 10 s, certyfikaty: 1 h)."""

    def __init__(self, ttl, clock=time.time):
        self.ttl = float(ttl)
        self._clock = clock
        self._data = {}
        self._lock = threading.Lock()

    def get(self, key):
        with self._lock:
            entry = self._data.get(key)
        if entry is None:
            return None
        value, expires = entry
        if self._clock() >= expires:
            return None
        return value

    def set(self, key, value, ttl=None):
        with self._lock:
            self._data[key] = (value, self._clock() + (self.ttl if ttl is None else ttl))

    def get_or_set(self, key, factory, ttl=None):
        cached = self.get(key)
        if cached is not None:
            return cached, True
        value = factory()
        self.set(key, value, ttl)
        return value, False


# --------------------------------------------------------------------------
# Migawka stanu (wynik jednego cyklu odświeżania)
# --------------------------------------------------------------------------
class Snapshot:
    def __init__(self):
        self.up = False
        self.last_refresh = 0.0
        self.last_error = None
        self.refreshes = 0
        self.services = []          # list[dict]
        self.containers = []        # list[dict]
        self.targets = []           # list[Target]
        self.probes = {}            # url -> ProbeResult
        self.certs = {}             # host -> {"days_left": float, "expires_at": ts}
        self.df = {
            "images_reclaimable_bytes": 0,
            "volumes_reclaimable_bytes": 0,
            "containers_total": 0,
            "containers_running": 0,
        }
        self.new_services_total = 0
        self.stacks = {}


# --------------------------------------------------------------------------
# Równoległe wywołania (wyłącznie threading ze stdlib — bez pul zewnętrznych)
# --------------------------------------------------------------------------
def parallel_map(func, items, workers=8):
    """Zwraca listę wyników w kolejności `items`; wyjątek trafia jako wartość."""
    items = list(items)
    results = [None] * len(items)
    if not items:
        return results
    lock = threading.Lock()
    cursor = [0]

    def worker():
        while True:
            with lock:
                index = cursor[0]
                if index >= len(items):
                    return
                cursor[0] = index + 1
            try:
                results[index] = func(items[index])
            except Exception as exc:  # noqa: BLE001 - izolacja błędów per element
                results[index] = exc

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(max(1, min(workers, len(items))))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return results


# --------------------------------------------------------------------------
# Agregacje Docker Swarm
# --------------------------------------------------------------------------
def normalize_task_state(raw_state):
    state = str(raw_state or "").strip().lower()
    return state if state in TASK_STATES else "other"


def aggregate_tasks(tasks, now_ts, window_seconds=3600.0):
    """ServiceID -> {'states': {...}, 'running': n, 'failed_1h': n, 'last_state', 'last_error'}.

    `last_state`/`last_error` opisują NAJNOWSZE zadanie w stanie `failed` albo
    `rejected` — to jedyne miejsce, w którym Docker mówi WPROST, dlaczego usługa
    się przewraca („No such image: …”, „task: non-zero exit (137): dockerexec:
    unhealthy container”). Panel pokazuje to w szczegółach usługi, więc nie
    trzeba zgadywać przyczyny z liczby restartów. Brak danych => `None`.
    """
    stats = {}
    for task in as_list(tasks, "GET /tasks"):
        if not isinstance(task, dict):
            continue
        service_id = str(task.get("ServiceID") or "").strip()
        if not service_id:
            continue
        entry = stats.setdefault(
            service_id,
            {"states": {}, "running": 0, "failed_1h": 0,
             "last_state": None, "last_error": None, "last_error_at": 0.0},
        )
        status = task.get("Status") if isinstance(task.get("Status"), dict) else {}
        state = normalize_task_state(status.get("State"))
        entry["states"][state] = entry["states"].get(state, 0) + 1
        if state == "running":
            entry["running"] += 1
        desired = str(task.get("DesiredState") or "").strip().lower()
        created = parse_rfc3339(task.get("CreatedAt"))
        if desired == "running" and state != "running" and created is not None:
            age = now_ts - created.timestamp()
            if 0.0 <= age <= window_seconds:
                entry["failed_1h"] += 1
        if state in ("failed", "rejected"):
            # Kolejność: `UpdatedAt` jest świeższe niż `CreatedAt` (zadanie mogło
            # paść po restarcie kontenera), ale bierzemy to, co jest.
            znacznik_zmian = parse_rfc3339(task.get("UpdatedAt"))
            kiedy = znacznik_zmian or created
            znacznik = kiedy.timestamp() if kiedy is not None else 0.0
            if znacznik >= entry["last_error_at"]:
                # Puste i białe „błędy” traktujemy jak brak treści — panel ma
                # pokazać „brak danych”, a nie pusty prostokąt.
                blad = str(status.get("Err") or "").strip() or None
                entry["last_state"] = state
                entry["last_error"] = blad
                entry["last_error_at"] = znacznik
    return stats


def service_mode(spec):
    """'global' | 'global-job' | 'replicated' | 'replicated-job' | 'unknown'."""
    mode = (spec or {}).get("Mode") or {}
    for key, value in (
        ("Global", "global"),
        ("GlobalJob", "global-job"),
        ("ReplicatedJob", "replicated-job"),
        ("Replicated", "replicated"),
    ):
        if key in mode:
            return value
    return "unknown"


def desired_replicas(spec, running_tasks):
    """
    Replicated -> Spec.Mode.Replicated.Replicas.

    Global / *Job -> liczba aktualnie działających zadań. Usługi globalne nie mają
    zadeklarowanej liczby replik, więc desired=0 dawałoby fałszywe „0/0" w panelu
    (portainer_agent, promtail, node-exporter).
    """
    if service_mode(spec) == "replicated":
        replicated = ((spec or {}).get("Mode") or {}).get("Replicated") or {}
        try:
            return max(0, int(replicated.get("Replicas", 0) or 0))
        except (TypeError, ValueError):
            return 0
    return int(running_tasks or 0)


def service_limits(task_template):
    """Limity zasobów z spec usługi Swarm: `(rdzenie CPU, bajty RAM)`.

    Źródło: `Spec.TaskTemplate.Resources.Limits` — `NanoCPUs` (1e9 = 1 vCPU)
    i `MemoryBytes`. Panel potrzebuje ich, żeby pokazać „teraz vs limit":
    wcześniej limitów nie było w API, a metryki znają wyłącznie limit RAM
    (z `docker stats`) — limit CPU nie miał żadnego źródła.

    Brak limitu zwracamy jako `None`, a NIE jako 0 — inaczej panel pokazałby
    „0,00 vCPU" i liczył procent z zera. Usługi bez limitów (cudze stacki)
    są normą, więc to nie jest przypadek brzegowy.
    """
    zasoby = as_dict(
        as_dict(as_dict(task_template, "TaskTemplate").get("Resources"), "Resources usługi").get("Limits"),
        "Limits usługi",
    )
    nano = zasoby.get("NanoCPUs")
    pamiec = zasoby.get("MemoryBytes")
    cpu = None
    if isinstance(nano, (int, float)) and not isinstance(nano, bool) and nano > 0:
        cpu = float(nano) / 1_000_000_000
    mem = None
    if isinstance(pamiec, (int, float)) and not isinstance(pamiec, bool) and pamiec > 0:
        mem = int(pamiec)
    return cpu, mem


def compute_cpu_percent(stats):
    """Dokładnie jak Docker: (cpu_delta / system_delta) * online_cpus * 100."""
    stats = stats or {}
    cpu = stats.get("cpu_stats") or {}
    previous = stats.get("precpu_stats") or {}
    usage = (cpu.get("cpu_usage") or {}).get("total_usage") or 0
    previous_usage = (previous.get("cpu_usage") or {}).get("total_usage") or 0
    system = cpu.get("system_cpu_usage")
    previous_system = previous.get("system_cpu_usage")
    if not system or not previous_system:
        return 0.0
    cpu_delta = usage - previous_usage
    system_delta = system - previous_system
    if cpu_delta <= 0 or system_delta <= 0:
        return 0.0
    online_cpus = cpu.get("online_cpus") or len((cpu.get("cpu_usage") or {}).get("percpu_usage") or [])
    if not online_cpus:
        online_cpus = 1
    return (cpu_delta / system_delta) * float(online_cpus) * 100.0


def container_memory(stats):
    memory = ((stats or {}).get("memory_stats") or {})
    return float(memory.get("usage") or 0), float(memory.get("limit") or 0)


def container_network(stats):
    """Suma ruchu ze wszystkich interfejsów kontenera (liczniki narastające).

    Docker podaje `networks.<iface>.rx_bytes/tx_bytes` — to liczniki, więc
    w Prometheusie liczymy z nich `rate()`, żeby pokazać ruch w B/s.
    """
    rx = tx = 0.0
    for interfejs in ((stats or {}).get("networks") or {}).values():
        rx += float((interfejs or {}).get("rx_bytes") or 0)
        tx += float((interfejs or {}).get("tx_bytes") or 0)
    return rx, tx


def container_blockio(stats):
    """Odczyt/zapis dysku kontenera (liczniki narastające, z blkio_stats)."""
    odczyt = zapis = 0.0
    for wpis in (((stats or {}).get("blkio_stats") or {}).get("io_service_bytes_recursive") or []):
        operacja = str((wpis or {}).get("op") or "").lower()
        wartosc = float((wpis or {}).get("value") or 0)
        if operacja == "read":
            odczyt += wartosc
        elif operacja == "write":
            zapis += wartosc
    return odczyt, zapis


def docker_df_summary(raw_df):
    """
    Obrazy: suma Size dla obrazów nieużywanych (Images[].Containers == 0).
    Gdy Docker nie zwraca flagi Containers — fallback na LayersSize.
    BuildCache jest odczytywany, ale nieeksponowany (specyfikacja nie podaje
    nazwy metryki); dostępny w logach diagnostycznych.
    """
    raw_df = as_dict(raw_df, "GET /system/df")
    images = as_list(raw_df.get("Images"), "Images")
    reclaimable = 0
    saw_flag = False
    for image in images:
        if not isinstance(image, dict):
            continue
        flag = image.get("Containers", None)
        if flag is None:
            continue
        saw_flag = True
        try:
            in_use = int(flag)
        except (TypeError, ValueError):
            in_use = -1
        if in_use <= 0:
            reclaimable += int(image.get("Size") or 0)
    if not saw_flag:
        try:
            reclaimable = int(raw_df.get("LayersSize") or 0)
        except (TypeError, ValueError):
            reclaimable = 0
    volumes_reclaimable = 0
    for volume in as_list(raw_df.get("Volumes"), "Volumes"):
        if not isinstance(volume, dict):
            continue
        usage = as_dict(volume.get("UsageData"), "UsageData wolumenu")
        try:
            ref_count = int(usage.get("RefCount") or 0)
        except (TypeError, ValueError):
            ref_count = 0
        if ref_count == 0:
            try:
                volumes_reclaimable += int(usage.get("Size") or 0)
            except (TypeError, ValueError):
                continue
    build_cache = 0
    for entry in as_list(raw_df.get("BuildCache"), "BuildCache"):
        if isinstance(entry, dict):
            try:
                build_cache += int(entry.get("Size") or 0)
            except (TypeError, ValueError):
                continue
    if build_cache:
        log("BuildCache na dysku: %d B (nieeksponowane w metrykach)", build_cache)
    return {
        "images_reclaimable_bytes": reclaimable,
        "volumes_reclaimable_bytes": volumes_reclaimable,
    }


def container_identity(labels):
    """(stack, service) z labeli kontenera Swarm."""
    if not isinstance(labels, dict):
        return None, None
    full_name = str(labels.get("com.docker.swarm.service.name") or "").strip()
    full_name = re.sub(r"\.\d+\.[a-z0-9]+$", "", full_name)
    if not full_name:
        return None, None
    stack = str(labels.get("com.docker.swarm.stack.namespace") or "").strip()
    derived_stack, service = split_stack_service(full_name)
    return (stack or derived_stack), service


# --------------------------------------------------------------------------
# Ekspozycja metryk Prometheusa
# --------------------------------------------------------------------------
METRIC_FAMILIES = (
    ("swarm_service_desired_replicas", "gauge", "Liczba pożądanych replik usługi Swarm."),
    ("swarm_service_running_replicas", "gauge", "Liczba działających replik usługi Swarm."),
    ("swarm_service_tasks", "gauge", "Liczba zadań usługi w danym stanie."),
    ("swarm_service_failed_tasks_1h", "gauge", "Zadania nieuruchomione w ostatniej godzinie przy DesiredState=running."),
    ("swarm_service_info", "gauge", "Informacje o usłudze (zawsze 1)."),
    ("swarm_service_updated_at", "gauge", "Czas ostatniej aktualizacji usługi (unix)."),
    ("swarm_container_cpu_percent", "gauge", "Zużycie CPU kontenera w procentach."),
    ("swarm_container_memory_bytes", "gauge", "Zużycie RAM kontenera w bajtach."),
    ("swarm_container_memory_limit_bytes", "gauge", "Limit RAM kontenera w bajtach."),
    ("swarm_container_health", "gauge", "Stan healthchecku kontenera (zawsze 1)."),
    ("swarm_container_network_receive_bytes_total", "counter",
     "Odebrane bajty przez interfejsy kontenera (licznik narastający)."),
    ("swarm_container_network_transmit_bytes_total", "counter",
     "Wysłane bajty przez interfejsy kontenera (licznik narastający)."),
    ("swarm_container_block_read_bytes_total", "counter",
     "Bajty odczytane z dysku przez kontener (licznik narastający)."),
    ("swarm_container_block_write_bytes_total", "counter",
     "Bajty zapisane na dysk przez kontener (licznik narastający)."),
    ("discovery_probe_success", "gauge", "Wynik własnej sondy HTTP (1 = ok)."),
    ("discovery_probe_latency_seconds", "gauge", "Czas odpowiedzi własnej sondy HTTP."),
    ("discovery_cert_days_left", "gauge", "Dni do wygaśnięcia certyfikatu TLS hosta."),
    ("discovery_http_targets", "gauge", "Liczba celów HTTP przekazanych do Prometeusza."),
    ("discovery_stacks", "gauge", "Liczba wykrytych stacków."),
    ("discovery_services", "gauge", "Liczba wykrytych usług."),
    ("discovery_up", "gauge", "Czy ostatnie odświeżenie discovery się powiodło."),
    ("discovery_last_refresh_timestamp_seconds", "gauge", "Czas ostatniego odświeżenia (unix)."),
    ("discovery_new_services_total", "counter", "Usługi zobaczone pierwszy raz w tym procesie."),
    ("docker_images_reclaimable_bytes", "gauge", "Miejsce możliwe do odzyskania z nieużywanych obrazów."),
    ("docker_volumes_reclaimable_bytes", "gauge", "Miejsce możliwe do odzyskania z nieużywanych wolumenów."),
    ("docker_containers", "gauge", "Liczba wszystkich kontenerów."),
    ("docker_containers_running", "gauge", "Liczba działających kontenerów."),
)


def escape_label_value(value):
    """Escaping etykiet Prometheusa: backslash, cudzysłów, newline."""
    text = "" if value is None else str(value)
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def labels_str(labels):
    if not labels:
        return ""
    parts = ['%s="%s"' % (key, escape_label_value(labels[key])) for key in sorted(labels)]
    return "{" + ",".join(parts) + "}"


def fmt_value(value):
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "0"
    if not math.isfinite(number):
        return "0"
    if number == int(number) and abs(number) < 1e15:
        return str(int(number))
    return repr(round(number, 6))


def render_metrics(snapshot):
    """Czysta funkcja: migawka -> tekst exposition Prometheusa."""
    samples = []

    def add(name, labels, value):
        samples.append((name, labels, value))

    # Usługi oznaczone jako `skip` nie trafiają do metryk — inaczej powstałyby
    # alerty o czymś, czego użytkownik świadomie nie chce monitorować.
    severity_by_service = {}
    for service in snapshot.services:
        severity_by_service[(service["stack"], service["service"])] = service.get("severity") or "warning"
    monitorowane = [s for s in snapshot.services if (s.get("severity") or "warning") != "skip"]

    for service in monitorowane:
        base = {
            "stack": service["stack"],
            "service": service["service"],
            "severity": severity_by_service.get((service["stack"], service["service"]), "warning"),
        }
        add("swarm_service_desired_replicas", base, service["desired"])
        add("swarm_service_running_replicas", base, service["running"])
        states = dict(service.get("states") or {})
        states.setdefault("running", 0)
        for state in TASK_STATES:
            if state in states:
                add(
                    "swarm_service_tasks",
                    dict(base, state=state),
                    states[state],
                )
        add("swarm_service_failed_tasks_1h", base, service["failed_1h"])
        add("swarm_service_info", dict(base, image=service.get("image") or ""), 1)
        add("swarm_service_updated_at", base, service.get("updated_at") or 0)
    for container in snapshot.containers:
        sev = severity_by_service.get((container["stack"], container["service"]), "warning")
        if sev == "skip":
            continue
        base = {
            "stack": container["stack"],
            "service": container["service"],
            "container": container["container"],
            "severity": sev,
        }
        add("swarm_container_cpu_percent", base, round(container.get("cpu") or 0.0, 4))
        add("swarm_container_memory_bytes", base, container.get("mem") or 0)
        add("swarm_container_memory_limit_bytes", base, container.get("mem_limit") or 0)
        add("swarm_container_health", dict(base, health=container.get("health") or "none"), 1)
        add("swarm_container_network_receive_bytes_total", base, container.get("net_rx") or 0)
        add("swarm_container_network_transmit_bytes_total", base, container.get("net_tx") or 0)
        add("swarm_container_block_read_bytes_total", base, container.get("blk_read") or 0)
        add("swarm_container_block_write_bytes_total", base, container.get("blk_write") or 0)
    for target in snapshot.targets:
        if target.severity == "skip":
            continue
        probe = coerce_probe(snapshot.probes.get(target.url), target.url)
        base = {"stack": target.stack, "service": target.service, "url": target.url}
        add("discovery_probe_success", base, probe.success)
        add("discovery_probe_latency_seconds", base, round(probe.latency, 6))
    for host in sorted(snapshot.certs):
        info = snapshot.certs[host]
        days_left = finite(info.get("days_left")) if isinstance(info, dict) else 0.0
        add("discovery_cert_days_left", {"host": host}, days_left)
    add("discovery_http_targets", {}, len([t for t in snapshot.targets if t.severity != "skip"]))
    add("discovery_stacks", {}, len(snapshot.stacks))
    add("discovery_services", {}, len(snapshot.services))
    add("discovery_up", {}, 1 if snapshot.up else 0)
    add("discovery_last_refresh_timestamp_seconds", {}, snapshot.last_refresh)
    add("discovery_new_services_total", {}, snapshot.new_services_total)
    add("docker_images_reclaimable_bytes", {}, snapshot.df.get("images_reclaimable_bytes", 0))
    add("docker_volumes_reclaimable_bytes", {}, snapshot.df.get("volumes_reclaimable_bytes", 0))
    add("docker_containers", {}, snapshot.df.get("containers_total", 0))
    add("docker_containers_running", {}, snapshot.df.get("containers_running", 0))

    grouped = {}
    for name, labels, value in samples:
        grouped.setdefault(name, []).append((labels, value))
    known = [family[0] for family in METRIC_FAMILIES]
    lines = []
    for name, metric_type, help_text in METRIC_FAMILIES:
        lines.append("# HELP %s %s" % (name, help_text))
        lines.append("# TYPE %s %s" % (name, metric_type))
        for labels, value in grouped.get(name, []):
            lines.append("%s%s %s" % (name, labels_str(labels), fmt_value(value)))
    for name in sorted(set(grouped) - set(known)):
        lines.append("# TYPE %s gauge" % name)
        for labels, value in grouped[name]:
            lines.append("%s%s %s" % (name, labels_str(labels), fmt_value(value)))
    return "\n".join(lines) + "\n"


def slugify(value, max_len=80):
    slug = re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-")
    return (slug[:max_len].strip("-") or "check")


def finite(value, default=0.0):
    """Bezpieczna konwersja na skończoną liczbę (Prometheus potrafi zwrócić NaN/Inf)."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return float(default)
    return number if math.isfinite(number) else float(default)


def empty_host(now_ts):
    """Sekcja `host` z zerami — używana, gdy Prometheus nie odpowiada."""
    return {
        "cpu_percent": 0,
        "load1": 0,
        "load5": 0,
        "load15": 0,
        "mem_total_bytes": 0,
        "mem_used_bytes": 0,
        "mem_used_percent": 0,
        "swap_total_bytes": 0,
        "disk_total_bytes": 0,
        "disk_used_bytes": 0,
        "disk_used_percent": 0,
        "inodes_used_percent": 0,
        "uptime_seconds": 0,
        "time_utc": iso_z(now_ts),
    }


def empty_backup():
    return {
        "state": "unknown",
        "last_success_at": None,
        "age_hours": None,
        "size_bytes": 0,
        "objects_in_r2": 0,
        "restore_test_days": 0,
    }


def empty_security():
    # Liczniki jako None, a nie 0: „nie wiem" nie może wyglądać jak „zero
    # zdarzeń". Panel renderuje None jako „—" (fmtInt w panel/src/lib/status.ts).
    return {"ssh_failed_24h": None, "ssh_bans_24h": None, "logins_24h": [], "state": "unknown"}


# --- sekcja „Bezpieczeństwo" z Loki ----------------------------------------
# Skąd dane: promtail zbiera journald hosta (config/promtail/promtail-config.yaml),
# więc próby logowania SSH są już w Loki — nie trzeba osobnego agenta na hoście.
# Zmierzone na produkcji 22.09.2026: w 24 h 203 linie „Failed password" i 44
# „Accepted", a jednostka systemd to `ssh.service` (nie `ssh`). fail2ban pisze
# do journala tylko start/stop („Server ready", „Shutdown successful"), więc
# liczby banów z journala nie da się policzyć — zostaje None, a panel pokazuje
# „—" zamiast fałszywego zera.
LOKI_SSH = 'unit="ssh.service"'
LOKI_FAIL2BAN = 'unit="fail2ban.service"'
LOKI_LICZNIKI = (
    ("ssh_failed_24h",
     'sum(count_over_time({job="journald", %s} |= "Failed password" [24h]))' % LOKI_SSH),
    ("ssh_bans_24h",
     'sum(count_over_time({job="journald", %s} |~ "(?i)ban" [24h]))' % LOKI_FAIL2BAN),
)
LOKI_LOGINY = '{job="journald", %s} |= "Accepted"' % LOKI_SSH
LOKI_LOGIN_WZORZEC = re.compile(
    r"Accepted (?P<metoda>\S+) for (?P<uzytkownik>\S+) from (?P<ip>\S+) port (?P<port>\d+)"
)


def sekcja_z_loki(loki_url, json_get, limit_logowan=20, teraz=None):
    """Buduje sekcję `security` z Loki. Zwraca None, gdy Loki nie odpowiedziało."""
    teraz = time.time() if teraz is None else teraz
    sekcja = {"ssh_failed_24h": None, "ssh_bans_24h": None, "logins_24h": [], "state": "unknown"}
    odpowiedzialo = False

    for klucz, zapytanie in LOKI_LICZNIKI:
        adres = "%s/loki/api/v1/query?%s" % (
            loki_url, urllib.parse.urlencode({"query": zapytanie, "time": "%.0f" % teraz}),
        )
        try:
            dane = json_get(adres, timeout=5.0)
        except Exception as wyjatek:  # noqa: BLE001 - brak Loki => licznik zostaje None
            log("Loki nie odpowiedziało na %s (%s)", klucz, wyjatek)
            continue
        odpowiedzialo = True
        wynik = ((dane or {}).get("data") or {}).get("result") or []
        if not wynik:
            continue
        try:
            sekcja[klucz] = int(float(wynik[0]["value"][1]))
        except (KeyError, IndexError, TypeError, ValueError):
            log("Loki: nieoczekiwany kształt odpowiedzi dla %s", klucz)

    koniec_ns = int(teraz * 1e9)
    adres = "%s/loki/api/v1/query_range?%s" % (
        loki_url,
        urllib.parse.urlencode({
            "query": LOKI_LOGINY,
            "start": str(koniec_ns - 24 * 3600 * 10**9),
            "end": str(koniec_ns),
            "limit": str(limit_logowan),
            "direction": "backward",
        }),
    )
    try:
        dane = json_get(adres, timeout=5.0)
    except Exception as wyjatek:  # noqa: BLE001
        log("Loki nie odpowiedziało na listę logowań (%s)", wyjatek)
    else:
        odpowiedzialo = True
        for strumien in ((dane or {}).get("data") or {}).get("result") or []:
            for znacznik, linia in strumien.get("values") or []:
                dopasowanie = LOKI_LOGIN_WZORZEC.search(linia or "")
                if not dopasowanie:
                    continue
                sekcja["logins_24h"].append({
                    "service": dopasowanie.group("uzytkownik"),
                    "ip": dopasowanie.group("ip"),
                    "method": dopasowanie.group("metoda"),
                    "at": iso_z(float(znacznik) / 1e9),
                })

    if not odpowiedzialo:
        return None
    sekcja["state"] = "ok"
    return sekcja


# --------------------------------------------------------------------------
# Narzędzia pokazywane w panelu
# --------------------------------------------------------------------------
TOOLS = (
    {"id": "status", "name": "Stan usług", "url": None, "embed": False, "kind": "internal",
     "icon": "activity", "description": "Przegląd stanu usług, certyfikatów i backupu"},
    # Grafana w ramce panelu dostaje `?kiosk`, czyli bez własnego paska
    # nawigacji. Zmierzone na produkcji przy ramce 2504 px: bez `kiosk`
    # siatka dashboardu miała 2062 px, bo 319 px zabierało menu Grafany;
    # z `kiosk` rośnie do 2448 px (panel nie musi znać specyfiki narzędzi —
    # parametr jedzie z API jako `embed_query`).
    {"id": "grafana", "name": "Grafana", "url": "/grafana", "embed": True, "kind": "internal",
     "embed_query": "kiosk", "icon": "chart-line", "description": "Dashboardy i logi"},
    {"id": "prometheus", "name": "Prometheus", "url": "/prometheus", "embed": True, "kind": "internal",
     "icon": "chart-area", "description": "Metryki i zapytania PromQL"},
    {"id": "alertmanager", "name": "Alertmanager", "url": "/alertmanager", "embed": True, "kind": "internal",
     "icon": "bell", "description": "Aktywne alerty i wyciszenia"},
    {"id": "healthchecks", "name": "healthchecks.io", "url": "https://healthchecks.io/checks", "embed": False,
     "kind": "external", "icon": "heart-pulse", "description": "Zewnętrzny watchdog (dead-man's switch)"},
    {"id": "portainer", "name": "Portainer", "url": "https://portainer.subscribeit.pl", "embed": False,
     "kind": "external", "icon": "server", "description": "Zarządzanie kontenerami"},
    {"id": "cockpit", "name": "Cockpit", "url": "https://57.129.41.248:9090", "embed": False,
     "kind": "external", "icon": "terminal", "description": "Panel hosta"},
)

HOST_QUERIES = {
    "cpu_percent": '100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)',
    "load1": "node_load1",
    "load5": "node_load5",
    "load15": "node_load15",
    "mem_available_bytes": "node_memory_MemAvailable_bytes",
    "mem_total_bytes": "node_memory_MemTotal_bytes",
    "swap_total_bytes": "node_memory_SwapTotal_bytes",
    "fs_avail_bytes": 'node_filesystem_avail_bytes{mountpoint="/"}',
    "fs_size_bytes": 'node_filesystem_size_bytes{mountpoint="/"}',
    "files_free": 'node_filesystem_files_free{mountpoint="/"}',
    "files_total": 'node_filesystem_files{mountpoint="/"}',
    "uptime_seconds": "time() - node_boot_time_seconds",
}


# --------------------------------------------------------------------------
# Serwis
# --------------------------------------------------------------------------
# --------------------------------------------------------------------------
# Logi z Loki dla panelu (`/status/logs`)
# --------------------------------------------------------------------------
# Po co proxy w tej usłudze, a nie bezpośrednio z przeglądarki do Loki:
# 1. panel nie musi znać LogQL — wysyła parametry strukturalne (stack, usługa,
#    źródło, zakres), a zapytanie buduje serwer, więc **tekst użytkownika nigdy
#    nie trafia do zapytania** (żadnego wstrzykiwania/regexów w LogQL),
# 2. działa niezależnie od tego, czy edge wystawia `/loki` na tym samym
#    originie (trasy nie dało się potwierdzić z zewnątrz: ForwardAuth zwraca 401
#    na każdą ścieżkę), a `/status/*` jest trasowane na pewno — panel już z niego
#    czyta stan,
# 3. odpowiedź jest przycięta do tego, co panel pokazuje (czas, treść, strumień).
LOGI_ZAKRESY = {"15m": 900, "1h": 3600, "24h": 86400}
LOGI_ZAKRES_DOMYSLNY = "1h"
LOGI_LIMITY = (200, 500, 1000)
LOGI_LIMIT_DOMYSLNY = 200
LOGI_ZRODLA = ("usluga", "host", "traefik")


def _bezpieczna_etykieta(wartosc):
    """Czyści wartość do użycia w selektorze LogQL.

    Nazwy usług/stacków pochodzą z Dockera, ale nie ufamy im bezgranicznie:
    cudzysłów albo backslash w nazwie rozjechałby selektor (albo pozwolił
    dopisać własny warunek). Zostawiamy wyłącznie znaki legalne w nazwach.
    """
    return re.sub(r"[^A-Za-z0-9_.:/-]", "", str(wartosc or "")).strip()


def logi_zapytanie(zrodlo, stack, usluga):
    """Buduje selektor LogQL z parametrów strukturalnych (patrz komentarz wyżej)."""
    zrodlo = zrodlo if zrodlo in LOGI_ZRODLA else "usluga"
    if zrodlo == "host":
        return '{job="journald", unit=~".+"}'
    if zrodlo == "traefik":
        return '{job="traefik"}'
    stack_czysty = _bezpieczna_etykieta(stack)
    usluga_czysta = _bezpieczna_etykieta(usluga)
    if not stack_czysty or not usluga_czysta:
        return None
    # Etykieta `service` w Loki ma PREFIKS stacka — tak ustawia ją promtail
    # z `com.docker.swarm.service.name`.
    return '{job="docker", stack="%s", service="%s_%s"}' % (stack_czysty, stack_czysty, usluga_czysta)


def logi_parametry(zapytanie):
    """Waliduje parametry żądania `/status/logs` (śmieci => wartości domyślne)."""
    def jeden(klucz, dozwolone, domyslna):
        wartosc = (zapytanie.get(klucz) or [""])[0].strip()
        return wartosc if wartosc in dozwolone else domyslna

    try:
        limit = int((zapytanie.get("limit") or [""])[0])
    except (TypeError, ValueError):
        limit = LOGI_LIMIT_DOMYSLNY
    return {
        "zrodlo": jeden("zrodlo", LOGI_ZRODLA, "usluga"),
        "zakres": jeden("zakres", LOGI_ZAKRESY.keys(), LOGI_ZAKRES_DOMYSLNY),
        "limit": limit if limit in LOGI_LIMITY else LOGI_LIMIT_DOMYSLNY,
        "stack": (zapytanie.get("stack") or [""])[0].strip(),
        "usluga": (zapytanie.get("usluga") or [""])[0].strip(),
    }


class DiscoveryService:
    def __init__(self, config, docker=None, probe_fn=None, json_get=None, cert_fn=None, clock=time.time):
        self.config = config
        self.docker = docker if docker is not None else DockerClient(config.docker_socket)
        self.probe_fn = probe_fn or http_probe
        self.json_get = json_get or http_get_json
        if cert_fn is None:
            timeout = config.probe_timeout
            cert_fn = lambda host: fetch_cert_not_after(host, 443, timeout)  # noqa: E731
        self.cert_fn = cert_fn
        self.clock = clock
        self.snapshot = Snapshot()
        self.tracker = NewServiceTracker()
        self.check_since = StateTracker(clock)
        self.cert_cache = TTLCache(CERT_CACHE_TTL_SECONDS, clock)
        self.prom_cache = TTLCache(PROM_CACHE_TTL_SECONDS, clock)
        self.tool_cache = TTLCache(PROM_CACHE_TTL_SECONDS, clock)
        self._lock = threading.Lock()

    # -- stan --------------------------------------------------------------
    def snapshot_view(self):
        with self._lock:
            return self.snapshot

    def run(self, stop_event):
        while not stop_event.is_set():
            try:
                self.refresh()
            except Exception as exc:  # noqa: BLE001 - pętla nie może umrzeć
                log_error("Nieoczekiwany błąd odświeżania: %s", exc)
            stop_event.wait(self.config.refresh_seconds)

    # -- odświeżanie -------------------------------------------------------

    # `/system/df` to najdroższe wywołanie Dockera: przechodzi warstwy obrazów,
    # wolumeny i wszystkie kontenery. Zmierzone na produkcji (79 kontenerów,
    # 45 działających): wołane co 30 s trzymało dockerd tak zajęty, że sama lista
    # kontenerów przez API Portainera odpowiadała po 20–30 s, a Portainer — który
    # stoi na tym samym daemonie — „nie odpowiadał”. Metryki liczone z `df`
    # (obrazy/wolumeny do odzyskania, liczniki kontenerów) nie potrzebują
    # świeżości 30 s, więc trzymamy je w cache.
    SYSTEM_DF_TTL_SECONDS = 600
    SYSTEM_DF_RETRY_SECONDS = 60

    def system_df_cached(self):
        teraz = self.clock()
        zapis = getattr(self, "_df_cache", None)
        if zapis is not None:
            ttl = self.SYSTEM_DF_TTL_SECONDS if zapis[2] else self.SYSTEM_DF_RETRY_SECONDS
            if teraz - zapis[0] < ttl:
                return zapis[1]
        try:
            raw = as_dict(self.docker.system_df(), "GET /system/df")
            self._df_cache = (teraz, raw, True)
            return raw
        except Exception as exc:  # noqa: BLE001 - brak `df` nie może psuć odświeżenia
            log("Nie udało się odczytać /system/df (%s) — zostaje poprzedni pomiar", exc)
            poprzedni = zapis[1] if zapis else {}
            self._df_cache = (teraz, poprzedni, False)
            return poprzedni

    def refresh(self):
        try:
            raw_services = as_list(self.docker.services(), "GET /services")
            raw_tasks = as_list(self.docker.tasks(), "GET /tasks")
            raw_containers = as_list(self.docker.containers(), "GET /containers/json?all=1")
            raw_df = self.system_df_cached()
        except Exception as exc:  # noqa: BLE001 - brak Dockera nie może wywalić serwisu
            log_error("Odświeżenie nie powiodło się: %s", exc)
            with self._lock:
                self.snapshot.up = False
                self.snapshot.last_error = "%s: %s" % (type(exc).__name__, exc)
                self.snapshot.last_refresh = self.clock()
            return False

        now = self.clock()
        snapshot = Snapshot()
        task_stats = aggregate_tasks(raw_tasks, now)

        for raw in raw_services:
            if not isinstance(raw, dict):
                log("Ostrzeżenie: pomijam wpis usługi, który nie jest obiektem (%s)", type(raw).__name__)
                continue
            spec = as_dict(raw.get("Spec"), "Spec usługi")
            full_name = str(spec.get("Name") or "").strip()
            if not full_name:
                continue
            labels = as_dict(spec.get("Labels"), "Labels usługi")
            stats = task_stats.get(raw.get("ID") or "", {"states": {}, "running": 0, "failed_1h": 0})
            stack, service_name = split_stack_service(full_name)
            task_template = as_dict(spec.get("TaskTemplate"), "TaskTemplate")
            container_spec = as_dict(task_template.get("ContainerSpec"), "ContainerSpec")
            updated = parse_rfc3339(raw.get("UpdatedAt"))
            entry = {
                "id": raw.get("ID") or "",
                "full_name": full_name,
                "stack": stack,
                "service": service_name,
                "labels": labels,
                # Poziom istotności jedzie ZARÓWNO do sond (HTTP SD), jak i do metryk
                # replik — bez tego alert o zejściu produkcji z N/N nie miałby
                # etykiety severity i w nocy poszedłby tylko mailem.
                "severity": (
                    "skip"
                    if _is_true(labels.get(LABEL_SKIP))
                    else classify_severity(stack, labels, self.config.critical_stacks, self.config.warn_stacks)
                ),
                "image": container_spec.get("Image") or "",
                "mode": service_mode(spec),
                "desired": desired_replicas(spec, stats["running"]),
                "running": stats["running"],
                "states": stats["states"],
                "failed_1h": stats["failed_1h"],
                "updated_at": updated.timestamp() if updated else 0.0,
            }
            # Limity z spec usługi (NanoCPUs/MemoryBytes) — panel pokazuje nimi
            # „teraz vs limit"; `None` = limit nieustawiony, nie zero.
            entry["cpu_limit_cores"], entry["mem_limit_bytes"] = service_limits(task_template)
            # Dlaczego usługa się przewraca — wprost z Dockera, bez zgadywania.
            entry["last_task_state"] = stats.get("last_state")
            entry["last_task_error"] = stats.get("last_error")
            entry["replicas_text"] = "%d/%d" % (entry["running"], entry["desired"])
            snapshot.services.append(entry)
            snapshot.stacks.setdefault(stack, []).append(entry)

        for raw in raw_containers:
            if not isinstance(raw, dict):
                log("Ostrzeżenie: pomijam wpis kontenera, który nie jest obiektem (%s)", type(raw).__name__)
                continue
            stack, service_name = container_identity(raw.get("Labels"))
            if not stack:
                continue
            names = as_list(raw.get("Names"), "Names kontenera")
            name = str(names[0] if names else raw.get("Id") or "").lstrip("/")
            snapshot.containers.append(
                {
                    "id": raw.get("Id") or "",
                    "container": name,
                    "stack": stack,
                    "service": service_name,
                    "state": str(raw.get("State") or ""),
                    "status": str(raw.get("Status") or ""),
                    "cpu": 0.0,
                    "mem": 0.0,
                    "mem_limit": 0.0,
                    "health": "none",
                    "restart_count": 0,
                }
            )
        snapshot.df["containers_total"] = len(snapshot.containers)
        running_containers = [c for c in snapshot.containers if c["state"] == "running" and c["id"]]
        snapshot.df["containers_running"] = len(running_containers)

        def inspect(container):
            data = self.docker.container_inspect(container["id"])
            state = data.get("State") or {}
            health = str((state.get("Health") or {}).get("Status") or "none").lower()
            container["health"] = health if health in ("healthy", "unhealthy", "starting") else "none"
            try:
                container["restart_count"] = int(state.get("RestartCount") or 0)
            except (TypeError, ValueError):
                container["restart_count"] = 0

        def stats(container):
            data = self.docker.container_stats(container["id"])
            container["cpu"] = compute_cpu_percent(data)
            container["mem"], container["mem_limit"] = container_memory(data)
            container["net_rx"], container["net_tx"] = container_network(data)
            container["blk_read"], container["blk_write"] = container_blockio(data)

        for container, outcome in zip(running_containers, parallel_map(inspect, running_containers)):
            if isinstance(outcome, Exception):
                log("Nie udało się odczytać healthchecku %s: %s", container["container"], outcome)
        for container, outcome in zip(running_containers, parallel_map(stats, running_containers)):
            if isinstance(outcome, Exception):
                log("Nie udało się odczytać statystyk %s: %s", container["container"], outcome)

        snapshot.df.update(docker_df_summary(raw_df))

        snapshot.targets = build_targets(raw_services, self.config)
        active_targets = [t for t in snapshot.targets if t.severity != "skip"]
        # Sonda dokładnie raz na cykl, na unikalny URL (nie na router).
        unique_urls = sorted({t.url for t in active_targets})
        probe_results = parallel_map(
            lambda url: self.probe_fn(url, self.config.probe_timeout), unique_urls
        )
        for url, outcome in zip(unique_urls, probe_results):
            if isinstance(outcome, Exception):
                snapshot.probes[url] = ProbeResult("critical", None, 0.0, "%s: %s" % (type(outcome).__name__, outcome))
                log_error("Sonda %s nie powiodła się: %s", url, outcome)
            else:
                snapshot.probes[url] = coerce_probe(outcome, url)
        log(
            "Odświeżono: %d usług, %d stacków, %d celów, %d sond",
            len(snapshot.services), len(snapshot.stacks), len(active_targets), len(unique_urls),
        )

        hosts = sorted({t.host for t in active_targets if t.host})
        for host, outcome in zip(hosts, parallel_map(self._cert_info, hosts, workers=4)):
            if isinstance(outcome, Exception):
                log_error("Certyfikat %s: %s", host, outcome)
                snapshot.certs[host] = {"days_left": 0.0, "expires_at": None, "error": str(outcome)}
            else:
                snapshot.certs[host] = outcome

        self.tracker.observe(sorted(service["full_name"] for service in snapshot.services))
        snapshot.new_services_total = self.tracker.count
        snapshot.up = True
        snapshot.last_error = None
        snapshot.last_refresh = now
        with self._lock:
            snapshot.refreshes = self.snapshot.refreshes + 1
            self.snapshot = snapshot
        return True

    def _cert_info(self, host):
        cached = self.cert_cache.get(host)
        if cached is not None:
            return cached
        try:
            not_after = self.cert_fn(host)
            days_left = (not_after - datetime.now(timezone.utc)).total_seconds() / 86400.0
            value = {"days_left": round(days_left, 3), "expires_at": not_after.timestamp(), "error": None}
            self.cert_cache.set(host, value)
        except Exception as exc:  # noqa: BLE001 - brak TLS/certu nie może wywalić cyklu
            log_error("Nie udało się odczytać certyfikatu %s: %s", host, exc)
            value = {"days_left": 0.0, "expires_at": None, "error": "%s: %s" % (type(exc).__name__, exc)}
            self.cert_cache.set(host, value, ttl=300.0)
        return value

    # -- Prometheus --------------------------------------------------------
    def prom_scalar(self, expression):
        key = "q:" + expression
        cached = self.prom_cache.get(key)
        if cached is not None:
            return cached[0]
        url = "%s/api/v1/query?%s" % (
            self.config.prometheus_url,
            urllib.parse.urlencode({"query": expression}),
        )
        try:
            payload = self.json_get(url, timeout=5.0)
        except Exception as exc:  # noqa: BLE001 - brak Prometheusa => zera i warning
            log_error("Prometheus nie odpowiada (%s): %s", expression[:48], exc)
            return None
        if not isinstance(payload, dict):
            log("Prometheus zwrócił nieoczekiwany format (%s) dla %s", type(payload).__name__, expression[:48])
            return None
        data = payload.get("data")
        if not isinstance(data, dict):
            return None
        results = data.get("result")
        if not isinstance(results, list):
            return None
        values = []
        for item in results:
            if not isinstance(item, dict):
                continue
            pair = item.get("value")
            if not isinstance(pair, (list, tuple)) or len(pair) < 2:
                continue
            try:
                number = float(pair[1])
            except (TypeError, ValueError):
                continue
            if math.isfinite(number):
                values.append(number)
        value = max(values) if values else None
        self.prom_cache.set(key, (value,))
        return value

    def host_section(self):
        values = {key: self.prom_scalar(expression) for key, expression in HOST_QUERIES.items()}
        available = sum(1 for value in values.values() if value is not None)
        prom_ok = available > 0
        mem_total = finite(values.get("mem_total_bytes"))
        mem_available = finite(values.get("mem_available_bytes"))
        mem_used = max(0.0, mem_total - mem_available) if mem_total else 0.0
        fs_total = finite(values.get("fs_size_bytes"))
        fs_available = finite(values.get("fs_avail_bytes"))
        fs_used = max(0.0, fs_total - fs_available) if fs_total else 0.0
        files_total = finite(values.get("files_total"))
        files_free = finite(values.get("files_free"))
        host = {
            "cpu_percent": round(finite(values.get("cpu_percent")), 2),
            "load1": round(finite(values.get("load1")), 2),
            "load5": round(finite(values.get("load5")), 2),
            "load15": round(finite(values.get("load15")), 2),
            "mem_total_bytes": int(mem_total),
            "mem_used_bytes": int(mem_used),
            "mem_used_percent": round(mem_used / mem_total * 100.0, 2) if mem_total else 0.0,
            "swap_total_bytes": int(finite(values.get("swap_total_bytes"))),
            "disk_total_bytes": int(fs_total),
            "disk_used_bytes": int(fs_used),
            "disk_used_percent": round(fs_used / fs_total * 100.0, 2) if fs_total else 0.0,
            "inodes_used_percent": round((1.0 - files_free / files_total) * 100.0, 2) if files_total else 0.0,
            "uptime_seconds": int(finite(values.get("uptime_seconds"))),
            "time_utc": iso_z(self.clock()),
        }
        return host, prom_ok

    # -- sekcje api.json ---------------------------------------------------
    def checks_section(self):
        snapshot = self.snapshot_view()
        by_url = {}
        for target in sorted(snapshot.targets, key=lambda item: (item.url, item.stack, item.service)):
            if target.severity == "skip":
                continue
            by_url.setdefault(target.url, target)
        checks = []
        for url in sorted(by_url):
            target = by_url[url]
            probe = coerce_probe(snapshot.probes.get(url), url)
            check_id = slugify(url)
            since = self.check_since.observe(check_id, probe.state)
            checks.append(
                {
                    "id": check_id,
                    "name": target.service,
                    "group": target.stack,
                    "kind": "http",
                    "state": probe.state,
                    "detail": probe.detail_pl(),
                    "url": url,
                    "since": iso_z(since),
                    "latency_ms": int(round(probe.latency * 1000.0)),
                }
            )
        return checks

    def stacks_section(self):
        snapshot = self.snapshot_view()
        unhealthy = set()
        usage = {}
        for container in snapshot.containers:
            key = (container["stack"], container["service"])
            if container["health"] == "unhealthy":
                unhealthy.add(key)
            cpu, memory = usage.get(key, (0.0, 0.0))
            usage[key] = (cpu + (container.get("cpu") or 0.0), memory + (container.get("mem") or 0.0))
        stacks = []
        for stack_name in sorted(snapshot.stacks):
            services = []
            stack_state = "ok"
            running_sum = desired_sum = 0
            for service in sorted(snapshot.stacks[stack_name], key=lambda item: item["service"]):
                running_sum += service["running"]
                desired_sum += service["desired"]
                key = (stack_name, service["service"])
                if service["running"] < service["desired"]:
                    service_state = "critical"
                elif service["failed_1h"] > 0 or key in unhealthy:
                    service_state = "warning"
                else:
                    service_state = "ok"
                if service_state == "critical":
                    stack_state = "critical"
                elif service_state == "warning" and stack_state == "ok":
                    stack_state = "warning"
                cpu, memory = usage.get(key, (0.0, 0.0))
                services.append(
                    {
                        "name": service["service"],
                        "full_name": service["full_name"],
                        "state": service_state,
                        "desired": service["desired"],
                        "running": service["running"],
                        "image": service["image"],
                        "cpu_percent": round(cpu, 2),
                        "mem_bytes": int(memory),
                        "cpu_limit_cores": service.get("cpu_limit_cores"),
                        "mem_limit_bytes": service.get("mem_limit_bytes"),
                        "restarts_1h": service["failed_1h"],
                        "replicas_text": service["replicas_text"],
                        # Czasy w ISO Z (jak `generated_at`), `None` = brak danych.
                        "updated_at": (
                            iso_z(service["updated_at"]) if service.get("updated_at") else None
                        ),
                        "last_task_state": service.get("last_task_state"),
                        "last_task_error": service.get("last_task_error"),
                    }
                )
            stacks.append(
                {
                    "name": stack_name,
                    "state": stack_state,
                    "services_running": running_sum,
                    "services_desired": desired_sum,
                    "services": services,
                }
            )
        return stacks

    def certs_section(self):
        snapshot = self.snapshot_view()
        certs = []
        for host in sorted(snapshot.certs):
            info = snapshot.certs[host]
            if not isinstance(info, dict):
                log("Ostrzeżenie: nieoczekiwane dane certyfikatu dla %s (%s)", host, type(info).__name__)
                info = {"days_left": 0.0, "expires_at": None, "error": "nieoczekiwane dane"}
            days_left = finite(info.get("days_left"))
            expires_at = info.get("expires_at")
            certs.append(
                {
                    "host": host,
                    "days_left": round(days_left, 2),
                    "expires_at": iso_z(expires_at) if isinstance(expires_at, (int, float)) else None,
                    "state": "unknown" if info.get("error") else cert_state(days_left),
                }
            )
        return certs

    def backup_section(self):
        default = {
            "state": "unknown",
            "last_success_at": None,
            "age_hours": None,
            "size_bytes": 0,
            "objects_in_r2": 0,
            "restore_test_days": 0,
        }
        if not self.config.health_ping_url:
            return default
        try:
            payload = self.json_get(self.config.health_ping_url + "/backup.json", timeout=5.0)
        except Exception as exc:  # noqa: BLE001 - brak health-ping => unknown
            log("health-ping niedostępny (%s) — sekcja backupu: unknown", exc)
            return default
        if not isinstance(payload, dict):
            return default
        section = dict(default)
        for key in default:
            if key in payload:
                section[key] = payload[key]
        return section

    def alerts_section(self):
        url = self.config.alertmanager_url + "/api/v2/alerts"
        try:
            payload = self.json_get(url, timeout=5.0)
        except Exception as exc:  # noqa: BLE001 - brak Alertmanagera => pusta lista
            log("Alertmanager niedostępny (%s)", exc)
            return []
        if not isinstance(payload, list):
            log("Alertmanager zwrócił nieoczekiwany format (%s) — pomijam alerty", type(payload).__name__)
            return []
        alerts = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            labels = item.get("labels") or {}
            annotations = item.get("annotations") or {}
            alerts.append(
                {
                    "name": labels.get("alertname") or "alert",
                    "severity": str(labels.get("severity") or "unknown").lower(),
                    "stack": labels.get("stack") or labels.get("namespace") or "",
                    "summary": annotations.get("summary") or annotations.get("description") or "",
                    "since": item.get("startsAt") or "",
                }
            )
        return alerts

    def logs_section(self, zapytanie):
        """Linie logów z Loki dla panelu. Zwraca `(kod HTTP, payload)`.

        Brak źródła (Loki nie odpowiada) to nie wyjątek, a czytelny komunikat:
        panel ma pokazać, że nie wie, a nie udawać pustkę.
        """
        parametry = logi_parametry(zapytanie)
        selektor = logi_zapytanie(parametry["zrodlo"], parametry["stack"], parametry["usluga"])
        if selektor is None:
            return 400, {
                "error": "Brak usługi — wybierz usługę albo przełącz źródło na host/Traefik.",
                "zrodlo": parametry["zrodlo"],
            }
        if not self.config.loki_url:
            return 503, {"error": "Loki nie jest skonfigurowane (LOKI_URL).", "zapytanie": selektor}

        teraz = int(self.clock())
        sekundy = LOGI_ZAKRESY[parametry["zakres"]]
        adres = "%s/loki/api/v1/query_range?%s" % (
            self.config.loki_url,
            urllib.parse.urlencode({
                "query": selektor,
                "start": str((teraz - sekundy) * 1_000_000_000),
                "end": str(teraz * 1_000_000_000),
                "limit": str(parametry["limit"]),
                "direction": "backward",
            }),
        )
        try:
            dane = self.json_get(adres, timeout=10.0)
        except Exception as exc:  # noqa: BLE001 - brak Loki => komunikat, nie 500
            log("Logi: Loki nie odpowiedziało (%s)", exc)
            return 503, {"error": "Loki nie odpowiedziało — spróbuj ponownie.", "zapytanie": selektor}

        linie = []
        for strumien in ((dane or {}).get("data") or {}).get("result") or []:
            if not isinstance(strumien, dict):
                continue
            etykiety = strumien.get("stream") if isinstance(strumien.get("stream"), dict) else {}
            opis = (etykiety.get("service") or etykiety.get("unit") or etykiety.get("container")
                    or etykiety.get("RequestHost") or etykiety.get("job") or "")
            for wpis in strumien.get("values") or []:
                if not isinstance(wpis, list) or len(wpis) < 2:
                    continue
                try:
                    czas = float(wpis[0]) / 1e9
                except (TypeError, ValueError):
                    continue
                tresc = wpis[1] if isinstance(wpis[1], str) else None
                if tresc is None:
                    continue
                linie.append({"czas": czas, "tekst": tresc, "strumien": opis})
        linie.sort(key=lambda linia: linia["czas"], reverse=True)
        return 200, {
            "zrodlo": parametry["zrodlo"],
            "zakres": parametry["zakres"],
            "limit": parametry["limit"],
            "zapytanie": selektor,
            "linie": linie,
        }

    def security_section(self):
        default = empty_security()
        # Zewnętrzny JSON (jeśli ktoś go poda) ma pierwszeństwo — może zawierać
        # dane, których w journalu nie ma (np. bany z fail2bana).
        if self.config.security_json_url:
            try:
                payload = self.json_get(self.config.security_json_url, timeout=5.0)
            except Exception as exc:  # noqa: BLE001 - brak źródła => unknown
                log("Źródło bezpieczeństwa niedostępne (%s)", exc)
                return default
            if not isinstance(payload, dict):
                return default
            section = dict(default)
            section.update(payload)
            # `empty_security()` ma teraz `state: unknown`, więc setdefault nic
            # by nie zmienił — a skoro źródło odpowiedziało, to nie jest unknown.
            if not payload.get("state"):
                section["state"] = "ok"
            return section
        if self.config.loki_url:
            section = sekcja_z_loki(self.config.loki_url, self.json_get)
            if section is not None:
                return section
        return default

    def tools_section(self):
        tools = []
        for template in TOOLS:
            tool = dict(template)
            if tool["kind"] == "internal":
                if tool["url"] is None:
                    tool["state"] = "ok"
                else:
                    tool["state"] = self._tool_state(tool["url"])
            else:
                tool["state"] = "unknown"
            tools.append(tool)
        return tools

    def _tool_state(self, path):
        if not self.config.base_url:
            return "unknown"
        key = "tool:" + path
        cached = self.tool_cache.get(key)
        if cached is not None:
            return cached
        try:
            probe = self.probe_fn(self.config.base_url + path, self.config.probe_timeout)
            state = probe.state
        except Exception as exc:  # noqa: BLE001 - narzędzie może być niedostępne
            log("Sonda narzędzia %s nie powiodła się: %s", path, exc)
            state = "critical"
        self.tool_cache.set(key, state)
        return state

    # -- widoki ------------------------------------------------------------
    def metrics(self):
        return render_metrics(self.snapshot_view())

    def http_sd(self):
        snapshot = self.snapshot_view()
        entries = []
        for target in sorted(snapshot.targets, key=lambda item: (item.stack, item.service, item.url)):
            if target.severity == "skip":
                continue
            entries.append({"targets": [target.url], "labels": target.sd_labels()})
        return entries

    def health(self):
        snapshot = self.snapshot_view()
        return {
            "status": "ok" if snapshot.up else "degraded",
            "up": bool(snapshot.up),
            "last_refresh": iso_z(snapshot.last_refresh) if snapshot.last_refresh else None,
            "last_error": snapshot.last_error,
        }

    def api_json(self):
        """
        Zagregowany stan dla panelu.

        Każda sekcja liczona jest w izolacji: uszkodzone dane z Prometheusa,
        Alertmanagera, health-ping czy Docker API nie mogą wywrócić generatora —
        panel musi dostać 200 z kompletnym schematem.
        """
        snapshot = self.snapshot_view()
        now = self.clock()
        host_default = (empty_host(now), False)
        host, prom_ok = self._safe("host", self.host_section, host_default)
        if not isinstance(host, dict):
            host, prom_ok = host_default
        checks = self._safe_list("checks", self.checks_section)
        stacks = self._safe_list("stacks", self.stacks_section)
        certs = self._safe_list("certs", self.certs_section)
        backup = self._safe("backup", self.backup_section, empty_backup())
        if not isinstance(backup, dict):
            backup = empty_backup()
        alerts = self._safe_list("alerts", self.alerts_section)
        security = self._safe("security", self.security_section, empty_security())
        if not isinstance(security, dict):
            security = empty_security()
        tools = self._safe_list("tools", self.tools_section)
        overall = self._safe(
            "overall",
            lambda: compute_overall(checks, stacks, snapshot, prom_ok, backup),
            "warning",
        )
        if overall not in ("ok", "warning", "critical"):
            overall = "warning"
        return {
            "generated_at": iso_z(now),
            "overall": overall,
            "host": host,
            "checks": checks,
            "stacks": stacks,
            "certs": certs,
            "backup": backup,
            "alerts": alerts,
            "security": security,
            "tools": tools,
        }

    def _safe(self, label, factory, default):
        """Uruchamia sekcję api.json tak, żeby jej błąd nie psuł całej odpowiedzi."""
        try:
            return factory()
        except Exception as exc:  # noqa: BLE001 - panel nie może zginąć przez jedną sekcję
            log_error("Sekcja %s w /status/api.json nie powiodła się: %s", label, exc)
            return default

    def _safe_list(self, label, factory):
        value = self._safe(label, factory, [])
        return value if isinstance(value, list) else []


def compute_overall(checks, stacks, snapshot, prom_ok, backup):
    """
    critical: check critical LUB jakakolwiek usługa z running < desired.
    warning: cokolwiek warning/unknown, discovery_up == 0, brak Prometheusa,
             backup w stanie innym niż ok.
    """
    for check in checks:
        if isinstance(check, dict) and check.get("state") == "critical":
            return "critical"
    for stack in stacks:
        if not isinstance(stack, dict):
            continue
        for service in stack.get("services") or []:
            if not isinstance(service, dict):
                continue
            if finite(service.get("running")) < finite(service.get("desired")):
                return "critical"
    if not snapshot.up or not prom_ok:
        return "warning"
    for check in checks:
        if isinstance(check, dict) and check.get("state") in ("warning", "unknown"):
            return "warning"
    for stack in stacks:
        if not isinstance(stack, dict) or stack.get("state") != "ok":
            return "warning"
    if str((backup or {}).get("state") if isinstance(backup, dict) else "unknown") != "ok":
        return "warning"
    return "ok"


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------
def make_handler(service):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "%s/1.0" % NAME

        def log_message(self, fmt, *args):
            log("%s - %s", self.address_string(), fmt % args)

        def _send(self, code, body, content_type):
            if isinstance(body, str):
                body = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _send_json(self, payload, code=200):
            self._send(code, json.dumps(payload, ensure_ascii=False, indent=None), "application/json; charset=utf-8")

        def do_GET(self):  # noqa: N802 - API BaseHTTPRequestHandler
            route = urllib.parse.urlsplit(self.path).path
            route = route.rstrip("/") or "/"
            try:
                if route == "/health":
                    self._send_json(service.health())
                elif route == "/sd/http.json":
                    self._send_json(service.http_sd())
                elif route == "/metrics":
                    self._send(200, service.metrics(), "text/plain; version=0.0.4; charset=utf-8")
                elif route == "/status/api.json":
                    self._send_json(service.api_json())
                elif route == "/status/logs":
                    kod, payload = service.logs_section(urllib.parse.parse_qs(
                        urllib.parse.urlsplit(self.path).query))
                    self._send_json(payload, kod)
                elif route == "/":
                    self._send_json(
                        {
                            "service": NAME,
                            "endpoints": ["/health", "/sd/http.json", "/metrics", "/status/api.json",
                                       "/status/logs"],
                        }
                    )
                else:
                    self._send_json({"error": "nie znaleziono", "path": route}, 404)
            except Exception as exc:  # noqa: BLE001 - pojedyncze żądanie nie może zabić serwisu
                log_error("Błąd obsługi %s: %s", route, exc)
                try:
                    self._send_json({"error": str(exc)}, 500)
                except Exception:  # noqa: BLE001 - klient mógł się rozłączyć
                    pass

        def do_HEAD(self):  # noqa: N802
            self.do_GET()

        def _reject(self):
            self._send_json({"error": "dozwolone jest wyłącznie GET"}, 405)

        do_POST = _reject  # noqa: N815
        do_PUT = _reject  # noqa: N815
        do_DELETE = _reject  # noqa: N815
        do_PATCH = _reject  # noqa: N815

    return Handler


def main():
    try:
        config = Config()
    except ConfigError as exc:
        log_error("%s", exc)
        return 2
    service = DiscoveryService(config)
    try:
        server = ThreadingHTTPServer(("0.0.0.0", config.port), make_handler(service))
    except OSError as exc:
        log_error("Nie mogę wystartować na porcie %d: %s", config.port, exc)
        return 1
    server.daemon_threads = True
    stop_event = threading.Event()

    def handle_signal(signum, _frame):
        log("Otrzymano sygnał %s — zamykam", signum)
        stop_event.set()
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)
    worker = threading.Thread(target=service.run, args=(stop_event,), name="refresh", daemon=True)
    worker.start()
    log(
        "Start na porcie %d (socket=%s, odświeżanie co %ss, domena=%s)",
        config.port, config.docker_socket, config.refresh_seconds, config.monitoring_domain or "-",
    )
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        server.server_close()
        worker.join(timeout=5.0)
        log("Zamknięty")
    return 0


if __name__ == "__main__":
    sys.exit(main())
