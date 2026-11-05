"""Generate the standard countersunk 3.5 x 14 mm hardware screw.

Run in background Blender 4.2 to preserve the oldest supported asset format.
Writes archy_builder/assets/hardware/parafuso.blend. Stored mesh names, version,
provenance and wireframe exclusion attributes remain compatible with saved scenes."""
from pathlib import Path
import math
import os

import bmesh
import bpy
from mathutils import Vector

AQUI = str(Path(__file__).resolve().parents[2])
DESTINO = os.path.join(AQUI, 'archy_builder', "assets/hardware")
NOME = 'Parafuso Chipboard 3,5x14 Chata'
MATERIAL = 'Aco Bicromatizado'
SEGMENTOS = 24
VERSAO = 2                   # 1 = flush 7 mm head (v326).
RAIO_CABECA = 2.889          # mm: the user's screw (5.78 mm head).
SALIENCIA = 0.876            # mm that the head top projects above the component, from the user's model.
# Profile (radius, z) in mm FROM THE TOP, descending: top, head edge,
# cone, smooth shank, thread core, and tip; shift everything upward
# by `SALIENCIA` at the end.
PERFIL = ((0.0, 0.0), (RAIO_CABECA, 0.0), (RAIO_CABECA, -0.15), (1.25, -2.4),
          (1.25, -4.4), (1.05, -4.6), (1.05, -12.0), (0.0, -14.0))
FENDA = (3.8, 0.9, 1.5)      # PH2: cross width, arm width, and depth.
AFINA_FENDA = 0.4            # Bottom cross size relative to the top.
# Thread (mm): crest, root inside the core, half thread base, pitch,
# start/end positions, and where it begins tapering toward the tip.
ROSCA = dict(crista=1.75, raiz=0.95, meia_base=0.5, passo=1.4, inicio=-4.7,
             fim=-13.6, afina=-11.6)
PASSOS_POR_VOLTA = 16
ATRIBUTO_SEM_ARAME = 'cabinet_sem_arame'     # `arame.ATRIBUTO_SEM_ARAME`


def malha_do_corpo():
    bm = bmesh.new()
    pontos = [bm.verts.new((r / 1000.0, 0.0, z / 1000.0)) for r, z in PERFIL]
    arestas = [bm.edges.new((a, b)) for a, b in zip(pontos, pontos[1:])]
    bmesh.ops.spin(bm, geom=pontos + arestas, cent=(0, 0, 0), axis=(0, 0, 1),
                   angle=math.tau, steps=SEGMENTOS, use_duplicate=False)
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-7)
    # Quads touching the axis become triangles; the exact Boolean
    # returned an empty result with degenerate faces.
    bmesh.ops.dissolve_degenerate(bm, edges=bm.edges[:], dist=1e-7)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    malha = bpy.data.meshes.new(NOME)
    bm.to_mesh(malha)
    bm.free()
    return malha


def recortar_fenda(malha):
    """Phillips recess: cross cut into the top with the Boolean applied."""
    cortador = bpy.data.meshes.new('Fenda')
    bm = bmesh.new()
    meia, meio_braco, fundo = FENDA[0] / 2000.0, FENDA[1] / 2000.0, FENDA[2] / 1000.0
    # Make the cross ONE 12-sided prism: two overlapping boxes caused
    # an empty exact Boolean result, or holes with the fast solver.
    a, b = meio_braco, meia
    cruz = ((a, b), (-a, b), (-a, a), (-b, a), (-b, -a), (-a, -a),
            (-a, -b), (a, -b), (a, -a), (b, -a), (b, a), (a, a))
    # Taper the bottom like a real Phillips recess: straight walls pierced the cone.
    base = bm.faces.new([bm.verts.new((x * AFINA_FENDA, y * AFINA_FENDA, -fundo))
                         for x, y in cruz])
    extrudado = bmesh.ops.extrude_face_region(bm, geom=[base])
    for v in [v for v in extrudado['geom'] if isinstance(v, bmesh.types.BMVert)]:
        v.co.x /= AFINA_FENDA
        v.co.y /= AFINA_FENDA
    bmesh.ops.translate(bm, vec=(0, 0, fundo + 0.001),
                        verts=[v for v in extrudado['geom'] if isinstance(v, bmesh.types.BMVert)])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    bm.to_mesh(cortador)
    bm.free()
    obj = bpy.data.objects.new(NOME, malha)
    corte = bpy.data.objects.new('Fenda', cortador)
    for o in (obj, corte):
        bpy.context.scene.collection.objects.link(o)
    corte.hide_set(True)
    booleano = obj.modifiers.new('Fenda', 'BOOLEAN')
    booleano.operation, booleano.solver, booleano.object = 'DIFFERENCE', 'EXACT', corte
    bpy.context.view_layer.update()
    final = bpy.data.meshes.new_from_object(obj.evaluated_get(
        bpy.context.evaluated_depsgraph_get()))
    obj.modifiers.clear()
    obj.data = final
    bpy.data.objects.remove(corte, do_unlink=True)
    bpy.data.meshes.remove(cortador)
    bpy.data.meshes.remove(malha)
    final.name = NOME
    return obj


def acrescentar_rosca(malha):
    """Triangular helical thread from the end of the smooth shank to
    the tip, tapering with it."""
    r = {k: v / 1000.0 for k, v in ROSCA.items()}
    bm = bmesh.new()
    bm.from_mesh(malha)
    antes = set(bm.verts)
    meio = r['inicio'] - r['meia_base']
    triangulo = bm.faces.new([bm.verts.new((r['raiz'], 0.0, meio + r['meia_base'])),
                              bm.verts.new((r['crista'], 0.0, meio)),
                              bm.verts.new((r['raiz'], 0.0, meio - r['meia_base']))])
    # The last thread base stops at `fim`.
    voltas = (r['inicio'] - r['fim'] - 2 * r['meia_base']) / r['passo']
    passos = round(voltas * PASSOS_POR_VOLTA)
    bmesh.ops.spin(bm, geom=[triangulo, *triangulo.verts, *triangulo.edges],
                   cent=(0, 0, 0), axis=(0, 0, 1),
                   dvec=(0, 0, -r['passo'] / PASSOS_POR_VOLTA),
                   angle=-math.tau * passos / PASSOS_POR_VOLTA, steps=passos,
                   use_duplicate=False)
    novos = [v for v in bm.verts if v not in antes]
    ponta = PERFIL[-1][1] / 1000.0
    for v in novos:
        if v.co.z < r['afina']:
            # The thread fades out at the tip, like a real screw.
            fator = max(0.0, (v.co.z - ponta) / (r['afina'] - ponta))
            v.co.x *= fator
            v.co.y *= fator
    faces = list({f for v in novos for f in v.link_faces})
    bmesh.ops.recalc_face_normals(bm, faces=faces)
    bm.to_mesh(malha)
    bm.free()


def suavizar(malha):
    """Sharp above 30 degrees, like Smooth by Angle on other components."""
    bm = bmesh.new()
    bm.from_mesh(malha)
    for e in bm.edges:
        e.smooth = not (len(e.link_faces) != 2
                        or e.calc_face_angle(0.0) > math.radians(30.0))
    for f in bm.faces:
        f.smooth = True
    bm.to_mesh(malha)
    bm.free()


def marcar_fora_do_arame(malha):
    """Only the head TOP (circle and cross) appears in the wireframe:
    the rest gets `cabinet_sem_arame` = 1 and is skipped by previews,
    selection, and handle outlines. Drawing everything on top made the
    cross bottom, doubled edge, and cone obscure the head (user screenshot);
    the thread filled the hinge with lines. The attribute survives when
    the add-on copies the screw to another mesh. Same rule as
    `ferragens.marcar_arame_parafuso`."""
    topo = max(v.co.z for v in malha.vertices) - 1e-6
    camada = malha.attributes.new(ATRIBUTO_SEM_ARAME, 'INT', 'EDGE')
    for e in malha.edges:
        camada.data[e.index].value = int(min(malha.vertices[i].co.z for i in e.vertices) < topo)
    malha['cabinet_arame_topo'] = True       # `arame.MARCA_ARAME_TOPO`


def elevar(malha):
    """Move the origin down to the component surface: the top sits
    `SALIENCIA` above it, matching the user's model."""
    for v in malha.vertices:
        v.co.z += SALIENCIA / 1000.0


def material():
    # Yellow chromate finish: yellow from the user's reference photo.
    cor = (0.78, 0.62, 0.28, 1.0)
    mat = bpy.data.materials.new(MATERIAL)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get('Principled BSDF')
    bsdf.inputs['Base Color'].default_value = cor
    bsdf.inputs['Metallic'].default_value = 1.0
    bsdf.inputs['Roughness'].default_value = 0.3
    mat.diffuse_color = cor
    mat.metallic, mat.roughness = 1.0, 0.3
    return mat


for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)
objeto = recortar_fenda(malha_do_corpo())
acrescentar_rosca(objeto.data)
suavizar(objeto.data)
elevar(objeto.data)
marcar_fora_do_arame(objeto.data)
objeto.data['cabinet_versao'] = VERSAO
objeto.data.materials.append(material())
for idb in (objeto.data, objeto.data.materials[0]):
    idb['cabinet_origem'] = idb.name          # The add-on uses this for deduplication.
bpy.data.orphans_purge(do_recursive=True)
os.makedirs(DESTINO, exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(DESTINO, 'parafuso.blend'),
                            compress=True, copy=True)
vs = [v.co for v in objeto.data.vertices]
print("[screw] %s: %d vertices, %d faces, head %.2f mm, length %.2f mm" % (
    NOME, len(vs), len(objeto.data.polygons),
    2000 * max(Vector((v.x, v.y)).length for v in vs),
    1000 * (max(v.z for v in vs) - min(v.z for v in vs))))
