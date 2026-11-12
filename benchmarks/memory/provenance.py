"""The one hash/identity implementation that benchmark provenance is recorded with.

A published run can carry a ``provenance`` block, and a later checker can only trust that block
if every number in it came from one implementation. This module is that implementation: the
corpus identity, the runner identity and the working-tree state are computed here and nowhere
else. Nothing here reads or writes a published artifact; it only answers "what was measured,
on what, and can that be proven later?".

Three properties are deliberate.

**Exact bytes.** A corpus hash is ``sha256`` over a file's bytes, never over a parsed or
re-serialised form. A formatter run or a CRLF checkout then shows up as a different corpus
instead of a silently equal one.

**Fail closed.** An input that cannot be determined raises :class:`RuntimeError` rather than
being omitted or guessed, so an incomplete record is impossible: a run that cannot prove what it
measured is not a recorded run. ``is_dirty`` follows the same rule -- no usable ``git`` means
dirty, because a tree you cannot prove clean is not clean.

**Identity, not approval.** ``corpus_status`` reports whether the corpus inputs are unmodified
relative to ``HEAD``. ``"stale"`` means the bytes hashed here are not the committed corpus, so
the run is not comparable with published history; it is a flag for the reader, not a refusal.

``kind`` is ``"hnsw"`` (the synthetic pgvector corpus), ``"gold"`` (the ranking-quality v2 gold
set) or ``"gold_v1"`` (the v1 gold set the legacy ranking producer measures). Anything else is a
:class:`ValueError` -- a typo must not silently hash the wrong corpus, and ``"gold"`` keeps
meaning v2 because a published v2 record must not change meaning.
"""

from __future__ import annotations

import hashlib
import importlib.util
import os
import platform
import subprocess
from pathlib import Path
from types import ModuleType
from typing import Final

_HERE: Final = Path(__file__).resolve().parent
_REPO_ROOT: Final = _HERE.parents[1]

SYNTH_PATH: Final = _HERE / "synth.py"
CORPUS_PATH: Final = _HERE / "corpus.py"
GOLD_SET_PATH: Final = _HERE / "ranking_quality" / "gold_set_v2.json"
GOLD_V1_SET_PATH: Final = _HERE / "ranking_quality" / "gold_set_v1.json"

KINDS: Final = ("hnsw", "gold", "gold_v1")
PRODUCER: Final = "benchmarks/memory/provenance.py"
HASH_ALGO: Final = "sha256"
ENV_RUNNER_CPU: Final = "IBEX_BENCH_RUNNER_CPU"
ENV_RUNNER_RAM_MIB: Final = "IBEX_BENCH_RUNNER_RAM_MIB"

_MIB: Final = 1024 * 1024
_SUBPROCESS_TIMEOUT_S: Final = 10.0
_SYNTH_MODULE_NAME: Final = "_ibex_bench_provenance_synth"
_CPUINFO_MODEL_KEYS: Final = ("model name", "cpu model", "hardware")
_synth_cache: ModuleType | None = None


def _missing(what: str, path: Path) -> RuntimeError:
    return RuntimeError(f"provenance: missing input {what}: {path}")


def file_sha256(path: str | Path) -> str:
    """Return the hex ``sha256`` of a file's exact bytes.

    A missing or unreadable file is a :class:`RuntimeError`: identity of an absent file is not
    an empty string, it is an unknown that must stop the run.
    """
    target = Path(path)
    try:
        data = target.read_bytes()
    except OSError as exc:
        raise _missing("file", target) from exc
    return hashlib.sha256(data).hexdigest()


def _load_synth_module(path: Path) -> ModuleType:
    """Load the corpus source at ``path`` as a private module and execute it once."""
    spec = importlib.util.spec_from_file_location(_SYNTH_MODULE_NAME, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"provenance: cannot load corpus source: {path}")
    module = importlib.util.module_from_spec(spec)
    # Any failure to import the corpus source is a missing input, not a bug to surface.
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        raise RuntimeError(
            f"provenance: cannot load corpus source {path}: {exc}"
        ) from exc
    return module


def _synth() -> ModuleType:
    """Import ``synth.py`` by path so its pinned constants come from the file itself.

    Loaded by path rather than by name so this works whatever the process ``sys.path`` is, and
    the module is cached because the dimensions cannot change while the process runs.
    """
    global _synth_cache
    if _synth_cache is not None:
        return _synth_cache
    if not SYNTH_PATH.is_file():
        raise _missing("corpus source", SYNTH_PATH)
    _synth_cache = _load_synth_module(SYNTH_PATH)
    return _synth_cache


def _hnsw_identity() -> tuple[str, str]:
    """Identity of the synthetic corpus: the two source files plus the pinned dimensions."""
    synth_sha = file_sha256(SYNTH_PATH)
    corpus_sha = file_sha256(CORPUS_PATH)
    module = _synth()
    try:
        params = f"dim={int(module.DIM)},active={int(module.ACTIVE_DIMS)}"
    except (AttributeError, TypeError, ValueError) as exc:
        raise RuntimeError(
            f"provenance: {SYNTH_PATH} has no usable DIM/ACTIVE_DIMS"
        ) from exc
    manifest = f"pgvector|synth.py={synth_sha}|corpus.py={corpus_sha}|{params}"
    digest = hashlib.sha256(
        f"pgvector|{synth_sha}|{corpus_sha}|{params}".encode("ascii")
    )
    return digest.hexdigest(), manifest


def _gold_set_path(kind: str) -> Path:
    """The gold set file ``kind`` names.

    ``"gold"`` stays on ``gold_set_v2.json``: its published hash is the identity of a v2 run, so
    pointing it at the v1 file would silently relabel every recorded v2 measurement. Read from
    the module constants at call time so a test can repoint a file and see the hash move.
    """
    return GOLD_V1_SET_PATH if kind == "gold_v1" else GOLD_SET_PATH


def _gold_identity(path: Path | None = None) -> tuple[str, str]:
    """Identity of a ranking-quality corpus: the bytes of its gold set file.

    Both gold sets are byte-deterministic (the v2 generator writes sorted keys at a fixed
    indent), so hashing the bytes is the whole identity. ``path`` defaults to the v2 gold set.
    """
    target = GOLD_SET_PATH if path is None else path
    digest = file_sha256(target)
    return digest, f"{target.name}={digest}"


def _corpus_files(kind: str) -> tuple[Path, ...]:
    return (SYNTH_PATH, CORPUS_PATH) if kind == "hnsw" else (_gold_set_path(kind),)


def _checked_kind(kind: str) -> str:
    if kind not in KINDS:
        raise ValueError(
            f"provenance: unknown corpus kind {kind!r}; expected one of {KINDS}"
        )
    return kind


def corpus_identity(kind: str) -> tuple[str, str]:
    """Return ``(corpus_hash, corpus_manifest)`` for ``kind``.

    ``corpus_manifest`` is the human-readable statement of what ``corpus_hash`` covers, so a
    reader can re-derive the hash without reading this file.
    """
    checked = _checked_kind(kind)
    if checked == "hnsw":
        return _hnsw_identity()
    return _gold_identity(_gold_set_path(checked))


def _cpuinfo_entry(line: str) -> tuple[str, str]:
    """Split one ``/proc/cpuinfo`` line into ``(name, value)``; empty pair when unusable."""
    key, sep, value = line.partition(":")
    if not sep:
        return "", ""
    return key.strip().lower(), value.strip()


def _read_proc_cpuinfo() -> dict[str, str]:
    """``/proc/cpuinfo`` as first-value-per-key, or an empty mapping when unreadable."""
    try:
        text = Path("/proc/cpuinfo").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    found: dict[str, str] = {}
    for line in text.splitlines():
        name, model = _cpuinfo_entry(line)
        if model and name not in found:
            found[name] = model
    return found


def _arm_processor_model(processor: str) -> str | None:
    """``processor`` as a model name, unless it is only the core number arm64 kernels write."""
    if not processor or processor.isdigit():
        return None
    return processor


def _proc_cpu_model() -> str | None:
    """The CPU model named in ``/proc/cpuinfo``, or ``None`` off Linux."""
    found = _read_proc_cpuinfo()
    for name in _CPUINFO_MODEL_KEYS:
        if found.get(name):
            return found[name]
    # arm64 kernels label the block "processor" and may number it; a bare number is not a model.
    return _arm_processor_model(found.get("processor", ""))


def _sysctl(name: str) -> str | None:
    """Read one ``sysctl`` key (macOS). Returns ``None`` when the tool or key is absent."""
    try:
        # Fixed argv, no shell, no user input.
        result = subprocess.run(
            ["sysctl", "-n", name],
            capture_output=True,
            text=True,
            timeout=_SUBPROCESS_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = result.stdout.strip()
    return value if result.returncode == 0 and value else None


def _env_cpu_model() -> str | None:
    """The ``IBEX_BENCH_RUNNER_CPU`` override, or ``None`` when it is unset."""
    override = os.environ.get(ENV_RUNNER_CPU)
    if override is None:
        return None
    model = override.strip()
    if not model:
        raise RuntimeError(f"provenance: {ENV_RUNNER_CPU} is empty")
    return model


def _sysctl_cpu_model() -> str | None:
    """The CPU brand string ``sysctl`` reports, on the platform that has that key."""
    if platform.system() != "Darwin":
        return None
    return _sysctl("machdep.cpu.brand_string")


def _platform_cpu_model() -> str | None:
    """The model or architecture ``platform`` reports, or ``None`` when it names neither."""
    for candidate in (platform.processor(), platform.machine()):
        if candidate and candidate.strip():
            return candidate.strip()
    return None


# The fallback chain, in the order a source is trusted: kernel, macOS sysctl, then platform.
_CPU_MODEL_SOURCES: Final = (_proc_cpu_model, _sysctl_cpu_model, _platform_cpu_model)


def _runner_cpu_model() -> str:
    """Name the CPU: env override, ``/proc/cpuinfo``, ``sysctl``, then ``platform``."""
    override = _env_cpu_model()
    if override is not None:
        return override
    for source in _CPU_MODEL_SOURCES:
        model = source()
        if model:
            return model
    raise RuntimeError(
        f"provenance: cannot determine the runner CPU model; set {ENV_RUNNER_CPU}"
    )


def _runner_cpu_count() -> int:
    count = os.cpu_count()
    if count is None:
        try:
            count = len(os.sched_getaffinity(0))
        except (AttributeError, OSError):
            count = None
    if not count or count < 1:
        raise RuntimeError("provenance: cannot determine the runner CPU count")
    return int(count)


def _proc_ram_mib() -> int | None:
    try:
        text = Path("/proc/meminfo").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    for line in text.splitlines():
        key, sep, value = line.partition(":")
        if sep and key.strip() == "MemTotal":
            kib = value.split()
            if kib and kib[0].isdigit():
                return int(kib[0]) // 1024
    return None


def _sysconf_ram_mib() -> int | None:
    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
    except (AttributeError, OSError, ValueError):
        return None
    if not isinstance(pages, int) or not isinstance(page_size, int):
        return None
    if pages < 1 or page_size < 1:
        return None
    return (pages * page_size) // _MIB


def _sysctl_ram_mib() -> int | None:
    raw = _sysctl("hw.memsize")
    if raw is None or not raw.isdigit():
        return None
    mib = int(raw) // _MIB
    return mib if mib >= 1 else None


def _positive_int(raw: str, label: str) -> int:
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(
            f"provenance: {label} must be a positive integer, got {raw!r}"
        ) from exc
    if value < 1:
        raise RuntimeError(
            f"provenance: {label} must be a positive integer, got {raw!r}"
        )
    return value


def _runner_ram_mib() -> int:
    """Total RAM in MiB: env override, ``/proc/meminfo``, ``sysconf``, then ``sysctl``."""
    override = os.environ.get(ENV_RUNNER_RAM_MIB)
    if override is not None:
        return _positive_int(override.strip(), ENV_RUNNER_RAM_MIB)
    for source in (_proc_ram_mib, _sysconf_ram_mib, _sysctl_ram_mib):
        mib = source()
        if mib is not None and mib >= 1:
            return mib
    raise RuntimeError(
        f"provenance: cannot determine the runner RAM; set {ENV_RUNNER_RAM_MIB} (MiB)"
    )


def runner_identity() -> dict[str, object]:
    """Describe the machine that produced a run: CPU model, CPU count, RAM in MiB.

    Every value is required, so an unknowable one raises instead of being filled in from the
    host default or left out of the record.
    """
    return {
        "runner_cpu_model": _runner_cpu_model(),
        "runner_cpu_count": _runner_cpu_count(),
        "runner_ram_mib": _runner_ram_mib(),
    }


def _git(*args: str) -> subprocess.CompletedProcess[str] | None:
    """Run ``git`` in the repository root, or return ``None`` if it cannot run at all."""
    try:
        # Fixed argv, no shell, no user input.
        return subprocess.run(
            ["git", *args],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=_SUBPROCESS_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None


def is_dirty() -> bool:
    """Return ``True`` when tracked files differ from ``HEAD``.

    Untracked files are ignored: a raw run written under ``output/`` does not make the code that
    produced it unclear. The answer fails closed -- without a usable ``git``, or outside a
    repository, the tree is reported dirty because cleanliness cannot be proven.
    """
    result = _git("status", "--porcelain", "--untracked-files=no")
    if result is None or result.returncode != 0:
        return True
    return bool(result.stdout.strip())


def corpus_status(kind: str) -> str:
    """Report ``"current"`` or ``"stale"`` for the corpus inputs of ``kind``.

    ``"current"`` means every corpus input is committed and unmodified, so the hash recorded
    here is the hash another checkout will compute. Anything else -- a local edit, an untracked
    corpus file, no usable ``git`` -- is ``"stale"``.
    """
    paths = _corpus_files(_checked_kind(kind))
    relative: list[str] = []
    for path in paths:
        try:
            relative.append(str(path.relative_to(_REPO_ROOT)))
        except ValueError:
            return "stale"  # corpus outside the repository cannot be compared with a commit
    result = _git("status", "--porcelain", "--", *relative)
    if result is None or result.returncode != 0:
        return "stale"
    return "stale" if result.stdout.strip() else "current"


def provenance_record(kind: str) -> dict[str, object]:
    """Return the complete ``provenance`` block for a run measured on ``kind``'s corpus.

    Everything is gathered before the dict is built, so a failure half-way through raises
    instead of returning a record with a missing field. The keys match
    ``benchmarks/data-schema/*-benchmark-data.schema.json``; the gold kinds also name the gold
    set, because for those corpora the gold set *is* the corpus and a reader should not have to
    infer the filename from the hash.
    """
    checked = _checked_kind(kind)
    corpus_hash, manifest = corpus_identity(checked)
    runner = runner_identity()
    status = corpus_status(checked)
    dirty = is_dirty()
    record: dict[str, object] = {
        "status": "recorded",
        "producer": PRODUCER,
        "runner_cpu_model": runner["runner_cpu_model"],
        "runner_cpu_count": runner["runner_cpu_count"],
        "runner_ram_mib": runner["runner_ram_mib"],
        "corpus_hash": corpus_hash,
        "corpus_hash_algo": HASH_ALGO,
        "corpus_manifest": manifest,
        "corpus_status": status,
        "dirty": dirty,
    }
    if checked != "hnsw":
        record["gold_set_hash"] = corpus_hash
        record["gold_set_name"] = _gold_set_path(checked).name
    return record
