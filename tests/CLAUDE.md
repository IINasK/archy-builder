# Test harness and regression policy

AGENTS.md and CLAUDE.md are exact mirrors, maximum 200 lines. Follow root
instructions. Scenario inventory: SCENARIOS.md in this directory.

## Execute

```
blender --background --factory-startup --python tests/run_tests.py
blender ... --python tests/run_tests.py -- --versoes 5.2 --suites hud
blender ... --python tests/run_tests.py -- --gui
blender ... --python tests/run_tests.py -- --atualizar
```

Blender's bundled Python can run the harness without starting Blender itself.
It discovers versions in C:/Program Files/Blender Foundation and starts each
suite in a SEPARATE factory-startup background process. Suites run in parallel;
GUI runs serially. A failure, missing suite, or count below PISO exits with 1.
Library timeout is 600 seconds; other suites 300. Run relevant suites while
working, then the COMPLETE harness before delivery in Blender 4.2 and 5.2.
`--gui` opens a real window and requires the user releasing the PC NOW.

## Layers

| Layer | Files | Detects |
|---|---|---|
| Headless unit/integration | test_*_blender.py | Geometry, data, tuple layouts |
| Characterization | test_snapshot_blender.py + snapshots/*.json | Unintended behavior changes |
| Real interaction | gui_*.py + interaction_harness.py | Keymaps, gizmos, hover, modal sequencing |
| Coverage contract | test_coverage_blender.py | Registered classes without tests, orphan snapshots |
| Count floors | PISO in run_tests.py | Silently removed or skipped tests |

## Required scenarios

Every bug fix requires an automated regression in the SAME commit: reproduce the
bug, fail before the fix, pass after it. Every improvement needs explicit input
parameters and expected outcomes. Record both in SCENARIOS.md. A fix is
unfinished without this regression. Use temporary scenes and directories;
never modify the open project or the actual library.

1. Every new registered class is cited by a meaningful test. SEM_TESTE_ACEITO
   requires a reason and may only shrink as coverage arrives.
2. Floors only rise. Any intentional removal needs explicit justification;
   never lower a floor just to make a refactor pass.
3. Only intentionally update snapshots with --atualizar; REVIEW the JSON diff.
4. Record discovered unfixed behavior as expectedFailure with a BUG comment.
   Remove the marker when fixed, keeping the reproducible regression.
5. Library tests redirect pasta_biblioteca and options._pasta_addon BEFORE
   register. Copy small fixtures and a sample (two presets/category) to temp;
   verify real-library hashes unchanged. Whole-library integrity reads only.
6. Blender 4.2 cannot read presets saved by 5.x. Explicitly skip incompatible
   preset reads; GUI uses Pular(reason). Do not hide code failures as version skips.
7. Use unittest, ASCII, temporary data, register/run/unregister and raise on
   failure. Patch the canonical owner module, never copied root functions.
8. Architecture refactors must preserve native undo, module identity/reload,
   modeled meshes, resource paths, operator IDs and saved data compatibility.

## GUI harness constraints

The official Blender ui_simulate/easy_keys pattern uses --enable-event-simulate
(ignores real keyboard/mouse). Tests are generators advanced by a timer;
each yield processes four event-loop ticks; esperar(seconds) waits on the clock.
Mouse.mover/clicar/apertar/soltar/tecla/digitar use WINDOW coordinates (region.x+x).
Use widget rectangles from _widgets_interativos, never fixed pixels; na_tela
projects 3D points. Read GUI fixtures before changing an interaction test.

- Background Window.event_simulate crashes 5.2 because eventstate is uninitialized,
  even with --enable-event-simulate. Use authorized GUI harness for gestures.
- Simulation does not generate DOUBLE_CLICK (check_double_click=false). Modal
  operators receive PRESS instead; photo double-click uses the clock.
- Keymap double-click tests invoke the operator with _ENTRADAS_KEYMAP properties
  in a real context. Windows delivery itself needs a physical mouse.
- popup_menu in background crashes Blender. _abrir_pergunta records the pending
  answer; tests call the response operator. GUI closes popup with ESC; moving
  the mouse does not close it and leaves the next test's first click swallowed.
- Blender only PRINTS draw/gizmo/timer exceptions. ErrosDeCallback captures stderr
  and fails even if assertions pass. Timer failures terminate with os._exit(code).
- Popup on PRESS consumes the same click's RELEASE as the first response. Sidebar
  popup/modal actions, including gizmo icons, trigger on RELEASE.
- bpy.ops from another operator receives current eventstate; esperar_soltar
  conveys a press-started operation. Do not infer it from the RELEASE context.
- Removing/rebinding menu gizmos during redraw crashes tooltip initialization.
  Retain gizmo pools and change visibility/operator hints.

Known expected failures remain in library tests; never delete them merely to
produce a green result. Record intermittent native undo results with logs and
baseline comparison rather than weakening assertions.
