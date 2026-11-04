"""Classificacao por face e apoio local das instalacoes arquitetonicas."""
import bpy
import bmesh
import blf
import gpu
from bpy.props import StringProperty
from bpy.types import Operator
from gpu_extras.batch import batch_for_shader
from mathutils import Matrix, Vector

_ambientes = _paredes = _paredes_edicao = _paredes_selecao = _opcoes = _gaveta = None
_instalacoes = None
_hud = None

TIPOS = ('PAREDE', 'PISO', 'TETO')
ATR_TIPO = 'cabinet_tipo_superficie'
ATR_FACE = 'cabinet_face_apoio'
CHAVE_TIPADA = 'cabinet_alvenaria_tipificada'
CHAVE_ABRIR = 'cabinet_menu_criar_alvenaria'
ALVO_TIPO = '@tipo_alvenaria'
MARCA = 'cabinet_instalacao'
MEDIDAS = 'cabinet_instalacao_medidas'
PECA = 'cabinet_instalacao_peca'
CHAVE_VINCULO = 'cabinet_apoio_instalacao'
CHAVE_SEM_APOIO = 'cabinet_instalacao_sem_apoio'
_regioes = [{}]
_cotas_menu = [{}]
_guias = [{}]


def superficie(obj, indice, normal, malha=None):
    if not _paredes.alvenaria_definida(obj):
        return None
    malha = malha or obj.data
    camada = malha.attributes.get(ATR_TIPO)
    if camada is not None and 0 <= indice < len(camada.data):
        valor = camada.data[indice].value
        if 1 <= valor <= len(TIPOS):
            return TIPOS[valor - 1]
    return None if obj.get(CHAVE_TIPADA) else _paredes.tipo_superficie(normal)


def classificar(obj, tipo):
    if tipo not in TIPOS or obj.mode != 'EDIT':
        raise ValueError('Selecione faces em modo de edicao')
    if obj.data.users > 1:
        raise ValueError('Torne a malha independente antes de classificar as faces')
    bm = bmesh.from_edit_mesh(obj.data)
    if not any(f.select and not f.hide for f in bm.faces):
        raise ValueError('Selecione as faces da alvenaria')
    camada = bm.faces.layers.int.get(ATR_TIPO)
    if camada is None:
        camada = bm.faces.layers.int.new(ATR_TIPO)
        _ambientes._faces_nativas[0].pop(obj.data.name, None)
    for face in bm.faces:
        if face.select and not face.hide:
            face[camada] = TIPOS.index(tipo) + 1
    if not _paredes.alvenaria_definida(obj):
        obj[CHAVE_TIPADA] = True
    obj[_paredes.CHAVE_ALVENARIA] = True
    bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
    _paredes._retangulos.clear()
    _regioes[0].clear()


class OBJECT_OT_classificar_alvenaria(Operator):
    bl_idname = 'object.cabinet_classificar_alvenaria'
    bl_label = 'Classificar Alvenaria'
    bl_options = {'UNDO'}
    tipo: StringProperty(options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return (context.mode in {'OBJECT', 'EDIT_MESH'} and
                _paredes_edicao.superficie(context.object))

    def execute(self, context):
        try:
            classificar(context.object, self.tipo)
        except ValueError as erro:
            self.report({'WARNING'}, str(erro))
            return {'CANCELLED'}
        return {'FINISHED'}

    def invoke(self, context, event):
        if context.mode == 'EDIT_MESH' and any(
                f.select and not f.hide for f in bmesh.from_edit_mesh(context.object.data).faces):
            return self.execute(context)
        try:
            self.token = _ambientes.preparar_selecao(context, context.object,
                                                    classificar=self.tipo)
        except ValueError as erro:
            self.report({'WARNING'}, str(erro))
            return {'CANCELLED'}
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        try:
            return _ambientes.evento_selecao(context, event, self.token)
        except Exception:
            _ambientes.encerrar_selecao()
            raise

    def cancel(self, context):
        if id(_ambientes._edicao_faces[0]) == self.token:
            _ambientes.encerrar_selecao()


def grupo_de(obj):
    while obj is not None:
        if MARCA in obj:
            return obj
        obj = obj.parent
    return None


def referencial(ponto, normal):
    normal = Vector(normal).normalized()
    vertical = Vector((0, 0, 1))
    cima = vertical - normal * vertical.dot(normal)
    if cima.length < 1e-6:
        frente = Vector((0, 1, 0))
        cima = frente - normal * frente.dot(normal)
    cima.normalize()
    lateral = cima.cross(normal).normalized()
    matriz = Matrix((lateral, cima, normal)).transposed().to_4x4()
    matriz.translation = ponto
    return matriz


def _rigida(obj):
    return Matrix.Translation(obj.matrix_world.translation) @ obj.matrix_world.to_quaternion().to_matrix().to_4x4()


def _identificar_face(apoio, indice):
    if apoio.data.users > 1:
        apoio.data = apoio.data.copy()
    camada = apoio.data.attributes.get(ATR_FACE)
    if camada is None:
        camada = apoio.data.attributes.new(ATR_FACE, 'INT', 'FACE')
    valor = camada.data[indice].value
    if valor <= 0 or sum(f.value == valor for f in camada.data) != 1:
        valor = int(apoio.get(ATR_FACE, 0)) + 1
        camada.data[indice].value = valor
        apoio[ATR_FACE] = valor
    return valor


def vincular(obj, apoio, indice, matriz, tipo):
    if apoio.data.is_editmode or not 0 <= indice < len(apoio.data.polygons):
        raise ValueError('Selecione uma face de apoio valida')
    obj[CHAVE_VINCULO] = dict(
        uid=_paredes._uid_da_parede(apoio), nome=apoio.name, tipo=tipo,
        face=_identificar_face(apoio, indice),
        matriz=[list(linha) for linha in _rigida(apoio).inverted() @ matriz])
    obj.matrix_world = matriz
    obj.pop(CHAVE_SEM_APOIO, None)


def apoio_de(obj):
    dados = obj.get(CHAVE_VINCULO)
    if dados is None:
        return None
    apoio = bpy.data.objects.get(dados['nome'])
    if apoio is not None and apoio.get(_paredes.CHAVE_UID_PAREDE) == dados['uid']:
        return apoio
    candidatos = [o for o in bpy.context.scene.objects
                  if o.get(_paredes.CHAVE_UID_PAREDE) == dados['uid']]
    return candidatos[0] if len(candidatos) == 1 else None


def regiao(apoio, indice, matriz):
    lateral, cima, normal = (matriz.to_3x3().col[i] for i in range(3))
    ponto = apoio.matrix_world @ apoio.data.polygons[indice].center
    limites = _paredes._calcular_regiao(apoio.data, apoio.matrix_world, ponto, normal,
                                        indice, lateral, conferir_vertices=True, v=cima)
    if limites:
        limites['triangulos'] = _paredes_selecao.triangulos_reais(
            apoio.data, limites['faces'], apoio.matrix_world)
    return limites


def resolver(obj):
    apoio = apoio_de(obj)
    dados = obj.get(CHAVE_VINCULO)
    if apoio is None or not _paredes.alvenaria_definida(apoio) or apoio.data.is_editmode:
        return None
    matriz = _rigida(apoio) @ Matrix(dados['matriz'])
    chave = (apoio.as_pointer(), dados['face'], _paredes._assinatura(apoio.matrix_world))
    if chave not in _regioes[0]:
        camada = apoio.data.attributes.get(ATR_FACE)
        indices = [i for i, f in enumerate(camada.data) if f.value == dados['face']] if camada else []
        if len(indices) != 1:
            _regioes[0][chave] = None
        else:
            indice = indices[0]
            normal = _paredes._normal_no_mundo(apoio, apoio.data.polygons[indice].normal)
            tipo = superficie(apoio, indice, normal)
            limites = regiao(apoio, indice, matriz) if tipo == dados['tipo'] else None
            _regioes[0][chave] = (indice, limites) if limites else None
    resultado = _regioes[0][chave]
    return (apoio, matriz, *resultado) if resultado else None


def cotas(obj, resolvido=None):
    resolvido = resolvido or resolver(obj)
    if resolvido is None:
        return {}
    _, matriz, _, limites = resolvido
    largura, altura = obj['cabinet_instalacao_medidas'][:2]
    lateral, cima = (matriz.to_3x3().col[i] for i in (0, 1))
    x, y = matriz.translation.dot(lateral), matriz.translation.dot(cima)
    esq, dir, abaixo, acima = limites['retangulo']
    return dict(esquerda=x - largura / 2 - esq, direita=dir - x - largura / 2,
                abaixo=y - altura / 2 - abaixo, acima=acima - y - altura / 2)


def destino_cota(obj, lado, valor):
    resolvido = resolver(obj)
    medidas = cotas(obj, resolvido) if resolvido else {}
    if lado not in medidas:
        raise ValueError('A instalacao precisa de um apoio valido')
    apoio, matriz, indice, _ = resolvido
    eixo = 0 if lado in {'esquerda', 'direita'} else 1
    sinal = 1 if lado in {'esquerda', 'abaixo'} else -1
    matriz.translation += matriz.to_3x3().col[eixo] * sinal * (valor - medidas[lado])
    return apoio, matriz, indice, resolvido[3]


def editar_cota(obj, lado, valor):
    try:
        apoio, matriz, indice, _ = destino_cota(obj, lado, valor)
    except ValueError as erro:
        return str(erro)
    vincular(obj, apoio, indice, matriz, obj[CHAVE_VINCULO]['tipo'])
    return None


def verificar():
    cotas_menu = {}
    guias = {}
    for obj in bpy.context.scene.objects:
        if MARCA not in obj or CHAVE_VINCULO not in obj:
            continue
        resolvido = resolver(obj)
        if resolvido is None:
            if not obj.get(CHAVE_SEM_APOIO):
                obj[CHAVE_SEM_APOIO] = True
            continue
        obj.pop(CHAVE_SEM_APOIO, None)
        if _instalacoes.absorver_transformacao(obj, resolvido):
            resolvido = resolver(obj)
        matriz = resolvido[1]
        if _paredes._assinatura(obj.matrix_world) != _paredes._assinatura(matriz):
            obj.matrix_world = matriz
        cotas_menu[obj.name] = cotas(obj, resolvido)
        centro = matriz.translation
        l, a = obj[MEDIDAS][:2]
        u, v = (matriz.to_3x3().col[i] for i in (0, 1))
        origens = dict(esquerda=(centro-u*l/2, -u), direita=(centro+u*l/2, u),
                       acima=(centro+v*a/2, v), abaixo=(centro-v*a/2, -v))
        guias[obj.name] = [(p, p + eixo*cotas_menu[obj.name][chave], cotas_menu[obj.name][chave])
                           for chave, (p, eixo) in origens.items()]
    _cotas_menu[0] = cotas_menu
    _guias[0] = guias


def invalidar(depsgraph):
    if any(u.is_updated_geometry and isinstance(u.id, bpy.types.Mesh)
           or isinstance(u.id, bpy.types.Object) and _paredes.alvenaria_definida(u.id)
           for u in depsgraph.updates):
        _regioes[0].clear()


def esquecer():
    _regioes[0].clear()
    _cotas_menu[0].clear()
    _guias[0].clear()


def desenhar_guias(context, tela, cor):
    grupo = grupo_de(getattr(context, 'object', None))
    linhas = _guias[0].get(grupo.name) if grupo else None
    if not linhas:
        return
    escala = context.preferences.system.ui_scale
    tamanho = _opcoes._opcao('hud_tamanho_rotulo') * escala
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    anterior = gpu.state.blend_get()
    try:
        gpu.state.blend_set('ALPHA')
        for p, q, valor in linhas:
            a, b = tela(p), tela(q)
            if a is None or b is None:
                continue
            shader.bind()
            shader.uniform_float('color', cor)
            batch_for_shader(shader, 'LINES', {'pos': (a, b)}).draw(shader)
            texto = _opcoes._texto_medida(valor * 1000)
            blf.size(0, tamanho)
            largura, altura = blf.dimensions(0, texto)
            meio = (a+b)/2
            _hud._caixa_texto_hud(meio.x-largura/2, meio.y-altura/2, texto, tamanho, escala)
    finally:
        gpu.state.blend_set(anterior)


def widgets_classificar(context, itens, x, y, w):
    tela = getattr(context, 'screen', None)
    aberto = bool(tela and tela.get(CHAVE_ABRIR))
    y -= 30
    itens.append((x, y, w, 30, 'Criar Alvenaria',
                  ('escolha', 'criar_alvenaria', not aberto, aberto, True, ALVO_TIPO)))
    y -= 6
    if aberto:
        y -= 25
        for i, (tipo, rotulo) in enumerate(zip(TIPOS, ('Parede', 'Piso', 'Teto'))):
            coluna = (w - 12) / 3
            itens.append((x + i * (coluna + 6), y, coluna, 25, rotulo,
                          ('escolha', 'tipo_alvenaria', tipo, False, True, ALVO_TIPO)))
        y -= 6
    return y


def widgets(context, itens, x, y, w):
    obj = grupo_de(context.object)
    if obj is None:
        return y
    y = _gaveta._titulo_secao(itens, x, y + 26, w, obj.name)
    medidas = _cotas_menu[0].get(obj.name, {})
    if not medidas:
        if obj.get(CHAVE_SEM_APOIO):
            itens.append((x, y - 20, w, 20, 'Selecione um novo apoio', None))
            return y - 32
        return y
    metade = (w - 6) / 2
    for i, (chave, mm) in enumerate((k, medidas[k] * 1000)
                                    for k in ('esquerda', 'direita', 'acima', 'abaixo')):
        rotulo = chave.capitalize()
        itens.append((x + i % 2 * (metade + 6), y - 37 - i // 2 * 43,
                      metade, 37, rotulo + ': ' + _opcoes._texto_medida(mm),
                      ('medida', 'instalacao', chave, rotulo, mm)))
    return y - 86
