"""The status-vocabulary guard, split by responsibility.

The guard is one check, but it is four jobs, and each lives in its own module so
none of them grows into the next:

``lexer``
    The TypeScript scan: comment, string, and template state, brace depth, and the
    line, trivia, and string helpers the row reader uses.
``site_vocabulary``
    The declared vocabulary in ``ledger.ts``: the ``Status`` union and
    ``statusMeta``.
``capability_rows``
    The ``capabilityRows`` array in ``ledger.ts``: which declaration is the real
    one, where the array opens and closes, and every entry between them.
``tables``
    The markdown surfaces: the pipe-table reader, the baseline table, the docs
    vocabulary table, and the concepts list.
``compare``
    Declared vocabulary against observed, the capability join, and every finding
    message.
``collect``
    Read every surface once and hand the comparison what it compares.
``cli``
    argv, the report, and the exit code.

``infra/scripts/check-status-vocabulary.py`` stays the entry point CI and
``dev-tool.sh`` invoke; it is a shim over ``cli.main``. This module re-exports the
package's public names so a caller or a test imports one place.
"""

from __future__ import annotations

from .capability_rows import parse_site_rows
from .cli import main
from .collect import collect, read
from .compare import (
    compare_capabilities,
    compare_rows,
    compare_vocabulary,
    read_status,
)
from .contract import (
    CAPABILITIES,
    DOCS_LEDGER,
    DOCS_MIRROR,
    DOCS_VOCABULARY,
    ENGINEERING_LEDGER,
    ROOT,
    SITE_LEDGER,
    SURFACE_KEYS,
    SURFACES,
    InputError,
    Surface,
)
from .site_vocabulary import parse_site_vocabulary, parse_status_union
from .tables import parse_baseline_table, parse_docs_vocabulary, parse_vocabulary_list

__all__ = [
    "CAPABILITIES",
    "DOCS_LEDGER",
    "DOCS_MIRROR",
    "DOCS_VOCABULARY",
    "ENGINEERING_LEDGER",
    "ROOT",
    "SITE_LEDGER",
    "SURFACES",
    "SURFACE_KEYS",
    "InputError",
    "Surface",
    "collect",
    "compare_capabilities",
    "compare_rows",
    "compare_vocabulary",
    "main",
    "parse_baseline_table",
    "parse_docs_vocabulary",
    "parse_site_rows",
    "parse_site_vocabulary",
    "parse_status_union",
    "parse_vocabulary_list",
    "read",
    "read_status",
]
