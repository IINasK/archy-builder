# Library resources and saved preset contracts

AGENTS.md and CLAUDE.md are exact mirrors; maximum 200 lines. Root instructions
apply. This is RESOURCE DATA, not a Python package; never add __init__.py.
This resource directory uses the current English layout. Filenames, index schemas
and catalog UUIDs remain data contracts; visible catalog names use English.
Source code lives in ../../integrations/library.py and importing.py.
Detailed historical decisions: ../../../docs/reference/library_history.md.

## One library

pasta_biblioteca() is the single source for company AND user presets, registered
once as Archy Builder. Remove old registrations before adding this one.
No separate factory/team libraries. Item-level bloqueado controls editability;
location alone does not lock an item. UI saves here unless preferences override it.
ZIP updates may overwrite bundled data: preserve custom external library paths.
The development junction links this data to the checkout; do not mutate it in tests.

## Formats

- One compressed .blend per preset; native bpy.data.libraries.write.
- PNG preview shares the basename, normally 512x512.
- indice.json is a list (indent=1, ensure_ascii=False), with nome, arquivo,
  tipo (modulo/object), n1/n2/n3; optional niveis stores the FULL unlimited path.
- Use caminho_de for the complete path; _niveis_de returns the first three.
  Read legacy categoria/subcategoria too, but do not create new legacy indices.
- Optional foto, ordem, bloqueado and caixa cache; bytes invalidates bounds.
  arquivo is identity (basename only). pasta/origem are in-memory fields;
  never persist them into the index.
- blender_assets.cats.txt: VERSION 1, UUID:catalog/path:simple_name.
  Catalog UUID lives INSIDE each .blend's asset_data. Preserve it permanently.
- _garantir_catalogos generates the entire ARVORE below one Archy Builder root.
  RAIZES_ANTIGAS renames old roots without changing UUID. Write atomically only
  when content changes; two concurrent Blender instances once changed all UUIDs.
- Move a preset with refiliar_preset, which changes the .blend catalog too.
  Updating only indice.json leaves Asset Browser stale.

## Import and geometry

The current library uses integrated DXF presets. The native cabinet generator
remains for tests; do not populate the real library without an explicit request.
Export source folder = tab, file = category; full paths may contain 4+ levels.
Use unique category/room prefixes, not just repeated base names.
DXF: one layer per piece, mm, Z up, front -Y. Color semantics: 7 wood,
253 hardware, 254 aluminum/glass, 8 handles, 28 accessory, 250-252 appliances.
Only wood becomes panels; hardware guides native rig placement, never wood.
Door hinges -> native leaves; box/basket-backed fronts -> native drawers;
aluminum frames -> sliding frame leaves. Thin backs/top rails are dependents.
Native library hinges, handles and rails replace source geometry as designed.
Remove source floor/decorative pieces by the existing import rules.

Touching parts form one cabinet via native BVH after bounds. Empty L-shaped
regions do not join cabinets. Hanging internal systems remain inside the assembly.
Curved door adoption requires explicit add-on control; Tab does not enable a
parametric solver. Preserve modeled meshes and controlled-curve resize behavior.
Use oriented actual faces for supports/hinges; never assume cabinet -Y.
Back margins are per plane, not the whole assembly box. Preserve thickness,
materials, model topology, UID, names and catalog UUID during all migrations.
Base/top fit correction is limited to the existing 3.1 mm rule; retain internal
shelves, larger intentional gaps and back channels. Backs retain minimum recess.

## Publication and tests

Maintenance scripts now live in ../../../tools (see ../../../tools/AGENTS.md).
Prepare outside the library, validate .blend and preview by reopening, store
originals/backups and hashes, then publish ONLY with the explicit apply flag.
Rollback restores the exact originals. Verify hashes before the first write.
Do not run a migration on real data as a test or rewrite binary assets for naming.
Changing a preset does not update copies already inserted in a scene.

Photos are generated after saving in a disposable copy. Close ALL door types
without changing their opening side. Apply preview only after scene pieces are
removed: reloading while names remain generated .001 assets. Preview generation
is asynchronous; aplicar_preview_png is the validated write path.
Never regenerate or rename the complete catalog to reorganize source files.

Run library/import/migration suites with temporary fixtures. Blender 5.x presets
cannot be read by 4.2: explicit version skip, not a code-test skip. GUI requires
the user releasing the PC NOW. Preserve all expectedFailure cases until fixed.
