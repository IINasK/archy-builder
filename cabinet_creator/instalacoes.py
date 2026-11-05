"""Montagens, recortes e posicionador das instalacoes da alvenaria."""
import math
import uuid
import os

import bmesh
import blf
import bpy
import numpy as np
from bpy.props import BoolProperty, StringProperty, IntProperty, FloatVectorProperty
from bpy.types import Operator
from bpy_extras import view3d_utils
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

_alvenaria = _esquadrias = _paredes = _paredes_selecao = _paredes_edicao = None
_gaveta = _opcoes = _hud = _eventos = None
_iluminacao = None
_biblioteca = None

DONO = 'cabinet_instalacao_dono'
IDENTIDADE = 'cabinet_instalacao_uid'
CORTE = 'Cabinet Creator - Recorte '
FILTRO = 'Cabinet Creator - Superficie '
ATR_CORTE = 'cabinet_face_do_cortador'
ALVO = '@instalacao'
CHAVE_TIPO_MENU = 'cabinet_instalacoes_tipo'
CHAVE_CATEGORIA = 'cabinet_instalacoes_caminho'
CATEGORIAS = {
    'PORTA': ('Esquadrias', 'Portas'), 'SACADA': ('Esquadrias', 'Portas'),
    'JANELA': ('Esquadrias', 'Janelas'),
    'TOMADA': ('Eletrica', 'Tomadas'), 'INTERRUPTOR': ('Eletrica', 'Interruptores'),
    'SPOT_EMBUTIDO': ('Iluminacao', 'Spots'), 'SPOT_SOBREPOSTO': ('Iluminacao', 'Spots'),
    'PENDENTE': ('Iluminacao', 'Pendentes'), 'REBAIXO': ('Tetos', 'Rebaixos'),
}
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


def anel(obj, nome, raio, fundo, centro, abertura=.78):
    def criar(bm):
        voltas = []
        for r, z in ((1., -.5), (1., .5), (abertura, .5), (abertura, -.5)):
            voltas.append([bm.verts.new((r*math.cos(i*math.tau/32),
                                        r*math.sin(i*math.tau/32), z)) for i in range(32)])
        faces = []
        for a, b in zip(voltas, voltas[1:]+voltas[:1]):
            for i in range(32):
                j = (i+1)%32
                faces.append(bm.faces.new((a[i], a[j], b[j], b[i])))
        bmesh.ops.recalc_face_normals(bm, faces=faces)
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


def _area_intersecao(limites, pontos, normal, eixos):
    try:
        recorte = _paredes_selecao.recortar(limites, pontos, normal, eixos=eixos)
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
    ocupada = _area_intersecao(limites, pontos, n, (u, v))
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
            if peca.get(_iluminacao.FORRO):
                _iluminacao.devolver_luzes_do_forro(peca)
            remover_peca(peca)
    bpy.data.objects.remove(obj, do_unlink=True)


def instalar(context, modelo, apoio, indice, matriz, medidas=None):
    nome, padrao = modelos()[modelo]
    medidas = medidas or padrao
    tipo = _alvenaria.superficie(apoio, indice, matriz.to_3x3().col[2])
    if tipo not in tipos_de_apoio(modelo):
        raise ValueError('Escolha uma superficie compativel com a instalacao')
    if modelo == 'REBAIXO':
        return _iluminacao.instalar_forro(context, apoio, indice, matriz)
    perfura = modelo in _esquadrias.MODELOS or modelo == 'SPOT_EMBUTIDO'
    profundidade = _medir_corte(apoio, matriz, indice, medidas) if perfura else None
    obj = nova(context, modelo, nome, medidas, matriz)
    try:
        _alvenaria.vincular(obj, apoio, indice, matriz, tipo)
        montar(obj)
        if perfura:
            _recorte(obj, apoio, profundidade)
        _iluminacao.guardar_origem(obj, apoio, matriz)
    except Exception:
        remover(obj)
        raise
    return obj


def modelos():
    return {**_esquadrias.MODELOS, **_iluminacao.MODELOS}


def tipos_de_apoio(modelo):
    return _alvenaria.TIPOS if modelo in _esquadrias.MODELOS else _iluminacao.tipos_de_apoio(modelo)


def reassociar(context, obj, apoio, indice, matriz):
    """Valida antes de mudar o apoio; o gesto conserva o original ate' confirmar."""
    modelo = obj[_alvenaria.MARCA]
    tipo = _alvenaria.superficie(apoio, indice, matriz.to_3x3().col[2])
    if tipo not in tipos_de_apoio(modelo) or modelo == 'REBAIXO':
        raise ValueError('Escolha uma superficie compativel com a instalacao')
    perfura = modelo in _esquadrias.MODELOS or modelo == 'SPOT_EMBUTIDO'
    profundidade = _medir_corte(apoio, matriz, indice, tuple(obj[_alvenaria.MEDIDAS])) if perfura else None
    anterior = _alvenaria.apoio_de(obj)
    vinculo = obj[_alvenaria.CHAVE_VINCULO].to_dict()
    origem = obj.get(_iluminacao.FONTE)
    origem = origem.to_dict() if origem else None
    pose = obj.matrix_world.copy()
    sem_apoio = bool(obj.get(_alvenaria.CHAVE_SEM_APOIO))
    bases = {o.name: o.matrix_basis.copy() for o in obj.children}
    modificadores = {m.name for m in apoio.modifiers}
    malha = apoio.data
    camada = malha.attributes.get(_alvenaria.ATR_FACE)
    ids = [f.value for f in camada.data] if camada else None
    chaves = (_alvenaria.ATR_FACE, _paredes.CHAVE_UID_PAREDE)
    propriedades = {chave: apoio[chave] for chave in chaves if chave in apoio}
    try:
        _alvenaria.vincular(obj, apoio, indice, matriz, tipo)
        if modelo == 'PENDENTE':
            _iluminacao.posar_pendente(obj, matriz)
        if perfura:
            _recorte(obj, apoio, profundidade)
        _iluminacao.guardar_origem(obj, apoio, matriz)
    except Exception:
        obj[_alvenaria.CHAVE_VINCULO] = vinculo
        obj.matrix_world = pose
        if sem_apoio:
            obj[_alvenaria.CHAVE_SEM_APOIO] = True
        if origem is None:
            obj.pop(_iluminacao.FONTE, None)
        else:
            obj[_iluminacao.FONTE] = origem
        for peca in tuple(obj.children):
            if peca.name in bases:
                peca.matrix_basis = bases[peca.name]
            else:
                remover_peca(peca)
        for mod in tuple(apoio.modifiers):
            if mod.name not in modificadores and mod.name.endswith(obj[IDENTIDADE]):
                apoio.modifiers.remove(mod)
        if apoio.data != malha:
            copia = apoio.data
            apoio.data = malha
            if copia.users == 0:
                bpy.data.meshes.remove(copia)
        else:
            camada = malha.attributes.get(_alvenaria.ATR_FACE)
            if ids is None and camada is not None:
                malha.attributes.remove(camada)
            elif camada is not None:
                camada.data.foreach_set('value', ids)
        for chave in chaves:
            if chave in propriedades:
                apoio[chave] = propriedades[chave]
            else:
                apoio.pop(chave, None)
        _alvenaria.esquecer()
        raise
    if anterior is not None and anterior != apoio:
        for prefixo in (CORTE, FILTRO):
            mod = anterior.modifiers.get(prefixo + obj[IDENTIDADE])
            if mod:
                anterior.modifiers.remove(mod)
    if perfura and profundidade is None:
        for peca in tuple(obj.children):
            if peca.get(_alvenaria.PECA) == 'Recorte':
                remover_peca(peca)
    _poses[0].pop(obj.name, None)
    _alvenaria.esquecer()


def montar(obj):
    if obj[_alvenaria.MARCA] in _esquadrias.MODELOS:
        _esquadrias.montar(obj)
    else:
        _iluminacao.montar(obj)


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
    _iluminacao.guardar_origem(obj, apoio, matriz)


def absorver_transformacao(obj, resolvido):
    apoio, matriz, indice, limites = resolvido
    esperado = _paredes._assinatura(matriz)
    anterior = _poses[0].get(obj.name)
    _poses[0][obj.name] = esperado
    if obj[_alvenaria.MARCA] == 'REBAIXO':
        if anterior != esperado:
            _iluminacao.atualizar_forro(obj, matriz)
        return False
    if obj[_alvenaria.MARCA] == 'PENDENTE' and anterior != esperado:
        _iluminacao.posar_pendente(obj, matriz)
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
    if obj[_alvenaria.MARCA] == 'REBAIXO':
        return 'O forro acompanha a regiao selecionada do teto'
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
    for nome in tuple(o.name for o in bpy.context.scene.objects):
        obj = bpy.data.objects.get(nome)
        if obj is None:
            continue
        dono = obj.get(DONO)
        if dono and obj.parent is None:
            if obj.get(_iluminacao.FORRO):
                _iluminacao.devolver_luzes_do_forro(obj)
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
        cor = _alvenaria.CORES[previa['tipo']]
        _paredes._desenhar_face_alvo(previa['face_visual'], tela, cor, context.region, context.region_data)
        _paredes._desenhar_face_alvo(previa, tela, _hud._cor_realce_hud(), context.region, context.region_data)
        ponto = tela(previa['centro_face'])
        if ponto is not None:
            _gaveta._texto_gaveta(ponto.x, ponto.y, _alvenaria.ROTULOS[previa['tipo']], 14, (*cor, 1))


class OBJECT_OT_instalar(Operator):
    bl_idname = 'object.cabinet_instalar'
    bl_label = 'Posicionar instalacao'
    bl_options = {'UNDO'}

    modelo: StringProperty(options={'SKIP_SAVE'})
    arrastar: BoolProperty(options={'SKIP_SAVE'})
    origem: StringProperty(options={'SKIP_SAVE'})
    direito: BoolProperty(options={'SKIP_SAVE'})
    apoio_destino: StringProperty(options={'SKIP_SAVE'})
    face_destino: IntProperty(options={'SKIP_SAVE'})
    ponto_destino: FloatVectorProperty(size=3, options={'SKIP_SAVE'})
    normal_destino: FloatVectorProperty(size=3, default=(0,0,1), options={'SKIP_SAVE'})

    def execute(self, context):
        apoio = context.scene.objects.get(self.apoio_destino)
        if (not _paredes.alvenaria_definida(apoio) or apoio.data.is_editmode
                or not 0 <= self.face_destino < len(apoio.data.polygons)):
            return {'CANCELLED'}
        matriz = _alvenaria.referencial(self.ponto_destino, self.normal_destino)
        origem = context.scene.objects.get(self.origem) if self.origem else None
        if (self.origem and origem is None) or (not self.origem and self.modelo not in modelos()):
            return {'CANCELLED'}
        try:
            if origem is not None:
                reassociar(context, origem, apoio, self.face_destino, matriz)
            else:
                instalar(context, self.modelo, apoio, self.face_destino, matriz)
        except ValueError as erro:
            self.report({'WARNING'}, str(erro))
            return {'CANCELLED'}
        return {'FINISHED'}

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
        self.regiao_forro = None
        obj = context.scene.objects.get(self.origem) if self.origem else None
        self.ignorados = {obj.name, *(o.name for o in obj.children_recursive)} if obj else set()
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
            atingido = _paredes.raio_ate_parede(context, origem, direcao, self.ignorados)
        apoio = atingido[0] if atingido else None
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
        obj = context.scene.objects.get(self.origem) if self.origem else None
        if self.origem and obj is None:
            return
        medidas = tuple(obj[_alvenaria.MEDIDAS]) if obj else modelos()[self.modelo][1]
        ponto = apoio.matrix_world @ local
        self.referencia = apoio.name, tuple(ponto), tuple(normal)
        matriz = _alvenaria.referencial(ponto, normal)
        if self.modelo in _esquadrias.MODELOS:
            if self.modelo == 'SACADA' and obj is None and _paredes.tipo_superficie(normal) == 'PAREDE':
                medidas = _sugerir_sacada(context, ponto, normal, medidas)
            matriz.translation += matriz.to_3x3().col[1] * medidas[1] / 2
        cache = self.regiao_forro
        if cache is None or cache[0] != apoio.name or indice not in cache[1]['faces']:
            limites = _alvenaria.regiao(apoio, indice, matriz)
            if limites is None:
                return
            self.regiao_forro = apoio.name, limites
        limites = self.regiao_forro[1]
        if self.modelo == 'REBAIXO':
            deslocamento = Vector((0, 0, -medidas[2]))
            visual = dict(contorno=[(a+deslocamento,b+deslocamento) for a,b in limites['contorno']],
                          triangulos=limites['triangulos']+np.array(deslocamento))
        else:
            ps = _retangulo(matriz, medidas)
            visual = dict(contorno=list(zip(ps, ps[1:]+ps[:1])),
                          triangulos=np.array([ps[i] for i in (0,1,2,0,2,3)]))
        tipo = _alvenaria.superficie(apoio, indice, normal)
        pontos = np.asarray(limites['triangulos']).reshape(-1,3)
        _previa[0] = dict(visual, regiao=regiao.as_pointer(), tipo=tipo,
                         face_visual=limites, centro_face=Vector(pontos.mean(axis=0)))
        self.alvo = (apoio.name, indice, matriz, medidas)

    def modal(self, context, event):
        area = next((a for a in context.screen.areas if a.as_pointer() == self.area), None)
        if area is None or context.scene.name != self.cena or _eventos._desfazendo[0]:
            self.cancel(context)
            return {'CANCELLED'}
        if event.type == 'ESC' or event.type == 'RIGHTMOUSE' and not self.direito:
            self.cancel(context)
            return {'CANCELLED'}
        regiao = next(r for r in area.regions if r.type == 'WINDOW')
        if event.type == 'MOUSEMOVE':
            self._mover(context, area, regiao, event)
            area.tag_redraw()
        if event.type == ('RIGHTMOUSE' if self.direito else 'LEFTMOUSE') and event.value == ('RELEASE' if self.arrastar else 'PRESS'):
            self._mover(context, area, regiao, event)
            if self.arrastar and math.dist(self.inicio, (event.mouse_x, event.mouse_y)) < 6:
                if self.direito:
                    self.cancel(context)
                    with context.temp_override(area=area, region=regiao):
                        bpy.ops.wm.call_menu('INVOKE_DEFAULT', name='VIEW3D_MT_object_context_menu')
                    return {'CANCELLED'}
                self.arrastar = False
                return {'RUNNING_MODAL'}
            if self.alvo is None:
                self.cancel(context)
                return {'CANCELLED'}
            nome, indice, matriz, medidas = self.alvo
            apoio = bpy.data.objects.get(nome)
            try:
                with context.temp_override(area=area, region=regiao):
                    obj = context.scene.objects.get(self.origem) if self.origem else None
                    if obj is not None:
                        reassociar(context, obj, apoio, indice, matriz)
                    elif not self.origem:
                        obj = instalar(context, self.modelo, apoio, indice, matriz, medidas)
                    else:
                        self.cancel(context)
                        return {'CANCELLED'}
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
        if _iluminacao.acao_forro(obj, self.acao):
            return {'FINISHED'}
        chaves = {'inverter': _esquadrias.CHAVE_FACE, 'espelhar': _esquadrias.CHAVE_LADO}
        if obj.get(_alvenaria.MARCA) != 'PORTA' or self.acao not in chaves:
            return {'CANCELLED'}
        chave = chaves[self.acao]
        obj[chave] = -obj.get(chave, 1)
        _esquadrias.posar(obj)
        return {'FINISHED'}


def _sugerir_sacada(context, ponto, normal, medidas):
    deps = context.evaluated_depsgraph_get()
    origem = ponto + normal*.035
    teto = None
    for lado in (-1, 1):
        z = Vector((0, 0, lado))
        hit, p, n, indice, apoio, _ = context.scene.ray_cast(deps, origem+z*.003, z)
        tipo = _alvenaria.superficie(apoio, indice, n, apoio.evaluated_get(deps).data) if hit else None
        if tipo != ('PISO' if lado == -1 else 'TETO'):
            return medidas
        if lado == 1:
            teto = p.z
    altura = teto-ponto.z
    return (medidas[0], altura, medidas[2]) if altura >= .3 else medidas


def widgets_seletor(context, itens, x, y, w):
    tipo = context.screen.get(CHAVE_TIPO_MENU, 'PAREDE') if context.screen else 'PAREDE'
    blf.size(0,12)
    pesos = [blf.dimensions(0, rotulo.capitalize())[0]+18 for rotulo in _alvenaria.TIPOS]
    larguras = [(w-46)*p/sum(pesos) for p in pesos] if w < 240 else [(w-46)/3]*3
    y -= 25
    inicio = x
    for rotulo, coluna in zip(_alvenaria.TIPOS, larguras):
        itens.append((inicio, y, coluna, 25, rotulo.capitalize(),
                      ('escolha', 'tipo_instalacao', rotulo, tipo == rotulo, True, ALVO)))
        inicio += coluna+6
    visivel = bool(context.scene.get(_alvenaria.CHAVE_VISUAL, False))
    itens.append((x+w-28, y, 28, 25, '',
                  ('escolha', 'alvenaria_visual', visivel, visivel, True, _alvenaria.ALVO_TIPO)))
    return y-6


def widgets_tipos(context, itens, x, y, w):
    y = widgets_seletor(context, itens, x, y, w)
    tipo = context.screen.get(CHAVE_TIPO_MENU, 'PAREDE') if context.screen else 'PAREDE'
    return widgets_modelos(context, itens, x, y, w, tipo)


def widgets_modelos(context, itens, x, y, w, apoio, excluir=()):
    y = _gaveta._titulo_secao(itens, x, y, w, 'Instalacoes')
    y -= 25
    indice = catalogo()
    trilha = tuple(context.screen.get(CHAVE_CATEGORIA, '').split('/'))
    trilha = tuple(p for p in trilha if p)
    for nivel in range(1, len(trilha)+2):
        filhos = _biblioteca.filhos_de(indice, trilha[:nivel-1])
        if not filhos:
            break
        y = _gaveta._linha_cascata_gaveta(itens, x, y, w, ['Todos']+filhos, nivel,
                trilha[nivel-1] if len(trilha)>=nivel else 'Todos', prefixo='cabinet_instalacoes')
        v = itens[-1];acao = v[5]
        itens[-1] = v[:5]+(acao[:3]+((ALVO, nivel),)+acao[4:],)
    daqui = [it for it in indice if tuple(it['niveis'][:len(trilha)]) == trilha and it['modelo'] not in excluir]
    bloco, colunas, altura = _gaveta._grade_biblioteca(context.scene, w)
    for i, it in enumerate(daqui):
        itens.append((x+i%colunas*(bloco+8), y-altura-i//colunas*(altura+8), bloco, altura,
                      it['nome'], ('escolha', 'modelo_instalacao', it['modelo'], False, True, ALVO)))
    return y - math.ceil(len(daqui)/colunas)*(altura+8) - 6


def catalogo():
    return [item_do_modelo(modelo) for modelo in modelos()]


def item_do_modelo(modelo):
    return dict(modelo=modelo, nome=modelos()[modelo][0], niveis=CATEGORIAS[modelo],
                pasta=os.path.join(os.path.dirname(__file__), 'fotos', 'instalacoes'), foto=modelo+'.png')


def definir_categoria(context, nivel, valor):
    trilha = [p for p in context.screen.get(CHAVE_CATEGORIA, '').split('/') if p][:nivel-1]
    if valor != 'Todos' and valor in _biblioteca.filhos_de(catalogo(), trilha):
        trilha.append(valor)
    context.screen[CHAVE_CATEGORIA] = '/'.join(trilha)


def widgets(context, itens, x, y, w, obj):
    y = _iluminacao.widgets(context, itens, x, y, w, obj)
    if obj.get(_alvenaria.MARCA) in _esquadrias.MODELOS:
        colunas = _gaveta._colunas_medidas(context, w + 24, 3)
        coluna = (w - (colunas-1)*6) / colunas
        for i, rotulo in enumerate(('Largura', 'Altura', 'Profundidade')):
            mm = obj[_alvenaria.MEDIDAS][i]*1000
            itens.append((x + i%colunas*(coluna+6), y-37-i//colunas*43, coluna, 37,
                          rotulo + ': ' + _opcoes._texto_medida(mm),
                          ('medida', 'instalacao_tamanho', str(i), rotulo, mm)))
        y -= math.ceil(3/colunas)*43
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
