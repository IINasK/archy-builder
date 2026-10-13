"""Porta selecionada na viewport: cantos (Alt) e slider de abertura."""

import bpy, gpu, blf
from gpu_extras.batch import batch_for_shader
from bpy.props import (FloatProperty, BoolProperty, StringProperty,
                       IntProperty, FloatVectorProperty)
from mathutils import Matrix, Vector
from bpy.types import Gizmo, GizmoGroup, Operator

# usados so' ao RODAR (import circular): o __init__ liga estes
# apelidos depois de carregar todos (`_ligar_modulos`)
_chapas = None
_eventos = None
_portas = None
_ferragens = None
_puxadores = None
_hud = None
_solda = None
_perguntas = None

# ------------------------------------------ os 4 cantos da porta
# Pedido do usuario: clique simples na porta mostra os fios do wizard
# (laranja = cobertura, branco = vao) e, com Alt, as 4 bolinhas viram
# alcas: arrastar um canto ate' outro vertice refaz a porta como se os
# 4 cliques tivessem sido dados ali (cobertura e dobradica automaticas).
# Os cantos nao sao gravados: saem da porta (vao + cobertura de cada
# lado), entao acompanham o modulo quando ele muda.
_arraste_canto_porta = [None]    # estado do arraste de um canto


def _porta_veio_do_modulo(grupo):
    """A porta esta' selecionada so' porque o MODULO dela esta' (clique nas
    chapas). Ai' nada da porta se desenha -- dobradicas, linhas do vao,
    diagonal, cantos, sliders (pedido do usuario: visao mais limpa); a
    HUD do modulo ja' mostra o contorno dela."""
    modulo = grupo.parent
    while modulo is not None and _chapas.MARCA_CONJUNTO not in modulo:
        modulo = modulo.parent
    return modulo is not None and modulo.select_get()


def _portas_com_cantos(context):
    """Portas selecionadas INTEIRAS (clique simples, nao a folha) por si
    mesmas, nao junto com o modulo."""
    return [o for o in getattr(context, 'selected_objects', ()) or ()
            if _chapas.MARCA_PORTAS in o and o.get('porta_parametros')
            and o.get('porta_vao_largura_mm') is not None
            and not _porta_veio_do_modulo(o)]


def _folhas_com_contorno(context):
    """Folhas selecionadas SEM a porta inteira (duplo clique): o contorno
    nativo esta' desligado, entao sem o branco do add-on parecia que nada
    tinha sido selecionado (pedido do usuario)."""
    selecionados = getattr(context, 'selected_objects', ()) or ()
    saida = []
    for o in selecionados:
        grupo = (_portas._grupo_portas(o) if _chapas.MARCA_FOLHA in o
                 else None)
        if (grupo is not None and not grupo.select_get()
                and not _porta_veio_do_modulo(grupo)):
            saida.append(o)
    return saida


def _caixa_da_folha(folha):
    """8 cantos (MUNDO) da folha, na ordem de `ARESTAS_CAIXA`."""
    l, a, e, _centro = _ferragens._dados_da_folha(folha)
    meia = Vector((l, a, e)) / 2000.0
    return [folha.matrix_world @ Vector((meia.x * sx, meia.y * sy, meia.z * sz))
            for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]


def _cantos_da_porta(grupo):
    """Os 4 pontos do wizard em MUNDO, na ordem dos cliques: canto da
    porta e do vao em cima a esquerda, do vao e da porta embaixo a
    direita (o desenho do usuario)."""
    p = grupo['porta_parametros']
    L = float(grupo['porta_vao_largura_mm'])
    A = float(grupo['porta_vao_altura_mm'])
    # o ponto CLICADO (meio da espessura), nao a borda da folha: a meia
    # chapa recua o respiro, e o canto arrastado com Alt tem de reconhecer
    # a meia de novo
    padrao = (0.0 if p.get('abertura') == 'CORRER' else
              {'RETA': 1.0, 'CURVA': 0.5}.get(p.get('dobradica'), 0.0))
    lateral = float(p['lateral_mm'])
    cob = [float(p[k]) * lateral if k in p else padrao * lateral
           for k in _portas.COBERTURAS_LADOS]
    m = grupo.matrix_world
    return [m @ (Vector((x, y, 0.0)) / 1000.0) for x, y in (
        (-cob[0], A + cob[3]), (0.0, A), (L, 0.0), (L + cob[1], -cob[2]))]


def _coberturas_da_porta(grupo):
    p = grupo.get('porta_parametros') or {}
    return {k: float(p[k]) for k in _portas.COBERTURAS_LADOS if k in p}


def _canto_porta_sob_mouse(context, posicao):
    """(grupo, indice) da bolinha de canto sob o mouse (so' com Alt)."""
    if not _solda._correntes_visiveis():
        return None, None
    raio = _solda.RAIO_BOLINHA_PX * max(1.0, context.preferences.system.ui_scale)
    mouse = Vector(posicao)
    melhor = None
    for grupo in _portas_com_cantos(context):
        for i, ponto in enumerate(_cantos_da_porta(grupo)):
            p = _hud._projetar_hud(context, ponto)
            if p is None:
                continue
            d = (p - mouse).length
            if d <= raio and (melhor is None or d < melhor[0]):
                melhor = (d, grupo, i)
    return (melhor[1], melhor[2]) if melhor else (None, None)


COR_LINHAS_VAO = (1.0, 0.85, 0.1, 1.0)      # amarelo: o vao (pedido do usuario)


def _desenho_da_porta(grupo):
    """O que a porta selecionada mostra, em MUNDO: a caixa de cada folha
    e o retangulo do vao (faces internas das chapas). As ferragens nao:
    so' aparecem criando ou SELECIONADAS (`_arame_ferragens`).
    Refeito da porta a cada desenho: acompanha o modulo."""
    p = dict(grupo['porta_parametros'])
    L = float(grupo['porta_vao_largura_mm'])
    A = float(grupo['porta_vao_altura_mm'])
    m = grupo.matrix_world
    mundo = lambda v: m @ (Vector(v) / 1000.0)
    desenho = {'folhas': [],
               'vao': [mundo((x, y, 0.0)) for x, y in
                       ((0, 0), (L, 0), (L, A), (0, A))]}
    try:
        folhas = _portas._calcular_folhas_portas(L, A, p)
    except (ValueError, KeyError, TypeError):
        return desenho
    objetos = _portas._folhas_portas(grupo)
    for i, (l, alt, e, centro) in enumerate(folhas):
        meia = Vector((l, alt, e)) / 2000.0
        # pela folha de verdade: o contorno abre junto com ela
        matriz = (objetos[i].matrix_world if i < len(objetos)
                  else m @ Matrix.Translation(Vector(centro) / 1000.0))
        desenho['folhas'].append([matriz @ Vector((meia.x * sx, meia.y * sy,
                                                   meia.z * sz))
                                  for sx in (-1, 1) for sy in (-1, 1)
                                  for sz in (-1, 1)])
    return desenho


def _desenhar_cantos_porta(context):
    """Porta selecionada (print do usuario): contorno branco das folhas,
    linhas internas do vao em amarelo, os fios dos 4 cantos e, com Alt
    (ou arrastando), as 4 bolinhas brancas. As dobradicas nao (pedido do
    usuario): so' criando ou com elas selecionadas."""
    portas = _portas_com_cantos(context)
    folhas = _folhas_com_contorno(context)
    if not (portas or folhas):
        return
    estado = _arraste_canto_porta[0]
    escala = max(1.0, context.preferences.system.ui_scale)
    realce = _hud._cor_realce_hud()
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    gpu.state.blend_set('ALPHA')
    try:
        shader.bind()
        for folha in folhas:
            # so' a folha: sem vao, fios nem cantos (sao da porta inteira)
            tela = [_hud._projetar_hud(context, v) for v in _caixa_da_folha(folha)]
            if any(v is None for v in tela):
                continue
            shader.uniform_float('color', _portas.COR_FIO_VAO)
            for i, j in _portas.ARESTAS_CAIXA:
                batch_for_shader(shader, 'TRIS', {'pos': _puxadores._quad_2d(
                    tela[i], tela[j], 1.4 * escala)}).draw(shader)
        for grupo in portas:
            desenho = _desenho_da_porta(grupo)
            contornos = [(caixa, _portas.ARESTAS_CAIXA, _portas.COR_FIO_VAO)
                         for caixa in desenho['folhas']]
            contornos.append((desenho['vao'], ((0, 1), (1, 2), (2, 3), (3, 0)),
                              COR_LINHAS_VAO))
            for pontos, arestas, cor in contornos:
                tela = [_hud._projetar_hud(context, v) for v in pontos]
                if any(v is None for v in tela):
                    continue
                shader.uniform_float('color', cor)
                for i, j in arestas:
                    batch_for_shader(shader, 'TRIS', {'pos': _puxadores._quad_2d(
                        tela[i], tela[j], 1.4 * escala)}).draw(shader)
            arrastando = estado is not None and estado['grupo'] == grupo.name
            pontos = estado['pontos'] if arrastando else _cantos_da_porta(grupo)
            tela = [_hud._projetar_hud(context, p) for p in pontos]
            if any(p is None for p in tela):
                continue
            for i in range(3):
                shader.uniform_float('color', _portas.COR_FIO_VAO if i == 1
                                     else _portas.COR_FIO_COBERTURA)
                batch_for_shader(shader, 'TRIS', {'pos': _puxadores._quad_2d(
                    tela[i], tela[i + 1], 2.0 * escala)}).draw(shader)
            if not (arrastando or _solda._correntes_visiveis()):
                continue
            for i, p in enumerate(tela):
                aceso = arrastando and i == estado['indice']
                if aceso:
                    _hud._bolinha_2d(shader, p, 8 * escala, realce)
                _hud._bolinha_2d(shader, p, (6 if aceso else 5) * escala,
                            (1.0, 1.0, 1.0, 1.0))
            if arrastando and estado.get('alvo') is None:
                _hud._bolinha_2d(shader, estado['mouse'], 4 * escala, realce)
    finally:
        gpu.state.blend_set('NONE')


def _dentro_da_porta(obj, grupo):
    while obj is not None:
        if obj == grupo:
            return True
        obj = obj.parent
    return False


def _mover_cantos_porta(context, grupo, pontos, objetos=(None,) * 4):
    """Refaz a porta pelos 4 pontos (mundo), como o wizard faria."""
    modulo = bpy.data.objects.get(grupo.get(_portas.CHAVE_MODULO_PORTA, ''))
    if modulo is not None and _chapas.MARCA_CONJUNTO not in modulo:
        modulo = None
    referencia = (modulo.matrix_world.to_quaternion().to_matrix()
                  if modulo is not None else Matrix.Identity(3))
    valores = tuple(v for linha in referencia for v in linha)
    pai = modulo if modulo is not None else grupo.parent
    folha = (_portas._folhas_portas(grupo) or [None])[0]
    resultado = bpy.ops.object.cabinet_portas(
        'EXEC_DEFAULT', capturado=True, grupo_alvo=grupo.name,
        ponto_a=pontos[1], ponto_b=pontos[2], quatro_pontos=True,
        porta_a=pontos[0], porta_b=pontos[3],
        objeto_a_nome=objetos[1].name if objetos[1] is not None else '',
        objeto_b_nome=objetos[2].name if objetos[2] is not None else '',
        referencia=valores, referencia_ativa=valores,
        pai_nome=pai.name if pai is not None else '',
        modulo_nome=modulo.name if modulo is not None else '',
        orientacao='AUTO', frente=grupo.get('porta_frente', 'NEG_Y'))
    # quem cria deixa o MODULO ativo; aqui a porta continua selecionada
    # para o usuario seguir ajustando
    folha = (_portas._folhas_portas(grupo) or [folha])[0]
    if folha is not None:
        _hud._selecionar_porta_hud(context, folha, 'PORTA')
    return resultado


def _aplicar_cantos_porta(context, grupo, pontos, objetos, antigos):
    """Arraste solto: refaz a porta e, se a cobertura sair do padrao,
    pergunta (viewport: pop-up). "Nao" volta os cantos de antes."""
    resultado = _mover_cantos_porta(context, grupo, pontos, objetos)
    if 'FINISHED' not in resultado:
        return resultado
    if _portas._lados_fora_do_padrao(_coberturas_da_porta(grupo)):
        planos = tuple(v for p in antigos for v in p)
        _perguntas._perguntar(context, 'As medidas estao corretas?', [
            ('Sim', 'CHECKMARK', 'object.cabinet_cantos_porta',
             {'grupo': grupo.name, 'manter': True}),
            ('Nao', 'X', 'object.cabinet_cantos_porta',
             {'grupo': grupo.name, 'pontos': planos})], na_gaveta=False)
    return resultado


class OBJECT_OT_cantos_porta(Operator):
    """Refaz a porta pelos 4 cantos (resposta do "As medidas estao corretas?")"""
    bl_idname = 'object.cabinet_cantos_porta'
    bl_label = 'Cantos da Porta'
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}

    grupo: StringProperty(options={'SKIP_SAVE'})
    pontos: FloatVectorProperty(size=12, options={'SKIP_SAVE'})
    manter: BoolProperty(options={'SKIP_SAVE'})

    def execute(self, context):
        grupo = bpy.data.objects.get(self.grupo)
        if grupo is None or _chapas.MARCA_PORTAS not in grupo:
            return {'CANCELLED'}
        if self.manter:
            return {'FINISHED'}
        v = list(self.pontos)
        pontos = [Vector(v[i:i + 3]) for i in range(0, 12, 3)]
        return _mover_cantos_porta(context, grupo, pontos)


class OBJECT_OT_arrastar_canto_porta(Operator):
    """Arraste um dos 4 cantos da porta (Alt) ate' outro vertice: a porta se refaz por ele"""
    bl_idname = 'object.cabinet_arrastar_canto_porta'
    bl_label = 'Mover Canto da Porta'
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}

    grupo: StringProperty(options={'SKIP_SAVE'})
    indice: IntProperty(options={'SKIP_SAVE'})

    def invoke(self, context, event):
        grupo = bpy.data.objects.get(self.grupo)
        if (grupo is None or _chapas.MARCA_PORTAS not in grupo
                or not 0 <= self.indice < 4 or context.region is None):
            return {'CANCELLED'}
        # vertices lidos UMA vez (como no wizard); a propria porta nao
        # serve de ima para si mesma
        self._alvos = [(o, vs) for o, vs in _portas._alvos_do_ima(context)
                       if not _dentro_da_porta(o, grupo)]
        self._antigos = _cantos_da_porta(grupo)
        _arraste_canto_porta[0] = {
            'regiao': context.region.as_pointer(), 'grupo': grupo.name,
            'indice': self.indice, 'pontos': list(self._antigos),
            'alvo': None, 'objeto': None,
            'mouse': Vector((event.mouse_region_x, event.mouse_region_y))}
        self._area = context.area
        context.window_manager.modal_handler_add(self)
        self._area.tag_redraw()
        return {'RUNNING_MODAL'}

    def _encerrar(self):
        estado, _arraste_canto_porta[0] = _arraste_canto_porta[0], None
        self._area.tag_redraw()
        return estado

    def cancel(self, context):
        self._encerrar()

    def _imantar(self, context, mouse):
        melhor = None
        for obj, vertices in self._alvos:
            for co in vertices:
                p = _hud._projetar_hud(context, co)
                if p is None:
                    continue
                d = (p - mouse).length
                if d <= _portas.RAIO_IMA_PX and (melhor is None or d < melhor[0]):
                    melhor = (d, co, obj)
        return (melhor[1], melhor[2]) if melhor else (None, None)

    def modal(self, context, event):
        estado = _arraste_canto_porta[0]
        if estado is None:
            return {'CANCELLED'}
        mouse = Vector((event.mouse_region_x, event.mouse_region_y))
        if event.type in {'ESC', 'RIGHTMOUSE'}:
            self._encerrar()
            return {'CANCELLED'}
        if event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            return {'PASS_THROUGH'}
        if event.type == 'MOUSEMOVE':
            alvo, obj = self._imantar(context, mouse)
            estado.update(mouse=mouse, alvo=alvo, objeto=obj)
            pontos = list(self._antigos)
            if alvo is not None:
                pontos[self.indice] = alvo
            estado['pontos'] = pontos
            self._area.tag_redraw()
            return {'RUNNING_MODAL'}
        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            alvo, obj = self._imantar(context, mouse)
            if alvo is None:
                alvo, obj = estado.get('alvo'), estado.get('objeto')
            self._encerrar()
            if alvo is None or (alvo - self._antigos[self.indice]).length < 1e-6:
                return {'CANCELLED'}
            grupo = bpy.data.objects.get(self.grupo)
            if grupo is None:
                return {'CANCELLED'}
            pontos = list(self._antigos)
            pontos[self.indice] = alvo
            objetos = [None] * 4
            objetos[self.indice] = obj
            resultado = _aplicar_cantos_porta(context, grupo, pontos, objetos,
                                              self._antigos)
            return {'FINISHED'} if 'FINISHED' in resultado else {'CANCELLED'}
        return {'RUNNING_MODAL'}


# ------------------------------------------ slider de abertura (Epico 4)
# Um por folha, so' com a porta (ou a folha) selecionada: na BASE da folha
# FECHADA, um pouco a' frente (fica parado enquanto ela abre, entao nao
# foge do mouse) e por cima de tudo (raio-X). Arrastar para a direita
# abre, para a esquerda fecha -- seja qual for o lado da dobradica.
# Grosso (pedido do usuario) e recuado das pontas da folha: em porta dupla
# os dois nunca se encostam no meio, sobra uma folga entre eles.
SLIDER_FRENTE_MM = 30.0
SLIDER_RECUO_MM = 40.0           # de cada ponta da folha (min.)
SLIDER_RECUO_FRACAO = 0.12       # ... ou esta fracao da largura
SLIDER_DEGRAU_MM = 40.0          # correr: um slider acima do outro, por trilho
# Medidas em MM do mundo (pedido do usuario): longe, o slider encolhe na
# mesma proporcao da porta; perto, para no teto (2x). Calibrado na vista
# normal de um modulo (~1 px/mm): o desenho aprovado pelo usuario.
SLIDER_ESPESSURA_MM = 13.0       # altura do trilho
SLIDER_BOTAO_MM = 12.0           # raio da bolinha = o alcance do clique
SLIDER_TEXTO_MM = 13.0           # altura do valor
SLIDER_PX_POR_MM_MAX = 2.0       # teto da escala (por ui_scale)
SLIDER_TEXTO_MIN_PX = 7.0        # menor que isto o valor nao se le: some
SIMBOLO_GRAU = chr(0xB0)         # codigo so' em ASCII
_arraste_slider_porta = [None]   # nome da folha sendo arrastada
_slider_hover = [None]           # nome da folha com a bolinha sob o mouse


def _folhas_com_slider(context):
    folhas = []
    for o in getattr(context, 'selected_objects', ()) or ():
        if _chapas.MARCA_PORTAS in o and o.get('porta_parametros'):
            grupo, candidatas = o, _portas._folhas_portas(o)
        elif _chapas.MARCA_FOLHA in o and _portas._grupo_portas(o) is not None:
            grupo, candidatas = _portas._grupo_portas(o), [o]
        else:
            continue
        if _porta_veio_do_modulo(grupo):
            continue        # modulo selecionado: sem sliders
        folhas += [f for f in candidatas if f not in folhas]
    return folhas


def _slider_no_mundo(folha):
    """As 2 pontas do slider em MUNDO: base da folha fechada, a' frente,
    recuadas das quinas (a folga entre os sliders de uma porta dupla)."""
    l, a, e, centro = _ferragens._dados_da_folha(folha)
    fechada = _ferragens._matriz_fechada(folha)
    curso = _curso_do_slider(folha, l, centro)
    if curso is not None:
        # correr: do centro da folha fechada ao da aberta (a bolinha anda
        # embaixo dela), um degrau acima por trilho -- os sliders de uma
        # porta de varias folhas nao se sobrepoem
        y = -a / 2.0 + int(folha.get('porta_indice', 0)) * SLIDER_DEGRAU_MM
        return [fechada @ (Vector((dx, y, e / 2.0 + SLIDER_FRENTE_MM)) / 1000.0)
                for dx in curso]
    recuo = min(max(SLIDER_RECUO_MM, SLIDER_RECUO_FRACAO * l), 0.3 * l)
    return [fechada @ (Vector((sx * (l / 2.0 - recuo), -a / 2.0,
                               e / 2.0 + SLIDER_FRENTE_MM)) / 1000.0)
            for sx in (-1, 1)]


def _curso_do_slider(folha, l, centro):
    """(0, deslocamento) da folha de CORRER fechada ate' aberta (mm, no X
    do vao), ou None se ela nao for de correr."""
    grupo = _portas._grupo_portas(folha)
    p = (grupo.get('porta_parametros') or {}) if grupo is not None else {}
    if p.get('abertura') != 'CORRER':
        return None
    fechado, destino = _ferragens._curso_correr(
        p, float(grupo.get('porta_vao_largura_mm', 0.0)),
        len(_portas._folhas_portas(grupo)), l, centro[0])
    return 0.0, destino - fechado


def _slider_na_tela(context, folha):
    """(inicio, fim) do slider em pixels, o inicio sempre a' esquerda --
    menos no de correr, que vai de onde a folha fecha para onde ela abre
    (a bolinha acompanha a folha)."""
    pontos = [_hud._projetar_hud(context, p) for p in _slider_no_mundo(folha)]
    if any(p is None for p in pontos) or (pontos[1] - pontos[0]).length < 1:
        return None
    if _curso_do_slider(folha, *_ferragens._dados_da_folha(folha)[::3]) is not None:
        return tuple(pontos)
    return tuple(sorted(pontos, key=lambda p: p.x))


def _fracao_no_slider(inicio, fim, mouse):
    trilho = fim - inicio
    return max(0.0, min(1.0, (mouse - inicio).dot(trilho) / trilho.length_squared))


def _px_por_mm_do_slider(context, folha):
    """Pixels por mm no meio do slider, medidos na vertical da TELA (a
    inclinacao do trilho nao afina o desenho), com o teto."""
    rv3d = context.region_data
    a, b = _slider_no_mundo(folha)
    meio = (a + b) / 2.0
    cima = rv3d.view_rotation @ Vector((0.0, 1.0, 0.0))
    p, q = (_hud._projetar_hud(context, v) for v in (meio, meio + cima * 0.1))
    teto = SLIDER_PX_POR_MM_MAX * max(1.0, context.preferences.system.ui_scale)
    if p is None or q is None:
        return teto
    return min((q - p).length / 100.0, teto)


def _botao_do_slider(context, folha):
    """Centro da bolinha do slider (pixels), ou None."""
    tela = _slider_na_tela(context, folha)
    if tela is None:
        return None
    return tela[0].lerp(tela[1], float(folha.get(_ferragens.CHAVE_ABERTURA, 0.0)))


def _slider_sob_mouse(context, posicao):
    """A folha cuja BOLINHA esta' sob o mouse, ou None. O alcance e' o
    tamanho da bolinha (pedido do usuario): o trilho nao pega o clique."""
    if getattr(context, 'region_data', None) is None:
        return None             # sem vista 3D nao ha' slider na tela
    mouse = Vector(posicao)
    melhor = None
    for folha in _folhas_com_slider(context):
        botao = _botao_do_slider(context, folha)
        if botao is None:
            continue
        # do tamanho da bolinha desenhada (3 px no minimo: ainda se pega)
        raio = max(3.0, SLIDER_BOTAO_MM * _px_por_mm_do_slider(context, folha))
        d = (botao - mouse).length
        if d <= raio and (melhor is None or d < melhor[0]):
            melhor = (d, folha)
    return melhor[1] if melhor else None


def _texto_abertura(folha):
    grupo = _portas._grupo_portas(folha)
    p = (grupo.get('porta_parametros') or {}) if grupo is not None else {}
    fracao = float(folha.get(_ferragens.CHAVE_ABERTURA, 0.0))
    abertura = p.get('abertura', 'GIRO')
    if abertura == 'CORRER':
        l, a, e, centro = _ferragens._dados_da_folha(folha)
        mm = (_ferragens._matriz_abertura(p, float(grupo.get('porta_vao_largura_mm', 0.0)),
                               len(_portas._folhas_portas(grupo)),
                               int(folha.get('porta_indice', 0)),
                               (l, a, e, centro), fracao).translation * 1000.0
              - Vector(centro)).length
        return '%d mm' % round(mm)
    maximo = (_ferragens._giro_maximo_rig() if _ferragens._usa_rig(p)
              else _ferragens.ABERTURA_MAX_GRAUS.get(abertura, 110.0))
    return '%d%s' % (round(maximo * fracao), SIMBOLO_GRAU)


def _desenhar_sliders_porta(context):
    folhas = _folhas_com_slider(context)
    if not folhas:
        return
    realce = _hud._cor_realce_hud()
    arrastando = _arraste_slider_porta[0]
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    gpu.state.blend_set('ALPHA')
    try:
        for folha in folhas:
            tela = _slider_na_tela(context, folha)
            if tela is None:
                continue
            inicio, fim = tela
            fracao = float(folha.get(_ferragens.CHAVE_ABERTURA, 0.0))
            botao = inicio.lerp(fim, fracao)
            # tudo proporcional ao zoom: 1 "escala" = 1 mm na tela
            mm = _px_por_mm_do_slider(context, folha)
            grosso = SLIDER_ESPESSURA_MM * mm
            raio = SLIDER_BOTAO_MM * mm
            aceso = folha.name in (arrastando, _slider_hover[0])
            shader.bind()
            # cores opacas: com alfa, a emenda das pontas redondas apareceria
            _capsula_2d(shader, inicio, fim, grosso + 3.0 * mm,
                        (0.92, 0.92, 0.92, 1.0))
            _capsula_2d(shader, inicio, fim, grosso, (0.13, 0.13, 0.13, 1.0))
            if fracao > 0:
                _capsula_2d(shader, inicio, botao, grosso * 0.65, realce)
            if aceso:
                _hud._bolinha_2d(shader, botao, raio + 3.0 * mm, realce)
            _hud._bolinha_2d(shader, botao, raio, (1.0, 1.0, 1.0, 1.0))
            _hud._bolinha_2d(shader, botao, raio * 0.45, realce)
            # o valor numa caixa preta, centrado acima do botao; pequeno
            # demais para ler, some (o slider continua)
            tamanho = SLIDER_TEXTO_MM * mm
            if tamanho >= SLIDER_TEXTO_MIN_PX:
                texto = _texto_abertura(folha)
                blf.size(0, tamanho)
                largura = blf.dimensions(0, texto)[0]
                _hud._caixa_texto_hud(botao.x - largura / 2.0,
                                 botao.y + raio + 7.0 * mm, texto, tamanho,
                                 tamanho / 12.0)
                gpu.state.blend_set('ALPHA')
    finally:
        gpu.state.blend_set('NONE')


def _capsula_2d(shader, a, b, grossura, rgba):
    """Trilho com as pontas redondas (o slider)."""
    shader.uniform_float('color', rgba)
    quad = _puxadores._quad_2d(a, b, grossura)
    if quad:
        batch_for_shader(shader, 'TRIS', {'pos': quad}).draw(shader)
    for ponta in (a, b):
        _hud._bolinha_2d(shader, ponta, grossura / 2.0, rgba)


class OBJECT_OT_abrir_porta(Operator):
    """Arraste o slider da folha: para a direita abre, para a esquerda fecha"""
    bl_idname = 'object.cabinet_abrir_porta'
    bl_label = 'Abrir Porta'
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}

    folha: StringProperty(options={'SKIP_SAVE'})
    fracao: FloatProperty(min=0.0, max=1.0, options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return _hud._contexto_hud(context)

    def execute(self, context):
        folha = bpy.data.objects.get(self.folha)
        if folha is None or not _ferragens._definir_abertura(context, folha, self.fracao):
            return {'CANCELLED'}
        _eventos._redesenhar_viewports(context)
        return {'FINISHED'}

    def invoke(self, context, event):
        # do gizmo da bolinha (ou do keymap): fora dela o clique segue
        folha = _slider_sob_mouse(context, (event.mouse_region_x,
                                            event.mouse_region_y))
        if folha is None:
            return {'PASS_THROUGH'}
        self.folha = folha.name
        self._antes = float(folha.get(_ferragens.CHAVE_ABERTURA, 0.0))
        self._area = context.area
        # pegou a bolinha fora do centro: ela nao pula ate' o mouse
        self._desvio = self._fracao_do_mouse(context, event, folha) - self._antes
        _arraste_slider_porta[0] = folha.name
        context.window_manager.modal_handler_add(self)
        self._area.tag_redraw()
        return {'RUNNING_MODAL'}

    @staticmethod
    def _fracao_do_mouse(context, event, folha):
        tela = _slider_na_tela(context, folha)
        if tela is None:
            return float(folha.get(_ferragens.CHAVE_ABERTURA, 0.0))
        return _fracao_no_slider(*tela, Vector((event.mouse_region_x,
                                                event.mouse_region_y)))

    def _arrastar(self, context, event):
        folha = bpy.data.objects.get(self.folha)
        if folha is None:
            return
        self.fracao = max(0.0, min(1.0, self._fracao_do_mouse(
            context, event, folha) - self._desvio))
        _ferragens._definir_abertura(context, folha, self.fracao)
        self._area.tag_redraw()

    def _encerrar(self):
        _arraste_slider_porta[0] = None
        self._area.tag_redraw()

    def cancel(self, context):
        self._encerrar()

    def modal(self, context, event):
        if event.type in {'ESC', 'RIGHTMOUSE'}:
            folha = bpy.data.objects.get(self.folha)
            if folha is not None:
                _ferragens._definir_abertura(context, folha, self._antes)
            self._encerrar()
            return {'CANCELLED'}
        if event.type == 'MOUSEMOVE':
            self._arrastar(context, event)
            return {'RUNNING_MODAL'}
        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            self._arrastar(context, event)
            self._encerrar()
            return {'FINISHED'}
        if event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            return {'PASS_THROUGH'}
        return {'RUNNING_MODAL'}


class VIEW3D_GT_slider_porta(Gizmo):
    """A bolinha do slider de abertura; o hit-test e' do tamanho dela.

    Gizmo e nao so' keymap: o gizmo e' avaliado ANTES de qualquer keymap.
    No keyconfig do usuario a selecao vinha antes da entrada do slider
    (o head=True do add-on nao vale na ordem dele), limpava a selecao e
    o slider sumia antes de receber o clique."""
    bl_idname = 'VIEW3D_GT_slider_porta'

    def draw(self, context):
        pass

    def test_select(self, context, location):
        folha = (_slider_sob_mouse(context, location)
                 if _hud._contexto_hud(context) else None)
        nome = folha.name if folha is not None else None
        if nome != _slider_hover[0]:
            _slider_hover[0] = nome
            context.area.tag_redraw()
        return 0 if folha is not None else -1


class VIEW3D_GGT_slider_porta(GizmoGroup):
    bl_idname = 'VIEW3D_GGT_slider_porta'
    bl_label = 'Slider de abertura das portas'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'WINDOW'
    bl_options = {'PERSISTENT'}

    @classmethod
    def poll(cls, context):
        return _hud._contexto_hud(context) and bool(_folhas_com_slider(context))

    def setup(self, context):
        self.botao = self.gizmos.new('VIEW3D_GT_slider_porta')
        self.botao.use_tooltip = False
        self.botao.target_set_operator('object.cabinet_abrir_porta')

    def draw_prepare(self, context):
        if not self.botao.is_highlight and _slider_hover[0] is not None:
            _slider_hover[0] = None
