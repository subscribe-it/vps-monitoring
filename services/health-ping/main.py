#!/usr/bin/env python3
"""
health-ping — watchdog wychodzący do healthchecks.io.

Co INTERVAL_SECONDS ocenia stan całego stacku monitoringu (dysk, i-węzły,
repliki usług, sondy HTTP, certyfikaty, backup, test odtworzenia, Alertmanager)
i pinguje healthchecks.io TYLKO wtedy, gdy wszystko jest zielone. Przy problemie
wysyła ping na <url>/fail z powodem.

Zero zależności zewnętrznych — tylko biblioteka standardowa Pythona.
"""

from __future__ import annotations

import json
import os
import re
import signal
import socket
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

NAME = "health-ping"
DEFAULT_PORT = 8080
DEFAULT_DOCKER_SOCKET = "/var/run/docker.sock"
DEFAULT_DISCOVERY_URL = "http://discovery:8080"
DEFAULT_ALERTMANAGER_URL = "http://alertmanager:9093"
DEFAULT_PROMETHEUS_URL = "http://prometheus:9090"
DEFAULT_BACKUP_SERVICE = "ventiplan-prod_db-backup"
DEFAULT_RESTORE_TEST_FILE = "/data/restore-test.json"

READ_CHUNK = 65536

# Kolejność ma znaczenie w raportach i metrykach.
CHECKS = (
    "disk",
    "inodes",
    "services",
    "http",
    "certs",
    "backup",
    "restore_test",
    "alertmanager",
)


# --------------------------------------------------------------------------
# Logowanie (stderr, prefiks [health-ping])
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
    def __init__(self, env=None):
        env = dict(os.environ if env is None else env)
        self.env = env
        self.docker_socket = _normalize_docker_host(env.get("DOCKER_HOST", ""))
        self.hc_ping_all_ok = (env.get("HC_PING_ALL_OK", "") or "").strip()
        self.hc_ping_backup = (env.get("HC_PING_BACKUP", "") or "").strip()
        self.interval_seconds = _env_float(env, "INTERVAL_SECONDS", 120.0, minimum=10.0)
        self.prometheus_url = (env.get("PROMETHEUS_URL", DEFAULT_PROMETHEUS_URL) or "").rstrip("/")
        self.discovery_url = (env.get("DISCOVERY_URL", DEFAULT_DISCOVERY_URL) or "").rstrip("/")
        self.alertmanager_url = (env.get("ALERTMANAGER_URL", DEFAULT_ALERTMANAGER_URL) or "").rstrip("/")
        self.backup_service = (env.get("BACKUP_SERVICE", DEFAULT_BACKUP_SERVICE) or "").strip()
        self.backup_success_regex = (env.get("BACKUP_SUCCESS_REGEX", "") or "").strip()
        self.backup_max_age_hours = _env_float(env, "BACKUP_MAX_AGE_HOURS", 26.0, minimum=1.0)
        self.backup_min_size_mb = _env_float(env, "BACKUP_MIN_SIZE_MB", 0.0, minimum=0.0)
        self.disk_min_free_percent = _env_float(env, "DISK_MIN_FREE_PERCENT", 15.0, minimum=0.0)
        self.inodes_min_free_percent = _env_float(env, "INODES_MIN_FREE_PERCENT", 10.0, minimum=0.0)
        self.cert_min_days = _env_float(env, "CERT_MIN_DAYS", 14.0, minimum=0.0)
        self.restore_test_max_days = _env_float(env, "RESTORE_TEST_MAX_DAYS", 45.0, minimum=1.0)
        self.services_ignore_stacks = set(
            _env_csv(env, "SERVICES_IGNORE_STACKS", "monitoring,kosmetix-staging,staging_mdi-studio")
        )
        self.restore_test_file = (env.get("RESTORE_TEST_FILE", DEFAULT_RESTORE_TEST_FILE) or "").strip()
        self.port = _env_int(env, "PORT", DEFAULT_PORT)
        self.request_timeout = _env_float(env, "REQUEST_TIMEOUT_SECONDS", 5.0, minimum=0.5)
        self.ping_timeout = _env_float(env, "PING_TIMEOUT_SECONDS", 10.0, minimum=1.0)

    @property
    def config_warnings(self):
        warnings = []
        if not self.hc_ping_all_ok:
            warnings.append("HC_PING_ALL_OK nie jest ustawione — pingi do healthchecks.io są pomijane")
        if not self.hc_ping_backup:
            warnings.append("HC_PING_BACKUP nie jest ustawione — ping backupu jest pomijany")
        return warnings


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


def _env_csv(env, key, default=""):
    raw = env.get(key, default)
    if raw is None:
        raw = default
    return [item.strip() for item in str(raw).split(",") if item.strip()]


def _normalize_docker_host(raw):
    value = (raw or "").strip()
    if not value:
        return DEFAULT_DOCKER_SOCKET
    if value.startswith("unix://"):
        return value[len("unix://") :] or DEFAULT_DOCKER_SOCKET
    if value.startswith("/"):
        return value
    raise ConfigError(
        "DOCKER_HOST=%r nie jest obsługiwany: dozwolone jest wyłącznie gniazdo unix "
        "(np. unix:///var/run/docker.sock)" % value
    )


def iso_z(ts):
    if ts is None:
        return None
    return datetime.fromtimestamp(float(ts), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_rfc3339(value):
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


# --------------------------------------------------------------------------
# Klienty HTTP (stdlib, wyłącznie GET z wyjątkiem pingów healthchecks.io)
# --------------------------------------------------------------------------
def http_get_text(url, timeout=5.0):
    request = urllib.request.Request(url, method="GET")
    request.add_header("User-Agent", "monitoring-%s/1.0" % NAME)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", "replace")


def http_get_json(url, timeout=5.0):
    return json.loads(http_get_text(url, timeout=timeout) or "null")


def http_get_status(url, timeout=5.0):
    """Kod HTTP odpowiedzi (błędy 4xx/5xx też zwracają kod, nie wyjątek)."""
    request = urllib.request.Request(url, method="GET")
    request.add_header("User-Agent", "monitoring-%s/1.0" % NAME)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response.read(1024)
            return int(getattr(response, "status", 0) or 0)
    except urllib.error.HTTPError as exc:
        try:
            exc.read(1024)
        except Exception:  # noqa: BLE001 - best-effort
            pass
        return int(exc.code or 0)


def http_post(url, body="", timeout=10.0):
    data = (body or "").encode("utf-8")
    request = urllib.request.Request(url, data=data, method="POST")
    request.add_header("User-Agent", "monitoring-%s/1.0" % NAME)
    request.add_header("Content-Type", "text/plain; charset=utf-8")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        response.read(1024)
        return int(getattr(response, "status", 0) or 0)


def ping_healthchecks(ping_url, ok, message, timeout=10.0):
    """
    Pinguje healthchecks.io. Przy problemie wysyła na <url>/fail z powodem.

    healthchecks.io akceptuje POST z treścią; `/fail` oznacza stan czerwony.
    """
    if not ping_url:
        return None
    target = ping_url.rstrip("/") if ok else ping_url.rstrip("/") + "/fail"
    body = "OK" if ok else (message or "check nie przeszedł")
    try:
        status = http_post(target, body, timeout=timeout)
    except Exception as exc:  # noqa: BLE001 - brak sieci nie może wywalić pętli
        log_error("Ping %s nie powiódł się: %s", target, exc)
        return False
    if 200 <= status < 400:
        log("Ping %s OK (%d)", target, status)
        return True
    log_error("Ping %s zwrócił HTTP %d", target, status)
    return False


# --------------------------------------------------------------------------
# Docker API — wyłącznie GET przez unix socket
# --------------------------------------------------------------------------
class DockerError(RuntimeError):
    pass


def _split_http_response(raw):
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
    parts = lines[0].strip().split(" ", 2)
    if len(parts) < 2 or not parts[1].isdigit():
        raise DockerError("nieprawidłowa linia statusu HTTP: %r" % lines[0])
    status = int(parts[1])
    headers = {}
    for line in lines[1:]:
        line = line.strip("\r")
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        headers[key.strip().lower()] = value.strip()
    if "chunked" in headers.get("transfer-encoding", "").lower():
        body = decode_chunked(body)
    return status, headers, body


def decode_chunked(body):
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
    """Klient Docker Engine API — cały ruch to GET przez AF_UNIX."""

    def __init__(self, socket_path=DEFAULT_DOCKER_SOCKET, timeout=10.0, fetcher=None):
        self.socket_path = socket_path
        self.timeout = float(timeout)
        self._fetcher = fetcher

    def _unix_get(self, path):
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
            raise DockerError("brak połączenia z Docker API (%s): %s" % (self.socket_path, exc)) from exc
        finally:
            try:
                sock.close()
            except OSError:
                pass

    def get_raw(self, path):
        fetcher = self._fetcher or self._unix_get
        try:
            return fetcher(path)
        except DockerError:
            raise
        except Exception as exc:  # noqa: BLE001 - transport wstrzykiwany w testach
            raise DockerError("błąd transportu Docker API: %s" % exc) from exc

    def get_bytes(self, path):
        status, _headers, body = _split_http_response(self.get_raw(path))
        if status >= 400:
            raise DockerError("Docker API zwróciło HTTP %d dla %s" % (status, path))
        return body

    def get_json(self, path):
        body = self.get_bytes(path)
        try:
            return json.loads(body.decode("utf-8", "replace") or "null")
        except ValueError as exc:
            raise DockerError("nieprawidłowy JSON z Docker API dla %s" % path) from exc

    def containers(self):
        return self.get_json("/containers/json?all=1") or []

    def container_inspect(self, container_id):
        return self.get_json("/containers/%s/json" % container_id) or {}

    def container_logs(self, container_id, tail=2000):
        return self.get_bytes(
            "/containers/%s/logs?stdout=1&stderr=1&tail=%d" % (container_id, int(tail))
        )


# --------------------------------------------------------------------------
# Parsowanie strumienia logów Dockera (8-bajtowe nagłówki ramek)
# --------------------------------------------------------------------------
def parse_docker_log_stream(raw):
    """
    Docker przy /logs zwraca strumień ramkowany: [typ(1) 000 rozmiar(4 BE)] + treść.

    Funkcja odfiltrowuje nagłówki. Jeśli strumień nie jest ramkowany (np. TTY),
    zwraca treść bez zmian.
    """
    if not raw:
        return ""
    if len(raw) < 8:
        return raw.decode("utf-8", "replace")
    out = bytearray()
    pos = 0
    while pos + 8 <= len(raw):
        frame_type = raw[pos]
        size = int.from_bytes(raw[pos + 4 : pos + 8], "big")
        if frame_type not in (0, 1, 2) or pos + 8 + size > len(raw):
            if pos == 0:
                return raw.decode("utf-8", "replace")
            break  # obcięta ostatnia ramka (np. limit tail) — pomijamy ogon
        out += raw[pos + 8 : pos + 8 + size]
        pos += 8 + size
    if pos == 0:
        return raw.decode("utf-8", "replace")
    return out.decode("utf-8", "replace")


# --------------------------------------------------------------------------
# Wyciąganie czasu ostatniego udanego backupu z logów
# --------------------------------------------------------------------------
_TS_RE = re.compile(
    r"(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}:\d{2})(?:\.(\d+))?(Z|z|[+-]\d{2}:?\d{2})?"
)

# Domyślne znaczniki sukcesu (polskie i angielskie). Przy realnych logach
# najlepiej ustawić BACKUP_SUCCESS_REGEX — patrz README.
STRONG_SUCCESS_PATTERNS = (
    r"backup\s+ok",
    r"backup\s+complete",
    r"backup\s+completed",
    r"backup\s+successful",
    r"backup\s+succeeded",
    r"uploaded",
    r"dump\s+ok",
    r"zakonczony\s+sukcesem",
    r"zakończony\s+sukcesem",
    r"zakończony",
    r"zakonczony",
    r"sukces",
    r"backup\s+done",
)

WEAK_FILE_PATTERN = re.compile(r"[\w./-]+\.(?:dump|age)\b", re.IGNORECASE)

_SIZE_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(B|KB|kB|MB|GB|TB|KiB|MiB|GiB|TiB)\b")
_SIZE_UNITS = {
    "b": 1,
    "kb": 1000,
    "mb": 1000 ** 2,
    "gb": 1000 ** 3,
    "tb": 1000 ** 4,
    "kib": 1024,
    "mib": 1024 ** 2,
    "gib": 1024 ** 3,
    "tib": 1024 ** 4,
}


def extract_timestamp(line):
    """Znacznik czasu z linii logu (ISO8601 / 'YYYY-MM-DD HH:MM:SS'), domyślnie UTC."""
    match = _TS_RE.search(line or "")
    if not match:
        return None
    date_part, time_part, fraction, tz = match.group(1), match.group(2), match.group(3), match.group(4)
    text = "%sT%s" % (date_part, time_part)
    if fraction:
        text += "." + fraction[:6]
    if tz:
        text += "+00:00" if tz in ("Z", "z") else (tz if ":" in tz else tz[:3] + ":" + tz[3:])
    else:
        text += "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def extract_size_bytes(text):
    """Pierwszy rozmiar w tekście (np. '512.4 MB', '2 GiB') jako bajty."""
    match = _SIZE_RE.search(text or "")
    if not match:
        return None
    value = float(match.group(1).replace(",", "."))
    unit = match.group(2).lower()
    return int(value * _SIZE_UNITS.get(unit, 1))


class BackupInfo:
    __slots__ = ("last_success_at", "size_bytes", "matched_line", "timestamp_source", "weak_match")

    def __init__(self, last_success_at=None, size_bytes=None, matched_line=None,
                 timestamp_source="none", weak_match=False):
        self.last_success_at = last_success_at
        self.size_bytes = size_bytes
        self.matched_line = matched_line
        self.timestamp_source = timestamp_source
        self.weak_match = weak_match


def extract_backup_info(text, success_regex=None):
    """
    Szuka w logach znacznika ostatniego SUKCESU backupu.

    Kolejność źródeł czasu: znacznik w dopasowanej linii -> najnowszy znacznik
    gdziekolwiek w logu -> brak (wtedy wynik jest bezużyteczny i check gaśnie).
    """
    lines = [line for line in (text or "").splitlines() if line.strip()]
    newest_log_ts = None
    for line in lines:
        timestamp = extract_timestamp(line)
        if timestamp is not None and (newest_log_ts is None or timestamp > newest_log_ts):
            newest_log_ts = timestamp

    candidates = []
    if success_regex:
        try:
            matcher = re.compile(success_regex, re.IGNORECASE)
        except re.error as exc:
            raise ValueError("BACKUP_SUCCESS_REGEX jest nieprawidłowy: %s" % exc) from exc
        candidates = [line for line in lines if matcher.search(line)]
    else:
        for line in lines:
            if any(re.search(pattern, line, re.IGNORECASE) for pattern in STRONG_SUCCESS_PATTERNS):
                candidates.append(line)
    weak = False
    if not candidates and not success_regex:
        matches = [line for line in lines if WEAK_FILE_PATTERN.search(line)]
        if matches:
            candidates = matches
            weak = True
    if not candidates:
        return BackupInfo()

    matched_line = candidates[-1]
    timestamp = extract_timestamp(matched_line)
    source = "line"
    if timestamp is None:
        timestamp = newest_log_ts
        source = "log" if timestamp is not None else "none"
    size = extract_size_bytes(matched_line)
    return BackupInfo(timestamp, size, matched_line.strip()[:400], source, weak)


# --------------------------------------------------------------------------
# Parsowanie ekspozycji Prometheusa (własny parser, bez bibliotek)
# --------------------------------------------------------------------------
_SAMPLE_RE = re.compile(r"^([a-zA-Z_:][a-zA-Z0-9_:]*)(\{.*\})?\s+([^\s]+)(?:\s+\S+)?$")


def parse_label_set(text):
    """'{a="1",b="x\\"y"}' -> {'a': '1', 'b': 'x"y'} (z obsługą escapowania)."""
    labels = {}
    body = (text or "").strip()
    if body.startswith("{"):
        body = body[1:]
    if body.endswith("}"):
        body = body[:-1]
    if not body.strip():
        return labels
    index = 0
    length = len(body)
    while index < length:
        while index < length and body[index] in ", \t":
            index += 1
        start = index
        while index < length and body[index] != "=":
            index += 1
        key = body[start:index].strip()
        index += 1  # '='
        if index >= length or body[index] != '"':
            break
        index += 1
        chars = []
        while index < length:
            char = body[index]
            if char == "\\" and index + 1 < length:
                nxt = body[index + 1]
                chars.append({"n": "\n", "\\": "\\", '"': '"'}.get(nxt, nxt))
                index += 2
                continue
            if char == '"':
                index += 1
                break
            chars.append(char)
            index += 1
        if key:
            labels[key] = "".join(chars)
        while index < length and body[index] in ", \t":
            index += 1
    return labels


def parse_prometheus_text(text):
    """[(nazwa, {etykiety}, wartość)] — komentarze i linie bez wartości są pomijane."""
    samples = []
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = _SAMPLE_RE.match(line)
        if not match:
            continue
        try:
            value = float(match.group(3))
        except (TypeError, ValueError):
            continue
        samples.append((match.group(1), parse_label_set(match.group(2) or ""), value))
    return samples


def collect_service_replicas(samples):
    """{(stack, service): {'desired': x, 'running': y}} z metryk discovery."""
    replicas = {}
    for name, labels, value in samples:
        stack, service = labels.get("stack"), labels.get("service")
        if not stack or not service:
            continue
        entry = replicas.setdefault((stack, service), {"desired": 0.0, "running": 0.0})
        if name == "swarm_service_desired_replicas":
            entry["desired"] = value
        elif name == "swarm_service_running_replicas":
            entry["running"] = value
    return replicas


def failing_services(samples, ignore_stacks):
    """Usługi z running < desired, poza stackami z SERVICES_IGNORE_STACKS."""
    failing = []
    for (stack, service), entry in sorted(collect_service_replicas(samples).items()):
        if stack in ignore_stacks:
            continue
        if entry["running"] < entry["desired"]:
            failing.append("%s_%s (%d/%d)" % (stack, service, entry["running"], entry["desired"]))
    return failing


def min_cert_days(samples):
    """Najmniejsza wartość discovery_cert_days_left lub None."""
    values = [value for name, _labels, value in samples if name == "discovery_cert_days_left"]
    return min(values) if values else None


# --------------------------------------------------------------------------
# Ekspozycja metryk Prometheusa
# --------------------------------------------------------------------------
METRIC_FAMILIES = (
    ("monitoring_all_ok", "gauge", "1, gdy wszystkie sprawdzenia są zielone."),
    ("monitoring_check_ok", "gauge", "Wynik pojedynczego sprawdzenia (1 = ok)."),
    ("monitoring_backup_age_seconds", "gauge", "Wiek ostatniego udanego backupu."),
    ("monitoring_backup_size_bytes", "gauge", "Rozmiar ostatniego backupu."),
    ("monitoring_restore_test_age_days", "gauge", "Dni od ostatniego testu odtworzenia."),
    ("monitoring_last_hc_ping_timestamp_seconds", "gauge", "Czas ostatniego udanego pingu do healthchecks.io."),
    ("monitoring_hc_ping_failures_total", "counter", "Liczba nieudanych pingów do healthchecks.io."),
    ("monitoring_last_run_timestamp_seconds", "gauge", "Czas ostatniego przebiegu pętli kontrolnej."),
    ("monitoring_up", "gauge", "Czy pętla kontrolna health-ping działa."),
)

PING_TARGETS = ("all_ok", "backup")


def escape_label_value(value):
    text = "" if value is None else str(value)
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def labels_str(labels):
    if not labels:
        return ""
    return "{" + ",".join('%s="%s"' % (key, escape_label_value(labels[key])) for key in sorted(labels)) + "}"


def fmt_value(value):
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "0"
    if number != number or number in (float("inf"), float("-inf")):
        return "0"
    if number == int(number) and abs(number) < 1e15:
        return str(int(number))
    return repr(round(number, 6))


def render_metrics(state):
    """
    Czysta funkcja: słownik stanu -> tekst exposition Prometheusa.

    `monitoring_backup_age_seconds` i `monitoring_backup_size_bytes` pojawiają się
    tylko wtedy, gdy znamy wartość — brak serii jest czytelniejszy niż zero, które
    wyglądałoby jak „świeży backup". Sygnał problemu niesie monitoring_check_ok.
    """
    samples = []
    checks = state.get("checks") or CHECKS
    results = state.get("results") or {}
    samples.append(("monitoring_all_ok", {}, 1 if state.get("all_ok") else 0))
    for check in checks:
        outcome = results.get(check)
        samples.append(("monitoring_check_ok", {"check": check}, 1 if outcome and outcome.ok else 0))
    if state.get("backup_age_seconds") is not None:
        samples.append(("monitoring_backup_age_seconds", {}, state["backup_age_seconds"]))
    if state.get("backup_size_bytes") is not None:
        samples.append(("monitoring_backup_size_bytes", {}, state["backup_size_bytes"]))
    samples.append(
        ("monitoring_restore_test_age_days", {}, state.get("restore_test_age_days") or 0)
    )
    last_ping = state.get("last_ping") or {}
    for target in PING_TARGETS:
        if target in last_ping:
            samples.append(("monitoring_last_hc_ping_timestamp_seconds", {"target": target}, last_ping[target]))
    ping_failures = state.get("ping_failures") or {}
    for target in PING_TARGETS:
        samples.append(("monitoring_hc_ping_failures_total", {"target": target}, ping_failures.get(target, 0)))
    samples.append(("monitoring_last_run_timestamp_seconds", {}, state.get("last_run") or 0))
    samples.append(("monitoring_up", {}, 1 if state.get("up") else 0))

    grouped = {}
    for name, labels, value in samples:
        grouped.setdefault(name, []).append((labels, value))
    lines = []
    for name, metric_type, help_text in METRIC_FAMILIES:
        lines.append("# HELP %s %s" % (name, help_text))
        lines.append("# TYPE %s %s" % (name, metric_type))
        for labels, value in grouped.get(name, []):
            lines.append("%s%s %s" % (name, labels_str(labels), fmt_value(value)))
    return "\n".join(lines) + "\n"


def find_backup_container(containers, service_name):
    """Kontener, którego com.docker.swarm.service.name == BACKUP_SERVICE."""
    if not service_name:
        return None
    for container in containers or []:
        labels = container.get("Labels") or {}
        name = (labels.get("com.docker.swarm.service.name") or "").strip()
        if name == service_name:
            return container
    return None


def _read_text_file(path):
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


# --------------------------------------------------------------------------
# Sprawdzenia
# --------------------------------------------------------------------------
class CheckOutcome:
    __slots__ = ("ok", "detail", "data")

    def __init__(self, ok, detail, data=None):
        self.ok = bool(ok)
        self.detail = detail
        self.data = data or {}

    def __repr__(self):
        return "CheckOutcome(ok=%s, detail=%r)" % (self.ok, self.detail)


class HealthPing:
    def __init__(self, config, docker=None, text_get=None, json_get=None, status_get=None,
                 ping_fn=None, statvfs=None, file_reader=None, clock=time.time):
        self.config = config
        self.docker = docker if docker is not None else DockerClient(config.docker_socket)
        self.text_get = text_get or http_get_text
        self.json_get = json_get or http_get_json
        self.status_get = status_get or http_get_status
        self.ping_fn = ping_fn or ping_healthchecks
        self.statvfs = statvfs or os.statvfs
        self.file_reader = file_reader or _read_text_file
        self.clock = clock
        self.results = {name: CheckOutcome(False, "brak danych") for name in CHECKS}
        self.all_ok = False
        self.up = False
        self.last_run = 0.0
        self.backup_info = BackupInfo()
        self.backup_state = "unknown"
        self.backup_age_seconds = None
        self.restore_test_days = 0.0
        self.last_ping = {}
        self.ping_failures = {target: 0 for target in PING_TARGETS}
        self.last_ping_status = {}
        self._lock = threading.Lock()

    # -- Prometheus --------------------------------------------------------
    def prom_scalar(self, expression):
        url = "%s/api/v1/query?%s" % (
            self.config.prometheus_url,
            urllib.parse.urlencode({"query": expression}),
        )
        try:
            payload = self.json_get(url, timeout=self.config.request_timeout)
        except Exception as exc:  # noqa: BLE001 - brak Prometheusa => fallback lokalny
            log("Prometheus nie odpowiada (%s): %s", expression[:48], exc)
            return None
        results = ((payload or {}).get("data") or {}).get("result") or []
        values = []
        for item in results:
            try:
                values.append(float((item.get("value") or [None, None])[1]))
            except (TypeError, ValueError, IndexError):
                continue
        return max(values) if values else None

    # -- sprawdzenia -------------------------------------------------------
    def disk_free_percent(self):
        """Wolne miejsce na '/' — najpierw Prometheus (host), potem lokalny statvfs."""
        available = self.prom_scalar('node_filesystem_avail_bytes{mountpoint="/"}')
        size = self.prom_scalar('node_filesystem_size_bytes{mountpoint="/"}')
        if available is not None and size:
            return (available / size) * 100.0, "prometheus"
        try:
            stats = self.statvfs("/")
            total = stats.f_blocks * stats.f_frsize
            free = stats.f_bavail * stats.f_frsize
            if total:
                log("Używam statvfs('/') zamiast Prometheusa")
                return (free / total) * 100.0, "statvfs"
        except Exception as exc:  # noqa: BLE001 - brak danych => check czerwony
            log_error("statvfs('/') nie powiodło się: %s", exc)
        return None, "none"

    def inodes_free_percent(self):
        free = self.prom_scalar('node_filesystem_files_free{mountpoint="/"}')
        total = self.prom_scalar('node_filesystem_files{mountpoint="/"}')
        if free is not None and total:
            return (free / total) * 100.0, "prometheus"
        try:
            stats = self.statvfs("/")
            if stats.f_files:
                return (stats.f_ffree / stats.f_files) * 100.0, "statvfs"
        except Exception as exc:  # noqa: BLE001
            log_error("statvfs('/') dla i-węzłów nie powiodło się: %s", exc)
        return None, "none"

    def check_disk(self):
        percent, source = self.disk_free_percent()
        if percent is None:
            return CheckOutcome(False, "brak danych o wolnym miejscu na /")
        ok = percent > self.config.disk_min_free_percent
        return CheckOutcome(
            ok,
            "wolne %.1f%% na / (próg %.1f%%, źródło: %s)"
            % (percent, self.config.disk_min_free_percent, source),
            {"percent": percent, "source": source},
        )

    def check_inodes(self):
        percent, source = self.inodes_free_percent()
        if percent is None:
            return CheckOutcome(False, "brak danych o wolnych i-węzłach na /")
        ok = percent > self.config.inodes_min_free_percent
        return CheckOutcome(
            ok,
            "wolne %.1f%% i-węzłów na / (próg %.1f%%, źródło: %s)"
            % (percent, self.config.inodes_min_free_percent, source),
            {"percent": percent, "source": source},
        )

    def fetch_discovery_metrics(self):
        """(CheckOutcome błędu lub None, próbki metryk discovery)."""
        try:
            text = self.text_get(self.config.discovery_url + "/metrics", self.config.request_timeout)
        except Exception as exc:  # noqa: BLE001 - discovery może nie odpowiadać
            return CheckOutcome(False, "discovery /metrics niedostępny: %s" % exc), []
        return None, parse_prometheus_text(text)

    def check_services(self, samples=None):
        if samples is None:
            error, samples = self.fetch_discovery_metrics()
            if error is not None:
                return error
        if not any(name == "swarm_service_running_replicas" for name, _labels, _value in samples):
            return CheckOutcome(False, "brak metryk replik w ekspozycji discovery")
        failing = failing_services(samples, self.config.services_ignore_stacks)
        if failing:
            return CheckOutcome(False, "repliki poniżej desired: %s" % ", ".join(failing[:6]))
        return CheckOutcome(True, "wszystkie usługi mają pełne repliki")

    def check_http(self):
        try:
            payload = self.json_get(
                self.config.discovery_url + "/status/api.json", timeout=self.config.request_timeout
            )
        except Exception as exc:  # noqa: BLE001
            return CheckOutcome(False, "discovery /status/api.json niedostępny: %s" % exc)
        checks = (payload or {}).get("checks") or []
        critical = [item for item in checks if str(item.get("state")) == "critical"]
        if critical:
            names = ", ".join("%s/%s" % (item.get("group", "?"), item.get("name", "?")) for item in critical[:6])
            return CheckOutcome(False, "krytyczne sondy HTTP: %s" % names)
        return CheckOutcome(True, "brak krytycznych sond (%d sprawdzonych)" % len(checks))

    def check_certs(self, samples=None):
        if samples is None:
            error, samples = self.fetch_discovery_metrics()
            if error is not None:
                return error
        days = min_cert_days(samples)
        if days is None:
            return CheckOutcome(False, "brak danych o certyfikatach w metrykach discovery")
        ok = days > self.config.cert_min_days
        return CheckOutcome(
            ok,
            "najkrótszy certyfikat wygasa za %.1f dni (próg %.1f)" % (days, self.config.cert_min_days),
            {"days_left": days},
        )

    def check_backup(self):
        try:
            containers = self.docker.containers()
        except Exception as exc:  # noqa: BLE001 - brak Dockera => backup nieznany
            return CheckOutcome(False, "Docker API niedostępne: %s" % exc), BackupInfo()
        container = find_backup_container(containers, self.config.backup_service)
        if container is None:
            return CheckOutcome(
                False, "nie znaleziono kontenera usługi %s" % self.config.backup_service
            ), BackupInfo()
        container_id = container.get("Id") or ""
        try:
            raw = self.docker.container_logs(container_id, tail=2000)
        except Exception as exc:  # noqa: BLE001
            return CheckOutcome(False, "nie mogę odczytać logów backupu: %s" % exc), BackupInfo()
        text = parse_docker_log_stream(raw)
        try:
            info = extract_backup_info(text, self.config.backup_success_regex or None)
        except ValueError as exc:
            return CheckOutcome(False, str(exc)), BackupInfo()
        if info.last_success_at is None:
            return CheckOutcome(
                False,
                "brak znacznika sukcesu w logach %s (ustaw BACKUP_SUCCESS_REGEX)" % self.config.backup_service,
            ), info
        age_seconds = (datetime.now(timezone.utc) - info.last_success_at).total_seconds()
        age_hours = age_seconds / 3600.0
        problems = []
        if age_hours >= self.config.backup_max_age_hours:
            problems.append("wiek %.1f h >= %.1f h" % (age_hours, self.config.backup_max_age_hours))
        if self.config.backup_min_size_mb > 0 and info.size_bytes is not None:
            size_mb = info.size_bytes / 1e6
            if size_mb < self.config.backup_min_size_mb:
                problems.append("rozmiar %.1f MB < %.1f MB" % (size_mb, self.config.backup_min_size_mb))
        extra = ""
        if info.size_bytes is None and self.config.backup_min_size_mb > 0:
            extra = " (rozmiaru nie wykryto w logach — sprawdzam tylko wiek)"
            log("Nie wykryto rozmiaru backupu w logach — kryterium rozmiaru pominięte")
        if info.weak_match:
            extra += " (dopasowanie słabe: nazwa pliku bez znacznika sukcesu)"
            log("Backup dopasowany słabo (tylko nazwa pliku .dump/.age) — zweryfikuj BACKUP_SUCCESS_REGEX")
        detail = "ostatni sukces %.1f h temu%s" % (age_hours, extra)
        return CheckOutcome(not problems, detail if not problems else "; ".join(problems) + extra), info

    def check_restore_test(self):
        path = self.config.restore_test_file
        data = None
        if path:
            try:
                data = json.loads(self.file_reader(path) or "null")
            except FileNotFoundError:
                log("Brak pliku %s — przyjmuję, że odtworzenia nigdy nie testowano", path)
            except Exception as exc:  # noqa: BLE001
                log_error("Nie mogę odczytać %s: %s", path, exc)
        last_test = parse_rfc3339((data or {}).get("last_test_at")) if isinstance(data, dict) else None
        if last_test is None:
            return CheckOutcome(False, "nigdy nie testowano odtworzenia backupu (%s)" % path, {"days": 0.0})
        days = (datetime.now(timezone.utc) - last_test).total_seconds() / 86400.0
        ok = days < self.config.restore_test_max_days
        return CheckOutcome(
            ok,
            "test odtworzenia %.1f dni temu (próg %.1f)" % (days, self.config.restore_test_max_days),
            {"days": days},
        )

    def check_alertmanager(self):
        url = self.config.alertmanager_url + "/-/healthy"
        try:
            status = self.status_get(url, self.config.request_timeout)
        except Exception as exc:  # noqa: BLE001
            return CheckOutcome(False, "Alertmanager niedostępny: %s" % exc)
        if status == 200:
            return CheckOutcome(True, "Alertmanager odpowiada 200")
        return CheckOutcome(False, "Alertmanager /-/healthy zwrócił HTTP %s" % status)

    # -- przebieg ----------------------------------------------------------
    def run_once(self):
        results = {}
        results["disk"] = self.check_disk()
        results["inodes"] = self.check_inodes()
        metric_error, samples = self.fetch_discovery_metrics()
        results["services"] = metric_error if metric_error is not None else self.check_services(samples)
        results["certs"] = metric_error if metric_error is not None else self.check_certs(samples)
        results["http"] = self.check_http()
        backup_outcome, backup_info = self.check_backup()
        results["backup"] = backup_outcome
        results["restore_test"] = self.check_restore_test()
        results["alertmanager"] = self.check_alertmanager()
        missing = [name for name in CHECKS if name not in results]
        for name in missing:  # bezpieczeństwo: zawsze komplet wyników
            results[name] = CheckOutcome(False, "sprawdzenie nie zostało wykonane")

        all_ok = all(results[name].ok for name in CHECKS)
        with self._lock:
            self.results = results
            self.all_ok = all_ok
            self.up = True
            self.last_run = self.clock()
            self.backup_info = backup_info
            self.backup_age_seconds = (
                (datetime.now(timezone.utc) - backup_info.last_success_at).total_seconds()
                if backup_info.last_success_at
                else None
            )
            self.restore_test_days = float(results["restore_test"].data.get("days") or 0.0)
            if backup_info.last_success_at is None:
                self.backup_state = "unknown"
            elif not backup_outcome.ok and self.backup_age_seconds > self.config.backup_max_age_hours * 3600 * 2:
                self.backup_state = "critical"
            elif backup_outcome.ok:
                self.backup_state = "ok"
            else:
                self.backup_state = "warning"
        log(
            "Przebieg zakończony: all_ok=%s, problemy=%s",
            all_ok,
            [name for name in CHECKS if not results[name].ok] or "brak",
        )
        self.send_pings(results, all_ok)
        return all_ok

    def send_pings(self, results, all_ok):
        failing = [name for name in CHECKS if not results[name].ok]
        if all_ok:
            message = "OK"
        else:
            message = "PROBLEM: " + "; ".join("%s: %s" % (name, results[name].detail) for name in failing)
        self._do_ping("all_ok", self.config.hc_ping_all_ok, all_ok, message)
        backup_ok = results["backup"].ok
        self._do_ping(
            "backup",
            self.config.hc_ping_backup,
            backup_ok,
            "backup: %s" % results["backup"].detail,
        )

    def _do_ping(self, target, url, ok, message):
        if not url:
            log("Ping %s pominięty — brak URL w konfiguracji", target)
            with self._lock:
                self.last_ping_status[target] = None
            return None
        result = self.ping_fn(url, ok, message, self.config.ping_timeout)
        with self._lock:
            self.last_ping_status[target] = result
            if result:
                self.last_ping[target] = self.clock()
            elif result is False:
                self.ping_failures[target] = self.ping_failures.get(target, 0) + 1
        return result

    def run(self, stop_event):
        while not stop_event.is_set():
            try:
                self.run_once()
            except Exception as exc:  # noqa: BLE001 - pętla nie może umrzeć
                log_error("Nieoczekiwany błąd przebiegu: %s", exc)
                with self._lock:
                    self.up = False
            stop_event.wait(self.config.interval_seconds)

    # -- widoki ------------------------------------------------------------
    def state_view(self):
        with self._lock:
            return {
                "checks": CHECKS,
                "results": self.results,
                "all_ok": self.all_ok,
                "up": self.up,
                "last_run": self.last_run,
                "backup_age_seconds": self.backup_age_seconds,
                "backup_size_bytes": self.backup_info.size_bytes,
                "restore_test_age_days": self.restore_test_days,
                "last_ping": dict(self.last_ping),
                "ping_failures": dict(self.ping_failures),
            }

    def metrics(self):
        return render_metrics(self.state_view())

    def health(self):
        with self._lock:
            return {
                "status": "ok" if self.up else "starting",
                "up": bool(self.up),
                "all_ok": bool(self.all_ok),
                "last_run": iso_z(self.last_run) if self.last_run else None,
                "checks": {name: (1 if outcome.ok else 0) for name, outcome in self.results.items()},
                "details": {name: outcome.detail for name, outcome in self.results.items()},
            }

    def backup_json(self):
        with self._lock:
            info = self.backup_info
            return {
                "state": self.backup_state,
                "last_success_at": iso_z(info.last_success_at.timestamp()) if info.last_success_at else None,
                "age_hours": (
                    round(self.backup_age_seconds / 3600.0, 2) if self.backup_age_seconds is not None else None
                ),
                "size_bytes": int(info.size_bytes or 0),
                "objects_in_r2": 0,  # brak dostępu do R2 z tego serwisu (patrz README)
                "restore_test_days": int(round(self.restore_test_days)),
            }


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
            self._send(code, json.dumps(payload, ensure_ascii=False), "application/json; charset=utf-8")

        def do_GET(self):  # noqa: N802
            route = urllib.parse.urlsplit(self.path).path
            route = route.rstrip("/") or "/"
            try:
                if route == "/health":
                    self._send_json(service.health())
                elif route == "/metrics":
                    self._send(200, service.metrics(), "text/plain; version=0.0.4; charset=utf-8")
                elif route == "/backup.json":
                    self._send_json(service.backup_json())
                elif route == "/":
                    self._send_json({"service": NAME, "endpoints": ["/health", "/metrics", "/backup.json"]})
                else:
                    self._send_json({"error": "nie znaleziono", "path": route}, 404)
            except Exception as exc:  # noqa: BLE001
                log_error("Błąd obsługi %s: %s", route, exc)
                try:
                    self._send_json({"error": str(exc)}, 500)
                except Exception:  # noqa: BLE001
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
    for warning in config.config_warnings:
        log("Ostrzeżenie: %s", warning)
    service = HealthPing(config)
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
    worker = threading.Thread(target=service.run, args=(stop_event,), name="checks", daemon=True)
    worker.start()
    log(
        "Start na porcie %d (interwał %ss, backup=%s, próg wieku %.0f h)",
        config.port, config.interval_seconds, config.backup_service, config.backup_max_age_hours,
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
