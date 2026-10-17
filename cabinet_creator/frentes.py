"""Referencia geometrica comum das frentes, em coordenadas da Mesh.

Faces semanticas acompanham subdivisao/edicao nativa. Coordenadas derivadas
sao preparadas na montagem ou apos editar; desenho e hover so' leem cache.
Nao conserva objetos em estado global nem usa indices gravados em presets.
"""
import hashlib
import math
from array import array

import bpy
import bmesh
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

_chapas = _ferragens = _eventos = _puxadores = None
CHAVE = 'cabinet_frente_referencia'
ATR_FACE = 'cabinet_frente_face'
ATR_BORDA = 'cabinet_frente_borda'
VERSAO = 1
_pendentes = set()  # nomes, nunca RNA que o undo pode liberar
_cena_pendente = [False]


def _digital(malha):
    co = array('f', [0]) * (3*len(malha.vertices))
    malha.vertices.foreach_get('co', co)
    ids = array('i', [0]) * len(malha.loops)
    malha.loops.foreach_get('vertex_index', ids)
    totais = array('i',[0])*len(malha.polygons)
    malha.polygons.foreach_get('loop_total',totais)
    return hashlib.sha1(co.tobytes()+ids.tobytes()+totais.tobytes()).hexdigest()


def copiar_rotulos(origem,destino):
    """Migra copias nativas anteriores ao esquema, sem trocar a referencia
    original de resize. So' topologias identicas permitem copiar atributos;
    coordenadas podem diferir, pois a copia conserva a medida de origem.
    """
    faltantes=[chave for chave in (ATR_FACE,ATR_BORDA)
               if origem.attributes.get(chave) is not None and destino.attributes.get(chave) is None]
    if not faltantes:
        return
    for colecao,nome,tamanho in (('loops','vertex_index',1),('polygons','loop_total',1),('edges','vertices',2)):
        a,b=getattr(origem,colecao),getattr(destino,colecao)
        if len(a)!=len(b):return
        va=array('i',[0])*(len(a)*tamanho);vb=array('i',[0])*(len(b)*tamanho)
        a.foreach_get(nome,va);b.foreach_get(nome,vb)
        if va!=vb:return
    for chave in faltantes:
        atributo=origem.attributes[chave]
        novo=destino.attributes.new(chave,'INT',atributo.domain)
        valores=array('i',[0])*len(atributo.data)
        atributo.data.foreach_get('value',valores);novo.data.foreach_set('value',valores)
    if CHAVE in destino:del destino[CHAVE]


def invalidar(chapa, conferir=False):
    if chapa is not None and chapa.type == 'MESH':
        if conferir:
            ref = chapa.data.get(CHAVE)
            if ref and ref.get('digital')==_digital(chapa.data):
                return
        chapa.data[CHAVE+'_invalida']=True
        _pendentes.add(chapa.data.name)


def esquecer():
    _pendentes.clear()
    _cena_pendente[0] = True


def encerrar():
    _pendentes.clear()
    _cena_pendente[0] = False


def referencia(chapa):
    """Leitura barata: nenhuma extracao, hash, BMesh ou ray cast aqui."""
    if (chapa is None or chapa.type != 'MESH' or
            chapa.data.get(CHAVE+'_invalida',False)):
        return None
    dado = chapa.data.get(CHAVE)
    if (not dado or not dado.get('valida',True) or dado.get('versao') != VERSAO or
            dado.get('vertices') != len(chapa.data.vertices) or
            dado.get('poligonos') != len(chapa.data.polygons)):
        return None
    return dado.to_dict()


def _expandir(sementes, proibidas=(),sinal=None,coplanar=False,elegiveis=None):
    patch = set(sementes)
    fila = list(patch)
    while fila:
        face = fila.pop()
        for e in face.edges:
            d = e.verts[1].co-e.verts[0].co
            if d.length < 1e-9:
                continue
            for outra in e.link_faces:
                if (outra in patch or outra in proibidas or abs(outra.normal.y) > .5
                        or face.normal.dot(outra.normal) < .001):
                    continue
                if elegiveis is not None and outra not in elegiveis:
                    continue
                if abs(d.normalized().y)<.9 and face.normal.dot(outra.normal)<.9999:
                    continue
                if sinal is not None and outra.normal.z*sinal<.001:
                    continue
                if coplanar and face.normal.dot(outra.normal)<.9999:
                    continue
                patch.add(outra); fila.append(outra)
    return patch


def _sementes_por_solido(bm,sinal,proibidas=(),elegiveis=None):
    """Quadro/painel podem compartilhar a Mesh sem compartilhar vertices.
    Cada solido contribui sua superficie, em vez de o vidro maior ocultar
    o perfil menor. Componentes sao reconhecidos so' durante o preparo.
    """
    restantes=set(bm.faces)
    sementes=[]
    while restantes:
        primeira=restantes.pop(); componente={primeira}; fila=[primeira]
        while fila:
            for e in fila.pop().edges:
                for outra in e.link_faces:
                    if outra in restantes:
                        restantes.remove(outra); componente.add(outra); fila.append(outra)
        candidatas=[f for f in componente if f not in proibidas
                    and f.normal.z*sinal>.001 and abs(f.normal.y)<.5
                    and (elegiveis is None or f in elegiveis)]
        if candidatas:
            sementes.append(max(candidatas,key=lambda f:f.calc_area()))
    return sementes


def _faces_opostas(bm):
    """A espessura atravessa superficies opostas; uma tampa radial
    encontra a curva transversalmente. A consulta nativa distingue ambas
    sem limitar tamanho de segmento nem supor uma espessura constante.
    """
    candidatas=[f for f in bm.faces if abs(f.normal.y)<.5]
    if not any(.001<abs(f.normal.z)<.999 for f in candidatas):
        return None
    arvore=BVHTree.FromBMesh(bm)
    amostras={}
    for tri in bm.calc_loop_triangles():
        face=tri[0].face
        if face not in candidatas:
            continue
        a,b,c=(l.vert.co for l in tri)
        normal=(b-a).cross(c-a)
        area=normal.length_squared
        if area>amostras.get(face,(0,None,None))[0]:
            amostras[face]=(area,(a+b+c)/3,normal.normalized())
    elegiveis=set()
    for face,(_area,ponto,direcao) in amostras.items():
        # Num quad torcido, o centro medio pode estar fora da superficie:
        # o raio acertava a propria face e cortava o arco. A tessellacao
        # nativa fornece um ponto SOBRE a face sem mudar a Mesh modelada.
        co,normal,_indice,_dist=arvore.ray_cast(ponto-direcao*1e-7,-direcao)
        if co is not None and normal.dot(direcao)<-.95:
            elegiveis.add(face)
    return elegiveis or None


def _ordenar(segmentos):
    """Maior cadeia de coordenadas, independente dos indices da malha."""
    vizinhos = {}
    for a,b in segmentos:
        a,b = tuple(a),tuple(b)
        if (Vector(a)-Vector(b)).length < 1e-9:
            continue
        vizinhos.setdefault(a,set()).add(b)
        vizinhos.setdefault(b,set()).add(a)
    saidas = []
    usados = set()
    for inicio in sorted(vizinhos, key=lambda v:(len(vizinhos[v]) != 1,v)):
        if inicio in usados:
            continue
        atual,anterior,caminho = inicio,None,[]
        while atual is not None and atual not in usados:
            caminho.append(Vector(atual)); usados.add(atual)
            proxima = next((v for v in sorted(vizinhos[atual])
                            if v != anterior and v not in usados),None)
            anterior,atual = atual,proxima
        if len(caminho)>1:
            saidas.append(caminho)
    if not saidas:
        return []
    caminho = max(saidas,key=lambda ps:sum((b-a).length for a,b in zip(ps,ps[1:])))
    if caminho[0].x > caminho[-1].x:
        caminho.reverse()
    return caminho


def contorno_tem_curva(segmentos,tolerancia=.05,extensao_minima=30.):
    """Segmentos em mm: varias mudancas graduais, nao uma reta tessellada.
    Sem ajustar circulo: reconhece tambem arcos elipticos e editados por Tab.
    Cortes pequenos de acabamento nao mudam a referencia do movel inteiro.
    """
    ps=_ordenar(segmentos)
    if len(ps)<5:return False
    fechado=any((a-ps[0]).length<tolerancia and (b-ps[-1]).length<tolerancia
                 or (b-ps[0]).length<tolerancia and (a-ps[-1]).length<tolerancia
                 for a,b in segmentos)
    # Colapsar colineares antes de contar mudancas: densidade da Mesh
    # nao decide se a borda e' curva. A mesma regra vale no fecho do anel.
    mudou=True
    while mudou and len(ps)>3:
        mudou=False
        for i in range(len(ps)) if fechado else range(1,len(ps)-1):
            a,b,c=ps[i-1],ps[i],ps[(i+1)%len(ps)]
            u,v=b-a,c-b
            if u.dot(v)>0 and u.cross(v).length/max((c-a).length,1e-9)<=tolerancia:
                ps.pop(i);mudou=True;break
    if len(ps)<5:return False
    caminho=ps+ps[:4] if fechado else ps
    soma=0.;numero=0;inicio=0;anterior=0.
    for i in range(1,len(caminho)-1):
        u=caminho[i]-caminho[i-1];v=caminho[i+1]-caminho[i]
        angulo=math.atan2(u.x*v.y-u.y*v.x,u.dot(v))
        if not math.radians(.2)<abs(angulo)<=math.radians(30.1):
            soma=0.;numero=0;anterior=0.;continue
        if angulo*anterior<=0:
            soma=0.;numero=0;inicio=i-1
        soma+=angulo;numero+=1;anterior=angulo
        if (numero>=3 and abs(soma)>=math.radians(15) and
                (caminho[i]-caminho[inicio+1]).length>=extensao_minima):return True
    return False


def _dados_patch(patch,camada_borda,papel):
    borda = [e for f in patch for e in f.edges
             if sum(outra in patch for outra in e.link_faces)==1]
    borda = set(borda)
    vertices = {v for f in patch for v in f.verts}
    if not vertices:
        return None
    baixo = min(v.co.y for v in vertices)
    cima = max(v.co.y for v in vertices)
    tolerancia = max(1e-7,(cima-baixo)*1e-5)
    linhas = []
    alturas={}
    for v in vertices:
        chave=(round(v.co.x,7),round(v.co.z,7))
        alturas.setdefault(chave,[]).append(v.co.y)
    for lado,y in enumerate((baixo,cima)):
        elegiveis=[e for e in borda if e[camada_borda]==papel+lado]
        if not elegiveis:
            def no_limite(v):
                ys=alturas[(round(v.co.x,7),round(v.co.z,7))]
                if max(ys)-min(ys)<tolerancia:
                    return (v.co.y <= (baixo+cima)/2) if lado==0 else (v.co.y >= (baixo+cima)/2)
                return abs(v.co.y-(min(ys) if lado==0 else max(ys)))<tolerancia
            elegiveis=[e for e in borda if all(no_limite(v) for v in e.verts)]
        segmentos = [(e.verts[0].co.copy(),e.verts[1].co.copy()) for e in elegiveis]
        caminho = _ordenar(segmentos)
        if len(caminho)<2:
            # Uma borda recortada pode nao ter um trecho horizontal inteiro.
            # A secao central da superficie conserva o percurso da frente.
            meio = (baixo+cima)/2
            segmentos = []
            for f in patch:
                cortes = []
                for e in f.edges:
                    a,b = (v.co for v in e.verts)
                    if abs(b.y-a.y)>1e-9 and min(a.y,b.y)<=meio<=max(a.y,b.y):
                        cortes.append(a.lerp(b,(meio-a.y)/(b.y-a.y)))
                if len(cortes)>=2:
                    a,b = cortes[0].copy(),cortes[-1].copy()
                    a.y=b.y=y; segmentos.append((a,b))
            caminho = _ordenar(segmentos)
        linhas.append(caminho)
        for e in elegiveis:
            e[camada_borda]=papel+lado
    if any(len(l)<2 for l in linhas):
        return None
    arestas = set(borda)
    for f in patch:
        for e in f.edges:
            ligadas = [outra for outra in e.link_faces if outra in patch]
            if len(ligadas)==2 and ligadas[0].normal.dot(ligadas[1].normal)<.866:
                arestas.add(e)
    contorno = [list(v.co) for e in sorted(arestas,key=lambda e:e.index) for v in e.verts]
    mapa={frozenset(tuple(v.co) for v in e.verts):e for e in borda}
    normais=[]
    for ps in linhas:
        ns=[]
        for a,b in zip(ps,ps[1:]):
            e=mapa.get(frozenset((tuple(a),tuple(b))))
            normal=sum((f.normal for f in e.link_faces if f in patch),Vector()) if e else (b-a).cross(Vector((0,1,0)))
            ns.append(list(normal.normalized()))
        normais.append(ns)
    return linhas[0],linhas[1],contorno,normais


def _retangular_canonica(baixo,cima,contorno):
    """Subdividir uma borda reta nao transforma uma caixa em curva."""
    a,b,c,d=baixo[0],baixo[-1],cima[-1],cima[0]
    if (abs(a.y-b.y)>1e-7 or abs(c.y-d.y)>1e-7 or
            max(p.z for p in (a,b,c,d))-min(p.z for p in (a,b,c,d))>1e-7 or
            abs(a.x-d.x)>1e-7 or abs(b.x-c.x)>1e-7):
        return False
    segmentos=((a,b),(b,c),(c,d),(d,a))
    for v in [Vector(p) for p in contorno]:
        erros=[]
        for x,y in segmentos:
            t=max(0,min(1,(v-x).dot(y-x)/max((y-x).length_squared,1e-18)))
            erros.append((v-x.lerp(y,t)).length)
        if min(erros)>1e-7:
            return False
    return True


def preparar(chapa, forcar=False):
    """Reconhece a superficie uma vez e guarda faces semanticas nativas.

    O guia legado so' semeia a primeira migracao. Toda reconstrucao posterior
    usa atributos de faces, que o Blender transporta ao editar a topologia.
    """
    if (chapa is None or chapa.type != 'MESH' or chapa.mode == 'EDIT'
            or chapa.data.is_editmode):
        return None
    malha = chapa.data
    if not malha.vertices or not malha.polygons:
        _sem_referencia(malha,_digital(malha))
        return None
    digital = _digital(malha)
    if _chapas.MARCA_CHAPA in chapa:
        _chapas.preparar_espessura(chapa,digital)
    anterior = malha.get(CHAVE)
    if (not forcar and anterior and anterior.get('versao')==VERSAO and
            anterior.get('amostragem_triangular') and anterior.get('digital')==digital):
        _pendentes.discard(malha.name)
        malha[CHAVE+'_invalida']=False
        migrar_puxadores(chapa)
        return referencia(chapa)
    bm = bmesh.new()
    try:
        bm.from_mesh(malha)
        bm.faces.ensure_lookup_table(); bm.faces.index_update(); bm.edges.index_update()
        bm.normal_update()
        camada = bm.faces.layers.int.get(ATR_FACE)
        frente = {f for f in bm.faces if camada is not None and f[camada]==1}
        tras = {f for f in bm.faces if camada is not None and f[camada]==-1}
        migrar=not anterior or not anterior.get('amostragem_triangular')
        elegiveis=_faces_opostas(bm) if migrar or not frente or not tras else None
        if migrar and elegiveis is not None:
            # Os rotulos antigos tambem guardam o corte causado pelo raio.
            # Conservam o lado semantico, mas precisam completar o percurso
            # uma vez, inclusive quando o hash geometrico nao mudou.
            frente=_expandir(frente,tras,elegiveis=elegiveis)
            tras=_expandir(tras,frente,elegiveis=elegiveis)
        if not frente:
            sementes = set()
            guia = chapa.get('porta_linha_frente')
            if guia:
                y = sum((min(v.co.y for v in bm.verts),max(v.co.y for v in bm.verts)))/2
                ps = [Vector(v) for v in guia]
                arvore = BVHTree.FromBMesh(bm)
                for a,b in zip(ps,ps[1:]):
                    ponto = (a+b)/2; ponto.y=y
                    co,_normal,i,_dist = arvore.find_nearest(ponto)
                    if co is not None and 0<=i<len(bm.faces) and abs(bm.faces[i].normal.y)<.5:
                        sementes.add(bm.faces[i])
            if not sementes:
                sementes.update(_sementes_por_solido(bm,1,elegiveis=elegiveis))
            frente = _expandir(sementes,sinal=None if guia else 1,coplanar=bool(guia),elegiveis=elegiveis)
        if not tras:
            tras = _expandir(_sementes_por_solido(bm,-1,frente,elegiveis),frente,sinal=-1,elegiveis=elegiveis)
        camada_borda=bm.edges.layers.int.get(ATR_BORDA) or bm.edges.layers.int.new(ATR_BORDA)
        if migrar:
            for e in bm.edges:
                e[camada_borda]=0
        dados = _dados_patch(frente,camada_borda,1)
        costas = _dados_patch(tras,camada_borda,3)
        if dados is None:
            _sem_referencia(malha,digital)
            return None
        if costas is None:
            # Superficie aberta continua selecionavel. A espessura nominal
            # fornece o verso ate' existir geometria fechada novamente.
            esp = float(chapa.chapa_espessura_mm)/1000
            costas = ([v-Vector((0,0,esp)) for v in dados[0]],
                      [v-Vector((0,0,esp)) for v in dados[1]],[],
                      [[list(-Vector(n)) for n in ns] for ns in dados[3]])
        atributo = malha.attributes.get(ATR_FACE)
        if atributo is None:
            atributo = malha.attributes.new(ATR_FACE,'INT','FACE')
        papeis = [1 if f in frente else -1 if f in tras else 0 for f in bm.faces]
        atributo.data.foreach_set('value',papeis)
        atributo_borda=malha.attributes.get(ATR_BORDA)
        if atributo_borda is None:
            atributo_borda=malha.attributes.new(ATR_BORDA,'INT','EDGE')
        atributo_borda.data.foreach_set('value',[e[camada_borda] for e in bm.edges])
        caminho,topo,contorno_local,_normais = dados
        nominal = float(getattr(chapa,'chapa_comprimento_mm',0))/1000
        altura = max(v.y for v in topo)-min(v.y for v in caminho)
        montagem = [[p.copy() for p in ps] for ps in (caminho,topo,costas[0],costas[1])]
        cortes=set(filter(None,str(chapa.get('chapa_rebaixos','')).split(',')))
        if cortes:
            # O perfil ocupa a faixa retirada pela montagem parametrica.
            # Contorno/selecionar usam madeira real; acoplar usa sua borda
            # nominal, conservada explicitamente pelo proprio corte.
            hx=float(chapa.chapa_largura_mm)/2000
            hy=float(chapa.chapa_comprimento_mm)/2000
            for i,ps in enumerate(montagem):
                if len(ps)==2 and abs(ps[-1].z-ps[0].z)<1e-7:
                    if 'X-' in cortes:ps[0].x=-hx
                    if 'X+' in cortes:ps[-1].x=hx
                if ('Y-' if i%2==0 else 'Y+') in cortes:
                    for p in ps:p.y=-hy if i%2==0 else hy
        malha[CHAVE] = dict(versao=VERSAO,amostragem_triangular=True,digital=digital,vertices=len(malha.vertices),
            poligonos=len(malha.polygons),frente=[list(v) for v in caminho],
            tras=[list(v) for v in costas[0]],cima_frente=[list(v) for v in topo],
            cima_tras=[list(v) for v in costas[1]],contorno=contorno_local,
            normais_frente=dados[3][0],normais_cima_frente=dados[3][1],
            normais_tras=costas[3][0],normais_cima_tras=costas[3][1],
            espessura=float(chapa.chapa_espessura_mm)/1000,
            plana_retangular=_retangular_canonica(caminho,topo,contorno_local),
            montagem_frente=[list(v) for v in montagem[0]],
            montagem_cima_frente=[list(v) for v in montagem[1]],
            montagem_tras=[list(v) for v in montagem[2]],
            montagem_cima_tras=[list(v) for v in montagem[3]],
            altura=altura,altura_nominal=max(altura,nominal),
            comprimento=sum((b-a).length for a,b in zip(caminho,caminho[1:])))
    finally:
        bm.free()
    _pendentes.discard(malha.name)
    malha[CHAVE+'_invalida']=False
    migrar_puxadores(chapa)
    return referencia(chapa)


def _sem_referencia(malha,digital):
    # Uma superficie incompleta nao pode provocar extracao infinita no
    # timer. Outra edicao muda a assinatura e permite reconhece-la de novo.
    malha[CHAVE]=dict(versao=VERSAO,amostragem_triangular=True,digital=digital,valida=False,
                      vertices=len(malha.vertices),poligonos=len(malha.polygons))
    malha[CHAVE+'_invalida']=False
    _pendentes.discard(malha.name)


def _linhas(chapa,face=1,montagem=False):
    ref = referencia(chapa)
    if ref is None:
        return None
    prefixo='montagem_' if montagem else ''
    return ([Vector(v) for v in ref[prefixo+('frente' if face>=0 else 'tras')]],
            [Vector(v) for v in ref[prefixo+('cima_frente' if face>=0 else 'cima_tras')]])


def perfil(chapa,fechada=False,interno=False):
    linhas = _linhas(chapa,-1 if interno else 1)
    if linhas is None:
        return None
    matriz = (_ferragens._matriz_fechada(chapa) if fechada and 'eh_folha_porta' in chapa
              else chapa.matrix_world)
    return tuple([matriz@p for p in linha] for linha in linhas)


def contorno(chapa):
    ref = referencia(chapa)
    if ref is None:
        return None
    ps = [chapa.matrix_world@Vector(v) for v in ref['contorno']]
    return ps,[(i,i+1) for i in range(0,len(ps),2)]


def bordas(chapa,face=1):
    linhas = _linhas(chapa,face,montagem=True)
    if linhas is None:
        return {}
    baixo,cima = linhas
    mundo = chapa.matrix_world
    saida = {'X-':(mundo@cima[0],mundo@baixo[0]),
             'X+':(mundo@baixo[-1],mundo@cima[-1])}
    if face<0:
        saida={k:(b,a) for k,(a,b) in saida.items()}
    for nome,ps in (('Y-',baixo),('Y+',cima)):
        for i,(a,b) in enumerate(zip(ps,ps[1:])):
            saida[nome+'|'+str(i)] = (mundo@a,mundo@b)
    return saida


def normalizar_borda(chapa,borda,fracao):
    if '|' not in borda:
        return borda,fracao
    nome,indice = borda.split('|',1)
    linhas = _linhas(chapa,montagem=True)
    if linhas is None:
        return nome,fracao
    ps = linhas[1] if nome=='Y+' else linhas[0]
    ds = [(b-a).length for a,b in zip(ps,ps[1:])]
    indice = max(0,min(len(ds)-1,int(indice)))
    return nome,(sum(ds[:indice])+ds[indice]*fracao)/max(sum(ds),1e-9)


def _amostra(ps,distancia):
    for a,b in zip(ps,ps[1:]):
        tamanho = (b-a).length
        if distancia<=tamanho+1e-9:
            return a.lerp(b,max(0,min(1,distancia/max(tamanho,1e-9)))),(b-a).normalized()
        distancia-=tamanho
    return ps[-1].copy(),(ps[-1]-ps[-2]).normalized()


def _normal(chapa,face,cima,ps,distancia):
    ref=referencia(chapa)
    nome=('normais_cima_' if cima else 'normais_')+('frente' if face>=0 else 'tras')
    ns=ref[nome]
    for i,(a,b) in enumerate(zip(ps,ps[1:])):
        d=(b-a).length
        if distancia<=d+1e-9:
            return Vector(ns[min(i,len(ns)-1)]).normalized()
        distancia-=d
    return Vector(ns[-1]).normalized()


def lugar(chapa,borda,face,fracao,comprimento_mm,recuo_mm,inteiro=False):
    borda,fracao = normalizar_borda(chapa,borda,fracao)
    linhas = _linhas(chapa,face,montagem=True)
    if linhas is None:
        return None
    baixo,cima = linhas
    ref = referencia(chapa)
    sinal = 1 if borda.endswith('+') else -1
    comprimento,recuo = float(comprimento_mm)/1000,float(recuo_mm)/1000
    if borda.startswith('Y'):
        ps = cima if sinal>0 else baixo
        total = sum((b-a).length for a,b in zip(ps,ps[1:]))
        if inteiro:
            comprimento=total; distancia=total/2
        else:
            livre=max(0,total-comprimento)
            distancia=(total/2 if comprimento>=total else
                       comprimento/2+max(0,min(livre,fracao*total-comprimento/2)))
            distancia=min(total,distancia)
        ponto,tangente = _amostra(ps,distancia)
        fora=_normal(chapa,face,sinal>0,ps,distancia)
        ao_longo=tangente*(-sinal)*(1 if face>=0 else -1)
        dentro=fora.cross(ao_longo).normalized()
    else:
        ps = list(baixo)
        if sinal>0:
            ps.reverse()
        total=sum((b-a).length for a,b in zip(ps,ps[1:]))
        ponto,tangente=_amostra(ps,min(total,recuo))
        if sinal>0:
            tangente=-tangente
        distancia=min(total,recuo)
        fora=_normal(chapa,face,False,baixo,total-distancia if sinal>0 else distancia)
        ao_longo=Vector((0,sinal,0))*(1 if face>=0 else -1)
        dentro=fora.cross(ao_longo).normalized()
        altura=cima[0 if sinal<0 else -1].y-baixo[0 if sinal<0 else -1].y
        centro_y=(cima[0 if sinal<0 else -1].y+baixo[0 if sinal<0 else -1].y)/2
        if inteiro:
            comprimento=altura
        livre=max(0,altura-comprimento)/2
        ponto.y=centro_y+max(-livre,min(livre,(fracao-.5)*altura))*sinal*(1 if face>=0 else -1)
        recuo=0  # ja' percorrido sobre o perfil, nao sobre sua corda
    matriz=Matrix((ao_longo,dentro,fora)).transposed().to_4x4()
    matriz.translation=ponto+dentro*recuo
    return matriz,comprimento*1000


def migrar_puxadores(chapa):
    """Traduz uma vez a coordenada antiga, nunca um desvio acumulado."""
    for pux in chapa.children:
        if ('eh_puxador' not in pux or pux.get('puxador_referencia_versao',0)>=1):
            continue
        borda=str(pux.get('puxador_borda',''))
        face=int(pux.get('puxador_face',1))
        if (not chapa.get('porta_linha_frente') and borda.startswith('Y')
                and (1 if borda.endswith('+') else -1)*face>0):
            pux['puxador_fracao']=1-float(pux.get('puxador_fracao',.5))
        pux['puxador_referencia_versao']=1
        if pux.type=='MESH' and _puxadores is not None:
            # Aplica a migracao tambem aos exemplares ja' inseridos. A
            # referencia ja' existe e a marca precede a montagem: sem ciclo.
            _puxadores.posicionar_puxador(pux)


def fracao_do_ponto(chapa,borda,face,ponto):
    """Projecao LOCAL comum a adocao de pecas e ao posicionamento novo."""
    linhas=_linhas(chapa,face,montagem=True)
    if linhas is None:
        return None
    baixo,cima=linhas
    if borda.startswith('Y'):
        ps=cima if borda.endswith('+') else baixo
    else:
        ps=[cima[0],baixo[0]] if borda=='X-' else [baixo[-1],cima[-1]]
        if face<0:ps.reverse()
    tamanhos=[(b-a).length for a,b in zip(ps,ps[1:])]
    total=sum(tamanhos);percorrido=0;melhor=None
    ponto=Vector(ponto)
    for (a,b),d in zip(zip(ps,ps[1:]),tamanhos):
        t=max(0,min(1,(ponto-a).dot(b-a)/max(d*d,1e-18)))
        distancia=(ponto-a.lerp(b,t)).length_squared
        if melhor is None or distancia<melhor[0]:
            melhor=(distancia,(percorrido+d*t)/max(total,1e-9))
        percorrido+=d
    return melhor[1] if melhor else .5


def processar_pendentes():
    if _eventos is not None and _eventos._desfazendo[0]:
        return
    if _cena_pendente[0]:
        preparar_cena()
    for nome in tuple(_pendentes):
        malha=bpy.data.meshes.get(nome)
        if malha is None:
            _pendentes.discard(nome)
            _cena_pendente[0]=True
        else:
            for obj in bpy.data.user_map(subset={malha}).get(malha,()):
                if isinstance(obj,bpy.types.Object) and obj.mode!='EDIT':
                    preparar(obj)
                    break


def preparar_cena():
    for obj in bpy.data.objects:
        if obj.type=='MESH' and 'eh_chapa' in obj:
            preparar(obj)
    _cena_pendente[0] = False


def preparar_conjunto(conj):
    for obj in conj.children_recursive:
        if obj.type=='MESH' and 'eh_chapa' in obj:
            preparar(obj)


def transportar(chapa,pontos,matriz):
    """Captura referencia da geometria transportada antes de mudar o rig.

    Opera numa copia nativa para nao substituir a malha editada. Retorna
    o percurso fechado em MUNDO, preservando correspondencia por faces.
    """
    copia=chapa.copy(); copia.data=chapa.data.copy()
    try:
        for v,p in zip(copia.data.vertices,pontos):
            v.co=matriz.inverted()@p
        copia.data.update()
        dado=preparar(copia,forcar=True)
        return [matriz@Vector(v) for v in dado['frente']] if dado else None
    finally:
        malha=copia.data
        bpy.data.objects.remove(copia)
        if malha.users==0:
            bpy.data.meshes.remove(malha)
