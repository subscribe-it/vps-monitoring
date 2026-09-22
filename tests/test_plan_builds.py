"""Testy planisty budowy obrazów (scripts/ci/plan_builds.py).

Pilnuje, żeby po zmianie plików budowały się tylko potrzebne obrazy — pomyłka
w tej mapie oznacza albo spalone minuty CI (budowa wszystkiego), albo — gorzej —
wdrożenie starego obrazu, bo zmiana nie została zbudowana.
"""
import importlib.util
import pathlib
import sys
import unittest

PLIK = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "ci" / "plan_builds.py"
spec = importlib.util.spec_from_file_location("plan_builds", PLIK)
plan = importlib.util.module_from_spec(spec)
sys.modules["plan_builds"] = plan
spec.loader.exec_module(plan)


class PlanBuildsTests(unittest.TestCase):
    def wszystkie(self):
        return set(plan.mapa_obrazow())

    def test_mapa_ma_wszystkie_obrazy(self):
        """Każdy obraz z compose musi mieć Dockerfile w mapie planisty."""
        import re
        compose = (PLIK.parent.parent.parent / "docker-compose.yml").read_text(encoding="utf-8")
        obrazy = set(re.findall(r"ghcr\.io/subscribe-it/vps-monitoring-([a-z0-9-]+):", compose))
        brak = sorted(obrazy - self.wszystkie())
        self.assertEqual(brak, [], f"obrazy bez Dockerfile w mapie: {brak}")

    def test_zmiana_konfiguracji_buduje_tylko_jeden_obraz(self):
        self.assertEqual(plan.obrazy_do_budowy(["config/auth/default.conf"]), ["auth"])
        self.assertEqual(plan.obrazy_do_budowy(["config/loki/rules/fake/postgres.yml"]), ["loki"])
        self.assertEqual(plan.obrazy_do_budowy(["config/grafana/dashboards/host.json"]), ["grafana"])

    def test_zmiana_kodu_serwisu_buduje_ten_serwis(self):
        self.assertEqual(plan.obrazy_do_budowy(["services/notifier/main.py"]), ["notifier"])
        self.assertEqual(plan.obrazy_do_budowy(["services/health-ping/s3.py"]), ["health-ping"])

    def test_panel_ma_wlasny_kontekst(self):
        self.assertEqual(plan.obrazy_do_budowy(["panel/src/pages/index.astro"]), ["panel"])
        self.assertEqual(plan.obrazy_do_budowy(["panel/Dockerfile"]), ["panel"])

    def test_zmiana_compose_nie_buduje_obrazow(self):
        """Compose zmienia WDROŻENIE, nie zawartość obrazów — deploy bez budowy."""
        self.assertEqual(plan.obrazy_do_budowy(["docker-compose.yml"]), [])
        # …ale compose obok zmiany w obrazie: budujemy tylko ten obraz.
        self.assertEqual(plan.obrazy_do_budowy(["docker-compose.yml", "config/auth/default.conf"]), ["auth"])

    def test_zmiana_tylko_dokumentacji_nie_buduje_nic(self):
        for plik in ("README.md", "docs/RUNBOOK.md", ".github/workflows/validate.yml"):
            self.assertEqual(plan.obrazy_do_budowy([plik]), [], f"{plik} nie powinien nic budować")

    def test_brak_informacji_o_zmianach_buduje_wszystko(self):
        """Bezpieczny fallback: gdy nie wiemy, co się zmieniło, budujemy wszystko."""
        self.assertEqual(sorted(plan.obrazy_do_budowy(None)), sorted(self.wszystkie()))

    def test_dockerfile_serwisu_jest_brany_pod_uwage(self):
        self.assertIn("promtail", plan.obrazy_do_budowy(["dockerfiles/promtail/Dockerfile"]))


if __name__ == "__main__":
    unittest.main()
