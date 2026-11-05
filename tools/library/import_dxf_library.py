"""Import layered cabinet DXF exports into native library presets.

Runs immediately in a disposable background Blender 5.x process. Supply the
source directory explicitly after --; it follows the environment/category layout.
Writes to the configured library directly; this is not a staged migration."""
from pathlib import Path
import argparse
import os
import sys
import traceback

import bpy

AQUI = str(Path(__file__).resolve().parents[2])
sys.path.insert(0, AQUI)
import archy_builder as addon  # noqa: E402


def main():
    argumentos = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', help='Source directory containing the layered DXF exports')
    raiz = parser.parse_args(argumentos).source
    if not os.path.isdir(raiz):
        parser.error('The source directory must exist')
    addon.register()
    for obj in list(bpy.data.objects):          # cubo, camera e luz de fabrica
        bpy.data.objects.remove(obj, do_unlink=True)
    total = 0
    try:
        for pasta, _dirs, arquivos in sorted(os.walk(raiz)):
            for nome in sorted(a for a in arquivos if a.lower().endswith('.dxf')):
                caminho = os.path.join(pasta, nome)
                niveis, prefixo = addon.importacao.destino_categoria_promob(caminho,raiz)
                arqs, info = addon.importacao.importar_promob_para_biblioteca(
                    bpy.context, caminho,
                    niveis, prefixo)
                total += len(arqs)
                print('[dxf import] %s/%s - %s: %d modulo(s) %s' % (
                    niveis[1], '/'.join(niveis[2:-1]), niveis[-1], len(arqs), info))
    except Exception:
        traceback.print_exc()
        sys.exit(1)
    print('[dxf import] %d presets em %s' % (total, addon.biblioteca.pasta_biblioteca()))


main()
