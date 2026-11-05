# Archy Builder features and regression scenarios

## Installable package identity (409)

- The source folder, archive root, developer link and preference key now use
  archy_builder. Native editor types and preference classes use ArchyBuilder;
  newly created cut modifiers use the Archy Builder prefix. No old-root import
  shim is installed, as authorized before public use.
- test_preferencias_nativas_pertencem_ao_pacote_archy_builder registers an actual
  Blender preference entry, resolves its concrete preference type, changes the
  unit to CM and verifies the option reader observes it. The old source directory
  must be absent. test_vinculo_de_desenvolvimento_usa_a_pasta_archy_builder checks
  the exact junction source/destination in a temporary directory without linking
  or changing an installed add-on. Packaging tests require a single new ZIP root.
- Existing editor tests now save/reopen the new native editor identity, preserving
  mesh, parent links and object properties. Installation and lighting tests cover
  the updated cut names. Real library files were moved with identical contents.
- Validation: targeted 302 tests in 16 executions, then full 3436 tests in 80
  executions on Blender 4.2/5.2 passed (dist/rename409-targeted-confirmed.log,
  dist/rename409-full.log). A unit assertion initially inspected an RNA instance's
  bl_idname instead of its actual preference registration; the corrected scenario
  verifies the concrete type, module key, RNA identity and effective option value.


## Source organization (408)

- Scope: 44 runtime owners grouped under core, cabinetry, architecture, ui and
  integrations; 29 offline scripts grouped under tools/library, hardware,
  migrations and audit; build/link under tools/development. Technical source,
  test and documentation paths use English. User-facing descriptions omit
  external product branding; serialized legacy API/property spellings survive.
- Compatibility inputs: old and canonical imports for all 44 owners, six cabinet
  domains, owner monkeypatches, cabinet resize with modeled internal meshes,
  native undo/redo and unregister/reload/register. Expected: one module object per
  owner, unchanged meshes/scene objects, correct coordination and original IDs.
  Automated scenarios: test_todos_os_aliases_tem_uma_unica_implementacao_inglesa,
  test_recarga_religa_setores_e_preserva_objetos_da_cena and existing organization
  behavior tests in test_organization_blender.py.
- Resource inputs: nested preferences/library/hardware source paths. Expected:
  original root preference key and bundled biblioteca/ferragens/fotos directories.
  test_recursos_e_preferencias_continuam_na_raiz_instalavel protects these paths.
- Structure inputs: five sector boundaries and all nested implementations.
  Expected: exact root package set, declaration-only boundary initializers, every
  implementation in the explicit reload list, no copied cross-domain functions.
  test_structure_blender.py preserves and strengthens these contracts.
- Tool inputs: direct CLI from an unrelated temporary directory, no PYTHONPATH,
  missing explicit DXF source, nine hardware/photo resource declarations, staged
  publication with simulated copy/delete failures. Expected: help exits 0;
  missing source exits 2 without writes; resources stay in original directories;
  hashes, backups and rollback survive relocation. test_migrations_blender.py
  now has 14 tests; internal audit/repair and joint suites use canonical imports.
- Documentation: 21 English AGENTS/CLAUDE pairs with exact mirrors, scoped guides,
  source routing and local safety contracts. Historical notes remain reference
  documents rather than automatically inherited instructions. 174 ignored logs
  moved to dist/logs/legacy without deletion. Data/snapshot/library filenames and
  binary contents remain unchanged.
- Validation: full Blender 4.2/5.2 harness, 3432 tests in 80 executions passed
  (dist/organization408-full.log). Independent review strengthened the boundary
  inventory; subsequent targeted run passed 156 tests in 8 executions
  (dist/organization408-review.log). No GUI or open-project interaction.
- Package: build from an unrelated working directory; 759 archive entries,
  all runtime Python sources identical to the checkout. Fresh ZIP extraction in
  temporary directories passed import/register/unregister/reload in 4.2 and 5.2
  (dist/package408-4.2.log, dist/package408-5.2.log). Static audit: 21 exact ASCII
  guide pairs, line limits respected, no broken local links, no binary/data diff.
- Deployment constraint: updating an already loaded 407-or-earlier session needs
  ONE Blender restart because its old source paths no longer exist. Saved .blend
  files require no conversion. Reload within the new layout is automated-tested.


## Historical deliveries

These entries translate recorded work and evidence; they do not claim new test
runs. Historical behavior can be superseded by later versions. Test names, data
identifiers, filenames and evidence paths remain unchanged.

### User tutorial and identity (407-405)

407: README separates ready-made ZIP download/installation/activation/first steps
from developer commands, Blender installation, branding history and code work.
DEVELOPMENT owns clone/junction/build/tests/contribution with reciprocal navigation;
Releases points to installable ZIP. Contribution guide covers reports/suggestions;
banner free use, public repository and LICENSE/NOTICE retained. Links/anchors/XML/
mirrors/temporary packaging checked. Final 4.2/5.2 harness 3422 tests/80 executions
passed (`dist/tutorial407-completo-confirmacao.log`),744 ZIP entries matched source.
First run and isolated repeat failed 4.2 wall insertion undo/redo; next direct 86-test
run and three disposable 406 runs passed. Intermittency recorded without weakening
tests or logic; no open-project/library changes or Blender GUI interaction.

406: Archy Builder name/custom cabinetry/woodworking/architecture/interiors in
editor/library/menus/messages/README/banner/GitHub; archive and internal package
archy_builder. Preferences/operators/properties/editor IDs/cut/trim prefixes kept.
Editor regression saves/reopens temporary legacy tree/properties/UID/parent/mesh;
library regressions cover both old roots, UUID/idempotence/single registration,
personal libraries retained. Packaging retains internal package/licenses.
Targeted 218, full 3422/80 passed (`dist/marca406-completo.log`);744 archive files,
100 catalog UUIDs, mirrors/links/XML checked. No open project/preset changes or
physical GUI gestures; registered labels/layouts checked headlessly.

405: welcoming README/development notice/install/contribution, old history retained.
Official CC0 LICENSE/rights-scoped NOTICE included in ZIP. Two packaging tests use
temporary files, complete license/credits, exclude backups/cache/temp, clean rebuild
without previous-version residue. Full 4.2/5.2:3414/80 passed
(`dist/publicacao405-completo.log`), complete notices/local links/banner XML checked.

### Masonry, installations and room editing (404-393)

404: orange Edit first; native eye right of Ceiling toggles all three type outlines/
names, editing independent. Numeric timer BMesh-copy cache invalidated by undo.
Nine PNG cards use existing photo cache, filhos_de/cascade/floating list/shared grid,
independent upper trail from lower library. Wall/Floor/Ceiling never filter models;
door may lie as trapdoor, spots/pendant on all three, lowered ceiling keeps support.
Drag starts in source editor. Native ray ignores assembly, queries marked masonry;
preview highlights full face/type name/color. Right-drag reuses placer, release
changes support UID/face/pose/cut; original unchanged in preview. Identity/modeling/
opening/light energy preserved without remount; invalid/exception rolls back.
Instalacoes 21 covers 190/320/564, eye/forced edit, catalog/photos/cascade, free models,
floor door/all-support lights, ray/preview/Esc/left-right release, different faces
on same object, cut transfer/rollback/modeling/energy/save/reopen/native undo-redo
of create/reassign/eye with support/cut assertions after every undo. Title-overlap
regression failed `dist/alvenaria404-titulo-antes.log`; field now 8 px below title.
GPU background 5.2 light/dark at 3 widths: `dist/alvenaria404-*-modelos.png`,
`*-categorias.png`, eye callbacks `dist/alvenaria404-faces-cima.png`, `*-baixo.png`,
`*-ocultas.png`. HIDE_ON/OFF metadata checked; native icon absent from offscreen
proof. No physical gesture/test window/open-project/library changes. Full 3410/78
passed (`dist/alvenaria404-completo-final.log`); snapshots unchanged, new context only.

403: own masonry tab/types/installations; Cabinets keeps 2D/categories. Create first
only for undefined mesh; mixed ignores registered active support. Type choice opens
native face selection, type colors/names only there. Confirm/Enter same operation,
Esc no registration/change. Edit preselects type, deselection preserves other types/
Mesh; legacy normals materialized. Room categories never merge type selector sides;
Shift-click two native faces does not repaint categories. Alvenaria 5->16. Native A
then immediate confirm before timer used to refuse; direct native selection read
fails before/passes after both versions (`dist/alvenaria403-confirmacao-antes.log`,
`*-depois.log`). GPU5.2 Dark/Light 190/320/564: `dist/alvenaria403-*-modelos.png`,
`*-piso.png`, `*-teto.png`, `*-confirmar.png`, `*-modulos.png`, `*-porta.png`,
`*-forro.png`; real cube callbacks `dist/alvenaria403-faces-cima.png`, `*-baixo.png`.
Fixture UI scale 1 because background returns 0; names/occlusion checked. No window/
physical gestures/live data changes. Full 3368/76 passed
(`dist/alvenaria403-completo-final.log`),45 packaged sources/mirrors/limits matched.

402: electrical outlets/switch plates, recessed/surface spots, vertical pendant;
ceiling lowering from region/selected faces, flat or sloped, per-side perimeter trim/
linear light. Iluminacao covers hole/direction on floor/wall/ceiling, lights following
lowered ceiling/returning to original, partial trim/save/reopen/undo-redo/cards at
190/320/564. GPU5.2 Dark/Light `dist/instalacoes402-*-modelos.png`, `*-porta.png`,
`*-forro.png`. Full-panel regression prevents Installation title/support overlap.
Cut must use support frame rather than assumed vertical Z. Remove ceiling transfers
only linked lights before deleting mesh/cutters.

401: swing door/sliding window/balcony door cards, dimensions/opening. Esquadrias
covers shell/solid cut/restoration/existing opening/resize over step/native scale/
flip-mirror/mid-swing collision/tall cabinet/layout. Shell Boolean Exact may return
marked cutter caps; native-face filter keeps opening clear. Passage/swept-leaf warning
does not block cabinet.400: Wall/Floor/Ceiling faces on one mesh, normal legacy
compatibility, editable dimensions and moving support link; classify without Mesh
replacement, legacy normals, dimension/translation/lost-face/three-width layout.

399: names apply category to all selected faces, remove only if all already match;
mixed gets chosen category. No Category clears without square/empty record; repeat
preserves others. Eye beside Exit toggles colors/names only. Automatic category or
free connected plane;2D restricts clicked plane. Native Shift/Ctrl/Shift+Ctrl face/
path/fill:3x3 grid 0->8 gives 5 path faces/9 fill; original face-only index canceled
with 1, vertex+edge offset fixes 5/9 (`dist/ambientes399-novos.log`,
`ambientes399-corrigido.log`). Original joins Local View only for operator without
redraw; restore camera/isolation/proxy/session/manual hiding. Categories inside 2D
keep view/full list; hits/preview/colors clipped to active area, whole native faces
classified, no geometry split. Central-hole Ctrl routes 5 faces without crossing hole;
no path preserves selection, modifiers dispatch. Fast clicks reuse BVH; Tab closes
only categories; undo clears handlers/proxy; scene switch preserves new selection.
Ambientes 47->61; GUI fixture changed to Shift. Targeted 908/18 passed
(`dist/ambientes399-setores.log`); GPU tuple/helpers `dist/ambientes399-menu.png`
at 3 widths, eye metadata only; real `dist/ambientes399-faces.png` callback verifies
clipping/visible selection with eye off. No window/reload/live-data changes or physical
GUI. Full 3306/70 (`dist/ambientes399-completo.log`),41 source/mirror/limit checks.

398: equal 2D/Categories columns, full red Detach below, orange Define. Room name
applies on release through existing named UNDO operator; no Set As; square palette
only, full-width exit/return, no category list in 2D selection. Tab returns 2D; reopening
categories starts new category edit. Existing faces retain category on vertex moves/
neighbor removal; duplicate coincident/subdivision new faces start 0; reused native
faces count as existing. Transient BMesh wrapper/Python identity, no RNA IDs or
coordinate inference; clear on exit/undo/save/open/unregister. FACE CustomData
reallocates wrappers: recapture after allocation before paint. Unchanged cache does
not reread Mesh. Regression sees native copied category 1 before observer,0 after,
manual click assigns Bedroom. Ambientes 38->47 covers 190/320/564, actual release
operator, red drawing branch only detach, moved/new/neighbor faces, cleanup/subdivide/
undo-redo/two contexts. Targeted 564/12 (`ambientes398-alvos.log`); partial drag context
without mode now uses native context for sensor while retaining cache API, final 790/16
(`ambientes398-alvos2.log`). Real GPU tuple/color callback `dist/ambientes398-menu.png`,
`dist/ambientes398-faces.png`: new face gray until manual,[1,2,0]->[1,2,2]. No window/
reload/live data/physical gestures. Full 3278/70 (`dist/ambientes398-final.log`),41
packaged sources/mirrors/limits matched.

397: removed initial Edit Rooms duplication, kept Edit Wall/Remove Masonry side by
side and internal room context. Three-width single-entry/no-method/no-point layout;
Ambientes remains 38, selection/navigation unchanged. Targeted 420/6
(`dist/ambientes397-alvos.log`), tuple GPU `dist/ambientes397-menu.png`; no window/live
changes/gestures. Full 3260/70 (`dist/ambientes397-completo.log`),41 sources/mirrors/limits.

396: wall 2D or direct room Edit Mode without camera alignment; native faces, automatic
connected planar hover/Ctrl single face, automatic click vs Ctrl toggles, Enter manual
2D confirmation. No method/point/confirm/remove/cancel menu controls; old point API
retained. Preview independent of selection, moving to menu preserves it. Native
BVH/dissolve BMesh copy at entry/timer, never hover/click rebuild. Fixed masonry
ignores ceiling/externals; Ctrl actual faces, no selected-vertex inference. Numeric/
name state/cache cleared on Tab/Esc/scene/undo/unregister. Ambientes 24->38 covers
three widths/two entries/camera/planes/Ctrl/fixed-source/hiding/hover/no-rebuild/
menu/navigation/click/Enter/Tab/native undo/moved-vertex invalidation/scene. GUI
points fixture changed to Ctrl/Enter; syntax only, no window. Real GPU callbacks
`dist/ambientes396-menu.png`, `dist/ambientes396-previa.png`:64800/32400 pixels.
Targeted 626/14 then 74/2. Hole regression: native dissolve needs multiple faces;
previous preview omitted part, failed `dist/ambientes396-furo-antes.log`;8 m2 region
with 1 m2 hole remains clear. Cache-only grouping; `dist/ambientes396-furo.png`
54000 automatic/6750 manual pixels. Final targeted 166/4; full 3260/70
(`dist/ambientes396-final.log`), earlier 3258 also passed
(`dist/ambientes396-completo.log`).41 sources/mirrors/limits; no physical gestures.

395: Exit Rooms/Return Wall and Set As Room side by side, equal orange 28 px/6 gap,
room list below, existing assignment/return operators. Ambientes 23->24 covers return/
no-return 190/320/564, bounds/alignment/operation/highlight. Old expectedFailure
`dist/ambientes395-antes.log`; targeted 392/6. Real tuple GPU
`dist/ambientes395-menu.png`; no window/live changes. Full 3232/70
(`dist/ambientes395-completo.log`),41 source/mirror/limit checks; no physical gestures.

394: stripes reproduced as native-face/color depth fighting, not duplicate mesh.
Native GPU projection depth only, stack restored even on exception; no vertex/
material/XY movement/custom shader. Cube 8 vertices/6 faces/12 unique cached triangles.
Before `dist/ambientes394-antes.log`, regression both projections. Equal Edit Wall/
Remove columns, Define full row; room edit inside wall returns same clipped region,
Tab retains return, entry failure restores wall, invalidation clears names/numbers,
new operator on RELEASE. Ambientes 17->23 covers projection/restoration/topology/
cache/widths/native return/Tab/failure. Isolated native GPU100% color coverage both
views, front occluder retained (`dist/ambientes394-gpu.png`,`.json`); menu helpers
`dist/ambientes394-menu.png`. No window/reload/live-data/physical gestures.
Full 3230/70 (`dist/ambientes394-entrega.log`).

393: explicit mesh Define Masonry, native ray ignores undefined occluders, one block
can have opposing walls/floor/ceiling. World normals classify; ceiling never cabinet
support. RMB and library attach freely despite size/occupancy without deforming.
Confirm rereads marker/face; Esc restores. Floor retains Z rotation/upright base,
90-degree wheel/support following. Native G stores offset; zero/negative motion
respect plane, dynamic dimensions/Mesh retained, save/reopen/undo-redo. Three-pulse
numeric signal/timer reserved, not size-triggered or opening implementation.
Paredes 21->39: marker/remove/ray/whole block/overlap/floor/G/zero/cache/wheel/Esc/
persistence/isolated pulses; prior G reset reproduced `dist/apoios393-antes.log`.
Ambientes 17: INT native-face selection without mesh/material change, presets/UID/color,
shared-copy isolation/empty selection, wall-floor Kitchen/G Bedroom/renamed folder UID,
square/name/palette release, per-UID colors preserving others, full label rectangle
inside concavities or omitted, native-copy dissolve/external exclusion/Object Mode
hiding/save/reopen/undo-redo. Reuse native estimates/Collections, no parallel material/
module hierarchy. Earlier entries now explicitly mark supports/free placement.
Targeted 742/18 before final palette cases. Disposable callback primitives include
Kitchen/Bedroom, omit narrow Laundry; `dist/alvenaria393-primitivas.png` is a diagram,
not screenshot. Open-instance GPU refused connection; no window/live-data/real GUI.
Full 3218/70 (`dist/alvenaria393-fechamento.log`);17/39 suites, structural contracts/
snapshots unchanged,41 packaged sources/mirrors/limits checked.

### Measurements, envelope and visibility (392-386)

392: text opens unselected/cursor end; normal Backspace, Ctrl+A/Shift selection,
highlight editable characters only (not auto unit/result), click/Shift positioning,
plain arrow collapses selection. Ctrl+Z/Shift+Z/Y local 80 history restores cursor/
selection, new writing drops redo, no scene geometry until confirm. Wall shortcut
never inserts unicode; scroll distance->quantity resets history. Medidas 13->21:
prior Ctrl+Z inserted z/ignored, menu/HUD entry/Backspace, keyboard/history/highlight/
real modals/two wall dimensions. Before `dist/medidas392-antes.log`; unit parser
100+50CM ->600 mm/150 cm/100,5 m by option, no neighbor-unit inheritance; old inline
fixture now explicit Ctrl+A. Targeted 830/10 (`dist/medidas392-alvos2.log`). Isolated
real-function GPU `dist/medidas392-campos.png` covers Backspace/select/mixed/history;
wcol_text almost black so wcol_regular.inner_sel now provides contrast. GUI fixture
600->60 Backspace->600 undo->Ctrl+A->arrow->expression syntax checked only. No
window/reload/live data/physical gestures. Full 3148/68 (`dist/medidas392-final.log`),
40 packaged sources/mirrors/limits, snapshots unchanged.

391: existing period-thousands/comma-decimal formatting with configured MM/CM/M,
leading fractional zero/no artificial zeros, original input separate from display
so typed 1234 is not reinterpreted as 1.234 decimal. Cursor map maintains click/arrows/
insert/delete; native expressions/units/pasted thousands/comma, original single dot
remains decimal. Editable expression preview/cache 128 per text/unit, cleanup on
unregister, quiet incomplete/error. Names/counts/pixels/angles never receive mm.
Menu/HUD/wall/guides share scaled 4 px rounded box.28 snapshot labels changed, geometry
unchanged. Medidas 13 inputs 1/.1/1234/12345/12345.67/comma, units,.2+.5, m/cm, error,
cursor/keyboard/paste/cache 20 draws=1 calculation/unit switch/types/corners.
Before `dist/medidas391-antes.log`; targeted 814/10, preflight 2964/66. Isolated GPU
partial-occlusion feasibility `dist/provar_gpu391.py`, `dist/gpu391-parcial.png`:
native BLF/depth fades occluded text/line only. RTX4070 SUPER/OpenGL medians 5 samples,
40 frames/sample,4 dimensions/frame:0.2294 ms current vs 0.3853 two-pass,+0.1559 ms.
Effect NOT enabled under user's condition; no guarantee for other GPUs/scenes.
No new window/gesture/live project/library change. Full 3132/68
(`dist/medidas391-entrega.log`), real-box GPU `dist/medidas391-caixas.png` six inputs,
all sources/mirrors/limits checked.

390: `caixa_local_do_modulo` formerly measured door carcass via
portas._limites_locais_modulo; now modulos.pecas_do_envelope and nominal HUD corners
include frame/supports without changing inner door opening. Local frame prevents
rotated bound inflation, shared back orientation; drag/library/dimensions/obstacles
share it. Exclude open leaves/handles/outside copies. Framed sliding regression 15 mm
frame/100 plinth/80 header previously penetrated side 15/base 115 mm
(`dist/parede390-antes.log`). Paredes 16->21: native bound_box comparison/inner opening/
rotation/four backs/exclusions/wall limits/dimensions/two-frame contact. Targeted 878/10
(`dist/parede390-alvos2.log`); live read-only 389 six supports, body 1300x2503x550,
envelope~1330x2571.921x649.073 mm, confirms divergence without writes/reload.
Full 3106/66 (`dist/parede390-entrega.log`),40 ZIP sources/mirrors/library retained,
no live gestures.

389: Alt rejects occupied handle position before parent/property/wood rebuild,
using shared numeric `_lugar_do_puxador`,0.1 mm effective-anchor tolerance/intervals
on same edge/face, including clamped endpoints with different fractions. Separate
positions/opposite face/other panel allowed; hidden neighbor still blocks. Existing
profile never deleted; refused target retains last valid/header warning; Esc restores
legacy duplicate origin. No mesh scans. Two ALCA Y+/X+ reproduction yielded 0 distance
before (`dist/puxador389-antes.log`). Puxadores 32->40 covers overlap/proximity/clamp/
separate/opposite/rotation/self/hidden/ALCA-BORDA/profile/cancel; failures
`dist/puxador389-regressoes-antes.log`, targeted 640/8 `dist/puxador389-alvos.log`,
original after `dist/puxador389-depois.log`. Full 3096/66
(`dist/puxador389-entrega.log`),40 sources/mirrors/library, no GUI/live changes.

388: contextual fixed visibility strip, plain label left, icon-only eye/pencil
36x30 right, short label narrow; selection-compatible only, no empty reservation
for common/no selection/Handles/isolated hardware. Editor's fixed target retains
controls when extra selected. Reuse materiais.protegida_no_grupo, unchanged wire/
snap/grouping. Visibilidade 26 covers 220/320/480, icon centers/context/reservation/
top library. Old test_faixa_segue_referencia... failed
(`dist/visibilidade388-antes.log`); snapshot revised. `dist/visibilidade388-layout.png`
is coordinate diagram/illustrative icons, no window. Full 3080/66
(`dist/visibilidade388-entrega.log`),40 sources/mirrors/36 reviewed snapshots/library.

387: replaces 386 Create-row eye with 38 px fixed strip by divider, eye/pencil plus
text; top library places it above footer. At this historical stage present with no
selection/after cancel, disabled isolated hardware (388 later changes). Tab groups:
door leaves/frames/bases/rails/hardware; drawer body/front/handle/rails; shelves+
partitions; backs; body. Native white WIRE/.22 opacity preserves mesh/material/E/
parent/H/Alt+H/render; restore temporary viewport settings but preserve manual edits.
Native pencil left includes with descendants/right removes, Enter/pencil confirms,
Esc restores; cabinet UIDs, no new Collection/reparent. Navigation/menu pass; failure/
undo/load/unregister free editor. Save suspends/resumes without persisting appearance;
overlapping groups restore only after last turns off. Hide doors? Yes same controller,
No unchanged. Surface ray passes wire, native vertex snap includes actual extras,
no copied meshes. Visibilidade 24 across both versions: sliding frame/drawer rails/
internals/renamed UID/extras/overlap/H/undo/delete/save/native copy/restore/ray/
editor cancellation/error/navigation/fixed empty strip.386 failed 0 vs 2 controls
(`dist/visibilidade387-antes.log`). Areas_criacao floor 58 with updated wire/undo;
sidebar/structure disabled fixed buttons/clipping/options priority/short scrollbar
travel/track. Snapshots reserve bar column;220/320/480 coordinate diagram
`dist/visibilidade387-layout.png`, no physical capture/gesture/live edit.
Full 3076/66 (`dist/visibilidade387-entrega.log`),40 byte-identical sources/mirrors/limits.

386: visible target doors prompt Hide doors? Yes/No before points/free volume. Yes
whole leaves/frames/handles/hardware, No preserves view; no visible doors skip. Eye
30 px shares Create row, available in wizard/free reference, native View Layer
hide_set only, no parallel state/timer rehiding. Show explicit doors only, not rig
controls/holes/render/collections/body/other modules. Target stays wizard cabinet,
hidden active leaf resolves cabinet, stale context refused. Native H/Alt+H; cancel/
undo/load clears prompt. Areas_criacao+16 covers 3 domains/volume/answers/target scope/
narrow icon+dimensions/real visibility/rig/H/undo/free target/active leaf/no doors/
menu/stale/cleanup. Remapped native hide key matcher passes between points, old
guard failed `portas386-h-repro.log`. Menu answer keeps future questions there,
restores origin on exit; operator coverage/SKIP_SAVE.220/480 rectangle diagram
`dist/portas386-layout.png`, illustrative icon, no GUI. Full 3028/64
(`dist/portas386-entrega.log`),39 packaged sources. Intermediate 4.2 wall undo failed,
isolated/final passed without wall changes/test weakening; live project/library intact.

### Selection and shared interiors (385-372)

385: simple drawer group, double front/body unit, then its own handle simple selects
accessory; direct double handle also isolates, active accessory stays. Precedes wall
scope, no global click counter or ordinary-native change. HUD+6 covers front/back->
handle/tab, direct double, already active, wall, other-unit handle, no inherited focus,
native ordinary/wall PRESS/CLICK. Three fail-before `gestos385-repro.log`; cleanup
restores tab. Targeted 906/10 `gestos385-cenarios.log`; full 2996/64
`gestos385-completo.log`,39 sources, no physical GUI/live edit.

384: Shift-click adds another unit after isolation; Shift-double removes whole-opening
selection accumulated on first PRESS before isolating, preserves external groups.
Plain click global; doors/handles unchanged. HUD+3 actual keymap PRESS/DOUBLE_CLICK/
Shift, two units/native Tab excludes third, Shift-double external preservation/plain
return. First two fail-before `selecao384-repro.log`; helper restores tab. Targeted 658/6
`selecao384-cenarios.log`; full 2984/64 `selecao384-completo.log`,39 sources; no GUI.

383: selecao.malhas_para_editar recognizes eh_gaveta plus eh_grupo_gavetas, native
multiobject box+handle edit only selected units, no ascent to cabinet/other drawers.
Restore active/selection, shared Mesh isolation for multiple units. Operadores+3:
unit/three Tab cycles, two units+externally shared mesh, native undo/redo individual
scope. All failed old poll (`tab383-repro.log`),118 pass after both versions
(`tab383-operadores-final.log`). Read-only open scene, no physical Tab. Full 2978/64
`tab383-completo.log`,39 sources.

382: group paint filters handles/hinges/accessories/drawer rails/descendants. Native
Ctrl+L menu, protected material operator delegates make_links_data with filtered
context, selection/active unchanged for move/hide/duplicate. Individual no-group stays
native. HUD+8: group+external source/catalog/unmarked child/individual handle/hardware
source/native menu+other actions/no-group/internal groups/undo-redo. Compare actual
material references/names including .001; no real library access/deletion. Two fail
`pintura382-repro.log`; targeted 650/10 `pintura382-cenarios-finais.log`. Disposable
seven panels painted,104 hardware meshes keep metal/selection; isolated renders
`Backups/ArchyBuilder/pintura382-auditoria/`, live data intact, no physical Ctrl+L.
Full 2972/64 `pintura382-completo.log`,39 sources.

375: six tabs/unified Shelves-Partitions, old enums/read/selection follow compatible.
areas_criacao owns type/points-volume/one numeric capture/count/gap/other-type/exit,
names/numbers per scene, ends snap before questions, no recapture/duplicate type.
Both orders detect gap before mutation, including new shelves+old partitions;
cancel keeps existing, invalid creates nothing. Partition subsets by name permit
different depth/height/coplanar contact, preserve drawer limits. Fill left/right
extends chosen segment only, actual support face/Boolean EXACT. Keep leaves gap.
BMesh bisect/cap preserves Mesh/UV/material; uniform coplanar caps avoid float wedge
creating four-face Boolean edge, no artificial clearance. Live cut follows depth,
undo-redo keeps references. Divisorias+12 keep/fill 2 sides/later creation/coplanar/
partial thickness/heights/drawer limits/resize/undo/rotation/Mirror/closed volumes.
Areas+7 type-first/volume/continue/no extra clicks/gap/cancel/shelves later/invalid
command-scene/unified tab. GUI adapted type->volume->partitions->shelves->exit,
not run. Full 2836/64 `internos375-final.log`; final narrow-question 56 directed
`internos375-perguntas.log`. Render keep/left/right expected volume/Mesh in
`Backups/ArchyBuilder/internos375-auditoria/` PNG/resultado.json; snapshots only
header, fields same,39 ZIP sources/live scene retained.

374: individually selected leaf is creator's fixed native Object.ray_cast target,
overlapping leaf cannot steal hit. No fixed leaf uses visible HUD ray; hidden/locked
still protected, no Python vertex scan. Swing<->sliding adapts lateral parametric
edge, owner/fraction preserved; sliding external edges, swing free side. Closed pose
prevents inversion when open; horizontal/nonparametric/resize-only retain contracts.
Puxadores+7 convert-return/no duplicate, new profile sliding, open pose, overlap target,
hidden/locked, visible HUD bridge, delete/recreate second leaf without changing first.
Read-only live scene had hidden leaves/no handles, never revealed/changed. Isolated
renders swing/sliding/delete-recreate, one handle/leaf, `Backups/ArchyBuilder/puxadores374-auditoria/`
PNG/result; no full physical gestures. Full 2798/64 external `puxadores374-completo.log`,
ZIP sources checked.

373: independent theme overflow scrollbars, proportional/thumb/track/wheel/touchpad,
only pointed panel, Esc restore; fixed tabs/footer, options/lists above. Existing bounds/
offsets, not viewport. `rolagem` vertical track distinct size slider. Sidebar+5 all tabs/
overflow/drag/bounds/Esc/independence/wheel/touchpad/header/options/proportion/resize.
12 px bar column reflows fields/photos, no overlap, header/divider retained. Shelf
pairwise-overlap regression retained, library uses useful width; shrinking-photo threshold
stable, TRACKPADPAN ANY. Snapshot bar/narrow reflow plus pending 372; existing labels same.
GUI+1 independent scroll/cancel prepared only. Captured callback primitives/theme/
clipping/free column `Backups/ArchyBuilder/rolagem373-auditoria/`; approximate-font 2D
export does not validate window gestures. Full 2784/64, external
`Backups/ArchyBuilder/rolagem373-entrega.log`, package 373 checked.

372: areas_criacao owns temporary volume/plane, one surface/interior/view-plane click,
no vertices required, module frame. Empty+numeric bounds prohibit Edit/subdivision/
shear,8/4 corners. G/R/S/HUD/face centers/B reuse native paths. Apply passes names/
numbers to drawers/shelves/partitions/backs; doors start FOLHAS with explicit plane,
E stays domain. Count/depth never reopen old gesture. Existing copy/restore dimensions/
cursor/selection, invalid leaves reference. Cleanup Esc/undo/save/load/unregister;
Enter confirming G/field does not Apply, zero S keeps last valid. Areas+21 topology/
orthogonality/GRS/4-point plane/anchoring/validation/HUD/B after displacement/one handoff/
5 domains/preview=door/first click/Tab/menu/cancel/undo/save/invalid atomic. Snapshot
only 12 Define by Plane insertions, old values/shapes same. GUI+1 button->nonvertex
face->blocked Tab->typed dimensions->Apply->quantity, prepared only. Full 2774/64.
Headless geometry 200 mm cube->473x600x964 volume,473x964 plane, shelf right opening,
body intact/no temporaries. Reviewed renders use numeric corners, not GPU interaction
proof. `Backups/ArchyBuilder/area372-entrega.log`, `area372-auditoria/` PNG/result.

### Walls, joints and native editing (371-296)

371: fixed Object.ray_cast only chosen wall, no scene fallback, skip ceiling/hidden
backfaces even same mesh. Points native VERTEX/ONLY_SELECTABLE cursor translate,
face plane, RELEASE confirm, restore cursor/hide_select. Visibility is frontal-envelope
intersection area with actual region including holes/concavity;>=90% on entry remains
editable all session even outside later, new registrations editable. Other partials
use temporary evaluated BMesh/Boolean EXACT gray/hide_select, excluded dimensions/
editing, sources intact. Exit/undo/error restores Local View/hiding and cleans volume/
copy/locks. All three entry methods share. Paredes_selecao+11: external/same-mesh
ceiling/backface, snap params/filters/confirm, cancel/error restore,90/89.9/50% and
triangle, clipped immutable geometry, retained permission, rotated wall, undo/rollback.
GUI+1 three-vertex press-drag-release/ceiling exclusion/cursor/menu confirm prepared
only. Headless whole/gray partial render, eight original meshes intact, zero residue,
`Backups/ArchyBuilder/parede371-*`. Full 2732/62,38 ZIP sources/mirrors checked.

370: actual read-only diagnosis found non-PERSISTENT panel handler vanished on load;
general timer survived but deletion cleanup not scheduled, hardware clicks emptied
native selection. Observer now persistent; click/Shift visible in-layer hardware,
menu/Alt restores afterward. Leaf index includes unrigged hardware; partial deletion
preserves survivor assembly/opening index. Portas+5 save/reopen/delete group,
residue selection/delete/undo, hiding/layer/deselect, double-leaf deletion rigged/unrigged.
Disposable real-scene copy 210 hardware/170 native selected->Delete/cleanup zero
residue, other 527 objects' matrices/vertices/materials unchanged. Full 2710/62,
38 packaged sources, isolated before-after renders, no actual window gestures/live edit.

369: deleted Peca LAYER89/LAYER90 remained children_recursive without scene/collection.
Native view_layer.objects limits click/Shift/door/Tab, safe active when parent absent;
never relink Collections to force selection, retain referenced orphan IDs. Depsgraph
also tracks per-scene objects: Delete may keep data count but remove leaf from scene.
Timer cleans hardware/empty group without resurrecting door, guards undo/Edit/modal,
common children/excluded collections/other-scene leaf. HUD+3 native referenced Delete/
excluded collection/out-of-layer parent. Portas+6 referenced delete-cleanup-hover,
unchanged ID count trigger, one outside leaf, excluded collection, undo, other scene.
Full 2700/62, package-source match. Live diagnosis read-only; MCP disconnected before
final actual-click check.

368: selected A1/A2/A3 always with values, A3 depth callout lower-right through existing
operator, separate offset; resize hides only distances. Free-area placement avoids
existing labels, background DPI0 uses 1. Composicao+3 prefixes/values/corner/no overlap,
A3 hit/typed 600 mm/E retained, area borders. Authorized replacement of old two-stage
contract, input stays in dimension value, no duplicate HUD. Short dimension checks
center, background circle scale 1. Full 2682/62; native GPU/BLF offscreen normal/bottom
edge shows legible labels/separate depth, objects intact, package checked; no live gestures.

367:366 parser fix still drew base 100 mm under floor. `_regiao_acima_do_apoio` uses
evaluated BVH contact-strip faces to clip only fully occupied bottom bands at entry.
Wall/cabinet unchanged; proxy/dimensions/guides/fit/installation share region; reentry
recalculates, no redraw query. Regressions continuous 100 floor/proxy-guide-zero/Mesh,
rotated negative-Z wall, partial floor/suspended beam, cabinets/distant objects.
Recovery-drag refusal uses partial 2.9 m obstacle on 3 m wall; continuous floor is now
unpointable base.366 zero test updated to actual support while penetration refused.
Full 2676/62; read-only supplied scene base+100.00038 mm, Below 0.000002 mm, zero validates.
GPU before-after/objects/session/package checked; no real gestures.

366: Below/Above/Previous/Next/Offset accept 0, also legacy non 2D guides. Zero dimensions/
negative inputs still rejected. Five regressions five offsets modal/no vertex-ID
change, invalids, actual 100 mm floor blocking type/drag, four legacy guides,0.2 micrometer
edge noise. Existing tolerance unchanged; clip only already accepted noise before
contour sample, holes/collisions remain. Read-only Parede.004 occupies 100 mm below
cabinet, region limit below support. Full 2668/62; window/native query confirmed 100 mm
and blocker without movement/pending input changes. Live Blender 365, fix gestures not run.

365: native ArchyBuilderMenu/Biblioteca NODE_EDITOR with owned empty 4.2 gizmo tree.
Editor 19 regressions/version save/reopen, pointer-independent identities/distinct roles,
untouched user trees, actual 3D bridge/context restore, origin text/drag, no viewport error,
legacy strip/workspace migration, tab click, undo, unregister. Temporary cabinet/real 3D
region, not real library/background event simulation. Existing GUI strip now checks
subtypes; switch editor never reopens menu, deactivate retains areas/removes owned tree/
registration. Full 2658/62, package checked; Blender/MCP disconnected, no visual/gesture
GUI/new window.

364: resize recreates hardware/controls; finally reconciles append list with hierarchy
on success/failure, wall registration same before Local View/wires. Selection/cancel
share current list. Paredes_edicao+3 same-name deleted/recreated control, real resize
import with/without cached box, failed regeneration removes new generation.
Full 2620/60, wall editor 81/version; no real-project GUI.

363: real 2600 wall/100 raised floor/2503 cabinet fits 2500 within default 10 mm width/
height limit, zero off, E/model/depth/preset retained. Wall editor+10 floor 3 deficit,
real-opening width, rotated model/wall, persistent 0/2/4 limits, topology/E, numeric preview/
confirm-only resize, native undo, non 2D attachment, cancel/staging/handlers. Excess red
POST_PIXEL/status actual cause/height, RELEASE reports it. Full 2614/60, both cache/deferred
load checked. Separate real-support Armario Quarto 01 audit 2503->2500, ten panels retain
physical/param E, limit 2 refuses, Workbench render checked, no original save/GUI gestures.

362: seven tabs measured font 12/margin 18 become full-name dropdown below abbreviation
fit. Sidebar 79/version,+8 actual-font threshold/open-switch-close/normal dispatch/
content priority/cascade exclusivity/scroll/no lost fields/width roundtrip/no selection
or mesh change; test_cabecalho_tem_as_sete_abas includes imported presets. Snapshot
header only; draw regression covers after-top-clear field/current choice. Native GPU/
BLF offscreen 564/320/190, no window/live changes/gestures. Full 2594/60.

361: native connected BMesh vertices/faces, orientation 1 degree/plane 2 mm, no selection
reconstruction. Object automatic hover or 3+ planar points, left add/Backspace remove/
Enter confirm/right-Esc cancel, same menu actions; outside viewport/navigation pass.
Attachment ray/highlight, regional cache, no Python vertex scan, native triangulation,
concavity/holes/real bounds. Local View temporary region plus actual plane/area-linked
furniture/descendants; plan original excluded here, Mesh/material/modeling unchanged.
Insertion ray resolves original UID/face, never temporary. Exit/orbit/save/deactivate
cleans/restores; undo cleanup only regular timer after guard. Changed source/missing
proxy ends session. Methods only Cabinets/Walls or active choice, not other wizards.
Wall selection 34 cases monolithic foreground wall, connectivity/orientation/tolerance/
points/concavity/window/coincident edges/hover-cache/actions/menu/rotation/other face/
noneditable source/no residue/prior isolation/manual hiding/restore/delete/move/undo.
`D:/Blender/Backups/ArchyBuilder/` contains `paredes361-cenario.blend`,
`paredes361-antes.png`, `paredes361-depois.png`, `paredes361-visual.py`; render only
maps Local View members to test hide_render, no user edits. Root/test mirrors now
require reproducible temporary scenarios. Earlier pending work committed e786876,
564233d first, no push, Home Builder not consulted.27Oct2026 full 2578/60 passed
`D:/Blender/Backups/ArchyBuilder/paredes361-completo.log`, package 361 checked.
Historical new changes uncommitted then; loaded instance needs reload, no GUI harness.

360: Backs tab, two-corner AssistenteDoVao/native snap, one undo, panel selection. Grooved
6/9 mm Exact supports without replacing meshes; external nailed overlay;15 flush inset,
no nail simulation. Same object edits/type; Esc restores internals. New backs excluded
from structural door/drawer/shelf bounds. Link UID+actual parent+overlap, depth point
within 5 mm finds even legacy, collision also links, nearest back wins. Capacity validates
all before build, invalid restores pose/reason. PostG/Tab timer retains front/height/E,
adapts depth/rails, individual inner-face limits. UNPINNED keeps dimensions/blocks
reassociation to same UID. Delete cutter/modifiers, Edit/undo guards, no legacy auto type/
cuts. Fundos 30 covers 3 types/native groove/6-9-15/invalid atomic/rotation-resize/support E/
delete/link/bounds/snap/distance/height/parent/two backs/rails/individual/Esc/legacy/
partial-failure/no-link/default choices/relink/capacity/responsive icon/undo/guards.
Disposable 3-cabinet right-side-hidden audit `D:/Blender/Backups/ArchyBuilder/fundos360-visual.*`,
live project/library intact, no GUI. Historical Arauco 2024 catalog 6/9/12/15/18, no 8 in
those products; new default 6, gGroove6/9, other positive free E. Authorized 6->7 tabs,
36 snapshots header-only. Legacy missing UID is not empty link, no extra metadata/refit.
27Oct full 2510/58 `D:/Blender/Backups/ArchyBuilder/fundos360-entrega.log`.
Actual handlers/native transform.translate 545->465 mm in both versions, detach keeps 465
after later move;`D:/Blender/Backups/ArchyBuilder/fundos360-handlers*`. ZIP checked,
loaded instance requires reload, no live project changes.

359: writer rejects duplicate object-pair records any direction/end; manual validates
all targets before replacement, no automatic extras. Normalize once after load/append/
undo outside Edit/modal/guards, saved origins retained; nonredundant axial restrictions
move into single-edge metadata, batch resize/loose-group map. Explicit world KDTree
migration nearest existing vertices, no geometry/E/material changes. Solda 16 covers
uniqueness/reciprocal/rotated-scaled true minimum/aligned-index origin-direction/multiple
neighbors/duplicate UID across groups/atomic validation/guards/undo; uN also identifies
thickness partner without sign fallback. Independent review adds optimization/rewrite/
primary reset-map precedence/legacy neg-without-face. Soldas_biblioteca22 external
stage/reopen/idempotence/independent minimum/integrity/source-backup hashes/atomic
publication/rollback/reversal. Historical live 47 objects,10 relations/20 inferred pairs
->10, exact geometry/pose/material/selection; backup
`Documentos/Cabinet Creator Backups/soldas359-sessao-20261027/antes.blend`, report
relatorio.json there. Existing-window visual 4 wires for 4 displaced-side joints,
native library/menu preserved, no GUI clicks. Structure UID contract unique edge/reverse
restriction/rename resolution. Published 328 audited,265 refined,63 intact,2385->1978
same unique pairs, zero invalid/duplicates, independent Cartesian minima 0.001 mm tolerance,
coordinates/topology/materials/parents/UID/catalog/photos/previews retained. Independent
3-model/52-pair reread including modeled meshes. Backup
`Documentos/Cabinet Creator Backups/soldas359-aceite-20261027-042135Z`.
First full assertions passed but byte guard failed because asset guides changed midrun;
reran with stable resources, no weakened guard, separate published hashes.27Oct full 2450/56
`D:/Blender/Backups/ArchyBuilder/soldas359-completo-estavel.log`, ZIP+265 blends checked,
no automated GUI gestures.

358: mixed ordinary object restores only add-on-hidden native outline, removal returns
exclusive HUD; unmarked child within selected group not external. Native select_get/
ViewLayer, no mesh/selection mutation or active dependency, user-disabled outline respected.
HUD2 regressions transitions/child/external curve/preference/native Ctrl+L ordinary
master, floor 180. Historical live Cube master/45 selected, active/selection unchanged;
computer-use existing-window confirmed orange Cube/visible blocking, minimized MCP
black screenshots not evidence.27Oct full 2374/52
`D:/Blender/Backups/ArchyBuilder/contorno358-completo.log`, package checked, no GUI harness.

357: Tab/G exit batches rigs,<=2 explicit layer evaluations regardless hinge count.
Participating handles retain edited Mesh, numeric contour only; nonparticipants keep
parametric positioning. Entry stores names immediately, not timer; same-front refs cached.
Operators native 2400->2100 G/profile not rebuilt/constant hardware cost; handles individual/
material/UV/undo. Both fail old code (rebuild,6 updates instead 2).5.2
Armario_Quarto_08_600x2503x550,276 objects, cProfile: no GUI, Tab exit 0.830->0.425 s,
exit+3 ticks+hardware check 1.235->0.815 s. Logs under
`D:/Blender/Backups/ArchyBuilder/`: `perfil357-extra-antes.log`,
`perfil357-extra-depois.log`, `tab357-prova-anterior.log`.26Oct full 2370/52
`tab357-completo.log`; isolated `tab357-visual.png` profiles stay attached/in bounds.
MCP unavailable, no window/user-scene changes, ZIP5 changed sources checked.

356: Shift keeps whole groups selected but clicked panel/leaf master active, native
Ctrl+L only, no parallel operator. Plain click Empty active, Shift-double isolates source
without painting its other group parts. HUD4 groups/isolated source/loose multiOBJECT
slots/leaf, materials-selection-geometry, floor 178. Door scope remains group with leaf
master; Shift test updated.26Oct full 2364/52
`D:/Blender/Backups/ArchyBuilder/materiais356-final-completo.log`.
Historical live injection only 3 selection functions, active/selection/1146 objects kept,
no re-registration.

355: joint create/reanchor blocks geometry HUD draw/hits/arrows/dimensions/sliders,
clears hover/restores exit, chain/ruler/distance/snap remain. Existing orange start/
confirm. HUD174 blocking/restore, sidebar 71 highlight.
354: pilot one vertex pair across distinct parts/modules even changing source/target
panels, zero-contact first; within-module joints independent, read-only audit, HUD173.
353: preview chain/ruler/numeric without selection, index ruler zeros final fixed anchor,
chain removes pending pair only. Separate gizmo pools preserve bindings/symbols, modal
passes clicks, marker/distance native cursor, no scans. Deterministic read-only cabinet
audit zero first/unique vertex/thickness-separated corners<=25 mm;354 narrows to one
pair. Explicit KDTree outside gestures, uncontacted requires review. HUD+8/floor 171;
external pilot never modifies library.
352: own panel no estimate/room, distance/reset/back/create/cancel, instructions; right/Esc
restores, Backspace/Ctrl+Z previous, Alt same pieces/native cursor. Reset final anchor
fixed, new zero reference, other gaps possible. Restore preview before final operator;
undo geometry+metadata, manual zero controls retained. Semantic box corners/INT POINT
cabinet_solda_vertice u tokens, v legacy; BMesh/reference/save/append/reordered indices
preserve identity. Removed/ambiguous anchor warns without deleting data. Object UID/
parent, destination-local refs follow rotation/reflection. Native-face no-cache snap,
not click-time whole-tree build. HUD163/sidebar 70 cancellation/back/zero/params/Alt/
controls/rotation/Mirror/undo/save/append/rename/reorder/delete/fallback; old gap reset kept.
351: removed finished-door action row, mirror context retained. Assembly Chain/Reset text+
icon, stack narrow. Pool by symbol/occurrence fixes Button 2D immutable-first-symbol
library folder/disk leaking into Assembly. Alternate order/two same icons, never remove/
unbounded growth. Sidebar 69/doors 154, snapshots reviewed.

350:369 modules audited by full category/8 geometry orientations/material/systems;
remove 10 curved diagonals+34 duplicates/mirrors, straight/chamfer retained, front-right
photo visibility tie by ordinal.325 cabinets+3 objects, names/UUID/bytes retained.
External plan/hash/originals, atomic index/delete blends/photos/rollback. Temporary
migrations 11 preserve catalog/metadata/straight/backup, refuse changed library/backup,
delete-failure restores. Backup `Documentos/Cabinet Creator Backups/variantes350-20261025`.
Native group Empty reflection, dimensions positive, shape/door/internal frame parity;
recenter/repeated edits/S after R/Mirror preserve depth/internals. Armarios 20 two
mirror/recenter regressions; angular CUSTOM target, old target migration keeps meshes,
Portas 154 angular-arm volume. Mirror group Object Mode, per-panel duplicating modifier
not equivalent. Retired curved bedroom fixture remains for append/resize/support,
active library tests use active models.
349: release text Create Joint above Chain/Reset, panels/cabinets, existing native snap,
cabinet picks source first point/individual fixes; footer confirm/question returns
origin.190/320/564/no selection/two points/timer-handler cleanup, sidebar 68/HUD152.
348: one rig asset load/assembly, other hinges native Object copies/remapped refs, parent
inverse/IK/drivers/shared mesh/independent opening; native batch deletion preserves
used data, modeled asset-marked mesh not deduplicated. Portas 153 checks attribute
compatibility before native 4.2 comparator crash. Chain detection once/event, stable
bindings/current target, CANCELLED propagated, owner undo, HUD151. David V2 old/new
closed/open geometry/matrix proof.
347: all targets before panel/door/hardware mutation, no two targets for same corner,
thickness skins move together, group validates all before write; CANCELLED no remount,
shared pair validator/simultaneous deltas, HUD148. Duplicate UID within module uses
stored name among matching siblings, not nearest copy; cross-module UID priority,
Operadores 49.
346: outside/ordinary/other-module click clears click/hover and returns GROUP; next click
group, new double for individual. Shift-empty preserves individual scope; invalidate
other viewport memories, HUD146.
345: unchanged swing/full-overlay opening/dimensions/poses preserve leaves/handles/rig,
existing native calculation/no new solver/cache. Changed margin/deleted-old rig/oblique
support still update, Portas 149. Shelves skip identical writes/depsgraph but repair
changed pose without Mesh replacement, Prateleiras 53. David V2 copied benchmark same
panel fit/final carcass checked.
344: before group Tab materialize hardware Mirror in unique meshes in stack order,
keep evaluated form/rig/other copies, no clipping-stuck half. Panels without UV get
metric 1 unit/m, custom orientation/scale kept, native Correct Face Attributes G/R/S
retains texture density, Operadores 48.
343: native ray ignores hidden/local-view walls, group click before/after Tab, HUD143.
Moving all hinge-part vertices during group Tab moves whole hardware/screws/spring/
cup cut, keeps Mesh/partial modeling, persists remount/open/undo without accumulation.
Numeric Mesh reference participates undo/clears completion, rig-version update keeps
manual displacement, Operadores 45.
342: external backup repair restores sides wrongly drawers, adopts 4 Armario Quarto 08
internal boxes, fronts clear carcass, depth native-ray limited, shelves compartment gaps.
Preserve geometry/UID/material in family merge, fixed separators/stretchers structural,
local Boolean Mesh/empty repaired cuts. Check stationary panels/catalog/reopen/photos/
index before hash publication/rollback, Correcao_internos10/migracoes. Audit closed
leaves/drawers and native topology after small cuts.
341: read-only all-module audit actual frames distinguishes envelope overlap from solid
collision, native SAT/BVH0.25 mm, parity ray, L cuts, open meshes not confirmed volume,
excess parts/origin-rotation-scale misalignment, Auditoria 9. Remove Balcao 09/15,
Gaveteiro 01/03 only, curved reception/chamfer diagonals stay, Biblioteca 84. Findings
reported, not automatic rebuild.
340: simple handle selects owner, double handle editor, Puxadores 24/Gavetas 50. Native
mesh guide dashes TRACO_GUIA_M/PASSO_GUIA_M preserve snap, gray label/black hover or
typed box (`atualizar_guia_hover`), Composicao 67.
339: Enter/Exit Wall orange centered 30 px, strong exit OPERADORES_DESTAQUE, Wall editor 68.
338: Composition only selected dimension cross, no Free/Fixed/Redistribute/Replace/
Detach or wall left-right-spacing fields, hidden no selection, Wall editor 67. Edge-dot
typing uses green dimension value digitacao_hud, no duplicate HUD box, Composicao 66.
337: wall HUD so_faces only edge-center dots, filled 5 px/halo,7 highlighted, no arrows,
Composicao 65.336: side distances at half height, top-bottom at half width, face to
neighbor/limit/support, Composicao 65.335: historical two-stage selected distances vs
editing width-height; wall-plane only, no anchor, snap-corner precedence, HUD click never
moves module, arrows inside area_livre via recortar_cota, Composicao 64 (later 368 changes).
334:16 px corner hover highlight 7 px circle, active corner carried with G/drag to
closest target, Composicao 59.333: remove 21 curved-leaf presets,376 remain, straight
diagonals stay, legacy fixture copies, Biblioteca 83/Importacao 80.
331: library place preference biblioteca_lugar global, old screen migrates once, button
changes open layout, Biblioteca_faixa31.332 default MENU.330: Assets button and
object.cabinet_prateleira removed strip/menu/legacy; native View AssetShelf remains,
Biblioteca_faixa30.329: screw head 5.78/top.876 above surface, origin on surface,
cabinet_versao/_anexar_sem_repetir source+version timer replaces v1 flush head,
Portas 145/Puxadores 23/BORDA snapshot.328: screw wire only top circle/cross, unrigged
hardware uses cached _contorno_da_ferragem not thread edges, one-time old marking,
Portas 145.327: old full-overlay v2 incorrectly used adjustment screw on fixing plates;
_ferragens_antigas rebuilds once old rig/pan screw, adjustment remains arm, Portas 145.
326: user-photo flat countersunk 3.5x14, short smooth shank/thread/tip, bichromate, new
name avoids old pan reuse, cabinet_sem_arame below head excluded, Puxadores 23/Portas 144,
BORDA snapshot 3 mm shallower.325: corner 16 px snaps without Alt; Alt adds sides,
Composicao 57.324: back opposite actual door/drawer front saved parede_costas; wheel 90
steps during both drags, width becomes depth at 90; Paredes 15, index caixa.costas,
missing remeasure, Wall editor 66.323: historical pan 3.5x14, two BORDA tab screws tip never
front, four hinge fixing+articulated, real scale, Puxadores 23/Portas 144.
322: user slim edge 80/hole 64,144->128, rear tab/front 20 roll all E, no scaled holes,
flat shading, actual wire, Puxadores 23.321: batch wall region once/Paredes 13, index
caixa wire-only drag, deferred load on release/Loading, first uncached drag writes box,
blend change invalidates, Wall editor 65.320: snap only held Alt, corners/sides, release
free, Ctrl none, Composicao 57.319: G/left drag side under pointer whole-side snap to
neighbors/face/snappable guides, other axis free, historical Alt corner, Ctrl none, Esc
restore; right release outside wall detaches without move, Wall editor 64/Composicao 57.
318: outside 2D preset back on wall/center cursor/limits/floor/ceiling/no overlap/link,
outside wall restores preset rotation, Wall editor 63.317: release G/R/S box-plane snap
12 px to neighbor/face/guides, no front-back confusion, associated returns within face,
typed dimensions unaffected, Composicao 51.316: menu library right-only actions like strip,
grid 8 px, sidebar 67.315: DXF Above/Previous/Offset/Next/Below cross menu/viewport,
offset survives timer/G, Composicao 49; library strip or MENU via timer
cabinet_lugar_biblioteca, Biblioteca_faixa29; menu floating per-level lists/columns/
row-hover/materials/choice, structure 51, old carousel removed.
313:2D project guides 150 plinth/900 counter/1100 sill/1500 upper base/2150 max mm
from face floor, editable viewport/menu, Hidden/Visible/Snap, native EDGE temporary
object removed/restored undo, Wall layout 44,+4.314:70 mm labels/capped dimension font,
hide<7 px, typing cursor blinks.5 s own tick/text selection,46.312: any piece in 2D
selects cabinet for native G, double individual; temporary VERTEX/CLOSEST restores,
depsgraph cached local box+matrix, no mesh reread, Wall layout 40,+3.311: curved-door
resize exact out/back,5.2 curved counter passes.

301: Wall editor 62,+7 collision/full wall rollback/corners/rotated preset preview-center-
confirm/right drag/height/opposite face; Composicao 36 light-dark/halo/arrows/text-after-line.
Shared faixas_livres for placers/distribution/edit, no geometry shrink.22Oct targeted 322
pass 4.2/5.2; full 2003 counted,46/48 executions pass, curved counter 5.2 and 300s library
preview timeout remain (`D:/Blender/Backups/ArchyBuilder/paredes301-completo.log`).
5.2 scene audit legible white-wall/dark-grid labels, lower-right exact bounds/center,
furniture target finds adjacent gap;347 objects/matrices/vertices unchanged, selection/
view restored, backup `D:/Blender/Backups/ArchyBuilder/antes-paredes301.blend`.
300: estimate reads evaluated group axes/actual leaves-drawers/hinges/used face materials,
no persisted counts/3D changes/open-door inflation; missing/partial materials/unidentified
hinge pending, unused slots/hardware excluded. Estimativas 16,+6 measurements/edit/rotation/
read-only/delete/hinge/mixed.21Oct targeted 174 pass; full 1985 counted,46/48 pass, curved
counter 5.2/library 300s failures (`D:/Blender/Backups/ArchyBuilder/orcamento300-completo.log`).
Isolated library refiliation passed but preview regeneration timed out, no floor/timeout
change,`D:/Blender/Backups/ArchyBuilder/orcamento300-biblioteca.log`.
299:2D door click cabinet/double leaf, Shift/PRESS/CLICK multiselection, outside door group.
Actual evaluated creases gray-alpha only hidden, Mesh unchanged; geometry/pose invalidates,
exit/undo discards, numeric redraw, dimensions near item. Wall layout 34,+6; targeted 1054
both versions,5.2 audit 157 objects preserved, latest 2054 only curved-counter failure.
Earlier 4.2 batch redo second Collection scene-unlinked in 2/24 even interior disabled,
kept pending/assertions intact,`D:/Blender/Backups/ArchyBuilder/299-repeticao-*.log`,
`299-sem-interior-*.log`.
298: orbit PERSP/gesture retained, temporary solid/black outlines restored. Drag/click/
right-drag retain mesh/size/release point; double right of last else center, persistent
order; hidden staging previous bounds, children sync confirm. Wall editor 55 release/
rotated movements/double/cancel/cleanup/native wires-restore-undo/no fit; temporary
5.2 visual 3 presets 600x1356x550, original intact.21Oct2042 tests/48,2041 pass, only
preexisting curved-counter 5.2, no tolerance/test changes.
297: width-height/gapE1/E2 clickable, local menu, Free/Fixed and explicit redistribution
separating upper rows; G/add/delete recalculates without moving neighbors. Validate
replacement before removing original, keep size/position/link. No wall menu measurements,
SOLID/OBJECT/FLAT/restored exit-undo, passive observer never blocks native sync.
Wall layout 28 rotated/E/Mesh/invalid/rollback/replace/Esc/undo.20Oct targeted both,
5.2 disposable-window visual, original intact. Full 2006/48,2005 pass, preexisting
importacao:: test_curva_bancada_encaixa_sem_apagar_modelagem_e_abre_fora_do_corpo
error 0.000677527 m vs 0.00005 tolerance, unchanged.
296: context Walls/native context menu, clicked or largest view-facing face, native
Local View restores prior isolation/hiding. Orbit/Walk/Fly exits, pan/zoom stay.
Library/count/gaps/spacing/preview, real contour/openings, height/face obstacles/native
BVH returns. Independent confirm/E preserved/isolated rollback, undo/save/delete ends.
Wall editor 37 both versions; drawing/gesture has no separate solver.

284: six same-name sector packages retain public imports/module aliases/reload with
objects/meshes. Organization identity/reload, TestPacote exact inventory rejects duplicate
same-name implementations; root routing/local mirrors.282: own partition tab/operator
OBJECT_OT_criar_divisorias uses native AssistenteDoVao/snap, validates gaps before writes,
subtracts E, independent drawers/shelves before/after creation, UID supports follow spacing/
resize. BMesh keeps Mesh/material/E/height/cuts. Click group dimensions/side distances,
double panel/native Tab. Partitions tests 3->6/maleiro, multiple/partial shelves/rotation/
other cabinet/params-opening-handles/invalid/fields/bounds/selection/HUD/hits/Esc/dependents/
undo.280: legacy chapa-g3 tag recognizes renamed fake-user asset wrapper even unmarked,
Delete cleans nested inside-out; common/third-party/nonempty data and library untouched,
undo restores tag/fake user.235: Normalize Heights group/unit preserves total/gaps/material/
opening/rails/setback/handles/selection, validates before writes, one drawer no action.
234: individual height redistributes with neighbor, total/gaps same, per-unit depth/rail/
width/gaps, preview no rebuild, one final confirm, Esc restores, one drawer edits opening;
real GUI individual-height/preview/Esc/type regression remains referenced below.


## Historical version 126 inventory

The suite column identifies test_<suite>_blender.py, gui_interaction.py or snapshot golden masters. test_coverage_blender.py requires registered classes to have meaningful coverage. Later versions supersede historical behavior where stated.

## Panels (basic units)

| Feature | Code | Tests |
|---|---|---|
| Real BMesh geometry, X=L Y=C Z=E. | `gerar_malha_chapa`, `nova_chapa` | estrutura, snapshot |
| Modeled meshes stretch and are never replaced. | `_malha_e_caixa`, `_esticar_malha` | estrutura |
| Free positive thickness; red warning above 60 mm. | `_espessura_livre`, `_medida_em_alerta` | estrutura, hud, portas |
| Scale S becomes dimensions; discard Z scale. | `normalizar_chapas`, handler, timer | estrutura, operadores, gui (S no modulo) |
| Leaving Edit Mode updates measurements. | `absorver_edicoes_de_malha` | estrutura |
| Mark/unmark a panel. | `cabinet_marcar` | gaveta, importacao |

## Cabinet and adjacency

| Feature | Code | Tests |
|---|---|---|
| Group panels under a dimensioned Empty. | `cabinet_agrupar`, `agrupar_chapas` | hud, portas, operadores |
| Named group: matching Empty/Collection, requested name through F3 dialog or sidebar box when Chain joins loose parts; door named by model; ungroup returns to root. | `nomear_grupo`, `_nome_da_porta`, `cabinet_nomear_grupo`, `cabinet_digitar_nome_grupo` | portas, hud |
| Complete furniture-only company estimate from 3D doors/shelves/partitions/handles with pending issues; Options Generate Estimate saves.txt through Save As and shows panel result. | `orcamento_da_cena`, `_pecas_internas`, `cabinet_exportar_orcamento`, `_botao_orcamento_opcoes` | orcamento, gaveta, snapshot, gui_interacao |
| Room is Outliner folder containing cabinet Collections; inline expanding Cabinets row, typed Other Name, legacy Varanda=Sacada alias; old cabinet gains Collection. | `definir_comodo`, `cabinet_definir_comodo`, `_abrir_caixa_comodo` | orcamento, gui_interacao |
| Orange Create Handle at top of Handles, matching Create Doors. | `_botao_criar_puxador` | gaveta, puxadores, gui_interacao |
| Cabinet L/A/P rearranges its parts. | `redimensionar_grupo`, `conj_*` | hud, portas, snapshot |
| Cabinet thickness grows inward. | `aplicar_espessura_grupo` | operadores, snapshot |
| Individual panel thickness anchors outer face. | `aplicar_espessura_chapa` | operadores |
| Loose group without Empty uses Scene fields. | `grupo_*_mm`, `redimensionar_grupo_da_cena` | operadores, portas |
| S on cabinet Empty, regression fixed in 126. | `absorver_conjuntos` | operadores, gui |
| Adjacency remembers and closes gaps. | `detectar_adjacencia`, `aplicar_adjacencia` | estrutura, operadores |
| Neighbors resolve by UID, including .001 copies. | `_resolver_vizinho` | operadores, biblioteca |
| Alt chains on all joint corners deviating>5 mm; detach chain and reset ruler. | `_ligacoes_adjacencia`, `desagregar`, `VIEW3D_GGT_correntes_cabinet`, `cabinet_clique_corrente`, `cabinet_tecla_corrente` | hud, gui |
| Sidebar Chain uses selection: group/part confirms detach; targets then external active part connects within 5 mm or chooses vertices; Join Cabinet keeps target fixed; release-triggered. | `_acao_corrente`, `cabinet_corrente_objeto`, `cabinet_desagregar_selecao`, `desagregar_grupo`, `cabinet_conectar_distancia`, `cabinet_conectar_vertices`, `cabinet_confirmar_conexao`, `cabinet_juntar_modulo`, `_puxar_por_pares`, `associar_por_distancia` | hud, gui |
| Alt-drag anchor changes vertex only; ruler deforms toward it. | `cabinet_arrastar_ancora`, `_ancoras_da_ligacao`, `_deformar_ancoras`, `_medida_solda` | hud, gui |
| Reset ruler moves active panel back to joints, asks if dimensions change; active cabinet adapts instead. | `cabinet_resetar_distancia`, `_plano_reset_chapa`, `resetar_ponta`, `_peca_afastada` | hud, gaveta, gui |
| Automatic measurement refresh, no Synchronize action. | `_sincronizar_medidas_ativas` | gaveta |

## Viewport selection and HUD

| Feature | Code | Tests |
|---|---|---|
| Click cabinet/double part; door click whole door/double leaf. | `cabinet_selecionar`, `_selecionar_porta_hud`, `_ENTRADAS_KEYMAP` | hud, portas, gui |
| Create Doors at top; clearance controls only with selected door. | `_aba_portas_gaveta`, `_botao_criar_portas` | gaveta, portas |
| Single-panel thickness never pulls joints. | `aplicar_espessura_chapa` | operadores |
| Click one of multiple selected items leaves only it. | PRESS/CLICK pass-through | hud |
| Shift adds group, or panel if its group already individual; Shift+double isolates within selection. | `_somar_peca`, Shift+DOUBLE_CLICK entry | hud, gui |
| Poll only Object Mode and enabled preference. | `OBJECT_OT_selecionar.poll` | operadores |
| Native outline hidden for cabinet and restored to prior state. | `sincronizar_contornos` | hud |
| HUD for ALL selected groups/panels without hierarchy order; any item arrow/corner. | `_itens_da_selecao`, `_itens_hud`, `_acertar_hud`, `_alvo_e_do_item` | hud, gui |
| Ctrl+Z under HUD never draws freed objects, user-crash regression. | `_esquecer_referencias`, `_alvo_vivo` | hud, operadores, gui |
| Ctrl+Z immediately after door creation: finished modal releases scene objects. | `_larga_dados_ao_terminar` | operadores |
| L/A/P/E lines, labels and screen-limited arrow. | `_geometria_hud`, `_rotulos_hud`, `_triangulos_seta_hud` | hud, snapshot |
| Arrow drag keeps chosen corner fixed. | `cabinet_arrastar_hud`, `_aplicar_valor_hud` | hud, gui |
| Arrow click accepts typing. | `OBJECT_OT_arrastar_hud._digitar` | hud, gui |
| Corner movement uses native cursor translate; native Ctrl vertex snap only other cabinets/panels, never own parts. | `_preparar_quina_nativa`, `cabinet_mover_quina_hud`, `cabinet_confirmar_quina_hud` | hud, gui |
| Typing: operator continues expression, click moves cursor, detached/mid-number unit applies to number. | `_tecla_no_texto`, `_cursor_no_x`, `_arrumar_texto_medida` | hud, gui |
| E arrow at corners. | `_redimensionar_chapa_ancorada` (axis 2) | hud |
| Multiple items: no popup; pending arrows blink, choose one per item, one value applies to all. | `_itens_da_selecao`, `_piscar_pendentes`, `_brilho_piscada` | hud, gui |

## Sidebar

| Feature | Code | Tests |
|---|---|---|
| Opens at minimum width fitting L/A/P on one row. | `cabinet_alternar_gaveta`, `_largura_inicial_gaveta` | estrutura, gui |
| Cabinets/Doors/Handles tabs. | `('aba', ...)` | gaveta, gui |
| Fixed measurement block, editable fields. | `_bloco_medidas_gaveta`, `cabinet_editar_medida_gaveta` | gaveta, portas, gui |
| Historical fixed bottom library and draggable divider. | `_paineis_gaveta`, `_divisa_gaveta` | gaveta, gui |
| Each panel scrolls independently. | `_limites_rolagem_gaveta` | gaveta, gui |
| Clipped widget hits only visible part. | `_recortar_ao_painel` | gaveta |
| Invisible-gizmo hover/glow. | `VIEW3D_GGT_cabinet_gaveta`, `VIEW3D_GT_campo_gaveta` | estrutura, gui |
| Gear options/colors/sliders/dropdowns. | `_rodape_gaveta`, `cabinet_opcoes_gaveta` | gaveta |
| Sidebar-button question stays INSIDE black box; popup only from viewport. | `_perguntar`, `_pergunta_na_gaveta`, `cabinet_responder_pergunta` | gaveta, hud, gui |
| Unavailable button gray and unclickable. | `_operador_apagado` | gaveta |
| Full layout at 190/320/482/564 widths. | `_widgets_gaveta` | snapshot |

## Preset library

| Feature | Code | Tests |
|---|---|---|
| Index and levels, including legacy format. | `_ler_indice`, `_niveis_de`, `registrar_no_indice` | biblioteca |
| Single catalog root and UUID-preserving migration. | `_garantir_catalogos`, `_migrar_raiz` | biblioteca |
| Save preset: blend/photo/index. | `cabinet_salvar_biblioteca`, `salvar_na_biblioteca` | biblioteca |
| Photo becomes asset preview. | `aplicar_preview_png`, `cabinet_regerar_previews` | biblioteca |
| Reorganize catalogs. | `cabinet_refiliar`, `refiliar_preset` | biblioteca |
| Edit/lock preset. | `cabinet_editar_modelo`, `cabinet_bloqueio` | biblioteca |
| Navigate category cascade. | `cabinet_navegar` | biblioteca |
| Insert at cursor. | `cabinet_inserir_preset`, `inserir_preset` | biblioteca |
| Photo click ->placer ->viewport click. | `cabinet_arrastar_preset` | gui |
| Historical photo double-click ->3D cursor. | `_duplo_clique_na_foto` | gaveta, gui |
| Cabinets/Materials beside title, below when narrow. | `_cabecalho_biblioteca`, `cabinet_bib_modo` | biblioteca, gui |
| MDF/MDP solid-color catalog with own cascade. | `ler_materiais`, `filhos_n1`, `cabinet_mat_n1` | biblioteca |
| Quick paint: right sphere ->rooms/No Room/All ->All/Body Only/Doors Only in black box below material; answers wrap rows. | `cabinet_pintar_modulos`, `perguntar_pintar`, `modulos_por_comodo`, `pecas_do_modulo`, `LARGURA_MIN_RESPOSTA` | biblioteca, gui |
| Sphere single click does nothing, double paints selection (cabinet panels/door leaves+frame/part), drag-release paints below or full selection when target selected; selected material highlights. | `cabinet_aplicar_material` (`alvo`), `pecas_dos_alvos`, `pecas_do_solte`, `duplo_clique_na_esfera` | biblioteca, gui |
| Shaded sphere preview without rendering. | `esfera_rgba`, `desenhar_esfera` | biblioteca |
| New/edit/delete material; Delete? below action row. | `cabinet_novo_material`, `cabinet_editar_material`, `cabinet_apagar_material` | biblioteca |

## Doors

| Feature | Code | Tests |
|---|---|---|
| Leaf calculation for swing/lift-up/sliding and hinges. | `_calcular_folhas_portas` | portas, snapshot |
| Create from opening with two clicks and snap. | `cabinet_apanhar_vao`, `cabinet_portas` | portas |
| Two-click wizard 283: opposite door bounds, automatic opening/coverage/hinge, preview matches execution, retry invalid diagonal/back retains first corner; legacy 4-point API kept. | `_cliques`, `_previa`, `_concluir`, `_coberturas_dos_cantos`, `_dobradica_da_cobertura` | portas, gui |
| Wizard leaves/opening/hinge edge (lift-up always TOP), scroll count, Y margin, lift-up piston count/automatic position, Y raises only within stroke. | `_arestas_da_porta`, `_posicoes_ferragens` | portas, gui |
| Wizard boxes/messages never clip beyond viewport. | `_botoes_assistente`, `_desenhar_assistente_2d` | gaveta, gui |
| Doors tab mirrors clickable wizard box/stages/dimensions; reanswer rebuilds from there. | `_filas_do_assistente`, `_responder_pela_gaveta`, `ALVO_ASSISTENTE` | gaveta, gui |
| Context sidebar: no selection only Create, measurement block only owner tab. | `_selecionado`, `_aba_modulos_gaveta`, `_aba_portas_gaveta`, `_aba_puxadores_gaveta` | gaveta, portas, importacao, snapshot |
| Sidebar hinges/pistons editable during creation or selected hardware across all cabinet doors. | `_secao_ferragens_gaveta`, `_editar_assistente`, `_editar_ferragens_selecionadas`, `ALVO_FERRAGENS` | gaveta, portas, gui |
| Preview real wireframe: full-overlay rig asset contour, boxes, pistons, handle along line; HUD highlight/thickness. | `_arame_dos_itens`, `_arame_ferragens`, `_arame_puxador`, `_desenhar_arame`, `tools/hardware/extract_hinge_wireframe.py` | portas, puxadores, gui |
| Alt-drag handle anchor to another edge of own group, line snap and edge-aligned orientation. | `cabinet_arrastar_puxador`, `_chapas_do_grupo_do_puxador`, `_ancora_do_puxador` | puxadores, gui |
| Switch handle model while placing or selected. | `_trocar_modelo`, `_trocar_modelo_puxador`, `ALVO_PUXADOR` | puxadores |
| Portrait carousel replaces names for handles/openings/detected hinges; factory 45-degree photos. | `_carrossel_gaveta`, `foto_padrao`, `tools/library/generate_default_photos.py` | gaveta, portas, puxadores, gui |
| Use as Handle makes external object a library model with 45-degree photo; touching panel adopts in place, loose object asks contact-face click then creator with model. | `cabinet_usar_como_puxador`, `_quadro_do_modelo`, `_chapa_encostada`, `salvar_modelo_puxador` | puxadores, gui |
| Library is handle-model source, edits update creator; factory cascade protected, click opens creator. | `modelos_do_usuario`, `_malha_modelo_usuario`, `itens_de_fabrica`, `_modelo_do_criador` | puxadores |
| Doors tab auto-scrolls to new wizard stage. | `_rolar_ate_o_fim` | gui |
| Green accept beside active count/offset/piston field; hinge detected at hovered edge; opening/hinge/counter row; opening portrait returns to choice. | `_confirmar_etapa`, `CONFIRMAR_ETAPA`, `_secao_ferragens_gaveta`, `_icone_acao_gaveta` | gaveta, portas, gui |
| All numeric fields drag right+/left-, Shift/Ctrl, Esc restore, one undo; count drag or click halves. | `aplicar_medida`, `_modal_campo`, `_aplicar_contador` | gaveta, portas, gui |
| Framed sliding:18 mm leaves cover entire front, one per user's extruded aluminum rail channel;15 mm frame side linings/back-to-front, upper rail base+header, lower base+plinth add beyond cabinet. E edits all frame pieces; Thickness/Plinth/Header fields. | `_pecas_moldura`, `_montar_moldura`, `_avanco_moldura`, `_alturas_moldura`, `_espessura_da_moldura_mudou`, `_trilhos_moldura`, `perfil_trilho_moldura`, `MARCA_MOLDURA` | portas |
| Frame counts in cabinet L/A/P/HUD envelope; target dimension subtracts frame addition from body. | `pecas_do_envelope`, `_acrescimo_da_moldura`, `redimensionar_conjunto`, `medir_conjunto` | portas |
| Framed wizard asks base; no plinth means floor, zero removes piece, viewport/sidebar same. | `OPCOES_BASE`, etapa `BASE` | portas, gui |
| Frame rail asked at creation/editable later: heavy aluminum; light routed base channels chapa_canais/user U insert,15 mm leaves, flush flange,5 mm top clearance, no header or field. | `ITENS_TRILHO`, `_trilho_leve`, `_canais_das_bases`, `_malha_com_canais`, `_gravar_canais`, `_trilhos_moldura` | portas, gui |
| Sliding click pairs on inner corner imply inset, outer-to-inner framed; half-mixed asks Inset or Framed and uses inner opening or full cabinet respectively. | `_metade_metade`, `TIPOS_CORRER`, `COBERTURA_DO_TIPO_CORRER`, `_preparar_vao_portas(forcar)` | portas |
| Selected Door categories: Door, Leaves, Position/Rails/Frame, Opening, Assembly-style titles, short complete labels. | `_titulo_secao`, `_campos_em_linhas` | portas |
| Ctrl+D panel gets own identity/no original joints; F3 Recalculate Anchoring rebuilds selected location-based joints within 5 mm. | `separar_copias`, `_separar_copias_no_timer`, `recalcular_ancoragem`, `OBJECT_OT_recalcular_ancoragem` | operadores |
| Compact Leaves counter beside final interleaf/plane gap field, drag/type, warn opening limit; no Reposition/Front/Mirror row. | `_eh_campo_contador`, `LARGURA_CAMPO_FOLHAS` | portas |
| All handle/opening/hinge portraits same square; title slider cabinet_tam_retrato updates all. | `_lado_retrato`, `_titulo_com_slider`, `_trilho_slider_gaveta` | gaveta |
| Lift-up piston actual catalog model; open length=2x closed, manual within stroke, wireframe wizard. | `_geometria_pistao`, `_pistao_do_vao`, `_pontas_pistao`, `_caixas_dos_itens_pistao` | portas |
| Hinge body/cup volumes on inner panel face. | `_caixas_dobradicas` | portas |
| No hinge overlap: margin keeps whole hinge on leaf and 60 mm center spacing; count physically limited in wizard/sidebar/Alt/legacy saved doors. | `_ajustar_dobradicas`, `_ajustar_dobradicas_wizard`, `_valor_ferragem` | portas |
| Right-hold cabinet/release vertical nonfurniture FACE highlights and attaches back to coplanar edge-connected region; snaps ends/floor/ceiling; no-drag right keeps context menu. | `cabinet_arrastar_na_parede`, `raio_ate_parede`, `regiao_da_parede`, `associar`, `posicao_no_arraste` | paredes, gui |
| Associated cabinet follows wall move/rotation; native G/R returns to plane via timer; F3 detach. | `manter_nas_paredes`, `cabinet_desassociar_parede` | paredes |
| Selected cabinet wall guides left/right/floor/ceiling: click types, drag changes. | `calcular_guias`, `aplicar_guia`, `cabinet_guia_parede`, `VIEW3D_GGT_guias_parede` | paredes, gui |
| Open-top counter cabinet has two 70 mm front/back stretchers between sides, regenerated by L/P/E, no joints. | `criar_armario(topo='TRAVESSAS')`, `adicionar_travessas`, `ajustar_travessas`, `ajustar_dependentes`, `TOPO_POR_TIPO`, `MARCA_TRAVESSA` | armarios |
| DXF layer-per-piece becomes native panel-only groups by contact; remove floor/hardware/thin plates, preserve cut meshes, save library by room/category. | `ler_dxf_promob`, `importar_dxf_promob`, `importar_promob_para_biblioteca`, `cabinet_importar_promob`, `tools/library/import_dxf_library.py` | importacao |
| Historical curved DXF front adopted deforming accessory eh_peca_curva; curved shelf panel, not microwave/basket; thin floor removed even with outside cabinets; folder=tab, file=category, tab prefix outside Inferiores. | `_eh_peca_curva`, `FACES_PRINCIPAIS_MINIMO`, `_eh_piso`, `categoria_promob`, `CATEGORIAS_PROMOB` | importacao |
| Historical Cabinets Shape P1/P2/Radius/diagonal angle, corner front fixed/P1 moves; fields drag/type. | `_secao_forma_gaveta`, `aplicar_medida('forma')`, `forma_angulo_*`, `aplicar(('ANG', k))` | formas |
| DXF native integration: color 7 panels, hardware/aluminum/handles never wood; hinged fronts native leaf/side/full-half hinge, pairs double/top lift-up; boxes/baskets native proportional/curved drawers; aluminum frame sliding; thin backs/top stretchers dependent; E is most common body thickness. | `cores_dxf_promob`, `promob.planejar`, `vao_atras`, `promob.aplicar`, `marcar_dependentes`, `_espessura_de` | importacao |
| Sliding aluminum frame 23x10 around 5 mm panel 6 mm from front, two materials; switch back to panel in Doors. | `ITENS_FOLHA_CORRER`, `_vestir_folha`, `_chapas._malha_quadro`, `porta_folha` | portas |
| Curved concentric drawer fronts, sagitta field; imported height proportions reset when count changes. | `frente_curva_mm`, `_chapas._malha_arco`, `proporcoes`, `frentes` | gavetas |
| Panel area=volume/E and edge; F3 Calculate Areas, angle detector removed 309. | `medidas_da_chapa`, `areas`, `cabinet_calcular_areas` | geometria |
| Actual drawer front/box sides/inner front/back/bottom/rails: telescopic 12.7 mm per side, concealed 5, longest catalog length fitting; overlay/inset/front-inter gaps/setback. Cabinet resize carries nearest base/top block without changing chosen size/opening/handle/material; children not separate cabinet-selection targets. | `calcular`, `criar_gavetas`, `montar`, `editar`, `atualizar_gavetas_do_conjunto`, `acompanhar_redimensionamento` | gavetas |
| Historical drawer two-diagonal-click/count-scroll/Alt depth/rail wizard; group/unit fields and handle, only selected drawers HUD, L/A/P fixed-corner both directions, Esc restores after rename/move/resize, actual parent beats old name, selection survives rebuilt parts. Front slider/three Alt points. | `cabinet_criar_gavetas`, `_aba_gavetas_gaveta`, `selecionar`, `linhas_hud`, `cabinet_abrir_gaveta`, `VIEW3D_GGT_slider_gaveta`, `cabinet_arrastar_ponto_gaveta` | gavetas, gui |
| Shelves in cabinet opening, fixed margins/support following, E/setback/side clearance. Historical Equal/Free gaps, one gap moves one shelf, top residual, Between all; reuse same panels, invalid restores, estimate count, depth stops at back. | `calcular`, `vaos`, `mover_vao`, `criar_prateleiras`, `montar`, `editar`, `atualizar_do_conjunto`, `profundidade_ate_o_fundo`, `quantas_no_modulo` | prateleiras |
| DXF L backs per-plane shape/margins, no corner crossing, resize/setback/remove; touching partitions follow base/top. Hinged curved leaf retains mesh/sagitta/native opening/tangent handle/reanchor; measured planes/gaps/category profiles. | `fundos_do_modulo`, `guardar_formato_fundo`, `_ajustar_fundo_por_formato`, `reencaixar_verticais`, `_portas_curvas_referenciadas`, `adotar_contorno_modelado`, `tools/migrations/refine_corners.py` | armarios, importacao |
| Historical shelf AssistenteDoVao two clicks+scroll, depth to back/front Setback; count/Panel/Equal-Free/Between/gaps 1..n+1 or Below-Above for one. Click all/double one, HUD opening L/A/P and each gap value, drag/type/Esc restore. | `cabinet_criar_prateleiras`, `_aba_prateleiras_gaveta`, `selecionar`, `linhas_hud`, `aplicar`, `copia`/`restaurar` | prateleiras, gui |
| Drawer/shelf points native snap, no Python evaluated-vertex projection; second click recovers cabinet from state; confirm/Esc/error restores cursor/locks/drawing/timer, modal mixin releases references. | `cabinet_marcar_ponto_vao`, `cabinet_confirmar_ponto_vao`, `_aceitar_canto`, `_terminar_snap_criacao`, `_larga_dados_ao_terminar` | gavetas, gui_interacao |
| Unlimited library niveis, n1/n2/n3 first three, complete catalog path, one carousel per level, no counts/empty branches; DXF Armarios>room>tab>category. | `caminho_de`, `filhos_de`, `itens_em`, `trilha_da_cena`, `registrar_no_indice`, `cabinet_navegar`, `chapa_n_mais` | biblioteca |
| Diagonal tip sharp to triangular-cabinet corner, or stops at panel thickness; thickness segment outline only, angle uses following side; small fixed-screen arc<=quarter side. | `PONTA_AFIADA_MM`, `ESPESSURA_PONTA_MM`, `_arcos_da_diagonal`, `_mm_por_pixel` (arco pequeno: raio fixo na tela, <= 1/4 do lado) | formas |
| Whole-side diagonal becomes chamfer; editable internal angle at both ends. | `_feicao`, `_arcos_da_diagonal`, `_angulo_da_ponta`, `_eh_angulo`, `aplicar(('ANG', k))` | formas |
| Historical L/diagonal plan P1/P2, diagonal R/right-sloped angles; modeled curves stay blocking, cached real segments, no circular inference/radial deformation; L/A/P/Tab retained. | `forma_do_modulo`, `segmentos`, `aplicar`, `_linhas_da_forma`, `estrutura_hud`, `_mover_perna`, `_esticar_total` | formas |
| Cabinet back 5 mm, groove 15 mm from rear, insertion 7; follows L/A/P/E, not adjacency; F3 setback/thickness/remove. | `ajustar_fundo`, `adicionar_fundo`, `cabinet_fundo_modulo`, `MARCA_FUNDO` | armarios |
| Historical 39 native cabinet presets with full-overlay doors, one leaf<=500 mm/two above; profile top lower cabinets, bottom uppers, horizontal near 1 m towers, vertical opening side wardrobes. Headless photo ajar, default Profile. | `criar_armario`, `porta_no_modulo`, `perfis_na_porta`, `PERFIL_POR_TIPO`, `ARMARIOS_NATIVOS`, `gerar_armario_nativo`, `fotografar_com_camera`, `tools/library/generate_native_cabinets.py` | armarios, biblioteca |
| Double isolates white-outlined leaf/native outline off; sliding rail click hardware wireframe. | `_folhas_com_contorno`, `TIPOS_SELECAO_FERRAGEM` | gui |
| Selected door: white leaves, yellow opening, two-click diagonal, no hinges; Alt drags two gesture corners (four before 309), rebuilds using clicked panel/native snap. | `_desenho_da_porta`, `_cantos_da_porta`, `cabinet_arrastar_canto_porta` (snap nativo: `cabinet_mover_canto_porta`), `cabinet_cantos_porta` | portas, gui |
| User full-overlay hinge model/rig from extract_hinge.py, one native copy per hinge, drivers/IK/shared mesh, cup-measured Boolean, measured rig motion/controller rotates copy, minimum model clearance; without asset box/fixed-axis fallback. | `_instanciar_rig`, `_passo_rig`, `_movimento_rig`, `_furar_folhas`, `_girar_rigs`, `_afastamento_porta` | portas |
| Full-overlay plate/spacer sit on side inner face; coverage adjustment moves only them, cup/door fixed, same preview. | `_calco_rig`, `FACE_PECAS_CALCO`, `MALHAS_CALCO` | portas |
| Phase 3 actual hardware: body on cabinet/cup on leaf, piston Damped Track and actual diameters/supports, sliding rails; historical Blender selection excluded, delete/duplicate checks. | `_ferragens_da_porta`, `_montar_ferragens`, `_conferir_ferragens` | portas, hud |
| Hardware click all type/Shift add, double native part/Tab; only wireframe selected. Alt hinge-edge mirrored margin or piston-side stroke-limited controller. | `_selecionar_ferragem`, `_selecionar_peca`, `_ferragens_em_edicao`, `_caixas_ferragens`, `_controles_ferragens`, `_valor_do_controle`, `cabinet_arrastar_ferragem` | portas |
| Per-leaf swing rear hinge corner (front for inset), lift-up/sliding, no open gap to cabinet, resize persists; closed-base slider, right opens, native undo. | `_matriz_abertura`, `_definir_abertura`, `cabinet_abrir_porta` | portas, gui |
| Profile uses user's aluminum asset/material/UV, load once; ends/back move intact, only straight segment stretches, no chamfer deformation. | `_dados_perfil`, `_malha_modelo_perfil`, `_malha_perfil_do_modelo`, `_corte_do_perfil`, `_deformar_perfil`, `_altura_perfil_mm` | puxadores, snapshot |
| Historical Portuguese object names without underscores for leaves/handles/hardware/rig; old rig copies replaced by current asset. Existing saved names remain data contracts. | `_padronizar_nome`, `NOMES_FERRAGEM`, `_anexar_sem_repetir` | portas |
| Sliding one independent plane/rail per leaf/full-opening travel, single leaf half opening, editable leaf L resets on count/opening change and never exceeds opening, no overlap field. Upper deep U/lift clearance, lower standing guide per leaf, travel slider, no perimeter-gap field; outside coverage becomes framed. | `_correr_sobreposta`, `_largura_folha_correr`, `_plano_correr`, `_curso_correr`, `_trilhos_correr`, `altura_trilho_baixo`, `_inicios_porta`, `CHAVE_LARGURA_CORRER`, `_curso_do_slider` | portas, gaveta |
| Every standard full/half/inset/sliding coverage leaves 2 mm, never flush. | `_cobertura_mm`, `RESPIRO_PORTA_MM` | portas, snapshot |
| Native EDGE_MIDPOINT produces half thickness minus 2 mm, tracks cabinet. | `_iniciar_snap_nativo`, `_meias_do_vao`, `_inicios_porta` | portas |
| Linked door follows cabinet. | `atualizar_portas_do_conjunto` | portas, snapshot |
| Door in cabinet/world, F3 only, intertab chains retired. | `cabinet_corrente_porta` | portas, importacao |
| Active item HUD line thicker in multiselection. | `_principal_hud`, `_espessura_principal_hud` | hud |
| Edit placed door parameter. | `_editar_parametro_porta` | portas, gaveta |
| Define front by click. | `cabinet_definir_frente` | importacao, gui |
| Convert to door/double door/link. | `cabinet_folha_de_objetos`, `cabinet_porta_dupla`, `cabinet_vincular_porta` | importacao |

## Import and handles

| Feature | Code | Tests |
|---|---|---|
| Classify panel versus accessory. | `_analisar_peca`, `cabinet_converter_modulo` | importacao |
| Convert handle/link leaf. | `cabinet_converter_puxador`, `cabinet_vincular_puxador` | operadores |
| Imported handles with L/A/P locks. | `_ajustar_puxadores` | importacao |
| Parametric profile/bar/edge handles. | `criar_puxador`, `posicionar_puxador` | puxadores, snapshot |
| Legacy curved-leaf profile 305: straight X edge from full front line or ray 1 mm inside tip. standardize_profile_handles.py makes all profiles, same bar edge, missing doors import rule/curves side, NONE drawers->profile. | `test_perfil_na_borda_reta_da_folha_curva_senta_na_madeira`, `test_perfil_na_folha_curva_sem_linha_senta_na_madeira`, `_lugar_do_puxador` | importacao |
| Reversed curved front 307: Define Front flips reference without moving wood, swaps side/coverage, opens outward; curved handle finds own end vertices. repair_reversed_curved_doors.py puts hinge actual inside face and 15 mm support at door height where end follows side. | `_virar_porta_modelada`, `test_virar_frente_da_porta_curva_nao_mexe_na_madeira`, `posicionar_puxador` | importacao |
| Profiles 308 horizontal except wardrobes; posicao_do_perfil tall/tower ALTURA chooses upper/lower edge closest 1 m per leaf, Quartos>Armarios LADO. Loose door height treated top; standardize_profile_handles.py gives curved front references. | `perfis_na_porta`, `ALTURA_MAO_MM`, `test_perfil_sempre_horizontal_salvo_guarda_roupa` | armarios, puxadores |
| Line placement tool plus snaps. | `cabinet_posicionar_puxador`, `_snaps` | puxadores |

## Registration

| Feature | Code | Tests |
|---|---|---|
| All registered classes in CLASSES; unregister clears everything. | `register`/`unregister` | estrutura, operadores |
| Every class covered by meaningful test. | coverage guard | cobertura |

## Historically accepted coverage exceptions (`SEM_TESTE_ACEITO`)

The version126 inventory accepted the following limits: enabled-only add-on preferences; opening Explorer; Asset Browser/Shelf requiring native areas and dragging; library registration that changes user preferences; legacy panel operators `modo_medidas` and `definir_tamanho`. GPU drawing then required GUI inspection, without image comparison. These historical exceptions do not claim that later coverage is absent.


| Alt drawer/door-corner/joint-anchor and door-wizard performance: native cursor/snap, no Python vertex read/projection, own pieces excluded. | `iniciar_cursor_nativo`, `acompanhar_cursor_nativo`, `_iniciar_snap_nativo` | gavetas, portas, hud, gui |

| Native drawer-anchor cursor translate excludes own pieces/hardware temporarily; confirm/Esc restores cursor/overlay/targets, one undo-redo. | `OBJECT_OT_mover_ancora_gaveta`, `OBJECT_OT_confirmar_ancora_gaveta` | gavetas, gui_interacao |

| Drawer handle click isolates accessory/Handles tab, Shift adds, rails select drawers, individual model/settings survive resize. | `_selecionar_puxador`, `_trocar_modelo_puxador`, `montar` | gavetas, gui_interacao |

| Library strip above menu/viewport, horizontal categories/photos, collapse/expand, reconnect/migrate areas, preset target/tooltips, bounded cache/reused index. | `biblioteca_faixa`, `OBJECT_OT_recolher_biblioteca` | biblioteca_faixa, gui_biblioteca_faixa, gui_interacao |
| Compact 18 px category tabs, no under-module buttons; right-release photo/name Insert/Edit/Lock, recheck protection, models use creator. | `abrir_menu_item`, `OBJECT_OT_acao_item_biblioteca` | biblioteca_faixa, gui_biblioteca_faixa |
| Category/photo arrows overflow-only toward hidden items; resize recovers width/reveals all even stale offset. | `biblioteca_faixa._linha`, `biblioteca_faixa.widgets` | biblioteca_faixa, gui_biblioteca_faixa |
| Historical strip<160 px puts subcategories side by side with per-level gap/divider, independent X/Y scroll, photos accessible. | `_subcategorias_em_linha`, `biblioteca_faixa.widgets` | biblioteca_faixa, gui_biblioteca_faixa |
| DXF fits base/top inset<=3.1 mm to outer corner; keep E/modeled Mesh/UID/larger internal opening/systems, idempotent/rotated cabinet. | `promob.ajustar_encaixes`, `importar_dxf_promob` | importacao |
| DXF real-face L/diagonal/perpendicular doors: plate+arm one hinge, asymmetric leaf heights, double articulates outward, short near-top side not lift-up, unsupported/cyclic joint uses outer side. References survive resize/index reorder until manual edit; articulated support uses touching native plate, hardware separate by group. | `_referencias_dobradicas`, `_portas_referenciadas`, `gravar_vao_orientado`, `_vao_orientado`, `_gravar_assinaturas_vao`, `_dobradicas_da_porta`, `vincular_folha_de_apoio`, `_matriz_fechada`, `_ferragens_portas` | importacao |
## Zigzag doors and integration (231 onward)

- Opening/orientation 239: ray and bounds captured at definition, unequal setbacks use innermost front, depth snap projects only along depth/stops at back without changing L/A/orientation; native translate matrix transposed. Drawer and shelf regressions. References: `test_assistente_deduz_frente_lateral_e_a_preserva_ao_editar`, `test_assistente_deduz_face_oposta_e_modulo_girado`, `test_assistente_gap_usa_frente_interna_e_profundidade_mais_curta`, `test_assistente_frente_diagonal_nao_usa_caixa_inflada_do_modulo`, `test_assistente_previa_nao_reconsulta_malhas_nem_raios`, `test_ancora_de_profundidade_lateral_projeta_so_no_eixo_e_para_no_fundo`, `test_translate_nativo_usa_eixo_real_da_ancora_girada`, `test_prateleiras_do_assistente_conservam_referencia_da_face_lateral`.

- Real left opening 238: every plate has actual support, heights/materials/leaves/handles retained, coplanar chains reversed, corner articulations preserved; external migration with backup/reread. References: `test_padrao_esquerdo_preserva_alturas_material_uid_e_puxador`, `test_padrao_esquerdo_nao_cria_dobradica_sem_lateral_de_apoio`, `test_promob_cadeia_da_direita_inverte_apoio_para_esquerda`, `tools/migrations/adjust_left_opening.py`.

- Thumbnails 237: disposable left-open copy leaves preset original, crease outlines exclude triangulation, restore color/render/temporaries; photo migration rereads assembly and backs up before publication. References: `test_foto_da_porta_direita_abre_copia_a_esquerda_e_preset_fica_original`, `test_contorno_da_foto_ignora_diagonais_de_triangulacao`, `test_foto_com_linhas_restaura_cor_render_e_nao_deixa_objetos`, `tools/migrations/refresh_library_photos.py`.

- Backs/islands 236: rotated setback preserves E/material/UID, partial back never tower rectangle, shelves/rails refit, single-front island native back, perpendicular corner fronts preserved, source flush back imports recessed without shelf penetration; backup/reread migration. References: `test_promob_recuo_preserva_fundo_girado_espessura_material_e_uid`, `test_promob_fundo_parcial_recuado_nao_vira_fundo_da_torre`, `test_promob_fundo_recuado_reencaixa_prateleiras_e_trilhos`, `test_promob_ilha_duas_frentes_fica_com_porta_e_fundo_nativos`, `test_promob_frentes_perpendiculares_de_canto_sao_preservadas`, `test_promob_fundo_rente_na_fonte_importa_recuado_sem_atravessar_prateleira`, `tools/migrations/adjust_backs_and_doors.py`.

- Zigzag:3/4/8 leaves, left/right, coaxial joints closed/half/open. References: `test_zigzag_espelha_a_cadeia_e_mantem_eixos_coincidentes`.
- Zigzag: create/open/change count-side retains terminal handle and single slider. References: `test_zigzag_puxador_ultima_folha_abertura_e_edicao`.
- Zigzag: user carcass rig, native joint volumes, meshes unchanged when opening. References: `test_zigzag_volumes_presos_as_duas_folhas`.
- Wizard offers three-leaf zigzag during creation. References: `test_assistente_oferece_zigzag_tres_folhas`.
- Historical corner photo pose: one fully open, other half. References: `test_foto_de_canto_abre_uma_inteira_e_a_outra_metade`.
- Oblique fit 232:135-degree hinge whole face contacts without penetration, angular arm follows cup without rebuild, prism/wire retain actual plane, old preset update preserves door/handle/opening. References: `test_dobradica_de_135_encosta_com_a_face_inteira_sem_penetrar`, `test_braco_angular_segue_o_copo_sem_refazer_malhas`, `test_prisma_angular_e_arame_preservam_o_plano_real`, `test_atualiza_preset_antigo_sem_alterar_porta_puxador_ou_abertura`.
- Integration 233: actual-side drawers native selection/open/edit, whole sides never drawers/metals reference only, tall narrow fronts/two box levels, shelves retain UID/material/shape/functions/cuts. Legacy assembly survives reinsertion. Audit expected/before/after, selection/sliders/open/edit/restore, world geometry/UID/material/catalogs before backed-up publication. References: `test_promob_gavetas_na_face_lateral_tem_selecao_abertura_e_edicao`, `test_promob_lateral_inteira_nao_vira_gaveta_e_metais_so_referenciam`, `test_promob_frente_alta_estreita_com_caixas_em_dois_niveis`, `test_promob_prateleiras_adotam_uid_material_forma_e_funcoes`, `test_promob_prateleira_recortada_preserva_malha_material_e_edicao`, `test_sistemas_em_montagem_antiga_sobrevivem_a_reinsercao`, `tools/migrations/audit_and_repair_integration.py`.

| Reversible resize 242:550->100->550, native reference/topology, drawer/free-gap refit, rail limits/Esc/rotation/append/HUD no duplicate work. | `test_shapes_blender.py`, `test_drawers_blender.py`, `test_shelves_blender.py`, `test_operators_blender.py`, `test_library_blender.py`, `test_hud_blender.py` |

| Corners 243: door follows inner opening not envelope/anchor; drawer front width/rotation, Esc restores reference; photos close all opening types without changing side. | `test_shapes_blender.py`, `test_doors_blender.py` |

| Blind corner 244: preserve 40x15 strip/49.9998 mm trim, native cabinet hinge not fixed-panel articulation,2 mm gap, reversible open-close. | `test_canto_cego_preserva_ripas_e_arremate_com_dobradica_de_movel` (importacao) |

| Partial door 245: native interpolated strip/side face, width reduction-return, midface reference, staged L corner, full-overlay cup inside leaf. | `test_porta_parcial_segue_ripa_e_lateral_ao_reduzir_largura`, `test_ancora_da_porta_no_meio_da_face_usa_interpolacao_nativa`, `test_dobradica_reta_real_na_porta_parcial_cabe_na_folha`, `test_canto_real_reduz_largura_em_etapas_sem_perder_referencia` (importacao) |

| Libraries/selection 246: BVH contact does not join empty L, room destinations, standalone doors, perpendicular front handle, native group Tab/unique meshes. | importacao, puxadores, operadores (`cabinet_editar_grupo`) |
| Shelves 247: global Tab propagates in SAME Mesh/isolates other cabinets, individual preserves neighbors, undo restores native scope. Per-unit settings, quantity inherits geometry/settings/material/modifiers, real thickness gap split. Mixed types ask reference viewport, validate clicked group, Esc cancels; drag number-only preview. Individual depth reduces/returns with cabinet. | `iniciar_edicao`, `concluir_edicao`, `editar_individual`, `cabinet_referencia_prateleira`, `resolver_referencia` | prateleiras |

| Reference prompt 248 follows pointer in active viewport/window coordinates, switches viewport, hides over menu/outside; wizard message clamps edges. | `atualizar_aviso_referencia`, `_desenhar_assistente_2d` | prateleiras |

| Mirror 249 group/leaf: swing/double/zigzag wood fixed closed/last handle, lift-up pistons, sliding reversed travel; twice restores, sidebar/context icon, leaf refs survive E/resize. | `cabinet_espelhar_porta`, `espelhar_porta`, `menu_contexto_porta` | portas |
| Connections 249: positive-area cabinet support, clean endpoints also UID, migration keeps manual anchors/geometry, nearby controls grouped without link loss, export-inset vertical trim reaches corners, internal partitions retained. | `otimizar_adjacencia`, `_correntes_sem_repeticao`, `alinhar_arremates`, `tools/migrations/refine_library_connections_v249.py` | hud, armarios |
| Diagonal/Tab 250: line/arcs/angle on actual horizontal edge/thickness ends; native Edit Mode keeps Empties, exit restores active/selection/invalidates plan; mode selector, multiple groups, later selection, undo retained. | `pontas_diagonal`, `angulo_diagonal`, `concluir_edicao_grupo`, `recuperar_edicao_grupo` | formas, operadores |

| Diagonals 251: profile follows actual top, outward normal/supported side/base contact, unrecognized plate fronts become doors, handle/Alt each segment; resize preserves edited vertices/faces/closed center/opening. | `alinhar_frente_ao_corpo`, `integrar_frentes_diagonais`, `_reancorar_perfil_modelado`, `_bordas_da_face`, `_lugar_no_perfil`, `tools/migrations/refine_diagonal_fronts_v251.py` | importacao, formas, portas, puxadores |
| Diagonals 252: profile/opening contour without chord, segmented Y+ preview matches handle, both skin ends clear real sides/tops; Sup Alto 02 and 32-preset BVH audit. | `_contorno_da_folha`, `_limitar_pontas_frente`, `_lugar_do_puxador`, `tools/migrations/refine_diagonal_clearance_v252.py` | importacao |
| Fronts 253: shared local semantic FACE/EDGE for curves/facets/frames, actual normal/topology/cuts, numeric redraw-hover, Mesh/undo/rename invalidation, wood vs mounting edge, once-only migration/OBJECT painting, profile follows edge, prepare before capture/deform including open native append. | `frentes.py`, `FRONTES.md`, `test_fronts_blender.py`, `test_diagonal_quarto_append_sem_cache_resize_preserva_apoios_e_geometria`, `test_previa_em_movimento_reutiliza_geometria_preparada`, `test_material_do_objeto_sobrevive_migracao_e_redimensionamento` | frentes, portas, puxadores, importacao |

| Cabinet outline 254: actual per-leaf geometry, no aggregated box for curved/faceted fronts; shared drawing/isolated reference. | `hud.py`, `test_hud_blender.py` | hud |

| Shape/angle 255: internal angle from two native edges, orthogonal endpoints/roundtrip; back follows support/normal setback; Tab reorients flat panel preserving world/UV/material/children/unrounded E. | `formas.py`, `chapas/`, `hud.py`, `test_shapes_blender.py` | formas, hud, operadores, importacao |

| Vertical tilt 256: shared XY/XZ/YZ solver, actual angle/diagonal length, back/E/UV/material preserved; rotated roundtrip, Tab invalidation, Esc restore, individual shared-Mesh isolation, profile-clipped dimensions/native reference survives duplicate-name append. | `test_shapes_blender.py` | formas, hud |

| Free contour 257: native group/Tab/G/Tab oblique corner/strips, CDT union preserves concavity/islands/holes/overlap; on-wood rotated lines, numeric redraw, no Mesh/BMesh/CDT, Mesh/UV/material/fields/arrows/drag/Esc kept. | `test_shapes_blender.py` | formas, hud, operadores |
| Actual profiles 259: compound tilts/staggered shelves never invent curve/diagonal; rounded raised-base blocking uses cached native segments/keeps IDs/poses. | `test_inclinacao_composta_nao_inventa_curva_nem_diagonal_sem_apoio`, `test_curva_com_base_elevada_usa_arestas_nativas_sem_arco_aproximado` | formas, hud |
| Contour/resize 259: rounded profile never imaginary diagonal, coplanar inverted-normal diagonals removed, profile disappearing at limit retains channel/XY reference for field roundtrip. | `test_perfil_arredondado_nao_inventa_diagonal_entre_pontas`, `test_contorno_ignora_diagonais_coplanares_com_normais_invertidas`, `test_resize_pelo_campo_recupera_referencia_se_perfil_some_no_limite` | formas, modulos, hud |
| Twisted front 258: native tessellation avoids own-face raycast, migration recovers truncated labels/cache, open reanchor keeps Mesh/topology/UV/material/modifier/cups behind wood. | `test_curva_torcida_reconhece_superficies_inteiras`, `test_curva_recupera_cache_antigo_truncado_sem_recriar_mesh`, `test_reancorar_curva_torcida_aberta_preserva_madeira_e_dados` | frentes, portas |
| Profile scope 259: chamfers validate all panels/independent corners. | `test_perfil_reto_valida_todos_os_cantos_da_caixa` | formas |
| No curvature system 259: modeled curves straight-segment blocking, no circular inference/radial deformation, legacy R no geometry change, no radius menu, L/A/P/Tab kept. | `test_contorno_curvo_modelado_nao_cria_parametro_radial`, `test_comando_radial_antigo_nao_deforma_blocagem`, `test_rotulos_da_forma_aparecem` | formas, hud |

| Blocking/joint 260:8 corners from 2 sides/12 dimensions, curved front rectangular envelope since 262, no facets/leaves/internal shelves; asymmetric sides offer INNER angle.3D rotation/XZ/YZ/tilted sides/roundtrip/actual E/UV/same Mesh/support cuts/cache-only redraw. | `blocagem_do_modulo`, `dados_junta`, `aplicar_angulo_junta`, `_deformar_chapa_com_secao`, `_linhas_da_blocagem`, `test_blocagem_assimetrica_e_corda_reta_sem_segmentos_da_madeira`, `test_angulo_da_blocagem_preserva_secao_contato_uv_mesh_e_retorno`, `test_junta_em_lateral_inclinada_preserva_espessura_e_angulo_exato`, `test_blocagem_curva_retangular_sem_diagonal_falsa_nem_mudar_madeira` | formas, hud |

| Compound tilt 261: XY/XZ/YZ one 3D body/12 dimensions, no phantom extrusions, spatial-vector arcs/values meet wood under rotation/sloped base. Angle intersects support spatial line, preserves section/roundtrip. Cached native hull validates without closing L, no redraw Mesh/hull. | `blocagem_cobre_estrutura`, `_delta_da_junta`, `test_inclinacoes_multiplas_desenham_um_corpo_3d_e_arcos_nas_arestas`, `test_juntas_com_inclinacao_composta_editam_o_angulo_real_sem_mudar_secao`, `test_inclinacoes_compostas_cacheiam_o_corpo_e_preservam_topologia_em_l` | formas, hud |

| Structural reference 262: curves local rectangle per principal plane, no fake angle/arc; real contour ignores triangulation/subdivided lines/doors/small trim. Vertical tilt still editable/E preserved, Tab/restore invalidates. | `planos_curvos`, `contorno_tem_curva`, `test_blocagem_curva_retangular_sem_diagonal_falsa_nem_mudar_madeira`, `test_gatilho_curvo_ignora_subdivisoes_quina_l_e_arremate_pequeno`, `test_frente_curva_nao_apaga_inclinacao_vertical_real`, `test_curvatura_da_porta_isolada_nao_muda_referencia_da_carcaca`, `test_prateleira_curva_direta_no_modulo_nao_troca_o_tipo_da_caixa`, `test_classificacao_curva_cacheia_e_invalida_apos_tab_e_restauracao` | formas, frentes, hud |

| Simplified scope 263 supersedes 259-262 group controls: every cabinet 8-corner/12-edge L/A/P box, no shape/P1/P2/R/angle menu/HUD; BOX resize no angular solver, old events refused. Angle individual panel only, neighbors/Mesh isolation preserved; old group solver tests compatibility API only. | `test_inclinacoes_multiplas_usam_caixa_sem_angulo_no_modulo`, `test_menu_modulo_nao_oferece_formato_nem_aceita_evento_angular_antigo`, `test_hud_do_l_so_oferece_caixa_e_redimensionamento_convencional`, `test_angulo_so_aparece_com_selecao_individual_da_chapa`, `test_evento_hud_antigo_nao_edita_angulo_do_modulo`, `test_diagonal_inteira_so_mostra_angulos_na_chapa_individual` | formas, hud, gaveta, modulos |

| Chamfer/Tab undo 264: manual absorption never regenerates Mesh, keeps world/topology/UV/material/ID, timer blocked during undo, completion defers references/clears old transition, shared Mesh.is_editmode protects all users. Native chamfer+move+Tab+4 undo cycles/native copy, contracts reject 263 implementation. | `test_absorver_chanfro_modelado_nao_reconstroi_malha_do_undo`, `test_timer_nao_consulta_cena_enquanto_undo_esta_restaurando`, `test_fecho_do_undo_nao_escreve_malhas_e_descarta_transicao_antiga`, `test_chanfrar_mover_tab_undo_redo_conserva_topologia_e_copia_nativa`, `test_instancia_nao_altera_mesh_que_outra_instancia_esta_editando`, `test_instancia_fora_do_edit_mode_nao_escreve_mesh_em_edicao` | operadores, frentes |
| Neutral dimensions/physical E265: A1/A2 etc without renaming saved props; fold/chamfer corresponding skins, nominal E if ambiguous, resize preserves midline; E cached real edges, no redraw extraction. | `test_cotas_numeradas_preservam_alvos_e_edicao_dos_eixos`, `test_chapa_dobrada_oferece_E_nas_arestas_reais_sem_medir_no_redraw`, `test_medidas_exibem_A1_A2_A3_sem_renomear_props_salvas`, `test_dobra_chanfrada_mede_pele_e_resize_preserva_linha_media`, `test_secao_ambigua_nao_inventa_espessura_pelo_envelope` | hud, gaveta, operadores |
| Dynamic menu dimensions 266: A1..An/E same semantic targets/values/highlight as HUD; transverse midline offset>E gets own A6. Edit keeps wood/Mesh, drag original backup, Esc geometry/cache, native undo; cabinet conventional blocking. | `test_deslocamento_transversal_ganha_A6_com_E_independente`, `test_todas_as_cotas_da_viewport_sao_editaveis_pelo_menu`, `test_escape_do_campo_deslocamento_restaura_malha_e_cache`, `test_realce_do_menu_acende_a_mesma_cota_na_viewport`, `test_edicao_de_A6_pelo_operador_aceita_undo_redo_nativo`, `test_menu_chapa_chanfrada_exibe_cotas_da_viewport_com_campos_proprios` | hud, gaveta |
| Multiple chamfers 266: independent A fields per diagonal corner, same front/back edge shares one dimension. | `test_dois_chanfros_tem_cotas_independentes_no_menu` | hud |

| Actual spatial contour 267: twisted/chamfered sides both 3D skins, no floating flat box/triangulation. Semantic fields measure spatial length, edit one pair, keep Mesh/UV/E/undo; angle exact 90, Esc restore, pixel-limited arc, offset near low edge, numeric redraw. | `test_chapa_quadrada_torcida_nao_usa_caixa_plana`, `test_chanfro_com_desvio_usa_as_duas_peles_reais`, `test_triangulacao_interna_nao_cria_cota_ou_diagonal`, `test_contorno_3D_nao_consulta_mesh_ou_forma_no_redraw`, `test_editar_aresta_3D_move_so_um_par_e_preserva_ID_E_UV`, `test_angulo_3D_aceita_90_exatos_sem_mudar_E_ou_Mesh`, `test_aresta_real_editada_pelo_menu_aceita_undo_redo`, `test_guia_de_deslocamento_fica_na_borda_baixa_sem_exceder_envelope`, `test_arco_3D_converte_mm_em_metros_e_fica_colado_na_quina`, `test_cancelar_angulo_3D_restaura_contorno_cotas_e_mesma_Mesh` | hud |

| Native joints 268: actual MeshVertex points on twisted/chamfered panels, shared cursor VERTEX snap/native KDTree outside draw; restore cursor/selectability. Anchor preserves form/position, per-pair gap not closed 269, distinct constraints keep E/Mesh/references/undo. | `test_selecao_de_solda_usa_todos_os_vertices_nativos_sem_caixa`, `test_snap_de_solda_reutiliza_translate_nativo_sem_projecao_de_vertices`, `test_snap_compartilhado_da_solda_devolve_cursor_e_alvos_ao_confirmar`, `test_fim_da_escolha_resolve_destino_na_malha_real`, `test_juntar_chapa_torcida_preserva_forma_e_cadastra_afastamento`, `test_juntar_varias_ancoras_reais_chega_a_zero_sem_media`, `test_ancoras_incompativeis_nao_deformam_espessura`, `test_parceiro_de_espessura_nao_depende_do_sinal_do_Z`, `test_solda_automatica_tambem_aponta_vertices_reais_da_chapa_torcida`, `test_undo_redo_de_juntar_preserva_vertices_e_ancora` | hud |
| Native joint flow 268: Enter finishes after pair, not swallowed by next snap; release starts next pair. Joining two loose parts keeps manual anchors, automatic detection never erases them. | `test_escolha_de_solda_pausa_apos_par_para_concluir_com_enter`, `test_juntar_duas_soltas_conserva_ancoras_ao_criar_modulo` | hud |

| Anchor origin 269: register 3D gap without movement, Reset restores both sides/multiple pairs without averaging, frame follows cabinet rotation, cleanup/undo retains origins. | `test_gap_cadastrado_nao_move_nem_acende_reset`, `test_reset_restaura_gap_3D_sem_mudar_forma_E_Mesh_ou_alvo`, `test_reset_do_destino_tambem_restaura_gap_cadastrado`, `test_gap_acompanha_rotacao_e_translacao_do_modulo`, `test_origens_da_ancora_saem_ao_desligar_ou_substituir_junta`, `test_reset_de_gaps_distintos_recupera_vertices_sem_media`, `test_undo_redo_do_reset_preserva_origem_cadastrada` | hud |

| Selection-based chain 270: Alt/gizmo detach active panel even target side; group chooses displaced part. HUD/menu/shelf opening exclude detached piece in 3-axis resize, undo keeps parent/envelope. | `test_alt_corrente_desvincula_lateral_ativa_e_nao_a_base`, `test_gizmo_corrente_desvincula_o_mesmo_alvo_que_a_regua`, `test_corrente_no_grupo_remove_a_lateral_afastada_mesmo_sendo_destino`, `test_hud_e_menu_redimensionam_so_o_modulo_apos_desvincular`, `test_undo_redo_da_corrente_conserva_o_escopo_real_do_modulo` | hud |

| Rejoin legacy 271: recover exclusive Collection marker or create own without taking unrelated items, same room normalization, prepare before membership, accept prior failed partial parenting; preserve gap/shape/undo. | `test_soldar_novamente_reconhece_colecao_importada_sem_marca`, `test_nova_solda_recupera_parentesco_parcial_de_tentativa_que_falhou`, `test_solda_sem_colecao_propria_cria_montagem_sem_tomar_itens_alheios`, `test_soldar_modulo_antigo_na_raiz_cria_colecao_propria`, `test_undo_redo_de_nova_solda_restaura_marca_colecao_e_parentesco` | hud, orcamento |

| Maintenance 272:12 read-only help CLIs, external real-path/Windows-case preparation, hashes before writes, backup/copy-failure rollback, temporary tests only. | `TestMigracoes` in `test_migrations_blender.py` | migracoes |
| Shelves 273/274: native delete updates count/gaps without moving/recreating survivors, remaps choices/fits, zero never resurrects. Spacing 37 px Center Spacing symbol and E1..En+1 for group/unit, no Equal-Free/Below-Above; keep individual Mesh/E, three widths/undo. | `sincronizar_exclusoes`, `OBJECT_OT_alinhar_prateleiras`, `test_excluir_qualquer_unidade_preserva_posicoes_e_recalcula_hud_e_menu`, `test_secao_espacamento_tem_campos_E_e_botao_sem_sobreposicao_em_tres_larguras`, `test_undo_redo_de_excluir_e_alinhar_restaura_quantidade_e_posicoes` | prateleiras |
| Library categories 276/277: modes/levels one row every height, gray hover boxes/light-gray theme borders/dividers all joints, no navigation halo; background never steals tabs, padding wheel only own level, Shift reaches deeper levels. | `test_todos_os_grupos_incluindo_modos_tem_caixa_e_divisoria_na_mesma_linha`, `test_hover_de_aba_realca_so_a_caixa_daquela_categoria`, `test_caixa_tem_hover_no_espaco_vazio_sem_roubar_o_hit_test_da_aba`, `test_roda_no_padding_da_caixa_rola_apenas_seu_nivel` | biblioteca_faixa |
| Responsive library 278: photos proportional to height, fit arrows even tall/narrow, preserve size/path; border only category-tab hover, not permanent/empty background. | `test_miniaturas_crescem_com_a_area_sem_ultrapassar_altura_ou_largura`, `test_hover_de_aba_realca_so_a_caixa_daquela_categoria` | biblioteca_faixa |
| Native Delete cleanup 279: remove hidden hinge controls/Empties/marked empty cabinet folder; partial delete keeps survivors/shared data/common objects-folders; defer Tab/modal/undo, native undo restores assembly/Collection. | `test_delete_pecas_limpa_rig_empties_e_pasta`, `test_delete_so_folha_limpa_rig_e_preserva_carcaca`, `test_delete_pai_deixa_subgrupos_mas_limpeza_remove_pasta`, `test_delete_parcial_preserva_porta_e_dobradicas`, `test_limpeza_preserva_objeto_comum_na_pasta_e_grupo`, `test_limpeza_rig_preserva_filho_comum_e_dados_compartilhados`, `test_limpeza_so_remove_pastas_marcadas_e_comodos_vazios`, `test_limpeza_adiada_em_undo_edicao_ocupado_e_modal`, `test_delete_undo_redo_restauram_modulo_e_pasta` | portas |
## Volume controls (285)

Group origins 287: Hide/Show, default hidden, native per-viewport flags, restore on individual selection/save/deactivation, respect manual changes and prior hiding. TestHUD references: `test_origens_grupo_restaura_flags_nativas_e_opcao_muda_na_hora`, `test_origens_respeita_viewport_e_intervencao_manual`, `test_origens_somem_em_todos_os_grupos_mas_nao_na_folha_individual`, `test_menu_oferece_ocultar_e_mostrar_origens_no_grupo`.

286: drag starts without snap even when global magnet is on; B activates native base. Face dots radius 2 px/hover 3 px, larger click area retained.

- Six actual face centers, picking and rotated box. References: `TestHUD.test_volume_seis_centros_reais_e_hit_test_em_caixa_girada`.
- Native translate/vertex filter, state contains no scene IDs; macro executes real translate/confirmation. References: `TestHUD.test_volume_translate_nativo_vertice_base_b_e_estado_sem_ids`, `test_volume_macro_executa_translate_real_e_confirma`.
- One original reference for repeated previews; Esc restores mesh. References: `TestHUD.test_volume_previa_reparte_da_origem_e_esc_restaura_malha`.
- Invalid physical size allows recovery to valid size without leaving modal. References: `TestHUD.test_volume_medida_invalida_nao_abandona_translate_e_pode_recuperar`.
- Correct shelf top/base opening without moving body. References: `TestHUD.test_volume_prateleiras_corrige_topo_e_base_sem_mover_corpo`.
- Moving shelf front keeps back fixed; repeated drawer/partition previews handle rebuilt children. References: `TestHUD.test_volume_prateleiras_frente_movel_preserva_costas`, `test_volume_gavetas_e_divisorias_previa_repetida_com_filhos_refeitos`.
- Volume interaction does not intercept angles or individual-unit dimensions. References: `TestHUD.test_volume_nao_intercepta_angulo_e_cota_de_unidade`.
- Real B/Esc/numeric/undo events require authorized GUI. References: `gui_interacao.test_circulo_da_face_translate_b_esc_e_undo`.

## Options and internal fitting (288)

- Independent support dots/guides with RNA preferences; no invisible hit targets. References: `TestHUD.test_opcoes_independentes_escondem_bolinhas_e_guias_sem_alvo_fantasma`, `test_menu_tem_controles_ligado_desligado_para_bolinhas_e_guias`.
- Consume clearance before shrinking; restore chosen drawer/shelf size when space returns. References: `TestGavetas.test_reducao_com_folga_preserva_gavetas_ate_faltar_espaco`, `TestPrateleiras.test_reducao_com_folga_preserva_prateleiras_e_so_adapta_ao_encostar`.
- Native S preserves physical internal mesh dimensions until space runs out, and recovers. References: `TestGavetas.test_escala_nativa_conserva_internos_ate_faltar_espaco`.
- A narrower individual drawer does not shrink with its opening while it still fits. References: `TestGavetas.test_gaveta_individual_menor_nao_encolhe_junto_com_o_vao`.
- Cancel HUD resize restores metadata and geometry. References: `TestPrateleiras.test_cancelar_resize_do_modulo_restaura_vao_parametros_e_geometria`.

## Snap base after preview (289/290)

- 290 supersedes 289's return-to-origin: B keeps CURRENT geometry and absorbs latest motion before timer. Three axes/both directions, vertex reaches target, cursor intact at preparation, real translate/Esc. References: `TestHUD.test_volume_base_snap_apos_arraste_preserva_geometria_atual_em_todos_os_eixos`.
- Repeated B/same base keeps accumulated displacement without double counting; Esc recovers original geometry/reference. References: `TestHUD.test_volume_base_snap_repetida_acumula_so_arrastes_e_esc_restaura_origem`.
- Observer forwards events/undo, uses native matcher/remapped shortcuts, installs after translate and frees timer. References: `TestHUD.test_volume_observador_repassa_base_nativa_e_termina_sem_consumir_undo`, `test_volume_observador_abre_depois_do_translate_e_libera_timer`.
- Authorized GUI: drag 60 px->B, current position retained->current base vertex->B->fixed target vertex->Enter/release->undo. References: `gui_interacao.test_snap_b_depois_de_arrastar_face_nao_soma_deslocamento_anterior`.

## Explicit cabinet update ownership (295)

- Cabinet owner updates doors->drawers->shelves once each; internos=False preserves fits. Doors keeps own applicator/old public facade without coordinating internals. References: `modulos.atualizar_sistemas_do_conjunto`, `internos=False`.
- Coordinator order and compatible legacy signature without duplication. References: `test_coordenador_atualiza_portas_gavetas_prateleiras_uma_vez_nesta_ordem`, `test_api_legada_delega_ao_mesmo_coordenador_sem_duplicar`.
- Door-only scope preserves actual internals; missing/unmarked targets ignored. References: `test_atualizar_apenas_portas_preserva_internos_reais`, `test_coordenador_ignora_alvo_ausente_ou_sem_marca`.
- Actual no-door resize calls each owner once, retains modeled Mesh IDs/cutouts. References: `test_resize_sem_porta_usa_coordenador_e_preserva_malhas_modeladas`.
- Production callers do not coordinate through old door facade. References: `test_producao_nao_coordena_sistemas_pela_api_legada_de_portas`.
- Native resize undo/redo, reload/dynamic domain links preserved, organization suite. References: `test_undo_redo_do_resize_coordenado_restaura_corpo_e_internos`, `test_recarga_religa_setores_e_preserva_objetos_da_cena`.

## Local shelf subdivisions (294)

- Group total/full blocking; unit only its subdivisions between external supports, local count/dimensions/frame, persistent per-copy UID without new hierarchy.
- Subdivide 1->2/3/1, keep active/support positions, last E never moves support, Center only redistributes local interval. References: `test_quantidade_local_subdivide_so_entre_os_apoios_e_reutiliza_a_familia`.
- Selection switches counter/E fields/HUD bounds between local and group scopes. References: `test_selecao_local_tem_contador_e_caixa_limitados_e_grupo_tem_total`.
- Four drawers preserved under 3D rotation, copies keep IDs/cut/material/modifier/parameters. References: `test_detalhamento_preserva_quatro_gavetas_e_herda_madeira_em_modulo_girado`.
- Count target by name, preview without copies, Esc cancels, typed count local interval only. References: `test_contador_local_digitado_arrastado_e_esc_mantem_escopo`.
- Validate physical capacity before mutation; zero removes local interval only, preserving supports. References: `test_detalhamento_inviavel_nao_altera_cena_e_zero_remove_so_o_trecho`.
- Undo/redo/save/reopen retain local support links; independent groups may share UID. References: `test_undo_redo_de_detalhar_preserva_vinculo_e_apoios`, `test_detalhamento_gravado_em_blend_reabre_com_escopo_local`.

## Native shelf movement and dimensions (293)

- Native transform.translate in individual/global Tab, up/down,3D-rotated cabinet, HUD/menu E, same Mesh IDs, no remount jump or neighbor movement. References: `test_g_nativo_em_tab_individual_e_global_atualiza_cotas_sem_mover_vizinhas`.
- Object G synchronizes only after confirm; discard prior fit without timer rebuild. References: `test_g_nativo_em_objeto_sincroniza_so_apos_confirmar_e_conserva_encaixe`.
- Crossing shelves reorders actual bottom-up E fields, individual settings/selection follow panel. References: `test_g_cruzando_prateleira_reordena_cotas_e_conserva_parametros_individuais`.
- Native G undo/redo restores geometry/dimensions, guard held until regular timer. References: `test_undo_redo_do_g_nativo_restaura_malha_posicao_e_cotas`.

## Centering an individual shelf (292)

- Selected shelf equalizes only above/below gaps between actual support faces/opening limits; group still distributes all.
- First/middle/last/only shelf, individual E/cut/Mesh ID, neighbors/selection retained. References: `test_centralizar_individual_iguala_so_vaos_vizinhos_e_preserva_madeira`.
- Absorb timer-pending deletion/compact index before choosing supports for centering. References: `test_centralizar_individual_absorve_exclusao_e_remapeia_indice`.
- Native undo/redo restores heights and active individual unit. References: `test_centralizar_individual_undo_redo_restaura_posicao_e_selecao`.

## Actual B-key recognition during resize (291)

- Direct modal matcher fails due empty idname/operator poll; internal normal mirror preserves shortcuts/modifiers/remapping, cleans on finish/unregister. Native RNA fixture, not mocked matcher. Open-Blender proof rejects empty item, accepts valid operator with real event, rejects other shortcut. References: `TestHUD.test_volume_mapa_snap_nativo_tem_operador_valido_e_copia_atalhos_modais`.
- Bent body/four drawers/90-degree rotation: initial size retained, pre-B drag/current reference/new translation preserve dimension, Esc restores. References: `TestHUD.test_volume_gavetas_em_corpo_dobrado_e_girado_preservam_previa_ao_ancorar`.
- Authorized GUI full gesture to actual body corner/native undo; assert B reached observer. References: `gui_interacao.test_snap_b_gavetas_em_corpo_dobrado_e_girado_alinha_vertice_real`.

- 376: areas_criacao40 covers arbitrary 3 points/all 6 orders, rotated/scaled/mirrored cabinet, invalid/coplanar, six fronts preserve volume/corners, preview-only ray, CANTO1/2/3/FRENTE/QUANTIDADE, third-point correction, mandatory front, suspended HUD, parent modal handoff/cleanup, actual 3-domain creation, Backspace/Esc. Isolated full 4.2/5.2 2860/64 passed. Headless real callback primitives/3 shelves in 500x350x700 mm, two images reviewed. GUI3-point/front update prepared, PC authorization required.

- 377: gavetas 57/areas_criacao41, fixed entry target/internal children included, other cabinet/inverted ceiling/curve excluded, native identification only scoped targets even coincident external mesh. First point without selection fixes target, deselected active does not; confirm/Esc/error restore flags/cursor without revealing hidden. Native ray passes external occluder; free volume/HUD/B same scope. Isolated owner-alias interactive macro patched to avoid background gesture. Full 2876/64 passed. Headless global ceiling ray vs cabinet BVH only Lateral Esquerda/Base,964x600x1364 box/three drawers reviewed, no real GUI.

- 378: gavetas 61/areas 42/operadores 56/gaveta 86, free camera between points/front/free-volume, no hover translate, PRESS release_confirm, confirm never reopens. Native navigate/walk/fly/pan/zoom; Shift+scroll keeps count. Door group from leaf/handle, native H aggregates, same Hide Door descendants/layer/Mesh/neighbors/timer/undo, Alt+H; Shift+G native groups retained. Orange 30 px free volume at 3 widths, reviewed height snapshot. Full 2900/64 passed, real menu primitives 190/320/564 reviewed. GUI Walk/D between points prepared only, requires free PC.

- 379: prateleiras 60/divisorias 42/hud 186, scroll V subdivides empty gap with fixed supports, inherited model/material/E, native stock without source, reduce/zero/Esc/undo/atomic capacity/Enter quantity. cabinet_blocagem_uid per partition/shared session, HUD/selection aggregate active orientation only, legacy actual-support timer, independent blocking retained. Right-side drawer fixture preserves opposite Mesh/pose/count. Full 2932/64 passed. Temporary 700 mm lower gap/three shelves/four 161.5 mm gaps, right dimensions intact, partitions only two horizontal 473 mm gaps. GUI scroll/Enter/Esc prepared, not run without free PC.

## Post-Tab contour and internal snap regressions (380)

- Warm 600x2000x18 panel cache, native Edit Mode moves one skin corner 80 mm, exit Tab: all HUD lines actual edges, each value actual length, E nominal 18. Old projection of one profile onto different back reproduced expectedFailure then unmarked pass. References: `test_tab_em_canto_da_chapa_plana_mantem_cotas_nas_arestas_reais`.
- Drawing callback receives actual edge's projected endpoints, including oblique top/horizontal back. References: `test_seta_do_topo_editado_segue_a_aresta_clicada`.
- Different-skin contour/menu draw numeric only; Mesh/pose/faces/UV/material retained. References: `test_contorno_com_peles_diferentes_e_cache_sem_extracao_no_redraw`.
- Second internal Tab edit without L/A/E envelope change invalidates cache and keeps dimensions on wood. References: `test_segundo_tab_sem_mudar_envelope_atualiza_as_cotas_reais`.
- Edit real edge by UID, retain topology partner/same Mesh/nominal E; native undo restores dimension/contour. References: `test_cota_real_de_pele_editada_preserva_mesh_e_undo_redo`.
- Invalid UID never separates shared Mesh; valid edit isolates edited user only after validation. References: `test_cota_de_pele_editada_isola_mesh_compartilhada_so_apos_validar`.
- B at CANTO1/2/3 for shelves/partitions/drawers starts VERTEX/EDGE_MIDPOINT translate; key RELEASE never confirms. ExpectedFailure before fix, existing click/drag/navigation regressions retained. References: `test_b_ativa_snap_nativo_nos_tres_pontos_sem_confirmar_ao_soltar_tecla`.
- Disposable headless numeric-HUD-edge before/after render: max 80 mm error before,0 after. Open project/real library unchanged, no physical GUI.
- Root/test AGENTS/CLAUDE require automated same-commit regression per fix, failing before/passing after.
- Recorded final: HUD192/drawers 62 per version, full 4.2/5.2 2946 tests/64 passed,380 ZIP39 Python sources identical.

## Vertical closure using a frame panel (381)

- Warm-cache frame 649x2531x15, Tab narrows off-center X to 64.9, R rotates 90 degrees. Exit measures/HUD actual edges, keeps Mesh/world coordinates/door-group params. Old frame absorption exclusion reproduced expectedFailure. References: `test_tab_afina_moldura_gira_vertical_e_hud_acompanha_malha`.
- Already altered geometry/no stored Edit transition as after reopen: timer native bound_box mismatch recovers dimensions, also expectedFailure before fix. References: `test_moldura_ja_editada_corrige_limites_no_timer_sem_novo_tab`.
- Frame width 3 mm/E15, axes never swapped or panel thickened. References: `test_fechamento_mais_estreito_que_E_mantem_contorno_e_espessura`.
- Three unchanged timer checks never reabsorb or re-recognize mesh. References: `test_moldura_sincronizada_nao_reextrai_malha_a_cada_timer`.
- Three native undo/redo cycles restore original/narrow width with real contour/E retained. References: `test_undo_redo_do_fechamento_vertical_conserva_cotas_e_geometria`.
- Headless actual-HUD audit: before narrow wood inside 649 mm box, after contour follows 64.9 mm. Disposable scene, live project/library intact, no physical gestures.
- Recorded final: HUD197/version, full 4.2/5.2 2956 tests/64 passed,381 ZIP39 identical Python sources, mirrors/guide limits checked.

- Offline tools relocation: `test_direct_cli_from_external_directory_keeps_help_read_only` launches four guarded tools from a temporary working directory without PYTHONPATH; expected exit 0, help output and no files created. `test_hardware_resources_stay_in_addon_after_relocation` evaluates only nine resource path declarations; expected paths stay in archy_builder/assets/hardware or archy_builder/assets/previews without running any extractor (migracoes).

- Explicit DXF inputs: `test_source_paths_are_explicit_before_preparing` invokes six CLI entry points without a source path; expected exit 2, a source-required message and no staging/library files created. Legacy source flags remain accepted; publication obtains source paths from its existing manifest (migracoes).

## Historical delivery test references

Names are retained verbatim so existing tests and evidence remain searchable.

- `test_marca_nova_preserva_identificadores_e_preferencias`
- `test_arquivo_com_identidade_antiga_reabre_sem_converter_dados`
- `test_marca_nova_migra_catalogos_antigos_sem_trocar_uuid`
- `test_registro_renomeia_biblioteca_legada_sem_duplicar_pasta`
- `test_paredes_selecao_blender`
- `test_fundos_blender`
- `test_solda_blender`
- `test_soldas_biblioteca_blender`
- `test_estrutura_blender`
- `test_operadores_blender`
- `test_puxadores_blender`
- `test_portas_blender`
- `test_mirror_nativo_do_grupo_preserva_malhas_e_recalculo_dos_internos`
- `test_redimensionar_e_recentrar_modulo_espelhado_girado`
- `test_braco_angular_espelhado_preserva_volume_e_migra_mira_antiga`
- `test_wall_layout_blender`
- `test_estimates_blender`
- `test_wall_editor_blender`
- `test_partitions_blender`
- `test_append_delete_limpa_embalagem_asset_legada_com_fake_user`
- `test_embalagem_asset_nao_vazia_e_assets_alheios_sao_preservados`
- `test_embalagens_asset_aninhadas_limpam_de_dentro_para_fora`
- `test_undo_redo_restaura_embalagem_asset_e_sua_identificacao`
- `test_botao_normaliza_alturas_preservando_total_folgas_e_ajustes`
- `test_normalizar_que_nao_cabe_preserva_estado_e_uma_so_nao_tem_botao`
- `OBJECT_OT_normalizar_gavetas`
- `test_altura_individual_reencaixa_vizinha_sem_mudar_conjunto`
- `test_unidade_tem_profundidade_trilho_largura_e_espacamentos_proprios`
- `test_hud_segmentos_individuais_hover_e_selecao_isolada`
- `test_previa_individual_nao_reconstroi_e_esc_restaura`
- `test_menu_da_unidade_mostra_medidas_e_escolhas_somente_dela`
- `test_edicao_preserva_madeira_abertura_e_puxador_individuais`
- `test_altura_de_uma_gaveta_com_previa_esc_e_digitacao`


## English presentation and resources (410)

- Main tabs, registered operator labels, native dimension labels and fixed catalog
  labels use English. Direction captions Left/Right/Above/Below retain the saved
  action keys; Individual/Group retain INDIVIDUAL/GRUPO. Eight language scenarios
  use disposable native objects and a copied temporary library.
- Hinge Reverse/Mirror captions keep inverter/espelhar action identifiers and
  execute the existing installation actions. English abbreviations retain the
  responsive header at 190, 320 and 564 px.
- Source folder aliases from foreign CAD input map to English catalog paths.
  Catalog path translation keeps distinct Tall Cabinets and Tower Cabinets;
  all catalog UUIDs and bundled asset filenames remain unchanged.
- Resources move to assets/library, assets/hardware and assets/previews. Fixture
  paths, packaging, offline tools and documentation resolve those same owners.
  Native generated names and estimate prose use English; material/geometry
  assertions remain unchanged.
- Saved installation component roles still resolve when opening doors/windows or
  positioning pendants. Original cut/filter/shadow-gap prefixes are recognized
  and renamed when used; deletion restores the support and removes linear lights.
  Four new native-scene regressions failed before the identity resolver and pass
  after it: test_saved_leaf_roles_still_open_without_rebuilding,
  test_removing_saved_cut_prefixes_restores_wall,
  test_saved_pendant_roles_keep_canopy_and_vertical_drop,
  test_saved_shadow_gap_cleanup_removes_cuts_and_lights.
- The English library suite retains its 600-second timeout; other suites keep
  300 seconds. test_library_timeout_survives_english_suite_rename imports the
  runner without starting processes and checks subprocess arguments.
- Reviewed English snapshot changes affect labels, generated names and responsive
  layout. Panel mesh, HUD coordinates and handle geometry remain unchanged.
- Documentation, mirrored instructions, code comments/docstrings, CLI help and
  maintenance diagnostics use English. Serialized keys, internal API identifiers,
  input-format aliases and asset filenames remain technical data identities.
- Final headless validation: 3,464 tests across 82 runs in Blender 4.2 and 5.2,
  all harness suites passed. Existing version skips and expected failures remain.
  Evidence: dist/english410-validated.log. Fresh extracted ZIP registers,
  unregisters and reloads twice in each version; 759 entries match source and
  resources. All 677 binary assets match version 409 byte for byte. Catalog
  entries use the native English path order, with unchanged UUIDs and filenames.
  All 21 instruction pairs match and local documentation links resolve.
  No interactive window, live project or real-library maintenance was used.
