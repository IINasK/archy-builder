"""Panels: markers, BMesh geometry, free thickness, normalization,
depsgraph handler, world geometry, panel adjacency/welding and
operators for creating/marking panels."""

import bpy, bmesh, math, uuid
from bpy.props import BoolProperty
from mathutils import Matrix, Vector
from mathutils.kdtree import KDTree
from bpy.types import Operator

# Used only at runtime (circular imports): __init__ binds these
# aliases after loading all modules (`_ligar_modulos`).
_modulos = None
_eventos = None
_portas = None
_ferragens = None
_importacao = None
_puxadores = None
_solda = None
_frentes = None
_formas = None

# CONVENTIONAL thicknesses are only options/defaults for door enums.
# They no longer constrain the field: any thickness is valid, and
# the sidebar marks values above ESPESSURA_ALERTA_MM in red.
ESPESSURAS_PERMITIDAS = [15.0, 18.0, 20.0, 30.0]
ESPESSURA_ALERTA_MM = 60.0


def _espessura_livre(valor):
    """Requested thickness: positive and free of floating-point noise."""
    return round(max(1.0, float(valor)), 2)


def _espessura_em_alerta(valor):
    return float(valor) > ESPESSURA_ALERTA_MM + 1e-6

# ID marker. WARNING: bpy.props properties on bpy.types.Object are RNA
# and do NOT appear in `"x" in obj`.
# Internal property names (chapa_*, eh_chapa, adj_*) deliberately retain
# their legacy names: preset .blend files already store them.
# Renaming would invalidate the entire
# saved library.
MARCA_CHAPA = "eh_chapa"
MARCA_CONJUNTO = "eh_conjunto_chapa"
MARCA_PORTAS = "eh_grupo_portas"
MARCA_FOLHA = "eh_folha_porta"
# Sliding-door FRAME part (side cladding, track bases, fascia and plinth):
# an actual panel parented to the door group and rebuilt with it,
# like a leaf (`_portas._pecas_moldura`).
MARCA_MOLDURA = "eh_moldura_porta"
# Cabinet BACK (setback 5 mm panel in grooves): DEPENDENT part rebuilt
# from the cabinet box (`_modulos.ajustar_fundo`), outside adjacency,
# proportional resizing and cabinet thickness.
MARCA_FUNDO = "eh_fundo_modulo"
# Front/rear CROSSPIECES replace countertop-cabinet tops: dependent too,
# rebuilt from the box while retaining width (`ajustar_travessas`).
MARCA_TRAVESSA = "eh_travessa_modulo"


def eh_dependente(obj):
    """Back or crosspiece: follows the cabinet box, outside adjacency."""
    return MARCA_FUNDO in obj or MARCA_TRAVESSA in obj
# External objects entering cabinets/doors without becoming panels (IMPORT).
MARCA_ACESSORIO = "eh_acessorio"
MARCA_PUXADOR = "eh_puxador"
# Attachment Empties (cabinet, door group, piston end) remain in the scene:
# native parenting moves the entire cabinet, saves presets and makes doors
# follow the cabinet. Keep them at Blender's minimum display size
# to avoid clutter, as requested.
TAMANHO_EMPTY_OCULTO = 0.0001


def _ocultar_empty(obj):
    if obj.type == 'EMPTY':
        obj.empty_display_type = 'PLAIN_AXES'
        obj.empty_display_size = TAMANHO_EMPTY_OCULTO


CHAVE_TRAVAS_PUXADOR = "puxador_travas"     # [L, A, P]: 1 = locked.

_ocupado = [False]
_havia_modal = [False]   # Remember whether a modal operator was active.
CHAVE_ESPESSURA = 'cabinet_secao_espessura'
ATR_COTA_ARESTA = 'cabinet_cota_aresta'


def _secao_espessura(malha):
    """Pair skins along the local transverse axis, outside redraw.

    A bend moves the middle line without increasing corresponding-vertex
    distance. Only complete, uniform sections determine E; ambiguous cuts
    retain nominal thickness, never the bounding volume.
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
    """Edges of both skins; internal triangulation edges are not dimensions.

    The attribute follows native editing/undo. Vertex indices exist only
    for this query, never as identities stored by HUD/menu.
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
    """Numeric cache shared by measurement, resize and HUD."""
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
        # Independently edited skins cannot be extruded from a common profile.
        # Native topology retains each edge, including a different rear skin.
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
    # Projection beyond thickness is a separate wood dimension.
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
    """Move an endpoint along its actual edge; both skins move together."""
    if obj.mode=='EDIT' or obj.data.is_editmode:raise ValueError("Exit Edit Mode")
    secao=_secao_espessura(obj.data)
    if not secao:
        atributo=obj.data.attributes.get(ATR_COTA_ARESTA)
        aresta=next((e for e in obj.data.edges if atributo and atributo.data[e.index].value==int(uid)),None)
        if aresta is None:raise ValueError("The edge no longer exists")
        a,b=aresta.vertices if lado=='min' else tuple(aresta.vertices)[::-1]
        vetor=obj.data.vertices[b].co-obj.data.vertices[a].co
        if vetor.length<1e-8:raise ValueError("Edge has no length")
        if obj.data.users>1:obj.data=obj.data.copy()
        delta=vetor.normalized()*(max(1.,float(valor_mm))/1000-vetor.length)
        # The topological pair retains skin separation even when a corner
        # was edited without moving its counterpart.
        pares=[j for e in obj.data.edges if b in e.vertices for j in e.vertices
            if j not in (a,b) and abs(abs(obj.data.vertices[j].co.z-obj.data.vertices[b].co.z)*1000
                -obj.chapa_espessura_mm)<.01]
        obj.data.vertices[b].co+=delta
        if len(pares)==1:obj.data.vertices[pares[0]].co+=delta
        _terminar_edicao_secao(obj)
        return
    bordas=_bordas_da_secao(obj.data,secao)
    par=bordas.get(str(uid))
    if par is None:raise ValueError("The edge no longer exists")
    a,b=par if lado=='min' else par[::-1]
    pa,pb=(Vector(secao['pares'][i][0]) for i in (a,b))
    vetor=pb-pa
    if vetor.length<1e-8:raise ValueError("Edge has no length")
    delta=vetor.normalized()*(max(1.,float(valor_mm))/1000-vetor.length)
    if obj.data.users>1:obj.data=obj.data.copy()
    for v,g in zip(obj.data.vertices,secao['grupos']):
        if g==b:v.co+=delta
    _terminar_edicao_secao(obj)


def definir_angulo_arestas(obj, face, valor):
    """Rotate an edge in the plane of the two actual edges, preserving E."""
    if obj.mode=='EDIT' or obj.data.is_editmode:raise ValueError("Exit Edit Mode")
    secao=_secao_espessura(obj.data)
    if not secao:raise ValueError("The panel does not define two corresponding skins")
    bordas=_bordas_da_secao(obj.data,secao)
    ea,eb=(bordas.get(str(uid)) for uid in face)
    comuns=set(ea or ())&set(eb or ())
    if len(comuns)!=1:raise ValueError("The corner no longer exists")
    canto=comuns.pop();a=next(i for i in ea if i!=canto);b=next(i for i in eb if i!=canto)
    p,pa,pb=(Vector(secao['pares'][i][0]) for i in (canto,a,b))
    base=(pa-p).normalized();vetor=pb-p
    normal=vetor-base*vetor.dot(base)
    if normal.length<1e-8:raise ValueError("The corner does not define a rotation plane")
    angulo=math.radians(max(.1,min(179.9,float(valor))))
    delta=p+(base*math.cos(angulo)+normal.normalized()*math.sin(angulo))*vetor.length-pb
    if obj.data.users>1:obj.data=obj.data.copy()
    for v,g in zip(obj.data.vertices,secao['grupos']):
        if g==b:v.co+=delta
    _terminar_edicao_secao(obj)


def definir_deslocamento(obj, valor_mm, lado='min'):
    """Change middle-line sagitta; each pair retains its own E."""
    if obj.mode=='EDIT' or obj.data.is_editmode:raise ValueError("Exit Edit Mode")
    secao=_secao_espessura(obj.data)
    if not secao:raise ValueError("The panel does not define two corresponding skins")
    esp=secao['espessura_mm']/1000
    meios=[v.co.z-lado_v*esp/2 for v,lado_v in zip(obj.data.vertices,secao['lados'])]
    lo,hi=min(meios),max(meios)
    if hi-lo<1e-8:raise ValueError("The panel has no transverse displacement")
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
    """Is the mesh still the add-on's box: eight vertices, one at each
    corner of its own bounds? Any cutout, chamfer, bore or vertex away
    from a corner makes it a MODELED mesh."""
    vertices = malha.vertices
    if len(vertices) == 0:
        return True             # New mesh: start as a box.
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
    """Set the current mesh as stretch reference with the width/length in m
    it represents. Call BEFORE changing dimensions: curved-door wood
    extends beyond nominal width at actual corners, so mesh-based
    measurement irreversibly shrank it on the first resize."""
    estado=obj.get('chapa_edicao')
    if estado and estado['ultimo']==_digital_malha(obj.data):
        return
    _nova_referencia(obj,nominal=[largura,comprimento])['ultimo']=_digital_malha(obj.data)


def _esticar_malha(obj, medidas):
    """Resize a MODELED mesh to dimensions in m without deleting anything:
    vertices follow their nearest side face, maximum above the midpoint
    and minimum below. Cutouts/bores retain their size and distance
    from the nearest edge."""
    _frentes.preparar(obj)
    estado=obj.get('chapa_edicao')
    if not estado or estado['ultimo']!=_digital_malha(obj.data):
        estado=_nova_referencia(obj)
    # Without a stored nominal size, use measured mesh dimensions (general case).
    nominal=estado.get('nominal')
    _frentes.copiar_rotulos(obj.data,estado['malha'])
    # Do not recalculate vertex sides after crossing the midpoint:
    # the native reference preserves bores, cutouts and indices on restoration.
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
    """Panel in m with ROUTED local-Y grooves on the top face
    (Z+, `chapa_canal_lado` 1) or underside (-1), as in the user's
    light-track base. Extrude the notched X/Z section along Y."""
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
    # Repeated points at corner grooves would create degenerate faces.
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
    """ALUMINUM-FRAME sliding leaf from the DXF pantry: perimeter profile
    with face width `chapa_quadro_mm` (material 0), thin glass/mirror/MDF
    infill (material 1) `chapa_painel_frente_mm` behind outer Z+ face,
    penetrating `chapa_painel_entra_mm` into the profile. Rebuild per size
    like grooves: neither a box nor manually modeled geometry."""
    hx, hy, hz = L / 2.0, C / 2.0, E / 2.0
    q = min(float(obj['chapa_quadro_mm']) / 1000.0, hx * 0.45, hy * 0.45)
    p = min(float(obj.get('chapa_painel_mm', 5.0)) / 1000.0, E)
    frente = min(float(obj.get('chapa_painel_frente_mm', 6.0)) / 1000.0, E - p)
    entra = min(float(obj.get('chapa_painel_entra_mm', 5.0)) / 1000.0, q)
    bm = bmesh.new()
    try:
        # Four profile bars: full-height verticals, horizontals between them.
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
    """Arc-CURVED panel from the DXF corner drawer front: width is the chord,
    `chapa_arco_mm` sagitta points toward Z+ (outward), and endpoints
    remain on the straight panel plane. Concentric thickness; extrude
    the X/Z section along Y (length)."""
    f = float(obj['chapa_arco_mm']) / 1000.0
    meia = L / 2.0
    f = min(f, meia)                          # At most a semicircle.
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
            # Both arcs smooth; endpoints (i = n and i = m-1) flat.
            face.smooth = i != n and i != m - 1
        # Quad caps because the arc section is not convex.
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
    """Actual BMesh mesh, editable in Edit Mode.
    Local X=width, Y=length, Z=THICKNESS.

    Auto-regeneration is retired: all panel edits must persist. Rebuild
    standard boxes; STRETCH Edit-Mode-modeled meshes with `_esticar_malha`,
    never replace them."""
    if (obj is None or obj.type != 'MESH' or obj.mode == 'EDIT'
            or obj.data.is_editmode):
        return
    L = obj.chapa_largura_mm / 1000.0
    C = obj.chapa_comprimento_mm / 1000.0
    E = obj.chapa_espessura_mm / 1000.0
    if obj.get('chapa_canais') or obj.get('chapa_quadro_mm') or obj.get('chapa_arco_mm'):
        if obj.get('chapa_canais'):
            # Rebuild light-track bases WITH grooves: neither boxes nor modeled
            # meshes, since stretching would move grooves too.
            _malha_com_canais(obj, L, C, E)
        elif obj.get('chapa_quadro_mm'):
            _malha_quadro(obj, L, C, E)
        else:
            _malha_arco(obj, L, C, E)
        _frentes.preparar(obj)
        # Profiles on frame/arc leaves also follow the new mesh.
        for filho in obj.children:
            if _puxadores._eh_puxador_parametrico(filho):
                _puxadores.posicionar_puxador(filho)
        return
    if not _malha_e_caixa(obj.data):
        # On curved leaves, mesh Z measures arc SAGITTA rather than wood
        # thickness. Reapplying parameters must not flatten it.
        profundidade = (max(v.co.z for v in obj.data.vertices)-min(v.co.z for v in obj.data.vertices)
                        if obj.get('porta_curva_modelada') else E)
        _esticar_malha(obj, (L, C, profundidade))
        _frentes.preparar(obj)
        for filho in obj.children:
            if _puxadores._eh_puxador_parametrico(filho):
                _puxadores.posicionar_puxador(filho)
        return
    bm = bmesh.new()
    # The box was rebuilt: its face indices belong to another topology.
    # Recognize the surface geometrically once.
    for chave in (_frentes.ATR_FACE,_frentes.ATR_BORDA):
        atributo = obj.data.attributes.get(chave)
        if atributo is not None:
            obj.data.attributes.remove(atributo)
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co.x *= L
        v.co.y *= C
        v.co.z *= E
    # Child profile: remove its strip from the MESH; keep nominal properties
    # because door size, adjacency and HUD read properties, not mesh geometry.
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
    # Parametric handles follow the new panel.
    for filho in obj.children:
        if _puxadores._eh_puxador_parametrico(filho):
            _puxadores.posicionar_puxador(filho)


def _upd_chapa(self, context):
    if _ocupado[0]:
        return
    gerar_malha_chapa(self)


def _espessura_da_malha(obj):
    """ACTUAL mesh thickness in mm. The update callback sees an already
    changed PROPERTY but the old mesh, which supplies previous thickness
    needed to determine inward growth direction."""
    if obj is None or obj.type != 'MESH' or not obj.data.vertices:
        return None
    secao=_secao_espessura(obj.data)
    if secao:return secao['espessura_mm']
    if not _malha_e_caixa(obj.data):
        ref=obj.data.get(_frentes.CHAVE)
        return float(ref['espessura'])*1000 if ref and ref.get('espessura') else None
    # Do not multiply by scale.z: Z scale is discarded by invariant,
    # so the local mesh represents the old property value.
    zs = [v.co.z for v in obj.data.vertices]
    return (max(zs) - min(zs)) * 1000.0


def _upd_espessura(self, context):
    """Store FREE thickness (`_espessura_livre`, without rounding) and
    thicken the panel INWARD (`_modulos.aplicar_espessura_chapa`)."""
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
    # Door leaves do not thicken into the cabinet: rebuild the entire door
    # at the new thickness (`_portas._espessura_da_folha_mudou`).
    if MARCA_FOLHA in self and _portas._espessura_da_folha_mudou(self, alvo):
        return
    # Frame part: E applies to the whole editable frame, stored on the door,
    # which rebuilds all six parts.
    if MARCA_MOLDURA in self and _portas._espessura_da_moldura_mudou(self, alvo):
        return
    if (MARCA_CHAPA not in self
            or e_velha is None or abs(e_velha - alvo) < 1e-4):
        gerar_malha_chapa(self)
        return
    _modulos.aplicar_espessura_chapa(self, alvo, e_velha)


# ===================================================== NORMALIZATION
def normalizar_chapas(objs=None):
    """Convert accumulated panel scale into DIMENSIONS in mm and reset scale
    to 1.

    CENTRAL RULE: DISCARD local Z scale (thickness), do not convert it.
    Local Z is always thickness, upright or horizontal, so thickness
    remains immune to scaling along ANY world axis.

    Return adjusted parts.
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
            # Cabinet scaling with internals still awaits the timer. Do not absorb
            # inherited scale into individual panels before refitting.
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
            # Deliberately IGNORE sz (thickness).
            obj.scale = (1.0, 1.0, 1.0)
    finally:
        _ocupado[0] = False

    for obj, _sx, _sy, _sz in alvos:
        gerar_malha_chapa(obj)

    # Close gaps introduced by scale arithmetic.
    try:
        aplicar_adjacencia()
    except Exception as e:
        print("[Archy Builder] adjacency:", e)

    return [o for o, _a, _b, _c in alvos]


# Panel names in Edit Mode on the previous timer tick.
_chapas_em_edicao = set()


def preparar_uvs_chapa(obj):
    """Initial metric map: one UV unit per meter, retaining existing maps."""
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
    """Panels just EXITED from Edit Mode: absorb user mesh edits into
    dimensions (`absorver_malha_editada`).

    HUD, sidebar and adjacency read PROPERTIES, not the mesh; stretching
    an edge left HUD outlines stale. Ordinary panels use only the mode
    transition; frames also recover old mismatches from native bounds.
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
            # Already edited scenes lost the Tab transition; native bounds detect
            # the mismatch without rereading the mesh.
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
        # Moving internal vertices need not change L/A/E or the vertex count
        # used in the plan signature.
        _formas.esquecer()
    for obj in saidas:
        try:
            if _puxadores._eh_puxador_parametrico(obj):
                _puxadores.atualizar_contorno(obj)
                continue
            absorver_malha_editada(obj)
            _frentes.preparar(obj)
            for filho in obj.children:
                # In group Tab, handle geometry already followed the native gesture.
                # Recreating it would undo the confirmed movement.
                if (_puxadores._eh_puxador_parametrico(filho)
                        and filho.name not in anteriores):
                    _puxadores.posicionar_puxador(filho)
        except Exception as e:
            print("[Archy Builder] absorb edit:", e)


def _alinhar_plano_da_chapa(obj):
    """Reexpress a flat panel in its actual plane without changing WORLD
    geometry. A Tab-tilted panel's AABB Z is not thickness. Require two
    parallel surfaces before changing the frame.
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
    """Local mesh bounds -> width/length/thickness; recenter the origin
    WITHOUT moving the part in world space.

    Exclude door leaves (edited through their group) and profiled panels,
    whose profile strip is deliberately removed only from mesh geometry.
    Return True if anything changed.
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
        # Children (imported handles, accessories) retain their position;
        # parametric handles rebuild from properties in gerar_malha_chapa.
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
    # Geometry already matches the user's confirmed Edit Mode result.
    # This path must not rebuild buffers still retained by native undo.
    # Absorption only updates measurements/references.
    _frentes.invalidar(obj)
    obj.data.update()
    return True


# ============================= HANDLER: act ONLY after the modal finishes
@bpy.app.handlers.persistent
def ao_atualizar_depsgraph(scene, depsgraph):
    """Let the panel deform normally during native S dragging. When the
    modal finishes with Enter, click or Esc, detect the transition and
    recalculate all panels together.

    Changing scale DURING the modal does not work: the operator caches
    initial scale and reapplies its factor on every mouse move, overwriting
    any mid-drag correction on the next frame.
    """
    if _ocupado[0] or _eventos._desfazendo[0]:
        # Immediately after undo, data has just been restored
        # (`_eventos._depois_de_desfazer`): no recalculation; mutation here crashed.
        return
    for atualizacao in depsgraph.updates if depsgraph is not None else ():
        dado = atualizacao.id
        if (isinstance(dado, bpy.types.Object) and dado.type == 'MESH'
                and MARCA_CHAPA in dado and atualizacao.is_updated_geometry):
            _frentes.invalidar(dado.original, conferir=True)
    # Selection changes also pass here: update the outline immediately
    # rather than waiting for the timer.
    _eventos.sincronizar_contornos()
    # After deletion/duplication, check door hardware later in a timer;
    # never remove objects inside the depsgraph handler.
    contagem = (len(bpy.data.objects), tuple((s.name, len(s.objects)) for s in bpy.data.scenes))
    anterior = _ferragens._contagem_objetos[0]
    if contagem != anterior:
        _solda._normalizar_pendente[0] = True
        surgiu = anterior is not None and contagem[0] > anterior[0]
        _ferragens._contagem_objetos[0] = contagem
        if not bpy.app.timers.is_registered(_ferragens._conferir_ferragens):
            bpy.app.timers.register(_ferragens._conferir_ferragens, first_interval=0.0)
        # Ctrl+D on a panel: give the copy its own identity without the
        # original's welds, as requested.
        if surgiu and not bpy.app.timers.is_registered(_separar_copias_no_timer):
            bpy.app.timers.register(_separar_copias_no_timer, first_interval=0.0)

    modal_ativo = _eventos._ha_modal_ativo()

    if modal_ativo:
        _havia_modal[0] = True     # Drag in progress: do not touch.
        return

    # Modal finished or absent (script/panel scaling): recalculate everything.
    _havia_modal[0] = False
    _modulos.absorver_conjuntos()
    normalizar_chapas()



# ===================================================== ADJACENCY
# For each panel end (X- X+ Y- Y+), store its touching neighbor and
# the detected gap. After recalculation, stretch/shorten the panel
# to restore that gap, closing spaces introduced by
# scale arithmetic.
#
# Scaling by F multiplies side-panel POSITION by F but not THICKNESS.
# Per-side gap = (E/2)*(F-1).
PONTAS = ("x_neg", "x_pos", "y_neg", "y_pos")
TOL_ENCOSTE = 0.06   # 60 mm: maximum neighborhood distance.


def _garantir_uid(obj):
    """Stable panel identity. Name-based adjacency breaks when inserting
    library cabinets: names gain .001 suffixes and links would target
    the wrong part."""
    if not obj.get("chapa_uid"):
        obj["chapa_uid"] = uuid.uuid4().hex[:12]
    return obj["chapa_uid"]


def _resolver_vizinho(C, uid, nome):
    """Find neighbors among SIBLINGS (same parent) first so copies of the
    same cabinet cannot be confused."""
    if uid:
        # The name only disambiguates a sibling with that UID, avoiding another
        # scene search per joint without substituting the nearest copy's identity.
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
    """Local axes expressed in WORLD space. Using local rotation_euler broke
    when the parent Empty left the origin: its frame no longer matched
    world space, and face-on-boundary tests stopped recognizing parts."""
    m = obj.matrix_world.to_3x3()
    return m.col[0].normalized(), m.col[1].normalized(), m.col[2].normalized()


def _centro(obj):
    return obj.matrix_world.translation.copy()


def _definir_centro(obj, novo):
    """Set a WORLD center respecting parent and matrix_parent_inverse."""
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


# AUTOMATIC distance connection (Chain button) reaches only this far.
# Beyond it, use vertex selection. Cabinet-grouping detectar_adjacencia
# still uses TOL_ENCOSTE.
ALCANCE_CONEXAO_AUTOMATICA = 0.005


def _melhor_vizinho(C, eixo, lado, candidatos, alcance=None):
    """Nearest (neighbor, gap, face) to C's axis/side end among `candidatos`,
    or None. Same rules as detectar_adjacencia; `alcance` in m replaces
    TOL_ENCOSTE."""
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
        # Consider only neighbors overlapping in other directions.
        # Coincident corners/edges are not support faces. Inclusive tests
        # created up to four welds for the same corner.
        modulo = C.parent is not None and MARCA_CONJUNTO in C.parent
        if not all((min(_faixa(C, w)[1], _faixa(N, w)[1]) -
                    max(_faixa(C, w)[0], _faixa(N, w)[0]) > 1e-5) if modulo else
                   _sobrepoe(_faixa(C, w), _faixa(N, w)) for w in perp):
            continue
        faces = _faixa(N, u)   # Neighbor (min, max) in direction u.
        # Anchor to the neighbor face NEAREST the endpoint.
        # Always using the far face embedded old thickness
        # in the gap; changing thickness then pushed the part
        # outward and grew the cabinet spontaneously.
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
            del C[f"adj_{eixo}_{lado}{sufixo}"]   # New weld: do not inherit the previous origin.
    C[f"adj_{eixo}_{lado}"] = N.name
    C[f"adj_{eixo}_{lado}_uid"] = _garantir_uid(N)
    C[f"adj_{eixo}_{lado}_folga"] = float(folga)
    C[f"adj_{eixo}_{lado}_face"] = int(face)
    _solda._gravar_restricoes(C, ponta, N, restricoes)
    return True


def detectar_adjacencia(objs):
    """For each panel end, find its nearest neighbor in that direction
    and store the current gap."""
    chapas = sorted((o for o in objs if o.type == 'MESH' and MARCA_CHAPA in o
                     and not eh_dependente(o)), key=lambda o: o.name)
    for c in chapas:
        _garantir_uid(c)
    n = 0
    for C in chapas:
        _limpar_pontas(C)  # Clear the old UID too: an empty name does not disconnect.
    for C in chapas:
        for eixo in ("x", "y"):
            for lado in ("pos", "neg"):
                achado = _melhor_vizinho(C, eixo, lado, chapas)
                if achado is not None:
                    n += int(_gravar_ligacao(C, eixo, lado, *achado))
    return n


def otimizar_adjacencia(objs):
    """Revalidate automatic assembly welds; preserve manual anchors.
    Used in preset migration, never drawing or dragging.
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
    # Plan ALL objects before clearing, or another endpoint's newly assigned
    # fittings could be erased.
    for C, ponta, _achado in planos:
        _limpar_ponta(C, ponta)
    for C, ponta, achado in sorted(planos, key=lambda p: (p[0].name, p[1])):
        if achado is not None:
            eixo, lado = ponta.split('_')
            _gravar_ligacao(C, eixo, lado, *achado)
    return [o.name for o in chapas if antes[o.name] != repr(sorted(
        (k, str(v)) for k, v in o.items() if k.startswith('adj_')))]


def associar_por_distancia(C, vizinhos, alcance=None):
    """Connect ONE part to reachable neighbors without recalculating their
    other links: detectar_adjacencia clears all recipient links, losing
    connections such as a cabinet's external neighbor. Rebuild C's ends;
    only EMPTY neighbor ends gain links to C. Return connected-end count."""
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
    """Remove ONE endpoint's weld so it no longer pulls its neighbor."""
    C[f"adj_{ponta}"] = ""
    C[f"adj_{ponta}_folga"] = 0.0
    for sufixo in ("_uid", "_face", "_ancoras", "_origens", "_manual", "_direcoes", "_restricoes"):
        if f"adj_{ponta}{sufixo}" in C:
            del C[f"adj_{ponta}{sufixo}"]


def _limpar_pontas(C):
    for k in PONTAS:
        _limpar_ponta(C, k)


def _copias_com_mesmo_uid(objs=None):
    """Return {(parent, uid): [panels]} for SIBLINGS sharing identity, left
    by Ctrl+D copying `chapa_uid` and welds. Exclude whole-cabinet
    duplicates because their parent differs."""
    grupos = {}
    for o in (bpy.data.objects if objs is None else objs):
        uid = o.get("chapa_uid")
        if uid and o.type == 'MESH' and MARCA_CHAPA in o:
            grupos.setdefault((o.parent, uid), []).append(o)
    return {k: v for k, v in grupos.items() if len(v) > 1}


def _original_entre(copias):
    """Identity keeper: the UNSELECTED part (Ctrl+D selects only copies),
    then on ties prefer the name without the larger suffix."""
    def chave(o):
        try:
            selecionada = o.select_get()
        except Exception:
            selecionada = False
        return (selecionada, o.name.rpartition('.')[2].isdigit(), o.name)
    return min(copias, key=chave)


def separar_copias(objs=None):
    """Give each copy a new identity WITHOUT original welds: old links
    targeted the original's neighbors and stretched incorrectly. Links
    to the original remain attached to it. Return separated copies."""
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
    """Ctrl+D timer, scheduled by the handler on object creation: do not
    mutate ID properties inside the depsgraph handler."""
    try:
        if not _eventos._desfazendo[0]:
            separar_copias()
    except Exception as erro:
        print("[Archy Builder] separate copies:", erro)
    return None


def recalcular_ancoragem(chapas):
    """Rebuild `chapas` welds at their CURRENT positions for Recalculate
    Anchoring: separate copies, clear ends, reconnect touching siblings
    and selected parts within ALCANCE_CONEXAO_AUTOMATICA. For other
    neighbors, connect only empty ends or ends pointing to rebuilt parts.
    Return connected-end count."""
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
                    # Previously pointed to a rebuilt part that no longer touches.
                    _limpar_ponta(V, ponta)
    return n


def _chapas_candidatas(C, candidatos=None):
    """Other scene panels, or only `candidatos` targets selected before
    the external part."""
    fonte = bpy.data.objects if candidatos is None else candidatos
    return [o for o in fonte
            if o is not C and o.type == 'MESH' and MARCA_CHAPA in o]


def _vizinhos_por_distancia(C, alcance=ALCANCE_CONEXAO_AUTOMATICA,
                            candidatos=None):
    """Panels that would connect to C by distance, without writing:
    those reached by C's ends and those whose ends reach C."""
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
    """Stretch/shorten each panel along width/length to restore stored
    neighbor gaps."""
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
            # Keep center HERE between axes: rereading stale matrix_world for Y
            # lost X displacement, since view_layer.update
            # cannot run inside the handler.
            centro = _centro(C)
            for eixo, u in (("x", ex), ("y", ey)):
                hx, hy, hz = _meias(C)
                h = hx if eixo == "x" else hy
                centro_u = centro.dot(u)
                p_pos, p_neg = centro_u + h, centro_u - h
                alvo_pos, alvo_neg = p_pos, p_neg

                N, fp, folga_pos = restricoes[C].get(eixo+'_pos', (None, 0, 0.))
                if N is not None and N.parent!=C.parent and (N.get('eh_prateleira') or N.get('gaveta_peca')):
                    N = None   # Former integrated panel no longer pulls the cabinet body.
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
    """Recalculate selected panels from their applied scale."""
    bl_idname = "object.cabinet_normalizar"
    bl_label = "Recalculate Panels"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        alvo = context.selected_objects or bpy.data.objects
        ajustadas = normalizar_chapas(alvo)
        self.report({'INFO'}, "%d panel(s) recalculated" % len(ajustadas))
        return {'FINISHED'}


# ================================================== OBJECT CREATION
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
    """Create a loose panel (600 x 400 x 18 mm)."""
    bl_idname = "object.cabinet_criar"
    bl_label = "Create Panel"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = nova_chapa("Panel", 600.0, 400.0, 18.0, (0, 0, 0), (0, 0, 0), context)
        for o in context.selected_objects:
            o.select_set(False)
        obj.select_set(True)
        context.view_layer.objects.active = obj
        return {'FINISHED'}


class OBJECT_OT_criar_nicho(Operator):
    """Create a backless cabinet: two sides, top and base."""
    bl_idname = "object.cabinet_criar_nicho"
    bl_label = "Create Niche (No Back)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        L, A, P, E = 600.0, 400.0, 300.0, 18.0
        li = L - 2 * E
        pecas = [
            ("Lateral_Esq", A, P, E, (-(L / 2 - E / 2), 0, A / 2), (0, 90, 0)),
            ("Lateral_Dir", A, P, E, ((L / 2 - E / 2), 0, A / 2), (0, 90, 0)),
            ("Base",        li, P, E, (0, 0, E / 2), (0, 0, 0)),
            ("Top",       li, P, E, (0, 0, A - E / 2), (0, 0, 0)),
        ]
        for o in context.selected_objects:
            o.select_set(False)
        criadas = [nova_chapa(n, la, c, e, lo, r, context) for n, la, c, e, lo, r in pecas]
        for c in criadas:
            c.select_set(True)
        context.view_layer.objects.active = criadas[0]
        return {'FINISHED'}


class OBJECT_OT_marcar_como_chapa(Operator):
    """Convert the selected object into a G3 panel."""
    bl_idname = "object.cabinet_marcar"
    bl_label = "Mark as Panel"
    bl_options = {'REGISTER', 'UNDO'}

    alternar: BoolProperty(default=False, options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return context.object is not None and context.object.type == 'MESH'

    def execute(self, context):
        obj = context.object
        if self.alternar and MARCA_CHAPA in obj:
            if MARCA_FOLHA in obj:
                self.report({'WARNING'}, "Parametric leaf: edit through the door group")
                return {'CANCELLED'}
            # Explicit conversion preserves mesh and hierarchy. Clear references
            # so adjacency cannot use the deactivated panel.
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
        # Measure the part's SHAPE (`converter_em_chapa`), not world-axis
        # `obj.dimensions`, so upright sides acquire the correct thickness
        # without movement. Apply to the entire selection:
        # imported cabinets contain dozens of parts.
        alvos = [o for o in context.selected_objects
                 if o.type == 'MESH' and MARCA_CHAPA not in o
                 and MARCA_PUXADOR not in o]
        if obj not in alvos and MARCA_CHAPA not in obj and MARCA_PUXADOR not in obj:
            alvos.append(obj)
        convertidas = [o for o in alvos if _importacao.converter_em_chapa(o) is not None]
        if not convertidas:
            self.report({'WARNING'}, "Nothing with volume to convert")
            return {'CANCELLED'}
        if len(convertidas) == 1:
            c = convertidas[0]
            self.report({'INFO'}, "Panel %.0f x %.0f x %.0f mm"
                        % (c.chapa_largura_mm, c.chapa_comprimento_mm,
                           c.chapa_espessura_mm))
        else:
            self.report({'INFO'}, "%d panels converted" % len(convertidas))
        return {'FINISHED'}
