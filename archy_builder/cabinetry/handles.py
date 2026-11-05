"""Parametric handles (user profile, pull, edge handle), placement tool
and Alt-drag to another edge."""

import bpy, bmesh, math, os, json, gpu
from gpu_extras.batch import batch_for_shader
from bpy.props import FloatVectorProperty, StringProperty
from mathutils import Matrix, Vector
from bpy_extras import view3d_utils
from bpy.types import Operator

# Used at LOAD time (class bodies/constants): already loaded earlier.
from .. import ferragens as _ferragens
# Used only at runtime (circular imports): __init__ binds these
# aliases after loading all modules (`_ligar_modulos`).
_biblioteca = None
_chapas = None
_modulos = None
_eventos = None
_portas = None
_gaveta_eventos = None
_importacao = None
_hud = None
_solda = None
_gavetas = None
_frentes = None
_arame = None

# ======================================== PARAMETRIC HANDLES
# Three ready-made models in EDGE coordinates at the clicked face edge:
# X along the edge, Y inward across the face, Z out of the face.
# State lives on the handle itself (edge, face, fraction, setback), and
# `posicionar_puxador` rebuilds everything from panel
# PROPERTIES, without an error-prone old dimension, so resizing a door,
# panel or cabinet carries its handle along.
MODELOS_PUXADOR = {
    # (name, length, setback) in mm; profiles span the entire edge.
    'PERFIL': ("Profile", 0.0, 0.0),
    'ALCA': ("Pull", 148.0, 40.0),
    # 80 mm with 64 mm hole spacing: commercial slim edge-handle standard.
    'BORDA': ("Edge", 80.0, 0.0),
    # USER model: mesh and length come from the user's .blend below.
    'MODELO': ("Model", 0.0, 40.0),
}
# Factory models in carousel order are PROTECTED as requested:
# they live in the add-on, not the library, and cannot be edited there.
MODELOS_PADRAO = ('PERFIL', 'ALCA', 'BORDA')
ALTURA_PERFIL_MM = 30.0     # J-profile strip width for the box fallback, without the asset.
BORDAS_CHAPA = ('X-', 'X+', 'Y-', 'Y+')
MATERIAL_PUXADOR = "Handle"


def _caixas_puxador(tipo, espessura, comprimento):
    """Boxes (x0, x1, y0, y1, z0, z1) in edge-space mm.

    PROFILE: J profile flush with both faces in the removed strip; its
    finger recess opens at the front between edge flange and front plate.
    PULL: bar with two legs standing on the face. EDGE: cap on the edge
    with a thin flange dropping in front of the face.
    """
    meio, e = comprimento / 2.0, espessura
    if tipo == 'PERFIL':
        h = ALTURA_PERFIL_MM
        return [(-meio, meio, h - 2, h, -e, 0),     # Base against the wood.
                (-meio, meio, 15, h, -2, 0),        # Front, flush with the face.
                (-meio, meio, 0, h, -e, -e + 2),    # Rear.
                (-meio, meio, 0, 2, -e, -6)]        # Edge flange.
    if tipo == 'ALCA':
        return [(-meio, meio, -5, 5, 20, 30),
                (-meio + 5, -meio + 15, -5, 5, 0, 20),
                (meio - 15, meio - 5, -5, 5, 0, 20)]
    return [(-meio, meio, -5, 0, -e, 8),
            (-meio, meio, -5, 15, 6, 8)]


def _material_puxador():
    material = bpy.data.materials.get(MATERIAL_PUXADOR)
    if material is None:
        material = bpy.data.materials.new(MATERIAL_PUXADOR)
        material.diffuse_color = (0.09, 0.09, 0.1, 1.0)
        material.metallic = 0.8
        material.roughness = 0.35
    return material


# ---- Actual PROFILE handle: the user's aluminum model
# (`extrair_puxador.py`), already in edge coordinates. Change length
# by stretching only the ENDS, retaining their chamfers. Adapt leaf
# thickness by scaling only behind the face; front, lip and recess
# retain model geometry. The model determines the removed wood strip.
# Fall back to the box J profile without the asset.
ARQUIVO_PUXADOR_PERFIL = os.path.join(_ferragens.PASTA_FERRAGENS, 'puxador_perfil.blend')
_puxador_perfil = [None]     # Asset .json, read once.
_corte_perfil = [None]       # Model section (z, gap), measured once.


def _dados_perfil():
    if _puxador_perfil[0] is None:
        try:
            with open(os.path.join(_ferragens.PASTA_FERRAGENS, 'puxador_perfil.json'),
                      encoding='utf-8') as f:
                dados = json.load(f)
            for chave in ('altura_mm', 'espessura_porta_mm', 'comprimento_mm'):
                dados[chave] = float(dados[chave])
            _puxador_perfil[0] = dados
        except (OSError, ValueError, KeyError, TypeError):
            _puxador_perfil[0] = {}
    if not _puxador_perfil[0] or not os.path.exists(ARQUIVO_PUXADOR_PERFIL):
        return None
    return _puxador_perfil[0]


def _altura_perfil_mm():
    """Wood strip occupied by the profile."""
    dados = _dados_perfil()
    return dados['altura_mm'] if dados else ALTURA_PERFIL_MM


def _malha_modelo_perfil():
    """Model mesh, loaded once and used by no object."""
    dados = _dados_perfil()
    if dados is None:
        return None
    for malha in bpy.data.meshes:
        if malha.get('cabinet_origem') == dados['malha'] and not malha.library:
            if _arame is not None:
                _arame.preparar_modelos()
            return malha
    novas = _ferragens._anexar_sem_repetir(ARQUIVO_PUXADOR_PERFIL, 'meshes',
                                {dados['malha']})
    if novas and _arame is not None:
        _arame.preparar_modelos()
    return novas[0] if novas else None


def _corte_do_perfil(modelo):
    """(cut z, gap) in m: where the profile SECTION splits to accommodate
    door thickness, at the largest vertex-free gap between rear and face.
    Move everything behind it, including rounded rear corners, as a unit;
    only the straight gap section stretches/shrinks."""
    if _corte_perfil[0] is None:
        zs = sorted({round(v.co.z, 7) for v in modelo.vertices if v.co.z < 0.0})
        vaos = [(b - a, (a + b) / 2.0) for a, b in zip(zs, zs[1:])]
        vao, corte = max(vaos) if vaos else (0.0, 0.0)
        _corte_perfil[0] = (corte, vao)
    return _corte_perfil[0]


def _deformar_perfil(co, estica, corte, recua, fator):
    """Map a profile-model point onto the current door, changing size but
    NOT chamfers. Length: move each end intact by `estica`. Thickness:
    move geometry behind `corte` by `recua`; if the gap cannot accommodate
    a much thinner door, fall back to scaling with `fator`."""
    x, y, z = co
    if recua is None:
        z = z * fator if z < 0.0 else z
    elif z < corte:
        z += recua
    # copysign(estica, x) lost the SIGN of estica: an edge shorter than
    # the model expanded the ends outward instead of shrinking.
    return Vector((x + estica * math.copysign(1.0, x), y, z))


def _ajuste_do_perfil(modelo, espessura, comprimento):
    """Model-to-door (estica, corte, recua, fator)."""
    dados = _dados_perfil()
    estica = (comprimento - dados['comprimento_mm']) / 2000.0
    fator = espessura / dados['espessura_porta_mm']
    corte, vao = _corte_do_perfil(modelo)
    recua = -(espessura - dados['espessura_porta_mm']) / 1000.0
    # A door THINNER than the model nearly eliminates the straight gap;
    # beyond that, the rear would pass through the face.
    if recua > 0.9 * vao:
        recua = None
    return estica, corte, recua, fator


def _bmesh_perfil(modelo, espessura, comprimento, chapa=None,
                   borda='Y+', face=1):
    """Preview and final part share the same derived mesh without touching wood."""
    ajuste = _ajuste_do_perfil(modelo, espessura, comprimento)
    bm = bmesh.new()
    try:
        bm.from_mesh(modelo)
        for v in bm.verts:
            v.co = _deformar_perfil(v.co, *ajuste)
        _acompanhar_borda(bm, chapa, borda, face, comprimento)
        bm.normal_update()
        return bm
    except Exception:
        bm.free()
        raise


def _acompanhar_borda(bm, chapa, borda, face, comprimento):
    if (chapa is None or _frentes is None
            or _frentes.referencia(chapa) is None or comprimento <= 0):
        return
    borda, _fracao = _borda_e_fracao(chapa, borda, .5)
    centro, _ = _frentes.lugar(chapa, borda, face, .5, 0, 0, inteiro=True)
    inicio, _ = _frentes.lugar(chapa, borda, face, 0, 0, 0)
    fim, _ = _frentes.lugar(chapa, borda, face, 1, 0, 0)
    sinal = (1 if (fim.translation - inicio.translation).dot(
        centro.to_3x3().col[0]) >= 0 else -1)
    tamanho = comprimento / 1000.0
    cortes = set()
    for chave in _frentes.bordas(chapa, face):
        if chave.split('|')[0] != borda or '|' not in chave:
            continue
        for t in (0, 1):
            _, fracao = _frentes.normalizar_borda(chapa, chave, t)
            if 1e-6 < fracao < 1 - 1e-6:
                cortes.add(sinal * (fracao - .5) * tamanho)
    # Long asset faces need sections at front corners; moving only original
    # vertices would leave chords crossing the curve.
    for x in sorted(cortes):
        bmesh.ops.bisect_plane(
            bm, geom=list(bm.verts) + list(bm.edges) + list(bm.faces),
            dist=1e-7, plane_co=(x, 0, 0), plane_no=(1, 0, 0))
    inversa = centro.inverted_safe()
    quadros = {}
    for v in bm.verts:
        x, y, z = v.co
        if x not in quadros:
            quadro, _ = _frentes.lugar(
                chapa, borda, face, max(0, min(1, .5 + sinal*x/tamanho)), 0, 0)
            quadros[x] = inversa @ quadro
        v.co = quadros[x] @ Vector((0, y, z))


def _malha_perfil_do_modelo(pux, modelo, espessura, comprimento):
    bm = _bmesh_perfil(modelo, espessura, comprimento, pux.parent,
                        pux.get('puxador_borda', 'Y+'),
                        int(pux.get('puxador_face', 1)))
    bm.to_mesh(pux.data)
    bm.free()
    pux.data.update()
    pux.data.materials.clear()
    for material in modelo.materials:
        pux.data.materials.append(material)


# ---- Actual EDGE handle: the user's slim flange model
# (`extrair_puxador_borda.py`) in edge coordinates: cap over the edge,
# rolled front and two-hole rear flange. Resizing NEVER scales details:
# for length, move each half intact from a vertex-free gap between
# the middle and a hole. Holes stay 8 mm from the ends (80 -> 64,
# 144 -> 128 hole spacing, matching commercial models). For door
# thickness, move the flange and geometry behind the rear cut.
# Holes, chamfers and rolled front retain model geometry.
ARQUIVO_PUXADOR_BORDA = os.path.join(_ferragens.PASTA_FERRAGENS, 'puxador_borda.blend')
_puxador_borda = [None]      # Asset .json, read once.


def _dados_borda():
    if _puxador_borda[0] is None:
        try:
            with open(os.path.join(_ferragens.PASTA_FERRAGENS, 'puxador_borda.json'),
                      encoding='utf-8') as f:
                dados = json.load(f)
            for chave in ('espessura_porta_mm', 'comprimento_mm', 'corte_x', 'vao_x',
                          'corte_costas', 'vao_costas'):
                dados[chave] = float(dados[chave])
            _puxador_borda[0] = dados
        except (OSError, ValueError, KeyError, TypeError):
            _puxador_borda[0] = {}
    if not _puxador_borda[0] or not os.path.exists(ARQUIVO_PUXADOR_BORDA):
        return None
    return _puxador_borda[0]


def _malha_modelo_borda():
    """Model mesh, loaded once and used by no object."""
    dados = _dados_borda()
    if dados is None:
        return None
    for malha in bpy.data.meshes:
        if malha.get('cabinet_origem') == dados['malha'] and not malha.library:
            return malha
    novas = _ferragens._anexar_sem_repetir(ARQUIVO_PUXADOR_BORDA, 'meshes', {dados['malha']})
    return novas[0] if novas else None


def _ajuste_da_borda(espessura, comprimento):
    """(estica, fator_x, recua, fator_z, corte_x, corte_costas). Fall back
    to scaling when shorter/thinner than the gaps can accommodate."""
    dados = _dados_borda()
    estica = (comprimento - dados['comprimento_mm']) / 2000.0
    recua = -(espessura - dados['espessura_porta_mm']) / 1000.0
    fator_x = (comprimento / dados['comprimento_mm']
               if -2.0 * estica > 0.9 * dados['vao_x'] else None)
    fator_z = (espessura / dados['espessura_porta_mm']
               if recua > 0.9 * dados['vao_costas'] else None)
    return estica, fator_x, recua, fator_z, dados['corte_x'], dados['corte_costas']


def _deformar_borda(co, estica, fator_x, recua, fator_z, corte_x, corte_costas):
    """Map an edge-model point onto this door using translation only,
    so saved Weighted Normal normals remain valid."""
    x, y, z = co
    if fator_x is not None:
        x *= fator_x
    else:
        x += estica if x > corte_x else -estica
    if fator_z is not None:
        z = z * fator_z if z < 0.0 else z
    elif z < corte_costas:
        z += recua
    return Vector((x, y, z))


def _bmesh_borda(modelo, espessura, comprimento):
    ajuste = _ajuste_da_borda(espessura, comprimento)
    bm = bmesh.new()
    try:
        bm.from_mesh(modelo)
        for v in bm.verts:
            v.co = _deformar_borda(v.co, *ajuste)
        bm.normal_update()
        return bm
    except Exception:
        bm.free()
        raise


NOME_NORMAIS_BORDA = "Edge normals"


def _normais_da_borda(pux, ligar):
    """Weighted Normal for EDGE handles: 22.5-degree rounded corners, below
    Smooth by Angle's 30 degrees, caused gradients on flat faces. Use a
    modifier rather than saved normals because the mesh resizes each time."""
    modificador = pux.modifiers.get(NOME_NORMAIS_BORDA)
    if ligar and modificador is None:
        modificador = pux.modifiers.new(NOME_NORMAIS_BORDA, 'WEIGHTED_NORMAL')
        modificador.mode, modificador.weight = 'FACE_AREA', 100
        modificador.keep_sharp = True
    elif not ligar and modificador is not None:
        pux.modifiers.remove(modificador)


FOLGA_PONTA_PARAFUSO_M = 0.003     # Minimum tip clearance from the front.


def lugares_dos_parafusos_borda(espessura, comprimento):
    """Edge-space matrix of each flange screw: seated in its hole, moving
    with flange and end; head points rearward (-Z)."""
    dados = _dados_borda()
    if dados is None:
        return []
    ajuste = _ajuste_da_borda(espessura, comprimento)
    vira = Matrix.Rotation(math.pi, 4, 'X')
    return [Matrix.Translation(_deformar_borda(Vector(furo), *ajuste)) @ vira
            for furo in dados.get('furos', ())]


def ponta_do_parafuso(co):
    """Door too thin for 14 mm: shorten the tip so it never reaches the front."""
    return Vector((co.x, co.y, min(co.z, -FOLGA_PONTA_PARAFUSO_M)))


def _parafusos_da_borda(bm, espessura, comprimento):
    """Standard flange-hole screws in the SAME handle mesh, after model
    indices. Heads sit outside the flange; shanks enter the door rear.
    Shorten tips if the door cannot fit 14 mm. Return screw material or None."""
    parafuso = _ferragens.malha_parafuso()
    lugares = lugares_dos_parafusos_borda(espessura, comprimento)
    if parafuso is None or not lugares:
        return None
    for lugar in lugares:
        # from_mesh APPENDS to BMesh: move only new vertices.
        vertices, faces = len(bm.verts), len(bm.faces)
        bm.from_mesh(parafuso)
        bm.verts.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        novos = bm.verts[vertices:]
        bmesh.ops.transform(bm, verts=novos, matrix=lugar)
        for v in novos:
            v.co = ponta_do_parafuso(v.co)
        for f in bm.faces[faces:]:
            f.material_index = 1
    return parafuso.materials[0] if parafuso.materials else None


def _malha_borda_do_modelo(pux, modelo, espessura, comprimento):
    bm = _bmesh_borda(modelo, espessura, comprimento)
    material_parafuso = _parafusos_da_borda(bm, espessura, comprimento)
    # Set slots BEFORE the mesh: clearing afterwards reset screw indices.
    pux.data.materials.clear()
    for material in modelo.materials[:1]:
        pux.data.materials.append(material)
    if not pux.data.materials:
        pux.data.materials.append(_material_puxador())
    if material_parafuso is not None:
        pux.data.materials.append(material_parafuso)
    bm.to_mesh(pux.data)
    bm.free()
    pux.data.update()


# ---- USER handle (Use as handle): turn any object into a MODEL
# stored in the library's Puxadores category. The library is the SOURCE:
# editing/saving its .blend changes future creator output. The .blend
# mesh is already in edge coordinates (X along the edge, Y inward
# across the face, Z outward; origin at the anchor), so only COPY
# and position the handle. Never stretch it:
# it is the supplier's part at its own dimensions.
CATEGORIA_PUXADORES = "Handles"
SUBCATEGORIA_MODELO = "Pull"     # New-model destination, changed by Edit.
PREFIXO_MODELO = 'MODELO:'       # Carousel value: 'MODELO:<file>'.
CHAVE_MALHA_MODELO = 'cabinet_modelo_puxador'   # Loaded mesh: source file.


def valor_do_modelo(tipo, arquivo=''):
    return PREFIXO_MODELO + arquivo if tipo == 'MODELO' else tipo


def modelo_do_valor(valor):
    """'MODELO:<file>' -> ('MODELO', file); 'ALCA' -> ('ALCA', '')."""
    valor = str(valor)
    if valor.startswith(PREFIXO_MODELO):
        return 'MODELO', valor[len(PREFIXO_MODELO):]
    return valor, ''


def modelos_do_usuario():
    """Library items in the Puxadores category with an existing .blend file."""
    return sorted((it for it in _biblioteca.indice_completo()
                   if _biblioteca._niveis_de(it)[0] == CATEGORIA_PUXADORES
                   and os.path.isfile(os.path.join(it['pasta'], it['arquivo']))),
                  key=lambda it: it.get('nome', '').casefold())


def _item_do_modelo(arquivo):
    return next((it for it in modelos_do_usuario()
                 if it['arquivo'] == arquivo), None)


def nome_do_modelo(tipo, arquivo=''):
    if tipo == 'MODELO':
        it = _item_do_modelo(arquivo)
        return it.get('nome', '') if it else os.path.splitext(arquivo)[0]
    return MODELOS_PUXADOR.get(tipo, ('',))[0]


def modelo_escolhido(cena):
    """(type, file) for the next creation; missing library models revert
    to the pull handle."""
    tipo = cena.cabinet_puxador_modelo
    arquivo = cena.cabinet_puxador_arquivo if tipo == 'MODELO' else ''
    if tipo == 'MODELO' and _item_do_modelo(arquivo) is None:
        return 'ALCA', ''
    return tipo, arquivo


def escolher_modelo(cena, tipo, arquivo=''):
    cena.cabinet_puxador_modelo = tipo
    cena.cabinet_puxador_arquivo = arquivo if tipo == 'MODELO' else ''


def _malha_modelo_usuario(arquivo, carregar=True):
    """Read the model mesh from its library .blend; RELOAD when the file
    changes after user edits. With `carregar=False` during drawing/panel
    mesh work, use only already loaded data: opening .blend there would
    freeze the display."""
    atual = next((m for m in bpy.data.meshes if not m.library
                  and m.get(CHAVE_MALHA_MODELO) == arquivo), None)
    if not carregar:
        return atual
    caminho = os.path.join(_biblioteca.pasta_biblioteca(), arquivo or '')
    try:
        data = os.path.getmtime(caminho) if arquivo else None
    except OSError:
        data = None
    if data is None or (
            atual is not None and atual.get('cabinet_data') == data):
        return atual
    antes = set(bpy.data.meshes)
    try:
        with bpy.data.libraries.load(caminho) as (de, para):
            para.meshes = list(de.meshes)
    except (OSError, RuntimeError) as e:
        print("[Archy Builder] handle model:", e)
        return atual
    novas = [m for m in bpy.data.meshes if m not in antes]
    if not novas:
        return atual
    malha = max(novas, key=lambda m: len(m.vertices))
    for m in novas:
        if m is not malha:
            bpy.data.meshes.remove(m)
    if atual is not None and atual.users == 0:
        bpy.data.meshes.remove(atual)
    malha[CHAVE_MALHA_MODELO] = arquivo
    malha['cabinet_data'] = data
    _contornos_modelo.clear()
    return malha


_contornos_modelo = {}      # File -> preview contour points.


def _comprimento_do_modelo(malha):
    xs = [v.co.x for v in malha.vertices] if malha is not None else []
    return (max(xs) - min(xs)) * 1000.0 if xs else 0.0


def _copiar_malha_modelo(pux, modelo):
    bm = bmesh.new()
    bm.from_mesh(modelo)
    bm.to_mesh(pux.data)
    bm.free()
    pux.data.update()
    pux.data.materials.clear()
    for material in modelo.materials:
        pux.data.materials.append(material)


def gerar_malha_puxador(pux, espessura, comprimento):
    """Actual mesh via BMesh, like panels; no object scaling."""
    borda = _malha_modelo_borda() if pux['puxador_tipo'] == 'BORDA' else None
    _normais_da_borda(pux, borda is not None)
    if borda is not None:
        _malha_borda_do_modelo(pux, borda, espessura, comprimento)
        return
    if pux['puxador_tipo'] == 'PERFIL':
        modelo = _malha_modelo_perfil()
        if modelo is not None:
            _malha_perfil_do_modelo(pux, modelo, espessura, comprimento)
            return
    if pux['puxador_tipo'] == 'MODELO':
        modelo = _malha_modelo_usuario(pux.get('puxador_modelo', ''),
                                       carregar=False)
        if modelo is not None:
            _copiar_malha_modelo(pux, modelo)
            return
        if len(pux.data.vertices):
            return      # Library unavailable on another PC: retain the existing copy.
    tipo = pux['puxador_tipo'] if pux['puxador_tipo'] != 'MODELO' else 'ALCA'
    bm = _bmesh_caixas(tipo, espessura, comprimento, pux.parent,
                       pux.get('puxador_borda', 'Y+'),
                       int(pux.get('puxador_face', 1)))
    bm.to_mesh(pux.data)
    bm.free()
    pux.data.update()
    if not pux.data.materials:
        pux.data.materials.append(_material_puxador())


def _bmesh_caixas(tipo, espessura, comprimento, chapa=None, borda='Y+', face=1):
    bm = bmesh.new()
    for x0, x1, y0, y1, z0, z1 in _caixas_puxador(
            tipo, espessura, comprimento or MODELOS_PUXADOR['ALCA'][1]):
        cubo = bmesh.ops.create_cube(bm, size=1.0)
        for v in cubo['verts']:
            v.co = Vector(((x0 + x1) / 2 + v.co.x * (x1 - x0),
                           (y0 + y1) / 2 + v.co.y * (y1 - y0),
                           (z0 + z1) / 2 + v.co.z * (z1 - z0))) / 1000.0
    if tipo == 'PERFIL':
        _acompanhar_borda(bm, chapa, borda, face, comprimento)
    bm.normal_update()
    return bm


def _referencial_da_linha(chapa, borda, face):
    """(along, inward, outward, point, size) in panel LOCAL space.

    `ponto` is the edge midpoint on the face surface; `tamanho` is edge
    length in meters. The vectors form a right-handed basis
    (along = inward x outward), preventing inverted meshes.
    """
    hx, hy, hz = _chapas._meias(chapa)
    sinal = 1.0 if borda.endswith('+') else -1.0
    fora = Vector((0.0, 0.0, 1.0 if face >= 0 else -1.0))
    if borda.startswith('Y'):
        dentro = Vector((0.0, -sinal, 0.0))
        ponto, tamanho = Vector((0.0, sinal * hy, fora.z * hz)), 2 * hx
    else:
        dentro = Vector((-sinal, 0.0, 0.0))
        ponto, tamanho = Vector((sinal * hx, 0.0, fora.z * hz)), 2 * hy
    return dentro.cross(fora), dentro, fora, ponto, tamanho


def _eh_puxador_parametrico(obj):
    return (obj is not None and _chapas.MARCA_PUXADOR in obj
            and obj.get('puxador_tipo') in MODELOS_PUXADOR)


def posicionar_puxador(pux):
    """Rebuild handle mesh and placement from its parent panel.

    Fixed length (profiles span the full edge), centered at the edge
    FRACTION so a centered handle stays centered, with fixed line setback.
    Clamp at both ends so it never extends beyond the edge.
    """
    chapa = pux.parent
    if not _eh_puxador_parametrico(pux) or chapa is None or _chapas.MARCA_CHAPA not in chapa:
        return False
    tipo = pux['puxador_tipo']
    matriz, comprimento = _lugar_do_puxador(
        chapa, tipo, pux.get('puxador_borda', 'Y+'),
        int(pux.get('puxador_face', 1)), float(pux.get('puxador_fracao', 0.5)),
        pux.get('puxador_comprimento_mm'), pux.get('puxador_recuo_mm'))
    if (chapa.get('porta_curva_modelada') and pux.get('puxador_curvo')
            and not chapa.get('porta_linha_frente')
            and (_frentes is None or _frentes.referencia(chapa) is None)):
        # One native local query during placement, never a scene scan
        # during hover. Seat the pull on the actual tangent, not its chord.
        vs=[v.co for v in chapa.data.vertices]
        esquerda=pux.get('puxador_borda')=='X-'
        borda_x=min(v.x for v in vs) if esquerda else max(v.x for v in vs)
        x=borda_x-.1 if esquerda else borda_x+.1
        # Profile with zero setback: a ray at the exact tip grazes and misses wood.
        recuo=max(.001,float(pux.get('puxador_recuo_mm',40))/1000)
        # The tip's Z side comes from ITS vertices, not the frame: when the front
        # faces outward (+Z), the curved tip lies at minimum Z.
        pontas=[v.z for v in vs if abs(v.x-borda_x)<.002]
        if sum(pontas)/len(pontas)>=sum(v.z for v in vs)/len(vs):
            z=max(pontas)-recuo
        else:
            z=min(pontas)+recuo
        y=(float(pux.get('puxador_fracao',.5))-.5)*chapa.chapa_comprimento_mm/1000
        hit,ponto,normal,_f=chapa.ray_cast(Vector((x,y,z)),Vector((1 if esquerda else -1,0,0)))
        if hit:
            ao_longo=Vector((0,1,0))
            dentro=normal.cross(ao_longo).normalized()
            matriz=Matrix((ao_longo,dentro,normal)).transposed().to_4x4()
            matriz.translation=ponto
    _ferragens._padronizar_nome(pux, "Handle " + (
        pux.get('puxador_nome') or MODELOS_PUXADOR[tipo][0]))
    materiais_objeto={i:slot.material for i,slot in enumerate(pux.material_slots)
                      if slot.link=='OBJECT'}
    gerar_malha_puxador(pux, chapa.chapa_espessura_mm, comprimento)
    # Geometry comes from the supplier; this instance's chosen finish belongs
    # to the object and survives rebuilding mesh slots.
    for i,material in materiais_objeto.items():
        if i<len(pux.material_slots):
            pux.material_slots[i].link='OBJECT'
            pux.material_slots[i].material=material
    atualizar_contorno(pux)
    pux.matrix_parent_inverse = Matrix.Identity(4)
    # Euler introduced residual sine at 180 degrees: preview used the exact
    # matrix, but Blender evaluated a different rotation for the part/cache.
    pux.rotation_mode = 'QUATERNION'
    pux.matrix_basis = matriz
    return True


def atualizar_contorno(pux):
    """Tab already edited the actual part; update its wireframe without rebuilding Mesh."""
    if _arame is not None:
        pux['puxador_contorno'] = [float(c) for p in
            _arame._contorno_malha(pux.data) for c in p]


def _atualizar_madeira(chapa):
    """Modeled wood retains its vertices when changing handles."""
    if (not _chapas._malha_e_caixa(chapa.data)
            and not any(chapa.get(chave) for chave in
                        ('chapa_arco_mm', 'chapa_quadro_mm', 'chapa_canais'))):
        for filho in chapa.children:
            if _eh_puxador_parametrico(filho):
                posicionar_puxador(filho)
        return
    _chapas.gerar_malha_chapa(chapa)


def _lugar_do_puxador(chapa, tipo, borda, face, fracao, comprimento=None,
                      recuo=None):
    """(matrix in panel LOCAL space, length in mm) for a handle on that edge;
    use the SAME calculation for object and preview."""
    # Preview receives a SEGMENT key; the object already stores a normalized
    # edge. Without this, hover interpreted Y+|3 as Y-.
    borda, fracao = _borda_e_fracao(chapa, borda, fracao)
    if _frentes is not None and _frentes.referencia(chapa) is not None:
        return _frentes.lugar(
            chapa, borda, face, fracao,
            float(MODELOS_PUXADOR[tipo][1] if comprimento is None else comprimento),
            float(MODELOS_PUXADOR[tipo][2] if recuo is None else recuo),
            inteiro=tipo == 'PERFIL')
    if chapa.get('porta_linha_frente') and (tipo != 'PERFIL' or borda.startswith('X')):
        if tipo == 'PERFIL':
            # The curved leaf's X edge is straight: the profile spans it entirely.
            # Box-based placement landed on the chord, outside the wood.
            comprimento = chapa.chapa_comprimento_mm
        return _lugar_no_perfil(chapa,tipo,borda,face,fracao,comprimento,recuo)
    ao_longo, dentro, fora, ponto, tamanho = _referencial_da_linha(
        chapa, borda, int(face))
    if tipo == 'PERFIL':
        comprimento, x = tamanho * 1000.0, 0.0
    else:
        comprimento = float(MODELOS_PUXADOR[tipo][1] if comprimento is None
                            else comprimento)
        livre = max(0.0, tamanho - comprimento / 1000.0) / 2.0
        x = max(-livre, min(livre, (float(fracao) - 0.5) * tamanho))
    recuo = float(MODELOS_PUXADOR[tipo][2] if recuo is None else recuo) / 1000.0
    matriz = Matrix((ao_longo, dentro, fora)).transposed().to_4x4()
    matriz.translation = ponto + ao_longo * x + dentro * recuo
    return matriz, comprimento


def _lugar_no_perfil(chapa,tipo,borda,face,fracao,comprimento,recuo):
    pontos=[Vector(p) for p in chapa['porta_linha_frente']]
    comprimento=float(MODELOS_PUXADOR[tipo][1] if comprimento is None else comprimento)
    recuo=float(MODELOS_PUXADOR[tipo][2] if recuo is None else recuo)/1000
    sinal=1 if borda.endswith('+') else -1
    total=sum((b-a).length for a,b in zip(pontos,pontos[1:]))
    if borda.startswith('X'):
        if (pontos[0].x-pontos[-1].x)*sinal < 0:pontos.reverse()
        distancia=min(recuo,total)
        ao_longo=Vector((0,sinal,0))
        livre=max(0,(chapa.chapa_comprimento_mm-comprimento)/2000)
        y=sinal*max(-livre,min(livre,(float(fracao)-.5)*chapa.chapa_comprimento_mm/1000))
    else:
        distancia=max(comprimento/2000,min(total-comprimento/2000,float(fracao)*total))
        y=sinal*(chapa.chapa_comprimento_mm/2000-recuo)
        ao_longo=None
    ponto=pontos[-1].copy()
    for a,b in zip(pontos,pontos[1:]):
        d=(b-a).length
        if distancia <= d:
            ponto=a+(b-a)*(distancia/max(d,1e-9));break
        distancia-=d
    ponto.y=y
    # Unprepared legacy data: derive the tangent from its numeric line,
    # never query wood geometry during preview/drawing.
    tangente = (b-a).normalized() if len(pontos) > 1 else Vector((1,0,0))
    if tangente.x < 0:
        tangente = -tangente
    fora = tangente.cross(Vector((0,1,0))).normalized()
    if face < 0:fora=-fora
    if ao_longo is None:
        dentro=Vector((0,-sinal,0));ao_longo=dentro.cross(fora).normalized()
    else:
        dentro=fora.cross(ao_longo).normalized()
    matriz=Matrix((ao_longo,dentro,fora)).transposed().to_4x4()
    matriz.translation=ponto
    return matriz,comprimento


def _rebaixos_da_chapa(chapa):
    """Return {edge: meters} removed from wood by child profiles."""
    return {f.get('puxador_borda', 'Y+'): _altura_perfil_mm() / 1000.0
            for f in chapa.children
            if _eh_puxador_parametrico(f) and f['puxador_tipo'] == 'PERFIL'}


def _conferir_rebaixos():
    """Deleted (X) or moved profiles return their wood to the panel.

    Without this, the cut strip stayed empty until the next dimension
    change. Check only panels with `chapa_rebaixos` to keep it cheap.
    """
    for obj in bpy.data.objects:
        gravado = obj.get('chapa_rebaixos')
        if gravado is None:
            continue
        if set(filter(None, gravado.split(','))) != set(_rebaixos_da_chapa(obj)):
            _atualizar_madeira(obj)


def _dados_do_tipo(pux, tipo, arquivo=''):
    """Store model length/setback on the handle, plus file/name for user models."""
    pux['puxador_tipo'] = tipo
    pux['puxador_comprimento_mm'] = MODELOS_PUXADOR[tipo][1]
    pux['puxador_recuo_mm'] = MODELOS_PUXADOR[tipo][2]
    for chave in ('puxador_modelo', 'puxador_nome'):
        if chave in pux:
            del pux[chave]
    if tipo == 'MODELO':
        modelo = _malha_modelo_usuario(arquivo)
        pux['puxador_modelo'] = arquivo
        pux['puxador_nome'] = nome_do_modelo(tipo, arquivo)
        pux['puxador_comprimento_mm'] = _comprimento_do_modelo(modelo)
        if modelo is not None and 'puxador_recuo_mm' in modelo:
            pux['puxador_recuo_mm'] = float(modelo['puxador_recuo_mm'])


def criar_puxador(context, chapa, tipo, borda, face, fracao=0.5, arquivo=''):
    """Create and place a handle parented to a leaf or loose panel.
    `arquivo` is the user's model .blend for type 'MODELO'."""
    borda,fracao=_borda_e_fracao(chapa,borda,fracao)
    nome = "Handle " + (nome_do_modelo(tipo, arquivo) or "Model")
    pux = bpy.data.objects.new(nome, bpy.data.meshes.new(nome))
    (chapa.users_collection[0] if chapa.users_collection
     else context.collection).objects.link(pux)
    pux[_chapas.MARCA_PUXADOR] = 1
    _dados_do_tipo(pux, tipo, arquivo)
    pux['puxador_borda'] = borda
    pux['puxador_face'] = 1 if face >= 0 else -1
    pux['puxador_fracao'] = max(0.0, min(1.0, float(fracao)))
    if (_frentes is not None and _frentes.referencia(chapa) is not None
            or chapa.get('porta_linha_frente')):
        pux['puxador_referencia_versao'] = 1
    pux.parent = chapa
    if tipo == 'PERFIL':
        # One profile per edge: the new one replaces the old.
        for velho in [f for f in chapa.children if f != pux
                      and _eh_puxador_parametrico(f)
                      and f['puxador_tipo'] == 'PERFIL'
                      and f.get('puxador_borda') == borda]:
            _gavetas._remover(velho)
        _atualizar_madeira(chapa)        # Cut the wood and position the handle.
    else:
        posicionar_puxador(pux)
    return pux


def _borda_na_direcao(folha, direcao, matriz=None):
    """Leaf edge (X-/X+/Y-/Y+) pointing toward world-space `direcao`."""
    rot = (matriz if matriz is not None else folha.matrix_world).to_3x3()
    eixos = {'X+': rot.col[0], 'X-': -rot.col[0],
             'Y+': rot.col[1], 'Y-': -rot.col[1]}
    return max(eixos, key=lambda b: eixos[b].normalized().dot(direcao))


def puxador_terminal(context, grupo):
    """Keep an articulated door's handle at the free end as leaf count changes."""
    folhas = _portas._folhas_portas(grupo)
    if not folhas:
        return None
    terminal = folhas[-1]
    p = grupo.get('porta_parametros') or {}
    puxadores = [pux for f in folhas for pux in f.children if _chapas.MARCA_PUXADOR in pux]
    if not puxadores:
        pux = criar_puxador(context, terminal, 'PERFIL',
            'X-' if p.get('dobradica_lado') == 'DIREITA' else 'X+', 1)
        pux['puxador_zigzag'] = True
        return pux
    antigas = set()
    for pux in puxadores:
        if pux.parent != terminal:
            antigas.add(pux.parent.name)
            pux.parent = terminal
            pux.matrix_parent_inverse = Matrix.Identity(4)
            if pux.get('puxador_zigzag'):
                pux['puxador_borda'] = 'X-' if p.get('dobradica_lado') == 'DIREITA' else 'X+'
            posicionar_puxador(pux)
        elif pux.get('puxador_zigzag'):
            pux['puxador_borda'] = 'X-' if p.get('dobradica_lado') == 'DIREITA' else 'X+'
    for nome in antigas | {terminal.name}:
        _atualizar_madeira(bpy.data.objects[nome])
    return puxadores[0]


ALTURA_MAO_MM = 1000.0     # 'ALTURA': the horizontal edge nearest hand height.


def _borda_lateral_da_folha(grupo, folha, indice, folhas):
    p = dict(grupo.get('porta_parametros') or {})
    fechada = _ferragens._matriz_fechada(folha)
    if p.get('abertura') == 'CORRER':
        centro = grupo.matrix_world.inverted_safe() @ fechada.translation
        sinal = -1 if centro.x <= float(grupo['porta_vao_largura_mm']) / 2000 else 1
        direcao = grupo.matrix_world.to_3x3().col[0].normalized() * sinal
    else:
        lado = _ferragens._lado_da_folha(p, indice, len(folhas))
        direcao = fechada.to_3x3().col[0].normalized() * (1 if lado == 'ESQUERDA' else -1)
    return _borda_na_direcao(folha, direcao, fechada)


def adaptar_abertura(grupo, anterior):
    atual = grupo.get('porta_parametros', {}).get('abertura')
    if {anterior, atual} != {'GIRO', 'CORRER'}:
        return
    folhas = _portas._folhas_portas(grupo)
    for i, folha in enumerate(folhas):
        for pux in folha.children:
            if _eh_puxador_parametrico(pux) and pux.get('puxador_borda') in {'X-', 'X+'}:
                pux['puxador_borda'] = _borda_lateral_da_folha(grupo, folha, i, folhas)


def perfis_na_porta(context, grupo, posicao):
    """One front-face profile per leaf: 'CIMA' for base cabinets, 'BAIXO'
    for wall cabinets, 'ALTURA' for towers (each leaf's upper/lower edge
    nearest 1 m above cabinet base), or 'LADO' for wardrobes only
    (vertical, opposite hinges). Use CLOSED door pose; derive the edge
    from the leaf matrix."""
    modulo = (bpy.data.objects.get(grupo.get(_portas.CHAVE_MODULO_PORTA, ''))
              or grupo.parent or grupo)
    # Loose door: up is its height (Y); group Z is the front and previously
    # produced a vertical profile.
    cima = modulo.matrix_world.to_3x3().col[1 if modulo is grupo else 2].normalized()
    p = dict(grupo.get('porta_parametros') or {})
    if p.get('abertura') == 'ZIGZAG':
        return [puxador_terminal(context, grupo)]
    folhas = _portas._folhas_portas(grupo)
    perfis = []
    for i, folha in enumerate(folhas):
        if posicao == 'CIMA':
            direcao = cima
        elif posicao == 'BAIXO':
            direcao = -cima
        elif posicao == 'ALTURA':
            fechada = _ferragens._matriz_fechada(folha)
            pe = modulo.matrix_world.translation
            alturas = [(fechada @ v.co - pe).dot(cima) * 1000.0 for v in folha.data.vertices]
            perto = (abs(max(alturas) - ALTURA_MAO_MM) < abs(min(alturas) - ALTURA_MAO_MM))
            direcao = cima if perto else -cima
        else:
            borda = _borda_lateral_da_folha(grupo, folha, i, folhas)
        # Native leaf +Z is the front, including on the other L-shaped arm.
        # Comparing against body -Y reversed the perpendicular profile.
        face = 1
        perfis.append(criar_puxador(context, folha, 'PERFIL',
                                    borda if posicao == 'LADO' else _borda_na_direcao(folha, direcao), face))
    return perfis


def _medidas_puxador_parametrico(pux):
    """Dimension-block fields: length and setback, without a lock.

    Profiles have no editable size (full edge, fixed strip): display
    height read-only; an empty property means a disabled field.
    """
    tipo = pux['puxador_tipo']
    if tipo == 'PERFIL':
        return [("Profile height", _altura_perfil_mm(), '')]
    if tipo == 'MODELO':
        # Supplier parts retain their own size: only setback is adjustable.
        return [("Length", float(pux.get('puxador_comprimento_mm', 0.0)), ''),
                ("Inset", float(pux.get('puxador_recuo_mm',
                                        MODELOS_PUXADOR[tipo][2])), 'puxp_recuo')]
    campos = [("Length", float(pux.get('puxador_comprimento_mm',
                                            MODELOS_PUXADOR[tipo][1])),
               'puxp_comprimento')]
    if tipo == 'ALCA':
        campos.append(("Inset", float(pux.get('puxador_recuo_mm',
                                              MODELOS_PUXADOR[tipo][2])),
                       'puxp_recuo'))
    return campos


# ---- Tool: click an edge, choose its point; scroll adds snap subdivisions.
_posicionador_puxador = [None]      # State read by drawing.
_handler_posicionador = [None]
MAXIMO_SNAPS_PUXADOR = 15


def _snaps(n):
    """n line subdivisions: 1=center, 2=thirds, 3=quarters, etc."""
    return [k / (n + 1) for k in range(1, n + 1)]


def _fracao_na_linha(a, b, mouse, n=0):
    """Project mouse onto screen segment a-b; n >= 1 enables snapping."""
    ab = b - a
    if ab.length_squared < 1e-9:
        t = 0.5
    else:
        t = max(0.0, min(1.0, (mouse - a).dot(ab) / ab.length_squared))
    if n >= 1:
        t = min(_snaps(n), key=lambda s: abs(s - t))
    return t


def _texto_fracao(t, n):
    if n >= 1:
        from fractions import Fraction
        f = Fraction(round(t * (n + 1)), n + 1)
        return '%d/%d' % (f.numerator, f.denominator)
    return '%d%%' % round(t * 100)


def _distancia_ao_segmento(p, a, b):
    ab = b - a
    if ab.length_squared < 1e-9:
        return (p - a).length
    t = max(0.0, min(1.0, (p - a).dot(ab) / ab.length_squared))
    return (p - (a + ab * t)).length


def _borda_mais_proxima(segmentos, mouse):
    """Given {edge: (a, b) on screen}, return the edge nearest the mouse."""
    if not segmentos:
        return None
    return min(segmentos, key=lambda b: _distancia_ao_segmento(
        mouse, *segmentos[b]))


def _bordas_da_face(chapa, face):
    """Return {edge: (fraction-0 endpoint, fraction-1 endpoint)} in WORLD space."""
    if _frentes is not None and _frentes.referencia(chapa) is not None:
        bordas = _frentes.bordas(chapa, face)
        # A complete line retains the old public key; keep segments separate
        # when an edge consists of multiple sections.
        for nome in ('Y-', 'Y+'):
            chaves = [c for c in bordas if c.split('|')[0] == nome]
            if len(chaves) == 1 and '|' in chaves[0]:
                bordas[nome] = bordas.pop(chaves[0])
        return bordas
    mundo = chapa.matrix_world
    if chapa.get('porta_linha_frente'):
        ps=[Vector(p) for p in chapa['porta_linha_frente']]
        hy=chapa.chapa_comprimento_mm/2000
        saida={}
        for borda in ('X-','X+'):
            p=min((ps[0],ps[-1]),key=lambda p:p.x) if borda=='X-' else max((ps[0],ps[-1]),key=lambda p:p.x)
            sinal=1 if borda=='X+' else -1
            a,b=p.copy(),p.copy();a.y=-sinal*hy;b.y=sinal*hy
            saida[borda]=(mundo@a,mundo@b)
        for borda in ('Y-','Y+'):
            y=-hy if borda=='Y-' else hy
            for i,(a,b) in enumerate(zip(ps,ps[1:])):
                a,b=a.copy(),b.copy();a.y=y;b.y=y
                saida[borda+'|'+str(i)]=(mundo@a,mundo@b)
        return saida
    bordas = {}
    for borda in BORDAS_CHAPA:
        ao_longo, _dentro, _fora, ponto, tamanho = _referencial_da_linha(
            chapa, borda, face)
        meio = ao_longo * (tamanho / 2.0)
        bordas[borda] = (mundo @ (ponto - meio), mundo @ (ponto + meio))
    return bordas


def _borda_e_fracao(chapa,borda,fracao):
    if _frentes is not None and _frentes.referencia(chapa) is not None:
        return _frentes.normalizar_borda(chapa, borda, fracao)
    if '|' not in borda:
        return borda,fracao
    nome,indice=borda.split('|');indice=int(indice)
    ps=[Vector(p) for p in chapa['porta_linha_frente']]
    ds=[(b-a).length for a,b in zip(ps,ps[1:])]
    return nome,(sum(ds[:indice])+ds[indice]*fracao)/max(sum(ds),1e-9)


def _face_da_chapa(chapa, normal, direcao_vista):
    """+1 front / -1 rear. For a narrow-face hit, use the broad face
    most oriented toward the viewer."""
    eixo_z = chapa.matrix_world.to_3x3().col[2].normalized()
    local = chapa.matrix_world.to_3x3().inverted() @ normal
    if abs(local.z) >= max(abs(local.x), abs(local.y)):
        return 1 if local.z >= 0 else -1
    return 1 if eixo_z.dot(-direcao_vista) >= 0 else -1


def _quad_2d(a, b, largura):
    """Thick line built from triangles; drivers can clamp line_width to 1 px."""
    d = b - a
    if d.length < 1e-6:
        return []
    n = Vector((-d.y, d.x)).normalized() * (largura / 2.0)
    return [a + n, b + n, b - n, a + n, b - n, a - n]


def _desenhar_posicionador_puxador():
    estado = _posicionador_puxador[0]
    context = bpy.context
    if (estado is None or context.region is None
            or context.region.as_pointer() != estado['regiao']):
        return
    rv3d = context.region_data
    projetar = lambda p: view3d_utils.location_3d_to_region_2d(
        context.region, rv3d, p)
    escala = max(1.0, context.preferences.system.ui_scale)
    cor = _hud._cor_linhas_hud(context)
    realce = _hud._cor_realce_hud()
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    gpu.state.blend_set('ALPHA')
    shader.bind()
    try:
        escolhida = estado.get('borda')
        for borda, (a, b) in estado.get('segmentos', {}).items():
            a2, b2 = projetar(a), projetar(b)
            if a2 is None or b2 is None:
                continue
            acesa = borda == escolhida
            shader.uniform_float('color', realce if acesa else (*cor[:3], 0.6))
            tris = _quad_2d(a2, b2, (5 if acesa else 2) * escala)
            if acesa and estado['fase'] == 'POSICAO':
                # Snap ticks crossing the line.
                n = estado['n']
                d = (b2 - a2).normalized()
                lado = Vector((-d.y, d.x)) * 9 * escala
                for t in _snaps(n):
                    p = a2.lerp(b2, t)
                    tris += _quad_2d(p - lado, p + lado, 2 * escala)
            if tris:
                batch_for_shader(shader, 'TRIS', {'pos': tris}).draw(shader)
        if estado['fase'] == 'POSICAO' and escolhida in estado.get('segmentos', {}):
            a, b = estado['segmentos'][escolhida]
            ponto = projetar(a.lerp(b, estado['fracao']))
            if ponto is not None:
                texto = _texto_fracao(estado['fracao'], estado['n'])
                if estado['n'] == 0:
                    texto += "  (scroll: snap points)"
                _hud._caixa_texto_hud(ponto.x + 14 * escala, ponto.y + 14 * escala,
                                 texto, 13 * escala, escala)
    finally:
        gpu.state.blend_set('NONE')


class OBJECT_OT_posicionar_puxador(Operator):
    """Click a door/panel edge, then choose a point on it. Scroll up to add
    center, thirds, quarters and further snap subdivisions."""
    bl_idname = "object.cabinet_posicionar_puxador"
    bl_label = "Create Handle"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def invoke(self, context, event):
        alvo = _importacao._viewport_alvo(context)
        if alvo is None:
            self.report({'ERROR'}, "No 3D viewport for placement")
            return {'CANCELLED'}
        self._area, self._regiao, self._rv3d = alvo
        # Profile/edge-handle preview uses the model wireframe: load here,
        # never during drawing.
        _malha_modelo_perfil()
        _malha_modelo_borda()
        _ferragens.malha_parafuso()
        _ferragens._ferragens_selecionadas[0] = None    # Creation ends the previous selection.
        tipo, arquivo = modelo_escolhido(context.scene)
        if tipo == 'MODELO':
            _malha_modelo_usuario(arquivo)      # Preview uses its wireframe.
        if _arame is not None:
            _arame.preparar_modelos(tipo, arquivo)
        self._estado = {'regiao': self._regiao.as_pointer(), 'fase': 'LINHA',
                        'tipo': tipo, 'arquivo': arquivo,
                        'chapa': None, 'face': 1, 'borda': None,
                        'segmentos': {}, 'n': 0, 'fracao': 0.5, 'pux': None}
        selecionados = list(context.selected_objects)
        self._estado['alvo'] = (selecionados[0].name if len(selecionados) == 1
            and _chapas.MARCA_FOLHA in selecionados[0] else '')
        _posicionador_puxador[0] = self._estado
        _eventos._redesenhar_viewports(context)
        if _handler_posicionador[0] is None:
            _handler_posicionador[0] = bpy.types.SpaceView3D.draw_handler_add(
                _desenhar_posicionador_puxador, (), 'WINDOW', 'POST_PIXEL')
        self._dica(context)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _dica(self, context):
        if self._estado['fase'] == 'LINHA':
            texto = ("Handle %s: click the EDGE where it will go | Esc cancels"
                     % nome_do_modelo(self._estado['tipo'],
                                      self._estado['arquivo']))
        else:
            texto = ("Choose the point | Scroll: snap points (%d) | Click confirms | Right mouse button: another edge" % self._estado['n'])
        self._area.header_text_set(texto)
        self._area.tag_redraw()

    def _mouse(self, event):
        return Vector((event.mouse_x - self._regiao.x,
                       event.mouse_y - self._regiao.y))

    def _projetados(self):
        projetar = lambda p: view3d_utils.location_3d_to_region_2d(
            self._regiao, self._rv3d, p)
        return {b: (projetar(a), projetar(c))
                for b, (a, c) in self._estado['segmentos'].items()
                if projetar(a) is not None and projetar(c) is not None}

    def _procurar_linha(self, context, mouse):
        estado = self._estado
        origem = view3d_utils.region_2d_to_origin_3d(self._regiao, self._rv3d, mouse)
        direcao = view3d_utils.region_2d_to_vector_3d(self._regiao, self._rv3d, mouse)
        alvo = bpy.data.objects.get(estado.get('alvo', ''))
        chapa = None
        with context.temp_override(area=self._area, region=self._regiao):
            if estado.get('alvo'):
                if (alvo is not None and alvo.visible_get(view_layer=context.view_layer,
                        viewport=self._area.spaces.active) and not alvo.hide_select):
                    mundo = alvo.matrix_world
                    inversa = mundo.inverted_safe()
                    acertou, _p, normal, _f = alvo.ray_cast(inversa @ origem,
                        inversa.to_3x3() @ direcao,
                        depsgraph=context.evaluated_depsgraph_get())
                    if acertou:
                        chapa = alvo
                        normal = (inversa.to_3x3().transposed() @ normal).normalized()
            else:
                acerto = _hud._raio_cru(bpy.context, mouse)
                if acerto:
                    chapa, _p, normal, _f, _m = acerto
        if chapa is not None and _chapas.MARCA_PUXADOR in chapa:
            chapa = chapa.parent        # Aimed at a handle: use its panel.
        if chapa is None or _chapas.MARCA_CHAPA not in chapa or chapa.hide_select:
            estado.update(chapa=None, borda=None, segmentos={}, arame=[],
                          chave_arame=None)
            return
        estado['chapa'] = chapa.name
        estado['face'] = _face_da_chapa(chapa, normal, direcao)
        estado['segmentos'] = _bordas_da_face(chapa, estado['face'])
        projetados = self._projetados()
        estado['borda'] = _borda_mais_proxima(projetados, mouse)
        if estado['borda'] in projetados:
            # The handle wireframe preview follows the mouse along the line.
            estado['fracao'] = _fracao_na_linha(
                *projetados[estado['borda']], mouse, estado['n'])
        self._preparar_arame()

    def _preparar_arame(self):
        estado = self._estado
        chapa = bpy.data.objects.get(estado.get('chapa') or '')
        if _arame is None or chapa is None or estado.get('borda') is None:
            estado['arame'] = []
            estado['chave_arame'] = None
            return
        chave = (chapa.name, estado['tipo'], estado['arquivo'],
                 estado['borda'], estado['face'],
                 None if estado['tipo'] == 'PERFIL' else estado['fracao'],
                 tuple(v for linha in chapa.matrix_world for v in linha),
                 (chapa.data.get(_frentes.CHAVE) or {}).get('digital')
                 if _frentes is not None else None)
        if estado.get('chave_arame') != chave:
            estado['arame'] = _arame.preparar_previa(
                chapa, estado['tipo'], estado['borda'], estado['face'],
                estado['fracao'], estado['arquivo'])
            estado['chave_arame'] = chave

    def _mover_puxador(self, mouse):
        estado = self._estado
        a, b = self._projetados().get(estado['borda'], (None, None))
        if a is None:
            return
        estado['fracao'] = _fracao_na_linha(a, b, mouse, estado['n'])
        pux = bpy.data.objects.get(estado['pux'] or '')
        if pux is not None:
            chapa=bpy.data.objects.get(estado['chapa'])
            _borda,fracao=_borda_e_fracao(chapa,estado['borda'],estado['fracao'])
            pux['puxador_fracao'] = fracao
            posicionar_puxador(pux)

    def _apagar_previa(self):
        pux = bpy.data.objects.get(self._estado['pux'] or '')
        if pux is not None:
            malha = pux.data
            bpy.data.objects.remove(pux, do_unlink=True)
            if malha.users == 0:
                bpy.data.meshes.remove(malha)
        self._estado['pux'] = None

    def _encerrar(self):
        _posicionador_puxador[0] = None
        for area in bpy.context.screen.areas if bpy.context.screen else ():
            if area.type == 'VIEW_3D':
                area.tag_redraw()
        if _handler_posicionador[0] is not None:
            bpy.types.SpaceView3D.draw_handler_remove(
                _handler_posicionador[0], 'WINDOW')
            _handler_posicionador[0] = None
        self._area.header_text_set(None)
        self._area.tag_redraw()

    def cancel(self, context):
        self._apagar_previa()
        self._encerrar()

    def _confirmar(self, context, pux):
        for obj in context.selected_objects:
            obj.select_set(False)
        pux.select_set(True)
        context.view_layer.objects.active = pux
        self._encerrar()
        return {'FINISHED'}

    def _trocar_modelo(self, context, valor):
        """Model chosen in the sidebar during placement: rebuild an existing
        preview at the same point. Profiles cover the full edge and are
        therefore ready immediately."""
        estado = self._estado
        tipo, arquivo = modelo_do_valor(valor)
        if (tipo not in MODELOS_PUXADOR
                or (tipo, arquivo) == (estado['tipo'], estado['arquivo'])):
            return None
        estado['tipo'], estado['arquivo'] = tipo, arquivo
        escolher_modelo(context.scene, tipo, arquivo)   # Next creation uses the same choice.
        if tipo == 'MODELO':
            _malha_modelo_usuario(arquivo)
        self._preparar_arame()
        chapa = bpy.data.objects.get(estado['chapa'] or '')
        if estado['fase'] == 'POSICAO' and chapa is not None:
            self._apagar_previa()
            pux = criar_puxador(context, chapa, tipo, estado['borda'],
                                estado['face'], estado['fracao'], arquivo)
            if tipo == 'PERFIL':
                return self._confirmar(context, pux)
            estado['pux'] = pux.name
        self._dica(context)
        _eventos._redesenhar_viewports(context)
        return None

    def modal(self, context, event):
        estado = self._estado
        if (event.type == 'LEFTMOUSE' and event.value == 'RELEASE'
                and getattr(self, '_engolir_soltar', False)):
            self._engolir_soltar = False     # Release of the sidebar click.
            return {'RUNNING_MODAL'}
        gaveta = (_gaveta_eventos._gaveta_sob_evento(context, event)
                  if event.type != 'ESC' else None)
        if gaveta is not None:
            # The sidebar owns its mouse; placement handles only the model choice.
            if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
                acao = _gaveta_eventos._acao_da_gaveta(context, event, *gaveta)
                if (acao and acao[0] == 'escolha' and len(acao) > 5
                        and acao[5] == _portas.ALVO_ASSISTENTE):
                    self._engolir_soltar = True
                    return (self._trocar_modelo(context, acao[2])
                            or {'RUNNING_MODAL'})
            return {'PASS_THROUGH'}
        rolagem = event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}
        if (event.type in {'MIDDLEMOUSE', 'TRACKPADPAN', 'TRACKPADZOOM'}
                or event.type.startswith('NDOF')
                or (rolagem and estado['fase'] == 'LINHA')):
            return {'PASS_THROUGH'}        # Orbit/zoom remain available.
        mouse = self._mouse(event)
        if event.type == 'MOUSEMOVE':
            if estado['fase'] == 'LINHA':
                self._procurar_linha(context, mouse)
            else:
                self._mover_puxador(mouse)
            self._area.tag_redraw()
            return {'RUNNING_MODAL'}
        if rolagem and event.value == 'PRESS':
            passo = 1 if event.type == 'WHEELUPMOUSE' else -1
            estado['n'] = max(0, min(MAXIMO_SNAPS_PUXADOR, estado['n'] + passo))
            self._mover_puxador(mouse)
            self._dica(context)
            return {'RUNNING_MODAL'}
        if event.type == 'ESC' and event.value == 'PRESS':
            self.cancel(context)
            return {'CANCELLED'}
        if event.type == 'RIGHTMOUSE' and event.value == 'PRESS':
            if estado['fase'] == 'POSICAO':
                self._apagar_previa()
                estado['fase'] = 'LINHA'
                self._dica(context)
                return {'RUNNING_MODAL'}
            self.cancel(context)
            return {'CANCELLED'}
        if event.type != 'LEFTMOUSE' or event.value != 'PRESS':
            return {'RUNNING_MODAL'}
        if estado['fase'] == 'POSICAO':
            pux = bpy.data.objects.get(estado['pux'] or '')
            return self._confirmar(context, pux) if pux else {'RUNNING_MODAL'}
        self._procurar_linha(context, mouse)
        chapa = bpy.data.objects.get(estado['chapa'] or '')
        if chapa is None or estado['borda'] is None:
            return {'RUNNING_MODAL'}
        a, b = self._projetados()[estado['borda']]
        estado['fracao'] = _fracao_na_linha(a, b, mouse, estado['n'])
        pux = criar_puxador(context, chapa, estado['tipo'], estado['borda'],
                            estado['face'], estado['fracao'], estado['arquivo'])
        if estado['tipo'] == 'PERFIL':
            return self._confirmar(context, pux)    # Full edge: done.
        estado['pux'] = pux.name
        estado['fase'] = 'POSICAO'
        self._dica(context)
        return {'RUNNING_MODAL'}


def _trocar_modelo_puxador(pux, valor):
    """Sidebar model change for a SELECTED handle: rebuild at the same edge
    and point. Profiles cut wood through panel rebuilding and remain
    one per edge, as in `criar_puxador`."""
    tipo, arquivo = modelo_do_valor(valor)
    if not _eh_puxador_parametrico(pux) or tipo not in MODELOS_PUXADOR:
        return
    antes = pux['puxador_tipo']
    chapa = pux.parent
    if ((antes, pux.get('puxador_modelo', '')) == (tipo, arquivo)
            or chapa is None or _chapas.MARCA_CHAPA not in chapa):
        return
    _dados_do_tipo(pux, tipo, arquivo)
    gaveta = _gavetas.gaveta_de(pux)
    if gaveta is not None:
        gaveta[_gavetas.CHAVE_PUXADOR] = valor
    # Do not carry the user's aluminum-profile material onto the box fallback.
    pux.data.materials.clear()
    if tipo == 'PERFIL':
        for velho in [f for f in chapa.children if f != pux
                      and _eh_puxador_parametrico(f)
                      and f['puxador_tipo'] == 'PERFIL'
                      and f.get('puxador_borda') == pux.get('puxador_borda')]:
            _gavetas._remover(velho)
    if 'PERFIL' in (antes, tipo):
        _atualizar_madeira(chapa)        # Cut/restore wood and position.
    else:
        posicionar_puxador(pux)


# ---- Handle: Alt-drag its anchor to another edge of the same GROUP.
# Limit targets to its owning panels: door leaves or cabinet panels.
# LINE snapping picks the nearest mouse edge on the viewer-facing
# surface and orients the handle accordingly (`_referencial_da_linha`),
# just as placement would there.
_arraste_puxador = [None]    # {'puxador', 'linhas': [(a, b) world], 'escolhida'}.


def _chapas_do_grupo_do_puxador(chapa):
    grupo = _portas._grupo_portas(chapa)
    if grupo is not None:
        return _portas._folhas_portas(grupo)
    modulo = _portas._modulo_da_chapa(chapa)
    if modulo is not None:
        return _modulos._chapas_do_conjunto(modulo)
    return _modulos.grupo_de(chapa) or [chapa]


def _puxadores_com_ancora(context):
    """Selected add-on handles, directly or through selected panels/leaves:
    those displaying an Alt anchor."""
    saida = []
    for o in getattr(context, 'selected_objects', ()) or ():
        for p in ([o] if _eh_puxador_parametrico(o) else o.children):
            if (_eh_puxador_parametrico(p) and p not in saida
                    and p.parent is not None and _chapas.MARCA_CHAPA in p.parent):
                saida.append(p)
    return saida


def _ancora_do_puxador(pux):
    """Handle anchor point ON the edge, in world space."""
    matriz, _c = _lugar_do_puxador(
        pux.parent, pux['puxador_tipo'], pux.get('puxador_borda', 'Y+'),
        int(pux.get('puxador_face', 1)), float(pux.get('puxador_fracao', 0.5)),
        pux.get('puxador_comprimento_mm'), 0.0)
    return pux.parent.matrix_world @ matriz.translation


def _puxador_sob_mouse(context, posicao):
    """Handle with its anchor under the mouse, only with Alt, or None."""
    if not _solda._correntes_visiveis():
        return None
    raio = _solda.RAIO_BOLINHA_PX * max(1.0, context.preferences.system.ui_scale)
    mouse = Vector(posicao)
    melhor = None
    for pux in _puxadores_com_ancora(context):
        ponto = _hud._projetar_hud(context, _ancora_do_puxador(pux))
        if ponto is not None and (ponto - mouse).length <= raio and (
                melhor is None or (ponto - mouse).length < melhor[0]):
            melhor = ((ponto - mouse).length, pux)
    return melhor[1] if melhor else None


def _desenhar_ancoras_puxador(context):
    """Alt displays a white dot at each selected handle's anchor. During
    drag, show group edges, highlight the chosen one, and show the anchor."""
    arraste = _arraste_puxador[0]
    puxadores = ([] if arraste is not None or not _solda._correntes_visiveis()
                 else _puxadores_com_ancora(context))
    if arraste is None and not puxadores:
        return
    escala = max(1.0, context.preferences.system.ui_scale)
    realce, cor = _hud._cor_realce_hud(), _hud._cor_linhas_hud(context)
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    gpu.state.blend_set('ALPHA')
    try:
        shader.bind()
        if arraste is not None:
            for i, (a, b) in enumerate(arraste['linhas']):
                a2, b2 = _hud._projetar_hud(context, a), _hud._projetar_hud(context, b)
                if a2 is None or b2 is None:
                    continue
                acesa = i == arraste['escolhida']
                shader.uniform_float('color', realce if acesa
                                     else (*cor[:3], 0.6))
                tris = _quad_2d(a2, b2, (5 if acesa else 2) * escala)
                if tris:
                    batch_for_shader(shader, 'TRIS', {'pos': tris}).draw(shader)
            pux = bpy.data.objects.get(arraste['puxador'])
            if _eh_puxador_parametrico(pux) and pux.parent is not None:
                puxadores = [pux]
        for pux in puxadores:
            ponto = _hud._projetar_hud(context, _ancora_do_puxador(pux))
            if ponto is None:
                continue
            if arraste is not None:
                _hud._bolinha_2d(shader, ponto, 8 * escala, realce)
            _hud._bolinha_2d(shader, ponto, (6 if arraste else 5) * escala,
                        (1.0, 1.0, 1.0, 1.0))
    finally:
        gpu.state.blend_set('NONE')


def _destino_ocupado(pux, chapa, borda, face, fracao):
    # Actual placement already clamps pulls at the ends; different fractions may coincide.
    matriz, comprimento = _lugar_do_puxador(chapa, pux['puxador_tipo'], borda, face,
        fracao, pux.get('puxador_comprimento_mm'), 0.0)
    for outro in chapa.children:
        if (outro == pux or not _eh_puxador_parametrico(outro)
                or int(outro.get('puxador_face', 1)) != face):
            continue
        outra_borda, outra_fracao = _borda_e_fracao(chapa,
            outro.get('puxador_borda', 'Y+'), float(outro.get('puxador_fracao', .5)))
        lugar, tamanho = _lugar_do_puxador(chapa, outro['puxador_tipo'], outra_borda,
            face, outra_fracao, outro.get('puxador_comprimento_mm'), 0.0)
        distancia = (matriz.translation - lugar.translation).length
        if (distancia < .0001 or borda == outra_borda
                and distancia < (comprimento + tamanho) / 2000.0 - .000001):
            return True
    return False


class OBJECT_OT_arrastar_puxador(Operator):
    """Alt-drag a handle anchor to another edge in the same group; it snaps to and follows that line."""
    bl_idname = 'object.cabinet_arrastar_puxador'
    bl_label = "Move Handle"
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}

    puxador: StringProperty(options={'SKIP_SAVE'})

    def invoke(self, context, event):
        pux = bpy.data.objects.get(self.puxador)
        if (not _eh_puxador_parametrico(pux) or pux.parent is None
                or _chapas.MARCA_CHAPA not in pux.parent or context.region is None
                or context.region_data is None):
            return {'CANCELLED'}
        self._antes = (pux.parent.name, pux.get('puxador_borda', 'Y+'),
                       int(pux.get('puxador_face', 1)),
                       float(pux.get('puxador_fracao', 0.5)))
        self._chapas = [c.name for c in
                        _chapas_do_grupo_do_puxador(pux.parent)]
        _arraste_puxador[0] = {'puxador': pux.name, 'linhas': [],
                               'escolhida': None}
        self._area = context.area
        context.window_manager.modal_handler_add(self)
        self._area.tag_redraw()
        return {'RUNNING_MODAL'}

    def _linha_sob_mouse(self, context, mouse):
        """(panel, edge, face, fraction) for the group edge nearest the mouse,
        on the viewer-facing surface."""
        estado = _arraste_puxador[0]
        regiao, rv3d = context.region, context.region_data
        direcao = view3d_utils.region_2d_to_vector_3d(regiao, rv3d, mouse)
        linhas, melhor = [], None
        for nome in self._chapas:
            chapa = bpy.data.objects.get(nome)
            if chapa is None:
                continue
            eixo_z = chapa.matrix_world.to_3x3().col[2].normalized()
            face = 1 if eixo_z.dot(-direcao) >= 0 else -1
            for borda, (a, b) in _bordas_da_face(chapa, face).items():
                a2 = view3d_utils.location_3d_to_region_2d(regiao, rv3d, a)
                b2 = view3d_utils.location_3d_to_region_2d(regiao, rv3d, b)
                if a2 is None or b2 is None:
                    continue
                linhas.append((a, b))
                d = _distancia_ao_segmento(mouse, a2, b2)
                if melhor is None or d < melhor[0]:
                    nome_borda,fracao=_borda_e_fracao(chapa,borda,_fracao_na_linha(a2,b2,mouse))
                    melhor = (d, len(linhas) - 1, nome, nome_borda, face,fracao)
        estado['linhas'] = linhas
        estado['escolhida'] = melhor[1] if melhor else None
        return melhor[2:] if melhor else None

    def _aplicar(self, context, nome, borda, face, fracao, validar=True):
        pux = bpy.data.objects.get(self.puxador)
        chapa = bpy.data.objects.get(nome)
        if pux is None or chapa is None:
            return False
        borda, fracao = _borda_e_fracao(chapa, borda, fracao)
        fracao = max(0.0, min(1.0, float(fracao)))
        if validar and _destino_ocupado(pux, chapa, borda, face, fracao):
            return False
        antiga = pux.parent
        mesma_linha = (antiga == chapa and pux.get('puxador_borda') == borda
                       and int(pux.get('puxador_face', 1)) == face)
        if mesma_linha and abs(float(pux.get('puxador_fracao', 0.5))
                               - fracao) < 1e-4:
            return True
        if antiga != chapa:
            pux.parent = chapa
        pux['puxador_borda'] = borda
        pux['puxador_face'] = face
        pux['puxador_fracao'] = max(0.0, min(1.0, float(fracao)))
        if pux['puxador_tipo'] == 'PERFIL':
            if not mesma_linha:
                # Restore wood on the old panel and remove it on the new one.
                if antiga is not None and antiga != chapa:
                    _atualizar_madeira(antiga)
                _atualizar_madeira(chapa)
            else:
                posicionar_puxador(pux)
        else:
            posicionar_puxador(pux)
        context.view_layer.update()
        return True

    def _encerrar(self):
        _arraste_puxador[0] = None
        self._area.header_text_set(None)
        self._area.tag_redraw()

    def cancel(self, context):
        self._aplicar(context, *self._antes, validar=False)
        self._encerrar()

    def modal(self, context, event):
        if _arraste_puxador[0] is None:
            return {'CANCELLED'}
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            self.cancel(context)
            return {'CANCELLED'}
        if event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            return {'PASS_THROUGH'}
        if event.type == 'MOUSEMOVE':
            achado = self._linha_sob_mouse(
                context, Vector((event.mouse_region_x, event.mouse_region_y)))
            if achado is not None:
                aplicado = self._aplicar(context, *achado)
                self._area.header_text_set(None if aplicado else "This position is already occupied by another handle")
            self._area.tag_redraw()
            return {'RUNNING_MODAL'}
        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            self._encerrar()
            return {'FINISHED'}
        return {'RUNNING_MODAL'}


# ---- Use as handle: turn an external object into a library MODEL
# in Puxadores, with a 45-degree photo, and add it to the creator carousel.
# If it touches an add-on panel, attach it immediately at its existing
# edge/point. Otherwise ask the user to click the door-contact face
# and open the creator with that model.
DISTANCIA_ENCOSTADO_MM = 5.0
RECUO_MINIMO_MODELO_MM = 40.0
MARCA_MODELO_PUXADOR = 'eh_modelo_puxador'
_usando_como_puxador = [None]     # {'objeto': name}, awaiting a click.


def _eh_objeto_de_fora(obj):
    return (obj is not None and obj.type == 'MESH' and not any(
        m in obj for m in (_chapas.MARCA_CHAPA, _chapas.MARCA_CONJUNTO,
                           _chapas.MARCA_PORTAS, _chapas.MARCA_FOLHA,
                           _chapas.MARCA_PUXADOR, _chapas.MARCA_ACESSORIO,
                           _ferragens.CHAVE_FERRAGEM)))


def _pontos_mundo(obj, depsgraph):
    avaliado = obj.evaluated_get(depsgraph)
    malha = avaliado.to_mesh()
    try:
        return [obj.matrix_world @ v.co for v in malha.vertices]
    finally:
        avaliado.to_mesh_clear()


def _quadro_do_modelo(pontos, fora, ao_longo=None):
    """Model frame (WORLD matrix): Z=`fora` from door toward handle, X along
    the edge, origin at the contact-face center anchor. Without `ao_longo`,
    use the part's longest direction for X, since bars/pulls follow the edge."""
    fora = fora.normalized()
    if ao_longo is None:
        u = fora.orthogonal().normalized()
        v = fora.cross(u)

        def extensao(d):
            valores = [p.dot(d) for p in pontos]
            return max(valores) - min(valores)
        ao_longo = max((u * math.cos(math.radians(a)) + v * math.sin(math.radians(a))
                        for a in range(0, 180, 15)), key=extensao)
    x = (ao_longo - fora * ao_longo.dot(fora)).normalized()
    y = fora.cross(x)
    meio = [(min(vs) + max(vs)) / 2.0 for vs in
            ([p.dot(x) for p in pontos], [p.dot(y) for p in pontos])]
    quadro = Matrix((x, y, fora)).transposed().to_4x4()
    quadro.translation = (x * meio[0] + y * meio[1]
                          + fora * min(p.dot(fora) for p in pontos))
    return quadro


def _chapa_encostada(context, pontos):
    """Return (panel, face, edge) of the add-on panel touching the part,
    with face distance <= DISTANCIA_ENCOSTADO_MM and part center inside
    the panel. Choose the nearest edge; return None for a loose part."""
    centro = sum(pontos, Vector()) / len(pontos)
    tolerancia = DISTANCIA_ENCOSTADO_MM / 1000.0
    melhor = None
    for chapa in context.scene.objects:
        if _chapas.MARCA_CHAPA not in chapa:
            continue
        inversa = chapa.matrix_world.inverted_safe()
        if _frentes is not None and _frentes.referencia(chapa) is not None:
            # Native query during conversion only, never redraw:
            # a bounding box does not represent a curved front's surface.
            c = inversa @ centro
            acertou, contato, normal, _indice = chapa.closest_point_on_mesh(c)
            if not acertou:
                continue
            normal.normalize()
            tangencial = c-contato
            tangencial -= normal*tangencial.dot(normal)
            if tangencial.length > tolerancia:
                continue
            folga = min((inversa @ p-contato).dot(normal) for p in pontos)
            if not -tolerancia <= folga <= tolerancia:
                continue
            face = 1 if normal.z >= 0 else -1
            bordas = _frentes.bordas(chapa, face)
            if not bordas:
                continue
            chave = min(bordas, key=lambda b: _distancia_ao_segmento(
                centro, *bordas[b]))
            borda, _fracao = _frentes.normalizar_borda(chapa, chave, .5)
            if melhor is None or abs(folga) < melhor[0]:
                melhor = (abs(folga), chapa, face, borda)
            continue
        hx, hy, hz = _chapas._meias(chapa)
        c = inversa @ centro
        if abs(c.x) > hx or abs(c.y) > hy:
            continue
        zs = [(inversa @ p).z for p in pontos]
        for face, folga in ((1, min(zs) - hz), (-1, -hz - max(zs))):
            if -tolerancia <= folga <= tolerancia and (
                    melhor is None or abs(folga) < melhor[0]):
                bordas = {'X+': hx - c.x, 'X-': hx + c.x,
                          'Y+': hy - c.y, 'Y-': hy + c.y}
                melhor = (abs(folga), chapa, face, min(bordas, key=bordas.get))
    return melhor[1:] if melhor else None


def _nome_livre_modelo(nome):
    """Name without `.001` that does not overwrite another library model."""
    pasta = _biblioteca.pasta_biblioteca()
    base = _portas._sem_sufixo(nome).strip() or "Handle"
    nome, n = base, 2
    while os.path.exists(os.path.join(
            pasta, _biblioteca._nome_arquivo_seguro(nome) + '.blend')):
        nome, n = '%s %d' % (base, n), n + 1
    return nome


def _ancora_na_referencia(chapa, borda, face, ponto):
    """Fraction follows the shared projection; setback retains mm units."""
    fracao = _frentes.fracao_do_ponto(chapa, borda, face, ponto)
    if borda.startswith('Y'):
        quadro, _ = _frentes.lugar(chapa, borda, face, fracao, 0, 0)
        recuo = (ponto-quadro.translation).dot(quadro.to_3x3().col[1])*1000
    else:
        # X: setback follows the entire front rather than the end tangent.
        percurso = _frentes.fracao_do_ponto(chapa, 'Y-', face, ponto)
        _, comprimento = _frentes.lugar(chapa, 'Y-', face, .5, 0, 0, inteiro=True)
        recuo = (1-percurso if borda == 'X+' else percurso)*comprimento
    return fracao, recuo


def salvar_modelo_puxador(context, obj, quadro, recuo_mm):
    """Save to Puxadores in model coordinates with a 45-degree photo; return
    the file. A photo is required for registration, as in the library;
    raise RuntimeError with the reason if it fails."""
    nome = _nome_livre_modelo(obj.name)
    malha = bpy.data.meshes.new_from_object(
        obj.evaluated_get(context.evaluated_depsgraph_get()))
    malha.transform(quadro.inverted() @ obj.matrix_world)
    malha.name = nome
    malha['puxador_recuo_mm'] = round(float(recuo_mm), 3)
    temporario = bpy.data.objects.new(nome, malha)
    temporario[MARCA_MODELO_PUXADOR] = 1
    context.scene.collection.objects.link(temporario)
    pasta = _biblioteca.pasta_biblioteca()
    niveis = (CATEGORIA_PUXADORES, SUBCATEGORIA_MODELO, '')
    try:
        arquivo = _biblioteca.salvar_na_biblioteca([temporario], nome, False,
                                                   niveis=niveis)
        png = os.path.splitext(arquivo)[0] + '.png'
        ok, msg = _biblioteca.capturar_viewport(
            png, None, isolar=[temporario], rotacao=_biblioteca.VISTA_FOTO)
        if not ok:
            os.remove(arquivo)
            raise RuntimeError("Required photo failed: " + msg)
        _biblioteca.aplicar_preview_png(arquivo, png)
        _biblioteca.registrar_no_indice(pasta, nome, arquivo, *niveis, 'objeto')
    finally:
        bpy.data.objects.remove(temporario, do_unlink=True)
        bpy.data.meshes.remove(malha)
    return os.path.basename(arquivo)


class OBJECT_OT_usar_como_puxador(Operator):
    """Convert an object into a library handle model in Puxadores; if touching a door, attach it immediately."""
    bl_idname = 'object.cabinet_usar_como_puxador'
    bl_label = "Use as Handle"
    bl_options = {'REGISTER', 'UNDO'}

    # Known door-contact face normal in WORLD space for F3/tests.
    normal: FloatVectorProperty(size=3, options={'SKIP_SAVE', 'HIDDEN'})

    @classmethod
    def poll(cls, context):
        obj = context.object
        return (context.mode == 'OBJECT' and _eh_objeto_de_fora(obj)
                and obj.select_get())

    def invoke(self, context, event):
        obj = context.object
        pontos = _pontos_mundo(obj, context.evaluated_depsgraph_get())
        if not pontos:
            self.report({'WARNING'}, "The object has no vertices")
            return {'CANCELLED'}
        if (_chapa_encostada(context, pontos) is not None
                or Vector(self.normal).length > 1e-6):
            return self.execute(context)
        alvo = _importacao._viewport_alvo(context)
        if alvo is None:
            self.report({'ERROR'}, "No 3D viewport")
            return {'CANCELLED'}
        self._area, self._regiao, self._rv3d = alvo
        self._objeto = obj.name
        _usando_como_puxador[0] = {'objeto': obj.name}
        self._area.header_text_set(
            "Click the handle face that touches the door | Esc cancels")
        _eventos._redesenhar_viewports(context)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _encerrar(self, context):
        _usando_como_puxador[0] = None
        self._area.header_text_set(None)
        _eventos._redesenhar_viewports(context)

    def cancel(self, context):
        self._encerrar(context)

    def modal(self, context, event):
        if event.type == 'ESC' or (event.type == 'RIGHTMOUSE'
                                   and event.value == 'PRESS'):
            self._encerrar(context)
            return {'CANCELLED'}
        if (event.type != 'LEFTMOUSE' or event.value != 'PRESS'
                or _gaveta_eventos._gaveta_sob_evento(context, event) is not None):
            return {'PASS_THROUGH'}        # Orbit, zoom and sidebar remain available.
        regiao = self._regiao
        mouse = Vector((event.mouse_x - regiao.x, event.mouse_y - regiao.y))
        if not (0 <= mouse.x < regiao.width and 0 <= mouse.y < regiao.height):
            return {'PASS_THROUGH'}
        acertou, _p, normal, _f, alvo, _m = context.scene.ray_cast(
            context.evaluated_depsgraph_get(),
            view3d_utils.region_2d_to_origin_3d(regiao, self._rv3d, mouse),
            view3d_utils.region_2d_to_vector_3d(regiao, self._rv3d, mouse))
        if not acertou or alvo is None or alvo.original.name != self._objeto:
            self.report({'INFO'}, "Click a face on the handle itself")
            return {'RUNNING_MODAL'}
        self.normal = normal
        self._encerrar(context)
        return self.execute(context)

    def execute(self, context):
        obj = bpy.data.objects.get(getattr(self, '_objeto', '')) or context.object
        if not _eh_objeto_de_fora(obj):
            return {'CANCELLED'}
        pontos = _pontos_mundo(obj, context.evaluated_depsgraph_get())
        encostado = _chapa_encostada(context, pontos) if pontos else None
        if encostado is not None:
            chapa, face, borda = encostado
            giro = chapa.matrix_world.to_3x3().normalized()
            inversa = chapa.matrix_world.inverted_safe()
            if _frentes is not None and _frentes.referencia(chapa) is not None:
                centro = inversa @ (sum(pontos, Vector()) / len(pontos))
                fracao, recuo = _ancora_na_referencia(chapa, borda, face, centro)
                linha, _ = _frentes.lugar(chapa, borda, face, fracao, 0, recuo)
                quadro = _quadro_do_modelo(
                    pontos, giro @ linha.to_3x3().col[2],
                    giro @ linha.to_3x3().col[0])
                # The contact-face center may differ from the asset's vertex average;
                # store the anchor that was actually saved.
                fracao, recuo = _ancora_na_referencia(
                    chapa, borda, face, inversa @ quadro.translation)
            else:
                ao_longo, dentro, fora, ponto, tamanho = _referencial_da_linha(
                    chapa, borda, face)
                quadro = _quadro_do_modelo(pontos, giro @ fora, giro @ ao_longo)
                desloc = inversa @ quadro.translation - ponto
                recuo = desloc.dot(dentro) * 1000.0
                fracao = .5 + desloc.dot(ao_longo) / max(tamanho, 1e-9)
        elif Vector(self.normal).length > 1e-6:
            quadro = _quadro_do_modelo(pontos, -Vector(self.normal))
            local = [quadro.inverted() @ p for p in pontos]
            recuo = max(RECUO_MINIMO_MODELO_MM,
                        (max(p.y for p in local) - min(p.y for p in local))
                        * 500.0 + 10.0)
        else:
            self.report({'WARNING'}, "Click the face that touches the door")
            return {'CANCELLED'}
        try:
            arquivo = salvar_modelo_puxador(context, obj, quadro, recuo)
        except (RuntimeError, OSError) as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}
        escolher_modelo(context.scene, 'MODELO', arquivo)
        nome = nome_do_modelo('MODELO', arquivo)
        if encostado is None:
            self.report({'INFO'}, "Model '%s' in the library: click the door edge" % nome)
            if hasattr(self, '_area'):
                # Open the creator directly with the new model selected.
                bpy.ops.object.cabinet_posicionar_puxador('INVOKE_DEFAULT')
            return {'FINISHED'}
        pux = criar_puxador(context, chapa, 'MODELO', borda, face,
                            fracao, arquivo)
        pux['puxador_recuo_mm'] = round(recuo, 3)
        posicionar_puxador(pux)
        malha = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        if malha is not None and malha.users == 0:
            bpy.data.meshes.remove(malha)
        for o in context.selected_objects:
            o.select_set(False)
        pux.select_set(True)
        context.view_layer.objects.active = pux
        self.report({'INFO'}, "Handle '%s' saved to the library and attached to the door" % nome)
        return {'FINISHED'}
