# Archy Builder - project instructions

AGENTS.md and CLAUDE.md are exact mirrors; update both. Maximum 200 lines.
Use English for file/folder names, UI, documentation, code annotations and commits.
Existing serialized keys and internal API identifiers remain data contracts.
Comments explain why. Do not translate persisted keys or operator identifiers.

## Read only the relevant sector

Start with [ARCHITECTURE.md](ARCHITECTURE.md): task -> owner -> guide -> tests.
Read its guide explicitly before editing. Do not load every guide.
Visible UI also requires [DESIGN.md](DESIGN.md) and the
[cabinet-design skill](docs/skills/cabinet-design/SKILL.md).
Front geometry requires [FRONT_GEOMETRY.md](FRONT_GEOMETRY.md).
Tests: [tests/AGENTS.md](tests/AGENTS.md). Assets:
[library guide](archy_builder/assets/library/AGENTS.md).

## Package and boundaries

Blender add-on (bl_info 4.0; tested in 4.2 and 5.2). Panels use BMesh;
cabinet assembly = Empty + Collection. `ui/sidebar.py` is the GPU editor;
`cabinetry/drawers/` owns furniture drawers.
Sector packages: core, cabinetry, architecture, ui, integrations.
The root __init__ loads, links and registers implementations in explicit order.
Cross-domain calls ALWAYS use the owner module (`_portas.name`, for example).
Relative imports load modules, never individual cross-domain functions.
Patch the owner module in tests, not a copied function at the package root.
Legacy imports alias the same canonical module in sys.modules; no duplicate code.
Do not add wrappers, discovery loaders or abstractions just to split files.

## Commands and verification

```
python tools/development/link_blender.py [version]
python tools/development/build.py
blender --background --factory-startup --python tests/run_tests.py
```

Without Python on PATH, use Blender's version/python/bin/python.exe.
During work use `-- --suites <area>`; run the complete harness before delivery.
Every bug fix requires an automated regression in the SAME commit: a reproducible
scenario failing before and passing after the fix. Every improvement requires
parameters and expected outcomes. Record both in tests/SCENARIOS.md.
Use temporary scenes/fixtures; never modify the open project or real library.
`--gui` OPENS Blender: only with the user releasing the PC NOW.
Structural failures protect intentional decisions. Do not weaken them; requested
architecture changes update the layout contract while preserving behavior.
Test-count floors only rise. Increment bl_info['version'] for each delivery (410).

## Global preferences

- Delegate only when explicitly authorized for the CURRENT task.
- SNAP: reuse Blender's native engine whenever applicable. No Python mesh scans
  on click/drag, including internal creation. Restore temporary cursor on confirm
  and Esc; one undo. translate.orient_matrix takes axes in ROWS: transpose a
  group Matrix whose axes are columns.

## Invariants - never break

1. Panel: X = width, Y = length, Z = thickness. Orient by rotation, never scale;
   discard `sz`.
2. Names stored in .blend are contracts: `eh_chapa`, `eh_conjunto_chapa`,
   `chapa_*`, `conj_*`, `adj_*`, `chapa_uid`, `eh_grupo_portas`,
   `eh_folha_porta`, `porta_*`, `eh_acessorio`, `eh_puxador`, `puxador_*`,
   `eh_colecao_modulo`, `eh_colecao_comodo`, `eh_moldura_porta`,
   `eh_fundo_modulo`, `fundo_recuo_mm`, `fundo_margens_mm`, `fundo_recuo_base_mm`,
   `eh_travessa_modulo`, `travessa_lado`, `cabinet_blocagem_uid`, `parede_*`,
   `cabinet_parede_uid`, `cabinet_canto`, `cabinet_forma_angulo`,
   `cabinet_material`, `eh_peca_curva`, `eh_grupo_gavetas`, `eh_gaveta`,
   `gaveta_*`, `gavetas_*`, `eh_grupo_prateleiras`, `eh_prateleira`,
   `cabinet_alvenaria_definida`, `cabinet_ambiente`, `cabinet_ambientes`,
   `cabinet_ambiente_uid`, `cabinet_ambiente_nome`, `cabinet_tipo_superficie`,
   `cabinet_face_apoio`, `cabinet_instalacao_*`, `cabinet_apoio_instalacao`,
   `prateleira_*`, `prateleiras_*`, `forma_edicao`, `chapa_edicao`.
   The installable package/preferences key is archy_builder; editor types use ArchyBuilder.
   Legacy CAD property/API spellings are compatibility data, not product branding.
3. Markers are ID props (`MARCA_CHAPA in obj`); bpy.props are RNA and do not
   appear in `"x" in obj`. Never interchange these checks.
4. Code writes to update= properties under `_ocupado[0] = True; try/finally`.
   `_upd_*` callbacks and handler return early while busy. Mesh work AFTER finally.
5. Geometry is WORLD space (`_eixos`, `_centro`, `_cantos`); set position through
   `_definir_centro` (parent aware).
6. view_layer.update() before reading matrix_world after changes.
7. Neighbors by UID, never names (inserted presets acquire .001).
8. Free thickness (`_espessura_livre`, >0; >60 mm red field), no rounding.
9. Mesh via BMesh: Blender 5.2 does not write Geometry Nodes input (#160038).
10. Never replace modeled meshes (`_esticar_malha` stretches); chapa_auto is residue.
11. No bpy.ops in register(): defer through bpy.app.timers.
12. Unregister EVERYTHING registered: CLASSES, props, handlers, timers, keymaps.
    Global state uses one-element lists, cleared there.
13. One library (`pasta_biblioteca()`); remove old registrations BEFORE add.
    Catalog lives INSIDE .blend (catalog_id; refiliar_preset moves it). Stable UUIDs,
    including RAIZES_ANTIGAS migration. Atomic cats writes only when changed
    (`_gravar_se_mudou`); concurrent Blenders formerly regenerated every UUID.
14. `_niveis_de` still accepts legacy categoria/subcategoria indices.
15. Left viewport click belongs to ADDON keyconfig. OBJECT_OT_selecionar.poll is
    False outside Object Mode or with selecao_por_grupo disabled. Native CLICK
    handles ordinary objects; never recreate it. Operator props SKIP_SAVE.
16. sincronizar_contornos restores only overlays that IT disabled.

## Confirmed Blender API traps

- Mesh.unit_test_compare crashes 4.2 with incompatible attributes: compare
  names/domains/types BEFORE the native comparison.
- Draw/gizmo/timer errors are only PRINTED; GUI harness must catch them. Never
  hash an action dict. Pool library/menu gizmos, hide instead of remove/rebind;
  fields retain their operator and update tooltip (WM_gizmomap_tooltip_init crash).
- popup_menu in --background crashes Blender: use `_abrir_pergunta`.
- Scene Objects retained globally can become freed RNA on undo/load/delete.
  Store NAMES; clear hover in undo_pre and validate through `_alvo_vivo`
  (as_pointer only, no object reads).
- No selection/mesh operations in depsgraph/timer during undo/redo (`_desfazendo`).
  Undo completion only releases the guard; rebuild references in the regular
  timer. Clear old Edit Mode/modal transitions. Absorbing Tab only measures and
  recenters, NEVER gerar_malha_chapa/BMesh.to_mesh. Mesh.is_editmode blocks writes
  even through other instances. Group selection uses select_get.
- Finished REGISTER modal operators stay alive: `_larga_dados_ao_terminar` wraps
  invoke/modal/cancel, including inherited mixins, dropping scene RNA (dict keys
  too). Exceptions clean handlers/timer/snap before propagating.
- Popup on PRESS receives that click's RELEASE as first answer. Sidebar actions
  opening popup/modal trigger on RELEASE (`OPERADORES_NO_SOLTAR`), including icons.
- bpy.ops inside operators: esperar_soltar. Modal lacks DOUBLE_CLICK:
  `_duplo_clique_na_foto`. User keyconfig order ignores head=True; gestures which
  must beat selection use GIZMO, before keymap (like sliders).
- GIZMO_GT_button_2d does not accept modified clicks; Alt chain/ruler uses
  cabinet_clique_corrente keymap.
- UILayout has no new widget or px support; template_asset_view removed in 5.x.
  asset_generate_preview is asynchronous: use aplicar_preview_png before write.
- Window width/height read-only; Asset Browser uses AREA split; shelf region_toggle.
  Curve/text/meta bound_box needs to_mesh (TIPOS_BBOX_INFIEL). Do not intercept
  modal S; handler acts after it finishes.

## Git and user data

Commit each validated stage automatically, with an English message; push only
on explicit request. Preserve pending edits. Ignore dist/, *.blend1, __pycache__.
Resources live in assets/library, assets/hardware and assets/previews.
Asset filenames and catalog UUIDs remain data identities. Do not run maintenance against the real library.
Old Chapa G3 tag and Object/Scene props remain compatibility contracts.
