"""Vista local de uma face de parede e distribuicao de presets nessa face.

A sessao guarda somente nomes e numeros: undo pode destruir qualquer ID.
Geometria e coordenadas pertencem a paredes; resize pertence a modulos.
"""

import math
import time
import bpy
import blf
import gpu
from bpy.props import StringProperty
from bpy.types import Operator, Menu
from bpy_extras import view3d_utils
from gpu_extras.batch import batch_for_shader
from mathutils import Matrix, Vector, Quaternion
from mathutils.geometry import intersect_line_plane
from mathutils.bvhtree import BVHTree

_paredes = _modulos = _biblioteca = _chapas = _hud = None
_gaveta = _opcoes = _eventos = _biblioteca_faixa = None
_paredes_composicao = None

_sessao = [None]
_ultima_face = [None]
_alvo_contexto = [None]
_sequencia = [0]
_aviso = ['']
_handler = [None]
_plano = [None]
ALVO_QUANTIDADE = 'paredes_quantidade'
CHAVE_VISUAL = 'cabinet_parede_exibicao_2d'
CHAVE_ORDEM = 'parede_ordem_posicionamento'
CHAVE_FIOS = 'cabinet_parede_arestas_2d'


def superficie(obj):
    return obj is not None and obj.type == 'MESH' and not _paredes.eh_movel(obj)


def lembrar_face(context, posicao, contexto=False):
    """Apenas observa o raycast; a selecao continua sendo do Blender."""
    acerto = _hud._raio_cru(context, posicao)
    if contexto:
        _alvo_contexto[0] = acerto[0].name if acerto and superficie(acerto[0]) else ''
    if acerto and superficie(acerto[0]) and _paredes.eixos_da_parede(acerto[2]):
        obj, ponto, normal, face, _matriz = acerto
        _ultima_face[0] = (obj.name, tuple(obj.matrix_world.inverted_safe() @ ponto),
                          tuple(obj.matrix_world.to_3x3().transposed() @ normal), face)


def face_do_objeto(context, obj):
    if not superficie(obj):
        return None
    # Tab pode alterar o contorno sem mudar a quantidade de vertices.
    # Esta leitura ocorre na entrada, nunca no desenho da gaveta.
    _paredes._retangulos.clear()
    anterior = _ultima_face[0]
    if anterior and anterior[0] == obj.name:
        ponto = obj.matrix_world @ Vector(anterior[1])
        normal = _paredes._normal_no_mundo(obj, anterior[2])
        regiao = _paredes.regiao_da_parede(obj, ponto, normal,
                    context.evaluated_depsgraph_get(), anterior[3])
        if regiao:
            return ponto, normal, regiao
    # Outliner nao fornece face: escolher a maior voltada para a vista.
    area = viewport(context)
    frente = (area.spaces.active.region_3d.view_rotation @ Vector((0, 0, 1))
              if area else Vector((0, -1, 0)))
    avaliado = obj.evaluated_get(context.evaluated_depsgraph_get())
    normal_mundo = obj.matrix_world.to_3x3().inverted_safe().transposed()
    candidatas = []
    for poly in avaliado.data.polygons:
        normal = (normal_mundo @ poly.normal).normalized()
        if _paredes.eixos_da_parede(normal) and normal.dot(frente) > 0:
            # Area avaliada no mundo, inclusive para paredes com escala.
            escala_area = abs(obj.matrix_world.to_3x3().determinant()) * (
                normal_mundo @ poly.normal).length
            candidatas.append((poly.area * escala_area, normal.dot(frente), poly.index))
    if not candidatas:
        return None
    indice = max(candidatas)[2]
    poly = avaliado.data.polygons[indice]
    ponto = obj.matrix_world @ poly.center
    normal = (normal_mundo @ poly.normal).normalized()
    regiao = _paredes.regiao_da_parede(obj, ponto, normal,
                                     context.evaluated_depsgraph_get(), indice)
    return (ponto, normal, regiao) if regiao else None


def viewport(context):
    s = _sessao[0]
    if s:
        return next((a for a in context.screen.areas
                     if a.as_pointer() == s['area']), None) if context.screen else None
    return _biblioteca_faixa.viewport(context.screen) if context.screen else None


def _janela_da_sessao():
    s = _sessao[0]
    if s is None:
        return None, None, None
    for janela in bpy.context.window_manager.windows:
        if janela.as_pointer() != s['janela']:
            continue
        area = next((a for a in janela.screen.areas if a.as_pointer() == s['area']), None)
        regiao = next((r for r in area.regions if r.type == 'WINDOW'), None) if area else None
        return janela, area, regiao
    return None, None, None


def ativa(context=None):
    s = _sessao[0]
    return bool(s and (context is None or (context.scene.name == s['cena']
                and context.window and context.window.as_pointer() == s['janela'])))


def associados(parede, ponto, normal, objetos, regiao=None):
    """Filtra tambem o plano: o mesmo objeto pode ter duas faces opostas."""
    resultado = []
    for obj in objetos:
        if _chapas.MARCA_CONJUNTO not in obj or _paredes.parede_do_modulo(obj) != parede:
            continue
        plano = _paredes.plano_do_modulo(obj, parede)
        if plano and plano[1].dot(normal) >= _paredes.COPLANAR_MIN and abs(
                (plano[0] - ponto).dot(normal)) <= _paredes.TOLERANCIA_PLANO_M:
            if regiao is not None:
                propria = _paredes.regiao_da_parede(parede, plano[0], plano[1],
                        bpy.context.evaluated_depsgraph_get(), obj.get(_paredes.CHAVE_PAREDE_FACE))
                if propria is None or propria['face'] not in regiao['faces']:
                    continue
            resultado.append(obj)
    return resultado


def _visiveis_da_face(context, parede, ponto, normal):
    manter = {parede.name}
    for modulo in associados(parede, ponto, normal, context.scene.objects,
                             _sessao[0]['regiao'] if ativa(context) else None):
        manter.add(modulo.name)
        manter.update(o.name for o in modulo.children_recursive)
    return manter


def _aplicar_isolamento(context, area, manter):
    espaco = area.spaces.active
    s = _sessao[0]
    s['local_anterior'] = espaco.local_view is not None
    context.view_layer.update()
    s['membros_anteriores'] = [o.name for o in context.scene.objects
                                if espaco.local_view and esta_na_vista(o, espaco, context)]
    if not espaco.local_view:
        selecionados = [o.name for o in context.selected_objects]
        ativo = context.view_layer.objects.active
        nome_ativo = ativo.name if ativo else ''
        try:
            for obj in context.selected_objects:
                obj.select_set(False)
            for nome in manter:
                obj = context.view_layer.objects.get(nome)
                if obj is not None and not obj.hide_get() and not obj.hide_viewport:
                    obj.select_set(True)
            bpy.ops.view3d.localview(frame_selected=False)
        finally:
            for obj in context.selected_objects:
                obj.select_set(False)
            for nome in selecionados:
                obj = context.view_layer.objects.get(nome)
                if obj is not None:
                    obj.select_set(True)
            context.view_layer.objects.active = context.view_layer.objects.get(nome_ativo)
    if espaco.local_view is None:
        raise ValueError('Nao foi possivel isolar a parede nesta viewport')
    for obj in context.scene.objects:
        obj.local_view_set(espaco, obj.name in manter)
    context.view_layer.update()


def esta_na_vista(obj, espaco, context):
    # 4.2 le base_local_view_bits da copia avaliada; o setter escreve no
    # Base da camada. O getter 5.x consulta o Base diretamente.
    if bpy.app.version < (4, 3, 0):
        obj = obj.evaluated_get(context.evaluated_depsgraph_get())
    return obj.local_view_get(espaco)


def modulo_da_porta(context, folha):
    """Excecao frontal so' na viewport isolada e na face associada."""
    if (folha is None or _chapas.MARCA_FOLHA not in folha
            or not ativa(context) or context.area is None
            or context.area.as_pointer() != _sessao[0]['area']):
        return None
    modulo = _paredes.modulo_de(folha)
    resumo = _paredes_composicao._resumo[0]
    if modulo and resumo and any(f['nome'] == modulo.name for f in resumo['itens']):
        return modulo
    return None


def _preparar_fios(objetos):
    # So' madeira: o wire das ferragens exporia triangulos e controles do rig.
    for obj in objetos:
        if obj.type == 'MESH' and _chapas.MARCA_CHAPA in obj:
            if CHAVE_FIOS not in obj:
                obj[CHAVE_FIOS] = obj.show_wire
            obj.show_wire = True


def _restaurar_fios():
    for obj in bpy.data.objects:
        if CHAVE_FIOS in obj:
            obj.show_wire = bool(obj[CHAVE_FIOS])
            del obj[CHAVE_FIOS]


def _preparar_visual(area, parede):
    espaco = area.spaces.active
    s = _sessao[0]
    s['visual'] = {
        'shading': {k: getattr(espaco.shading, k) for k in ('type', 'light', 'color_type', 'show_xray', 'show_object_outline')},
        'overlay': {k: getattr(espaco.overlay, k) for k in ('show_floor', 'show_axis_x', 'show_axis_y',
                                'show_relationship_lines', 'show_extras', 'show_outline_selected')},
        'parede_exibicao': parede.display_type,
    }
    s['visual']['shading']['object_outline_color'] = tuple(espaco.shading.object_outline_color)
    # Contorno nativo destaca as pecas sem esconder a superficie da parede.
    espaco.shading.type = 'SOLID'
    espaco.shading.light = 'FLAT'
    espaco.shading.color_type = 'OBJECT'
    espaco.shading.show_xray = False
    espaco.shading.show_object_outline = True
    espaco.shading.object_outline_color = (0, 0, 0)
    for k in s['visual']['overlay']:
        setattr(espaco.overlay, k, False)
    parede[CHAVE_VISUAL] = parede.display_type
    parede.display_type = 'SOLID'
    _preparar_fios(o for o in bpy.context.scene.objects if o.visible_get(viewport=espaco))


def _restaurar_visual(area, s):
    visual = s.get('visual')
    if visual is None:
        return
    espaco = area.spaces.active
    for k, valor in visual['shading'].items():
        setattr(espaco.shading, k, valor)
    for k, valor in visual['overlay'].items():
        setattr(espaco.overlay, k, valor)
    parede = bpy.data.objects.get(s['parede'])
    if parede and parede.display_type in {'WIRE', 'SOLID'}:
        parede.display_type = visual['parede_exibicao']
    if parede and CHAVE_VISUAL in parede:
        del parede[CHAVE_VISUAL]
    _restaurar_fios()


def iniciar(context, obj):
    face = face_do_objeto(context, obj)
    area = viewport(context)
    if face is None or area is None:
        return 'Selecione uma face plana vertical voltada para a vista'
    encerrar()
    perspectiva_anterior = area.spaces.active.region_3d.view_perspective
    ponto, normal, regiao = face
    n, u = _paredes.eixos_da_parede(normal)
    # A primeira versao nao projeta paredes inclinadas como se fossem verticais.
    if abs(normal.z) > 0.001:
        return 'A edicao 2D exige uma face vertical'
    _sequencia[0] = time.monotonic_ns()
    _sessao[0] = {
        'id': _sequencia[0], 'janela': context.window.as_pointer(),
        'area': area.as_pointer(), 'cena': context.scene.name,
        'camada': context.view_layer.name,
        'parede': obj.name, 'ponto': tuple(ponto), 'normal': tuple(n),
        'u': tuple(u), 'face': regiao['face'],
        'regiao': {'retangulo': tuple(regiao['retangulo']), 'faces': regiao['faces'],
                   'contorno': [(tuple(a), tuple(b)) for a, b in regiao['contorno']]},
        'modelo': None, 'substituir': '', 'ultimo_modulo': '',
        'perspectiva_anterior': perspectiva_anterior,
        'escolhendo': False, 's': sum(regiao['retangulo'][:2]) / 2,
        'quantidade': 1, 'esquerda': 0.0, 'direita': 0.0, 'espacamento': 0.0,
        'instalacao': regiao['retangulo'][2] * 1000.0,
        'altura': 720.0, 'profundidade': 550.0,
        'local_anterior': False, 'membros_anteriores': [],
        'enquadrando': True,
    }
    reg = next(r for r in area.regions if r.type == 'WINDOW')
    try:
        with context.temp_override(area=area, region=reg):
            _aplicar_isolamento(context, area, _visiveis_da_face(context, obj, ponto, n))
            _preparar_visual(area, obj)
            rv = area.spaces.active.region_3d
            rot = Matrix((u, Vector((0, 0, 1)), n)).transposed().to_quaternion()
            s0, s1, z0, z1 = regiao['retangulo']
            rv.view_rotation = rot
            rv.view_perspective = 'ORTHO'
            rv.view_location = ponto + u * ((s0 + s1) / 2 - ponto.dot(u))
            rv.view_location.z = (z0 + z1) / 2
            aspecto = reg.width / max(1, reg.height)
            rv.view_distance = max(z1 - z0, (s1 - s0) / aspecto) * 1.4
            _sessao[0]['rotacao'] = tuple(rv.view_rotation)
            if not bpy.app.background:
                bpy.ops.object.cabinet_observar_parede('INVOKE_DEFAULT')
        _handler[0] = bpy.types.SpaceView3D.draw_handler_add(desenhar, (), 'WINDOW', 'POST_PIXEL')
        _paredes._uid_da_parede(obj)
        modulos = associados(obj, ponto, n, context.scene.objects, regiao)
        ultimo = max(modulos, key=lambda o: o.get(CHAVE_ORDEM, 0), default=None)
        _sessao[0]['ultimo_modulo'] = ultimo.name if ultimo else ''
        _paredes_composicao.atualizar(context)
    except Exception as erro:
        encerrar()
        return str(erro)
    _aviso[0] = ''
    _redesenhar()
    return None


def encerrar(perspectiva=False):
    s = _sessao[0]
    if s is None:
        return
    janela, area, regiao = _janela_da_sessao()
    cena_atual = janela.scene if janela else None
    camada_atual = janela.view_layer.name if janela else ''
    try:
        if area and area.type == 'VIEW_3D':
            _restaurar_visual(area, s)
        if area and area.type == 'VIEW_3D' and area.spaces.active.local_view:
            cena = bpy.data.scenes.get(s['cena']) or janela.scene
            camada = cena.view_layers.get(s['camada']) or cena.view_layers[0]
            # Local View consulta a cena REAL da janela em C. Override
            # apenas de scene/view_layer deixa Bases de cenas diferentes
            # e derruba 4.2/5.2. Restaurar na janela real, sem redesenho.
            janela.scene = cena
            janela.view_layer = camada
            with bpy.context.temp_override(window=janela, area=area, region=regiao):
                if s['local_anterior']:
                    membros = set(s['membros_anteriores'])
                    for obj in cena.objects:
                        obj.local_view_set(area.spaces.active, obj.name in membros)
                else:
                    # O Blender restaura o ponto de vista anterior ao sair do Local
                    # View. Conservar a vista atual deixa o gesto de orbita continuar.
                    rv = area.spaces.active.region_3d
                    vista = (rv.view_rotation.copy(), rv.view_location.copy(),
                             rv.view_distance, rv.view_perspective)
                    bpy.ops.view3d.localview(frame_selected=False)
                    rv.view_rotation, rv.view_location, rv.view_distance, rv.view_perspective = vista
        if area and area.type == 'VIEW_3D':
            rv = area.spaces.active.region_3d
            if rv.view_perspective == 'ORTHO' and (perspectiva or s.get('perspectiva_anterior') == 'PERSP'):
                rv.view_perspective = 'PERSP'
    finally:
        _restaurar_fios()
        if janela and cena_atual and janela.scene != cena_atual:
            janela.scene = cena_atual
            janela.view_layer = cena_atual.view_layers.get(camada_atual) or cena_atual.view_layers[0]
        _sessao[0] = None
        _paredes_composicao.esquecer()
        _plano[0] = None
        if _handler[0] is not None:
            bpy.types.SpaceView3D.draw_handler_remove(_handler[0], 'WINDOW')
            _handler[0] = None
        _redesenhar()


def _redesenhar():
    for janela in bpy.context.window_manager.windows:
        for area in janela.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()


def verificar(atualizar_previa=True):
    if _eventos._desfazendo[0]:
        return
    if not ativa():
        _restaurar_fios()
        # Undo/redo pode restaurar a aparencia temporaria gravada no
        # snapshot. A marca identifica so' o que o modo 2D alterou.
        for obj in bpy.context.scene.objects:
            if CHAVE_VISUAL in obj:
                if obj.display_type in {'WIRE', 'SOLID'}:
                    obj.display_type = obj[CHAVE_VISUAL]
                del obj[CHAVE_VISUAL]
        return
    s = _sessao[0]
    janela, area, regiao = _janela_da_sessao()
    if (area is None or area.type != 'VIEW_3D' or janela.scene.name != s['cena']
            or bpy.data.objects.get(s['parede']) is None):
        encerrar()
        return
    rv = area.spaces.active.region_3d
    mudou = abs(rv.view_rotation.dot(Quaternion(s['rotacao']))) < 0.999999
    if mudou or rv.view_perspective != 'ORTHO' or area.spaces.active.local_view is None:
        encerrar(perspectiva=mudou)
    elif atualizar_previa:
        with bpy.context.temp_override(window=janela, area=area, region=regiao):
            if s.get('enquadrando') and not bpy.app.background:
                _enquadrar(bpy.context, s)
            _paredes_composicao.atualizar(bpy.context)
            if s['modelo'] is None:
                return
            plano = planejar(bpy.context, s)
            if plano != _plano[0]:
                _plano[0] = plano
                _redesenhar()


def _enquadrar(context, s):
    # A projecao nativa so' se atualiza no redraw. Ajustar no tique
    # seguinte considera lente, proporcao e tamanho REAL da regiao.
    u, ponto = Vector(s['u']), Vector(s['ponto'])
    s0, s1, z0, z1 = s['regiao']['retangulo']
    projetados = []
    for x in (s0, s1):
        for z in (z0, z1):
            p = ponto + u * (x - ponto.dot(u))
            p.z = z
            q = view3d_utils.location_3d_to_region_2d(context.region, context.region_data, p)
            if q is not None:
                projetados.append(q)
    if len(projetados) != 4:
        return
    fator = max((max(p.x for p in projetados) - min(p.x for p in projetados)) / (context.region.width * .8),
                (max(p.y for p in projetados) - min(p.y for p in projetados)) / (context.region.height * .8))
    if abs(fator - 1) > .02:
        context.region_data.view_distance *= fator
        context.area.tag_redraw()
    else:
        s['enquadrando'] = False


def navegacao_de_saida(context, event):
    """Consulta o keymap do usuario: inclui Walk/Fly antes do primeiro passo."""
    if event.value not in {'PRESS', 'ANY', 'NOTHING'}:
        return False
    operadores = {'view3d.walk', 'view3d.fly', 'view3d.rotate', 'view3d.view_axis',
                  'view3d.view_orbit', 'view3d.view_persportho', 'view3d.view_camera'}
    km = context.window_manager.keyconfigs.user.keymaps.get('3D View')
    item = km.keymap_items.match_event(event) if km else None
    return item is not None and item.idname in operadores


def contexto_painel(context):
    if ativa(context):
        return bpy.data.objects.get(_sessao[0]['parede'])
    obj = context.object
    return obj if superficie(obj) and obj.select_get() else None


def widgets(context, itens, x, topo, w):
    obj = contexto_painel(context)
    if obj is None:
        return topo
    topo = _gaveta._titulo_secao(itens, x, topo + 26, w, 'Paredes')
    def botao(rotulo, operador):
        nonlocal topo
        topo -= 28
        itens.append((x, topo, w, 28, rotulo, ('operador', operador)))
        topo -= 6
    if not ativa(context):
        botao('Editar parede', 'object.cabinet_editar_parede')
        if _aviso[0]:
            itens.append((x, topo - 20, w, 20, _aviso[0], None))
            topo -= 26
        return topo - 58
    s = _sessao[0]
    botao('Sair da edicao da parede', 'object.cabinet_sair_parede')
    topo = _paredes_composicao.widgets(context, itens, x, topo - 12, w)
    # Folgas da composicao tambem ficam acessiveis sem preparar um novo modelo.
    campos_folgas = [('%s: %s' % (rotulo, _opcoes._texto_medida(s[nome])),
                     ('medida', 'paredes', nome, rotulo, s[nome]))
                    for nome, rotulo in (('esquerda', 'Esquerda'), ('direita', 'Direita'),
                                         ('espacamento', 'Espacamento'))]
    topo = _gaveta._campos_em_linhas(context, itens, x, topo, w, campos_folgas)
    if s['modelo'] is None:
        mensagem = 'Escolha o novo modelo na biblioteca' if s.get('substituir') else 'Escolha um modulo na biblioteca'
        itens.append((x, topo - 20, w, 20, mensagem, None))
        return topo - 58
    itens.append((x, topo - 20, w, 20, s['modelo']['nome'], None))
    topo -= 28
    if s.get('substituir'):
        itens.append((x, topo - 20, w, 20, 'Mantem posicao, tamanho e associacao', None))
        topo -= 26
        botao('Substituir modulo', 'object.cabinet_distribuir_parede')
        botao('Cancelar previa', 'object.cabinet_cancelar_previa_parede')
        return topo - 58
    campos = []
    for nome, rotulo in (('instalacao', 'Instalacao'), ('altura', 'Altura'),
                         ('profundidade', 'Profundidade')):
        campos.append(('%s: %s' % (rotulo, _opcoes._texto_medida(s[nome])),
                       ('medida', 'paredes', nome, rotulo, s[nome])))
    campos.append((str(s['quantidade']),
                  ('contador', ALVO_QUANTIDADE, s['quantidade'], 1, 100,
                   '', 'Quantidade')))
    topo = _gaveta._campos_em_linhas(context, itens, x, topo, w, campos)
    botao('Clique no vao na viewport' if s['escolhendo'] else 'Escolher vao na parede',
          'object.cabinet_escolher_vao_parede')
    plano = _plano[0] or {'erro': 'Calculando previa...'}
    mensagem = plano.get('erro') or 'Largura por modulo: %s' % _opcoes._texto_medida(plano['largura'] * 1000)
    itens.append((x, topo - 20, w, 20, mensagem, None))
    topo -= 26
    botao('Substituir modulo' if s.get('substituir') else 'Criar modulos', 'object.cabinet_distribuir_parede')
    botao('Cancelar previa', 'object.cabinet_cancelar_previa_parede')
    return topo - 58


def editar_parametro(nome, valor):
    s = _sessao[0]
    if s is None:
        return 'A edicao da parede terminou'
    if nome == 'quantidade':
        if not 1 <= valor <= 100 or int(valor) != valor:
            return 'Quantidade deve ser um inteiro entre 1 e 100'
        s[nome] = int(valor)
    elif nome in ('instalacao', 'altura', 'profundidade', 'esquerda', 'direita', 'espacamento'):
        if not math.isfinite(valor) or valor < 0:
            return 'A medida deve ser positiva ou zero'
        s[nome] = valor
    else:
        return 'Parametro de parede desconhecido'
    _redesenhar()
    _plano[0] = None
    return None


def _dados_antes():
    return {nome: set(getattr(bpy.data, nome).keys()) for nome in
            ('objects', 'collections', 'meshes', 'curves', 'materials', 'node_groups',
             'actions', 'images', 'cameras', 'lights', 'armatures', 'lattices', 'metaballs')}


def _limpar_tentativa(antes):
    for nome, existentes in antes.items():
        dados = getattr(bpy.data, nome)
        for item in list(dados):
            if item.name not in existentes:
                dados.remove(item, do_unlink=True)


def ponto_no_evento(context, event):
    """Consulta somente a parede editada pelo raycast nativo, inclusive aberturas."""
    if not ativa(context):
        return None
    janela, area, regiao = _janela_da_sessao()
    xy = (event.mouse_x - regiao.x, event.mouse_y - regiao.y)
    if not (0 <= xy[0] < regiao.width and 0 <= xy[1] < regiao.height):
        return None
    rv = area.spaces.active.region_3d
    origem = view3d_utils.region_2d_to_origin_3d(regiao, rv, xy)
    direcao = view3d_utils.region_2d_to_vector_3d(regiao, rv, xy)
    s = _sessao[0]
    parede = bpy.data.objects.get(s['parede'])
    if parede is None:
        return None
    inversa = parede.matrix_world.inverted_safe()
    avaliado = parede.evaluated_get(context.evaluated_depsgraph_get())
    acertou, local, normal, face = avaliado.ray_cast(inversa @ origem, inversa.to_3x3() @ direcao)
    if not acertou or face not in s['regiao']['faces']:
        return None
    return parede.matrix_world @ local


def posicao_do_modelo(context, modulo, ponto=None, caixa=None):
    """Posiciona pelo cursor ou a' direita do ultimo, sem redimensionar a malha."""
    s = _sessao[0]
    if not ativa(context):
        return None, 'A edicao da parede terminou'
    caixa = caixa or _paredes.caixa_do_modulo(modulo)
    if caixa is None:
        return None, 'O modelo precisa conter um modulo completo'
    lo, hi = caixa
    escala = modulo.matrix_world.to_scale()
    largura, altura = (hi.x - lo.x) * escala.x, (hi.z - lo.z) * escala.z
    s0, s1, z0, z1 = s['regiao']['retangulo']
    esquerda, direita = s0 + s['esquerda'] / 1000, s1 - s['direita'] / 1000
    if largura > direita - esquerda + .00005 or altura > z1 - z0 + .00005:
        return None, 'O tamanho original do modelo nao cabe na parede'
    u, n, plano = (Vector(s[k]) for k in ('u', 'normal', 'ponto'))
    if ponto is None:
        ultimo = next((f for f in _paredes_composicao.itens_da_face(context)
                       if f['nome'] == s.get('ultimo_modulo')), None)
        centro = ultimo['fim'] + s['espacamento'] / 1000 + largura / 2 if ultimo else (s0 + s1) / 2
        if centro + largura / 2 > direita + .00005:
            centro = (s0 + s1) / 2
        base = ultimo['base'] if ultimo else max(z0, _paredes.ponto_das_costas(modulo, caixa).z)
    else:
        centro, base = ponto.dot(u), ponto.z - altura / 2
        janela, area, regiao = _janela_da_sessao()
        px = _paredes._px_por_metro(regiao, area.spaces.active.region_3d, ponto, u)
        if px:
            centro, base = _paredes.posicao_no_arraste(s['regiao']['retangulo'], centro,
                base, largura, altura, _paredes.SNAP_PX / px)
    alvo = plano + u * (centro - plano.dot(u))
    alvo.z = base + altura / 2
    return encaixar_na_face(context, modulo, alvo, s, caixa)


def registrar_posicionado(context, modulo, novos=()):
    """Inclui a instancia no isolamento e guarda apenas o nome do ultimo modulo."""
    if modulo is None or _paredes.parede_do_modulo(modulo) is None:
        return
    # A ordem persiste ao sair do 2D ou reabrir o arquivo, sem guardar IDs globais.
    modulo[CHAVE_ORDEM] = time.time()
    if not ativa(context):
        return
    s = _sessao[0]
    parede = bpy.data.objects.get(s['parede'])
    if modulo not in associados(parede, Vector(s['ponto']), Vector(s['normal']),
                                 context.scene.objects, s['regiao']):
        return
    s['ultimo_modulo'] = modulo.name
    janela, area, regiao = _janela_da_sessao()
    objetos = list(novos) or [modulo, *modulo.children_recursive]
    if area.spaces.active.local_view:
        for obj in objetos:
            obj.local_view_set(area.spaces.active, True)
            if s['local_anterior'] and obj.name not in s['membros_anteriores']:
                s['membros_anteriores'].append(obj.name)
    context.view_layer.update()
    _preparar_fios(objetos)
    _paredes_composicao.atualizar(context)
    _redesenhar()


def posicionar_modelo(context, modulo, ponto=None, novos=()):
    costas, erro = posicao_do_modelo(context, modulo, ponto)
    if erro:
        return erro
    s = _sessao[0]
    parede = bpy.data.objects[s['parede']]
    normal = Vector(s['normal'])
    _paredes.colocar_na_parede(modulo, parede, costas, normal)
    _paredes.associar(modulo, parede, costas, normal, s['face'])
    registrar_posicionado(context, modulo, novos)
    return None


def inserir_modelo(context, pasta, arquivo, tipo):
    """Insercao imediata reutiliza o append; distribuir continua sendo explicito."""
    if _sessao[0].get('substituir'):
        return preparar_modelo(context, pasta, arquivo, tipo)
    antes = _dados_antes()
    selecionados = [o.name for o in context.selected_objects]
    ativo = context.object.name if context.object else ''
    try:
        novos, raizes, erro = _biblioteca.inserir_preset(context, pasta, arquivo, tipo, Vector((0, 0, 0)))
        if erro:
            raise ValueError(erro)
        modulos = [o for o in raizes if _chapas.MARCA_CONJUNTO in o]
        if tipo != 'modulo' or len(modulos) != 1 or len(raizes) != 1:
            raise ValueError('Escolha um unico modulo completo')
        erro = posicionar_modelo(context, modulos[0], novos=novos)
        if erro:
            raise ValueError(erro)
        context.view_layer.objects.active = modulos[0]
        return None
    except Exception as erro:
        _limpar_tentativa(antes)
        for nome in selecionados:
            obj = context.view_layer.objects.get(nome)
            if obj:
                obj.select_set(True)
        context.view_layer.objects.active = context.view_layer.objects.get(ativo)
        return str(erro)


def preparar_modelo(context, pasta, arquivo, tipo):
    if not ativa(context):
        return 'Entre na edicao de uma parede'
    if tipo != 'modulo':
        return 'Escolha um modulo completo na biblioteca'
    antes = _dados_antes()
    selecao = [o.name for o in context.selected_objects]
    ativo = context.object.name if context.object else ''
    try:
        novos, raizes, erro = _biblioteca.inserir_preset(context, pasta, arquivo, tipo, Vector((0, 0, 0)))
        if erro:
            return erro
        modulos = [o for o in novos if _chapas.MARCA_CONJUNTO in o]
        if len(modulos) != 1 or any(o != modulos[0] for o in raizes):
            return 'O modelo precisa conter um unico modulo completo'
        modulo = modulos[0]
        medidas = _modulos.medir_conjunto(modulo)
        if not medidas or min(medidas) <= 0:
            return 'O modelo nao tem dimensoes validas'
        s = _sessao[0]
        s.update(modelo={'pasta': pasta, 'arquivo': arquivo, 'tipo': tipo,
                         'nome': modulo.name}, altura=medidas[1], profundidade=medidas[2],
                 instalacao=max(s['regiao']['retangulo'][2] * 1000, modulo.matrix_world.translation.z * 1000),
                 escolhendo=True)
        if s.get('substituir'):
            alvo = bpy.data.objects.get(s['substituir'])
            if alvo is None:
                return 'O modulo que seria substituido foi removido'
            atual = _paredes_composicao.ficha(alvo, s)
            s.update(altura=atual['altura'] * 1000, profundidade=atual['profundidade'] * 1000,
                     instalacao=atual['base'] * 1000, quantidade=1, escolhendo=False)
        _plano[0] = None
        _aviso[0] = ''
    except Exception as erro:
        return str(erro)
    finally:
        _limpar_tentativa(antes)
        for obj in context.selected_objects:
            obj.select_set(False)
        for nome in selecao:
            obj = context.view_layer.objects.get(nome)
            if obj:
                obj.select_set(True)
        context.view_layer.objects.active = context.view_layer.objects.get(ativo)
        _redesenhar()
    return None


def _intersecoes_contorno(regiao, u, z):
    cruzamentos = []
    for inicio, fim in regiao['contorno']:
        a, b = Vector(inicio), Vector(fim)
        if (a.z <= z < b.z) or (b.z <= z < a.z):
            t = (z - a.z) / (b.z - a.z)
            cruzamentos.append((a + (b - a) * t).dot(u))
    cruzamentos.sort()
    return list(zip(cruzamentos[::2], cruzamentos[1::2]))


def _intersectar_faixas(faixas, outras):
    return [(max(a, c), min(b, d)) for a, b in faixas for c, d in outras
            if min(b, d) - max(a, c) > 1e-6]


def faixas_da_face(regiao, u, base, topo):
    """Corta o contorno real: buracos e lados inclinados nao viram area util."""
    s0, s1, z0, z1 = regiao['retangulo']
    if base < z0 - 1e-6 or topo > z1 + 1e-6 or topo <= base:
        return []
    alturas = {base + 1e-7, topo - 1e-7}
    for a, b in regiao['contorno']:
        for p in (a, b):
            if base < p[2] < topo:
                alturas.update((max(base + 1e-7, p[2] - 1e-7),
                                min(topo - 1e-7, p[2] + 1e-7)))
    faixas = [(s0, s1)]
    for z in sorted(alturas):
        faixas = _intersectar_faixas(faixas, _intersecoes_contorno(regiao, u, z))
    return faixas


def faixas_livres(context, s, base, topo, profundidade, excluir=()):
    """A mesma area livre para inserir, arrastar, editar e distribuir."""
    faixas = faixas_da_face(s['regiao'], Vector(s['u']), base, topo)
    for a, b in obstaculos(context, s, base, topo, profundidade, excluir):
        faixas = [(c, d) for c0, d0 in faixas for c, d in
                  ((c0, min(d0, a)), (max(c0, b), d0)) if d - c > 1e-6]
    return faixas


def encaixar_na_face(context, modulo, ponto, s, caixa=None, tolerancia=0):
    """Limita o volume inteiro e escolhe o vao valido mais proximo do alvo.

    Recebe tambem uma face fora da edicao 2D: o arraste direito usa as
    mesmas restricoes, sem duplicar um posicionador ou redimensionar pecas.
    """
    caixa = caixa or _paredes.caixa_do_modulo(modulo)
    if caixa is None:
        return None, 'O modelo precisa conter um modulo completo'
    lo, hi = caixa
    escala = modulo.matrix_world.to_scale()
    largura, altura, profundidade = (abs((hi[i] - lo[i]) * escala[i]) for i in (0, 2, 1))
    s0, s1, z0, z1 = s['regiao']['retangulo']
    esquerda, direita = s0 + s.get('esquerda', 0) / 1000, s1 - s.get('direita', 0) / 1000
    if min(largura, altura, profundidade) <= 0:
        return None, 'O modelo nao tem dimensoes validas'
    if largura > direita - esquerda + .00005 or altura > z1 - z0 + .00005:
        return None, 'O tamanho original do modelo nao cabe na parede'
    u, plano = Vector(s['u']), Vector(s['ponto'])
    centro, base = ponto.dot(u), ponto.z - altura / 2
    if tolerancia:
        centro, base = _paredes.posicao_no_arraste(s['regiao']['retangulo'], centro,
                         base, largura, altura, tolerancia)
    base = max(z0, min(z1 - altura, base))
    faixas = faixas_livres(context, s, base, base + altura, profundidade, (modulo.name,))
    candidatos = []
    for a, b in faixas:
        a, b = max(a, esquerda), min(b, direita)
        if b - a >= largura - .00005:
            candidatos.append(max(a + largura / 2, min(b - largura / 2, centro)))
    if not candidatos:
        return None, 'Nao ha vao livre sem sobrepor outro modulo ou ultrapassar a parede'
    centro = min(candidatos, key=lambda c: abs(c - centro))
    costas = plano + u * (centro - plano.dot(u))
    costas.z = base
    return costas, None


def _caixa_no_referencial(obj, u, n, plano):
    pontos = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    return (min(p.dot(u) for p in pontos), max(p.dot(u) for p in pontos),
            min(p.z for p in pontos), max(p.z for p in pontos),
            min((p - plano).dot(n) for p in pontos), max((p - plano).dot(n) for p in pontos))


def _recortar_poligono(pontos, eixo, limite, sinal):
    """Recorta apenas as faces candidatas que a BVH nativa encontrou."""
    saida = []
    for a, b in zip(pontos, pontos[1:] + pontos[:1]):
        da, db = sinal * (a[eixo] - limite), sinal * (b[eixo] - limite)
        if da >= 0:
            saida.append(a)
        if (da >= 0) != (db >= 0):
            saida.append(a + (b - a) * (da / (da - db)))
    return saida


def _faces_no_volume(obj, avaliado, dep, s, base, topo, profundidade):
    """Consulta espacial nativa, sem varrer vertices da cena no gesto."""
    u, n, ponto = (Vector(s[k]) for k in ('u', 'normal', 'ponto'))
    s0, s1 = s['regiao']['retangulo'][:2]
    centro = ponto + u * ((s0 + s1) / 2 - ponto.dot(u)) + n * profundidade / 2
    centro.z = (base + topo) / 2
    raio = Vector(((s1 - s0) / 2, (topo - base) / 2, profundidade / 2)).length
    inversa = obj.matrix_world.inverted_safe()
    # Limite conservador para escala nao uniforme/shear do objeto.
    raio *= sum(inversa.to_3x3().col[i].length for i in range(3))
    arvore = BVHTree.FromObject(obj, dep)
    if arvore is None:
        return []
    indices = {acerto[2] for acerto in arvore.find_nearest_range(inversa @ centro, raio)}
    intervalos = []
    for indice in indices:
        poly = avaliado.data.polygons[indice]
        pontos = []
        for i in poly.vertices:
            p = obj.matrix_world @ avaliado.data.vertices[i].co
            pontos.append(Vector((p.dot(u), p.z, (p - ponto).dot(n))))
        for eixo, limite, sinal in ((0, s0, 1), (0, s1, -1), (1, base + 1e-6, 1),
                 (1, topo - 1e-6, -1), (2, 1e-5, 1), (2, profundidade - 1e-6, -1)):
            pontos = _recortar_poligono(pontos, eixo, limite, sinal)
            if not pontos:
                break
        if pontos:
            a, b = min(p.x for p in pontos), max(p.x for p in pontos)
            if b - a > 1e-6:
                intervalos.append((a, b))
    return intervalos


def obstaculos(context, s, base, topo, profundidade, excluir=()):
    context.view_layer.update()
    parede = bpy.data.objects.get(s['parede'])
    ponto, n, u = (Vector(s[k]) for k in ('ponto', 'normal', 'u'))
    resultado = []
    modulos = associados(parede, ponto, n, context.scene.objects, s['regiao'])
    for modulo in modulos:
        if modulo.name in excluir:
            continue
        caixa = _paredes.caixa_do_modulo(modulo)
        if caixa is None:
            continue
        lo, hi = caixa
        pontos = [modulo.matrix_world @ Vector((x, y, z)) for x in (lo.x, hi.x)
                  for y in (lo.y, hi.y) for z in (lo.z, hi.z)]
        if min(p.z for p in pontos) < topo - 1e-6 and max(p.z for p in pontos) > base + 1e-6:
            resultado.append((min(p.dot(u) for p in pontos), max(p.dot(u) for p in pontos)))
    # As paredes vizinhas sao consultadas pela malha avaliada. Raycast e'
    # nativo; a caixa e' apenas o descarte inicial, nunca o limite final.
    dep = context.evaluated_depsgraph_get()
    for obj in context.scene.objects:
        if not superficie(obj):
            continue
        avaliado = obj.evaluated_get(dep)
        cx = _caixa_no_referencial(avaliado, u, n, ponto)
        if cx[3] <= base + 1e-6 or cx[2] >= topo - 1e-6 or cx[5] <= 1e-5 or cx[4] >= profundidade:
            continue
        resultado.extend(_faces_no_volume(obj, avaliado, dep, s, base, topo, profundidade))
        # Eixos horizontais de paredes adjacentes: amostras nas duas
        # extremidades e no meio do volume evitam ignorar retorno em L.
        inversa = obj.matrix_world.inverted_safe()
        direcao = (inversa.to_3x3() @ u).normalized()
        for z in (base + 1e-5, (base + topo) / 2, topo - 1e-5):
            for d in (1e-5, profundidade / 2, profundidade - 1e-5):
                inicio = ponto + u * (cx[0] - ponto.dot(u) - 0.01) + n * d
                inicio.z = z
                local = inversa @ inicio
                entradas = []
                for _ in range(32):
                    acertou, pos, normal, indice = avaliado.ray_cast(local, direcao)
                    if not acertou:
                        break
                    mundo = obj.matrix_world @ pos
                    valor = mundo.dot(u)
                    if valor > cx[1] + 1e-5:
                        break
                    entradas.append(valor)
                    local = pos + direcao * 1e-6
                for a, b in zip(entradas[::2], entradas[1::2]):
                    if b - a > 1e-6:
                        resultado.append((a, b))
    return resultado


def planejar(context, s=None):
    s = s or _sessao[0]
    if s is None or s.get('modelo') is None:
        return {'erro': 'Escolha um modulo na biblioteca'}
    if s.get('substituir'):
        return _paredes_composicao.planejar_troca(context, s)
    quantidade = s['quantidade']
    base, altura, profundidade = (s[k] / 1000.0 for k in ('instalacao', 'altura', 'profundidade'))
    if quantidade < 1 or min(altura, profundidade) < 0.02:
        return {'erro': 'Quantidade ou dimensoes invalidas'}
    u = Vector(s['u'])
    faixas = faixas_livres(context, s, base, base + altura, profundidade)
    faixa = next(((a, b) for a, b in faixas if a - 1e-6 <= s['s'] <= b + 1e-6), None)
    if faixa is None:
        return {'erro': 'Escolha um vao livre compativel com a altura'}
    inicio = faixa[0] + s['esquerda'] / 1000
    fim = faixa[1] - s['direita'] / 1000
    espaco = s['espacamento'] / 1000
    largura = (fim - inicio - (quantidade - 1) * espaco) / quantidade
    if largura < 0.02:
        return {'erro': 'Nao ha espaco para a quantidade e as folgas'}
    return {'largura': largura, 'altura': altura, 'profundidade': profundidade,
            'base': base, 'inicios': [inicio + i * (largura + espaco) for i in range(quantidade)],
            'faixa': faixa}


def criar_modulos(context):
    s = _sessao[0]
    if s and s.get('substituir'):
        return _paredes_composicao.substituir(context)
    if s and s['escolhendo']:
        return 'Clique no vao da parede antes de criar os modulos'
    plano = planejar(context, s)
    if plano.get('erro'):
        return plano['erro']
    parede = bpy.data.objects.get(s['parede'])
    if parede is None:
        return 'Parede nao encontrada'
    antes = _dados_antes()
    selecionados = [o.name for o in context.selected_objects]
    ativo = context.object.name if context.object else ''
    uid_antes = parede.get(_paredes.CHAVE_UID_PAREDE)
    try:
        criados = []
        for inicio in plano['inicios']:
            m = s['modelo']
            novos, raizes, erro = _biblioteca.inserir_preset(context, m['pasta'], m['arquivo'], m['tipo'], Vector((0, 0, 0)))
            if erro:
                raise ValueError(erro)
            conjuntos = [o for o in novos if _chapas.MARCA_CONJUNTO in o]
            if len(conjuntos) != 1:
                raise ValueError('O modelo deixou de conter um unico modulo')
            conj = conjuntos[0]
            ocupado = _chapas._ocupado[0]
            _chapas._ocupado[0] = True
            try:
                conj.conj_largura_mm = plano['largura'] * 1000
                conj.conj_altura_mm = plano['altura'] * 1000
                conj.conj_profundidade_mm = plano['profundidade'] * 1000
            finally:
                _chapas._ocupado[0] = ocupado
            _modulos.redimensionar_conjunto(conj)
            real = _modulos.medir_conjunto(conj)
            if any(abs(a / 1000 - plano[k]) > 0.00005 for a, k in zip(real, ('largura', 'altura', 'profundidade'))):
                raise ValueError('O modelo nao permite estas dimensoes sem perder seus encaixes')
            u, n, ponto = (Vector(s[k]) for k in ('u', 'normal', 'ponto'))
            costas = ponto + u * (inicio + plano['largura'] / 2 - ponto.dot(u))
            costas.z = plano['base']
            _paredes.colocar_na_parede(conj, parede, costas, n)
            _paredes.associar(conj, parede, costas, n, s['face'])
            context.view_layer.update()
            criados += [o.name for o in novos]
        janela, area, regiao = _janela_da_sessao()
        if area and area.spaces.active.local_view:
            for nome in criados:
                bpy.data.objects[nome].local_view_set(area.spaces.active, True)
                if s['local_anterior']:
                    s['membros_anteriores'].append(nome)
            context.view_layer.update()
        s['modelo'] = None
        s['escolhendo'] = False
    except Exception as erro:
        _limpar_tentativa(antes)
        if uid_antes is None and _paredes.CHAVE_UID_PAREDE in parede:
            del parede[_paredes.CHAVE_UID_PAREDE]
        for nome in selecionados:
            obj = context.view_layer.objects.get(nome)
            if obj:
                obj.select_set(True)
        context.view_layer.objects.active = context.view_layer.objects.get(ativo)
        return str(erro)
    finally:
        _redesenhar()
    return None


def desenhar():
    context = bpy.context
    if not ativa(context) or context.area.as_pointer() != _sessao[0]['area']:
        return
    s = _sessao[0]
    _paredes_composicao.desenhar(context)
    if s['modelo'] is None or _eventos._desfazendo[0]:
        return
    plano = _plano[0]
    if plano is None:
        return
    if plano.get('erro'):
        return
    n, u, ponto = (Vector(s[k]) for k in ('normal', 'u', 'ponto'))
    cor = _hud._cor_realce_hud()
    segmentos, rotulos = [], []
    for inicio in plano['inicios']:
        pontos = []
        for z in (plano['base'], plano['base'] + plano['altura']):
            for x in (inicio, inicio + plano['largura']):
                p = ponto + u * (x - ponto.dot(u)) + n * 0.002
                p.z = z
                pontos.append(view3d_utils.location_3d_to_region_2d(context.region, context.region_data, p))
        if any(p is None for p in pontos):
            continue
        for a, b in ((0, 1), (1, 3), (3, 2), (2, 0)):
            segmentos.extend((pontos[a], pontos[b]))
        rotulos.append(((pontos[2] + pontos[3]) / 2, _opcoes._texto_medida(plano['largura'] * 1000)))
    if segmentos:
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        gpu.state.blend_set('ALPHA')
        try:
            shader.bind()
            shader.uniform_float('color', cor)
            batch_for_shader(shader, 'LINES', {'pos': segmentos}).draw(shader)
            blf.size(0, 12 * context.preferences.system.ui_scale)
            blf.color(0, *cor)
            for p, texto in rotulos:
                blf.position(0, p.x, p.y + 6, 0)
                blf.draw(0, texto)
        finally:
            gpu.state.blend_set('NONE')


class OBJECT_OT_editar_parede(Operator):
    bl_idname = 'object.cabinet_editar_parede'
    bl_label = 'Editar parede'
    objeto: StringProperty(options={'SKIP_SAVE'})

    def execute(self, context):
        obj = bpy.data.objects.get(self.objeto) if self.objeto else context.object
        erro = iniciar(context, obj)
        _aviso[0] = erro or ''
        if erro:
            self.report({'WARNING'}, erro)
        return {'CANCELLED'} if erro else {'FINISHED'}


class OBJECT_OT_sair_parede(Operator):
    bl_idname = 'object.cabinet_sair_parede'
    bl_label = 'Sair da edicao da parede'

    def execute(self, context):
        encerrar()
        return {'FINISHED'}


class OBJECT_OT_escolher_vao_parede(Operator):
    bl_idname = 'object.cabinet_escolher_vao_parede'
    bl_label = 'Escolher vao na parede'

    def execute(self, context):
        if not ativa(context):
            return {'CANCELLED'}
        _sessao[0]['escolhendo'] = True
        return {'FINISHED'}


class OBJECT_OT_cancelar_previa_parede(Operator):
    bl_idname = 'object.cabinet_cancelar_previa_parede'
    bl_label = 'Cancelar previa'

    def execute(self, context):
        if ativa(context):
            _sessao[0]['modelo'] = None
            _sessao[0]['substituir'] = ''
            _sessao[0]['escolhendo'] = False
            _redesenhar()
        return {'FINISHED'}


class OBJECT_OT_distribuir_parede(Operator):
    bl_idname = 'object.cabinet_distribuir_parede'
    bl_label = 'Criar modulos na parede'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if not ativa(context):
            return {'CANCELLED'}
        erro = criar_modulos(context)
        if erro:
            self.report({'WARNING'}, erro)
            return {'CANCELLED'}
        return {'FINISHED'}


class OBJECT_OT_observar_parede(Operator):
    bl_idname = 'object.cabinet_observar_parede'
    bl_label = 'Observar navegacao da parede'
    bl_options = {'INTERNAL'}

    def invoke(self, context, event):
        self.sessao = _sessao[0]['id']
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        try:
            return self._modal(context, event)
        except Exception:
            encerrar()
            raise

    def cancel(self, context):
        if ativa() and _sessao[0]['id'] == self.sessao:
            encerrar()

    def _modal(self, context, event):
        if not ativa() or _sessao[0]['id'] != self.sessao:
            return {'FINISHED'}
        if _eventos._desfazendo[0]:
            return {'PASS_THROUGH'}
        if _paredes_composicao._edicao[0] is not None:
            return {'PASS_THROUGH'}
        janela, area, regiao = _janela_da_sessao()
        if area is None:
            encerrar()
            return {'FINISHED'}
        na_vista = (regiao.x <= event.mouse_x < regiao.x + regiao.width
                    and regiao.y <= event.mouse_y < regiao.y + regiao.height)
        if na_vista:
            with context.temp_override(window=janela, area=area, region=regiao):
                if navegacao_de_saida(context, event):
                    encerrar(perspectiva=True)
                    return {'PASS_THROUGH'}
                s = _sessao[0]
                if not s['escolhendo'] and event.type == 'LEFTMOUSE' and event.value == 'PRESS':
                    cota = _paredes_composicao.cota_sob(event.mouse_x - regiao.x, event.mouse_y - regiao.y)
                    if cota:
                        bpy.ops.object.cabinet_editar_cota_parede('INVOKE_DEFAULT',
                            objeto=cota[4], propriedade=cota[5])
                        return {'RUNNING_MODAL'}
                if s['escolhendo']:
                    if event.type == 'ESC' and event.value == 'PRESS':
                        s['modelo'] = None
                        s['escolhendo'] = False
                        _redesenhar()
                        return {'RUNNING_MODAL'}
                    if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
                        xy = (event.mouse_x - regiao.x, event.mouse_y - regiao.y)
                        origem = view3d_utils.region_2d_to_origin_3d(regiao, context.region_data, xy)
                        direcao = view3d_utils.region_2d_to_vector_3d(regiao, context.region_data, xy)
                        ponto = intersect_line_plane(origem, origem + direcao,
                                      Vector(s['ponto']), Vector(s['normal']))
                        if ponto is not None:
                            s['s'] = ponto.dot(Vector(s['u']))
                            s['escolhendo'] = False
                            _plano[0] = None
                            _redesenhar()
                        return {'RUNNING_MODAL'}
                elif s['modelo'] is not None and event.type == 'ESC' and event.value == 'PRESS':
                    s['modelo'] = None
                    _plano[0] = None
                    _redesenhar()
                    return {'RUNNING_MODAL'}
        verificar(atualizar_previa=False)
        return {'PASS_THROUGH'}


class VIEW3D_MT_parede_cabinet(Menu):
    bl_idname = 'VIEW3D_MT_parede_cabinet'
    bl_label = 'Cabinet Creator'

    def draw(self, context):
        op = self.layout.operator('object.cabinet_editar_parede', text='Editar parede')
        op.objeto = _alvo_contexto[0] or ''


def menu_contexto(self, context):
    alvo = _alvo_contexto[0]
    obj = bpy.data.objects.get(alvo) if alvo is not None else context.object
    if superficie(obj) and context.mode == 'OBJECT':
        self.layout.separator()
        self.layout.menu('VIEW3D_MT_parede_cabinet')
