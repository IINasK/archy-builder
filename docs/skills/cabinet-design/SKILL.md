---
name: cabinet-design
description: Design and validate controls, thumbnails, dimensions and alerts in the Archy Builder editor. Use when changing add-on layout, interaction or visual feedback.
---

# Archy Builder design

Read the [UI guide](../../../archy_builder/ui/AGENTS.md) and applicable sections
of [DESIGN.md](../../../DESIGN.md). Use the Archy Builder editor. Layout produces
the six-field tuple; drawing and hit testing consume the same tuple, and events
dispatch to the action owner through the editor bridge. Reuse the existing verb,
field, button, slider and gizmo for the operation. Use theme colors and existing
semantic highlights; icons use native gizmos.

Installation example: thumbnail and name in a card, viewport preview, dimensions
in aligned columns and separate size fields. Show collision warnings near the
action while keeping confirmation available. Measure labels with BLF, including
narrow layouts; do not truncate the primary action.

Check 190, 320 and 564 px, light/dark themes, click and drag. Record what was
verified; run GUI checks only with current authorization to use the PC.
