> Historical technical notes. Current instructions: [architecture](../../ARCHITECTURE.md) and local sector guides. Source paths below remain where historically relevant.

# Integration - cross-sector reference

Read explicitly for integration work. This archived guide does not automatically
apply to source files in other directories; historical AGENTS/CLAUDE mirroring
and 120-line rules described its former role. Paths below are repository-relative.
Scope: `archy_builder/integrations/native_conversion.py`, `importacao.py`,
`paredes.py`, `biblioteca.py` and historical import/integrate/adjust/audit/refine
scripts. Resource `biblioteca/` is not a Python package. Its former owner used
`__file__` for photos; preserve resource resolution, imports and reload.
Read the [asset guide](../../archy_builder/assets/library/CLAUDE.md) for formats/index/
catalogs/history, [front geometry](../../FRONT_GEOMETRY.md) for fronts, and
[design](../../DESIGN.md)/[interface](interface.md) for visible changes.

## Historical task routing

Suite means `tests/test_<suite>_blender.py`; standalone scripts are not suites.

| Task | Entry | Suite |
|---|---|---|
| DXF/categories | importacao.py: `ler_dxf_promob`, `destino_categoria_promob`, `importar_dxf_promob` | importacao |
| Standalone doors/assets | importacao.py: `importar_portas_avulsas`, `importar_promob_para_biblioteca` | importacao, biblioteca |
| Native systems | promob.py: `planejar`, `aplicar`, `marcar_dependentes` | importacao |
| Fits/backs | promob.py: `ajustar_encaixes`, `reencaixar_verticais`, `ajustar_recuo_fundos` | importacao |
| Save/insert/photo | biblioteca.py: `salvar_na_biblioteca`, `inserir_preset`, `gravar_modulo_na_biblioteca`, `preparar_abertura_foto` | biblioteca |
| Wall face/guides | paredes.py: `associar`, `manter_nas_paredes`, `aplicar_guia` | paredes |
| Batch/publication | tools/library/integrate_dxf_library.py: `preparar`, `publicar`; tools/migrations/adjust_fits.py: `validar_destino`, `publicar` | migracoes |
| Audited variant removal/rollback | tools/migrations/consolidate_library_variants.py: `preparar`, `publicar` | migracoes, biblioteca |
| Preset internal repair | tools/migrations/repair_library_internals.py: `preparar`, `publicar` | correcao_internos, migracoes, biblioteca |
| Read-only internal gap/collision audit | tools/audit/audit_library_internals.py: `auditar`, `auditar_modulo` | auditoria_internos, biblioteca |
| Unique joints/minimum gap | tools/migrations/refine_library_joints.py: `preparar`, `publicar` | solda, soldas_biblioteca, migracoes |
| Audit/repair | tools/migrations/audit_and_repair_integration.py: `capturar`, `verificar_funcoes`, `preparar`; tools/migrations/adjust_doors.py: `preparar` | importacao, migracoes |

## Presets and publication

- Editor 365: drag originates in its NODE_EDITOR, retaining global coordinates and VIEW_3D target. Other commands use `editor.executar`; never change preset modal origin.
- Import 364: append's `novos` may contain removed RNA after resize. Refresh from the native hierarchy in finally, including rebuilt components. Ignoring ReferenceError is insufficient for selection/Local View/rollback.
- One library (`biblioteca.pasta_biblioteca`), including user models. Remove old registrations before adding it; asset guide owns UUIDs, embedded catalogs, legacy indices and locks.
- Drag 363: reduce width/height only up to Maximum Adjustment (10 mm, zero disables), preserving E/depth. Numeric preview; domain resize only on confirm, never edit the preset. Red preview/reason on refusal; cache belongs only to modal.
- Preset click starts placement; Save generates PNG. External objects become panels by shape. Real left opening requires every mounting plate to fit its support; coplanar chains reverse without moving closed leaves; unsupported corners retain articulation.
- Photos only after saving, in a disposable copy, with ALL doors closed including corner/sliding/zigzag. Never change hinge side for a photo. Legible crease outlines, no triangulation; restore helpers/colors.
- `tools/library/integrate_dxf_library.py`: resumable external preparation, hashes/backups/rollback. Validate and reopen blend/photo/preview and keep originals before `--apply`; verify hashes before first write. Resolve real paths including Windows junction/case; validate manifest names. Keep filenames, UIDs, materials/catalog UUIDs. Asset updates do not update already inserted instances.
- The same preparation/backup/publication contract applies to `tools/migrations/adjust_fits.py`, `adjust_doors.py`, `adjust_hinges.py`, `adjust_backs_and_doors.py`, `refine_corners.py`, `refresh_library_photos.py` and `adjust_left_opening.py`.

## DXF contracts

- Native integration, not a passive copy: `tools/library/import_dxf_library.py` -> importacao -> promob. Folder = tab; file = category. Bedroom branches retain Armarios/Bancadas/Escritorios/Superiores and unique room prefixes. Standalone doors become door groups (modeled wood or measured frame/panel), without an invented carcass.
- Native BVH contact after broad-phase bounds; empty L-shaped space never joins cabinets. Fully contained suspended internals follow the body. Systems remain INSIDE the asset assembly, including old unmarked assemblies; audit integration.
- Layer colors: 7 wood panel; 253/254/8 hardware/aluminum/handle never become wood. Native rails/hinges replace imported ones. Aluminum frame becomes a sliding frame leaf; thin backs/top stretchers become dependents.
- Color-7 strips/trim accept aspect ratio 1 and 0.05 mm tolerance; preserve 40/15 supports and 49.9998 mm pieces. Fixed panels never articulate leaves; maintain 2 mm from trim AND support face. Bottom-hinged fronts remain panels.
- Hinge plate/arm gives one face/side/height reference per leaf; never assume -Y front. L/diagonal uses actual plane (`porta_vao_orientado`); unsupported joints use existing outer side. Manual margin/count replaces references. Thin backs cannot support hinges.
- Curved fronts with plates become native leaves with original mesh: Z is sagitta, never flatten. Handle follows tangent; R deforms closed geometry and reanchors. Explicit add-on control also on adoption; native Tab and contour measurement do not activate parametric solving.
- Diagonal profile derives from largest horizontal panel, never stretcher. Both skins' ends clear actual body by 2 mm using native assembly queries. Wood determines outward normal; box-center inference reverses curves. Chosen side must have support.
- Shared frentes.py reference uses semantic INT FACE/EDGE, numeric Mesh cache and per-Mesh/undo invalidation outside drawing. `porta_linha_frente` migrates legacy only; indices never govern contour/resize. Handle/Alt/preview share edges/normals; profile follows curves. Migrate old fractions once. Resize reanchors tangentially without replacing edited vertices/faces; retain controlled-curve regression.
- Measure coverages/interleaf gaps (`respiro_original`) from panel normal, not noisy plate. Diagonal supports use angular hinges. Historical profile rule: upper cabinets bottom, lower cabinets top, towers side.
- Front backed by box/basket becomes native drawers by FACE, including rotated islands; never convert an entire side. Preserve side coverages/height proportions; manual edits replace references. Shelves retain UID/material/cutouts/free gaps. Audit: `tools/migrations/audit_and_repair_integration.py`.
- Base/top setback <=3.1 mm moves to outer corner through `ajustar_encaixes`, preserving E/shape/systems and rebuilding anchors. Extend partitions that previously touched the actual face. Back 5 mm, groove at 15, insertion 7; DXF minimum setback 15. Partial/orthogonal backs keep per-PLANE margins, never full-box expansion. Island has one front (+X/-Y in photo), opposite becomes back, corners preserved.
- Masonry 393: explicitly define mesh; native raycast skips undefined objects. Right-release onto vertical face uses cabinet back; upward horizontal uses base/upright placement. No size/gap limit; native G, offset dimension and zero control clearance. Ceiling is a reference, not cabinet support. Guides stay editable; `OBJECT_OT_arrastar_na_parede` retains the gesture.

Validation: read [tests](../../tests/CLAUDE.md). Redirect `pasta_biblioteca` and
`opcoes._pasta_addon` before register; temporary fixtures only, real integrity
read-only. Skip 5.x presets unreadable by 4.2. GUI requires current PC authorization.
