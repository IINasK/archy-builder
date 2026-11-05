"""Importacao: converter objetos de fora em chapa/modulo/puxador/
porta, vincular porta e modulo, definir a frente."""

import os
import math
import unicodedata

import bpy, bmesh
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree
from bpy_extras import view3d_utils
from bpy.types import Operator

# usados so' ao RODAR (import circular): o __init__ liga estes
# apelidos depois de carregar todos (`_ligar_modulos`)
_chapas = _modulos = _portas = _ferragens = _gaveta = _biblioteca = _formas = None
_promob = None
_frentes = None

# ========================================================== IMPORTACAO
# Objetos de fora -- um armario baixado, uma porta modelada, puxadores --
# chegam com qualquer rotacao, escala e origem. O que decide e' a FORMA:
# uma chapa e' uma caixa fina. Daqui saem chapas, modulos, folhas de
# porta, acessorios e puxadores que o resto do add-on ja' sabe tratar.
ESPESSURA_MAXIMA_CHAPA_MM = 40.0   # mais grosso que isto nao e' chapa
PROPORCAO_MINIMA_CHAPA = 3.0       # lados >= 3x a espessura
ENCHIMENTO_MINIMO_CHAPA = 0.85     # area em faces alinhadas a caixa
# ...ou as duas faces grandes: placa com contorno curvo (prateleira de
# cantoneira, travessa em arco), em que a borda redonda tem muita area
FACES_PRINCIPAIS_MINIMO = 0.6
GRUPOS_MAXIMOS_NORMAIS = 64        # peca curva: para de agrupar normais
# Modificadores que nao mudam a forma; os outros (solidify, array...)
# ja' entraram na medida da peca e dobrariam se ficassem.
MODIFICADORES_COSMETICOS = {'BEVEL', 'WEIGHTED_NORMAL', 'EDGE_SPLIT',
                            'TRIANGULATE'}


def _faces_em_mundo(obj):
    """[(normal, area)] e vertices da malha AVALIADA, em mundo."""
    try:
        dep = bpy.context.evaluated_depsgraph_get()
        avaliado = obj.evaluated_get(dep)
    except Exception:
        avaliado = obj
    malha = avaliado.to_mesh()
    try:
        bm = bmesh.new()
        try:
            bm.from_mesh(malha)
            bm.transform(obj.matrix_world)
            bm.normal_update()
            faces = []
            for face in bm.faces:
                area = face.calc_area()
                if area > 1e-12:
                    faces.append((face.normal.copy(), area))
            vertices = [v.co.copy() for v in bm.verts]
        finally:
            bm.free()
    finally:
        avaliado.to_mesh_clear()
    return faces, vertices


def _normais_dominantes(faces):
    """Direcoes de face agrupadas (sem sinal), da com mais area a menor."""
    grupos = []
    for normal, area in faces:
        for grupo in grupos:
            if abs(grupo[0].dot(normal)) > 0.995:
                grupo[1] += area
                break
        else:
            if len(grupos) < GRUPOS_MAXIMOS_NORMAIS:
                grupos.append([normal.normalized(), area])
    return sorted(grupos, key=lambda g: -g[1])


def _analisar_peca(obj, proporcao_minima=PROPORCAO_MINIMA_CHAPA):
    """Caixa orientada da peca e se ela e' uma chapa.

    Devolve {'chapa', 'base', 'dims', 'centro'} ou None. `base` tem as
    colunas X = largura, Y = comprimento, Z = espessura (a convencao da
    chapa); `dims` = (L, C, E) em mm. Os eixos saem da normal com mais
    area -- numa placa, as duas faces grandes -- e da maior face
    perpendicular a ela. Empates (um cubo) ficam com os eixos locais do
    objeto, para uma peca ja' alinhada nao girar a toa.
    """
    if obj is None or obj.type != 'MESH':
        return None
    faces, vertices = _faces_em_mundo(obj)
    if not vertices:
        return None
    m3 = obj.matrix_world.to_3x3()
    local = [m3.col[i].normalized() if m3.col[i].length > 1e-12
             else Vector([float(i == j) for j in range(3)]) for i in range(3)]
    grupos = _normais_dominantes(faces)
    a1 = grupos[0][0] if grupos else local[2]
    a2 = next((g[0] for g in grupos[1:] if abs(g[0].dot(a1)) < 0.02), None)
    if a2 is None:
        # Sem face perpendicular (disco, peca curva): o eixo local mais
        # perpendicular serve de referencia no plano.
        a2 = min(local, key=lambda e: abs(e.dot(a1)))
    a2 = (a2 - a1 * a2.dot(a1)).normalized()
    eixos = [a1, a2, a1.cross(a2).normalized()]
    faixas = []
    for eixo in eixos:
        projecoes = [v.dot(eixo) for v in vertices]
        faixas.append((min(projecoes), max(projecoes)))
    tamanho = [(hi - lo) * 1000.0 for lo, hi in faixas]
    iz = min(range(3), key=lambda i: (round(tamanho[i], 1),
                                      -abs(eixos[i].dot(local[2]))))
    resto = [i for i in range(3) if i != iz]
    ix = max(resto, key=lambda i: abs(eixos[i].dot(local[0])))
    iy = next(i for i in resto if i != ix)
    z = eixos[iz] if eixos[iz].dot(local[2]) >= 0 else -eixos[iz]
    x = eixos[ix] if eixos[ix].dot(local[0]) >= 0 else -eixos[ix]
    y = z.cross(x).normalized()
    centro = sum((eixos[i] * (faixas[i][0] + faixas[i][1]) / 2.0
                  for i in range(3)), Vector())
    L, C, E = tamanho[ix], tamanho[iy], tamanho[iz]
    total = sum(area for _n, area in faces) or 1.0
    alinhada = sum(area for n, area in faces
                   if any(abs(n.dot(e)) > 0.995 for e in eixos))
    principais = grupos[0][1] / total if grupos and iz == 0 else 0.0
    chapa = (0.05 < E <= ESPESSURA_MAXIMA_CHAPA_MM
             and min(L, C) >= proporcao_minima * E
             and (alinhada / total >= ENCHIMENTO_MINIMO_CHAPA
                  or principais >= FACES_PRINCIPAIS_MINIMO))
    return {'chapa': chapa, 'base': Matrix((x, y, z)).transposed(),
            'dims': (L, C, E), 'centro': centro}


def converter_em_chapa(obj, analise=None):
    """Transforma um objeto qualquer em chapa SEM tira-lo do lugar.

    A orientacao vai para a ROTACAO (invariante 1: local Z = espessura),
    a escala volta a 1 e a malha vira a caixa parametrica. Ler
    `obj.dimensions` em eixos de mundo, como antes, transformava uma
    lateral em pe' (18 x 400 x 700) numa chapa de espessura 30.
    """
    analise = analise or _analisar_peca(obj)
    if analise is None:
        return None
    L, C, E = analise['dims']
    pai = obj.parent
    if pai is not None and any(abs(s - 1.0) > 1e-4
                               for s in pai.matrix_world.to_scale()):
        # Pai com escala (FBX costuma vir em 0.01) faria a chapa herdar
        # escala, e a normalizacao a converteria em medida errada.
        mundo = obj.matrix_world.copy()
        obj.parent = None
        obj.matrix_world = mundo
    for mod in list(obj.modifiers):
        if mod.type not in MODIFICADORES_COSMETICOS:
            obj.modifiers.remove(mod)
    if obj.data.shape_keys:
        obj.shape_key_clear()
    if obj.data.users > 1:
        obj.data = obj.data.copy()
    nova = Matrix.LocRotScale(analise['centro'], analise['base'].to_quaternion(),
                              Vector((1.0, 1.0, 1.0)))
    # Os VERTICES vao junto para o referencial novo: a forma fica no mesmo
    # lugar do mundo. Sem isto, a peca recortada (malha preservada) ia para
    # outro lugar, e a caixa girada (porta a 45 graus) nao era reconhecida
    # como caixa.
    obj.data.transform(nova.inverted() @ obj.matrix_world)
    obj.matrix_world = nova
    obj[_chapas.MARCA_CHAPA] = 1
    _chapas._ocupado[0] = True
    try:
        obj.chapa_auto = True
        obj.chapa_largura_mm = max(1.0, L)
        obj.chapa_comprimento_mm = max(1.0, C)
        obj.chapa_espessura_mm = _chapas._espessura_livre(E)
    finally:
        _chapas._ocupado[0] = False
    _chapas.gerar_malha_chapa(obj)
    return analise


def _malhas_soltas(context):
    """Malhas selecionadas que ainda nao sao porta nem puxador."""
    return [o for o in context.selected_objects
            if o.type == 'MESH' and _chapas.MARCA_FOLHA not in o
            and _chapas.MARCA_PUXADOR not in o]


class OBJECT_OT_converter_modulo(Operator):
    """Converte a selecao num modulo: placas viram chapas, o resto acessorio"""
    bl_idname = "object.cabinet_converter_modulo"
    bl_label = "Converter em Modulo"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and bool(_malhas_soltas(context))

    def execute(self, context):
        analises = {}
        for obj in _malhas_soltas(context):
            analise = _analisar_peca(obj)
            if analise is not None:
                analises[obj] = analise
        if not analises:
            self.report({'WARNING'}, "Nenhuma malha com volume na selecao")
            return {'CANCELLED'}
        placas = [o for o, a in analises.items()
                  if a['chapa'] or _chapas.MARCA_CHAPA in o]
        # Regra do usuario: se nada parece chapa, tudo vira chapa.
        if not placas:
            placas = list(analises)
        acessorios = [o for o in analises if o not in placas]
        for obj in placas:
            if _chapas.MARCA_CHAPA not in obj:
                converter_em_chapa(obj, analises[obj])
        context.view_layer.update()
        conj = _modulos.agrupar_chapas(context, placas)
        for obj in acessorios:
            mundo = obj.matrix_world.copy()
            obj.parent = conj
            obj.matrix_parent_inverse = conj.matrix_world.inverted()
            obj.matrix_world = mundo
            obj[_chapas.MARCA_ACESSORIO] = 1
            colecao = _modulos._colecao_do_modulo(conj)
            if colecao is not None:
                _modulos._mover_para_colecao(obj, colecao)
        self.report({'INFO'}, "Modulo com %d chapa(s) e %d acessorio(s)"
                    % (len(placas), len(acessorios)))
        return {'FINISHED'}


# ---------------------------------------------------------- puxadores
class OBJECT_OT_converter_puxador(Operator):
    """Marca os objetos selecionados como puxador, preservando as medidas"""
    bl_idname = "object.cabinet_converter_puxador"
    bl_label = "Converter em Puxador"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and any(
            _chapas.MARCA_CHAPA not in o for o in _malhas_soltas(context))

    def execute(self, context):
        marcados = 0
        for obj in _malhas_soltas(context):
            if _chapas.MARCA_CHAPA in obj:
                continue        # chapa nao vira puxador por engano
            obj[_chapas.MARCA_PUXADOR] = 1
            obj[_chapas.CHAVE_TRAVAS_PUXADOR] = [1, 1, 1]
            marcados += 1
        self.report({'INFO'}, "%d puxador(es); ligue-os a uma porta pela corrente"
                    % marcados)
        return {'FINISHED'}


def _puxadores_e_folhas_da_selecao(context):
    puxadores = [o for o in context.selected_objects if _chapas.MARCA_PUXADOR in o]
    folhas = []
    for obj in context.selected_objects:
        grupo = _portas._grupo_portas(obj)
        if grupo is None:
            continue
        for folha in ([obj] if _chapas.MARCA_FOLHA in obj else _portas._folhas_portas(grupo)):
            if folha not in folhas:
                folhas.append(folha)
    return puxadores, folhas


class OBJECT_OT_vincular_puxador(Operator):
    """Liga os puxadores selecionados a porta selecionada"""
    bl_idname = "object.cabinet_vincular_puxador"
    bl_label = "Vincular Puxador e Porta"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        puxadores, folhas = _puxadores_e_folhas_da_selecao(context)
        return context.mode == 'OBJECT' and bool(puxadores) and bool(folhas)

    def execute(self, context):
        puxadores, folhas = _puxadores_e_folhas_da_selecao(context)
        context.view_layer.update()
        for pux in puxadores:
            _portas._ligar_puxador(pux, _portas._folha_mais_proxima(pux, folhas))
        self.report({'INFO'}, "%d puxador(es) ligado(s)" % len(puxadores))
        return {'FINISHED'}


def _referencial_do_puxador(pux):
    """Base em que L/A/P do puxador sao medidos e o indice de cada um.

    Ligado: o da chapa pai -- folha ou chapa avulsa -- (X largura,
    Y altura, Z espessura). Solto: o do mundo, com a convencao das
    medidas (L = X, A = Z, P = Y).
    """
    folha = pux.parent if pux.parent is not None and _chapas.MARCA_CHAPA in pux.parent else None
    if folha is not None:
        return folha.matrix_world.to_3x3().normalized(), (0, 1, 2), folha
    return Matrix.Identity(3), (0, 2, 1), None


def _medidas_do_puxador(pux):
    base, indices, _folha = _referencial_do_puxador(pux)
    inversa = base.transposed()
    pontos = [inversa @ (pux.matrix_world @ Vector(c)) for c in pux.bound_box]
    tamanho = [(max(p[k] for p in pontos) - min(p[k] for p in pontos)) * 1000.0
               for k in range(3)]
    travas = list(pux.get(_chapas.CHAVE_TRAVAS_PUXADOR, (1, 1, 1)))
    return [(nome, tamanho[k], 'pux_%d' % k, bool(travas[k]), k)
            for nome, k in zip(('Largura', 'Altura', 'Profundidade'), indices)]


def _redimensionar_puxador(pux, eixo, valor_mm):
    """Escala o puxador em UM eixo do referencial, pelo centro dele."""
    base, _indices, _folha = _referencial_do_puxador(pux)
    inversa = base.transposed()
    pontos = [inversa @ (pux.matrix_world @ Vector(c)) for c in pux.bound_box]
    c_min = min(p[eixo] for p in pontos)
    c_max = max(p[eixo] for p in pontos)
    if c_max - c_min < 1e-9:
        raise ValueError("Puxador sem medida nesse eixo")
    escala = [1.0, 1.0, 1.0]
    escala[eixo] = (valor_mm / 1000.0) / (c_max - c_min)
    centro = Vector()
    centro[eixo] = (c_min + c_max) / 2.0
    no_referencial = (Matrix.Translation(centro)
                      @ Matrix.Diagonal((*escala, 1.0))
                      @ Matrix.Translation(-centro))
    base4 = base.to_4x4()
    pux.matrix_world = base4 @ no_referencial @ base4.inverted() @ pux.matrix_world


# ------------------------------------------- porta a partir de objetos
def _caixa_no_referencial(objs, base):
    """(lo, hi) em mm dos vertices das malhas, nos eixos de `base`."""
    inversa = base.transposed()
    pontos = [inversa @ (o.matrix_world @ v.co) * 1000.0
              for o in objs for v in o.data.vertices]
    if not pontos:
        raise ValueError("Folha sem geometria")
    return (Vector(tuple(min(p[i] for p in pontos) for i in range(3))),
            Vector(tuple(max(p[i] for p in pontos) for i in range(3))))


def _vao_inverso(caixa, parametros):
    """O vao que, com estes parametros, gera folhas nesta caixa.

    O inverso de `_portas._calcular_folhas_portas`: externo = vao - 2*inicio,
    com inicio = folga - cobertura; o plano do vao fica atras da folha
    (sobreposta) ou na frente dela (embutida/correr). Com isso uma porta
    importada e' regenerada exatamente onde estava.
    Devolve (largura, altura, origem) -- origem em mm, nos eixos da caixa.
    """
    lo, hi = caixa
    p = parametros
    esq, dir_, baixo, cima = _portas._inicios_porta(p)
    largura = (hi.x - lo.x) + esq + dir_
    altura = (hi.y - lo.y) + baixo + cima
    if p['abertura'] == 'CORRER':
        plano = hi.z + p['recuo_correr_mm']
    elif p['dobradica'] == 'SUPER_CURVA':
        plano = hi.z + p['recuo_embutida_mm']
    else:
        plano = lo.z - _ferragens._afastamento_porta(p)
    return largura, altura, Vector((lo.x - esq, lo.y - baixo, plano))


def _matriz_do_vao(base, origem_mm):
    matriz = base.to_4x4()
    matriz.translation = base @ (origem_mm / 1000.0)
    return matriz


def _frente_no_mundo(normal):
    i = max(range(3), key=lambda k: abs(normal[k]))
    return ('NEG_' if normal[i] < 0 else 'POS_') + 'XYZ'[i]


def _novo_grupo_portas(context, pai=None):
    grupo = bpy.data.objects.new("Portas", None)
    context.collection.objects.link(grupo)
    grupo[_chapas.MARCA_PORTAS] = 1
    _chapas._ocultar_empty(grupo)
    grupo.parent = pai
    # As medidas sao de mundo, mesmo quando o pai tem escala.
    if pai is not None:
        grupo.matrix_parent_inverse = pai.matrix_world.inverted()
    return grupo


def _guardar_puxadores(grupo):
    return [(p, p.matrix_world.copy()) for f in _portas._folhas_portas(grupo)
            for p in f.children if _chapas.MARCA_PUXADOR in p]


def _devolver_puxadores(grupo, guardados):
    """Puxadores voltam ao lugar de antes, ligados a folha mais perto.

    Para operacoes que so' REORIENTAM a porta (frente, vinculo): a
    folha e' a mesma caixa no mesmo lugar, mas os eixos dela mudaram, e
    sem isto o puxador giraria junto.
    """
    folhas = _portas._folhas_portas(grupo)
    for pux, mundo in guardados:
        pux.parent = None
        pux.matrix_world = mundo
    bpy.context.view_layer.update()
    for pux, _mundo in guardados:
        _portas._ligar_puxador(pux, _portas._folha_mais_proxima(pux, folhas))


def _direcao_da_vista(context):
    """Do movel para quem olha, se houver uma viewport a mao."""
    for area in getattr(context.screen, 'areas', ()):
        if area.type == 'VIEW_3D' and not _gaveta._eh_area_gaveta_bruto(area):
            espaco = area.spaces.active
            rv3d = getattr(espaco, 'region_3d', None)
            if rv3d is not None:
                return rv3d.view_rotation @ Vector((0.0, 0.0, 1.0))
    return None


def _porta_de_objetos(context, objs):
    """Uma folha de porta a partir de objetos importados.

    A maior placa vira a folha; o resto vira puxador dela. A frente vai
    para o lado do puxador (e' nele que se pega); sem puxador, para quem
    olha. De pe', a altura e' o Z do mundo; deitada, a largura e' o lado
    maior. "Definir como frente" corrige o palpite.
    """
    analises = {o: a for o in objs for a in [_analisar_peca(o)] if a}
    if not analises:
        raise ValueError("Selecione os objetos da porta")
    placas = [o for o, a in analises.items() if a['chapa']] or list(analises)
    placa = max(placas, key=lambda o: analises[o]['dims'][0]
                * analises[o]['dims'][1])
    outros = [o for o in analises if o is not placa]
    analise = analises[placa]
    base, (L, C, E) = analise['base'], analise['dims']
    normal = base.col[2].copy()
    if outros:
        alvo = (sum((_portas._centro_mundo(o) for o in outros), Vector()) / len(outros)
                - analise['centro'])
    else:
        alvo = _direcao_da_vista(context)
        if alvo is None:
            alvo = (Vector((0, 0, 1)) if abs(normal.z) > 0.7
                    else Vector((0, -1, 0)))
    if normal.dot(alvo) < 0:
        normal = -normal
    if abs(normal.z) < 0.7:
        cima = Vector((0.0, 0.0, 1.0))
    else:
        cima = (base.col[1] if C < L else base.col[0]).copy()
        if cima.dot(Vector((1.0, 1.0, 0.0))) < 0:
            cima = -cima
    cima = (cima - normal * cima.dot(normal)).normalized()
    direita = cima.cross(normal).normalized()
    referencial = Matrix((direita, normal.cross(direita), normal)).transposed()

    parametros = _portas._parametros_portas_da_cena(context.scene, numerico=True)
    parametros['folhas'] = 1
    if parametros['abertura'] == 'CORRER':
        parametros['abertura'] = 'GIRO'
    if parametros['dobradica'] == 'ESCOLHER':
        parametros['dobradica'] = 'RETA'
    parametros['espessura_mm'] = _chapas._espessura_livre(E)
    converter_em_chapa(placa, analise)
    context.view_layer.update()
    largura, altura, origem = _vao_inverso(
        _caixa_no_referencial([placa], referencial), parametros)
    grupo = _novo_grupo_portas(context)
    grupo.matrix_world = _matriz_do_vao(referencial, origem)
    placa[_chapas.MARCA_FOLHA] = 1
    placa['porta_indice'] = 0
    placa.parent = grupo
    placa.matrix_parent_inverse = Matrix.Identity(4)
    largura_em = 'X' if abs(direita.x) >= abs(direita.y) else 'Y'
    _portas._aplicar_portas(context, grupo, _matriz_do_vao(referencial, origem), None,
                    largura, altura, parametros,
                    frente=_frente_no_mundo(normal), largura_em=largura_em)
    for obj in outros:
        obj[_chapas.MARCA_PUXADOR] = 1
        obj[_chapas.CHAVE_TRAVAS_PUXADOR] = [1, 1, 1]
        _portas._ligar_puxador(obj, placa)
    return grupo


class OBJECT_OT_folha_de_objetos(Operator):
    """Converte os objetos selecionados (placa + puxador) numa porta"""
    bl_idname = "object.cabinet_folha_de_objetos"
    bl_label = "Converter em Porta"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and any(
            _chapas.MARCA_CHAPA not in o or o.parent is None
            or _chapas.MARCA_CONJUNTO not in o.parent for o in _malhas_soltas(context))

    def execute(self, context):
        try:
            grupo = _porta_de_objetos(context, _malhas_soltas(context))
        except (ValueError, KeyError) as erro:
            self.report({'WARNING'}, str(erro))
            return {'CANCELLED'}
        for obj in context.selected_objects:
            obj.select_set(False)
        grupo.select_set(True)
        context.view_layer.objects.active = grupo
        self.report({'INFO'}, "Folha criada; selecione outra e agrupe em porta dupla")
        return {'FINISHED'}


def _grupos_da_selecao(context):
    grupos = []
    for obj in context.selected_objects:
        grupo = _portas._grupo_portas(obj)
        if grupo is not None and grupo.get('porta_parametros') and grupo not in grupos:
            grupos.append(grupo)
    return grupos


def _fundir_portas(context, g1, g2):
    """Duas portas de uma folha cada viram uma porta dupla."""
    folhas = [_portas._folhas_portas(g) for g in (g1, g2)]
    if any(len(f) != 1 for f in folhas):
        raise ValueError("Selecione duas portas de UMA folha cada")
    base = g1.matrix_world.to_3x3().normalized()
    outra = g2.matrix_world.to_3x3().normalized()
    if base.col[2].dot(outra.col[2]) < 0.999:
        raise ValueError("As folhas nao estao viradas para o mesmo lado")
    if base.col[1].dot(outra.col[1]) < 0.999:
        raise ValueError("Folhas com orientacao diferente; use Definir como frente")
    p1, p2 = dict(g1['porta_parametros']), g2['porta_parametros']
    if abs(float(p1['espessura_mm']) - float(p2['espessura_mm'])) > 0.01:
        raise ValueError("As folhas tem espessuras diferentes")
    f1, f2 = folhas[0][0], folhas[1][0]
    c1, c2 = (_caixa_no_referencial([f], base) for f in (f1, f2))
    if (abs(c1[0].z - c2[0].z) > 1.0 or abs(c1[1].z - c2[1].z) > 1.0):
        raise ValueError("As folhas nao estao no mesmo plano")
    if (abs(c1[0].y - c2[0].y) > 1.0 or abs(c1[1].y - c2[1].y) > 1.0):
        raise ValueError("As folhas tem alturas diferentes")
    if c2[0].x < c1[0].x:
        (f1, c1), (f2, c2) = (f2, c2), (f1, c1)
    fresta = c2[0].x - c1[1].x
    if fresta < -0.5:
        raise ValueError("As folhas se sobrepoem")
    lo = Vector(tuple(min(c1[0][i], c2[0][i]) for i in range(3)))
    hi = Vector(tuple(max(c1[1][i], c2[1][i]) for i in range(3)))
    p1['folhas'] = 2
    p1['entre_folhas_mm'] = max(0.0, fresta)
    if p1['abertura'] == 'BASCULANTE':
        p1['abertura'] = 'GIRO'
    largura, altura, origem = _vao_inverso((lo, hi), p1)
    _portas._calcular_folhas_portas(largura, altura, p1)       # recusa antes de mexer
    modulo = bpy.data.objects.get(g1.get(_portas.CHAVE_MODULO_PORTA, ''))
    for indice, folha in enumerate((f1, f2)):
        if folha.parent != g1:
            mundo = folha.matrix_world.copy()
            folha.parent = g1
            folha.matrix_parent_inverse = Matrix.Identity(4)
            folha.matrix_basis = g1.matrix_world.inverted() @ mundo
        folha['porta_indice'] = indice
    for filho in list(g2.children):
        mundo = filho.matrix_world.copy()
        filho.parent = g1
        filho.matrix_parent_inverse = g1.matrix_world.inverted()
        filho.matrix_world = mundo
    bpy.data.objects.remove(g2, do_unlink=True)
    _portas._aplicar_portas(context, g1, _matriz_do_vao(base, origem), g1.parent,
                    largura, altura, p1)
    if modulo is not None:
        _vincular_porta_modulo(context, g1, modulo)
    return g1


class OBJECT_OT_porta_dupla(Operator):
    """Converte duas portas de uma folha numa porta dupla"""
    bl_idname = "object.cabinet_porta_dupla"
    bl_label = "Converter em Porta Dupla"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and len(_grupos_da_selecao(context)) == 2

    def execute(self, context):
        g1, g2 = _grupos_da_selecao(context)
        try:
            grupo = _fundir_portas(context, g1, g2)
        except (ValueError, KeyError) as erro:
            self.report({'WARNING'}, str(erro))
            return {'CANCELLED'}
        context.view_layer.objects.active = grupo
        self.report({'INFO'}, "Porta dupla criada")
        return {'FINISHED'}


# -------------------------------------------- vincular porta e modulo
def _vincular_porta_modulo(context, grupo, modulo):
    """A porta passa a pertencer ao modulo e a acompanha-lo.

    A ANCORA sao as faces do modulo, nao um ponto: a mesma convencao das
    portas criadas no vao (`_portas._folgas_do_vao`). Os parametros sao deduzidos
    da posicao: atras da face do modulo = embutida; na frente, a
    cobertura das laterais diz reta (~E) ou curva (~E/2).
    """
    parametros = dict(grupo['porta_parametros'])
    folhas = _portas._folhas_portas(grupo)
    caixa = _portas._caixa_do_modulo(modulo)
    limites = _portas._limites_locais_modulo(modulo)
    if not folhas or caixa is None or limites is None:
        raise ValueError("Porta ou modulo sem geometria")
    E = caixa[3]
    lo_m, hi_m = limites
    eixos_modulo = modulo.matrix_world.to_quaternion().to_matrix()
    local = eixos_modulo.transposed()
    base_porta = grupo.matrix_world.to_3x3().normalized()
    frente = _frente_no_mundo(local @ base_porta.col[2])
    direita = local @ base_porta.col[0]
    largura_em = 'X' if abs(direita.x) >= abs(direita.y) else 'Y'
    il, _ia, inormal = _portas._eixos_da_frente(frente, largura_em)
    pontos = [_portas._local_no_modulo(modulo, f.matrix_world @ v.co)
              for f in folhas for v in f.data.vertices]
    lo_p = [min(p[i] for p in pontos) for i in range(3)]
    hi_p = [max(p[i] for p in pontos) for i in range(3)]
    positiva = frente.startswith('POS')
    sinal = 1.0 if positiva else -1.0
    face = hi_m[inormal] if positiva else lo_m[inormal]
    tras = lo_p[inormal] if positiva else hi_p[inormal]
    diante = hi_p[inormal] if positiva else lo_p[inormal]
    afastado = sinal * (tras - face)
    parametros['lateral_mm'] = _portas._espessura_do_vao(modulo, padrao=E)
    if parametros['abertura'] == 'CORRER':
        parametros['recuo_correr_mm'] = max(0.1, -sinal * (diante - face))
    elif afastado < -0.5:
        parametros['dobradica'] = 'SUPER_CURVA'
        parametros['recuo_embutida_mm'] = max(0.0, -sinal * (diante - face))
    else:
        parametros['afastamento_mm'] = max(0.0, afastado)
        cobertura = max(0.0, ((lo_m[il] + E) - lo_p[il]
                              + hi_p[il] - (hi_m[il] - E)) / 2.0)
        parametros['dobradica'] = 'RETA' if cobertura >= 0.75 * E else 'CURVA'
        ideal = E if parametros['dobradica'] == 'RETA' else E / 2.0
        parametros['folga_mm'] = max(0.0, ideal - cobertura)
    referencial = _portas._base_da_frente(eixos_modulo, frente, largura_em).transposed()
    largura, altura, origem = _vao_inverso(
        _caixa_no_referencial(folhas, referencial), parametros)
    matriz = _matriz_do_vao(referencial, origem)
    _portas._calcular_folhas_portas(largura, altura, parametros)  # recusa antes
    girou = any(abs(a - b) > 1e-4 for linha_a, linha_b in
                zip(base_porta, referencial) for a, b in zip(linha_a, linha_b))
    guardados = _guardar_puxadores(grupo) if girou else []
    if grupo.parent != modulo:
        mundo = grupo.matrix_world.copy()
        grupo.parent = modulo
        grupo.matrix_parent_inverse = modulo.matrix_world.inverted()
        grupo.matrix_world = mundo
    for i in range(4):
        if 'porta_ancora_%d' % i in grupo:
            del grupo['porta_ancora_%d' % i]
    _portas._aplicar_portas(context, grupo, matriz, modulo, largura, altura,
                    parametros, frente=frente, largura_em=largura_em)
    if guardados:
        _devolver_puxadores(grupo, guardados)
    canto_b = matriz @ Vector((largura / 1000.0, altura / 1000.0, 0.0))
    medido = _portas._folgas_do_vao(modulo, matriz.translation, canto_b, frente,
                            largura_em)
    if medido is None:
        raise ValueError("Modulo sem medidas para ancorar a porta")
    grupo[_portas.CHAVE_MODULO_PORTA] = modulo.name
    grupo[_portas.CHAVE_FOLGAS_PORTA] = list(medido[0])
    grupo[_portas.CHAVE_RECUO_PORTA] = medido[1]
    return grupo


def _porta_e_modulo_da_selecao(context):
    grupos = _grupos_da_selecao(context)
    modulos = []
    for obj in context.selected_objects:
        if _portas._grupo_portas(obj) is not None:
            continue
        modulo = obj if _chapas.MARCA_CONJUNTO in obj else _portas._modulo_da_chapa(obj)
        if modulo is not None and modulo not in modulos:
            modulos.append(modulo)
    return grupos, modulos


class OBJECT_OT_vincular_porta(Operator):
    """Liga a porta (unica ou dupla) selecionada ao modulo selecionado"""
    bl_idname = "object.cabinet_vincular_porta"
    bl_label = "Vincular Porta e Modulo"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        grupos, modulos = _porta_e_modulo_da_selecao(context)
        return context.mode == 'OBJECT' and bool(grupos) and len(modulos) == 1

    def execute(self, context):
        grupos, modulos = _porta_e_modulo_da_selecao(context)
        try:
            for grupo in grupos:
                _vincular_porta_modulo(context, grupo, modulos[0])
        except (ValueError, KeyError) as erro:
            self.report({'WARNING'}, str(erro))
            return {'CANCELLED'}
        self.report({'INFO'}, "%d porta(s) ligada(s) ao modulo; use "
                    "Reposicionar para encaixar no vao" % len(grupos))
        return {'FINISHED'}


# ------------------------------------- corrente Modulos | Portas
# A corrente e' o INTERRUPTOR de associacao (substituiu "Eixos do vao"):
# ligada = a porta pertence ao modulo e usa os eixos dele; partida = a
# porta e' solta, nos eixos do mundo. Com uma porta ATIVA (2o/3o nivel
# do clique) ela mostra e troca o estado DAQUELA porta; sem porta ativa,
# decide como nasce a proxima (`Scene.porta_associar`). O modulo
# selecionado tambem seleciona as portas dele -- por isso vale a ATIVA.
CHAVE_MODULO_ANTIGO = "porta_modulo_antigo"


def _porta_ativa(context):
    grupo = _portas._grupo_portas(context.object)
    return grupo if grupo is not None and grupo.get('porta_parametros') else None


def _corrente_porta_ligada(context):
    grupo = _porta_ativa(context)
    if grupo is not None:
        return bool(grupo.get(_portas.CHAVE_MODULO_PORTA))
    return bool(getattr(context.scene, 'porta_associar', True))


def _desvincular_porta(grupo):
    """A porta fica onde esta', mas deixa de seguir o modulo."""
    antigo = grupo.get(_portas.CHAVE_MODULO_PORTA)
    mundo = grupo.matrix_world.copy()
    grupo.parent = None
    grupo.matrix_world = mundo
    for chave in (_portas.CHAVE_MODULO_PORTA, _portas.CHAVE_FOLGAS_PORTA, _portas.CHAVE_RECUO_PORTA):
        if chave in grupo:
            del grupo[chave]
    if antigo:
        # religar pela mesma corrente volta para o mesmo modulo
        grupo[CHAVE_MODULO_ANTIGO] = antigo


class OBJECT_OT_corrente_porta(Operator):
    """Associa a porta ao modulo (corrente ligada) ou ao mundo (partida).
    Sem porta ativa, vale para a proxima porta criada"""
    bl_idname = "object.cabinet_corrente_porta"
    bl_label = "Porta no Modulo / no Mundo"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def execute(self, context):
        grupo = _porta_ativa(context)
        if grupo is None:
            s = context.scene
            s.porta_associar = not s.porta_associar
            self.report({'INFO'}, "Proxima porta: " + (
                "presa ao modulo" if s.porta_associar else "solta, no mundo"))
            return {'FINISHED'}
        if grupo.get(_portas.CHAVE_MODULO_PORTA):
            _desvincular_porta(grupo)
            self.report({'INFO'}, "Porta solta: eixos do mundo")
            return {'FINISHED'}
        _grupos, modulos = _porta_e_modulo_da_selecao(context)
        modulo = (modulos[0] if modulos else
                  bpy.data.objects.get(grupo.get(CHAVE_MODULO_ANTIGO, '')))
        if modulo is None or _chapas.MARCA_CONJUNTO not in modulo:
            self.report({'WARNING'}, "Selecione tambem o modulo (Shift)")
            return {'CANCELLED'}
        try:
            _vincular_porta_modulo(context, grupo, modulo)
        except (ValueError, KeyError) as erro:
            self.report({'WARNING'}, str(erro))
            return {'CANCELLED'}
        if CHAVE_MODULO_ANTIGO in grupo:
            del grupo[CHAVE_MODULO_ANTIGO]
        self.report({'INFO'}, "Porta presa ao modulo " + modulo.name)
        return {'FINISHED'}


# ---------------------------------------------------- definir a frente
def _virar_porta_modelada(grupo):
    """Gira o referencial 180 graus em torno da altura SEM mexer na madeira.

    A caixa da folha curva nao e' o vao: `_vao_inverso` a deslocava 10-76 cm.
    Aqui o vao fica [0, L] (x -> L - x, z -> 2*Zc - z: o centro da folha
    continua o que os parametros dao) e os vertices voltam ao mesmo mundo.
    """
    folhas = _portas._folhas_portas(grupo)
    if len(folhas) != 1:
        raise ValueError("Porta curva de varias folhas: vire uma folha por vez")
    folha = folhas[0]
    _ferragens._definir_abertura(bpy.context, folha, 0.0)
    bpy.context.view_layer.update()
    largura = float(grupo['porta_vao_largura_mm'])
    centro = Vector(folha[_ferragens.CHAVE_CENTRO_FOLHA])
    guardados = _guardar_puxadores(grupo)
    giro = Matrix.Diagonal((-1.0, 1.0, -1.0, 1.0))
    grupo.matrix_world = (grupo.matrix_world @ Matrix.Translation(
        Vector((largura, 0.0, 2.0 * centro.z)) / 1000.0) @ giro)
    folha[_ferragens.CHAVE_CENTRO_FOLHA] = (largura - centro.x, centro.y, centro.z)
    folha.data.transform(giro)
    folha.data.update()
    p = _portas._copiar_parametros(grupo['porta_parametros'])
    lados = {'ESQUERDA': 'DIREITA', 'DIREITA': 'ESQUERDA'}
    p['dobradica_lado'] = lados.get(p.get('dobradica_lado'), p.get('dobradica_lado'))
    esq, dir_ = _portas.COBERTURAS_LADOS[:2]
    valores = (p.pop(esq, None), p.pop(dir_, None))
    for chave, valor in zip((dir_, esq), valores):
        if valor is not None:
            p[chave] = valor
    grupo['porta_parametros'] = p
    grupo['porta_frente'] = _frente_no_mundo(grupo.matrix_world.to_3x3().col[2])
    _ferragens._posicionar_folha(grupo, folha)
    bpy.context.view_layer.update()
    _devolver_puxadores(grupo, guardados)
    for pux, _mundo in guardados:
        # x virou -x: a mesma borda fisica troca de nome
        borda = pux.get('puxador_borda', '')
        if borda in ('X-', 'X+'):
            pux['puxador_borda'] = 'X+' if borda == 'X-' else 'X-'
    conj = _portas._modulo_da_chapa(folha)
    if conj is not None and _portas.CHAVE_VAO_ORIENTADO in grupo:
        # o redimensionar refaria o referencial antigo pelos cantos gravados
        _portas.gravar_vao_orientado(grupo, conj)
    _ferragens._refazer_ferragens(grupo)


def _definir_frente_porta(context, grupo, normal):
    """A face clicada passa a ser a FRENTE da porta.

    So' as faces grandes valem; a porta vira 180 graus em torno da
    altura, as folhas ficam no mesmo lugar e os puxadores tambem.
    Devolve False se a face clicada ja' era a frente.
    """
    base = grupo.matrix_world.to_3x3().normalized()
    alinhamento = Vector(normal).normalized().dot(base.col[2])
    if abs(alinhamento) < 0.9:
        raise ValueError("Clique numa das faces grandes da porta")
    if alinhamento > 0:
        return False
    if any(f.get('porta_curva_modelada') for f in _portas._folhas_portas(grupo)):
        _virar_porta_modelada(grupo)
        return True
    cima, nova = base.col[1].copy(), -base.col[2]
    direita = cima.cross(nova).normalized()
    referencial = Matrix((direita, cima, nova)).transposed()
    parametros = dict(grupo['porta_parametros'])
    folhas = _portas._folhas_portas(grupo)
    largura, altura, origem = _vao_inverso(
        _caixa_no_referencial(folhas, referencial), parametros)
    guardados = _guardar_puxadores(grupo)
    modulo = bpy.data.objects.get(grupo.get(_portas.CHAVE_MODULO_PORTA, ''))
    _portas._aplicar_portas(context, grupo, _matriz_do_vao(referencial, origem),
                    grupo.parent, largura, altura, parametros,
                    frente=_frente_no_mundo(nova))
    _devolver_puxadores(grupo, guardados)
    if modulo is not None:
        _vincular_porta_modulo(context, grupo, modulo)
    return True


def _viewport_alvo(context):
    """(area, regiao, region_3d) da viewport onde clicar.

    Chamado da gaveta, que tambem e' uma VIEW_3D, o alvo e' a viewport
    vizinha -- a mesma regra do apanhador do vao.
    """
    area = context.area
    if area is not None and _gaveta._eh_area_gaveta(context):
        area = next((a for a in context.screen.areas
                     if a.type == 'VIEW_3D' and a != context.area
                     and not _gaveta._eh_area_gaveta_bruto(a)), None)
    if area is None or area.type != 'VIEW_3D':
        return None
    regiao = next((r for r in area.regions if r.type == 'WINDOW'), None)
    rv3d = getattr(area.spaces.active, 'region_3d', None)
    if regiao is None or rv3d is None:
        return None
    return area, regiao, rv3d


class OBJECT_OT_definir_frente(Operator):
    """Clique numa face grande da porta: ela passa a ser a frente"""
    bl_idname = "object.cabinet_definir_frente"
    bl_label = "Definir como Frente"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        grupo = _portas._grupo_portas(context.object)
        return (context.mode == 'OBJECT' and grupo is not None
                and bool(grupo.get('porta_parametros')))

    def invoke(self, context, event):
        alvo = _viewport_alvo(context)
        if alvo is None:
            self.report({'ERROR'}, "Sem viewport 3D para clicar")
            return {'CANCELLED'}
        self._area, self._regiao, self._rv3d = alvo
        self._grupo = _portas._grupo_portas(context.object).name
        self._area.header_text_set("Clique na face que e' a FRENTE da porta (Esc cancela)")
        context.window.cursor_modal_set('EYEDROPPER')
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _encerrar(self, context):
        self._area.header_text_set(None)
        context.window.cursor_modal_restore()

    def modal(self, context, event):
        if event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            return {'PASS_THROUGH'}
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            self._encerrar(context)
            return {'CANCELLED'}
        if event.type != 'LEFTMOUSE' or event.value != 'PRESS':
            return {'RUNNING_MODAL'}
        mouse = (event.mouse_x - self._regiao.x, event.mouse_y - self._regiao.y)
        origem = view3d_utils.region_2d_to_origin_3d(self._regiao, self._rv3d, mouse)
        direcao = view3d_utils.region_2d_to_vector_3d(self._regiao, self._rv3d, mouse)
        acertou, _ponto, normal, _face, obj, _matriz = context.scene.ray_cast(
            context.evaluated_depsgraph_get(), origem, direcao)
        grupo = bpy.data.objects.get(self._grupo)
        if not acertou or grupo is None or _portas._grupo_portas(obj.original) != grupo:
            self.report({'WARNING'}, "Clique numa folha desta porta")
            return {'RUNNING_MODAL'}
        try:
            _definir_frente_porta(context, grupo, normal)
        except (ValueError, KeyError) as erro:
            self.report({'WARNING'}, str(erro))
            return {'RUNNING_MODAL'}
        self._encerrar(context)
        return {'FINISHED'}


# ============================================== MODULOS DO DXF (DXF)
# Pedido do usuario: trazer os modulos prontos do DXF. Os arquivos da
# biblioteca dele sao RECEITAS (formulas do motor do DXF, sem as pecas);
# o caminho e' o DXF calcular e exportar a cena em DXF. Nesse DXF cada
# PECA e' uma camada (LAYER<n>) de 3DFACE ou polyface, em mm, Z para cima,
# frente em -Y. Vem so' o que e' CHAPA (pela forma, `_analisar_peca`):
# dobradica, puxador, decoracao e o piso ficam de fora (pedido do usuario).
FOLGA_MODULO_PROMOB_MM = 3.0     # pecas a ate' 3 mm uma da outra: mesmo modulo
# Chapa do DXF: >= 3 mm (o fundo tem 6). Cor 7 tambem conserva ripas
# estreitas; sem cor continua o filtro de 50 mm contra ferragens finas.
ESPESSURA_MINIMA_PROMOB_MM = 3.0
LADO_MINIMO_PROMOB_MM = 50.0
# O PISO da cena: chapa DEITADA de mais de 1,5 m2 por baixo de quase
# tudo (cobre o centro de >= 80% das outras pecas) -- uma base de modulo
# nunca cobre as laterais, que ficam fora dela
AREA_MINIMA_PISO_M2 = 1.5
COBERTURA_MINIMA_PISO = 0.8
# ...ou FINA assim (o piso do DXF tem 5 mm; base de modulo, 15+): os
# modulos podem passar da borda dele (Especiais: so' 72% em cima)
ESPESSURA_MAXIMA_PISO_MM = 6.0
# PECA CURVA (porta/painel em arco): o perfil curvo puxado na vertical --
# so' faces deitadas (tampas) e em pe' (laterais) --, fina e comprida.
# Cesto aramado, pe' e puxador nao passam.
FACES_EXTRUSAO_MINIMO = 0.98
COMPRIMENTO_MINIMO_CURVA_MM = 150.0
# ...e CURVA de verdade: parte das laterais fora das duas direcoes
# principais (o micro-ondas da torre e' caixa com moldura e passava)
LATERAL_CURVA_MINIMO = 0.3


def _espessura_da_curva(obj):
    """A espessura (mm) da peca curva, ou None se ela nao e' curva."""
    faces, vertices = _faces_em_mundo(obj)
    total = sum(area for _n, area in faces)
    if total <= 0 or not vertices:
        return None
    tampas = sum(area for n, area in faces if abs(n.z) > 0.98)
    lados = sum(area for n, area in faces if abs(n.z) < 0.02)
    altura = (max(v.z for v in vertices) - min(v.z for v in vertices)) * 1000.0
    if (tampas + lados) / total < FACES_EXTRUSAO_MINIMO or lados <= 0 or altura < 50.0:
        return None
    espessura = tampas * altura / lados                 # mm
    comprimento = tampas * 1e6 / 2.0 / max(espessura, 1e-6)
    em_pe = [(n, area) for n, area in faces if abs(n.z) < 0.02]
    principal = max(em_pe, key=lambda f: f[1])[0]
    outra = principal.cross(Vector((0.0, 0.0, 1.0))).normalized()
    retas = sum(area for n, area in em_pe
                if abs(n.dot(principal)) > 0.995 or abs(n.dot(outra)) > 0.995)
    if (ESPESSURA_MINIMA_PROMOB_MM <= espessura <= ESPESSURA_MAXIMA_CHAPA_MM
            and comprimento >= COMPRIMENTO_MINIMO_CURVA_MM
            and (lados - retas) / lados >= LATERAL_CURVA_MINIMO):
        return espessura
    return None


def cores_dxf_promob(caminho):
    """{camada: cor} da tabela de camadas do DXF (sem tabela: {})."""
    with open(caminho, encoding='latin1') as f:
        linhas = f.read().splitlines()
    pares = [(linhas[i].strip(), linhas[i + 1].strip())
             for i in range(0, len(linhas) - 1, 2)]
    cores, secao, nome = {}, None, None
    for i, (codigo, valor) in enumerate(pares):
        if codigo == '0' and valor == 'SECTION' and i + 1 < len(pares):
            secao = pares[i + 1][1]
        elif secao == 'ENTITIES':
            break
        elif secao == 'TABLES':
            if codigo == '0':
                nome = None
            elif codigo == '2':
                nome = valor
            elif codigo == '62' and nome is not None:
                try:
                    cores[nome] = abs(int(valor))
                except ValueError:
                    pass
    return cores


def ler_dxf_promob(caminho):
    """{camada: (vertices, faces)} em mm: 3DFACE e polyface (POLYLINE 64)."""
    with open(caminho, encoding='latin1') as f:
        linhas = f.read().splitlines()
    pares = [(linhas[i].strip(), linhas[i + 1].strip())
             for i in range(0, len(linhas) - 1, 2)]
    pecas = {}

    def peca(camada):
        return pecas.setdefault(camada, ([], []))
    secao, i, poli = None, 0, None
    while i < len(pares):
        codigo, valor = pares[i]
        if codigo == '0' and valor == 'SECTION' and i + 1 < len(pares):
            secao = pares[i + 1][1]
        if secao != 'ENTITIES' or codigo != '0':
            i += 1
            continue
        j, dados = i + 1, {}
        while j < len(pares) and pares[j][0] != '0':
            dados.setdefault(pares[j][0], pares[j][1])
            j += 1
        camada = dados.get('8', '0')

        def ponto(n, d=dados):
            return tuple(float(d.get('%d%d' % (k, n), 0.0)) for k in (1, 2, 3))
        if valor == '3DFACE':
            vs, fs = peca(camada)
            pts = [ponto(n) for n in range(4)]
            # sem 13/23/33 o 4o canto viraria a ORIGEM e esticaria a peca
            if '13' not in dados or pts[3] == pts[2]:
                pts = pts[:3]
            fs.append([len(vs) + k for k in range(len(pts))])
            vs.extend(pts)
        elif valor == 'POLYLINE':
            poli = (camada, int(dados.get('70', 0)) & 64, len(peca(camada)[0]))
        elif valor == 'VERTEX' and poli is not None and poli[1]:
            vs, fs = peca(poli[0])
            bandeira = int(dados.get('70', 0))
            if bandeira & 64:                    # vertice da polyface
                vs.append(ponto(0))
            elif bandeira & 128:                 # face: indices de 1 em diante
                indices = [abs(int(dados[k])) for k in ('71', '72', '73', '74')
                           if k in dados and int(dados[k]) != 0]
                if len(indices) >= 3:
                    fs.append([poli[2] + n - 1 for n in indices])
        elif valor == 'SEQEND':
            poli = None
        i = j
    return {k: v for k, v in pecas.items() if v[1]}


def _objeto_da_peca(context, nome, vertices, faces, colecao):
    """Malha em metros, vertices repetidos fundidos, objeto na origem."""
    bm = bmesh.new()
    try:
        vs = [bm.verts.new(Vector(v) / 1000.0) for v in vertices]
        for face in faces:
            try:
                bm.faces.new([vs[k] for k in face])
            except ValueError:
                pass                              # face repetida
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
        # triangulos do DXF de volta a quadrados: a caixa vira 8 vertices
        bmesh.ops.dissolve_limit(bm, angle_limit=0.0175, verts=bm.verts,
                                 edges=bm.edges)
        malha = bpy.data.meshes.new(nome)
        bm.to_mesh(malha)
    finally:
        bm.free()
    obj = bpy.data.objects.new(nome, malha)
    colecao.objects.link(obj)
    return obj


def _caixa_mundo_mm(obj):
    pts = [obj.matrix_world @ v.co * 1000.0 for v in obj.data.vertices]
    return ([min(p[k] for p in pts) for k in range(3)],
            [max(p[k] for p in pts) for k in range(3)])


def _modulos_por_contato(objs, folga=FOLGA_MODULO_PROMOB_MM):
    """Caixas filtram; BVH nativa confirma contato na superficie real.
    A caixa de uma chapa em L inclui o vazio: nao pode soldar outro
    armario so' porque ele foi exportado dentro desse retangulo.
    """
    caixas = [_caixa_mundo_mm(o) for o in objs]
    arvores = {}
    pontos = {}
    def superficie(i):
        if i not in arvores:
            bm = bmesh.new()
            try:
                bm.from_mesh(objs[i].data)
                bm.transform(objs[i].matrix_world)
                arvores[i] = BVHTree.FromBMesh(bm)
                pontos[i] = [v.co.copy() for v in bm.verts]
            finally:
                bm.free()
        return arvores[i]

    def encosta(a, b):
        A, B = superficie(a), superficie(b)
        if A.overlap(B):
            return True
        alcance = (folga + .05) / 1000
        return any(arvore.find_nearest(p, alcance)[0] is not None
                   for arvore, vertices in ((A,pontos[b]),(B,pontos[a])) for p in vertices)
    pai = list(range(len(objs)))

    def raiz(a):
        while pai[a] != a:
            pai[a] = pai[pai[a]]
            a = pai[a]
        return a
    ordem = sorted(range(len(objs)), key=lambda i: caixas[i][0][0])
    for pos, a in enumerate(ordem):
        for b in ordem[pos+1:]:
            (la, ha), (lb, hb) = caixas[a], caixas[b]
            if lb[0] > ha[0] + folga:
                break
            if raiz(a) == raiz(b):
                continue
            if (all(la[k] - folga <= hb[k] and lb[k] - folga <= ha[k] for k in range(3))
                    and encosta(a,b)):
                pai[raiz(a)] = raiz(b)
    grupos = {}
    for k, o in enumerate(objs):
        grupos.setdefault(raiz(k), []).append(o)
    grupos = list(grupos.values())
    limites = []
    for g in grupos:
        cs = [_caixa_mundo_mm(o) for o in g]
        limites.append(([min(c[0][k] for c in cs) for k in range(3)],
                        [max(c[1][k] for c in cs) for k in range(3)]))
    # Caixas de gaveta/prateleiras ficam suspensas no vao pelos trilhos.
    # Contencao COMPLETA distingue esses internos de dois corpos em L
    # cujas caixas apenas se cruzam. Corpos de altura igual nao se fundem.
    destinos = {}
    for i,(lo,hi) in enumerate(limites):
        candidatos = [j for j,(a,b) in enumerate(limites) if j != i
                      and hi[2]-lo[2] < .8*(b[2]-a[2])
                      and all(a[k]-folga <= lo[k] and hi[k] <= b[k]+folga for k in range(3))]
        if candidatos:
            destinos[i] = min(candidatos, key=lambda j: math.prod(
                limites[j][1][k]-limites[j][0][k] for k in range(3)))
    for i,j in destinos.items():
        while j in destinos:j=destinos[j]
        grupos[j].extend(grupos[i])
    return sorted([g for i,g in enumerate(grupos) if i not in destinos], key=lambda g: (round(min(_caixa_mundo_mm(o)[0][1] for o in g)),
                                                   round(min(_caixa_mundo_mm(o)[0][0] for o in g))))


def _eh_piso(obj, analise, caixas, centros):
    lo, hi = caixas[obj.name]
    deitada = abs(analise['base'].col[2].z) > 0.99
    area = (hi[0] - lo[0]) * (hi[1] - lo[1]) / 1e6
    if not deitada or area < AREA_MINIMA_PISO_M2:
        return False
    if analise['dims'][2] <= ESPESSURA_MAXIMA_PISO_MM:
        return True
    outros = [c for n, c in centros.items() if n != obj.name]
    dentro = sum(1 for c in outros
                 if lo[0] <= c[0] <= hi[0] and lo[1] <= c[1] <= hi[1])
    return bool(outros) and dentro >= COBERTURA_MINIMA_PISO * len(outros)


def _remover_objeto(obj):
    malha = obj.data
    bpy.data.objects.remove(obj, do_unlink=True)
    if malha is not None and malha.users == 0:
        bpy.data.meshes.remove(malha)


def _eixo_da_espessura(analise):
    normal = analise['base'].col[2]
    return max(range(3), key=lambda k: abs(normal[k]))


def importar_dxf_promob(context, caminho, prefixo='Modulo', na_origem=False):
    """Os modulos do DXF do DXF como modulos NATIVOS, nomeados
    `<prefixo> NN LxAxP` (com `na_origem`, cada um vai para a origem, como
    os presets). So' a COR de chapa (`_promob.CORES_CHAPA`) vira chapa; a
    ferragem do DXF so' informa (a dobradica diz que a frente e' porta,
    o quadro de aluminio que e' correr) e sai. Frentes viram portas e
    gavetas NATIVAS, fundo e travessas as dependentes (`_promob`).
    Devolve ([modulos], {'pecas', 'chapas', 'curvas', 'descartadas',
    'piso', 'portas', 'gavetas', 'correr'})."""
    pecas = ler_dxf_promob(caminho)
    cores = cores_dxf_promob(caminho)
    colecao = context.scene.collection
    objs, cor_de = [], {}
    for camada, (vs, fs) in pecas.items():
        obj = _objeto_da_peca(context, 'Peca ' + camada, vs, fs, colecao)
        objs.append(obj)
        cor_de[obj.name] = cores.get(camada)
    context.view_layer.update()
    caixas = {o.name: _caixa_mundo_mm(o) for o in objs}
    centros = {n: [(lo[k] + hi[k]) / 2.0 for k in range(3)]
               for n, (lo, hi) in caixas.items()}
    chapas, curvas, ferragens, descartadas, piso = [], {}, [], 0, 0
    for obj in objs:
        cor = cor_de[obj.name]
        if cor not in _promob.CORES_CHAPA:
            # A placa fina da dobradica revela a face da folha, inclusive
            # no canto. Guardamos geometria de referencia, nunca o modelo.
            a = (_analisar_peca(obj) if cor == _promob.COR_FERRAGEM
                 and max(hi - lo for lo, hi in zip(*caixas[obj.name]))
                 <= _promob.DOBRADICA_MAXIMA_MM else None)
            ferragens.append(_promob.peca(None, *caixas[obj.name], cor=cor,
                                          analise=a, pontos=[tuple(obj.matrix_world @ v.co * 1000)
                                                             for v in obj.data.vertices] if a else None))
            _remover_objeto(obj)
            descartadas += 1
            continue
        analise = _analisar_peca(obj, 1.0 if cor == _promob.COR_CHAPA
                                 else PROPORCAO_MINIMA_CHAPA)
        if analise is not None and analise['chapa'] and _eh_piso(obj, analise, caixas, centros):
            piso += 1
            analise = None
        if analise is not None and analise['chapa']:
            L, C, E = analise['dims']
            # O DXF arredonda a ripa de 50 mm para 49,9998. Madeira
            # estreita e alta tambem e' apoio/arremate, nao ferragem.
            ripa = (cor == _promob.COR_CHAPA and min(L, C) >= E - .05
                    and max(L, C) >= 100.0)
            if (E < ESPESSURA_MINIMA_PROMOB_MM
                    or (min(L, C) < LADO_MINIMO_PROMOB_MM - .05 and not ripa)):
                analise = None                    # ferragem fina
        if analise is None or not analise['chapa']:
            espessura = _espessura_da_curva(obj)
            if espessura is not None:
                curvas[obj] = espessura
                continue
        if analise is None or not analise['chapa']:
            _remover_objeto(obj)
            descartadas += 1
            continue
        chapas.append((obj, analise))
    modulos = []
    analises = dict(chapas)
    grupos = [g for g in _modulos_por_contato([o for o, _a in chapas] + list(curvas))
              if any(o in analises for o in g)]
    soltas = [o for o in curvas if not any(o in g for g in grupos)]
    for o in soltas:                                  # curva sem modulo: sai
        del curvas[o]
        _remover_objeto(o)
        descartadas += 1
    feitos = {'portas': 0, 'gavetas': 0, 'correr': 0, 'prateleiras': 0}
    for n, grupo in enumerate(grupos, 1):
        dados = []
        for obj in grupo:
            lo, hi = caixas[obj.name]
            if obj in analises:
                a = analises[obj]
                dados.append(_promob.peca(obj, lo, hi, _eixo_da_espessura(a),
                                          espessura=a['dims'][2], analise=a,
                                          pontos=[tuple(obj.matrix_world @ v.co * 1000)
                                                  for v in obj.data.vertices]))
            else:
                dados.append(_promob.peca(obj, lo, hi, curva=True,
                                          espessura=curvas[obj],
                                          pontos=[tuple(obj.matrix_world @ v.co * 1000)
                                                  for v in obj.data.vertices]))
        caixa = _promob._uniao(dados)
        perto = [f for f in ferragens
                 if all(f['lo'][k] < caixa['hi'][k] + 100.0
                        and f['hi'][k] > caixa['lo'][k] - 100.0 for k in range(3))]
        plano = _promob.planejar(dados, perto)
        aba, _categoria, _prefixo = categoria_promob(caminho)
        partes=[_ascii(p) for p in os.path.normpath(caminho).split(os.sep)]
        if 'Quartos' in partes:
            if 'Armarios' in partes:aba='Armarios'
            elif 'Superiores' in partes:aba='Superiores'
        plano['puxador_posicao'] = posicao_do_perfil(aba)
        fora = {id(p['obj']) for p in plano['remover']}
        for p in {id(p['obj']):p for p in plano['remover']}.values():
            # tira das listas ANTES: objeto removido nao se compara mais
            curvas.pop(p['obj'], None)
            analises.pop(p['obj'], None)
            _remover_objeto(p['obj'])
        grupo = [o for o in grupo if id(o) not in fora]
        placas = [o for o in grupo if o in analises]
        if not placas:
            continue
        for obj in placas:
            converter_em_chapa(obj, analises[obj])
        context.view_layer.update()
        conj = _modulos.agrupar_chapas(context, placas, '%s %02d' % (prefixo, n))
        for obj in grupo:
            if obj in analises:
                continue
            # porta/painel curvo: entra no modulo como acessorio que
            # deforma junto com a forma (o raio da HUD refaz o arco)
            mundo = obj.matrix_world.copy()
            obj.parent = conj
            obj.matrix_parent_inverse = conj.matrix_world.inverted()
            obj.matrix_world = mundo
            obj[_chapas.MARCA_ACESSORIO] = 1
            obj[_formas.MARCA_CURVA] = 1
            colecao = _modulos._colecao_do_modulo(conj)
            if colecao is not None:
                _modulos._mover_para_colecao(obj, colecao)
        _promob.orientar_modulo(conj, plano)
        _promob.marcar_dependentes(conj, plano)
        context.view_layer.update()
        for chave, valor in _promob.aplicar(context, conj, plano).items():
            feitos[chave] += valor
        ajustes=_promob.ajustar_encaixes(conj)
        _promob.reencaixar_verticais(conj,ajustes)
        _promob.alinhar_arremates(conj)
        _promob.ajustar_recuo_fundos(conj)
        _promob.ajustar_internos_ao_fundo(conj)
        if _categoria == 'Diagonais':
            _promob.integrar_frentes_diagonais(conj)
        else:
            _promob.corrigir_curvas_legadas(conj)
        _frentes.preparar_conjunto(conj)
        if na_origem:
            # como os nativos: a biblioteca insere no cursor
            conj.location = (0.0, 0.0, 0.0)
            context.view_layer.update()
        _modulos.sincronizar_medidas_conjunto(conj)
        nome = '%s %02d %dx%dx%d' % (prefixo, n, round(conj.conj_largura_mm),
                                     round(conj.conj_altura_mm),
                                     round(conj.conj_profundidade_mm))
        _modulos.nomear_grupo(conj, nome)
        modulos.append(conj)
    return modulos, dict({'pecas': len(pecas), 'chapas': len(chapas),
                          'curvas': len(curvas),
                          'descartadas': descartadas - piso, 'piso': piso}, **feitos)


def importar_promob_para_biblioteca(context, caminho, niveis, prefixo):
    """Cada modulo do DXF vira um preset da biblioteca em `niveis`
    (quantos forem). Devolve ([arquivos .blend], info)."""
    if _ascii(os.path.basename(os.path.dirname(caminho))).lower() == 'portas':
        modulos, info = importar_portas_avulsas(context, caminho, prefixo)
    else:
        modulos, info = importar_dxf_promob(context, caminho, prefixo, na_origem=True)
    arquivos = []
    for conj in modulos:
        arquivos.append(_biblioteca.gravar_modulo_na_biblioteca(
            context, conj, conj.name, niveis))
    return arquivos, info


def importar_portas_avulsas(context, caminho, prefixo):
    """Catalogo de FOLHAS: conserva madeira modelada; quadro/painel
    medidos viram folha nativa. Ferragens do DXF apenas referenciam lado.
    Nao inventa uma caixa de armario para uma porta exportada sozinha.
    """
    dados=ler_dxf_promob(caminho);cores=cores_dxf_promob(caminho)
    pecas=[];metais=[]
    for nome,(vs,fs) in dados.items():
        # sem tabela de camadas tudo e' chapa (CORES_CHAPA aceita None)
        cor=cores.get(nome,7)
        lo=[min(v[k] for v in vs) for k in range(3)]
        hi=[max(v[k] for v in vs) for k in range(3)]
        if cor==_promob.COR_FERRAGEM:
            metais.append((lo,hi));continue
        if cor not in (7,254) or hi[2]-lo[2]<50:continue
        obj=_objeto_da_peca(context,'Peca '+nome,vs,fs,context.scene.collection)
        pecas.append((obj,lo,hi,cor))
    # Sobreposicao aqui e' na frente exportada: o painel esta' DENTRO
    # do quadro. Cada grupo continua separado dos demais mostruarios.
    grupos=[]
    for p in sorted(pecas,key=lambda p: -(p[2][0]-p[1][0])*(p[2][2]-p[1][2])):
        grupo=next((g for g in grupos if all(p[1][k]>=g[0][1][k]-5 and p[2][k]<=g[0][2][k]+5 for k in range(3))),None)
        if grupo is None:grupos.append([p])
        else:grupo.append(p)
    saida=[]
    base=Matrix(((1,0,0),(0,0,1),(0,-1,0))).transposed().to_4x4()
    for i,g in enumerate(sorted(grupos,key=lambda g:(g[0][1][1],g[0][1][0])),1):
        obj,lo,hi,cor=g[0];L,A=hi[0]-lo[0],hi[2]-lo[2]
        E=hi[1]-lo[1]
        p=_portas._parametros_portas_da_cena(context.scene,numerico=True)
        lado='ESQUERDA'
        centros=[(a[0]+b[0])/2 for a,b in metais if lo[0]-50<=(a[0]+b[0])/2<=hi[0]+50
                 and lo[2]<=(a[2]+b[2])/2<=hi[2] and abs(a[1]-hi[1])<60]
        if centros and sum(centros)/len(centros)>(lo[0]+hi[0])/2:lado='DIREITA'
        p.update(abertura='GIRO',folhas=1,dobradica='RETA',dobradica_lado=lado,
                 espessura_mm=E,lateral_mm=15,folga_mm=0,respiro_original=True,
                 folha='QUADRO' if cor==254 else 'CHAPA')
        p.update({k:0.0 for k in _portas.COBERTURAS_LADOS})
        if cor==254:
            painel=min(g,key=lambda p:p[2][1]-p[1][1])
            p['quadro_perfil_mm']=max(1,min((L-(painel[2][0]-painel[1][0]))/2,
                                          (A-(painel[2][2]-painel[1][2]))/2))
            p['quadro_painel_mm']=painel[2][1]-painel[1][1]
        matriz=base.copy()
        matriz.translation=Vector((lo[0],hi[1],lo[2]))/1000
        grupo=_portas._aplicar_portas(context,None,matriz,None,L,A,p,frente='NEG_Y')
        folha,=_portas._folhas_portas(grupo)
        if cor==7:
            # Modelos usinados/moldurados conservam todos os vertices.
            bm=bmesh.new();inv=folha.matrix_world.inverted()
            centro=Vector(tuple((lo[k]+hi[k])/2000 for k in range(3)))
            desloc=Matrix.Translation(folha.matrix_world.translation-centro)
            try:
                for src,_,_,_ in g:
                    inicio=len(bm.verts);bm.from_mesh(src.data)
                    novos=list(bm.verts)[inicio:]
                    bmesh.ops.transform(bm,matrix=inv @ desloc @ src.matrix_world,verts=novos)
                bm.to_mesh(folha.data)
            finally:bm.free()
            folha.data.update()
        grupo.name='%s %02d %dx%d'%(prefixo,i,round(L),round(A))
        folha['porta_origem_promob']=obj.name
        for src,_,_,_ in g:_remover_objeto(src)
        grupo.location=(0,0,0)
        context.view_layer.update()
        _portas._ferragens._refazer_ferragens(grupo)
        saida.append(grupo)
    return saida,dict(pecas=len(dados),portas=len(saida),gavetas=0,correr=0,prateleiras=0)


def prefixo_da_categoria(categoria):
    """"Cantos" -> "Canto", "Inferiores" -> "Inferior": nome de UM modulo."""
    nome = categoria.strip()
    if nome.lower().endswith('ores'):
        return nome[:-2]
    if nome.lower().endswith('oes'):
        return nome[:-3] + 'ao'
    if nome.lower().endswith('ais'):
        return nome[:-3] + 'al'
    return nome[:-1] if nome.lower().endswith('s') else nome


# As abas do DXF (Cozinha > Inferiores > Cantos...): cada .dxf exportado
# e' UMA categoria, pelo nome do arquivo. A aba e a categoria sao DOIS niveis
# da biblioteca (Armarios > Cozinha > Inferiores > Cantos: pedido do usuario,
# a cascata nao tem limite). Chave: o nome do arquivo sem acento, so' letras.
CATEGORIAS_PROMOB = {
    'cantos': ('Inferiores', 'Cantos', 'Canto'),
    'bifond': ('Inferiores', 'Cantos Bifold', 'Bifold'),
    'bifold': ('Inferiores', 'Cantos Bifold', 'Bifold'),
    'cantosbifold': ('Inferiores', 'Cantos Bifold', 'Bifold'),
    'balcoes': ('Inferiores', 'Balcoes', 'Balcao'),
    'especiais': ('Inferiores', 'Especiais', 'Especial'),
    'gaveteiros': ('Inferiores', 'Gaveteiros', 'Gaveteiro'),
    'peletros': ('Inferiores', 'Para Eletros', 'Eletro'),
    'paraeletros': ('Inferiores', 'Para Eletros', 'Eletro'),
    'pias': ('Inferiores', 'Pias', 'Pia'),
    'diagonais': ('Inferiores', 'Diagonais', 'Diagonal'),
    'cantoneiras': ('Inferiores', 'Cantoneiras', 'Cantoneira'),
    'fechamentos': ('Inferiores', 'Fechamentos', 'Fechamento'),
    'despenseiros': ('Altos', 'Despenseiros', 'Despenseiro'),
}
ABAS_PROMOB = ('Inferiores', 'Altos', 'Ilhas', 'Sup Baixos', 'Sup Medios',
               'Sup Altos', 'Tampos', 'Componentes')


def _ascii(texto):
    return unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode()


def posicao_do_perfil(aba):
    """Borda do perfil pela aba (nivel 3 da biblioteca). Pedido do usuario:
    sempre na HORIZONTAL, salvo guarda-roupa (Quartos > Armarios)."""
    if aba.startswith('Sup') or aba == 'Superiores':
        return 'BAIXO'
    if aba == 'Armarios':
        return 'LADO'
    return 'ALTURA' if aba in ('Altos', 'Torres') else 'CIMA'


def categoria_promob(caminho):
    """(aba, categoria, prefixo) de um .dxf exportado: a PASTA e' a aba
    (Altos, Ilhas, Sup Baixos...) e o ARQUIVO a categoria. Pasta que nao
    e' aba (as primeiras exportacoes: Cantos/, Bifond/) fica com a aba da
    tabela, ou Inferiores. Fora de Inferiores o nome leva a aba ("Canto
    Sup Baixo 01"): sem isto o "Canto 01" de uma aba gravava por cima do
    da outra."""
    nome = _ascii(os.path.splitext(os.path.basename(caminho))[0]).strip()
    chave = ''.join(c for c in nome.lower() if c.isalpha())
    pasta = _ascii(os.path.basename(os.path.dirname(caminho))).strip()
    aba_pasta = next((a for a in ABAS_PROMOB if a.lower() == pasta.lower()), None)
    aba, categoria, prefixo = CATEGORIAS_PROMOB.get(
        chave, ('Inferiores', nome, prefixo_da_categoria(nome)))
    aba = aba_pasta or aba
    if aba != 'Inferiores':
        prefixo = '%s %s' % (prefixo, prefixo_da_categoria(aba))
    return aba, categoria, prefixo


def destino_categoria_promob(caminho, raiz):
    """Endereco sem colidir Cozinha/Quartos nem perder os novos ramos.
    A subpasta Cantos dos armarios de quarto e' o lote de exportacao,
    como o antigo Cozinha/Cantos; cada arquivo continua sua categoria.
    """
    partes=[_ascii(p) for p in os.path.relpath(os.path.dirname(caminho),raiz).split(os.sep)]
    ambiente=partes[0] if partes[0]!='.' else 'Diversos'
    aba,categoria,prefixo=categoria_promob(caminho)
    # sem caixa, como importar_promob_para_biblioteca decide a pasta de portas
    if ambiente=='Cozinha' and partes[-1].lower()!='portas':
        return ('Armarios',ambiente,aba,categoria),prefixo
    if partes[-1].lower()=='portas':
        return ('Armarios',ambiente,'Portas',categoria),'Porta '+categoria
    pastas=partes[1:]
    if len(pastas)>1 and pastas[-1]=='Cantos':pastas=pastas[:-1]
    niveis=['Armarios',ambiente]+pastas
    if not niveis or niveis[-1]!=categoria:niveis.append(categoria)
    sufixo=[prefixo_da_categoria(ambiente)]
    if pastas and pastas[0]!=categoria:sufixo.append(prefixo_da_categoria(pastas[0]))
    return tuple(niveis),prefixo_da_categoria(categoria)+' '+' '.join(sufixo)


class OBJECT_OT_importar_promob(Operator):
    """Importa os modulos de um DXF exportado do DXF: so' as chapas
    (ferragens, puxadores e decoracao ficam de fora)"""
    bl_idname = "object.cabinet_importar_promob"
    bl_label = "Importar Modulos (DXF)"
    bl_options = {'REGISTER', 'UNDO'}

    filepath: bpy.props.StringProperty(subtype='FILE_PATH', options={'SKIP_SAVE'})
    filter_glob: bpy.props.StringProperty(default='*.dxf', options={'HIDDEN'})

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        if not self.filepath.lower().endswith('.dxf'):
            self.report({'WARNING'}, "Escolha um arquivo .dxf")
            return {'CANCELLED'}
        modulos, info = importar_dxf_promob(context, self.filepath,
                                            categoria_promob(self.filepath)[2])
        if not modulos:
            self.report({'WARNING'}, "Nenhuma chapa no arquivo")
            return {'CANCELLED'}
        self.report({'INFO'}, "%d modulo(s), %d chapa(s); %d peca(s) que nao sao "
                    "chapa ficaram de fora" % (len(modulos), info['chapas'],
                                               info['descartadas']))
        return {'FINISHED'}
