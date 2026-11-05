"""Geometria das pecas: a AREA de chapa e a borda para o orcamento.

O detector de angulos (quinas, extremidades e centros de curva) servia ao
ima em Python; com o snap NATIVO do Blender (v304) ficou sem uso e saiu na
v309, a pedido do usuario.
"""

import bmesh
from bpy.types import Operator

# usados so' ao RODAR (import circular): o __init__ liga estes
# apelidos depois de carregar todos (`_ligar_modulos`)
_chapas = _modulos = None


# ============================================================ AREA
def medidas_da_chapa(obj):
    """(area m2, borda m) da peca pela MALHA: area = volume / espessura
    (vale para recorte, chanfro e curva: a area desenvolvida), borda =
    a area das laterais / espessura (o comprimento da fita de borda)."""
    if obj is None or obj.type != 'MESH' or not len(obj.data.polygons):
        return 0.0, 0.0
    espessura = float(getattr(obj, 'chapa_espessura_mm', 0.0) or 0.0) / 1000.0
    bm = bmesh.new()
    try:
        bm.from_mesh(obj.data)        # chapa nao tem escala (invariante 1)
        volume = abs(bm.calc_volume(signed=True))
        total = sum(f.calc_area() for f in bm.faces)
    finally:
        bm.free()
    if espessura <= 0.0:
        return total / 2.0, 0.0
    area = volume / espessura
    borda = max(0.0, (total - 2.0 * area) / espessura)
    return area, borda


def areas(objs):
    """Resumo de area das CHAPAS de `objs` (e dos filhos: portas,
    gavetas): {'pecas': [(nome, material, espessura, m2, borda m)],
    'por_material': {(material, espessura): m2}, 'total_m2', 'borda_m'}."""
    vistos, pecas = set(), []
    for obj in objs:
        for o in [obj] + list(obj.children_recursive):
            if o.name in vistos or o.type != 'MESH' or _chapas.MARCA_CHAPA not in o:
                continue
            vistos.add(o.name)
            area, borda = medidas_da_chapa(o)
            slot = next((s.material for s in o.material_slots if s.material), None)
            pecas.append((o.name, slot.name if slot else '', round(o.chapa_espessura_mm, 1),
                          area, borda))
    por_material = {}
    for _n, mat, e, area, _b in pecas:
        por_material[(mat, e)] = por_material.get((mat, e), 0.0) + area
    return {'pecas': pecas, 'por_material': por_material,
            'total_m2': sum(p[3] for p in pecas), 'borda_m': sum(p[4] for p in pecas)}


class OBJECT_OT_calcular_areas(Operator):
    """Area de chapa (m2) e comprimento de borda (m) dos modulos selecionados"""
    bl_idname = 'object.cabinet_calcular_areas'
    bl_label = 'Calcular Areas'
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return bool(context.selected_objects)

    def execute(self, context):
        alvos = []
        for obj in context.selected_objects:
            conj = _modulos._conj_de(obj)
            alvos.append(conj or obj)
        r = areas(alvos)
        if not r['pecas']:
            self.report({'WARNING'}, "Nenhuma chapa na selecao")
            return {'CANCELLED'}
        partes = ['%s %g mm: %.2f m2' % (mat or 'sem material', e, m2)
                  for (mat, e), m2 in sorted(r['por_material'].items())]
        self.report({'INFO'}, "%.2f m2 de chapa, %.1f m de borda (%d pecas) -- %s" % (
            r['total_m2'], r['borda_m'], len(r['pecas']), '; '.join(partes)))
        return {'FINISHED'}
