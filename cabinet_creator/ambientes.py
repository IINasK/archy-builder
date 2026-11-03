"""Ambientes por faces nativas da Alvenaria; cores so' durante a definicao."""
import bpy, bmesh, colorsys, uuid
import numpy as np
import gpu, blf
from bpy.types import Operator
from bpy.props import StringProperty, FloatVectorProperty
from gpu_extras.batch import batch_for_shader
from mathutils import Vector, Matrix

_paredes = _paredes_edicao = _orcamento = _eventos = _gaveta = None
ATR_FACE = 'cabinet_ambiente'
CHAVE_MAPA = 'cabinet_ambientes'
CHAVE_NOME = 'cabinet_ambiente_nome'
ALVO = '@ambiente_alvenaria'
_sujo = [True]
_cache = [{}]
_handler = [None]
_retorno = [None]


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
    bm=bmesh.from_edit_mesh(obj.data)
    if not any(f.select for f in bm.faces): raise ValueError('Selecione as faces do ambiente')
    if obj.data.users>1:
        bm=None
        bpy.ops.object.mode_set(mode='OBJECT');obj.data=obj.data.copy();bpy.ops.object.mode_set(mode='EDIT')
        bm=bmesh.from_edit_mesh(obj.data)
    indice,_=registro(obj,nome,criar=True)
    camada=bm.faces.layers.int.get(ATR_FACE) or bm.faces.layers.int.new(ATR_FACE)
    for f in bm.faces:
        if f.select: f[camada]=indice
    bmesh.update_edit_mesh(obj.data,loop_triangles=False,destructive=False)
    _sujo[0]=True;_paredes._conferidos.clear()
    atualizar(context);_paredes._redesenhar()


class OBJECT_OT_definir_ambiente(Operator):
    bl_idname='object.cabinet_definir_ambiente'
    bl_label='Definir ambiente nas faces'
    bl_options={'REGISTER','UNDO'}

    @classmethod
    def poll(cls,context):
        return context.mode=='EDIT_MESH' and _paredes.alvenaria_definida(context.edit_object)

    def execute(self,context):
        try: definir(context,context.edit_object,context.scene.get(CHAVE_NOME,'Cozinha'))
        except ValueError as erro:
            self.report({'WARNING'},str(erro));return {'CANCELLED'}
        return {'FINISHED'}


class OBJECT_OT_editar_ambientes(Operator):
    bl_idname='object.cabinet_editar_ambientes'
    bl_label='Editar ambientes da parede'

    @classmethod
    def poll(cls,context):
        return _paredes_edicao.ativa(context) or bool(_retorno[0] and _retorno[0]['cena']==context.scene.name)

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
        if retorno is None or retorno['cena']!=context.scene.name: return {'CANCELLED'}
        obj=context.view_layer.objects.get(retorno['objeto'])
        if obj is None:
            _retorno[0]=None;return {'CANCELLED'}
        if context.mode=='EDIT_MESH':bpy.ops.object.mode_set(mode='OBJECT')
        _retorno[0]=None
        erro=_paredes_edicao.iniciar(context,obj,
            face=(Vector(retorno['ponto']),Vector(retorno['normal']),retorno['regiao']),
            recortar=retorno['recortar'])
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
    metade=(w-6)/2
    y-=30
    itens.append((x,y,metade,28,'Voltar a edicao da parede' if _retorno[0] else 'Sair da edicao de ambientes',
                  ('operador','object.cabinet_editar_ambientes' if _retorno[0] else 'object.editmode_toggle')))
    itens.append((x+metade+6,y,metade,28,'Definir como '+nome,('operador','object.cabinet_definir_ambiente')))
    y-=32
    itens.append((x,y,w,23,'Ambientes',None));y-=29
    for n in _orcamento._comodos_da_lista(context.scene):
        i,r=registro(obj,n);cor=r['cor'] if r else _cor_padrao(n)
        itens.append((x,y,24,24,'',('escolha','ambiente_cor',n,False,True,ALVO,tuple(cor))))
        itens.append((x+31,y,w-31,24,n,('escolha','ambiente_nome',n,n==nome,True,ALVO)))
        y-=28
    return y-12


def invalidar(cena,depsgraph):
    if _eventos._desfazendo[0]: return
    if _retorno[0] and _retorno[0]['cena']!=cena.name:_retorno[0]=None
    malhas={v['malha'] for v in _cache[0].values()}
    for u in depsgraph.updates:
        if not u.is_updated_geometry: continue
        if ((isinstance(u.id,bpy.types.Object) and u.id.name in _cache[0])
                or (isinstance(u.id,bpy.types.Mesh) and u.id.name in malhas)):
            _sujo[0]=True
            return


def atualizar(context=None):
    if not _sujo[0] or _eventos._desfazendo[0]: return
    context=context or bpy.context;cache={}
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
    _cache[0]={};_sujo[0]=True;_retorno[0]=None
