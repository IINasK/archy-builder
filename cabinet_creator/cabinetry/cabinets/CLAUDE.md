# Cabinets
Keep AGENTS.md and CLAUDE.md identical, English ASCII, at most 120 lines.

## Ownership and routes
Cabinet body, envelope, Empty/Collection and dependent backs/crosspieces.
Doors and internal systems keep their own owners; individual shapes belong
to [panels](../panels/AGENTS.md). Joints, anchors, rooms and estimates:
[assembly](../../../docs/reference/assembly.md).
External adoption: [integration](../../../docs/reference/integration.md).
Maintenance scripts: [tools](../../../tools/AGENTS.md).
Legacy addon.modulos and canonical cabinets imports are the SAME module;
preserve Portuguese APIs, persisted names and module-based dispatch.

| Task | Entry point |
|---|---|
| Create/group | criar_armario, agrupar_chapas in __init__.py |
| Name and Outliner collection | _nome_livre, nomear_grupo, _garantir_colecao_modulo |
| Envelope/resize | medir_conjunto, redimensionar_conjunto, redimensionar_grupo |
| Resize on a rotated wall | redimensionar_orientado |
| Two-point backs, groove/nailed/internal, hitbox | criar, atualizar_internos, verificar in ../backs.py |
| Legacy backs and margins | adicionar_fundo, guardar_formato_fundo, ajustar_fundo |
| Crosspieces/dependants | adicionar_travessas, ajustar_dependentes |
| Systems after resize/joints/HUD | atualizar_sistemas_do_conjunto |

## Collections, backs and identity
- A cabinet is an Empty plus a Collection with the SAME name from
  _nome_livre, initially at the scene root, containing its panels and doors.
  Doors retain their recorded cabinet name and compatible parent semantics.
- F3 rename opens the existing dialog; chains joining loose parts use their
  existing field. Joints/room affiliation ensure the Collection exists first.
- An unmarked preset may reuse only its exclusive same-name Collection.
  A shared Collection must never become a cabinet.
- Legacy backs are 5 mm, groove setback 15 mm, penetration 7 mm. Backs and
  crosspieces remain dependants. Preserve the source adapter's minimum
  15 mm setback and actual source geometry.
- New backs have their own sidebar context and use two-point native snap
  through AssistenteDoVao. Grooves 6/9 mm use nondestructive Boolean EXACT;
  nailed backs sit outside, internal backs flush (15 mm selects that type).
  Do not automatically migrate legacy backs.
- Internal opening bounds exclude new backs: moving a back does not enlarge
  the support structure. Associate by UID and actual parent only with
  overlap; allow snap within 5 mm or collision with a new back.
- After G/Tab, the stable timer adapts depth/slide without changing height or
  front. Insufficient capacity restores the valid pose and reports it.
  UNPINNED removes association, retains size and ignores future automatic
  reassociation until explicit snap. New behavior is in backs.py; legacy
  behavior stays in this package by contract.
- Partial/orthogonal backs retain margins in EACH plane; never expand them
  to the entire cabinet box.
- Moving an inset base/top extends only the partition that actually touched
  its face. Nominal bounding boxes cannot invent support.
- Islands retain one front (+X/-Y in the photo convention); the opposite
  side becomes a back, preserving corners. Maintenance belongs to tools.

## Coordination, resize and undo
- atualizar_sistemas_do_conjunto runs after the body is ready: doors, then
  drawers, then shelves, ONCE each. internos=False updates only doors,
  preserving restored openings/fittings without rebuilding internal systems.
- Resize, thickness, shapes, HUD and joints enter through that coordinator.
  Door leaves are written by portas.atualizar_do_conjunto.
  portas.atualizar_portas_do_conjunto(..., sistemas=...) is external
  compatibility only; production callers must not coordinate through it.
- No additional cache/state, generic service or captured function exports.
  Owner-module patches and reload must reach every domain call.
- Loose-group/joint resize queries axial constraints in a batch. Constraints
  can lie at the other edge; do not invent reverse-link scope.
- Native S with internal systems: absorver_conjuntos(no_timer=True) measures
  the scaled native box and uses the common resize in the stable timer.
  Depsgraph only defers. Do not absorb inherited scale into panels first
  or multiply drawer/shelf geometry; preserve the pivot-derived corner.
- Group Mirror keeps unit-magnitude signed scale on the Empty. Opening and
  shape axes preserve parity; quaternion conversion loses reflection.
  Recentering a reflected cabinet moves child translation only.
  S after R measures local axes and uses redimensionar_orientado.
- Keep modeled Mesh IDs, parent relationships and UID associations. Update
  the view layer before reading changed matrix_world. Native undo must not
  retain freed scene references or trigger mesh/selection work mid-transition.

## Validation
Read [tests](../../../tests/AGENTS.md). Suites: armarios, operadores, hud;
dependants/imported assets: importacao, migracoes, portas, gavetas, prateleiras.
Check body-to-system order, modeled meshes, reflected resize, S/R, undo/redo
and owner patches after reload. Use temporary scenes/library copies; never
write to the real library or change the open project. GUI needs permission.
