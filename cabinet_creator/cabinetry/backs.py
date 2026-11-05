"""Fundos criados pelo vao e limite de profundidade dos sistemas internos."""
import math
import bpy
from mathutils import Matrix, Vector
from bpy.types import Operator
from .. import gavetas as _gavetas

_chapas = _modulos = _prateleiras = _eventos = _gaveta = _opcoes = None
TIPOS = (('CANAL', 'Em canal'), ('PREGADO', 'Sobreposto (pregado)'), ('APOIADO', 'Interno rente'))
PADRAO = dict(tipo='CANAL', espessura_mm=6.0, recuo_mm=15.0, entrada_mm=7.0)
VINCULO = 'fundo_vinculo_uid'
FOLGA = 'fundo_vinculo_folga_mm'
IGNORADOS = 'fundos_desassociados'
ALVO_MENU = '__FUNDOS__'
_assistente_fundo = [None]
_digitais = [{}]


def parametros(fundo=None, context=None):
    alvo = fundo if fundo is not None else (context or bpy.context).scene
    return {k: alvo.get('fundo_' + k, v) for k, v in PADRAO.items()}


def validar(p):
    p = dict(p)
    if p['tipo'] not in dict(TIPOS):
        raise ValueError('Tipo de fundo invalido')
    for k in ('espessura_mm', 'recuo_mm', 'entrada_mm'):
        if not math.isfinite(float(p[k])) or float(p[k]) < (0.1 if k == 'espessura_mm' else 0):
            raise ValueError('Medidas do fundo invalidas')
    if p['tipo'] == 'CANAL' and not any(abs(p['espessura_mm'] - e) < .001 for e in (6, 9)):
        if p['espessura_mm'] >= 12:
            p['tipo'] = 'APOIADO'
        else:
            raise ValueError('Fundo em canal: use espessura comercial de 6 ou 9 mm')
    return p


def _uid(obj):
    return _chapas._garantir_uid(obj)


def _pose(obj):
    return tuple(round(v, 7) for linha in obj.matrix_world for v in linha)


def _caixa(obj, inversa):
    pontos = [inversa @ (obj.matrix_world @ Vector(v)) * 1000 for v in obj.bound_box]
    return [min(v[k] for v in pontos) for k in range(3)], [max(v[k] for v in pontos) for k in range(3)]


def _recorte(l, a, p, e):
    entra = p['entrada_mm'] if p['tipo'] == 'CANAL' else e if p['tipo'] == 'PREGADO' else 0
    y = p['recuo_mm'] if p['tipo'] == 'CANAL' else -p['espessura_mm'] if p['tipo'] == 'PREGADO' else 0
    return (-entra, l + entra, y, y + p['espessura_mm'], -entra, a + entra)


def _aplicar(fundo, matriz, l, a, p, e):
    x0, x1, y0, y1, z0, z1 = _recorte(l, a, p, e)
    if min(l, a) <= 1:
        raise ValueError('O vao do fundo deve ter largura e altura positivas')
    # A chapa conserva X/L, Y/A e Z/E; a normal aponta para fora do movel.
    rot = Matrix((matriz.to_3x3().col[0], matriz.to_3x3().col[2], -matriz.to_3x3().col[1])).transposed()
    pose = rot.to_4x4()
    pose.translation = matriz @ (Vector(((x0+x1)/2, (y0+y1)/2, (z0+z1)/2))/1000)
    medidas = (x1-x0, z1-z0, p['espessura_mm'])
    _chapas._ocupado[0] = True
    try:
        fundo.chapa_largura_mm, fundo.chapa_comprimento_mm, fundo.chapa_espessura_mm = medidas
    finally:
        _chapas._ocupado[0] = False
    _chapas.gerar_malha_chapa(fundo)
    fundo.matrix_world = pose
    bpy.context.view_layer.update()
    fundo['fundo_pose_gerada'] = list(_pose(fundo))


def criar(context, conj, pontos, p=None, nomes=('', '')):
    p = validar(dict(PADRAO, **(p or {})))
    if _chapas.MARCA_CONJUNTO not in conj or _eventos._desfazendo[0] or context.mode != 'OBJECT':
        raise ValueError('Selecione um modulo em Object Mode')
    if any(nome and _modulos._conj_de(bpy.data.objects.get(nome))!=conj for nome in nomes):
        raise ValueError('Os dois cantos devem pertencer ao mesmo modulo')
    ref = _gavetas.referencia_do_vao(conj, *pontos)
    pontos = _gavetas.pontos_internos_do_vao(conj, pontos, nomes, ref)
    mundo = conj.matrix_world @ ref.to_4x4()
    locais = [mundo.inverted() @ Vector(pt) * 1000 for pt in pontos]
    lo = Vector(tuple(min(pt[k] for pt in locais) for k in range(3)))
    hi = Vector(tuple(max(pt[k] for pt in locais) for k in range(3)))
    l, a = hi.x-lo.x, hi.z-lo.z
    if min(l, a) <= 1 or hi.y-lo.y > 5:
        raise ValueError('Marque dois cantos opostos no mesmo plano vertical das costas')
    if p['tipo']=='CANAL' and not 0<p['entrada_mm']<conj.conj_espessura_mm:
        raise ValueError('O encaixe deve entrar no apoio sem atravessar sua espessura')
    _minimo, maximo = _gavetas.limites_na_referencia(conj,ref)
    if p['tipo']=='CANAL' and lo.y+p['recuo_mm']+p['espessura_mm']>=maximo.y:
        raise ValueError('O recuo do fundo ultrapassa a profundidade do modulo')
    fundo = _chapas.nova_chapa('Fundo', l, a, p['espessura_mm'], (0,0,0), (0,0,0), context)
    fundo[_chapas.MARCA_FUNDO] = 1
    fundo.parent = conj
    fundo.matrix_parent_inverse = Matrix.Identity(4)
    _modulos._mover_para_colecao(fundo, _modulos._garantir_colecao_modulo(context.scene, conj))
    for k, valor in p.items():
        fundo['fundo_' + k] = valor
    try:
        _aplicar(fundo, mundo @ Matrix.Translation(lo/1000), l, a, p, conj.conj_espessura_mm)
        guardar_formato(fundo)
        atualizar_canal(fundo)
        atualizar_internos(conj)
        fundo['fundo_ultima_valida']=list(_pose(fundo))
    except Exception:
        remover_canal(fundo)
        _gavetas._remover(fundo)
        raise
    return fundo


def guardar_formato(fundo):
    conj = _modulos._conj_de(fundo)
    rot = (conj.matrix_world.inverted() @ fundo.matrix_world).to_3x3().normalized()
    ref = Matrix((rot.col[0], -rot.col[2], rot.col[1])).transposed()
    lo, hi = _gavetas.limites_na_referencia(conj, ref)
    centro = ref.transposed() @ (conj.matrix_world.inverted() @ fundo.matrix_world.translation) * 1000
    p = parametros(fundo)
    if p['tipo']=='CANAL' and tuple(fundo.get('fundo_pose_gerada',()))!=_pose(fundo):
        p['recuo_mm']=max(0.0,centro.y-lo.y-fundo.chapa_espessura_mm/2)
        fundo['fundo_recuo_mm']=p['recuo_mm']
    c = _recorte(0, 0, p, conj.conj_espessura_mm)
    entra = -c[0]
    origem = centro - Vector((fundo.chapa_largura_mm/2-entra, (c[2]+c[3])/2, fundo.chapa_comprimento_mm/2-entra))
    l, a = fundo.chapa_largura_mm-2*entra, fundo.chapa_comprimento_mm-2*entra
    fundo['fundo_referencia'] = [v for linha in ref for v in linha]
    fundo['fundo_limites_base'] = list(lo) + list(hi)
    fundo['fundo_apoio_base_mm'] = float(conj.conj_espessura_mm)
    fundo['fundo_margens_criacao'] = [origem.x-lo.x, hi.x-origem.x-l, origem.z-lo.z, hi.z-origem.z-a, origem.y-lo.y]
    fundo['fundo_pose_gerada'] = list(_pose(fundo))


def ajustar_ao_modulo(fundo, forcar=False):
    conj = _modulos._conj_de(fundo)
    if conj is None or fundo.data.is_editmode or 'fundo_referencia' not in fundo:
        return
    ref = Matrix([fundo['fundo_referencia'][i:i+3] for i in (0,3,6)])
    lo, hi = _gavetas.limites_na_referencia(conj, ref)
    base = list(lo)+list(hi)
    apoio=float(conj.conj_espessura_mm)
    apoio_base=float(fundo.get('fundo_apoio_base_mm',apoio))
    if not forcar and abs(apoio-apoio_base)<.001 and all(abs(a-b)<.001 for a,b in zip(base, fundo['fundo_limites_base'])):
        return
    margens=list(fundo['fundo_margens_criacao'])
    for k in range(4):
        if abs(margens[k]-apoio_base)<.1:
            margens[k]+=apoio-apoio_base
    esq, dir_, baixo, cima, tras = margens
    origem = Vector((lo.x+esq, lo.y+tras, lo.z+baixo))
    p=parametros(fundo)
    if p['tipo']=='CANAL' and (not 0<p['entrada_mm']<apoio or origem.y+p['recuo_mm']+p['espessura_mm']>=hi.y):
        raise ValueError('Canal ou recuo do fundo ultrapassa os apoios do modulo')
    _aplicar(fundo, conj.matrix_world @ ref.to_4x4() @ Matrix.Translation(origem/1000),
             hi.x-lo.x-esq-dir_, hi.z-lo.z-baixo-cima, p, conj.conj_espessura_mm)
    fundo['fundo_limites_base'] = base
    fundo['fundo_apoio_base_mm'] = apoio
    fundo['fundo_margens_criacao'] = margens
    atualizar_canal(fundo)


def remover_canal(fundo):
    uid = _uid(fundo)
    conj = _modulos._conj_de(fundo)
    for obj in list(conj.children_recursive) if conj else []:
        for mod in list(obj.modifiers):
            if mod.type == 'BOOLEAN' and mod.object is not None and mod.object.get('fundo_canal_uid') == uid:
                obj.modifiers.remove(mod)
    for obj in list(conj.children_recursive) if conj else []:
        if obj.get('fundo_canal_uid') == uid:
            _gavetas._remover(obj)


def atualizar_canal(fundo):
    conj = _modulos._conj_de(fundo)
    p = parametros(fundo)
    uid = _uid(fundo)
    cortador = next((o for o in fundo.children if o.get('fundo_canal_uid') == uid), None)
    if p['tipo'] != 'CANAL':
        remover_canal(fundo)
        return
    if cortador is None:
        malha = bpy.data.meshes.new('Canal do fundo')
        cortador = bpy.data.objects.new('Canal do fundo', malha)
        _modulos._garantir_colecao_modulo(bpy.context.scene, conj).objects.link(cortador)
        cortador['fundo_canal_uid'] = uid
        cortador.parent = fundo
        cortador.hide_render = True
        cortador.hide_select = True
        cortador.hide_set(True)
    # Boolean nativo nao destrutivo: a malha modelada de apoio nunca e' substituida.
    import bmesh
    bm = bmesh.new()
    try:
        bm.from_mesh(fundo.data)
        lo=Vector(tuple(min(v.co[k] for v in bm.verts) for k in range(3)))
        hi=Vector(tuple(max(v.co[k] for v in bm.verts) for k in range(3)))
        meio=(lo+hi)/2
        for v in bm.verts:
            for k in range(3):
                v.co[k]+=.0002 if v.co[k]>meio[k] else -.0002
        bm.to_mesh(cortador.data)
    finally:
        bm.free()
    cortador.matrix_basis = Matrix.Identity(4)
    bpy.context.view_layer.update()
    inversa = fundo.matrix_world.inverted()
    a,b = _caixa(cortador,inversa)
    for obj in _modulos._estruturais(_modulos._chapas_do_conjunto(conj)):
        if obj.data.is_editmode:
            continue
        for antigo in list(obj.modifiers):
            if antigo.type=='BOOLEAN' and antigo.object is not None and antigo.object.get('fundo_canal_uid') and _modulos._conj_de(antigo.object)!=conj:
                obj.modifiers.remove(antigo)
        c,d = _caixa(obj,inversa)
        cruza = all(min(b[k],d[k])-max(a[k],c[k])>.01 for k in range(3))
        mod = next((m for m in obj.modifiers if m.type=='BOOLEAN' and m.object==cortador),None)
        if cruza and mod is None:
            mod = obj.modifiers.new('Canal do fundo','BOOLEAN')
            mod.operation='DIFFERENCE'
            mod.solver='EXACT'
            mod.object=cortador
        elif not cruza and mod is not None:
            obj.modifiers.remove(mod)


def _limite(grupo, fundo):
    if _modulos._conj_de(grupo) != _modulos._conj_de(fundo):
        return None
    direcao = grupo.matrix_world.to_3x3().col[1].normalized()
    normal = fundo.matrix_world.to_3x3().col[2].normalized()
    if abs(direcao.dot(normal)) < .995:
        return None
    inv = grupo.matrix_world.inverted()
    lo, hi = _caixa(fundo, inv)
    sistema = _prateleiras if _prateleiras.MARCA_GRUPO in grupo else _gavetas
    l,a,_p = sistema.medidas(grupo)
    if min(hi[0],l)-max(lo[0],0)<.1 or min(hi[2],a)-max(lo[2],0)<.1 or hi[1]<=0:
        return None
    return lo[1]


def associar(grupo, fundo, ponto=None):
    limite = _limite(grupo,fundo)
    if limite is None:
        return False
    if ponto is not None:
        y = (grupo.matrix_world.inverted() @ Vector(ponto)).y*1000
        if abs(y-limite)>5:
            return False
    grupo[VINCULO] = _uid(fundo)
    grupo[FOLGA] = 0.0
    return True


def detectar_no_ponto(grupo, ponto):
    conj = _modulos._conj_de(grupo)
    for fundo in _modulos.fundos_do_modulo(conj) if conj else []:
        if associar(grupo,fundo,ponto):
            return fundo
    return None


def atualizar_internos(conj):
    fundos = _modulos.fundos_do_modulo(conj)
    planos=[]
    vinculos=[]
    for sistema in (_gavetas,_prateleiras):
        for grupo in sistema.grupos_do_modulo(conj):
            p = sistema.parametros(grupo)
            atual = float(p['profundidade_mm'])
            por_uid = {_uid(f):f for f in fundos}
            fundo = por_uid.get(grupo.get(VINCULO,''))
            if fundo is None and grupo.get(VINCULO):
                vinculos.append((grupo,None))
            if fundo is None:
                candidatos = [(d,f) for f in fundos if 'fundo_tipo' in f and _uid(f) not in grupo.get(IGNORADOS,())
                              if (d:=_limite(grupo,f)) is not None and d<=atual+5]
                if not candidatos:
                    continue
                fundo = min(candidatos,key=lambda v:v[0])[1]
            else:
                candidatos=[(d,f) for f in fundos if f==fundo or ('fundo_tipo' in f and _uid(f) not in grupo.get(IGNORADOS,()))
                            if (d:=_limite(grupo,f)) is not None]
                if candidatos:
                    proximo=min(candidatos,key=lambda v:v[0])[1]
                    if proximo!=fundo:
                        fundo=proximo
            limite = _limite(grupo,fundo)
            if limite is None:
                continue
            vinculos.append((grupo,fundo))
            limite -= float(grupo.get(FOLGA,0))
            novo = dict(p,profundidade_mm=limite)
            if isinstance(p.get('individuais'),dict):
                novo['individuais']={k:dict(v,profundidade_mm=min(float(v['profundidade_mm']),limite))
                                     if 'profundidade_mm' in v else dict(v)
                                     for k,v in p['individuais'].items()}
            elif p.get('individuais'):
                novo['individuais']=[dict(v,profundidade_mm=min(float(v['profundidade_mm']),limite))
                                     if 'profundidade_mm' in v else dict(v) for v in p['individuais']]
            if abs(limite-atual)<.01 and novo.get('individuais')==p.get('individuais'):
                continue
            # Valida o dominio antes de gravar/remontar; vao insuficiente nao apaga internos.
            try:
                l,a,_ = sistema.medidas(grupo)
                sistema.calcular(l,a,novo)
            except ValueError as erro:
                grupo['fundo_erro'] = str(erro)
                raise ValueError('O fundo nao deixa espaco para os internos: '+str(erro)) from erro
            if 'fundo_erro' in grupo:
                del grupo['fundo_erro']
            planos.append((sistema,grupo,novo))
    for grupo,fundo in vinculos:
        if fundo is None:
            if VINCULO in grupo:
                del grupo[VINCULO]
        elif grupo.get(VINCULO)!=_uid(fundo):
            grupo[VINCULO]=_uid(fundo)
            grupo[FOLGA]=0.0
    for sistema,grupo,novo in planos:
        grupo[sistema.CHAVE_PARAMETROS] = novo
        sistema.montar(grupo)


def verificar():
    if _eventos._desfazendo[0] or _chapas._ocupado[0] or bpy.context.mode!='OBJECT' or _eventos._ha_modal_ativo():
        return
    fundos = [o for o in bpy.context.scene.objects if _chapas.MARCA_FUNDO in o and o.type=='MESH']
    uids={o.get('chapa_uid') for o in fundos}
    orfaos=[o for o in bpy.context.scene.objects if o.get('fundo_canal_uid') and o['fundo_canal_uid'] not in uids]
    if orfaos:
        for obj in bpy.context.scene.objects:
            for mod in list(obj.modifiers):
                if mod.type=='BOOLEAN' and mod.object in orfaos:
                    obj.modifiers.remove(mod)
        for obj in orfaos:
            _gavetas._remover(obj)
    vivos = {o.name for o in fundos}
    for nome in set(_digitais[0])-vivos:
        del _digitais[0][nome]
    modulos = {}
    for fundo in fundos:
        if fundo.data.is_editmode:
            continue
        if not fundo.data.vertices:
            remover_canal(fundo)
            continue
        conj = _modulos._conj_de(fundo)
        if conj is None:
            continue
        internos = [*_gavetas.grupos_do_modulo(conj), *_prateleiras.grupos_do_modulo(conj)]
        if 'fundo_tipo' not in fundo and not any(g.get(VINCULO) and g[VINCULO]==fundo.get('chapa_uid') for g in internos):
            continue
        edicao=fundo.get('chapa_edicao')
        digital = (_pose(fundo),tuple(fundo.dimensions),edicao.get('ultimo') if edicao else None,tuple((g.name,_pose(g),repr(g.get(VINCULO)),repr(g.get(IGNORADOS)),
                    repr((_prateleiras if _prateleiras.MARCA_GRUPO in g else _gavetas).parametros(g))) for g in internos))
        if _digitais[0].get(fundo.name)==digital:
            continue
        if 'fundo_tipo' in fundo:
            if tuple(fundo.get('fundo_pose_gerada',())) != _pose(fundo):
                guardar_formato(fundo)
            atualizar_canal(fundo)
        _digitais[0][fundo.name]=digital
        modulos[conj.name]=conj
    for conj in modulos.values():
        try:
            atualizar_internos(conj)
            for fundo in _modulos.fundos_do_modulo(conj):
                fundo['fundo_ultima_valida']=list(_pose(fundo))
                if 'fundo_erro' in fundo:
                    del fundo['fundo_erro']
        except ValueError as erro:
            for fundo in _modulos.fundos_do_modulo(conj):
                ultima=fundo.get('fundo_ultima_valida')
                if ultima:
                    fundo.matrix_world=Matrix([ultima[i:i+4] for i in (0,4,8,12)])
                    bpy.context.view_layer.update()
                    guardar_formato(fundo)
                    atualizar_canal(fundo)
                fundo['fundo_erro']=str(erro)


def editar(context, fundo, nome, valor):
    if context.mode!='OBJECT' or _eventos._desfazendo[0]:
        raise ValueError('Finalize a edicao nativa antes de editar o fundo')
    alvo = fundo if fundo is not None and _chapas.MARCA_FUNDO in fundo else context.scene
    anterior=parametros(fundo if alvo!=context.scene else None,context)
    p=dict(anterior, **{nome:valor})
    if nome=='tipo' and valor=='CANAL' and p['espessura_mm'] not in (6,9):
        p['espessura_mm']=6.0
    p=validar(p)
    for k,v in p.items():
        alvo['fundo_'+k]=v
    if alvo!=context.scene:
        try:
            ajustar_ao_modulo(alvo,forcar=True)
            atualizar_internos(_modulos._conj_de(alvo))
        except ValueError:
            for k,v in anterior.items():
                alvo['fundo_'+k]=v
            ajustar_ao_modulo(alvo,forcar=True)
            raise


def selecionar(context, fundo, somar=False):
    ligado = not fundo.select_get() if somar else True
    if not somar:
        for obj in context.selected_objects:
            obj.select_set(False)
    fundo.select_set(ligado)
    if ligado:
        context.view_layer.objects.active=fundo
    context.scene.cabinet_aba='FUNDOS'


def widgets_vinculo(context, itens, x, y, w):
    if grupos_vinculados(context):
        itens.append((x,y,w,28,'Desassociar fundo',('operador','object.cabinet_desassociar_fundo')))
        y-=40
    return y


def widgets(context, itens, x, y, w):
    assistente = _assistente_fundo[0]
    if assistente is not None:
        itens.append((x,y,w,26,assistente.get('recado',''),None))
        return itens
    obj=context.object
    fundo = obj if obj is not None and _chapas.MARCA_FUNDO in obj else None
    if fundo is not None and 'fundo_tipo' not in fundo:
        itens.append((x,y,w,23,'Fundo existente: modelagem preservada',None))
        return itens
    p=parametros(fundo,context)
    y=_gaveta._titulo_secao(itens,x,y+26,w,'Fundo selecionado' if fundo is not None else 'Novo fundo')
    y=_gaveta._linha_escolha_gaveta(itens,x,y-25,w,'','tipo',TIPOS,p['tipo'],alvo=ALVO_MENU,por_linha=1)+23
    y=_gaveta._linha_escolha_gaveta(itens,x,y-25,w,'','espessura_mm',((6.0,'6 mm'),(9.0,'9 mm'),(15.0,'15 mm')),p['espessura_mm'],alvo=ALVO_MENU)+23
    campos = [('Espessura: %s' % _opcoes._texto_medida(p['espessura_mm']),
               ('medida','fundos','espessura_mm','Espessura',p['espessura_mm']))]
    if p['tipo']=='CANAL':
        campos += [(rotulo+': '+_opcoes._texto_medida(p[nome]),('medida','fundos',nome,rotulo,p[nome]))
                   for nome,rotulo in (('recuo_mm','Recuo'),('entrada_mm','Encaixe'))]
    y=_gaveta._campos_em_linhas(context,itens,x,y,w,campos)
    y=widgets_vinculo(context,itens,x,y-34,w)
    if fundo is not None and fundo.get('fundo_erro'):
        itens.append((x,y-28,w,23,fundo['fundo_erro'],None))
    return itens


def grupos_vinculados(context):
    obj = context.object
    if obj is None:
        return []
    if _chapas.MARCA_FUNDO in obj:
        conj = _modulos._conj_de(obj)
        return [o for o in conj.children_recursive if o.get(VINCULO)==obj.get('chapa_uid','')] if conj else []
    grupo = _gavetas.grupo_de(obj) or _prateleiras.grupo_de(obj)
    return [grupo] if grupo is not None and grupo.get(VINCULO) else []


def copia(context, nome):
    obj=bpy.data.objects.get(nome)
    fundo=obj if obj is not None and _chapas.MARCA_FUNDO in obj else None
    conj=_modulos._conj_de(fundo) if fundo is not None else None
    grupos=[]
    for sistema in (_gavetas,_prateleiras):
        for grupo in sistema.grupos_do_modulo(conj) if conj else []:
            grupos.append((grupo.name,sistema.CHAVE_PARAMETROS,grupo[sistema.CHAVE_PARAMETROS].to_dict()))
    return dict(nome=fundo.name if fundo is not None else '',p=parametros(fundo,context),grupos=grupos)


def restaurar(context, estado):
    fundo=bpy.data.objects.get(estado['nome'])
    alvo=fundo if fundo is not None else context.scene
    for k,v in estado['p'].items():
        alvo['fundo_'+k]=v
    if fundo is not None:
        ajustar_ao_modulo(fundo,forcar=True)
    for nome,chave,p in estado['grupos']:
        grupo=bpy.data.objects.get(nome)
        if grupo is not None:
            grupo[chave]=p
            (_gavetas if chave==_gavetas.CHAVE_PARAMETROS else _prateleiras).montar(grupo)


class OBJECT_OT_desassociar_fundo(Operator):
    """Conserva a profundidade atual e desliga o acompanhamento deste fundo"""
    bl_idname='object.cabinet_desassociar_fundo'
    bl_label='Desassociar fundo'
    bl_options={'REGISTER','UNDO'}

    @classmethod
    def poll(cls,context):
        return context.mode=='OBJECT' and bool(grupos_vinculados(context))

    def execute(self,context):
        for grupo in grupos_vinculados(context):
            grupo[IGNORADOS]=list(set(grupo.get(IGNORADOS,()))|{grupo[VINCULO]})
            del grupo[VINCULO]
        return {'FINISHED'}


class OBJECT_OT_criar_fundo(_gavetas.AssistenteDoVao,Operator):
    """Marca dois cantos opostos das costas pelo snap nativo"""
    bl_idname='object.cabinet_criar_fundo'
    bl_label='Criar Fundo'
    bl_options={'REGISTER','UNDO'}
    _estado=_assistente_fundo
    ABA='FUNDOS'
    ITEM=('fundo','fundos')
    RECADOS=dict(_gavetas.RECADOS, CANTO1='Fundo: marque o primeiro canto das costas',CANTO2='Fundo: marque o canto oposto das costas')

    def _parametros_padrao(self):
        obj=bpy.context.object
        fundo=obj if obj is not None and _chapas.MARCA_FUNDO in obj else None
        return dict(parametros(fundo),quantidade=1,profundidade_mm=0)

    def _comecar_no_modulo(self,conj,ponto):
        self._w['p']['apoio_mm']=conj.conj_espessura_mm

    def _calcular(self,l,a,p):
        if min(l,a)<=1:
            raise ValueError('Marque um vao vertical com largura e altura')
        return {'caixas':[_recorte(l,a,p,p.get('apoio_mm',0))]}

    def _caixas_da_previa(self,dados):
        return dados['caixas']

    def _aceitar_canto(self,context,ponto,nome):
        saida=super()._aceitar_canto(context,ponto,nome)
        return self._criar(context) if self._w.get('etapa')=='QUANTIDADE' else saida

    def _criar_grupo(self,context,conj,margens,p):
        return criar(context,conj,self._w['pontos'],{k:p[k] for k in PADRAO},self._w['nomes'])

    def _selecionar_grupo(self,context,fundo):
        for obj in context.selected_objects:
            obj.select_set(False)
        fundo.select_set(True)
        context.view_layer.objects.active=fundo


def esquecer():
    if _assistente_fundo[0] is not None:
        _assistente_fundo[0]['cancelar']=True
        _gavetas._terminar_snap_criacao()
    _assistente_fundo[0]=None
    _digitais[0].clear()
