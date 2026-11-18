"""The comparison: what each surface states, and every disagreement found.

Three properties are checked against the parsed surfaces -- one vocabulary, one
status per capability, and no unaccounted row -- and each produces findings rather
than a verdict, so the report names what disagrees instead of only that something
does. Findings are strings assembled here and printed by the command line, which
keeps the message wording in one module and the exit code in another.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .contract import CAPABILITIES
from .tables import undecorate

CLASS_TOKEN = re.compile(r"`([a-z][a-z-]*)`")

# The kind of thing a finding is about: a status label or a capability. Every
# finding opens with one, so each is named once here instead of at every site
# that reports one.
LABEL_KIND = "label"
CAPABILITY_KIND = "capability"


def finding(kind: str, name: str, detail: str) -> str:
    """A finding: what it is about, which one, and what disagrees."""
    return f"{kind} {name}: {detail}"


def surfaces_without(label: str, surfaces: Mapping[str, set[str]]) -> list[str]:
    """The surfaces that do not name `label`."""
    return [name for name, names in surfaces.items() if label not in names]


def missing_from_surfaces(
    declared: Sequence[str], surfaces: Mapping[str, set[str]]
) -> list[str]:
    """One finding per declared label a surface does not name."""
    problems: list[str] = []
    for label in sorted(set(declared)):
        absent = surfaces_without(label, surfaces)
        if absent:
            problems.append(
                finding(
                    LABEL_KIND,
                    label,
                    f"declared in `Status` but missing from {', '.join(absent)}",
                )
            )
    return problems


def undeclared_labels(surfaces: Mapping[str, set[str]], declared: Sequence[str]) -> list[str]:
    """One finding per label a surface names that `Status` does not declare."""
    named = set().union(*surfaces.values())
    return [
        finding(LABEL_KIND, label, "named by the docs but not declared in `Status`")
        for label in sorted(named - set(declared))
    ]


def class_disagreements(
    declared: Sequence[str],
    site: Mapping[str, str],
    docs: Mapping[str, str],
) -> list[str]:
    """One finding per declared label whose ledger class differs between the two maps."""
    return [
        finding(
            LABEL_KIND,
            label,
            f"ledger class '{site[label]}' in `statusMeta` but "
            f"'{docs[label]}' in the docs vocabulary table",
        )
        for label in sorted(set(declared) & set(site) & set(docs))
        if site[label] != docs[label]
    ]


def compare_vocabulary(
    declared: Sequence[str],
    site: Mapping[str, str],
    docs: Mapping[str, str],
    listed: Sequence[str],
) -> list[str]:
    """One finding per label whose presence or ledger class disagrees."""
    surfaces = {
        "`statusMeta`": set(site),
        "the docs vocabulary table": set(docs),
        "the concepts list": set(listed),
    }
    return [
        *missing_from_surfaces(declared, surfaces),
        *undeclared_labels(surfaces, declared),
        *class_disagreements(declared, site, docs),
    ]


def read_status(cell: str, states_ledger_class: bool, vocabulary: Mapping[str, str]) -> str | None:
    """The declared label a status cell states, or None when it states none.

    A site surface writes the label; the engineering ledger writes a ledger class
    and its cell may name several, so the row status is the first one. Reading a
    label the vocabulary does not declare as `None` is deliberate: an unknown
    label is a finding, not a value to compare.
    """
    if not states_ledger_class:
        label = undecorate(cell)
        return label if label in vocabulary else None
    tokens = CLASS_TOKEN.findall(cell)
    if not tokens:
        return None
    return next(
        (label for label, ledger_class in vocabulary.items() if ledger_class == tokens[0]),
        None,
    )


@dataclass(frozen=True)
class Reading:
    """What is needed to turn one surface's status cell into a declared label."""

    rows_by_surface: Mapping[str, Mapping[str, str]]
    vocabulary: Mapping[str, str]
    class_surfaces: frozenset[str]

    def label(self, surface: str, cell: str) -> str | None:
        """The label the cell states, or None when it states none."""
        return read_status(cell, surface in self.class_surfaces, self.vocabulary)


def stated_by_surface(
    reading: Reading,
    capability: str,
    declared: Mapping[str, str | None],
) -> tuple[dict[str, str], list[str]]:
    """The label each surface states for `capability`, and the findings where it cannot."""
    stated: dict[str, str] = {}
    problems: list[str] = []
    for surface, name in declared.items():
        rows = reading.rows_by_surface.get(surface) if name is not None else None
        if rows is None:
            continue
        if name not in rows:
            problems.append(
                finding(
                    CAPABILITY_KIND,
                    capability,
                    f"declared in {surface} as '{name}', but that surface has no such row",
                )
            )
            continue
        label = reading.label(surface, rows[name])
        if label is None:
            problems.append(
                finding(
                    CAPABILITY_KIND,
                    capability,
                    f"{surface} states '{rows[name]}', which is not a declared status",
                )
            )
            continue
        stated[surface] = label
    return stated, problems


def compare_capabilities(
    rows_by_surface: Mapping[str, Mapping[str, str]],
    vocabulary: Mapping[str, str],
    class_surfaces: frozenset[str],
) -> list[str]:
    """One finding per capability whose status disagrees, or cannot be read."""
    reading = Reading(rows_by_surface, vocabulary, class_surfaces)
    problems: list[str] = []
    for capability, declared in CAPABILITIES.items():
        stated, stated_problems = stated_by_surface(reading, capability, declared)
        problems.extend(stated_problems)
        if len(set(stated.values())) > 1:
            problems.append(
                finding(
                    CAPABILITY_KIND,
                    capability,
                    "; ".join(f"{surface} says {label}" for surface, label in stated.items()),
                )
            )
    return problems


def compare_rows(rows_by_surface: Mapping[str, Mapping[str, str]]) -> list[str]:
    """One finding per row that no declared capability accounts for."""
    declared = {
        (surface, name)
        for names in CAPABILITIES.values()
        for surface, name in names.items()
        if name is not None
    }
    return [
        f"{surface} lists '{name}', which no declared capability accounts for"
        for surface, rows in rows_by_surface.items()
        for name in rows
        if (surface, name) not in declared
    ]
