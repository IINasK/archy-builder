# Library redesign plan

Status: implemented and compacted in version 229. Automated validation and
screenshots used isolated tests; the real library catalog and thumbnails were
preserved. Reference: the user's 13 October 2026 image, with horizontal category
tabs and a row of thumbnails below.

## Approved layout

The library spans the top of the entire Archy Builder workspace, above both the
left menu and main viewport. The menu edits the selected item. The library stays
accessible while switching between Cabinets, Doors, Drawers, Shelves and Handles.

```text
+-------------------------------------------------------------------+
| Cabinets / Materials | level 1 categories                          |
| deeper categories: currently open path                            |
| [photo + name] [photo + name] [photo + name] ...          <     >   |
+---------------------+---------------------------------------------+
| Selected-item       |                                             |
| editing menu        | Main viewport                               |
|                     |                                             |
+---------------------+---------------------------------------------+
```

## Navigation and appearance

- Compact horizontal category tabs: height 18 px, step 20, font 10, gap 2; active tabs use theme highlighting. Each level shows children of the previous selection.
- Preserve `niveis`, UUIDs, catalogs and the existing single library. This changes presentation without reclassifying presets.
- Unlimited category depth; hide empty branches. Shift+wheel reaches overflowing levels while keeping photos and the complete path accessible.
- One horizontal thumbnail row: photo above, name below, full-name tooltip, row scrolling and arrows. Reuse existing names, catalog and PNGs. Show arrows only for overflow, pointing toward hidden items; otherwise use the released width.
- Photos fit available height (40-68 px at the default size). Initial strip height 180 px, resized through the native area boundary, with a collapse option. Layout was checked at 100/150/200% scale.
- The original compact-height proposal put deeper levels side by side below 160 logical px, with 24 px gaps and theme dividers; each group scrolled independently, Shift+wheel reached deep levels, and photos shrank to remain accessible. Increasing height restored one row per level. Later refinements in DESIGN.md supersede this arrangement.
- Materials remain spheres. No counts on categories/items. Preserve rename, save, delete and protection behavior.

## Preserved interactions

- Click a cabinet to begin viewport placement; Esc cancels.
- Right-click photo/name: on RELEASE, open the menu near the pointer with Insert, Edit and Lock/Unlock. No buttons under cabinet thumbnails; disable Edit on locked items. Preserve factory protection. Handles use their creator rather than inserting a loose mesh.
- Material: single click does not paint; double-click paints selection; drag paints its target on release; right-click opens quick painting by room/part.
- Library questions stay inside the strip, with room and scrolling for answers. The cabinet context menu is the explicit exception to viewport-only popups.
- The pointer's area owns events: library rows or viewport. Camera, selection, gizmos, HUD and snap never receive strip clicks.
- Clicking the body selects the cabinet; doors/handles open their controls. Drawer handles are individual; drawer rails stay with drawers.

## Proposed implementation sequence

1. Prototype a dedicated top area: split horizontally, then split the bottom vertically into menu and scene, so the strip spans both columns. Reuse GPU drawing, theme and events; no floating window.
2. Preserve view, menu width and navigation state during migration. Reorganize only add-on areas and their viewport. Validate open/close/restore in 4.2 and 5.2 before automatic migration; leave other editors alone.
3. Separate strip presentation from menu layout while sharing catalog, thumbnails and actions. A UI module owns the strip; remove the bottom library from the menu.
4. Adapt operator/gizmo area filters, drag targets, questions and scrolling. Reconnect areas by role when reopening; area pointers cannot be the sole persisted identity.
5. Load photos only for visible items plus a small margin, bound image/texture cache, and filter using the index. Never open `.blend` files to draw a row. Invalidate on category/catalog changes; no drawing-time mesh scans.
6. Update documentation and snapshots when integrated; remove the old internal divider and bottom-library dependencies.

## Validation and delivery criteria

First validate the complete layout in a test scene; measure opening, category
switching, scrolling and memory with the current library and a larger synthetic
catalog. Never write to the real library. Then verify actual events: cabinets,
materials, quick paint, save/delete, tab switching and collapse/restore.
Test narrow windows, UI scales, deep paths, two windows, workspace changes,
file reopening and deactivation. Delivery requires a strip above both columns,
legible content, preserved state, no scene-control interference and checks in
both versions. Report preexisting wall/material failures separately; do not
claim the complete suite passed when it did not.

Work order: complete layout -> catalog/thumbnails -> events/questions ->
cache/performance -> migration/regression tests.
