#!/usr/bin/env python3
"""
notifier — jedyne wyjście alertów (ntfy + e-mail).

Odbiera webhooki Alertmanagera, zdarzenia zewnętrzne (np. nieudane GitHub Actions)
oraz pingi watchdoga, i rozsyła powiadomienia dwoma niezależnymi kanałami.
Błąd jednego kanału nigdy nie przerywa drugiego.

Zero zależności zewnętrznych — tylko biblioteka standardowa Pythona.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import smtplib
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from email.message import EmailMessage
from email.utils import formatdate
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

NAME = "notifier"
DEFAULT_PORT = 8080
DEFAULT_NTFY_URL = "https://ntfy.sh"
DEFAULT_ALERT_BASE_URL = ""
MAX_BODY_BYTES = 1024 * 1024
GROUP_LIMIT = 10
SEVERITY_RANK = {"info": 0, "warning": 1, "critical": 2}

CHANNELS = ("ntfy", "email")
STATUSES = ("sent", "failed", "skipped")


# --------------------------------------------------------------------------
# Logowanie (stderr, prefiks [notifier])
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
def _env_bool(env, key, default=False):
    raw = env.get(key, "")
    if raw is None or str(raw).strip() == "":
        return bool(default)
    return str(raw).strip().lower() in ("1", "true", "yes", "tak", "on")


def _env_int(env, key, default):
    raw = env.get(key, "")
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return int(default)


class Config:
    def __init__(self, env=None):
        env = dict(os.environ if env is None else env)
        self.env = env
        self.ntfy_url = (env.get("NTFY_URL", DEFAULT_NTFY_URL) or DEFAULT_NTFY_URL).rstrip("/")
        self.ntfy_topic = (env.get("NTFY_TOPIC", "") or "").strip()
        self.ntfy_token = (env.get("NTFY_TOKEN", "") or "").strip()
        self.ntfy_priority_critical = (env.get("NTFY_PRIORITY_CRITICAL", "urgent") or "urgent").strip()
        self.ntfy_priority_warning = (env.get("NTFY_PRIORITY_WARNING", "default") or "default").strip()
        self.smtp_host = (env.get("SMTP_HOST", "") or "").strip()
        self.smtp_port = _env_int(env, "SMTP_PORT", 587)
        self.smtp_secure = _env_bool(env, "SMTP_SECURE", False)
        self.smtp_username = (env.get("SMTP_USERNAME", "") or "").strip()
        self.smtp_password = env.get("SMTP_PASSWORD", "") or ""
        self.alert_email_from = (env.get("ALERT_EMAIL_FROM", "") or "").strip()
        self.alert_email_to = [
            item.strip() for item in (env.get("ALERT_EMAIL_TO", "") or "").split(",") if item.strip()
        ]
        self.email_min_severity = (
            env.get("EMAIL_MIN_SEVERITY", "warning") or "warning"
        ).strip().lower()
        self.alert_base_url = (env.get("ALERT_BASE_URL", DEFAULT_ALERT_BASE_URL) or "").strip()
        self.hc_ping_monitoring = (env.get("HC_PING_MONITORING", "") or "").strip()
        self.watchdog_ping = (env.get("WATCHDOG_PING", "") or "").strip()
        self.notifier_token = (env.get("NOTIFIER_TOKEN", "") or "").strip()
        self.port = _env_int(env, "PORT", DEFAULT_PORT)
        self.timeout = 10.0

    @property
    def sender_address(self):
        return self.alert_email_from or self.smtp_username or "monitoring@localhost"

    @property
    def watchdog_target(self):
        """
        WATCHDOG_PING może być flagą (0/false wyłącza) albo pełnym URL-em.
        Domyślnie używamy HC_PING_MONITORING.
        """
        raw = self.watchdog_ping.strip().lower()
        if raw in ("0", "false", "no", "off", "nie"):
            return None
        if self.watchdog_ping.lower().startswith("http"):
            return self.watchdog_ping
        return self.hc_ping_monitoring or None

    @property
    def config_warnings(self):
        warnings = []
        if not self.ntfy_topic:
            warnings.append("NTFY_TOPIC nie jest ustawione — kanał ntfy będzie pomijany (skipped)")
        if not self.smtp_host or not self.alert_email_to:
            warnings.append("SMTP_HOST/ALERT_EMAIL_TO nie są ustawione — kanał e-mail będzie pomijany")
        if not self.notifier_token:
            warnings.append("NOTIFIER_TOKEN nie jest ustawiony — POST /alert będzie zawsze zwracał 403")
        if not self.watchdog_target:
            warnings.append("HC_PING_MONITORING/WATCHDOG_PING nie są ustawione — /watchdog nic nie wyśle")
        return warnings


def severity_rank(value):
    return SEVERITY_RANK.get(str(value or "").strip().lower(), 1)


def normalize_severity(value):
    severity = str(value or "").strip().lower()
    return severity if severity in SEVERITY_RANK else "warning"


def token_matches(provided, expected):
    """Porównanie tokenów bez wycieku czasu (hashlib, bez hmac)."""
    if not expected:
        return False
    return hashlib.sha256(str(provided or "").encode("utf-8")).digest() == hashlib.sha256(
        expected.encode("utf-8")
    ).digest()


def alert_authorized(provided_token, config):
    """Autoryzacja POST /alert: brak tokenu w konfiguracji = fail-closed (403)."""
    if not config.notifier_token:
        return False
    return token_matches(provided_token, config.notifier_token)


# --------------------------------------------------------------------------
# Model alertu i grupy
# --------------------------------------------------------------------------
class Alert:
    __slots__ = (
        "status",
        "name",
        "severity",
        "stack",
        "summary",
        "description",
        "starts_at",
        "ends_at",
        "labels",
        "annotations",
        "url",
    )

    def __init__(self, status, name, severity, stack, summary, description,
                 starts_at="", ends_at="", labels=None, annotations=None, url=""):
        self.status = status
        self.name = name
        self.severity = severity
        self.stack = stack
        self.summary = summary
        self.description = description
        self.starts_at = starts_at
        self.ends_at = ends_at
        self.labels = labels or {}
        self.annotations = annotations or {}
        self.url = url

    @property
    def resolved(self):
        return self.status == "resolved"

    def one_line(self):
        suffix = " · " + self.stack if self.stack else ""
        return "%s%s" % (self.name, suffix)


def normalize_alert(raw):
    """Pojedynczy alert z webhooka Alertmanagera -> Alert."""
    raw = raw or {}
    labels = raw.get("labels") or {}
    annotations = raw.get("annotations") or {}
    name = labels.get("alertname") or "alert"
    summary = annotations.get("summary") or annotations.get("description") or ""
    description = annotations.get("description") or ""
    return Alert(
        status=str(raw.get("status") or "firing").strip().lower(),
        name=name,
        severity=normalize_severity(labels.get("severity")),
        stack=labels.get("stack") or labels.get("namespace") or "",
        summary=summary,
        description=description,
        starts_at=raw.get("startsAt") or "",
        ends_at=raw.get("endsAt") or "",
        labels=labels,
        annotations=annotations,
    )


class NotificationGroup:
    """Grupa alertów z jednego webhooka — jedno powiadomienie na kanał."""

    __slots__ = ("status", "alerts")

    def __init__(self, alerts, status=None):
        self.alerts = list(alerts)
        if status is None:
            status = "resolved" if self.alerts and all(alert.resolved for alert in self.alerts) else "firing"
        self.status = status

    @property
    def severity(self):
        if not self.alerts:
            return "info"
        return max((alert.severity for alert in self.alerts), key=severity_rank)

    @property
    def headline(self):
        return self.alerts[0].name if self.alerts else "alert"

    @property
    def stack(self):
        for alert in self.alerts:
            if alert.stack:
                return alert.stack
        return ""

    @property
    def status_label(self):
        return "RESOLVED" if self.status == "resolved" else self.severity.upper()

    def overflow(self, limit=GROUP_LIMIT):
        return max(0, len(self.alerts) - limit)


def group_from_webhook(payload):
    """Webhook Alertmanagera -> NotificationGroup (albo None, gdy brak alertów)."""
    alerts = [normalize_alert(item) for item in (payload or {}).get("alerts") or []]
    if not alerts:
        return None
    status = str((payload or {}).get("status") or "").strip().lower()
    if status not in ("firing", "resolved"):
        status = None
    return NotificationGroup(alerts, status)


def group_from_event(title, message, severity, url=""):
    """Zdarzenie z POST /alert -> NotificationGroup."""
    severity = normalize_severity(severity)
    alert = Alert(
        status="firing",
        name=title or "zdarzenie",
        severity=severity,
        stack="",
        summary=message or title or "",
        description=message or "",
        url=url or "",
    )
    return NotificationGroup([alert], "firing")


# --------------------------------------------------------------------------
# Treść powiadomień
# --------------------------------------------------------------------------
def ntfy_priority(severity, config):
    severity = normalize_severity(severity)
    if severity == "critical":
        return config.ntfy_priority_critical or "urgent"
    if severity == "warning":
        return config.ntfy_priority_warning or "default"
    return "low"


def ntfy_tags(group, severity):
    if group.status == "resolved":
        return "white_check_mark"
    return {"critical": "rotating_light", "warning": "warning", "info": "information_source"}.get(
        normalize_severity(severity), "warning"
    )


def build_ntfy_message(group, config):
    """
    Tytuł: [CRITICAL] <alertname> · <stack> (lub [RESOLVED]).
    Treść: summary + description, lista grupy (maks. 10) i link do panelu.
    """
    headline = group.headline
    if len(group.alerts) > 1:
        headline = "%s (+%d)" % (headline, len(group.alerts) - 1)
    title = "[%s] %s" % (group.status_label, headline)
    if group.stack:
        title += " · %s" % group.stack

    lines = []
    if len(group.alerts) == 1:
        alert = group.alerts[0]
        if alert.summary:
            lines.append(alert.summary)
        if alert.description and alert.description != alert.summary:
            lines.append(alert.description)
        if not lines:
            lines.append(alert.name)
    else:
        lines.append("Alertów w grupie: %d" % len(group.alerts))
        for alert in group.alerts[:GROUP_LIMIT]:
            lines.append("- [%s] %s" % (alert.severity.upper(), alert.one_line()))
            if alert.summary:
                lines.append("  %s" % alert.summary)
        remaining = group.overflow()
        if remaining > 0:
            lines.append("…i %d więcej" % remaining)
    base = config.alert_base_url
    if base:
        lines.append("")
        lines.append("Panel: %s" % base)
    return {
        "title": title,
        "priority": ntfy_priority(group.severity, config),
        "tags": ntfy_tags(group, group.severity),
        "body": "\n".join(lines),
    }


def should_send_email(severity, config):
    """E-mail tylko dla severity >= EMAIL_MIN_SEVERITY."""
    return severity_rank(severity) >= severity_rank(config.email_min_severity)


def build_email(group, config):
    severity = group.severity
    status = "resolved" if group.status == "resolved" else "firing"
    subject = "[monitoring] %s %s (%s)" % (status, group.headline, group.stack or "-")
    lines = []
    if len(group.alerts) == 1:
        alert = group.alerts[0]
        lines.append("Alert: %s" % alert.name)
        if alert.stack:
            lines.append("Stack: %s" % alert.stack)
        lines.append("Severity: %s" % alert.severity)
        lines.append("Status: %s" % alert.status)
        if alert.starts_at:
            lines.append("Od: %s" % alert.starts_at)
        if alert.ends_at:
            lines.append("Do: %s" % alert.ends_at)
        lines.append("")
        if alert.summary:
            lines.append(alert.summary)
        if alert.description and alert.description != alert.summary:
            lines.append("")
            lines.append(alert.description)
    else:
        lines.append("Alertów w grupie: %d (severity: %s)" % (len(group.alerts), severity))
        lines.append("")
        for alert in group.alerts[:GROUP_LIMIT]:
            lines.append("- [%s] %s" % (alert.severity.upper(), alert.one_line()))
            if alert.summary:
                lines.append("  %s" % alert.summary)
        remaining = group.overflow()
        if remaining > 0:
            lines.append("…i %d więcej" % remaining)
    if config.alert_base_url:
        lines.append("")
        lines.append("Panel: %s" % config.alert_base_url)
    return {"subject": subject, "body": "\n".join(lines)}


# --------------------------------------------------------------------------
# Wysyłka: ntfy
# --------------------------------------------------------------------------
def http_post(url, body, headers=None, timeout=10.0, method="POST"):
    """POST zwracający kod HTTP (4xx/5xx jako kod, nie wyjątek)."""
    data = body.encode("utf-8") if isinstance(body, str) else (body or b"")
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("User-Agent", "monitoring-%s/1.0" % NAME)
    request.add_header("Content-Type", "text/plain; charset=utf-8")
    for key, value in (headers or {}).items():
        request.add_header(key, value)
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


def send_ntfy(message, config, poster=None):
    """('sent'|'failed'|'skipped', szczegóły)."""
    if not config.ntfy_topic:
        return "skipped", "NTFY_TOPIC nie jest ustawione"
    poster = poster or http_post
    url = "%s/%s" % (config.ntfy_url.rstrip("/"), urllib.parse.quote(config.ntfy_topic))
    headers = {
        "Title": message["title"],
        "Priority": str(message["priority"]),
        "Tags": message["tags"],
    }
    if config.ntfy_token:
        headers["Authorization"] = "Bearer %s" % config.ntfy_token
    try:
        status = poster(url, message["body"], headers, config.timeout)
    except Exception as exc:  # noqa: BLE001 - kanał nie może wywalić całości
        log_error("ntfy: wysyłka nie powiodła się: %s", exc)
        return "failed", str(exc)
    if 200 <= status < 300:
        log("ntfy: wysłano „%s” (HTTP %d)", message["title"], status)
        return "sent", "HTTP %d" % status
    log_error("ntfy: HTTP %d dla „%s”", status, message["title"])
    return "failed", "HTTP %d" % status


# --------------------------------------------------------------------------
# Wysyłka: e-mail
# --------------------------------------------------------------------------
def default_smtp_factory(host, port, timeout, secure):
    if secure:
        return smtplib.SMTP_SSL(host, port, timeout=timeout)
    client = smtplib.SMTP(host, port, timeout=timeout)
    client.starttls()
    return client


def send_email(message, config, smtp_factory=None):
    """('sent'|'failed'|'skipped', szczegóły)."""
    if not config.smtp_host or not config.alert_email_to:
        return "skipped", "SMTP_HOST/ALERT_EMAIL_TO nie są ustawione"
    smtp_factory = smtp_factory or default_smtp_factory
    email = EmailMessage()
    email["Subject"] = message["subject"]
    email["From"] = config.sender_address
    email["To"] = ", ".join(config.alert_email_to)
    email["Date"] = formatdate(localtime=True)
    email.set_content(message["body"])
    client = None
    try:
        client = smtp_factory(config.smtp_host, config.smtp_port, config.timeout, config.smtp_secure)
        if config.smtp_username:
            client.login(config.smtp_username, config.smtp_password)
        client.send_message(email)
        log("email: wysłano „%s” do %s", message["subject"], ", ".join(config.alert_email_to))
        return "sent", "wysłano do %d adresatów" % len(config.alert_email_to)
    except Exception as exc:  # noqa: BLE001 - kanał nie może wywalić całości
        log_error("email: wysyłka nie powiodła się: %s", exc)
        return "failed", str(exc)
    finally:
        if client is not None:
            try:
                client.quit()
            except Exception:  # noqa: BLE001 - zamknięcie jest best-effort
                try:
                    client.close()
                except Exception:  # noqa: BLE001
                    pass


# --------------------------------------------------------------------------
# Ekspozycja metryk Prometheusa
# --------------------------------------------------------------------------
METRIC_FAMILIES = (
    ("notifier_notifications_total", "counter", "Liczba powiadomień według kanału i statusu."),
    ("notifier_last_notification_timestamp_seconds", "gauge", "Czas ostatniego udanego powiadomienia."),
    ("notifier_watchdog_pings_total", "counter", "Liczba pingów watchdoga według statusu."),
    ("notifier_last_watchdog_ping_timestamp_seconds", "gauge", "Czas ostatniego udanego pingu watchdoga."),
    ("notifier_up", "gauge", "Czy notifier działa."),
)


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
    """Czysta funkcja: słownik stanu -> tekst exposition Prometheusa."""
    samples = []
    counters = state.get("counters") or {}
    for channel in CHANNELS:
        for status in STATUSES:
            samples.append(
                ("notifier_notifications_total", {"channel": channel, "status": status},
                 counters.get((channel, status), 0))
            )
    last_notification = state.get("last_notification") or {}
    for channel in CHANNELS:
        if channel in last_notification:
            samples.append(
                ("notifier_last_notification_timestamp_seconds", {"channel": channel}, last_notification[channel])
            )
    watchdog = state.get("watchdog_pings") or {}
    for status in ("sent", "failed"):
        samples.append(("notifier_watchdog_pings_total", {"status": status}, watchdog.get(status, 0)))
    if state.get("last_watchdog_ping"):
        samples.append(
            ("notifier_last_watchdog_ping_timestamp_seconds", {}, state["last_watchdog_ping"])
        )
    samples.append(("notifier_up", {}, 1 if state.get("up") else 0))

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


# --------------------------------------------------------------------------
# Serwis
# --------------------------------------------------------------------------
class NotifierService:
    def __init__(self, config, ntfy_sender=None, email_sender=None, smtp_factory=None,
                 poster=None, clock=time.time):
        self.config = config
        self.ntfy_sender = ntfy_sender or (
            lambda message: send_ntfy(message, config, poster)
        )
        self.email_sender = email_sender or (
            lambda message: send_email(message, config, smtp_factory)
        )
        self.clock = clock
        self.counters = {(channel, status): 0 for channel in CHANNELS for status in STATUSES}
        self.last_notification = {}
        self.watchdog_pings = {"sent": 0, "failed": 0}
        self.last_watchdog_ping = None
        self.up = True
        self._lock = threading.Lock()

    # -- kanały ------------------------------------------------------------
    def _ntfy_channel(self, group):
        return self.ntfy_sender(build_ntfy_message(group, self.config))

    def _email_channel(self, group):
        if not should_send_email(group.severity, self.config):
            return "skipped", "severity %s < EMAIL_MIN_SEVERITY=%s" % (
                group.severity, self.config.email_min_severity,
            )
        return self.email_sender(build_email(group, self.config))

    def dispatch_group(self, group):
        """
        Wysyła grupę oboma kanałami. Błąd jednego kanału nie przerywa drugiego.

        Kod odpowiedzi: 200 gdy cokolwiek wysłano (albo wszystkie kanały są
        nieskonfigurowane — ponawianie nic nie da), 500 gdy kanały próbowały
        wysłać i wszystkie zawiodły.
        """
        outcomes = {}
        for channel, handler in (("ntfy", self._ntfy_channel), ("email", self._email_channel)):
            try:
                status, detail = handler(group)
            except Exception as exc:  # noqa: BLE001 - izolacja kanałów
                log_error("%s: nieoczekiwany błąd: %s", channel, exc)
                status, detail = "failed", str(exc)
            if status not in STATUSES:
                status = "failed"
            outcomes[channel] = (status, detail)
            with self._lock:
                self.counters[(channel, status)] = self.counters.get((channel, status), 0) + 1
                if status == "sent":
                    self.last_notification[channel] = self.clock()
            log("Kanał %s: %s (%s)", channel, status, detail)

        sent = [channel for channel, (status, _) in outcomes.items() if status == "sent"]
        failed = [channel for channel, (status, _) in outcomes.items() if status == "failed"]
        if sent:
            code = 200
        elif failed:
            code = 500
        else:
            code = 200
        body = {
            "status": "sent" if sent else ("failed" if failed else "skipped"),
            "group": {
                "status": group.status,
                "severity": group.severity,
                "alerts": len(group.alerts),
                "headline": group.headline,
            },
            "channels": {channel: {"status": status, "detail": detail}
                         for channel, (status, detail) in outcomes.items()},
        }
        return code, body

    # -- wejścia -----------------------------------------------------------
    def handle_webhook(self, payload):
        group = group_from_webhook(payload)
        if group is None:
            return 400, {"error": "webhook nie zawiera żadnych alertów"}
        return self.dispatch_group(group)

    def handle_event(self, payload):
        if not isinstance(payload, dict):
            return 400, {"error": "treść musi być obiektem JSON"}
        title = str(payload.get("title") or "").strip()
        message = str(payload.get("message") or "").strip()
        if not title and not message:
            return 400, {"error": "wymagane jest pole 'title' lub 'message'"}
        group = group_from_event(title, message, payload.get("severity"), str(payload.get("url") or ""))
        return self.dispatch_group(group)

    def handle_watchdog(self):
        target = self.config.watchdog_target
        if not target:
            log_error("Watchdog: brak skonfigurowanego URL (HC_PING_MONITORING/WATCHDOG_PING)")
            with self._lock:
                self.watchdog_pings["failed"] += 1
            return 500, {"status": "failed", "error": "brak skonfigurowanego URL watchdoga"}
        try:
            status = http_post(target, "watchdog ok", {}, self.config.timeout)
        except Exception as exc:  # noqa: BLE001 - brak sieci nie może wywalić serwisu
            log_error("Watchdog: ping nie powiódł się: %s", exc)
            with self._lock:
                self.watchdog_pings["failed"] += 1
            return 500, {"status": "failed", "error": str(exc)}
        if 200 <= status < 300:
            with self._lock:
                self.watchdog_pings["sent"] += 1
                self.last_watchdog_ping = self.clock()
            log("Watchdog: ping OK (HTTP %d)", status)
            return 200, {"status": "sent", "http_status": status}
        log_error("Watchdog: ping zwrócił HTTP %d", status)
        with self._lock:
            self.watchdog_pings["failed"] += 1
        return 500, {"status": "failed", "http_status": status}

    # -- widoki ------------------------------------------------------------
    def state_view(self):
        with self._lock:
            return {
                "counters": dict(self.counters),
                "last_notification": dict(self.last_notification),
                "watchdog_pings": dict(self.watchdog_pings),
                "last_watchdog_ping": self.last_watchdog_ping,
                "up": self.up,
            }

    def metrics(self):
        return render_metrics(self.state_view())

    def health(self):
        return {
            "status": "ok" if self.up else "degraded",
            "up": bool(self.up),
            "ntfy_configured": bool(self.config.ntfy_topic),
            "email_configured": bool(self.config.smtp_host and self.config.alert_email_to),
            "token_configured": bool(self.config.notifier_token),
            "watchdog_configured": bool(self.config.watchdog_target),
            "warnings": self.config.config_warnings,
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

        def _read_body(self):
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except (TypeError, ValueError):
                length = 0
            if length <= 0:
                return b""
            if length > MAX_BODY_BYTES:
                raise ValueError("treść żądania przekracza limit %d B" % MAX_BODY_BYTES)
            return self.rfile.read(length)

        def _read_json(self):
            raw = self._read_body()
            if not raw:
                return None
            return json.loads(raw.decode("utf-8", "replace"))

        def do_GET(self):  # noqa: N802
            route = urllib.parse.urlsplit(self.path).path
            route = route.rstrip("/") or "/"
            try:
                if route == "/health":
                    self._send_json(service.health())
                elif route == "/metrics":
                    self._send(200, service.metrics(), "text/plain; version=0.0.4; charset=utf-8")
                elif route == "/":
                    self._send_json(
                        {"service": NAME, "endpoints": ["/health", "/metrics"],
                         "webhooks": ["/webhook", "/watchdog", "/alert"]}
                    )
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

        def do_POST(self):  # noqa: N802
            route = urllib.parse.urlsplit(self.path).path
            route = route.rstrip("/") or "/"
            try:
                if route == "/webhook":
                    payload = self._read_json()
                    if payload is None:
                        self._send_json({"error": "puste ciało żądania"}, 400)
                        return
                    code, body = service.handle_webhook(payload)
                    self._send_json(body, code)
                elif route == "/watchdog":
                    code, body = service.handle_watchdog()
                    self._send_json(body, code)
                elif route == "/alert":
                    if not alert_authorized(self.headers.get("X-Auth-Token"), service.config):
                        log("POST /alert odrzucony: brak lub zły X-Auth-Token")
                        self._send_json({"error": "forbidden"}, 403)
                        return
                    payload = self._read_json()
                    if payload is None:
                        self._send_json({"error": "puste ciało żądania"}, 400)
                        return
                    code, body = service.handle_event(payload)
                    self._send_json(body, code)
                else:
                    self._send_json({"error": "nie znaleziono", "path": route}, 404)
            except ValueError as exc:
                self._send_json({"error": str(exc)}, 400)
            except json.JSONDecodeError as exc:
                self._send_json({"error": "nieprawidłowy JSON: %s" % exc}, 400)
            except Exception as exc:  # noqa: BLE001
                log_error("Błąd obsługi %s: %s", route, exc)
                try:
                    self._send_json({"error": str(exc)}, 500)
                except Exception:  # noqa: BLE001
                    pass

        def _reject(self):
            self._send_json({"error": "metoda niedozwolona"}, 405)

        do_PUT = _reject  # noqa: N815
        do_DELETE = _reject  # noqa: N815
        do_PATCH = _reject  # noqa: N815

    return Handler


def main():
    config = Config()
    for warning in config.config_warnings:
        log("Ostrzeżenie: %s", warning)
    service = NotifierService(config)
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
    log(
        "Start na porcie %d (ntfy=%s, topic=%s, email=%s)",
        config.port, config.ntfy_url, config.ntfy_topic or "-",
        "tak" if (config.smtp_host and config.alert_email_to) else "nie",
    )
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        server.server_close()
        log("Zamknięty")
    return 0


if __name__ == "__main__":
    sys.exit(main())
