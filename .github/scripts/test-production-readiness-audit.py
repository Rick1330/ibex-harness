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


class WorkflowLifecycleTests(unittest.TestCase):
    def test_complete_single_image_lifecycle_is_detected(self) -> None:
        workflow = """\
jobs:
  build-api:
    steps:
      - uses: docker/build-push-action@v1
        with:
          file: services/api/Dockerfile
          push: false
  scan-image-api:
    needs: build-api
    steps:
      - run: trivy image --input /tmp/api.tar
  push-api:
    needs: [resolve-tag, scan-image-api]
    outputs:
      digest: ${{ steps.build.outputs.digest }}
    steps:
      - uses: docker/build-push-action@v1
        id: build
        with:
          file: services/api/Dockerfile
          push: true
          tags: example/api:tag
  scan-pushed-api:
    needs: [push-api]
    steps:
      - name: Scan pushed image by digest
        env:
          IMAGE_DIGEST: ${{ needs.push-api.outputs.digest }}
        run: |
          image="ghcr.io/org/api@${IMAGE_DIGEST}"
          trivy image "${image}"
  attest-provenance:
    steps:
      - name: Attest api image provenance
        uses: actions/attest-build-provenance@v1
        with:
          subject-name: ghcr.io/org/api
          subject-digest: ${{ needs.push-api.outputs.digest }}
      - name: Sign api image
        run: cosign sign --yes "${REPO}/api@${{ needs.push-api.outputs.digest }}"
"""
        lifecycle = _AUDIT._image_lifecycle(workflow)["api"]
        self.assertEqual(set(lifecycle.values()), {True})

        with_push_disabled = workflow.replace("push: true", "push: false")
        self.assertFalse(_AUDIT._image_lifecycle(with_push_disabled)["api"]["publish"])
        with_wrong_scan_dependency = workflow.replace(
            "needs: [resolve-tag, scan-image-api]",
            "needs: [resolve-tag, scan-image-worker]",
        )
        self.assertFalse(_AUDIT._image_lifecycle(with_wrong_scan_dependency)["api"]["publish"])
        with_echo_only_trivy = workflow.replace(
            "trivy image --input /tmp/api.tar",
            "echo 'trivy image --input /tmp/api.tar'",
        )
        self.assertFalse(_AUDIT._image_lifecycle(with_echo_only_trivy)["api"]["pre_push_scan"])

    def test_workflow_event_keys_are_not_misread_as_jobs_and_inline_comments_parse(self) -> None:
        workflow = """\
on:
  pull_request:
  build-api:
jobs:
  build-api: # actual job, not an event trigger
    steps: []
"""
        self.assertEqual(set(_AUDIT._workflow_jobs(workflow)), {"build-api"})

    def test_comment_and_unrelated_build_do_not_complete_migration_lifecycle(self) -> None:
        workflow = """\
jobs:
# file: infra/migrations/Dockerfile
  build-api:
    steps:
      - uses: docker/build-push-action@v1
        with:
          file: services/api/Dockerfile
  attest-provenance:
    steps: []
"""
        lifecycle = _AUDIT._image_lifecycle(workflow)["migrate"]
        self.assertFalse(any(lifecycle.values()))


class ConsolePrivilegedGateTests(unittest.TestCase):
    def test_all_literal_true_flags_are_reported_enabled(self) -> None:
        source = """\
export const PRIVILEGED_GATES = {
  cascade_preview_equals_execution: true,
  cross_store_receipts_wired: true,
  replay_sandbox_negative_tests_pass: true,
} as const
"""
        self.assertEqual(_AUDIT._client_privileged_gate_state(source), "enabled")

    def test_any_literal_false_flag_keeps_the_client_gate_disabled(self) -> None:
        source = """\
export const PRIVILEGED_GATES = {
  cascade_preview_equals_execution: true,
  cross_store_receipts_wired: false,
  replay_sandbox_negative_tests_pass: true,
} as const
"""
        self.assertEqual(_AUDIT._client_privileged_gate_state(source), "disabled")

    def test_missing_or_nonliteral_flags_are_unknown(self) -> None:
        for source in (
            "export const PRIVILEGED_GATES = {} as const",
            """\
export const PRIVILEGED_GATES = {
  cascade_preview_equals_execution: true,
  cross_store_receipts_wired: process.env.RECEIPTS === "true",
  replay_sandbox_negative_tests_pass: true,
} as const
""",
        ):
            with self.subTest(source=source):
                self.assertEqual(_AUDIT._client_privileged_gate_state(source), "unknown")

    def test_comments_do_not_turn_disabled_flags_on(self) -> None:
        source = """\
export const PRIVILEGED_GATES = {
  // Keep this true only after review.
  cascade_preview_equals_execution: false,
  cross_store_receipts_wired: true,
  replay_sandbox_negative_tests_pass: true,
} as const
"""
        self.assertEqual(_AUDIT._client_privileged_gate_state(source), "disabled")

    def test_block_comments_cannot_hide_or_override_the_real_declaration(self) -> None:
        commented_declaration = """\
/*
export const PRIVILEGED_GATES = {
  cascade_preview_equals_execution: false,
  cross_store_receipts_wired: true,
  replay_sandbox_negative_tests_pass: true,
} as const
*/
export const PRIVILEGED_GATES = {
  cascade_preview_equals_execution: true,
  cross_store_receipts_wired: true,
  replay_sandbox_negative_tests_pass: true,
} as const
"""
        comment_inside_object = """\
export const PRIVILEGED_GATES = {
  /* cascade_preview_equals_execution: false, */
  cascade_preview_equals_execution: true,
  cross_store_receipts_wired: true,
  replay_sandbox_negative_tests_pass: true,
} as const
"""
        self.assertEqual(
            _AUDIT._client_privileged_gate_state(commented_declaration), "enabled"
        )
        self.assertEqual(
            _AUDIT._client_privileged_gate_state(comment_inside_object), "enabled"
        )

    def test_string_literals_cannot_supply_a_fake_gate_declaration(self) -> None:
        source = '''\
const example = `export const PRIVILEGED_GATES = {
  cascade_preview_equals_execution: false,
  cross_store_receipts_wired: true,
  replay_sandbox_negative_tests_pass: true,
} as const`;
export const PRIVILEGED_GATES = {
  cascade_preview_equals_execution: true,
  cross_store_receipts_wired: true,
  replay_sandbox_negative_tests_pass: true,
} as const
'''
        self.assertEqual(_AUDIT._client_privileged_gate_state(source), "enabled")

    def test_inline_flags_trailing_comments_and_semicolon_parse(self) -> None:
        source = """\
export const PRIVILEGED_GATES = { cascade_preview_equals_execution: false, cross_store_receipts_wired: true, replay_sandbox_negative_tests_pass: true } as const; // closed
"""
        self.assertEqual(_AUDIT._client_privileged_gate_state(source), "disabled")


class ConsoleBooleanExportTests(unittest.TestCase):
    def test_only_one_literal_exported_boolean_is_classified(self) -> None:
        cases = (
            ("export const FLAG = true\n", "enabled"),
            ("export const FLAG = false;\n", "disabled"),
            ("export const FLAG = process.env.ENABLED === \"true\"\n", "unknown"),
            ("const sample = `export const FLAG = false`\n", "unknown"),
            ("export const FLAG = true\nexport const FLAG = false\n", "unknown"),
        )
        for source, expected in cases:
            with self.subTest(source=source):
                self.assertEqual(
                    _AUDIT._client_boolean_export_state(source, "FLAG"), expected
                )


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
            "ARTIFACT-LIFECYCLE-INCOMPLETE",
            "PRODUCTION-IMAGE-SENTINELS",
            "CHART-SECURITY-BOUNDARY",
            "MIGRATION-JOB-HARDENING",
            "CONSOLE-PRIVILEGED-ACTIONS-OPEN",
            "CONSOLE-CONTROLLED-ACTIONS-OPEN",
        ):
            with self.subTest(finding=finding_id):
                self.assertIn(finding_id, self.findings)
                self.assertEqual(self.findings[finding_id]["status"], "OPEN")

    def test_service_wiring_evidence_names_declared_and_missing_keys(self) -> None:
        evidence = self.findings["SERVICE-CONFIG-CHART-WIRING"]["evidence"]
        self.assertTrue(any("POSTGRES_DSN" in item and "proxy-deployment.yaml" in item for item in evidence))
        self.assertTrue(any("IBEX_MCP_REDIS_URL" in item and "mcp-memory-deployment.yaml" in item for item in evidence))

    def test_privileged_console_gates_are_reported_as_open_without_backend_claims(self) -> None:
        finding = self.findings["CONSOLE-PRIVILEGED-ACTIONS-OPEN"]
        self.assertEqual(finding["status"], "OPEN")
        self.assertIn("source state: enabled", finding["evidence"][0])
        self.assertTrue(any("not backend authorization" in item for item in finding["evidence"]))
        self.assertEqual(self.report["inputs"]["console_privileged_gate_state"], "enabled")

    def test_directive_control_flag_is_open_without_claiming_production_effects(self) -> None:
        finding = self.findings["CONSOLE-CONTROLLED-ACTIONS-OPEN"]
        self.assertEqual(finding["status"], "OPEN")
        self.assertIn("source state: enabled", finding["evidence"][0])
        self.assertTrue(any("local view state" in item for item in finding["evidence"]))
        self.assertEqual(self.report["inputs"]["console_controlled_actions_state"], "enabled")

    def test_lifecycle_finding_names_missing_image_stages(self) -> None:
        evidence = self.findings["ARTIFACT-LIFECYCLE-INCOMPLETE"]["evidence"]
        self.assertIn("migrate: missing build", evidence)
        self.assertIn("migrate: missing publish", evidence)
        self.assertIn("api: missing post_push_scan", evidence)
        self.assertNotIn("worker: missing post_push_scan", evidence)

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
