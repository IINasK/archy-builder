# UI

Keep AGENTS.md and CLAUDE.md identical, in English ASCII, at most 120 lines.
Read the root routing guide and design contract before visible changes.
Read the domain guide for behavior beyond presentation and dispatch.

## Ownership

| Module | Responsibility | Legacy module |
|---|---|---|
| sidebar.py | Context, layout, tabs, fields and sidebar state | gaveta |
| sidebar_drawing.py | GPU/BLF drawing and text presentation | gaveta_desenho |
| sidebar_events.py | Sidebar input, fields, gizmos and dispatch | gaveta_eventos |
| editor.py | Persistent custom editor and viewport command bridge | editor |
| selection.py | Native selection scope and group editing | selecao |
| hud.py | Dimensions, hover, viewport controls and edits | hud |
| volume_hud.py | Native volume drag, snap base and observer | hud_volume |
| library_strip.py | Library navigation, cards and scrolling | biblioteca_faixa |
| wireframe.py | Hardware wireframe previews and caches | arame |
| dialogs.py | Existing confirmation routing | perguntas |
| legacy_panel.py | Unregistered legacy panel reference | painel_legado |
| creation_areas.py | Shared creation area and continuation session | areas_criacao |
| visibility.py | Temporary display and visual group scope | visibilidade |
| door_controls.py | Door sliders, corners and opening controls | portas_viewport |

The legacy gaveta module means sidebar; gavetas means furniture drawers.
UI text, documentation and code annotations use English. Preserve internal
function names, widget actions, operator IDs and persisted editor identities.

## Imports and lifecycle

The root owns explicit loading, immediate legacy import aliases, dependency
wiring and registration. English and old imports/attributes must resolve
to the SAME owner object. Keep calls on owner modules so patches and reload
remain effective; do not copy functions into facades.
Editor classes inherit sidebar_events classes at import time. Preserve that
dependency during initial load and reload. Register each class only once.

## Interaction contracts

- Layout produces existing six-element widget tuples; drawing paints and
  events dispatch. Geometry/calculation belongs to its existing domain.
- Keep the sidebar/library custom NODE_EDITOR roles and saved type IDs.
  Viewport commands use the editor bridge; text and drag originate where
  the interaction started.
- Native Blender selection, navigation, snapping and transforms retain
  precedence where specified. Common objects use native CLICK selection.
- Native gizmos win before keymaps. Preserve modifier-click handling,
  release-triggered modal/dialog actions and waiting for an opening release.
- Gizmos use a reusable pool: hide/reuse, do not remove/rebind during redraw.
  Keep operators attached to fields and update properties/tooltips.
- Drawing/hover only read numeric caches. Never open .blend files, rebuild
  meshes or hash dictionary-bearing actions during drawing.
- Scene targets stored across undo are names/numeric session IDs. Clear
  hover and edit/modal transitions before invalid IDs can be accessed.
- Restore only overlays/display state this code changed. Native H/Alt+H,
  Local View and manually hidden objects keep their behavior.
- Never call popup_menu in background. Use existing confirmation routing;
  sidebar confirmations remain in the sidebar and library ones in its strip.
- Modal completion/cancel/error must release scene references, native snap
  sessions, handlers and timers. unregister clears all UI state/resources.
- Keep photo paths rooted in the existing fotos data directory. Moving UI
  modules must not redirect caches or photos to a new empty resource tree.
- The legacy panel remains unregistered unless explicitly requested.

## Validation

Read the root tests/AGENTS.md. Relevant suites: gaveta, hud, editor,
biblioteca_faixa, areas_criacao, visibilidade, medidas, operadores, estrutura,
snapshot and the authorized GUI suites. Verify owner patches and class
inheritance after reload as well as complete unregister.
Callback tracebacks are failures even when assertions pass. Do not refresh
snapshots merely to accept a layout change. GUI needs current explicit
permission to use the PC; never change the open project for a fixture.
