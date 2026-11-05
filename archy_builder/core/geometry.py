"""Part geometry: panel AREA and edge length for estimates.

The angle detector (corners, endpoints and curve centers) served Python
snapping. Native Blender snap in v304 made it unused; it was removed
in v309 at the user's request.
"""

import bmesh
from bpy.types import Operator

# Used only at runtime (circular imports): __init__ binds these
# aliases after loading all modules (`_ligar_modulos`).
_chapas = _modulos = None


# ============================================================ AREA
def medidas_da_chapa(obj):
    """Mesh-based (area m2, edge m): area = volume / thickness, giving
    developed area for notches/chamfers/curves. Edge length = side-face
    area / thickness, the required edge-band length."""
    if obj is None or obj.type != 'MESH' or not len(obj.data.polygons):
        return 0.0, 0.0
    espessura = float(getattr(obj, 'chapa_espessura_mm', 0.0) or 0.0) / 1000.0
    bm = bmesh.new()
    try:
        bm.from_mesh(obj.data)        # Panels have no scale (invariant 1).
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
    """Panel-area summary for `objs` and children such as doors/drawers:
    {'pecas': [(name, material, thickness, m2, edge m)],
    'por_material': {(material, thickness): m2}, 'total_m2', 'borda_m'}."""
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
    """Panel area in m2 and edge length in m for selected cabinets."""
    bl_idname = 'object.cabinet_calcular_areas'
    bl_label = "Calculate Areas"
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
            self.report({'WARNING'}, "No panel in the selection")
            return {'CANCELLED'}
        partes = ['%s %g mm: %.2f m2' % (mat or "no material", e, m2)
                  for (mat, e), m2 in sorted(r['por_material'].items())]
        self.report({'INFO'}, "%.2f m2 of panels, %.1f m of edging (%d parts) -- %s" % (
            r['total_m2'], r['borda_m'], len(r['pecas']), '; '.join(partes)))
        return {'FINISHED'}
