"""Popula a biblioteca da empresa com os armarios NATIVOS de fabrica
(`biblioteca.ARMARIOS_NATIVOS`: balcoes, aereos, torres, roupeiros e
gabinetes -- caixa de chapas do add-on + fundo de 5 mm em canal + porta
Reta de giro, 1 ou 2 folhas, ou basculante nos aereos).

    blender --background --factory-startup --python gerar_armarios_nativos.py

NAO abre janela (a foto e' render Workbench por camera). Use o Blender
5.x: os .blend sairao no formato dele (o 4.2 nao le os da biblioteca).
Rodar de novo regrava os mesmos arquivos e as mesmas linhas do indice.

ATENCAO: grava em `pasta_biblioteca()`, a biblioteca REAL, sem backup.
Decisao do usuario: a biblioteca usa so' os modulos do Promob e os 39
nativos foram apagados -- nao rode sem pedido (biblioteca/AGENTS.md).
"""
import os
import sys
import traceback

import bpy

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import cabinet_creator as addon  # noqa: E402


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
