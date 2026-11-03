"""Ambientes por faces nativas da Alvenaria; cores so' durante a definicao."""
import bpy, bmesh, colorsys, uuid, math
import numpy as np
import gpu, blf
from bpy.types import Operator
from bpy.props import StringProperty, FloatVectorProperty
from gpu_extras.batch import batch_for_shader
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree
from bpy_extras import view3d_utils

_paredes = _paredes_edicao = _orcamento = _eventos = _gaveta = None
ATR_FACE = 'cabinet_ambiente'
CHAVE_MAPA = 'cabinet_ambientes'
CHAVE_NOME = 'cabinet_ambiente_nome'
ALVO = '@ambiente_alvenaria'
_sujo = [True]
_cache = [{}]
_handler = [None]
_retorno = [None]
_edicao_faces = [None]
_faces_nativas = [{}]  # Wrappers BMesh so' no Edit Mode; soltar antes do undo.


def acompanhar_faces(context=None,verificar=True):
    """Preserva faces nativas existentes; faces criadas nao herdam a categoria."""
    if _eventos._desfazendo[0]:return
    context=context or bpy.context
    objetos=context.objects_in_mode_unique_data if context.mode=='EDIT_MESH' else ()
    atuais={}
    for obj in objetos:
        if not _paredes.alvenaria_definida(obj):continue
        bm=bmesh.from_edit_mesh(obj.data);anterior=_faces_nativas[0].get(obj.data.name)
        if anterior and anterior['bmesh'] is bm and not verificar:
            atuais[obj.data.name]=anterior;continue
        # Reter os wrappers impede reuso de id durante a comparacao de identidades.
        faces={id(f):f for f in bm.faces}
        atuais[obj.data.name]=dict(bmesh=bm,faces=faces)
        camada=bm.faces.layers.int.get(ATR_FACE)
        if anterior and anterior['bmesh'] is bm and camada is not None:
            mudou=False
            for identidade,face in faces.items():
                if anterior['faces'].get(identidade) is not face and face[camada]:
                    face[camada]=0;mudou=True
            if mudou:
                _sujo[0]=True
                # Publica a nova identidade antes do update que notifica o depsgraph.
                _faces_nativas[0][obj.data.name]=atuais[obj.data.name]
                bmesh.update_edit_mesh(obj.data,loop_triangles=False,destructive=False)
    _faces_nativas[0]=atuais


def encerrar_selecao():
    s=_edicao_faces[0]
    _edicao_faces[0]=None
    if s is None:return
    bpy.types.SpaceView3D.draw_handler_remove(s['handler'],'WINDOW')
    try:bpy.context.window_manager.event_timer_remove(s['timer'])
    except (ReferenceError,RuntimeError):pass
    cena=bpy.data.scenes.get(s['cena']) if not _eventos._desfazendo[0] else None
    if cena is not None:cena.tool_settings.mesh_select_mode=s['modo_anterior']
    for janela in bpy.context.window_manager.windows:
        if janela.as_pointer()==s['janela']:
            area=next((a for a in janela.screen.areas if a.as_pointer()==s['area']),None)
            if area is not None:area.header_text_set(None)
    _paredes._redesenhar()


def preparar_selecao(context,obj,parede_2d=False):
    if not _paredes.alvenaria_definida(obj):raise ValueError('Selecione a Alvenaria')
    encerrar_selecao()
    area=_paredes_edicao.viewport(context)
    if area is None:raise ValueError('Sem viewport 3D para editar a Alvenaria')
    regiao=next(r for r in area.regions if r.type=='WINDOW')
    anterior=tuple(context.scene.tool_settings.mesh_select_mode)
    with context.temp_override(area=area,region=regiao):
        if context.mode=='OBJECT':
            for o in context.selected_objects:o.select_set(False)
            obj.select_set(True);context.view_layer.objects.active=obj
            bpy.ops.object.mode_set(mode='EDIT')
        if context.edit_object!=obj or len(context.objects_in_mode_unique_data)!=1:
            raise ValueError('Edite uma unica Alvenaria')
        context.scene.tool_settings.mesh_select_mode=(False,False,True)
        bpy.ops.mesh.select_all(action='DESELECT')
    s=dict(objeto=obj.name,cena=context.scene.name,area=area.as_pointer(),regiao=regiao.as_pointer(),
           janela=context.window.as_pointer(),parede_2d=parede_2d,modo_anterior=anterior,
           cache=None,sujo=True,hover=None,xy=None,manual=False)
    s['handler']=bpy.types.SpaceView3D.draw_handler_add(desenhar_selecao,(),'WINDOW','POST_VIEW')
    try:s['timer']=context.window_manager.event_timer_add(.1,window=context.window)
    except Exception:
        bpy.types.SpaceView3D.draw_handler_remove(s['handler'],'WINDOW');raise
    _edicao_faces[0]=s
    acompanhar_faces(context)
    _paredes_edicao._aviso[0]=''
    try:atualizar_selecao(obj)
    except Exception:
        encerrar_selecao();raise
    area.header_text_set('Clique na area | Ctrl+clique seleciona faces | Enter abre a vista 2D | Esc sai'
                        if parede_2d else 'Selecione faces | Clique no nome da categoria no menu | Ctrl: face individual | Esc sai')
    return id(s)


def atualizar_selecao(obj):
    s=_edicao_faces[0]
    if s is None or not s['sujo']:return
    bm=bmesh.from_edit_mesh(obj.data).copy()
    try:
        bm.faces.index_update();original=bm.faces.layers.int.new('origem_selecao')
        for f in bm.faces:f[original]=f.index
        bmesh.ops.delete(bm,geom=[f for f in bm.faces if f.hide],context='FACES')
        bm.faces.index_update()
        ids=[f[original] for f in bm.faces]
        caches=[]
        for automatico in (False,True):
            if automatico:
                # Dissolve apenas a copia; o Blender continua dono da malha e da selecao.
                bmesh.ops.dissolve_limit(bm,angle_limit=math.radians(1),verts=[],edges=list(bm.edges))
                bm.faces.index_update()
            trios={}
            for tri in bm.calc_loop_triangles():trios.setdefault(tri[0].face.index,[]).extend(tuple(l.vert.co) for l in tri)
            if automatico:
                # O dissolve conserva faces ao redor de furos; a previa inclui a regiao inteira.
                vistas=set()
                for face in bm.faces:
                    if face in vistas:continue
                    regiao={face};pendentes=[face];vistas.add(face)
                    while pendentes:
                        atual=pendentes.pop()
                        for e in atual.edges:
                            for vizinha in e.link_faces:
                                if vizinha not in vistas and face.normal.dot(vizinha.normal)>=math.cos(math.radians(1)):
                                    vistas.add(vizinha);regiao.add(vizinha);pendentes.append(vizinha)
                    pontos=[p for f in regiao for p in trios.get(f.index,[])]
                    for f in regiao:trios[f.index]=pontos
            caches.append((BVHTree.FromBMesh(bm),trios))
        s.update(cache=caches,ids=ids,sujo=False,hover=None)
    finally:bm.free()


def acerto_selecao(obj,inicio,direcao,manual=False):
    s=_edicao_faces[0]
    if s is None or s['sujo'] or s['cache'] is None:return None
    inversa=obj.matrix_world.inverted_safe()
    return s['cache'][0 if manual else 1][0].ray_cast(inversa@inicio,
        (inversa.to_3x3()@direcao).normalized())[2]


def selecionar_face(context,obj,indice,manual=False):
    s=_edicao_faces[0];bm=bmesh.from_edit_mesh(obj.data);bm.faces.ensure_lookup_table()
    if not manual:bpy.ops.mesh.select_all(action='DESELECT')
    face=bm.faces[s['ids'][indice]]
    face.select_set(not face.select if manual else True);bm.faces.active=face
    bm.select_flush_mode()
    bmesh.update_edit_mesh(obj.data,loop_triangles=False,destructive=False)
    if not manual:bpy.ops.mesh.faces_select_linked_flat(sharpness=math.radians(1))


def evento_selecao(context,event,token):
    s=_edicao_faces[0]
    if s is None or id(s)!=token:return {'CANCELLED'}
    obj=bpy.data.objects.get(s['objeto'])
    area=next((a for a in context.window.screen.areas if a.as_pointer()==s['area']),None)
    if (_eventos._desfazendo[0] or context.scene.name!=s['cena'] or context.mode!='EDIT_MESH'
            or context.window.as_pointer()!=s['janela']
            or obj is None or area is None or context.edit_object!=obj):
        encerrar_selecao();return {'CANCELLED'}
    regiao=next(r for r in area.regions if r.type=='WINDOW')
    if event.type=='TIMER':
        if not _eventos._transformando():atualizar_selecao(obj)
        return {'PASS_THROUGH'}
    if event.type=='ESC' and event.value=='PRESS':
        encerrar_selecao();bpy.ops.object.mode_set(mode='OBJECT');return {'CANCELLED'}
    xy=(event.mouse_x-regiao.x,event.mouse_y-regiao.y)
    dentro=0<=xy[0]<regiao.width and 0<=xy[1]<regiao.height
    confirmar=s['parede_2d'] and event.type in {'RET','NUMPAD_ENTER'} and event.value=='PRESS'
    if dentro and (event.type in {'MOUSEMOVE','LEFT_CTRL','RIGHT_CTRL','LEFTMOUSE'}):
        rv=area.spaces.active.region_3d
        inicio=view3d_utils.region_2d_to_origin_3d(regiao,rv,xy)
        direcao=view3d_utils.region_2d_to_vector_3d(regiao,rv,xy)
        indice=acerto_selecao(obj,inicio,direcao,event.ctrl)
        s.update(hover=indice,manual=event.ctrl,xy=xy);area.tag_redraw()
        if event.type=='LEFTMOUSE' and event.value=='PRESS' and indice is not None:
            with context.temp_override(area=area,region=regiao):
                original=acerto_selecao(obj,inicio,direcao,True)
                if original is not None:selecionar_face(context,obj,original,event.ctrl)
            confirmar=s['parede_2d'] and not event.ctrl
            if not confirmar:return {'RUNNING_MODAL'}
        if event.type=='LEFTMOUSE' and event.value=='PRESS' and not confirmar:return {'RUNNING_MODAL'}
    elif not dentro:
        s['hover']=None;area.tag_redraw()
    if confirmar:
        with context.temp_override(area=area,region=regiao):
            erro=_paredes_edicao.entrar_por_vertices(context,obj,somente_faces=True)
        _paredes_edicao._aviso[0]=erro or ''
        if erro:return {'RUNNING_MODAL'}
        encerrar_selecao();return {'FINISHED'}
    if dentro and event.type=='LEFTMOUSE':return {'RUNNING_MODAL'}
    return {'PASS_THROUGH'}


def desenhar_selecao():
    s=_edicao_faces[0];context=bpy.context
    if (s is None or s['hover'] is None or s['sujo'] or context.mode!='EDIT_MESH'
            or _eventos._desfazendo[0] or _eventos._transformando()
            or context.region.as_pointer()!=s['regiao']):return
    obj=bpy.data.objects.get(s['objeto'])
    if obj is None:return
    ps=s['cache'][0 if s['manual'] else 1][1].get(s['hover'],[])
    anterior=(gpu.state.blend_get(),gpu.state.depth_test_get(),gpu.state.depth_mask_get())
    try:
        gpu.state.blend_set('ALPHA');gpu.state.depth_test_set('LESS_EQUAL');gpu.state.depth_mask_set(False)
        with gpu.matrix.push_pop_projection(),gpu.matrix.push_pop():
            projecao=gpu.matrix.get_projection_matrix();projecao[2]=projecao[2]-projecao[3]*1e-6
            gpu.matrix.load_projection_matrix(projecao);gpu.matrix.multiply_matrix(obj.matrix_world)
            shader=gpu.shader.from_builtin('UNIFORM_COLOR');shader.bind();shader.uniform_float('color',(1,.45,.05,.35))
            batch_for_shader(shader,'TRIS',{'pos':ps}).draw(shader)
    finally:
        gpu.state.blend_set(anterior[0]);gpu.state.depth_test_set(anterior[1]);gpu.state.depth_mask_set(anterior[2])


def _mapa(obj):
    return {k:dict(nome=v['nome'],uid=v['uid'],cor=list(v['cor']))
            for k,v in obj.get(CHAVE_MAPA,{}).items()}


def _cor_padrao(nome):
    nomes=list(_orcamento.COMODOS)
    i=nomes.index(nome) if nome in nomes else len(nomes)
    return colorsys.hsv_to_rgb((i*.61803398875)%1,.65,.95)


def registro(obj,nome,criar=False):
    mapa=_mapa(obj)
    indice=next((int(k) for k,v in mapa.items() if v['nome']==nome),None)
    if indice is None and criar:
        indice=max([0,*map(int,mapa)])+1
        anterior=next((r for o in bpy.context.scene.objects for r in o.get(CHAVE_MAPA,{}).values()
                       if r['nome']==nome),None)
        mapa[str(indice)]=dict(nome=nome,uid=anterior['uid'] if anterior else uuid.uuid4().hex,
                              cor=list(anterior['cor']) if anterior else list(_cor_padrao(nome)))
        obj[CHAVE_MAPA]=mapa
    return indice,mapa.get(str(indice))


def definir(context,obj,nome):
    if not _paredes.alvenaria_definida(obj) or obj.mode!='EDIT':
        raise ValueError('Selecione faces da Alvenaria no modo de edicao')
    nome=_orcamento._limpar_nome_comodo(nome)
    if not nome: raise ValueError('Informe o nome do ambiente')
    acompanhar_faces(context)
    bm=bmesh.from_edit_mesh(obj.data)
    if not any(f.select for f in bm.faces): raise ValueError('Selecione as faces do ambiente')
    if obj.data.users>1:
        bm=None
        bpy.ops.object.mode_set(mode='OBJECT');obj.data=obj.data.copy();bpy.ops.object.mode_set(mode='EDIT')
        bm=bmesh.from_edit_mesh(obj.data)
    indice,_=registro(obj,nome,criar=True)
    camada=bm.faces.layers.int.get(ATR_FACE)
    if camada is None:
        camada=bm.faces.layers.int.new(ATR_FACE)
        # Criar CustomData realoca as faces nativas, sem criar novas superficies.
        _faces_nativas[0].pop(obj.data.name,None)
        acompanhar_faces(context)
    for f in bm.faces:
        if f.select: f[camada]=indice
    bmesh.update_edit_mesh(obj.data,loop_triangles=False,destructive=False)
    _sujo[0]=True;_paredes._conferidos.clear()
    atualizar(context);_paredes._redesenhar()


class OBJECT_OT_definir_ambiente(Operator):
    bl_idname='object.cabinet_definir_ambiente'
    bl_label='Definir ambiente nas faces'
    bl_options={'REGISTER','UNDO'}
    nome:StringProperty(options={'SKIP_SAVE'})

    @classmethod
    def poll(cls,context):
        return context.mode=='EDIT_MESH' and _paredes.alvenaria_definida(context.edit_object)

    def execute(self,context):
        try: definir(context,context.edit_object,self.nome or context.scene.get(CHAVE_NOME,'Cozinha'))
        except ValueError as erro:
            self.report({'WARNING'},str(erro));return {'CANCELLED'}
        return {'FINISHED'}


def retomar_parede(context):
    retorno=_retorno[0]
    if retorno is None or retorno['cena']!=context.scene.name:return 'A parede anterior nao esta disponivel'
    obj=context.view_layer.objects.get(retorno['objeto'])
    _retorno[0]=None
    if obj is None:return 'A parede anterior nao esta disponivel'
    if context.mode=='EDIT_MESH':bpy.ops.object.mode_set(mode='OBJECT')
    return _paredes_edicao.iniciar(context,obj,
        face=(Vector(retorno['ponto']),Vector(retorno['normal']),retorno['regiao']),
        recortar=retorno['recortar'])


class OBJECT_OT_editar_ambientes(Operator):
    bl_idname='object.cabinet_editar_ambientes'
    bl_label='Editar categorias da Alvenaria'

    @classmethod
    def poll(cls,context):
        return (_paredes_edicao.ativa(context) or _paredes.alvenaria_definida(context.object)
                or bool(_retorno[0] and _retorno[0]['cena']==context.scene.name))

    def invoke(self,context,event):
        resultado=self.execute(context)
        if resultado=={'FINISHED'} and context.mode=='EDIT_MESH':
            try:self.token=preparar_selecao(context,context.edit_object)
            except ValueError as erro:
                self.report({'WARNING'},str(erro));return {'CANCELLED'}
            context.window_manager.modal_handler_add(self)
            return {'RUNNING_MODAL'}
        return resultado

    def modal(self,context,event):
        try:return evento_selecao(context,event,self.token)
        except Exception:
            encerrar_selecao();raise

    def cancel(self,context):
        if _edicao_faces[0] and id(_edicao_faces[0])==self.token:encerrar_selecao()

    def execute(self,context):
        s=_paredes_edicao._sessao[0]
        if s is not None:
            obj=context.view_layer.objects.get(s['parede'])
            if obj is None: return {'CANCELLED'}
            retorno=dict(cena=context.scene.name,objeto=obj.name,ponto=tuple(s['ponto']),
                         normal=tuple(s['normal']),regiao=dict(s['regiao']),recortar=s['recorte_explicito'])
            _paredes_edicao.encerrar()
            for o in context.selected_objects:o.select_set(False)
            obj.select_set(True);context.view_layer.objects.active=obj
            try: bpy.ops.object.mode_set(mode='EDIT')
            except RuntimeError as erro:
                _paredes_edicao.iniciar(context,obj,
                    face=(Vector(retorno['ponto']),Vector(retorno['normal']),retorno['regiao']),
                    recortar=retorno['recortar'])
                self.report({'WARNING'},str(erro));return {'CANCELLED'}
            _retorno[0]=retorno
            return {'FINISHED'}
        retorno=_retorno[0]
        if retorno is None or context.mode=='OBJECT':
            _retorno[0]=None
            if not _paredes.alvenaria_definida(context.object):return {'CANCELLED'}
            if context.mode=='OBJECT':
                for o in context.selected_objects:
                    if o!=context.object:o.select_set(False)
                bpy.ops.object.mode_set(mode='EDIT')
            return {'FINISHED'}
        erro=retomar_parede(context)
        if erro:
            self.report({'WARNING'},erro);return {'CANCELLED'}
        return {'FINISHED'}


class OBJECT_OT_cor_ambiente(Operator):
    bl_idname='object.cabinet_cor_ambiente'
    bl_label='Cor do ambiente'
    bl_options={'REGISTER','UNDO'}
    nome:StringProperty(options={'SKIP_SAVE'})
    objeto:StringProperty(options={'SKIP_SAVE'})
    cor:FloatVectorProperty(name='Cor',subtype='COLOR',size=3,min=0,max=1,options={'SKIP_SAVE'})

    def invoke(self,context,event):
        obj=context.edit_object
        if not _paredes.alvenaria_definida(obj): return {'CANCELLED'}
        self.objeto=obj.name
        _,r=registro(obj,self.nome)
        self.cor=r['cor'] if r else _cor_padrao(self.nome)
        if bpy.app.background: return {'CANCELLED'}
        return context.window_manager.invoke_props_dialog(self,width=250)

    def draw(self,context):
        self.layout.label(text=self.nome)
        self.layout.prop(self,'cor',text='')

    def execute(self,context):
        obj=bpy.data.objects.get(self.objeto)
        if not _paredes.alvenaria_definida(obj): return {'CANCELLED'}
        _i,r=registro(obj,self.nome,criar=True)
        for alvo in context.scene.objects:
            mapa=_mapa(alvo);mudou=False
            for v in mapa.values():
                if v['uid']==r['uid']: v['cor']=list(self.cor);mudou=True
            if mudou: alvo[CHAVE_MAPA]=mapa
        _sujo[0]=True;_paredes._redesenhar()
        return {'FINISHED'}


def atribuir(context,conj,parede=None,ponto=None,normal=None):
    parede=parede or _paredes.parede_do_modulo(conj)
    if parede is None or not parede.get(CHAVE_MAPA): return
    dep=context.evaluated_depsgraph_get()
    if ponto is None: ponto,normal=_paredes.plano_do_modulo(conj,parede)
    normal=Vector(normal);ponto=Vector(ponto);inv=parede.matrix_world.inverted_safe()
    ok,_p,n,face=parede.ray_cast(inv@(ponto+normal*.001),
        (inv.to_3x3()@(-normal)).normalized(),depsgraph=dep)
    if not ok: return
    n=(parede.matrix_world.to_3x3().inverted_safe().transposed()@n).normalized()
    if n.dot(normal)<_paredes.COPLANAR_MIN: return
    atributo=parede.evaluated_get(dep).data.attributes.get(ATR_FACE)
    if atributo is None or face>=len(atributo.data): return
    r=parede[CHAVE_MAPA].get(str(atributo.data[face].value))
    if r is None: return
    conj[_paredes.CHAVE_PAREDE_FACE]=face
    destino=next((c for c in bpy.data.collections if c.get('cabinet_ambiente_uid')==r['uid']),None)
    if destino is not None and _orcamento._comodo_do_modulo(conj)==destino: return
    _orcamento.definir_comodo(context.scene,[conj],_orcamento._nome_comodo(destino) if destino else r['nome'])
    destino=_orcamento._comodo_do_modulo(conj)
    if destino is not None: destino['cabinet_ambiente_uid']=r['uid']


def widgets(context,itens,obj,x,y,w):
    nome=context.scene.get(CHAVE_NOME,'Cozinha')
    if _edicao_faces[0] and _edicao_faces[0]['parede_2d'] and _paredes_edicao._aviso[0]:
        y-=24;itens.append((x,y,w,22,_paredes_edicao._aviso[0],None))
    y-=30
    escolha_2d=bool(_edicao_faces[0] and _edicao_faces[0]['parede_2d'])
    rotulo=('Cancelar selecao 2D' if escolha_2d else
            'Voltar a edicao da parede' if _retorno[0] else 'Sair da edicao de categorias')
    itens.append((x,y,w,28,rotulo,
                  ('operador','object.cabinet_editar_ambientes' if _retorno[0] else 'object.editmode_toggle')))
    if escolha_2d:return y-12
    y-=32
    itens.append((x,y,w,23,'Categorias',None));y-=29
    for n in _orcamento._comodos_da_lista(context.scene):
        i,r=registro(obj,n);cor=r['cor'] if r else _cor_padrao(n)
        itens.append((x,y,24,24,'',('escolha','ambiente_cor',n,False,True,ALVO,tuple(cor))))
        itens.append((x+31,y,w-31,24,n,('escolha','ambiente_nome',n,n==nome,True,ALVO)))
        y-=28
    return y-12


def invalidar(cena,depsgraph):
    if _eventos._desfazendo[0]: return
    acompanhar_faces(verificar=any(u.is_updated_geometry for u in depsgraph.updates)
                     and not _eventos._transformando())
    if _retorno[0] and _retorno[0]['cena']!=cena.name:_retorno[0]=None
    malhas={v['malha'] for v in _cache[0].values()}
    for u in depsgraph.updates:
        if not u.is_updated_geometry: continue
        s=_edicao_faces[0]
        if s and ((isinstance(u.id,bpy.types.Object) and u.id.name==s['objeto'])
                  or (isinstance(u.id,bpy.types.Mesh) and bpy.context.edit_object is not None
                      and u.id.name==bpy.context.edit_object.data.name)):s['sujo']=True
        if ((isinstance(u.id,bpy.types.Object) and u.id.name in _cache[0])
                or (isinstance(u.id,bpy.types.Mesh) and u.id.name in malhas)):
            _sujo[0]=True
            return


def atualizar(context=None):
    if _eventos._desfazendo[0]:return
    context=context or bpy.context
    if bpy.context.mode!='EDIT_MESH':_faces_nativas[0]={}
    if not _sujo[0] or _eventos._desfazendo[0]: return
    acompanhar_faces(verificar=False);cache={}
    for obj in context.scene.objects:
        if not _paredes.alvenaria_definida(obj) or not obj.get(CHAVE_MAPA): continue
        bm=bmesh.from_edit_mesh(obj.data).copy() if obj.mode=='EDIT' else bmesh.new()
        try:
            if obj.mode!='EDIT': bm.from_object(obj,context.evaluated_depsgraph_get())
            camada=bm.faces.layers.int.get(ATR_FACE)
            if camada is None: continue
            # Dissolve so' no cache: faces coplanares do mesmo ambiente viram uma legenda.
            arestas=[e for e in bm.edges if len(e.link_faces)==2
                     and e.link_faces[0][camada]==e.link_faces[1][camada]]
            bmesh.ops.dissolve_limit(bm,angle_limit=.001,verts=[],edges=arestas)
            bm.faces.index_update();grupos={};faces={}
            for tri in bm.calc_loop_triangles():
                f=tri[0].face;i=f[camada]
                if str(i) not in obj[CHAVE_MAPA]: continue
                ps=[tuple(l.vert.co) for l in tri]
                grupos.setdefault(i,[]).extend(ps)
                faces.setdefault(f.index,dict(indice=i,centro=tuple(f.calc_center_median()),normal=tuple(f.normal),triangulos=[]))['triangulos'].extend(ps)
            cache[obj.name]=dict(malha=obj.data.name,grupos=[(i,np.array(ps,dtype=np.float32)) for i,ps in grupos.items()],faces=list(faces.values()))
        finally: bm.free()
    _cache[0]=cache;_sujo[0]=False


def rotulo_cabe(triangulos,largura,altura):
    """O retangulo inteiro deve ficar dentro da face, inclusive em contorno concavo."""
    area=0
    for k in range(0,len(triangulos),3):
        ps=[Vector((p[0],p[1],0)) for p in triangulos[k:k+3]]
        for eixo,limite,sinal in ((0,-largura/2,1),(0,largura/2,-1),(1,-altura/2,1),(1,altura/2,-1)):
            ps=_paredes_edicao._recortar_poligono(ps,eixo,limite,sinal)
            if not ps: break
        if len(ps)>=3: area+=abs(sum(a.x*b.y-b.x*a.y for a,b in zip(ps,ps[1:]+ps[:1])))/2
    return area>=largura*altura*(1-1e-5)


def _rotulo(context,obj,f,nome):
    centro=obj.matrix_world@Vector(f['centro'])
    n=(obj.matrix_world.to_3x3().inverted_safe().transposed()@Vector(f['normal'])).normalized()
    if _paredes.tipo_superficie(n)!='PAREDE': return
    u=Vector((0,0,1)).cross(n).normalized();v=n.cross(u)
    px=_paredes._px_por_metro(context.region,context.region_data,centro,u)
    py=_paredes._px_por_metro(context.region,context.region_data,centro,v)
    if not px or not py: return
    tamanho=14*context.preferences.system.ui_scale;blf.size(0,tamanho)
    l,a=blf.dimensions(0,nome)
    ps=[obj.matrix_world@Vector(p)-centro for p in f['triangulos']]
    if not rotulo_cabe([(p.dot(u),p.dot(v)) for p in ps],(l+8)/px,(a+8)/py): return
    matriz=Matrix((u,v,n)).transposed().to_4x4();matriz.translation=centro+n*.002
    with gpu.matrix.push_pop():
        gpu.matrix.multiply_matrix(matriz);gpu.matrix.scale((1/px,1/py,1))
        blf.position(0,-l/2,-a/2,0);blf.color(0,1,1,1,1);blf.draw(0,nome)


def desenhar():
    context=bpy.context
    if context.mode!='EDIT_MESH' or _eventos._desfazendo[0] or _eventos._transformando(): return
    obj=context.edit_object
    if obj is None or obj.name not in _cache[0]: return
    anterior=(gpu.state.blend_get(),gpu.state.depth_test_get(),gpu.state.depth_mask_get())
    try:
        gpu.state.blend_set('ALPHA');gpu.state.depth_test_set('LESS_EQUAL');gpu.state.depth_mask_set(False)
        shader=gpu.shader.from_builtin('UNIFORM_COLOR');mapa=obj.get(CHAVE_MAPA,{})
        with gpu.matrix.push_pop_projection(),gpu.matrix.push_pop():
            # A cor coplanar precisa de prioridade no depth, sem mover a malha.
            projecao=gpu.matrix.get_projection_matrix()
            projecao[2]=projecao[2]-projecao[3]*1e-6
            gpu.matrix.load_projection_matrix(projecao)
            gpu.matrix.multiply_matrix(obj.matrix_world)
            for i,ps in _cache[0][obj.name]['grupos']:
                if str(i) not in mapa: continue
                shader.bind();shader.uniform_float('color',(*mapa[str(i)]['cor'],.5))
                batch_for_shader(shader,'TRIS',{'pos':ps}).draw(shader)
        for f in _cache[0][obj.name]['faces']:
            if str(f['indice']) in mapa: _rotulo(context,obj,f,mapa[str(f['indice'])]['nome'])
    finally:
        gpu.state.blend_set(anterior[0]);gpu.state.depth_test_set(anterior[1]);gpu.state.depth_mask_set(anterior[2])


def esquecer():
    _faces_nativas[0]={}
    encerrar_selecao()
    # Restaurar a selecao pode notificar novamente o depsgraph.
    _faces_nativas[0]={}
    _cache[0]={};_sujo[0]=True;_retorno[0]=None
