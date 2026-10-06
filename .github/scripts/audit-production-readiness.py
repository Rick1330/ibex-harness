#!/usr/bin/env python3
"""Report source-level production-readiness gaps without performing side effects.

This is a review/evidence aid, not a deployability validator or acceptance gate.
It reads checked-in source files only; it never renders Helm, invokes tools,
contacts services, or writes reports. Findings are expected residuals and do not
make the command fail unless the audit itself cannot run (or --check is used and
the required evidence inputs are missing).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


EXPECTED_WORKLOADS = (
    "api",
    "auth",
    "embedder",
    "mcp-memory",
    "memory",
    "proxy",
    "worker",
)

# Selected external integration keys verified in the service config modules.
# This is a review matrix, not a complete env-schema parser; requiredness and
# Secret ownership remain owner decisions.
SERVICE_WIRING_KEYS = {
    "auth": (
        ("services/auth/internal/config/env_config.go", "REDIS_URL"),
        ("services/auth/internal/config/env_config.go", "IBEX_CREDENTIALS_MASTER_KEY"),
        ("services/auth/internal/config/env_config.go", "JWT_PRIVATE_KEY_PEM"),
        ("services/auth/internal/config/env_config.go", "IBEX_AUTH_SERVICE_TOKEN"),
    ),
    "proxy": (
        ("services/proxy/internal/config/env_config.go", "POSTGRES_DSN"),
        ("services/proxy/internal/config/env_config.go", "CLICKHOUSE_DSN"),
        ("services/proxy/internal/config/env_config.go", "IBEX_CONTEXT_GRPC_TARGET"),
        ("services/proxy/internal/config/env_config.go", "IBEX_WORKER_ENQUEUE_BASE_URL"),
    ),
    "worker": (
        ("services/worker/app/config.py", "POSTGRES_DSN"),
        ("services/worker/app/config.py", "CLICKHOUSE_DSN"),
        ("services/worker/app/config.py", "S3_ENDPOINT"),
        ("services/worker/app/config.py", "S3_ACCESS_KEY"),
        ("services/worker/app/config.py", "S3_SECRET_KEY"),
        ("services/worker/app/config.py", "OPENAI_API_KEY"),
        ("services/worker/app/config.py", "MEMORY_BASE_URL"),
        ("services/worker/app/config.py", "MEMORY_API_TOKEN"),
    ),
    "memory": (
        ("services/memory/app/config.py", "IBEX_MEMORY_REDIS_URL"),
        ("services/memory/app/config.py", "IBEX_AUTH_GRPC_ADDR"),
        ("services/memory/app/config.py", "IBEX_EMBEDDING_API_TOKEN"),
    ),
    "mcp-memory": (
        ("services/mcp-memory/app/config.py", "IBEX_AUTH_GRPC_ADDR"),
        ("services/mcp-memory/app/config.py", "IBEX_MEMORY_HTTP_URL"),
        ("services/mcp-memory/app/config.py", "IBEX_MCP_REDIS_URL"),
    ),
    "embedder": (
        ("services/embedder/app/config.py", "IBEX_EMBEDDING_TEI_BASE_URL"),
        ("services/embedder/app/config.py", "IBEX_EMBEDDING_CACHE_REDIS_URL"),
    ),
}


def _read(root: Path, relative: str) -> str:
    path = root / relative
    resolved_root = root.resolve()
    resolved_path = path.resolve()
    if not resolved_path.is_relative_to(resolved_root):
        raise RuntimeError(f"audit input escapes repository root: {relative}")
    try:
        return resolved_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"required audit input unavailable: {relative}: {exc}") from exc


def _finding(finding_id: str, severity: str, summary: str, evidence: list[str]) -> dict[str, Any]:
    return {
        "id": finding_id,
        "status": "OPEN",
        "severity": severity,
        "summary": summary,
        "evidence": evidence,
    }


def _image_sentinels(values: str) -> list[str]:
    """Return YAML image-value lines using repeated-character sentinel digests."""
    matches: list[str] = []
    for number, line in enumerate(values.splitlines(), start=1):
        if line.lstrip().startswith("#") or "sha256:" not in line:
            continue
        digest = line.split("sha256:", 1)[1].split()[0].strip("'\"",)
        if len(digest) == 64 and len(set(digest)) == 1:
            matches.append(f"values-prod.yaml:{number}")
    return matches


def _resource_kinds(texts: list[tuple[str, str]]) -> set[str]:
    kinds: set[str] = set()
    for _path, text in texts:
        uncommented = "\n".join(
            line for line in text.splitlines() if not line.lstrip().startswith("#")
        )
        kinds.update(re.findall(r"(?m)^kind:\s*([A-Za-z]+)\s*$", uncommented))
    return kinds


def _valid_measurement(value: Any, target: Any) -> bool:
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and value >= 0
        and isinstance(target, int)
        and not isinstance(target, bool)
        and target >= 0
        and value <= target
    )


def _postgres_rpo_accepted(report: dict[str, Any]) -> bool:
    postgres = report.get("postgres")
    if not isinstance(postgres, dict):
        return False
    return (
        postgres.get("mechanism") == "pgbackrest_wal"
        and postgres.get("backup_ok") is True
        and postgres.get("restore_ok") is True
        and postgres.get("rpo_pass") is True
        and _valid_measurement(
            postgres.get("rpo_measured_sec"), postgres.get("rpo_target_sec")
        )
    )


def _outbox_evidence_accepted(outbox: Any) -> bool:
    if not isinstance(outbox, dict):
        return False
    sequence = outbox.get("max_aggregate_seq")
    pending = outbox.get("pending")
    return (
        isinstance(sequence, int)
        and not isinstance(sequence, bool)
        and sequence > 0
        and isinstance(pending, int)
        and not isinstance(pending, bool)
        and pending == 0
        and outbox.get("rpo_pass") is True
    )


def _workflow_builds_migration(workflow: str) -> bool:
    """Detect a Docker build-push step whose `file` is the migration Dockerfile."""
    lines = workflow.splitlines()
    for index, line in enumerate(lines):
        if not re.search(r"uses:\s*docker/build-push-action(?:@|\s|$)", line):
            continue
        block = "\n".join(lines[index + 1 : index + 15])
        if re.search(r"(?m)^\s*file:\s*infra/migrations/Dockerfile\s*$", block):
            return True
    return False


def build_report(root: Path) -> dict[str, Any]:
    """Build deterministic review findings from repository source only."""
    chart = root / "infra/helm/ibex-harness"
    template_paths = sorted(
        path for path in (chart / "templates").rglob("*")
        if path.is_file() and path.suffix in {".yaml", ".yml"}
    )
    if not template_paths:
        raise RuntimeError("required audit input unavailable: Helm templates")
    templates = [(str(path.relative_to(root)), _read(root, str(path.relative_to(root)))) for path in template_paths]
    template_names = {path.name for path in template_paths}
    workflow = _read(root, ".github/workflows/docker-publish.yml")
    prod_values = _read(root, "infra/helm/ibex-harness/values-prod.yaml")
    schema = _read(root, "infra/helm/ibex-harness/values.schema.json")
    migrate_dockerfile = _read(root, "infra/migrations/Dockerfile")
    migrate_template = _read(root, "infra/helm/ibex-harness/templates/migrate-job.yaml")
    drill_report = json.loads(
        _read(root, "infra/scripts/platform/evidence/4p5-restore-drill/restore-drill-report.json")
    )
    backup_rule = _read(root, "infra/monitoring/prometheus/rules/ibex-platform-backup.yml")

    findings: list[dict[str, Any]] = []

    missing_workloads = [
        name for name in EXPECTED_WORKLOADS
        if f"{name}-deployment.yaml" not in template_names
    ]
    if missing_workloads:
        findings.append(_finding(
            "CHART-WORKLOAD-COVERAGE", "high",
            "The chart does not render every currently inventoried application workload.",
            [f"missing template: {name}-deployment.yaml" for name in missing_workloads],
        ))
    if "console-deployment.yaml" not in template_names:
        findings.append(_finding(
            "CHART-CONSOLE-ABSENT", "high",
            "The canonical Console workload is not represented in the application chart.",
            ["infra/helm/ibex-harness/templates has no console-deployment.yaml"],
        ))

    missing_wiring: list[str] = []
    for service, contracts in SERVICE_WIRING_KEYS.items():
        template_name = f"{service}-deployment.yaml"
        template_path = chart / "templates" / template_name
        if not template_path.is_file():
            continue
        template = _read(root, str(template_path.relative_to(root)))
        for source, key in contracts:
            source_text = _read(root, source)
            if key not in source_text:
                raise RuntimeError(f"audit contract key no longer exists in source: {source}: {key}")
            if not re.search(rf"(?m)^\s*-\s*name:\s*{re.escape(key)}\s*$", template):
                missing_wiring.append(
                    f"{service}: {key} declared in {source} but absent from {template_name} env names"
                )
    if missing_wiring:
        findings.append(_finding(
            "SERVICE-CONFIG-CHART-WIRING", "high",
            "Selected external integration keys declared by services are absent from their Helm workload env lists.",
            missing_wiring,
        ))

    if not _workflow_builds_migration(workflow):
        findings.append(_finding(
            "MIGRATION-IMAGE-SUPPLY-CHAIN", "high",
            "No Docker Buildx step was found configured to build the migration Dockerfile.",
            [".github/workflows/docker-publish.yml has no build-push-action step with file: infra/migrations/Dockerfile"],
        ))

    sentinels = _image_sentinels(prod_values)
    if sentinels:
        findings.append(_finding(
            "PRODUCTION-IMAGE-SENTINELS", "high",
            "Production values intentionally retain repeated-character image digest sentinels.",
            sentinels,
        ))

    kinds = _resource_kinds(templates)
    absent_security_kinds = [kind for kind in ("NetworkPolicy", "ServiceAccount", "Role", "RoleBinding") if kind not in kinds]
    if absent_security_kinds:
        findings.append(_finding(
            "CHART-SECURITY-BOUNDARY", "high",
            "The application chart does not declare the inventoried network/identity resource kinds.",
            [f"resource kind absent from application templates: {kind}" for kind in absent_security_kinds],
        ))

    container_block = re.search(
        r"(?ms)^\s{6,}containers:\s*\n(?P<body>.*?)(?=^\s{6,}\w[\w-]*:|^\{\{[-]?\s*end)",
        migrate_template,
    )
    migrate_hardened = bool(
        container_block
        and re.search(r"(?m)^\s{10,}securityContext:\s*$", container_block.group("body"))
    )
    if not migrate_hardened:
        findings.append(_finding(
            "MIGRATION-JOB-HARDENING", "medium",
            "The migration Job has no container-level securityContext declaration.",
            ["infra/helm/ibex-harness/templates/migrate-job.yaml lacks container securityContext"],
        ))

    if not _postgres_rpo_accepted(drill_report):
        postgres = drill_report.get("postgres", {})
        if not isinstance(postgres, dict):
            postgres = {}
        findings.append(_finding(
            "RECOVERY-POSTGRES-RPO", "high",
            "Committed recovery evidence does not demonstrate PostgreSQL PITR/RPO acceptance.",
            [
                f"mechanism={postgres.get('mechanism')!r}",
                f"rpo_measured_sec={postgres.get('rpo_measured_sec')!r}",
                f"rpo_pass={postgres.get('rpo_pass')!r}",
            ],
        ))
    clickhouse = drill_report.get("clickhouse", {})
    object_store = drill_report.get("object_minio", {})
    if not isinstance(clickhouse, dict):
        clickhouse = {}
    if not isinstance(object_store, dict):
        object_store = {}
    unmeasured = []
    for store, label in ((clickhouse, "clickhouse"), (object_store, "object_minio")):
        if not _valid_measurement(store.get("rpo_measured_sec"), store.get("rpo_target_sec")):
            unmeasured.append(f"{label}.rpo_measured_sec={store.get('rpo_measured_sec')!r}")
        if not _valid_measurement(store.get("rto_measured_sec"), store.get("rto_target_sec")):
            unmeasured.append(f"{label}.rto_measured_sec={store.get('rto_measured_sec')!r}")
    if clickhouse.get("reachable") is not True:
        unmeasured.append(f"clickhouse.reachable={clickhouse.get('reachable')!r}")
    if unmeasured:
        findings.append(_finding(
            "RECOVERY-MULTISTORE-UNMEASURED", "high",
            "Committed recovery evidence lacks valid in-target ClickHouse/object-store measurements.",
            unmeasured,
        ))

    outbox = drill_report.get("outbox", {})
    if not _outbox_evidence_accepted(outbox):
        if not isinstance(outbox, dict):
            outbox = {}
        findings.append(_finding(
            "RECOVERY-OUTBOX-VACUOUS", "medium",
            "Committed outbox evidence does not prove a non-empty, zero-pending, accepted sequence snapshot.",
            [
                f"outbox.max_aggregate_seq={outbox.get('max_aggregate_seq')!r}",
                f"outbox.pending={outbox.get('pending')!r}",
                f"outbox.rpo_pass={outbox.get('rpo_pass')!r}",
            ],
        ))

    metric = "ibex_restore_drill_last_success_unixtime"
    metric_producers: list[str] = []
    for base in (root / "infra", root / "services", root / "packages"):
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix not in {".py", ".go", ".sh"}:
                continue
            if "node_modules" in path.parts or ".git" in path.parts:
                continue
            if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
                continue
            try:
                content = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                continue
            declaration = (
                re.search(rf"\b(?:Gauge|Counter|Histogram|Summary)(?:Vec)?\s*\([^\n]*['\"]{re.escape(metric)}['\"]", content)
                or re.search(rf"\b(?:NewGauge|NewCounter|NewHistogram|NewSummary)\b[\s\S]{{0,240}}?Name\s*:\s*['\"]{re.escape(metric)}['\"]", content)
                or re.search(rf"(?m)^\s*(?:printf|echo)\b[^\n]*['\"]?{re.escape(metric)}\b", content)
            )
            if declaration:
                metric_producers.append(str(path.relative_to(root)))
    if metric in backup_rule and not metric_producers:
        findings.append(_finding(
            "OBSERVABILITY-METRIC-PRODUCER", "medium",
            "A backup alert references a restore-success metric with no producer found in repository source.",
            [f"alert rule references {metric}", "repository search scope: infra/, services/, packages/"],
        ))

    return {
        "audit": "ibex-production-readiness-static-source-audit",
        "version": 1,
        "scope": "read-only source inspection; no rendering, execution, network, registry, cluster, or deployment",
        "interpretation": "OPEN findings are residuals for review, not deployability results or gate acceptance.",
        "inputs": {
            "chart_template_count": len(template_paths),
            "expected_application_workloads": list(EXPECTED_WORKLOADS),
            "migration_dockerfile_present": bool(migrate_dockerfile.strip()),
            "schema_present": bool(schema.strip()),
            "production_values_present": bool(prod_values.strip()),
        },
        "findings": findings,
        "summary": {
            "open_findings": len(findings),
            "by_severity": {
                severity: sum(item["severity"] == severity for item in findings)
                for severity in ("critical", "high", "medium", "low")
            },
            "g0_accepted": False,
            "deployment_performed": False,
            "production_support_claim": False,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail only if the audit cannot load its required source evidence (OPEN findings are expected)",
    )
    args = parser.parse_args(argv)
    try:
        report = build_report(args.root.resolve())
    except (RuntimeError, json.JSONDecodeError) as exc:
        print(f"audit error: {exc}", file=sys.stderr)
        return 2 if args.check else 1
    if args.format == "json":
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print("IBEX production-readiness static source audit")
        print(report["scope"])
        for finding in report["findings"]:
            print(f"[{finding['status']}] {finding['id']} ({finding['severity']}): {finding['summary']}")
            for evidence in finding["evidence"]:
                print(f"  - {evidence}")
        print(f"Open findings: {report['summary']['open_findings']}")
        print("G0 accepted: no; deployment performed: no; production support claim: no")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
