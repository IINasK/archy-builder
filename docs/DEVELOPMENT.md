# Developer guide

[User guide](../README.md) | **Developers**

Archy Builder is public and open for modification under [CC0](../LICENSE).
For installation and everyday use, follow the separate user guide.

## Get the source

```sh
git clone https://github.com/IINasK/archy-builder.git
cd archy-builder
```

Read [AGENTS.md](../AGENTS.md), then use
[ARCHITECTURE.md](../ARCHITECTURE.md) to find the owner and its local guide.
Technical filenames and context guides use English. Existing Portuguese APIs,
operator identifiers, saved properties and the Portuguese UI remain compatible.

## Develop against Blender

On Windows, link the checkout to the selected Blender version:

```sh
python tools/development/link_blender.py 5.2
```

Restart Blender and enable Archy Builder. The link reads source directly from
the checkout. The script refuses to replace a regular installation directory
which may contain user presets. Work in a disposable scene, not a live project.

After updating from version 407 or earlier to this layout, restart Blender once.
F3 Reload Scripts in an already loaded older session still refers to removed
source paths. Save your work and restart; no .blend migration is required.
F3 reload within the new layout is covered by the organization suite.

## Build the installation package

```sh
python tools/development/build.py
```

The output is **dist/archy_builder.zip**, ready to install. GitHub's automatic
source-code ZIP is the complete repository, not the installation package.
If Python is absent from PATH, use Blender's bundled interpreter:

```powershell
& 'C:\Program Files\Blender Foundation\Blender 5.2\5.2\python\bin\python.exe' tools/development/build.py
```

The package includes the library, LICENSE and NOTICE, excluding caches, backups
and temporary files. Its cabinet_creator root and saved editor/preference
identifiers remain unchanged for compatibility with existing .blend files.

## Validate changes

```powershell
& 'C:\Program Files\Blender Foundation\Blender 5.2\5.2\python\bin\python.exe' tests/run_tests.py
```

During work, add `-- --suites editor empacotamento` to run relevant suites.
Before delivery, run the complete harness in Blender 4.2 and 5.2. Each suite
uses a separate factory-startup process and temporary fixtures. GUI interaction
tests open windows and require current authorization to use the PC.
Never run tests against the open project or the actual preset library.
See [tests/AGENTS.md](../tests/AGENTS.md).

## Repository sectors

- cabinet_creator/core: preferences, lifecycle, geometry utilities.
- cabinet_creator/cabinetry: panels, cabinet bodies, doors, drawers, shelves,
  partitions, hardware, handles, backs and welding.
- cabinet_creator/architecture: masonry, rooms, wall editing, openings and lights.
- cabinet_creator/ui: editor, sidebar, selection, HUD and shared creation controls.
- cabinet_creator/integrations: catalogs, materials, DXF conversion and estimates.
- tools: development, library preparation, hardware extraction, audit, migrations.
- tests: headless regressions, snapshots and authorized interaction scenarios.
- docs: developer/reference/planning documentation and project design skill.

## Contribute

1. Fork the repository and create a branch for a cohesive change.
2. Read the sector guide and preserve stored data, native gestures and undo.
3. Add a regression for every bug; define inputs and expected results for features.
4. Register scenarios in [SCENARIOS.md](../tests/SCENARIOS.md).
5. Explain the problem, behavior and validation in the pull request.

UI changes follow [DESIGN.md](../DESIGN.md) and the
[cabinet-design skill](skills/cabinet-design/SKILL.md).
Contribute only content you can publish under CC0. Preserve external licenses
and provenance as described in [NOTICE](../NOTICE).

- [Architecture](../ARCHITECTURE.md)
- [Library contract](../cabinet_creator/biblioteca/AGENTS.md)
- [Historical documentation](HISTORY.md)
