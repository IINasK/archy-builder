# Hardware tools

Mirror this guide in `CLAUDE.md`; follow `../AGENTS.md`.
Extractors require named objects in a disposable source scene. Most scripts
execute immediately on import and write directly to `archy_builder/assets/hardware`.
Never import them for discovery or execute them against real assets in tests.

Keep the existing `.blend`/`.json` resource basenames and serialized schema.
`cabinet_origem`, `cabinet_peca`, `cabinet_versao`, `cabinet_sem_arame`, source
object names and JSON provenance remain compatibility data. Foreign metadata
cleanup keys must remain literal even when they identify another add-on.
Use Blender 4.2 when creating hardware read by both supported Blender versions.

Hinge workflow: `extract_hinge.py`, `generate_screw.py`, then
`replace_hinge_screws.py`. Both hinge scripts invoke the sibling
`extract_hinge_wireframe.py`; keep those paths independent of the working directory.
`extract_frame_track.py` preserves LEVE; `extract_light_track.py` preserves
CIMA/BAIXO in their shared JSON. `extract_edge_handle.py` retains its two CLI
modes, `exportar` and `montar`, for cross-version geometry transfer.
Checks: migracoes (safe resource-path checks), portas and puxadores.
