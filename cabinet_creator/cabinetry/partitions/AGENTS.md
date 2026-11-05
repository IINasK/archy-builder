# Partitions

Keep AGENTS.md and CLAUDE.md identical, English ASCII, at most 120 lines.

## Ownership and routes
Vertical partitions segment internal systems they intersect.
[Shelves](../shelves/AGENTS.md) and [drawers](../drawers/AGENTS.md) retain ownership of resulting groups; supports belong to actual panels.
Reuse drawers.AssistenteDoVao rather than another assistant or solver. Shared creation: [creation_areas](../../ui/creation_areas.py).
Legacy addon.divisorias and canonical partitions are the SAME module; retain Portuguese APIs, placeholders and saved ID/property names.

| Task | Entry point in __init__.py |
|---|---|
| Dimensions/assembly | calcular, montar, vao |
| Creation/edits | criar_divisorias, editar, OBJECT_OT_criar_divisorias |
| Validate/split | _plano, _partir, _separar_prateleiras |
| Cut existing panel | _cortar_chapa |
| Systems created afterwards | particionar_grupo |
| Supports/resize/deletion | _apoios, limitar_vao, atualizar_dependentes |

## Geometry, segmentation and selection
- CHAVE_BLOCAGEM/cabinet_blocagem_uid links segments and types created in one session.
  Geometry groups remain independent; selection/HUD aggregate only the active orientation within the same cabinet/UID.
- Partition copies retain that link BEFORE cutting. Legacy systems without UID use saved supports and compatible frame/height/depth only,
  in timer/selection processing; never infer identity from names or write in redraw. The aggregate frame cannot resize an isolated segment.
- creation_areas coordinates unified shelf/internal creation and reusable volume: ask type first, another type/exit afterwards.
  Gap choice MANTER/ESQUERDA/DIREITA occurs BEFORE mutation, for both creation orders.
- Shelves accept shallow, oblique and thickness-partial partitions. Determine planes from panel subsets/names without forcing aligned depths.
- Fill extends only the chosen panel to the opposite support face. Native Boolean DIFFERENCE/EXACT preserves live fitting.
  Retain base Mesh/UVs; align bisect caps to avoid single-precision wedges.
- Supports record min/max face for resize. Coplanar contact is NOT an intersection and must not split a system.
- Reuse shelf/drawer native snap vertically: three unordered points -> cabinet-axis min/max box -> explicit front click before quantity.
  Never infer orientation from the diagonal or scan mesh vertices in Python during clicks/drags.
- Restore cursor and snap targets on confirmation/Esc/error, keep one undo operation; transpose column-axis matrices for native translate rows.
- Segment intersected drawers/shelves, including ones created AFTER the partition, subtracting partition E.
  Supports reference the REAL panel UID; never invent another cabinet to represent the split.
- Validate ALL openings BEFORE mutation. One valid half cannot authorize partially split systems when another half fails.
- Shelf cuts use bisect/cap BMesh in the SAME Mesh, preserving height, materials AND previous cuts.
  Never reconstruct as a box or replace surviving IDs.
- Resulting groups stay editable AND independent. Retain individual drawer/shelf APIs, saved references, selection and material contracts.
- Deleting a support keeps the LAST bound; never merge edited systems.
- Drawer stacks need the partition across FULL height AND depth; shelves permit splitting a PARTIAL selection of their group.
- Reload drawers before partition classes/constants are evaluated; rewire afterwards. Old/canonical imports keep owner calls patchable.
  No copied function exports or registration facades.
- Never retain freed scene IDs across undo or write a Mesh in Edit Mode. Drawing consumes numeric state;
  defer rebuild/selection work during undo.

## Validation
Read [tests](../../../tests/AGENTS.md): partitions, drawers, shelves.
Cover both creation orders, partial/oblique cuts, systems created afterwards, refusal without partial mutation,
edited Mesh identity, support deletion, independent edits and reload/undo behavior.
Use temporary scenes/fixtures; never change the open project or real library. GUI needs current permission.
