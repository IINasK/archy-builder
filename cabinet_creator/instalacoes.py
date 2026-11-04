"""Montagens, recortes e posicionador das instalacoes da alvenaria."""
import math
import uuid

import bmesh
import bpy
import numpy as np
from bpy.props import BoolProperty, StringProperty
from bpy.types import Operator
from bpy_extras import view3d_utils
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

_alvenaria = _esquadrias = _paredes = _paredes_selecao = _paredes_edicao = None
_gaveta = _opcoes = _hud = _eventos = None

DONO = 'cabinet_instalacao_dono'
IDENTIDADE = 'cabinet_instalacao_uid'
CORTE = 'Cabinet Creator - Recorte '
FILTRO = 'Cabinet Creator - Superficie '
ATR_CORTE = 'cabinet_face_do_cortador'
ALVO = '@instalacao'
_previa = [None]
_poses = [{}]


def arvore(apoio):
    bm = bmesh.new()
    try:
        bm.from_mesh(apoio.data)
        return BVHTree.FromBMesh(bm)
    finally:
        bm.free()


def _peca(obj, nome, medidas, criar, centro=(0, 0, 0)):
    for peca in obj.children:
        if peca.get(_alvenaria.PECA) == nome:
            break
    else:
        malha = bpy.data.meshes.new(nome)
        bm = bmesh.new()
        try:
            criar(bm)
            bm.to_mesh(malha)
        finally:
            bm.free()
        peca = bpy.data.objects.new(nome, malha)
        obj.users_collection[0].objects.link(peca)
        peca.parent = obj
        peca[_alvenaria.PECA] = nome
        peca[DONO] = obj[IDENTIDADE]
    peca.matrix_basis = Matrix.Translation(centro) @ Matrix.Diagonal((*medidas, 1.))
    return peca


def caixa(obj, nome, centro, medidas):
    return _peca(obj, nome, medidas, lambda bm: bmesh.ops.create_cube(bm, size=1.), centro)


def cilindro(obj, nome, raio, fundo, centro=(0, 0, 0)):
    def criar(bm):
        bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=64,
                             radius1=1., radius2=1., depth=1.)
    return _peca(obj, nome, (raio, raio, fundo), criar, centro)


def nova(context, modelo, nome, medidas, matriz):
    obj = bpy.data.objects.new(nome, None)
    context.collection.objects.link(obj)
    obj[_alvenaria.MARCA] = modelo
    obj[_alvenaria.MEDIDAS] = tuple(medidas)
    obj[IDENTIDADE] = uuid.uuid4().hex
    obj.empty_display_size = .06
    obj.matrix_world = matriz
    return obj


def _retangulo(matriz, medidas):
    x, y = (v / 2 for v in medidas[:2])
    return [matriz @ Vector(p) for p in ((-x, -y, 0), (x, -y, 0), (x, y, 0), (-x, y, 0))]


def _area_intersecao(limites, pontos, normal):
    try:
        recorte = _paredes_selecao.recortar(limites, pontos, normal)
    except ValueError:
        return 0.
    a, b, c = np.asarray(recorte['triangulos']).reshape(-1, 3, 3).transpose(1, 0, 2)
    return float(np.linalg.norm(np.cross(b-a, c-a), axis=1).sum() / 2)


def _medir_corte(apoio, matriz, indice, medidas, limites=None):
    limites = limites or _alvenaria.regiao(apoio, indice, matriz)
    if limites is None:
        raise ValueError('Selecione uma regiao plana de apoio')
    l, a, _ = medidas
    n = matriz.to_3x3().col[2]
    pontos = _retangulo(matriz, medidas)
    u, v = (matriz.to_3x3().col[i] for i in (0, 1))
    x0, x1, y0, y1 = limites['retangulo']
    if any(not (x0-.001 <= p.dot(u) <= x1+.001 and y0-.001 <= p.dot(v) <= y1+.001) for p in pontos):
        raise ValueError('A instalacao excede os limites do apoio')
    ocupada = _area_intersecao(limites, pontos, n)
    if ocupada < l*a*1e-4:
        return None
    if ocupada < l*a*.999:
        raise ValueError('O vao cruza uma borda ou um recorte existente')
    # So' atravessa ate' a face oposta da mesma casca. Uma face sem fundo
    # precisa apenas de um prisma fino para o Boolean do Blender.
    bm = bmesh.new()
    try:
        bm.from_mesh(apoio.data)
        bm.faces.ensure_lookup_table()
        frente = bm.faces[indice]
        visitadas = {frente}
        pendentes = [frente]
        while pendentes:
            for aresta in pendentes.pop().edges:
                for vizinha in aresta.link_faces:
                    if vizinha not in visitadas:
                        visitadas.add(vizinha)
                        pendentes.append(vizinha)
        if not all(e.is_manifold for f in visitadas for e in f.edges):
            return .002
        mundo = apoio.matrix_world
        inv = mundo.inverted_safe()
        origem = inv @ (matriz.translation - n*.0001)
        acerto, normal, outra, _ = BVHTree.FromBMesh(bm).ray_cast(origem, inv.to_3x3() @ -n)
        if acerto is None or bm.faces[outra] not in visitadas or (mundo.to_3x3().inverted_safe().transposed() @ normal).dot(n) >= 0:
            raise ValueError('Nao foi possivel delimitar a espessura do apoio')
        return max(.002, (matriz.translation - mundo @ acerto).dot(n) + .002)
    finally:
        bm.free()


def _recorte(obj, apoio, profundidade):
    nome = CORTE + obj[IDENTIDADE]
    nome_filtro = FILTRO + obj[IDENTIDADE]
    mod = apoio.modifiers.get(nome)
    filtro = apoio.modifiers.get(nome_filtro)
    if profundidade is None:
        if filtro:
            apoio.modifiers.remove(filtro)
        if mod:
            cortador = mod.object
            apoio.modifiers.remove(mod)
            if cortador:
                remover_peca(cortador)
        return
    l, a, _ = obj[_alvenaria.MEDIDAS]
    fundo = profundidade + .002
    centro = (0, 0, (.002 - profundidade) / 2)
    if obj[_alvenaria.MARCA] == 'SPOT_EMBUTIDO':
        cortador = cilindro(obj, 'Recorte', l/2, fundo, centro)
    else:
        cortador = caixa(obj, 'Recorte', centro, (l, a, fundo))
    cortador.display_type = 'WIRE'
    cortador.hide_render = True
    cortador.hide_select = True
    cortador.hide_set(True)
    if mod is None:
        mod = apoio.modifiers.new(nome, 'BOOLEAN')
        mod.operation = 'DIFFERENCE'
        mod.solver = 'EXACT'
    mod.object = cortador
    # No Boolean de uma casca aberta, o Blender pode devolver tampas do
    # prisma. Marcar a origem preserva somente a superficie recortada.
    if profundidade == .002:
        marca = cortador.data.attributes.get(ATR_CORTE)
        if marca is None:
            marca = cortador.data.attributes.new(ATR_CORTE, 'BOOLEAN', 'FACE')
            marca.data.foreach_set('value', [True] * len(marca.data))
            cortador.data.update()
        if filtro is None:
            filtro = apoio.modifiers.new(nome_filtro, 'NODES')
            filtro.node_group = _grupo_superficie()
    elif filtro:
        apoio.modifiers.remove(filtro)
        marca = cortador.data.attributes.get(ATR_CORTE)
        if marca:
            cortador.data.attributes.remove(marca)


def _grupo_superficie():
    nome = FILTRO.rstrip()
    grupo = next((g for g in bpy.data.node_groups if g.get(ATR_CORTE)), None)
    if grupo is not None:
        return grupo
    grupo = bpy.data.node_groups.new(nome, 'GeometryNodeTree')
    grupo[ATR_CORTE] = True
    grupo.interface.new_socket(name='Geometry', in_out='INPUT', socket_type='NodeSocketGeometry')
    grupo.interface.new_socket(name='Geometry', in_out='OUTPUT', socket_type='NodeSocketGeometry')
    entrada = grupo.nodes.new('NodeGroupInput')
    saida = grupo.nodes.new('NodeGroupOutput')
    marca = grupo.nodes.new('GeometryNodeInputNamedAttribute')
    marca.data_type = 'BOOLEAN'
    marca.inputs['Name'].default_value = ATR_CORTE
    apagar = grupo.nodes.new('GeometryNodeDeleteGeometry')
    apagar.domain = 'FACE'
    grupo.links.new(entrada.outputs['Geometry'], apagar.inputs['Geometry'])
    grupo.links.new(marca.outputs['Attribute'], apagar.inputs['Selection'])
    grupo.links.new(apagar.outputs['Geometry'], saida.inputs['Geometry'])
    return grupo


def remover_peca(peca):
    dados = peca.data
    tipo = peca.type
    bpy.data.objects.remove(peca, do_unlink=True)
    if dados and dados.users == 0:
        if tipo == 'MESH':
            bpy.data.meshes.remove(dados)
        elif tipo == 'LIGHT':
            bpy.data.lights.remove(dados)


def remover(obj):
    apoio = _alvenaria.apoio_de(obj)
    nome = CORTE + obj[IDENTIDADE]
    if apoio is not None and (mod := apoio.modifiers.get(nome)):
        apoio.modifiers.remove(mod)
    if apoio is not None and (filtro := apoio.modifiers.get(FILTRO + obj[IDENTIDADE])):
        apoio.modifiers.remove(filtro)
    for peca in tuple(obj.children):
        if peca.get(DONO) == obj[IDENTIDADE]:
            remover_peca(peca)
    bpy.data.objects.remove(obj, do_unlink=True)


def instalar(context, modelo, apoio, indice, matriz, medidas=None):
    nome, padrao = modelos()[modelo]
    medidas = medidas or padrao
    tipo = _alvenaria.superficie(apoio, indice, matriz.to_3x3().col[2])
    if tipo not in tipos_de_apoio(modelo):
        raise ValueError('Escolha uma superficie compativel com a instalacao')
    perfura = modelo in _esquadrias.MODELOS or modelo == 'SPOT_EMBUTIDO'
    profundidade = _medir_corte(apoio, matriz, indice, medidas) if perfura else None
    obj = nova(context, modelo, nome, medidas, matriz)
    try:
        _alvenaria.vincular(obj, apoio, indice, matriz, tipo)
        montar(obj)
        if perfura:
            _recorte(obj, apoio, profundidade)
    except Exception:
        remover(obj)
        raise
    return obj


def modelos():
    return _esquadrias.MODELOS


def tipos_de_apoio(modelo):
    return ('PAREDE',)


def montar(obj):
    _esquadrias.montar(obj)


def _aplicar_pose(obj, apoio, indice, matriz, limites, medidas):
    modelo = obj[_alvenaria.MARCA]
    perfura = modelo in _esquadrias.MODELOS or modelo == 'SPOT_EMBUTIDO'
    if modelo in _esquadrias.MODELOS and any(
            not math.isfinite(v) or v < minimo for v, minimo in zip(medidas, (.15, .15, .055))):
        raise ValueError('A medida nao comporta o batente ou o trilho')
    profundidade = _medir_corte(apoio, matriz, indice, medidas, limites) if perfura else None
    obj[_alvenaria.MEDIDAS] = medidas
    _alvenaria.vincular(obj, apoio, indice, matriz, obj[_alvenaria.CHAVE_VINCULO]['tipo'])
    montar(obj)
    if perfura:
        _recorte(obj, apoio, profundidade)


def absorver_transformacao(obj, resolvido):
    apoio, matriz, indice, limites = resolvido
    esperado = _paredes._assinatura(matriz)
    anterior = _poses[0].get(obj.name)
    _poses[0][obj.name] = esperado
    if anterior != esperado or not obj.select_get() or obj.mode != 'OBJECT':
        return False
    atual = obj.matrix_world.copy()
    if _paredes._assinatura(atual) == esperado:
        return False
    escala = atual.to_scale()
    medidas = tuple(obj[_alvenaria.MEDIDAS])
    destino = matriz.copy()
    deslocamento = atual.translation - matriz.translation
    normal = matriz.to_3x3().col[2]
    destino.translation += deslocamento - normal * deslocamento.dot(normal)
    if obj[_alvenaria.MARCA] in _esquadrias.MODELOS:
        medidas = tuple(abs(s)*m for s, m in zip(escala, medidas))
        destino.translation += matriz.to_3x3().col[1] * (medidas[1]-obj[_alvenaria.MEDIDAS][1])/2
    try:
        _aplicar_pose(obj, apoio, indice, destino, limites, medidas)
    except ValueError:
        return False
    _poses[0][obj.name] = _paredes._assinatura(destino)
    return True


def editar_cota(obj, lado, valor):
    try:
        apoio, matriz, indice, limites = _alvenaria.destino_cota(obj, lado, valor)
        _aplicar_pose(obj, apoio, indice, matriz, limites, tuple(obj[_alvenaria.MEDIDAS]))
    except ValueError as erro:
        return str(erro)
    return None


def editar_medida(obj, eixo, valor):
    anterior = tuple(obj[_alvenaria.MEDIDAS])
    medidas = list(anterior)
    medidas[eixo] = valor
    if not math.isfinite(valor) or valor < (.15 if eixo < 2 else .055):
        return 'A medida nao comporta o batente ou o trilho'
    resolvido = _alvenaria.resolver(obj)
    if resolvido is None:
        return 'Selecione um novo apoio'
    apoio, matriz, indice, limites = resolvido
    if eixo == 1:
        matriz.translation += matriz.to_3x3().col[1] * (valor - anterior[1]) / 2
    try:
        _aplicar_pose(obj, apoio, indice, matriz, limites, medidas)
    except ValueError as erro:
        return str(erro)
    return None


def verificar():
    for obj in tuple(bpy.context.scene.objects):
        dono = obj.get(DONO)
        if dono and obj.parent is None:
            remover_peca(obj)
        elif _paredes.alvenaria_definida(obj) and not obj.data.is_editmode:
            for mod in list(obj.modifiers):
                if mod.type != 'BOOLEAN' or not mod.name.startswith(CORTE):
                    continue
                if mod.object is None:
                    obj.modifiers.remove(mod)
                else:
                    invalido = bool(mod.object.parent and mod.object.parent.get(_alvenaria.CHAVE_SEM_APOIO))
                    if mod.show_viewport == invalido:
                        mod.show_viewport = mod.show_render = not invalido
            for mod in list(obj.modifiers):
                if mod.name.startswith(FILTRO) and not obj.modifiers.get(CORTE + mod.name[len(FILTRO):]):
                    obj.modifiers.remove(mod)


def esquecer():
    _previa[0] = None
    _poses[0].clear()


def desenhar_previa(context, tela):
    previa = _previa[0]
    if previa and previa['regiao'] == context.region.as_pointer():
        _paredes._desenhar_face_alvo(previa, tela, _hud._cor_realce_hud(), context.region, context.region_data)


class OBJECT_OT_instalar(Operator):
    bl_idname = 'object.cabinet_instalar'
    bl_label = 'Posicionar instalacao'
    bl_options = {'UNDO'}

    modelo: StringProperty(options={'SKIP_SAVE'})
    arrastar: BoolProperty(options={'SKIP_SAVE'})

    def invoke(self, context, event):
        area = _paredes_edicao.viewport(context)
        if self.modelo not in modelos() or area is None or context.mode != 'OBJECT':
            return {'CANCELLED'}
        self.area = area.as_pointer()
        self.inicio = (event.mouse_x, event.mouse_y)
        self.cena = context.scene.name
        self.apoio = ''
        self.alvo = None
        self.arvore = None
        self.referencia = None
        apoio = _paredes_edicao.contexto_painel(context)
        if _paredes.alvenaria_definida(apoio) and self.modelo in _esquadrias.MODELOS:
            face = _paredes_edicao.face_do_objeto(context, apoio)
            if face:
                ponto, normal, limites = face
                self.referencia = (apoio.name, tuple(ponto), tuple(normal))
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _mover(self, context, area, regiao, event):
        self.alvo = None
        _previa[0] = None
        xy = event.mouse_x - regiao.x, event.mouse_y - regiao.y
        if not (0 <= xy[0] < regiao.width and 0 <= xy[1] < regiao.height):
            return
        rv = area.spaces.active.region_3d
        origem = view3d_utils.region_2d_to_origin_3d(regiao, rv, xy)
        direcao = view3d_utils.region_2d_to_vector_3d(regiao, rv, xy)
        with context.temp_override(area=area, region=regiao):
            atingido = _hud._raio_cru(context, xy)
        if atingido:
            apoio, _, _, _, _ = atingido
            apoio = _paredes_selecao.fonte_da_exibicao(apoio) or apoio
        else:
            apoio = None
        if not _paredes.alvenaria_definida(apoio) and self.referencia:
            apoio = bpy.data.objects.get(self.referencia[0])
        if not _paredes.alvenaria_definida(apoio) or apoio.data.is_editmode:
            return
        if self.apoio != apoio.name:
            self.apoio = apoio.name
            self.arvore = arvore(apoio)
        inv = apoio.matrix_world.inverted_safe()
        local, n, indice, _ = self.arvore.ray_cast(inv @ origem, inv.to_3x3() @ direcao)
        if local is None:
            if not self.referencia or self.referencia[0] != apoio.name:
                return
            _, ref, normal = self.referencia
            normal = Vector(normal)
            produto = normal.dot(direcao)
            if abs(produto) < 1e-6:
                return
            ponto = origem + direcao * (Vector(ref)-origem).dot(normal)/produto
            _, n, indice, _ = self.arvore.find_nearest(inv @ ponto)
            if indice is None:
                return
            local = inv @ ponto
        normal = _paredes._normal_no_mundo(apoio, n)
        if _alvenaria.superficie(apoio, indice, normal) not in tipos_de_apoio(self.modelo):
            return
        medidas = modelos()[self.modelo][1]
        ponto = apoio.matrix_world @ local
        self.referencia = apoio.name, tuple(ponto), tuple(normal)
        matriz = _alvenaria.referencial(ponto, normal)
        if self.modelo in _esquadrias.MODELOS:
            matriz.translation += matriz.to_3x3().col[1] * medidas[1] / 2
        ps = _retangulo(matriz, medidas)
        _previa[0] = dict(regiao=regiao.as_pointer(), contorno=list(zip(ps, ps[1:]+ps[:1])),
                          triangulos=np.array([ps[i] for i in (0,1,2,0,2,3)]))
        self.alvo = (apoio.name, indice, matriz, medidas)

    def modal(self, context, event):
        area = next((a for a in context.screen.areas if a.as_pointer() == self.area), None)
        if area is None or context.scene.name != self.cena or _eventos._desfazendo[0]:
            self.cancel(context)
            return {'CANCELLED'}
        if event.type in {'ESC', 'RIGHTMOUSE'}:
            self.cancel(context)
            return {'CANCELLED'}
        regiao = next(r for r in area.regions if r.type == 'WINDOW')
        if event.type == 'MOUSEMOVE':
            self._mover(context, area, regiao, event)
            area.tag_redraw()
        if event.type == 'LEFTMOUSE' and event.value == ('RELEASE' if self.arrastar else 'PRESS'):
            self._mover(context, area, regiao, event)
            if self.arrastar and math.dist(self.inicio, (event.mouse_x, event.mouse_y)) < 6:
                self.arrastar = False
                return {'RUNNING_MODAL'}
            if self.alvo is None:
                self.cancel(context)
                return {'CANCELLED'}
            nome, indice, matriz, medidas = self.alvo
            apoio = bpy.data.objects.get(nome)
            try:
                with context.temp_override(area=area, region=regiao):
                    obj = instalar(context, self.modelo, apoio, indice, matriz, medidas)
                    if area.spaces.active.local_view:
                        for peca in (obj, *obj.children):
                            if not peca.hide_select:
                                peca.local_view_set(area.spaces.active, True)
                    for selecionado in context.selected_objects:
                        selecionado.select_set(False)
                    obj.select_set(True)
                    context.view_layer.objects.active = obj
            except ValueError as erro:
                self.report({'WARNING'}, str(erro))
                self.cancel(context)
                return {'CANCELLED'}
            self.cancel(context)
            return {'FINISHED'}
        return {'PASS_THROUGH'}

    def cancel(self, context):
        esquecer()
        _eventos._redesenhar_viewports(context)


class OBJECT_OT_acao_instalacao(Operator):
    bl_idname = 'object.cabinet_acao_instalacao'
    bl_label = 'Editar instalacao'
    bl_options = {'UNDO'}
    acao: StringProperty(options={'SKIP_SAVE'})

    def execute(self, context):
        obj = _alvenaria.grupo_de(context.object)
        if obj is None:
            return {'CANCELLED'}
        if self.acao == 'remover':
            remover(obj)
            return {'FINISHED'}
        chaves = {'inverter': _esquadrias.CHAVE_FACE, 'espelhar': _esquadrias.CHAVE_LADO}
        if obj.get(_alvenaria.MARCA) != 'PORTA' or self.acao not in chaves:
            return {'CANCELLED'}
        chave = chaves[self.acao]
        obj[chave] = -obj.get(chave, 1)
        _esquadrias.posar(obj)
        return {'FINISHED'}


def widgets_modelos(context, itens, x, y, w, apoio):
    y = _gaveta._titulo_secao(itens, x, y + 26, w, 'Instalacoes')
    modelos_validos = [modelo for modelo in modelos() if apoio in tipos_de_apoio(modelo)]
    colunas = 3 if w >= 290 else 2
    coluna = (w - (colunas - 1)*6) / colunas
    for i, modelo in enumerate(modelos_validos):
        nome, _ = modelos()[modelo]
        itens.append((x + i % colunas * (coluna+6), y - 68 - i//colunas*74,
                      coluna, 68, nome, ('escolha', 'modelo_instalacao', modelo, False, True, ALVO)))
    return y - math.ceil(len(modelos_validos)/colunas)*74 - 6


def widgets(context, itens, x, y, w, obj):
    if obj.get(_alvenaria.MARCA) in _esquadrias.MODELOS:
        coluna = (w - 12) / 3
        for i, rotulo in enumerate(('Largura', 'Altura', 'Profundidade')):
            mm = obj[_alvenaria.MEDIDAS][i]*1000
            itens.append((x + i*(coluna+6), y-37, coluna, 37,
                          rotulo + ': ' + _opcoes._texto_medida(mm),
                          ('medida', 'instalacao_tamanho', str(i), rotulo, mm)))
        y -= 43
        for i in range(1 if obj[_alvenaria.MARCA] == 'PORTA' else 2):
            y -= 29
            itens.append((x, y, w, 25, 'Abertura %d' % (i+1),
                          ('slider', 'instalacao', obj.name, i, obj[_esquadrias.CHAVE_ABERTURAS][i])))
        if obj[_alvenaria.MARCA] == 'PORTA':
            metade = (w-6)/2
            y -= 34
            for i, rotulo in enumerate(('Inverter', 'Espelhar')):
                itens.append((x+i*(metade+6), y, metade, 28, rotulo,
                              ('escolha', 'acao_instalacao', rotulo.lower(), False, True, ALVO)))
    y -= 34
    itens.append((x, y, w, 28, 'Remover instalacao',
                  ('escolha', 'acao_instalacao', 'remover', False, True, ALVO)))
    return y - 6
