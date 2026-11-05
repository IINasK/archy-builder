# Shelves
Keep AGENTS.md and CLAUDE.md identical, English ASCII, at most 120 lines.

## Ownership and routes
Internal shelves, count, gaps and individual/group edits.
[Drawers](../drawers/AGENTS.md) owns the shared AssistenteDoVao reference/
gesture; [partitions](../partitions/AGENTS.md) owns segmentation.
Sidebar/HUD dispatch here; [panels](../panels/AGENTS.md) owns the base mesh.
Legacy addon.prateleiras and canonical shelves are the SAME module.
Preserve Portuguese APIs, stored attributes and owner-based patching.

| Task | Entry point in __init__.py |
|---|---|
| Gaps/calculation | vaos, calcular, mover_vao |
| Create/assemble/resize | criar_prateleiras, montar, atualizar_do_conjunto |
| Deletion/centering | sincronizar_exclusoes, OBJECT_OT_alinhar_prateleiras |
| Native G/actual dimensions | _sincronizar_disposicao, sincronizar_exclusoes_da_cena |
| Parameters/count | editar, editar_individual, resolver_referencia |
| Local subdivision/copies | detalhamento, editar_quantidade_local, CHAVE_DETALHAMENTO |
| Tab/propagation | iniciar_edicao, edicao_atual, concluir_edicao |
| Reference/assistant | OBJECT_OT_referencia_prateleira, OBJECT_OT_criar_prateleiras |

## Creation, subdivision and scope
- Shared Prateleiras / Divisorias tab: creation_areas coordinates type,
  common volume, continue/exit and gap choice BEFORE mutation. Partitions
  owns cutting; preenchimento_divisorias preserves this creation choice.
- Reuse AssistenteDoVao: three unordered points -> cabinet-axis min/max box
  -> explicit front -> quantity. Depth is from the box; front gap is RECUO.
  Store/use the same opening reference and native snap protocol as drawers.
- backs.py supplies associated inner-back depth limits; retain heights and
  front. Opening bounds use structure without expanding for the back.
- preparar_subdivisao_vao fixes supports/parameters; subdividir_vao copies
  stock/modeling ONLY into empty space. Scroll changes NEW session copies.
  Originals/neighbours keep Mesh, material and pose. Validate capacity first.
- Esc removes only copies, restores indices/parameters before HUD backup;
  Enter confirms quantity, not a dimension. Zero restores initial state.
  The HUD operator owns undo.
- cabinet_blocagem_uid links cut segments within a cabinet. Group selection
  covers linked shelf segments; double-click remains local. HUD shows their
  common read-only frame and each segment's V dimensions with actual targets.
  Independent systems never merge. Legacy migration uses saved support UIDs/
  coplanarity outside undo, never names or redraw writes.
- Show only E fields for selected scope, from bottom to top. Do not restore
  Equal/Free, Between shelves or Abaixo/Acima sidebar controls.
- Group count is global; unit count covers it and its copies ONLY between
  surrounding supports. prateleira_detalhamento_uid is on panels, with no
  new Empty/box. Derive limits from current gaps; any copy finds that scope.
- Outside that scope nothing moves/rebuilds, including drawers. Reduction
  keeps the active unit; zero deletes only that scope. Validate before copy.
  Local parameters/centering include copies; individual Tab remains native.
- Local HUD shows its E fields, local count and support-to-support frame;
  that frame never resizes the global block. Last E moves the last copy,
  not its support. The count field stores target NAME for typing/preview/Esc.
  Explicit API references remain global; global copies do not inherit local
  subdivision UID.
- Centralizar espacamento remains in Espacamento with the existing
  left-arrow/bar/right-arrow icon and 37 height, never beside count.
  Group distributes all; unit without copies equalizes its two adjacent
  gaps; with copies redistributes ONLY the local scope.

## Native edits, meshes and resize
- Deletion updates count/gaps WITHOUT moving survivors; redistribution
  requires its explicit action. Changing ONE gap moves ONE shelf and its
  neighbour yields. Individual parameters never move neighbours.
- After native G (Object or individual/group Tab), dimensions follow native
  bounds in opening coordinates at confirmation/exit. Do not rebuild or
  move neighbours. Crossing shelves reorder bottom-up with their parameters.
- Discard old fittings; synchronize only outside modal/Edit/undo after Tab
  absorption. No vertex scan or dimension calculation during drawing.
- Click selects all, double-click one. HUD shows opening L/A/P and each
  actual gap. Individual parameters retain their scope.
- Group Tab edits the same actual panels through native multi-object Edit
  Mode and propagates on completion; individual Tab isolates its mesh.
  NEVER replace Mesh ID on completion: BMesh.to_mesh writes into the SAME
  mesh because native undo retains that ID. Undo back into Edit Mode
  recovers scope from native selection.
- Count copies the selected unit's geometry, parameters, material AND
  modifiers. Mixed types without an active reference ask Selecione a
  prateleira de referencia at the mouse; clamp to viewport edges and cancel
  with Esc without adding anything.
- Quantity drag previews only; assemble on RELEASE. Identical assembly
  must not rewrite transforms/dimensions or update the depsgraph: this used
  to invalidate native BVHs while another panel's ruler was active.
- Cabinet resize keeps the block while it fits. Share drawer transport/
  capacity rules; ajustar_ao_espaco stores choices, atualizar_do_conjunto
  assembles. Do not revert to fixed margins that grow with the cabinet.
  Cabinet Esc restores opening, margins, parameters AND fittings.
- Creation after partitions calls particionar_grupo. Cuts preserve height,
  material and existing modeling; crossing/support rules belong to partitions.
- Retain group reflection, native snap, shared cursor cleanup and numeric/
  name-only state across undo. Tests must patch the owning module object.

## Validation
Read [tests](../../../tests/AGENTS.md). Suites: prateleiras; shared gesture/
partitioning: gavetas, divisorias; Tab/undo/presentation: operadores, formas,
hud, gaveta. Check local/global isolation, copied modeling, Mesh identity,
native transforms and reload. Use temporary scenes; never change the open
project or real library. GUI needs current explicit permission.
