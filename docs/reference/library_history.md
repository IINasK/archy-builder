> Historical technical notes. Current instructions: [architecture](../../ARCHITECTURE.md) and local sector guides. Source paths below remain where historically relevant.

# Library history and asset contracts

This records the former library CLAUDE.md (then limited to 200 lines). Current
instructions live in the [asset guide](../../archy_builder/assets/library/AGENTS.md).

## One library and its files

The company library is the only library. `pasta_biblioteca()` resolves it and
Blender registers one Archy Builder asset library. UI Save writes there. The old
factory/team split produced duplicate Asset Browser entries; locks are now per
item (`bloqueado`), never implicit from directory membership.

Writing inside the add-on was safe in the company checkout because development
used a junction (`vincular_blender.py`). ZIP updates can overwrite that directory;
ZIP installations should configure Preferences `pasta_biblioteca` to a network
folder when retaining company assets.

| File | Purpose |
|---|---|
| `*.blend` | One compressed binary preset written with `bpy.data.libraries.write`. |
| `*.png` | 512x512 photo with the blend basename. |
| `indice.json` | UI catalog, avoiding a blend read per item. |
| `blender_assets.cats.txt` | Asset Browser catalogs, `VERSION 1`. |

Index is a JSON list, `indent=1`, `ensure_ascii=False`; example retained as data:

```json
{
 "nome": "Nicho 600x400x300",
 "arquivo": "Nicho_600x400x300.blend",
 "tipo": "modulo",
 "n1": "Armarios", "n2": "Cozinha", "n3": "Inferiores"
}
```

- `tipo`: `modulo` means asset Collection/whole assembly; `objeto` loose objects.
- `n1/n2/n3` are the first tree levels, extended dynamically; absent third level is empty string.
- Optional `niveis` is the complete unlimited path, e.g. `["Armarios", "Cozinha", "Altos", "Despenseiros"]`; first three remain in n1/n2/n3. Read with `caminho_de`; `_niveis_de` returns only three. Catalog uses the complete path.
- Optional `foto`, `ordem` (grid position), `bloqueado`, `caixa` (drag wireframe without opening blend; `bytes` invalidates it).
- `_niveis_de` still reads legacy `categoria`/`subcategoria`; do not generate these or break reading them.
- `arquivo` basename is item identity. `indice_completo()` adds `pasta`/`origem` in memory; never persist them in JSON.

Catalog line: `UUID:caminho/do/catalogo:nome_simples`. Presets store UUID in
asset_data; replacing it makes assets disappear from categories. `_garantir_catalogos()`
generates the full ARVORE cascade under single Archy Builder root; do not hand-edit.
`RAIZES_ANTIGAS` (Cabinet Creator/Chapa G3) renames paths while retaining UUIDs.
Level 1 matches ARVORE UI keys; Chapas/Modulos type catalogs are uncategorized-save
fallbacks, outside the cascade. Category moves use `refiliar_preset()` because
catalog_id lives inside blend; changing only the index cannot move Asset Browser entries.

## Native factory cabinets and DXF adoption

User decision: use DXF modules only. The 39 native presets were deleted; generator
`tools/library/generate_native_cabinets.py` and `ARMARIOS_NATIVOS` remain for tests,
never run on real library without request. Apply preview only AFTER removing
scene pieces: `aplicar_preview_png` reloads/rewrites and existing names caused .001.

DXF folder = tab (Altos/Ilhas/Sup Baixos...), file = category. Unlimited `niveis`
currently includes four or more levels, e.g. Armarios > Cozinha > Inferiores >
Cantos. Early Cantos/Bifond exports map to Inferiores (`importacao.categoria_promob`).
`tools/library/import_dxf_library.py` runs background in Blender 5.x and reads
`Documentos/DXF/<Ambiente>/<Aba>/<Categoria>.dxf`. Names such as `Canto 01 LxAxP`
exclude door depth; non-Inferiores include tab (`Canto Sup Baixo 01`) to prevent
collisions. Reimport replaces by name; if naming rules change, remove old index
entries (former n3 `Aba - Categoria`) and their blend/png first.

DXF has a layer per part, 3DFACE/polyface, mm, Z up, front -Y. Colors: 7 wood,
253 hardware, 254 aluminum/glass, 8 handles, 28 accessories, 250..252 appliances.
Integrate into native systems: panels color 7, >=3 mm thick, sides>=50 mm including
curves; hinged fronts -> native doors/hinges/coverage; MDF boxes/wire baskets ->
native drawers/rails with proportional heights and sagitta for curved fronts;
23 mm color 254 aluminum frame -> sliding aluminum-frame leaf/native rail.
Thin backs/top stretchers become dependents. Imported curved doors use explicit
native add-on control; Tab-curved meshes never silently activate it.

Hardware, handles, baskets, appliances and decoration never become wood. Remove
floor panels lying flat >1.5 m2 and <=6 mm, or underneath 80% of pieces. L/diagonal
hinge plate/arm determines face/heights; oriented opening follows real vertices
(cabinet_canto/vN), including R/angle. Articulated leaf follows its support leaf,
with plate/cup, not a floating carcass hinge. Hardware belongs only to nearest
group. Unsupported/cyclic joints use actual outer side. Bottom-hinged fronts
remain panels (drop-down unsupported). Touching pieces form one cabinet; separate
modules in DXF scene. Native source `.entity` files contain engine recipes/formulas,
not geometry; manufacturer `.model` is encrypted and cannot substitute for DXF.

## Recorded migrations and audits

These results and backup names are historical evidence, not checks rerun during
translation. Original asset names, paths and labels below remain data contracts.

| Version | Recorded work and evidence |
|---|---|
| 230 | `tools/migrations/adjust_fits.py`: base/top up to3.1 mm inset moved to outer side corners; preserve E, contours, UID, doors/drawers, external bounds; rebuild anchors. Internal shelves/grooved backs/larger setbacks excluded. Native import also applies `promob.ajustar_encaixes`. Prepare/reopen/check blend/photos/previews externally, keep originals; publish with hashes and unchanged names/index/UUIDs. 13 Oct2026:182 audited,172 corrected,269 panels at -3/+3 mm; zero residual gaps, all external bounds retained. Backup `Documentos/Cabinet Creator Backups/encaixes-20261013` with manifest/hashes. |
| 231 | `tools/migrations/adjust_doors.py`: replace doors only from category DXF, restore misclassified panels, adopt formerly fixed corner fronts. Preserve other UID/geometry/fits/materials/handles/names/UUIDs; reopen/check before apply. Normalized per-leaf hinge-height references replaced only by manual count/margin, never count plate as second hinge. Full-overlay spacer may move outward for half coverage; no zero clamp leaving plate7 mm away. Preserve references/OBJECT slots. 14 Oct:96 corrected,26 panels restored,68 fronts integrated,339 hinge supports verified touching. Backup `Documentos/Cabinet Creator Backups/portas-20261014-preparo5`. Closed blend; historical corner photo100%/50%. |
| 232 | `tools/migrations/adjust_hinges.py` repairs oblique-support hardware only, no door/panel rebuild. Whole plate touches actual face:four coplanar vertices plus outward thickness, not nearest single corner. Preserve inclined prism in wireframe/mesh. Native zigzag:2..8 alternating leaves, plates/nodes/axis/screws, handle last only. |
| 233 | `tools/migrations/audit_and_repair_integration.py`: DXF comparison, selection/sliders/open/edit/restore including save/reopen.182 audited,134 corrected;113 native drawers (was96),220 shelves/free gaps in original panels. Islands by actual face, misclassified sides restored, front coverages/proportions retained; materials/UID/world body geometry/catalogs verified. Backup `Documentos/Cabinet Creator Backups/integracao-20261014-preparo11`, expected/before/after manifest per preset. Library updates require reinserting old scene instances. BLENDER17/5.x unreadable by4.2.1, which validates code only. |
| 236 | `tools/migrations/adjust_backs_and_doors.py`:25 backs set15 mm, four single-front islands Inferior02/03/Superior01/05,29 presets. Opposite front -> native5 mm back, corners preserved; shelves/boxes refitted, partial backs retain profile. Backup `Documentos/Cabinet Creator Backups/fundos-portas-20261014-preparo3`. |
| 237/238 | First door photographed left, others closed, corner100%/50%, crease-only outlines.238 makes real supported left opening; reverses coplanar chains. `tools/migrations/adjust_left_opening.py`, backup `esquerda-20261014-preparo2`. Assembly intact; `tools/migrations/refresh_library_photos.py` checks reread/hashes, backup `Documentos/Cabinet Creator Backups/fotos-20261014-preparo1`. |
| 241 |11 Sup Medios > Cantos rebuilt from DXF by `tools/migrations/refine_corners.py`. L backs retain margins on EACH plane; partial back never full rectangle (formerly+75 mm). Base/top to corner, touching partitions follow inner face. Exact gaps/coverage, panel normal free from plate noise, native angular hinge for diagonal support. Profile below; later306 curved door profile uses straight edge, native leaf retains mesh/sagitta/R/opening. Closed files, historical100%/50% photos, reread/open/contact audited. Names/index/UUID/material retained. Final backup `Documentos/Cabinet Creator Backups/cantos-20261015-preparo7`, initial originals preparo6. |
| 243 | ALL doors closed in photos/previews, sides/hardware unchanged;183 modules. Backup `Documentos/Cabinet Creator Backups/fotos-fechadas-20261015-v243`. |
| 244/245 |33 corner door modules Inferiores/Sup Baixos/Sup Medios rebuilt: narrow strips/trim retained, fixed panel never leaf articulation,2 mm gap. Backups `cantos-apoios244-{supmedios,supbaixos,inferiores-validado}`. Inferiores07/12 already lacked functional leaves, preserved.245 adds face references/full-overlay rig for flat leaves/perpendicular support, cups audited inside leaf; backups `cantos-reta245-{medios,baixos,inferiores}`. |
| 246 |+220 models,408 presets;30 categories (26 new,4 revised). Kitchen Sup Altos/remaining Sup Medios/Portas (32 wood,12 aluminum); Bedrooms Armarios/Bancadas/Escritorios/Cabeceiras/Superiores. Canto05/08 split A/B with individual measurements/local-front profile. Audit259 assets,246 leaves,12 drawer groups,149 shelf groups. Backup `bibliotecas246-preparo` originals/new/manifest/audit. Inserted instances remain unchanged. |
| 249 |405 modules audited; positive-support-area automatic joints, residual UIDs cleaned, manual anchors retained;8557 ->3129 links. Canto Sup Alto11 strip3..1053 ->0..1056 mm, new closed photo. Backup/reread/hash `conexoes249-preparo`; `tools/migrations/refine_library_connections_v249.py`. |
| 251 |32 Diagonais corrected from top profile;12 modeled fronts adopted, handle/Alt tangent, supports touching.100 mm resize/return audited; body/UID/material/catalog retained. Backup `diagonais251-validado`; `tools/migrations/refine_diagonal_fronts_v251.py`. |
| 252 |Same32 with free actual-panel ends, profile outline/top preview corrected; no BVH intersections. Backup `diagonais252-final`; `tools/migrations/refine_diagonal_clearance_v252.py`. |
| 306 |User chose ALL profile handles. `tools/migrations/standardize_profile_handles.py`:142 modules,37 bar handles ->profile on SAME edge (curves vertical straight edge),147 missing door handles added by import rule (curves side),8 drawers NONE ->profile. Reread505 profiles,zero handleless doors. Profile saved without model material as before,+1.6 MB. Backup `puxador-perfil-20261024-preparo4`. |
| 307 |Bancadas Quarto01/02/05 curved fronts reversed (external hinges/inward opening); `_virar_porta_modelada` turns reference with wood fixed, hinges on actual inner face.01/02 ends aligned with side get user-selected15 mm `Apoio Dobradica` at door height, cut to inner base. Bancada03 profile moved off hinge edge. `tools/migrations/repair_reversed_curved_doors.py`; backup `portas-curvas-20261024-preparo2`. |
| 308 |Profiles always horizontal except wardrobes, by user decision.95 modules redone with standardize_profile_handles.py; tall cabinets by hand height, curved leaves get front references. Reread51 vertical,all Quartos > Armarios. Backup `puxador-horizontal-20261024-preparo1`. |
| 310 |Removed11 leaf-on-leaf hinged/folding modules, user decision: Despenseiro Alto03/04,Balcao11,Inferior Ilha05/06,Armario Quarto02/06,Bifold01/02 (Cantos Bifold category removed),Canto Quarto Armario07/12. Do not reimport articulated leaves into library. |
| 333 |Removed21 curved-leaf modules: Diagonal01/02,Diagonal Sup Baixo02/03,Sup Alto01/02,Sup Medio01/02,Diagonal Quarto Armario01/02,Canto08B,Canto Sup Alto01,Sup Baixo05,Sup Medio03,Canto Quarto Armario02,Canto Quarto Bancada01,Canto Quarto Superior02,Bancada Quarto01/02/03/05. Straight chamfered diagonals stay. Backup `portas-curvas-remocao-20261025`;two copies in tests/fixtures. |
| 341/342 |341 removes Balcao09/15 (curved fronts still ordinary panels),Gaveteiro01/03 (arc fronts); curved reception desks/chamfered diagonals stay by user choice. Backup `frentes-curvas-remocao-20261025-v341`.342 prepares/reopens nonoverlapping internal gaps/local cuts/repaired seams; fixed separators stay structure. Gaveteiro19/Mesa de Cabeceira04 sides restored from DXF; Armario Quarto08 gets four native drawers. Photos/previews/index boxes updated;backup `internos342-preparo`. |
| 350 |Removed remaining10 diagonals with `porta_curva_modelada` and34 repeated/mirrored variants; straight/chamfered/curved reception desks stay. Geometry/material/systems audited across369 modules; preserve most visible front-right-photo orientation, ties by ordinal. Kept names/UUIDs/bytes unchanged. `tools/migrations/consolidate_library_variants.py`:external plan,backup/hashes,atomic index/rollback. Originals `Documentos/Cabinet Creator Backups/variantes350-20261025`;audit/choices sibling `variantes350-auditoria`. Mirror is native GROUP Object Mode transform, never per-panel duplicating modifier. Inserted instances not removed. |
| 359 |`tools/migrations/refine_library_joints.py`:328 audited,265 blend files refined;2385 records ->1978 unique pairs, nearest actual vertices. Geometry/material/UID/catalog/photos retained. Reversible backup `Documentos/Cabinet Creator Backups/soldas359-aceite-20261027-042135Z`. |

## Data safeguards

- `.blend`/`.png` are binary in `.gitattributes`; never edit as text.
- Do not commit ignored `*.blend1`/`*.blend2` backups.
- Saved `eh_chapa`, `chapa_*`, `adj_*`, `chapa_uid` are compatibility contracts.
- Historical build.py packages the whole folder including this guide. Recorded state:328 assets,325 cabinets/3 objects, index/file/photo/catalog consistent. Preparation validates external real paths including Windows junction/case; publication checks hashes/backups and rolls back (migracoes suite).
