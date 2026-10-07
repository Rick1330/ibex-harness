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


def _without_yaml_comments(text: str) -> str:
    """Strip YAML comments while preserving quoted `#` characters and lines."""
    output: list[str] = []
    for line in text.splitlines():
        quote: str | None = None
        escaped = False
        end = len(line)
        for index, char in enumerate(line):
            if escaped:
                escaped = False
                continue
            if char == "\\" and quote == '"':
                escaped = True
                continue
            if quote:
                if char == quote:
                    quote = None
                continue
            if char in {"'", '"'}:
                quote = char
            elif char == "#" and (index == 0 or line[index - 1].isspace()):
                end = index
                break
        output.append(line[:end])
    return "\n".join(output)


def _workflow_jobs(workflow: str) -> dict[str, str]:
    """Split jobs under the `jobs` mapping; event triggers are never job blocks."""
    clean = _without_yaml_comments(workflow)
    lines = clean.splitlines(keepends=True)
    jobs_index = next(
        (i for i, line in enumerate(lines) if re.match(r"^jobs:\s*$", line.rstrip("\n"))),
        None,
    )
    if jobs_index is None:
        return {}
    jobs_indent = len(lines[jobs_index]) - len(lines[jobs_index].lstrip(" "))
    section_end = len(lines)
    for i in range(jobs_index + 1, len(lines)):
        line = lines[i]
        if line.strip() and not line.lstrip().startswith("#"):
            indent = len(line) - len(line.lstrip(" "))
            if indent <= jobs_indent:
                section_end = i
                break
    candidates = [
        (i, line) for i, line in enumerate(lines[jobs_index + 1 : section_end], jobs_index + 1)
        if line.strip()
    ]
    if not candidates:
        return {}
    child_indent = min(len(line) - len(line.lstrip(" ")) for _, line in candidates)
    matches = [
        (i, re.match(rf"^ {{{child_indent}}}([A-Za-z0-9_-]+):\s*$", lines[i].rstrip("\n")))
        for i, _line in candidates
    ]
    headers = [(i, match) for i, match in matches if match]
    jobs: dict[str, str] = {}
    for index, (start, match) in enumerate(headers):
        end = headers[index + 1][0] if index + 1 < len(headers) else section_end
        jobs[match.group(1)] = "".join(lines[start + 1 : end])
    return jobs


def _job_needs(job: str, dependency: str) -> bool:
    clean = _without_yaml_comments(job)
    match = re.search(r"(?m)^\s*needs:\s*(.*?)\s*$", clean)
    if not match:
        return False
    value = match.group(1).strip()
    if value.startswith("[") and value.endswith("]"):
        dependencies = {item.strip().strip("'\"") for item in value[1:-1].split(",")}
        return dependency in dependencies
    if value:
        return value.strip("'\"") == dependency
    return bool(re.search(rf"(?m)^\s*-\s*{re.escape(dependency)}\s*$", clean))


def _steps(job: str) -> list[str]:
    clean = _without_yaml_comments(job)
    marker = re.compile(r"(?m)^(?P<indent> +)-\s+(?:name|uses|run):")
    matches = list(marker.finditer(clean))
    if not matches:
        return []
    step_indent = min(len(match.group("indent")) for match in matches)
    matches = [match for match in matches if len(match.group("indent")) == step_indent]
    return [
        clean[match.start() : matches[i + 1].start() if i + 1 < len(matches) else len(clean)]
        for i, match in enumerate(matches)
    ]


def _action_step(job: str, action: str, context: str) -> str:
    for step in _steps(job):
        if re.search(rf"(?m)^\s*(?:-\s*)?uses:\s*{re.escape(action)}@", step) and re.search(
            rf"(?m)^\s*file:\s*['\"]?{re.escape(context)}/Dockerfile['\"]?\s*$", step
        ):
            return step
    return ""


def _runs_trivy_image(step: str) -> bool:
    clean = _without_yaml_comments(step)
    return re.search(r"(?m)^\s*(?:-\s*run:\s*|run:\s*|)?trivy\s+image\b", clean) is not None


def _image_lifecycle(workflow: str) -> dict[str, dict[str, bool]]:
    """Inspect job/step-bounded source wiring; never claim workflow execution proof."""
    jobs = _workflow_jobs(workflow)
    artifacts = {name: f"services/{name}" for name in EXPECTED_WORKLOADS}
    artifacts["migrate"] = "infra/migrations"
    lifecycle: dict[str, dict[str, bool]] = {}
    attest = jobs.get("attest-provenance", "")
    attest_steps = _steps(attest)
    for name, context in artifacts.items():
        slug = name
        build_job = f"build-{slug}"
        scan_job = f"scan-image-{slug}"
        push_job = f"push-{slug}"
        postscan_job = f"scan-pushed-{slug}"
        build = jobs.get(build_job, "")
        scan = jobs.get(f"scan-image-{slug}", "")
        push = jobs.get(f"push-{slug}", "")
        pushed_scan = jobs.get(f"scan-pushed-{slug}", "")
        digest_expression = rf"\$\{{\{{\s*needs\.{re.escape(push_job)}\.outputs\.digest\s*\}}\}}"
        build_action = _action_step(build, "docker/build-push-action", context)
        push_action = _action_step(push, "docker/build-push-action", context)
        pre_scan_ok = (
            _job_needs(scan, build_job)
            and any(
                _runs_trivy_image(step)
                and re.search(rf"--input\s+[^\s\"']*{re.escape(slug)}\.tar\b", step)
                for step in _steps(scan)
            )
        )
        push_ok = (
            bool(push_action)
            and _job_needs(push, scan_job)
            and re.search(r"(?m)^\s*id:\s*build\s*$", push_action) is not None
            and re.search(r"(?m)^\s*push:\s*true\s*$", push_action) is not None
            and re.search(r"(?m)^\s*tags:\s*\S+", push_action) is not None
            and re.search(r"(?m)^\s*digest:\s*\$\{\{\s*steps\.build\.outputs\.digest\s*\}\}\s*$", push) is not None
        )
        postscan_ok = (
            _job_needs(pushed_scan, push_job)
            and any(
                _runs_trivy_image(step)
                and any(
                    re.search(
                        rf"(?m)^\s*image=['\"]?[^\n]*/{re.escape(slug)}@\$\{{{re.escape(variable)}\}}['\"]?\s*$",
                        step,
                    )
                    for variable in re.findall(
                        rf"(?m)^\s*([A-Z0-9_]*DIGEST):\s*{digest_expression}\s*$", step
                    )
                )
                for step in _steps(pushed_scan)
            )
        )
        provenance_ok = any(
            "actions/attest-build-provenance@" in step
            and re.search(rf"(?m)^\s*subject-name:.*?/{re.escape(name)}\s*$", step)
            and re.search(rf"(?m)^\s*subject-digest:\s*{digest_expression}\s*$", step)
            for step in attest_steps
        )
        signature_ok = any(
            re.search(
                rf"(?m)^\s*(?:run:\s*)?cosign sign[^\n]*\$\{{REPO\}}/{re.escape(name)}@{digest_expression}\s*['\"]?\s*$",
                step,
            )
            for step in attest_steps
        )
        lifecycle[name] = {
            "build": bool(build_action and re.search(r"(?m)^\s*push:\s*false\s*$", build_action)),
            "pre_push_scan": pre_scan_ok,
            "publish": push_ok,
            "post_push_scan": postscan_ok,
            "provenance": provenance_ok,
            "signature": signature_ok,
        }
    return lifecycle


PRIVILEGED_GATE_KEYS = (
    "cascade_preview_equals_execution",
    "cross_store_receipts_wired",
    "replay_sandbox_negative_tests_pass",
)


def _mask_ts_comments_and_strings(source: str) -> str:
    """Mask comments and literals so source-pattern checks only inspect code."""
    output = list(source)
    state = "code"
    quote = ""
    index = 0

    def mask(position: int) -> None:
        if output[position] != "\n":
            output[position] = " "

    while index < len(source):
        char = source[index]
        following = source[index + 1] if index + 1 < len(source) else ""
        if state == "code":
            if char == "/" and following == "/":
                mask(index)
                mask(index + 1)
                state = "line_comment"
                index += 2
                continue
            if char == "/" and following == "*":
                mask(index)
                mask(index + 1)
                state = "block_comment"
                index += 2
                continue
            if char in {"'", '"', "`"}:
                quote = char
                state = "string"
                mask(index)
        elif state == "line_comment":
            if char == "\n":
                state = "code"
            else:
                mask(index)
        elif state == "block_comment":
            if char == "*" and following == "/":
                mask(index)
                mask(index + 1)
                state = "code"
                index += 2
                continue
            mask(index)
        else:
            if char == "\\":
                mask(index)
                if following:
                    mask(index + 1)
                    index += 2
                    continue
            elif char == quote:
                state = "code"
                quote = ""
            mask(index)
        index += 1
    return "".join(output)


def _client_privileged_gate_state(source: str) -> str:
    """Return enabled/disabled/unknown from literal client gate flags only."""
    uncommented = _mask_ts_comments_and_strings(source)
    declarations = list(re.finditer(
        r"\bexport\s+const\s+PRIVILEGED_GATES\s*=\s*\{(?P<body>[^{}]*)\}\s*as\s+const\s*;?",
        uncommented,
        re.DOTALL,
    ))
    if len(declarations) != 1:
        return "unknown"

    properties = re.findall(
        r"\b([a-z_]+)\s*:\s*(true|false)(?=\s*(?:[,}]|$))",
        declarations[0].group("body"),
    )
    values: dict[str, list[str]] = {}
    for key, value in properties:
        values.setdefault(key, []).append(value)
    if any(len(values.get(key, [])) != 1 for key in PRIVILEGED_GATE_KEYS):
        return "unknown"

    return (
        "enabled"
        if all(values[key][0] == "true" for key in PRIVILEGED_GATE_KEYS)
        else "disabled"
    )


def _client_boolean_export_state(source: str, export_name: str) -> str:
    """Read one literal exported client flag; uncertain syntax remains unknown."""
    uncommented = _mask_ts_comments_and_strings(source)
    declarations = re.findall(
        rf"(?m)^[ \t]*export[ \t]+const[ \t]+{re.escape(export_name)}[ \t]*=[ \t]*(true|false)[ \t]*;?[ \t]*$",
        uncommented,
    )
    if len(declarations) != 1:
        return "unknown"
    return "enabled" if declarations[0] == "true" else "disabled"


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
    artifact_lifecycle = _image_lifecycle(workflow)
    prod_values = _read(root, "infra/helm/ibex-harness/values-prod.yaml")
    schema = _read(root, "infra/helm/ibex-harness/values.schema.json")
    migrate_dockerfile = _read(root, "infra/migrations/Dockerfile")
    migrate_template = _read(root, "infra/helm/ibex-harness/templates/migrate-job.yaml")
    drill_report = json.loads(
        _read(root, "infra/scripts/platform/evidence/4p5-restore-drill/restore-drill-report.json")
    )
    backup_rule = _read(root, "infra/monitoring/prometheus/rules/ibex-platform-backup.yml")
    console_gates = _read(root, "services/console/src/lib/sessions/types.ts")
    directive_controls = _read(root, "services/console/src/lib/directives/types.ts")
    incident_controls = _read(root, "services/console/src/lib/incidents/types.ts")

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

    console_gate_state = _client_privileged_gate_state(console_gates)
    if console_gate_state != "disabled":
        findings.append(_finding(
            "CONSOLE-PRIVILEGED-ACTIONS-OPEN", "medium",
            "Console session export/delete/replay controls are not proven disabled by their client-side readiness gates.",
            [
                f"PRIVILEGED_GATES source state: {console_gate_state}",
                "services/console/src/lib/sessions/types.ts describes these as design fixtures gated until safety gates close",
                "services/console/src/components/sessions/privileged-gate.tsx enables its button when privilegedActionsEnabled() is true",
                "A client-side gate is not backend authorization or evidence that an external effect occurred",
            ],
        ))

    controlled_actions_state = _client_boolean_export_state(
        directive_controls, "CONTROLLED_ACTIONS_ENABLED"
    )
    if controlled_actions_state != "disabled":
        findings.append(_finding(
            "CONSOLE-CONTROLLED-ACTIONS-OPEN", "medium",
            "Directive and experiment controls are not proven disabled by their client-side fail-closed flag.",
            [
                f"CONTROLLED_ACTIONS_ENABLED source state: {controlled_actions_state}",
                "services/console/src/lib/directives/types.ts says setting the flag false makes preview/approval fail closed",
                "PromotionConsole and ExperimentPanel gate their controls on this client-side constant",
                "Inspected components update local view state; this does not establish backend authorization or production effects",
            ],
        ))

    incident_writes_state = _client_boolean_export_state(
        incident_controls, "INCIDENT_WRITES_ENABLED"
    )
    if incident_writes_state != "disabled":
        findings.append(_finding(
            "CONSOLE-INCIDENT-WRITES-OPEN", "medium",
            "Incident triage mutations are not proven disabled by their client-side read-only rollback flag.",
            [
                f"INCIDENT_WRITES_ENABLED source state: {incident_writes_state}",
                "services/console/src/lib/incidents/types.ts says setting the flag false restores read-only triage",
                "IncidentDetailView gates status, ownership, severity, and comment controls on this client-side constant",
                "Inspected component updates local React state; this does not establish backend authorization or production writes",
            ],
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

    incomplete_lifecycle = [
        f"{image}: missing {stage}"
        for image, stages in artifact_lifecycle.items()
        for stage, present in stages.items()
        if not present
    ]
    if incomplete_lifecycle:
        findings.append(_finding(
            "ARTIFACT-LIFECYCLE-INCOMPLETE", "high",
            "The workflow source does not wire every image through build, pre-push scan, publish, post-push scan, provenance, and signature stages.",
            incomplete_lifecycle,
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
        "scope": "read-only source inspection; workflow triggers/conditions/reachability and actual execution are not verified; no rendering, network, registry, cluster, or deployment",
        "interpretation": "OPEN findings are residuals for review, not deployability results or gate acceptance; source patterns are not execution evidence and do not constitute policy acceptance.",
        "inputs": {
            "chart_template_count": len(template_paths),
            "expected_application_workloads": list(EXPECTED_WORKLOADS),
            "migration_dockerfile_present": bool(migrate_dockerfile.strip()),
            "image_lifecycle_source_matrix": artifact_lifecycle,
            "schema_present": bool(schema.strip()),
            "production_values_present": bool(prod_values.strip()),
            "console_privileged_gate_state": console_gate_state,
            "console_controlled_actions_state": controlled_actions_state,
            "console_incident_writes_state": incident_writes_state,
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
