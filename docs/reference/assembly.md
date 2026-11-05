> Historical technical notes. Current instructions: [architecture](../../ARCHITECTURE.md) and local sector guides. Source paths below remain where historically relevant.

# Assembly and associations

Explicit reference for `archy_builder/cabinetry/welding.py`, `paredes.py`,
`ambientes.py`, `orcamento.py` and cabinet collection membership in `modulos/`.
This former guide is not inherited by source directories. Historical instruction
pairs were exact AGENTS/CLAUDE mirrors.

## Historical task routing

| Task | Entry | Suite |
|---|---|---|
| Join/detach panel | `solda.juntar_conexao`, `solda.desagregar` | hud |
| Cabinet link/folder | `modulos.agrupar_chapas`, `_garantir_colecao_modulo` | operadores, hud |
| Ruler/chain/reset/anchor | solda.py `cabinet_*` operators; hud.py | hud |
| Masonry/support/rooms | paredes.py marker/floor/G; ambientes.py faces/color/Collection | paredes, ambientes |
| 2D/Local View/preview/distribution | paredes_edicao.py | paredes_edicao, gaveta |
| Dimensions/fixed widths/redistribute/replace | paredes_composicao.py | paredes_composicao, hud |
| Room/estimate file | orcamento.py | orcamento |

Read [cabinets](../../archy_builder/cabinetry/cabinets/AGENTS.md) for envelope,
shared Collections/dependents, [interface](interface.md) for click/gizmo precedence,
and [integration](integration.md) for right-drag, face attachment, G/R and guides.

## Masonry, wall sessions and placement

- 404: orange Edit first, eye beside Ceiling, editing forces visibility. Installations reuse cascade/grid/photos and originating drag; right-drag uses same placement. Validate reassociation before writes, transfer only its cut, preserve components; undo/redo invalidate numeric cache (instalacoes).
- 403: face types in dedicated tab; native selector independent of room categories. Numeric preview from timer BMesh copy. Edit replaces chosen type only; confirm reads current native selection; materialize legacy normals first.
- 402: support UID/original face, planar dimensions, reversible Boolean Exact; cutter-face filtering for shells only. Openings, ceiling perimeter trim and lighting have separate owners.
- 399/398: automatic category/plane, Shift face, native Ctrl path/Shift+Ctrl fill. Mixed applies; all-same removes; No Category clears. Eye toggles colors/names. 2D categories retain session/proxy; clipped BVH limits hits/preview but whole native faces receive category. Side-by-side modes, red detach below; names apply on release. World normal distinguishes wall/floor/ceiling; free attachment and upright floor placement. Existing categories persist; new faces start 0. BMesh wrappers exist only transiently in Edit Mode, cleared before undo/save/load/unregister; FACE layer allocation requires recapture. INT FACE/UID map, copied cache, projection-depth bias. Room Collection membership uses UID; pulses remain reserved.
- 371: query only fixed wall, skipping hidden ceilings/backfaces. Points use native cursor/translate VERTEX/ONLY_SELECTABLE with restoration. >=90% visible on entry stays editable throughout session; others use gray locked evaluated/Boolean EXACT copies. Sources intact; clean temporaries/state on exit/undo/save.
- 367/366: continuous support in wall contact strip clips buried base. Proxy/dimensions/guides/drag share clipped region; partial/suspended supports and cabinets do not raise base. Distances accept zero; owner validates dimensions; <=1 micrometer noise never permits collision.
- 364: resize may rebuild components; `aplicar_ajuste_do_modelo` refreshes `novos` in finally from native hierarchy. Registration/Local View/rollback use the same live generation.
- 361: connected BMesh vertices (1 degree/2 mm), polygon >=3 points, hover ray/attachment highlight. Local View shows temporary selected region plus actual area-associated furniture; original mesh unchanged. Proxy ray resolves source/UID; cleanup on exit/save/unregister or regular timer after undo.
- 296: `paredes_edicao` stores names/numbers; native Local View preserves prior isolation/manual hiding. Orbit/Walk/Fly exit; zoom/pan stay. End before undo/open/save/unregister invalidates references. 4.2 Local View getter uses evaluated object. Library width/height fit limit 10 mm in 363, zero off, E unchanged; double-click right of last or centered if no room. Explicit redistribution; height/face/gaps/obstacles in planning and native BVH/rays for returns. Drawing reads numeric timer preview; failed attempt cleans only its own data.
- 297/298: `paredes_composicao` publishes numeric cabinet/gap records; `modulos.redimensionar_orientado` owns resize. `parede_largura_fixa` persists; move/delete recalculate gaps only. Validate replacement before deleting original. No wall measurements in menu. Temporary SOLID marker `cabinet_parede_exibicao_2d` may return through undo: clean in timer. Passive observer must not block G/Tab handler. Orbit returns PERSP; black outline temporary. `parede_ordem_posicionamento` retains last across sessions; hidden staging uses previous box because children do not update in depsgraph. `cabinet_parede_arestas_2d` restores panel show_wire after exit/undo; hardware excluded.
- 299/301: interior evaluated BMesh copy in timer, real creases without coplanar triangulation, numeric depsgraph-invalidated cache. POST_VIEW/GREATER draws hidden alpha lines without Mesh changes. Shared `faixas_livres`/`encaixar_na_face` for drag/library/insert/dimensions/distribution; exclude self, respect vertical overlap/face/holes/depth. Preview/crosshair use accepted envelope/center, not raw pointer.
- 312/313: any part selects cabinet for native G. Temporary VERTEX/CLOSEST in `visual['snap']`, restored. Depsgraph `acompanhar_arraste` updates numeric `_caixas`; timer owns cabinet/interior/box inventories. Scene `parede_guias`/`parede_guias_modo`; snap guides are edge-only `MARCA_OBJETO_GUIAS`, hide_select + EDGE. Without guide snap, `use_snap_selectable` excludes them. Scene `cabinet_parede_snap_2d` survives undo for timer restoration; orphan guide object removed.
- 315/317/318: `_medir_vaos` provides below/above; `parede_afastamento_mm` in CHAVES_ASSOCIACAO stores point ON plane, `matriz_na_parede` adds clearance. Timer/drag/insertion agree. Under `_transformando`, observer only marks `_movidos`; nonmodal timer `encaixar_movidos` snaps edges/limits to face. Outside 2D, `_mover_contra_parede` shares fit/matrix, associates in `_confirmar`.
- 319/321: user-remapped G or press/drag -> `OBJECT_OT_mover_na_parede`, `lado_sob`/`posicao_com_ima` on boxes, then face fit. Native snap cannot identify a whole side and confused front/back corners; wait for drag threshold. Real-scene region uses numpy `.corner_*` attributes, per-FACE cache and batch `faixas_da_face`, no Python face loop.
- 390/324/368: envelope uses `modulos.pecas_do_envelope` and nominal HUD corners, includes heavy-rail frames/supports, excludes open leaves/handles. Never fit group using inner door opening. `caixa_do_modulo` is in WALL frame from `parede_costas`, opposite door; use `referencial(conj)`/`escala_no_referencial`, not matrix_world. `medidas_na_parede` measures. A1/A2/A3 always on selection, A3 depth callout at corner. Resize hides distances; `_geometria_na_parede`/`_hud_na_parede` keep edge-center dots/`so_faces`, snap corner wins. Observer yields click to gizmo; typed input enters `digitacao_hud`.

## Joints and anchors

- Manual joints share native translate/snap; cached KDTree or native face query, never click-time mesh scans. Anchor/Join stores destination-local 3D separation in `adj_<ponta>_origens`. Legacy reset restores saved gap. New creation 352 resets against fixed FINAL anchor; that zero becomes future reference. Alt changes anchor without replacing reference.
- 353: chain/ruler/editable distance in preview; chain removes only pending pair, indexed ruler zeros against final anchor. Marker/distance read native cursor. Read-only cabinet audit chooses minimum distance first; one vertex may serve different destinations.
- 359: one record and one vertex pair per unordered OBJECT pair. Other joints stay independent even sharing a vertex. Library KDTree uses world positions for minimum real gap, without moving meshes.
- Creation panel excludes estimate/room; distance/zero/back/accept/cancel. Right/Esc cancels, Backspace/Ctrl+Z returns, Alt picks another vertex on same part. Snap starts PRESS, confirms RELEASE; modal handles shortcuts between gestures. Restore numeric preview before confirm/cancel; only `cabinet_juntar_modulo` stores final geometry undo.
- `adj_<ponta>_manual` retains chain/ruler/distance at zero; directions/origins destination-local. Box uses `cabinet_canto`; modeled mesh uses INT POINT `cabinet_solda_vertice` (u), legacy v accepted. Deleted/ambiguous IDs warn, never silently replace by proximity. Disconnect/replace also clears manual/directions.
- `normalizar_ligacoes=False` preserves anchor/origin/direction; True registers current minimum gap only in explicit migration. `adj_<ponta>_restricoes` keeps old axial fits on both ends without extra wire/record. Manual creates no extra automatic joints; repeated destination refused.
- 345/347: coordinator keeps domain order; unchanged door/shelf results avoid rebuilds, retaining BVHs/modeling. Validate repeated targets/thickness pairs BEFORE moving/updating; impossible joint cancels untouched, group validates all before first write. Reuse `_puxar_por_pares` validation; compute all deformation deltas before applying.
- 348/349: share detected chains within event; valid name/UID/parent avoid repeated searches. Dispatcher creates no undo; owner does, and external canceled ruler remains CANCELLED. Own release-triggered Create Joint in Cabinets/Assembly; cabinet chooses source at first snap, individual fixes source. Names only; reuse snap/cursor/originating confirmation.
- Adjacency stores current gap as origin. Chain/ruler appear for deviation (>5 mm viewport, any in button); both choose SAME part by selection, never record direction. Active panel moves (ask if dimensions must change); active cabinet adapts. Automatic cabinet joints require positive support area, not point/edge; loose panels retain legacy closure. Clear name AND UID, preserve manual anchors in optimization. HUD groups thickness controls without deleting links; Ctrl+D panel gets new UID/no joints; F3 Recalculate Anchoring.
- Alt-drag white endpoint changes `adj_<ponta>_ancoras` only; ruler moves active part from either side through normal joints and deforms remainder, including opposite thickness endpoint. Touching pair hides controls; new part returns to factory state.

## Estimates

Estimate belongs at end of Options; company .txt file for furniture, missing data
reported as pending, no ERP/clipboard flow. Room is the Outliner folder, sole
source, with a Cabinets field. `cadastro_do_modulo` (300) reads evaluated geometry
in group axes, actual leaves/drawers, hinge types and used-face materials. Never
persist preset counts; open doors do not enlarge envelope. Missing material or
hinge type remains pending rather than guessed.
