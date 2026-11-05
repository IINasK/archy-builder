"""Generate native cabinet presets in the configured library.

Runs immediately in background Blender 5.x and overwrites matching presets.
The native factory collection was retired; use only on a temporary library
or when explicitly requested. There is no staging or backup in this generator."""
from pathlib import Path
import os
import sys
import traceback

import bpy

AQUI = str(Path(__file__).resolve().parents[2])
sys.path.insert(0, AQUI)
import archy_builder as addon  # noqa: E402


def main():
    addon.register()
    for obj in list(bpy.data.objects):          # cubo, camera e luz de fabrica
        bpy.data.objects.remove(obj, do_unlink=True)
    feitos = 0
    try:
        for tipo, L, A, P, niveis, portas in addon.biblioteca.ARMARIOS_NATIVOS:
            arq = addon.biblioteca.gerar_armario_nativo(
                bpy.context, tipo, L, A, P, niveis, portas)
            feitos += 1
            print('[armarios nativos] %s' % os.path.basename(arq))
    except Exception:
        traceback.print_exc()
        sys.exit(1)
    print('[armarios nativos] %d presets em %s'
          % (feitos, addon.biblioteca.pasta_biblioteca()))


main()
