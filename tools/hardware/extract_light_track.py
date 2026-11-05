"""Extract light sliding-door track sections from the user source scene.

Adds LEVE to archy_builder/assets/hardware/trilho_moldura.json, preserving the
heavy-track sections. Requires the named sample board and evaluated U profiles.
Section coordinates are millimeters from the back and the board face."""
from pathlib import Path
import json
import os

import bmesh
import bpy

AQUI = str(Path(__file__).resolve().parents[2])
DESTINO = os.path.join(AQUI, 'archy_builder', "assets/hardware",
                       'trilho_moldura.json')
CHAPA, PERFIL = 'Base.002', 'Trilho inferior.001'
TOL = 1e-4          # m


def _contornos_da_ponta(obj):
    """Outlines (edge loops) at the minimum-Y end, in world space (m)."""
    grafo = bpy.context.evaluated_depsgraph_get()
    avaliado = obj.evaluated_get(grafo)
    malha = avaliado.to_mesh()
    bm = bmesh.new()
    bm.from_mesh(malha)
    bm.transform(obj.matrix_world)
    try:
        y0 = min(v.co.y for v in bm.verts)
        ponta = {v for v in bm.verts if abs(v.co.y - y0) < TOL}
        vizinhos = {v: [e.other_vert(v) for e in v.link_edges
                        if e.other_vert(v) in ponta] for v in ponta}
        # Traversal depends on the starting point (some evaluated mesh vertices
        # have more than two neighbors): try ALL starts and keep the longest loops.
        laços = []
        for inicio in ponta:
            for primeiro in vizinhos[inicio]:
                laço, vistos = [inicio, primeiro], {inicio, primeiro}
                anterior, atual = inicio, primeiro
                while True:
                    seguinte = next((n for n in vizinhos[atual]
                                     if n is not anterior and n not in vistos), None)
                    if seguinte is None:
                        break
                    laço.append(seguinte)
                    vistos.add(seguinte)
                    anterior, atual = atual, seguinte
                laços.append([v.co.copy() for v in laço])
        return laços
    finally:
        bm.free()
        avaliado.to_mesh_clear()


def _canais_da_chapa(obj, face_z):
    """[(x_min, x_max, bottom_z)] for grooves milled into the top face."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.transform(obj.matrix_world)
    try:
        y0 = min(v.co.y for v in bm.verts)
        faces = [f for f in bm.faces if all(abs(v.co.y - y0) < TOL for v in f.verts)]
        # A groove is the opening between faces reaching the top face with
        # a bottom below it: the low faces (top < face) beneath the groove.
        baixas = []
        for f in faces:
            zs = [v.co.z for v in f.verts]
            xs = [v.co.x for v in f.verts]
            if max(zs) < face_z - TOL:
                baixas.append((min(xs), max(xs), max(zs)))
        altas = sorted((min(v.co.x for v in f.verts), max(v.co.x for v in f.verts))
                       for f in faces
                       if abs(max(v.co.z for v in f.verts) - face_z) < TOL)
        canais = []
        for (a0, a1), (b0, b1) in zip(altas, altas[1:]):
            if b0 - a1 > TOL:          # Opening between two upper faces = groove.
                fundo = max(z for x0, x1, z in baixas if x0 <= a1 + TOL and x1 >= b0 - TOL)
                canais.append((a1, b0, fundo))
        return canais
    finally:
        bm.free()


def main():
    chapa = bpy.data.objects[CHAPA]
    face = max((chapa.matrix_world @ v.co).z for v in chapa.data.vertices)
    laços = _contornos_da_ponta(bpy.data.objects[PERFIL])
    costas = max(p.x for l in laços for p in l)       # Front is -X.
    u = lambda x: round((costas - x) * 1000.0, 3)
    v = lambda z: round((z - face) * 1000.0, 3)
    canais = sorted(_canais_da_chapa(chapa, face), key=lambda c: -c[0])
    centros = [round((u(c[0]) + u(c[1])) / 2.0, 3) for c in canais]
    # The U profiles are identical; one model has loose vertices, breaking
    # its loop into pieces. Use the longest complete loop, centered in
    # EACH groove.
    modelo = max(laços, key=len)
    perfil = [(u(p.x), v(p.z)) for p in modelo]
    meio = (min(a for a, _b in perfil) + max(a for a, _b in perfil)) / 2.0
    poligonos = [[(round(a - meio + c, 3), b) for a, b in perfil] for c in centros]
    dados = {
        'origem': os.path.basename(bpy.data.filepath),
        'versao_blender': bpy.app.version_string,
        'malha': PERFIL, 'chapa': CHAPA,
        'profundidade_mm': max(a for p in poligonos for a, _b in p),
        'aba_mm': max(b for p in poligonos for _a, b in p),
        'poligonos': poligonos,
        # Center of each groove (back -> front), width, and bottom.
        'canais_mm': centros,
        'canal_largura_mm': round(max(abs(u(c[0]) - u(c[1])) for c in canais), 3),
        'canal_fundo_mm': round(max(-v(c[2]) for c in canais), 3)}
    with open(DESTINO, encoding='utf-8') as arq:
        saida = json.load(arq)
    saida['trilhos']['LEVE'] = dados
    with open(DESTINO, 'w', encoding='utf-8') as arq:
        json.dump(saida, arq, indent=1)
    print('LEVE', len(poligonos), 'perfis', dados['profundidade_mm'], dados['aba_mm'],
          dados['canais_mm'], dados['canal_largura_mm'], dados['canal_fundo_mm'])
    print("Saved", DESTINO)


main()
