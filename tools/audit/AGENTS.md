# Read-only audits

Mirror this guide in `CLAUDE.md`; follow `../AGENTS.md` and `../../tests/AGENTS.md`.
`audit_library_internals.py` measures internal geometry without writing the library.
Reports must go outside it; preserve the shared destination guard from
`tools.migrations.adjust_fits`. Resolve resource defaults from the repository root.

Preserve the 0.25 mm contact tolerance and distinguish envelope warnings from
actual mesh intersections. Use native BVH queries and synthetic, temporary scenes.
The integration audit that can repair/publish belongs in `../migrations/`.
Checks: auditoria_internos, migracoes and biblioteca.
