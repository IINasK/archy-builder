"""Grupos visuais por categoria; arame nativo conserva geometria e snap."""
import json
import bpy
from bpy.types import Operator

_chapas = _modulos = _portas = _gavetas = _prateleiras = _divisorias = None
_areas_criacao = _selecao = _gaveta = _hud = _eventos = _ferragens = None
_biblioteca_faixa = None
_fundos = None
_materiais = None
ATIVOS = 'cabinet_visual_ativos'
GRUPOS = 'cabinet_visual_grupos'
ORIGINAL = 'cabinet_visual_original'
ALTERNAR = 'object.cabinet_alternar_partes'
EDITAR = 'object.cabinet_editar_grupo_visual'
ALTURA = 38
_edicao = [None]
_vistas = [{}]


def categoria(context):
    aba = context.scene.cabinet_aba
    return ('INTERNOS' if aba in {'PRATELEIRAS', 'DIVISORIAS'} else
            aba if aba in {'MODULOS', 'PORTAS', 'GAVETAS', 'FUNDOS'} else '')


def modulo(context):
    if _eventos._desfazendo[0]:
        return None
    if _edicao[0]:
        return context.scene.objects.get(_edicao[0]['modulo'])
    return _areas_criacao.modulo_das_portas(context)


def _ler(obj, chave, padrao):
    return json.loads(obj.get(chave, json.dumps(padrao)))


def ativo(obj, tipo):
    return obj is not None and tipo in _ler(obj, ATIVOS, [])


def esmaecido(obj):
    return ORIGINAL in obj and obj.display_type == 'WIRE'


def disponivel(context):
    if context.mode != 'OBJECT' or not categoria(context):
        return False
    dono = modulo(context)
    if dono is None:
        return False
    if _edicao[0]:
        return True
    obj = context.view_layer.objects.active
    if obj is None or not obj.select_get():
        return False
    if dono.select_get():
        return True
    if _areas_criacao.MARCA in obj:
        return True
    return _modulos._conj_de(obj) == dono and not _materiais.protegida_no_grupo(obj)


def altura(context):
    return ALTURA if disponivel(context) else 0


def _fisicas(objetos):
    return {o for o in objetos if o.type in {'MESH', 'CURVE', 'SURFACE', 'FONT', 'META'}
            and o.get('cabinet_peca') not in _ferragens.PECAS_OCULTAS_RIG}


def membros(context, dono, tipo):
    todos = list(dono.children_recursive)
    marcas = {'GAVETAS': (_gavetas.MARCA_GRUPO,),
              'INTERNOS': (_prateleiras.MARCA_GRUPO, _divisorias.MARCA_GRUPO),
              'FUNDOS': (_chapas.MARCA_FUNDO,)}
    if tipo == 'PORTAS':
        raizes = _portas._portas_do_conjunto(dono)
    elif tipo == 'MODULOS':
        raizes = [o for o in _modulos._chapas_do_conjunto(dono) if _chapas.MARCA_FUNDO not in o]
    else:
        raizes = [o for o in todos if any(m in o for m in marcas.get(tipo, ()))]
    objetos = _fisicas(o for raiz in raizes for o in [raiz, *raiz.children_recursive])
    config = _ler(dono, GRUPOS, {}).get(tipo, {})
    incluir, excluir = set(config.get('incluir', [])), set(config.get('excluir', []))
    objetos.update(o for o in context.scene.objects if o.get('chapa_uid') in incluir)
    objetos = _fisicas(o for o in objetos if o.get('chapa_uid') not in excluir)
    return _selecao.objetos_na_camada(context, objetos)


def configurar(context, dono, tipo, obj, incluir):
    grupos = _ler(dono, GRUPOS, {})
    config = grupos.setdefault(tipo, dict(incluir=[], excluir=[]))
    sim, nao = ('incluir', 'excluir') if incluir else ('excluir', 'incluir')
    for peca in _fisicas([obj, *obj.children_recursive]):
        uid = _chapas._garantir_uid(peca)
        if uid not in config[sim]:
            config[sim].append(uid)
        if uid in config[nao]:
            config[nao].remove(uid)
    dono[GRUPOS] = json.dumps(grupos)
    verificar(context)


def definir(context, dono, tipo, esconder):
    tipos = set(_ler(dono, ATIVOS, []))
    tipos.add(tipo) if esconder else tipos.discard(tipo)
    dono[ATIVOS] = json.dumps(sorted(tipos))
    verificar(context)


def alvos_snap(context, dono):
    return {o.name for tipo in _ler(dono, ATIVOS, []) for o in membros(context, dono, tipo)}


def _restaurar(obj):
    original = _ler(obj, ORIGINAL, {})
    if obj.display_type == 'WIRE':
        obj.display_type = original['tipo']
    if tuple(obj.color) == (1, 1, 1, 1):
        obj.color = original['cor']
    del obj[ORIGINAL]


def _ajustar_vistas(context, usar):
    vivas = set()
    for janela in context.window_manager.windows:
        for area in janela.screen.areas:
            for espaco in area.spaces:
                if espaco.type != 'VIEW_3D':
                    continue
                chave = espaco.as_pointer(); vivas.add(chave)
                anterior = _vistas[0].get(chave)
                if usar and anterior is None:
                    _vistas[0][chave] = (espaco.shading.wireframe_color_type,
                                        espaco.overlay.wireframe_opacity, espaco.overlay.show_overlays)
                    espaco.shading.wireframe_color_type = 'OBJECT'
                    espaco.overlay.wireframe_opacity = .22
                    espaco.overlay.show_overlays = True
                elif not usar and anterior is not None:
                    if espaco.shading.wireframe_color_type == 'OBJECT':
                        espaco.shading.wireframe_color_type = anterior[0]
                    if abs(espaco.overlay.wireframe_opacity - .22) < .0001:
                        espaco.overlay.wireframe_opacity = anterior[1]
                    if espaco.overlay.show_overlays:
                        espaco.overlay.show_overlays = anterior[2]
                    del _vistas[0][chave]
    for chave in set(_vistas[0]) - vivas:
        del _vistas[0][chave]


def verificar(context=None):
    if _eventos._desfazendo[0]:
        return
    context = context or bpy.context
    desejados = set()
    for dono in context.scene.objects:
        if _chapas.MARCA_CONJUNTO in dono:
            for tipo in _ler(dono, ATIVOS, []):
                desejados.update(membros(context, dono, tipo))
    ocupado = _chapas._ocupado[0]
    _chapas._ocupado[0] = True
    try:
        for obj in bpy.data.objects:
            if obj in desejados and ORIGINAL not in obj:
                obj[ORIGINAL] = json.dumps(dict(tipo=obj.display_type, cor=list(obj.color)))
                obj.display_type = 'WIRE'
                obj.color = (1, 1, 1, 1)
            elif obj not in desejados and ORIGINAL in obj:
                _restaurar(obj)
        _ajustar_vistas(context, bool(desejados))
    finally:
        _chapas._ocupado[0] = ocupado


def eh_acao(acao):
    return bool(acao and acao[0] == 'operador' and acao[1] in {ALTERNAR, EDITAR})


def widgets(context, x, w, altura):
    if not disponivel(context):
        return []
    tipo = categoria(context); dono = modulo(context)
    base = (_gaveta._divisa_gaveta(context, altura) + _gaveta.FOLGA_DIVISA_GAVETA
            if context.screen.get(_biblioteca_faixa.CHAVE_LAYOUT) != 2
            else _gaveta.ALTURA_RODAPE_GAVETA)
    escondido = ativo(dono, tipo)
    rotulo = 'Visibilidade de objetos' if w >= 260 else 'Visibilidade'
    return [(x + w - 78, base + 4, 36, 30, '', ('operador', ALTERNAR, escondido)),
            (x + w - 36, base + 4, 36, 30, '', ('operador', EDITAR)),
            (x, base + 4, max(0, w - 84), 30, rotulo, ('rotulo',))]


class OBJECT_OT_alternar_partes(Operator):
    bl_idname = ALTERNAR
    bl_label = 'Mostrar ou esmaecer partes da aba atual'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return disponivel(context)

    def execute(self, context):
        dono = modulo(context); tipo = categoria(context)
        definir(context, dono, tipo, not ativo(dono, tipo))
        _eventos._redesenhar_viewports(context)
        return {'FINISHED'}


def _selecionar_nativo(context, event):
    # O seletor nativo resolve o hit, incluindo arestas do arame e oclusao.
    bpy.ops.view3d.select('EXEC_DEFAULT', location=(event.mouse_x - context.region.x, event.mouse_y - context.region.y),
                          deselect_all=True)
    return context.view_layer.objects.active


def _terminar(context, cancelar):
    estado = _edicao[0]
    esquecer_edicao()
    if not estado:
        return
    dono = context.scene.objects.get(estado['modulo'])
    if cancelar and dono is not None:
        dono[GRUPOS] = estado['original']
    for obj in context.view_layer.objects:
        obj.select_set(obj.name in estado['selecao'])
    context.view_layer.objects.active = context.view_layer.objects.get(estado['ativo'])
    verificar(context)
    _eventos._redesenhar_viewports(context)


def esquecer_edicao():
    estado = _edicao[0]; _edicao[0] = None
    if estado:
        for janela in bpy.context.window_manager.windows:
            for area in janela.screen.areas:
                if area.as_pointer() == estado['area']:
                    area.header_text_set(None)


class OBJECT_OT_editar_grupo_visual(Operator):
    bl_idname = EDITAR
    bl_label = 'Editar grupo visual: esquerdo inclui, direito retira, Enter conclui, Esc cancela'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return OBJECT_OT_alternar_partes.poll(context)

    def invoke(self, context, event):
        if _edicao[0]:
            _edicao[0]['concluir'] = True
            return {'FINISHED'}
        dono = modulo(context)
        # O editor nao disputa cliques com uma captura interrompida.
        _areas_criacao.esquecer()
        for estado in (_gavetas._assistente_gavetas[0], _prateleiras._assistente_prateleiras[0],
                       _divisorias._assistente_divisorias[0], _fundos._assistente_fundo[0],
                       _portas._assistente_porta[0]):
            if estado:
                estado['cancelar'] = True
        _edicao[0] = dict(modulo=dono.name, cena=context.scene.name, tipo=categoria(context),
            original=dono.get(GRUPOS, '{}'), selecao=[o.name for o in context.selected_objects],
            ativo=context.object.name if context.object else '', concluir=False, area=context.area.as_pointer())
        _hud._hover_hud.clear()
        context.window_manager.modal_handler_add(self)
        context.area.header_text_set('Grupo visual: esquerdo inclui | direito retira | Enter conclui | Esc cancela')
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        estado = _edicao[0]
        if (not estado or estado['cena'] != context.scene.name
                or not context.scene.objects.get(estado['modulo']) or context.area is None):
            esquecer_edicao()
            return {'CANCELLED'}
        if estado['concluir'] or event.type in {'RET', 'NUMPAD_ENTER', 'ESC'}:
            cancelar = event.type == 'ESC'
            _terminar(context, cancelar)
            return {'CANCELLED'} if cancelar else {'FINISHED'}
        regiao = context.region
        dentro = (regiao and regiao.x <= event.mouse_x < regiao.x + regiao.width
                  and regiao.y <= event.mouse_y < regiao.y + regiao.height)
        if context.area.type != 'VIEW_3D' or _gaveta._eh_area_gaveta(context) or not dentro:
            return {'PASS_THROUGH'}
        if event.type in {'LEFTMOUSE', 'RIGHTMOUSE'}:
            if event.value == 'PRESS':
                try:
                    obj = _selecionar_nativo(context, event)
                    if obj is not None and obj.select_get():
                        configurar(context, context.scene.objects[estado['modulo']], estado['tipo'], obj,
                                   event.type == 'LEFTMOUSE')
                except Exception:
                    _terminar(context, True)
                    raise
            return {'RUNNING_MODAL'}
        return {'PASS_THROUGH'}

    def cancel(self, context):
        _terminar(context, True)


@bpy.app.handlers.persistent
def suspender(*_args):
    if _edicao[0]:
        _terminar(bpy.context, True)
    _edicao[0] = None
    for obj in bpy.data.objects:
        if ORIGINAL in obj:
            _restaurar(obj)
    _ajustar_vistas(bpy.context, False)


@bpy.app.handlers.persistent
def retomar(*_args):
    verificar()


HANDLERS = (('save_pre', suspender), ('save_post', retomar), ('load_pre', suspender))
