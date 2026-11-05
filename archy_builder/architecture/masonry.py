"""Face classification and local support for architectural fixtures."""
import bpy
import bmesh
import blf
import gpu
import numpy as np
import math
from bpy.props import StringProperty, BoolProperty
from bpy.types import Operator
from gpu_extras.batch import batch_for_shader
from mathutils import Matrix, Vector

_ambientes = _paredes = _paredes_edicao = _paredes_selecao = _opcoes = _gaveta = None
_instalacoes = None
_hud = None
_eventos = None

TIPOS = ('PAREDE', 'PISO', 'TETO')
ROTULOS = {'PAREDE': "Walls", 'PISO': "Floor", 'TETO': "Ceiling"}
CORES = {'PAREDE': (.20, .54, .94), 'PISO': (.24, .77, .39), 'TETO': (.96, .62, .16)}
ATR_TIPO = 'cabinet_tipo_superficie'
ATR_FACE = 'cabinet_face_apoio'
CHAVE_TIPADA = 'cabinet_alvenaria_tipificada'
CHAVE_ABRIR = 'cabinet_menu_criar_alvenaria'
CHAVE_VISUAL = 'cabinet_alvenaria_visual'
ALVO_TIPO = '@tipo_alvenaria'
MARCA = 'cabinet_instalacao'
MEDIDAS = 'cabinet_instalacao_medidas'
PECA = 'cabinet_instalacao_peca'
CHAVE_VINCULO = 'cabinet_apoio_instalacao'
CHAVE_SEM_APOIO = 'cabinet_instalacao_sem_apoio'
_regioes = [{}]
_cotas_menu = [{}]
_guias = [{}]
_visuais = [{}]


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


def classificar(obj, tipo, substituir=False):
    if tipo not in TIPOS or obj.mode != 'EDIT':
        raise ValueError("Select faces in Edit Mode")
    if obj.data.users > 1:
        raise ValueError("Make the mesh single-user before classifying faces")
    bm = bmesh.from_edit_mesh(obj.data)
    if not substituir and not any(f.select and not f.hide for f in bm.faces):
        raise ValueError("Select the masonry faces")
    camada = bm.faces.layers.int.get(ATR_TIPO)
    legado = _paredes.alvenaria_definida(obj) and not obj.get(CHAVE_TIPADA)
    herdadas = {}
    if legado:
        for i, face in enumerate(bm.faces):
            valor = face[camada] if camada is not None else 0
            if not valor:
                normal = _paredes._normal_no_mundo(obj, face.normal)
                efetivo = _paredes.tipo_superficie(normal)
                valor = TIPOS.index(efetivo)+1 if efetivo in TIPOS else 0
            herdadas[i] = valor
    if camada is None:
        camada = bm.faces.layers.int.new(ATR_TIPO)
        _ambientes._faces_nativas[0].pop(obj.data.name, None)
    for i, face in enumerate(bm.faces):
        if legado:
            face[camada] = herdadas[i]
        if face.select and not face.hide:
            face[camada] = TIPOS.index(tipo) + 1
        elif substituir and not face.hide and face[camada] == TIPOS.index(tipo)+1:
            face[camada] = 0
    obj[CHAVE_TIPADA] = True
    obj[_paredes.CHAVE_ALVENARIA] = True
    bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
    _paredes._retangulos.clear()
    _regioes[0].clear()


class OBJECT_OT_classificar_alvenaria(Operator):
    bl_idname = 'object.cabinet_classificar_alvenaria'
    bl_label = "Classify Masonry"
    bl_options = {'UNDO'}
    tipo: StringProperty(options={'SKIP_SAVE'})
    editar: BoolProperty(options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return context.mode in {'OBJECT', 'EDIT_MESH'} and bool(
            candidatos(context) or _paredes.alvenaria_definida(context.object))

    def execute(self, context):
        try:
            classificar(context.object, self.tipo)
        except ValueError as erro:
            self.report({'WARNING'}, str(erro))
            return {'CANCELLED'}
        return {'FINISHED'}

    def invoke(self, context, event):
        try:
            self.token = iniciar_edicao(context, self.tipo, self.editar)
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


def candidatos(context):
    selecionados = getattr(context, 'selected_objects', ())
    return [obj for obj in selecionados if _paredes_edicao.superficie(obj)
            and not _paredes.alvenaria_definida(obj)]


def alvo_novo(context):
    novos = candidatos(context)
    return context.object if context.object in novos else next(iter(novos), None)


def iniciar_edicao(context, tipo, editar=False):
    if tipo not in TIPOS:
        raise ValueError("Choose Wall, Floor or Ceiling")
    obj = context.object if editar else alvo_novo(context)
    if obj is None or (editar and not _paredes.alvenaria_definida(obj)):
        raise ValueError("Select an object compatible with this operation")
    if _paredes_edicao.ativa(context):
        _paredes_edicao.encerrar()
    if context.mode == 'EDIT_MESH' and context.edit_object != obj:
        bpy.ops.object.mode_set(mode='OBJECT')
    token = _ambientes.preparar_selecao(context, obj, classificar=tipo)
    s = _ambientes._edicao_faces[0]
    s['substituir_tipo'] = editar
    context.scene.cabinet_aba = 'ALVENARIA'
    if context.screen:
        context.screen[_instalacoes.CHAVE_TIPO_MENU] = tipo
    if editar:
        bm = bmesh.from_edit_mesh(obj.data)
        camada = bm.faces.layers.int.get(ATR_TIPO)
        valor = TIPOS.index(tipo)+1
        for face in bm.faces:
            herdado = (not obj.get(CHAVE_TIPADA) and (camada is None or not face[camada]) and
                       _paredes.tipo_superficie(_paredes._normal_no_mundo(obj, face.normal)) == tipo)
            face.select_set(not face.hide and (herdado or (camada is not None and face[camada] == valor)))
        bm.select_flush_mode()
        bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
        _ambientes.guardar_selecao(obj)
    s['visual_sujo'] = True
    atualizar_visual(obj)
    return token


def confirmar(context):
    s = _ambientes._edicao_faces[0]
    if s is None or not s.get('classificar') or _eventos._desfazendo[0]:
        raise ValueError("No active masonry selection")
    obj = context.edit_object
    if obj is None or obj.name != s['objeto'] or context.scene.name != s['cena']:
        raise ValueError("The masonry selection lost its source object")
    # Native keyboard selection may finish before the next timer tick.
    _ambientes.guardar_selecao(obj)
    if not s['selecionadas'] and not s.get('substituir_tipo'):
        raise ValueError("Select at least one face")
    classificar(obj, s['classificar'], substituir=s.get('substituir_tipo', False))
    _ambientes.encerrar_selecao()
    bpy.ops.object.mode_set(mode='OBJECT')
    context.scene.cabinet_aba = 'ALVENARIA'
    _paredes._redesenhar()


class OBJECT_OT_confirmar_alvenaria(Operator):
    bl_idname = 'object.cabinet_confirmar_alvenaria'
    bl_label = "Confirm selection"
    bl_options = {'UNDO'}

    @classmethod
    def poll(cls, context):
        s = _ambientes._edicao_faces[0]
        return bool(s and s.get('classificar') and context.mode == 'EDIT_MESH')

    def execute(self, context):
        try:
            confirmar(context)
        except ValueError as erro:
            self.report({'WARNING'}, str(erro))
            return {'CANCELLED'}
        return {'FINISHED'}


def atualizar_visual(obj):
    s = _ambientes._edicao_faces[0]
    if not s or not s.get('classificar') or not s.get('visual_sujo', True):
        return
    bm = bmesh.from_edit_mesh(obj.data).copy()
    try:
        bm.normal_update()
        bm.faces.index_update()
        camada = bm.faces.layers.int.get(ATR_TIPO)
        valores = {}
        escolhidas = set(s['selecionadas'])
        hover = s.get('hover')
        if hover is not None:
            escolhidas.update((s['ids'][hover],) if s['manual'] else s['grupos'][hover])
        tipo_atual = TIPOS.index(s['classificar'])+1
        for face in bm.faces:
            valor = face[camada] if camada else 0
            if not valor and _paredes.alvenaria_definida(obj) and not obj.get(CHAVE_TIPADA):
                normal = _paredes._normal_no_mundo(obj, face.normal)
                tipo = _paredes.tipo_superficie(normal)
                valor = TIPOS.index(tipo)+1 if tipo in TIPOS else 0
            if face.index in escolhidas:
                valor = tipo_atual
            elif s.get('substituir_tipo') and valor == tipo_atual and not face.hide:
                valor = 0
            valores[face.index] = valor
        s['visual_tipos'] = visual_da_malha(bm, valores)
        s['visual_sujo'] = False
    finally:
        bm.free()


def visual_da_malha(bm, valores):
    """The same numeric copy drives editing, visibility, and outlines by type."""
    visual = bm.faces.layers.int.new('tipo_visual')
    for face in bm.faces:
        face[visual] = valores[face.index]
    arestas = [e for e in bm.edges if len(e.link_faces) == 2
               and e.link_faces[0][visual] == e.link_faces[1][visual]]
    bmesh.ops.dissolve_limit(bm, angle_limit=.001, verts=[], edges=arestas)
    bm.faces.index_update()
    grupos, faces, bordas = {}, {}, {}
    for tri in bm.calc_loop_triangles():
        face = tri[0].face
        valor = face[visual]
        if not 1 <= valor <= len(TIPOS) or face.hide:
            continue
        ps = [tuple(l.vert.co) for l in tri]
        grupos.setdefault(valor, []).extend(ps)
        ficha = faces.setdefault(face.index, dict(centro=tuple(face.calc_center_median()),
            normal=tuple(face.normal), triangulos=[], tipo=TIPOS[valor-1]))
        ficha['triangulos'].extend(ps)
    for face in bm.faces:
        valor = face[visual]
        if 1 <= valor <= len(TIPOS) and not face.hide:
            bordas.setdefault(valor, []).extend(tuple(v.co) for e in face.edges for v in e.verts)
    return dict(grupos=grupos, faces=list(faces.values()), bordas=bordas)


def atualizar_visuais(context):
    if not context.scene.get(CHAVE_VISUAL, False):
        _visuais[0].clear()
        return
    nomes = set()
    for obj in context.scene.objects:
        if not _paredes.alvenaria_definida(obj) or obj.data.is_editmode:
            continue
        nomes.add(obj.name)
        if obj.name in _visuais[0]:
            continue
        bm = bmesh.new()
        try:
            bm.from_mesh(obj.data)
            bm.normal_update();bm.faces.index_update()
            camada = bm.faces.layers.int.get(ATR_TIPO)
            valores = {}
            for face in bm.faces:
                valor = face[camada] if camada else 0
                if not valor and not obj.get(CHAVE_TIPADA):
                    tipo = _paredes.tipo_superficie(_paredes._normal_no_mundo(obj, face.normal))
                    valor = TIPOS.index(tipo)+1 if tipo in TIPOS else 0
                valores[face.index] = valor
            _visuais[0][obj.name] = visual_da_malha(bm, valores)
        finally:
            bm.free()
    for nome in tuple(_visuais[0]):
        if nome not in nomes:
            del _visuais[0][nome]


def desenhar_tipos(context):
    if _eventos._desfazendo[0] or not context.scene.get(CHAVE_VISUAL, False):
        return
    s = _ambientes._edicao_faces[0]
    if s and s.get('classificar'):
        return
    for nome, visual in _visuais[0].items():
        obj = context.scene.objects.get(nome)
        if obj is not None and obj.visible_get(viewport=context.space_data):
            desenhar_visual(context, obj, visual)


class OBJECT_OT_visualizar_alvenaria(Operator):
    bl_idname = 'object.cabinet_visualizar_alvenaria'
    bl_label = "Show Masonry types"
    bl_options = {'UNDO'}

    def execute(self, context):
        context.scene[CHAVE_VISUAL] = not context.scene.get(CHAVE_VISUAL, False)
        atualizar_visuais(context)
        _paredes._redesenhar()
        return {'FINISHED'}


def desenhar_visual(context, obj, visual=None):
    s = _ambientes._edicao_faces[0]
    if visual is None:
        if not s or not s.get('classificar') or not s.get('visual_tipos'):
            return
        visual = s['visual_tipos']
    anterior = gpu.state.blend_get(), gpu.state.depth_test_get(), gpu.state.depth_mask_get()
    try:
        gpu.state.blend_set('ALPHA')
        gpu.state.depth_test_set('LESS_EQUAL')
        gpu.state.depth_mask_set(False)
        with gpu.matrix.push_pop_projection(), gpu.matrix.push_pop():
            projecao = gpu.matrix.get_projection_matrix()
            projecao[2] = projecao[2]-projecao[3]*1e-6
            gpu.matrix.load_projection_matrix(projecao)
            gpu.matrix.multiply_matrix(obj.matrix_world)
            shader = gpu.shader.from_builtin('UNIFORM_COLOR')
            for valor, ps in visual['grupos'].items():
                shader.bind()
                shader.uniform_float('color', (*CORES[TIPOS[valor-1]], .24))
                batch_for_shader(shader, 'TRIS', {'pos': ps}).draw(shader)
            for valor, ps in visual.get('bordas', {}).items():
                shader.bind()
                shader.uniform_float('color', (*CORES[TIPOS[valor-1]], 1))
                batch_for_shader(shader, 'LINES', {'pos': ps}).draw(shader)
        for face in visual['faces']:
            normal = _paredes._normal_no_mundo(obj, face['normal'])
            matriz = referencial((0, 0, 0), normal)
            ficha = dict(face, eixos=(matriz.to_3x3().col[0], matriz.to_3x3().col[1]))
            _ambientes._rotulo(context, obj, ficha, ROTULOS[face['tipo']])
    finally:
        gpu.state.blend_set(anterior[0])
        gpu.state.depth_test_set(anterior[1])
        gpu.state.depth_mask_set(anterior[2])


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
        raise ValueError("Select a valid support face")
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
    camada = apoio.data.attributes.get(ATR_TIPO)
    mascara = None
    if camada is not None:
        valores = np.empty(len(camada.data), dtype=np.int32)
        camada.data.foreach_get('value', valores)
        tipo = superficie(apoio, indice, normal)
        if tipo in TIPOS:
            mascara = valores == TIPOS.index(tipo)+1
            if not apoio.get(CHAVE_TIPADA):
                mascara |= valores == 0
    limites = _paredes._calcular_regiao(apoio.data, apoio.matrix_world, ponto, normal,
                                        indice, lateral, conferir_vertices=True, v=cima,
                                        mascara=mascara)
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
        raise ValueError("The installation requires a valid support surface")
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
    atualizar_visuais(bpy.context)
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
        _visuais[0].clear()


def esquecer():
    _visuais[0].clear()
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
    if not candidatos(context):
        return y
    tela = getattr(context, 'screen', None)
    aberto = bool(tela and tela.get(CHAVE_ABRIR))
    y -= 30
    itens.append((x, y, w, 30, "Create Masonry",
                  ('escolha', 'criar_alvenaria', not aberto, aberto, True, ALVO_TIPO)))
    y -= 6
    if aberto:
        y -= 25
        for i, (tipo, rotulo) in enumerate(zip(TIPOS, ("Wall", "Floor", "Ceiling"))):
            coluna = (w - 12) / 3
            itens.append((x + i * (coluna + 6), y, coluna, 25, rotulo,
                          ('escolha', 'tipo_alvenaria', tipo, False, True, ALVO_TIPO)))
        y -= 6
    return y


def painel(context, itens, x, y, w):
    s = _ambientes._edicao_faces[0]
    if s and s.get('classificar') and s['cena'] == context.scene.name:
        y = _gaveta._titulo_secao(itens, x, y+26, w, "Edit " + ROTULOS[s['classificar']])
        y -= 30
        itens.append((x, y, w, 30, "Confirm selection",
                      ('operador', 'object.cabinet_confirmar_alvenaria')))
        y -= 26
        itens.append((x, y, w, 20, "Enter confirms | Esc cancels", None))
        return y-12
    y = widgets_classificar(context, itens, x, y+30, w)
    if candidatos(context):
        return y
    obj = contexto(context)
    if obj is None:
        return y
    tipo = context.screen.get(_instalacoes.CHAVE_TIPO_MENU, 'PAREDE') if context.screen else 'PAREDE'
    y -= 30
    itens.append((x, y, w, 30, "Edit",
                  ('escolha', 'editar_alvenaria', tipo, False, True, ALVO_TIPO)))
    y = _instalacoes.widgets_seletor(context, itens, x, y-8, w)
    return _instalacoes.widgets_modelos(context, itens, x, y, w, tipo)


def contexto(context):
    s = _ambientes._edicao_faces[0]
    if s and s.get('classificar') and s['cena'] == context.scene.name:
        return context.scene.objects.get(s['objeto'])
    if _paredes.alvenaria_definida(context.object):
        return context.object
    return next((obj for obj in getattr(context, 'selected_objects', ())
                 if _paredes.alvenaria_definida(obj)), None)


def widgets(context, itens, x, y, w):
    obj = grupo_de(context.object)
    if obj is None:
        return y
    y = _gaveta._titulo_secao(itens, x, y + 26, w, obj.name)
    medidas = _cotas_menu[0].get(obj.name, {})
    if not medidas:
        if obj.get(CHAVE_SEM_APOIO):
            itens.append((x, y - 20, w, 20, "Select a new support surface", None))
            return y - 32
        return y
    colunas = min(2, _gaveta._colunas_medidas(context, w+24, 2))
    largura = (w - (colunas-1)*6) / colunas
    for i, (chave, mm) in enumerate((k, medidas[k] * 1000)
                                    for k in ('esquerda', 'direita', 'acima', 'abaixo')):
        rotulo = _opcoes.DIRECTION_LABELS[chave.upper()]
        itens.append((x + i % colunas * (largura + 6), y - 37 - i // colunas * 43,
                      largura, 37, rotulo + ': ' + _opcoes._texto_medida(mm),
                      ('medida', 'instalacao', chave, rotulo, mm)))
    return y - math.ceil(4/colunas)*43
