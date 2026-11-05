# Drawers
Keep AGENTS.md and CLAUDE.md identical, English ASCII, at most 120 lines.

## Ownership and routes
Furniture drawers: front, box, slides, opening, travel and per-unit edits.
The sidebar is [sidebar.py](../../ui/sidebar.py), not this package.
AssistenteDoVao also serves [shelves](../shelves/AGENTS.md) and
[partitions](../partitions/AGENTS.md): fix shared gestures here, never copy.
Handles/front references: [doors](../doors/AGENTS.md), [fronts](../fronts.py),
[contract](../../../FRONT_GEOMETRY.md). Legacy addon.gavetas and canonical
drawers imports are the SAME module; retain Portuguese APIs and saved IDs.

| Task | Entry point in __init__.py |
|---|---|
| Calculation/assembly | calcular, montar, criar_gavetas |
| Front reference/depth | referencia_do_vao, pontos_internos_do_vao, profundidade_disponivel |
| Group/unit/height edits | editar, editar_individual, normalizar_alturas |
| Follow cabinet body | acompanhar_redimensionamento, limitar_medidas, _adaptar_espaco |
| Shared gesture/snap | AssistenteDoVao, OBJECT_OT_marcar_ponto_vao |
| Travel/slider/Alt | definir_abertura, OBJECT_OT_abrir_gaveta, OBJECT_OT_arrastar_ponto_gaveta |

## Creation and shared native gestures
- creation_areas keeps a rectangular free-volume box from one click, using
  shared HUD/snap/B. Applying delivers numeric frame/diagonal/depth directly
  to AssistenteDoVao at QUANTIDADE; drawers continue to the slide choice.
  Shelves/partitions/backs use the same bridge, with no invented supports.
- Internal creation coordinates type, optional gap and continuation through
  creation_areas; finish shared snap/modal before asking the next question.
  Drawers/backs retain their existing completion flow.
- Three unordered points define min/max in cabinet axes -> explicit front
  face click -> quantity -> slide. Backspace reopens front/third point.
  Use native ray hover, no inferred diagonal orientation. Old two-support
  editing and 2D-plane contracts remain compatible.
- Native translate/snap runs only from point PRESS until RELEASE confirms.
  Between points, native MMB/trackpad/keymap navigation remains available,
  including walk/fly; Shift+scroll navigates even at the quantity stage.
  Preserve the existing continuous door/joint protocol.
- Applied volume also asks front: permute axes while preserving all eight
  corners/dimensions. Continued shelves/partitions reuse that oriented area.
  Depth comes from the creation box, not another capture gesture; legacy
  editing and Alt retain their existing depth contracts.
- B during three-point capture opens native vertex/edge-midpoint translate;
  key release does not confirm, click does. Existing click/drag retains
  release_confirm and the camera remains free between points.
- Capture the SELECTED cabinet and descendant names before first translate;
  without selection, the first valid point fixes the target. All subsequent
  points use alvos_snap and native closest_point_on_mesh within that target.
  Reject external names; never swap target from current context.
  raio_no_modulo serves free-volume first click using native visible-member
  BVHs. Restrict area HUD/B too, without restricting unrelated HUD behavior.
- Restore cursor and hide_select on confirm/Esc/error without revealing
  hidden objects. Do not scan mesh vertices in Python during clicks/drags.
  Native undo stays a single operation. translate.orient_matrix expects axes
  in ROWS: transpose a group Matrix that stores axes in columns.
- Alt edits two front corners plus depth with the same native cursor snap;
  Esc restores cursor AND snap targets.

## Bounds, selection, editing and resize
- backs.py identifies a matching back by UID within the cabinet at depth
  confirmation. The limit is its inner FACE, not centre; that owner handles
  hitbox association, this domain keeps calculation/slide/assembly.
- Slides remain full-size blocking geometry pending a definitive model.
- Click selects all drawers, double-click one; only that scope gets HUD
  lines. The slider follows the front and stays visible. A selected cabinet
  absorbs its children into the cabinet HUD.
- After isolating a unit, Shift+click adds units from the same opening;
  Shift+double-click reduces only that opening and preserves external
  selection. Plain click returns to group; Tab edits chosen units only.
- Direct double-click isolates a handle. An already isolated drawer also
  allows a single click on its own handle; active accessories stay selected.
  Other drawers/groups, ordinary objects and walls retain their own scope.
- Before internal capture ask Esconder portas? through existing routing.
  Yes uses visibility.definir(PORTAS), native wire display with snap.
  The fixed eye/pencil strip follows the tab and includes boxes/slides/
  handles; native H/Alt+H stay independent. SKIP_SAVE portas_verificadas
  avoids repeating on continuation. Surface rays pass faded parts while
  alvos_snap retains their geometry and visual-group extras.
- Resize first transports from the near face without growing. Consume the
  actual free space between supports before shrinking, using native bounds
  outside HUD. Adapt only when necessary, down to physical minimum; restore
  choices on growth and retain smaller individual widths.
  sincronizar_margens serves drawers AND shelves after transport.
- References preserve group Mirror reflection: normalize matrix columns,
  never convert to quaternion. Direct edits preserve selection; Esc restores
  dimensions. Actual PARENT is authoritative, not an old preset name.
- Curved fronts and proportional heights remain supported. Each shared edge
  transfers height to/from its neighbour at fixed total; outer edges anchor
  the limit. A single drawer uses its own opening.
- Per-unit double-click exposes existing L/A/P, Abaixo/Acima, front/slide/
  setback/handle fields; group changes all. Travel/material are per unit.
- Preview only parameters/contour; assemble ONCE on confirmation.
  Creation after partitions calls particionar_grupo; a rejected opening
  must not leave a partially created drawer system.

## Validation
Read [tests](../../../tests/AGENTS.md). Suites: gavetas; shared gestures/
partitioning: prateleiras, divisorias; selection/sliders/children: hud,
operadores, portas. Use temporary scenes, check undo/reload owner identity;
never change the open project or real library. GUI needs current permission.
