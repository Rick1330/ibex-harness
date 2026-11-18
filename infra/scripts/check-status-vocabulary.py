#!/usr/bin/env python3
"""Fail when the four places that state a capability's status disagree.

GAP-001: nothing prevented the status vocabulary drifting. Four surfaces state
it, and each is edited on its own:

1. ``engineering/architecture-v2/00-status-and-evidence.md`` -- the engineering
   ledger's "Current baseline" table. Its status column names a ledger class
   (``shipped-local``, ``provisional``, ``design-intent``, ``deferred``).
2. ``site/app/data/ledger.ts`` -- ``statusMeta`` (label to ledger class) and the
   ``capabilityRows`` the site and the Console render.
3. ``site/content/docs/02.architecture/05.status-and-evidence.md`` -- the public
   "Status vocabulary" table and the "Current baseline" table.
4. The ``site/content/docs`` mirrors -- the vocabulary list in
   ``01.getting-started/02.concepts.md`` and the baseline table in
   ``01.getting-started/01.introduction.md``.

Three properties are checked, offline and stdlib-only:

1. **One vocabulary.** ``Status`` in ``ledger.ts`` is the declared label set.
   ``statusMeta``, the public vocabulary table, and the concepts list must name
   exactly that set, and the label-to-class map must agree between
   ``ledger.ts`` and the public table. A label renamed in one file, or a class
   moved under a different label, fails naming the label.
2. **One status per capability.** Every capability a surface lists must carry
   the same status everywhere it is listed. A disagreement fails naming the
   capability and each surface's value. The engineering ledger states a class
   where the site states a label, so its cell is read as the first backticked
   class token and translated through the vocabulary before the comparison.
3. **No unaccounted row.** Every row of every surface must belong to a declared
   capability, and a declared capability must still be found where it is
   declared. A capability added, renamed, or dropped in one surface fails here
   instead of passing unscanned, which is the drift this guard exists for. A row
   or a label the reader cannot parse, or a label listed twice, is an input error
   rather than an entry to skip: skipping it would leave it out of the comparison
   while it stayed visible to a reader. The same holds for every element of
   ``capabilityRows``: one that is not one single-quoted tuple on its own line --
   a spread, a second tuple on the line, a tuple broken across lines -- is
   rejected naming its line rather than dropped from the comparison. The array
   itself is found at its module-level declaration rather than at the first mention
   of its name, it must be a direct array initializer, and only whitespace or a
   ``//`` comment may follow its closing bracket: each of those is a way the guard
   could compare one array while the site rendered another. So is a token after
   that ``]`` which continues the initializer (``[``, ``(``, ``.``, a template
   literal): a filter applied there drops a row the guard would still count.

What is *not* compared, and why:

- **The limitation columns.** "What must not be inferred" in the engineering
  ledger and "Must not be inferred" on the site are free prose, written
  separately for each audience and deliberately not identical: the site names
  what a reader must not conclude, the engineering ledger names the evidence
  that is missing. There is no shared key to compare, so a prose comparison
  would either be meaningless or force two audiences to share a sentence
  neither wants. The status columns are the mechanical contract.
- **Tables that use another vocabulary.** ``11.operations/08.console.md`` states
  Console surface availability (``Live D1``, ``Preview``, ADR-0089), not a
  capability status, and ``11.operations/06.billing-and-budgets.md`` states
  per-store notes in prose. Both would be false positives, so the surfaces are
  declared explicitly instead of discovered by "any table with a Status
  column".

Exit 1 on drift, 2 when a surface cannot be read or parsed, 0 otherwise.

Usage:
    python3 infra/scripts/check-status-vocabulary.py
    python3 infra/scripts/check-status-vocabulary.py --root .
"""

from __future__ import annotations

import sys
from pathlib import Path

# `infra/scripts` is not on `sys.path` when this file is run as a script, so the
# package beside it is resolved from this file's own directory. This is the same
# pattern the other multi-file scripts under `infra/scripts` use.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from status_vocabulary.cli import main

if __name__ == "__main__":
    raise SystemExit(main(description=__doc__))
