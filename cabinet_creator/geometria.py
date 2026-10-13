"""Geometria das pecas: o que a malha TEM de notavel (pedido do usuario:
"detector de angulo", quinas retas para o snap, superficies e bordas
arredondadas com as extremidades interagiveis) e a AREA para o orcamento.

`pontos_notaveis(malha)` le a malha (bmesh), separa as regioes PLANAS
(faces coplanares vizinhas) e anda pelo contorno de cada uma medindo o
giro em cada vertice:
- QUINA: canto vivo; `angulo` = o angulo interno (90 = reta, 270 = a
  quina de dentro de um recorte em L, 135 = chanfro);
- EXTREMIDADE: onde um trecho CURVO do contorno comeca/termina (a
  tangente da curva com a reta, ou a ponta do arco);
- CENTRO: o centro do arco (circulo pelos pontos do trecho).
Os vertices do MEIO do arco sao `ruido`: o ima nao os oferece (eram
dezenas de pontos colados numa borda redonda).

Tudo em coordenadas LOCAIS da malha, guardado por assinatura da malha.
"""

import math

import bmesh, bpy
from mathutils import Vector
from bpy.types import Operator

# usados so' ao RODAR (import circular): o __init__ liga estes
# apelidos depois de carregar todos (`_ligar_modulos`)
_chapas = _modulos = None

ANGULO_PLANO_GRAUS = 0.5     # faces vizinhas abaixo disto: mesmo plano
ANGULO_VIVO_GRAUS = 30.0     # giro do contorno acima disto: quina
TOL_RETA_GRAUS = 1.0         # 90 +- isto (ou 270) = quina RETA
TETO_FACES = 20000           # malha maior: so' os vertices, sem analise
CORDAS_PARELHAS = 0.75       # arco: cordas vizinhas de tamanho parecido

_cache = {}                  # ponteiro da malha -> (assinatura, resultado)


def _assinatura(malha):
    n = len(malha.vertices)
    co = [0.0] * (n * 3)
    malha.vertices.foreach_get('co', co)
    return (n, len(malha.polygons), round(sum(co), 6), round(sum(abs(c) for c in co), 6))


def _regioes(bm):
    """Faces em regioes planas (vizinhas a menos de ANGULO_PLANO)."""
    limite = math.radians(ANGULO_PLANO_GRAUS)
    regiao = {}
    regioes = []
    for face in bm.faces:
        if face.index in regiao:
            continue
        atual, pilha, semente = [], [face], face.normal.copy()
        regiao[face.index] = len(regioes)
        while pilha:
            f = pilha.pop()
            atual.append(f)
            for aresta in f.edges:
                for outra in aresta.link_faces:
                    # contra a 1a face: superficie muito dividida nao
                    # "anda" de vizinha em vizinha ate' virar um plano so'
                    if (outra.index not in regiao
                            and semente.angle(outra.normal, 0.0) < limite):
                        regiao[outra.index] = len(regioes)
                        pilha.append(outra)
        regioes.append(atual)
    return regioes, regiao


def _lacos(faces, regiao, indice):
    """Contornos da regiao: listas ORDENADAS de vertices (na volta da
    normal), pelas arestas com uma face so' nela."""
    seguinte = {}
    for f in faces:
        for loop in f.loops:
            aresta = loop.edge
            dentro = [g for g in aresta.link_faces if regiao.get(g.index) == indice]
            if len(dentro) == 1:
                seguinte[loop.vert.index] = loop.link_loop_next.vert
    vistos, lacos = set(), []
    for inicio in list(seguinte):
        if inicio in vistos:
            continue
        laco, atual = [], inicio
        while atual not in vistos and atual in seguinte:
            vistos.add(atual)
            v = seguinte[atual]
            laco.append(v)
            atual = v.index
        if len(laco) >= 3:
            lacos.append(laco)
    return lacos


def _circulo(a, b, c):
    """Centro do circulo por 3 pontos (None se alinhados)."""
    ab, ac = b - a, c - a
    n = ab.cross(ac)
    if n.length_squared < 1e-18:
        return None
    centro = a + (n.cross(ab) * ac.length_squared + ac.cross(n) * ab.length_squared) / (
        2.0 * n.length_squared)
    return centro


def _analisar_bm(bm):
    bm.normal_update()
    bm.faces.ensure_lookup_table()
    bm.verts.ensure_lookup_table()
    regioes, regiao = _regioes(bm)
    vivo = math.radians(ANGULO_VIVO_GRAUS)
    plano = math.radians(ANGULO_PLANO_GRAUS)
    quinas = {}            # indice -> (angulo, area da regiao)
    extremidades, centros, ruido = {}, [], set()
    for i, faces in enumerate(regioes):
        area = sum(f.calc_area() for f in faces)
        normal = faces[0].normal
        # fatia de superficie curva (vizinha suave dos dois lados): os
        # cantos dela nao sao quinas -- a tampa da peca ja' traz o contorno
        suaves = 0
        for f in faces:
            for aresta in f.edges:
                fs = aresta.link_faces
                if len(fs) == 2 and (regiao[fs[0].index] == i) != (regiao[fs[1].index] == i):
                    if fs[0].normal.angle(fs[1].normal, 0.0) < vivo:
                        suaves += 1
        if suaves >= 2:
            continue
        for laco in _lacos(faces, regiao, i):
            n = len(laco)
            pts = [v.co for v in laco]
            giros = []
            for k in range(n):
                a, b, c = pts[k - 1], pts[k], pts[(k + 1) % n]
                u, w = b - a, c - b
                if u.length < 1e-9 or w.length < 1e-9:
                    giros.append(0.0)
                    continue
                giro = u.angle(w, 0.0)
                if u.cross(w).dot(normal) < 0:
                    giro = -giro           # concavo: o recorte
                giros.append(giro)
            for k, v in enumerate(laco):
                g = giros[k]
                if abs(g) > vivo:
                    interno = 180.0 - math.degrees(g)      # 90 / 270 / 135
                    anterior = quinas.get(v.index)
                    if anterior is None or area > anterior[1]:
                        quinas[v.index] = (interno, area)
            # ARCOS: o vertice do MEIO de um arco tem o mesmo centro (pelo
            # circulo dele e dos 2 vizinhos) que os vizinhos de arco; o
            # ponto de tangencia nao (um vizinho e' da reta). O trecho de
            # centro igual e' ruido; os vizinhos das pontas, que ainda
            # estao no arco, sao as EXTREMIDADES (ou a quina onde ele acaba)
            centros_k = []
            for k in range(n):
                antes = (pts[k] - pts[k - 1]).length
                depois = (pts[(k + 1) % n] - pts[k]).length
                # no arco as cordas vizinhas sao IGUAIS; a reta entre dois
                # arcos simetricos caia num circulo enorme sem isto
                parelhas = min(antes, depois) >= CORDAS_PARELHAS * max(antes, depois)
                c = (_circulo(pts[k - 1], pts[k], pts[(k + 1) % n])
                     if plano <= abs(giros[k]) <= vivo and parelhas else None)
                centros_k.append(c)

            def mesmo(a, b):
                ca, cb = centros_k[a], centros_k[b]
                if ca is None or cb is None:
                    return False
                raio = (pts[a] - ca).length
                return (ca - cb).length <= max(1e-6, 1e-3 * raio)
            if all(mesmo(k, (k + 1) % n) for k in range(n)):
                # circulo fechado: sem ponta, so' o centro
                ruido.update(v.index for v in laco)
                centros.append(centros_k[0].copy())
                continue
            inicio = next(k for k in range(n) if not mesmo(k, (k + 1) % n))
            trechos, atual = [], []
            for passo in range(1, n + 1):
                k = (inicio + passo) % n
                if centros_k[k] is not None:
                    if atual and not mesmo(atual[-1], k):
                        trechos.append(atual)
                        atual = []
                    atual.append(k)
                elif atual:
                    trechos.append(atual)
                    atual = []
            if atual:
                trechos.append(atual)
            for trecho in trechos:
                # um vertice so' nao diz nada: o circulo por 3 pontos
                # sempre passa pelos vizinhos (e' o da tangencia)
                if len(trecho) < 2:
                    continue
                centro = centros_k[trecho[0]]
                pontas = ((trecho[0] - 1) % n, (trecho[-1] + 1) % n)
                for k in trecho:
                    ruido.add(laco[k].index)
                for p in pontas:
                    if laco[p].index not in quinas:
                        extremidades[laco[p].index] = True
                centros.append(centro.copy())
    ruido -= set(quinas) | set(extremidades)
    pontos = [{'co': bm.verts[i].co.copy(), 'tipo': 'QUINA', 'angulo': round(a, 1),
               'indice': i} for i, (a, _area) in quinas.items()]
    pontos += [{'co': bm.verts[i].co.copy(), 'tipo': 'EXTREMIDADE', 'angulo': None,
                'indice': i} for i in extremidades if i not in quinas]
    pontos += [{'co': c, 'tipo': 'CENTRO', 'angulo': None, 'indice': None}
               for c in _sem_repetidos(centros)]
    return {'pontos': pontos, 'ruido': ruido}


def _sem_repetidos(pontos, tol=1e-5):
    saida = []
    for p in pontos:
        if all((p - q).length > tol for q in saida):
            saida.append(p)
    return saida


def pontos_notaveis(malha):
    """{'pontos': [{'co', 'tipo', 'angulo', 'indice'}], 'ruido': {indices}}
    da malha (coordenadas locais). Guardado por malha + assinatura."""
    if malha is None or not len(malha.polygons) or len(malha.polygons) > TETO_FACES:
        return {'pontos': [], 'ruido': set()}
    try:
        chave = malha.as_pointer()
    except ReferenceError:
        return {'pontos': [], 'ruido': set()}
    assinatura = _assinatura(malha)
    guardado = _cache.get(chave)
    if guardado is not None and guardado[0] == assinatura:
        return guardado[1]
    bm = bmesh.new()
    try:
        bm.from_mesh(malha)
        resultado = _analisar_bm(bm)
    finally:
        bm.free()
    if len(_cache) > 512:
        _cache.clear()
    _cache[chave] = (assinatura, resultado)
    return resultado


def pontos_no_mundo(obj, malha=None):
    """[(ponto de mundo, tipo, angulo)] de um objeto de malha."""
    if obj is None or obj.type != 'MESH':
        return []
    m = obj.matrix_world
    return [(m @ p['co'], p['tipo'], p['angulo'])
            for p in pontos_notaveis(malha or obj.data)['pontos']]


def rotulo(tipo, angulo):
    """Texto do ponto para a tela: 'Quina 90', 'Angulo 135', ..."""
    if tipo == 'QUINA':
        if angulo is not None and min(abs(angulo - 90.0), abs(angulo - 270.0)) <= TOL_RETA_GRAUS:
            return 'Quina reta'
        return 'Angulo %d' % round(angulo or 0.0)
    if tipo == 'EXTREMIDADE':
        return 'Fim da curva'
    if tipo == 'CENTRO':
        return 'Centro do arco'
    return ''


# ---- registro do que o ima ofereceu (para o rotulo na tela)
_rotulos = {}


def lembrar_rotulos(obj, malha=None, notaveis=None):
    """Guarda o rotulo de cada ponto notavel do objeto, pela posicao de
    mundo arredondada (o ima so' devolve o ponto)."""
    if len(_rotulos) > 50000:
        _rotulos.clear()            # cada assistente relembra o que ve
    pontos = ([(obj.matrix_world @ p['co'], p['tipo'], p['angulo'])
               for p in notaveis['pontos']] if notaveis is not None
              else pontos_no_mundo(obj, malha))
    for co, tipo, angulo in pontos:
        _rotulos[_chave_ponto(co)] = rotulo(tipo, angulo)


def _chave_ponto(co):
    return tuple(round(c, 5) for c in co)


def rotulo_do_ponto(co):
    if co is None:
        return ''
    return _rotulos.get(_chave_ponto(co), '')


def marcar_rotulo(estado, ponto):
    """Poe no estado do assistente o rotulo do ponto que o ima pegou
    (o desenho 2D o mostra ao lado da bolinha)."""
    if estado is None:
        return
    texto = rotulo_do_ponto(ponto)
    estado['rotulo_snap'] = texto
    estado['ponto_rotulo'] = ponto.copy() if (texto and ponto is not None) else None


def esquecer():
    _cache.clear()
    _rotulos.clear()


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
            conj = _modulos._conj_de(obj) if _modulos is not None else None
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
