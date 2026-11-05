"""Replace hinge mounting screws with the generated standard hardware screw.

Run with the hinge asset open in background Blender 4.2 after generate_screw.py
and extract_hinge.py. Updates the stored hardware version and saves the hinge,
then executes extract_hinge_wireframe.py. Adjustment screws remain unchanged."""
from pathlib import Path
import json
import os
import runpy

import bpy
from mathutils import Matrix, Vector

AQUI = str(Path(__file__).resolve().parents[2])
FERRAGENS = os.path.join(AQUI, 'cabinet_creator', 'ferragens')
PARAFUSO = 'Parafuso Chipboard 3,5x14 Chata'
FIXACAO = ('Dobradica Parafuso.001', 'Dobradica Parafuso.002',
           'Dobradica Parafuso.003', 'Dobradica Parafuso.004')
VERSAO = 5


def assento(obj):
    """(matriz de mundo SEM escala no assento da cabeca, +Z = cabeca) do
    parafuso antigo: eixo = Z local (o mais comprido); a cabeca e' a ponta
    mais larga, o assento a menor altura com o raio dela."""
    vs = [v.co for v in obj.data.vertices]
    raio = lambda v: Vector((v.x, v.y)).length
    zs = sorted(v.z for v in vs)
    cima = [v for v in vs if v.z > zs[-1] - (zs[-1] - zs[0]) * 0.25]
    raio_cabeca = max(raio(v) for v in cima)
    z = min(v.z for v in vs if raio(v) > raio_cabeca * 0.9)
    mundo = obj.matrix_world @ Matrix.Translation((0.0, 0.0, z))
    local, rotacao, _escala = mundo.decompose()
    return Matrix.LocRotScale(local, rotacao, None)


with bpy.data.libraries.load(os.path.join(FERRAGENS, 'parafuso.blend'), link=False) as (de, para):
    para.meshes = [PARAFUSO]
malha = para.meshes[0]
for nome in FIXACAO:
    obj = bpy.data.objects[nome]
    antiga = obj.data
    if antiga.get('cabinet_origem', '').startswith('Parafuso Chipboard'):
        # o padrao anterior: a origem dele ja' e' o assento na placa
        local, rotacao, _escala = obj.matrix_world.decompose()
        pose = Matrix.LocRotScale(local, rotacao, None)
    else:
        pose = assento(obj)
    obj.modifiers.clear()          # subdivisao/suavizar eram do parafuso antigo
    obj.data = malha
    obj.matrix_world = pose
    if antiga.users == 0:
        bpy.data.meshes.remove(antiga)
malha.name = PARAFUSO                 # sem o .001 da malha que saiu
raiz = next(o for o in bpy.data.objects if o.get('cabinet_peca') == 'raiz')
raiz['cabinet_versao'] = VERSAO
bpy.data.orphans_purge(do_recursive=True)
caminho = os.path.join(FERRAGENS, 'dobradica_reta.json')
with open(caminho, encoding='utf-8') as f:
    dados = json.load(f)
dados['versao'] = VERSAO
with open(caminho, 'w', encoding='utf-8') as f:
    json.dump(dados, f, separators=(',', ':'))
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(FERRAGENS, 'dobradica_reta.blend'),
                            compress=True)
runpy.run_path(str(Path(__file__).with_name('extract_hinge_wireframe.py')))
print('[parafusos] %d trocados; versao %d' % (len(FIXACAO), VERSAO))
