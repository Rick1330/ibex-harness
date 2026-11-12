#!/usr/bin/env python3
"""Offline, fail-closed reproducibility check for the published benchmark artifacts.

A published run is evidence only if a reader can re-derive what it measured. This checker is
the consumer of the provenance contract in ``benchmarks/memory/provenance.py``: it reads the
artifacts under ``site/public/benchmarks/`` and refuses the claims that cannot be true.

What it checks, and why each check exists:

1. **Identity.** ``sha`` is exactly 40 lowercase hex characters, ``short_sha`` is its first
   seven, no sha repeats inside one artifact, and a run that declares
   ``provenance.status == "recorded"`` names the run that produced it. A recorded run with an
   empty ``run_url`` is a claim with no source.
2. **Clean tree.** A run measured on a modified tree cannot be reproduced from its commit, so
   ``provenance.dirty == true`` fails.
3. **Corpus.** The corpus identity is recomputed from the checked-out tree and compared with a
   run's declaration when -- and only when -- that run claims ``corpus_status: "current"``. The
   comparison covers the complete identity -- ``corpus_hash``, the ``corpus_manifest`` that states
   what the hash covers, and ``gold_set_hash`` where the record carries it -- because a matching
   hash next to a different manifest is still a different corpus. ``"stale"`` is history, not a
   false claim: an older run measured other bytes, so it is checked for internal consistency only
   and retaining it does not turn the check red. A recorded run on an artifact kind with no corpus
   identity is unverifiable, so it fails.
4. **Percentiles.** A p50 above its p95, a p95 above its p99, or a p95 outside its own
   confidence interval is a broken measurement, not a slow one.
5. **Ranking.** ``gold_set`` names a known set, and on every recorded run ``gold_set_name`` must be
   the file that label names (``v1`` is ``gold_set_v1.json``, ``ranking_quality_v2`` is
   ``gold_set_v2.json``) while ``gold_set_hash`` must be the ``corpus_hash`` the same record
   states, because on this benchmark the gold set *is* the corpus. A v1 label next to a v2 name
   claims a corpus that was not measured. The bytes in this checkout are compared with those
   fields only when the run claims ``corpus_status: "current"``, so an older gold set recorded
   honestly as ``"stale"`` passes. A ``modes`` object covers only defined modes while always
   including the two the ranking milestone compares.
6. **Unrecorded runs.** A run with no provenance block, or ``status == "unrecorded"``, is
   counted and reported as a warning. It is *not* evidence, and the count is printed so that
   "28 unrecorded runs" can never be read as "28 verified runs". Enforcement is flipped
   separately; until then these runs do not fail the check.

Anything the checker cannot read -- an unreadable file, an artifact whose kind it does not
know, a missing or unusable schema -- is a failure. There is no skip flag: an unchecked
artifact is the one thing a reproducibility gate must not produce.

Exit code 0 means every checkable claim holds; 1 means at least one line on stderr says which
one does not. Warnings never change the exit code.

The script fails closed when ``jsonschema`` is missing: every artifact then reports "jsonschema
is not installed", so the check exits 1 instead of skipping the schema validation. The local
gate runs it through ``make reproducibility-check`` (and therefore ``make repo-guards``). Wiring
it into CI needs an edit under ``.github/workflows/**`` plus a ``jsonschema`` install from
``.github/requirements/jsonschema.txt``; that change is owner-gated, so it is deliberately not
made here.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any, Final

try:
    import jsonschema
except ImportError:  # CI installs it from .github/requirements/jsonschema.txt
    jsonschema = None  # type: ignore[assignment]

_SCRIPTS: Final = Path(__file__).resolve().parent
_BENCH: Final = _SCRIPTS.parent
_ROOT: Final = _BENCH.parent
_MEMORY: Final = _BENCH / "memory"


def _load_provenance() -> ModuleType:
    """Import ``benchmarks/memory/provenance.py`` by path, so identity has one implementation.

    Loaded by path rather than by name, the way ``provenance._synth`` loads the corpus source:
    the checker works whatever the process ``sys.path`` is, and it cannot be shadowed by an
    unrelated module called ``provenance``.
    """
    source = _MEMORY / "provenance.py"
    spec = importlib.util.spec_from_file_location("_ibex_bench_provenance", source)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load provenance contract: {source}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


provenance = _load_provenance()

SCRIPT_NAME: Final = "check_reproducibility"
SCHEMA_DIR: Final = _BENCH / "data-schema"
PUBLISHED_DIR: Final = _ROOT / "site" / "public" / "benchmarks"
ARTIFACT_SUFFIX: Final = "-benchmark-data.json"
SHA_RE: Final = re.compile(r"[0-9a-f]{40}")


@dataclass(frozen=True, slots=True)
class GoldCorpus:
    """The corpus a ``gold_set`` label names: its label, its file, and the kind it hashes as."""

    label: str
    name: str
    kind: str


# The two labels are different corpora, so a v1 label next to a v2 hash describes a corpus that
# was not measured. Both gold sets are byte-deterministic, so the file's hash is its identity.
GOLD_SETS: Final[dict[str, GoldCorpus]] = {
    "v1": GoldCorpus(label="v1", name="gold_set_v1.json", kind="gold_v1"),
    "ranking_quality_v2": GoldCorpus(
        label="ranking_quality_v2", name="gold_set_v2.json", kind="gold"
    ),
}
# Mirrors MODES in benchmarks/memory/ranking_quality/modes.py; a test asserts the parity.
MODE_NAMES: Final = frozenset({"dense_only", "hybrid", "hybrid_rerank", "full_graph"})
REQUIRED_MODES: Final = frozenset({"hybrid_rerank", "full_graph"})
# filename stem -> provenance corpus kind, or None when the artifact records no corpus.
CORPUS_KINDS: Final[dict[str, str | None]] = {
    "hnsw": "hnsw",
    "ranking-quality": "gold_v1",
    "extraction-quality": None,
    "write-pipeline": None,
}
_P50, _P95, _P99 = "_p50", "_p95", "_p99"
_PERCENTILES: Final = (_P50, _P95, _P99)
_CI_LOW: Final = "_p95_ci_low"
_CI_HIGH: Final = "_p95_ci_high"
# The fields a recorded run states its corpus identity with. ``gold_set_hash`` is compared when
# the record carries it; ``corpus_manifest`` is what the hash covers, so both are needed.
_IDENTITY_FIELDS: Final = ("corpus_hash", "corpus_manifest", "gold_set_hash")
# A corpus identity: ``(corpus_hash, corpus_manifest)``, as ``provenance.corpus_identity`` returns.
Identity = tuple[str, str]


class ArtifactError(ValueError):
    """An artifact the checker cannot trust: unreadable, unknown kind, or missing schema."""


@dataclass(slots=True)
class Report:
    """The outcome of one run: every problem, every warning, and the unrecorded tally."""

    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    run_count: int = 0
    unrecorded: int = 0

    @property
    def ok(self) -> bool:
        return not self.problems


def _display(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(path)


def _kind(path: Path) -> str | None:
    """Return the corpus kind for ``path``, or raise when the artifact kind is unknown."""
    if not path.name.endswith(ARTIFACT_SUFFIX):
        raise ArtifactError(f"not a published artifact name (expected *{ARTIFACT_SUFFIX})")
    stem = path.name[: -len(ARTIFACT_SUFFIX)]
    if stem not in CORPUS_KINDS:
        known = ", ".join(sorted(CORPUS_KINDS))
        raise ArtifactError(f"unknown artifact kind {stem!r}; known kinds: {known}")
    return CORPUS_KINDS[stem]


def _load(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ArtifactError(f"cannot read artifact: {exc.strerror or exc}") from exc
    try:
        payload = json.loads(text)
    except ValueError as exc:
        raise ArtifactError(f"invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ArtifactError("artifact root must be a JSON object")
    return payload


def _schema(stem: str) -> dict[str, Any]:
    path = SCHEMA_DIR / f"{stem}.schema.json"
    try:
        schema = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ArtifactError(f"missing schema {path.name}: {exc.strerror or exc}") from exc
    except ValueError as exc:
        raise ArtifactError(f"invalid schema {path.name}: {exc}") from exc
    return schema


def _path_part(part: str | int, text: str) -> str:
    if isinstance(part, int):
        return f"[{part}]"
    return f".{part}" if text else str(part)


def _path_text(path: Sequence[str | int]) -> str:
    text = ""
    for part in path:
        text += _path_part(part, text)
    return text or "<root>"


def _schema_problems(payload: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    if jsonschema is None:
        return ["jsonschema is not installed; the artifact cannot be checked against its schema"]
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(payload), key=lambda e: _path_text(e.absolute_path))
    return [f"schema: {_path_text(e.absolute_path)}: {e.message}" for e in errors]


def _runs_of(payload: dict[str, Any]) -> list[Any]:
    runs = payload.get("runs")
    return runs if isinstance(runs, list) else []


def _provenance(run: Any) -> dict[str, Any]:
    if not isinstance(run, dict):
        return {}
    value = run.get("provenance")
    return value if isinstance(value, dict) else {}


def _prov_status(run: Any) -> str | None:
    status = _provenance(run).get("status")
    return status if isinstance(status, str) else None


def _check_identity(run: dict[str, Any], label: str, index: int, seen: dict[str, int]) -> list[str]:
    problems: list[str] = []
    sha = run.get("sha")
    if isinstance(sha, str) and SHA_RE.fullmatch(sha):
        if sha in seen:
            problems.append(f"{label}.sha: duplicate {sha} (first seen at runs[{seen[sha]}])")
        else:
            seen[sha] = index
    else:
        problems.append(f"{label}.sha: {sha!r} is not 40 lowercase hex characters")
    expected = sha[:7] if isinstance(sha, str) else None
    short = run.get("short_sha")
    if expected is not None and short != expected:
        problems.append(f"{label}.short_sha: {short!r} != sha[:7] {expected!r}")
    return problems


def _check_source(run: dict[str, Any], label: str) -> list[str]:
    """A recorded run must name the run that produced it; a dirty tree fails any run."""
    problems: list[str] = []
    if _provenance(run).get("dirty") is True:
        problems.append(
            f"{label}.provenance.dirty: true; a run measured on a modified tree cannot be"
            " reproduced from its commit"
        )
    if _prov_status(run) != "recorded":
        return problems
    url = run.get("run_url")
    if not isinstance(url, str) or not url.strip():
        problems.append(
            f"{label}.run_url: empty on a run with provenance.status='recorded'; a recorded"
            " claim must name the run that produced it"
        )
    return problems


def _as_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _percentile_prefixes(node: dict[str, Any]) -> list[str]:
    prefixes = {
        key[: -len(suffix)] for key in node for suffix in _PERCENTILES if key.endswith(suffix)
    }
    complete = (p for p in prefixes if all(f"{p}{s}" in node for s in _PERCENTILES))
    return sorted(complete)


def _check_interval(label: str, prefix: str, p95: float, node: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    low = _as_number(node.get(f"{prefix}{_CI_LOW}"))
    high = _as_number(node.get(f"{prefix}{_CI_HIGH}"))
    if low is not None and low > p95:
        problems.append(f"{label}.{prefix}: p95 {p95} below ci_low {low}")
    if high is not None and p95 > high:
        problems.append(f"{label}.{prefix}: p95 {p95} above ci_high {high}")
    return problems


def _check_percentile_group(label: str, node: dict[str, Any], prefix: str) -> list[str]:
    names = [f"{prefix}{suffix}" for suffix in _PERCENTILES]
    values = [_as_number(node[name]) for name in names]
    broken = next(((n, v) for n, v in zip(names, values, strict=True) if v is None), None)
    if broken is not None:
        return [f"{label}.{broken[0]}: not a number ({node[broken[0]]!r})"]
    p50, p95, p99 = (value for value in values if value is not None)
    problems: list[str] = []
    if p50 > p95:
        problems.append(f"{label}.{prefix}: p50 {p50} > p95 {p95}")
    if p95 > p99:
        problems.append(f"{label}.{prefix}: p95 {p95} > p99 {p99}")
    return problems + _check_interval(label, prefix, p95, node)


def _flat(chunks: Iterable[Iterable[str]]) -> list[str]:
    return [item for chunk in chunks for item in chunk]


def _check_groups(label: str, node: dict[str, Any]) -> list[str]:
    prefixes = _percentile_prefixes(node)
    return _flat(_check_percentile_group(label, node, prefix) for prefix in prefixes)


def _check_children(label: str, node: Any) -> list[str]:
    if isinstance(node, dict):
        return _flat(_check_percentiles(f"{label}.{key}", node[key]) for key in sorted(node))
    if isinstance(node, list):
        return _flat(
            _check_percentiles(f"{label}[{index}]", value) for index, value in enumerate(node)
        )
    return []


def _check_percentiles(label: str, node: Any) -> list[str]:
    groups = _check_groups(label, node) if isinstance(node, dict) else []
    return groups + _check_children(label, node)


def _modes_of(run: dict[str, Any]) -> Any:
    modes = run.get("modes")
    if modes is not None:
        return modes
    summary = run.get("gate_summary")
    return summary.get("modes") if isinstance(summary, dict) else None


def _check_modes(label: str, modes: Any) -> list[str]:
    if not isinstance(modes, dict):
        return [f"{label}.modes: must be an object keyed by mode name"]
    problems: list[str] = []
    unknown = sorted(set(modes) - MODE_NAMES)
    if unknown:
        problems.append(
            f"{label}.modes: unknown mode(s) {unknown}; defined modes are {sorted(MODE_NAMES)}"
        )
    absent = sorted(REQUIRED_MODES - set(modes))
    if absent:
        problems.append(f"{label}.modes: missing required mode(s) {absent}")
    return problems


def _check_ranking(run: dict[str, Any], label: str, cache: dict[str, Identity]) -> list[str]:
    problems: list[str] = []
    gold = run.get("gold_set")
    if gold is not None and gold not in GOLD_SETS:
        problems.append(f"{label}.gold_set: {gold!r} is not one of {sorted(GOLD_SETS)}")
    problems.extend(_check_gold_set(label, run, cache))
    modes = _modes_of(run)
    if modes is not None:
        problems.extend(_check_modes(label, modes))
    return problems


def _newest_recorded(runs: list[Any]) -> tuple[int, dict[str, Any]] | None:
    """The newest recorded run. The publisher prepends, so the first recorded run is newest."""
    for index, run in enumerate(runs):
        if _prov_status(run) == "recorded" and isinstance(run, dict):
            return index, run
    return None


def _current_identity(kind: str, cache: dict[str, Identity]) -> tuple[Identity | None, list[str]]:
    """``(corpus_hash, corpus_manifest)`` of the checked-out corpus for ``kind``."""
    if kind in cache:
        return cache[kind], []
    try:
        identity = provenance.corpus_identity(kind)
    except (RuntimeError, ValueError) as exc:
        return None, [f"corpus identity for kind {kind!r} cannot be computed: {exc}"]
    cache[kind] = identity
    return identity, []


def _identity_values(identity: Identity) -> dict[str, str]:
    """What a record must declare to be the corpus ``identity``.

    ``gold_set_hash`` repeats the corpus hash on a gold corpus, so the same expectation covers
    it; on the HNSW corpus the field is absent and is not compared.
    """
    corpus_hash, manifest = identity
    return {"corpus_hash": corpus_hash, "corpus_manifest": manifest, "gold_set_hash": corpus_hash}


def _mismatched_identity(record: dict[str, Any], identity: Identity) -> list[str]:
    """The identity fields ``record`` declares that do not describe ``identity``."""
    expected = _identity_values(identity)
    return [
        field for field in _IDENTITY_FIELDS if field in record and record[field] != expected[field]
    ]


def _describe_mismatch(record: dict[str, Any], identity: Identity, fields: list[str]) -> str:
    """The mismatched fields as ``field declared != expected``, for one actionable message."""
    expected = _identity_values(identity)
    return ", ".join(f"{field} {record.get(field)!r} != {expected[field]}" for field in fields)


def _gold_corpus(gold: Any) -> GoldCorpus | None:
    """The corpus a ``gold_set`` label names, or ``None`` for an unknown one."""
    return GOLD_SETS.get(gold) if isinstance(gold, str) else None


def _gold_field_problem(
    corpus: GoldCorpus, record: dict[str, Any], field: tuple[str, Any]
) -> str:
    """One gold set field as ``declared != expected``, naming the label that implies it."""
    key, expected = field
    return (
        f"{corpus.label}.provenance.{key}: {record.get(key)!r} != {expected!r}, the value"
        f" gold_set={corpus.label!r} implies for {corpus.name}"
    )


def _gold_name_problems(label: str, record: dict[str, Any], corpus: GoldCorpus) -> list[str]:
    """``gold_set_name`` must be the file the ``gold_set`` label names.

    The label-to-file map is fixed, so this needs no checked-out bytes and holds for an older run
    too: a name that disagrees with the label is a claim about a corpus that was not measured.
    """
    declared = record.get("gold_set_name")
    if declared == corpus.name:
        return []
    return [_gold_field_problem(corpus, record, ("gold_set_name", corpus.name))]


def _gold_hash_problems(label: str, record: dict[str, Any]) -> list[str]:
    """``gold_set_hash`` must be the corpus hash the same record states.

    On this benchmark the gold set *is* the corpus, so one record cannot state two identities for
    it: a reader re-deriving either from the other must land on the same bytes. This compares the
    record with itself, never with the checkout, so an older run keeps its own hash.
    """
    declared = record.get("gold_set_hash")
    corpus_hash = record.get("corpus_hash")
    if declared == corpus_hash:
        return []
    return [
        (
            f"{label}.provenance.gold_set_hash: {declared!r} != corpus_hash {corpus_hash!r}; on a"
            " ranking run the gold set is the corpus, so the record must state one identity"
        )
    ]


def _gold_checkout_problems(
    record: dict[str, Any], corpus: GoldCorpus, identity: Identity
) -> list[str]:
    """The gold set hash, checked against the corpus bytes in this checkout."""
    expected = identity[0]
    if record.get("gold_set_hash") == expected:
        return []
    return [_gold_field_problem(corpus, record, ("gold_set_hash", expected))]


def _check_gold_set(label: str, run: dict[str, Any], cache: dict[str, Identity]) -> list[str]:
    """A recorded ranking run must name the gold set it declares, and state one identity.

    ``gold_set`` is the label; ``provenance.gold_set_name`` must be the file that label names and
    ``gold_set_hash`` must agree with the run's own ``corpus_hash``. Both are checked on every run
    and neither needs the bytes in this checkout, so an older run recorded as ``"stale"`` is not
    failed for being old. The checkout is consulted only when the run claims
    ``corpus_status: "current"``, which is the claim that says a reader will find this gold set
    here.
    """
    record = _provenance(run)
    corpus = _gold_corpus(run.get("gold_set"))
    if record.get("status") != "recorded" or corpus is None:
        return []
    problems = _gold_name_problems(label, record, corpus) + _gold_hash_problems(label, record)
    if record.get("corpus_status") != "current":
        return problems
    identity, identity_problems = _current_identity(corpus.kind, cache)
    if identity is None:
        return problems + identity_problems
    return problems + _gold_checkout_problems(record, corpus, identity)


def _identity_verdict(
    label: str, record: dict[str, Any], kind: str, identity: Identity
) -> list[str]:
    """A ``"current"`` claim must describe the checked-out corpus; ``"stale"`` is left alone.

    A matching hash next to a different manifest is still a different corpus: the manifest states
    what the hash covers, so a reader re-deriving one from the other must get what the record
    promised. The failure that matters is a run claiming ``"current"`` on an identity that is not
    the checked-out corpus, so that is the only claim compared with the bytes here.

    ``"stale"`` is not compared at all. It says the run measured bytes that are not the ones in
    this checkout, which is what an older run honestly records, and the publisher also writes it
    for a corpus edited locally -- where the hash *does* match this checkout. Failing either one
    would make retaining history, or publishing an honest flag, turn the check red.
    """
    if record.get("corpus_status") != "current":
        return []
    mismatched = _mismatched_identity(record, identity)
    if not mismatched:
        return []
    return [
        (
            f"{label}.provenance.corpus_status: 'current' but"
            f" {_describe_mismatch(record, identity, mismatched)} does not describe the"
            f" checked-out {kind} corpus ({identity[0]})"
        )
    ]


def _corpus_kind(run: dict[str, Any], kind: str | None) -> str | None:
    """The corpus ``run`` must be measured against.

    On the ranking artifact a recorded run names its own ``gold_set``, and that label -- not the
    artifact's filename -- says which corpus the number came from, so it wins when it is known.
    """
    corpus = _gold_corpus(run.get("gold_set"))
    return kind if corpus is None else corpus.kind


def _check_corpus(runs: list[Any], kind: str | None, cache: dict[str, Identity]) -> list[str]:
    newest = _newest_recorded(runs)
    if newest is None:
        return []
    index, run = newest
    label = f"runs[{index}]"
    expected_kind = _corpus_kind(run, kind)
    if expected_kind is None:
        return [
            (
                f"{label}.provenance: recorded on an artifact kind with no corpus identity, so"
                " the claim cannot be verified"
            )
        ]
    identity, problems = _current_identity(expected_kind, cache)
    if identity is None:
        return problems
    return _identity_verdict(label, _provenance(run), expected_kind, identity)


def _run_problems(runs: list[Any], cache: dict[str, Identity]) -> list[str]:
    problems: list[str] = []
    seen: dict[str, int] = {}
    for index, run in enumerate(runs):
        label = f"runs[{index}]"
        if not isinstance(run, dict):
            problems.append(f"{label}: not a JSON object")
            continue
        problems.extend(_check_identity(run, label, index, seen))
        problems.extend(_check_source(run, label))
        problems.extend(_check_percentiles(label, run))
        problems.extend(_check_ranking(run, label, cache))
    return problems


def _check_payload(payload: dict[str, Any], kind: str | None) -> list[str]:
    runs = payload.get("runs")
    if not isinstance(runs, list):
        return ["runs: missing or not an array"]
    cache: dict[str, Identity] = {}
    return _run_problems(runs, cache) + _check_corpus(runs, kind, cache)


def _inspect(path: Path) -> tuple[dict[str, Any], str | None, dict[str, Any]]:
    return _load(path), _kind(path), _schema(path.stem)


def _unrecorded_warning(display: str, unrecorded: int, total: int) -> str:
    return (
        f"{display}: {unrecorded} of {total} run(s) are unrecorded -- not reproducible"
        " evidence; provenance enforcement has not been flipped on (warning, not a failure)"
    )


def check_path(path: Path, report: Report) -> None:
    """Check one artifact, appending its problems and warnings to ``report``."""
    display = _display(path)
    try:
        payload, kind, schema = _inspect(path)
    except ArtifactError as exc:
        report.problems.append(f"{display}: {exc}")
        return
    messages = _schema_problems(payload, schema) + _check_payload(payload, kind)
    report.problems.extend(f"{display}: {message}" for message in messages)
    runs = _runs_of(payload)
    unrecorded = sum(1 for run in runs if _prov_status(run) != "recorded")
    report.run_count += len(runs)
    report.unrecorded += unrecorded
    if unrecorded:
        report.warnings.append(_unrecorded_warning(display, unrecorded, len(runs)))


def default_paths() -> list[Path]:
    return sorted(PUBLISHED_DIR.glob(f"*{ARTIFACT_SUFFIX}"))


def check_paths(paths: Sequence[Path]) -> Report:
    report = Report()
    for path in paths:
        check_path(path, report)
    return report


def _render(report: Report, artifact_count: int) -> None:
    for message in report.warnings:
        print(f"Warning: {message}", file=sys.stderr)
    for message in report.problems:
        print(f"{SCRIPT_NAME}: {message}", file=sys.stderr)
    summary = (
        f"{SCRIPT_NAME}: {artifact_count} artifact(s), {report.run_count} run(s),"
        f" {len(report.problems)} problem(s), {len(report.warnings)} warning(s),"
        f" {report.unrecorded} unrecorded run(s)"
    )
    print(summary, file=sys.stdout if report.ok else sys.stderr)


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fail when a published benchmark artifact makes a claim it cannot support."
    )
    parser.add_argument(
        "artifacts",
        nargs="*",
        type=Path,
        help="artifact paths; default is every site/public/benchmarks/*-benchmark-data.json",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    paths: list[Path] = list(args.artifacts) or default_paths()
    if not paths:
        print(f"{SCRIPT_NAME}: no artifacts found under {PUBLISHED_DIR}", file=sys.stderr)
        return 1
    report = check_paths(paths)
    _render(report, len(paths))
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
