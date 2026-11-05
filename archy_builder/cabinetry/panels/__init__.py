"""Chapa: marcadores, malha (bmesh), espessura livre, normalizacao,
o handler do depsgraph, a geometria em mundo, a deteccao da
adjacencia (solda) entre chapas e os operadores de criar/marcar chapa."""

import bpy, bmesh, math, uuid
from bpy.props import BoolProperty
from mathutils import Matrix, Vector
from mathutils.kdtree import KDTree
from bpy.types import Operator

# usados so' ao RODAR (import circular): o __init__ liga estes
# apelidos depois de carregar todos (`_ligar_modulos`)
_modulos = None
_eventos = None
_portas = None
_ferragens = None
_importacao = None
_puxadores = None
_solda = None
_frentes = None
_formas = None

# Espessuras CONVENCIONAIS: so' opcoes/padrao (enum das portas). Nao
# limitam mais o campo (pedido do usuario): qualquer espessura vale, e
# acima de ESPESSURA_ALERTA_MM a gaveta pinta o campo de vermelho.
ESPESSURAS_PERMITIDAS = [15.0, 18.0, 20.0, 30.0]
ESPESSURA_ALERTA_MM = 60.0


def _espessura_livre(valor):
    """A espessura que o usuario pediu: positiva e sem ruido de float."""
    return round(max(1.0, float(valor)), 2)


def _espessura_em_alerta(valor):
    return float(valor) > ESPESSURA_ALERTA_MM + 1e-6

# Marcador ID. ATENCAO: propriedades criadas com bpy.props em
# bpy.types.Object sao RNA e NAO aparecem em `"x" in obj`.
# Os nomes das propriedades internas (chapa_*, eh_chapa, adj_*) sao
# deliberadamente mantidos do nome antigo do add-on: eles estao gravados
# dentro dos .blend dos presets. Renomea-los invalidaria toda a
# biblioteca ja' salva.
MARCA_CHAPA = "eh_chapa"
MARCA_CONJUNTO = "eh_conjunto_chapa"
MARCA_PORTAS = "eh_grupo_portas"
MARCA_FOLHA = "eh_folha_porta"
# Peca da MOLDURA da porta de correr (revestimento das laterais, bases do
# trilho, testeira e rodape): chapa de verdade, filha do grupo da porta e
# refeita com ela, como a folha (`_portas._pecas_moldura`).
MARCA_MOLDURA = "eh_moldura_porta"
# FUNDO do modulo (chapa de 5 mm em canal, recuada): peca DEPENDENTE --
# refeita pela caixa do modulo (`_modulos.ajustar_fundo`), fora da
# adjacencia, da proporcao do redimensionar e da espessura do modulo.
MARCA_FUNDO = "eh_fundo_modulo"
# TRAVESSA (frente/tras) no lugar do tampo dos modulos de bancada: tambem
# dependente -- refeita pela caixa, com a largura que tiver (`ajustar_travessas`)
MARCA_TRAVESSA = "eh_travessa_modulo"


def eh_dependente(obj):
    """Fundo ou travessa: segue a caixa do modulo, fora da adjacencia."""
    return MARCA_FUNDO in obj or MARCA_TRAVESSA in obj
# Objetos de fora que entram no modulo/porta sem virar chapa (IMPORTACAO).
MARCA_ACESSORIO = "eh_acessorio"
MARCA_PUXADOR = "eh_puxador"
# Empties de amarracao (modulo, grupo de portas, ponta do pistao) ficam na
# cena: o parentesco do Blender e' o que move o armario inteiro, salva o
# preset e faz a porta seguir o modulo. Mas ninguem precisa ve-los
# (pedido do usuario: poluiam a vista): tamanho minimo do Blender.
TAMANHO_EMPTY_OCULTO = 0.0001


def _ocultar_empty(obj):
    if obj.type == 'EMPTY':
        obj.empty_display_type = 'PLAIN_AXES'
        obj.empty_display_size = TAMANHO_EMPTY_OCULTO


CHAVE_TRAVAS_PUXADOR = "puxador_travas"     # [L, A, P]: 1 = travado

_ocupado = [False]
_havia_modal = [False]   # lembra se um operador modal estava ativo
CHAVE_ESPESSURA = 'cabinet_secao_espessura'
ATR_COTA_ARESTA = 'cabinet_cota_aresta'


def _secao_espessura(malha):
    """Pareia as duas peles pelo eixo transversal local, fora do redraw.

    Uma dobra desloca a linha media, mas nao aumenta a distancia entre
    vertices correspondentes. So' uma secao completa e uniforme decide E;
    recortes ambiguos conservam a medida nominal, nunca o volume envolvente.
    """
    if malha.is_editmode or len(malha.vertices)<6:return None
    arvore=KDTree(len(malha.vertices))
    for v in malha.vertices:arvore.insert((v.co.x,v.co.y,0),v.index)
    arvore.balance()
    vistos=set();pares=[];lados=[0]*len(malha.vertices);espessuras=[]
    grupos=[-1]*len(malha.vertices)
    for v in malha.vertices:
        if v.index in vistos:continue
        ids=[i for _p,i,_d in arvore.find_range((v.co.x,v.co.y,0),.000002)]
        zs=[malha.vertices[i].co.z for i in ids];lo,hi=min(zs),max(zs)
        if hi-lo<.000001 or any(min(abs(z-lo),abs(z-hi))>.000002 for z in zs):return None
        if any(i in vistos for i in ids):return None
        vistos.update(ids);espessuras.append(hi-lo)
        baixo=min(ids,key=lambda i:malha.vertices[i].co.z)
        alto=max(ids,key=lambda i:malha.vertices[i].co.z)
        grupo=len(pares)
        pares.append((tuple(malha.vertices[baixo].co),tuple(malha.vertices[alto].co)))
        for i in ids:grupos[i]=grupo
        for i in ids:lados[i]=-1 if abs(malha.vertices[i].co.z-lo)<.000002 else 1
    if len(pares)<3 or max(espessuras)-min(espessuras)>.000005:return None
    return dict(espessura_mm=sum(espessuras)/len(espessuras)*1000,pares=pares,lados=lados,grupos=grupos)


def _bordas_da_secao(malha, secao):
    """Bordas das duas peles; arestas internas da triangulacao nao sao cotas.

    O atributo acompanha a edicao/undo nativos. Indices de vertices servem
    so' nesta consulta, nunca como identidade guardada pela HUD/menu.
    """
    grupos=secao['grupos'];lados=secao['lados'];contagens={-1:{},1:{}}
    for face in malha.polygons:
        ids=list(face.vertices);lado=lados[ids[0]]
        if any(lados[i]!=lado for i in ids):continue
        for a,b in zip(ids,ids[1:]+ids[:1]):
            chave=tuple(sorted((grupos[a],grupos[b])))
            contagens[lado][chave]=contagens[lado].get(chave,0)+1
    bordas=[k for k,n in contagens[-1].items() if n==1 and contagens[1].get(k)==1]
    if not bordas:return {}
    atributo=malha.attributes.get(ATR_COTA_ARESTA)
    if atributo is None:atributo=malha.attributes.new(ATR_COTA_ARESTA,'INT','EDGE')
    pares_arestas={k:[] for k in bordas}
    for e in malha.edges:
        a,b=e.vertices;k=tuple(sorted((grupos[a],grupos[b])))
        if lados[a]==lados[b] and k in pares_arestas:pares_arestas[k].append(e.index)
    proximo=max((v.value for v in atributo.data),default=0)+1
    usados=set();resultado={}
    for k,ids in pares_arestas.items():
        if len(ids)!=2:continue
        antigos=[atributo.data[i].value for i in ids]
        uid=next((v for v in antigos if v>0 and v not in usados),None)
        if uid is None:uid=proximo;proximo+=1
        usados.add(uid)
        for i in ids:
            if atributo.data[i].value!=uid:atributo.data[i].value=uid
        resultado[str(uid)]=k
    return resultado


def preparar_espessura(obj, digital=None):
    """Cache numerico compartilhado por medicao, resize e HUD."""
    if obj.type!='MESH' or obj.data.is_editmode:return None
    digital=digital or _frentes._digital(obj.data)
    antigo=obj.data.get(CHAVE_ESPESSURA)
    if antigo and antigo.get('digital')==digital and antigo.get('versao')==3:return antigo
    secao=_secao_espessura(obj.data)
    envelope=(max(v.co.z for v in obj.data.vertices)-min(v.co.z for v in obj.data.vertices))*1000 if obj.data.vertices else 0.
    dado=dict(digital=digital,versao=3,espessura_mm=secao['espessura_mm'] if secao else 0.,
              dobrada=bool(secao and envelope>secao['espessura_mm']+.01),
              pares={str(i):[list(a),list(b)] for i,(a,b) in enumerate(secao['pares'])} if secao else {})
    bordas=_bordas_da_secao(obj.data,secao) if secao and dado['dobrada'] else {}
    dado['bordas']={uid:[list(secao['pares'][a][s]) for a in par for s in (0,1)]
                    for uid,par in bordas.items()}
    quinas={};incidencia={}
    for uid,(a,b) in bordas.items():
        incidencia.setdefault(a,[]).append((int(uid),b))
        incidencia.setdefault(b,[]).append((int(uid),a))
    for i,par in enumerate(secao['pares'] if secao else ()):
        incidentes=incidencia.get(i,())
        if len(incidentes)!=2:continue
        (ua,a),(ub,b)=sorted(incidentes)
        quinas[str(ua)+':'+str(ub)]=dict(face=[ua,ub],ponto=list(par[1]),
            a=list(secao['pares'][a][1]),b=list(secao['pares'][b][1]))
    dado['quinas']=quinas
    if secao is None and not obj.get('chapa_rebaixos'):
        # Peles editadas separadamente nao podem ser extrudadas pelo mesmo perfil.
        # A topologia nativa conserva cada borda, inclusive o verso diferente.
        bm=bmesh.new()
        try:
            bm.from_mesh(obj.data);bm.normal_update();bm.edges.index_update()
            reais=[e.index for e in bm.edges if len(e.link_faces)!=2 or
                abs(e.link_faces[0].normal.dot(e.link_faces[1].normal))<.99999]
        finally:bm.free()
        atributo=obj.data.attributes.get(ATR_COTA_ARESTA)
        if atributo is None:atributo=obj.data.attributes.new(ATR_COTA_ARESTA,'INT','EDGE')
        proximo=max((v.value for v in atributo.data),default=0)+1
        usados=set();arestas={}
        for i in reais:
            uid=atributo.data[i].value
            if uid<=0 or uid in usados:
                uid=proximo;proximo+=1;atributo.data[i].value=uid
            usados.add(uid)
            a,b=[obj.data.vertices[j].co for j in obj.data.edges[i].vertices]
            if (b-a).length<1e-8:continue
            espessura=(abs(a.x-b.x)<1e-6 and abs(a.y-b.y)<1e-6
                and abs(abs(a.z-b.z)*1000-obj.chapa_espessura_mm)<.01)
            arestas[str(uid)]=dict(pontos=[list(a),list(b)],espessura=espessura)
        dado['arestas']=arestas
    centros=[(Vector(a)+Vector(b))/2 for a,b in secao['pares']] if secao else []
    desvio=(max(p.z for p in centros)-min(p.z for p in centros))*1000 if centros else 0.
    # Uma projecao fora da espessura e' uma medida independente da madeira.
    dado['deslocamento_mm']=desvio
    if centros:
        apoio=max(centros,key=lambda p:(p.x,-p.y)).copy()
        apoio.z=min(p.z for p in centros)
        dado['linha_deslocamento']=[list(apoio),list(apoio+Vector((0,0,desvio/1000)))]
    obj.data[CHAVE_ESPESSURA]=dado
    return obj.data[CHAVE_ESPESSURA]


def _terminar_edicao_secao(obj):
    obj.data.update()
    absorver_malha_editada(obj,reorientar=False)
    _frentes.preparar(obj,forcar=True);_formas.esquecer()
    bpy.context.view_layer.update()


def definir_aresta(obj, uid, valor_mm, lado='min'):
    """Uma ponta anda na direcao real da aresta; as duas peles andam juntas."""
    if obj.mode=='EDIT' or obj.data.is_editmode:raise ValueError('Saia do modo de edicao')
    secao=_secao_espessura(obj.data)
    if not secao:
        atributo=obj.data.attributes.get(ATR_COTA_ARESTA)
        aresta=next((e for e in obj.data.edges if atributo and atributo.data[e.index].value==int(uid)),None)
        if aresta is None:raise ValueError('A aresta nao existe mais')
        a,b=aresta.vertices if lado=='min' else tuple(aresta.vertices)[::-1]
        vetor=obj.data.vertices[b].co-obj.data.vertices[a].co
        if vetor.length<1e-8:raise ValueError('Aresta sem comprimento')
        if obj.data.users>1:obj.data=obj.data.copy()
        delta=vetor.normalized()*(max(1.,float(valor_mm))/1000-vetor.length)
        # O par topologico conserva o afastamento entre as peles mesmo
        # quando um canto foi editado sem mover o seu correspondente.
        pares=[j for e in obj.data.edges if b in e.vertices for j in e.vertices
            if j not in (a,b) and abs(abs(obj.data.vertices[j].co.z-obj.data.vertices[b].co.z)*1000
                -obj.chapa_espessura_mm)<.01]
        obj.data.vertices[b].co+=delta
        if len(pares)==1:obj.data.vertices[pares[0]].co+=delta
        _terminar_edicao_secao(obj)
        return
    bordas=_bordas_da_secao(obj.data,secao)
    par=bordas.get(str(uid))
    if par is None:raise ValueError('A aresta nao existe mais')
    a,b=par if lado=='min' else par[::-1]
    pa,pb=(Vector(secao['pares'][i][0]) for i in (a,b))
    vetor=pb-pa
    if vetor.length<1e-8:raise ValueError('Aresta sem comprimento')
    delta=vetor.normalized()*(max(1.,float(valor_mm))/1000-vetor.length)
    if obj.data.users>1:obj.data=obj.data.copy()
    for v,g in zip(obj.data.vertices,secao['grupos']):
        if g==b:v.co+=delta
    _terminar_edicao_secao(obj)


def definir_angulo_arestas(obj, face, valor):
    """Gira uma borda no plano das duas bordas reais, conservando E."""
    if obj.mode=='EDIT' or obj.data.is_editmode:raise ValueError('Saia do modo de edicao')
    secao=_secao_espessura(obj.data)
    if not secao:raise ValueError('A chapa nao define duas peles correspondentes')
    bordas=_bordas_da_secao(obj.data,secao)
    ea,eb=(bordas.get(str(uid)) for uid in face)
    comuns=set(ea or ())&set(eb or ())
    if len(comuns)!=1:raise ValueError('A quina nao existe mais')
    canto=comuns.pop();a=next(i for i in ea if i!=canto);b=next(i for i in eb if i!=canto)
    p,pa,pb=(Vector(secao['pares'][i][0]) for i in (canto,a,b))
    base=(pa-p).normalized();vetor=pb-p
    normal=vetor-base*vetor.dot(base)
    if normal.length<1e-8:raise ValueError('A quina nao define um plano de giro')
    angulo=math.radians(max(.1,min(179.9,float(valor))))
    delta=p+(base*math.cos(angulo)+normal.normalized()*math.sin(angulo))*vetor.length-pb
    if obj.data.users>1:obj.data=obj.data.copy()
    for v,g in zip(obj.data.vertices,secao['grupos']):
        if g==b:v.co+=delta
    _terminar_edicao_secao(obj)


def definir_deslocamento(obj, valor_mm, lado='min'):
    """Muda a flecha da linha media; cada par conserva sua propria E."""
    if obj.mode=='EDIT' or obj.data.is_editmode:raise ValueError('Saia do modo de edicao')
    secao=_secao_espessura(obj.data)
    if not secao:raise ValueError('A chapa nao define duas peles correspondentes')
    esp=secao['espessura_mm']/1000
    meios=[v.co.z-lado_v*esp/2 for v,lado_v in zip(obj.data.vertices,secao['lados'])]
    lo,hi=min(meios),max(meios)
    if hi-lo<1e-8:raise ValueError('A chapa nao tem deslocamento transversal')
    fixo=hi if lado=='max' else lo
    fator=max(0.,float(valor_mm))/1000/(hi-lo)
    if obj.data.users>1:obj.data=obj.data.copy()
    for v,meio,lado_v in zip(obj.data.vertices,meios,secao['lados']):
        v.co.z=fixo+(meio-fixo)*fator+lado_v*esp/2
    obj.data.update()
    absorver_malha_editada(obj)
    _frentes.preparar(obj,forcar=True);_formas.esquecer()
    bpy.context.view_layer.update()


def _malha_e_caixa(malha):
    """A malha ainda e' a caixa que o add-on gera: 8 vertices, um em
    cada canto da propria caixa. Qualquer recorte, chanfro, furo ou
    vertice fora do canto faz dela uma malha MODELADA."""
    vertices = malha.vertices
    if len(vertices) == 0:
        return True             # malha nova: nasce caixa
    if len(vertices) != 8:
        return False
    lo = [min(v.co[i] for v in vertices) for i in range(3)]
    hi = [max(v.co[i] for v in vertices) for i in range(3)]
    cantos = set()
    for v in vertices:
        canto = []
        for i in range(3):
            if abs(v.co[i] - lo[i]) < 1e-6:
                canto.append(0)
            elif abs(v.co[i] - hi[i]) < 1e-6:
                canto.append(1)
            else:
                return False
        cantos.add(tuple(canto))
    return len(cantos) == 8


def _digital_malha(malha):
    import hashlib
    from array import array
    co=array('f',[0])*(3*len(malha.vertices))
    malha.vertices.foreach_get('co',co)
    return hashlib.sha1(co.tobytes()).hexdigest()


def _nova_referencia(obj, **extra):
    estado=obj.get('chapa_edicao')
    velha=estado.get('malha') if estado else None
    obj['chapa_edicao']=dict(malha=obj.data.copy(),ultimo='',**extra)
    if isinstance(velha,bpy.types.Mesh) and velha.users==0:
        bpy.data.meshes.remove(velha)
    return obj['chapa_edicao']


def guardar_referencia_malha(obj, largura, comprimento):
    """Fixa a malha atual como referencia do esticar, com a largura e o
    comprimento (m) que ela representa. Chamar ANTES de trocar as medidas:
    a madeira da porta curva passa da largura nominal (quinas reais), e
    medir pela malha a encolhia no primeiro resize, sem volta."""
    estado=obj.get('chapa_edicao')
    if estado and estado['ultimo']==_digital_malha(obj.data):
        return
    _nova_referencia(obj,nominal=[largura,comprimento])['ultimo']=_digital_malha(obj.data)


def _esticar_malha(obj, medidas):
    """Leva a malha MODELADA as medidas (m) sem apagar nada: cada
    vertice anda junto com a face do lado em que esta' (acima do meio,
    a face maxima; abaixo, a minima). Recortes e furos mantem o tamanho
    e a distancia ate' a borda mais proxima."""
    _frentes.preparar(obj)
    estado=obj.get('chapa_edicao')
    if not estado or estado['ultimo']!=_digital_malha(obj.data):
        estado=_nova_referencia(obj)
    # Sem nominal guardado, a malha vale o que mede (caso geral).
    nominal=estado.get('nominal')
    _frentes.copiar_rotulos(obj.data,estado['malha'])
    # Nao recalcular de que lado o vertice esta' depois de cruzar o meio:
    # a referencia nativa conserva furos, recortes e indices no retorno.
    bm=bmesh.new()
    try:
        bm.from_mesh(estado['malha'])
        secao=_secao_espessura(estado['malha'])
        lo=[min(v.co[i] for v in bm.verts) for i in range(3)]
        hi=[max(v.co[i] for v in bm.verts) for i in range(3)]
        for i in range(3):
            if i==2 and secao:
                delta=(medidas[2]-secao['espessura_mm']/1000)/2
                for v,lado in zip(bm.verts,secao['lados']):v.co.z+=lado*delta
                continue
            delta=(medidas[i]-(nominal[i] if nominal and i<2 else hi[i]-lo[i]))/2
            meio=(lo[i]+hi[i])/2
            mais=[v for v in bm.verts if v.co[i]>meio]
            menos=[v for v in bm.verts if v.co[i]<=meio]
            vetor=Vector();vetor[i]=delta
            bmesh.ops.translate(bm,verts=mais,vec=vetor)
            bmesh.ops.translate(bm,verts=menos,vec=-vetor)
        bm.to_mesh(obj.data)
    finally:bm.free()
    obj.data.update()
    estado['ultimo']=_digital_malha(obj.data)


def _malha_com_canais(obj, L, C, E):
    """A chapa (m) com canais FRESADOS ao longo do comprimento (Y local),
    na face de cima (Z+, `chapa_canal_lado` 1) ou de baixo (-1): a base do
    trilho leve, como o "Trilho exemplo" do usuario. Secao no plano X/Z
    com os entalhes, extrudada em Y."""
    hx, hy, hz = L / 2.0, C / 2.0, E / 2.0
    largura = float(obj.get('chapa_canal_largura', 0.0)) / 1000.0
    fundo = min(float(obj.get('chapa_canal_fundo', 0.0)) / 1000.0, E * 0.9)
    lado = 1.0 if int(obj.get('chapa_canal_lado', 1)) >= 0 else -1.0
    face = lado * hz
    contorno = [(-hx, face)]
    for c in sorted(float(x) / 1000.0 for x in obj['chapa_canais']):
        a, b = max(-hx, c - largura / 2.0), min(hx, c + largura / 2.0)
        if b - a <= 1e-6:
            continue
        contorno += [(a, face), (a, face - lado * fundo),
                     (b, face - lado * fundo), (b, face)]
    contorno += [(hx, face), (hx, -face), (-hx, -face)]
    # pontos repetidos (canal na quina) deixariam face degenerada
    secao = [p for i, p in enumerate(contorno)
             if (Vector(p) - Vector(contorno[i - 1])).length > 1e-7]
    bm = bmesh.new()
    try:
        pontas = [[bm.verts.new((x, y, z)) for x, z in secao] for y in (-hy, hy)]
        n = len(secao)
        for i in range(n):
            j = (i + 1) % n
            bm.faces.new((pontas[0][i], pontas[0][j], pontas[1][j], pontas[1][i]))
        bm.faces.new(pontas[0])
        bm.faces.new(pontas[1][::-1])
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(obj.data)
    finally:
        bm.free()
    obj.data.update()


def _caixa_bm(bm, x0, x1, y0, y1, z0, z1, material=0):
    vs = [bm.verts.new((x, y, z)) for z in (z0, z1) for y in (y0, y1) for x in (x0, x1)]
    for indices in ((0, 2, 3, 1), (4, 5, 7, 6), (0, 1, 5, 4), (2, 6, 7, 3),
                    (0, 4, 6, 2), (1, 3, 7, 5)):
        bm.faces.new([vs[i] for i in indices]).material_index = material


def _malha_quadro(obj, L, C, E):
    """Folha de correr QUADRO DE ALUMINIO (a do despenseiro do DXF):
    perfil de `chapa_quadro_mm` de face em volta (material 0) e o painel
    fino (vidro/espelho/MDF, material 1) a `chapa_painel_frente_mm` da
    face de fora (Z+), entrando `chapa_painel_entra_mm` no perfil. Refeita
    a cada medida, como a dos canais: nao e' caixa, nem foi modelada."""
    hx, hy, hz = L / 2.0, C / 2.0, E / 2.0
    q = min(float(obj['chapa_quadro_mm']) / 1000.0, hx * 0.45, hy * 0.45)
    p = min(float(obj.get('chapa_painel_mm', 5.0)) / 1000.0, E)
    frente = min(float(obj.get('chapa_painel_frente_mm', 6.0)) / 1000.0, E - p)
    entra = min(float(obj.get('chapa_painel_entra_mm', 5.0)) / 1000.0, q)
    bm = bmesh.new()
    try:
        # o perfil em 4 barras: as de pe' inteiras, as deitadas entre elas
        for x0, x1, y0, y1 in ((-hx, -hx + q, -hy, hy), (hx - q, hx, -hy, hy),
                               (-hx + q, hx - q, -hy, -hy + q),
                               (-hx + q, hx - q, hy - q, hy)):
            _caixa_bm(bm, x0, x1, y0, y1, -hz, hz, 0)
        _caixa_bm(bm, -hx + q - entra, hx - q + entra, -hy + q - entra,
                  hy - q + entra, hz - frente - p, hz - frente, 1)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(obj.data)
    finally:
        bm.free()
    obj.data.update()


SEGMENTOS_ARCO_CHAPA = 16


def _malha_arco(obj, L, C, E):
    """Chapa CURVADA em arco (frente de gaveta de canto do DXF): a
    corda e' a largura, a flecha `chapa_arco_mm` vai para Z+ (fora) e as
    pontas ficam onde a chapa reta estaria. Espessura concentrica; secao
    no plano X/Z puxada em Y (comprimento)."""
    f = float(obj['chapa_arco_mm']) / 1000.0
    meia = L / 2.0
    f = min(f, meia)                          # no maximo meio circulo
    raio = (meia * meia + f * f) / (2.0 * f)
    alfa = math.asin(min(1.0, meia / raio))
    centro_z = E / 2.0 + f - raio
    n = SEGMENTOS_ARCO_CHAPA
    angulos = [-alfa + 2.0 * alfa * k / n for k in range(n + 1)]
    fora = [(raio * math.sin(a), centro_z + raio * math.cos(a)) for a in angulos]
    dentro = [((raio - E) * math.sin(a), centro_z + (raio - E) * math.cos(a))
              for a in angulos]
    secao = fora + dentro[::-1]
    bm = bmesh.new()
    try:
        pontas = [[bm.verts.new((x, y, z)) for x, z in secao] for y in (-C / 2.0, C / 2.0)]
        m = len(secao)
        for i in range(m):
            j = (i + 1) % m
            face = bm.faces.new((pontas[0][i], pontas[0][j], pontas[1][j], pontas[1][i]))
            # os dois arcos lisos; as pontas (i = n e i = m-1) retas
            face.smooth = i != n and i != m - 1
        # tampas em quadrados (a secao em arco nao e' convexa)
        for lado in pontas:
            for k in range(n):
                quad = (lado[k], lado[k + 1], lado[m - 2 - k], lado[m - 1 - k])
                bm.faces.new(quad)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(obj.data)
    finally:
        bm.free()
    obj.data.update()


def gerar_malha_chapa(obj):
    """Malha REAL via bmesh -> editavel em Edit Mode.
    X local = largura | Y local = comprimento | Z local = ESPESSURA.

    Nao existe mais "Auto-regenerar" (pedido do usuario: toda mudanca
    na chapa e' para ficar). Caixa padrao e' refeita; malha modelada no
    Modo Edicao e' ESTICADA (`_esticar_malha`), nunca substituida."""
    if (obj is None or obj.type != 'MESH' or obj.mode == 'EDIT'
            or obj.data.is_editmode):
        return
    L = obj.chapa_largura_mm / 1000.0
    C = obj.chapa_comprimento_mm / 1000.0
    E = obj.chapa_espessura_mm / 1000.0
    if obj.get('chapa_canais') or obj.get('chapa_quadro_mm') or obj.get('chapa_arco_mm'):
        if obj.get('chapa_canais'):
            # base do trilho leve: refeita COM os canais (nao e' caixa, mas
            # tambem nao foi modelada -- esticar levaria os canais junto)
            _malha_com_canais(obj, L, C, E)
        elif obj.get('chapa_quadro_mm'):
            _malha_quadro(obj, L, C, E)
        else:
            _malha_arco(obj, L, C, E)
        _frentes.preparar(obj)
        # o perfil numa folha Quadro/Arco tambem acompanha a malha nova
        for filho in obj.children:
            if _puxadores._eh_puxador_parametrico(filho):
                _puxadores.posicionar_puxador(filho)
        return
    if not _malha_e_caixa(obj.data):
        # Na folha curva o Z da malha e' a FLECHA do arco, nao a
        # espessura da madeira. Reaplicar parametros nao pode achata-la.
        profundidade = (max(v.co.z for v in obj.data.vertices)-min(v.co.z for v in obj.data.vertices)
                        if obj.get('porta_curva_modelada') else E)
        _esticar_malha(obj, (L, C, profundidade))
        _frentes.preparar(obj)
        for filho in obj.children:
            if _puxadores._eh_puxador_parametrico(filho):
                _puxadores.posicionar_puxador(filho)
        return
    bm = bmesh.new()
    # A caixa foi reconstruida: seus indices de faces pertencem a outra
    # topologia. A superficie sera reconhecida geometricamente uma vez.
    for chave in (_frentes.ATR_FACE,_frentes.ATR_BORDA):
        atributo = obj.data.attributes.get(chave)
        if atributo is not None:
            obj.data.attributes.remove(atributo)
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co.x *= L
        v.co.y *= C
        v.co.z *= E
    # Perfil filho: a faixa dele sai da MALHA, as props seguem nominais
    # (medida da porta, adjacencia e HUD leem as props, nao a malha).
    rebaixos = _puxadores._rebaixos_da_chapa(obj)
    for borda, corte in rebaixos.items():
        eixo = 0 if borda.startswith('X') else 1
        sinal = 1.0 if borda.endswith('+') else -1.0
        meia = (L if eixo == 0 else C) / 2.0
        corte = min(corte, meia * 2.0 - 0.001)
        for v in bm.verts:
            if v.co[eixo] * sinal > 0:
                v.co[eixo] = sinal * (meia - corte)
    bm.to_mesh(obj.data)
    bm.free()
    _solda._gravar_cantos(obj)
    obj.data.update()
    if rebaixos:
        obj['chapa_rebaixos'] = ','.join(sorted(rebaixos))
    elif 'chapa_rebaixos' in obj:
        del obj['chapa_rebaixos']
    _frentes.preparar(obj, forcar=True)
    # puxadores parametricos acompanham a chapa nova
    for filho in obj.children:
        if _puxadores._eh_puxador_parametrico(filho):
            _puxadores.posicionar_puxador(filho)


def _upd_chapa(self, context):
    if _ocupado[0]:
        return
    gerar_malha_chapa(self)


def _espessura_da_malha(obj):
    """Espessura REAL da malha, em mm. Quando o callback de update roda a
    PROP ja' foi trocada mas a malha ainda e' a antiga -- e' dela que sai
    a medida velha, necessaria para saber para que lado engrossar."""
    if obj is None or obj.type != 'MESH' or not obj.data.vertices:
        return None
    secao=_secao_espessura(obj.data)
    if secao:return secao['espessura_mm']
    if not _malha_e_caixa(obj.data):
        ref=obj.data.get(_frentes.CHAVE)
        return float(ref['espessura'])*1000 if ref and ref.get('espessura') else None
    # sem multiplicar por scale.z: por invariante a escala em Z e'
    # descartada, entao a malha local e' o valor antigo da prop
    zs = [v.co.z for v in obj.data.vertices]
    return (max(zs) - min(zs)) * 1000.0


def _upd_espessura(self, context):
    """Grava a espessura LIVRE (`_espessura_livre`, sem arredondar) e
    engrossa a chapa para DENTRO do movel
    (ver `_modulos.aplicar_espessura_chapa`)."""
    if _ocupado[0]:
        return
    val = self.chapa_espessura_mm
    alvo = _espessura_livre(val)
    e_velha = _espessura_da_malha(self)
    if abs(val - alvo) > 1e-6:
        _ocupado[0] = True
        try:
            self.chapa_espessura_mm = alvo
        finally:
            _ocupado[0] = False
    # Folha de porta nao engrossa para dentro do modulo: a porta inteira
    # e' refeita com a espessura nova (ver `_portas._espessura_da_folha_mudou`).
    if MARCA_FOLHA in self and _portas._espessura_da_folha_mudou(self, alvo):
        return
    # Peca da moldura: o E vale para a moldura inteira (pedido do usuario:
    # editavel), gravado na porta, que refaz as seis pecas
    if MARCA_MOLDURA in self and _portas._espessura_da_moldura_mudou(self, alvo):
        return
    if (MARCA_CHAPA not in self
            or e_velha is None or abs(e_velha - alvo) < 1e-4):
        gerar_malha_chapa(self)
        return
    _modulos.aplicar_espessura_chapa(self, alvo, e_velha)


# ===================================================== NORMALIZACAO
def normalizar_chapas(objs=None):
    """Converte a escala acumulada em cada chapa em MEDIDA (mm) e zera
    a escala de volta para 1.

    REGRA CENTRAL: o componente Z local (espessura) e' DESCARTADO, nao
    convertido. Como Z local e' sempre a espessura -- esteja a peca
    deitada ou em pe' -- a espessura fica imune a escala em QUALQUER
    eixo do mundo.

    Devolve a lista de pecas ajustadas.
    """
    if objs is None:
        objs = bpy.data.objects
    alvos = []
    for obj in objs:
        if (obj.type != 'MESH' or MARCA_CHAPA not in obj or obj.mode == 'EDIT'
                or obj.data.is_editmode):
            continue
        pai = obj.parent
        while pai is not None:
            if MARCA_CONJUNTO in pai and any(abs(abs(s)-1)>1e-6 for s in pai.scale):
                break
            pai = pai.parent
        if pai is not None:
            # Escala do modulo com internos ainda aguarda o timer. Nao
            # incorporar a escala herdada em cada chapa antes do encaixe.
            continue
        sx, sy, sz = obj.scale
        if abs(sx - 1) < 1e-6 and abs(sy - 1) < 1e-6 and abs(sz - 1) < 1e-6:
            continue
        alvos.append((obj, sx, sy, sz))
    if not alvos:
        return []

    _ocupado[0] = True
    try:
        for obj, sx, sy, sz in alvos:
            obj.chapa_largura_mm = obj.chapa_largura_mm * sx
            obj.chapa_comprimento_mm = obj.chapa_comprimento_mm * sy
            # sz (espessura) deliberadamente IGNORADO
            obj.scale = (1.0, 1.0, 1.0)
    finally:
        _ocupado[0] = False

    for obj, _sx, _sy, _sz in alvos:
        gerar_malha_chapa(obj)

    # fecha os vaos abertos pela aritmetica da escala
    try:
        aplicar_adjacencia()
    except Exception as e:
        print("[Archy Builder] adjacencia:", e)

    return [o for o, _a, _b, _c in alvos]


# Chapas que estavam em Modo Edicao no ultimo tique do timer (por nome)
_chapas_em_edicao = set()


def preparar_uvs_chapa(obj):
    """Mapa metrico inicial: uma unidade UV por metro, sem alterar mapas existentes."""
    if (obj.type != 'MESH' or MARCA_CHAPA not in obj or obj.data.is_editmode
            or obj.data.uv_layers):
        return False
    uv = obj.data.uv_layers.new(name='UVMap')
    for face in obj.data.polygons:
        normal = face.normal
        eixo = Vector((1, 0, 0)) if abs(normal.x) < .9 else Vector((0, 1, 0))
        u = (eixo - normal * eixo.dot(normal)).normalized()
        v = normal.cross(u).normalized()
        for indice in face.loop_indices:
            co = obj.data.vertices[obj.data.loops[indice].vertex_index].co
            uv.data[indice].uv = (co.dot(u), co.dot(v))
    obj.data.update()
    return True


def absorver_edicoes_de_malha():
    """Chapa que acabou de SAIR do Modo Edicao: a malha que o usuario
    mexeu vira medida (`absorver_malha_editada`).

    A HUD, a gaveta e a adjacencia leem as PROPS, nao a malha. Esticar
    um lado no Modo Edicao deixava o contorno da HUD com a medida velha
    (print do usuario). Chapas comuns usam so' a transicao; molduras
    tambem recuperam medidas antigas divergentes pela caixa nativa.
    """
    agora, saidas = set(), []
    for obj in bpy.data.objects:
        if obj.type != 'MESH' or (MARCA_CHAPA not in obj
                and not _puxadores._eh_puxador_parametrico(obj)):
            continue
        if obj.mode == 'EDIT':
            agora.add(obj.name)
        elif obj.name in _chapas_em_edicao:
            saidas.append(obj)
        elif (MARCA_MOLDURA in obj and not obj.get('chapa_rebaixos')
                and obj.data.vertices and not obj.data.is_editmode
                and all(abs(s-1)<1e-6 for s in obj.scale)):
            # Cenas ja' editadas perderam a transicao do Tab. A caixa
            # nativa permite reconhecer a divergencia sem reler a malha.
            lo,hi=(Vector(obj.bound_box[i]) for i in (0,6))
            tamanho=(hi-lo)*1000
            if (abs(tamanho.x-obj.chapa_largura_mm)>.01
                    or abs(tamanho.y-obj.chapa_comprimento_mm)>.01
                    or (lo+hi).length>2e-7):
                saidas.append(obj)
    anteriores = _chapas_em_edicao.copy()
    _chapas_em_edicao.clear()
    _chapas_em_edicao.update(agora)
    if saidas:
        # Mover vertices internos nao muda necessariamente L/A/E nem
        # a contagem de vertices que participa da assinatura da planta.
        _formas.esquecer()
    for obj in saidas:
        try:
            if _puxadores._eh_puxador_parametrico(obj):
                _puxadores.atualizar_contorno(obj)
                continue
            absorver_malha_editada(obj)
            _frentes.preparar(obj)
            for filho in obj.children:
                # No Tab do grupo a geometria do puxador ja' acompanhou
                # o gesto nativo. Recria-la anulava o movimento confirmado.
                if (_puxadores._eh_puxador_parametrico(filho)
                        and filho.name not in anteriores):
                    _puxadores.posicionar_puxador(filho)
        except Exception as e:
            print("[Archy Builder] absorver edicao:", e)


def _alinhar_plano_da_chapa(obj):
    """Reexpressa uma chapa plana no seu plano real, sem mudar MUNDO.
    AABB Z de uma chapa inclinada por Tab nao e' sua espessura. Somente
    duas superficies paralelas permitem essa troca de referencial.
    """
    malha=obj.data
    if not malha.polygons:return False
    face=max(malha.polygons,key=lambda f:f.area)
    normal=face.normal.copy()
    if normal.z<0:normal.negate()
    if normal.z<.2 or normal.z>.99999:return False
    distancias=[v.co.dot(normal) for v in malha.vertices]
    lo,hi=min(distancias),max(distancias)
    if hi-lo<1e-9 or any(min(abs(d-lo),abs(d-hi))>1e-5 for d in distancias):
        return False
    ey=Vector((0,1,0));ey=(ey-normal*ey.dot(normal)).normalized()
    ex=ey.cross(normal).normalized()
    rotacao=Matrix((ex,ey,normal)).transposed().to_4x4()
    usuarios=[o for o in bpy.data.user_map(subset={malha}).get(malha,())
              if isinstance(o,bpy.types.Object)]
    poses={o:o.matrix_world.copy() for o in usuarios}
    filhos={f:f.matrix_world.copy() for o in usuarios for f in o.children}
    malha.transform(rotacao.inverted())
    for o,m in poses.items():o.matrix_world=m@rotacao
    bpy.context.view_layer.update()
    for f,m in filhos.items():f.matrix_world=m
    malha.update()
    for o in usuarios:_frentes.invalidar(o)
    return True


def absorver_malha_editada(obj, reorientar=True):
    """Caixa local da malha -> largura/comprimento/espessura; a origem
    volta ao centro da caixa SEM a peca sair do lugar no mundo.

    Folha de porta fica de fora (edita-se pelo grupo), e chapa com perfil
    tambem: a faixa do perfil e' cortada de proposito so' na malha.
    Devolve True se mudou algo.
    """
    if (obj.mode == 'EDIT' or obj.data.is_editmode or
            MARCA_FOLHA in obj or obj.get('chapa_rebaixos')
            or not obj.data.vertices
            or any(abs(s - 1.0) > 1e-6 for s in obj.scale)):
        return False
    reorientada = _alinhar_plano_da_chapa(obj) if reorientar else False
    cos = [v.co for v in obj.data.vertices]
    lo = Vector([min(c[i] for c in cos) for i in range(3)])
    hi = Vector([max(c[i] for c in cos) for i in range(3)])
    tamanho = (hi - lo) * 1000.0
    centro = (lo + hi) / 2.0
    usuarios=[o for o in bpy.data.user_map(subset={obj.data}).get(obj.data,())
              if isinstance(o,bpy.types.Object)]
    chapas=[o for o in usuarios if MARCA_CHAPA in o]
    secao=_secao_espessura(obj.data)
    espessura=(secao['espessura_mm'] if secao else
               max(1e-6,tamanho.z) if reorientada else obj.chapa_espessura_mm)
    medidas=(tamanho.x,tamanho.y,espessura)
    if (not reorientada and all(all(abs(t-a)<.01 for t,a in zip(medidas,
            (o.chapa_largura_mm,o.chapa_comprimento_mm,o.chapa_espessura_mm))) for o in chapas)
            and centro.length < 1e-7):
        return False
    if centro.length >= 1e-7:
        # Filhos (puxador importado, acessorio) ficam onde estavam; o
        # parametrico e' refeito pelas props em gerar_malha_chapa.
        filhos = {f:f.matrix_world.copy() for o in usuarios for f in o.children}
        mundos = {o:o.matrix_world.copy() for o in usuarios}
        obj.data.transform(Matrix.Translation(-centro))
        for o,mundo in mundos.items():o.matrix_world=mundo@Matrix.Translation(centro)
        bpy.context.view_layer.update()
        for filho, matriz in filhos.items():
            filho.matrix_world = matriz
    preparar_espessura(obj)
    _ocupado[0] = True
    try:
        for o in chapas:
            o.chapa_largura_mm = tamanho.x
            o.chapa_comprimento_mm = tamanho.y
            o.chapa_espessura_mm = espessura
    finally:
        _ocupado[0] = False
    # A geometria ja' e' a que o usuario confirmou no Edit Mode.
    # Esse caminho nao pode reconstruir buffers que o undo nativo ainda
    # conserva. Absorver so' atualiza medidas/referencias.
    _frentes.invalidar(obj)
    obj.data.update()
    return True


# ============================= HANDLER: age SO' depois do modal acabar
@bpy.app.handlers.persistent
def ao_atualizar_depsgraph(scene, depsgraph):
    """A chapa deforma normalmente durante o arraste do S (a ferramenta
    nativa do Blender trabalha sem interferencia). Assim que o operador
    modal termina -- Enter, clique ou Esc -- este handler detecta a
    transicao e recalcula todas as chapas de uma vez.

    Mexer na escala DURANTE o modal nao funciona: o operador guarda a
    escala inicial em cache e reaplica o fator a cada movimento do
    mouse, entao qualquer correcao feita no meio do arraste e'
    sobrescrita no quadro seguinte.
    """
    if _ocupado[0] or _eventos._desfazendo[0]:
        # logo apos um undo os dados acabaram de voltar (ver
        # `_eventos._depois_de_desfazer`): nada a recalcular, e mexer aqui derrubava
        return
    for atualizacao in depsgraph.updates if depsgraph is not None else ():
        dado = atualizacao.id
        if (isinstance(dado, bpy.types.Object) and dado.type == 'MESH'
                and MARCA_CHAPA in dado and atualizacao.is_updated_geometry):
            _frentes.invalidar(dado.original, conferir=True)
    # trocar a selecao tambem passa por aqui: o contorno acompanha na
    # hora, sem esperar o timer
    _eventos.sincronizar_contornos()
    # apagou/duplicou algo: as ferragens das portas se conferem depois
    # (num timer: remover objeto dentro do handler do depsgraph nao)
    contagem = (len(bpy.data.objects), tuple((s.name, len(s.objects)) for s in bpy.data.scenes))
    anterior = _ferragens._contagem_objetos[0]
    if contagem != anterior:
        _solda._normalizar_pendente[0] = True
        surgiu = anterior is not None and contagem[0] > anterior[0]
        _ferragens._contagem_objetos[0] = contagem
        if not bpy.app.timers.is_registered(_ferragens._conferir_ferragens):
            bpy.app.timers.register(_ferragens._conferir_ferragens, first_interval=0.0)
        # Ctrl+D numa chapa: a copia sai com identidade propria e sem as
        # soldas da original (pedido do usuario)
        if surgiu and not bpy.app.timers.is_registered(_separar_copias_no_timer):
            bpy.app.timers.register(_separar_copias_no_timer, first_interval=0.0)

    modal_ativo = _eventos._ha_modal_ativo()

    if modal_ativo:
        _havia_modal[0] = True     # arraste em andamento: nao tocar
        return

    # o modal acabou, ou nunca houve (escala por script/painel): recalcula tudo
    _havia_modal[0] = False
    _modulos.absorver_conjuntos()
    normalizar_chapas()



# ===================================================== ADJACENCIA
# Guarda, para cada ponta da chapa (X- X+ Y- Y+), qual peca vizinha ela
# encosta e qual era a folga no momento da deteccao. Depois de qualquer
# recalculo, a chapa e' esticada/encurtada para reencontrar a mesma
# folga -- fechando o vao que a aritmetica da escala abre.
#
# O vao aparece porque, ao escalar por F, a POSICAO das laterais e' multi-
# plicada por F mas a ESPESSURA delas nao. Por lado: vao = (E/2)*(F-1).
PONTAS = ("x_neg", "x_pos", "y_neg", "y_pos")
TOL_ENCOSTE = 0.06   # 60mm: distancia maxima para considerar vizinhanca


def _garantir_uid(obj):
    """Identificador estavel da chapa. Necessario porque a adjacencia
    guardada por NOME quebra ao trazer um modulo da biblioteca: os nomes
    ganham sufixo (.001) e os vinculos apontariam para a peca errada."""
    if not obj.get("chapa_uid"):
        obj["chapa_uid"] = uuid.uuid4().hex[:12]
    return obj["chapa_uid"]


def _resolver_vizinho(C, uid, nome):
    """Procura o vizinho primeiro entre os IRMAOS (mesmo pai), para que
    copias de um mesmo modulo nao se confundam entre si."""
    if uid:
        # O nome so' atesta um irmao com aquele UID; evita buscar a cena
        # de novo por junta e nao troca a identidade pela copia mais proxima.
        gravado = bpy.data.objects.get(nome) if nome else None
        if (gravado is not None and gravado.parent == C.parent
                and gravado.get("chapa_uid") == uid):
            return gravado
        irmaos = [o for o in (C.parent.children if C.parent else bpy.data.objects)
                  if o.parent == C.parent and o.get("chapa_uid") == uid]
        if len(irmaos) == 1:
            return irmaos[0]
        if len(irmaos) > 1:
            return min(irmaos, key=lambda o: (o.location - C.location).length)
    if nome and nome in bpy.data.objects:
        return bpy.data.objects[nome]
    return None


def _eixos(obj):
    """Eixos locais expressos em MUNDO. Usar rotation_euler (local) aqui
    quebrava assim que o Empty pai saia da origem: o espaco de
    referencia deixava de coincidir com o mundo e o teste de 'face
    encostada no limite' parava de reconhecer as pecas."""
    m = obj.matrix_world.to_3x3()
    return m.col[0].normalized(), m.col[1].normalized(), m.col[2].normalized()


def _centro(obj):
    return obj.matrix_world.translation.copy()


def _definir_centro(obj, novo):
    """Grava um centro de MUNDO respeitando pai e matrix_parent_inverse."""
    if obj.parent is not None:
        base = obj.parent.matrix_world @ obj.matrix_parent_inverse
        obj.location = base.inverted() @ novo
    else:
        obj.location = novo


def _meias(obj):
    return (obj.chapa_largura_mm / 2000.0,
            obj.chapa_comprimento_mm / 2000.0,
            obj.chapa_espessura_mm / 2000.0)


def _cantos(obj):
    ex, ey, ez = _eixos(obj)
    hx, hy, hz = _meias(obj)
    c = _centro(obj)
    pts = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            for sz in (-1, 1):
                pts.append(c + ex * (sx * hx) + ey * (sy * hy) + ez * (sz * hz))
    return pts


def _faixa(obj, d):
    p = [v.dot(d) for v in _cantos(obj)]
    return min(p), max(p)


def _sobrepoe(a, b, folga=1e-4):
    return (a[0] < b[1] + folga) and (b[0] < a[1] + folga)


# Conexao AUTOMATICA (botao Corrente, "conectar por distancia") so' ate'
# aqui (pedido do usuario). Mais longe ja' e' "selecionar vertice". O
# detectar_adjacencia (agrupar o modulo) segue com o TOL_ENCOSTE.
ALCANCE_CONEXAO_AUTOMATICA = 0.005


def _melhor_vizinho(C, eixo, lado, candidatos, alcance=None):
    """(vizinho, folga, face) mais proximo da ponta eixo/lado de C entre
    os `candidatos`, ou None. Mesma regra do detectar_adjacencia; o
    `alcance` (m) troca o TOL_ENCOSTE."""
    limite = TOL_ENCOSTE if alcance is None else alcance
    ex, ey, ez = _eixos(C)
    hx, hy, _hz = _meias(C)
    u, h = (ex, hx) if eixo == "x" else (ey, hy)
    perp = [w for w in (ex, ey, ez) if w is not u]
    ponta = _centro(C).dot(u) + (h if lado == "pos" else -h)
    melhor = None
    for N in candidatos:
        if N is C or N.type != 'MESH' or MARCA_CHAPA not in N:
            continue
        # so' considera vizinho que se sobrepoe nas outras direcoes
        # Quinas/arestas coincidentes nao sao uma face de apoio. A regra
        # inclusiva criava ate' quatro soldas para a mesma quina.
        modulo = C.parent is not None and MARCA_CONJUNTO in C.parent
        if not all((min(_faixa(C, w)[1], _faixa(N, w)[1]) -
                    max(_faixa(C, w)[0], _faixa(N, w)[0]) > 1e-5) if modulo else
                   _sobrepoe(_faixa(C, w), _faixa(N, w)) for w in perp):
            continue
        faces = _faixa(N, u)   # (min, max) do vizinho na direcao u
        # Ancora na face do vizinho MAIS PROXIMA da ponta.
        # Usar sempre a face distante embutia a espessura
        # antiga na folga: ao trocar a espessura, a peca era
        # empurrada para fora e o modulo crescia sozinho.
        i_face = 0 if abs(faces[0] - ponta) <= abs(faces[1] - ponta) else 1
        folga = (faces[i_face] - ponta) if lado == "pos" else (ponta - faces[i_face])
        if folga < -limite or folga > limite + 1e-9:
            continue
        if melhor is None or abs(folga) < abs(melhor[1]):
            melhor = (N, folga, i_face)
    return melhor


def _gravar_ligacao(C, eixo, lado, N, folga, face):
    existente = _solda._ligacao_entre(C, N)
    ponta = '%s_%s' % (eixo, lado)
    if existente is not None and existente[0].get('adj_%s_manual'%existente[1]):
        return False
    if existente is not None and existente != (C, ponta):
        dono, antiga = existente
        vizinho = _solda._vizinho_da_ponta(dono, antiga)
        _solda._gravar_restricoes(dono, antiga, vizinho,
            _solda._restricoes_da_ligacao(dono, antiga, vizinho) + [(C, ponta, N, int(face), float(folga))])
        return False
    restricoes = _solda._restricoes_da_ligacao(C, ponta, N) if existente else []
    for sufixo in ('_ancoras','_origens','_manual','_direcoes'):
        if f"adj_{eixo}_{lado}{sufixo}" in C:
            del C[f"adj_{eixo}_{lado}{sufixo}"]   # solda nova: nao herda a origem anterior
    C[f"adj_{eixo}_{lado}"] = N.name
    C[f"adj_{eixo}_{lado}_uid"] = _garantir_uid(N)
    C[f"adj_{eixo}_{lado}_folga"] = float(folga)
    C[f"adj_{eixo}_{lado}_face"] = int(face)
    _solda._gravar_restricoes(C, ponta, N, restricoes)
    return True


def detectar_adjacencia(objs):
    """Para cada ponta de cada chapa, acha a peca vizinha mais proxima
    naquela direcao e memoriza a folga atual."""
    chapas = sorted((o for o in objs if o.type == 'MESH' and MARCA_CHAPA in o
                     and not eh_dependente(o)), key=lambda o: o.name)
    for c in chapas:
        _garantir_uid(c)
    n = 0
    for C in chapas:
        _limpar_pontas(C)  # UID antigo tambem precisa sair: nome vazio nao desliga.
    for C in chapas:
        for eixo in ("x", "y"):
            for lado in ("pos", "neg"):
                achado = _melhor_vizinho(C, eixo, lado, chapas)
                if achado is not None:
                    n += int(_gravar_ligacao(C, eixo, lado, *achado))
    return n


def otimizar_adjacencia(objs):
    """Revalida soldas automaticas da montagem; conserva ancoras manuais.
    Usado ao migrar presets, nunca no desenho nem durante um arraste.
    """
    chapas = [o for o in objs if o.type == 'MESH' and MARCA_CHAPA in o]
    candidatas = [o for o in chapas if not eh_dependente(o)]
    antes = {o.name: repr(sorted((k, str(v)) for k, v in o.items()
                                if k.startswith('adj_'))) for o in chapas}
    planos = []
    for C in chapas:
        for ponta in PONTAS:
            if _solda._ancoras_gravadas(C, ponta):
                continue
            eixo, lado = ponta.split('_')
            achado = None if eh_dependente(C) else _melhor_vizinho(C, eixo, lado, candidatas)
            planos.append((C, ponta, achado))
    # Limpar depois de planejar TODOS os objetos evita apagar uma aresta
    # que acabou de receber os encaixes do outro extremo.
    for C, ponta, _achado in planos:
        _limpar_ponta(C, ponta)
    for C, ponta, achado in sorted(planos, key=lambda p: (p[0].name, p[1])):
        if achado is not None:
            eixo, lado = ponta.split('_')
            _gravar_ligacao(C, eixo, lado, *achado)
    return [o.name for o in chapas if antes[o.name] != repr(sorted(
        (k, str(v)) for k, v in o.items() if k.startswith('adj_')))]


def associar_por_distancia(C, vizinhos, alcance=None):
    """Liga UMA peca aos vizinhos ao alcance, sem recalcular as outras
    ligacoes deles (detectar_adjacencia zera tudo de quem recebe e
    perderia, por exemplo, a ligacao de um modulo com o vizinho de fora).
    As pontas de C sao refeitas; nos vizinhos, so' pontas VAZIAS ganham
    ligacao com C. Devolve quantas pontas ligou."""
    vizinhos = [v for v in vizinhos if v is not C and MARCA_CHAPA in v
                and not eh_dependente(v)]
    _garantir_uid(C)
    n = 0
    for eixo in ("x", "y"):
        for lado in ("pos", "neg"):
            achado = _melhor_vizinho(C, eixo, lado, vizinhos, alcance)
            if achado is not None:
                n += int(_gravar_ligacao(C, eixo, lado, *achado))
    for V in vizinhos:
        for eixo in ("x", "y"):
            for lado in ("pos", "neg"):
                if _solda._vizinho_da_ponta(V, "%s_%s" % (eixo, lado)) is not None:
                    continue
                achado = _melhor_vizinho(V, eixo, lado, [C], alcance)
                if achado is not None:
                    n += int(_gravar_ligacao(V, eixo, lado, *achado))
    return n


def _limpar_ponta(C, ponta):
    """Tira a solda de UMA ponta (ela deixa de puxar vizinho)."""
    C[f"adj_{ponta}"] = ""
    C[f"adj_{ponta}_folga"] = 0.0
    for sufixo in ("_uid", "_face", "_ancoras", "_origens", "_manual", "_direcoes", "_restricoes"):
        if f"adj_{ponta}{sufixo}" in C:
            del C[f"adj_{ponta}{sufixo}"]


def _limpar_pontas(C):
    for k in PONTAS:
        _limpar_ponta(C, k)


def _copias_com_mesmo_uid(objs=None):
    """{(pai, uid): [chapas]} dos IRMAOS que dividem a identidade -- o
    rastro do Ctrl+D numa chapa (a copia leva o `chapa_uid` e as soldas
    da original). Modulo duplicado inteiro nao entra: o pai e' outro."""
    grupos = {}
    for o in (bpy.data.objects if objs is None else objs):
        uid = o.get("chapa_uid")
        if uid and o.type == 'MESH' and MARCA_CHAPA in o:
            grupos.setdefault((o.parent, uid), []).append(o)
    return {k: v for k, v in grupos.items() if len(v) > 1}


def _original_entre(copias):
    """A que fica com a identidade: a que NAO esta' selecionada (o Ctrl+D
    seleciona so' as copias) ou, empatando, o nome sem sufixo maior."""
    def chave(o):
        try:
            selecionada = o.select_get()
        except Exception:
            selecionada = False
        return (selecionada, o.name.rpartition('.')[2].isdigit(), o.name)
    return min(copias, key=chave)


def separar_copias(objs=None):
    """Cada copia ganha identidade propria e sai SEM as soldas da original
    (pedido do usuario: as ligacoes ficavam apontando para os vizinhos da
    outra e a chapa esticava errado). Quem soldava na original continua
    soldado nela. Devolve as copias separadas."""
    separadas = []
    for copias in _copias_com_mesmo_uid(objs).values():
        original = _original_entre(copias)
        for C in copias:
            if C is original:
                continue
            C["chapa_uid"] = uuid.uuid4().hex[:12]
            _limpar_pontas(C)
            separadas.append(C)
    return separadas


def _separar_copias_no_timer():
    """Timer do Ctrl+D (registrado pelo handler quando surge objeto):
    mexer em ID prop dentro do handler do depsgraph nao."""
    try:
        if not _eventos._desfazendo[0]:
            separar_copias()
    except Exception as erro:
        print("[Archy Builder] separar copias:", erro)
    return None


def recalcular_ancoragem(chapas):
    """Refaz as soldas das `chapas` pelo lugar onde estao AGORA (comando
    "Recalcular ancoragem", pedido do usuario): copia separada da
    original, pontas zeradas e religadas a quem encosta (ate'
    ALCANCE_CONEXAO_AUTOMATICA) entre as irmas e as outras escolhidas.
    Nos vizinhos que ficam de fora, so' pontas vazias ou que apontavam
    para uma das refeitas ganham ligacao. Devolve quantas pontas ligou."""
    chapas = [c for c in chapas if c.type == 'MESH' and MARCA_CHAPA in c
              and MARCA_FOLHA not in c and MARCA_MOLDURA not in c]
    if not chapas:
        return 0
    separar_copias(chapas + [o for o in bpy.data.objects
                             if o.parent in {c.parent for c in chapas}])
    refeitas = set(chapas)
    for C in chapas:
        _garantir_uid(C)
        _limpar_pontas(C)
    candidatos = set(chapas)
    for C in chapas:
        candidatos.update(o for o in bpy.data.objects if o.parent == C.parent
                          and o.type == 'MESH' and MARCA_CHAPA in o
                          and MARCA_FOLHA not in o and MARCA_MOLDURA not in o)
    candidatos = list(candidatos)
    n = 0
    for C in chapas:
        for eixo in ("x", "y"):
            for lado in ("pos", "neg"):
                achado = _melhor_vizinho(C, eixo, lado, candidatos,
                                         ALCANCE_CONEXAO_AUTOMATICA)
                if achado is not None:
                    n += int(_gravar_ligacao(C, eixo, lado, *achado))
    for V in candidatos:
        if V in refeitas:
            continue
        for eixo in ("x", "y"):
            for lado in ("pos", "neg"):
                ponta = "%s_%s" % (eixo, lado)
                atual = _solda._vizinho_da_ponta(V, ponta)
                if atual is not None and atual not in refeitas:
                    continue
                achado = _melhor_vizinho(V, eixo, lado, chapas,
                                         ALCANCE_CONEXAO_AUTOMATICA)
                if achado is not None:
                    n += int(_gravar_ligacao(V, eixo, lado, *achado))
                elif atual is not None:
                    # apontava para uma refeita que nao encosta mais
                    _limpar_ponta(V, ponta)
    return n


def _chapas_candidatas(C, candidatos=None):
    """As outras chapas da cena, ou so' as `candidatos` (os alvos
    selecionados antes da peca de fora)."""
    fonte = bpy.data.objects if candidatos is None else candidatos
    return [o for o in fonte
            if o is not C and o.type == 'MESH' and MARCA_CHAPA in o]


def _vizinhos_por_distancia(C, alcance=ALCANCE_CONEXAO_AUTOMATICA,
                            candidatos=None):
    """Chapas que ficariam ligadas a C por distancia (sem gravar nada):
    as que as pontas de C alcancam e as que alcancam C."""
    outras = _chapas_candidatas(C, candidatos)
    achados = set()
    for eixo in ("x", "y"):
        for lado in ("pos", "neg"):
            achado = _melhor_vizinho(C, eixo, lado, outras, alcance)
            if achado is not None:
                achados.add(achado[0])
    for V in outras:
        if V in achados:
            continue
        if any(_melhor_vizinho(V, e, l, [C], alcance) is not None
               for e in ("x", "y") for l in ("pos", "neg")):
            achados.add(V)
    return achados


def aplicar_adjacencia(objs=None):
    """Estica/encurta cada chapa nos eixos de largura e comprimento
    para reencontrar a folga memorizada com seus vizinhos."""
    if objs is None:
        objs = bpy.data.objects
    chapas = [o for o in objs if o.type == 'MESH' and MARCA_CHAPA in o
              and o.mode != 'EDIT' and not eh_dependente(o)]
    ajustadas = []
    restricoes = _solda.restricoes_adjacencia(chapas)
    _ocupado[0] = True
    try:
        for C in chapas:
            ex, ey, ez = _eixos(C)
            mudou = False
            # Centro mantido AQUI entre os eixos: relido de matrix_world, o
            # passo em Y perdia o deslocamento do X (matriz defasada, sem
            # view_layer.update -- que nao pode rodar dentro do handler).
            centro = _centro(C)
            for eixo, u in (("x", ex), ("y", ey)):
                hx, hy, hz = _meias(C)
                h = hx if eixo == "x" else hy
                centro_u = centro.dot(u)
                p_pos, p_neg = centro_u + h, centro_u - h
                alvo_pos, alvo_neg = p_pos, p_neg

                N, fp, folga_pos = restricoes[C].get(eixo+'_pos', (None, 0, 0.))
                if N is not None and N.parent!=C.parent and (N.get('eh_prateleira') or N.get('gaveta_peca')):
                    N = None   # antiga chapa integrada nao puxa mais a caixa
                if N is not None:
                    alvo_pos = _faixa(N, u)[fp] - folga_pos
                N, fn, folga_neg = restricoes[C].get(eixo+'_neg', (None, 1, 0.))
                if N is not None and N.parent!=C.parent and (N.get('eh_prateleira') or N.get('gaveta_peca')):
                    N = None
                if N is not None:
                    alvo_neg = _faixa(N, u)[fn] + folga_neg

                novo_h = (alvo_pos - alvo_neg) / 2.0
                if novo_h <= 0.0005:
                    continue
                novo_centro_u = (alvo_pos + alvo_neg) / 2.0
                if abs(novo_h - h) < 1e-7 and abs(novo_centro_u - centro_u) < 1e-7:
                    continue

                if eixo == "x":
                    C.chapa_largura_mm = novo_h * 2000.0
                else:
                    C.chapa_comprimento_mm = novo_h * 2000.0
                centro = centro + u * (novo_centro_u - centro_u)
                _definir_centro(C, centro)
                mudou = True
            if mudou:
                ajustadas.append(C)
    finally:
        _ocupado[0] = False

    for C in ajustadas:
        gerar_malha_chapa(C)
    return ajustadas


class OBJECT_OT_normalizar(Operator):
    """Recalcula as chapas selecionadas a partir da escala aplicada"""
    bl_idname = "object.cabinet_normalizar"
    bl_label = "Recalcular Chapas"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        alvo = context.selected_objects or bpy.data.objects
        ajustadas = normalizar_chapas(alvo)
        self.report({'INFO'}, "%d chapa(s) recalculada(s)" % len(ajustadas))
        return {'FINISHED'}


# ================================================== CRIACAO DE OBJETOS
def nova_chapa(nome, larg, comp, esp, loc_mm, rot_graus, context):
    malha = bpy.data.meshes.new(nome)
    obj = bpy.data.objects.new(nome, malha)
    context.collection.objects.link(obj)
    obj[MARCA_CHAPA] = 1
    _ocupado[0] = True
    try:
        obj.chapa_largura_mm = larg
        obj.chapa_comprimento_mm = comp
        obj.chapa_espessura_mm = esp
    finally:
        _ocupado[0] = False
    obj.location = tuple(v / 1000.0 for v in loc_mm)
    obj.rotation_euler = tuple(math.radians(a) for a in rot_graus)
    gerar_malha_chapa(obj)
    return obj


class OBJECT_OT_criar_chapa(Operator):
    """Cria uma chapa avulsa (600 x 400 x 18mm)"""
    bl_idname = "object.cabinet_criar"
    bl_label = "Criar Chapa"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = nova_chapa("Chapa", 600.0, 400.0, 18.0, (0, 0, 0), (0, 0, 0), context)
        for o in context.selected_objects:
            o.select_set(False)
        obj.select_set(True)
        context.view_layer.objects.active = obj
        return {'FINISHED'}


class OBJECT_OT_criar_nicho(Operator):
    """Cria um nicho sem fundo: 2 laterais + tampo + base"""
    bl_idname = "object.cabinet_criar_nicho"
    bl_label = "Criar Nicho (sem fundo)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        L, A, P, E = 600.0, 400.0, 300.0, 18.0
        li = L - 2 * E
        pecas = [
            ("Lateral_Esq", A, P, E, (-(L / 2 - E / 2), 0, A / 2), (0, 90, 0)),
            ("Lateral_Dir", A, P, E, ((L / 2 - E / 2), 0, A / 2), (0, 90, 0)),
            ("Base",        li, P, E, (0, 0, E / 2), (0, 0, 0)),
            ("Tampo",       li, P, E, (0, 0, A - E / 2), (0, 0, 0)),
        ]
        for o in context.selected_objects:
            o.select_set(False)
        criadas = [nova_chapa(n, la, c, e, lo, r, context) for n, la, c, e, lo, r in pecas]
        for c in criadas:
            c.select_set(True)
        context.view_layer.objects.active = criadas[0]
        return {'FINISHED'}


class OBJECT_OT_marcar_como_chapa(Operator):
    """Converte o objeto selecionado em chapa G3"""
    bl_idname = "object.cabinet_marcar"
    bl_label = "Marcar como Chapa"
    bl_options = {'REGISTER', 'UNDO'}

    alternar: BoolProperty(default=False, options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return context.object is not None and context.object.type == 'MESH'

    def execute(self, context):
        obj = context.object
        if self.alternar and MARCA_CHAPA in obj:
            if MARCA_FOLHA in obj:
                self.report({'WARNING'}, 'Folha parametrica: edite pelo grupo de portas')
                return {'CANCELLED'}
            # A conversao explicita preserva a malha e a hierarquia. Limpar
            # referencias evita que a adjacencia use a chapa ja' desativada.
            for chapa in bpy.data.objects:
                if MARCA_CHAPA not in chapa:
                    continue
                for ponta in PONTAS:
                    base = 'adj_' + ponta
                    vizinho = _resolver_vizinho(
                        chapa, chapa.get(base + '_uid', ''), chapa.get(base, ''))
                    if chapa == obj or vizinho == obj:
                        for sufixo in ('', '_uid', '_folga', '_face', '_ancoras', '_origens','_manual','_direcoes','_restricoes'):
                            if base + sufixo in chapa:
                                del chapa[base + sufixo]
            _ocupado[0] = True
            try:
                obj.chapa_auto = False
                del obj[MARCA_CHAPA]
            finally:
                _ocupado[0] = False
            return {'FINISHED'}
        # A medida sai da FORMA da peca (`converter_em_chapa`), nao de
        # `obj.dimensions` em eixos de mundo: assim uma lateral em pe'
        # vira chapa com a espessura certa e sem sair do lugar. Vale para
        # toda a selecao -- um armario importado tem dezenas de pecas.
        alvos = [o for o in context.selected_objects
                 if o.type == 'MESH' and MARCA_CHAPA not in o
                 and MARCA_PUXADOR not in o]
        if obj not in alvos and MARCA_CHAPA not in obj and MARCA_PUXADOR not in obj:
            alvos.append(obj)
        convertidas = [o for o in alvos if _importacao.converter_em_chapa(o) is not None]
        if not convertidas:
            self.report({'WARNING'}, "Nada com volume para converter")
            return {'CANCELLED'}
        if len(convertidas) == 1:
            c = convertidas[0]
            self.report({'INFO'}, "Chapa %.0f x %.0f x %.0f mm"
                        % (c.chapa_largura_mm, c.chapa_comprimento_mm,
                           c.chapa_espessura_mm))
        else:
            self.report({'INFO'}, "%d chapas convertidas" % len(convertidas))
        return {'FINISHED'}
