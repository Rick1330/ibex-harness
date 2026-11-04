"""The four retrieval configurations the benchmark compares.

Each mode is a named delta over the service's own settings, never a bespoke code path: that is
the only way "hybrid beats dense" can mean the pipeline users run. The delta is explicit so a
reader can see exactly what changes between two published rows, and so a new setting cannot
silently leak into every mode.

`full_graph` also turns conflict suppression on. That flag does not exist on `Settings` yet —
suppression is currently unconditional in the read path (ADR-0094) — so it lives on the mode and
is passed separately until the service gains the switch. Publishing a `full_graph` number before
that switch exists would be claiming a comparison the code cannot make, so the runner refuses to
build that mode while the service lacks the flag.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from app.config import Settings

# Where the composite relevance floor sits; kept here so a mode cannot quietly change it.
_RELEVANCE_FLOOR_KEYS: Final = ("composite_relevance_floor",)


@dataclass(frozen=True, slots=True)
class BenchmarkMode:
    """One configuration under test."""

    name: str
    description: str
    hybrid: bool
    rerank: bool
    conflict_suppression: bool
    settings_delta: MappingProxyType

    def settings_for(self, base: Settings) -> Settings:
        """Apply this mode's delta to ``base``.

        Every other field is inherited untouched: a mode is a delta, not a new configuration,
        so an unrelated setting can never diverge between two published rows.
        """
        if self.conflict_suppression and not _schema_has(base, "conflict_suppression_enabled"):
            raise UnsupportedModeError(
                f"mode {self.name!r} needs Settings.conflict_suppression_enabled, which the "
                "service does not define; refusing to build a configuration that cannot apply it"
            )
        settings = base.model_copy(update=dict(self.settings_delta))
        self._require_applied(settings)
        return settings

    def _require_applied(self, settings: Settings) -> None:
        """A mode that declares suppression must actually turn it on.

        ``model_copy`` does not validate, so a missing field would silently produce a
        `full_graph` row that is byte-identical to `hybrid_rerank` while carrying a graph label.
        """
        if not self.conflict_suppression:
            return
        if getattr(settings, "conflict_suppression_enabled", None) is True:
            return
        raise UnsupportedModeError(
            f"mode {self.name!r} declares conflict suppression but the resulting settings do not "
            "enable it; refusing to publish a row that would equal hybrid_rerank"
        )


DENSE_ONLY = BenchmarkMode(
    name="dense_only",
    description="Vector search only: the pre-Phase-5 baseline.",
    hybrid=False,
    rerank=False,
    conflict_suppression=False,
    settings_delta=MappingProxyType(
        {
            "search_hybrid_enabled": False,
            "rerank_enabled": False,
            "conflict_suppression_enabled": False,
            # Without this the page is refilled with full-text hits when vector search comes
            # up short, so the "vector only" baseline would contain lexical results.
            "search_fallback_enabled": False,
        }
    ),
)

HYBRID = BenchmarkMode(
    name="hybrid",
    description="Dense + sparse fused with RRF; no cross-encoder.",
    hybrid=True,
    rerank=False,
    conflict_suppression=False,
    settings_delta=MappingProxyType(
        {
            "search_hybrid_enabled": True,
            "rerank_enabled": False,
            "conflict_suppression_enabled": False,
        }
    ),
)

HYBRID_RERANK = BenchmarkMode(
    name="hybrid_rerank",
    description="Hybrid fused window, reranked by the cross-encoder.",
    hybrid=True,
    rerank=True,
    conflict_suppression=False,
    settings_delta=MappingProxyType(
        {
            "search_hybrid_enabled": True,
            "rerank_enabled": True,
            "conflict_suppression_enabled": False,
        }
    ),
)

FULL_GRAPH = BenchmarkMode(
    name="full_graph",
    description="Hybrid + rerank, with unresolved-conflict suppression applied.",
    hybrid=True,
    rerank=True,
    conflict_suppression=True,
    settings_delta=MappingProxyType(
        {
            "search_hybrid_enabled": True,
            "rerank_enabled": True,
            "conflict_suppression_enabled": True,
        }
    ),
)

MODES: Final = (DENSE_ONLY, HYBRID, HYBRID_RERANK, FULL_GRAPH)
MODE_BY_NAME: Final = {mode.name: mode for mode in MODES}

# The comparison the milestone is about: graph-aware must not give back what reranking bought.
GATE_REFERENCE_MODE = "hybrid_rerank"
GATE_SUBJECT_MODE = "full_graph"
# Queries whose subset is "graph" are excluded from that comparison: they are the ones the
# suppression change is supposed to move, so including them would grade the change on the
# dimension it was designed to affect.
GRAPH_SUBSET = "graph"


def _schema_has(settings: Settings, field: str) -> bool:
    """Whether ``Settings`` *declares* the field.

    ``hasattr`` is not enough: ``model_copy(update=...)`` writes into the instance dict, so an
    injected attribute would authorise a mode the service cannot run.
    """
    return field in type(settings).model_fields


class UnsupportedModeError(RuntimeError):
    """The service cannot execute this mode yet, so its number would be fiction."""


def require_supported(mode: BenchmarkMode, base: Settings) -> None:
    """Refuse a mode the service cannot actually run.

    ``full_graph`` is the only one that can fail today: it needs
    ``conflict_suppression_enabled`` on ``Settings``, and until that field exists the read path
    suppresses unconditionally, so a ``full_graph`` row would either equal ``hybrid_rerank``
    (suppression on, nothing to compare) or claim a switch that was never applied.
    """
    if not mode.conflict_suppression:
        return
    if not _schema_has(base, "conflict_suppression_enabled"):
        raise UnsupportedModeError(
            f"mode {mode.name!r} needs Settings.conflict_suppression_enabled, which the service "
            "does not define yet; suppressing the row until the switch lands"
        )
    # The field existing is not enough: applying the mode must actually enable it.
    mode.settings_for(base)


def modes_with_suppression_support(base: Settings) -> list[BenchmarkMode]:
    """The modes this checkout can run, in publication order."""
    runnable: list[BenchmarkMode] = []
    for mode in MODES:
        try:
            require_supported(mode, base)
        except UnsupportedModeError:
            continue
        runnable.append(mode)
    return runnable
