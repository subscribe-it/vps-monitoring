"""Kontrakt usługi Duplicati w stacku Swarma bez zewnętrznych zależności."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
COMPOSE = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")


class BackupComposeTests(unittest.TestCase):
    def test_image_is_pinned_and_service_has_no_public_surface(self):
        self.assertIn(
            "image: duplicati/duplicati@sha256:e32e280cc30e98ac5cea8d2b339cd19810b1b39e638fb9d39253786630104de0",
            COMPOSE,
        )
        service = COMPOSE.split("\n  duplicati:\n", 1)[1].split("\n  # ---------------------------------------------------------------------------", 1)[0]
        self.assertNotIn("\n    ports:", service)
        self.assertNotIn("traefik.", service)
        self.assertIn("\n      - monitoring\n", service)

    def test_recovery_sources_are_read_only_and_state_is_dedicated(self):
        self.assertIn("- /var/lib/docker/volumes:/source/docker-volumes:ro", COMPOSE)
        self.assertIn("- /var/lib/docker/swarm:/source/docker-swarm:ro", COMPOSE)
        self.assertIn("- /etc/docker:/source/docker-config:ro", COMPOSE)
        self.assertNotIn("- /:/host:ro", COMPOSE)
        self.assertIn("- duplicati_data_v2:/data", COMPOSE)
        self.assertIn("/source/docker-volumes /source/docker-swarm /source/docker-config", COMPOSE)
        self.assertIn("--exclude=/source/docker-volumes/monitoring_duplicati_data_v2/**", COMPOSE)
        self.assertIn("--dbpath=/data/duplicati-volumes.sqlite", COMPOSE)
        self.assertIn("touch /data/backup-running", COMPOSE)
        self.assertIn("if [ -f /data/backup-running ]; then exit 0; fi", COMPOSE)

    def test_secrets_are_external_and_not_inline(self):
        self.assertIn("external: true\n    name: ${DUPLICATI_SECRET_PROVIDER_NAME", COMPOSE)
        self.assertIn("external: true\n    name: ${MONITORING_R2_ACCESS_SECRET_NAME", COMPOSE)
        self.assertIn("external: true\n    name: ${MONITORING_R2_SECRET_SECRET_NAME", COMPOSE)
        self.assertIn("file-secret:///run/secrets/duplicati-secretprovider", COMPOSE)
        self.assertIn("'--passphrase=$$backup-passphrase'", COMPOSE)
        self.assertNotIn("ACCESS_KEY_ID", COMPOSE)
        self.assertNotIn("SECRET_ACCESS_KEY", COMPOSE)

    def test_watchdog_reads_r2_credentials_from_secret_files(self):
        self.assertIn(
            "R2_ACCESS_KEY_FILE=${R2_ACCESS_KEY_FILE:-/run/secrets/monitoring-r2-access}",
            COMPOSE,
        )
        self.assertIn(
            "R2_SECRET_KEY_FILE=${R2_SECRET_KEY_FILE:-/run/secrets/monitoring-r2-secret}",
            COMPOSE,
        )
        self.assertIn("source: monitoring_r2_access\n        target: monitoring-r2-access", COMPOSE)
        self.assertIn("source: monitoring_r2_secret\n        target: monitoring-r2-secret", COMPOSE)


if __name__ == "__main__":
    unittest.main()
