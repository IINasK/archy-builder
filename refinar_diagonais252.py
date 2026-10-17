"""Folga real das pontas diagonais, com preparo/backup/releitura da 251.

Blender --background --factory-startup --python este_arquivo --
  --destino PASTA [--aplicar]
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mathutils.bvhtree import BVHTree
import refinar_diagonais251 as base


_validar_anterior = base.validar


def validar(conj):
    registros = _validar_anterior(conj)
    addon = base.addon
    chapas = addon.modulos._estruturais(addon.modulos._chapas_do_conjunto(conj))
    for grupo in addon.portas._portas_do_conjunto(conj):
        if grupo.get('porta_perfil_versao', 0) < 2:
            raise AssertionError('Perfil sem folga atualizada: '+conj.name)
        folha, = addon.portas._folhas_portas(grupo)
        fechada = addon.ferragens._matriz_fechada(folha)
        arvore = BVHTree.FromPolygons([fechada@v.co for v in folha.data.vertices],
                                     [list(p.vertices) for p in folha.data.polygons])
        for chapa in chapas:
            outra = BVHTree.FromPolygons([chapa.matrix_world@v.co for v in chapa.data.vertices],
                                         [list(p.vertices) for p in chapa.data.polygons])
            if arvore.overlap(outra):
                raise AssertionError('Porta atravessa '+chapa.name+' em '+conj.name)
    return registros


base.validar = validar
if __name__ == '__main__':
    base.main()
