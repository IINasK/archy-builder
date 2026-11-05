"""Export source edge-handle geometry or build the compatible hardware asset.

Run in the source Blender version with -- exportar OBJECT geometry.json,
then in background Blender 4.2 with -- montar geometry.json. Writes the
existing puxador_borda.blend/.json resources. The commercial handle length
is 80 mm, hole spacing 64 mm and projection 20 mm, for an 18 mm door."""
from pathlib import Path
import json
import os
import sys

import bmesh
import bpy
from mathutils import Vector

AQUI = str(Path(__file__).resolve().parents[2])
DESTINO = os.path.join(AQUI, 'archy_builder', 'ferragens')
NOME = 'Puxador Borda'
ESPESSURA_PORTA = 0.018      # o modelo e' montado para porta de 18 mm
COMPRIMENTO = 0.080
ENTRE_FUROS = 0.064
PROJECAO = 0.020             # quanto o tampo avanca a' frente da porta


def _vao(valores, filtro=lambda a, b: True):
    """(tamanho, a, b) do maior intervalo sem vertice que passa no filtro."""
    vs = sorted(set(round(c, 7) for c in valores))
    return max(((b - a, a, b) for a, b in zip(vs, vs[1:]) if filtro(a, b)), default=None)


def geometria_borda(objeto):
    """Geometria crua do objeto no referencial da linha, com as medidas
    comerciais: so' os trechos RETOS andam (furos, chanfros e o enrolado
    da frente continuam do modelo)."""
    dep = bpy.context.evaluated_depsgraph_get()
    # avaliado: o Smooth by Angle vira aresta viva (edge.smooth no BMesh)
    malha = bpy.data.meshes.new_from_object(objeto.evaluated_get(dep))
    bm = bmesh.new()
    bm.from_mesh(malha)
    bm.transform(objeto.matrix_world)
    ps = [v.co for v in bm.verts]
    x_meio = (min(p.x for p in ps) + max(p.x for p in ps)) / 2
    topo = max(p.z for p in ps)
    y_tras = max(p.y for p in ps)
    meio = [p for p in ps if abs(p.x - x_meio) < 0.02]
    # baixo do tampo (assenta na borda) entre a aba e o enrolado da frente,
    # que desce mais; dentro da aba (encosta nas costas da porta)
    baixo_tampo = min(p.z for p in meio if 0.0015 < y_tras - p.y < 0.0295
                      and topo - p.z < 0.003)
    dentro_aba = min(p.y for p in meio if baixo_tampo - p.z > 0.003)
    for v in bm.verts:
        x, y, z = v.co
        v.co = Vector((-(x - x_meio), baixo_tampo - z, (dentro_aba - y) - ESPESSURA_PORTA))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])

    xs = [v.co.x for v in bm.verts]
    comprimento = max(xs) - min(xs)
    furo = [v.co.x for v in bm.verts if v.co.z < -ESPESSURA_PORTA + 0.002
            and v.co.y > 0.003 and 0.005 < v.co.x < comprimento / 2 - 0.004]
    centro_furo = (min(furo) + max(furo)) / 2
    _, a1, b1 = _vao([abs(x) for x in xs], lambda a, b: a > centro_furo)
    _, a2, b2 = _vao([abs(x) for x in xs], lambda a, b: b <= min(furo) + 1e-6)
    corte_ponta, corte_meio = (a1 + b1) / 2, (a2 + b2) / 2
    d_meio = (ENTRE_FUROS - 2 * centro_furo) / 2
    d_ponta = (comprimento + 2 * d_meio - COMPRIMENTO) / 2
    zs = [v.co.z for v in bm.verts]
    _, a3, b3 = _vao(zs, lambda a, b: b > 0)
    corte_frente = (max(a3, 0.0) + b3) / 2
    d_frente = PROJECAO - max(zs)
    for v in bm.verts:
        x = v.co.x
        sinal = 1.0 if x > 0 else -1.0
        v.co.x = x + sinal * ((d_meio if abs(x) > corte_meio else 0.0)
                              - (d_ponta if abs(x) > corte_ponta else 0.0))
        if v.co.z > corte_frente:
            v.co.z += d_frente
    uv = bm.loops.layers.uv.active
    bm.verts.index_update()
    return {
        'origem': bpy.path.basename(bpy.data.filepath), 'objeto': objeto.name,
        'versao_blender': bpy.app.version_string,
        'vertices': [list(v.co) for v in bm.verts],
        'faces': [[v.index for v in f.verts] for f in bm.faces],
        'uv': [[list(l[uv].uv) for l in f.loops] for f in bm.faces] if uv else None,
        'vivas': [[e.verts[0].index, e.verts[1].index] for e in bm.edges if not e.smooth],
    }


def furos(vs):
    """[[x, y, z]] (m) de cada furo da aba: o centro dele no ASSENTO do
    parafuso (a face de fora da aba). A parede do furo e' o que fica entre
    as duas faces da aba, longe do tampo, da ponta de baixo e do
    arredondado das pontas (que tambem fica entre as faces)."""
    fora = min(v.z for v in vs)                       # face de fora da aba
    dentro = -ESPESSURA_PORTA
    meio = max(abs(v.x) for v in vs)
    parede = [v for v in vs if fora + 1e-5 < v.z < dentro - 1e-5
              and 0.002 < v.y < max(w.y for w in vs) - 0.002
              and abs(v.x) < meio - 0.004]
    resultado = []
    for lado in (-1, 1):
        pontos = [v for v in parede if v.x * lado > 0]
        resultado.append([round((min(v.x for v in pontos) + max(v.x for v in pontos)) / 2, 7),
                          round((min(v.y for v in pontos) + max(v.y for v in pontos)) / 2, 7),
                          round(fora, 7)])
    return resultado


def montar(dados):
    malha = bpy.data.meshes.new(NOME)
    malha.from_pydata(dados['vertices'], [], dados['faces'])
    malha.shade_smooth()
    if dados.get('uv'):
        camada = malha.uv_layers.new(name='UVMap')
        for poly, uvs in zip(malha.polygons, dados['uv']):
            for li, uv in zip(poly.loop_indices, uvs):
                camada.data[li].uv = uv
    vivas = {tuple(sorted(par)) for par in dados['vivas']}
    for e in malha.edges:
        e.use_edge_sharp = tuple(sorted(e.vertices)) in vivas
    # A escala -1 do objeto do usuario deixava o recalculo virado para
    # DENTRO (volume negativo): o solido fechado decide pelo volume.
    bm = bmesh.new()
    bm.from_mesh(malha)
    if bm.calc_volume(signed=True) < 0:
        bmesh.ops.reverse_faces(bm, faces=bm.faces[:], flip_multires=False)
        bm.to_mesh(malha)
    bm.free()
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    objeto = bpy.data.objects.new(NOME, malha)
    bpy.context.scene.collection.objects.link(objeto)
    # Normais NAO gravadas: esticar muda a forma das faces em volta dos
    # furos e normal gravada entortava (15 graus). O add-on poe o Weighted
    # Normal no puxador (`_normais_da_borda`), refeito a cada medida.
    final = malha
    final['cabinet_origem'] = NOME            # o add-on deduplica por isto

    vs = [v.co for v in final.vertices]
    xs, ys, zs = ([v[i] for v in vs] for i in range(3))
    # corte das COSTAS: o trecho reto do tampo sobre a porta (atras da face
    # da frente); a aba e o que fica atras dele andam com a espessura
    _, a, b = _vao(zs, lambda a, b: a < 0.0 < b)
    _, ax, bx = _vao(xs)
    medidas = {'origem': dados.get('origem'), 'objeto': dados.get('objeto'),
               'versao_blender': bpy.app.version_string, 'malha': NOME,
               'espessura_porta_mm': ESPESSURA_PORTA * 1000,
               'comprimento_mm': round((max(xs) - min(xs)) * 1000, 4),
               'entre_furos_mm': ENTRE_FUROS * 1000,
               'projecao_mm': round(max(zs) * 1000, 4),
               'aba_mm': round(max(ys) * 1000, 4),
               'tampo_mm': round(-min(ys) * 1000, 4),
               # onde a malha estica: x (comprimento) e z (espessura da porta)
               'corte_x': round((ax + bx) / 2, 7), 'vao_x': round(bx - ax, 7),
               'corte_costas': round(a + 0.95 * (0.0 - a), 7),
               'vao_costas': round(0.95 * (0.0 - a), 7),
               'furos': furos(vs)}
    os.makedirs(DESTINO, exist_ok=True)
    with open(os.path.join(DESTINO, 'puxador_borda.json'), 'w', encoding='utf-8') as f:
        json.dump(medidas, f, indent=1)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(DESTINO, 'puxador_borda.blend'),
                                compress=True, copy=True)
    print('[extrair] puxador borda:', medidas, len(final.vertices), 'vertices')


if __name__ == '__main__':
    argumentos = sys.argv[sys.argv.index('--') + 1:]
    if argumentos[0] == 'exportar':
        with open(argumentos[2], 'w') as f:
            json.dump(geometria_borda(bpy.data.objects[argumentos[1]]), f)
    else:
        with open(argumentos[1]) as f:
            montar(json.load(f))
