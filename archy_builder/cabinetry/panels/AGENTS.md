# Panels
Keep AGENTS.md and CLAUDE.md identical, English ASCII, at most 120 lines.

## Ownership and routes
Panel mesh and dimensions live here. Individual shapes and derived geometry
use [shapes](../shapes.py), [geometry](../../core/geometry.py) and
[fronts](../fronts.py). The envelope belongs to [cabinets](../cabinets/AGENTS.md).
Joints/anchors: [assembly](../../../docs/reference/assembly.md).
Front references: [contract](../../../FRONT_GEOMETRY.md).
Legacy addon.chapas and canonical panels imports are the SAME module;
retain Portuguese APIs, placeholders and persisted names.

| Task | Entry point |
|---|---|
| Create, measure, absorb native Edit Mode | nova_chapa, absorver_malha_editada in __init__.py |
| Mesh, thickness and section | gerar_malha_chapa, preparar_espessura, _esticar_malha |
| Individual edge/angle/offset | definir_aresta, definir_angulo_arestas, definir_deslocamento |
| Shape, resize and actual support | estrutura_hud, _deformar, _apoios_dos_paineis in ../shapes.py |
| Corners and area | OBJECT_OT_calcular_areas and recognition in ../../core/geometry.py |

## Geometry, editing and lifecycle
- Preserve panel X width, Y length, Z thickness; orient by rotation rather
  than scale, discard sz, and preserve the existing free-thickness contract.
  ID properties and RNA remain distinct; never translate saved markers.
- The delete observer is persistent across file load. Count IDs and objects
  per scene; reset on undo/load. Check hardware only in the stable timer,
  never inside the depsgraph callback.
- A selected CABINET always has a conventional envelope: eight corners and
  twelve dimensions. Do not infer group shape/angles or revive old hover
  behavior. Cabinet resize remains box-based.
- Visible dimensions are A1, A2... and E for thickness. L/A/P/R remain
  internal identifiers. Sidebar and HUD use the same semantic dimension
  keys, never the displayed A number.
- Thickness comes from corresponding skins on the local transverse axis.
  Bend/sag is not thickness; ambiguous sections retain nominal E. Resize
  preserves the middle line. Offset larger than E gets its own dimension
  (for example A6), without thickening the wood; drag/Esc restore references.
- For unmatched XY skins, use cached native structural edges and EDGE UIDs;
  do not extrude a profile onto a different back skin.
- Frames also absorb Edit Mode without rebuilding Mesh or changing door
  parameters. Recover stale measurements by native bound_box in the timer;
  already synchronized parts must not repeat mesh extraction.
- Defer inherited scale while a cabinet is still scaled: cabinet absorption
  converts native S through coordinated resize, preserving internal systems.
- Make shared meshes unique before individual edits. Tab stays native;
  update measurements/caches on exit and invalidate on undo. No automatic
  radial deformation or legacy group solver; its existing API remains.
- Handles involved in Tab keep vertices, materials and UVs; refresh only
  numerical contours. Unchanged fronts reuse caches without recognition.
- Group Tab supplies metric UVs where missing (one unit/metre), preserves
  existing maps and uses native Correct Face Attributes.
- Resize references never accumulate deltas: use the native Mesh and restore
  parents and porta_centro_folha BEFORE children. Door/drawer openings follow
  the body map; do not reanchor before restoring. Preserve E along its normal.
- formas.matriz_do_modulo keeps Mirror parity: remove scale magnitudes only,
  never reflections. Use world geometry and parent-aware center setters;
  update the view layer before reading changed matrix_world.
- Partial fronts use the actual support face through closest_point_on_mesh
  and poly_3d_calc, with weights stored once. No entire-box substitution or
  redraw search. Cabinet HUD reads numeric caches, not Mesh/CDT/hull data.
- Corner identity comes from cabinet_canto, not coordinate signs. New joints
  on modeled meshes use cabinet_solda_vertice (INT POINT, u); accept legacy v.
  Individual E never changes other panels; cabinet E has the wider scope.
- Chain-only controls apply up to 5 mm; beyond that show the vertex.
  Snap uses angled corners, curve tips and centre, excluding arc midpoint.
  Area for estimates/F3 is volume divided by E.
- Find neighbours by sibling UID first. Old duplicate UIDs within one parent
  may use the stored name only to disambiguate; distance is the last resort.
- Never replace a modeled Mesh, write while it is in Edit Mode, or retain
  scene IDs across undo. Property updates keep the existing busy guard.

## Validation
Read [tests](../../../tests/AGENTS.md). Suites: formas, geometria, frentes,
hud, operadores; resize with children also portas and gavetas. Check native
Tab, undo, modeled meshes and owner patches after reload in temporary scenes.
Never change the open project or real library; GUI needs current permission.
