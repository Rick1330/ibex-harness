# Architecture Decision Records (moved)

ADR content has moved to the docs site source at `web/content/docs/adr/`.

- **Public site:** `/docs/adr` (when deployed) or run the docs app locally and open `/docs/adr`.
- **Contributor edits:** change MDX under `web/content/docs/adr/`, then run `pnpm exec fumadocs-mdx` in `web/`.
- **New ADRs:** copy `ADR-0001-template.md` workflow from git history (`git show 9b67c73:docs/adr/ADR-0001-template.md`) or match an existing ADR under `web/content/docs/adr/` (required YAML frontmatter: `title`, `description`, `adrId`, `status`, `date`, `authors`; required sections: Context, Decision, Consequences, References); assign the next sequential number (currently **0062** after ADR-0061).

Cross-links from roadmap decision logs point to `/docs/adr/*`.
