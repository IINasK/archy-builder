# Development tooling

Build and local Blender linking only. Do not import bpy here: these commands run
under ordinary Python or Blender's bundled Python from any working directory.
Repository root is resolved from __file__, never from the current directory.

- build.py packages cabinet_creator plus LICENSE/NOTICE into dist/archy_builder.zip.
  Retain the installable package name and exclude caches, backups and temp files.
- link_blender.py links the existing source to Blender's scripts/addons directory.
  Refuse to replace a normal directory which may contain the user's library.

Run tests/test_packaging_blender.py and the complete harness before delivery.
Use temporary fixtures; never replace installed user data during tests.
Mirror this file to CLAUDE.md. Root instructions apply.
