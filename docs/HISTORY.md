# Archy Builder historical archive

## English presentation (410)

The interface, library labels, documentation, code annotations and tool help use
English. Resources are organized under assets/library, assets/hardware and
assets/previews. Generated part names are separated from saved role identifiers;
legacy installation cuts and components remain functional.

Validation: 3,464 headless tests across 82 runs in Blender 4.2 and 5.2; both
versions load, register, clean up and reload the extracted installation package.
All 677 binary assets are unchanged. UI snapshots and numeric geometry checks
were reviewed; interactive GUI tests were not run in this delivery.

This document preserves the Cabinet Creator and Chapa G3 names used in earlier
stages. Current presentation and installation instructions are in the
[README](../README.md). The descriptions below record earlier behavior and layouts.

# Cabinet Creator

A Blender add-on originally used at G3 to generate custom cabinets. Wood panels
have arbitrary positive thickness that remains immune to own, parent-inherited
or multiselection scaling. Real BMesh geometry stays editable in Edit Mode.

## Recorded development

- Shelf gaps (379): click an empty-space dimension and scroll to add/remove shelves only there; Enter confirms, Esc discards preview, supports/neighbors stay. Shared blocking shows all shelf-segment dimensions; selecting partitions changes orientation. Common frame is visual; internal dimensions edit their own segment.
- Interior editing (378): MMB, zoom or Shift+`/WASD navigate between volume points; native snap runs only during each point gesture through release. Select a door part then Shift+G -> Door Group -> H, or Hide Door and Aggregates in Doors; Alt+H reveals. Define by Volume uses Create's orange highlight.
- Creation snap (377): select cabinet first to restrict drawer/shelf/partition points to its parts. No ceiling/wall/curve/other-cabinet targets. Without selection the first valid point fixes cabinet. Free-volume placement/editing uses same restriction and restores temporary locks.
- 3D creation (376): three points in any order define module-axis min/max box, then front-face click and quantity. Free-volume Apply also asks front; Backspace returns, Esc cancels. Door/back planes stay 2D.
- Internals (375): shared Shelves/Partitions tab; choose type, points or adjustable volume, then other type in same area or Exit. A smaller partition may cut a shelf at different depth; keep gap or fill left/right.
- Per-leaf handles (374): double isolates leaf before Create Handle; native ray prioritizes it despite overlap. Swing/sliding adapts parametric side handles without changing owner. Reveal/unlock hidden/locked leaves in Outliner before insertion.
- Menu scrolling (373): controls/library have independent overflow scrollbars, wheel/touchpad/thumb; reserved scrollbar column, fixed tabs/footer.
- Free area (372): Define by Volume for internals, Define by Plane for doors/backs. One click positions reference; face handles, dimensions and G/R/S edit rectangular volume/four-corner plane. Apply volume asks front; planes proceed to system options. Point capture uses the 3D flow above.
- Wall selection (371): query chosen mesh only through foreground objects; native vertex snap on that object. Noneditable partial cabinets are clipped gray; initial editing permission remains for the session.
- Hinges/Delete (370): persistent deletion observer survives reopening. Deleting a leaf removes its hardware while preserving the other. Hardware native selection permits Delete; Shift/menu/double-click retain roles.
- Deletion/selection (369): click/Shift/Tab use native View Layer; scene-deleted IDs never reenter through ancestry. Referenced deletion still schedules hinge cleanup even when data ID count is unchanged. Preserve excluded collections/other-scene leaves; empty door group cannot resurrect assembly.
- Wall indicators (368): selected cabinet retains A1 width/A2 height/A3 depth, with clickable corner A3 callout separate from offset. Resize hides neighbor distances only; menu and HUD share targets.
- Wall base (367): continuous adjacent support defines usable base; buried floor band disappears, Below=0 meets actual support. Dimensions/guides/drag share region; partial supports remain local obstacles, wood unchanged.
- Wall dimensions (366): typed distances accept zero; owner validates dimensions. Edge numerical tolerance never admits collisions; zero still refused if it penetrates a floor inside the selected region.
- Dedicated editor (365): native Cabinet Creator Node Editor subtype in selector, identity saved in blend; legacy conversion preserves scene view. Optional top library has own editor. VIEW_3D overlays never draw over menu. Layout/fields/drag unchanged; scene commands forwarded to real 3D viewport.
- Wall import (364): after resize, reconcile append list with live hierarchy including rebuilt hardware; Local View/selection/cancel use current generation.
- Drag fit (363): shrink width/height only within wall Maximum Adjustment, default 10 mm each, zero off; preview shows size, confirm preserves E. Excess gives red box/reason without inserting/changing preset.
- Menu (362): seven tabs become full-name dropdown if even abbreviations do not fit; widening restores row with selection retained.
- Walls (361): connected Edit Mode vertices or Object Mode automatic hover/3+ point polygon. Enter confirms, Backspace removes, right/Esc cancels; same menu actions. Isolate region/associated furniture without changing plan.
- Backs (360): new tab, two corners/native snap; recessed groove 6/9 mm with support Booleans, nailed overlay, flush inset 15 mm. Linked drawers/shelves follow inner face; Unpinned detach keeps dimensions. Existing backs preserve modeling/legacy behavior.
- Joints (359): one connection/vertex pair per object pair; manual honors target, old files retain saved gap; migration chooses nearest real vertices without remodeling.328 audited,265 updated,407 redundant records removed, all pairs/geometry/materials retained.
- Mixed selection (358): Shift-add ordinary object restores native outline for material source; removing it resumes add-on outline.
- Native group edit (357): Tab/G height reduction preserves edited handle meshes; hardware updates in batches without scene recalculation per hinge.
- Native materials (356): select target cabinet, Shift-click source panel last; native Ctrl+L Link Materials uses clicked mesh as master, group pieces stay selected. Shift+double isolates source panel in another cabinet. Native transfer/undo; Solid Color>Material displays it.
- Wall placement (301): library/double/right-drag share free space; full envelope stops at same-face/height neighbors/edges. No room refuses insertion/cancels reposition; no shrink-to-fit at this stage. Preview uses accepted envelope/center even at corners; contrasting halo/arrow dimensions, active HUD highlight.
- Estimates (300): Options -> Generate Estimate writes company .txt from actual evaluated body/frame width x height x depth in mm, door openings, hinge types, drawers/shelves/partitions/handles/used materials. No preset-count dependence after edits/deletion. Group axes survive rotation; open leaves/drawers do not enlarge size. Mixed materials exclude hardware; missing material/hinge identity is pending. Rooms remain marked Outliner folders.
- Wall editing (299): selected vertical mesh -> Walls/Edit Wall or Cabinet Creator context entry. Native Local View orthographic face/cabinets; orbit/Walk/Fly exits, pan/zoom stay. Library/right-drag release sets position, preserves original size. Photo double-click right of last or center if no room/no previous; never stretch to fill. Elevation dimensions and menu fields edit. Free/Fixed governs explicit redistribution; G/delete recalculate gaps without moving neighbors. Replacement validates confirmation, preserves size/position/association. No wall measurements in menu; native modeling. Solid black outlines, hidden origins/relationship lines, restored visual state; orbit returns perspective. Door click cabinet, double leaf; gray transparent actual interior edges behind fronts, dimensions near selected part, no mesh changes.

## Historical source layout

Paths below describe the earlier layout, not the current sector map.

```text
archy_builder/
  __init__.py        # loading, linking and registration
  chapas/            # panel mesh and thickness
  modulos/           # body, envelope and dependents
  portas/            # opening, coverage and leaves
  gavetas/           # furniture drawers and shared wizard
  prateleiras/       # units and gaps
  divisorias/        # vertical panels and system segmentation
  gaveta*.py         # MENU: layout, drawing and events
  hud.py             # viewport dimensions and interaction
  promob.py          # imported-object integration
  paredes_edicao.py  # local wall view and preset distribution
  paredes_composicao.py # dimensions, fixed widths and replacement
  biblioteca/        # factory presets bundled with add-on
    *.blend
    indice.json      # unlimited-depth preset catalog
build.py             # creates dist/archy_builder.zip
tools/development/link_blender.py  # links checkout to Blender using a junction
```

Development begins with [task routing](../ARCHITECTURE.md). Historical six packages
retained public names and local AGENTS/CLAUDE instructions. Development steps:
`python tools/development/link_blender.py` links archy_builder to Blender add-ons;
edits then affect loaded source. Reload through disable/enable or restart.
`python tools/development/build.py` creates dist/archy_builder.zip for other machines.

## Core concepts and door workflow

Panel X=width, Y=length, Z=thickness; orient through rotation, never scale. After S
finishes, accumulated scale becomes millimeter dimensions and Z is discarded.
Adjacency remembers neighbor/gap at each end and closes joints after resizing.
All geometry uses matrix_world; local location fails under a displaced parent Empty.

Historical left menu was its own GPU VIEW_3D with Cabinets/Doors/Drawers/Shelves/
Partitions/Handles and a top library strip. Selection/context chooses controls;
[DESIGN.md](../DESIGN.md) records current visual decisions and rejected alternatives.

Object Mode door creation: Create Doors, mark two opposite bounds. Solver derives
opening/full outer/half-thickness/inset coverage and automatic hinge. Choose leaves/
opening and applicable hardware stages, mirrored in sidebar. Esc cancels/right
returns. Click finished door for group, double for leaf; reposition also two corners,
Tab native. Swing/lift-up/sliding/zigzag; sliding inset/framed, mixed bounds ask.
Existing properties remain the only UI data model. Fields drag/type, Enter confirms,
Esc restores, modeled meshes/materials preserved. See [doors](../archy_builder/cabinetry/doors/AGENTS.md),
[interface](reference/interface.md) and [architecture](../ARCHITECTURE.md).

Historical test commands (use disposable scenes; they clear their fixture):

```powershell
& 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' --background --factory-startup --python-exit-code 1 --python tests/test_doors_blender.py
& 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' --background --factory-startup --python-exit-code 1 --python tests/test_sidebar_blender.py
```

They cover coverage/setbacks/leaf bounds/plane collision/joint BMesh selection/
parent transforms/closed meshes/editing/material preservation.

## Recorded limitations

- Blender 4.2 wall batch redo may restore second Collection without scene link, including without interior drawing; regression remains active.
- Sidebar is a separate area; user drags native boundary. On release, screen.area_move reapplies 564 px limit when adjacent viewport exists. Area.width is read-only, so it cannot lock during the gesture.
- Preset drag uses custom modal and needs interactive Blender validation.
- Blender 5.2 Geometry Nodes Python input-writing issue #160038 is why panels use BMesh.
