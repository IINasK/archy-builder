"""Validate real diagonal end clearance using the v251 staging and backup workflow.

Keeps the v252 migration identity. Importing this module extends the v251
validator; tests must restore that module state after use."""
from pathlib import Path
import os
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mathutils.bvhtree import BVHTree
import tools.migrations.refine_diagonal_fronts_v251 as base


_validar_anterior = base.validar


def validar(conj):
    registros = _validar_anterior(conj)
    addon = base.addon
    chapas = addon.modulos._estruturais(addon.modulos._chapas_do_conjunto(conj))
    for grupo in addon.portas._portas_do_conjunto(conj):
        if grupo.get('porta_perfil_versao', 0) < 2:
            raise AssertionError("Profile clearance not updated: "+conj.name)
        folha, = addon.portas._folhas_portas(grupo)
        fechada = addon.ferragens._matriz_fechada(folha)
        arvore = BVHTree.FromPolygons([fechada@v.co for v in folha.data.vertices],
                                     [list(p.vertices) for p in folha.data.polygons])
        for chapa in chapas:
            outra = BVHTree.FromPolygons([chapa.matrix_world@v.co for v in chapa.data.vertices],
                                         [list(p.vertices) for p in chapa.data.polygons])
            if arvore.overlap(outra):
                raise AssertionError("Door intersects "+chapa.name+" in "+conj.name)
    return registros


base.validar = validar
if __name__ == '__main__':
    base.main()
