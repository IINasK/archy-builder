# DESIGN.md - designing UI for Archy Builder

Keep this file at most 200 lines. Read it before adding any visible screen, button, field, section or icon. Structural tests protect intentional
decisions; change their contract only for an authorized design change. Current rules below supersede archived layouts in [history](docs/HISTORY.md)
and [reference](docs/reference/interface.md). UI text and annotations use English; identifiers and saved data stay compatible.

## Editor, ownership and widgets

The UI is the native `NODE_EDITOR` subtype `ArchyBuilderMenu` (365), saved in `.blend`. Toolbar, N-region and overlays are off; the native header
keeps its editor selector. GPU and native gizmos consume the existing layout, without `UILayout`: no `layout.prop`, `layout.operator`, `row()`,
`column()`, `grid_flow`, `ui_units_x` or `scale_x`. `VIEW3D_PT_archy_builder` remains unregistered. An owned empty node tree enables 4.2 gizmos
without using the user's nodes. Scene commands use `editor.executar`; text/drag stay in the originating editor.

Layout `_widgets_gaveta(context, largura, altura)` returns exactly six elements: `(x, y, w, h, rotulo, acao)`, in region pixels, bottom-left origin.
`acao` is None for decoration or a tuple whose first item is the verb. Layout positions, `_desenhar_gaveta` draws, `OBJECT_OT_interagir_gaveta`
dispatches. Never mix them. Append in layout and advance y by height plus spacing; reuse an existing verb. New verbs enter structural `VERBOS` and
`_chave_widget` when highlighted. Generic `_botao_gaveta` usually suffices; decorative actions finish without side effects.

| Element | Height | y step |
|---|---|---|
| Main tab | 29 | top at `altura - 40` |
| Mode tab / segment | 25 | 33 / 29 |
| Measurement | 37 | 43 |
| Operator button | 28 | 34 |
| Section title / label | 23 / 20 | 31 / 26 |
| Category cascade row | 25 | 39 |

Margins: `x = 12`, `w = max(24, min(540, largura - 24))`; horizontal gap 6 px (4 in cascade); button radius 4, fill radius 3; preset `w - 10 == h -
27`; 1 px separator at `y + 31.5`. Reuse metrics rather than inventing new ones.

## Theme, responsiveness and events

Use `_cores_gaveta()` theme `(wcol_regular, fundo)` and inner/inner_sel/outline/text, never literal sidebar colors. `_texto_gaveta` handles fixed
labels; `_texto_cabivel_gaveta` shrinks 12 -> 9 before clipping. Measure with `blf.dimensions()`, never estimated `PX_*` widths. Abbreviate only
names, preserving count suffixes; category cascades have no counts or depth limit.

Divide useful width by `ui_scale`: logical >=480 uses one basic-measurement row and up to three dynamic columns, >=240 two columns, otherwise one.
Assembly `colunas = min(3, max(1, w // 36))`. Initial width fits L/A/P on one row (`LARGURA_MEDIDAS_EM_LINHA` times scale + 2), capped at half the
viewport. `_LARGURA_MAX_GAVETA` is 564 px, never below initial width. Since `Area.width` is read-only, `_limitar_largura_gaveta` corrects after
resizing via timer/native area move, never a blocking modal. Widgets end at `min(largura - 12, 552)`. Controls/library scroll independently, theme
scrollbar only on overflow; proportional thumb, track click, drag, wheel/touchpad; Esc restores scroll. Headers/divider/footer stay fixed;
options/lists draw above scrollbars.

Use native `GIZMO_GT_button_2d` for icons over GPU rectangles; adjust matrix_basis for alignment. Pool/hide/reuse gizmos: removing/rebinding on redraw
crashes `WM_gizmomap_tooltip_init`. Pool Button2D by icon/occurrence because its symbol is fixed on first draw. Keep operators bound to fields; update
props/tooltips. Invisible `VIEW3D_GT_campo_gaveta` owns rectangular hover; exclude the icon disc from its hit area. Combine icon/rectangle highlight;
never duplicate geometry between drawing and hit-testing. Never hash actions containing dictionaries.

Any enabled button uses `_chave_widget`/`_glow_gaveta`; disabled operators are gray, without halo/click. Draw halo before body; set its own
`blend_set('ALPHA')` after BLF. Every path restores blend NONE and scissor state. One `_animar_realces` timer at 60 fps, self-removing; no second
animation timer. Persistent click capture uses Gizmo/test_select, never a modal; modals are transient interactions. Questions route through
`_perguntar`/`cabinet_responder_pergunta`: viewport popup, menu black answer box below action, library question in its strip. Never direct
`popup_menu` in background. Modal/question buttons, including icons, trigger on RELEASE (`OPERADORES_NO_SOLTAR`); press-started native operators wait
for release.

## Selection, geometry HUD and numeric editing

Selection decides scope; no extra Individual/Group editing selector. One click selects a group, double-click an individual part; Shift adds/removes,
Shift+double reduces only that group and preserves outside selection. Empty selected means group. `_itens_da_selecao` shows all selected scopes;
closest target wins, only its item highlights. Active item lines are +40% thick, minimum +1 px, with multiple items. Common objects keep native CLICK;
group interception is Object Mode only. Hide native outlines only for add-on groups/leaves and restore only what the add-on disabled, including
save/open/unregister and mixed ordinary selections. Origins follow a separate Hide/Show option, default hidden for groups, respecting manual
per-viewport settings. Support dots and corner guides are independent, default on; hidden dots are absent from hit-testing too.

Cabinet HUD is always the envelope box: eight corners, twelve edges, A1/A2/A3, including L/diagonal/curved/tilted shapes and Tab edits. No group
P1/P2/R/arcs or shape inference. A1/A2/A3 resize the box. Individual panels show their actual face edges/angles A1..An in HUD/menu, E from
corresponding skins. Distinct skins use both real structural boundaries, not an extruded plan/nominal box; no internal triangulation dimensions.
Transverse displacement >E has its own low-edge label (e.g. A6). Individual angular edits never propagate to neighbors/cabinet. Arcs follow actual
vertex/sides, about 26 screen px and <=1/4 shorter side. Click types, drag rotates; preserve E/UV/cutouts. Door contours remain per leaf. Front/handle
curves use actual segment tangents, including Alt; see [fronts](FRONT_GEOMETRY.md).

Six face-center dots (2 px, hover 3, UI-scaled, larger hit target) move a face with its opposite fixed. Box arrows/dots use native cursor translate,
initially without snap even if global magnet is on. B chooses native vertex snap/base; keep shortcuts and native displacement input (`50mm`). Before B
absorb the latest movement, keep current wood, accumulate offset once and preserve original Esc/ undo reference. A passive native-keymap observer
forwards all events and stores only numeric session ID; remove observer/keymap mirror/cache/timer on exit. Drag displays resulting A1/A2/A3; click
types absolute dimension. Esc restores geometry/cursor/selection, confirmation is one undo. Nearest arrow corner stays fixed; E grows away from that
corner. Hide HUD during native G/R/S. Shared multi-item editing asks each pending item for its fixed corner, blinking twice; last choice opens one
value, each item keeps its anchor; Esc restores all.

Text uses one `_tecla_no_texto` core: cursor at end without auto-selection, normal Backspace, Ctrl+A, Shift+arrows/Home/End and click/Shift+click
selection. Local history <=80 edits per field handles Ctrl+Z/Shift+Z/Y without scene undo; new writing clears redo. A typed operator continues the
expression; click inside moves cursor, outside confirms. `_arrumar_texto_medida` retains native parsing including `500 + cm` and `51cm00`. Numeric
formatting retains the existing period thousands/comma decimal convention and MM/CM/M, without artificial zeros: `.1 -> 0,1 mm`, `12345.67 ->
12.345,67 mm`. Original buffer and cursor map stay separate. Unitless terms use configured default: `100 + 50cm` gives 600 mm, 150 cm or 100,5 m;
multiplication factors remain dimensionless. Preview cache 128 text/unit entries; incomplete input is quiet. Counts/names/angles/pixels keep their
types. Black rounded box uses scaled 4 px radius. Fixed screen arrow cap `COMPRIMENTO_SETA_HUD`; labels outside faces, separated when overlapping,
hidden below `FATOR_ROTULO_HUD` except active. Dialogs/messages remain inside viewport.

## Contextual tabs, creation and native editing

No selection: only orange Create action (Cabinets empty; creation is library). Creating: show each reached wizard stage and the same clickable
viewport answer. Selected: only that item's owner controls; inactive-but-unselected does not count. Automatic hinges/conversion stay out of finished
door controls (F3 remains). Shelf/Partition share a tab and numeric creation session: choose type, volume/ points, quantity, optional gap, then other
type in same area or Exit. Subtract thickness at crossings; shallower partitions may keep a gap or fill left/right. Tabs use full/abbreviated measured
labels, then a fixed dropdown if neither fits; floating list handles events first, closes on choose/outside, resets tab scroll and restores tab row
when widened. Legacy DIVISORIAS remains a visual alias.

Volume creation uses three unordered points -> module-axis min/max rectangular box -> explicit front-face click -> quantity. Native translate runs
only through RELEASE; camera/navigation stay free between points. Free volume/plane is orange, 30 px: one placement click, numeric HUD/centers/G/R/S,
Apply, then front for a volume. Backspace returns, Esc cancels; 2D door/back planes stay 2D. Selected cabinet fixes snap scope; otherwise first valid
point fixes it. No external mesh scans/scene hiding. Front choice suspends drag handles. Temporary Empty stores 8/4 orthogonal corners; deliver
numbers without reinterpreting supports. Clear sessions on undo/load/save/unregister without deleting confirmed results.

Tab on group Empty uses native multiobject Edit Mode on real meshes only, including one/multiple selected drawer units; exclude cutters/rig controls
and isolate shared meshes first. Record entry immediately, store names only, preserve Empties and restore selection/active on exit. Shelves in global
scope propagate on the SAME Mesh for native undo; individual scope edits one. Quantity inherits a selected reference or asks beside the pointer when
mixed types need one; Esc cancels. Quantity dragging previews a number, builds on release.

## Domain controls and visibility

Doors: two opposite corners determine gap/coverage/automatic hinge; invalid second corner can be retried. Nonstandard coverage asks confirmation.
Wizard proceeds leaves -> non-inferable opening -> hinge edge -> count -> 100 mm default margin; lift-up adds piston count/automatic placement, Y only
raises within stroke. Right-click goes back, Esc cancels. Standard full/half/inset coverage leaves 2 mm; no perimeter-gap control or redundant
sliding-overlap control. Finished sections: Door L/A/E, Leaves with compact count/gaps, Position, Rails or Frame, Opening. Sliding: inset from inner
corners, framed from outer; mixed asks. Frame uses 15 mm boards, base/plinth/header and contributes to cabinet envelope. Heavy rail uses aluminum;
light uses routed channels/U, 15 mm leaves, no header. Leaf choice: Panel/Aluminum frame with independent thin-panel material. Zigzag: 2..8
alternating leaves, one last-leaf slider/profile handle, chain reverses on mirror. Mirror Door is native context action for group/leaf; lift-up
includes pistons, sliding reverses travel, handles follow, wood is not mirrored. No redundant positioning action row.

Hardware previews/selection use real wireframe, creases >30 degrees for imported hinge rig, asset JSON cache and GPU batches; no placeholder boxes.
Native edit/ Delete remains available. Click selects all hardware of type, Shift adds, Alt moves count/margin controller, double isolates one part;
drawer rails stay drawers. Door sliders sit 30 mm before closed leaf base, rail 13 mm, knob radius 12 mm, 40 mm/12% end inset, world dimensions capped
at 2 px/mm, values hidden below 7 px; sliding rails stagger 40 mm. Only knob hits; no jump when grabbed off-center, right opens, Esc/right restores.
Cabinet selection hides separate door HUD.

Drawers: selected group edits L/A/P/count, fronts, rail and handle; individual has L/A/P and above/below without group count. Normalize Heights is
explicit for >=2, preserving opening/gaps/choices. Consume support clearance before shrinking internals and restore original choices when space
returns. Preview while dragging, rebuild once at confirm; Esc restores parameters/meshes/material/opening/selection. Shelves: E fields bottom-up, each
moves its shelf (top moves last). Center Spacing is explicit; one unit centers only neighboring gaps, group distributes all. Delete never moves
others; native G/Tab refreshes fields. Local copies/quantity affect only the interval between external supports, preserve active on reduction, zero
removes that interval. Partitions use E fields left-right and split crossed systems without changing shelf heights. Shared blocking shows relevant
segment dimensions.

Visibility is a fixed 38 px strip, label plus 36x30 eye/pencil, only for compatible selection; no blank reservation otherwise. It follows tab groups
with aggregates, never isolated hardware/handles. Native WIRE, white/.22 opacity retains snap and independent H/Alt+H; surface rays pass through.
Pencil includes/excludes with native left/right selection, Enter/pencil accepts one undo, Esc restores. Store extra/ excluded UIDs without
reparenting. Restore temporary appearance on save/unregister, reconcile undo in timer. Hide doors? Yes uses this same group; no visible doors skips
it.

Handles: create orange/top, model portraits; single follows owner, double isolates, including after drawer isolation before wall scope. Alt moves only
within own group, line then point, scroll k/(n+1), right returns. Occupied/overlapping effective intervals on same edge/face retain last valid
position with header warning; no replacing hidden handles; opposite face/separate intervals allowed. Esc restores even legacy overlap. Profile/edge
assets retain modeled holes/chamfers/rounding; move straight sections, not whole-section scale (thin-profile fallback retained). Profile wood cut
34.81 mm, J fallback 30. Edge model 1.1 mm top, 20 front roll, 13.4 rear tab, ~4.3 holes; 80 length/64 centers, 144 ->128. Screws 3.5x14, head 5.78,
top .876 above surface; wireframe only top circle/cross. Preserve existing object names as saved contracts.

## Library, welding, rooms and delivery

Library: top `NODE_EDITOR` spans menu/scene (horizontal split then lower vertical), initial height 180; optional MENU placement below internal
divider, switched by timer. Dropdown level lists float and win events. Strip has modes/levels in one row, 18 px category tabs/font10/gap2, gray boxes,
2 px light-gray dividers, 12 px group gaps; outline only on category hover. Unlimited levels, no counts/empty branches; wheel and overflow-only
directional arrows; Shift+wheel deeper levels. Proportional photos, visible widgets only, RGBA8 LRU 64 MiB, catalog path/mtime cache, no redraw
`.blend`. Right-release photo/name menu Insert/Edit/Lock is popup exception; respect protection. Material single click does nothing, double paints
selection, drag paints target on release, right quick-paints room then body/doors/all. Preserve hardware/handles in group painting and native Ctrl+L,
filtering only MATERIAL targets. Portraits share `_lado_retrato`, 40..128 slider, shrink only to fit three. Factory models stay locked.

Welding: own orange creation panel, full-width Create above Chain/Reset with icon/text, stack narrow. Native snap; numeric preview,
distance/zero/back/accept/cancel, Alt reanchors, Backspace/Ctrl+Z returns, Esc/right restores. Geometry HUD blocked only while creating/reanchoring;
chain/ruler stay active. One record/vertex pair/wire per unordered object pair. Persist local 3D gap/origin; new zero uses final fixed anchor, legacy
origins survive. Active part decides detach/reset, never record direction. Validate impossible/duplicate/thickness constraints before any write. No
silent nearest replacement for deleted/ambiguous anchors. One final geometry undo.

Masonry: dedicated tab, first orange Create only for undefined mesh, mixed selection ignores existing supports. Edit first/30 px/orange, then
Wall/Floor/Ceiling with eye 28 px at right. Native faces determine types; Enter/confirm reads current selection, Esc cancels, other types preserved.
Eye shows all types/names/outlines; editing forces visibility. Installations reuse library cascade/grid/photo cache with separate trail; drag starts
in origin, preview highlights full support. Wall/floor/ceiling all valid for doors/lights, ceiling lowering retains its own support. Right-drag reuses
placement, confirms on release, preserves assembly/model/opening/light energy and transfers only its own cut; Esc/invalid/exception restores.
Undo/redo invalidate numeric timer caches.

Cabinets tab retains equal-column Edit in 2D/Edit Categories, 30 px, 6 gap; full-width red-theme Detach Masonry below. Room name applies on
RELEASE/UNDO; only all-same toggles off, mixed applies, No Category always clears. Color square only edits color. Eye by Exit toggles labels/colors
without selection changes. Native Shift face/Ctrl path/ Shift+Ctrl fill, automatic category/connected plane. 2D category editing retains view,
proxy/isolation/session, clips hits/colors to active area but classifies whole native faces. Existing faces keep category; truly new faces start zero.
BMesh identities are transient, refreshed after FACE-layer allocation and cleared before undo/save/load. Projection-depth bias only, restored even on
errors; never move mesh for highlighting.

Defined masonry attachment takes precedence over legacy bounded 2D fitting: explicit marked support only, wall uses cabinet back, floor base/upright;
ceiling reference only. No size/occupancy rejection or forced resize; native G stores offset, zero returns to support, room UID moves cabinet
Collection. Legacy 2D sessions retain Local View and restore state, exit on orbit/Walk/Fly, preserve pan/zoom. A1/A2/A3 remain visible while resize
hides neighbor distances; A3 callout separate from offset. Guides dashed 10/40 mm, 70 mm labels hidden <7 px; 12 px plane magnet, 16 px corner/7 px
circle, Alt whole-side snap within 24 px, Ctrl unchanged. Frame-aware envelope, no open leaves. Library preview from indexed `caixa`; deferred load on
release, max width/height fit 10 mm default (zero off) only in bounded legacy placement, preserving E/depth/preset.

Outliner room Collections are the estimate source. Room list expands inline, Other opens black text box, applies to all selected cabinets. Estimate
.txt is last Options action on release, native Save As, saved count/issues visible 30 s; read actual evaluated body/doors/hardware/materials, missing
data stays pending. No redundant Sync/Recalculate, clipboard export or ERP language. Before delivery run full harness, intentional snapshot review,
190/320/564 widths and light/dark themes; increment version. Report actual GUI checks separately: headless/GPU evidence does not establish physical
interaction.
