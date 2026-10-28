"""Referencia retangular temporaria para criar internos sem vertices de apoio."""
import math
import bpy
import gpu
from bpy.types import Operator
from bpy.props import StringProperty
from bpy_extras import view3d_utils
from gpu_extras.batch import batch_for_shader
from mathutils import Matrix, Vector
from mathutils.geometry import intersect_line_plane, intersect_ray_tri

_hud = _hud_volume = _gaveta = _gaveta_eventos = _gavetas = None
_portas = _assistente = _prateleiras = _divisorias = _fundos = None
_eventos = _editor = None
_opcoes = None
_modulos = None
_biblioteca_faixa = None
_perguntas = None
_estado = [None]
_entrega = [None]
_internos = [None]
MARCA = 'cabinet_area_criacao'
DESTINOS = {'GAVETAS': 'object.cabinet_criar_gavetas',
            'PRATELEIRAS': 'object.cabinet_criar_prateleiras',
            'DIVISORIAS': 'object.cabinet_criar_divisorias',
            'PORTAS': 'object.cabinet_apanhar_vao', 'FUNDOS': 'object.cabinet_criar_fundo'}
FACES = {'Z-': (0, 2, 3, 1), 'Z+': (4, 5, 7, 6),
         'Y-': (0, 1, 5, 4), 'Y+': (2, 6, 7, 3),
         'X-': (0, 4, 6, 2), 'X+': (1, 3, 7, 5)}
RECADO_FRENTE = 'Clique na face que sera a frente | Backspace volta | Esc cancela'


def caixa_de_pontos(modulo, pontos, validar=True):
    # A diagonal nunca define os eixos: o modulo fornece apenas sua rotacao.
    mundo = modulo.matrix_world
    if any(not math.isfinite(v) for linha in mundo for v in linha):
        raise ValueError('O modulo precisa de um referencial valido')
    x = mundo.to_3x3().col[0].normalized()
    z = mundo.to_3x3().col[2]; z = (z - x * z.dot(x)).normalized()
    y = z.cross(x)
    if min(x.length, y.length, z.length) < .5:
        raise ValueError('O modulo precisa de tres eixos validos')
    if y.dot(mundo.to_3x3().col[1]) < 0:
        y = -y
    m = Matrix((x, y, z)).transposed().to_4x4()
    m.translation = mundo.translation
    inv = m.inverted()
    locais = [inv @ Vector(p) for p in pontos]
    if not locais or any(not math.isfinite(v) for p in locais for v in p):
        raise ValueError('Marque pontos finitos para definir a area')
    lo = Vector(tuple(min(p[i] for p in locais) for i in range(3)))
    hi = Vector(tuple(max(p[i] for p in locais) for i in range(3)))
    medidas = tuple((hi[i] - lo[i]) * 1000 for i in range(3))
    if validar and min(medidas) < 1:
        raise ValueError('Os tres pontos devem delimitar pelo menos 1 mm nos tres eixos')
    m.translation = m @ lo
    return dict(matriz=tuple(v for linha in m for v in linha), medidas=medidas,
                modulo=modulo.name, plana=False)


def cantos_dados(d):
    m = _matriz(d['matriz']); l, p, a = (v / 1000 for v in d['medidas'])
    return [m @ Vector((x, y, z)) for z in (0, a)
            for y in ((0,) if d['plana'] else (0, p)) for x in (0, l)]


def face_no_raio(d, origem, direcao):
    c = cantos_dados(d); acertos = []
    # Somente as doze faces trianguladas da propria previa, via mathutils nativo.
    for nome, (a, b, e, f) in FACES.items():
        for indices in ((a, b, e), (a, e, f)):
            p = intersect_ray_tri(*(c[i] for i in indices), direcao, origem, True)
            if p is not None and (p - origem).dot(direcao) >= 0:
                acertos.append(((p - origem).length_squared, nome))
    return min(acertos)[1] if acertos else None


def orientar_frente(d, face):
    if face not in FACES:
        raise ValueError('Escolha a face da frente da area')
    antigo = _matriz(d['matriz']).to_3x3()
    eixo = 'XYZ'.index(face[0]); sinal = -1 if face[1] == '-' else 1
    y = -sinal * antigo.col[eixo]
    z = antigo.col[2 if eixo != 2 else 1].copy()
    x = y.cross(z).normalized()
    m = Matrix((x, y, z)).transposed().to_4x4()
    origem = _matriz(d['matriz']).translation.copy(); medidas = []
    # E' uma permutacao de eixos: conservar as medidas evita erro de arredondamento.
    for novo in (x, y, z):
        indice = max(range(3), key=lambda i: abs(novo.dot(antigo.col[i])))
        medida = d['medidas'][indice]; medidas.append(medida)
        if novo.dot(antigo.col[indice]) < 0:
            origem += antigo.col[indice] * (medida / 1000)
    m.translation = origem
    return dict(d, matriz=tuple(v for linha in m for v in linha), medidas=tuple(medidas))


def realcar_frente(shader, d, face):
    if face not in FACES:
        return
    c = cantos_dados(d); a, b, e, f = FACES[face]
    shader.uniform_float('color', (*_hud._cor_realce_hud()[:3], .35))
    batch_for_shader(shader, 'TRIS', {'pos': [c[i] for i in (a, b, e, a, e, f)]}).draw(shader)


def oferecer(context):
    aba = context.scene.cabinet_aba
    if aba not in DESTINOS or any((
            _portas._apanhando_vao[0], _portas._assistente_porta[0] is not None,
            _gavetas._criando(), _prateleiras._criando(),
            _divisorias._criando(), _fundos._assistente_fundo[0] is not None)):
        return False
    obj = context.object if context.object and context.object.select_get() else None
    if aba == 'PORTAS':
        return _portas._grupo_portas(obj) is None
    dono = {'GAVETAS': _gavetas, 'PRATELEIRAS': _prateleiras, 'DIVISORIAS': _divisorias}.get(aba)
    return dono is None or dono.grupo_de(obj) is None


def objeto():
    s = _estado[0]
    return bpy.data.objects.get(s.get('objeto', '')) if s else None


def escolhendo_frente():
    return bool(_estado[0] and _estado[0].get('etapa') == 'FRENTE')


def _matriz(valores):
    return Matrix([valores[i:i + 4] for i in (0, 4, 8, 12)])


def dados(obj):
    mundo = obj.matrix_world.copy()
    eixos = [mundo.to_3x3().col[i].copy() for i in range(3)]
    escalas = [e.length for e in eixos]
    if (min(escalas) <= 1e-8 or any(not math.isfinite(v) for v in escalas)
            or any(not math.isfinite(v) for linha in mundo for v in linha)):
        raise ValueError('A area precisa de medidas positivas e finitas')
    eixos = [e.normalized() for e in eixos]
    if any(abs(eixos[i].dot(eixos[j])) > 1e-5 for i, j in ((0, 1), (0, 2), (1, 2))):
        raise ValueError('A area deve permanecer retangular')
    base = Matrix(eixos).transposed().to_4x4()
    base.translation = mundo.translation
    medidas = tuple(float(v) * escala for v, escala in zip(obj['area_medidas_mm'], escalas))
    if (any(not math.isfinite(v) for v in medidas) or min(medidas[0], medidas[2]) < 1
            or not obj['area_plana'] and medidas[1] < 1):
        raise ValueError('A area precisa de pelo menos 1 mm em cada direcao')
    return dict(matriz=tuple(v for linha in base for v in linha), medidas=medidas,
                modulo=obj.get('area_modulo', ''), plana=bool(obj['area_plana']))


def cantos(obj):
    return cantos_dados(dados_visuais(obj))


def linhas_hud(obj, chapas):
    pontos = cantos(obj)
    pares = (((0, 1), (2, 3)), (), ((0, 2), (1, 3))) if len(pontos) == 4 else _hud.ARESTAS_EIXO
    linhas = [dict(tipo='area_criacao', objeto=obj, modo='AREA_CRIACAO', eixo=eixo,
                    letra=('L', 'P', 'A')[eixo], face=(('L', 'P', 'A')[eixo],),
                    cantos=(i, j), chapas=[], pontos=[pontos[i], pontos[j]])
              for eixo, arestas in enumerate(pares) for i, j in arestas]
    return pontos, linhas


def controles_plano(geometria):
    pontos = geometria['cantos']; linhas = geometria['linhas']
    saida = []
    for eixo, pares in ((0, ((0, 2), (1, 3))), (2, ((0, 1), (2, 3)))):
        linha = next(l for l in linhas if l['eixo'] == eixo)
        centros = [(pontos[a] + pontos[b]) / 2 for a, b in pares]
        for lado in (0, 1):
            saida.append(dict(linha, controle_face=True, lado='min' if lado else 'max',
                              pontos=[centros[1 - lado], centros[lado]]))
    return saida


def valor(obj, chave):
    return dados_visuais(obj)['medidas'][{'L': 0, 'P': 1, 'A': 2}[chave[0]]]


def dados_visuais(obj):
    try:
        d = dados(obj)
    except ValueError:
        if _estado[0] and _estado[0].get('valido'):
            return _estado[0]['valido']
        raise
    if _estado[0]:
        _estado[0]['valido'] = d
    return d


def aplicar(context, obj, chave, novo, lado=None):
    if obj is None:
        return 'A area nao esta mais ativa'
    if not math.isfinite(novo) or novo < 1:
        return 'Informe uma medida de pelo menos 1 mm'
    d = dados_visuais(obj); eixo = {'L': 0, 'P': 1, 'A': 2}[chave[0]]
    if d['plana'] and eixo == 1:
        return 'O plano nao tem profundidade'
    medidas = list(d['medidas']); m = _matriz(d['matriz'])
    if lado == 'max':
        m.translation -= m.to_3x3().col[eixo] * (novo - medidas[eixo]) / 1000
    medidas[eixo] = novo
    obj['area_medidas_mm'] = medidas
    obj.matrix_world = m
    context.view_layer.update()
    dados_visuais(obj)
    _eventos._redesenhar_viewports(context)


def copia(obj):
    return obj.name, tuple(v for linha in obj.matrix_world for v in linha), tuple(obj['area_medidas_mm'])


def restaurar(estado):
    nome, matriz, medidas = estado
    obj = bpy.data.objects.get(nome)
    if obj is not None:
        obj.matrix_world = _matriz(matriz); obj['area_medidas_mm'] = medidas
        bpy.context.view_layer.update()


def criar_referencia(context, destino, ponto, modulo=None, matriz=None):
    """Empty impede Tab/bevel/subdivisao; o volume tem somente limites numericos."""
    if destino not in DESTINOS:
        raise ValueError('Sistema de criacao desconhecido')
    obj = bpy.data.objects.new('Area de criacao', None)
    context.scene.collection.objects.link(obj)
    obj[MARCA] = True
    obj['area_plana'] = destino in {'PORTAS', 'FUNDOS'}
    obj['area_modulo'] = modulo.name if modulo else ''
    obj['area_medidas_mm'] = (200.0, 0.0 if obj['area_plana'] else 200.0, 200.0)
    obj.empty_display_size = .001; obj.hide_render = True
    obj.matrix_world = (matriz.copy() if matriz is not None else
                        modulo.matrix_world.to_3x3().normalized().to_4x4() if modulo else Matrix.Identity(4))
    obj.matrix_world.translation = ponto
    for outro in context.selected_objects:
        outro.select_set(False)
    obj.select_set(True); context.view_layer.objects.active = obj
    if context.space_data and context.space_data.type == 'VIEW_3D' and context.space_data.local_view:
        obj.local_view_set(context.space_data, True)
    context.view_layer.update()
    return obj


def encerrar(restaurar_selecao=True):
    s, _estado[0] = _estado[0], None
    if s:
        nativo = _hud_volume._estado[0]
        if nativo and nativo.get('objeto') == s.get('objeto'):
            _hud_volume.terminar(cancelar=True)
        for nome in ('handler',):
            if s.get(nome) is not None:
                bpy.types.SpaceView3D.draw_handler_remove(s[nome], 'WINDOW')
        if s.get('timer') is not None:
            try:
                bpy.context.window_manager.event_timer_remove(s['timer'])
            except (ReferenceError, RuntimeError):
                pass
        for janela in bpy.context.window_manager.windows:
            for area in janela.screen.areas:
                if area.as_pointer() == s['area']:
                    area.header_text_set(None)
        _hud._hover_hud.clear()
    for obj in list(bpy.data.objects):
        if MARCA in obj:
            bpy.data.objects.remove(obj, do_unlink=True)
    if s and restaurar_selecao and bpy.context.scene.name == s['cena']:
        camada = bpy.context.view_layer
        for obj in bpy.context.selected_objects:
            obj.select_set(False)
        for nome in s['selecao']:
            obj = camada.objects.get(nome)
            if obj is not None:
                obj.select_set(True)
        camada.objects.active = camada.objects.get(s['ativo'])
    _eventos._redesenhar_viewports(bpy.context)


def esquecer():
    encerrar(); _entrega[0] = None
    cancelar_internos()


def cancelar_internos():
    _internos[0] = None
    pergunta = _perguntas._pergunta_atual[0]
    if pergunta and pergunta.get('internos'):
        _perguntas._pergunta_atual[0] = None


def preparar_assistente_internos(tipo):
    s = _internos[0]
    if s and (s.get('etapa') != 'CRIANDO' or s.get('tipo') != tipo or s.get('cena') != bpy.context.scene.name):
        cancelar_internos()


def _perguntar_internos(context, texto, escolhas):
    s = _internos[0]
    _perguntas._perguntar(context, texto,
        [(rotulo, 'NONE', 'object.cabinet_internos', {'acao': acao, 'valor': valor})
         for rotulo, acao, valor in escolhas], na_gaveta=s['na_gaveta'])
    _perguntas._pergunta_atual[0]['internos'] = True
    _gaveta._rolar_ate_o_fim(context)


def iniciar_internos(context, modo='PONTOS'):
    cancelar_internos()
    _internos[0] = dict(etapa='TIPO', modo=modo, cena=context.scene.name,
        na_gaveta=bool(_perguntas._na_gaveta[0] or _gaveta._eh_area_gaveta(context)))
    context.scene.cabinet_aba = 'PRATELEIRAS'
    _perguntar_internos(context, 'Criar prateleiras ou divisorias?',
        [('Prateleiras', 'TIPO', 'PRATELEIRAS'),
         ('Divisorias', 'TIPO', 'DIVISORIAS'), ('Sair', 'SAIR', '')])
    return {'FINISHED'}


def criar_internos(context, assistente, extra):
    w = assistente._w
    conj = bpy.data.objects.get(w['modulo'])
    if conj is None:
        assistente._encerrar(context); cancelar_internos()
        return {'CANCELLED'}
    _dados, matriz = assistente._dados()
    l, a = w['vao']
    if _internos[0] is None:
        _internos[0] = dict(na_gaveta=True, cena=context.scene.name)
    s = _internos[0]
    area = s.get('area') or dict(matriz=tuple(v for r in matriz for v in r),
        medidas=(l, float(w['p']['profundidade_mm']), a), modulo=conj.name, plana=False)
    s.update(etapa='CRIANDO', tipo=assistente.ABA,
        area=area,
        criacao=dict(modulo=conj.name, p=_portas._copiar_parametros(dict(w['p'], **extra)),
            margens=list(_gavetas.margens_do_vao(conj, *w['pontos'],
                referencial=w.get('referencia'), limites_referencia=w.get('limites_ref'))),
            referencia=tuple(v for r in w.get('referencia', Matrix.Identity(3)) for v in r)))
    assistente._encerrar(context)
    c = s['criacao']
    ref = Matrix([c['referencia'][i:i+3] for i in (0,3,6)])
    lacuna = False
    if s['tipo'] == 'DIVISORIAS':
        _p, planos = _divisorias.planejar(conj, c['margens'], c['p'], ref)
        lacuna = any(plano[-1] for plano in planos)
    else:
        lacuna = _divisorias.prever_lacunas_prateleiras(conj,c['margens'],c['p'],ref)
    if lacuna:
        s['etapa'] = 'LACUNA'
        _perguntar_internos(context, 'Qual prateleira preenche a lacuna?',
            [('Esquerda', 'LACUNA', 'ESQUERDA'), ('Direita', 'LACUNA', 'DIREITA'),
             ('Manter vao', 'LACUNA', 'MANTER'), ('Cancelar', 'SAIR', '')])
        return {'FINISHED'}
    return confirmar_internos(context)


def confirmar_internos(context):
    s = _internos[0]; c = s['criacao']
    conj = bpy.data.objects.get(c['modulo'])
    if conj is None:
        cancelar_internos(); return {'CANCELLED'}
    dono = _prateleiras if s['tipo'] == 'PRATELEIRAS' else _divisorias
    ref = Matrix([c['referencia'][i:i+3] for i in (0,3,6)])
    criar = dono.criar_prateleiras if dono is _prateleiras else dono.criar_divisorias
    grupo = criar(context, conj, c['margens'], c['p'], referencial=ref,
                  blocagem_uid=s.get('blocagem_uid'))
    s['blocagem_uid'] = grupo[_divisorias.CHAVE_BLOCAGEM]
    dono.selecionar(context, grupo, 'GRUPO')
    context.scene.cabinet_aba = s['tipo']
    s['etapa'] = 'CONTINUAR'
    concluidos = s.setdefault('concluidos', [])
    if s['tipo'] not in concluidos:
        concluidos.append(s['tipo'])
    outro = 'DIVISORIAS' if s['tipo'] == 'PRATELEIRAS' else 'PRATELEIRAS'
    escolhas = ([] if outro in concluidos else
        [('Prateleiras' if outro == 'PRATELEIRAS' else 'Divisorias', 'CONTINUAR', outro)])
    _perguntar_internos(context, 'Continuar no mesmo volume?' if escolhas else 'Concluir criacao',
        escolhas + [('Sair', 'SAIR', '')])
    return {'FINISHED'}


class OBJECT_OT_internos(Operator):
    bl_idname = 'object.cabinet_internos'
    bl_label = 'Criar Prateleiras ou Divisorias'
    bl_options = {'REGISTER', 'UNDO'}
    acao: StringProperty(default='INICIAR', options={'SKIP_SAVE'})
    valor: StringProperty(options={'SKIP_SAVE'})

    def execute(self, context):
        try:
            if self.acao == 'INICIAR':
                return iniciar_internos(context)
            if self.acao == 'SAIR':
                cancelar_internos(); return {'FINISHED'}
            s = _internos[0]
            if s is None:
                return {'CANCELLED'}
            if s['cena'] != context.scene.name:
                cancelar_internos(); return {'CANCELLED'}
            if self.acao == 'LACUNA' and s['etapa'] == 'LACUNA' and self.valor in {'ESQUERDA','DIREITA','MANTER'}:
                chave = 'preenchimento' if s['tipo'] == 'DIVISORIAS' else 'preenchimento_divisorias'
                s['criacao']['p'][chave] = self.valor
                return confirmar_internos(context)
            if self.acao not in {'TIPO','CONTINUAR'} or self.valor not in {'PRATELEIRAS','DIVISORIAS'}:
                return {'CANCELLED'}
            if s['etapa'] != ('TIPO' if self.acao == 'TIPO' else 'CONTINUAR'):
                return {'CANCELLED'}
            if self.acao == 'CONTINUAR' and self.valor in s.get('concluidos', []):
                return {'CANCELLED'}
            s.update(tipo=self.valor, etapa='CRIANDO')
            context.scene.cabinet_aba = self.valor
            if self.acao == 'TIPO' and s['modo'] == 'VOLUME':
                resultado = _editor.executar(context, 'object.cabinet_definir_area', destino=self.valor)
            else:
                if self.acao == 'CONTINUAR':
                    _entrega[0] = dict(s['area'], destino=self.valor)
                try:
                    resultado = _editor.executar(context, DESTINOS[self.valor])
                finally:
                    _entrega[0] = None
            if 'CANCELLED' in resultado:
                cancelar_internos()
            return {'FINISHED'}
        except ValueError as erro:
            self.report({'WARNING'}, str(erro))
            return {'CANCELLED'}


def verificar():
    if _eventos._desfazendo[0]:
        return
    if _internos[0] and _internos[0]['cena'] != bpy.context.scene.name:
        cancelar_internos()
    s = _estado[0]
    existe_area = s and any(a.as_pointer() == s['area']
        for janela in bpy.context.window_manager.windows for a in janela.screen.areas)
    if not s or not existe_area or s['cena'] != bpy.context.scene.name or s.get('objeto') and objeto() is None:
        if s or any(MARCA in o for o in bpy.data.objects):
            encerrar()
    elif objeto() is not None and not _eventos._transformando():
        obj = objeto()
        try:
            dados_visuais(obj)
        except ValueError:
            return
        # S pode atravessar zero enquanto o operador nativo esta' vivo.
        # Ao terminar, conservar o ultimo retangulo valido sem erro no redraw.
        try:
            dados(obj)
        except ValueError:
            d = s['valido']
            obj.matrix_world = _matriz(d['matriz']); obj['area_medidas_mm'] = d['medidas']
            bpy.context.view_layer.update()


def consumir(destino):
    d = _entrega[0]
    if d and d['destino'] == destino:
        _entrega[0] = None
        return d


def preparar_entrega(context):
    s = _estado[0]; obj = objeto()
    if obj is None:
        raise ValueError('Posicione a area com um clique na viewport')
    d = dict(dados(obj), destino=s['destino'])
    if not d['plana']:
        d = orientar_frente(d, s.get('frente'))
    modulo = bpy.data.objects.get(d['modulo'])
    if d['destino'] != 'PORTAS' and modulo is None:
        raise ValueError('Selecione um modulo antes de definir a area')
    l, prof, a = d['medidas']
    donos = {'GAVETAS': _gavetas, 'PRATELEIRAS': _prateleiras, 'DIVISORIAS': _divisorias}
    if d['destino'] in donos:
        dono = donos[d['destino']]
        dono.calcular(l, a, dict(dono.PARAMETROS_PADRAO, profundidade_mm=prof))
    elif d['destino'] == 'PORTAS':
        p = _portas._parametros_portas_da_cena(context.scene, numerico=True)
        p.update(dict.fromkeys(_portas.COBERTURAS_LADOS, 0.0))
        _portas._calcular_folhas_portas(l, a, p)
    elif min(l, a) <= 1:
        raise ValueError('Marque uma area com largura e altura maiores que 1 mm')
    return d


def entregar(context):
    d = preparar_entrega(context)
    if _internos[0] is not None and 'area' not in _internos[0] and d['destino'] in {'PRATELEIRAS','DIVISORIAS'}:
        _internos[0]['area'] = {k:v for k,v in d.items() if k != 'destino'}
    encerrar(restaurar_selecao=False)
    _entrega[0] = d
    try:
        resultado = _editor.executar(context, DESTINOS[d['destino']])
        return {'CANCELLED'} if 'CANCELLED' in resultado else {'FINISHED'}
    finally:
        _entrega[0] = None


def solicitar_frente(context):
    obj = objeto()
    if obj is None:
        raise ValueError('Posicione a area com um clique na viewport')
    if dados(obj)['plana']:
        return entregar(context)
    _estado[0].update(etapa='FRENTE', face_hover=None)
    for area in context.screen.areas:
        if area.as_pointer() == _estado[0]['area']:
            area.header_text_set(RECADO_FRENTE)
    _eventos._redesenhar_viewports(context)
    return {'RUNNING_MODAL'}


def vao_porta(d):
    m = _matriz(d['matriz']); l, _p, a = d['medidas']
    x, y, z = (m.to_3x3().col[i] for i in range(3))
    frente = Matrix((x, z, -y)).transposed().to_4x4()
    frente.translation = m.translation
    return l, a, frente


def validar_plano(medidas, matriz):
    if any(not math.isfinite(v) for v in medidas) or min(medidas) < 1:
        raise ValueError('Area da porta invalida')
    eixos = [matriz.to_3x3().col[i] for i in range(3)]
    if (any(not math.isfinite(v) for linha in matriz for v in linha)
            or any(abs(e.length - 1) > 1e-5 for e in eixos)
            or any(abs(eixos[i].dot(eixos[j])) > 1e-5 for i, j in ((0,1),(0,2),(1,2)))):
        raise ValueError('O plano deve permanecer retangular e sem escala')


def receber_internos(assistente, d):
    w = assistente._w; conj = bpy.data.objects.get(d['modulo'])
    if conj is None:
        raise ValueError('O modulo da area nao existe mais')
    m = _matriz(d['matriz']); l, prof, a = d['medidas']
    w.update(modulo=conj.name, pontos=[m @ Vector((0, 0, a / 1000)),
        m @ Vector((l / 1000, 0, 0))], nomes=['', ''], area_livre=True)
    if not d['plana']:
        w.setdefault('caixa_area', dict(d))
    w['referencia'] = conj.matrix_world.to_3x3().inverted_safe() @ m.to_3x3()
    w['limites_ref'] = _gavetas.limites_na_referencia(conj, w['referencia'])
    w['limites'] = _gavetas._limites(conj)
    assistente._comecar_no_modulo(conj, w['pontos'][0])
    w['p']['profundidade_mm'] = prof
    w['maxprof'] = prof
    w['iniciar_snap'] = False
    assistente._ir('QUANTIDADE')


def widgets(context, itens, x, y, w):
    obj = objeto()
    if obj is None:
        itens.append((x, y, w, 28, 'Clique na viewport para posicionar a area', None))
    elif _estado[0].get('etapa') == 'FRENTE':
        itens.append((x, y, w, 28, 'Clique na face da frente na viewport', None))
        y -= 38
    else:
        topo = _gaveta._titulo_secao(itens, x, y, w, 'Area de criacao')
        chaves = [('L', 'A1'), ('A', 'A2')] + ([] if obj['area_plana'] else [('P', 'A3')])
        campos = [(rotulo + ': ' + _opcoes._texto_medida(valor(obj, (chave,))),
                   ('medida', 'area_criacao', chave, rotulo, valor(obj, (chave,)))) for chave, rotulo in chaves]
        y = _gaveta._campos_em_linhas(context, itens, x, topo, w, campos, colunas_uniformes=True)
        y -= 30
        itens.append((x, y, w, 30, 'Aplicar area', ('operador', 'object.cabinet_aplicar_area')))
        y -= 38
    if obj is None:
        y -= 36
    itens.append((x, y, w, 28, 'Cancelar', ('operador', 'object.cabinet_cancelar_area')))
    return itens


def desenhar():
    obj = objeto(); s = _estado[0]
    if obj is None or not s or bpy.context.area.as_pointer() != s['area']:
        return
    c = cantos(obj)
    faces = ((0, 1, 3, 2),) if len(c) == 4 else ((0, 2, 3, 1), (4, 5, 7, 6),
        (0, 1, 5, 4), (2, 6, 7, 3), (0, 4, 6, 2), (1, 3, 7, 5))
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    cor = _hud._cor_realce_hud()
    try:
        gpu.state.blend_set('ALPHA'); gpu.state.depth_test_set('LESS_EQUAL')
        shader.bind(); shader.uniform_float('color', (*cor[:3], .18))
        tris = [c[i] for a, b, d, e in faces for i in (a, b, d, a, d, e)]
        batch_for_shader(shader, 'TRIS', {'pos': tris}).draw(shader)
        shader.uniform_float('color', cor)
        linhas = linhas_hud(obj, [])[1]
        batch_for_shader(shader, 'LINES', {'pos': [p for l in linhas for p in l['pontos']]}).draw(shader)
        if s.get('etapa') == 'FRENTE':
            gpu.state.depth_test_set('NONE')
            realcar_frente(shader, dados_visuais(obj), s.get('face_hover'))
    finally:
        gpu.state.depth_test_set('NONE'); gpu.state.blend_set('NONE')


class OBJECT_OT_definir_area(Operator):
    bl_idname = 'object.cabinet_definir_area'
    bl_label = 'Definir Area de Criacao'
    bl_options = {'INTERNAL'}
    destino: StringProperty(options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def invoke(self, context, event):
        destino = self.destino or context.scene.cabinet_aba
        if not self.destino and destino in {'PRATELEIRAS', 'DIVISORIAS'}:
            return iniciar_internos(context, 'VOLUME')
        if destino not in DESTINOS:
            return {'CANCELLED'}
        encerrar()
        area = _biblioteca_faixa.viewport(context.screen)
        if area is None:
            return {'CANCELLED'}
        ativo = context.object
        modulo = _modulos._conj_de(ativo) if ativo is not None and ativo.select_get() else None
        _estado[0] = dict(destino=destino, objeto='', modulo=modulo.name if modulo else '',
            cena=context.scene.name, area=area.as_pointer(),
            selecao=[o.name for o in context.selected_objects],
            ativo=context.object.name if context.object else '',
            handler=None, timer=None)
        try:
            _estado[0]['handler'] = bpy.types.SpaceView3D.draw_handler_add(desenhar, (), 'WINDOW', 'POST_VIEW')
            _estado[0]['timer'] = context.window_manager.event_timer_add(.1, window=context.window)
            context.scene.cabinet_aba = destino
            area.header_text_set('Clique para posicionar a area | Esc cancela')
            context.window_manager.modal_handler_add(self)
        except Exception:
            encerrar(); raise
        _eventos._redesenhar_viewports(context)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        s = _estado[0]
        if s is None:
            return {'FINISHED'}
        try:
            if context.scene.name != s['cena'] or _eventos._desfazendo[0]:
                encerrar(); return {'CANCELLED'}
            area = next((a for a in context.screen.areas if a.as_pointer() == s['area']), None)
            if area is None or area.type != 'VIEW_3D':
                encerrar(); return {'CANCELLED'}
            regiao = next(r for r in area.regions if r.type == 'WINDOW')
            dentro = regiao.x <= event.mouse_x < regiao.x + regiao.width and regiao.y <= event.mouse_y < regiao.y + regiao.height
            if event.type == 'ESC' and event.value == 'PRESS':
                esquecer(); return {'CANCELLED'}
            if event.type == 'TAB' and dentro:
                return {'RUNNING_MODAL'}
            if s.get('etapa') == 'FRENTE':
                if event.type == 'BACK_SPACE' and event.value == 'PRESS':
                    s.pop('etapa', None); s.pop('face_hover', None)
                    area.header_text_set('Ajuste a area | Enter aplica | Esc cancela')
                    return {'RUNNING_MODAL'}
                if dentro and event.type in {'MOUSEMOVE', 'LEFTMOUSE'}:
                    xy = (event.mouse_x - regiao.x, event.mouse_y - regiao.y)
                    rv = area.spaces.active.region_3d
                    s['face_hover'] = face_no_raio(dados(objeto()),
                        view3d_utils.region_2d_to_origin_3d(regiao, rv, xy),
                        view3d_utils.region_2d_to_vector_3d(regiao, rv, xy))
                    area.tag_redraw()
                    if event.type == 'LEFTMOUSE' and event.value == 'PRESS' and s['face_hover']:
                        s['frente'] = s['face_hover']
                        entregar(context); return {'FINISHED'}
                    return {'RUNNING_MODAL'}
                return {'PASS_THROUGH'}
            if event.type in {'RET', 'NUMPAD_ENTER'} and objeto() is not None:
                # O Enter que confirma um campo/G nao confirma tambem a area.
                if event.value == 'PRESS' and dentro:
                    s['aplicar_tecla'] = True
                    return {'RUNNING_MODAL'}
                if event.value == 'RELEASE' and s.pop('aplicar_tecla', False):
                    return solicitar_frente(context)
            if not dentro or event.type != 'LEFTMOUSE' or event.value != 'PRESS':
                return {'PASS_THROUGH'}
            with context.temp_override(area=area, region=regiao):
                xy = (event.mouse_x - regiao.x, event.mouse_y - regiao.y)
                if objeto() is not None:
                    return {'PASS_THROUGH'} if _hud._acertar_hud(context, Vector(xy)) else {'RUNNING_MODAL'}
                modulo = bpy.data.objects.get(s['modulo'])
                if modulo is not None:
                    rv = area.spaces.active.region_3d
                    acerto = _gavetas.raio_no_modulo(context, modulo,
                        view3d_utils.region_2d_to_origin_3d(regiao, rv, xy),
                        view3d_utils.region_2d_to_vector_3d(regiao, rv, xy))
                else:
                    acerto = _hud._raio_cru(context, xy)
                if acerto:
                    ponto = acerto[1]
                    modulo = _modulos._conj_de(acerto[0]) or modulo
                else:
                    rv = area.spaces.active.region_3d
                    inicio = view3d_utils.region_2d_to_origin_3d(regiao, rv, xy)
                    direcao = view3d_utils.region_2d_to_vector_3d(regiao, rv, xy)
                    ponto = intersect_line_plane(inicio, inicio + direcao, context.scene.cursor.location,
                                                rv.view_rotation @ Vector((0, 0, 1)))
                if ponto is not None:
                    obj = criar_referencia(context, s['destino'], ponto, modulo)
                    s['objeto'] = obj.name
                    dados_visuais(obj)
                    area.header_text_set('Ajuste as faces ou use G/R/S | Enter aplica | Esc cancela')
            _eventos._redesenhar_viewports(context)
            return {'RUNNING_MODAL'}
        except ValueError as erro:
            self.report({'WARNING'}, str(erro))
            return {'RUNNING_MODAL'}
        except Exception:
            encerrar(); raise

    def cancel(self, context):
        encerrar()


class OBJECT_OT_aplicar_area(Operator):
    bl_idname = 'object.cabinet_aplicar_area'
    bl_label = 'Aplicar Area'
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        return objeto() is not None

    def execute(self, context):
        try:
            resultado = solicitar_frente(context)
            return {'FINISHED'} if 'RUNNING_MODAL' in resultado else resultado
        except ValueError as erro:
            self.report({'WARNING'}, str(erro)); return {'CANCELLED'}


class OBJECT_OT_cancelar_area(Operator):
    bl_idname = 'object.cabinet_cancelar_area'
    bl_label = 'Cancelar Area'
    bl_options = {'INTERNAL'}

    def execute(self, context):
        esquecer(); return {'FINISHED'}
