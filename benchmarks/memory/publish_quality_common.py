"""Shared helpers for ranking-quality and write-pipeline published history."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

import provenance
from path_guard import PathResolveOptions, resolve_workspace_path

# What a published ``provenance`` block has to carry. These are the HNSW schema's ``status ==
# "recorded"`` requirements plus the status itself, kept in one place so both publishers refuse
# the same incomplete record.
REQUIRED_PROVENANCE_FIELDS: Final = (
    "status",
    "producer",
    "runner_cpu_model",
    "runner_cpu_count",
    "runner_ram_mib",
    "corpus_hash",
    "corpus_hash_algo",
    "corpus_manifest",
    "corpus_status",
    "dirty",
)
# The ranking-quality schema also requires the gold set identity: on that benchmark the gold set
# *is* the corpus, so a recorded run that does not name it cannot be re-derived.
GOLD_SET_PROVENANCE_FIELDS: Final = ("gold_set_hash", "gold_set_name")
RANKING_PROVENANCE_FIELDS: Final = REQUIRED_PROVENANCE_FIELDS + GOLD_SET_PROVENANCE_FIELDS

# The corpus a published ranking-quality run measures. The publisher restates the recorded
# ``corpus_status`` against it, and ``check_reproducibility`` derives the same kind from the run's
# ``gold_set`` label.
RANKING_CORPUS_KIND: Final = "gold_v1"

_HASH_TEXT: Final = re.compile(r"^[0-9a-f]{64}$")


def _is_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_positive_int(value: Any) -> bool:
    # bool is an int, so `true` would otherwise pass as a CPU count of one.
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _is_hash(value: Any) -> bool:
    return isinstance(value, str) and _HASH_TEXT.fullmatch(value) is not None


def _is_bool(value: Any) -> bool:
    return isinstance(value, bool)


def _is_corpus_status(value: Any) -> bool:
    return value in {"current", "stale"}


def _is_hash_algo(value: Any) -> bool:
    return value == provenance.HASH_ALGO


# Required field -> (what it must hold, how to say it). One row per field, so a refusal names the
# field and the expectation instead of only reporting that something was wrong, and a zero, a
# typo or a quoted boolean -- each of which would publish an unreproducible claim -- is refused by
# the same pass. ``status`` is not here: it has its own message in ``_require_recorded_status``.
_TEXT_EXPECTATION: Final = "a non-empty string"

_FIELD_RULES: Final[dict[str, tuple[Any, str]]] = {
    "producer": (_is_text, _TEXT_EXPECTATION),
    "runner_cpu_model": (_is_text, _TEXT_EXPECTATION),
    "runner_cpu_count": (_is_positive_int, "a positive integer"),
    "runner_ram_mib": (_is_positive_int, "a positive integer"),
    "corpus_hash": (_is_hash, "64 lowercase hex characters"),
    "corpus_hash_algo": (_is_hash_algo, repr(provenance.HASH_ALGO)),
    "corpus_manifest": (_is_text, _TEXT_EXPECTATION),
    "corpus_status": (_is_corpus_status, "'current' or 'stale'"),
    "dirty": (_is_bool, "a boolean"),
    "gold_set_hash": (_is_hash, "64 lowercase hex characters"),
    "gold_set_name": (_is_text, "a non-empty string"),
}


@dataclass(frozen=True, slots=True)
class RunMeta:
    sha: str
    branch: str
    run_number: int
    run_url: str


def gate_status(gate: dict[str, Any]) -> str:
    return "pass" if gate.get("status") == "pass" else "fail"


def _recorded_provenance_block(
    document: Mapping[str, Any], *, artifact: str, rerun: str
) -> Mapping[str, Any]:
    """The document's populated ``provenance`` mapping, or a refusal naming the fix."""
    record = document.get("provenance")
    if isinstance(record, Mapping) and record:
        return record
    raise RuntimeError(f"{artifact} has no provenance; {rerun}")


def _missing_fields(record: Mapping[str, Any], fields: tuple[str, ...]) -> list[str]:
    """The provenance fields ``record`` does not carry a value for."""
    return [field for field in fields if record.get(field) is None]


def _invalid_fields(record: Mapping[str, Any], fields: tuple[str, ...]) -> list[str]:
    """The required fields ``record`` fills with a value that cannot be true for it."""
    return [
        f"{field} must be {expectation}"
        for field, (is_valid, expectation) in _FIELD_RULES.items()
        if field in fields and not is_valid(record.get(field))
    ]


def _require_complete(
    record: Mapping[str, Any], *, artifact: str, rerun: str, fields: tuple[str, ...]
) -> None:
    """Refuse a block that is missing a required field, naming every one that is absent."""
    missing = _missing_fields(record, fields)
    if missing:
        raise RuntimeError(
            f"{artifact} provenance is incomplete (missing {', '.join(missing)}); {rerun}"
        )


def _require_valid_values(
    record: Mapping[str, Any], *, artifact: str, rerun: str, fields: tuple[str, ...]
) -> None:
    """Refuse a block whose present values do not describe a real run.

    Presence is not evidence: ``runner_cpu_count = 0``, ``corpus_hash = "bad"`` and
    ``dirty = "false"`` all fill the required fields while describing a run nobody can
    reproduce, so each is refused with the field and the expectation named.
    """
    invalid = _invalid_fields(record, fields)
    if invalid:
        raise RuntimeError(f"{artifact} provenance is invalid ({'; '.join(invalid)}); {rerun}")


def _require_recorded_status(
    record: Mapping[str, Any], *, artifact: str, rerun: str
) -> None:
    """Refuse a complete block whose status says the number cannot be reproduced."""
    status = record.get("status")
    if status != "recorded":
        raise RuntimeError(
            f"{artifact} provenance.status is {status!r}, expected 'recorded'; "
            f"a published number must be reproducible; {rerun}"
        )


def require_recorded_provenance(
    document: Mapping[str, Any],
    *,
    artifact: str,
    rerun: str,
    fields: tuple[str, ...] = REQUIRED_PROVENANCE_FIELDS,
) -> dict[str, Any]:
    """Return ``document``'s ``provenance`` block, refusing to publish without a full one.

    The schemas keep the block optional so artifacts written before it existed stay valid; that
    is a compatibility promise to old files, not permission to write a new one without it. A
    published number nobody can reproduce is not evidence, so a missing, partial or impossible
    block stops the publish and names the command that fixes it. ``fields`` is the schema's
    recorded requirements for the artifact being published.
    """
    record = _recorded_provenance_block(document, artifact=artifact, rerun=rerun)
    _require_complete(record, artifact=artifact, rerun=rerun, fields=fields)
    _require_valid_values(record, artifact=artifact, rerun=rerun, fields=fields)
    _require_recorded_status(record, artifact=artifact, rerun=rerun)
    return dict(record)


def restated_corpus_status(record: Mapping[str, Any], *, kind: str) -> str:
    """``record``'s ``corpus_status``, recomputed from the checkout doing the publishing.

    A run measured against an older corpus is a real measurement, so it is published rather than
    refused -- but it must not be published *as* the corpus this checkout has. ``"current"``
    therefore means exactly "the recorded hash is the corpus here, and that corpus is committed
    and unmodified", which is the one rule a reader can re-derive without trusting the run.
    """
    current_hash, _ = provenance.corpus_identity(kind)
    if record.get("corpus_hash") != current_hash:
        return "stale"
    return provenance.corpus_status(kind)


def _resolve_existing_json_path(path: Path) -> Path:
    return resolve_workspace_path(
        path,
        options=PathResolveOptions(must_exist=True),
    )


def _resolve_output_json_path(path: Path) -> Path:
    return resolve_workspace_path(
        path,
        options=PathResolveOptions(allow_create_parent=True),
    )


def load_json(path: Path) -> dict[str, Any]:
    resolved = _resolve_existing_json_path(path)
    return json.loads(resolved.read_text(encoding="utf-8"))


def load_or_init_published(published_path: Path, *, benchmark: str) -> dict[str, Any]:
    resolved = _resolve_output_json_path(published_path)
    if not resolved.exists():
        return {"schema_version": 1, "benchmark": benchmark, "runs": []}
    data = load_json(resolved)
    data.setdefault("schema_version", 1)
    data["benchmark"] = benchmark
    data.setdefault("runs", [])
    return data


def write_published(published_path: Path, published: dict[str, Any]) -> None:
    resolved = _resolve_output_json_path(published_path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(  # NOSONAR pythonsecurity:S2083,pythonsecurity:S8707
        json.dumps(published, indent=2) + "\n",
        encoding="utf-8",
    )


@dataclass(frozen=True, slots=True)
class MergeRunRequest:
    published_path: Path
    benchmark: str
    entry: dict[str, Any]
    sha: str
    max_runs: int = 50


def merge_run(request: MergeRunRequest) -> dict[str, Any]:
    published = load_or_init_published(
        request.published_path, benchmark=request.benchmark
    )
    runs = [r for r in published.get("runs", []) if r.get("sha") != request.sha]
    runs.insert(0, request.entry)
    published["schema_version"] = 1
    published["benchmark"] = request.benchmark
    published["runs"] = runs[: request.max_runs]
    write_published(request.published_path, published)
    return published


def run_entry_base(meta: RunMeta, *, timestamp: str | None = None) -> dict[str, Any]:
    short = meta.sha[:7] if len(meta.sha) >= 7 else meta.sha
    return {
        "sha": meta.sha,
        "short_sha": short,
        "timestamp": timestamp or datetime.now(tz=UTC).isoformat(),
        "branch": meta.branch,
        "run_number": meta.run_number,
        "run_url": meta.run_url,
    }


def merge_ranking_quality_entry(
    latest: dict[str, Any], gate: dict[str, Any], meta: RunMeta
) -> dict[str, Any]:
    """One published ranking-quality run: the scored metrics, plus what produced them.

    ``provenance`` is read from the scored artifact and required. Its ``corpus_status`` is not
    copied: it is recomputed against ``RANKING_CORPUS_KIND`` in the checkout doing the
    publishing, so a run measured on an older gold set is published as ``stale`` instead of
    claiming to be the corpus a reader will find here. ``modes`` is deliberately not copied: no
    published shape defines it, and a mode comparison is published as its own artifact rather
    than smuggled into a single-mode history.
    """
    record = require_recorded_provenance(
        latest,
        artifact="ranking-quality artifact",
        rerun="re-run the ranking-quality bench on this checkout so the run is reproducible",
        fields=RANKING_PROVENANCE_FIELDS,
    )
    restated = restated_corpus_status(record, kind=RANKING_CORPUS_KIND)
    return {
        **run_entry_base(meta, timestamp=str(latest.get("timestamp") or None)),
        "gold_set": latest.get("gold_set", "v1"),
        "query_count": latest.get("query_count", 0),
        "memory_count": latest.get("memory_count", 0),
        "metrics": dict(latest.get("metrics") or {}),
        "status": gate_status(gate),
        "gate_summary": gate,
        "provenance": {**record, "corpus_status": restated},
    }


def merge_write_pipeline_entry(
    latest: dict[str, Any], gate: dict[str, Any], meta: RunMeta
) -> dict[str, Any]:
    return {
        **run_entry_base(meta, timestamp=str(latest.get("timestamp") or None)),
        "iterations": latest.get("iterations", 0),
        "metrics": dict(latest.get("metrics") or {}),
        "status": gate_status(gate),
        "gate_summary": gate,
    }
