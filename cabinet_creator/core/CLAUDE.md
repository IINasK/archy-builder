# Core runtime

Keep AGENTS.md and CLAUDE.md identical, in English ASCII, at most 120 lines.
Read the root routing guide before changing code. This guide covers only
this sector; read the owning sector guide for changes across boundaries.

## Ownership

| Module | Responsibility | Legacy module |
|---|---|---|
| options.py | Preferences, measurement formatting, option defaults | opcoes |
| events.py | Depsgraph/timer coordination, undo guards, reference invalidation | eventos |
| geometry.py | Shape recognition, measured areas, geometry queries | geometria |

Core is not a catch-all. Library/material integration belongs to integrations;
cabinet construction belongs to cabinetry and UI drawing/input to ui.
Do not move functions merely
because they are shared or because a file is long.

## Imports and lifecycle

- The root entry point owns the explicit import/alias map, load order,
  cross-module wiring, class registration and unregister cleanup.
- Canonical English imports and legacy cabinet_creator.<Portuguese>
  imports/attributes must resolve to the SAME module object.
- Keep existing Portuguese functions, dependency placeholders and APIs.
  Resolve calls on the owning module; never copy another sector's function.
- Root aliases are installed immediately after each canonical import.
  Import-time dependencies must already be loaded, including after reload.
- Reload each implementation once, in dependency order, then rewire.
  Sector initializers must not add a competing loader or registration path.

## Contracts and pitfalls

- Moving options.py changes __package__ and __file__. Preferences must still
  use the installed root add-on identity, not cabinet_creator.core.
- The library default still resolves the existing company library. Never
  derive it from the new options.py directory or create a second library.
- Code writing properties with update callbacks uses the existing busy
  guard with try/finally; geometry writes occur after releasing that guard.
- During undo/redo, handlers and timers must not inspect selection or
  rebuild meshes. Undo completion only releases the guard; the normal
  timer restores references and clears stale edit/modal transitions.
- Store names/numeric state instead of scene IDs across undo. Validate live
  targets before access. Preserve native selection, visibility and snapping.
- Never invoke bpy.ops during register; defer necessary work with timers.
  Remove every registered timer, handler, property and keymap on unregister.
- Mesh.unit_test_compare requires compatible attribute names/domains/types
  before native comparison; do not remove this Blender-version protection.

## Validation

Read tests/AGENTS.md from the repository root before changing tests.
Relevant suites: medidas, geometria, operadores, hud, organizacao, estrutura.
Test old and canonical owner patches, reload identity, preference lookup,
undo/redo and complete unregister. Use temporary scenes and library paths;
never modify the open project or the real library. GUI needs current,
explicit permission to use the PC. Follow root delivery checks.
