"""Parametric doors: parameters, openings, coverage, leaf calculation,
cabinet links, capture snapping, and wizard constants/calculations
(pistons and hinge boxes). The modal lives in `assistente`."""

import bpy, bmesh, math
from bpy.types import Operator
from mathutils import Matrix, Vector
from mathutils.interpolate import poly_3d_calc

# Used only at runtime (circular imports): __init__ binds these
# aliases after loading all modules (`_ligar_modulos`).
_chapas = _modulos = _ferragens = _puxadores = None
_prateleiras = None
_solda = None
_frentes = None

# ================================================ PARAMETRIC DOORS
LIMITES_FOLHAS = {'GIRO': 2, 'BASCULANTE': 1, 'CORRER': 4, 'ZIGZAG': 8}
ITENS_ABERTURA = (
    ('GIRO', "Hinged", "One or two leaves"),
    ('BASCULANTE', "Lift-up", "Exactly one leaf"),
    ('CORRER', "Sliding", "One to four inset leaves"),
    ('ZIGZAG', "Zig-zag", "Two to eight articulated leaves; handle on the last"),
)
ITENS_DOBRADICA = (
    ('ESCOLHER', "Choose a hinge...", "Selection required"),
    ('RETA', "Straight - Full Overlay", "Covers the full side thickness"),
    ('CURVA', "Half Crank - Partial Overlay", "Covers half the side thickness"),
    ('SUPER_CURVA', "Full Crank - Inset", "Inside the opening"),
)
# The sidebar edits door parameters directly without a popup, so they
# live on Scene. The operator receives complete values and opens no dialog.
# Keep labels short because each option becomes a button segment.
# FRONT is inferred from the diagonal (`_frente_automatica`), not chosen.
# Thickness is not a choice here either: side thickness comes from the
# cabinet; door thickness is edited through leaf E, like any other panel.
# Opening AXES follow the chain link: cabinet doors use cabinet axes,
# loose doors use world axes (`_referencia_do_par`).
ESCOLHAS_PORTAS = (
    ('porta_abertura', "Opening", (('GIRO', "Hinged"),
                                    ('BASCULANTE', "Lift-up"),
                                    ('CORRER', "Sliding"), ('ZIGZAG', 'Zig-zag'))),
)
# (property in meters, property in mm, label, minimum in mm).
MEDIDAS_PORTAS = (
    ('ui_porta_entre_folhas', 'porta_entre_folhas_mm', "Between Leaves", 0.0),
    ('ui_porta_afastamento', 'porta_afastamento_mm', "Offset", 0.0),
    ('ui_porta_recuo_embutida', 'porta_recuo_embutida_mm',
     "Inset Recess", 0.0),
    ('ui_porta_recuo_correr', 'porta_recuo_correr_mm',
     "Rail Recess", 0.1),
    ('ui_porta_entre_planos', 'porta_entre_planos_mm',
     "Between Planes", 0.1),
    # Sliding-door frame: editable as requested.
    ('ui_porta_moldura', 'porta_moldura_mm', "Thickness", 1.0),
    ('ui_porta_rodape', 'porta_rodape_mm', "Toe Kick", 0.0),
    ('ui_porta_testeira', 'porta_testeira_mm', "Fascia", 0.0),
)
# Default door dimensions for values that do not start at zero.
PADRAO_MEDIDAS_PORTAS = {'porta_entre_folhas_mm': 2.0,
                         'porta_recuo_correr_mm': 30.0,
                         'porta_entre_planos_mm': 2.0,
                         # Frame: all 15 mm as requested; plinth and fascia dimensions
                         # come from the user's wardrobe example.
                         'porta_moldura_mm': 15.0,
                         'porta_rodape_mm': 100.0,
                         'porta_testeira_mm': 80.0}


# Sidebar field -> group parameter for editing an installed door.
_PARAMETRO_DA_MEDIDA_PORTA = dict(
    [(m[0], m[1][len('porta_'):]) for m in MEDIDAS_PORTAS]
    + [('ui_porta_espessura', 'espessura_mm'),
       ('ui_porta_largura_folha', 'largura_folha_mm')])


def _parametros_portas_da_cena(s, numerico=False):
    """Use the names expected by `_PARAMETROS_PORTAS`.

    Thickness no longer lives on Scene: resolve it from the cabinet at
    creation (`_espessura_do_vao`). Supply defaults here to keep the
    dictionary complete. Operators store thickness as Enum STRINGs,
    but `_calcular_folhas_portas` performs arithmetic and cannot use text:
    direct calculation callers request `numerico=True`.
    """
    converter = float if numerico else (lambda v: v)
    padrao = '%d' % ESPESSURA_PADRAO_PORTA
    return {
        'abertura': s.porta_abertura,
        'folhas': s.porta_folhas,
        'dobradica': s.porta_dobradica,
        'espessura_mm': converter(padrao),
        'lateral_mm': converter(padrao),
        # No field (always zero by request); only imported doors store a value
        # to preserve their original position (`importacao`).
        'folga_mm': 0.0,
        'entre_folhas_mm': s.porta_entre_folhas_mm,
        'afastamento_mm': s.porta_afastamento_mm,
        'recuo_embutida_mm': s.porta_recuo_embutida_mm,
        'recuo_correr_mm': s.porta_recuo_correr_mm,
        'entre_planos_mm': s.porta_entre_planos_mm,
        'moldura_mm': s.porta_moldura_mm,
        'rodape_mm': s.porta_rodape_mm,
        'testeira_mm': s.porta_testeira_mm,
        'trilho': s.porta_trilho,
        'folha': s.porta_folha,
        # Creation-wizard hardware: 0 = automatic from leaf dimensions
        # (`_qtd_dobradicas_padrao`, `_qtd_pistoes_padrao`,
        # `_pistao_do_vao`); the wizard stores the selected values.
        'dobradica_lado': 'ESQUERDA',
        'dobradicas_qtd': 0,
        'dobradicas_margem_mm': MARGEM_DOBRADICAS_PADRAO,
        'pistoes_qtd': 0,
        'pistoes_offset_mm': 0.0,
    }


def _carregar_portas_na_cena(s, grupo):
    """Load an existing group's parameters into the sidebar."""
    guardados = grupo.get('porta_parametros') or {}
    for nome, valor in guardados.items():
        if nome in {'espessura_mm', 'lateral_mm'}:
            continue    # Stored on the group and cabinet, not the tab.
        elif nome == 'folhas':
            s.porta_folhas = int(valor)
        elif nome in {'abertura', 'dobradica', 'trilho', 'folha'}:
            setattr(s, 'porta_' + nome, valor)
        elif nome in _PARAMETROS_PORTAS and hasattr(s, 'porta_' + nome):
            # Wizard hardware (side/counts) lives only on the door.
            setattr(s, 'porta_' + nome, float(valor))


_PARAMETROS_PORTAS = (
    'abertura', 'folhas', 'dobradica', 'espessura_mm', 'lateral_mm',
    'folga_mm', 'entre_folhas_mm', 'afastamento_mm', 'recuo_embutida_mm',
    'recuo_correr_mm', 'entre_planos_mm',
    'moldura_mm', 'rodape_mm', 'testeira_mm', 'trilho', 'folha',
    'dobradica_lado', 'dobradicas_qtd', 'dobradicas_margem_mm',
    'pistoes_qtd', 'pistoes_offset_mm',
)


def _grupo_portas(obj):
    if obj is not None and _chapas.MARCA_PORTAS in obj:
        return obj
    if (obj is not None and _chapas.MARCA_FOLHA in obj and obj.parent is not None
            and _chapas.MARCA_PORTAS in obj.parent):
        return obj.parent
    return None


def _folhas_portas(grupo):
    return sorted((o for o in grupo.children if _chapas.MARCA_FOLHA in o),
                  key=lambda o: o.get('porta_indice', 0))


def _capturar_vertices_portas(context, com_objetos=False):
    """Read the live BMesh, including selection across two different panels."""
    if context.mode != 'EDIT_MESH':
        raise ValueError("Enter Edit Mode and select 2 diagonal vertices")
    marcados = []
    # Do not use unique_data: instances sharing a mesh have different matrices.
    for obj in context.objects_in_mode:
        if obj.type != 'MESH':
            continue
        bm = bmesh.from_edit_mesh(obj.data)
        for vert in bm.verts:
            if vert.select and not vert.hide:
                marcados.append((obj, obj.matrix_world @ vert.co))
                if len(marcados) > 2:
                    raise ValueError("Select exactly 2 vertices in total")
    if len(marcados) != 2:
        raise ValueError("Select exactly 2 vertices in total")

    referencia, pai = _referencia_do_par(marcados[0][0], marcados[1][0])
    resultado = marcados[0][1], marcados[1][1], referencia, pai
    return resultado + (marcados[0][0], marcados[1][0]) if com_objetos else resultado


def _referencia_do_par(obj_a, obj_b):
    """Opening orientation from the two parts' common ancestor.

    That ancestor supplies cabinet axes. A side panel's individual
    rotation is unsuitable because its local Z is thickness.
    """
    # Door-group Y is height; it is not the cabinet basis.
    modulo = _modulo_da_chapa(obj_a)
    if modulo is not None and modulo == _modulo_da_chapa(obj_b):
        return modulo.matrix_world.to_3x3().normalized(), modulo
    ancestrais = []
    pai = obj_a.parent
    while pai is not None:
        ancestrais.append(pai)
        pai = pai.parent
    pai = obj_b.parent
    while pai is not None and pai not in ancestrais:
        pai = pai.parent
    referencia = (pai.matrix_world.to_3x3().normalized()
                  if pai is not None else Matrix.Identity(3))
    return referencia, pai


NORMAIS_FRENTE = {'NEG_Y': (0, -1, 0), 'POS_Y': (0, 1, 0),
                  'NEG_X': (-1, 0, 0), 'POS_X': (1, 0, 0),
                  'NEG_Z': (0, 0, -1), 'POS_Z': (0, 0, 1)}
ESPESSURA_PADRAO_PORTA = 18.0


def _frente_automatica(referencia, ponto_a, ponto_b, centro):
    """Infer the opening face from the two marked points.

    The axis with NO variation is the face normal, including Z: a diagonal
    at constant height describes a horizontal door, such as a bench lid.
    Compare against the cabinet center to choose the outward face, never
    the opposite one. Ties prefer Y, then X, the usual front directions.
    """
    base = referencia.transposed()
    a = base @ Vector(ponto_a)
    b = base @ Vector(ponto_b)
    c = base @ Vector(centro)
    eixo = min((1, 0, 2), key=lambda i: abs(a[i] - b[i]))
    return ('NEG_' if a[eixo] < c[eixo] else 'POS_') + 'XYZ'[eixo]


def _resolver_frente(frente, referencia, ponto_a, ponto_b, centro):
    if frente != 'AUTO':
        return frente
    return _frente_automatica(referencia, ponto_a, ponto_b, centro)


def _largura_do_vao(referencia, ponto_a, ponto_b):
    """Width axis ('X' or 'Y') for a horizontal door.

    Upright doors always have height along Z, so this does not matter.
    For horizontal doors, width follows the LONGER diagonal component,
    which is the leaf subdivision direction. Store the result on the group
    so resizing that swaps the longer side does not rotate the door.
    """
    base = referencia.transposed()
    d = base @ (Vector(ponto_b) - Vector(ponto_a))
    return 'X' if abs(d.x) >= abs(d.y) else 'Y'


def _base_da_frente(referencia, frente, largura_em='X'):
    """Opening rows (right, up, normal): X=width, Y=height, Z=outward."""
    normal = referencia @ Vector(NORMAIS_FRENTE[frente])
    if frente.endswith('Z'):
        cima = referencia @ Vector((0, 1, 0) if largura_em == 'X'
                                   else (1, 0, 0))
    else:
        cima = referencia @ Vector((0, 0, 1))
    # Quaternion conversion loses Mirror reflection; width must retain parity.
    paridade = -1 if referencia.determinant() < 0 else 1
    return Matrix((cima.cross(normal).normalized() * paridade, cima, normal))


def _eixos_da_frente(frente, largura_em='X'):
    """Indices (width, height, normal) in cabinet axes."""
    if frente.endswith('Y'):
        return 0, 2, 1
    if frente.endswith('X'):
        return 1, 2, 0
    return (0, 1, 2) if largura_em == 'X' else (1, 0, 2)


def _espessura_do_vao(modulo, objetos=(), padrao=ESPESSURA_PADRAO_PORTA):
    """Thickness of the panels bounding the opening: the SIDE thickness.

    This used to duplicate cabinet E in a tab field; disagreement made
    the door protrude. Use cabinet thickness when linked, otherwise
    the clicked panel's thickness.
    """
    if modulo is not None:
        caixa = _caixa_do_modulo(modulo)
        if caixa is not None and caixa[3] > 0:
            return _chapas._espessura_livre(caixa[3])
    for obj in objetos:
        if obj is not None and _chapas.MARCA_CHAPA in obj and _chapas.MARCA_FOLHA not in obj:
            return _chapas._espessura_livre(obj.chapa_espessura_mm)
    return float(padrao)


def _espessura_da_porta_nova(modulo, objetos=(), padrao=ESPESSURA_PADRAO_PORTA):
    """New doors inherit cabinet thickness; edit leaf E afterwards.

    When supported by another door, inherit that door's thickness so
    two rows on the same cabinet start with equal thickness.
    """
    for obj in objetos:
        if obj is not None and _chapas.MARCA_FOLHA in obj:
            return float(obj.chapa_espessura_mm)
    return _espessura_do_vao(modulo, objetos, padrao)


def _centro_do_movel(obj_a, obj_b):
    """Interior cabinet point used to determine which face points outward.

    The cabinet origin is unsuitable: it sits at the BASE
    (`reposicionar_origem`), which would make a bottom door point upward.
    """
    modulo = _modulo_da_chapa(obj_a)
    if modulo is not None:
        limites = _limites_locais_modulo(modulo)
        if limites is not None:
            lo, hi = limites
            return modulo.matrix_world @ ((lo + hi) / 2000.0)
        return modulo.matrix_world.translation.copy()
    limites = _modulos._limites_mundo(bpy.context, {obj_a, obj_b})
    if limites is None:
        return (Vector(obj_a.matrix_world.translation)
                + Vector(obj_b.matrix_world.translation)) / 2.0
    lo, hi, _n = limites
    return Vector(((lo[i] + hi[i]) / 2.0 for i in range(3)))


def _mapear_vao_portas(ponto_a, ponto_b, referencia, frente, largura_em=None):
    """Orthonormal basis: X=width, Y=height, Z=out of the cabinet."""
    if largura_em is None:
        largura_em = _largura_do_vao(referencia, ponto_a, ponto_b)
    base = _base_da_frente(referencia, frente, largura_em).transposed()
    a = base.transposed() @ Vector(ponto_a)
    b = base.transposed() @ Vector(ponto_b)
    if abs(a.z - b.z) > 0.0001:
        raise ValueError("Vertices are not in the same front plane; check Front")
    largura, altura = abs(a.x - b.x), abs(a.y - b.y)
    if largura < 0.001 or altura < 0.001:
        raise ValueError("The vertices must form a diagonal with width and height")
    origem = base @ Vector((min(a.x, b.x), min(a.y, b.y),
                             (a.z + b.z) / 2.0))
    matriz = base.to_4x4()
    matriz.translation = origem
    return largura * 1000.0, altura * 1000.0, matriz


# Leaves NEVER sit flush with the cabinet edge: all standard coverages
# retain this clearance. Straight = thickness MINUS clearance;
# half overlay = half thickness minus clearance (two doors sharing an
# 18 mm middle panel covered 7 mm each, leaving 4 mm between leaves).
# Inset/sliding edges sit this far INSIDE the opening. `folga_mm`
# (no field; stored only for imports) adds to it. Nonstandard coverage
# explicitly marked and confirmed by the user is kept as marked.
RESPIRO_PORTA_MM = 2.0


def _cobertura_mm(fracao, lateral):
    """Panel coverage in mm from the thickness fraction; negative means
    the edge sits inside the opening."""
    if abs(fracao - 1.0) < 1e-9:
        return lateral - RESPIRO_PORTA_MM
    if abs(fracao - 0.5) < 1e-9:
        return max(0.0, lateral / 2.0 - RESPIRO_PORTA_MM)
    if abs(fracao) < 1e-9:
        return -RESPIRO_PORTA_MM
    return fracao * lateral


def _cobertura_porta(p):
    fracao = (0.0 if p['abertura'] == 'CORRER'
              else {'RETA': 1.0, 'CURVA': 0.5}.get(p['dobradica'], 0.0))
    return (fracao * p['lateral_mm'] if p.get('respiro_original')
            else _cobertura_mm(fracao, p['lateral_mm']))


# Per-side leaf coverage (left, right, bottom, top; same indices as
# `porta_ancora_*`) in SIDE-THICKNESS FRACTIONS: 1 covers the entire
# panel, 0.5 half, 0 puts the edge at the opening. Derived from four
# wizard clicks (door corner versus opening corner) or a thickness midpoint.
# Missing keys use hinge coverage. Fractions rather than mm make the door
# follow cabinet thickness. Store separate keys rather than a list:
# lists become IDPropertyArray, whose equality differs. Keep outside
# `_PARAMETROS_PORTAS`: these belong to the opening, not scene defaults.
COBERTURAS_LADOS = ('cobertura_esq_e', 'cobertura_dir_e',
                    'cobertura_baixo_e', 'cobertura_cima_e')
INDICE_LADO = {'ESQUERDA': 0, 'DIREITA': 1, 'BAIXO': 2, 'CIMA': 3}
TOL_COBERTURA_MM = 2.0      # Full overlay / half overlay / inset: +-2 mm.


def _inicios_porta(p):
    """Each leaf edge's intrusion into the opening (left, right, bottom, top):
    clearance - coverage; negative values cover the panel."""
    cobertura = _cobertura_porta(p)
    lateral = p['lateral_mm']
    converter = (lambda f, e: f*e) if p.get('respiro_original') else _cobertura_mm
    inicios = [p['folga_mm'] - (converter(float(p[k]), lateral) if k in p
                                else cobertura)
               for k in COBERTURAS_LADOS]
    if p.get('abertura') == 'CORRER' and _correr_sobreposta(p):
        # With a frame, the leaf covers the cabinet front as requested:
        # from the lower track (`_pe_da_folha_moldura`) to cabinet top;
        # the frame adds space above and, with a plinth, below.
        inicios[2] = _pe_da_folha_moldura(p)
        inicios[3] = -float(lateral)
    elif p.get('abertura') == 'CORRER':
        # Stand on the lower track guide; enter the upper channel with enough
        # clearance to lift out, matching the user's track photo. The track
        # sits on the opening edge.
        borda = [min(0.0, i) for i in inicios]
        inicios[2] = borda[2] + _ferragens.altura_trilho_baixo()
        inicios[3] = (borda[3] + _ferragens.TRILHO_CIMA_CHAPA_MM
                      + _ferragens.TRILHO_LEVANTAR_MM)
    return inicios


def _correr_sobreposta(p):
    """Sliding doors covering a panel on any side require a FRAME: the user's
    outer-to-inner gesture places leaves/tracks IN FRONT of the cabinet
    inside `_pecas_moldura`. Recessed doors within the opening are INSET."""
    if p.get('abertura') != 'CORRER':
        return False
    lateral = float(p.get('lateral_mm', ESPESSURA_PADRAO_PORTA))
    return any(_cobertura_mm(float(p[k]), lateral) > 1e-6
               for k in COBERTURAS_LADOS if k in p)


# ------------------------------------------------ FRAMED sliding doors
# User's wardrobe example: cladding on both sides, upper track base
# plus fascia, lower track base plus plinth, all `moldura_mm` (15).
# The frame ADDS above/below the cabinet and the 18 mm leaves cover
# its entire front. Tracks are the user's aluminum profiles
# (`_ferragens.perfil_trilho_moldura`) with two channels:
# one leaf per channel, alternating. Door coordinates: x across opening,
# y up, z OUTWARD (0 = cabinet front).
TRILHO_MOLDURA_COSTAS_MM = 16.0   # Cabinet front to track rear.
TRILHO_MOLDURA_FRENTE_MM = 4.0    # Track front to fascia.
INSERCAO_CANAL_MM = 15.0          # Leaf penetration into the upper channel.
ESPESSURA_PORTA_MOLDURA_MM = 18.0
# Answer to inset or framed installation for mixed midpoint clicks:
# coverage on all sides (`_preparar_vao_portas`).
TIPOS_CORRER = (('EMBUTIDA', "Inset Door"),
                ('MOLDURA', "Framed Door"))
COBERTURA_DO_TIPO_CORRER = {'EMBUTIDA': 0.0, 'MOLDURA': 1.0}
# For framed doors, the wizard asks about the BASE: some sliding cabinets
# sit directly on the floor without a lower front panel (plinth).
# No base means plinth 0, omitting that part; then expose the Plinth field.
OPCOES_BASE = (('COM', "With Plinth"), ('SEM', "Without Plinth"))
# Also ask TRACK TYPE: HEAVY uses the wardrobe's aluminum profiles
# (on the base, tall upper channel); LIGHT uses the track example's
# two ROUTED channels in the frame bases, on top of the lower base
# and under the upper one, with inset U profiles flush with the panel.
# Light-track channels are 17.3 mm apart: an 18 mm leaf cannot fit,
# so light-track leaves start at 15 mm.
ITENS_TRILHO = (('PESADO', "Heavy Track", "Aluminum profiles"),
                ('LEVE', "Light Track", "Grooves milled into the panel"))
OPCOES_TRILHO = tuple((k, t) for k, t, _d in ITENS_TRILHO)
ESPESSURA_PORTA_TRILHO = {'PESADO': ESPESSURA_PORTA_MOLDURA_MM, 'LEVE': 15.0}
FOLGA_TOPO_TRILHO_LEVE_MM = 5.0   # Leaf to upper base: clearance to lift out.
# Sliding-door LEAF: adapt the distinctive DXF pantry door to our style.
# Use MDF panels or an ALUMINUM FRAME: 23 mm deep, 10 mm face width,
# surrounding a 5 mm infill panel (glass, mirror, MDF) 6 mm behind
# the front and penetrating 5 mm into the profile (DXF dimensions).
# Retain the add-on's track.
ITENS_FOLHA_CORRER = (('CHAPA', "Panel", "MDF leaf"),
                      ('QUADRO', "Aluminum Frame",
                       "Aluminum profile surrounding a thin panel"))
OPCOES_FOLHA_CORRER = tuple((k, t) for k, t, _d in ITENS_FOLHA_CORRER)
ESPESSURA_QUADRO_MM = 23.0
FACE_QUADRO_MM = 10.0
PAINEL_QUADRO_MM = 5.0
PAINEL_FRENTE_MM = 6.0
PAINEL_ENTRA_MM = 5.0
NOME_MATERIAL_QUADRO = 'Aluminio Quadro'
NOME_MATERIAL_PAINEL = 'Painel Quadro'


def _moldura_mm(p):
    return float(p.get('moldura_mm', PADRAO_MEDIDAS_PORTAS['porta_moldura_mm']))


def _trilho_leve(p):
    return p.get('trilho') == 'LEVE'


def _perfil_trilho(p, lado='CIMA'):
    """Track-type profile (`_ferragens.perfil_trilho_moldura`):
    light tracks use the same U profile at top and bottom."""
    return _ferragens.perfil_trilho_moldura('LEVE' if _trilho_leve(p) else lado)


def _canais_moldura(p):
    """(rear, front): channel centers measured from the track rear."""
    if _trilho_leve(p):
        return tuple(_perfil_trilho(p)['canais_mm'])
    return _ferragens.CANAIS_TRILHO_MOLDURA_MM


def _espessura_porta_do_trilho(p):
    return ESPESSURA_PORTA_TRILHO.get(p.get('trilho'), ESPESSURA_PORTA_MOLDURA_MM)


def _folha_quadro(p):
    return p.get('folha') == 'QUADRO'


def _material_solido(nome, cor):
    mat = bpy.data.materials.get(nome)
    if mat is None:
        mat = bpy.data.materials.new(nome)
        mat.diffuse_color = cor
    return mat


def _vestir_folha(folha, p):
    """Aluminum frames enable `_chapas._malha_quadro` and its two materials;
    panel leaves revert to a box. No `_ocupado` here: these are ID
    properties, not properties with update callbacks."""
    if _folha_quadro(p):
        folha['chapa_quadro_mm'] = float(p.get('quadro_perfil_mm', FACE_QUADRO_MM))
        folha['chapa_painel_mm'] = float(p.get('quadro_painel_mm', PAINEL_QUADRO_MM))
        folha['chapa_painel_frente_mm'] = PAINEL_FRENTE_MM
        folha['chapa_painel_entra_mm'] = PAINEL_ENTRA_MM
        mats = folha.data.materials
        if len(mats) < 2:
            # Keep the user's object-slot finish in slot 1: the profile.
            while len(mats) < 2:
                mats.append(None)
            mats[0] = mats[0] or _material_solido(NOME_MATERIAL_QUADRO,
                                                  (0.62, 0.64, 0.67, 1.0))
            mats[1] = _material_solido(NOME_MATERIAL_PAINEL, (0.55, 0.7, 0.75, 1.0))
        return
    if 'chapa_quadro_mm' in folha:
        for chave in ('chapa_quadro_mm', 'chapa_painel_mm', 'chapa_painel_frente_mm',
                      'chapa_painel_entra_mm'):
            if chave in folha:
                del folha[chave]
        folha.data.clear_geometry()          # Start as a box again.
        mats = folha.data.materials
        while len(mats) > 1:
            mats.pop()
        if len(mats) and mats[0] is not None and mats[0].name == NOME_MATERIAL_QUADRO:
            mats[0] = None


def _avanco_moldura(p):
    """Cabinet front to fascia face, in mm."""
    return (TRILHO_MOLDURA_COSTAS_MM + _perfil_trilho(p)['profundidade_mm']
            + TRILHO_MOLDURA_FRENTE_MM + _moldura_mm(p))


def _sem_base(p):
    """Zero plinth means the frame sits directly on the floor (wizard choice)."""
    return float(p.get('rodape_mm', PADRAO_MEDIDAS_PORTAS['porta_rodape_mm'])) <= 0.0


def _topo_base_baixo(p):
    """Door-space y in mm of the lower base TOP, where the track rests.
    The base meets the cabinet bottom (y = -lateral) without the former
    6 mm gap. With a plinth, the base sits immediately BELOW the cabinet
    and the plinth extends down; without a base, it sits on the floor
    at cabinet-bottom level."""
    lateral = float(p['lateral_mm'])
    return -lateral + (_moldura_mm(p) if _sem_base(p) else 0.0)


def _pe_da_folha_moldura(p):
    """Framed leaf's bottom y: on the lower track, or on the light U-profile
    flange flush with the panel."""
    sobre = (_perfil_trilho(p)['aba_mm'] if _trilho_leve(p)
             else _ferragens.perfil_trilho_moldura('BAIXO')['altura_mm'])
    return _topo_base_baixo(p) + sobre


def _alturas_moldura(p, altura):
    """(upper-track y, upper-base y, lower-base y, lower-base underside y),
    in door-space mm. The light upper track is INSET into the upper base:
    both y values are its underside, a clearance above the leaf top."""
    lateral = float(p['lateral_mm'])
    if _trilho_leve(p):
        trilho_cima = base_cima = altura + lateral + FOLGA_TOPO_TRILHO_LEVE_MM
    else:
        trilho_cima = altura + lateral - INSERCAO_CANAL_MM
        base_cima = (trilho_cima
                     + _ferragens.perfil_trilho_moldura('CIMA')['altura_mm'])
    base_baixo = _topo_base_baixo(p)
    return trilho_cima, base_cima, base_baixo, base_baixo - _moldura_mm(p)


def _canais_das_bases(p):
    """Return {part: (local x mm, width, depth, side)} for routed LIGHT-track
    frame-base channels (`_chapas._malha_com_canais`): above the lower base
    (side +1), below the upper (-1). Base local x = door z minus half
    the projection (axis 1 of `EIXOS_PECA_MOLDURA`)."""
    if not _trilho_leve(p):
        return {}
    leve = _perfil_trilho(p)
    meio = _avanco_moldura(p) / 2.0
    xs = [TRILHO_MOLDURA_COSTAS_MM + c - meio for c in leve['canais_mm']]
    dados = (xs, leve['canal_largura_mm'], leve['canal_fundo_mm'])
    return {'BASE_BAIXO': dados + (1,), 'BASE_CIMA': dados + (-1,)}


# Local X/Y/Z columns in door coordinates, indexed by thickness axis:
# panel X=width, Y=length, Z=thickness (invariant 1).
EIXOS_PECA_MOLDURA = {
    0: ((0, 0, 1), (0, 1, 0), (-1, 0, 0)),   # Side: depth x height.
    1: ((0, 0, 1), (1, 0, 0), (0, 1, 0)),    # Base: depth x width.
    2: ((1, 0, 0), (0, 1, 0), (0, 0, 1)),    # Fascia/plinth: front-facing.
}


def _pecas_moldura(p, largura, altura, profundidade=0.0):
    """Return [(id, name, box (x0, x1, y0, y1, z0, z1) mm, thickness axis)]
    for the frame; empty for other door types. `profundidade` is cabinet
    depth: side cladding extends from its rear to the frame front."""
    if not _correr_sobreposta(p):
        return []
    lateral, t = float(p['lateral_mm']), _moldura_mm(p)
    avanco = _avanco_moldura(p)
    _trilho, base_cima, base_baixo, fundo_baixo = _alturas_moldura(p, altura)
    teto = base_cima + t
    piso = fundo_baixo - float(p.get('rodape_mm', 0.0))
    x0, x1 = -lateral, largura + lateral
    # The LIGHT track has no upper front closure, matching the user's image:
    # the leaf remains exposed up to the upper base.
    testeira = 0.0 if _trilho_leve(p) else float(p.get('testeira_mm', 0.0))
    pecas = [
        ('LATERAL_ESQ', "Left Side Frame",
         (x0 - t, x0, piso, teto, -profundidade, avanco), 0),
        ('LATERAL_DIR', "Right Side Frame",
         (x1, x1 + t, piso, teto, -profundidade, avanco), 0),
        ('BASE_CIMA', "Upper Frame Base",
         (x0, x1, base_cima, teto, 0.0, avanco), 1),
        ('TESTEIRA', "Frame Fascia",
         (x0, x1, base_cima - testeira, base_cima, avanco - t, avanco), 2),
        ('BASE_BAIXO', "Lower Frame Base",
         (x0, x1, fundo_baixo, base_baixo, 0.0, avanco), 1),
        ('RODAPE', "Frame Plinth",
         (x0, x1, piso, fundo_baixo, avanco - t, avanco), 2),
    ]
    # Zero plinth/fascia: omit the part.
    return [peca for peca in pecas
            if min(peca[2][1] - peca[2][0], peca[2][3] - peca[2][2],
                   peca[2][5] - peca[2][4]) > 0.5]


def _matriz_peca_moldura(caixa, eixo):
    """Return (matrix_basis in m, (width, length, thickness) in mm)."""
    x0, x1, y0, y1, z0, z1 = caixa
    medidas = (x1 - x0, y1 - y0, z1 - z0)
    colunas = [Vector(c) for c in EIXOS_PECA_MOLDURA[eixo]]
    rotacao = Matrix(colunas).transposed()        # Vectors are COLUMNS.
    centro = Vector(((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)) / 1000.0
    dims = tuple(abs(c.dot(Vector(medidas))) for c in colunas)
    return Matrix.Translation(centro) @ rotacao.to_4x4(), dims


def _montar_moldura(grupo, pecas, canais=None):
    """Create/update/remove frame panels by part ID, as with leaves, under
    `_ocupado`. `canais` supplies light-track base grooves
    (`_canais_das_bases`). Return the remaining parts."""
    canais = canais or {}
    existentes = {}
    for o in list(grupo.children):
        if _chapas.MARCA_MOLDURA in o:
            if o.get('porta_moldura_peca') in existentes:
                _remover_chapa(o)
            else:
                existentes[o.get('porta_moldura_peca')] = o
    feitas = []
    for chave, nome, caixa, eixo in pecas:
        obj = existentes.pop(chave, None)
        if obj is None:
            obj = bpy.data.objects.new(nome, bpy.data.meshes.new(nome))
            grupo.users_collection[0].objects.link(obj)
            obj[_chapas.MARCA_CHAPA] = 1
            obj[_chapas.MARCA_MOLDURA] = 1
            obj['porta_moldura_peca'] = chave
        elif obj.data.users > 1:
            obj.data = obj.data.copy()
        _ferragens._padronizar_nome(obj, nome)
        obj.parent = grupo
        obj.matrix_parent_inverse = Matrix.Identity(4)
        matriz, (l, c, e) = _matriz_peca_moldura(caixa, eixo)
        obj.matrix_basis = matriz
        obj.chapa_largura_mm = l
        obj.chapa_comprimento_mm = c
        obj.chapa_espessura_mm = e
        obj.chapa_auto = True
        _gravar_canais(obj, canais.get(chave))
        feitas.append(obj)
    for obj in existentes.values():
        _remover_chapa(obj)
    return feitas


CHAVES_CANAIS = ('chapa_canais', 'chapa_canal_largura', 'chapa_canal_fundo',
                 'chapa_canal_lado')


def _gravar_canais(obj, dados):
    """Lengthwise panel grooves for light-track bases, cut into the mesh
    by `_chapas._malha_com_canais`; None removes them."""
    if dados is None:
        if 'chapa_canais' in obj:
            # Back to heavy tracks: an empty mesh becomes a box again. Otherwise
            # the grooved mesh would count as modeled and stretch its grooves too.
            obj.data.clear_geometry()
        for chave in CHAVES_CANAIS:
            if chave in obj:
                del obj[chave]
        return
    xs, largura, fundo, lado = dados
    obj['chapa_canais'] = [float(x) for x in xs]
    obj['chapa_canal_largura'] = float(largura)
    obj['chapa_canal_fundo'] = float(fundo)
    obj['chapa_canal_lado'] = int(lado)


def _remover_chapa(obj):
    malha = obj.data
    bpy.data.objects.remove(obj, do_unlink=True)
    if malha is not None and malha.users == 0:
        bpy.data.meshes.remove(malha)


def _moldura_da_porta(grupo):
    return [o for o in grupo.children if _chapas.MARCA_MOLDURA in o]


def _espessura_da_moldura_mudou(peca, espessura):
    """ONE frame part's E applies to the entire frame, as for leaves."""
    grupo = peca.parent
    if (grupo is None or _chapas.MARCA_PORTAS not in grupo
            or not grupo.get('porta_parametros')):
        return False
    erro = _editar_parametro_porta(bpy.context, grupo, 'moldura_mm', espessura)
    if erro:
        print("[Archy Builder] frame thickness:", erro)
        return False
    return True


def _encaixar_cobertura(mm, lateral):
    """Measured coverage (mm) -> thickness fraction, snapping to full (1),
    half (0.5) or inset (0) within TOL_COBERTURA_MM."""
    for fracao in (1.0, 0.5, 0.0):
        if abs(mm - fracao * lateral) <= TOL_COBERTURA_MM:
            return fracao
    return mm / lateral


def _coberturas_dos_cantos(bordas, vaos, lateral):
    """Per-side {key: fraction}: from DOOR corners (clicks 1 and 4)
    to OPENING corners (2 and 3), in door-space mm."""
    bx, by = [p.x for p in bordas], [p.y for p in bordas]
    vx, vy = [p.x for p in vaos], [p.y for p in vaos]
    mm = (min(vx) - min(bx), max(bx) - max(vx),
          min(vy) - min(by), max(by) - max(vy))
    return {k: _encaixar_cobertura(c, lateral)
            for k, c in zip(COBERTURAS_LADOS, mm)}


def _espelhar_margem(bordas, vaos):
    """Clicks 1 and 2 at the SAME point (or 3 and 4): use the other pair's
    margin INWARD from that click, as requested. Return (openings, mirrored
    sides). If neither pair has a margin, keep the usual conversion."""
    tolerancia = _modulos.TOL_BORDA * 1000.0
    margens = [Vector(((v - b).x, (v - b).y)) for b, v in zip(bordas, vaos)]
    zeros = [m.length <= tolerancia for m in margens]
    novos = [v.copy() for v in vaos]
    espelhados = [False, False]
    for i in (0, 1):
        if zeros[i] and not zeros[1 - i]:
            for eixo in (0, 1):
                dentro = 1 if vaos[1 - i][eixo] > bordas[i][eixo] else -1
                novos[i][eixo] = (bordas[i][eixo]
                                  + dentro * abs(margens[1 - i][eixo]))
            espelhados[i] = True
    return novos, espelhados


def _lados_fora_do_padrao(coberturas):
    """Sides with neither full, half nor inset coverage: the wizard
    asks whether the dimensions are correct."""
    return [k for k in COBERTURAS_LADOS
            if k in coberturas and coberturas[k] not in (0.0, 0.5, 1.0)]


def _porta_embutida(coberturas):
    """No side covers a panel: the door sits INSIDE the opening."""
    return bool(coberturas) and all(f <= 0.0 for f in coberturas.values())


NOME_DOBRADICA = {'RETA': "Full Overlay", 'CURVA': "Half Crank",
                  'SUPER_CURVA': "Full Crank"}


def _dobradica_da_cobertura(fracao, embutida=False):
    """Infer the hinge from its side's coverage, as requested: full thickness
    = straight/full-overlay, half = half-overlay, inside = inset hinge."""
    if embutida:
        return 'SUPER_CURVA'
    return 'RETA' if fracao >= 0.75 else 'CURVA'


def _meias_do_vao(a, b, base, objetos, pontos):
    """A point marked at panel thickness midpoint (offered by edge-midpoint
    snapping) extends the opening to the face toward the other point,
    with half-thickness coverage on that side.

    Adjust `pontos` (mm in the `base` frame) and return side bits.
    """
    meias = 0
    originais = (Vector(a), Vector(b))
    for i, obj in enumerate(objetos):
        if obj is None or obj.type != 'MESH' or _chapas.MARCA_CHAPA not in obj:
            continue
        zs = [v.co.z for v in obj.data.vertices]
        if not zs:
            continue
        meio, metade = (max(zs) + min(zs)) / 2.0, (max(zs) - min(zs)) / 2.0
        local = obj.matrix_world.inverted() @ originais[i]
        if metade <= 2 * _modulos.TOL_BORDA or abs(local.z - meio) > _modulos.TOL_BORDA:
            continue
        espessura = base @ (obj.matrix_world.to_3x3() @ Vector((0, 0, 1)))
        eixo = 0 if abs(espessura.x) >= abs(espessura.y) else 1
        if abs(espessura.normalized()[eixo]) < 0.9:
            continue        # Thickness outside the door plane.
        alvo = (base @ originais[1 - i])[eixo] * 1000.0
        sinal = 1 if alvo > pontos[i][eixo] else -1
        pontos[i][eixo] = ((base @ originais[i])[eixo]
                           + sinal * metade * espessura.length) * 1000.0
        meias |= 1 << (2 * eixo + (0 if sinal > 0 else 1))
    return meias


def _preparar_vao_portas(a, b, referencia, frente, parametros,
                         modulo=None, objetos=(None, None), portas=None,
                         forcar=''):
    """Convert external corners and door contacts to an internal opening.

    `portas`: DOOR corners (wizard clicks 1 and 4; a and b bound the
    opening). Return (opening, world points, supports, per-side coverages).
    `forcar` is the inset/frame answer (`TIPOS_CORRER`): use the cabinet's
    INTERNAL opening, returning outer clicks inside the panel, and apply
    the answer's coverage to every side.

    The calculator always receives free opening space. Normalize BEFORE
    calculation to avoid double coverage in both gestures and execute.
    """
    largura_em = _largura_do_vao(referencia, a, b)
    base = _base_da_frente(referencia, frente, largura_em)
    pontos = [base @ Vector(p) * 1000.0 for p in (a, b)]
    bordas, espelhados = None, [False, False]
    forcada = COBERTURA_DO_TIPO_CORRER.get(forcar)
    if portas is not None:
        bordas = [base @ Vector(p) * 1000.0 for p in portas]
        if forcada is None or modulo is None:
            # No cabinet means no panel for finding the inner corner:
            # a coincident pair copies the other pair's margin as usual.
            pontos, espelhados = _espelhar_margem(bordas, pontos)
    originais = [p.copy() for p in pontos]
    tolerancia = _modulos.TOL_BORDA * 1000.0
    ancoras = {}
    if modulo is not None:
        L, A, P, E = _caixa_do_modulo(modulo)
        lo, hi = _limites_locais_modulo(modulo) or (
            Vector((-L / 2, -P / 2, 0)), Vector((L / 2, P / 2, A)))
        cantos = [base @ (modulo.matrix_world @ (Vector((x, y, z)) / 1000)) * 1000
                  for x in (lo.x, hi.x) for y in (lo.y, hi.y)
                  for z in (lo.z, hi.z)]
        for eixo in (0, 1):
            lo = min(p[eixo] for p in cantos)
            hi = max(p[eixo] for p in cantos)
            for ponto, espelhado in zip(pontos, espelhados):
                if espelhado:
                    continue        # Already exact from the other pair's margin.
                if abs(ponto[eixo] - lo) <= tolerancia:
                    ponto[eixo] = lo + E
                elif abs(ponto[eixo] - hi) <= tolerancia:
                    ponto[eixo] = hi - E
    meias = _meias_do_vao(a, b, base, tuple(
        None if e else o for o, e in zip(objetos, espelhados)), pontos)
    for i, obj in enumerate(objetos):
        grupo = _grupo_portas(obj)
        if grupo is None or _chapas.MARCA_FOLHA not in obj:
            continue
        cantos = [base @ (obj.matrix_world @ v.co) * 1000.0
                  for v in obj.data.vertices]
        if not cantos:
            continue
        # The leaf face is one thickness away from the opening. Use the original
        # plane to avoid placing the next door one step farther forward.
        pontos[i].z = (base @ grupo.matrix_world.translation).z * 1000.0
        for eixo in (0, 1):
            lo = min(p[eixo] for p in cantos)
            hi = max(p[eixo] for p in cantos)
            outro = originais[1 - i][eixo]
            sinal = (1 if outro > hi + tolerancia else
                     -1 if outro < lo - tolerancia else 0)
            borda = hi if sinal > 0 else lo
            if not sinal or abs(originais[i][eixo] - borda) > tolerancia:
                continue
            ajuste = (_cobertura_porta(parametros)
                      + max(parametros['entre_folhas_mm'], parametros['folga_mm'])
                      - parametros['folga_mm'])
            pontos[i][eixo] = borda + sinal * ajuste
            # Boundary index in door coordinates (X left/right, Y bottom/top).
            ancoras[2 * eixo + (0 if sinal > 0 else 1)] = obj
    mundo = [base.transposed() @ (p / 1000.0) for p in pontos]
    if any((pontos[1][i] - pontos[0][i]) * (originais[1][i] - originais[0][i]) <= 0
           for i in (0, 1)):
        raise ValueError("Edges and gaps leave no room for the opening")
    vao = _mapear_vao_portas(*mundo, referencia, frente, largura_em)
    if bordas is not None:
        coberturas = _coberturas_dos_cantos(bordas, pontos,
                                            parametros['lateral_mm'])
        if forcada is not None:
            coberturas = {k: forcada for k in COBERTURAS_LADOS}
        for indice in ancoras:
            # Touching another door: the support governs.
            coberturas.pop(COBERTURAS_LADOS[indice], None)
    elif _cobertura_porta(parametros) > 0:
        coberturas = {COBERTURAS_LADOS[i]: 0.5 for i in range(4)
                      if meias >> i & 1}
    else:
        coberturas = {}
    return vao, mundo, ancoras, coberturas


# Sliding doors: each leaf has its OWN track. One to four leaves travel
# the entire opening and pass over one another. Without explicit width,
# a single leaf has HALF opening width to leave travel room;
# multiple leaves cover the opening with neighboring overlap
# `SOBREPOSICAO_CORRER_MM`. Explicit width
# (`CHAVE_LARGURA_CORRER`, a separate key like coverage, belonging to this
# door rather than scene defaults) applies to all and never exceeds
# the opening. No overlap field: width and distribution determine it
# as (n x width - opening) / (n - 1), as requested.
CHAVE_LARGURA_CORRER = 'largura_folha_mm'
SOBREPOSICAO_CORRER_MM = 20.0


def _largura_folha_correr(p, util, n):
    escolhida = float(p.get(CHAVE_LARGURA_CORRER, 0.0) or 0.0)
    if escolhida > 0:
        return min(escolhida, util)
    if n == 1:
        return util / 2.0
    return (util + (n - 1) * SOBREPOSICAO_CORRER_MM) / n


def _plano_correr(p, e, indice, n=1):
    """Sliding leaf `indice` center z in mm: one track per leaf, first in
    front. Setback measures the OUTERMOST FACE so even half a thickness
    cannot enter track space. Overlay doors sit in front of the cabinet,
    with the rear leaf against the track wall touching the cabinet."""
    passo = e + float(p['entre_planos_mm'])
    if _correr_sobreposta(p):
        # Framed: centered in one of the user's TWO track channels;
        # first leaf in front, others alternating.
        costas, frente = _canais_moldura(p)
        return TRILHO_MOLDURA_COSTAS_MM + (frente if indice % 2 == 0 else costas)
    return -float(p['recuo_correr_mm']) - e / 2.0 - indice * passo


def _calcular_folhas_portas(largura, altura, parametros):
    """Return (L, A, E, center_mm) per leaf; create no hardware."""
    p = parametros
    abertura, n = p['abertura'], p['folhas']
    if abertura not in LIMITES_FOLHAS or not (2 if abertura == 'ZIGZAG' else 1) <= n <= LIMITES_FOLHAS[abertura]:
        raise ValueError("Invalid leaf count for this opening")
    # .get supports old doors and test dictionaries lacking hardware fields.
    numericos = [largura, altura] + [float(p.get(k, 0.0)) for k in
                                    _PARAMETROS_PORTAS if k.endswith('_mm')]
    if not all(math.isfinite(v) and v >= 0 for v in numericos):
        raise ValueError("Measurements must be finite and nonnegative")
    e, lateral = p['espessura_mm'], p['lateral_mm']
    if not (e > 0 and lateral > 0):
        raise ValueError("Thickness must be greater than zero")
    correr = abertura == 'CORRER'
    if not correr and p['dobradica'] not in {'RETA', 'CURVA', 'SUPER_CURVA'}:
        raise ValueError("Choose a hinge: straight, half crank, or full crank")
    esq, dir_, baixo, cima = _inicios_porta(p)
    util = largura - esq - dir_
    a = altura - baixo - cima
    if correr:
        if p['recuo_correr_mm'] <= 0:
            raise ValueError("Sliding doors require a positive rail recess")
        l = _largura_folha_correr(p, util, n)
        # Spread leaves across the opening, first at the left and last at the
        # right; a single leaf stays left and travels toward the other side.
        if l > util + 1e-6:
            raise ValueError("Opening too narrow for the leaves")
        passo = (util - l) / (n - 1) if n > 1 else 0.0
    else:
        l = (util - (n - 1) * p['entre_folhas_mm']) / n
        passo = l + p['entre_folhas_mm']
    if l < 1.0 or a < 1.0:
        raise ValueError("Gaps exceed the available opening")
    saida = []
    for i in range(n):
        if correr:
            z = _plano_correr(p, e, i, n)
        elif p['dobradica'] == 'SUPER_CURVA':
            z = -p['recuo_embutida_mm'] - e / 2.0
        else:
            z = _ferragens._afastamento_porta(p) + e / 2.0
        posicao = n - 1 - i if abertura == 'ZIGZAG' and p.get('dobradica_lado') == 'DIREITA' else i
        x = esq + l / 2.0 + posicao * passo
        if correr and p.get('correr_espelhadas', {}).get(str(i)):
            x = 2 * esq + util - x
        saida.append((l, a, e,
                      (x,
                       baixo + a / 2.0, z)))
    return saida


# ============================== DOOR-TO-CABINET LINK (scenario 2)
# When the first click hits a PANEL, the opening belongs to its cabinet.
# Absolute mm would break that link on the first resize, so store
# the four clearances to cabinet faces in THICKNESS UNITS.
# The door then follows both cabinet width/height and panel thickness,
# which together define
# the opening.
CHAVE_MODULO_PORTA = "porta_modulo"
CHAVE_FOLGAS_PORTA = "porta_folgas_em_e"
CHAVE_RECUO_PORTA = "porta_recuo_frente_mm"
CHAVE_VAO_ORIENTADO = "porta_vao_orientado"


def gravar_vao_orientado(grupo, conj):
    """Three corners in cabinet axes preserve corner faces. Ordinary X/Y
    clearances cannot represent diagonal or perpendicular doors.
    """
    lo, hi = _limites_locais_modulo(conj)
    inversa = conj.matrix_world.inverted()
    L, A = grupo['porta_vao_largura_mm'], grupo['porta_vao_altura_mm']
    pontos = [inversa @ (grupo.matrix_world @ (Vector(p) / 1000)) * 1000
              for p in ((0, 0, 0), (L, 0, 0), (0, A, 0))]
    grupo[CHAVE_VAO_ORIENTADO] = {str(i): [(v[k] - lo[k]) / (hi[k] - lo[k])
                                         for k in range(3)] for i, v in enumerate(pontos)}
    for chave in list(grupo.keys()):
        if chave.startswith(('porta_vao_face_', 'porta_vao_apoio_', 'porta_vao_vertice_',
                             'porta_vao_offset_', 'porta_vao_assinatura_')):
            del grupo[chave]
    # The inner corner can move (R/angle) without changing the outer box.
    # Support on actual vertices keeps the door off its obsolete plane.
    for i, ponto in enumerate(pontos):
        mundo = conj.matrix_world @ (ponto / 1000)
        candidatos = []
        for obj in _modulos._estruturais(_modulos._chapas_do_conjunto(conj)):
            local = obj.matrix_world.inverted() @ mundo
            hit, perto, _normal, face = obj.closest_point_on_mesh(local)
            if not hit:
                continue
            distancia = (obj.matrix_world @ perto - mundo).length * 1000
            if distancia >= 60:
                continue
            # The top/base also touches opening corners. The side/strip determines
            # partial width, rather than interpolation from an arbitrary point
            # in the middle of a top spanning the box.
            lateral = abs(_chapas._eixos(obj)[2].dot(grupo.matrix_world.to_3x3().col[0])) > .5
            candidatos.append((not lateral, distancia, obj, perto, face, local))
        if not candidatos:
            continue
        _, distancia, obj, perto, face, local = min(candidatos, key=lambda c: c[:2])
        indices = list(obj.data.polygons[face].vertices)
        vertices = [obj.data.vertices[k].co for k in indices]
        pesos = poly_3d_calc(vertices, perto)
        indice = min(indices, key=lambda k: (obj.data.vertices[k].co - perto).length)
        grupo['porta_vao_apoio_%d' % i] = obj
        grupo['porta_vao_vertice_%d' % i] = indice
        grupo['porta_vao_offset_%d' % i] = list(local - obj.data.vertices[indice].co)
        grupo['porta_vao_face_%d' % i] = dict(
            cantos={str(k):_assinatura_vertice_vao(obj, v) for k,v in enumerate(indices)},
            pesos=list(pesos), offset=list(local-perto))
    _gravar_assinaturas_vao(grupo)
    grupo['porta_vao_referencia'] = 2


def preparar_referencias_vaos(conj):
    """Migrate once BEFORE resizing. Partial doors follow actual strips/
    partitions rather than distances to the entire box. No mesh search
    during redraw or opening-slider interaction.
    """
    for grupo in _portas_do_conjunto(conj):
        folgas = grupo.get(CHAVE_FOLGAS_PORTA, ())
        parcial = len(folgas) >= 2 and max(abs(float(f)) for f in folgas[:2]) > 2
        if (abs(grupo.matrix_world.to_3x3().col[1].normalized().z) > .99
                and (grupo.get(CHAVE_VAO_ORIENTADO) or parcial)
                and not any(grupo.get('porta_ancora_%d' % i) for i in range(4))
                and grupo.get('porta_vao_referencia') != 2):
            gravar_vao_orientado(grupo, conj)


def _assinatura_vertice_vao(obj, indice):
    if len(obj.data.vertices) != 8:
        return 'v%d' % indice
    atributo = obj.data.attributes.get(_solda.ATRIBUTO_CANTO)
    if atributo and len(atributo.data) == 8:
        codigo = atributo.data[indice].value
        return ''.join('+' if codigo & (1 << k) else '-' for k in range(3))
    centro = sum((v.co for v in obj.data.vertices), Vector()) / 8
    return ''.join('+' if a > b else '-' for a,b in zip(obj.data.vertices[indice].co,centro))


def _gravar_assinaturas_vao(grupo):
    for i in range(3):
        obj = grupo.get('porta_vao_apoio_%d' % i)
        indice = int(grupo.get('porta_vao_vertice_%d' % i, -1))
        if not isinstance(obj, bpy.types.Object) or obj.type != 'MESH' or not 0 <= indice < len(obj.data.vertices):
            continue
        grupo['porta_vao_assinatura_%d' % i] = _assinatura_vertice_vao(obj, indice)


def _vao_orientado(grupo, conj):
    dados = grupo.get(CHAVE_VAO_ORIENTADO)
    if not dados:
        return None
    lo, hi = _limites_locais_modulo(conj)
    pontos = [Vector(tuple(lo[k] + float(dados[str(i)][k]) * (hi[k] - lo[k])
                           for k in range(3))) for i in range(3)]
    inversa = conj.matrix_world.inverted()
    for i in range(3):
        obj = grupo.get('porta_vao_apoio_%d' % i)
        indice = int(grupo.get('porta_vao_vertice_%d' % i, -1))
        assinatura = grupo.get('porta_vao_assinatura_%d' % i)
        if isinstance(obj, bpy.types.Object) and assinatura:
            indices = _solda._indices_da_assinatura(obj, assinatura)
            indice = indices[0] if indices else -1
        if isinstance(obj, bpy.types.Object) and obj.type == 'MESH' and 0 <= indice < len(obj.data.vertices):
            face = grupo.get('porta_vao_face_%d' % i)
            if face:
                vertices = [_solda._indices_da_assinatura(obj, face['cantos'][str(k)])
                            for k in range(len(face['pesos']))]
                if all(vertices):
                    local = sum((obj.data.vertices[js[0]].co * peso
                                 for js,peso in zip(vertices,face['pesos'])), Vector())
                    pontos[i] = inversa @ (obj.matrix_world @ (local+Vector(face['offset']))) * 1000
                    continue
            pontos[i] = inversa @ (obj.matrix_world @ (obj.data.vertices[indice].co +
                Vector(grupo['porta_vao_offset_%d' % i]))) * 1000
    x, y = pontos[1] - pontos[0], pontos[2] - pontos[0]
    x.z = 0
    y = Vector((0, 0, y.z))
    L, A = x.length, y.length
    if min(L, A) < 1:
        raise ValueError("The oriented opening has no room for the door")
    x.normalize()
    y.normalize()
    matriz = Matrix((x, y, x.cross(y))).transposed().to_4x4()
    matriz.translation = pontos[0] / 1000
    return L, A, conj.matrix_world @ matriz


def preparar_deformacao_vaos(conj, desloc):
    """Transport the CLOSED opening's three points through the body's map.
    Moving only one L-shaped arm leaves the envelope unchanged.
    """
    planos=[]
    inv=conj.matrix_world.inverted()
    for grupo in _portas_do_conjunto(conj):
        folhas=_folhas_portas(grupo)
        if not folhas or any(o.get('porta_curva_modelada') for o in folhas):continue
        apoio=grupo.get('porta_apoio_folha')
        matriz=(_ferragens._matriz_fechada(apoio) @ grupo.matrix_basis
                if isinstance(apoio,bpy.types.Object) else grupo.matrix_world)
        L,A=float(grupo['porta_vao_largura_mm']),float(grupo['porta_vao_altura_mm'])
        pontos=[inv @ (matriz @ (Vector(p)/1000))*1000
                for p in ((0,0,0),(L,0,0),(0,A,0))]
        planos.append((grupo,[conj.matrix_world @ ((p+desloc(p))/1000) for p in pontos]))
    return planos


def aplicar_deformacao_vaos(conj, planos):
    """Store the transported opening without old anchors pulling it back.
    Envelope fractions still support overall width/height changes.
    """
    if not planos:return
    lo,hi=_limites_locais_modulo(conj)
    inv=conj.matrix_world.inverted()
    for grupo,pontos in planos:
        locais=[inv @ p*1000 for p in pontos]
        grupo[CHAVE_VAO_ORIENTADO]={str(i):[(p[k]-lo[k])/max(hi[k]-lo[k],1e-6)
                                          for k in range(3)] for i,p in enumerate(locais)}
        for chave in list(grupo.keys()):
            if chave.startswith(('porta_vao_face_','porta_vao_apoio_','porta_vao_vertice_',
                                 'porta_vao_assinatura_','porta_vao_offset_')):
                del grupo[chave]
        grupo['porta_vao_referencia'] = 0


def vincular_folha_de_apoio(grupo, folha, conj):
    """A hinged corner leaf follows the door supporting its hinge.
    The opening stays linked to the cabinet for resizing.
    """
    if folha in grupo.children_recursive:
        raise ValueError("Cycle between supporting doors")
    gravar_vao_orientado(grupo, conj)
    fechada = grupo.matrix_world.copy()
    grupo['porta_apoio_folha'] = folha
    grupo.parent = folha
    grupo.matrix_parent_inverse = Matrix.Identity(4)
    grupo.matrix_basis = _ferragens._matriz_fechada(folha).inverted() @ fechada
    bpy.context.view_layer.update()


# Keep the tab button lit while capture runs so the user knows
# the tool is waiting for two
# viewport clicks.
_apanhando_vao = [False]


def _marcar_apanhando(ligado):
    if _apanhando_vao[0] == ligado:
        return
    _apanhando_vao[0] = ligado
    for janela in bpy.context.window_manager.windows:
        for area in janela.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()


def _motivo_portas(s):
    """Return why door creation is blocked, or '' if allowed.

    The operator rejects invalid parameters, but its report does not
    reach someone watching the sidebar, making clicks seem ineffective.
    The button itself now explains what is missing.
    """
    try:
        _calcular_folhas_portas(1000.0, 1000.0,
                                _parametros_portas_da_cena(s, numerico=True))
    except (ValueError, KeyError, TypeError) as erro:
        return str(erro)
    return ''


def _modulo_da_chapa(obj):
    """Find the assembly containing this panel by walking its parents."""
    if obj is None or _chapas.MARCA_CHAPA not in obj:
        return None
    pai = obj.parent
    while pai is not None:
        if _chapas.MARCA_CONJUNTO in pai:
            return pai
        pai = pai.parent
    return None


def _caixa_do_modulo(conj):
    """Cabinet (L, A, P, E) in mm, or None if a dimension is missing."""
    try:
        limites = _limites_locais_modulo(conj)
        if limites is not None:
            lo, hi = limites
            return (hi.x - lo.x, hi.z - lo.z, hi.y - lo.y,
                    float(conj.conj_espessura_mm))
        return (float(conj.conj_largura_mm), float(conj.conj_altura_mm),
                float(conj.conj_profundidade_mm),
                float(conj.conj_espessura_mm))
    except (AttributeError, TypeError, ValueError):
        return None


def _limites_locais_modulo(conj):
    """Panel box without doors; old fields may be stale."""
    inversa = conj.matrix_world.inverted()
    pontos = [inversa @ (o.matrix_world @ v.co) * 1000
              for o in _modulos._chapas_do_conjunto(conj)
              if _prateleiras.MARCA_PRATELEIRA not in o and 'fundo_tipo' not in o for v in o.data.vertices]
    if not pontos:
        return None
    return (Vector(tuple(min(p[i] for p in pontos) for i in range(3))),
            Vector(tuple(max(p[i] for p in pontos) for i in range(3))))


def _local_no_modulo(conj, ponto):
    """World point expressed on cabinet axes, in mm."""
    return conj.matrix_world.inverted() @ Vector(ponto) * 1000.0


def _folgas_do_vao(conj, ponto_a, ponto_b, frente, largura_em='X'):
    """Clearances (left, right, bottom, top) in THICKNESS UNITS plus setback mm.

    The assembly Empty is at XY center and Z base (`reposicionar_origem`),
    so its local box spans -L/2..L/2 on X, -P/2..P/2 on Y and 0..A on Z.
    Bottom/top refer to door HEIGHT: depth for a horizontal lid.
    """
    caixa = _caixa_do_modulo(conj)
    if caixa is None:
        return None
    L, A, P, E = caixa
    if E <= 0.0:
        return None
    lo, hi = _limites_locais_modulo(conj) or (
        Vector((-L / 2, -P / 2, 0)), Vector((L / 2, P / 2, A)))
    a = _local_no_modulo(conj, ponto_a)
    b = _local_no_modulo(conj, ponto_b)
    il, ia, inormal = _eixos_da_frente(frente, largura_em)
    esq, dir_ = min(a[il], b[il]) - lo[il], hi[il] - max(a[il], b[il])
    baixo, cima = min(a[ia], b[ia]) - lo[ia], hi[ia] - max(a[ia], b[ia])
    recuo = (min(a[inormal], b[inormal]) - lo[inormal]
             if frente.startswith('NEG')
             else hi[inormal] - max(a[inormal], b[inormal]))
    return ((esq / E, dir_ / E, baixo / E, cima / E), recuo)


def _vao_do_modulo(conj, folgas, recuo, frente, largura_em='X'):
    """Rebuild opening (width, height, matrix) from the current cabinet."""
    caixa = _caixa_do_modulo(conj)
    if caixa is None:
        return None
    L, A, P, E = caixa
    lo, hi = _limites_locais_modulo(conj) or (
        Vector((-L / 2, -P / 2, 0)), Vector((L / 2, P / 2, A)))
    esq, dir_, baixo, cima = (f * E for f in folgas)
    il, ia, inormal = _eixos_da_frente(frente, largura_em)
    canto_a, canto_b = Vector(), Vector()
    canto_a[il], canto_b[il] = lo[il] + esq, hi[il] - dir_
    canto_a[ia], canto_b[ia] = lo[ia] + baixo, hi[ia] - cima
    canto_a[inormal] = canto_b[inormal] = (
        lo[inormal] + recuo if frente.startswith('NEG')
        else hi[inormal] - recuo)
    mundo = conj.matrix_world
    referencia = mundo.to_3x3().normalized()
    return _mapear_vao_portas(mundo @ (canto_a / 1000.0),
                              mundo @ (canto_b / 1000.0),
                              referencia, frente, largura_em)


def _portas_do_conjunto(conj):
    """Door groups linked to this cabinet."""
    grupos=[]
    for o in bpy.data.objects:
        if _chapas.MARCA_PORTAS not in o:continue
        pai=o.parent
        while pai is not None and _chapas.MARCA_CONJUNTO not in pai:pai=pai.parent
        # Strings do not acquire .001 on append; hierarchy is authoritative,
        # including chains supported on another leaf.
        if pai==conj or (pai is None and o.get(CHAVE_MODULO_PORTA)==conj.name):grupos.append(o)
    return grupos


def porta_no_modulo(conj, folhas=1, abertura='GIRO', **extras):
    """Full-front STRAIGHT/full-overlay door via the same four wizard clicks
    (outer corners = door, inner corners = opening), used by native library
    cabinets. Pass `extras` directly to `cabinet_portas`, e.g.
    dobradica_lado or pistoes_qtd. Return the door group."""
    L, A, P, E = _caixa_do_modulo(conj)
    y = -P / 2.0
    cantos = [(-L / 2, y, A), (-L / 2 + E, y, A - E), (L / 2 - E, y, E), (L / 2, y, 0)]
    mundo = [conj.matrix_world @ (Vector(c) / 1000.0) for c in cantos]
    laterais = [c for c in _modulos._chapas_do_conjunto(conj)
                if abs(_chapas._eixos(c)[2].x) > 0.9]
    esquerda = min(laterais, key=lambda c: (conj.matrix_world.inverted()
                                            @ c.matrix_world.translation).x)
    opcoes = dict(dobradica='RETA', folhas=folhas, abertura=abertura)
    if abertura == 'BASCULANTE':
        opcoes['dobradica_lado'] = 'CIMA'
    opcoes.update(extras)
    resultado = bpy.ops.object.cabinet_portas(
        'EXEC_DEFAULT', capturado=True, ponto_a=mundo[1], ponto_b=mundo[2],
        quatro_pontos=True, porta_a=mundo[0], porta_b=mundo[3],
        referencia=tuple(v for linha in conj.matrix_world.to_3x3().normalized()
                         for v in linha),
        pai_nome=conj.name, modulo_nome=conj.name, objeto_a_nome=esquerda.name,
        frente='NEG_Y', folga_mm=0, **opcoes)
    if 'FINISHED' not in resultado:
        raise RuntimeError("door for cabinet %s could not be created" % conj.name)
    return _portas_do_conjunto(conj)[-1]


def _vao_com_ancoras(grupo, vao, parametros):
    """Update boundaries supported by existing leaves without accumulating gaps."""
    largura, altura, matriz = vao
    inversa = matriz.inverted()
    limites = [0.0, largura, 0.0, altura]
    ajuste = (_cobertura_porta(parametros)
              + max(parametros['entre_folhas_mm'], parametros['folga_mm'])
              - parametros['folga_mm'])
    for indice in range(4):
        folha = grupo.get('porta_ancora_%d' % indice)
        if not isinstance(folha, bpy.types.Object) or folha.type != 'MESH':
            continue
        # Closed pose: opening the support door must not change this opening.
        fechada = _ferragens._matriz_fechada(folha)
        valores = [(inversa @ (fechada @ v.co))[indice // 2] * 1000
                   for v in folha.data.vertices]
        if valores:
            limites[indice] = (max(valores) + ajuste if indice % 2 == 0
                                else min(valores) - ajuste)
    matriz = matriz @ Matrix.Translation(Vector((limites[0], limites[2], 0)) / 1000)
    largura, altura = limites[1] - limites[0], limites[3] - limites[2]
    if largura < 1 or altura < 1:
        raise ValueError("The supporting door leaves no room for the opening")
    return largura, altura, matriz


def _porta_reta_sem_mudanca(grupo, p, largura, altura, matriz):
    """Compare assembled data without rebuilding Mesh or persistent caches.

    Only straight swing hinges are independent of oblique-support ray casts.
    Other types retain the complete update.
    """
    if (p.get('abertura') != 'GIRO' or p.get('folha', 'CHAPA') != 'CHAPA'
            or not _ferragens._usa_rig(p) or not grupo.get('porta_ferragens_encaixe')
            or _ferragens._ferragens_antigas(grupo)):
        return False
    if (abs(float(grupo.get('porta_vao_largura_mm', 0)) - largura) > .001
            or abs(float(grupo.get('porta_vao_altura_mm', 0)) - altura) > .001
            or max(abs(a - b) for x, y in zip(grupo.matrix_world, matriz)
                   for a, b in zip(x, y)) > 1e-6):
        return False
    folhas = _folhas_portas(grupo)
    calculadas = _calcular_folhas_portas(largura, altura, p)
    if len(folhas) != len(calculadas):
        return False
    for folha, (l, a, e, centro) in zip(folhas, calculadas):
        atual = _ferragens._dados_da_folha(folha)
        if any(abs(x - y) > .001 for x, y in zip(
                (*atual[:3], *atual[3]), (l, a, e, *centro))):
            return False
    itens = _ferragens._ferragens_da_porta(p, largura, altura, calculadas)
    rigs = {o.get(_ferragens.CHAVE_ID_FERRAGEM): o for o in _ferragens._ferragens_portas(grupo)
            if o.get('cabinet_peca') == 'raiz'}
    if len(rigs) != len(itens):
        return False
    for item in itens:
        obj = rigs.get(item['id'])
        if obj is None or item['forma'] != 'RIG':
            return False
        esperada = item['matriz'].copy()
        esperada.translation = (esperada.translation + Vector(
            obj.get('porta_ferragem_deslocamento_mm', (0, 0, 0)))) / 1000
        if max(abs(a - b) for x, y in zip(obj.matrix_basis, esperada)
               for a, b in zip(x, y)) > 1e-6:
            return False
    return True


def atualizar_do_conjunto(conj):
    """Rebuild leaves after cabinet dimensions change.

    Call AFTER `redimensionar_grupo` / `aplicar_espessura_grupo`, never
    during them: leaves read dimensions already applied.
    """
    if conj is None or _chapas.MARCA_CONJUNTO not in conj:
        return
    pendentes = _portas_do_conjunto(conj)
    ordenados = []
    # Supports first: alphabetical names do not represent dependencies.
    while pendentes:
        livres = [g for g in pendentes if not any(
            _grupo_portas(f) in pendentes for f in
            [g.get('porta_ancora_%d' % i) for i in range(4)] + [g.get('porta_apoio_folha')])]
        if not livres:
            print("[Archy Builder] cycle between supporting doors")
            break
        ordenados.extend(livres)
        pendentes = [g for g in pendentes if g not in livres]
    for grupo in ordenados:
        folgas = grupo.get(CHAVE_FOLGAS_PORTA)
        parametros = grupo.get('porta_parametros')
        if not folgas or not parametros:
            continue
        frente = grupo.get('porta_frente', 'NEG_Y')
        largura_em = grupo.get('porta_largura_em', 'X')
        # Side thickness IS cabinet-panel thickness: retaining its creation value
        # made full-overlay doors protrude when the cabinet became thinner.
        parametros = _copiar_parametros(parametros)
        parametros['lateral_mm'] = _espessura_do_vao(
            conj, padrao=parametros.get('lateral_mm', ESPESSURA_PADRAO_PORTA))
        try:
            vao = _vao_orientado(grupo, conj) or _vao_do_modulo(conj, list(folgas),
                                 float(grupo.get(CHAVE_RECUO_PORTA, 0.0)),
                                 frente, largura_em)
            if vao is None:
                continue
            largura, altura, matriz = _vao_com_ancoras(grupo, vao, parametros)
            apoio = grupo.get('porta_apoio_folha')
            if isinstance(apoio, bpy.types.Object):
                matriz = (apoio.matrix_world @ _ferragens._matriz_fechada(apoio).inverted()
                          @ matriz)
            if _porta_reta_sem_mudanca(grupo, parametros, largura, altura, matriz):
                continue
            _aplicar_portas(bpy.context, grupo, matriz, conj,
                            largura, altura, dict(parametros))
        except (ValueError, KeyError, TypeError) as e:
            print("[Archy Builder] linked door:", e)


def atualizar_portas_do_conjunto(conj, sistemas=True):
    """Legacy API compatibility; the cabinet owns coordination."""
    return _modulos.atualizar_sistemas_do_conjunto(conj, internos=sistemas)


def preferir_esquerda_no_modulo(context, conj):
    """Reverse COPLANAR chain order too, without changing closed leaves.
    Corner chains retain their geometric supports.
    """
    grupos=_portas_do_conjunto(conj)
    alteradas=[]
    for raiz in grupos:
        p=raiz.get('porta_parametros') or {}
        if raiz.get('porta_apoio_folha') or p.get('dobradica_articulada'):continue
        cadeia=[raiz]
        for _passo in range(len(grupos)):
            novas=[g for g in grupos if g not in cadeia and _grupo_portas(g.get('porta_apoio_folha')) in cadeia]
            if not novas:break
            cadeia+=novas
        if len(cadeia)<2 or p.get('dobradica_lado')!='DIREITA':continue
        if any(len(_folhas_portas(g))!=1 for g in cadeia):continue
        normal=raiz.matrix_world.to_3x3().col[2].normalized()
        if any(g.matrix_world.to_3x3().col[2].normalized().dot(normal)<.999 for g in cadeia):continue
        eixo=raiz.matrix_world.to_3x3().col[0].normalized()
        cadeia.sort(key=lambda g:_ferragens._matriz_fechada(_folhas_portas(g)[0]).translation.dot(eixo))
        guardados=[(g,g.parent,g.matrix_basis.copy(),g.matrix_parent_inverse.copy(),{k:_copiar_parametros(v) for k,v in g.items()}) for g in cadeia]
        mundos=[g.matrix_world.copy() for g in cadeia]
        for g,mundo in zip(cadeia,mundos):
            g.parent=conj;g.matrix_parent_inverse=Matrix.Identity(4);g.matrix_world=mundo
            if 'porta_apoio_folha' in g:del g['porta_apoio_folha']
            for k in range(4):
                chave='porta_ancora_%d'%k
                if _grupo_portas(g.get(chave)) in cadeia and chave in g:del g[chave]
        primeiro=cadeia[0]
        q=_copiar_parametros(primeiro['porta_parametros'])
        for chave in ('dobradica_articulada','dobradica_apoio_plano_mm','dobradica_articulada_sinal','dobradica_junta_mm'):
            q.pop(chave,None)
        q['dobradica_lado']='DIREITA';primeiro['porta_parametros']=q
        bpy.context.view_layer.update()
        if not preferir_abertura_esquerda(context,primeiro):
            for g,pai,matriz,inversa,props in guardados:
                for chave in list(g.keys()):del g[chave]
                for chave,valor in props.items():g[chave]=valor
                g.parent=pai;g.matrix_parent_inverse=inversa;g.matrix_basis=matriz
            bpy.context.view_layer.update()
            continue
        anterior=primeiro
        for g in cadeia[1:]:
            q=_copiar_parametros(g['porta_parametros'])
            q.update(dobradica_lado='ESQUERDA',dobradica='CURVA',dobradica_articulada=True,
                     dobradica_articulada_sinal=1)
            apoio=_folhas_portas(anterior)[0]
            pts=[g.matrix_world.inverted() @ (_ferragens._matriz_fechada(apoio) @ Vector(v))*1000 for v in apoio.bound_box]
            l,a,e,c=_ferragens._dados_da_folha(_folhas_portas(g)[0])
            q['dobradica_apoio_plano_mm']=max(v.z for v in pts)
            q['dobradica_junta_mm']=min(30,abs(c[0]-l/2-max(v.x for v in pts)))
            _reaplicar_portas(context,g,q)
            _puxadores_no_lado_livre(g)
            vincular_folha_de_apoio(g,apoio,conj)
            anterior=g
        for g in cadeia:gravar_vao_orientado(g,conj)
        alteradas += [g.name for g in cadeia]
    for g in grupos:
        if preferir_abertura_esquerda(context,g):alteradas.append(g.name)
    return alteradas


def preferir_abertura_esquerda(context, grupo):
    """Library/import default: double leaves retain both external sides;
    articulated leaves retain the joint to the support leaf. Reverse only
    when ALL hinges have actual body support.
    """
    p = _copiar_parametros(grupo.get('porta_parametros') or {})
    if (p.get('abertura') not in ('GIRO','ZIGZAG') or p.get('dobradica_lado')!='DIREITA'
            or (p.get('abertura')=='GIRO' and int(p.get('folhas',1))!=1)
            or p.get('dobradica_articulada') or grupo.get('porta_apoio_folha')):
        return False
    folhas = _folhas_portas(grupo)
    conj = _modulo_da_chapa(folhas[0]) if folhas else None
    if conj is None:return False
    p['dobradica_lado']='ESQUERDA'
    L,A = grupo['porta_vao_largura_mm'],grupo['porta_vao_altura_mm']
    calculadas = _calcular_folhas_portas(L,A,p)
    inversa=grupo.matrix_world.inverted()
    apoio_obliquo=False
    for aresta, distancias, i in _ferragens._dobradicas_da_porta(p,L,A,calculadas):
        if i>0 and p.get('abertura')=='ZIGZAG':continue
        costas=calculadas[i][3][2]-calculadas[i][2]/2
        for _placa, caneco in _caixas_dobradicas(aresta,distancias,costas):
            centro=sum(caneco,Vector())/8
            achou=False
            direcao=(grupo.matrix_world.to_3x3() @ Vector((-1,0,0))).normalized()
            for obj in _modulos._estruturais(_modulos._chapas_do_conjunto(conj)):
                inv=obj.matrix_world.inverted();dl=inv.to_3x3()@direcao
                for fundo in (25,35,45,55):
                    origem=grupo.matrix_world @ (Vector((centro.x,centro.y,costas-fundo))/1000)
                    hit,ponto,normal,_face=obj.ray_cast(inv@origem,dl.normalized(),distance=.12*dl.length)
                    if not hit:continue
                    n=(inversa.to_3x3() @ inv.to_3x3().transposed() @ normal).normalized()
                    if abs(n.y)>.02 or n.x<.15:continue
                    if n.x>=.995:
                        q=obj.matrix_world @ ponto
                        cabe=True
                        for altura in (-.021,.021):
                            for fundo_placa in (-.014,.014):
                                v=q+grupo.matrix_world.to_3x3() @ Vector((0,altura,fundo_placa))
                                ok,perto,no,_f=obj.closest_point_on_mesh(inv@v)
                                if not ok or (obj.matrix_world @ perto-v).length>.00005 or abs(no.dot(normal))<.999:
                                    cabe=False
                        if not cabe:continue
                    achou=True
                    apoio_obliquo |= n.x<.995
                    break
                if achou:break
            if not achou:return False
    if apoio_obliquo:
        p['dobradica']='CURVA'
        apoios=_ferragens._apoios_obliquos(conj,grupo.matrix_world,p,L,A,calculadas)
        esperados=sum(len(ds) for _a,ds,i in _ferragens._dobradicas_da_porta(p,L,A,calculadas) if i==0)
        if len(apoios)<esperados:return False
    _reaplicar_portas(context,grupo,p)
    _puxadores_no_lado_livre(grupo)
    _ferragens._refazer_ferragens(grupo)
    return True


def _puxadores_no_lado_livre(grupo):
    for folha in _folhas_portas(grupo):
        for pux in [o for o in folha.children if _chapas.MARCA_PUXADOR in o]:
            if not _puxadores._eh_puxador_parametrico(pux):
                pux.location.x=-pux.location.x
            elif pux.get('puxador_borda')=='X-':
                pux['puxador_borda']='X+'
                _puxadores.posicionar_puxador(pux)
            elif str(pux.get('puxador_borda','')).startswith('Y'):
                pux['puxador_fracao']=1-float(pux.get('puxador_fracao',.5))
                _puxadores.posicionar_puxador(pux)
        _chapas.gerar_malha_chapa(folha)


def alvos_para_espelhar(context):
    alvos = {}
    for obj in context.selected_objects:
        grupo = _grupo_portas(obj)
        if grupo is None or not grupo.get('porta_parametros'):
            continue
        if any(_chapas.MARCA_CONJUNTO in o and o.select_get()
               for o in _ancestrais_porta(grupo)):
            continue
        if obj == grupo:
            alvos[grupo] = None
        elif grupo not in alvos or alvos[grupo] is not None:
            alvos.setdefault(grupo, set()).add(int(obj.get('porta_indice', 0)))
    return alvos


def _ancestrais_porta(grupo):
    pai = grupo.parent
    while pai is not None:
        yield pai
        pai = pai.parent


def espelhar_porta(context, grupo, indices=None):
    """Reverse swing direction without mirroring wood or moving the opening."""
    p = _copiar_parametros(grupo.get('porta_parametros') or {})
    if p.get('abertura') not in LIMITES_FOLHAS:
        return "Door has no opening motion to mirror"
    folhas = _folhas_portas(grupo)
    escolhidas = set(range(len(folhas))) if indices is None else set(indices)
    if not escolhidas or not escolhidas <= set(range(len(folhas))):
        return "Door leaf not found"
    inverter = {'ESQUERDA': 'DIREITA', 'DIREITA': 'ESQUERDA'}
    if p['abertura'] == 'BASCULANTE':
        p['basculante_invertida'] = not p.get('basculante_invertida', False)
    elif p['abertura'] == 'CORRER':
        espelhadas = dict(p.get('correr_espelhadas') or {})
        for i in escolhidas:
            espelhadas[str(i)] = not espelhadas.get(str(i), False)
        p['correr_espelhadas'] = espelhadas
    elif p['abertura'] == 'ZIGZAG':
        # A single joint does not reverse the chain. Reversing index order
        # keeps each CLOSED leaf in the same place.
        p['dobradica_lado'] = inverter[p.get('dobradica_lado', 'ESQUERDA')]
        for folha in folhas:
            folha['porta_indice'] = len(folhas) - 1 - int(folha['porta_indice'])
        if p.get('dobradicas_referencia'):
            p['dobradicas_referencia'] = {str(len(folhas)-1-int(k)): v
                                          for k, v in p['dobradicas_referencia'].items()}
    elif len(folhas) == 1:
        p['dobradica_lado'] = inverter[_ferragens._lado_da_folha(p, 0, 1)]
        p.pop('dobradicas_lados_folhas', None)
    else:
        lados = dict(p.get('dobradicas_lados_folhas') or {})
        for i in escolhidas:
            lados[str(i)] = inverter[_ferragens._lado_da_folha(p, i, len(folhas))]
        p['dobradicas_lados_folhas'] = lados
    erro = _refazer_porta(context, grupo, p)
    if erro:
        return erro
    if p['abertura'] != 'ZIGZAG':
        vertical = p['abertura'] == 'BASCULANTE'
        eixo = 'Y' if vertical else 'X'
        for i in escolhidas:
            folha = folhas[i]
            for pux in [o for o in folha.children if _chapas.MARCA_PUXADOR in o]:
                if not _puxadores._eh_puxador_parametrico(pux):
                    pux.location[1 if vertical else 0] *= -1
                elif pux.get('puxador_borda') in {eixo+'-', eixo+'+'}:
                    pux['puxador_borda'] = eixo+'+' if pux['puxador_borda'] == eixo+'-' else eixo+'-'
                    _puxadores.posicionar_puxador(pux)
                else:
                    pux['puxador_fracao'] = 1 - float(pux.get('puxador_fracao', .5))
                    _puxadores.posicionar_puxador(pux)
            _chapas.gerar_malha_chapa(folha)
    context.view_layer.update()
    return ''


class OBJECT_OT_espelhar_porta(Operator):
    """Reverse the selected door's or leaf's opening direction."""
    bl_idname = 'object.cabinet_espelhar_porta'
    bl_label = "Mirror Door"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        alvos = alvos_para_espelhar(context) if context.mode == 'OBJECT' else {}
        return bool(alvos) and all(g['porta_parametros'].get('abertura') in LIMITES_FOLHAS
                                   for g in alvos)

    def execute(self, context):
        for grupo, indices in alvos_para_espelhar(context).items():
            erro = espelhar_porta(context, grupo, indices)
            if erro:
                self.report({'WARNING'}, erro)
                return {'CANCELLED'}
        return {'FINISHED'}


def menu_contexto_porta(self, context):
    if alvos_para_espelhar(context):
        self.layout.separator()
        self.layout.operator('object.cabinet_espelhar_porta', icon='MOD_MIRROR')


def _reaplicar_portas(context, grupo, parametros):
    """Rebuild leaves in the group's existing opening, respecting supports."""
    largura, altura, matriz = _vao_com_ancoras(
        grupo, (grupo['porta_vao_largura_mm'], grupo['porta_vao_altura_mm'],
                grupo.matrix_world.copy()), parametros)
    return _aplicar_portas(context, grupo, matriz, grupo.parent,
                           largura, altura, parametros)


def adotar_contorno_modelado(context, grupo, pontos):
    """Reanchor a curved leaf at the hinge tangent after editing R.
    Keep every deformed vertex and the opening, without flattening sag.
    """
    if len(_folhas_portas(grupo))==1:
        if _reancorar_perfil_modelado(context,grupo,pontos):
            return
    folha,=_folhas_portas(grupo)
    p=_copiar_parametros(grupo['porta_parametros'])
    inv=grupo.matrix_world.inverted()
    vs=[inv @ v*1000 for v in pontos]
    lo=Vector(tuple(min(v[k] for v in vs) for k in range(3)))
    hi=Vector(tuple(max(v[k] for v in vs) for k in range(3)))
    esq,dir_,baixo,cima=_inicios_porta(p)
    borda=lo.x if p['dobradica_lado']=='ESQUERDA' else hi.x
    costas=min(v.z for v in vs if abs(v.x-borda)<.05)
    matriz=grupo.matrix_world @ Matrix.Translation(Vector((lo.x-esq,lo.y-baixo,
                                   costas-_ferragens._afastamento_porta(p)))/1000)
    largura,altura=hi.x-lo.x+esq+dir_,hi.y-lo.y+baixo+cima
    _aplicar_portas(context,grupo,matriz,grupo.parent,largura,altura,p)
    bpy.context.view_layer.update()
    fechado=_ferragens._matriz_fechada(folha).inverted()
    for v,ponto in zip(folha.data.vertices,pontos):v.co=fechado @ ponto
    folha.data.update()
    _frentes.preparar(folha,forcar=True)
    conj=_modulo_da_chapa(folha)
    if conj is not None:
        a=matriz.translation;b=matriz @ Vector((largura/1000,altura/1000,0))
        vinculo=_folgas_do_vao(conj,a,b,grupo['porta_frente'],grupo.get('porta_largura_em','X'))
        if vinculo is not None:
            grupo[CHAVE_FOLGAS_PORTA],grupo[CHAVE_RECUO_PORTA]=vinculo
    for pux in folha.children:
        if _chapas.MARCA_PUXADOR in pux:_puxadores.posicionar_puxador(pux)
    _ferragens._refazer_ferragens(grupo)


def _reancorar_perfil_modelado(context,grupo,pontos):
    folha,=_folhas_portas(grupo)
    linha=_frentes.transportar(folha,pontos,_ferragens._matriz_fechada(folha))
    if linha is None or len(linha)<2:
        return False
    p=_copiar_parametros(grupo['porta_parametros'])
    ponta=int(grupo.get('porta_perfil_ponta',-1 if p['dobradica_lado']=='DIREITA' else 0))
    if p['dobradica_lado']!=grupo.get('porta_perfil_lado',p['dobradica_lado']):
        ponta=-1 if ponta==0 else 0
    t=linha[1]-linha[0] if ponta==0 else linha[-1]-linha[-2]
    cima=_ferragens._matriz_fechada(folha).to_3x3().col[1].normalized()
    t-=cima*t.dot(cima)
    fora=t.cross(cima).normalized()
    direita=cima.cross(fora)
    ref=Matrix((direita,cima,fora)).transposed()
    vs=[ref.transposed()@v for v in pontos]
    lo=Vector(tuple(min(v[k] for v in vs) for k in range(3)))
    hi=Vector(tuple(max(v[k] for v in vs) for k in range(3)))
    tras=(ref.transposed()@linha[ponta]).z-p['espessura_mm']/1000
    matriz=ref.to_4x4();matriz.translation=ref@Vector((lo.x,lo.y,tras))
    L,A=(hi.x-lo.x)*1000,(hi.y-lo.y)*1000
    p['dobradica_lado']='ESQUERDA' if (matriz.inverted()@linha[ponta]).x<L/2000 else 'DIREITA'
    _aplicar_portas(context,grupo,matriz,grupo.parent,L,A,p)
    context.view_layer.update()
    inv=_ferragens._matriz_fechada(folha).inverted()
    # Preserve ALL vertices and faces, including manual cutouts.
    for v,ponto in zip(folha.data.vertices,pontos):v.co=inv@ponto
    folha.data.update()
    folha['porta_linha_frente']=[list(inv@v) for v in linha]
    _frentes.preparar(folha,forcar=True)
    grupo['porta_perfil_ponta']=ponta
    grupo['porta_perfil_lado']=p['dobradica_lado']
    conj=_modulo_da_chapa(folha)
    if conj is not None:gravar_vao_orientado(grupo,conj)
    for pux in folha.children:
        if _chapas.MARCA_PUXADOR in pux:_puxadores.posicionar_puxador(pux)
    _ferragens._refazer_ferragens(grupo)
    context.view_layer.update()
    if folha.get('porta_curva_modelada') and grupo.get('porta_perfil_corpo'):
        grupo['porta_limite_pendente']=True
        grupo['porta_limite_validado']=False
    return True


def _refazer_porta(context, grupo, parametros):
    """Write new parameters to an INSTALLED door and rebuild its leaves.

    Return '' or a rejection reason. Validate BEFORE writing: rejection
    must not leave a half-updated door. For linked doors, rebuild through
    the cabinet, which also updates doors supported on this one.
    """
    try:
        _calcular_folhas_portas(float(grupo['porta_vao_largura_mm']),
                                float(grupo['porta_vao_altura_mm']),
                                parametros)
    except (ValueError, KeyError, TypeError) as erro:
        return str(erro)
    modulo = bpy.data.objects.get(grupo.get(CHAVE_MODULO_PORTA, ''))
    if (modulo is not None and _chapas.MARCA_CONJUNTO in modulo
            and grupo.get(CHAVE_FOLGAS_PORTA)):
        grupo['porta_parametros'] = dict(parametros)
        _modulos.atualizar_sistemas_do_conjunto(modulo)
        return ''
    try:
        _reaplicar_portas(context, grupo, parametros)
    except (ValueError, KeyError, TypeError) as erro:
        return str(erro)
    return ''


def _editar_parametro_porta(context, grupo, nome, valor):
    """Change ONE installed-door parameter at door level in the Doors tab."""
    guardados = grupo.get('porta_parametros') if grupo is not None else None
    if not guardados or nome not in _PARAMETROS_PORTAS + (CHAVE_LARGURA_CORRER,):
        return "Door has no editable parameters"
    parametros = _copiar_parametros(guardados)
    if nome in {'espessura_mm', 'moldura_mm'}:
        valor = _chapas._espessura_livre(valor)
    elif nome == CHAVE_LARGURA_CORRER:
        valor = max(1.0, float(valor))
    parametros[nome] = valor
    if nome in {'folhas', 'abertura', 'dobradica_lado'}:
        parametros.pop('dobradicas_lados_folhas', None)
    if nome in {'folhas', 'abertura'}:
        parametros.pop('correr_espelhadas', None)
        parametros.pop('basculante_invertida', None)
    if nome in {'dobradicas_qtd', 'dobradicas_margem_mm', 'dobradica_lado', 'folhas', 'abertura'}:
        # A manual choice replaces the measured DXF arrangement.
        parametros.pop('dobradicas_referencia', None)
    if nome in {'abertura', 'folhas'}:
        # Different type: restore that type's default width.
        parametros.pop(CHAVE_LARGURA_CORRER, None)
    if nome == 'abertura':
        if valor != 'GIRO':
            for chave in ('dobradica_articulada', 'dobradica_apoio_plano_mm',
                          'dobradica_articulada_sinal', 'dobradica_junta_mm'):
                parametros.pop(chave, None)
        parametros['folhas'] = min(int(parametros.get('folhas', 1)),
                                   LIMITES_FOLHAS[valor])
        if valor == 'ZIGZAG':
            parametros['folhas'] = max(2, parametros['folhas'])
    if nome == 'trilho':
        # Different track, different leaf: 18 mm cannot fit light-track channels.
        parametros['espessura_mm'] = _espessura_porta_do_trilho(parametros)
    if nome == 'folha' or (nome == 'trilho' and _folha_quadro(parametros)):
        # Frames use profile depth; panels return to track-specific thickness.
        parametros['espessura_mm'] = (
            ESPESSURA_QUADRO_MM if _folha_quadro(parametros)
            else _espessura_porta_do_trilho(parametros) if _correr_sobreposta(parametros)
            else ESPESSURA_PADRAO_PORTA)
    return _refazer_porta(context, grupo, parametros)


def _espessura_da_folha_mudou(folha, espessura):
    """ONE leaf's E applies to the entire door.

    A door cannot have leaves with different thicknesses. Without propagation,
    other leaves kept their old thickness and the next resize restored
    the saved value.
    """
    grupo = _grupo_portas(folha)
    if grupo is None or not grupo.get('porta_parametros'):
        return False
    erro = _editar_parametro_porta(bpy.context, grupo, 'espessura_mm', espessura)
    if erro:
        print("[Archy Builder] door thickness:", erro)
        return False
    return True


def _nome_da_porta(p):
    """Door-group name from its model, as requested."""
    abertura = p.get('abertura', 'GIRO')
    if abertura == 'ZIGZAG':
        return "Folding Door"
    if abertura == 'CORRER':
        return "Sliding Door"
    if abertura == 'BASCULANTE':
        return "Lift-Up Door"
    folhas = "Double" if int(p.get('folhas', 1)) > 1 else "Single"
    if p.get('dobradica') == 'SUPER_CURVA':
        return folhas + " Inset Door"
    return folhas + " Door"


def _sem_sufixo(nome):
    """"Double Door.001" -> "Double Door" (Blender's .NNN suffix)."""
    base, ponto, fim = nome.rpartition('.')
    return base if ponto and len(fim) == 3 and fim.isdigit() else nome


def _renomear_porta(grupo, p):
    """Follow the model name unless the user has renamed the group."""
    novo = _nome_da_porta(p)
    anterior = grupo.get('porta_nome_auto')
    if anterior is None or _sem_sufixo(grupo.name) == anterior:
        if _sem_sufixo(grupo.name) != novo:
            grupo.name = novo
        grupo['porta_nome_auto'] = novo


def _aplicar_portas(context, grupo, matriz, pai, largura, altura,
                    parametros, frente='', largura_em=''):
    """Validate before scene mutation; reuse leaves and their materials."""
    # dict(IDPropertyGroup) is a SHALLOW copy. Replacing the property frees
    # old arrays/groups; subsequently reading the old hinge reference
    # crashed Blender 5.2 during resize.
    parametros = _copiar_parametros(parametros)
    calculadas = _calcular_folhas_portas(largura, altura, parametros)
    antigas = _folhas_portas(grupo) if grupo is not None else []
    abertura_anterior = grupo.get('porta_parametros', {}).get('abertura') if grupo is not None else None
    fracao_zigzag = antigas[0].get(_ferragens.CHAVE_ABERTURA, 0) if antigas else 0
    if any(o.type != 'MESH' or o.mode != 'OBJECT' for o in antigas):
        raise ValueError("Leave door Edit Mode before reconfiguring")
    ocupado_antes = _chapas._ocupado[0]
    _chapas._ocupado[0] = True
    try:
        if grupo is None:
            grupo = bpy.data.objects.new(_nome_da_porta(parametros), None)
            grupo['porta_nome_auto'] = grupo.name
            # Inside the cabinet's Collection, alongside its panels.
            colecao = (pai.users_collection[0] if pai is not None
                       and pai.users_collection else context.collection)
            colecao.objects.link(grupo)
            grupo[_chapas.MARCA_PORTAS] = 1
            _chapas._ocultar_empty(grupo)
            grupo.parent = pai
            # Dimensions are world-space even when the parent is scaled.
            if pai is not None:
                grupo.matrix_parent_inverse = pai.matrix_world.inverted()
        # The opening moves during resize: updating dimensions alone left
        # the old origin and made the door drift past the cabinet edge.
        grupo.matrix_world = matriz
        _renomear_porta(grupo, parametros)
        grupo['porta_parametros'] = dict(parametros)
        grupo['porta_vao_largura_mm'] = largura
        grupo['porta_vao_altura_mm'] = altura
        if frente:
            grupo['porta_frente'] = frente
        if largura_em:
            grupo['porta_largura_em'] = largura_em
        for i, (l, a, e, centro) in enumerate(calculadas):
            antigo = None
            if i < len(antigas):
                folha = antigas[i]
                if folha.data.users > 1:
                    folha.data = folha.data.copy()
                antigo = (folha.chapa_largura_mm, folha.chapa_comprimento_mm,
                          folha.chapa_espessura_mm)
                if folha.get('porta_curva_modelada'):
                    # Curved wood extends beyond nominal width at corners:
                    # resize measures dimension changes, not the mesh.
                    _chapas.guardar_referencia_malha(folha, antigo[0] / 1000,
                                                     antigo[1] / 1000)
            else:
                malha = bpy.data.meshes.new("Leaf %02d" % (i + 1))
                folha = bpy.data.objects.new("Leaf %02d" % (i + 1), malha)
                grupo.users_collection[0].objects.link(folha)
                folha[_chapas.MARCA_CHAPA] = 1
                folha[_chapas.MARCA_FOLHA] = 1
            _ferragens._padronizar_nome(folha, "Leaf %02d" % (i + 1))
            folha['porta_indice'] = i
            folha.parent = grupo
            folha.matrix_parent_inverse = Matrix.Identity(4)
            # Opening survives resize (Phase 3).
            folha[_ferragens.CHAVE_CENTRO_FOLHA] = tuple(centro)
            if parametros.get('abertura') == 'ZIGZAG':
                folha[_ferragens.CHAVE_ABERTURA] = fracao_zigzag
            folha.matrix_basis = _ferragens._matriz_abertura(
                parametros, largura, len(calculadas), i, (l, a, e, centro),
                folha.get(_ferragens.CHAVE_ABERTURA, 0.0))
            folha.chapa_largura_mm = l
            folha.chapa_comprimento_mm = a
            folha.chapa_espessura_mm = e
            folha.chapa_auto = True
            _vestir_folha(folha, parametros)
            if antigo is not None:
                _ajustar_puxadores(folha, antigo, (l, a, e))
        # Only generated leaves omitted by the new type.
        # Their handles remain loose in place, then transfer to
        # the nearest surviving leaf.
        orfaos = []
        for folha in antigas[len(calculadas):]:
            for pux in [c for c in folha.children if _chapas.MARCA_PUXADOR in c]:
                mundo = pux.matrix_world.copy()
                pux.parent = None
                pux.matrix_world = mundo
                orfaos.append(pux)
            for ferragem in [c for c in folha.children_recursive
                             if _ferragens.CHAVE_FERRAGEM in c]:
                _ferragens._remover_ferragem(ferragem)
            malha = folha.data
            bpy.data.objects.remove(folha, do_unlink=True)
            if malha.users == 0:
                bpy.data.meshes.remove(malha)
        _ferragens._montar_ferragens(grupo, parametros, largura, altura, calculadas)
        modulo = pai if pai is not None and _chapas.MARCA_CONJUNTO in pai else None
        caixa = _caixa_do_modulo(modulo) if modulo is not None else None
        moldura = _montar_moldura(grupo, _pecas_moldura(
            parametros, largura, altura, caixa[2] if caixa else 0.0),
            _canais_das_bases(parametros))
    finally:
        _chapas._ocupado[0] = ocupado_antes
    if abertura_anterior != parametros.get('abertura'):
        context.view_layer.update()
        _puxadores.adaptar_abertura(grupo, abertura_anterior)
    for folha in _folhas_portas(grupo) + moldura:
        _chapas.gerar_malha_chapa(folha)
    context.view_layer.update()
    if modulo is not None:
        # The frame is part of the cabinet box: include it in cabinet
        # dimensions, or stop including it when removed.
        _modulos.sincronizar_medidas_conjunto(modulo)
    refazer = set()
    for pux in orfaos:
        folha = _folha_mais_proxima(pux, _folhas_portas(grupo))
        if (folha is not None and _puxadores._eh_puxador_parametrico(pux)
                and pux['puxador_tipo'] == 'PERFIL'
                and pux.get('puxador_borda') in _puxadores._rebaixos_da_chapa(folha)):
            # The surviving leaf already has a profile on this edge: avoid doubling it.
            bpy.data.objects.remove(pux, do_unlink=True)
            continue
        _ligar_puxador(pux, folha)
        if folha is not None and _puxadores._eh_puxador_parametrico(pux):
            refazer.add(folha.name)
    for nome in refazer:
        # Parametric handles use the same edge/fraction on the new leaf.
        _chapas.gerar_malha_chapa(bpy.data.objects[nome])
    if parametros.get('abertura') == 'ZIGZAG':
        _puxadores.puxador_terminal(context, grupo)
    return grupo


def _copiar_parametros(valor):
    if hasattr(valor, 'to_dict'):
        valor = valor.to_dict()
    if hasattr(valor, 'to_list'):
        valor = valor.to_list()
    if isinstance(valor, dict):
        return {k: _copiar_parametros(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_copiar_parametros(v) for v in valor]
    return valor


def _centro_mundo(obj):
    cantos = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    return sum(cantos, Vector()) / len(cantos)


def _folha_mais_proxima(obj, folhas):
    centro = _centro_mundo(obj)
    return min(folhas, key=lambda f: (f.matrix_world.translation - centro).length,
               default=None)


def _ligar_puxador(pux, folha):
    """Parent the handle to the leaf WITHOUT moving it.

    Keep the inverse identity so `matrix_basis` IS the handle's position
    in leaf coordinates (X width, Y height, Z thickness, centered origin),
    where `_ajustar_puxadores` performs its calculations.
    """
    if folha is None:
        return
    mundo = pux.matrix_world.copy()
    pux.parent = folha
    pux.matrix_parent_inverse = Matrix.Identity(4)
    pux.matrix_basis = folha.matrix_world.inverted() @ mundo


def _ajustar_puxadores(folha, antigo, novo):
    """The leaf changed from old to new (L, A, E): make its handle follow.

    LOCKED axis: keep size and distance to the nearest leaf edge.
    UNLOCKED: stretch proportionally from the leaf center (distorting
    the handle). Exclude parametric `puxador_tipo`: `posicionar_puxador`
    rebuilds it from leaf properties in the `gerar_malha_chapa` hook.
    """
    for pux in [c for c in folha.children if _chapas.MARCA_PUXADOR in c
                and not _puxadores._eh_puxador_parametrico(c)]:
        relativo = pux.matrix_parent_inverse @ pux.matrix_basis
        cantos = [relativo @ Vector(c) for c in pux.bound_box]
        travas = list(pux.get(_chapas.CHAVE_TRAVAS_PUXADOR, (1, 1, 1)))
        deslocar, escala = Vector(), [1.0, 1.0, 1.0, 1.0]
        for k in range(3):
            meia_antes, meia_nova = antigo[k] / 2000.0, novo[k] / 2000.0
            if abs(meia_nova - meia_antes) < 1e-9 or meia_antes <= 0:
                continue
            if travas[k]:
                c_min = min(p[k] for p in cantos)
                c_max = max(p[k] for p in cantos)
                sinal = 1 if (meia_antes - c_max) <= (c_min + meia_antes) else -1
                deslocar[k] = sinal * (meia_nova - meia_antes)
            else:
                escala[k] = meia_nova / meia_antes
        pux.matrix_parent_inverse = Matrix.Identity(4)
        pux.matrix_basis = (Matrix.Translation(deslocar)
                            @ Matrix.Diagonal(escala) @ relativo)


def _limitar_folhas_cena(self, context):
    """The new opening type may reject the current leaf count."""
    limite = LIMITES_FOLHAS.get(self.porta_abertura, 1)
    if self.porta_folhas > limite:
        self.porta_folhas = limite
    if self.porta_abertura == 'ZIGZAG' and self.porta_folhas < 2:
        self.porta_folhas = 2


def _limitar_folhas_portas(self, context):
    limite = LIMITES_FOLHAS[self.abertura]
    if self.folhas > limite:
        self.folhas = limite
    if self.abertura == 'ZIGZAG' and self.folhas < 2:
        self.folhas = 2


# ==================================== DOOR OPENING CAPTURE
# Marking an opening required Edit Mode and two vertices on different
# panels. The capture tool (`cabinet_apanhar_vao`, in `assistente`)
# keeps the user in Object Mode: Blender's NATIVE snap moves the cursor
# to a vertex, the first click fixes a corner, and the leaf preview
# follows the cursor until the second click.
RAIO_IMA_PX = 28.0          # Pixel reach for choosing a wizard edge.

ARESTAS_CAIXA = (
    (0, 1), (1, 3), (3, 2), (2, 0),
    (4, 5), (5, 7), (7, 6), (6, 4),
    (0, 4), (1, 5), (2, 6), (3, 7),
)


# ---- CREATION WIZARD (user backlog, Epic 1)
# Four clicks from the user's sketch: 1 = DOOR corner, 2 = OPENING corner,
# 3 = opposite opening corner, 4 = opposite door corner. Orange lines 1-2
# and 3-4 show coverage; white 2-3 shows the opening. These determine
# leaf, opening and automatic hinge: full thickness = straight,
# half = half-overlay, inside = inset. Other coverage asks whether
# dimensions are correct. Continue in the same order as the tab:
# LEAVES (1 | 2), TYPE (only what cannot be inferred: swing | lift-up,
# or swing | sliding for inset), hinge EDGE
# (click; omitted for lift-up, always TOP, and for two leaves),
# COUNT (scroll), MARGIN (mouse Y), then lift-up PISTONS:
# count (scroll) and AUTOMATIC initial position, adjustable only upward
# by mouse Y because lowering exceeds piston travel. The modal draws
# its own choice boxes rather than popup_menu, so opening-click release
# cannot answer them and tests can click them. The modal/boxes live in
# `assistente`; their constants and calculations remain here.
OPCOES_CONFIRMAR = (('SIM', "Yes, Create This"), ('NAO', "No, Mark Again"))
OPCOES_FOLHAS = tuple((str(n), "%d door panel%s" % (n, '' if n == 1 else 's')) for n in range(1, 9))
# Sidebar button confirming the wizard step (value = step).
CONFIRMAR_ETAPA = 'confirmar_etapa'
# Overlay: sliding doors use a FRAME; the outer-to-inner gesture
# places the door in front of the cabinet, as requested.
TIPOS_SOBREPOSTA = (('GIRO', "Hinged"), ('BASCULANTE', "Lift-up"),
                    ('CORRER', "Sliding"), ('ZIGZAG', 'Zig-zag'))
TIPOS_EMBUTIDA = (('GIRO', "Hinged (Full Crank)"), ('CORRER', "Sliding"), ('ZIGZAG', 'Zig-zag'))
COR_FIO_VAO = (1.0, 1.0, 1.0, 1.0)
COR_BORDA_EIXO = (0.25, 0.85, 0.3, 1.0)       # Green.
MARGEM_DOBRADICAS_PADRAO = 100.0   # mm from the corner: woodworking practice.
LIMITES_DOBRADICAS = (2, 6)
LIMITES_PISTOES = (1, 2)
_assistente_porta = [None]          # Wizard state read by tests.
# Doors-tab choice target answering the wizard, mirroring its choice box.
ALVO_ASSISTENTE = '@assistente'


def _qtd_dobradicas_padrao(comprimento_mm):
    """Default from leaf height (woodworking practice); scroll adjusts it."""
    for teto, n in ((900, 2), (1600, 3), (2000, 4)):
        if comprimento_mm <= teto:
            return n
    return 5


def _parametros_do_wizard(w):
    """Parameters for the wizard's door: preview opening, coverage and
    thickness, combined with answers given so far."""
    return dict(w.get('parametros') or {}, **w.get('escolhas', {}))


def _qtd_pistoes_padrao(largura_mm):
    """One on each side of wide leaves; only one for small wall cabinets."""
    return 2 if largura_mm > 600 else 1


# Actual furniture gas pistons: (open center-to-center, body diameter,
# rod diameter), in mm. 155/195 = Metrol NS-FF-6-60/-80 (15x6);
# 245 = cabinet "10 inch" (100 N, 18x8); 290-450 = Metrol 8 mm series
# (18x8). User's calculation rule: fully open door = DOUBLE closed
# piston length (actual travel is 60-90% of closed length).
PISTOES_CATALOGO = ((155.0, 15.0, 6.0), (195.0, 15.0, 6.0),
                    (245.0, 18.0, 8.0), (290.0, 18.0, 8.0),
                    (350.0, 18.0, 8.0), (410.0, 18.0, 8.0),
                    (450.0, 18.0, 8.0))
RAZAO_PISTAO = 2.0               # Open / closed.
PISTAO_RECUO_MM = 50.0           # Side mounting axis behind the leaf.
PISTAO_SUPORTE_MM = 10.0         # Leaf pin: bracket height.
PISTAO_SUPORTE_LADO_MM = 24.0    # Plate width/height.
PISTAO_DA_DOBRADICA_MIN_MM = 30.0  # Maximum upward travel of the leaf bracket.
PISTAO_FRACAO_DO_VAO = 2.0 / 3.0   # Side mounting in the upper two-thirds of the opening.


def _geometria_pistao(aberto, folha, cob_topo, abrir, offset=0.0):
    """Position ONE `aberto` mm piston on a lift-up door.

    In side section: `d` is leaf-bracket drop from leaf top, `vs` is
    side-mount drop from that same top (`recuo` behind the rear face).
    Closed length is aberto/RAZAO (hence vs = d + k). `abrir` maps the
    closed leaf point to its OPEN pose, either axis rotation or straight-
    hinge rig motion (`_matriz_abertura`). Binary search finds `d` giving
    length `aberto` there, since reach increases with d.

    `offset` is manual side-mount position in mm from OPENING TOP
    (0 = automatic). Closed length stays fixed; accept only positions
    reachable when open (automatic is the maximum).
    """
    _l, a, _e, centro = folha
    topo, costas = centro[1] + a / 2.0, centro[2] - _e / 2.0
    fechado = aberto / RAZAO_PISTAO
    dz = PISTAO_RECUO_MM - PISTAO_SUPORTE_MM
    k = math.sqrt(max(0.0, fechado * fechado - dz * dz))

    def alcance(d):
        na_folha = Vector((0.0, topo - d, costas - PISTAO_SUPORTE_MM))
        lateral = Vector((0.0, topo - d - k, costas - PISTAO_RECUO_MM))
        return (abrir(na_folha) - lateral).length

    baixo, cima = PISTAO_DA_DOBRADICA_MIN_MM, max(PISTAO_DA_DOBRADICA_MIN_MM, a)
    if alcance(baixo) >= aberto:
        d_max = baixo
    elif alcance(cima) <= aberto:
        d_max = cima
    else:
        for _passo in range(60):
            meio = (baixo + cima) / 2.0
            if alcance(meio) < aberto:
                baixo = meio
            else:
                cima = meio
        d_max = (baixo + cima) / 2.0
    d = d_max
    if offset > 0.0:
        d = max(PISTAO_DA_DOBRADICA_MIN_MM, min(d_max, offset + cob_topo - k))
    vs = d + k
    return {'aberto': aberto, 'fechado': fechado, 'd': d, 'vs': vs,
            'offset': vs - cob_topo, 'offset_max': d_max + k - cob_topo,
            'offset_min': PISTAO_DA_DOBRADICA_MIN_MM + k - cob_topo,
            # Piston length with the door open (= `aberto` in automatic mode).
            'alcance': alcance(d), 'abrir': abrir}


def _pistao_do_vao(altura, folha, offset=0.0, p=None):
    """Choose and position a catalog piston. `folha` = CLOSED (l, a, e,
    center) in opening coordinates (opening top y = `altura`).

    Use the LARGEST fitting piston for better leverage, with the side
    mount in the upper two-thirds and the leaf bracket within the leaf.
    Very low openings use the smallest. `p` specifies leaf opening motion."""
    _l, a, e, centro = folha
    cob_topo = centro[1] + a / 2.0 - altura
    parametros = dict(p or {})
    parametros['abertura'] = 'BASCULANTE'
    aberta = _ferragens._matriz_abertura(parametros, 0.0, 1, 0, folha, 1.0)
    c = Vector(centro)

    def abrir(ponto):
        return (aberta @ ((ponto - c) / 1000.0)) * 1000.0

    escolhido = PISTOES_CATALOGO[0]
    for modelo in reversed(PISTOES_CATALOGO):
        g = _geometria_pistao(modelo[0], folha, cob_topo, abrir)
        if (g['offset'] <= altura * PISTAO_FRACAO_DO_VAO
                and g['d'] <= a - PISTAO_DA_DOBRADICA_MIN_MM):
            escolhido = modelo
            break
    g = _geometria_pistao(escolhido[0], folha, cob_topo, abrir, offset)
    g.update(corpo=escolhido[1], haste=escolhido[2])
    return g


def _pontas_pistao(g, x, folha):
    """(side, closed leaf, open leaf) in opening-space mm."""
    _l, a, e, centro = folha
    topo, costas = centro[1] + a / 2.0, centro[2] - e / 2.0
    na_folha = Vector((x, topo - g['d'], costas - PISTAO_SUPORTE_MM))
    return (Vector((x, topo - g['vs'], costas - PISTAO_RECUO_MM)),
            na_folha, g['abrir'](na_folha))


def _posicoes_ferragens(comprimento, qtd, margem):
    """Distances in mm from the axis start for `qtd` equally spaced hardware
    items, with end items `margem` from the corners."""
    if qtd <= 0:
        return []
    if qtd == 1:
        return [comprimento / 2.0]
    margem = max(0.0, min(margem, comprimento / 2.0))
    passo = (comprimento - 2.0 * margem) / (qtd - 1)
    return [margem + i * passo for i in range(qtd)]


def _arestas_da_porta(largura, altura, coberturas, lateral, tipo):
    """Hinge positions in opening-space mm (x width, y height): LEFT/RIGHT
    for swing doors, TOP for lift-up.

    The line lies on the side panel's INNER FACE at the opening boundary
    (inner side of the thickness marked by clicks 1-2), not the leaf edge:
    this is where the hinge body attaches. Length follows the LEAF, with
    margins from its corners. `dentro` points into the cabinet; `cobertura`
    is leaf projection beyond the line in mm, keeping the cup in the leaf."""
    cob = [_cobertura_mm(float(coberturas.get(k, 0.0)), lateral)
           for k in COBERTURAS_LADOS]
    x0, x1 = -cob[0], largura + cob[1]
    y0, y1 = -cob[2], altura + cob[3]
    lados = {
        'ESQUERDA': (Vector((0.0, y0)), Vector((0.0, y1)), Vector((1, 0)), cob[0]),
        'DIREITA': (Vector((largura, y0)), Vector((largura, y1)),
                    Vector((-1, 0)), cob[1]),
        'CIMA': (Vector((x0, altura)), Vector((x1, altura)), Vector((0, -1)),
                 cob[3]),
    }
    usados = ('CIMA',) if tipo == 'BASCULANTE' else ('ESQUERDA', 'DIREITA')
    return [{'lado': lado, 'a': lados[lado][0], 'b': lados[lado][1],
             'dentro': lados[lado][2], 'cobertura': lados[lado][3]}
            for lado in usados]


# 35 mm concealed cup-hinge volume (see the door plan): BODY (mounting
# plate + arm) on the side panel's inner face behind the leaf, and CUP
# bored into the leaf's rear. Approximate dimensions for occupied-space
# visualization, not machining.
DOBRADICA_ALTURA_MM = 50.0     # Along the edge.
DOBRADICA_AVANCO_MM = 22.0     # From the inner face into the cabinet.
DOBRADICA_FUNDO_MM = 70.0      # Rearward from the leaf's rear face.
CANECO_DIAMETRO_MM = 35.0
CANECO_FUNDO_MM = 12.0         # Leaf bore (~11.5-13 mm).
# Cup flange/arm-head protrusion from the leaf rear: fully inside
# the bore, it disappeared into the door mesh in the user's image.
CANECO_ABA_MM = 4.0
CANECO_BORDA_MM = 5.0          # Leaf edge to bore (center ~22.5).
# Hinges must never overlap: a margin reaching edge center used to stack
# them all. Center spacing must include the body plus this clearance,
# and end hinges must remain entirely within the leaf.
FOLGA_ENTRE_DOBRADICAS_MM = 10.0
PASSO_MIN_DOBRADICAS_MM = DOBRADICA_ALTURA_MM + FOLGA_ENTRE_DOBRADICAS_MM
MARGEM_MIN_DOBRADICAS_MM = DOBRADICA_ALTURA_MM / 2.0


def _ajustar_dobradicas(comprimento, qtd, margem):
    """Return (count, margin) fitting an edge `comprimento` mm long. Margin
    keeps the entire hinge on the leaf and maintains at least
    `PASSO_MIN_DOBRADICAS_MM` between neighbors. Clamp count to capacity,
    never below the LIMITES_DOBRADICAS minimum."""
    util = comprimento - 2.0 * MARGEM_MIN_DOBRADICAS_MM
    cabem = int(max(0.0, util) // PASSO_MIN_DOBRADICAS_MM) + 1
    qtd = max(LIMITES_DOBRADICAS[0], min(LIMITES_DOBRADICAS[1], cabem, int(qtd)))
    maximo = (comprimento - (qtd - 1) * PASSO_MIN_DOBRADICAS_MM) / 2.0
    # Door too small for `qtd`: endpoints still govern; nothing outside the leaf.
    margem = max(MARGEM_MIN_DOBRADICAS_MM, min(float(margem), maximo))
    return qtd, min(margem, comprimento / 2.0)


def _caixa_da_ferragem(centro, eixo, dentro, faixa_u, faixa_v, faixa_z):
    """Eight corners in mm, ordered like preview boxes (ARESTAS_CAIXA)."""
    return [Vector((*(centro + eixo * u + dentro * v), z))
            for u in faixa_u for v in faixa_v for z in faixa_z]


def _caixas_dobradicas(aresta, distancias, costas_mm):
    """Return [(body, cup)] per hinge: occupied-space boxes in opening mm.
    `costas_mm` is the leaf rear-face z."""
    a, b = aresta['a'], aresta['b']
    eixo = (b - a).normalized() if (b - a).length else Vector((0, 1))
    dentro = aresta['dentro']
    borda = -float(aresta.get('cobertura', 0.0))     # Leaf edge.
    meia, raio = DOBRADICA_ALTURA_MM / 2.0, CANECO_DIAMETRO_MM / 2.0
    caixas = []
    for d in distancias:
        centro = a + eixo * d
        corpo = _caixa_da_ferragem(
            centro, eixo, dentro, (-meia, meia), (0.0, DOBRADICA_AVANCO_MM),
            (costas_mm - DOBRADICA_FUNDO_MM, costas_mm))
        caneco = _caixa_da_ferragem(
            centro, eixo, dentro, (-raio, raio),
            (borda + CANECO_BORDA_MM,
             borda + CANECO_BORDA_MM + CANECO_DIAMETRO_MM),
            (costas_mm - CANECO_ABA_MM, costas_mm + CANECO_FUNDO_MM))
        caixas.append((corpo, caneco))
    return caixas


# Scene properties used by the Doors tab for the NEXT door;
# HUD dragging saves all of them and restores them on Esc.
_PROPS_PORTAS_CENA = (
    "porta_abertura", "porta_dobradica", "porta_folhas", "porta_associar",
    "porta_trilho", "porta_folha",
) + tuple(m[1] for m in MEDIDAS_PORTAS)
