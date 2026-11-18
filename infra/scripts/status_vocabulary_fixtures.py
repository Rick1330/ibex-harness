"""The fixture surfaces the status-vocabulary tests read, written once.

A fixture that two test modules need is written here rather than copied, and the
`baseline` helper that dedents one belongs beside its reader. The repository-level
tests do not use these: they copy the real surfaces out of this checkout.
"""

from __future__ import annotations

BASELINE = """
    | Area | Status | Must not be inferred |
    | --- | --- | --- |
    | Auth and proxy foundations | IMPLEMENTED | Hosted HA. |
    | Memory substrate | IMPLEMENTED | Deletion certification. |
"""

ENGINEERING_BASELINE = """
    | Area | Current documented status | What must not be inferred |
    | --- | --- | --- |
    | Auth/proxy foundations | `shipped-local` / profile-dependent | Hosted HA. |
"""

SITE_LEDGER = """
export type Status = 'IMPLEMENTED' | 'PROVISIONAL'

export const statusMeta: Record<Status, StatusMeta> = {
  IMPLEMENTED: {
    label: 'Implemented',
    ledgerClass: 'shipped-local',
    description: 'Implemented and locally evidenced.',
  },
  PROVISIONAL: {
    label: 'Provisional',
    ledgerClass: 'provisional',
    description: 'A seam exists; evidence is open.',
  },
}

const capabilityRows: readonly CapabilityRow[] = [
  ['Auth and proxy foundations', 'IMPLEMENTED', 'Detail.', '/docs/security/authentication'],
  ['Memory substrate', 'PROVISIONAL', 'Detail.', '/docs/memory/overview'],
]
"""

# The label-to-class map the comparison tests translate a cell through.
CLASS_BY_LABEL = {"IMPLEMENTED": "shipped-local", "PROVISIONAL": "provisional"}
