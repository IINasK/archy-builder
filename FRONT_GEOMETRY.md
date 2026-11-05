# Front geometry reference

`archy_builder/cabinetry/fronts.py` provides geometry shared by doors, handles,
outlines, previews and transport during resizing. Recognition uses the local
Mesh itself, independently of the cabinet's name or category. The closed pose
comes from the existing rig; opening or moving does not change the local reference.

The cabinet HUD consumes the same outline for each individual door leaf.
It does not combine leaves into a nominal box that would cross curves and folds.

- `preparar`: extracts the reference during assembly, import or editing.
- `referencia`: reads numeric data without extracting or querying geometry.
- `perfil`, `contorno`: the physical surface and actual wood boundaries.
- `bordas`, `lugar`: placement along mounting edges, following their curves.
- `normalizar_borda`, `fracao_do_ponto`: a shared segment coordinate.
- `transportar`: queries a native copy of deformed geometry before reanchoring
  the rig; preserves the modeled Mesh, vertices and faces.

## Persistence and editing

`cabinet_frente_face` (INT/FACE) distinguishes front, back and caps.
`cabinet_frente_borda` (INT/EDGE) distinguishes upper/lower edges on both
surfaces. These native attributes travel with Blender edits. Vertex numbers
are never persisted as edge identity.

Preparation precedes reference capture and deformation. Old native copies
receive attributes only when topology matches, preserving the original resize
geometry. Curved front/back surfaces are distinguished from caps by a native
query of the opposite surface across the thickness.

`cabinet_frente_referencia` is a numeric Mesh cache with version, geometric
signature, paths and normals. Geometry changes invalidate that Mesh for all
users. The queue stores mesh names, not RNA objects; rename/undo/file-open
recovery happens outside drawing. The handler distinguishes geometry from pose.
Redraw/hover read the cache; recognition and BMesh stay outside those callbacks.

A parametric assembly with a profile handle may remove a strip of wood. The
outline uses the cut wood; the nominal edge retained by the cut remains the
handle's mounting reference. This prevents another profile offset when rebuilding.

## Compatibility

`porta_linha_frente` guides migration of old presets. `porta_linha_indices`
does not govern new consumers. Old handles translate their coordinate once
(`puxador_referencia_versao`); they never accumulate offsets during resize.
Without a cache, legacy drawing stays numeric until event/timer preparation.

Historical DXF diagonal reconstruction remains in the import adapter. It
remodels recognized old exports and requires a backup before asset publication.
It is not used to recognize fronts during redraw, editing or placement:
extending it to a partial door would replace its geometry with the full cabinet box.

## Verification

`tests/test_fronts_blender.py` covers boxes, curves/facets, normal thickness,
back surfaces, cutouts, topology, pose, mounting edges, migration, shared meshes,
renaming and no redraw scans. The portas/puxadores/importacao suites check
consumers. The integration audit reads real assets without rewriting the library.

Angular editing uses the native edge marked by `cabinet_forma_angulo`
(INT/EDGE), including when it reaches a right angle. Its actual neighbor defines
the internal angle; P1/P2 bounds do not constrain it. Backs stay outside the
envelope but follow their support with normal setback and thickness preserved.
Flat panels tilted through Tab are reexpressed in their actual plane, retaining
Mesh, world coordinates, UVs and users.

In 256, the shape solver uses an orthonormal basis per section: XY, XZ and YZ,
without rotating the scene for calculations. Native angular edges distinguish
planes; reference/undo retain the original cabinet basis. Systems receive
displacements converted to their parent's frame. The HUD combines and clips
cached numeric sections without scanning meshes during redraw. An isolated
panel's solver uses its local plane and separates Mesh users; leaving Tab
invalidates the three section caches together.

In 380, editing only one skin can give front and back different perimeters.
The individual HUD then uses actual structural edges with EDGE UIDs and
coordinates in the section cache; it never extrudes one skin's profile over
the other. Nominal E does not use an ambiguous envelope. Redraw and hover stay
numeric, without BMesh/CDT extraction.

In 257, free oblique shapes without a parametric classification use native
`delaunay_2d_cdt` union to find actual boundaries. Only structural mesh edges,
excluding coplanar triangulation diagonals, enter the HUD. Edge identity uses
UIDs and local fractions, never persisted indices. Caches retain no RNA and
never rerun CDT/BMesh on redraw. L/A/P, anchoring, arrows and Esc remain available.
