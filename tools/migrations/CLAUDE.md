# Staged migrations

Mirror this guide in `CLAUDE.md`; follow `../AGENTS.md` and `../../tests/AGENTS.md`.
`adjust_fits.py` owns the existing shared load, cleanup, snapshot, destination,
hash and publication helpers. Preserve this implementation while relocating it.
`../library/integrate_dxf_library.py` owns its resumable publisher.

Preparation must reject library-internal destinations, resolving junctions and
Windows case before writing. Reopen and validate staged assets; preserve names,
UIDs, materials and catalog UUIDs. Publication checks every hash before its first
write and preserves backups/rollback. Keep legacy CLI options and manifest keys.

`audit_and_repair_integration.py` prepares repairs and can publish: it is not a
read-only audit. `refine_library_joints.py` also supports audit and restore modes;
its manifests pin absolute source paths/hashes, so relocation requires new staging.
`refine_diagonal_clearance_v252.py` extends the v251 module validator on import.
Tests must preserve module identity and restore that validator after executing it.
Versioned filenames distinguish historical migration stages; do not merge them.

Checks: migracoes, correcao_internos, soldas_biblioteca, importacao, biblioteca.
All validation scenes, source fixtures and staging must be disposable.
