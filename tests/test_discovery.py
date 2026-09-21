"""Testy jednostkowe serwisu `discovery`.

Zero sieci i zero Dockera: wszystko przez wstrzykiwane atrapy (fetcher gniazda,
sonda HTTP, klient JSON, odczyt certyfikatów).
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


discovery = load_module("svc_discovery", "services/discovery/main.py")


# --------------------------------------------------------------------------
# Atrapy
# --------------------------------------------------------------------------
class FakeDocker:
    """Atrapa DockerClient — żadnych gniazd, żadnych kontenerów."""

    def __init__(self, services=None, tasks=None, containers=None, df=None,
                 inspect=None, stats=None, error=None):
        self._services = services or []
        self._tasks = tasks or []
        self._containers = containers or []
        self._df = df or {}
        self._inspect = inspect or {}
        self._stats = stats or {}
        self._error = error
        self.calls = []

    def _guard(self, path):
        self.calls.append(path)
        if self._error:
            raise discovery.DockerError(self._error)

    def services(self):
        self._guard("/services")
        return self._services

    def tasks(self):
        self._guard("/tasks")
        return self._tasks

    def containers(self):
        self._guard("/containers/json?all=1")
        return self._containers

    def system_df(self):
        self._guard("/system/df")
        return self._df

    def container_inspect(self, container_id):
        self._guard("/containers/%s/json" % container_id)
        return self._inspect.get(container_id, {})

    def container_stats(self, container_id):
        self._guard("/containers/%s/stats?stream=false" % container_id)
        return self._stats.get(container_id, {})


def make_config(**env):
    base = {
        "CRITICAL_STACKS": "ventiplan-prod",
        "WARN_STACKS": "monitoring",
        "REFRESH_SECONDS": "30",
        "MONITORING_DOMAIN": "monitoring.subscribeit.pl",
    }
    base.update(env)
    return discovery.Config(env=base)


def make_service(name, labels=None, image="nginx:1.27", mode=None, replicas=None,
                 updated_at="2026-09-21T19:40:00.123456789Z"):
    spec = {
        "Name": name,
        "Labels": labels or {},
        "TaskTemplate": {"ContainerSpec": {"Image": image}},
        "Mode": {},
    }
    if replicas is not None:
        spec["Mode"] = {"Replicated": {"Replicas": replicas}}
    if mode is not None:
        spec["Mode"] = mode
    return {"ID": "svc-" + name, "Spec": spec, "UpdatedAt": updated_at}


def make_task(service_id, state="running", desired="running", created="2026-09-21T19:40:00Z"):
    return {
        "ServiceID": service_id,
        "DesiredState": desired,
        "Status": {"State": state},
        "CreatedAt": created,
    }


def make_container(container_id, service_name, stack="ventiplan-prod", state="running", name=None):
    return {
        "Id": container_id,
        "Names": [name or ("/" + service_name + ".1.abc")],
        "Labels": {
            "com.docker.swarm.service.name": service_name,
            "com.docker.swarm.stack.namespace": stack,
        },
        "State": state,
        "Status": "Up 2 hours",
    }


def ok_probe(url, timeout=5.0):
    return discovery.ProbeResult("ok", 200, 0.209)


def build_service(docker, config=None, probe=None, json_get=None, cert_fn=None):
    return discovery.DiscoveryService(
        docker=docker,
        config=config or make_config(),
        probe_fn=probe or ok_probe,
        json_get=json_get or (lambda url, timeout=5.0: {}),
        cert_fn=cert_fn or (
            lambda host: datetime.now(timezone.utc) + timedelta(days=61, hours=12)
        ),
    )


# --------------------------------------------------------------------------
# Parsowanie reguł Traefika
# --------------------------------------------------------------------------
class TraefikRuleTests(unittest.TestCase):
    def test_host_with_path_prefix_backticks(self):
        rule = "Host(`app.ventiplan.pl`) && PathPrefix(`/api`)"
        self.assertEqual(discovery.parse_traefik_rule(rule), ("app.ventiplan.pl", "/api"))

    def test_single_quotes(self):
        rule = "Host('app.ventiplan.pl') && PathPrefix('/health')"
        self.assertEqual(discovery.parse_traefik_rule(rule), ("app.ventiplan.pl", "/health"))

    def test_double_quotes(self):
        rule = 'Host("app.ventiplan.pl") && PathPrefix("/x")'
        self.assertEqual(discovery.parse_traefik_rule(rule), ("app.ventiplan.pl", "/x"))

    def test_without_path_prefix(self):
        self.assertEqual(discovery.parse_traefik_rule("Host(`app.ventiplan.pl`)"), ("app.ventiplan.pl", ""))

    def test_root_path_is_empty(self):
        self.assertEqual(discovery.parse_traefik_rule("Host(`a.pl`) && PathPrefix(`/`)"), ("a.pl", ""))

    def test_trailing_slash_is_stripped(self):
        self.assertEqual(discovery.parse_traefik_rule("Host(`a.pl`) && PathPrefix(`/grafana/`)"), ("a.pl", "/grafana"))

    def test_rule_without_host_is_ignored(self):
        self.assertIsNone(discovery.parse_traefik_rule("PathPrefix(`/x`)"))
        self.assertIsNone(discovery.parse_traefik_rule(""))
        self.assertIsNone(discovery.parse_traefik_rule(None))

    def test_many_routers_and_mixed_syntax(self):
        labels = {
            "traefik.http.routers.web.rule": "Host(`a.pl`)",
            "traefik.http.routers.api.rule": "Host(`a.pl`) && PathPrefix(`/api`)",
            "traefik.http.routers.api.entrypoints": "websecure",
        }
        self.assertEqual(
            discovery.router_rules(labels),
            [("api", "Host(`a.pl`) && PathPrefix(`/api`)"), ("web", "Host(`a.pl`)")],
        )

    def test_url_building(self):
        self.assertEqual(discovery.build_traefik_url("a.pl", "/x"), "https://a.pl/x")
        self.assertEqual(discovery.build_traefik_url("a.pl", "/"), "https://a.pl")
        self.assertEqual(discovery.build_traefik_url("a.pl", ""), "https://a.pl")


# --------------------------------------------------------------------------
# Klasyfikacja
# --------------------------------------------------------------------------
class ClassificationTests(unittest.TestCase):
    def test_label_wins_over_stacks(self):
        self.assertEqual(
            discovery.classify_severity("ventiplan-prod", {"monitoring.io/severity": "warning"},
                                        {"ventiplan-prod"}, set()),
            "warning",
        )

    def test_critical_stack(self):
        self.assertEqual(discovery.classify_severity("ventiplan-prod", {}, {"ventiplan-prod"}, set()), "critical")

    def test_warn_stack(self):
        self.assertEqual(discovery.classify_severity("monitoring", {}, set(), {"monitoring"}), "warning")

    def test_default_is_warning(self):
        self.assertEqual(discovery.classify_severity("inne", {}, set(), set()), "warning")

    def test_skip_from_label(self):
        self.assertEqual(
            discovery.classify_severity("inne", {"monitoring.io/severity": "skip"}, set(), set()), "skip"
        )

    def test_module_from_expect(self):
        self.assertEqual(discovery.resolve_module({"monitoring.io/expect": "200"}, "http_2xx"), "http_2xx")
        self.assertEqual(discovery.resolve_module({"monitoring.io/expect": "401"}, "http_2xx"), "http_expect_auth")
        self.assertEqual(discovery.resolve_module({"monitoring.io/expect": "503"}, "http_2xx"), "http_alive")
        self.assertEqual(
            discovery.resolve_module({"monitoring.io/expect": "200", "monitoring.io/module": "tcp_connect"}, "http_2xx"),
            "tcp_connect",
        )
        self.assertEqual(discovery.resolve_module({}, "http_2xx"), "http_2xx")


# --------------------------------------------------------------------------
# HTTP SD
# --------------------------------------------------------------------------
class HttpSdTests(unittest.TestCase):
    def test_labels_contain_module_and_param_module(self):
        config = make_config()
        service = build_service(FakeDocker(services=[
            make_service("ventiplan-prod_api", {
                "traefik.enable": "true",
                "traefik.http.routers.api.rule": "Host(`app.ventiplan.pl`) && PathPrefix(`/health`)",
                "monitoring.io/health-path": "/health",
            }),
        ]), config=config)
        service.refresh()
        entries = service.http_sd()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["targets"], ["https://app.ventiplan.pl/health"])
        labels = entries[0]["labels"]
        self.assertEqual(labels["stack"], "ventiplan-prod")
        self.assertEqual(labels["service"], "api")
        self.assertEqual(labels["module"], "http_2xx")
        self.assertIn("__param_module", labels)
        self.assertEqual(labels["__param_module"], labels["module"])
        self.assertEqual(labels["severity"], "critical")
        self.assertEqual(labels["source"], "discovery")

    def test_probe_override_and_name(self):
        service = build_service(FakeDocker(services=[
            make_service("ventiplan-prod_api", {
                "traefik.http.routers.api.rule": "Host(`app.ventiplan.pl`)",
                "monitoring.io/probe": "https://inny.example.com/ping",
                "monitoring.io/name": "api-publiczne",
                "monitoring.io/severity": "warning",
                "monitoring.io/expect": "401",
            }),
        ]))
        service.refresh()
        entries = service.http_sd()
        self.assertEqual(entries[0]["targets"], ["https://inny.example.com/ping"])
        self.assertEqual(entries[0]["labels"]["service"], "api-publiczne")
        self.assertEqual(entries[0]["labels"]["severity"], "warning")
        self.assertEqual(entries[0]["labels"]["module"], "http_expect_auth")

    def test_many_routers_deduplicated_by_url(self):
        service = build_service(FakeDocker(services=[
            make_service("ventiplan-prod_api", {
                "traefik.http.routers.a.rule": "Host(`app.ventiplan.pl`)",
                "traefik.http.routers.b.rule": "Host(`app.ventiplan.pl`)",
                "traefik.http.routers.c.rule": "Host(`app.ventiplan.pl`) && PathPrefix(`/api`)",
            }),
        ]))
        service.refresh()
        urls = sorted(entry["targets"][0] for entry in service.http_sd())
        self.assertEqual(urls, ["https://app.ventiplan.pl", "https://app.ventiplan.pl/api"])

    def test_skips(self):
        docker = FakeDocker(services=[
            make_service("monitoring_grafana", {"traefik.http.routers.g.rule": "Host(`g.pl`)"}),
            make_service("ventiplan-prod_api", {
                "traefik.http.routers.a.rule": "Host(`a.pl`)", "monitoring.io/skip": "true",
            }),
            make_service("ventiplan-prod_web", {
                "traefik.http.routers.w.rule": "Host(`w.pl`)", "traefik.enable": "false",
            }),
            make_service("ventiplan-prod_ok", {"traefik.http.routers.o.rule": "Host(`o.pl`)"}),
        ])
        service = build_service(docker, config=make_config(SKIP_STACKS="monitoring"))
        service.refresh()
        self.assertEqual([entry["targets"][0] for entry in service.http_sd()], ["https://o.pl"])

    def test_skip_services_variable(self):
        docker = FakeDocker(services=[
            make_service("ventiplan-prod_api", {"traefik.http.routers.a.rule": "Host(`a.pl`)"}),
            make_service("ventiplan-prod_web", {"traefik.http.routers.w.rule": "Host(`w.pl`)"}),
        ])
        service = build_service(docker, config=make_config(SKIP_SERVICES="ventiplan-prod_api"))
        service.refresh()
        self.assertEqual([entry["targets"][0] for entry in service.http_sd()], ["https://w.pl"])


# --------------------------------------------------------------------------
# Sondy: raz na cykl, na unikalny URL, bez celów `skip`
# --------------------------------------------------------------------------
class ProbeTests(unittest.TestCase):
    def test_probe_runs_once_per_unique_url(self):
        calls = []

        def probe(url, timeout=5.0):
            calls.append(url)
            return discovery.ProbeResult("ok", 200, 0.1)

        docker = FakeDocker(services=[
            make_service("ventiplan-prod_api", {"traefik.http.routers.a.rule": "Host(`wspolny.pl`)"}),
            make_service("ventiplan-prod_web", {"traefik.http.routers.w.rule": "Host(`wspolny.pl`)"}),
            make_service("ventiplan-prod_inne", {"traefik.http.routers.i.rule": "Host(`inne.pl`)"}),
        ])
        service = build_service(docker, probe=probe)
        service.refresh()
        self.assertEqual(calls, ["https://inne.pl", "https://wspolny.pl"])
        # metryki nadal mają wpis na każdy cel (stack+service+url)
        metrics = service.metrics()
        self.assertIn('discovery_probe_success{service="api",stack="ventiplan-prod",url="https://wspolny.pl"} 1', metrics)
        self.assertIn('discovery_probe_success{service="web",stack="ventiplan-prod",url="https://wspolny.pl"} 1', metrics)

    def test_skip_severity_is_not_probed(self):
        calls = []

        def probe(url, timeout=5.0):
            calls.append(url)
            return discovery.ProbeResult("ok", 200, 0.1)

        docker = FakeDocker(services=[
            make_service("ventiplan-prod_api", {
                "traefik.http.routers.a.rule": "Host(`a.pl`)",
                "monitoring.io/severity": "skip",
            }),
        ])
        service = build_service(docker, probe=probe)
        service.refresh()
        self.assertEqual(calls, [])
        self.assertEqual(service.http_sd(), [])

    def test_probe_failure_marks_critical(self):
        def probe(url, timeout=5.0):
            raise OSError("connection refused")

        docker = FakeDocker(services=[
            make_service("ventiplan-prod_api", {"traefik.http.routers.a.rule": "Host(`a.pl`)"}),
        ])
        service = build_service(docker, probe=probe)
        service.refresh()
        self.assertIn('discovery_probe_success{service="api",stack="ventiplan-prod",url="https://a.pl"} 0',
                      service.metrics())
        self.assertEqual(service.checks_section()[0]["state"], "critical")


# --------------------------------------------------------------------------
# Metryki
# --------------------------------------------------------------------------
class MetricsTests(unittest.TestCase):
    def test_all_families_have_help_and_type(self):
        text = discovery.render_metrics(discovery.Snapshot())
        for name, metric_type, _help in discovery.METRIC_FAMILIES:
            self.assertIn("# TYPE %s %s" % (name, metric_type), text)
            self.assertIn("# HELP %s " % name, text)

    def test_label_escaping(self):
        snapshot = discovery.Snapshot()
        snapshot.up = True
        snapshot.services = [{
            "stack": 'sta"ck', "service": "svc\\x", "desired": 1, "running": 1,
            "states": {"running": 1}, "failed_1h": 0, "image": "img\nx", "updated_at": 1.0,
        }]
        text = discovery.render_metrics(snapshot)
        self.assertIn('swarm_service_info{image="img\\nx",service="svc\\\\x",stack="sta\\"ck"} 1', text)

    def test_values_and_states(self):
        text = discovery.render_metrics(discovery.Snapshot())
        self.assertIn("discovery_up 0", text)
        self.assertIn("discovery_new_services_total 0", text)
        self.assertIn("swarm_service_tasks{", discovery.render_metrics(self._snapshot_with_tasks()))

    @staticmethod
    def _snapshot_with_tasks():
        snapshot = discovery.Snapshot()
        snapshot.services = [{
            "stack": "s", "service": "x", "desired": 2, "running": 1,
            "states": {"running": 1, "failed": 1}, "failed_1h": 1, "image": "img", "updated_at": 5.0,
        }]
        return snapshot

    def test_task_state_mapping_and_unknown(self):
        self.assertEqual(discovery.normalize_task_state("Running"), "running")
        self.assertEqual(discovery.normalize_task_state("shutdown"), "shutdown")
        self.assertEqual(discovery.normalize_task_state("assigned"), "other")
        self.assertEqual(discovery.normalize_task_state(None), "other")

    def test_failed_tasks_only_within_last_hour(self):
        now = datetime(2026, 9, 21, 20, 0, 0, tzinfo=timezone.utc).timestamp()
        tasks = [
            make_task("s", state="failed", created="2026-09-21T19:30:00Z"),
            make_task("s", state="failed", created="2026-09-21T10:00:00Z"),
            make_task("s", state="running", created="2026-09-21T19:59:00Z"),
        ]
        stats = discovery.aggregate_tasks(tasks, now)
        self.assertEqual(stats["s"]["failed_1h"], 1)
        self.assertEqual(stats["s"]["running"], 1)


# --------------------------------------------------------------------------
# Global / Job mode, nowe usługi, pełny cykl
# --------------------------------------------------------------------------
class ReplicaModeTests(unittest.TestCase):
    def test_global_service_desired_equals_running(self):
        tasks = [make_task("svc-monitoring_node-exporter") for _ in range(3)]
        docker = FakeDocker(
            services=[make_service("monitoring_node-exporter", mode={"Global": {}})],
            tasks=tasks,
        )
        service = build_service(docker)
        service.refresh()
        metrics = service.metrics()
        self.assertIn('swarm_service_desired_replicas{service="node-exporter",stack="monitoring"} 3', metrics)
        self.assertIn('swarm_service_running_replicas{service="node-exporter",stack="monitoring"} 3', metrics)
        stack = service.api_json()["stacks"][0]
        self.assertEqual(stack["services"][0]["desired"], 3)
        self.assertEqual(stack["services"][0]["replicas_text"], "3/3")

    def test_replicated_mode_uses_spec_replicas(self):
        spec_replicated = {"Replicated": {"Replicas": 4}}
        self.assertEqual(discovery.desired_replicas({"Mode": spec_replicated}, 1), 4)

    def test_global_without_running_tasks_is_zero_not_error(self):
        self.assertEqual(discovery.desired_replicas({"Mode": {"Global": {}}}, 0), 0)

    def test_unknown_mode_falls_back_to_running(self):
        self.assertEqual(discovery.desired_replicas({}, 2), 2)

    def test_service_mode_detection(self):
        self.assertEqual(discovery.service_mode({"Mode": {"Global": {}}}), "global")
        self.assertEqual(discovery.service_mode({"Mode": {"Replicated": {"Replicas": 1}}}), "replicated")
        self.assertEqual(discovery.service_mode({"Mode": {"ReplicatedJob": {}}}), "replicated-job")
        self.assertEqual(discovery.service_mode({}), "unknown")


class NewServiceTrackerTests(unittest.TestCase):
    def test_counts_only_new_keys(self):
        tracker = discovery.NewServiceTracker()
        self.assertEqual(tracker.observe(["a", "b"]), 2)
        self.assertEqual(tracker.observe(["b", "c"]), 3)
        self.assertEqual(tracker.observe(["a", "b", "c"]), 3)

    def test_snapshot_counter_grows_once(self):
        docker = FakeDocker(services=[
            make_service("ventiplan-prod_api", {"traefik.http.routers.a.rule": "Host(`a.pl`)"}),
        ])
        service = build_service(docker)
        service.refresh()
        self.assertIn("discovery_new_services_total 1", service.metrics())
        service.refresh()
        self.assertIn("discovery_new_services_total 1", service.metrics())


class RefreshAndHealthTests(unittest.TestCase):
    def test_failed_refresh_keeps_service_alive_and_sets_up_zero(self):
        service = build_service(FakeDocker(error="brak połączenia z Docker API"))
        self.assertFalse(service.refresh())
        metrics = service.metrics()
        self.assertIn("discovery_up 0", metrics)
        self.assertFalse(service.health()["up"])
        self.assertIn("brak połączenia", service.health()["last_error"])

    def test_health_up_after_success(self):
        service = build_service(FakeDocker(services=[make_service("a_b")]))
        service.refresh()
        self.assertTrue(service.health()["up"])
        self.assertIn("discovery_up 1", service.metrics())

    def test_container_metrics(self):
        docker = FakeDocker(
            services=[make_service("ventiplan-prod_api", {"traefik.http.routers.a.rule": "Host(`a.pl`)"})],
            containers=[make_container("cid1", "ventiplan-prod_api")],
            inspect={"cid1": {"State": {"Health": {"Status": "healthy"}, "RestartCount": 0}}},
            stats={"cid1": {
                "cpu_stats": {"cpu_usage": {"total_usage": 200}, "system_cpu_usage": 2000, "online_cpus": 2},
                "precpu_stats": {"cpu_usage": {"total_usage": 100}, "system_cpu_usage": 1000},
                "memory_stats": {"usage": 1048576, "limit": 536870912},
            }},
            df={
                "LayersSize": 999,
                "Images": [{"Size": 100, "Containers": 0}, {"Size": 500, "Containers": 3}],
                "Volumes": [
                    {"UsageData": {"Size": 1024, "RefCount": 0}},
                    {"UsageData": {"Size": 2048, "RefCount": 2}},
                ],
            },
        )
        service = build_service(docker)
        service.refresh()
        metrics = service.metrics()
        self.assertIn('swarm_container_cpu_percent{container="ventiplan-prod_api.1.abc",service="api",stack="ventiplan-prod"} 20', metrics)
        self.assertIn('swarm_container_memory_bytes{container="ventiplan-prod_api.1.abc",service="api",stack="ventiplan-prod"} 1048576', metrics)
        self.assertIn('swarm_container_health{container="ventiplan-prod_api.1.abc",health="healthy",service="api",stack="ventiplan-prod"} 1', metrics)
        self.assertIn("docker_images_reclaimable_bytes 100", metrics)
        self.assertIn("docker_volumes_reclaimable_bytes 1024", metrics)
        self.assertIn("docker_containers 1", metrics)
        self.assertIn("docker_containers_running 1", metrics)

    def test_cpu_formula(self):
        stats = {
            "cpu_stats": {"cpu_usage": {"total_usage": 300}, "system_cpu_usage": 3000, "online_cpus": 4},
            "precpu_stats": {"cpu_usage": {"total_usage": 100}, "system_cpu_usage": 1000},
        }
        self.assertAlmostEqual(discovery.compute_cpu_percent(stats), (200 / 2000) * 4 * 100)

    def test_cpu_formula_without_system_delta(self):
        self.assertEqual(discovery.compute_cpu_percent({}), 0.0)

    def test_images_reclaimable_falls_back_to_layers_size(self):
        summary = discovery.docker_df_summary({"LayersSize": 4096, "Images": [{"Size": 10}]})
        self.assertEqual(summary["images_reclaimable_bytes"], 4096)


# --------------------------------------------------------------------------
# api.json
# --------------------------------------------------------------------------
class ApiJsonTests(unittest.TestCase):
    def _service(self):
        def json_get(url, timeout=5.0):
            if "/api/v1/query" in url:
                query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["query"][0]
                values = {
                    "node_load1": "0.42",
                    "node_memory_MemTotal_bytes": "1000",
                    "node_memory_MemAvailable_bytes": "400",
                    'node_filesystem_size_bytes{mountpoint="/"}': "1000",
                    'node_filesystem_avail_bytes{mountpoint="/"}': "600",
                    'node_filesystem_files{mountpoint="/"}': "1000",
                    'node_filesystem_files_free{mountpoint="/"}': "800",
                    "time() - node_boot_time_seconds": "3600",
                }
                if query in values:
                    return {"data": {"result": [{"value": [0, values[query]]}]}}
                return {"data": {"result": []}}
            if url.endswith("/backup.json"):
                return {"state": "ok", "last_success_at": "2026-09-21T03:00:00Z", "age_hours": 16.5,
                        "size_bytes": 0, "objects_in_r2": 0, "restore_test_days": 12}
            if url.endswith("/api/v2/alerts"):
                return [{"labels": {"alertname": "HighCpu", "severity": "warning", "stack": "monitoring"},
                         "annotations": {"summary": "Wysokie CPU"}, "startsAt": "2026-09-21T18:00:00Z"}]
            raise AssertionError("nieoczekiwany URL: %s" % url)

        docker = FakeDocker(
            services=[make_service("ventiplan-prod_api", {
                "traefik.http.routers.a.rule": "Host(`app.ventiplan.pl`) && PathPrefix(`/health`)",
                "monitoring.io/health-path": "/health",
            }, replicas=1)],
            tasks=[make_task("svc-ventiplan-prod_api")],
        )
        return build_service(docker, json_get=json_get)

    def test_schema_and_values(self):
        service = self._service()
        service.refresh()
        payload = service.api_json()
        self.assertEqual(
            list(payload.keys()),
            ["generated_at", "overall", "host", "checks", "stacks", "certs", "backup", "alerts", "security", "tools"],
        )
        self.assertTrue(payload["generated_at"].endswith("Z"))
        self.assertEqual(payload["overall"], "ok")
        self.assertEqual(payload["host"]["mem_used_percent"], 60.0)
        self.assertEqual(payload["host"]["disk_used_percent"], 40.0)
        self.assertEqual(payload["host"]["inodes_used_percent"], 20.0)
        self.assertEqual(payload["host"]["uptime_seconds"], 3600)
        check = payload["checks"][0]
        self.assertEqual(check["url"], "https://app.ventiplan.pl/health")
        self.assertEqual(check["state"], "ok")
        self.assertEqual(check["kind"], "http")
        self.assertEqual(check["latency_ms"], 209)
        self.assertIn("HTTP 200", check["detail"])
        self.assertIn("0,21", check["detail"])
        self.assertIn("Z", check["since"])
        self.assertEqual(payload["stacks"][0]["name"], "ventiplan-prod")
        self.assertEqual(payload["stacks"][0]["state"], "ok")
        self.assertEqual(payload["backup"]["state"], "ok")
        self.assertEqual(payload["alerts"][0]["name"], "HighCpu")
        self.assertEqual(payload["security"]["state"], "unknown")
        self.assertEqual(len(payload["certs"]), 1)
        self.assertEqual(payload["certs"][0]["host"], "app.ventiplan.pl")
        tools = {tool["id"]: tool for tool in payload["tools"]}
        self.assertEqual(tools["grafana"]["url"], "/grafana")
        self.assertTrue(tools["grafana"]["embed"])
        self.assertFalse(tools["healthchecks"]["embed"])
        self.assertEqual(tools["healthchecks"]["state"], "unknown")
        self.assertEqual(tools["portainer"]["url"], "https://portainer.subscribeit.pl")

    def test_overall_critical_when_probe_critical(self):
        def probe(url, timeout=5.0):
            return discovery.ProbeResult("critical", 503, 1.0)

        service = self._service()
        service.probe_fn = probe
        service.refresh()
        self.assertEqual(service.api_json()["overall"], "critical")

    def test_overall_critical_when_replicas_missing(self):
        def json_get(url, timeout=5.0):
            if "/api/v1/query" in url:
                return {"data": {"result": []}}
            if url.endswith("/backup.json"):
                return {"state": "ok", "restore_test_days": 12}
            if url.endswith("/api/v2/alerts"):
                return []
            raise AssertionError("nieoczekiwany URL: %s" % url)

        docker = FakeDocker(
            services=[make_service("ventiplan-prod_api", {"traefik.http.routers.a.rule": "Host(`a.pl`)"},
                                   replicas=2)],
            tasks=[make_task("svc-ventiplan-prod_api")],
        )
        service = build_service(docker, json_get=json_get)
        service.refresh()
        self.assertEqual(service.api_json()["overall"], "critical")

    def test_alerts_section_ignores_unexpected_payload(self):
        docker = FakeDocker(services=[make_service("a_b")],
                            tasks=[make_task("svc-a_b")])
        service = build_service(docker, json_get=lambda url, timeout=5.0: {"data": {"result": []}})
        service.refresh()
        self.assertEqual(service.api_json()["alerts"], [])

    def test_overall_warning_without_prometheus(self):
        docker = FakeDocker(
            services=[make_service("ventiplan-prod_api", {"traefik.http.routers.a.rule": "Host(`a.pl`)"},
                                   replicas=1)],
            tasks=[make_task("svc-ventiplan-prod_api")],
        )
        service = build_service(docker, json_get=lambda url, timeout=5.0: (_ for _ in ()).throw(OSError("brak")))
        service.refresh()
        self.assertEqual(service.api_json()["overall"], "warning")

    def test_backup_unknown_when_health_ping_missing(self):
        docker = FakeDocker(services=[make_service("a_b")])
        service = build_service(docker, json_get=lambda url, timeout=5.0: (_ for _ in ()).throw(OSError("brak")))
        service.refresh()
        self.assertEqual(service.api_json()["backup"]["state"], "unknown")


class BrokenDependencyTests(unittest.TestCase):
    """
    Uszkodzone odpowiedzi Prometheusa, Alertmanagera i health-ping nie mogą
    wywrócić /status/api.json — panel ma dostać 200 z kompletnym schematem.
    """

    SCHEMA = ["generated_at", "overall", "host", "checks", "stacks", "certs",
              "backup", "alerts", "security", "tools"]

    def _service(self, json_get, services=None, tasks=None, containers=None):
        docker = FakeDocker(
            services=services if services is not None else [
                make_service("ventiplan-prod_api", {"traefik.http.routers.a.rule": "Host(`a.pl`)"}, replicas=1),
            ],
            tasks=tasks if tasks is not None else [make_task("svc-ventiplan-prod_api")],
            containers=containers,
        )
        service = build_service(docker, json_get=json_get)
        service.refresh()
        return service

    def _assert_schema(self, payload):
        self.assertEqual(list(payload.keys()), self.SCHEMA)
        self.assertIn(payload["overall"], ("ok", "warning", "critical"))
        for key in ("host", "backup", "security"):
            self.assertIsInstance(payload[key], dict, key)
        for key in ("checks", "stacks", "certs", "alerts", "tools"):
            self.assertIsInstance(payload[key], list, key)
        for key in ("cpu_percent", "load1", "disk_used_percent", "uptime_seconds", "time_utc"):
            self.assertIn(key, payload["host"])
        self.assertIn("state", payload["security"])
        self.assertIn("state", payload["backup"])
        # całość musi się serializować do JSON-a (to wysyła handler)
        self.assertIsInstance(json.dumps(payload), str)

    def test_garbage_from_all_dependencies(self):
        def json_get(url, timeout=5.0):
            if "/api/v1/query" in url:
                return "<html>502 Bad Gateway</html>"
            if url.endswith("/api/v2/alerts"):
                return {"status": "error", "alerts": "nie-lista"}
            if url.endswith("/backup.json"):
                return ["to", "nie", "jest", "obiekt"]
            raise AssertionError("nieoczekiwany URL: %s" % url)

        service = self._service(json_get)
        self._assert_schema(service.api_json())
        payload = service.api_json()
        self.assertEqual(payload["alerts"], [])
        self.assertEqual(payload["backup"], discovery.empty_backup())
        self.assertEqual(payload["host"]["mem_total_bytes"], 0)
        self.assertEqual(payload["overall"], "warning")

    def test_alertmanager_list_with_non_dict_items(self):
        def json_get(url, timeout=5.0):
            if "/api/v1/query" in url:
                return {"data": {"result": [{"value": [0, "1"]}]}}
            if url.endswith("/api/v2/alerts"):
                return ["śmieci", 42, None, {"labels": {"alertname": "Prawdziwy", "severity": "critical"}}]
            if url.endswith("/backup.json"):
                return {"state": "ok", "restore_test_days": 12}
            raise AssertionError(url)

        payload = self._service(json_get).api_json()
        self._assert_schema(payload)
        self.assertEqual([alert["name"] for alert in payload["alerts"]], ["Prawdziwy"])
        # same alerty NIE wpływają na `overall` — zgodnie ze specyfikacją decydują
        # checks, repliki, discovery_up, Prometheus i sekcja backupu
        self.assertEqual(payload["overall"], "ok")

    def test_prometheus_returns_broken_shapes(self):
        shapes = [
            "nie-json",
            123,
            None,
            {"data": None},
            {"data": {"result": "nie-lista"}},
            {"data": {"result": [{"value": "nie-para"}]}},
            {"data": {"result": [{"value": [0, "NaN"]}]}},
            {"data": {"result": [{"value": [0, "+Inf"]}]}},
        ]
        for shape in shapes:
            with self.subTest(shape=shape):
                def json_get(url, _shape=shape, timeout=5.0):
                    if "/api/v1/query" in url:
                        return _shape
                    if url.endswith("/api/v2/alerts"):
                        return []
                    if url.endswith("/backup.json"):
                        return {"state": "ok"}
                    raise AssertionError(url)

                service = self._service(json_get)
                payload = service.api_json()
                self._assert_schema(payload)
                self.assertEqual(payload["host"]["mem_total_bytes"], 0)
                self.assertEqual(payload["host"]["uptime_seconds"], 0)
                self.assertEqual(payload["overall"], "warning")

    def test_corrupted_snapshot_entries_do_not_break_api_json(self):
        service = self._service(lambda url, timeout=5.0: {})
        service.snapshot.certs["zly.pl"] = "śmieci"          # nie-dict
        service.snapshot.probes["https://a.pl"] = object()   # obiekt bez atrybutów
        payload = service.api_json()
        self._assert_schema(payload)
        certs = {cert["host"]: cert for cert in payload["certs"]}
        self.assertEqual(certs["zly.pl"]["state"], "unknown")
        self.assertEqual(certs["zly.pl"]["days_left"], 0)
        self.assertEqual(payload["checks"][0]["state"], "unknown")

    def test_section_failure_falls_back_to_default(self):
        service = self._service(lambda url, timeout=5.0: {})
        service.checks_section = lambda: (_ for _ in ()).throw(RuntimeError("bum"))
        payload = service.api_json()
        self._assert_schema(payload)
        self.assertEqual(payload["checks"], [])

    def test_docker_garbage_does_not_break_refresh(self):
        docker = FakeDocker(
            services=["to nie jest słownik", None, 7],
            tasks="nie-lista",
            containers={"nie": "lista"},
            df="nie-obiekt",
        )
        service = build_service(docker)
        self.assertTrue(service.refresh())
        payload = service.api_json()
        self._assert_schema(payload)
        self.assertEqual(payload["stacks"], [])
        self.assertIn("discovery_up 1", service.metrics())


# --------------------------------------------------------------------------
# Klient Dockera: tylko GET, chunked, obsługa błędów
# --------------------------------------------------------------------------
class DockerClientTests(unittest.TestCase):
    @staticmethod
    def _response(body, chunked=False, status=200):
        if chunked:
            payload = b"%x\r\n%s\r\n0\r\n\r\n" % (len(body), body)
            headers = b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nTransfer-Encoding: chunked\r\n\r\n"
        else:
            payload = body
            headers = b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: %d\r\n\r\n" % len(body)
        return headers + payload

    def test_chunked_body_is_decoded(self):
        body = json.dumps([{"a": 1}]).encode()
        client = discovery.DockerClient(fetcher=lambda path: self._response(body, chunked=True))
        self.assertEqual(client.services(), [{"a": 1}])

    def test_plain_body_is_decoded(self):
        body = json.dumps({"Id": "x"}).encode()
        client = discovery.DockerClient(fetcher=lambda path: self._response(body))
        self.assertEqual(client.container_inspect("x"), {"Id": "x"})

    def test_paths_are_read_only_endpoints(self):
        seen = []

        def fetcher(path):
            seen.append(path)
            return self._response(b"[]")

        client = discovery.DockerClient(fetcher=fetcher)
        client.services()
        client.tasks()
        client.containers()
        client.system_df()
        client.container_logs("abc", tail=10)
        self.assertEqual(seen, [
            "/services",
            "/tasks",
            "/containers/json?all=1",
            "/system/df",
            "/containers/abc/logs?stdout=1&stderr=1&tail=10",
        ])

    def test_http_error_raises_docker_error(self):
        client = discovery.DockerClient(
            fetcher=lambda path: b"HTTP/1.1 500 Internal Server Error\r\nContent-Length: 0\r\n\r\n"
        )
        with self.assertRaises(discovery.DockerError):
            client.services()

    def test_transport_error_raises_docker_error(self):
        def fetcher(path):
            raise OSError("no such file")

        with self.assertRaises(discovery.DockerError):
            discovery.DockerClient(fetcher=fetcher).services()

    def test_source_contains_only_get_requests(self):
        source = (ROOT / "services" / "discovery" / "main.py").read_text(encoding="utf-8")
        self.assertIn('"GET %s HTTP/1.1', source)
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            self.assertNotIn('"%s %%s HTTP/1.1' % method, source)
        self.assertNotIn('method="POST"', source)
        self.assertNotIn('method="DELETE"', source)


class MetricLintTests(unittest.TestCase):
    """
    Odpowiednik `promtool check metrics`: konwencja `_total` tylko dla liczników,
    spójność TYPE/HELP z faktycznie wystawionymi seriami i brak duplikatów serii
    (duplikat oznacza odrzucenie całego scrape'a przez Prometheusa).
    """

    def _rendered(self):
        docker = FakeDocker(
            services=[
                make_service("ventiplan-prod_api", {
                    "traefik.http.routers.api.rule": "Host(`a.pl`) && PathPrefix(`/api`)",
                }, replicas=2),
                make_service("monitoring_grafana", {
                    "traefik.http.routers.g.rule": "Host(`g.pl`)"}, mode={"Global": {}}),
            ],
            tasks=[make_task("svc-ventiplan-prod_api"), make_task("svc-monitoring_grafana")],
            containers=[make_container("cid1", "ventiplan-prod_api")],
            inspect={"cid1": {"State": {"Health": {"Status": "healthy"}}}},
            stats={"cid1": {"cpu_stats": {"cpu_usage": {"total_usage": 10}, "system_cpu_usage": 100,
                                          "online_cpus": 1},
                            "precpu_stats": {"cpu_usage": {"total_usage": 5}, "system_cpu_usage": 50},
                            "memory_stats": {"usage": 10, "limit": 100}}},
        )
        service = build_service(docker)
        service.refresh()
        return service.metrics()

    def test_total_suffix_only_for_counters(self):
        for name, metric_type, _help in discovery.METRIC_FAMILIES:
            if name.endswith("_total"):
                self.assertEqual(
                    metric_type, "counter",
                    "%s kończy się na _total, ale nie jest licznikiem" % name,
                )

    def test_type_and_help_lines_match_families(self):
        text = self._rendered()
        declared = dict(re.findall(r"^# TYPE (\S+) (\S+)$", text, re.MULTILINE))
        self.assertEqual(declared, {name: mtype for name, mtype, _ in discovery.METRIC_FAMILIES})
        for name, _mtype, _help in discovery.METRIC_FAMILIES:
            self.assertIn("# HELP %s " % name, text)

    def test_every_sample_belongs_to_a_declared_family(self):
        text = self._rendered()
        declared = set(re.findall(r"^# TYPE (\S+) ", text, re.MULTILINE))
        for line in text.splitlines():
            if line.startswith("#") or not line.strip():
                continue
            sample = line.split("{", 1)[0].split(" ", 1)[0]
            self.assertIn(sample, declared, "seria bez rodziny: %s" % line)

    def test_no_duplicate_series(self):
        text = self._rendered()
        seen = set()
        for line in text.splitlines():
            if line.startswith("#") or not line.strip():
                continue
            key = line.rsplit(" ", 1)[0]
            self.assertNotIn(key, seen, "duplikat serii (Prometheus odrzuci scrape): %s" % key)
            seen.add(key)

    def test_values_are_parseable_floats(self):
        text = self._rendered()
        for line in text.splitlines():
            if line.startswith("#") or not line.strip():
                continue
            value = line.rsplit(" ", 1)[1]
            float(value)  # nie może rzucić


class ConfigTests(unittest.TestCase):
    def test_unix_socket_prefix(self):
        self.assertEqual(discovery.Config(env={"DOCKER_HOST": "unix:///var/run/docker.sock"}).docker_socket,
                         "/var/run/docker.sock")

    def test_tcp_host_is_rejected(self):
        with self.assertRaises(discovery.ConfigError):
            discovery.Config(env={"DOCKER_HOST": "tcp://1.2.3.4:2375"})

    def test_defaults(self):
        config = discovery.Config(env={})
        self.assertEqual(config.refresh_seconds, 30.0)
        self.assertEqual(config.blackbox_module, "http_2xx")
        self.assertEqual(config.probe_timeout, 5.0)
        self.assertEqual(config.prometheus_url, "http://prometheus:9090")
        self.assertEqual(config.port, 8080)
        self.assertEqual(config.default_probe_path, "")

    def test_invalid_numbers_fall_back_to_defaults(self):
        config = discovery.Config(env={"REFRESH_SECONDS": "abc", "PROBE_TIMEOUT_SECONDS": "0"})
        self.assertEqual(config.refresh_seconds, 30.0)
        self.assertEqual(config.probe_timeout, 0.5)


if __name__ == "__main__":
    unittest.main()
