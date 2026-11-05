# Architecture

Keep AGENTS.md and CLAUDE.md identical, in English ASCII, at most 120 lines.
Read the root routing guide; visible interaction also requires the root
design contract and the ui guide.

## Ownership

| Module | Responsibility | Legacy module |
|---|---|---|
| masonry.py | Wall/floor/ceiling surface classification and support | alvenaria |
| rooms.py | Face categories, room UIDs and collection affiliation | ambientes |
| walls.py | Wall association, support frames, guides and placement | paredes |
| wall_selection.py | Native face/region selection and hit testing | paredes_selecao |
| wall_editor.py | Wall editing sessions, 2D view and temporary proxies | paredes_edicao |
| wall_layout.py | Cabinet elevations, gaps, dimensions and layout | paredes_composicao |
| installations.py | Installation catalog, placement and reversible cuts | instalacoes |
| openings.py | Architectural openings, movement and collision | esquadrias |
| lighting.py | Lights, luminaires and ceiling details | iluminacao |

Cabinet dimensions and geometry remain cabinetry's responsibility. UI
presents and dispatches; do not introduce a second resize or snap solver.
Existing modules may contain their domain-specific widgets and operators;
directory organization alone does not require extracting every UI function.

## Imports and compatibility

The root entry point owns explicit loading, immediate legacy import aliases,
dependency wiring and registration. English and legacy Portuguese module
imports/attributes refer to the SAME owner object. Preserve functions,
placeholders, stored names, class names, operator IDs and property schemas.
Call other sectors through their module references; never capture exported
functions or add a second loader. Reload owners before their consumers.

## Data, editing and placement

- Face categories are persistent FACE attributes with stable numeric IDs
  and UID mappings. Preserve existing categories; new faces start unassigned.
- Temporary BMesh wrappers are valid only during their current edit session.
  Release them before undo/save/load/unregister; adding a layer can invalidate
  wrappers, so renew the capture before painting.
- Scene state across undo is names and numbers. Do not keep scene IDs or
  BMesh wrappers in global caches. Drawing reads precomputed numeric data.
- Preserve native ray casting, selection, Local View and snapping.
  Restrict selection/preview to the intended object, face and active area;
  hidden geometry or an unrelated scene object must not become the target.
- Temporary 2D proxies, wire display, colors, snap settings and isolation
  restore previous state on exit, undo, save/load and unregister.
- Wall layout consumes the cabinet envelope owner and its oriented resize
  contract. Open doors/handles are not the cabinet placement envelope.
  Redistribution remains explicit rather than a side effect of moving.
- Placement uses actual supporting faces and shared fitting constraints.
  Validate reassociation before writing; transfer only the installation's
  own reversible cut and preserve its components.
- Depsgraph callbacks invalidate caches; heavy extraction belongs to the
  stable timer, never hover/draw. During undo, defer selection/mesh work.
- Installation images remain in the existing fotos/instalacoes data tree.
  Resolve from the add-on resource root after moving installations.py,
  not from its new architecture directory.

## Validation

Read tests/AGENTS.md from the root. Relevant suites: alvenaria, ambientes,
paredes, paredes_selecao, paredes_edicao, paredes_composicao, instalacoes,
esquadrias, iluminacao, hud and gaveta. Cover category preservation, support
UIDs, independent cuts, 2D cleanup, undo/redo and cabinet-owner dispatch.
Use temporary scenes and resources; never change the open project or real
library. GUI needs current permission; follow root delivery checks.
