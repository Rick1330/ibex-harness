# Post-run transform record (4.P.5 restore-drill evidence)

The committed `restore-drill-report.json` is **not** a byte-identical copy of the
raw `restore_drill_report.py` stdout from the drill run. After a successful
evidence-grade run, the following normalizations were applied before commit:

1. **`transcript` path** — absolute host path under
   `…/infra/scripts/platform/evidence/4p5-restore-drill/transcript.txt` was
   rewritten to the repo-relative path
   `infra/scripts/platform/evidence/4p5-restore-drill/transcript.txt` so the
   artifact is portable across machines.
2. **`evidence_note`** — added to record environment (podman container
   `ibex-test-pg`, database `ibex_drill`, role `ibex_rls` → `SET LOCAL ROLE
   ibex_app`), mechanism honesty (`pg_dump_fallback` / `rpo_pass: false`), and
   Kyverno deferral (#869).

`transcript.txt` remains the verbatim tee of the drill stdout (including the
absolute `transcript` path printed inside the embedded JSON at run time).

To regenerate without hand-edits, re-run the drill with
`RESTORE_DRILL_REPORT_DIR` pointing at this directory and apply the same two
transforms (or teach `restore_drill_report.py` to emit relative paths when
`EVIDENCE_RELATIVE=1` — not required for this evidence pack).
