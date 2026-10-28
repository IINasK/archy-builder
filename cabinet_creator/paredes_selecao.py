"""Regioes de parede escolhidas na malha nativa ou delimitadas no plano."""
import math
import bpy
import bmesh
import numpy as np
from mathutils import Vector
from mathutils.geometry import tessellate_polygon, intersect_line_line_2d

_paredes = _paredes_edicao = None
ORIENTACAO_MIN = math.cos(math.radians(1))
MARCA_EXIBICAO = 'cabinet_parede_recorte_2d'
_candidatas = [{}]
_limpeza_pendente = [True]


def triangulos_reais(malha, faces, mundo):
    malha.calc_loop_triangles()
    trios = np.empty(len(malha.loop_triangles)*3,dtype=np.int32)
    donas = np.empty(len(malha.loop_triangles),dtype=np.int32)
    malha.loop_triangles.foreach_get('vertices',trios)
    malha.loop_triangles.foreach_get('polygon_index',donas)
    vertices = np.empty(len(malha.vertices)*3,dtype=np.float64)
    malha.vertices.foreach_get('co',vertices)
    pontos=vertices.reshape(-1,3) @ np.array(mundo.to_3x3()).T + np.array(mundo.translation)
    return pontos[trios.reshape(-1,3)[np.isin(donas,list(faces))]].reshape(-1,3)


def automatica(context,obj,ponto,normal,face):
    if not _paredes_edicao.superficie(obj) or abs(normal.z)>.001:
        raise ValueError('Aponte para uma superficie vertical')
    mundo=obj.matrix_world
    malha=obj.evaluated_get(context.evaluated_depsgraph_get()).data
    chave=(obj.name,malha.as_pointer(),len(malha.vertices),len(malha.polygons),_paredes._assinatura(mundo))
    conhecidas=_candidatas[0].setdefault(chave,[])
    for regiao in conhecidas:
        if face in regiao['faces']:
            return Vector(regiao['plano']),Vector(regiao['normal']),dict(regiao,face=face)
    eixos=_paredes.eixos_da_parede(normal)
    if eixos is None:
        raise ValueError('Aponte para uma superficie vertical')
    regiao=_paredes._calcular_regiao(malha,mundo,ponto,normal,face,eixos[1],
                                    orientacao_min=ORIENTACAO_MIN,conferir_vertices=True)
    if not regiao:
        raise ValueError('Nao foi encontrada uma regiao plana conectada')
    regiao['triangulos']=triangulos_reais(malha,regiao['faces'],mundo)
    regiao['delimitada']=True
    conhecidas.append(regiao)
    if len(_candidatas[0])>8:
        _candidatas[0]={chave:conhecidas}
    return Vector(regiao['plano']),Vector(regiao['normal']),regiao


def dos_vertices(context,obj):
    if context.mode!='EDIT_MESH' or obj is None or obj.type!='MESH':
        raise ValueError('Selecione vertices de uma parede em Edit Mode')
    editados=[o for o in context.objects_in_mode_unique_data if o.type=='MESH']
    if len(editados)!=1:
        raise ValueError('Selecione vertices de uma unica malha')
    bm=bmesh.from_edit_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    bm.faces.index_update()
    vertices={v for v in bm.verts if v.select and not v.hide}
    if len(vertices)<3:
        raise ValueError('Selecione pelo menos tres vertices conectados')
    visitados={next(iter(vertices))}
    fronteira=list(visitados)
    while fronteira:
        v=fronteira.pop()
        for aresta in v.link_edges:
            outro=aresta.other_vert(v)
            if outro in vertices and outro not in visitados:
                visitados.add(outro)
                fronteira.append(outro)
    if visitados!=vertices:
        raise ValueError('Os vertices selecionados devem estar conectados entre si')
    faces=[f for f in bm.faces if not f.hide and all(v in vertices for v in f.verts)]
    if not faces or set(v for f in faces for v in f.verts)!=vertices:
        raise ValueError('A selecao deve delimitar faces, sem vertices soltos')
    rot=obj.matrix_world.to_3x3().inverted_safe().transposed()
    normal=(rot @ max(faces,key=lambda f:f.calc_area()).normal).normalized()
    if abs(normal.z)>.001 or _paredes.eixos_da_parede(normal) is None:
        raise ValueError('A selecao deve formar uma parede vertical')
    ponto=obj.matrix_world @ next(iter(vertices)).co
    if any((rot @ f.normal).normalized().dot(normal)<ORIENTACAO_MIN for f in faces):
        raise ValueError('As faces devem ter a mesma orientacao (tolerancia de 1 grau)')
    if any(abs((obj.matrix_world @ v.co-ponto).dot(normal))>_paredes.TOLERANCIA_PLANO_M for v in vertices):
        raise ValueError('Os vertices devem estar no mesmo plano (tolerancia de 2 mm)')
    ids={f.index for f in faces}
    ligadas={faces[0]}
    pendentes=list(ligadas)
    while pendentes:
        for aresta in pendentes.pop().edges:
            for vizinha in aresta.link_faces:
                if vizinha.index in ids and vizinha not in ligadas:
                    ligadas.add(vizinha)
                    pendentes.append(vizinha)
    if len(ligadas)!=len(faces):
        raise ValueError('As faces selecionadas devem compartilhar arestas')
    trios=[tuple(obj.matrix_world @ l.vert.co) for tri in bm.calc_loop_triangles() if tri[0].face.index in ids for l in tri]
    contorno=[(obj.matrix_world @ e.verts[0].co,obj.matrix_world @ e.verts[1].co)
              for e in bm.edges if sum(f.index in ids for f in e.link_faces)==1]
    return ponto,normal,regiao_dos_triangulos(trios,contorno,ponto,normal,min(ids),ids)


def regiao_dos_triangulos(triangulos,contorno,ponto,normal,face,faces):
    t=np.asarray(triangulos,dtype=np.float64).reshape(-1,3)
    if len(t)<3:
        raise ValueError('A area escolhida nao cobre a parede')
    u=np.array(_paredes.eixos_da_parede(normal)[1])
    return dict(face=int(face),faces=frozenset(faces),plano=tuple(ponto),normal=tuple(normal),
                retangulo=(float((t@u).min()),float((t@u).max()),float(t[:,2].min()),float(t[:,2].max())),
                triangulos=t,contorno=[(Vector(a),Vector(b)) for a,b in contorno],delimitada=True)


def _cruz(a,b):
    return a[...,0]*b[...,1]-a[...,1]*b[...,0]


def _triangulos_do_poligono(pontos):
    p=[Vector(v) for v in pontos]
    if len(p)>1 and (p[0]-p[-1]).length<1e-7:
        p.pop()
    if len(p)<3:
        raise ValueError('Marque pelo menos tres pontas')
    if any((b-a).length<1e-6 for a,b in zip(p,p[1:]+p[:1])):
        raise ValueError('A area tem pontos repetidos')
    for i in range(len(p)):
        for j in range(i+1,len(p)):
            if j in (i,(i+1)%len(p)) or i==(j+1)%len(p):
                continue
            if intersect_line_line_2d(p[i],p[(i+1)%len(p)],p[j],p[(j+1)%len(p)]) is not None:
                raise ValueError('As linhas da area nao podem se cruzar')
    indices=tessellate_polygon([[Vector((v.x,v.y,0)) for v in p]])
    trios=np.array([[tuple(p[int(i)]) for i in tri] for tri in indices],dtype=np.float64).reshape(-1,3,2)
    if not len(trios) or np.sum(np.abs(_cruz(trios[:,1]-trios[:,0],trios[:,2]-trios[:,0])))<1e-8:
        raise ValueError('A area deve ter largura e altura')
    return trios


def _intervalos_segmento(a,b,triangulos):
    """Recorte convexo em lote; a uniao evita costuras das triangulacoes."""
    if not len(triangulos):
        return []
    tris=np.array(triangulos,dtype=np.float64)
    inverter=_cruz(tris[:,1]-tris[:,0],tris[:,2]-tris[:,0])<0
    tris[inverter]=tris[inverter][:,::-1]
    inicio=np.zeros(len(tris));fim=np.ones(len(tris));validos=np.ones(len(tris),dtype=bool)
    for i in range(3):
        p,q=tris[:,i],tris[:,(i+1)%3]
        da=_cruz(q-p,a-p);db=_cruz(q-p,b-p)
        den=db-da
        paralelos=np.abs(den)<1e-12
        validos &= ~(paralelos & (da < -1e-9))
        t=np.divide(-da,den,out=np.zeros_like(den),where=~paralelos)
        inicio=np.where((den>0)&~paralelos,np.maximum(inicio,t),inicio)
        fim=np.where((den<0)&~paralelos,np.minimum(fim,t),fim)
    intervalos=sorted((max(0,float(x)),min(1,float(y))) for x,y,ok in zip(inicio,fim,validos) if ok and y-x>1e-9)
    unidos=[]
    for x,y in intervalos:
        if unidos and x<=unidos[-1][1]+1e-8:
            unidos[-1]=(unidos[-1][0],max(unidos[-1][1],y))
        else:
            unidos.append((x,y))
    return unidos


def recortar(regiao,pontos,normal):
    """Intersecciona a area marcada com a superficie REAL, incluindo buracos."""
    if len(pontos)<3:
        raise ValueError('Marque pelo menos tres pontas')
    n,u=_paredes.eixos_da_parede(normal)
    u=np.array(u);n=np.array(n);plano=np.array(regiao['plano'])
    pontos=np.array(pontos,dtype=np.float64)
    if np.max(np.abs((pontos-plano)@n))>_paredes.TOLERANCIA_PLANO_M:
        raise ValueError('Marque a area no mesmo plano da parede')
    poligono=np.stack((pontos@u,pontos[:,2]),axis=1)
    recortes=_triangulos_do_poligono(poligono)
    origem=np.array(regiao['triangulos']).reshape(-1,3,3)
    tris=np.stack((origem@u,origem[:,:,2]),axis=2)
    saida=[]
    for corte in recortes:
        if _cruz(corte[1]-corte[0],corte[2]-corte[0])<0:
            corte=corte[::-1]
        dist=np.stack([_cruz(corte[(k+1)%3]-corte[k],tris-corte[k]) for k in range(3)],axis=2)
        inteiros=np.all(dist>=-1e-9,axis=(1,2))
        saida.extend(tris[inteiros])
        cruzam=~inteiros & ~np.any(np.all(dist < -1e-9,axis=1),axis=1)
        for tri in tris[cruzam]:
            partes=list(tri)
            for k in range(3):
                a,b=corte[k],corte[(k+1)%3]
                novo=[]
                for p,q in zip(partes[-1:]+partes[:-1],partes):
                    dp,dq=_cruz(b-a,p-a),_cruz(b-a,q-a)
                    if (dp>=-1e-9)!=(dq>=-1e-9):
                        novo.append(p+(q-p)*dp/(dp-dq))
                    if dq>=-1e-9:
                        novo.append(q)
                partes=novo
                if len(partes)<3:
                    break
            for k in range(1,len(partes)-1):
                tri=np.array((partes[0],partes[k],partes[k+1]))
                if abs(_cruz(tri[1]-tri[0],tri[2]-tri[0]))>1e-10:
                    saida.append(tri)
    if not saida:
        raise ValueError('A area marcada nao cobre a parede')
    def mundo(pt):
        v=plano+u*(pt[0]-plano@u)
        v[2]=pt[1]
        return tuple(v)
    contorno=[]
    for a,b in regiao['contorno']:
        pa,pb=np.array((Vector(a).dot(Vector(u)),a[2])),np.array((Vector(b).dot(Vector(u)),b[2]))
        for x,y in _intervalos_segmento(pa,pb,recortes):
            contorno.append((mundo(pa+(pb-pa)*x),mundo(pa+(pb-pa)*y)))
    for pa,pb in zip(poligono,np.roll(poligono,-1,axis=0)):
        for x,y in _intervalos_segmento(pa,pb,tris):
            contorno.append((mundo(pa+(pb-pa)*x),mundo(pa+(pb-pa)*y)))
    # Bordas da area e da parede podem coincidir; unir impede duplicar
    # cruzamentos e transformar um vao valido em vazio nas cotas.
    linhas={}
    for a,b in contorno:
        a=np.array((np.dot(a,u),a[2]));b=np.array((np.dot(b,u),b[2]))
        d=b-a
        if np.linalg.norm(d)<1e-8:
            continue
        d/=np.linalg.norm(d)
        if d[0]<-1e-8 or (abs(d[0])<=1e-8 and d[1]<0):d=-d
        perpendicular=np.array((-d[1],d[0]));offset=float(a@perpendicular)
        chave=tuple(np.round(np.r_[d,offset],7))
        linhas.setdefault(chave,[]).append(tuple(sorted((float(a@d),float(b@d)))))
    contorno=[]
    for (dx,dz,offset),intervalos in linhas.items():
        d=np.array((dx,dz));n2=np.array((-dz,dx));unidos=[]
        for a,b in sorted(intervalos):
            if unidos and a<=unidos[-1][1]+1e-7:unidos[-1]=(unidos[-1][0],max(b,unidos[-1][1]))
            else:unidos.append((a,b))
        contorno.extend((mundo(n2*offset+d*a),mundo(n2*offset+d*b)) for a,b in unidos)
    vertices=[mundo(pt) for tri in saida for pt in tri]
    return regiao_dos_triangulos(vertices,contorno,regiao['plano'],normal,regiao['face'],regiao['faces'])


def ponto_na_regiao(regiao,ponto,u):
    z=max(regiao['retangulo'][2]+2e-6,min(regiao['retangulo'][3]-2e-6,float(ponto.z)))
    return any(a-1e-6<=ponto.dot(u)<=b+1e-6 for a,b in _paredes_edicao.faixas_da_face(regiao,u,z-1e-6,z+1e-6))


def modulo_na_regiao(modulo,regiao,normal):
    caixa=_paredes.caixa_do_modulo(modulo)
    if caixa is None:
        return False
    lo,hi=caixa
    matriz=_paredes.referencial(modulo)
    u=_paredes.eixos_da_parede(normal)[1]
    costas=[matriz @ Vector((x,hi.y,z)) for x in (lo.x,hi.x) for z in (lo.z,hi.z)]
    a,b=min(p.dot(u) for p in costas),max(p.dot(u) for p in costas)
    z0=max(regiao['retangulo'][2],min(p.z for p in costas))
    z1=min(regiao['retangulo'][3],max(p.z for p in costas))
    if z1-z0<1e-6:
        return False
    alturas={z0+2e-6,(z0+z1)/2,z1-2e-6}
    alturas.update(v[2] for par in regiao['contorno'] for v in par if z0<v[2]<z1)
    return any(min(b,d)-max(a,c)>1e-6 for z in alturas
               for c,d in _paredes_edicao.faixas_da_face(regiao,u,z-1e-7,z+1e-7))


def criar_exibicao(context,parede,regiao):
    trios=np.asarray(regiao['triangulos'],dtype=np.float64).reshape(-1,3)
    pontos,indices=np.unique(np.round(trios,7),axis=0,return_inverse=True)
    bm=bmesh.new()
    malha=None
    obj=None
    try:
        verts=[bm.verts.new(v) for v in pontos]
        for tri in indices.reshape(-1,3):
            if len(set(tri))==3:
                try:
                    bm.faces.new([verts[int(i)] for i in tri])
                except ValueError:
                    pass
        bm.normal_update()
        bmesh.ops.dissolve_limit(bm,angle_limit=1e-5,verts=list(bm.verts),edges=list(bm.edges),use_dissolve_boundaries=False)
        malha=bpy.data.meshes.new('Regiao da parede 2D')
        bm.to_mesh(malha)
        obj=bpy.data.objects.new('Regiao da parede 2D',malha)
        context.scene.collection.objects.link(obj)
        obj[MARCA_EXIBICAO]=True
        obj['parede_origem_nome']=parede.name
        obj['parede_origem_uid']=_paredes._uid_da_parede(parede)
        obj['parede_origem_face']=int(regiao['face'])
        obj.color=parede.color
        obj.hide_render=True
        obj.hide_select=True
        _limpeza_pendente[0]=True
        return obj
    except Exception:
        if obj is not None:
            bpy.data.objects.remove(obj,do_unlink=True)
        if malha is not None and malha.users==0:
            bpy.data.meshes.remove(malha)
        raise
    finally:
        bm.free()


def fonte_da_exibicao(obj):
    if not obj or not obj.get(MARCA_EXIBICAO):
        return None
    parede=bpy.data.objects.get(obj.get('parede_origem_nome',''))
    return parede if parede and parede.get(_paredes.CHAVE_UID_PAREDE)==obj.get('parede_origem_uid') else None


def limpar_exibicoes(forcar=False):
    if not forcar and not _limpeza_pendente[0]:
        return
    for obj in list(bpy.data.objects):
        if obj.get(MARCA_EXIBICAO):
            malha=obj.data
            bpy.data.objects.remove(obj,do_unlink=True)
            if malha and malha.users==0:
                bpy.data.meshes.remove(malha)
    _limpeza_pendente[0]=False


def esquecer():
    _candidatas[0].clear()
    _limpeza_pendente[0]=True
