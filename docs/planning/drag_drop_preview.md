# Library drag-and-drop with spatial preview

## Status and objective

Implemented in 56.0.0. This historical document records the behavior and decisions
to preserve during maintenance. Move a library preset from the N-panel into the
viewport with an anchor crosshair and physical-volume wireframe before creating
the final instance.

## UI entry points

1. The preset-name button starts placement: click enables preview and the next viewport click inserts; press/drag attempts placement on viewport release. The separate arrow retains immediate insertion at the 3D cursor.
2. Trigger: `LEFTMOUSE` + `PRESS` in `User Interface`; a 6 px threshold distinguishes drag from click. The historical proposal registered `head=True` to precede other entries.
3. Read `context.button_operator`; accept only `object.cabinet_inserir_preset`.
4. Drags over fields, pencil, lock and other controls return `PASS_THROUGH`, preserving sliders and Blender interactions.
5. `UILayout.template_icon` is the only widget displaying an enlarged preview. It exposes neither operator nor drag event in Python; real image dragging belongs to Asset Shelf.

## Operator lifecycle

Capture selection, active object, existing collections, the same `VIEW_3D` area's
`WINDOW`/`region_3d`, and region pointer to prevent drawing elsewhere.

Stage with `inserir_preset(..., destino=(0, 0, 0))`; identify new objects, roots
and collections. Update the dependency graph and measure before hiding. Save
`hide_viewport` and `hide_get()` states and hide imported objects while placement
is undecided.

For `TIPOS_COM_VOLUME`, use `_cantos_avaliados` to include transforms/modifiers,
compute world min/max, eight corners and twelve edges. Anchor at the bottom-face
center `((min_x + max_x) / 2, (min_y + max_y) / 2, min_z)`. Never visually
normalize the box: it represents actual preset dimensions in Blender units.

Convert global event coordinates to region coordinates; obtain ray origin and
direction using `view3d_utils`. Try evaluated `scene.ray_cast`, ignoring staging
objects. On hit use its point/normal; otherwise intersect an XY plane at the 3D
cursor's Z, allowing placement in empty viewport space. Translate roots only;
children follow. Apply the same displacement to the eight GPU corners.

Register `SpaceView3D.draw_handler_add` at `POST_VIEW`. Draw a green box using
`LINES`/`UNIFORM_COLOR`; the crosshair has two tangent axes and one surface-normal
axis. Yellow indicates a surface hit, white the fallback plane. Draw only in the
originating `WINDOW`. Remove the handler on confirmation, cancellation or error.

## Completion and cleanup

A real drag confirms on left RELEASE; explicit operator invocation accepts the
next PRESS. Require a valid target inside the viewport. Remove the handler,
restore imported visibility, select imports and make a root active. The operator's
Undo covers the result.

Right-click, Esc, window deactivation, invalid target or release outside the
viewport cancels. Remove handler/status text, imported objects with
`do_unlink=True` and newly created collections; restore original selection/active
object. Leave no object, wireframe, crosshair or collection behind.

Initialize object/collection lists before importing so partial exceptions can be
cleaned. If no volumetric geometry exists, fall back to root positions; cancel
if those are absent too. Log raycast failures and use the cursor plane without
ending the modal. GPU failures must not kill placement. Never remove collections
that existed before the drag.

## Acceptance criteria

1. Dragging a name onto a face shows the yellow crosshair exactly under the pointer.
2. The green box follows the pointer with unchanged physical dimensions.
3. Empty-space placement uses the 3D cursor's horizontal plane.
4. Releasing inside reveals/selects the instance; releasing outside creates nothing.
5. Right-click/Esc immediately remove staging and preview.
6. No handler/status text survives completion.
7. Single-click starts placement; the arrow inserts directly at the cursor.
8. Sliders, pencil and lock still work.
9. Registration/unregistration succeed in Blender 4.2 and 5.2.

## Recorded validation

- Registration/unregister in Blender 4.2.1 LTS and 5.2.1 LTS.
- A 600 x 400 x 300 mm test preset yielded a 0.6 x 0.4 x 0.3 m bbox in both.
- Staging hide/restore and cancellation removal checked in both versions.
- `UNIFORM_COLOR` checked in a Blender 5.2.1 graphical session.
