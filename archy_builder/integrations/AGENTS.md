# Integrations

Keep AGENTS.md and CLAUDE.md identical, in English ASCII, at most 120 lines.
Read the root routing guide and the relevant domain/resource guide.
This sector owns runtime integration, not the repository's root tool scripts.

## Ownership

| Module | Responsibility | Legacy module |
|---|---|---|
| library.py | Presets, catalogs, index, append/save, photos and previews | biblioteca |
| materials.py | Material catalog, native linking and application scope | materiais |
| estimates.py | Geometry-based estimates and room affiliation | orcamento |
| importing.py | External object adoption and layered DXF ingestion | importacao |
| native_conversion.py | Imported geometry to native editable systems | promob |

Use neutral English filenames and descriptions of actual behavior. Preserve
legacy functions, attributes and identifiers, including brand-bearing data
keys or operator IDs required by older files/scripts. Do not substitute a
generic DXF promise for the existing layer-color and source-layout contract.
UI text uses English; internal function identifiers remain compatible.

## Imports and compatibility

The root owns the explicit canonical/legacy map, immediate sys.modules
aliases, dependency wiring, load order and registration. Canonical and
Portuguese imports/attributes must be the SAME module object.
Tests patch the owner, including legacy addon.biblioteca/opcoes attributes.
Do not add copied exports, facades, a plugin framework or another loader.
Reload each implementation once, then rewire references to its current code.

## Resources and persistence

- biblioteca, ferragens and fotos remain data directories with compatible
  existing paths. Do not add __init__.py or touch their .blend contents.
- library.py's former sibling fotos path and options.py's library default
  cannot be derived from the moved source directory. Resolve resource paths
  from the add-on root while preserving configured external library paths.
- There is one company library. Remove obsolete registered entries before
  adding the canonical entry; never create a parallel empty library.
- Existing index keys, file basenames, category paths and catalog UUIDs are
  contracts. Catalog membership lives inside the .blend, not only the index.
  Keep legacy categoria/subcategoria index reads and stable UUID migrations.
- Catalog writes stay atomic and occur only when content changes. Existing
  root-name migration aliases remain even when descriptions become neutral.
- Real-library publication requires existing staging, validation, backup,
  hash and rollback contracts. Moving Python code does not authorize it.
- Imported updates do not replace already-inserted scene instances.
- Preserve materials, modeled meshes, UIDs, parent relationships and
  independently editable native doors, drawers and shelves during adoption.
- DXF layer colors distinguish wood from hardware/accessories. Preserve
  measured support faces, openings, coverage, proportions and source
  references; never flatten modeled fronts or infer every front from -Y.
- Cabinet resize can recreate components. Refresh the live appended object
  list in finally so selection, Local View and rollback use current IDs.
- Previews/photos use disposable copies after saving; all doors close for
  photography. Native preview generation is asynchronous: keep the existing
  PNG application path rather than relying on asset_generate_preview alone.
- Materials use the established object-slot/native linking contracts.
  Estimates read evaluated geometry; missing data remains a pending item.

## Validation

Read root tests/AGENTS.md and the asset data guide before library work.
Relevant suites: biblioteca, importacao, migracoes, orcamento, frentes,
puxadores, biblioteca_faixa, organizacao, estrutura and snapshot.
Redirect library/default paths to temporary directories BEFORE register,
including after reload. Never write to the real library; fixtures are
temporary copies and real asset integrity checks are read-only.
Blender 4.2 cannot read 5.x library presets: retain the explicit skip.
GUI needs current permission; follow root delivery checks.
