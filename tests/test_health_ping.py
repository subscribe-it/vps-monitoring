"""Testy jednostkowe serwisu `health-ping`.

Zero Dockera i zero sieci: atrapy klienta Docker, klientów HTTP, pingów,
`statvfs` i czytnika plików.
"""

import importlib.util
import json
import pathlib
import re
import sys
import unittest
import urllib.parse
from datetime import datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parents[1]


def load_module(name, relative_path):
    spec = importlib.util.spec_from_file_location(name, str(ROOT / relative_path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


health = load_module("svc_health_ping", "services/health-ping/main.py")

BACKUP_SERVICE = "ventiplan-prod_db-backup"


# --------------------------------------------------------------------------
# Atrapy
# --------------------------------------------------------------------------
def frame(text, stream=1):
    """Ramka strumienia logów Dockera: [typ 000 rozmiar BE] + treść."""
    data = text.encode("utf-8")
    return bytes([stream, 0, 0, 0]) + len(data).to_bytes(4, "big") + data


def now_minus(hours=0.0, days=0.0):
    return datetime.now(timezone.utc) - timedelta(hours=hours, days=days)


def stamp(moment):
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


class FakeDocker:
    def __init__(self, containers=None, logs=None, error=None):
        self._containers = containers if containers is not None else [
            {"Id": "backupcid", "Labels": {"com.docker.swarm.service.name": BACKUP_SERVICE}},
        ]
        self._logs = logs if logs is not None else b""
        self._error = error
        self.calls = []

    def containers(self):
        self.calls.append("/containers/json?all=1")
        if self._error:
            raise health.DockerError(self._error)
        return self._containers

    def container_logs(self, container_id, tail=2000):
        self.calls.append("/containers/%s/logs?stdout=1&stderr=1&tail=%d" % (container_id, tail))
        if self._error:
            raise health.DockerError(self._error)
        return self._logs


class FakeStatvfs:
    def __init__(self, blocks=1000, bavail=500, files=1000, ffree=500, frsize=4096):
        self.f_blocks = blocks
        self.f_bavail = bavail
        self.f_files = files
        self.f_ffree = ffree
        self.f_frsize = frsize


def prom_json_get(values=None, status_payload=None):
    """Atrapa klienta JSON: Prometheus (/api/v1/query) + discovery /status/api.json."""
    values = values if values is not None else {
        'node_filesystem_avail_bytes{mountpoint="/"}': 800,
        'node_filesystem_size_bytes{mountpoint="/"}': 1000,
        'node_filesystem_files_free{mountpoint="/"}': 900,
        'node_filesystem_files{mountpoint="/"}': 1000,
    }

    def json_get(url, timeout=5.0):
        if "/api/v1/query" in url:
            query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["query"][0]
            if query not in values:
                return {"data": {"result": []}}
            return {"data": {"result": [{"value": [0, str(values[query])]}]}}
        if url.endswith("/status/api.json"):
            if status_payload is None:
                raise OSError("discovery nie odpowiada")
            return status_payload
        raise AssertionError("nieoczekiwany URL: %s" % url)

    return json_get


def metrics_text(running=2, desired=2, cert_days=61.5, extra=""):
    return (
        "# HELP swarm_service_running_replicas x\n"
        "# TYPE swarm_service_running_replicas gauge\n"
        'swarm_service_running_replicas{service="api",stack="ventiplan-prod"} %s\n'
        "# TYPE swarm_service_desired_replicas gauge\n"
        'swarm_service_desired_replicas{service="api",stack="ventiplan-prod"} %s\n'
        "# TYPE discovery_cert_days_left gauge\n"
        'discovery_cert_days_left{host="app.ventiplan.pl"} %s\n'
        "%s" % (running, desired, cert_days, extra)
    )


def text_get_factory(text):
    def text_get(url, timeout=5.0):
        if url.endswith("/metrics"):
            if text is None:
                raise OSError("discovery nie odpowiada")
            return text
        raise AssertionError("nieoczekiwany URL: %s" % url)

    return text_get


def sample_lines(text, metric):
    """Linie z wartościami danej metryki (pomija # HELP / # TYPE)."""
    return [
        line for line in text.splitlines()
        if line.startswith(metric + " ") or line.startswith(metric + "{")
    ]


def make_ping(result=True, calls=None):
    def ping(url, ok, message, timeout=10.0):
        if calls is not None:
            calls.append({"url": url, "ok": ok, "message": message, "timeout": timeout})
        return result

    return ping


def backup_logs(hours_ago=3.0, size="512.4 MB", marker="backup complete"):
    moment = now_minus(hours=hours_ago)
    return frame("%s [%s] %s: dump %s\n" % (stamp(moment), BACKUP_SERVICE, marker, size))


def build_service(env=None, docker=None, metrics=None, status_payload=None, prom_values=None,
                  ping=None, ping_calls=None, statvfs=None, restore_file=None,
                  clock=None, status_get=None):
    base_env = {"HC_PING_ALL_OK": "https://hc-ping.com/all", "HC_PING_BACKUP": "https://hc-ping.com/backup"}
    base_env.update(env or {})
    config = health.Config(env=base_env)
    if restore_file is None:
        restore_file = json.dumps({"last_test_at": stamp(now_minus(days=10))})

    def file_reader(path):
        if isinstance(restore_file, Exception):
            raise restore_file
        return restore_file

    return health.HealthPing(
        config,
        docker=docker if docker is not None else FakeDocker(logs=backup_logs()),
        text_get=text_get_factory(metrics_text() if metrics is None else metrics),
        json_get=prom_json_get(prom_values, status_payload if status_payload is not None
                               else {"checks": [{"name": "api", "group": "ventiplan-prod", "state": "ok"}]}),
        status_get=status_get or (lambda url, timeout=5.0: 200),
        ping_fn=ping or make_ping(calls=ping_calls),
        statvfs=statvfs or (lambda path: FakeStatvfs()),
        file_reader=file_reader,
        clock=clock or (lambda: 1758484800.0),
    )


# --------------------------------------------------------------------------
# Strumień logów Dockera
# --------------------------------------------------------------------------
class DockerLogStreamTests(unittest.TestCase):
    def test_multiple_frames(self):
        raw = frame("linia 1\n", 1) + frame("linia 2\n", 2) + frame("linia 3\n", 1)
        self.assertEqual(health.parse_docker_log_stream(raw), "linia 1\nlinia 2\nlinia 3\n")

    def test_unframed_stream_is_returned_as_is(self):
        raw = "zwykły tekst bez ramek\n".encode("utf-8")
        self.assertEqual(health.parse_docker_log_stream(raw), "zwykły tekst bez ramek\n")

    def test_truncated_tail_is_ignored(self):
        raw = frame("pełna ramka\n", 1) + bytes([1, 0, 0, 0]) + (100).to_bytes(4, "big") + b"urywek"
        self.assertEqual(health.parse_docker_log_stream(raw), "pełna ramka\n")

    def test_empty_stream(self):
        self.assertEqual(health.parse_docker_log_stream(b""), "")

    def test_client_decodes_chunked_framed_logs(self):
        """Docker odpowiada chunked, a w środku są ramki logów — oba poziomy naraz."""
        payload = frame("2026-09-21T03:00:00Z backup complete: dump 512.4 MB\n", 1)
        chunked = b"%x\r\n%s\r\n0\r\n\r\n" % (len(payload), payload)
        raw = b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n" + chunked
        client = health.DockerClient(fetcher=lambda path: raw)
        text = health.parse_docker_log_stream(client.container_logs("abc", tail=5))
        self.assertIn("backup complete", text)

    def test_logs_path_is_get_only(self):
        source = (ROOT / "services" / "health-ping" / "main.py").read_text(encoding="utf-8")
        self.assertIn('"GET %s HTTP/1.1', source)
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            self.assertNotIn('"%s %%s HTTP/1.1' % method, source)


# --------------------------------------------------------------------------
# Wyciąganie sukcesu backupu
# --------------------------------------------------------------------------
class BackupExtractionTests(unittest.TestCase):
    def test_english_marker_with_timestamp(self):
        text = "[2026-09-21T03:00:00Z] backup complete: dump 512.4 MB\n"
        info = health.extract_backup_info(text)
        self.assertEqual(info.last_success_at, datetime(2026, 9, 21, 3, 0, tzinfo=timezone.utc))
        self.assertEqual(info.size_bytes, int(512.4 * 1000 ** 2))
        self.assertEqual(info.timestamp_source, "line")
        self.assertFalse(info.weak_match)

    def test_polish_markers(self):
        for line in ("Backup zakończony sukcesem", "backup zakonczony sukcesem: plik.dump",
                     "dump ok", "uploaded to R2", "sukces"):
            with self.subTest(line=line):
                info = health.extract_backup_info("2026-09-21 03:00:00 " + line + "\n")
                self.assertIsNotNone(info.last_success_at, line)

    def test_custom_regex_takes_precedence(self):
        text = "2026-09-21T03:00:00Z ZROBIONE: kopia 1 GB\n"
        self.assertIsNone(health.extract_backup_info(text).last_success_at)
        info = health.extract_backup_info(text, r"ZROBIONE")
        self.assertIsNotNone(info.last_success_at)
        self.assertEqual(info.size_bytes, 1000 ** 3)

    def test_invalid_regex_raises_value_error(self):
        with self.assertRaises(ValueError):
            health.extract_backup_info("cokolwiek", "([nieprawidlowy")

    def test_no_marker_returns_empty_info(self):
        info = health.extract_backup_info("2026-09-21T03:00:00Z start kopiowania\n")
        self.assertIsNone(info.last_success_at)
        self.assertIsNone(info.size_bytes)
        self.assertEqual(info.timestamp_source, "none")

    def test_weak_match_on_dump_filename(self):
        text = "2026-09-21T03:00:00Z plik ventiplan-2026-09-21.dump\n"
        info = health.extract_backup_info(text)
        self.assertTrue(info.weak_match)
        self.assertIsNotNone(info.last_success_at)

    def test_timestamp_falls_back_to_newest_entry_in_log(self):
        text = "2026-09-21T03:00:00Z krok 1\n2026-09-21T04:00:00Z backup complete bez znacznika\n".replace(
            "2026-09-21T04:00:00Z backup complete bez znacznika", "backup complete bez znacznika"
        )
        info = health.extract_backup_info(text)
        self.assertEqual(info.timestamp_source, "log")
        self.assertEqual(info.last_success_at, datetime(2026, 9, 21, 3, 0, tzinfo=timezone.utc))

    def test_last_success_wins(self):
        text = ("2026-09-21T01:00:00Z backup complete\n"
                "2026-09-21T05:00:00Z backup complete\n")
        info = health.extract_backup_info(text)
        self.assertEqual(info.last_success_at, datetime(2026, 9, 21, 5, 0, tzinfo=timezone.utc))

    def test_size_units(self):
        self.assertEqual(health.extract_size_bytes("2 GiB"), 2 * 1024 ** 3)
        self.assertEqual(health.extract_size_bytes("1,5 MB"), int(1.5 * 1000 ** 2))
        self.assertIsNone(health.extract_size_bytes("brak rozmiaru"))

    def test_find_backup_container(self):
        containers = [
            {"Id": "a", "Labels": {"com.docker.swarm.service.name": "inna_usluga"}},
            {"Id": "b", "Labels": {"com.docker.swarm.service.name": BACKUP_SERVICE}},
        ]
        self.assertEqual(health.find_backup_container(containers, BACKUP_SERVICE)["Id"], "b")
        self.assertIsNone(health.find_backup_container(containers, "nie-ma"))
        self.assertIsNone(health.find_backup_container(["śmieci"], BACKUP_SERVICE))


# --------------------------------------------------------------------------
# Parser ekspozycji Prometheusa
# --------------------------------------------------------------------------
class PrometheusParsingTests(unittest.TestCase):
    def test_parse_samples(self):
        text = (
            "# HELP x y\n"
            "# TYPE x gauge\n"
            'swarm_service_running_replicas{service="api",stack="ventiplan-prod"} 2\n'
            "discovery_up 1\n"
        )
        samples = health.parse_prometheus_text(text)
        self.assertEqual(len(samples), 2)
        name, labels, value = samples[0]
        self.assertEqual(name, "swarm_service_running_replicas")
        self.assertEqual(labels, {"service": "api", "stack": "ventiplan-prod"})
        self.assertEqual(value, 2.0)

    def test_escaped_label_values(self):
        text = 'discovery_cert_days_left{host="a\\"b.pl",note="linia\\n2"} 5\n'
        _name, labels, _value = health.parse_prometheus_text(text)[0]
        self.assertEqual(labels["host"], 'a"b.pl')
        self.assertEqual(labels["note"], "linia\n2")

    def test_comments_and_broken_lines_ignored(self):
        samples = health.parse_prometheus_text("# komentarz\nzepsuta linia\nup 1\n")
        self.assertEqual([sample[0] for sample in samples], ["up"])

    def test_failing_services(self):
        samples = health.parse_prometheus_text(metrics_text(running=1, desired=2))
        self.assertEqual(health.failing_services(samples, set()), ["ventiplan-prod_api (1/2)"])
        self.assertEqual(health.failing_services(samples, {"ventiplan-prod"}), [])

    def test_min_cert_days(self):
        samples = health.parse_prometheus_text(
            'discovery_cert_days_left{host="a"} 61.5\n'
            'discovery_cert_days_left{host="b"} 9\n'
        )
        self.assertEqual(health.min_cert_days(samples), 9.0)
        self.assertIsNone(health.min_cert_days([]))


# --------------------------------------------------------------------------
# Pojedyncze sprawdzenia
# --------------------------------------------------------------------------
class CheckTests(unittest.TestCase):
    def test_disk_and_inodes_green(self):
        service = build_service()
        self.assertTrue(service.check_disk().ok)
        self.assertTrue(service.check_inodes().ok)

    def test_disk_below_threshold_is_red(self):
        service = build_service(prom_values={
            'node_filesystem_avail_bytes{mountpoint="/"}': 100,
            'node_filesystem_size_bytes{mountpoint="/"}': 1000,
        })
        outcome = service.check_disk()
        self.assertFalse(outcome.ok)
        self.assertIn("10.0%", outcome.detail)

    def test_disk_falls_back_to_statvfs(self):
        service = build_service(prom_values={}, statvfs=lambda path: FakeStatvfs(blocks=1000, bavail=700))
        outcome = service.check_disk()
        self.assertTrue(outcome.ok)
        self.assertEqual(outcome.data["source"], "statvfs")

    def test_services_check_red_when_replicas_missing(self):
        service = build_service(metrics=metrics_text(running=1, desired=3))
        outcome = service.check_services()
        self.assertFalse(outcome.ok)
        self.assertIn("1/3", outcome.detail)

    def test_services_check_ignores_configured_stacks(self):
        service = build_service(
            env={"SERVICES_IGNORE_STACKS": "ventiplan-prod"},
            metrics=metrics_text(running=0, desired=3),
        )
        self.assertTrue(service.check_services().ok)

    def test_http_check_red_on_critical_probe(self):
        service = build_service(status_payload={"checks": [
            {"name": "api", "group": "ventiplan-prod", "state": "ok"},
            {"name": "web", "group": "ventiplan-prod", "state": "critical"},
        ]})
        outcome = service.check_http()
        self.assertFalse(outcome.ok)
        self.assertIn("ventiplan-prod/web", outcome.detail)

    def test_certs_check(self):
        self.assertTrue(build_service(metrics=metrics_text(cert_days=61.5)).check_certs().ok)
        self.assertFalse(build_service(metrics=metrics_text(cert_days=9)).check_certs().ok)
        self.assertFalse(build_service(metrics=metrics_text(cert_days=14)).check_certs().ok)

    def test_backup_fresh_and_size_ok(self):
        service = build_service(docker=FakeDocker(logs=backup_logs(hours_ago=3)))
        outcome, info = service.check_backup()
        self.assertTrue(outcome.ok, outcome.detail)
        self.assertIsNotNone(info.last_success_at)
        self.assertEqual(info.size_bytes, int(512.4 * 1000 ** 2))

    def test_backup_too_old_is_red(self):
        service = build_service(docker=FakeDocker(logs=backup_logs(hours_ago=40)))
        self.assertFalse(service.check_backup()[0].ok)

    def test_backup_too_small_is_red(self):
        service = build_service(
            env={"BACKUP_MIN_SIZE_MB": "1000"},
            docker=FakeDocker(logs=backup_logs(hours_ago=3, size="512 MB")),
        )
        self.assertFalse(service.check_backup()[0].ok)

    def test_backup_without_marker_is_red(self):
        service = build_service(docker=FakeDocker(logs=frame("2026-09-21T03:00:00Z start\n")))
        outcome = service.check_backup()[0]
        self.assertFalse(outcome.ok)
        self.assertIn("BACKUP_SUCCESS_REGEX", outcome.detail)

    def test_backup_missing_container_is_red(self):
        service = build_service(docker=FakeDocker(containers=[]))
        self.assertFalse(service.check_backup()[0].ok)

    def test_backup_docker_unavailable_degrades(self):
        service = build_service(docker=FakeDocker(error="brak dostępu do gniazda"))
        outcome = service.check_backup()[0]
        self.assertFalse(outcome.ok)
        self.assertIn("Docker API niedostępne", outcome.detail)

    def test_restore_test_missing_file_is_red(self):
        service = build_service(restore_file=FileNotFoundError("/data/restore-test.json"))
        outcome = service.check_restore_test()
        self.assertFalse(outcome.ok)
        self.assertEqual(outcome.data["days"], 0.0)

    def test_restore_test_old_is_red(self):
        payload = json.dumps({"last_test_at": stamp(now_minus(days=100))})
        self.assertFalse(build_service(restore_file=payload).check_restore_test().ok)

    def test_restore_test_fresh_is_green(self):
        payload = json.dumps({"last_test_at": stamp(now_minus(days=10))})
        self.assertTrue(build_service(restore_file=payload).check_restore_test().ok)

    def test_alertmanager_check(self):
        self.assertTrue(build_service(status_get=lambda url, timeout=5.0: 200).check_alertmanager().ok)
        self.assertFalse(build_service(status_get=lambda url, timeout=5.0: 503).check_alertmanager().ok)

        def boom(url, timeout=5.0):
            raise OSError("connection refused")

        self.assertFalse(build_service(status_get=boom).check_alertmanager().ok)


# --------------------------------------------------------------------------
# Cały przebieg + logika all_ok
# --------------------------------------------------------------------------
class RunOnceTests(unittest.TestCase):
    def test_all_green(self):
        service = build_service()
        self.assertTrue(service.run_once())
        state = service.state_view()
        self.assertTrue(state["all_ok"])
        self.assertTrue(state["up"])
        for check in health.CHECKS:
            self.assertTrue(state["results"][check].ok, check)

    def test_one_red_makes_all_ok_zero(self):
        service = build_service(metrics=metrics_text(cert_days=3))
        self.assertFalse(service.run_once())
        self.assertFalse(service.state_view()["all_ok"])

    def test_metrics_report_check_results(self):
        service = build_service(metrics=metrics_text(cert_days=3))
        service.run_once()
        text = service.metrics()
        self.assertIn("monitoring_all_ok 0", text)
        self.assertIn('monitoring_check_ok{check="certs"} 0', text)
        self.assertIn('monitoring_check_ok{check="disk"} 1', text)
        for check in health.CHECKS:
            self.assertIn('monitoring_check_ok{check="%s"}' % check, text)

    def test_all_green_metrics(self):
        service = build_service()
        service.run_once()
        text = service.metrics()
        self.assertIn("monitoring_all_ok 1", text)
        self.assertIn('monitoring_check_ok{check="restore_test"} 1', text)
        self.assertIn("monitoring_up 1", text)
        self.assertIn("monitoring_backup_age_seconds", text)
        self.assertIn("monitoring_backup_size_bytes", text)
        self.assertIn("monitoring_restore_test_age_days 10", text)

    def test_restore_test_metric_zero_when_never_tested(self):
        service = build_service(restore_file=FileNotFoundError("brak"))
        service.run_once()
        text = service.metrics()
        self.assertIn("monitoring_restore_test_age_days 0", text)
        self.assertIn('monitoring_check_ok{check="restore_test"} 0', text)

    def test_backup_metrics_absent_when_unknown(self):
        service = build_service(docker=FakeDocker(error="brak gniazda"))
        service.run_once()
        text = service.metrics()

        self.assertIn('monitoring_check_ok{check="backup"} 0', text)
        self.assertEqual(sample_lines(text, "monitoring_backup_age_seconds"), [])

    def test_run_once_never_raises_when_everything_is_down(self):
        def boom(*args, **kwargs):
            raise OSError("wszystko padło")

        service = health.HealthPing(
            health.Config(env={"HC_PING_ALL_OK": "https://hc-ping.com/a"}),
            docker=FakeDocker(error="brak gniazda"),
            text_get=boom,
            json_get=boom,
            status_get=boom,
            ping_fn=make_ping(result=False),
            statvfs=boom,
            file_reader=boom,
        )
        self.assertFalse(service.run_once())
        self.assertEqual(len(service.state_view()["results"]), len(health.CHECKS))
        self.assertIn("monitoring_all_ok 0", service.metrics())
        self.assertIn("monitoring_up 1", service.metrics())

    def test_loop_survives_exception(self):
        class Boom(health.HealthPing):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.calls = 0

            def run_once(self):
                self.calls += 1
                raise RuntimeError("bum")

        service = Boom(health.Config(env={}))
        stop = __import__("threading").Event()
        stop.set()
        service.run(stop)  # nie może rzucić
        self.assertFalse(service.up)


# --------------------------------------------------------------------------
# Pingi do healthchecks.io
# --------------------------------------------------------------------------
class PingTests(unittest.TestCase):
    def test_success_ping_goes_without_fail_suffix(self):
        calls = []
        service = build_service(ping=make_ping(True, calls))
        service.run_once()
        urls = [call["url"] for call in calls]
        self.assertIn("https://hc-ping.com/all", urls)
        self.assertIn("https://hc-ping.com/backup", urls)
        self.assertNotIn("https://hc-ping.com/all/fail", urls)

    def test_problem_ping_goes_to_fail_with_reason(self):
        calls = []
        service = build_service(metrics=metrics_text(cert_days=3), ping=make_ping(True, calls))
        service.run_once()
        failing = [call for call in calls if call["ok"] is False]
        self.assertTrue(failing, calls)
        self.assertIn("PROBLEM", failing[0]["message"])
        self.assertIn("certs", failing[0]["message"])

    def test_fail_url_is_built_by_ping_target_url(self):
        self.assertEqual(health.ping_target_url("https://hc-ping.com/abc", True), "https://hc-ping.com/abc")
        self.assertEqual(health.ping_target_url("https://hc-ping.com/abc/", False), "https://hc-ping.com/abc/fail")

    def test_ping_healthchecks_posts_reason_to_fail_endpoint(self):
        sent = []

        def poster(url, body, timeout=10.0):
            sent.append({"url": url, "body": body})
            return 200

        self.assertTrue(health.ping_healthchecks("https://hc-ping.com/abc", True, "OK", poster=poster))
        self.assertTrue(health.ping_healthchecks("https://hc-ping.com/abc", False, "PROBLEM: dysk", poster=poster))
        self.assertEqual(sent[0], {"url": "https://hc-ping.com/abc", "body": "OK"})
        self.assertEqual(sent[1], {"url": "https://hc-ping.com/abc/fail", "body": "PROBLEM: dysk"})

    def test_ping_healthchecks_reports_transport_failure(self):
        def boom(url, body, timeout=10.0):
            raise OSError("brak sieci")

        self.assertFalse(health.ping_healthchecks("https://hc-ping.com/abc", True, "OK", poster=boom))
        self.assertIsNone(health.ping_healthchecks("", True, "OK", poster=boom))

    def test_ping_failure_increments_counter_and_keeps_timestamp_empty(self):
        service = build_service(ping=make_ping(False))
        service.run_once()
        text = service.metrics()
        self.assertIn('monitoring_hc_ping_failures_total{target="all_ok"} 1', text)
        self.assertEqual(sample_lines(text, "monitoring_last_hc_ping_timestamp_seconds"), [])

    def test_ping_success_sets_timestamp(self):
        service = build_service(ping=make_ping(True))
        service.run_once()
        self.assertIn(
            'monitoring_last_hc_ping_timestamp_seconds{target="all_ok"} 1758484800', service.metrics()
        )

    def test_ping_skipped_without_url(self):
        calls = []
        service = build_service(env={"HC_PING_ALL_OK": "", "HC_PING_BACKUP": ""},
                                ping=make_ping(True, calls))
        service.run_once()
        self.assertEqual(calls, [])
        self.assertEqual(service.state_view()["last_ping_status"]["all_ok"], None)
        self.assertEqual(sample_lines(service.metrics(), "monitoring_last_hc_ping_timestamp_seconds"), [])


# --------------------------------------------------------------------------
# /backup.json i konwencja metryk
# --------------------------------------------------------------------------
class BackupJsonTests(unittest.TestCase):
    def test_schema_when_ok(self):
        service = build_service()
        service.run_once()
        payload = service.backup_json()
        self.assertEqual(
            sorted(payload.keys()),
            ["age_hours", "last_success_at", "objects_in_r2", "restore_test_days", "size_bytes", "state"],
        )
        self.assertEqual(payload["state"], "ok")
        self.assertLess(payload["age_hours"], 26)
        self.assertEqual(payload["restore_test_days"], 10)
        self.assertTrue(payload["last_success_at"].endswith("Z"))
        self.assertIsInstance(json.dumps(payload), str)

    def test_unknown_state_without_docker(self):
        service = build_service(docker=FakeDocker(error="brak gniazda"))
        service.run_once()
        payload = service.backup_json()
        self.assertEqual(payload["state"], "unknown")
        self.assertIsNone(payload["age_hours"])
        self.assertIsNone(payload["last_success_at"])

    def test_stale_backup_is_critical(self):
        service = build_service(docker=FakeDocker(logs=backup_logs(hours_ago=100)))
        service.run_once()
        self.assertEqual(service.backup_json()["state"], "critical")

    def test_health_endpoint_shape(self):
        service = build_service()
        service.run_once()
        payload = service.health()
        self.assertEqual(payload["status"], "ok")
        self.assertTrue(payload["up"])
        self.assertEqual(len(payload["checks"]), len(health.CHECKS))
        self.assertIn("details", payload)

    def test_health_status_degraded_when_a_check_is_red(self):
        service = build_service(metrics=metrics_text(cert_days=3))
        service.run_once()
        payload = service.health()
        self.assertEqual(payload["status"], "degraded")
        self.assertTrue(payload["up"])
        self.assertFalse(payload["all_ok"])
        self.assertEqual(payload["checks"]["certs"], 0)

    def test_health_status_starting_before_first_run(self):
        service = build_service()
        payload = service.health()
        self.assertEqual(payload["status"], "starting")
        self.assertFalse(payload["up"])


class MetricLintTests(unittest.TestCase):
    def test_total_suffix_only_for_counters(self):
        for name, metric_type, _help in health.METRIC_FAMILIES:
            if name.endswith("_total"):
                self.assertEqual(metric_type, "counter", "%s nie jest licznikiem" % name)

    def test_no_duplicate_series(self):
        service = build_service()
        service.run_once()
        seen = set()
        for line in service.metrics().splitlines():
            if line.startswith("#") or not line.strip():
                continue
            key = line.rsplit(" ", 1)[0]
            self.assertNotIn(key, seen, "duplikat serii: %s" % key)
            seen.add(key)

    def test_every_sample_has_declared_family(self):
        service = build_service()
        service.run_once()
        text = service.metrics()
        declared = set(re.findall(r"^# TYPE (\S+) ", text, re.MULTILINE))
        for line in text.splitlines():
            if line.startswith("#") or not line.strip():
                continue
            self.assertIn(line.split("{", 1)[0].split(" ", 1)[0], declared, line)


class ConfigTests(unittest.TestCase):
    def test_defaults(self):
        config = health.Config(env={})
        self.assertEqual(config.interval_seconds, 120.0)
        self.assertEqual(config.disk_min_free_percent, 15.0)
        self.assertEqual(config.inodes_min_free_percent, 10.0)
        self.assertEqual(config.cert_min_days, 14.0)
        self.assertEqual(config.backup_max_age_hours, 26.0)
        self.assertEqual(config.restore_test_max_days, 45.0)
        self.assertEqual(config.backup_service, BACKUP_SERVICE)
        self.assertEqual(config.docker_socket, "/var/run/docker.sock")
        self.assertEqual(config.port, 8080)

    def test_ignore_stacks_default(self):
        self.assertEqual(
            health.Config(env={}).services_ignore_stacks,
            {"monitoring", "kosmetix-staging", "staging_mdi-studio"},
        )

    def test_tcp_docker_host_rejected(self):
        with self.assertRaises(health.ConfigError):
            health.Config(env={"DOCKER_HOST": "tcp://1.2.3.4:2375"})

    def test_config_warnings(self):
        warnings = health.Config(env={}).config_warnings
        self.assertEqual(len(warnings), 2)


if __name__ == "__main__":
    unittest.main()
