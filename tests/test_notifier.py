"""Testy jednostkowe serwisu `notifier`.

Zero sieci i zero SMTP: kanały ntfy/e-mail są wstrzykiwanymi atrapami,
a budowa wiadomości to czyste funkcje.
"""

import importlib.util
import json
import pathlib
import re
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def load_module(name, relative_path):
    spec = importlib.util.spec_from_file_location(name, str(ROOT / relative_path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


notifier = load_module("svc_notifier", "services/notifier/main.py")


# --------------------------------------------------------------------------
# Atrapy
# --------------------------------------------------------------------------
class RecordingSender:
    """Atrapa kanału: zapisuje wiadomości i udaje wybrany status."""

    def __init__(self, status="sent", detail="ok", raises=None):
        self.status = status
        self.detail = detail
        self.raises = raises
        self.messages = []

    def __call__(self, message):
        self.messages.append(message)
        if self.raises is not None:
            raise self.raises
        return self.status, self.detail

    @property
    def calls(self):
        return len(self.messages)


def make_config(**env):
    base = {
        "NTFY_URL": "https://ntfy.sh",
        "NTFY_TOPIC": "monitoring",
        "SMTP_HOST": "smtp.example.com",
        "ALERT_EMAIL_TO": "ops@example.com",
        "NOTIFIER_TOKEN": "sekret",
        "HC_PING_MONITORING": "https://hc-ping.com/watchdog",
        "ALERT_BASE_URL": "https://monitoring.subscribeit.pl",
    }
    base.update(env)
    return notifier.Config(env=base)


def make_alert(name="HighCpu", severity="critical", stack="monitoring", status="firing",
               summary="CPU 95%", description="Powyżej progu od 5 minut"):
    return {
        "status": status,
        "labels": {"alertname": name, "severity": severity, "stack": stack},
        "annotations": {"summary": summary, "description": description},
        "startsAt": "2026-09-21T18:00:00Z",
        "endsAt": "0001-01-01T00:00:00Z",
    }


def webhook(alerts, status="firing"):
    return {"version": "4", "status": status, "alerts": alerts}


def build_service(config=None, ntfy=None, email=None, poster=None):
    ntfy = ntfy if ntfy is not None else RecordingSender()
    email = email if email is not None else RecordingSender()
    service = notifier.NotifierService(
        config or make_config(),
        ntfy_sender=ntfy,
        email_sender=email,
        poster=poster or (lambda url, body, headers, timeout: 200),
        clock=lambda: 1758484800.0,
    )
    return service, ntfy, email


def sample_lines(text, metric):
    return [
        line for line in text.splitlines()
        if line.startswith(metric + " ") or line.startswith(metric + "{")
    ]


# --------------------------------------------------------------------------
# Budowa wiadomości ntfy
# --------------------------------------------------------------------------
class NtfyMessageTests(unittest.TestCase):
    def test_single_critical_alert(self):
        config = make_config()
        group = notifier.group_from_webhook(webhook([make_alert()]))
        message = notifier.build_ntfy_message(group, config)
        self.assertEqual(message["title"], "[CRITICAL] HighCpu · monitoring")
        self.assertEqual(message["priority"], "urgent")
        self.assertEqual(message["tags"], "rotating_light")
        self.assertIn("CPU 95%", message["body"])
        self.assertIn("Powyżej progu od 5 minut", message["body"])
        self.assertIn("https://monitoring.subscribeit.pl", message["body"])

    def test_resolved_title_and_tags(self):
        config = make_config()
        group = notifier.group_from_webhook(webhook([make_alert(status="resolved")], status="resolved"))
        message = notifier.build_ntfy_message(group, config)
        self.assertTrue(message["title"].startswith("[RESOLVED]"), message["title"])
        self.assertEqual(message["tags"], "white_check_mark")

    def test_warning_and_info_priorities(self):
        config = make_config()
        warning = notifier.group_from_webhook(webhook([make_alert(severity="warning")]))
        info = notifier.group_from_webhook(webhook([make_alert(severity="info")]))
        self.assertIn(notifier.build_ntfy_message(warning, config)["priority"], ("low", "min"))
        # info jest jeszcze cichsze niż warning — oba nie brzęczą
        self.assertEqual(notifier.build_ntfy_message(info, config)["priority"], "min")

    def test_custom_priorities_from_env(self):
        config = make_config(NTFY_PRIORITY_CRITICAL="max", NTFY_PRIORITY_WARNING="high")
        critical = notifier.group_from_webhook(webhook([make_alert(severity="critical")]))
        warning = notifier.group_from_webhook(webhook([make_alert(severity="warning")]))
        self.assertEqual(notifier.build_ntfy_message(critical, config)["priority"], "max")
        self.assertEqual(notifier.build_ntfy_message(warning, config)["priority"], "high")

    def test_group_severity_is_the_highest(self):
        group = notifier.group_from_webhook(webhook([
            make_alert(name="A", severity="warning"),
            make_alert(name="B", severity="critical"),
        ]))
        self.assertEqual(group.severity, "critical")

    def test_unknown_severity_falls_back_to_warning(self):
        group = notifier.group_from_webhook(webhook([make_alert(severity="dziwne")]))
        self.assertEqual(group.severity, "warning")

    def test_message_without_alert_base_url(self):
        message = notifier.build_ntfy_message(
            notifier.group_from_webhook(webhook([make_alert()])), make_config(ALERT_BASE_URL="")
        )
        self.assertNotIn("Panel:", message["body"])


class GroupingTests(unittest.TestCase):
    def test_group_is_one_notification_with_ten_items_plus_overflow(self):
        config = make_config()
        alerts = [make_alert(name="Alert%d" % index) for index in range(12)]
        group = notifier.group_from_webhook(webhook(alerts))
        message = notifier.build_ntfy_message(group, config)
        body = message["body"]
        self.assertEqual(message["title"], "[CRITICAL] Alert0 (+11) · monitoring")
        self.assertEqual(body.count("- [CRITICAL]"), 10)
        self.assertIn("…i 2 więcej", body)
        self.assertIn("Alertów w grupie: 12", body)
        self.assertNotIn("Alert11", body)
        self.assertEqual(group.overflow(), 2)

    def test_single_notification_for_whole_group(self):
        service, ntfy, email = build_service()
        code, body = service.handle_webhook(webhook([make_alert(name="A"), make_alert(name="B")]))
        self.assertEqual(code, 200)
        self.assertEqual(ntfy.calls, 1)
        self.assertEqual(email.calls, 1)
        self.assertEqual(body["group"]["alerts"], 2)

    def test_webhook_without_alerts_is_rejected(self):
        service, ntfy, _email = build_service()
        code, body = service.handle_webhook({"version": "4", "status": "firing", "alerts": []})
        self.assertEqual(code, 400)
        self.assertEqual(ntfy.calls, 0)
        self.assertIn("error", body)


# --------------------------------------------------------------------------
# Decyzja o e-mailu
# --------------------------------------------------------------------------
class EmailDecisionTests(unittest.TestCase):
    def test_info_is_skipped_by_default(self):
        service, ntfy, email = build_service()
        code, body = service.handle_webhook(webhook([make_alert(severity="info")]))
        self.assertEqual(code, 200)
        self.assertEqual(ntfy.calls, 1)
        self.assertEqual(email.calls, 0)
        self.assertEqual(body["channels"]["email"]["status"], "skipped")
        self.assertIn("EMAIL_MIN_SEVERITY", body["channels"]["email"]["detail"])

    def test_warning_and_critical_are_sent(self):
        for severity in ("warning", "critical"):
            with self.subTest(severity=severity):
                service, _ntfy, email = build_service()
                service.handle_webhook(webhook([make_alert(severity=severity)]))
                self.assertEqual(email.calls, 1)

    def test_min_severity_can_be_lowered(self):
        service, _ntfy, email = build_service(config=make_config(EMAIL_MIN_SEVERITY="info"))
        service.handle_webhook(webhook([make_alert(severity="info")]))
        self.assertEqual(email.calls, 1)

    def test_min_severity_can_be_raised_to_critical(self):
        service, _ntfy, email = build_service(config=make_config(EMAIL_MIN_SEVERITY="critical"))
        service.handle_webhook(webhook([make_alert(severity="warning")]))
        self.assertEqual(email.calls, 0)

    def test_should_send_email_helper(self):
        config = make_config()
        self.assertTrue(notifier.should_send_email("critical", config))
        self.assertTrue(notifier.should_send_email("warning", config))
        self.assertFalse(notifier.should_send_email("info", config))

    def test_email_subject_and_body(self):
        config = make_config()
        group = notifier.group_from_webhook(webhook([make_alert()]))
        message = notifier.build_email(group, config)
        self.assertEqual(message["subject"], "[monitoring] firing HighCpu (monitoring)")
        self.assertIn("Alert: HighCpu", message["body"])
        self.assertIn("Severity: critical", message["body"])
        self.assertIn("CPU 95%", message["body"])

    def test_email_subject_for_resolved(self):
        group = notifier.group_from_webhook(webhook([make_alert(status="resolved")], status="resolved"))
        self.assertEqual(notifier.build_email(group, make_config())["subject"],
                         "[monitoring] resolved HighCpu (monitoring)")

    def test_send_email_skipped_without_smtp_config(self):
        status, detail = notifier.send_email(
            {"subject": "s", "body": "b"}, make_config(SMTP_HOST="", ALERT_EMAIL_TO="")
        )
        self.assertEqual(status, "skipped")
        self.assertIn("SMTP_HOST", detail)

    def test_send_email_uses_smtp_factory(self):
        calls = {}

        class FakeSMTP:
            def __init__(self, host, port, timeout=None):
                calls["connect"] = (host, port, timeout)

            def starttls(self):
                calls["starttls"] = True

            def login(self, username, password):
                calls["login"] = (username, password)

            def send_message(self, message):
                calls["message"] = message

            def quit(self):
                calls["quit"] = True

        config = make_config(SMTP_SECURE="false", SMTP_USERNAME="user", SMTP_PASSWORD="pass")
        status, _detail = notifier.send_email(
            {"subject": "Temat", "body": "Treść"},
            config,
            smtp_factory=lambda host, port, timeout, secure: FakeSMTP(host, port, timeout),
        )
        self.assertEqual(status, "sent")
        self.assertEqual(calls["connect"][:2], ("smtp.example.com", 587))
        self.assertEqual(calls["login"], ("user", "pass"))
        self.assertEqual(calls["message"]["Subject"], "Temat")
        self.assertTrue(calls["quit"])

    def test_default_smtp_factory_uses_ssl_or_starttls(self):
        calls = {}

        class FakeSMTP:
            def __init__(self, host, port, timeout=None):
                calls["plain"] = (host, port, timeout)

            def starttls(self):
                calls["starttls"] = True

        class FakeSMTPSSL(FakeSMTP):
            def __init__(self, host, port, timeout=None):
                calls["ssl"] = (host, port, timeout)

        original_smtp, original_ssl = notifier.smtplib.SMTP, notifier.smtplib.SMTP_SSL
        notifier.smtplib.SMTP = FakeSMTP
        notifier.smtplib.SMTP_SSL = FakeSMTPSSL
        try:
            notifier.default_smtp_factory("smtp.example.com", 587, 5.0, False)
            self.assertIn("plain", calls)
            self.assertTrue(calls.get("starttls"))
            self.assertNotIn("ssl", calls)

            notifier.default_smtp_factory("smtp.example.com", 465, 5.0, True)
            self.assertEqual(calls["ssl"], ("smtp.example.com", 465, 5.0))
        finally:
            notifier.smtplib.SMTP = original_smtp
            notifier.smtplib.SMTP_SSL = original_ssl

    def test_send_email_reports_smtp_failure(self):
        def factory(host, port, timeout, secure):
            raise OSError("connection refused")

        status, detail = notifier.send_email({"subject": "s", "body": "b"}, make_config(),
                                             smtp_factory=factory)
        self.assertEqual(status, "failed")
        self.assertIn("connection refused", detail)

    def test_send_ntfy_skipped_without_topic(self):
        status, detail = notifier.send_ntfy(
            {"title": "t", "priority": "urgent", "tags": "x", "body": "b"}, make_config(NTFY_TOPIC="")
        )
        self.assertEqual(status, "skipped")
        self.assertIn("NTFY_TOPIC", detail)

    def test_send_ntfy_headers_and_body(self):
        sent = {}

        def poster(url, body, headers, timeout):
            sent.update({"url": url, "body": body, "headers": headers})
            return 200

        config = make_config(NTFY_TOKEN="tk_123")
        status, _detail = notifier.send_ntfy(
            {"title": "[CRITICAL] A · b", "priority": "urgent", "tags": "rotating_light", "body": "treść"},
            config,
            poster,
        )
        self.assertEqual(status, "sent")
        self.assertEqual(sent["url"], "https://ntfy.sh/monitoring")
        self.assertEqual(sent["headers"]["Title"], "[CRITICAL] A · b")
        self.assertEqual(sent["headers"]["Priority"], "urgent")
        self.assertEqual(sent["headers"]["Tags"], "rotating_light")
        self.assertEqual(sent["headers"]["Authorization"], "Bearer tk_123")
        self.assertEqual(sent["body"], "treść")

    def test_send_ntfy_without_token_has_no_authorization(self):
        sent = {}
        notifier.send_ntfy(
            {"title": "t", "priority": "low", "tags": "x", "body": "b"},
            make_config(NTFY_TOKEN=""),
            lambda url, body, headers, timeout: sent.update(headers) or 200,
        )
        self.assertNotIn("Authorization", sent)

    def test_send_ntfy_reports_http_error(self):
        status, detail = notifier.send_ntfy(
            {"title": "t", "priority": "low", "tags": "x", "body": "b"},
            make_config(),
            lambda url, body, headers, timeout: 500,
        )
        self.assertEqual(status, "failed")
        self.assertIn("500", detail)


# --------------------------------------------------------------------------
# Autoryzacja POST /alert
# --------------------------------------------------------------------------
class AlertAuthorizationTests(unittest.TestCase):
    def test_missing_token_is_rejected(self):
        self.assertFalse(notifier.alert_authorized(None, make_config()))
        self.assertFalse(notifier.alert_authorized("", make_config()))

    def test_wrong_token_is_rejected(self):
        self.assertFalse(notifier.alert_authorized("zly", make_config()))
        self.assertFalse(notifier.alert_authorized("sekret2", make_config()))

    def test_correct_token_is_accepted(self):
        self.assertTrue(notifier.alert_authorized("sekret", make_config()))

    def test_fail_closed_without_configured_token(self):
        config = make_config(NOTIFIER_TOKEN="")
        self.assertFalse(notifier.alert_authorized("cokolwiek", config))
        self.assertFalse(notifier.alert_authorized(None, config))

    def test_event_requires_title_or_message(self):
        service, ntfy, _email = build_service()
        code, body = service.handle_event({})
        self.assertEqual(code, 400)
        self.assertEqual(ntfy.calls, 0)
        self.assertIn("error", body)

    def test_event_is_dispatched(self):
        service, ntfy, email = build_service()
        code, body = service.handle_event(
            {"title": "GitHub Actions", "message": "Build failed", "severity": "critical",
             "url": "https://github.com/x/y/actions/runs/1"}
        )
        self.assertEqual(code, 200)
        self.assertEqual(ntfy.calls, 1)
        self.assertEqual(email.calls, 1)
        self.assertEqual(ntfy.messages[0]["title"], "[CRITICAL] GitHub Actions")
        self.assertIn("Build failed", ntfy.messages[0]["body"])

    def test_non_dict_event_is_rejected(self):
        service, _ntfy, _email = build_service()
        code, _body = service.handle_event(["nie", "obiekt"])
        self.assertEqual(code, 400)


# --------------------------------------------------------------------------
# Odporność kanałów
# --------------------------------------------------------------------------
class ChannelIsolationTests(unittest.TestCase):
    def test_ntfy_failure_does_not_stop_email(self):
        service, _ntfy, email = build_service(ntfy=RecordingSender(raises=RuntimeError("ntfy padło")))
        code, body = service.handle_webhook(webhook([make_alert()]))
        self.assertEqual(code, 200)
        self.assertEqual(body["channels"]["ntfy"]["status"], "failed")
        self.assertEqual(body["channels"]["email"]["status"], "sent")
        self.assertEqual(email.calls, 1)

    def test_email_failure_does_not_stop_ntfy(self):
        service, ntfy, _email = build_service(email=RecordingSender(raises=OSError("smtp padło")))
        code, body = service.handle_webhook(webhook([make_alert()]))
        self.assertEqual(code, 200)
        self.assertEqual(body["channels"]["email"]["status"], "failed")
        self.assertEqual(body["channels"]["ntfy"]["status"], "sent")
        self.assertEqual(ntfy.calls, 1)

    def test_both_channels_failing_gives_500(self):
        service, _ntfy, _email = build_service(
            ntfy=RecordingSender(status="failed"), email=RecordingSender(status="failed")
        )
        code, body = service.handle_webhook(webhook([make_alert()]))
        self.assertEqual(code, 500)
        self.assertEqual(body["status"], "failed")

    def test_all_channels_skipped_gives_200(self):
        service, _ntfy, _email = build_service(
            ntfy=RecordingSender(status="skipped"), email=RecordingSender(status="skipped")
        )
        code, body = service.handle_webhook(webhook([make_alert()]))
        self.assertEqual(code, 200)
        self.assertEqual(body["status"], "skipped")

    def test_unexpected_status_is_treated_as_failure(self):
        service, _ntfy, _email = build_service(
            ntfy=RecordingSender(status="dziwne"), email=RecordingSender(status="dziwne")
        )
        code, _body = service.handle_webhook(webhook([make_alert()]))
        self.assertEqual(code, 500)

    def test_both_channels_are_always_attempted(self):
        service, ntfy, email = build_service(
            ntfy=RecordingSender(raises=RuntimeError("bum")), email=RecordingSender(status="failed")
        )
        service.handle_webhook(webhook([make_alert()]))
        self.assertEqual(ntfy.calls, 1)
        self.assertEqual(email.calls, 1)


# --------------------------------------------------------------------------
# Watchdog
# --------------------------------------------------------------------------
class WatchdogTests(unittest.TestCase):
    def test_watchdog_pings_configured_url(self):
        sent = []
        service, _ntfy, _email = build_service(
            poster=lambda url, body, headers, timeout: sent.append(url) or 200
        )
        code, body = service.handle_watchdog()
        self.assertEqual(code, 200)
        self.assertEqual(body["status"], "sent")
        self.assertEqual(sent, ["https://hc-ping.com/watchdog"])
        self.assertIn('notifier_watchdog_pings_total{status="sent"} 1', service.metrics())
        self.assertIn("notifier_last_watchdog_ping_timestamp_seconds 1758484800", service.metrics())

    def test_watchdog_without_url_is_500(self):
        service, _ntfy, _email = build_service()
        service.config.hc_ping_monitoring = ""
        service.config.watchdog_ping = ""
        code, _body = service.handle_watchdog()
        self.assertEqual(code, 500)
        self.assertIn('notifier_watchdog_pings_total{status="failed"} 1', service.metrics())

    def test_watchdog_transport_failure_is_500(self):
        def boom(url, body, headers, timeout):
            raise OSError("brak sieci")

        service, _ntfy, _email = build_service(poster=boom)
        code, _body = service.handle_watchdog()
        self.assertEqual(code, 500)

    def test_watchdog_disabled_by_flag(self):
        service, _ntfy, _email = build_service(config=make_config(WATCHDOG_PING="false"))
        self.assertIsNone(service.config.watchdog_target)
        self.assertEqual(service.handle_watchdog()[0], 500)

    def test_watchdog_url_override(self):
        config = make_config(WATCHDOG_PING="https://hc-ping.com/inny")
        self.assertEqual(config.watchdog_target, "https://hc-ping.com/inny")

    def test_watchdog_falls_back_to_hc_ping_monitoring(self):
        config = make_config(WATCHDOG_PING="true")
        self.assertEqual(config.watchdog_target, "https://hc-ping.com/watchdog")


# --------------------------------------------------------------------------
# Metryki
# --------------------------------------------------------------------------
class MetricsTests(unittest.TestCase):
    def test_counters_after_dispatch(self):
        service, _ntfy, _email = build_service()
        service.handle_webhook(webhook([make_alert(severity="info")]))
        text = service.metrics()
        self.assertIn('notifier_notifications_total{channel="ntfy",status="sent"} 1', text)
        self.assertIn('notifier_notifications_total{channel="email",status="skipped"} 1', text)
        self.assertIn('notifier_last_notification_timestamp_seconds{channel="ntfy"} 1758484800', text)
        self.assertIn("notifier_up 1", text)

    def test_failed_counter(self):
        service, _ntfy, _email = build_service(ntfy=RecordingSender(status="failed"))
        service.handle_webhook(webhook([make_alert()]))
        self.assertIn(
            'notifier_notifications_total{channel="ntfy",status="failed"} 1', service.metrics()
        )

    def test_all_status_channels_are_declared(self):
        service, _ntfy, _email = build_service()
        text = service.metrics()
        for channel in ("ntfy", "email"):
            for status in ("sent", "failed", "skipped"):
                self.assertIn('notifier_notifications_total{channel="%s",status="%s"}' % (channel, status), text)

    def test_total_suffix_only_for_counters(self):
        for name, metric_type, _help in notifier.METRIC_FAMILIES:
            if name.endswith("_total"):
                self.assertEqual(metric_type, "counter", "%s nie jest licznikiem" % name)

    def test_no_duplicate_series_and_declared_families(self):
        service, _ntfy, _email = build_service()
        service.handle_webhook(webhook([make_alert()]))
        text = service.metrics()
        declared = set(re.findall(r"^# TYPE (\S+) ", text, re.MULTILINE))
        seen = set()
        for line in text.splitlines():
            if line.startswith("#") or not line.strip():
                continue
            key = line.rsplit(" ", 1)[0]
            self.assertNotIn(key, seen, "duplikat serii: %s" % key)
            seen.add(key)
            self.assertIn(line.split("{", 1)[0].split(" ", 1)[0], declared, line)

    def test_last_notification_timestamp_absent_when_nothing_was_sent(self):
        service, _ntfy, _email = build_service(
            ntfy=RecordingSender(status="failed"), email=RecordingSender(status="failed")
        )
        service.handle_webhook(webhook([make_alert()]))
        text = service.metrics()
        self.assertEqual(sample_lines(text, "notifier_last_notification_timestamp_seconds"), [])
        self.assertIn('notifier_notifications_total{channel="ntfy",status="failed"} 1', text)

    def test_health_shape(self):
        service, _ntfy, _email = build_service()
        payload = service.health()
        self.assertEqual(payload["status"], "ok")
        self.assertTrue(payload["ntfy_configured"])
        self.assertTrue(payload["email_configured"])
        self.assertTrue(payload["token_configured"])
        self.assertTrue(payload["watchdog_configured"])

    def test_health_warnings_when_unconfigured(self):
        service, _ntfy, _email = build_service(
            config=make_config(NTFY_TOPIC="", SMTP_HOST="", ALERT_EMAIL_TO="", NOTIFIER_TOKEN="",
                               HC_PING_MONITORING="")
        )
        payload = service.health()
        self.assertFalse(payload["ntfy_configured"])
        self.assertEqual(len(payload["warnings"]), 4)
        self.assertIsInstance(json.dumps(payload), str)


class ConfigTests(unittest.TestCase):
    def test_defaults(self):
        config = notifier.Config(env={})
        self.assertEqual(config.ntfy_url, "https://ntfy.sh")
        self.assertEqual(config.ntfy_priority_critical, "urgent")
        # domyślnie ostrzeżenie jest CICHE — inaczej budziłoby w nocy
        self.assertEqual(config.ntfy_priority_warning, "low")
        self.assertEqual(config.ntfy_priority_info, "min")
        self.assertEqual(config.smtp_port, 587)
        self.assertFalse(config.smtp_secure)
        self.assertEqual(config.email_min_severity, "warning")
        self.assertEqual(config.port, 8080)
        self.assertEqual(config.alert_email_to, [])

    def test_email_list_is_split(self):
        config = notifier.Config(env={"ALERT_EMAIL_TO": "a@x.pl, b@x.pl ,,c@x.pl"})
        self.assertEqual(config.alert_email_to, ["a@x.pl", "b@x.pl", "c@x.pl"])

    def test_sender_address_fallbacks(self):
        self.assertEqual(notifier.Config(env={"ALERT_EMAIL_FROM": "f@x.pl"}).sender_address, "f@x.pl")
        self.assertEqual(notifier.Config(env={"SMTP_USERNAME": "u@x.pl"}).sender_address, "u@x.pl")
        self.assertEqual(notifier.Config(env={}).sender_address, "monitoring@localhost")

    def test_bool_parsing(self):
        self.assertTrue(notifier.Config(env={"SMTP_SECURE": "TRUE"}).smtp_secure)
        self.assertTrue(notifier.Config(env={"SMTP_SECURE": "1"}).smtp_secure)
        self.assertFalse(notifier.Config(env={"SMTP_SECURE": "nie"}).smtp_secure)


if __name__ == "__main__":
    unittest.main()


class PriorytetyNtfyTests(unittest.TestCase):
    """Hałasuje tylko krytyczne — ostrzeżenie o 3:00 nie może budzić."""

    def test_tylko_krytyczne_brzeczy(self):
        config = notifier.Config(env={})
        self.assertEqual(notifier.ntfy_priority("critical", config), "urgent")
        for cicho in ("warning", "info"):
            priorytet = notifier.ntfy_priority(cicho, config)
            self.assertIn(priorytet, ("low", "min"), f"{cicho} nie może brzęczeć (jest {priorytet})")
        self.assertEqual(notifier.ntfy_priority("info", config), "min")
        self.assertEqual(notifier.ntfy_priority("warning", config), "low")

    def test_mozna_nadpisac_z_env(self):
        config = notifier.Config(env={"NTFY_PRIORITY_WARNING": "high", "NTFY_PRIORITY_INFO": "default"})
        self.assertEqual(notifier.ntfy_priority("warning", config), "high")
        self.assertEqual(notifier.ntfy_priority("info", config), "default")
