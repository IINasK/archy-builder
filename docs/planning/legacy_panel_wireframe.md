# Historical Archy Builder reference

This document preserves the Cabinet Creator name and its contemporary UI design.
The current contract is [DESIGN.md](../../DESIGN.md). Requirements below describe
an archived feature; later refinements supersede earlier proposals where noted.

# Plan: dynamic wireframe in the N-panel

## Purpose and recorded implementation

Specify a procedural representation of panel or cabinet dimensions alongside
measurement fields in the Blender N-panel. This was an implementation reference
for developers, covering requirements, formulas, architecture, integration,
edge cases and acceptance criteria.

Recorded status on 22 September 2026: implemented in 34.0.0. Projection, growth
limits, rasterization, cache, register/unregister and actual panel display were
validated in Blender 5.2. Loading, rasterization and registration lifecycle were
also validated in 4.2. These are historical results, not new validation claims.

| Refinement | Recorded behavior |
|---|---|
| 35.0.0 | Blender length proxies accept `600`, `60cm`, `0.6m` while storage stays in millimeters. Four fields and thickness list compacted and centered in the left column. |
| 36.0.0 | Controls anchored left, full labels above fields, larger preview centered in remaining space. Group indicators L/A/P; Individual L/C; no thickness letter. Individual/Group tabs also appear with the cabinet Empty selected; Individual selects its first panel. |
| 37.0.0 | Horizontal canvas, no vertical spacers, reduced UI scale and thinner outlines/indicators. One image avoids seams. |
| 38.0.0 | Independent left-aligned control column. Preview centered in remaining column; base scale 0.26 -> 0.46 px/mm within fixed margins, independent of panel resizing. |
| 39.0.0 | Removed base scale: largest projected extent always fits usable canvas. Small/large objects fill the same maximum area with correct proportions. Fixed display size increased from 8 to 20 UI units. |
| 40.0.0 | One square 160 x 160 image satisfies `template_icon`; UI scale 8.5 gives about 170 x 170 px. A 600 x 400 x 300 box occupies about 140 x 112 px; 600 x 2100 x 300 about 45 x 128. Internal vertical margin 20 px, buffer stroke 0.45 px. Controls remain left-aligned and vertically centered beside it. |
| 49.0.0 | Asymmetric horizontal margins: 14 px left for indicators, 2 px right. UI scale 10 with 0.45 px stroke; wide objects about 180 px. Individual Auto-regenerate moved into controls, removing the extra bottom row. A indicator constrained inside with lateral clearance from the vertical edge. |

## Functional and visual requirements

Draw exactly the twelve edges of a proportional parallelepiped from the current
fields, with depth fixed at 45 degrees upward and left. Front horizontals stay
horizontal, verticals vertical, front face rectangular. Angle never depends on
dimensions or panel width. Transparent background; plain technical outlines,
no fills, gradients, lighting, shadows, photographic perspective, materials,
textures, doors, handles, shelves, partitions, individual cabinet panels, numeric
dimensions, arrows linking fields, colored explanatory points or internal labels.

The initial proposal used a fixed canvas and display size: widening the N-panel
left extra blank space. Native DPI/UI scale still applied. Later responsive
refinements are recorded below; they supersede this initial fixed-size proposal.
The drawing remains centered with transparent margins, fits the maximum usable
area without clipping, preserves proportions and keeps a constant pixel stroke.
Increasing only height makes the other dimensions relatively narrower. Scaling
all dimensions together leaves the projected proportions and outer size unchanged.

Group directions: width along front horizontals, height vertical, depth diagonal.
Individual dimensions use `chapa_largura_mm`, `chapa_comprimento_mm`,
`chapa_espessura_mm`; a thin panel remains a complete box. Keep labels consistent
with existing properties; never rename RNA or ID properties. Local axes remain
X width, Y length, Z thickness; visual projection never changes real geometry.

Out of scope: scene rendering, cameras, auxiliary meshes, Grease Pencil, Geometry
Nodes, actual internal assemblies, manual orbit/zoom, clickable edges, exporting
images or saving a PNG on every update, scene geometry/adjacency changes, preset
or library format changes, and renaming properties saved in `.blend` files.

## Integration context and architecture

The historical implementation was concentrated in `archy_builder/__init__.py`.
Reuse `bpy.utils.previews`, `_previews = [None]`, `_colecao_previews()`, its
unregister cleanup, library `layout.template_icon()`,
`VIEW3D_PT_archy_builder.desenhar_medidas()`, Object panel/assembly properties
and Scene group properties. Writes obey `_ocupado[0]`; unregister every resource.
Keep API names compatible and add no mandatory external dependency.

Primary pipeline:

```text
current dimensions -> canonical cache key -> abstract 3D vertices
-> oblique 2D projection -> scale and framing -> twelve rasterized edges
-> transparent RGBA buffer -> ImagePreview.icon_pixels_float or icon_pixels
-> icon_id -> UILayout.template_icon()
```

Generate in memory: no scene render, camera, viewport dependency, temporary files
or persistent image datablocks. Reuse previews, cache by dimensions and remain
deterministic. First verify `icon_size`/`icon_pixels_float` updates in each
supported Blender. If `icon_id` updates are unreliable, retain the generator,
write a controlled temporary image, load with
`ImagePreviewCollection.load(..., 'IMAGE')`, invalidate old previews safely and
remove temporary files on shutdown where possible. This is a fallback only.

Initial suggested constants, not final approved values:

```python
WIREFRAME_LARGURA_PX = 256
WIREFRAME_ALTURA_PX = 192
WIREFRAME_MARGEM_PX = 14
WIREFRAME_ANGULO_GRAUS = 45.0
WIREFRAME_ESPESSURA_LINHA_PX = 2.0
WIREFRAME_ESCALA_UI = 20.0
WIREFRAME_CACHE_MAX = 48
WIREFRAME_ARREDONDAMENTO_MM = 0.1
```

Tune visually at UI scales 1.0 and 1.5. Avoid unnecessary resolution; reserve
antialias/stroke margins, fill the available limit for a standard cabinet and
keep a typical thin panel legible.

## Mathematical model

Positive L/A/P mean visual width/height/depth. Group uses external cabinet
measurements. Individual respects the real local axes without modifying them.
Eight abstract vertices:

```text
V000 = (0, 0, 0)
V100 = (L, 0, 0)
V010 = (0, P, 0)
V110 = (L, P, 0)
V001 = (0, 0, A)
V101 = (L, 0, A)
V011 = (0, P, A)
V111 = (L, P, A)
```

X grows right, Z up, Y is depth; Y=0 is front and Y=P back.
Draw all twelve edges without hidden-line removal:

```text
V000--V100
V100--V101
V101--V001
V001--V000
V010--V110
V110--V111
V111--V011
V011--V010
V000--V010
V100--V110
V101--V111
V001--V011
```

Projection and top-origin buffer conversion (the Portuguese symbols below are
retained as historical mathematical identifiers):

```text
c = cos(45 graus)
s = sin(45 graus)
projetado_x = x - y * c
projetado_y = z + y * s
pixel_y = altura_canvas - 1 - y_enquadrado
largura_projetada_mm = L + P * cos(45 graus)
altura_projetada_mm = A + P * sin(45 graus)
util_largura = canvas_largura - 2 * margem
util_altura = canvas_altura - 2 * margem
escala_largura = util_largura / largura_projetada_mm
escala_altura = util_altura / altura_projetada_mm
escala_final = min(escala_largura, escala_altura)
deslocamento_x = (canvas_largura - desenho_largura) / 2 - min_x_escalado
deslocamento_y = (canvas_altura - desenho_altura) / 2 - min_y_escalado
```

Negative projected X sends depth left; positive projected Y sends it up.
Centralize buffer-coordinate inversion in one function. Prefer min/max bounds
from all eight projected vertices, allowing later orientation refinement.
Usable dimensions must be positive. Use one uniform scale, never independent
X/Y scales; at least one extent reaches its limit and neither exceeds it.
Apply the same centering offset to all vertices after scaling.

## Rasterization and cache

Allocate a linear `largura_px * altura_px * 4` buffer initialized to `(0,0,0,0)`.
An independent segment routine may use Wu antialiasing, distance from pixel
center to segment or 2x supersampling. Initially prefer distance calculations
only inside each edge's clipped local rectangle; combine alpha correctly at
intersections instead of scanning the whole canvas twelve times. Strokes stay
constant in pixels, independent of geometry or scaling. Every edge must have
at least partial pixel coverage even when a 15 mm panel's edges are less than
one pixel apart. Preserve proportions; do not artificially thicken geometry.

Use a safely accessible theme text/line color. Mandatory fallback: opaque light
lines on dark themes and opaque dark lines on light themes. If detection is
unstable, use a neutral high-contrast color checked in official light/dark themes.
Never paint a background.

`draw()` can run repeatedly without changes. Canonical key:

```text
(versao_algoritmo, modo, round(L, 1), round(A, 1), round(P, 1),
 largura_canvas, altura_canvas, identificador_cor_tema)
wireframe:v1:...
```

Serialize stably. The 0.1 mm key rounding avoids invisible floating-point noise.
Use LRU/use order, initially 48 previews, evicting only `wireframe:` entries.
Never remove the entire shared collection in `draw()` or discard library photos.
Key/invalidation inputs include mode, all three dimensions, canvas resolution,
fixed display scale, margins, theme color and algorithm version. A complete key
is preferable to relying on a global dirty flag or callbacks alone.

On draw, read dimensions, build key, reuse `icon_id` on a hit; generate/store once
on a miss and draw with `template_icon()`. Only add a correctly registered and
removed debounce timer if measured continuous numeric dragging stalls; coalesce
to the latest request. Immutable previews per key avoid sharing incorrect pixels
between windows with different selections.

## Measurement sources and historical layout

| Context | Source and expected output |
|---|---|
| `MARCA_CONJUNTO in obj` | `obj.conj_largura_mm`, `obj.conj_altura_mm`, `obj.conj_profundidade_mm`; external box only, no child-detail inspection. |
| Panel with `obj.chapa_modo == 'INDIVIDUAL'` | Panel properties; proposed visual mapping `L = chapa_largura_mm`, `A = chapa_espessura_mm`, `P = chapa_comprimento_mm` shows a horizontal panel without changing local axes. |
| Panel with `obj.chapa_modo == 'GRUPO'` | `context.scene.grupo_largura_mm`, `grupo_altura_mm`, `grupo_profundidade_mm`; same external group box. |
| No valid panel/cabinet | Existing selection message, no preview or misleading default box. |

Historical layout proposal:

```python
linha_principal = box.row(align=False)
coluna_campos = linha_principal.column(align=True)
coluna_preview = linha_principal.column(align=False)
```

Use fixed `ui_units_x`/`template_icon(..., scale=...)` where possible; center in
its own column, keep thickness/synchronization/assembly controls and library
below measurements. The initial plan forbade region-width-dependent scale or
resolution; narrow layouts could stack without scaling. Native `EnumProperty`
with `expand=True` retains theme selection, immediately switching dimensions
and preview. Never put Individual/Group text inside the image.

Suggested helpers separate math, rasterization, cache and UI so pure math can
be tested outside Blender: `_medidas_wireframe(context)` returns mode/dimensions
or None; `_projetar_wireframe(largura, altura, profundidade)` returns eight 2D
points in projected millimeters; `_enquadrar_wireframe(pontos, largura_px,
altura_px, margem_px, escala_base)` applies uniform limited scale/centering;
`_arestas_wireframe()` returns twelve index pairs; `_rasterizar_wireframe`
returns transparent RGBA; `_chave_wireframe` builds a rounded/versioned key;
`_icone_wireframe(context)` returns an existing/new icon_id or zero;
`_limpar_cache_wireframe()` removes procedural cache entries only.

## Implementation sequence

1. Read `CLAUDE.md`, inspect git status/version, preserve unrelated changes and locate previews/`desenhar_medidas()`.
2. Isolate eight vertices, twelve edges, 45-degree projection, bounds, scale limit and centering; test numerically.
3. Rasterize one antialiased segment into a transparent buffer; clip loops, draw twelve edges, verify joins, buffer bounds and pixel Y orientation.
4. Integrate `_colecao_previews()`, `wireframe:` key, `icon_size`, pixels and icon_id; display separately and verify reload/deactivation.
5. Add rounded-key LRU and exercise more values than its limit; preserve library photos.
6. Integrate assembly/panel/Scene measurement sources, no-selection behavior and selection/mode switching.
7. Add controls/preview columns, centering and historical fixed scale; preserve existing controls and library order.
8. Change each measurement by typing and dragging; switch modes, objects and cabinet Empty; resize the N-panel.
9. Measure response, zero rasterization on cache hits, bounded memory and no per-update files/datablocks; add debounce only for a real problem.
10. Increment version, run `python -m py_compile archy_builder/__init__.py`, reload, execute manual matrix and update user documentation if needed. Never claim completion without executing its checks.

## Edge cases and verification matrix

Reject nonpositive dimensions defensively; epsilon only prevents division by
zero. Prefer no drawing plus a diagnostic to NaN/infinity. Height `1e9` mm stays
inside the canvas, reaches the vertical limit, permits other directions to
become tiny and raises nothing from `draw()`. An early small-dimension proposal
used natural scale without enlargement; 39.0.0 later required maximum-area fit.
Thin panels keep proportions and may have partly overlapping antialiased edges.
Wide panels never stretch strokes; narrow panels never throw and use controlled
stacking as required by the applicable refinement. Theme changes create a new
key without endless redraw. Undo/redo derive the key from restored values.
Unregister clears preview collection, Python LRU and any timer; reenabling is lazy.

Group inputs: 600 x 400 x 300; 600 x 2400 x 600; 2400 x 600 x 600;
300 x 300 x 1200; 10000 x 10000 x 10000; 100 x 1000000 x 100 mm.
Check proportions, 45-degree depth, centering, both limits, no clipping, exactly
twelve edges and no internal details. Individual inputs: 600 x 400 x 18;
2400 x 600 x 15; 300 x 300 x 30; 100 x 100 x 100 mm. Check correct dimensions,
recognizable thin panels, unchanged scene mesh and updates after valid thickness
changes. Double sidebar width, shrink to a practical minimum, change UI Scale,
check light/dark themes, repeated redraw/cache hits, eviction and library photos.

Acceptance requires both modes, external group box, twelve edges only, no
fill/details, transparency, fixed depth angle, influence of every dimension,
uniform scale, maximum-area fit, no extreme-input clipping, centering, constant
stroke, correct measurement/mode/selection updates, bounded cache, preserved
photos, no auxiliary scene objects or permanent per-update files, restored values
after undo/redo, full cleanup, py_compile and actual Blender validation. The
initial fixed-width acceptance item is superseded by the responsive refinement.

## Later responsive refinement and remaining visual choices

Recorded native-layout mitigation: stack below 310 logical px; no fixed field
width in narrow mode. Center L/A and P/E in explicit 50/50 cells and center the
container; without E, center P with 25/50/25. Below 210 logical px, center each
measurement, including Thickness, on its own row with 80% usable width. A newly
stacked wireframe retains scale 9 until available width itself requires less.
Horizontal layout reserves 4.5 UI units for controls and gives the rest to the
preview. Recorded ceilings: 7.5 narrow, 9 wide; final consolidated responsive
range 5..7.5 narrow, up to 9 wide. Center by alpha bounds including indicators.
These later decisions replace the original prohibition on responsive sizing.

Risks and mitigations: immutable keyed previews and cross-version checks for
ImagePreview updates; small canvas/local edge loops/cache and measured debounce
for Python rasterization cost; constrained sizing/stacking for native layout;
theme-derived keyed color plus tested fallback for contrast; exclusive prefix
and library checks for shared-cache cleanup.

Product decisions remain: dynamic proportional wireframe, fixed 45-degree depth,
external group box, no doors/handles/interiors/fills/colored reference markers,
limited fit preserving proportions, responsive range above and no auxiliary scene
objects. Visual refinement may choose exact resolution, scale, margin, stroke,
theme color, horizontal alignment, debounce, temporary-file fallback and minimum
sidebar behavior. Record final values in named constants and update changed
functional behavior here. Expected result: clean dimension fields and wireframe
beside them when space permits, stacked in a narrow panel, immediate proportional
updates and native, predictable interaction without changing the scene.
