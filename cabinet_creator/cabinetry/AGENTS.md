# Cabinetry

Keep AGENTS.md and CLAUDE.md identical, in English ASCII, at most 120 lines.
Read the root routing guide and the specific package guide when present.
Visible changes also require the root design contract.

## Ownership

| Module/package | Responsibility | Legacy module |
|---|---|---|
| panels/ | Panel mesh, thickness, dimensions, edit absorption | chapas |
| cabinets/ | Cabinet envelope, Empty/Collection, resize coordinator | modulos |
| doors/ | Door leaves, opening, coverage and assembly | portas |
| drawers/ | Furniture drawers and shared native opening assistant | gavetas |
| shelves/ | Shelves, gaps, quantity and individual edits | prateleiras |
| partitions/ | Vertical partitions and segmentation of internal systems | divisorias |
| shapes.py | Deformation and modeled-shape references | formas |
| fronts.py | Shared front-edge and normal references | frentes |
| backs.py | Back panels, grooves and depth association | fundos |
| welding.py | Joints, anchors, adjacency and distance constraints | solda |
| hardware.py | Hinges, rigs, screws and sliding hardware | ferragens |
| handles.py | Handle models, placement and anchors | puxadores |
| door_assistant.py | Door creation and placement workflow | assistente |

The sidebar is UI, not a furniture drawer. Estimates and external adoption
belong to integrations. Each domain continues to own its geometry.

## Imports and compatibility

The root owns the explicit canonical/legacy module map, immediate legacy
import aliases, load order and registration. Old and English imports must
return the SAME owner object; preserve Portuguese functions and placeholders.
Do not add facades, copied exports, service registries or duplicate loaders.
Tests patch the owner module, including through legacy addon attributes.

Import-time inheritance matters: drawers must load before shelves,
partitions, backs and consumers of AssistenteDoVao. Hardware must load before
handles. Reload these owners before their dependants and rewire afterwards.
Do not split package implementations solely to shorten __init__.py.

## Geometry and data contracts

- Panel axes remain X width, Y length, Z thickness. Rotate orientation;
  discard sz. Keep existing positive free-thickness behavior.
- Preserve ID properties, RNA names, enum values, attributes, UIDs, class
  identities, operator IDs and modifier names stored in existing projects.
  An English filename does not authorize translating any of these.
- Use world geometry and the existing parent-aware center setter. Update
  the view layer before reading matrix_world after changing transforms.
- Keep modeled Mesh IDs and edits; stretch existing meshes instead of
  replacing them. Never write a Mesh that is in Edit Mode.
- Cabinet resize coordinates doors, drawers, then shelves once each.
  internos=False preserves restored internal fittings. The old door update
  API remains compatibility only, not an internal coordination entry.
- Partitions validate every affected opening before mutation. Shelves and
  drawers retain ownership of the resulting independently editable groups.
- Native snapping and the shared drawer assistant remain shared. Do not
  scan meshes in Python during clicks/drags. Restore cursor and targets on
  confirmation, cancellation and error; preserve a single undo operation.
- Native translate orientation receives axes in rows: transpose group
  matrices that store axes in columns. Keep reflected-group parity.
- Front edges/normals use the existing semantic attributes and numeric
  cache. Invalidate outside drawing; preserve modeled and controlled curves.
- Keep furniture collections, parent relationships and UID associations.
  A duplicated preset name is not a reliable identity.

## Resources and lifecycle

Hardware models still come from the existing ferragens data directory;
library and photo data keep their existing compatible paths. New code paths
must resolve those from the add-on root, not the moved module's directory.
Do not rename .blend contents or library files as part of moving code.
Finished modal operators release scene IDs; unregister removes all native
snap sessions, timers, handlers, gizmos and transient state.

## Validation

Read the root tests/AGENTS.md. Relevant suites: armarios, portas, gavetas,
prateleiras, divisorias, fundos, formas, frentes, puxadores, solda, hud,
operadores, organizacao and estrutura. Verify modeled geometry, resize,
undo/redo, shared assistant inheritance, owner patches and reload identity.
Use temporary scenes/fixtures; never write to the real library or change
the open project. Follow root delivery checks; GUI needs current permission.
