"""The surfaces the guard compares, and the join it compares them on.

Every path, every surface key, and every capability wording is written once here.
The rest of the package reads them and never restates them, so a surface added,
renamed, or dropped is one edit here plus the surface itself.

``InputError`` lives here too: it is the contract every parser in the package
fails with, and a caller that reads a surface has to be able to name it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

# This file sits at ``infra/scripts/status_vocabulary/contract.py``, so the fourth
# parent is the repository root. It is derived from this file rather than from the
# working directory because CI, ``make repo-guards``, and a developer's shell all
# invoke the guard from a different place.
ROOT = Path(__file__).resolve().parents[3]

ENGINEERING_LEDGER = "engineering/architecture-v2/00-status-and-evidence.md"
SITE_LEDGER = "site/app/data/ledger.ts"
DOCS_LEDGER = "site/content/docs/02.architecture/05.status-and-evidence.md"
DOCS_VOCABULARY = "site/content/docs/01.getting-started/02.concepts.md"
DOCS_MIRROR = "site/content/docs/01.getting-started/01.introduction.md"


class InputError(Exception):
    """A surface could not be read or parsed as the table it is expected to be."""


@dataclass(frozen=True)
class Surface:
    """A markdown baseline table: which file, and which two columns to read."""

    key: str
    path: str
    capability_column: str
    status_column: str
    states_ledger_class: bool = False


# The key each surface is known by. Each is written once here so both the tables
# below and the capability alias rows further down name a surface by constant: a
# misspelt surface is then a NameError at import, not a row the guard silently
# stops checking.
ENGINEERING, DOCS, LEDGER, MIRROR = "engineering", "docs", "ledger", "mirror"
SURFACE_KEYS = (ENGINEERING, DOCS, LEDGER, MIRROR)

SURFACES = (
    Surface(
        key=ENGINEERING,
        path=ENGINEERING_LEDGER,
        capability_column="Area",
        status_column="Current documented status",
        states_ledger_class=True,
    ),
    Surface(
        key=DOCS,
        path=DOCS_LEDGER,
        capability_column="Area",
        status_column="Status",
    ),
    Surface(
        key=MIRROR,
        path=DOCS_MIRROR,
        capability_column="Surface",
        status_column="Status",
    ),
)

# Which surfaces list which capability, under which name. The names are not
# identical across surfaces -- the engineering ledger writes "Auth/proxy
# foundations" where the site writes "Auth and proxy foundations" -- so the join
# is declared rather than inferred from a similarity rule that would silently
# pair the wrong rows.
#
# A capability is declared as one row per distinct wording: the wording, then
# every surface that uses it. A wording several surfaces share is written once,
# and a surface that words the capability differently keeps that difference
# visible as its own row rather than hiding it behind a shared label. A surface
# no row names does not list the capability.
#
# Adding a capability to any surface without adding it here fails check 3, which
# is the point: the guard is updated in the same change as the claim.
CAPABILITY_ALIASES: Mapping[str, tuple[tuple[str, ...], ...]] = {
    "auth-proxy": (
        ("Auth/proxy foundations", ENGINEERING),
        ("Auth and proxy foundations", DOCS, LEDGER, MIRROR),
    ),
    "management-api": (
        ("Management API", ENGINEERING, LEDGER, MIRROR),
        ("Management API · tenant routes", DOCS),
    ),
    "rate-limiting": (
        ("Rate limiting", ENGINEERING, DOCS, LEDGER),
    ),
    "provider-routing": (
        ("Provider routing, breakers, and fallback", ENGINEERING, DOCS),
        ("Provider routing and fallback", LEDGER),
    ),
    "proxy-slo": (
        ("Proxy overhead SLO and benchmark gate (GAP-004)", ENGINEERING),
        ("Proxy p99 and benchmark gate (GAP-004)", DOCS),
    ),
    "provider-packages": (
        ("Provider/tokenizer packages", ENGINEERING),
        ("Provider and tokenizer packages", DOCS),
    ),
    "memory": (
        ("Memory substrate", ENGINEERING, DOCS, LEDGER, MIRROR),
    ),
    "embedding-identity": (
        ("Embedding model identity (P1-30, P1-31)", ENGINEERING),
        ("Embedding model identity", DOCS, LEDGER),
    ),
    "context-assembly": (
        ("Context assembly", ENGINEERING, DOCS, LEDGER, MIRROR),
    ),
    "ranking-quality": (
        ("Ranking-quality benchmarks (v1 gold set, v2 mode comparison)", ENGINEERING),
        ("Ranking-quality benchmark (v1 gold set, v2 mode comparison)", DOCS),
        ("Ranking-quality benchmarks", LEDGER),
    ),
    "extraction": (
        ("Extraction workers", ENGINEERING, DOCS, LEDGER, MIRROR),
    ),
    "mcp-memory": (
        ("MCP memory tools", ENGINEERING, DOCS, LEDGER, MIRROR),
    ),
    "mcp-operator": (
        ("MCP operator gateway (GAP-009)", ENGINEERING),
        ("MCP operator gateway", DOCS, LEDGER, MIRROR),
    ),
    "budget": (
        ("Budget, usage, and cost", ENGINEERING, DOCS, LEDGER),
    ),
    "evidence-plane": (
        ("Evidence plane and relay", ENGINEERING, DOCS),
        ("Evidence plane", LEDGER),
    ),
    "console-live": (
        ("Operator Console core-tier live reads", ENGINEERING),
        ("Operator Console · live reads", DOCS, LEDGER),
        ("Operator Console", MIRROR),
    ),
    "console-preview": (
        ("Operator Console core-tier preview and platform tier", ENGINEERING),
        ("Operator Console · preview tiers", DOCS, LEDGER),
    ),
    "streaming": (
        ("Streaming hardening", ENGINEERING, DOCS, LEDGER),
    ),
    "v1-single-node": (
        ("v1-single-node deployment profile", ENGINEERING),
        ("`v1-single-node` deployment profile", DOCS),
        ("v1-single-node profile", LEDGER),
    ),
    "production-ops": (
        ("Production operations, HA, recovery, and release gates", ENGINEERING),
        ("Production operations and recovery", DOCS, LEDGER),
    ),
    "decisionservice": (
        ("DecisionService/GLiNER", ENGINEERING),
        ("DecisionService and GLiNER", DOCS, LEDGER),
        ("DecisionService, GLiNER", MIRROR),
    ),
    "graph": (
        ("Graph/A2A/marketplace/sandbox", ENGINEERING),
        ("Graph, A2A, marketplace, sandbox", DOCS, LEDGER, MIRROR),
    ),
}


def alias_map(rows: Sequence[Sequence[str]]) -> dict[str, str | None]:
    """The surface-to-name map one capability's wording rows declare.

    Every surface is a key, in `SURFACE_KEYS` order -- the order the findings
    name surfaces in -- and a surface no row names maps to `None`.
    """
    named = {surface: row[0] for row in rows for surface in row[1:]}
    return {surface: named.get(surface) for surface in SURFACE_KEYS}


# The surface-to-name map the guard joins the surfaces on, built from the
# declaration above so each wording is written once.
CAPABILITIES: Mapping[str, Mapping[str, str | None]] = {
    capability: alias_map(rows) for capability, rows in CAPABILITY_ALIASES.items()
}
