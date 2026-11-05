# Library tools

Mirror this guide in `CLAUDE.md`. Follow `../AGENTS.md` and the asset guide at
`../../archy_builder/assets/library/AGENTS.md` before working with library formats.

- `import_dxf_library.py`: immediate DXF-to-preset import into the configured library.
- `integrate_dxf_library.py`: resumable external staging, source hashes and publication.
- `generate_native_cabinets.py`: immediate generator for the retired native collection.
- `generate_default_photos.py`: foreground viewport capture; schedules work on import
  and closes Blender when finished. Requires explicit current GUI authorization.

The immediate importer/generators overwrite outputs without a staging workflow.
Do not import them in discovery or run them on real assets for tests.
Supply source paths explicitly: importer positional directory after `--`, or
integrator `--source DIRECTORY`. There is no implicit historical source directory.
Preserve environment/category layout, preset identities, catalog UUIDs, source
layer references and `porta_origem_promob`, which existing assets use for matching.
Resolve resources from the repository root, not this script directory.
Checks: migracoes, importacao, biblioteca, armarios; disposable data only.
