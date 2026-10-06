#!/usr/bin/env python3
"""Regression tests for the side-effect-free production readiness source audit."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_AUDIT_PATH = Path(__file__).resolve().parent / "audit-production-readiness.py"
_SPEC = importlib.util.spec_from_file_location("production_readiness_audit", _AUDIT_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"cannot load production readiness audit from {_AUDIT_PATH}")
_AUDIT = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _AUDIT
_SPEC.loader.exec_module(_AUDIT)


class ImageSentinelTests(unittest.TestCase):
    def test_only_repeated_full_length_sha256_values_are_sentinels(self) -> None:
        content = """
image: ghcr.io/example/app@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
other: ghcr.io/example/app@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
short: sha256:aaaa
"""
        self.assertEqual(_AUDIT._image_sentinels(content), ["values-prod.yaml:2"])

    def test_digest_in_comment_is_not_reported(self) -> None:
        content = "# image: app@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n"
        self.assertEqual(_AUDIT._image_sentinels(content), [])


class WorkflowBuildDetectionTests(unittest.TestCase):
    def test_migration_path_comment_does_not_count_as_a_build(self) -> None:
        workflow = "# file: infra/migrations/Dockerfile\n- uses: docker/build-push-action@v1\n  with:\n    file: services/api/Dockerfile\n"
        self.assertFalse(_AUDIT._workflow_builds_migration(workflow))

    def test_migration_build_action_configuration_is_detected(self) -> None:
        workflow = "- uses: docker/build-push-action@v1\n  with:\n    context: .\n    file: infra/migrations/Dockerfile\n    push: false\n"
        self.assertTrue(_AUDIT._workflow_builds_migration(workflow))


class RecoveryEvidencePredicateTests(unittest.TestCase):
    def test_postgres_requires_pitr_verified_flags_and_valid_measurement(self) -> None:
        base = {
            "postgres": {
                "mechanism": "pgbackrest_wal",
                "backup_ok": True,
                "restore_ok": True,
                "rpo_pass": True,
                "rpo_measured_sec": 12,
                "rpo_target_sec": 300,
            }
        }
        self.assertTrue(_AUDIT._postgres_rpo_accepted(base))
        for changes in (
            {"mechanism": "unknown"},
            {"rpo_pass": False},
            {"rpo_measured_sec": -1},
            {"rpo_measured_sec": 301},
            {"rpo_measured_sec": True},
        ):
            with self.subTest(changes=changes):
                report = {"postgres": {**base["postgres"], **changes}}
                self.assertFalse(_AUDIT._postgres_rpo_accepted(report))

    def test_outbox_requires_nonempty_known_zero_pending_accepted_snapshot(self) -> None:
        accepted = {"max_aggregate_seq": 7, "pending": 0, "rpo_pass": True}
        self.assertTrue(_AUDIT._outbox_evidence_accepted(accepted))
        for rejected in (
            {"max_aggregate_seq": 0, "pending": 0, "rpo_pass": True},
            {"max_aggregate_seq": 7, "pending": None, "rpo_pass": True},
            {"max_aggregate_seq": 7, "pending": False, "rpo_pass": True},
            {"max_aggregate_seq": 7, "pending": 0, "rpo_pass": False},
            {"max_aggregate_seq": True, "pending": 0, "rpo_pass": True},
        ):
            with self.subTest(rejected=rejected):
                self.assertFalse(_AUDIT._outbox_evidence_accepted(rejected))


class SourceAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = _AUDIT.build_report(_REPO)
        cls.findings = {finding["id"]: finding for finding in cls.report["findings"]}

    def test_known_supply_chain_and_chart_gaps_are_reported_open(self) -> None:
        for finding_id in (
            "CHART-CONSOLE-ABSENT",
            "SERVICE-CONFIG-CHART-WIRING",
            "MIGRATION-IMAGE-SUPPLY-CHAIN",
            "PRODUCTION-IMAGE-SENTINELS",
            "CHART-SECURITY-BOUNDARY",
            "MIGRATION-JOB-HARDENING",
        ):
            with self.subTest(finding=finding_id):
                self.assertIn(finding_id, self.findings)
                self.assertEqual(self.findings[finding_id]["status"], "OPEN")

    def test_service_wiring_evidence_names_declared_and_missing_keys(self) -> None:
        evidence = self.findings["SERVICE-CONFIG-CHART-WIRING"]["evidence"]
        self.assertTrue(any("POSTGRES_DSN" in item and "proxy-deployment.yaml" in item for item in evidence))
        self.assertTrue(any("IBEX_MCP_REDIS_URL" in item and "mcp-memory-deployment.yaml" in item for item in evidence))

    def test_recovery_residuals_are_not_promoted_to_acceptance(self) -> None:
        for finding_id in (
            "RECOVERY-POSTGRES-RPO",
            "RECOVERY-MULTISTORE-UNMEASURED",
            "RECOVERY-OUTBOX-VACUOUS",
        ):
            with self.subTest(finding=finding_id):
                self.assertIn(finding_id, self.findings)
                self.assertEqual(self.findings[finding_id]["status"], "OPEN")
        self.assertFalse(self.report["summary"]["g0_accepted"])
        self.assertFalse(self.report["summary"]["deployment_performed"])
        self.assertFalse(self.report["summary"]["production_support_claim"])

    def test_report_scope_is_explicitly_static_and_side_effect_free(self) -> None:
        self.assertIn("read-only source inspection", self.report["scope"])
        self.assertIn("not deployability results", self.report["interpretation"])
        self.assertGreater(self.report["summary"]["open_findings"], 0)

    def test_production_profile_has_expected_workloads_and_metric_residual(self) -> None:
        self.assertIn("OBSERVABILITY-METRIC-PRODUCER", self.findings)
        self.assertNotIn("CHART-WORKLOAD-COVERAGE", self.findings)
        self.assertGreaterEqual(self.report["inputs"]["chart_template_count"], 7)
        self.assertEqual(
            self.report["inputs"]["expected_application_workloads"],
            ["api", "auth", "embedder", "mcp-memory", "memory", "proxy", "worker"],
        )


if __name__ == "__main__":
    unittest.main()
