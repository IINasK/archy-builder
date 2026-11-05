# Doors

Keep AGENTS.md and CLAUDE.md identical, English ASCII, at most 120 lines.

## Ownership and routes
Leaves, opening bounds, coverage, association and reapplication live here.
Creation: [assistant](../door_assistant.py); rigs: [hardware](../hardware.py); handles: [handles](../handles.py).
Sliders/corners: [controls](../../ui/door_controls.py); shared [fronts](../fronts.py) and [contract](../../../FRONT_GEOMETRY.md).
Read [UI](../../ui/AGENTS.md), [interface archive](../../../docs/reference/interface.md),
[integration archive](../../../docs/reference/integration.md) and [tools](../../../tools/AGENTS.md) as relevant.
Legacy addon.portas and canonical doors are the SAME owner module; retain Portuguese functions, UI text, IDs and placeholders.

| Task | Entry point |
|---|---|
| Opening/coverage/leaves | _preparar_vao_portas, _calcular_folhas_portas in __init__.py |
| Assembly/resize/mirror | _aplicar_portas, atualizar_do_conjunto, espelhar_porta |
| Creation/replacement | OBJECT_OT_apanhar_vao_portas, OBJECT_OT_portas_parametricas in ../door_assistant.py |
| Rig/closed pose | _montar_ferragens, _matriz_fechada, _definir_abertura in ../hardware.py |
| Handle/model/Alt | posicionar_puxador, OBJECT_OT_arrastar_puxador in ../handles.py |
| Shared contours | preparar, bordas, lugar, transportar in ../fronts.py |

## Creation, selection and presentation
- Free-plane creation uses creation_areas: four rectangular corners and numeric frame/dimensions, entry at FOLHAS, no second solver.
  Zero/inset coverage and E belong to the owner. Back never reopens old point capture; execute validates rigid references and measurements first.
- Delete observation persists across file load. Indexed hardware disappears only with its leaf; other scenes/layers, common children and referenced IDs survive.
  Native hardware selection respects hidden state and Delete; undo restores the assembly.
- New backs never enlarge support bounds. atualizar_do_conjunto updates ONLY leaves/supports; cabinets coordinate doors -> drawers -> shelves once.
  atualizar_portas_do_conjunto(conj, sistemas=True) is compatibility only; sistemas=False maps to internos=False. Never coordinate internals here.
- Curvature requires explicit add-on control, including adoption. Tab modeling and contour measurement never activate it.
  Preserve manual modeling AND controlled-curve resize regression coverage.
- Creation/replacement uses TWO native clicks through AssistenteDoVao._iniciar_snap_nativo and shared _referencia_do_par; read vertices once.
  Normalize bounds; cobertura_*_e is a thickness fraction: 1 overlay, 0.5 partial, 0 inset; hinge automatic. RESPIRO_PORTA_MM stays 2 mm, never flush.
- Mixed-support sliding asks inset/frame; nonstandard dimensions need confirmation. Four-point API stays compatible, outside the UI gesture.
- Wizard: leaves -> opening -> edge (lift-up CIMA) -> scroll quantity -> mouse-Y margin -> pistons.
  AUTO uses twice closed height when open, Y only rises. Green acceptance stays in viewport; reposition = two clicks.
  No popup_menu: its opening release could answer it.
- Shift+G offers door group while retaining native groups. Descendants must be visible/selectable in the View Layer.
  Hide the complete assembly natively, including handles/rigs; H/Alt+H/undo remain native. Click selects door group, double-click leaf, never cabinet.
- Independently selected doors show white contour, yellow opening, wires/slider per leaf.
  Alt drags only two recomputed CANTOS_DO_GESTO corners, never persisted, using native cursor/cabinet_mover_canto_porta snap.
- Mirror stays in context menu: reverse swing, entire zigzag chain, sliding travel or lift-up/pistons; handles follow, wood never mirrors.
  No sidebar Reposition/Front/Mirror rows.
- Sliding: one full-opening track per leaf; one leaf = half opening width. Width follows sidebar L; no added overlap/perimeter-gap controls.
- Covering panels needs a frame rebuilt with its 15 mm panels; ask base (none = zero plinth) and track.
  Heavy = aluminum/18 mm leaf; light = routed channels/U/15 mm leaf, no fascia. Include frame in envelope/HUD.
- Leaves stay panel or aluminum frame (23 x 10 profile, 5 mm infill). Zigzag: 2-8 alternating leaves, chosen side first, handle only last.
  Native joint components belong to leaves, one slider. Photos close ALL doors, including corner/sliding/zigzag, without changing hinge side.

## Parameters, geometry and rigs
- Parameters live on Scene, not operators. cabinet_portas EXEC_DEFAULT executes, INVOKE opens dialog.
  _parametros_portas_da_cena covers ALL _PARAMETROS_PORTAS; CHAVE_FOLGAS_PORTA stores margins in thickness units.
- Front resolves automatically and is saved resolved. Centred leaf matrix_basis is under its group; measure with _matriz_fechada. No hide_select.
  _conferir_ferragens checks rigs; the timer restores helper per-layer visibility lost by append/presets.
- Straight hinges use user's model/tables, not rebuilt geometry. _calco_rig puts support on actual face; the cup must fit the leaf.
  Partial coverage keeps bounds/edge. Oblique raycast/four coplanar corners preserve the prism, never substitute a rotated AABB.
- Old fittings/rigs update once in timer, preserving leaf/opening/handle. Equal swing bounds/leaves/rigs never rebuild on joint reset.
  Check poses/manual offsets; refresh missing/old rigs only.
- Load a rig asset ONCE per assembly. Object.copy preserves parents/inverses and remaps IK/modifiers/drivers.
  Source is THIS assembly, never modeled scene rigs/global RNA caches. Batch removal preserves shared users.
  Deduplicate Mesh by native equality AFTER checking attribute names/domains/types: incompatible attributes crash 4.2; Tab can preserve asset markers.
- Reverse modeled curved fronts by reference, keeping world vertices; _vao_inverso must not displace them. Inversion puts hinges outside/opening inward.
  Copy nested ID props RECURSIVELY before replacement: shallow copies/stale accesses could crash 5.2.
- New leaf/track text reaches _carregar_portas_na_cena and _valores_portas in ../../ui/sidebar.py; existing UI/functions remain Portuguese.
- Hardware appears as real-piece wireframe only during creation/selection: click all of type, Shift adds, Alt controller, double-click native piece.
  Group Tab moves whole parts through the hinge root, holes/IK/spring included; partial modeling stays native. Numeric Mesh references recover undo offsets.
  Materialize mirrors on unique copies before Tab, in stack order, avoiding clipping that pins half a hinge. Handle edits preserve Mesh/UVs.
- Handle double-click isolates it; isolated drawers also allow a single click on their own handle.
  A sole selected leaf fixes native ray target; otherwise use the visible HUD ray. Hidden/blocked leaves are excluded.
- Alt stays on the owning group's edge with native line snap. Reject occupied targets BEFORE mutation using actual anchor/length.
  Preserve neighbours/profiles, allow separated/opposite-face handles; Esc restores legacy state.
- Place handles by panel PROPS, never deltas. Profile is horizontal except wardrobes; keep imported placement rules, user models, moving ends/backs.
  Edge-model holes never scale. Swing/sliding switches use closed pose and parameterized outer X edge; other edges/mode switches stay stable.
  Hinges/handles share the same screw asset.
- Leaf front is LOCAL +Z, never cabinet -Y. Mirror preserves opening parity; angular-arm CUSTOM aiming migrates in timer without rebuilding Mesh.
  Hinge side uses CLOSED-leaf X, not cabinet X; factory models stay protected.
- Fronts use semantic INT FACE/EDGE attributes and numeric Mesh cache, invalidated outside drawing on Mesh/undo.
  porta_linha_frente only migrates old data; indices never govern contour/resize. Handles/Alt/preview share normals/edges; profiles follow curves.
  Old fractions migrate once. Resize reanchors by tangent without replacing modeled vertices/faces.

## Validation
Read [tests](../../../tests/AGENTS.md): doors, handles, fronts; consumers importing, hud, sidebar, drawers.
Preserve modeled/controlled curves, native Tab/undo, owner patches and reload. Fixtures only; GUI needs current permission.
