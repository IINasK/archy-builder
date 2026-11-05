# Offline tools

`AGENTS.md` and `CLAUDE.md` are identical. Keep this guide concise and English.
Read only the relevant sector guide and `tests/AGENTS.md` before changing tools.

| Responsibility | Sector | Checks |
|---|---|---|
| Packaging and local Blender link | `development/` | empacotamento |
| DXF library import, integration and generators | `library/` | migracoes, importacao, biblioteca |
| Hardware extraction and generation | `hardware/` | migracoes, portas, puxadores |
| Staged repairs and publication | `migrations/` | migracoes, correcao_internos, soldas_biblioteca |
| Read-only internal geometry audit | `audit/` | auditoria_internos |

Tools are outside the installed add-on; package initializers must not execute them.
Every executable tool is two directories below the repository root. Resolve it
from `Path(__file__).resolve().parents[2]`, never the current working directory.
Use absolute `tools.<sector>.<module>` imports after making that root available.
Hardware sibling execution resolves from `Path(__file__).with_name(...)`.

Use English filenames and descriptions without external product branding.
Preserve legacy CLI flags, serialized keys, asset filenames and source provenance.
Import/preparation requires an explicit source directory (or category DXF file)
on the CLI; publication uses the source paths already recorded in its manifest.
Do not rename runtime APIs as part of moving these tools.

Tests use synthetic scenes, temporary staging and redirected library paths.
Never run a mutating tool on real assets or the open user project for verification.
Some generators/extractors execute immediately on import; inspect before importing.
GUI photo generation requires explicit authorization that the PC is free now.
Keep destination guards, all-file hash checks, backups and rollback intact.
Prepared manifests can pin absolute source paths and hashes: moving or changing
source files can invalidate publication, requiring a fresh preparation.
