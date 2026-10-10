"""Puxadores parametricos (perfil do usuario, alca, borda), o
posicionador e o arraste com Alt para outra borda."""

import bpy, bmesh, math, os, json, gpu
from gpu_extras.batch import batch_for_shader
from bpy.props import StringProperty
from mathutils import Matrix, Vector
from bpy_extras import view3d_utils
from bpy.types import Operator

# usados ao CARREGAR (corpo de classe, constantes): ja' carregados antes
from . import ferragens as _ferragens
# usados so' ao RODAR (import circular): o __init__ liga estes
# apelidos depois de carregar todos (`_ligar_modulos`)
_chapas = None
_modulos = None
_eventos = None
_portas = None
_gaveta_eventos = None
_importacao = None
_hud = None
_solda = None

# ======================================== PUXADORES PARAMETRICOS
# Tres modelos prontos, montados no referencial da LINHA -- a borda da
# face onde o usuario clicou: X ao longo da borda, Y da borda para dentro
# da face, Z para fora da face. O estado mora no proprio puxador (borda,
# face, fracao, recuo) e `posicionar_puxador` refaz tudo a partir das
# PROPS da chapa: nao existe medida "antiga" para errar, entao porta,
# chapa ou modulo redimensionados levam o puxador junto.
MODELOS_PUXADOR = {
    # (nome, comprimento, recuo) em mm; perfil = borda inteira
    'PERFIL': ('Perfil', 0.0, 0.0),
    'ALCA': ('Alca', 148.0, 40.0),
    'BORDA': ('Borda', 60.0, 0.0),
}
ALTURA_PERFIL_MM = 30.0     # faixa do perfil J de caixas (sem o asset)
BORDAS_CHAPA = ('X-', 'X+', 'Y-', 'Y+')
MATERIAL_PUXADOR = "Puxador"


def _caixas_puxador(tipo, espessura, comprimento):
    """Caixas (x0, x1, y0, y1, z0, z1) em mm, no referencial da linha.

    PERFIL: perfil J rente as duas faces, no lugar da faixa cortada; a
    cava do dedo fica aberta na frente, entre a aba da borda e a placa
    da frente. ALCA: barra com duas pernas, de pe' na face. BORDA: tampa
    sentada na borda com uma aba fina caindo na frente da face.
    """
    meio, e = comprimento / 2.0, espessura
    if tipo == 'PERFIL':
        h = ALTURA_PERFIL_MM
        return [(-meio, meio, h - 2, h, -e, 0),     # base na madeira
                (-meio, meio, 15, h, -2, 0),        # frente, rente a face
                (-meio, meio, 0, h, -e, -e + 2),    # costas
                (-meio, meio, 0, 2, -e, -6)]        # aba na borda
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


# ---- Puxador PERFIL de verdade: o modelo de aluminio do usuario
# (`extrair_puxador.py`), ja' no referencial da linha. O comprimento sai
# esticando so' as PONTAS (o chanfro delas fica igual) e a espessura da
# folha, escalando o que fica atras da face (a frente, o labio e a cava
# continuam do modelo). A faixa que ele tira da madeira e' a do modelo.
# Sem o asset, volta o perfil J de caixas.
ARQUIVO_PUXADOR_PERFIL = os.path.join(_ferragens.PASTA_FERRAGENS, 'puxador_perfil.blend')
_puxador_perfil = [None]     # o .json do asset, lido uma vez
_corte_perfil = [None]       # (z, vao) da secao do modelo, medido uma vez


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
    """Faixa da madeira que o perfil ocupa."""
    dados = _dados_perfil()
    return dados['altura_mm'] if dados else ALTURA_PERFIL_MM


def _malha_modelo_perfil():
    """A malha do modelo (carregada uma vez; nenhum objeto a usa)."""
    dados = _dados_perfil()
    if dados is None:
        return None
    for malha in bpy.data.meshes:
        if malha.get('cabinet_origem') == dados['malha'] and not malha.library:
            return malha
    novas = _ferragens._anexar_sem_repetir(ARQUIVO_PUXADOR_PERFIL, 'meshes',
                                {dados['malha']})
    return novas[0] if novas else None


def _corte_do_perfil(modelo):
    """(z do corte, vao) em m: onde a SECAO do perfil se divide para
    acomodar a espessura da porta -- o maior vao sem vertice entre as
    costas e a face. O que fica atras dele (cantos arredondados das
    costas) anda inteiro; so' o trecho reto do vao estica ou encolhe."""
    if _corte_perfil[0] is None:
        zs = sorted({round(v.co.z, 7) for v in modelo.vertices if v.co.z < 0.0})
        vaos = [(b - a, (a + b) / 2.0) for a, b in zip(zs, zs[1:])]
        vao, corte = max(vaos) if vaos else (0.0, 0.0)
        _corte_perfil[0] = (corte, vao)
    return _corte_perfil[0]


def _deformar_perfil(co, estica, corte, recua, fator):
    """Ponto do modelo do perfil na porta de agora (pedido do usuario: a
    medida muda, os chanfros NAO). Comprimento: cada ponta anda inteira
    (`estica`). Espessura: o que esta' atras do `corte` anda `recua`;
    sem vao que caiba (porta muito mais fina), cai na escala (`fator`)."""
    x, y, z = co
    if recua is None:
        z = z * fator if z < 0.0 else z
    elif z < corte:
        z += recua
    return Vector((x + math.copysign(estica, x), y, z))


def _ajuste_do_perfil(modelo, espessura, comprimento):
    """(estica, corte, recua, fator) do modelo para esta porta."""
    dados = _dados_perfil()
    estica = (comprimento - dados['comprimento_mm']) / 2000.0
    fator = espessura / dados['espessura_porta_mm']
    corte, vao = _corte_do_perfil(modelo)
    recua = -(espessura - dados['espessura_porta_mm']) / 1000.0
    # porta mais FINA que o modelo: o trecho reto encolhe ate' quase
    # sumir; mais que isso as costas passariam da face
    if recua > 0.9 * vao:
        recua = None
    return estica, corte, recua, fator


def _malha_perfil_do_modelo(pux, modelo, espessura, comprimento):
    ajuste = _ajuste_do_perfil(modelo, espessura, comprimento)
    bm = bmesh.new()
    bm.from_mesh(modelo)
    for v in bm.verts:
        v.co = _deformar_perfil(v.co, *ajuste)
    bm.to_mesh(pux.data)
    bm.free()
    pux.data.update()
    pux.data.materials.clear()
    for material in modelo.materials:
        pux.data.materials.append(material)


def gerar_malha_puxador(pux, espessura, comprimento):
    """Malha real por bmesh, como a da chapa (nada de escala)."""
    if pux['puxador_tipo'] == 'PERFIL':
        modelo = _malha_modelo_perfil()
        if modelo is not None:
            _malha_perfil_do_modelo(pux, modelo, espessura, comprimento)
            return
    bm = bmesh.new()
    for x0, x1, y0, y1, z0, z1 in _caixas_puxador(
            pux['puxador_tipo'], espessura, comprimento):
        cubo = bmesh.ops.create_cube(bm, size=1.0)
        for v in cubo['verts']:
            v.co = Vector(((x0 + x1) / 2 + v.co.x * (x1 - x0),
                           (y0 + y1) / 2 + v.co.y * (y1 - y0),
                           (z0 + z1) / 2 + v.co.z * (z1 - z0))) / 1000.0
    bm.to_mesh(pux.data)
    bm.free()
    pux.data.update()
    if not pux.data.materials:
        pux.data.materials.append(_material_puxador())


def _referencial_da_linha(chapa, borda, face):
    """(ao_longo, dentro, fora, ponto, tamanho) no espaco LOCAL da chapa.

    `ponto` e' o meio da borda, na superficie da face; `tamanho` o
    comprimento da borda em metros. Os tres vetores formam base direita
    (ao_longo = dentro x fora), entao a malha nunca sai invertida.
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
    """Refaz malha e lugar do puxador a partir da chapa pai.

    Comprimento fixo (perfil: a borda inteira), centro na FRACAO da
    borda -- o que estava no meio continua no meio --, recuo fixo da
    linha. Preso nas pontas: nunca passa da borda.
    """
    chapa = pux.parent
    if not _eh_puxador_parametrico(pux) or chapa is None or _chapas.MARCA_CHAPA not in chapa:
        return False
    tipo = pux['puxador_tipo']
    matriz, comprimento = _lugar_do_puxador(
        chapa, tipo, pux.get('puxador_borda', 'Y+'),
        int(pux.get('puxador_face', 1)), float(pux.get('puxador_fracao', 0.5)),
        pux.get('puxador_comprimento_mm'), pux.get('puxador_recuo_mm'))
    _ferragens._padronizar_nome(pux, "Puxador " + MODELOS_PUXADOR[tipo][0])
    gerar_malha_puxador(pux, chapa.chapa_espessura_mm, comprimento)
    pux.matrix_parent_inverse = Matrix.Identity(4)
    pux.matrix_basis = matriz
    return True


def _lugar_do_puxador(chapa, tipo, borda, face, fracao, comprimento=None,
                      recuo=None):
    """(matriz no espaco LOCAL da chapa, comprimento em mm) do puxador
    naquela linha -- o MESMO calculo para o objeto e para a previa."""
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


def _rebaixos_da_chapa(chapa):
    """{borda: metros} que os perfis filhos tiram da madeira."""
    return {f.get('puxador_borda', 'Y+'): _altura_perfil_mm() / 1000.0
            for f in chapa.children
            if _eh_puxador_parametrico(f) and f['puxador_tipo'] == 'PERFIL'}


def _conferir_rebaixos():
    """Perfil apagado (X) ou movido: a chapa devolve a madeira.

    Sem isto a faixa cortada ficava vazia ate' a proxima mudanca de
    medida. So' olha quem tem `chapa_rebaixos`, entao custa pouco.
    """
    for obj in bpy.data.objects:
        gravado = obj.get('chapa_rebaixos')
        if gravado is None:
            continue
        if set(filter(None, gravado.split(','))) != set(_rebaixos_da_chapa(obj)):
            _chapas.gerar_malha_chapa(obj)


def criar_puxador(context, chapa, tipo, borda, face, fracao=0.5):
    """Puxador novo pendurado na chapa (folha ou avulsa), ja' no lugar."""
    nome = "Puxador " + MODELOS_PUXADOR[tipo][0]
    pux = bpy.data.objects.new(nome, bpy.data.meshes.new(nome))
    (chapa.users_collection[0] if chapa.users_collection
     else context.collection).objects.link(pux)
    pux[_chapas.MARCA_PUXADOR] = 1
    pux['puxador_tipo'] = tipo
    pux['puxador_borda'] = borda
    pux['puxador_face'] = 1 if face >= 0 else -1
    pux['puxador_fracao'] = max(0.0, min(1.0, float(fracao)))
    pux['puxador_comprimento_mm'] = MODELOS_PUXADOR[tipo][1]
    pux['puxador_recuo_mm'] = MODELOS_PUXADOR[tipo][2]
    pux.parent = chapa
    if tipo == 'PERFIL':
        # um perfil por borda: o novo substitui o velho
        for velho in [f for f in chapa.children if f != pux
                      and _eh_puxador_parametrico(f)
                      and f['puxador_tipo'] == 'PERFIL'
                      and f.get('puxador_borda') == borda]:
            bpy.data.objects.remove(velho, do_unlink=True)
        _chapas.gerar_malha_chapa(chapa)        # corta a madeira e posiciona
    else:
        posicionar_puxador(pux)
    return pux


def _medidas_puxador_parametrico(pux):
    """Campos do bloco de medidas: comprimento e recuo, sem cadeado.

    O perfil nao tem o que editar (borda inteira, faixa fixa): a altura
    aparece so' para leitura (prop vazia = campo apagado).
    """
    tipo = pux['puxador_tipo']
    if tipo == 'PERFIL':
        return [('Altura do perfil', _altura_perfil_mm(), '')]
    campos = [('Comprimento', float(pux.get('puxador_comprimento_mm',
                                            MODELOS_PUXADOR[tipo][1])),
               'puxp_comprimento')]
    if tipo == 'ALCA':
        campos.append(('Recuo', float(pux.get('puxador_recuo_mm',
                                              MODELOS_PUXADOR[tipo][2])),
                       'puxp_recuo'))
    return campos


# ---- ferramenta: clica numa linha, escolhe o ponto, scroll = snaps
_posicionador_puxador = [None]      # estado lido pelo desenho
_handler_posicionador = [None]
MAXIMO_SNAPS_PUXADOR = 15


def _snaps(n):
    """n subdivisoes da linha: 1 = centro, 2 = tercos, 3 = quartos..."""
    return [k / (n + 1) for k in range(1, n + 1)]


def _fracao_na_linha(a, b, mouse, n=0):
    """Mouse projetado no segmento a-b da tela; n >= 1 gruda no snap."""
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
    """{borda: (a, b) na tela} -> a borda mais perto do mouse."""
    if not segmentos:
        return None
    return min(segmentos, key=lambda b: _distancia_ao_segmento(
        mouse, *segmentos[b]))


def _bordas_da_face(chapa, face):
    """{borda: (ponta da fracao 0, ponta da fracao 1)} em MUNDO."""
    mundo = chapa.matrix_world
    bordas = {}
    for borda in BORDAS_CHAPA:
        ao_longo, _dentro, _fora, ponto, tamanho = _referencial_da_linha(
            chapa, borda, face)
        meio = ao_longo * (tamanho / 2.0)
        bordas[borda] = (mundo @ (ponto - meio), mundo @ (ponto + meio))
    return bordas


def _face_da_chapa(chapa, normal, direcao_vista):
    """+1 frente / -1 verso. Batendo na face estreita, vale a grande que
    esta' mais virada para quem olha."""
    eixo_z = chapa.matrix_world.to_3x3().col[2].normalized()
    local = chapa.matrix_world.to_3x3().inverted() @ normal
    if abs(local.z) >= max(abs(local.x), abs(local.y)):
        return 1 if local.z >= 0 else -1
    return 1 if eixo_z.dot(-direcao_vista) >= 0 else -1


def _quad_2d(a, b, largura):
    """Linha grossa em triangulos (line_width trava em 1 px em drivers)."""
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
                # riscos dos snaps atravessando a linha
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
                    texto += '  (scroll: snaps)'
                _hud._caixa_texto_hud(ponto.x + 14 * escala, ponto.y + 14 * escala,
                                 texto, 13 * escala, escala)
    finally:
        gpu.state.blend_set('NONE')


class OBJECT_OT_posicionar_puxador(Operator):
    """Clique numa borda da porta ou chapa; depois escolha o ponto nela
    (scroll para cima cria snaps: centro, tercos, quartos...)"""
    bl_idname = "object.cabinet_posicionar_puxador"
    bl_label = "Criar Puxador"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def invoke(self, context, event):
        alvo = _importacao._viewport_alvo(context)
        if alvo is None:
            self.report({'ERROR'}, "Sem viewport 3D para posicionar")
            return {'CANCELLED'}
        self._area, self._regiao, self._rv3d = alvo
        # a previa do perfil e' o arame do modelo: carregado aqui (no
        # desenho nao se carrega nada)
        _malha_modelo_perfil()
        _ferragens._ferragens_selecionadas[0] = None    # criar encerra aquela selecao
        self._estado = {'regiao': self._regiao.as_pointer(), 'fase': 'LINHA',
                        'tipo': context.scene.cabinet_puxador_modelo,
                        'chapa': None, 'face': 1, 'borda': None,
                        'segmentos': {}, 'n': 0, 'fracao': 0.5, 'pux': None}
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
            texto = ("Puxador %s: clique na BORDA onde ele vai | Esc cancela"
                     % MODELOS_PUXADOR[self._estado['tipo']][0])
        else:
            texto = ("Escolha o ponto | Scroll: snaps (%d) | Clique confirma"
                     " | Botao direito: outra borda" % self._estado['n'])
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
        acertou, _p, normal, _f, obj, _m = context.scene.ray_cast(
            context.evaluated_depsgraph_get(), origem, direcao)
        chapa = obj.original if acertou and obj is not None else None
        if chapa is not None and _chapas.MARCA_PUXADOR in chapa:
            chapa = chapa.parent        # mirou no puxador: vale a chapa dele
        if chapa is None or _chapas.MARCA_CHAPA not in chapa:
            estado.update(chapa=None, borda=None, segmentos={})
            return
        estado['chapa'] = chapa.name
        estado['face'] = _face_da_chapa(chapa, normal, direcao)
        estado['segmentos'] = _bordas_da_face(chapa, estado['face'])
        projetados = self._projetados()
        estado['borda'] = _borda_mais_proxima(projetados, mouse)
        if estado['borda'] in projetados:
            # a previa (arame) do puxador acompanha o mouse na linha
            estado['fracao'] = _fracao_na_linha(
                *projetados[estado['borda']], mouse, estado['n'])

    def _mover_puxador(self, mouse):
        estado = self._estado
        a, b = self._projetados().get(estado['borda'], (None, None))
        if a is None:
            return
        estado['fracao'] = _fracao_na_linha(a, b, mouse, estado['n'])
        pux = bpy.data.objects.get(estado['pux'] or '')
        if pux is not None:
            pux['puxador_fracao'] = estado['fracao']
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

    def _trocar_modelo(self, context, tipo):
        """Modelo escolhido na gaveta durante o posicionamento: o puxador
        de previa (se ja' ha') e' refeito no mesmo ponto; perfil e' a
        borda inteira, entao fica pronto na hora."""
        estado = self._estado
        if tipo not in MODELOS_PUXADOR or tipo == estado['tipo']:
            return None
        estado['tipo'] = tipo
        context.scene.cabinet_puxador_modelo = tipo   # a proxima vem igual
        chapa = bpy.data.objects.get(estado['chapa'] or '')
        if estado['fase'] == 'POSICAO' and chapa is not None:
            self._apagar_previa()
            pux = criar_puxador(context, chapa, tipo, estado['borda'],
                                estado['face'], estado['fracao'])
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
            self._engolir_soltar = False     # o soltar do clique na gaveta
            return {'RUNNING_MODAL'}
        gaveta = (_gaveta_eventos._gaveta_sob_evento(context, event)
                  if event.type != 'ESC' else None)
        if gaveta is not None:
            # a gaveta continua dela; o posicionador so' atende o modelo
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
            return {'PASS_THROUGH'}        # orbitar/zoom continuam
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
                            estado['face'], estado['fracao'])
        if estado['tipo'] == 'PERFIL':
            return self._confirmar(context, pux)    # borda inteira: pronto
        estado['pux'] = pux.name
        estado['fase'] = 'POSICAO'
        self._dica(context)
        return {'RUNNING_MODAL'}


def _trocar_modelo_puxador(pux, tipo):
    """O modelo do puxador SELECIONADO trocado na gaveta: refaz ele na
    mesma borda e ponto. Perfil corta a madeira (a chapa refaz) e e' um
    por borda, como no `criar_puxador`."""
    if not _eh_puxador_parametrico(pux) or tipo not in MODELOS_PUXADOR:
        return
    antes = pux['puxador_tipo']
    chapa = pux.parent
    if antes == tipo or chapa is None or _chapas.MARCA_CHAPA not in chapa:
        return
    pux['puxador_tipo'] = tipo
    pux['puxador_comprimento_mm'] = MODELOS_PUXADOR[tipo][1]
    pux['puxador_recuo_mm'] = MODELOS_PUXADOR[tipo][2]
    # o material do perfil (aluminio do usuario) nao fica no de caixas
    pux.data.materials.clear()
    if tipo == 'PERFIL':
        for velho in [f for f in chapa.children if f != pux
                      and _eh_puxador_parametrico(f)
                      and f['puxador_tipo'] == 'PERFIL'
                      and f.get('puxador_borda') == pux.get('puxador_borda')]:
            bpy.data.objects.remove(velho, do_unlink=True)
    if 'PERFIL' in (antes, tipo):
        _chapas.gerar_malha_chapa(chapa)        # corta/devolve a madeira e posiciona
    else:
        posicionar_puxador(pux)


# ---- puxador: Alt + arrastar a ancora leva-o a outra borda do GRUPO
# (pedido do usuario): so' as chapas onde ele foi colocado -- as folhas da
# porta, ou as chapas do modulo. Snap de LINHA: gruda na borda mais perto
# do mouse (na face virada para quem olha) e sai virado conforme ela
# (`_referencial_da_linha`), como o posicionador faria ali.
_arraste_puxador = [None]    # {'puxador', 'linhas': [(a, b) mundo], 'escolhida'}


def _chapas_do_grupo_do_puxador(chapa):
    grupo = _portas._grupo_portas(chapa)
    if grupo is not None:
        return _portas._folhas_portas(grupo)
    modulo = _portas._modulo_da_chapa(chapa)
    if modulo is not None:
        return _modulos._chapas_do_conjunto(modulo)
    return _modulos.grupo_de(chapa) or [chapa]


def _puxadores_com_ancora(context):
    """Puxadores do add-on da selecao (ele mesmo, ou os das chapas/folhas
    selecionadas): os que mostram a ancora com Alt."""
    saida = []
    for o in getattr(context, 'selected_objects', ()) or ():
        for p in ([o] if _eh_puxador_parametrico(o) else o.children):
            if (_eh_puxador_parametrico(p) and p not in saida
                    and p.parent is not None and _chapas.MARCA_CHAPA in p.parent):
                saida.append(p)
    return saida


def _ancora_do_puxador(pux):
    """Onde o puxador ancora: o ponto dele NA borda (mundo)."""
    matriz, _c = _lugar_do_puxador(
        pux.parent, pux['puxador_tipo'], pux.get('puxador_borda', 'Y+'),
        int(pux.get('puxador_face', 1)), float(pux.get('puxador_fracao', 0.5)),
        pux.get('puxador_comprimento_mm'), 0.0)
    return pux.parent.matrix_world @ matriz.translation


def _puxador_sob_mouse(context, posicao):
    """O puxador cuja ancora esta' sob o mouse (so' com Alt), ou None."""
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
    """Com Alt: a bolinha branca na ancora de cada puxador da selecao.
    Arrastando: as bordas do grupo (a escolhida acesa) e a ancora."""
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


class OBJECT_OT_arrastar_puxador(Operator):
    """Arraste a ancora do puxador (Alt) ate' outra borda do mesmo grupo: ele gruda na linha e vira com ela"""
    bl_idname = 'object.cabinet_arrastar_puxador'
    bl_label = 'Mover Puxador'
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
        """(chapa, borda, face, fracao) da borda do grupo mais perto do
        mouse, na face virada para quem olha."""
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
                    melhor = (d, len(linhas) - 1, nome, borda, face,
                              _fracao_na_linha(a2, b2, mouse))
        estado['linhas'] = linhas
        estado['escolhida'] = melhor[1] if melhor else None
        return melhor[2:] if melhor else None

    def _aplicar(self, context, nome, borda, face, fracao):
        pux = bpy.data.objects.get(self.puxador)
        chapa = bpy.data.objects.get(nome)
        if pux is None or chapa is None:
            return
        antiga = pux.parent
        mesma_linha = (antiga == chapa and pux.get('puxador_borda') == borda
                       and int(pux.get('puxador_face', 1)) == face)
        if mesma_linha and abs(float(pux.get('puxador_fracao', 0.5))
                               - fracao) < 1e-4:
            return
        if antiga != chapa:
            pux.parent = chapa
        pux['puxador_borda'] = borda
        pux['puxador_face'] = face
        pux['puxador_fracao'] = max(0.0, min(1.0, float(fracao)))
        if pux['puxador_tipo'] == 'PERFIL':
            if not mesma_linha:
                # a madeira volta na chapa velha e sai na nova
                if antiga is not None and antiga != chapa:
                    _chapas.gerar_malha_chapa(antiga)
                _chapas.gerar_malha_chapa(chapa)
        else:
            posicionar_puxador(pux)
        context.view_layer.update()

    def _encerrar(self):
        _arraste_puxador[0] = None
        self._area.tag_redraw()

    def cancel(self, context):
        self._aplicar(context, *self._antes)
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
                self._aplicar(context, *achado)
            self._area.tag_redraw()
            return {'RUNNING_MODAL'}
        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            pux = bpy.data.objects.get(self.puxador)
            if (pux is not None and pux['puxador_tipo'] == 'PERFIL'
                    and pux.parent is not None):
                # um perfil por borda, como no criar: o que ja' estava sai
                for velho in [f for f in pux.parent.children if f != pux
                              and _eh_puxador_parametrico(f)
                              and f['puxador_tipo'] == 'PERFIL'
                              and f.get('puxador_borda')
                              == pux.get('puxador_borda')]:
                    bpy.data.objects.remove(velho, do_unlink=True)
                _chapas.gerar_malha_chapa(pux.parent)
            self._encerrar()
            return {'FINISHED'}
        return {'RUNNING_MODAL'}
