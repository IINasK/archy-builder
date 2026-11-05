> Historical technical notes. Current instructions: [architecture](../../ARCHITECTURE.md) and local sector guides. Source paths below remain where historically relevant.

# Interface - cross-sector reference

Explicit historical routing reference for UI tasks, not inherited instructions
for `archy_builder/`. Former mirrored-guide limit: 120 lines. Paths below are
repository-relative. Historical scope: `archy_builder/ui/sidebar.py`,
`gaveta_desenho.py`, `gaveta_eventos.py`, `hud.py`, `selecao.py`, `eventos.py`,
`editor.py`, `areas_criacao.py`, `visibilidade.py`, `opcoes.py`,
`biblioteca_faixa.py`, `materiais.py`, `ambientes.py`; `gavetas/` means furniture.
Read [DESIGN.md](../../DESIGN.md), [assets](../../archy_builder/assets/library/CLAUDE.md)
and [integration](integration.md) when applicable. Backs 360 use their own tab,
release-triggered creation and UNPINNED detach in Backs or linked internals.

## Historical task routing

Suites: `tests/test_<suite>_blender.py`; GUI: `tests/<suite>.py`.

| Task | Entry | Suites |
|---|---|---|
| Context/layout/fading | gaveta.py `_widgets_gaveta`, `_widgets_interativos`; visibilidade.py `membros`, `verificar` | gaveta, visibilidade, estrutura, snapshot |
| Persistent editor/3D bridge | editor.py `configurar`, `reparar`, `executar` | editor, biblioteca_faixa |
| Drawing/identity | gaveta_desenho.py `_desenhar_gaveta`, `_chave_widget` | gaveta, estrutura, gui_interacao |
| Click/text/units | gaveta_eventos.py `OBJECT_OT_interagir_gaveta`; gaveta_desenho.py `_tecla_no_texto`, `_apresentacao_medida`; opcoes.py `_texto_medida` | medidas, gaveta, hud, gui_interacao |
| Selection/tab/Tab | selecao.py `OBJECT_OT_selecionar`, `_seguir_selecao_na_gaveta`, `OBJECT_OT_editar_grupo` | operadores, hud, gui_interacao |
| Dimensions/hover/drag | hud.py `campos_cotas`, `_acertar_hud`, `OBJECT_OT_arrastar_hud` | hud, gaveta, snapshot |
| Box faces/B snap | hud_volume.py `controles`, `iniciar`, `atualizar`, `terminar` | hud, gui_interacao |
| Walls/2D/library | paredes_edicao.py `widgets`, `iniciar`, `encerrar`, `preparar_modelo` | paredes_edicao, gaveta |
| Elevation/editable cabinet dimensions | paredes_composicao.py `widgets`, `desenhar`, `editar_modulo` | paredes_composicao |
| Undo/outline/timer | eventos.py `_antes_de_desfazer`, `_fim_do_desfazer`, `sincronizar_contornos`, `verificar_periodicamente` | operadores, hud, estrutura |
| Strip/levels/menu | biblioteca_faixa.py `widgets`, `catalogo`, `rolar`, `abrir_menu_item` | biblioteca_faixa, gui_biblioteca_faixa |
| Photo/cache | gaveta.py `_guardar_foto_gaveta`, `_desenhar_foto_gaveta`; biblioteca_faixa.py `invalidar` | biblioteca_faixa |
| Yes/No | gaveta.py `_pergunta_na_gaveta`; perguntas.py `_perguntar` | gaveta, biblioteca_faixa, gui_interacao |

## Interaction decisions

- Masonry 404: orange Edit first; eye beside Ceiling, forced visible when editing. Installation catalog reuses cascade/grid/photos; drag starts in origin; right-drag shares placer. Validate reassociation before writes, transfer own cut only, preserve components. Undo/redo invalidate numeric cache (instalacoes). 403: own Wall/Floor/Ceiling tab, Create first only for undefined meshes, mixed selection ignores existing supports. Edit loads chosen type; button/Enter confirms, Esc cancels; type colors/names only in editor. Cabinets retains 2D/categories. 402: draggable cards, responsive dimensions, bar/wheel opening under control, warnings without blocking; cabinet-design applies.
- Rooms 399/398: category toggles off only if ALL selected faces already match, otherwise applies to all. No Category clears without color/empty record. Eye toggles labels/colors. 2D categories preserve session/view/isolation, clip hits/previews to active area while applying whole native faces. Equal-column 2D/Categories, red full-width detach below, orange define. Names apply on RELEASE/UNDO; square only edits color, no Set As. Full-width exit/return, 2D selection has no category list. Tab returns 2D; reopening categories starts their own editor. Existing face categories survive G/neighbor removal; new faces start zero. Transient BMesh identity cleared before undo; native projection-depth bias; masonry-only snap.
- Wall 399: fixed target ignores other objects. Automatic chooses category or uncategorized coplanar region; 2D entry limits plane. Shift toggles face, native Ctrl path/Shift+Ctrl fill; Enter confirms. Native index adds vertex+edge+face counts. Original outside Local View participates only during call, no redraw. Automatic 2D click enters, Enter confirms manual; no method/point controls. Preview never mutates selection; menu/navigation pass. BVH/BMesh copies built in timer, not hover.
- Wall 299/301/363/368: menu never edits wall dimensions. 2D dimensions belong to cabinets/gaps; click types, Esc cancels. Temporary SOLID/OBJECT/FLAT with black outlines; restore on exit, G/Tab native. Explicit redistribution (outside menu since 338), replacement only after confirm. Orbit -> PERSP. Library fits width/height up to limit, double-click right of last or wall center. Temporary panel show_wire excludes hardware. Only 2D: any part selects cabinet, double isolates leaf. Interior actual evaluated creases gray/alpha behind fronts, timer extraction/numeric redraw. Dimensions theme line over opaque halo, arrows/font>=14, active HUD highlight; draw text after lines. A1/A2/A3 always; A3 depth at corner, separate offset, resize hides only distances.
- Questions use `_perguntar`: viewport popup, menu black box, library strip question. Never `popup_menu` background. Modal/question actions trigger RELEASE including icons (`solda.OPERADORES_NO_SOLTAR`). Exception: library right-release photo/name Insert/Edit/Lock popup; no under-card buttons, retain lock/protection.
- Selection decides editing scope. Shift adds, keeping last clicked mesh master for native Ctrl+L (356); sidebar follows owner tab. Body selects cabinet, double isolates panel; outside click ends individual, new simple click returns group, Shift preserves. Corner drag moves cabinet; Ctrl restricts snap to another cabinet/panel corner/curve endpoint.
- Visibility 388: fixed strip above library, label and compact right eye/pencil, only compatible selection, no blank reservation. Outside scroll/capture; tab groups include aggregates, not isolated hardware. Native white WIRE/opacity retains snap and independent H/Alt+H. Pencil native left includes/right removes, Enter accepts/Esc restores, extra/excluded UIDs on cabinet, no reparenting. Yes to Hide doors? activates same wireframe. Save/unregister restores appearance; undo reconciles in timer. Door click group/double leaf.
- No finished-door Reposition/Front/Mirror row. Mirror native context group/leaf reverses hinge/opening/handle, whole zigzag chain, sliding travel or lift-up pistons; never mirrors wood.
- Hardware appears only creating/selected, using real wireframe. Click native selection of all type (370), Shift adds, Alt controller, double isolates part with native Tab/G/X. Drawer rails stay with drawers.
- Handle 385: double directly isolates; simple click after drawer isolation selects its own handle before wall scope. Otherwise owner/group. Alt drags anchor along edge only inside its group, with line snap.
- Drawers/shelves 379: scroll while selected V dimension edits quantity only in that gap; Enter confirms/Esc removes preview copies. Shared blocking shows all shelf-segment dimensions; partitions only active orientation, no mixed clutter. Click all in opening, double one; 384 Shift preserves individual units, Shift+double narrows clicked opening. Cabinet absorbs children HUD. Partition click group/double panel; preserve type scope.
- Tab 383 on Empty includes one/multiple drawer units: native multiobject Edit Mode, actual meshes only, exclude cutters/controls, isolate shared meshes first. Keep Empties selected, record transition at entry (fast Tab independent of timer), restore active/selection, invalidate plan on exit, names only. Isolated part keeps native Tab. Local View rays ignore hidden; rigs move through ferragens with Mesh references for undo, materialized mirrors and native UV correction.
- Free area 377/378: selected cabinet fixes all snap targets; first point/HUD/B ignore outside geometry without hiding scene. Orange 30 px volume/plane like Create. Translate ends at RELEASE, camera keymaps pass between points. One point -> rectangular numeric reference/HUD/G/R/S -> Apply -> front for volumes. Three unordered 3D points form module-axis min/max box; explicit front native-ray highlight, drag handles suspended. Preserve 2D planes. Empty stores orthogonal 8/4 corners; numeric handoff without support reinterpretation. Undo/load/save/unregister clear.
- B snap base uses CURRENT geometry, not gesture start. Native cursor restores; `hud_volume.preparar_base_snap` absorbs last motion/accumulated delta without moving wood back. Repeated B never duplicates gap; original backup remains for Esc. Observer runs before native, forwards every event. `KeyMapItems.match_event` polls operators; modal maps have empty idname and cannot match. Internal NORMAL mirror with valid operator copies event fields (new_from_item cannot modal->normal), preserving original shortcuts/modifiers. Remap invalidates; observer/keymap/cache/timer all cleaned, only numeric session ID retained.
- Undo/redo: never query selection/mesh under `_desfazendo`; completion only releases guard, regular timer restores references. Discard old Edit/modal transitions. Hover clears undo_pre, validates `_alvo_vivo`; outline restores only its own changes, including nonactive ordinary mixed selection (358).
- Selection 369: `selecao.objetos_na_camada` restricts click/Shift/door/Tab to native View Layer; outside parent never active. ADDON keyconfig, ordinary native CLICK. `OBJECT_OT_selecionar.poll` refuses outside Object Mode or disabled selecao_por_grupo; SKIP_SAVE props.

## Sidebar and library (365: NODE_EDITOR ArchyBuilderMenu/Biblioteca)

- Tabs 362: measured BLF/font 12/margin 18 overflow becomes fixed full-name dropdown, floating list dispatches `aba`; dynamic prefix. 375: six tabs, Shelves/Partitions unified, DIVISORIAS visual alias, selected owner controls. areas_criacao session per scene stores numbers: type -> volume/points -> count -> optional gap -> other type/Exit; cleanup preserves created results.
- All tabs contextual: no selection only orange Create (Cabinets empty); creating stage fields mirror modal; selected only item controls. No finished-door hinge picker; hardware count/offset. Hinge/Convert stay F3.
- Joint 355: creation/reanchoring blocks geometry HUD/hover, retains chain/ruler/snap; orange create/confirm, own panel without estimate, distance/zero/back/accept/cancel. Right/Esc cancels, Backspace/Ctrl+Z returns, Alt reanchors. No item name/Sync/Auto-regenerate. Full-width Create above text+icon Chain/Reset, stack narrow; value drag/types.
- editor.py owns empty 4.2 gizmo tree, subtype persists role, pointer marker consumed by legacy migration. `executar` sends scene commands; text/drag origin retained.
- Six-tuple layout/draw/event separation. 391 formatting period thousands/comma decimal/MM/CM/M; original buffer/cursor map separate, native preview cache 128. 392 no initial selection, normal Backspace, Ctrl+A/Shift visible text-only selection; Ctrl+Z/Shift+Z/Y bounded local 80, never scene undo. Unitless = configured unit. Black rounded boxes. 373 independent scrolling, fixed tabs/footer, options over bars; `rolagem` distinguishes vertical track from horizontal slider.
- Never hash action dicts. Pool/hide gizmos; Button 2D by icon/occurrence. Fields/chain/ruler retain operator; update properties only.
- Library top strip (`cabinet_layout=2`) or menu (`cabinet_biblioteca_lugar=MENU`, no migration, timer switch); menu levels dropdowns. Unlimited `niveis`; 18 px tabs/font 10/gap 2. Modes/levels one row at every height, gray boxes/light-gray joints/gap 12. Border only during category hover; no navigation halo.
- Background never steals clicks; X/Y wheel. Directional arrows only overflow, no counts, empty branches hidden. Shift+wheel reaches deep levels; hashed scroll keys <=63 bytes. Visible-only proportional photos bounded by width, RGBA8 64 MiB cache/invalidatable index, no redraw file-open.
- Material solid color in OBJECT slot. Group 382 catalog/Ctrl+L preserve handles/hardware/descendants and full selection; only MATERIAL native menu/engine targets filtered. Individual native material editing allowed. Sphere single click does nothing, double paints selection, drag paints target, right quick-paints room then part; preserve gestures.

Validation: [tests](../../tests/CLAUDE.md), current GUI authorization only;
callback exceptions fail even when assertions pass.
