# Architecture and task routing

Read the root instructions, then only the owner guide below. AGENTS.md and
CLAUDE.md are mirrors. Canonical technical paths use English; existing public
Python names and persisted identifiers remain compatible.

| Task | Owner under archy_builder/ | Guide | Harness suites |
|---|---|---|---|
| Panel mesh, thickness, Tab, A1..An, individual angles | cabinetry/panels/, shapes.py, fronts.py; core/geometry.py | cabinetry/panels/AGENTS.md | formas, geometria, frentes, hud |
| Cabinet body, bounds, resize, Outliner collections | cabinetry/cabinets/ | cabinetry/cabinets/AGENTS.md | armarios, operadores, organizacao |
| Doors, hinges, handles, opening and creation | cabinetry/doors/, door_assistant.py, hardware.py, handles.py; ui/door_controls.py | cabinetry/doors/AGENTS.md | portas, puxadores, importacao |
| Drawer boxes, rails, shared native capture | cabinetry/drawers/ | cabinetry/drawers/AGENTS.md | gavetas, areas_criacao |
| Shelf counts, E1..En, deletion, distribution | cabinetry/shelves/ | cabinetry/shelves/AGENTS.md | prateleiras |
| Partitions, segmentation, shared creation area | cabinetry/partitions/; ui/creation_areas.py | cabinetry/partitions/AGENTS.md | divisorias, areas_criacao |
| Backs, rail supports, depth coupling | cabinetry/backs.py, cabinets/ | cabinetry/AGENTS.md | fundos, gavetas, prateleiras |
| Welding, anchors, gap, detach/reset | cabinetry/welding.py | cabinetry/AGENTS.md | solda, hud |
| Sidebar layout, drawing, events, numeric editor | ui/sidebar*.py | ui/AGENTS.md | gaveta, medidas, snapshot, estrutura |
| Selection, viewport HUD, volume handles, fading | ui/selection.py, hud.py, volume_hud.py, visibility.py | ui/AGENTS.md | hud, operadores, visibilidade |
| Editor persistence and scene command bridge | ui/editor.py | ui/AGENTS.md | editor, biblioteca_faixa |
| Preferences, timers, native undo guards | core/options.py, events.py | core/AGENTS.md | operadores, medidas, estrutura |
| Masonry, face selection, room categories | architecture/masonry.py, rooms.py, walls.py, wall_selection.py | architecture/AGENTS.md | alvenaria, ambientes, paredes_selecao |
| Wall 2D sessions, placement, dimensions | architecture/wall_editor.py, wall_layout.py | architecture/AGENTS.md | paredes_edicao, paredes_composicao |
| Openings, installations, lighting, ceilings | architecture/installations.py, openings.py, lighting.py | architecture/AGENTS.md | instalacoes, esquadrias, iluminacao |
| Catalog, presets, DXF adoption, estimates, materials | integrations/ | integrations/AGENTS.md | biblioteca, importacao, orcamento |
| Offline import, repair, audit, hardware extraction | tools/ | ../tools/AGENTS.md | migracoes, soldas_biblioteca, auditoria_internos |
| Build and local Blender link | ../tools/development/ | ../tools/development/AGENTS.md | empacotamento |
| Harness, regression scenes and count floors | ../tests/ | ../tests/AGENTS.md | cobertura and changed suites |

Guide links above are repository paths under archy_builder/ unless prefixed
with ../. No sector owns another sector's geometry. Sidebar is UI, drawers are
furniture. Temporary previews contain numeric data, not scene RNA.

## Loading and compatibility

The installable root and Blender preference key are archy_builder. The user
authorized retiring the previous package identity before public use; no old-root
import shim or preference migration is installed. Its __init__.py explicitly
imports each implementation in dependency order,
registers its historical module alias immediately, and links `_name` references
after all implementations load. `_MODULOS` is the explicit reload/registration
inventory; `_MODULE_ALIASES` maps historical API names to those same objects.

The package rename requires restarting Blender and installing the current ZIP,
or relinking the development package. An already loaded old package cannot use
ordinary F3 reload across this change. Reload within archy_builder is tested.

There is ONE implementation per module. For example:
`archy_builder.portas is archy_builder.cabinetry.doors`.
Monkeypatches at either import reach all consumers; reload preserves module
identity and then relinks consumers. No facade copies, plugin discovery or
service locator is introduced. Canonical English imports are preferred for new
external tools; persisted APIs and existing callers remain valid.

Sector __init__.py files only establish package boundaries. Domain package
initializers hold their original implementation. Every new implementation must
enter explicit loading and structural coverage. Cross-domain calls stay module
qualified. Never import a function from another domain.

Cabinets coordinate body -> doors -> drawers -> shelves, once per owner.
`internos=False` updates only doors. The old door coordinator delegates to
cabinetry/cabinets; production does not call that compatibility entry point.
Partitions segment groups while drawers/shelves continue to own generated items.
Fronts owns the shared semantic face/edge reference and caches outside redraw.

## Data and tooling

`biblioteca/`, `ferragens/`, `fotos/` remain resource directories with their original
names and bytes. They are NOT Python packages. Existing saved library paths,
catalog UUIDs and user models must survive source reorganization.
Core preferences and resource owners resolve these paths from the add-on root,
not from their newly nested source directory.

Maintenance lives outside the installable add-on. Tools prepare in disposable
directories, validate and back up before explicitly publishing. Never test them
against the real library. Build runs from any working directory and produces
dist/archy_builder.zip containing archy_builder, LICENSE and NOTICE.

## Navigation and validation

Start with `rg -n '^def |^class ' archy_builder/<sector>/<owner>` or a function
name. Read the implementation and only its direct dependencies. Local guides
capture safety contracts; docs/reference retains detailed historical decisions.
Root guides <=200 lines, sector guides <=120, exact AGENTS/CLAUDE mirrors.

The organization suite verifies old and canonical import identity, coordinated
updates, reload, modeled meshes and undo. Structural tests compare all nested
implementations to explicit load order; no implementation may silently disappear.
Run targeted suites while changing code, then the entire 4.2/5.2 harness.

## Method and sources

The layout groups code by cohesive responsibility and separates installable code,
development tools, tests and documentation. It retains a flat installable package
because Blender loads that package directly; a new src layer adds no value here.
This is an application of the references below, not an architecture certification.

- [Python packages and relative imports](https://docs.python.org/3/tutorial/modules.html#packages).
- [PyPA: src layout versus flat layout](https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/).
- [Google: cohesive changes and separate refactoring](https://google.github.io/eng-practices/review/developer/small-cls.html).
