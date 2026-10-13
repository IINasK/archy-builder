"""Converte os modulos exportados do Promob em presets da biblioteca.

    blender --background --factory-startup --python importar_promob.py -- [pasta]

`pasta` (padrao: Documentos/Promob) tem uma pasta por AMBIENTE (Cozinha)
e, em qualquer subpasta, os .dxf: cada ARQUIVO e' uma categoria do Promob
(Cantos.dxf, Balcoes.dxf, Despenseiros.dxf...). Vira Armarios > Cozinha >
Inferiores > Cantos (a PASTA e' a aba, um nivel; o arquivo, o de baixo:
`importacao.categoria_promob`), presets "Canto 01 LxAxP"... O modulo vira
o NOSSO (`importacao.importar_dxf_promob` + `promob`). NAO abre janela; use o Blender 5.x (os
.blend saem no formato dele).
"""
import os
import sys
import traceback

import bpy

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import cabinet_creator as addon  # noqa: E402


def main():
    argumentos = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    raiz = argumentos[0] if argumentos else os.path.join(
        os.path.expanduser('~'), 'Documents', 'Promob')
    addon.register()
    for obj in list(bpy.data.objects):          # cubo, camera e luz de fabrica
        bpy.data.objects.remove(obj, do_unlink=True)
    total = 0
    try:
        for pasta, _dirs, arquivos in sorted(os.walk(raiz)):
            for nome in sorted(a for a in arquivos if a.lower().endswith('.dxf')):
                relativo = os.path.relpath(pasta, raiz).split(os.sep)
                ambiente = relativo[0] if relativo[0] != '.' else 'Diversos'
                caminho = os.path.join(pasta, nome)
                aba, categoria, prefixo = addon.importacao.categoria_promob(caminho)
                arqs, info = addon.importacao.importar_promob_para_biblioteca(
                    bpy.context, caminho,
                    ('Armarios', ambiente, aba, categoria), prefixo)
                total += len(arqs)
                print('[promob] %s/%s - %s: %d modulo(s) %s' % (
                    ambiente, aba, categoria, len(arqs), info))
    except Exception:
        traceback.print_exc()
        sys.exit(1)
    print('[promob] %d presets em %s' % (total, addon.biblioteca.pasta_biblioteca()))


main()
