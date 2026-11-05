"""DXF -> add-on systems, as requested by the user: integration rather
than raw import. DXF supplies only SOLIDS; convert them to supported
systems: hinged fronts become native DOORS with OUR hinges; fronts
with boxes behind become native DRAWERS with our rails; sliding aluminum
frames become SLIDING doors with an aluminum-frame leaf and our rails;
thin backs and top rails become cabinet DEPENDENTS. Never retain DXF
hardware (rails, hinges, handles, baskets, appliances).

Layer COLOR distinguishes components, based on the user's DXF files:
7 = panel (MDF), 253 = hardware, 254 = aluminum/glass (sliding frame,
basket), 8 = handle, 28 = tall-cabinet accessory, 250-252 = appliance.

`planejar` uses WORLD geometry in mm; each door uses its hinge plate
frame, including L/diagonal layouts. `aplicar` mounts our hardware on
the supports; drawers/sliding doors retain the front path."""

import bpy
import bmesh
from mathutils import Matrix, Vector

# Used only at RUNTIME (circular imports): __init__ wires these
# aliases after loading all modules (`_ligar_modulos`).
_chapas = _modulos = _portas = _gavetas = _prateleiras = _puxadores = None
_frentes = None

COR_CHAPA = 7
COR_FERRAGEM = 253
COR_ALUMINIO = 254
# Without a layer table (test DXF, other exporter), everything is a panel.
CORES_CHAPA = {COR_CHAPA, None, 0, 256}

TOL_FRENTE_MM = 3.0          # Front: within 3 mm of the cabinet's front face.
FRENTE_MINIMA_MM = (100.0, 60.0)   # Width, height.
DOBRADICA_MAXIMA_MM = 70.0   # Small hardware component = hinge.
ALCANCE_DOBRADICA_MM = 60.0  # Behind the front.
LATERAL_GAVETA_MINIMA_MM = 150.0   # Box side length.
CESTO_MINIMO_MM = (80.0, 150.0, 80.0)  # Wire basket (color 254): width, depth, height.
FOLGA_PILHA_MM = 12.0        # Between fronts in the same drawer stack.
FOLGA_PAR_MM = 8.0           # Between the two leaves of a double door.
QUADRO_CORRER_MM = (18.0, 30.0)    # Sliding frame profile depth.
FUNDO_MAXIMO_MM = 8.0
TRAVESSA_MAXIMA_MM = 120.0
FOLGA_ENCAIXE_MAXIMA_MM = 3.1  # DXF places base/top 3 mm inward from the side.
TOL_ENCAIXE_MM = 0.05


# ------------------------------------------------------------ boxes
def peca(obj, lo, hi, eixo=None, curva=False, espessura=0.0, cor=COR_CHAPA,
         analise=None, pontos=None):
    """Component data for the plan: world box in mm, thickness axis
    (0/1/2; None = curved), and thickness (provided separately for curves)."""
    dados = {'obj': obj, 'lo': list(lo), 'hi': list(hi), 'eixo': eixo,
            'curva': curva, 'cor': cor,
            'espessura': espessura or (hi[eixo] - lo[eixo] if eixo is not None else 0.0)}
    if obj is not None:
        dados['origem'] = obj.name
    if pontos is not None:
        dados['pontos'] = pontos
    if analise is not None:
        dados['normal'] = tuple(analise['base'].col[2])
        dados['espessura'] = analise['dims'][2]
    elif eixo is not None:
        dados['normal'] = tuple(float(k == eixo) for k in range(3))
    return dados


def _vertices(p):
    return [Vector(v) for v in p.get('pontos', [])] or [
        Vector((x, y, z)) for x in (p['lo'][0], p['hi'][0])
        for y in (p['lo'][1], p['hi'][1]) for z in (p['lo'][2], p['hi'][2])]


def _em_referencia(p, referencia):
    pontos = [referencia.transposed() @ v for v in _vertices(p)]
    q = dict(p)
    q['lo'] = [min(v[k] for v in pontos) for k in range(3)]
    q['hi'] = [max(v[k] for v in pontos) for k in range(3)]
    if 'normal' in p:
        n = referencia.transposed() @ Vector(p['normal'])
        q['eixo'] = max(range(3), key=lambda k: abs(n[k]))
    q['original'] = p
    return q


def _referencias_dobradicas(pecas, ferragens):
    """Each plate/arm assembly belongs to ONE leaf. The thin plate is
    parallel to it; global boxes alone confused sides with doors."""
    pequenas = [f for f in ferragens if f['cor'] == COR_FERRAGEM
                and max(_tam(f, k) for k in range(3)) <= DOBRADICA_MAXIMA_MM]
    placas = [f for f in pequenas if f.get('espessura', 0) > 0
              and f['espessura'] <= 3 and abs(Vector(f['normal']).z) < 0.05]
    sementes = list(placas)
    centros = lambda f: Vector(tuple(_centro(f, k) for k in range(3)))
    # For exports without a plate (and older DXFs), the arm still gives
    # the depth axis. Do not count plate and arm as two hinges.
    for f in pequenas:
        if any((centros(f) - centros(p)).length < 40 for p in placas):
            continue
        if min(_tam(f, 0), _tam(f, 1)) < 8 or _tam(f, 2) < 8:
            continue
        s = dict(f)
        s['sem_placa'] = True
        eixo = max((0, 1), key=lambda k: _tam(f, k))
        s['normal'] = tuple(float(k == eixo) for k in range(3))
        sementes.append(s)
    associadas = {}
    for s in sementes:
        n = Vector(s['normal']).normalized()
        n.z = 0
        n.normalize()
        vizinhas = [f for f in pequenas if (centros(f) - centros(s)).length < 40]
        # The arm center lies INSIDE the leaf (the plate may extend beyond
        # the center joint). This difference distinguishes the two leaves.
        braco = max(vizinhas, key=lambda f: _tam(f, 0) * _tam(f, 1) * _tam(f, 2), default=s)
        centro = centros(braco)
        opcoes = []
        for f in pecas:
            if f['curva'] or 'normal' not in f:
                continue
            nf = Vector(f['normal'])
            if abs(nf.z) > 0.05 or abs(nf.dot(n)) < 0.995:
                continue
            proj = [v.dot(n) for v in _vertices(f)]
            distancia = min(abs(centros(s).dot(n) - b) for b in (min(proj), max(proj)))
            if s.get('sem_placa'):
                extremos = [v.dot(n) for v in _vertices(s)]
                distancia = min(abs(a - b) for a in (min(extremos), max(extremos))
                                for b in (min(proj), max(proj)))
            if distancia > 7:
                continue
            # Orientation derives from the arm's position relative to the leaf.
            # A triangulated plate may have angular noise. The panel plane
            # is the exact reference, including 45-degree diagonals.
            normal_folha=Vector((nf.x,nf.y,0)).normalized()
            media=sum(v.dot(normal_folha) for v in _vertices(f))/len(_vertices(f))
            dentro = normal_folha if centro.dot(normal_folha) >= media else -normal_folha
            fora = -dentro
            direita = Vector((0, 0, 1)).cross(fora).normalized()
            ref = Matrix((direita, dentro, Vector((0, 0, 1)))).transposed()
            local = _em_referencia(f, ref)
            c = ref.transposed() @ centro
            if (_tam(local, 0) < 100 or _tam(local, 2) < 60
                    or not local['lo'][0] - 2 <= c.x <= local['hi'][0] + 2
                    or not local['lo'][2] - 2 <= c.z <= local['hi'][2] + 2):
                continue
            borda = min(abs(c.x - local['lo'][0]), abs(c.x - local['hi'][0]),
                        abs(c.z - local['hi'][2]))
            opcoes.append((distancia + borda * 0.01, f, ref, c))
        if opcoes:
            _, f, ref, c = min(opcoes, key=lambda a: a[0])
            item = associadas.setdefault(id(f), {'frente': f, 'referencia': ref, 'centros': []})
            if not any((c - outro).length < 10 for outro in item['centros']):
                item['centros'].append(c)
    return list(associadas.values())


def _portas_curvas_referenciadas(pecas, ferragens):
    """The plate's TANGENT plane identifies the curved leaf side.

    Adopt the DXF mesh into the native leaf without approximating the
    arc with a straight door or importing DXF hardware."""
    saida = []
    for f in pecas:
        if not f['curva'] or f.get('obj') is None:
            continue
        placas = [s for s in ferragens if s['cor']==COR_FERRAGEM
                  and 0 < s.get('espessura', 0) <= 3
                  and abs(Vector(s.get('normal',(0,0,1))).z)<.05
                  and f['lo'][2]-.05 <= _centro(s,2) <= f['hi'][2]+.05
                  and all(f['lo'][k]-35 <= _centro(s,k) <= f['hi'][k]+35 for k in range(3))]
        if not placas:
            continue
        s = placas[0]
        n = Vector(s['normal']); n.z=0; n.normalize()
        cf = Vector(tuple(_centro(f,k) for k in range(3)))
        cs = Vector(tuple(_centro(s,k) for k in range(3)))
        dentro = n if (cs-cf).dot(n)>0 else -n
        direita = Vector((0,0,1)).cross(-dentro)
        ref = Matrix((direita,dentro,Vector((0,0,1)))).transposed()
        q = _em_referencia(f,ref)
        centros = [ref.transposed() @ Vector(tuple(_centro(p,k) for k in range(3))) for p in placas]
        lado = 'ESQUERDA' if sum(c.x for c in centros)/len(centros)<_centro(q,0) else 'DIREITA'
        obj=f['obj']
        comprimentos=[(obj.data.vertices[e.vertices[0]].co-obj.data.vertices[e.vertices[1]].co).length*1000
                      for e in obj.data.edges
                      if abs(obj.data.vertices[e.vertices[0]].co.z-obj.data.vertices[e.vertices[1]].co.z)<1e-5]
        esp = min((d for d in comprimentos if d>=3),default=f['espessura'])
        q['espessura']=esp
        q['lo'][1]=q['hi'][1]-esp
        corpo=[_em_referencia(p,ref) for p in pecas if p is not f]
        vao=vao_atras(corpo,q,q['hi'][1])
        saida.append(dict(folhas=[q],lado=lado,plano=q['hi'][1],vao=vao,
            referencia=ref,centros=[centros],curva_modelada=True,
            malha_original=dict(vertices=[list(v) for v in _vertices(f)],
                                faces=[list(p.vertices) for p in obj.data.polygons])))
    return saida


def _linha_do_corpo(conj, folha):
    """Actual top edge near the front. Query native BVH once during
    assembly/editing, never while drawing or opening the door."""
    from mathutils.bvhtree import BVHTree
    estruturais = _modulos._estruturais(_modulos._chapas_do_conjunto(conj))
    horizontais = [o for o in estruturais
                   if abs(_chapas._eixos(o)[2].z) > .99]
    if not horizontais:
        return None
    # A tall rail or cut top does not define the front envelope.
    # The largest horizontal panel preserves the box's full footprint.
    obj = max(horizontais, key=lambda o: (round(sum(p.area for p in o.data.polygons), 6),
                                         max(p.z for p in _chapas._cantos(o))))
    m = obj.matrix_world
    topo = [p for p in obj.data.polygons if (m.to_3x3() @ p.normal).z > .99]
    if not topo:
        return None
    pontos = [m @ v.co for v in obj.data.vertices]
    contagem = {}
    for p in topo:
        for e in p.edge_keys:
            e = tuple(sorted(e))
            contagem[e] = contagem.get(e, 0) + 1
    # Triangulated exports repeat vertices at the same coordinates.
    arestas = {}
    for (i, j), n in contagem.items():
        if n != 1:
            continue
        a, b = pontos[i], pontos[j]
        ka, kb = (tuple(round(v, 5) for v in p.xy) for p in (a, b))
        if ka == kb:
            continue
        chave = tuple(sorted((ka, kb)))
        arestas[chave] = arestas.get(chave, 0) + 1
    arestas = [e for e, n in arestas.items() if n % 2]
    fechada = _portas._ferragens._matriz_fechada(folha)
    vs = [fechada @ v.co for v in folha.data.vertices]
    arvore = BVHTree.FromPolygons(vs, [list(p.vertices) for p in folha.data.polygons])
    z = sum(p.z for p in vs) / len(vs)
    laterais = [(o, o.matrix_world.inverted()) for o in estruturais
                if abs(_chapas._eixos(o)[2].z) < .05]
    perto = []
    for a, b in arestas:
        a, b = Vector(a), Vector(b)
        meio = (a+b)/2
        co, normal, _face, dist = arvore.find_nearest(Vector((meio.x, meio.y, z)))
        d = b-a
        if co is None or dist > .06 or d.length < .003:
            continue
        normal2 = Vector((d.y, -d.x)).normalized()
        if not folha.get('porta_curva_modelada') and abs(normal2.dot(normal.xy)) < .98:
            continue
        coberta = False
        for lateral, inv in laterais:
            pt = Vector((meio.x, meio.y, z))
            local = inv @ pt
            hit, perto_face, normal_face, _f = lateral.closest_point_on_mesh(local)
            if hit and (local-perto_face).length < .0001:
                coberta = True
                break
        if coberta:
            continue
        perto.append((tuple(a), tuple(b)))
    # Each contiguous segment is a candidate. The long front wins over the
    # small side return that may also lie near the door end.
    vizinhos = {}
    for a, b in perto:
        vizinhos.setdefault(a, []).append(b)
        vizinhos.setdefault(b, []).append(a)
    caminhos = []
    visitados = set()
    for inicio in vizinhos:
        if inicio in visitados or len(vizinhos[inicio]) != 1:
            continue
        caminho, anterior, atual = [], None, inicio
        while atual is not None and atual not in visitados:
            caminho.append(Vector(atual)); visitados.add(atual)
            proximo = next((p for p in vizinhos[atual] if p != anterior), None)
            anterior, atual = atual, proximo
        if len(caminho) > 1:
            caminhos.append(caminho)
    if not caminhos:
        return None
    caminho = max(caminhos, key=lambda ps: sum((b-a).length for a,b in zip(ps,ps[1:])))
    if sum((b-a).length for a,b in zip(caminho,caminho[1:])) < .08:
        return None
    # A point slightly inside the panel distinguishes both directions
    # without assuming front -Y or relying on a DXF plate's orientation.
    a, b = max(zip(caminho,caminho[1:]), key=lambda ab: (ab[1]-ab[0]).length)
    meio=(a+b)/2; normal=Vector(((b-a).y, -(b-a).x)).normalized()
    teste=Vector((meio.x+normal.x*.001,meio.y+normal.y*.001,pontos[topo[0].vertices[0]].z))
    hit, co, _n, _f = obj.closest_point_on_mesh(m.inverted() @ teste)
    if hit and (m @ co-teste).length < .0001:
        caminho.reverse()
    return caminho


def _afastar_linha(pontos, distancia):
    normais = [Vector(((b-a).y, -(b-a).x)).normalized() for a,b in zip(pontos,pontos[1:])]
    saida = []
    for i,p in enumerate(pontos):
        n = normais[min(i,len(normais)-1)]
        if 0 < i < len(pontos)-1:
            soma = normais[i-1]+n
            n = soma / max(.2, soma.dot(n))
        saida.append(p+n*distancia)
    return saida


def _limitar_pontas_frente(conj, dentro, fora, alturas):
    """Trim BOTH leaf faces until the actual sides are clear.

    The top edge may pass inside a side panel; moving only along the
    curve normal does not clear that end. Native queries only during assembly."""
    apoios = [(o, o.matrix_world.inverted()) for o in
              _modulos._estruturais(_modulos._chapas_do_conjunto(conj))]
    folga = _portas.RESPIRO_PORTA_MM / 1000

    def livre(a, b):
        for obj, inv in apoios:
            for altura in (alturas[0], sum(alturas)/2, alturas[1]):
                for t in (0, .5, 1):
                    pt = inv @ Vector((*(a.lerp(b, t)), altura))
                    hit, co, normal, _i = obj.closest_point_on_mesh(pt)
                    if hit:
                        if (pt-co).length < folga - 2e-6:
                            return False
                        if (pt-co).dot(normal) < 0:
                            # At a corner, closest_point may return another face's
                            # normal. Native parity distinguishes inside from outside
                            # without extending that plane indefinitely.
                            direcao = Vector((.7123,.3217,.6271)).normalized()
                            origem = pt.copy(); cruzamentos = 0
                            for _ in range(64):
                                bateu, ponto, _n, _i = obj.ray_cast(origem, direcao)
                                if not bateu:
                                    break
                                cruzamentos += 1
                                origem = ponto + direcao*1e-6
                            if cruzamentos % 2:
                                return False
                inicio = inv @ Vector((*a, altura))
                fim = inv @ Vector((*b, altura))
                if obj.ray_cast(inicio, fim-inicio, distance=(fim-inicio).length)[0]:
                    return False
        return True

    dentro, fora = list(dentro), list(fora)
    for _ponta in range(2):
        if not livre(dentro[0], fora[0]):
            achou = False
            for i in range(len(dentro)-1):
                for passo in range(1, 17):
                    t = passo/16
                    if not livre(dentro[i].lerp(dentro[i+1], t),
                                 fora[i].lerp(fora[i+1], t)):
                        continue
                    lo, hi = (passo-1)/16, t
                    for _ in range(24):
                        meio = (lo+hi)/2
                        if livre(dentro[i].lerp(dentro[i+1], meio),
                                 fora[i].lerp(fora[i+1], meio)):
                            hi = meio
                        else:
                            lo = meio
                    dentro = [dentro[i].lerp(dentro[i+1], hi)] + dentro[i+1:]
                    fora = [fora[i].lerp(fora[i+1], hi)] + fora[i+1:]
                    achou = True
                    break
                if achou:
                    break
            if not achou:
                return None
        dentro.reverse(); fora.reverse()
    return dentro, fora


def _perfil_curvo_positivo(folha):
    # DXFs also contain inverted faces. Recognizing an oriented copy
    # avoids using the inner surface as the front without touching the wood
    # before knowing whether fitting is possible.
    copia=folha.copy();copia.data=folha.data.copy();me=copia.data
    try:
        bm=bmesh.new()
        try:
            bm.from_mesh(me);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(me)
        finally:bm.free()
        for nome in (_frentes.ATR_FACE,_frentes.ATR_BORDA):
            a=me.attributes.get(nome)
            if a is not None:me.attributes.remove(a)
        if _frentes.CHAVE in me:del me[_frentes.CHAVE]
        for chave in ('porta_linha_frente','porta_linha_indices'):
            if chave in copia:del copia[chave]
        ref=_frentes.preparar(copia,forcar=True)
        perfil=_frentes.perfil(copia,fechada=True) if ref else None
        return perfil,ref
    finally:
        bpy.data.objects.remove(copia,do_unlink=True);bpy.data.meshes.remove(me)


def _transportar_madeira_curva(folha,pontos,destino,verso):
    """Fit the path by length, preserving the section, cutouts, and ALL
    vertices/faces. Do not replace the wood with a new extrusion."""
    perfil,ref=_perfil_curvo_positivo(folha)
    if perfil is None:return None
    origem=[p.xy for p in perfil[0]]
    alvos=[p.copy() for p in destino]
    fundos=[p.copy() for p in verso]
    fechada=_portas._ferragens._matriz_fechada(folha)
    costas=[(fechada@Vector(p)).xy for p in ref['tras']]
    if len(origem)<2 or len(alvos)<2:return None
    invertido=((origem[0]-alvos[-1]).length+(origem[-1]-alvos[0]).length <
               (origem[0]-alvos[0]).length+(origem[-1]-alvos[-1]).length)
    if invertido:alvos.reverse();fundos.reverse()
    if ((costas[0]-origem[0]).length+(costas[-1]-origem[-1]).length >
            (costas[-1]-origem[0]).length+(costas[0]-origem[-1]).length):costas.reverse()
    def trechos(ps):
        saida=[];total=0.;marcos=[0.];anterior=None
        for i,(a,b) in enumerate(zip(ps,ps[1:])):
            d=b-a;l=d.length
            if l<1e-8:continue
            if anterior is not None and anterior.dot(d/l)<.95:marcos.append(total)
            saida.append((a,d,l,total,i));total+=l;anterior=d/l
        marcos.append(total)
        return saida,total,marcos
    frente,lt,mf=trechos(origem);tras,lb,mb=trechos(costas)
    _tf,comprimento,af=trechos(alvos);_tb,fundo,ab=trechos(fundos)
    if min(lt,lb,comprimento,fundo)<1e-8:return None
    if len({len(mf),len(mb),len(af),len(ab)})!=1:return None
    def coordenada(s,marcos):
        k=next((i for i in range(len(marcos)-1) if s<=marcos[i+1]+1e-10),len(marcos)-2)
        return k+(s-marcos[k])/max(marcos[k+1]-marcos[k],1e-12)
    def distancia(u,marcos):
        k=max(0,min(len(marcos)-2,int(u)))
        return marcos[k]+(u-k)*(marcos[k+1]-marcos[k])
    def parametro(p,segmentos,marcos):
        candidatos=[]
        for a,d,l,s,i in segmentos:
            t=max(0.,min(1.,(p-a).dot(d)/(l*l)))
            q=a+d*t
            candidatos.append(((p-q).length,coordenada(s+t*l,marcos),q,i))
        return min(candidatos,key=lambda c:c[0])
    novos=[]
    for p in pontos:
        df,sf,qf,i=parametro(p.xy,frente,mf);db,sb,qb,j=parametro(p.xy,tras,mb)
        t=df/max(df+db,1e-12);s=sf*(1-t)+sb*t
        a,ta=_frentes._amostra(alvos,distancia(s,af))
        b,tb=_frentes._amostra(fundos,distancia(s,ab))
        oa,sa=_frentes._amostra(origem,distancia(s,mf))
        ob,sb=_frentes._amostra(costas,distancia(s,mb))
        st=sa.lerp(sb,t).normalized();sn=(oa-ob).normalized()
        dt=ta.lerp(tb,t).normalized();dn=(a-b).normalized()
        base=Matrix(((st.x,sn.x),(st.y,sn.y)))
        if abs(base.determinant())<1e-8:return None
        residual=base.inverted()@(p.xy-oa.lerp(ob,t))
        # The residual preserves relief, cutouts, and corners between both
        # paths. If the profile is unchanged, no vertex moves.
        xy=a.lerp(b,t)+dt*residual.x+dn*residual.y
        novos.append(Vector((*xy,p.z)))
    return novos


def _limite_curvo_no_corpo(grupo,folha):
    """Sweep prepared during assembly with native BVH ray casts. The slider
    reads only the numeric limit; it neither queries meshes nor builds the door."""
    ferragens=_portas._ferragens
    conj=_portas._modulo_da_chapa(folha)
    corpo=[]
    for o in _modulos._estruturais(_modulos._chapas_do_conjunto(conj)):
        if o.type!='MESH' or o==folha:continue
        ps=[o.matrix_world@v.co for v in o.data.vertices]
        if not ps:continue
        arvore=ferragens.BVHTree.FromPolygons(ps,[list(f.vertices) for f in o.data.polygons])
        lo=Vector(tuple(min(v[k] for v in ps) for k in range(3)))
        hi=Vector(tuple(max(v[k] for v in ps) for k in range(3)))
        corpo.append((arvore,lo,hi))
    p=_portas._copiar_parametros(grupo['porta_parametros']);p.pop('abertura_limite_graus',None)
    dados=ferragens._dados_da_folha(folha);largura=float(grupo['porta_vao_largura_mm'])
    locais=[v.co.copy() for v in folha.data.vertices];arestas=[tuple(e.vertices) for e in folha.data.edges]
    def colide(graus):
        m=grupo.matrix_world@ferragens._matriz_abertura(p,largura,1,0,dados,graus/ferragens.ABERTURA_MAX_GRAUS['GIRO'])
        ps=[m@v for v in locais]
        lo=Vector(tuple(min(v[k] for v in ps) for k in range(3)))
        hi=Vector(tuple(max(v[k] for v in ps) for k in range(3)))
        for arvore,a,b in corpo:
            if any(min(hi[k],b[k])-max(lo[k],a[k])<=.00001 for k in range(3)):continue
            for i,j in arestas:
                d=ps[j]-ps[i];l=d.length
                if l<=.00002:continue
                u=d/l
                hit,_n,_f,_dist=arvore.ray_cast(ps[i]+u*.00001,u,l-.00002)
                if hit is not None:return True
        return False
    # A closed pose already obstructed supplies no free interval:
    # preserve legacy travel without presenting it as a validated limit.
    if colide(0):return None
    seguro=0.
    for graus in range(1,int(ferragens.ABERTURA_MAX_GRAUS['GIRO'])+1):
        if colide(graus):
            a,b=seguro,float(graus)
            for _ in range(8):
                meio=(a+b)/2
                if colide(meio):b=meio
                else:a=meio
            return max(0.,a-.25)
        seguro=float(graus)
    return seguro


def alinhar_frente_ao_corpo(grupo):
    """A diagonal door uses the carcass profile, including the tangent at
    the hinge support. Rebuild only on edit/import; opening is native."""
    folhas = _portas._folhas_portas(grupo)
    if len(folhas) != 1:
        return False
    folha = folhas[0]
    ja_alinhada=bool(grupo.get('porta_perfil_corpo'))
    conj = _portas._modulo_da_chapa(folha)
    if conj is None:
        return False
    linha = _linha_do_corpo(conj, folha)
    if linha is None:
        return False
    p = _portas._copiar_parametros(grupo['porta_parametros'])
    L,A = grupo['porta_vao_largura_mm'],grupo['porta_vao_altura_mm']
    l,a,e,c = _portas._calcular_folhas_portas(L,A,p)[0]
    fechada = _portas._ferragens._matriz_fechada(folha)
    antigos = [fechada @ v.co for v in folha.data.vertices]
    z0,z1 = min(v.z for v in antigos),max(v.z for v in antigos)
    # The DXF plate still identifies WHICH end is hinged, but its
    # normal does not replace the body's normal or the leaf's tangent.
    x = -l/2000 if p['dobradica_lado']=='ESQUERDA' else l/2000
    apoio = (fechada @ Vector((x,0,-e/2000))).xy
    ponta = (0 if not grupo.get('porta_perfil_corpo') else
             0 if (linha[0]-apoio).length < (linha[-1]-apoio).length else -1)
    esp = float(p['espessura_mm'])
    if folha.get('porta_curva_modelada') and not grupo.get('porta_perfil_corpo'):
        # The DXF's shortest edge was an arc segment (8.24 mm), not the
        # thickness. The body supplies this assembly's nominal wood thickness.
        esp = float(conj.conj_espessura_mm)
    dentro = _afastar_linha(linha, _portas.RESPIRO_PORTA_MM/1000)
    fora_linha = _afastar_linha(linha, (_portas.RESPIRO_PORTA_MM+esp)/1000)
    limitado = _limitar_pontas_frente(conj, dentro, fora_linha, (z0,z1))
    if limitado is None:
        return False
    dentro, fora_linha = limitado
    modelada=(_transportar_madeira_curva(folha,antigos,fora_linha,dentro)
              if folha.get('porta_curva_modelada') else None)
    if folha.get('porta_curva_modelada') and (modelada is None or len(modelada)!=len(folha.data.vertices)):
        return False
    p.update(espessura_mm=esp,folga_mm=0,respiro_original=True,
             afastamento_mm=0,cobertura_esq_e=0,cobertura_dir_e=0,
             cobertura_baixo_e=0,cobertura_cima_e=0)
    p.pop('dobradica_modelo_reta',None)
    p['dobradica']='CURVA'
    p['dobradica_apoio_real']=True
    tentativas = (ponta,) if grupo.get('porta_perfil_corpo') else (0,-1)
    for ponta in tentativas:
        passo = dentro[1]-dentro[0] if ponta == 0 else dentro[-1]-dentro[-2]
        fora = Vector((passo.y,-passo.x,0)).normalized()
        cima = Vector((0,0,1));direita=cima.cross(fora)
        ref = Matrix((direita,cima,fora)).transposed()
        nova = ref.to_4x4()
        locais = [ref.transposed() @ Vector((v.x,v.y,z)) for z in (z0,z1) for v in dentro+fora_linha]
        lo = Vector(tuple(min(v[k] for v in locais) for k in range(3)))
        hi = Vector(tuple(max(v[k] for v in locais) for k in range(3)))
        # Z=0 is the rear face at the hinged end, not the sagitta extreme.
        tras = (ref.transposed() @ Vector((*dentro[ponta],z0))).z
        nova.translation = ref @ Vector((lo.x,lo.y,tras))
        largura,altura=(hi.x-lo.x)*1000,(hi.y-lo.y)*1000
        ponto_local = nova.inverted() @ Vector((*dentro[ponta],z0))
        p['dobradica_lado'] = 'ESQUERDA' if ponto_local.x < largura/2000 else 'DIREITA'
        calculadas=_portas._calcular_folhas_portas(largura,altura,p)
        apoios=_portas._ferragens._apoios_obliquos(conj,nova,p,largura,altura,calculadas)
        esperados=sum(len(ds) for _ar,ds,_i in _portas._ferragens._dobradicas_da_porta(p,largura,altura,calculadas))
        if esperados and len(apoios) >= esperados:
            break
    else:
        if not grupo.get('porta_perfil_corpo'):
            return False
    fracao=float(folha.get(_portas._ferragens.CHAVE_ABERTURA,0))
    # The leaf keeps its native ID; apply the final profile below.
    _portas._aplicar_portas(bpy.context,grupo,nova,conj,largura,altura,p)
    bpy.context.view_layer.update()
    inversa = _portas._ferragens._matriz_fechada(folha).inverted()
    secao = dentro+list(reversed(fora_linha));n=len(secao);m=len(dentro)
    vs=[inversa @ Vector((v.x,v.y,z)) for z in (z0,z1) for v in secao]
    fs=[(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)]
    for i in range(m-1):
        fs.extend(((i,i+1,n-2-i,n-1-i),(n+i,2*n-1-i,2*n-2-i,n+i+1)))
    if modelada is not None:
        if len(modelada)!=len(folha.data.vertices):
            raise RuntimeError("Assembly changed the modeled leaf's topology")
        for v,ponto in zip(folha.data.vertices,modelada):v.co=inversa@ponto
        # Reversing the path may reverse the solid's orientation.
        # Native normals preserve per-corner UVs and make the handle project
        # from the physical face instead of pointing into the wood.
        bm=bmesh.new()
        try:
            bm.from_mesh(folha.data)
            bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(folha.data)
        finally:bm.free()
    else:
        bm=bmesh.new()
        try:
            folha.data.clear_geometry();folha.data.from_pydata(vs,[],fs)
            bm.from_mesh(folha.data);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(folha.data)
        finally:bm.free()
    folha.data.update()
    if len(linha)>2:
        folha['porta_curva_modelada']=1
    elif 'porta_curva_modelada' in folha:
        del folha['porta_curva_modelada']
    if len(linha)>2:
        folha['porta_linha_frente']=[list(inversa @ Vector((v.x,v.y,z0))) for v in fora_linha]
        if modelada is None:folha['porta_linha_indices']=[n-1-i for i in range(m)]
        else:
            # Legacy compatibility; current consumers use FACE/
            # EDGE. The query uses actual vertices, not the extrusion.
            folha['porta_linha_indices']=[min(range(len(folha.data.vertices)),
                key=lambda i:(folha.data.vertices[i].co-Vector(v)).length_squared)
                for v in folha['porta_linha_frente']]
    else:
        for chave in ('porta_linha_frente','porta_linha_indices'):
            if chave in folha:del folha[chave]
    grupo['porta_perfil_corpo']=1
    grupo['porta_perfil_versao']=2
    grupo['porta_perfil_ponta']=ponta
    grupo['porta_perfil_lado']=p['dobradica_lado']
    if 'chapa_edicao' in folha:del folha['chapa_edicao']
    if modelada is not None:
        for chave in (_frentes.ATR_FACE,_frentes.ATR_BORDA):
            a=folha.data.attributes.get(chave)
            if a is not None:folha.data.attributes.remove(a)
        if _frentes.CHAVE in folha.data:del folha.data[_frentes.CHAVE]
    _frentes.preparar(folha,forcar=True)
    if len(linha)>2:
        for pux in list(folha.children):
            if _chapas.MARCA_PUXADOR in pux and pux.get('puxador_tipo')=='PERFIL':
                bpy.data.objects.remove(pux,do_unlink=True)
        if not any(_chapas.MARCA_PUXADOR in o for o in folha.children):
            _puxadores.criar_puxador(bpy.context,folha,'ALCA',
                'X+' if p['dobradica_lado']=='ESQUERDA' else 'X-',1)
    else:
        _chapas.gerar_malha_chapa(folha)
    for pux in folha.children:
        if _chapas.MARCA_PUXADOR in pux:
            if not ja_alinhada and str(pux.get('puxador_borda','')).startswith('X'):
                pux['puxador_borda']='X+' if p['dobradica_lado']=='ESQUERDA' else 'X-'
            _puxadores.posicionar_puxador(pux)
    _portas.gravar_vao_orientado(grupo,conj)
    if folha.get('porta_curva_modelada'):
        limite=_limite_curvo_no_corpo(grupo,folha)
        parametros=_portas._copiar_parametros(grupo['porta_parametros'])
        if limite is None:parametros.pop('abertura_limite_graus',None)
        else:parametros['abertura_limite_graus']=limite
        grupo['porta_parametros']=parametros
        grupo['porta_limite_pendente']=False
        grupo['porta_limite_validado']=limite is not None
    _portas._ferragens._refazer_ferragens(grupo)
    _portas._ferragens._definir_abertura(bpy.context,folha,fracao)
    bpy.context.view_layer.update()
    return True


def corrigir_curvas_legadas(conj,paineis_fixos=()):
    """Once during assembly/attachment, using geometry and measured references,
    not category. A plate above the wood does not hinge a plinth."""
    mudancas=0
    for g in list(_portas._portas_do_conjunto(conj)):
        fs=_portas._folhas_portas(g)
        if len(fs)!=1 or g.get('porta_perfil_corpo'):continue
        folha=fs[0]
        if not folha.get('porta_curva_modelada') or not folha.get('porta_origem_promob'):continue
        p=g['porta_parametros'];refs=p.get('dobradicas_referencia',{}).get('0',[])
        if g.name in paineis_fixos:
            # Preserve the actual component and its data; remove only the automatic
            # system created from the neighboring door's plate.
            fechada=_portas._ferragens._matriz_fechada(folha)
            for o in list(_portas._ferragens._ferragens_portas(g)):
                _portas._ferragens._remover_ferragem(o)
            # Handles are an independent choice: even an automatically created
            # model may have been edited later. The audited asset migration
            # cleans up its own accessories outside this helper.
            folha.parent=conj;folha.matrix_parent_inverse=Matrix.Identity(4);folha.matrix_world=fechada
            for chave in list(folha.keys()):
                if chave.startswith('porta_') or chave==_chapas.MARCA_FOLHA:del folha[chave]
            folha['eh_peca_curva']=1
            for o in list(g.children):
                mundo=o.matrix_world.copy();o.parent=conj;o.matrix_world=mundo
            bpy.data.objects.remove(g,do_unlink=True);mudancas+=1
        else:
            # The legacy clamp lost the plate distance. That is not evidence
            # for removing a system; only the audited migration confirms it.
            if refs and all(float(r)<=1e-6 or float(r)>=1-1e-6 for r in refs):continue
            linha=_linha_do_corpo(conj,folha)
            if linha and len(linha)>3 and alinhar_frente_ao_corpo(g):mudancas+=1
    if mudancas:
        bpy.context.view_layer.update();_modulos.sincronizar_medidas_conjunto(conj)
    return mudancas


def integrar_frentes_diagonais(conj):
    """Exports without a recognizable plate may still have a modeled front.
    Adopt only a tall panel following the actual body edge."""
    grupos=_portas._portas_do_conjunto(conj)
    if not grupos:
        altura=float(conj.conj_altura_mm)/1000
        for obj in list(conj.children):
            if obj.type!='MESH' or not obj.get('eh_peca_curva'):
                continue
            originais=[obj.matrix_world@v.co for v in obj.data.vertices]
            z0,z1=min(v.z for v in originais),max(v.z for v in originais)
            if z1-z0<altura*.6:
                continue
            obj['porta_curva_modelada']=1
            linha=_linha_do_corpo(conj,obj)
            del obj['porta_curva_modelada']
            if linha is None:
                continue
            t=linha[1]-linha[0];fora=Vector((t.y,-t.x,0)).normalized()
            cima=Vector((0,0,1));ref=Matrix((cima.cross(fora),cima,fora)).transposed()
            vs=[ref.transposed()@v for v in originais]
            lo=Vector(tuple(min(v[k] for v in vs) for k in range(3)))
            hi=Vector(tuple(max(v[k] for v in vs) for k in range(3)))
            matriz=ref.to_4x4();matriz.translation=ref@lo
            p=_portas._parametros_portas_da_cena(bpy.context.scene,numerico=True)
            p.update(abertura='GIRO',folhas=1,dobradica='CURVA',dobradica_lado='ESQUERDA',
                     espessura_mm=float(conj.conj_espessura_mm),folga_mm=0,dobradicas_qtd=2)
            g=_portas._aplicar_portas(bpy.context,None,matriz,conj,(hi.x-lo.x)*1000,
                                     (z1-z0)*1000,p,frente='NEG_Y',largura_em='X')
            folha=_portas._folhas_portas(g)[0]
            inv=_portas._ferragens._matriz_fechada(folha).inverted()
            folha.data.clear_geometry()
            folha.data.from_pydata([inv@v for v in originais],[],[list(p.vertices) for p in obj.data.polygons])
            folha.data.update();folha['porta_curva_modelada']=1
            if alinhar_frente_ao_corpo(g):
                folha.data.materials.clear()
                for slot in obj.material_slots:
                    folha.data.materials.append(slot.material)
                    folha.material_slots[-1].link=slot.link
                    folha.material_slots[-1].material=slot.material
                malha=obj.data;bpy.data.objects.remove(obj,do_unlink=True)
                if malha.users==0:bpy.data.meshes.remove(malha)
                grupos.append(g)
            else:
                for filho in list(g.children_recursive):bpy.data.objects.remove(filho,do_unlink=True)
                bpy.data.objects.remove(g,do_unlink=True)
    for g in grupos:
        if not g.get('porta_perfil_corpo') or g.get('porta_perfil_versao', 0) < 2:
            alinhar_frente_ao_corpo(g)
        if g.get('porta_perfil_corpo'):
            g[_portas.CHAVE_MODULO_PORTA]=conj.name
            g[_portas.CHAVE_FOLGAS_PORTA]=(0,0,0,0)
            g[_portas.CHAVE_RECUO_PORTA]=0
    return grupos


def _portas_referenciadas(pecas, ferragens):
    associadas = _referencias_dobradicas(pecas, ferragens)
    ids = {id(a['frente']) for a in associadas}
    saida = []
    for a in associadas:
        ref = a['referencia']
        f = _em_referencia(a['frente'], ref)
        centros = a['centros']
        distancias = {
            'ESQUERDA': max(abs(c.x - f['lo'][0]) for c in centros) / _tam(f, 0),
            'DIREITA': max(abs(f['hi'][0] - c.x) for c in centros) / _tam(f, 0),
            'CIMA': max(abs(f['hi'][2] - c.z) for c in centros) / _tam(f, 2)}
        lado = min(distancias, key=distancias.get)
        if distancias[lado] > 0.3:
            continue
        corpo = [_em_referencia(p, ref) for p in pecas if p is not a['frente']
                 and (id(p) not in ids or abs(Vector(p['normal']).dot(ref.col[1])) < .05)]
        face = f['hi'][1]
        def apoios_lado(lado):
            cx, cz = _centro(f, 0), _centro(f, 2)
            return [p for p in corpo if p['eixo'] == (2 if lado == 'CIMA' else 0)
                    and p['lo'][1] - 1 <= face + 5 <= p['hi'][1] + 1
                    and (p['lo'][0] < cx < p['hi'][0] if lado == 'CIMA'
                         else p['lo'][2] < cz < p['hi'][2])
                    and (p['lo'][2] >= cz if lado == 'CIMA' else
                         p['hi'][0] <= cx if lado == 'ESQUERDA' else p['lo'][0] >= cx)
                    and abs((p['lo'][2] - f['hi'][2]) if lado == 'CIMA' else
                            (p['hi'][0] - f['lo'][0]) if lado == 'ESQUERDA' else
                            (p['lo'][0] - f['hi'][0])) <= ALCANCE_VAO_MM]
        # Some corners use a special inter-leaf joint in DXF
        # (135/180 degrees). Our standard hinge requires support:
        # do not mount at the free joint if only the opposite edge has a side panel.
        paralelo = None
        if lado in ('ESQUERDA', 'DIREITA') and not apoios_lado(lado):
            borda_x = f['lo'][0] if lado == 'ESQUERDA' else f['hi'][0]
            candidatos = [_em_referencia(p, ref) for p in pecas if p is not a['frente']
                          and not p['curva'] and 'normal' in p
                          and abs(Vector(p['normal']).dot(ref.col[1])) > .995]
            candidatos = [p for p in candidatos if p['lo'][2] < _centro(f, 2) < p['hi'][2]
                          and min(abs(p['lo'][1] - face), abs(p['hi'][1] - face)) < 25
                          and (p['hi'][0] <= _centro(f, 0) if lado == 'ESQUERDA'
                               else p['lo'][0] >= _centro(f, 0))
                          and abs((p['hi'][0] if lado == 'ESQUERDA' else p['lo'][0]) - borda_x) < 40]
            if candidatos:
                paralelo = min(candidatos, key=lambda p: abs(
                    (p['hi'][0] if lado == 'ESQUERDA' else p['lo'][0]) - borda_x))
            oposto = 'DIREITA' if lado == 'ESQUERDA' else 'ESQUERDA'
            if paralelo is None and apoios_lado(oposto):
                lado = oposto
        vao = list(vao_atras(corpo, f, face))
        # Support limit on the hinged side; the other side may be the free
        # joint with the neighboring leaf, never an invented support.
        indice = {'ESQUERDA': 0, 'DIREITA': 1, 'CIMA': 3}[lado]
        apoios = [p for p in corpo if id(p['original']) in ids
                  and p['eixo'] == (2 if lado == 'CIMA' else 0)
                  and p['lo'][1] - 1 <= face + 5 <= p['hi'][1] + 1
                  and abs((p['lo'][2] if lado == 'CIMA' else
                           p['hi'][0] if lado == 'ESQUERDA' else p['lo'][0]) - vao[indice]) < 1]
        apoio = paralelo if paralelo is not None else (apoios[0] if apoios else None)
        # FIXED trim is not another leaf. A hinged joint exists only
        # between doors recognized from DXF hardware.
        articulada = paralelo is not None and id(paralelo['original']) in ids
        if articulada:
            vao[indice] = (paralelo['hi'][0] + 2 if lado == 'ESQUERDA'
                           else paralelo['lo'][0] - 2)
        saida.append(dict(folhas=[f], lado=lado, plano=face, vao=tuple(vao),
                          referencia=ref, centros=[centros], apoio_indice=indice,
                          articulada=articulada,
                          apoio=apoio['original'].get('origem')
                          if apoio and id(apoio['original']) in ids else None,
                          apoio_plano_mm=face - paralelo['hi'][1] if articulada else 0))
        oposto = 'DIREITA' if lado == 'ESQUERDA' else 'ESQUERDA'
        saida[-1]['lado_externo'] = oposto if lado != 'CIMA' and apoios_lado(oposto) else None
    por_nome = {p['folhas'][0].get('origem'): p for p in saida}
    ciclos = [p for p in saida if p.get('apoio') in por_nome
              and por_nome[p['apoio']].get('apoio') == p['folhas'][0].get('origem')]
    # Two leaves cannot support each other at a free joint.
    # If DXF indicates that cycle, use the actual box sides instead.
    for p in ciclos:
        if p.get('lado_externo'):
            p.update(lado=p['lado_externo'], articulada=False, apoio=None, apoio_plano_mm=0)
            corpo = [_em_referencia(q, p['referencia']) for q in pecas if id(q) not in ids]
            p['vao'] = vao_atras(corpo, p['folhas'][0], p['plano'])
    saida.sort(key=lambda p: p['folhas'][0]['lo'][0])
    grupos = []
    while saida:
        a = saida.pop(0)
        fa = a['folhas'][0]
        par = next((b for b in saida if not a.get('articulada') and not b.get('articulada')
                    and a['lado'] == 'ESQUERDA' and b['lado'] == 'DIREITA'
                    and (a['referencia'].col[1] - b['referencia'].col[1]).length < 0.001
                    and abs(a['plano'] - b['plano']) < 1
                    and abs(fa['lo'][2] - b['folhas'][0]['lo'][2]) < 3
                    and abs(fa['hi'][2] - b['folhas'][0]['hi'][2]) < 3
                    and 0 <= b['folhas'][0]['lo'][0] - fa['hi'][0] <= FOLGA_PAR_MM), None)
        if par:
            saida.remove(par)
            a['folhas'] += [_em_referencia(f['original'],a['referencia']) for f in par['folhas']]
            a['centros'] += [[a['referencia'].transposed() @ (par['referencia'] @ c) for c in cs]
                            for cs in par['centros']]
            corpo = [_em_referencia(p, a['referencia']) for p in pecas if id(p) not in ids]
            a['vao'] = vao_atras(corpo, _uniao(a['folhas']), a['plano'])
        grupos.append(a)
    return grupos


def _tam(p, k):
    return p['hi'][k] - p['lo'][k]


def _centro(p, k):
    return (p['lo'][k] + p['hi'][k]) / 2.0


def _cruza(a, b, k, folga=0.0):
    return a['lo'][k] - folga < b['hi'][k] and b['lo'][k] - folga < a['hi'][k]


def _dentro(a, b, k, folga=0.0):
    """Whether a fits inside b along axis k."""
    return a['lo'][k] >= b['lo'][k] - folga and a['hi'][k] <= b['hi'][k] + folga


def _uniao(pecas):
    return {'lo': [min(p['lo'][k] for p in pecas) for k in range(3)],
            'hi': [max(p['hi'][k] for p in pecas) for k in range(3)]}


# ------------------------------------------------------------ reading
def _dobradicas(frente, ferragens):
    """Hinges (small hardware) touching the back of the front."""
    plano = frente['hi'][1]
    return [f for f in ferragens
            if f['cor'] == COR_FERRAGEM
            and max(_tam(f, k) for k in range(3)) <= DOBRADICA_MAXIMA_MM
            and _cruza(f, frente, 0, 10.0) and _cruza(f, frente, 2, 10.0)
            and f['lo'][1] < plano + ALCANCE_DOBRADICA_MM and f['hi'][1] > plano - 5.0]


def _caixa_de_gaveta(frente, corpo, costas, multinivel=False):
    """Box components behind the front (sides, inner front, rear, bottom),
    or [] if there is no box: >= 2 long upright sides with X normals,
    all INSIDE the opening behind the front and away from the cabinet
    back (`costas`, y mm). The cabinet base, sides, and back covered by
    the full front do not belong to this box."""
    x0, x1, z0, z1 = vao_atras(corpo, frente, frente['hi'][1], costas)
    vao = {'lo': [x0, 0.0, z0], 'hi': [x1, 0.0, z1]}
    pecas = [p for p in corpo
             if _dentro(p, vao, 0, 2.0) and _dentro(p, vao, 2, 2.0)
             and p['lo'][1] >= frente['lo'][1] - 1.0
             and p['hi'][1] < costas - 15.0]
    laterais = [p for p in pecas if p['eixo'] == 0
                and _tam(p, 1) >= LATERAL_GAVETA_MINIMA_MM]
    pares = [(a, b) for a in laterais for b in laterais if a['hi'][0] < b['lo'][0]
             and abs(a['lo'][2] - b['lo'][2]) < 3
             and abs(a['lo'][1] - b['lo'][1]) < 15 and abs(a['hi'][1] - b['hi'][1]) < 15]
    faixas = {round(a['lo'][2]) for a, b in pares}
    # A full side can cover SEVERAL boxes: it is not a front.
    if not faixas or (len(faixas) != 1 and not multinivel):
        return []
    a, b = max(pares, key=lambda par: par[1]['lo'][0] - par[0]['hi'][0])
    baixo = min(q['lo'][2] for par in pares for q in par)
    cima = max(q['hi'][2] for par in pares for q in par)
    if (_tam(frente, 2) - (cima-baixo) < 5
            or baixo - frente['lo'][2] > max(60, .3 * _tam(frente, 2))):
        return []
    return [p for p in pecas if p['lo'][2] >= baixo - (10 if p['eixo'] == 2 else 2)
            and p['hi'][2] <= cima + 2
            # Curved bottoms/inner fronts extend beyond straight sides.
            and p['lo'][1] >= min(frente['lo'][1], a['lo'][1], b['lo'][1]) - 1
            and p['hi'][1] <= max(a['hi'][1], b['hi'][1]) + 15]


def _gavetas_em_faces(pecas, ferragens, portas):
    """Single box behind a vertical FACE, including rotated islands.
    Aluminum sides are box references, never models to retain."""
    encontrados, cache = [], {}
    for f in pecas:
        if id(f) in portas or f['curva'] or 'normal' not in f:
            continue
        n = Vector(f['normal']).normalized()
        if abs(n.z) > .05:
            continue
        for dentro in (n, -n):
            direita = Vector((0, 0, 1)).cross(-dentro).normalized()
            ref = Matrix((direita, dentro, Vector((0, 0, 1)))).transposed()
            chave = tuple(round(v, 4) for linha in ref for v in linha)
            if chave not in cache:
                cache[chave] = ([_em_referencia(p, ref) for p in pecas],
                    [_em_referencia(p, ref) for p in ferragens if p['cor'] == COR_ALUMINIO])
            projetadas, metais = cache[chave]
            frente = next(p for p in projetadas if p['original'] is f)
            if _tam(frente, 0) < 100 or _tam(frente, 2) < 60:
                continue
            corpo = [p for p in projetadas if p['original'] is not f and id(p['original']) not in portas]
            if not corpo:
                continue
            metal = []
            for q in metais:
                if q['eixo'] is None:
                    q['eixo'] = min(range(3), key=lambda k: _tam(q, k))
                if _tam(q, q['eixo']) <= 30:
                    metal.append(q)
            costas = max(p['hi'][1] for p in corpo)
            # Spice pull-out: a tall front with boxes at several levels.
            # A handle on the face confirms the front; a side has none.
            puxadores = [_em_referencia(p,ref) for p in ferragens if p['cor'] == 8]
            puxador_na_face = any(_dentro(p,frente,0,5) and _dentro(p,frente,2,5)
                and p['hi'][1] <= frente['hi'][1]+5
                and p['hi'][1] >= frente['lo'][1]-30 for p in puxadores)
            frente_estreita = _tam(frente,0) < 250 and _tam(frente,2) > 2 * _tam(frente,0)
            caixa = _caixa_de_gaveta(frente, corpo + metal, costas,
                                    puxador_na_face or frente_estreita)
            if caixa:
                encontrados.append(dict(frente=frente, caixa=caixa, referencia=ref))
                break
    grupos = []
    # Join stacks only on the SAME face, never opposite sides of an island.
    while encontrados:
        ref = encontrados[0]['referencia']
        lado = [g for g in encontrados if (g['referencia'] - ref).col[1].length < .001]
        encontrados = [g for g in encontrados if g not in lado]
        for pilha in _pilhas(lado):
            fs = [g['frente'] for g in pilha]
            removidas = {id(p['original']) for g in pilha for p in g['caixa']}
            corpo = [_em_referencia(p, ref) for p in pecas
                     if id(p) not in removidas and id(p) not in portas and p not in [f['original'] for f in fs]]
            face = max(f['hi'][1] for f in fs)
            costas = max(p['hi'][1] for p in corpo)
            uniao = _uniao(fs)
            grupos.append(dict(frentes=fs, plano=face, referencia=ref,
                vao=vao_atras(corpo, uniao, face, costas),
                profundidade=_profundidade(corpo, uniao, face, max(100, costas - face)),
                curva=False, caixa=[p for g in pilha for p in g['caixa']]))
    return grupos


def orientar_modulo(conj, plano):
    """Single front aligned with the box: functional axes without moving components.
    For corners with different faces or diagonal boxes, preserve the axes."""
    refs = [p.get('referencia', Matrix.Identity(3)) for tipo in ('portas', 'gavetas')
            for p in plano[tipo]]
    if not refs:
        return False
    ref = refs[0]
    if any((r.col[1] - ref.col[1]).length > .001 for r in refs[1:]):
        return False
    verticais = [c.matrix_world.to_3x3().col[2].normalized()
                  for c in _modulos._chapas_do_conjunto(conj)
                  if abs(c.matrix_world.to_3x3().col[2].normalized().z) < .05]
    if not all(any(abs(n.dot(ref.col[k])) > .995 for n in verticais) for k in (0, 1)):
        return False
    if (conj.matrix_world.to_3x3().normalized() - ref).col[1].length < .001:
        return False
    filhos = [(c, c.matrix_world.copy()) for c in conj.children]
    nova = ref.to_4x4()
    nova.translation = conj.matrix_world.translation
    conj.matrix_world = nova
    for obj, mundo in filhos:
        obj.matrix_parent_inverse = Matrix.Identity(4)
        obj.matrix_world = mundo
    bpy.context.view_layer.update()
    _modulos.sincronizar_medidas_conjunto(conj)
    return True


ALCANCE_VAO_MM = 40.0        # Opening panel: within this distance of the front edge.
ALCANCE_COSTAS_MM = 30.0     # Cabinet box component: extends to the back.


def _estrutural(p, costas):
    """Cabinet BOX component (side, partition, base, top extending to
    the back), or a narrow rail; excludes the drawer box."""
    return (costas is None or p['hi'][1] >= costas - ALCANCE_COSTAS_MM
            or (p['eixo'] == 2 and _tam(p, 1) <= TRAVESSA_MAXIMA_MM))


def vao_atras(corpo, caixa, plano, costas=None, alcance=None):
    """Opening (x0, x1, z0, z1) in mm behind `caixa`: body panel faces
    reaching the front (`plano`, the rear face of the fronts), nearest
    its center if CLOSE to the front edge. Without a panel on a side
    (drawers below a door with no rail between), use the front edge
    minus the overlay measured on the other sides."""
    cx, cz = _centro(caixa, 0), _centro(caixa, 2)
    y = plano + 5.0
    tocam = [p for p in corpo if p['lo'][1] <= y <= p['hi'][1]]
    # The DRAWER box side and bottom do not define the opening.
    tocam = [p for p in tocam if _estrutural(p, costas)]
    achados = [
        max((p['hi'][0] for p in tocam if p['hi'][0] <= cx
             and p['lo'][2] < cz < p['hi'][2]), default=None),
        min((p['lo'][0] for p in tocam if p['lo'][0] >= cx
             and p['lo'][2] < cz < p['hi'][2]), default=None),
        max((p['hi'][2] for p in tocam if p['hi'][2] <= cz
             and p['lo'][0] < cx < p['hi'][0]), default=None),
        min((p['lo'][2] for p in tocam if p['lo'][2] >= cz
             and p['lo'][0] < cx < p['hi'][0]), default=None),
    ]
    bordas = [caixa['lo'][0], caixa['hi'][0], caixa['lo'][2], caixa['hi'][2]]
    sinais = (1.0, -1.0, 1.0, -1.0)            # Toward the INSIDE of the front.
    alcance = ALCANCE_VAO_MM if alcance is None else alcance
    validos = [a if a is not None and abs(a - b) <= alcance else None
               for a, b in zip(achados, bordas)]
    cobre = [s * (v - b) if v is not None else None
             for v, b, s in zip(validos, bordas, sinais)]

    def cobertura(k):
        # Use the OTHER axis (drawers overlay all four sides equally, measured
        # at the sides); otherwise the opposite side; with neither, use flush.
        outros = [c for j, c in enumerate(cobre) if c is not None and j // 2 != k // 2]
        if not outros:
            outros = [c for c in cobre if c is not None]
        return sum(outros) / len(outros) if outros else 0.0
    return tuple(v if v is not None else b + s * cobertura(k)
                 for k, (v, b, s) in enumerate(zip(validos, bordas, sinais)))


def _profundidade(corpo, caixa, plano, padrao):
    """From the front plane to the first panel behind it (the back), at the center."""
    cx, cz = _centro(caixa, 0), _centro(caixa, 2)
    atras = [p['lo'][1] for p in corpo if p['eixo'] == 1
             and p['lo'][1] > plano + 50.0
             and p['lo'][0] < cx < p['hi'][0] and p['lo'][2] < cz < p['hi'][2]]
    return (min(atras) - plano) if atras else padrao


def _pilhas(gavetas):
    """Stacked drawer fronts of the same width, touching, from bottom
    to top."""
    pilhas = []
    for g in sorted(gavetas, key=lambda g: g['frente']['lo'][2]):
        f = g['frente']
        for pilha in pilhas:
            topo = pilha[-1]['frente']
            if (abs(topo['lo'][0] - f['lo'][0]) <= 5.0
                    and abs(topo['hi'][0] - f['hi'][0]) <= 5.0
                    and 0.0 <= f['lo'][2] - topo['hi'][2] <= FOLGA_PILHA_MM):
                pilha.append(g)
                break
        else:
            pilhas.append([g])
    return pilhas


def portas_sem_faces_opostas(portas):
    """One front per box; the user requested non-through-access islands.
    Perpendicular corners retain two fronts. For opposite faces, use
    the front visible in the standard photo (+X/-Y), then the largest opening."""
    def prioridade(p):
        fora = -p.get('referencia', Matrix.Identity(3)).col[1]
        area = sum(_tam(f,0)*_tam(f,2) for f in p['folhas'])
        return (round(fora.x-fora.y,3),round(area,-2))
    mantidas=[]
    for p in sorted(portas,key=prioridade,reverse=True):
        normal=p.get('referencia',Matrix.Identity(3)).col[1]
        if not any(normal.dot(q.get('referencia',Matrix.Identity(3)).col[1]) < -.95 for q in mantidas):
            mantidas.append(p)
    return [p for p in portas if p in mantidas]


def planejar(pecas, ferragens):
    """Plan each cabinet component's conversion. `pecas` = cabinet panels
    and curves (`peca`); `ferragens` = non-panel components with color.
    Return {'portas': [{'folhas': [front], 'lado', 'vao', 'plano'}],
    'gavetas': [{'frentes', 'vao', 'plano', 'profundidade', 'curva'}],
    'correr': [{'quadros', 'vao', 'plano'}], 'remover': [component],
    'fundo': component|None, 'travessas': [(component, side)]}."""
    plano = {'portas': [], 'gavetas': [], 'correr': [], 'remover': [],
             'fundo': None, 'travessas': []}
    if not pecas:
        return plano
    portas = _portas_referenciadas(pecas, ferragens) + _portas_curvas_referenciadas(pecas,ferragens)
    # Cutouts and distinct faces require measured overlays; do not round
    # edges to straight/curved defaults and create corner interpenetrations.
    for p in portas:
        p['contorno_exato']=True
    plano['portas'] = portas_sem_faces_opostas(portas)
    traseiras = [f['original'] for p in portas if p not in plano['portas'] for f in p['folhas']]
    plano['fechar_traseira'] = bool(traseiras)
    reconhecidas = {id(f['original']) for p in plano['portas'] for f in p['folhas']}
    plano['remover'] += [p for p in pecas if id(p) in reconhecidas]
    plano['remover'] += traseiras
    reconhecidas.update(id(p) for p in traseiras)
    plano['gavetas'] = _gavetas_em_faces(pecas, ferragens, reconhecidas)
    for g in plano['gavetas']:
        plano['remover'] += [f['original'] for f in g['frentes'] + g['caixa'] if f['original'] in pecas]
    ids_gavetas = {id(p) for p in plano['remover']}
    reconhecidas |= ids_gavetas
    ymin = min(p['lo'][1] for p in pecas)
    frentes = [p for p in pecas if p['lo'][1] <= ymin + TOL_FRENTE_MM
               and (p['eixo'] == 1 or p['curva'])
               and _tam(p, 0) >= FRENTE_MINIMA_MM[0]
               and _tam(p, 2) >= FRENTE_MINIMA_MM[1]]
    corpo = [p for p in pecas if p not in frentes and id(p) not in reconhecidas]
    costas = max(p['hi'][1] for p in pecas)
    # Wire basket (deep drawer, spice pull-out): a DXF drawer without an
    # MDF box becomes OUR drawer with the add-on box and rails.
    cestos = [c for c in ferragens if c['cor'] == COR_ALUMINIO
              and all(_tam(c, k) >= CESTO_MINIMO_MM[k] for k in range(3))]
    com_frente = set()
    gavetas, usadas = [], set()
    for f in frentes:
        if id(f) in reconhecidas:
            continue
        # Only curves arrive without 'normal'; planar doors were handled above.
        caixa = _caixa_de_gaveta(f, corpo, costas) if f['curva'] else []
        dob = _dobradicas(f, ferragens) if not f['curva'] else []
        atras = [c for c in cestos
                 if f['lo'][0] - 5.0 <= _centro(c, 0) <= f['hi'][0] + 5.0
                 and f['lo'][2] - 5.0 <= _centro(c, 2) <= f['hi'][2] + 5.0]
        com_frente.update(id(c) for c in atras)
        if (caixa or atras) and not dob:
            gavetas.append({'frente': f, 'caixa': caixa})
            usadas.update(id(p) for p in caixa)
    # One drawer box does not define another's opening.
    corpo = [p for p in corpo if id(p) not in usadas]
    for pilha in _pilhas(gavetas):
        fs = [g['frente'] for g in pilha]
        uniao = _uniao(fs)
        # Rear face of the fronts (for curves, the face at the arc ends).
        face = max(f['hi'][1] for f in fs)
        curva = any(f['curva'] for f in fs)
        plano['gavetas'].append({
            'frentes': fs, 'plano': face,
            'vao': vao_atras(corpo, uniao, face, costas),
            'profundidade': _profundidade(corpo, uniao, face, 500.0),
            'curva': curva})
        plano['remover'] += fs + [p for g in pilha for p in g['caixa']]
    # Basket WITHOUT a panel front (its front was DXF basket geometry): use
    # a drawer filling its entire opening with an add-on front.
    for c in cestos:
        if id(c) in com_frente or c['lo'][1] > ymin + 20.0:
            continue
        x0, x1, z0, z1 = vao_atras(corpo, c, ymin, costas, alcance=1e9)
        caixa = {'lo': [x0, ymin, z0], 'hi': [x1, ymin, z1]}
        plano['gavetas'].append({
            'frentes': [], 'plano': ymin, 'vao': (x0, x1, z0, z1),
            'profundidade': _profundidade(corpo, caixa, ymin, 500.0),
            'curva': False})
    # Sliding doors: aluminum frames at the cabinet front, excluding
    # their glass and DXF rails.
    caixa_modulo = _uniao(pecas)
    quadros = [f for f in ferragens if f['cor'] == COR_ALUMINIO
               and QUADRO_CORRER_MM[0] <= _tam(f, 1) <= QUADRO_CORRER_MM[1]
               and _tam(f, 0) >= 300.0 and _tam(f, 2) >= 300.0
               and _dentro(f, caixa_modulo, 0, 5.0) and _dentro(f, caixa_modulo, 2, 5.0)
               and f['lo'][1] <= ymin + 80.0]
    if quadros:
        uniao = _uniao(quadros)
        plano['correr'].append({'quadros': quadros, 'plano': ymin,
                                'vao': vao_atras(corpo, uniao, ymin, costas)})
    # Back and top rails: cabinet dependents.
    restantes = [p for p in corpo if id(p) not in {id(r) for r in plano['remover']}]
    if restantes:
        caixa = _uniao(restantes)
        L, A = _tam(caixa, 0), _tam(caixa, 2)
        fundos = [p for p in restantes if p['eixo'] == 1
                  and p['espessura'] <= FUNDO_MAXIMO_MM
                  and p['hi'][1] >= caixa['hi'][1] - 30.0
                  and _tam(p, 0) * _tam(p, 2) >= 0.5 * L * A]
        if len(fundos) == 1:
            plano['fundo'] = fundos[0]
        deitadas = [p for p in restantes if p['eixo'] == 2
                    and p['hi'][2] >= caixa['hi'][2] - 1.0]
        tampo = any(_tam(p, 1) > TRAVESSA_MAXIMA_MM for p in deitadas)
        if not tampo:
            for p in deitadas:
                if (_tam(p, 1) <= TRAVESSA_MAXIMA_MM and _tam(p, 0) >= 0.8 * (L - 2 * p['espessura'])):
                    if p['lo'][1] <= caixa['lo'][1] + 5.0:
                        plano['travessas'].append((p, 'FRENTE'))
                    elif p['hi'][1] >= caixa['hi'][1] - 5.0:
                        plano['travessas'].append((p, 'TRAS'))
    plano['prateleiras'] = _prateleiras_do_corpo(restantes) if restantes else []
    if restantes:
        caixa=_uniao(restantes)
        plano['fundos']=[p for p in restantes if 0<p['espessura']<=FUNDO_MAXIMO_MM
            and p.get('eixo') in (0,1) and _tam(p,2)>100
            and min(abs(p['lo'][p['eixo']]-caixa['lo'][p['eixo']]),
                    abs(p['hi'][p['eixo']]-caixa['hi'][p['eixo']]))<=30]
    return plano


def _prateleiras_do_corpo(pecas):
    """Internal horizontal panels by opening/profile, excluding base, top,
    and rails. A vertical partition resting on one defines fixed structure."""
    if not pecas:
        return []
    caixa = _uniao(pecas)
    candidatas = []
    for p in pecas:
        if (p['eixo'] != 2 or _tam(p, 0) < 100 or _tam(p, 1) <= TRAVESSA_MAXIMA_MM
                or p['lo'][2] <= caixa['lo'][2] + p['espessura'] + 5
                or p['hi'][2] >= caixa['hi'][2] - p['espessura'] - 5):
            continue
        apoia_divisoria = any(q['eixo'] in (0, 1) and _tam(q, 2) > 100
            and (abs(q['lo'][2] - p['hi'][2]) < 2 or abs(q['hi'][2] - p['lo'][2]) < 2)
            and _dentro(q, p, 0, 2) and _dentro(q, p, 1, 2) for q in pecas if q is not p)
        if not apoia_divisoria:
            candidatas.append(p)
    grupos = []
    for p in sorted(candidatas, key=lambda p: p['lo'][2]):
        pilha = next((g for g in grupos if all(abs(p[k][e] - g[0][k][e]) < 2
                    for k in ('lo', 'hi') for e in (0, 1))
                    and abs(p['espessura'] - g[0]['espessura']) < .1), None)
        if pilha is None:
            grupos.append([p])
        else:
            pilha.append(p)
    return grupos


# ------------------------------------------------------------ scene
def encaixes_a_ajustar(conj):
    """Bases/tops flush with the outer corner, without touching internal shelves.

    The side already defines the correct height; moving the horizontal
    panel closes the recess without changing thickness, modeled outline,
    doors/drawers, or external size. Use cabinet axes throughout:
    presets may be rotated in the scene."""
    placas = _modulos._estruturais(_modulos._chapas_do_conjunto(conj))
    dados = []
    inversa = conj.matrix_world.inverted()
    for obj in placas:
        matriz = inversa @ obj.matrix_world
        zs = [(matriz @ v.co).z * 1000.0 for v in obj.data.vertices]
        if zs:
            dados.append((obj, min(zs), max(zs),
                          abs(matriz.to_3x3().col[2].normalized().z) > 0.999))
    if not dados:
        return []
    baixo = min(d[1] for d in dados)
    cima = max(d[2] for d in dados)
    ajustes = []
    for obj, z0, z1, deitada in dados:
        if not deitada:
            continue
        folga_baixo, folga_cima = z0 - baixo, cima - z1
        if TOL_ENCAIXE_MM < folga_baixo <= FOLGA_ENCAIXE_MAXIMA_MM:
            ajustes.append((obj, -folga_baixo))
        elif TOL_ENCAIXE_MM < folga_cima <= FOLGA_ENCAIXE_MAXIMA_MM:
            ajustes.append((obj, folga_cima))
    return ajustes


def ajustar_encaixes(conj):
    ajustes = encaixes_a_ajustar(conj)
    if not ajustes:
        return []
    eixo_z = conj.matrix_world.to_3x3() @ Vector((0, 0, 1))
    for obj, delta_mm in ajustes:
        _chapas._definir_centro(obj, obj.matrix_world.translation + eixo_z * (delta_mm / 1000.0))
    bpy.context.view_layer.update()
    # Anchors must remember the corrected assembly, not the old 3 mm offset.
    _chapas.detectar_adjacencia(_modulos._chapas_do_conjunto(conj))
    _modulos.sincronizar_medidas_conjunto(conj)
    return [{'chapa': obj.name, 'deslocamento_mm': delta} for obj, delta in ajustes]


def alinhar_arremates(conj):
    """Nearly full-height vertical slat (export recess up to 3.1 mm)
    ends at the same box corner; do not extend internal partitions."""
    corpos = _modulos._estruturais(_modulos._chapas_do_conjunto(conj))
    inv = conj.matrix_world.inverted()
    dados = []
    for obj in corpos:
        m = inv @ obj.matrix_world
        vs = [m @ v.co * 1000 for v in obj.data.vertices]
        if not vs:
            continue
        lo = Vector(tuple(min(v[k] for v in vs) for k in range(3)))
        hi = Vector(tuple(max(v[k] for v in vs) for k in range(3)))
        dados.append((obj, m, lo, hi))
    if not dados:
        return []
    baixo, cima = min(d[2].z for d in dados), max(d[3].z for d in dados)
    alteradas = []
    for obj, m, lo, hi in dados:
        eixo = max((0, 1), key=lambda k: abs(m.to_3x3().col[k].normalized().z))
        if abs(m.to_3x3().col[eixo].normalized().z) < .999:
            continue
        outra = obj.chapa_comprimento_mm if eixo == 0 else obj.chapa_largura_mm
        if outra > 60.05 or hi.z-lo.z < (cima-baixo)*.8:
            continue
        d0, d1 = lo.z-baixo, cima-hi.z
        if not (TOL_ENCAIXE_MM < max(d0, d1) <= FOLGA_ENCAIXE_MAXIMA_MM):
            continue
        if min(d0, d1) < -TOL_ENCAIXE_MM:
            continue
        prop = 'chapa_largura_mm' if eixo == 0 else 'chapa_comprimento_mm'
        _chapas._ocupado[0] = True
        try:
            setattr(obj, prop, getattr(obj, prop) + d0 + d1)
            _chapas._definir_centro(obj, obj.matrix_world.translation +
                conj.matrix_world.to_3x3() @ Vector((0, 0, (d1-d0)/2000)))
        finally:
            _chapas._ocupado[0] = False
        _chapas.gerar_malha_chapa(obj)
        alteradas.append(obj.name)
    if alteradas:
        bpy.context.view_layer.update()
    return alteradas


def reencaixar_verticais(conj, ajustes):
    """When moving base/top 3 mm outward, a partition that TOUCHED them
    must follow the inner face to avoid creating a new gap.
    Check the actual face with native ray/BVH queries, preserving L-shaped cutouts."""
    inv=conj.matrix_world.inverted()
    corpos=_modulos._estruturais(_modulos._chapas_do_conjunto(conj))
    planos=[]
    for ajuste in ajustes:
        obj=bpy.data.objects.get(ajuste['chapa'])
        if obj is None:continue
        vs=[inv @ (obj.matrix_world @ v.co)*1000 for v in obj.data.vertices]
        baixo=ajuste['deslocamento_mm']<0
        novo=(max(v.z for v in vs) if baixo else min(v.z for v in vs))
        planos.append((obj,baixo,novo,novo-ajuste['deslocamento_mm']))
    alteradas=[]
    for obj in corpos:
        local=inv @ obj.matrix_world
        eixo=max((0,1),key=lambda k:abs(local.to_3x3().col[k].z))
        if abs(local.to_3x3().col[eixo].z)<.999:continue
        vs=[local @ v.co*1000 for v in obj.data.vertices]
        z0,z1=min(v.z for v in vs),max(v.z for v in vs)
        novos=[z0,z1]
        for apoio,baixo,novo,velho in planos:
            k=0 if baixo else 1
            if abs((z0,z1)[k]-velho)>.05:continue
            centro=sum(vs,Vector())/len(vs);centro.z=novo
            mundo=conj.matrix_world @ (centro/1000)
            im=apoio.matrix_world.inverted()
            hit,co,_n,_f=apoio.closest_point_on_mesh(im @ mundo)
            if hit and (apoio.matrix_world @ co-mundo).length<.0001:novos[k]=novo
        if max(abs(a-b) for a,b in zip((z0,z1),novos))<.01:continue
        prop='chapa_largura_mm' if eixo==0 else 'chapa_comprimento_mm'
        _chapas._ocupado[0]=True
        try:
            setattr(obj,prop,getattr(obj,prop)+(novos[1]-novos[0])-(z1-z0))
            m=obj.matrix_world.copy()
            m.translation+=conj.matrix_world.to_3x3() @ Vector((0,0,(sum(novos)-z0-z1)/2000))
            obj.matrix_world=m
        finally:_chapas._ocupado[0]=False
        _chapas.gerar_malha_chapa(obj);alteradas.append(obj.name)
    if alteradas:
        bpy.context.view_layer.update()
        _chapas.detectar_adjacencia(_modulos._chapas_do_conjunto(conj))
    return alteradas


def _local(conj, ponto_mm):
    return conj.matrix_world.inverted() @ (Vector(ponto_mm) / 1000.0) * 1000.0


def _mundo(conj, x, y, z):
    return Vector((x, y, z)) / 1000.0


def _porta(conj, porta, vao, plano, referencia=None, **opcoes):
    """Native door from four wizard points (door, opening, opening, door),
    in the body front plane, following `_portas.porta_no_modulo`."""
    x0, x1, z0, z1 = vao
    px0, px1, pz0, pz1 = porta
    pontos = [_mundo(conj, px0, plano, pz1), _mundo(conj, x0, plano, z1),
              _mundo(conj, x1, plano, z0), _mundo(conj, px1, plano, pz0)]
    ref = referencia if referencia is not None else Matrix.Identity(3)
    pontos = [ref @ p for p in pontos]
    referencia = tuple(v for linha in ref for v in linha)
    antes = set(_portas._portas_do_conjunto(conj))
    resultado = bpy.ops.object.cabinet_portas(
        'EXEC_DEFAULT', capturado=True, ponto_a=pontos[1], ponto_b=pontos[2],
        quatro_pontos=True, porta_a=pontos[0], porta_b=pontos[3],
        referencia=referencia, pai_nome=conj.name, modulo_nome=conj.name,
        objeto_a_nome='', frente='NEG_Y', folga_mm=0,
        **opcoes)
    if 'FINISHED' not in resultado:
        return None
    novas = [g for g in _portas._portas_do_conjunto(conj) if g not in antes]
    grupo = novas[-1] if novas else None
    if grupo is not None:
        _portas.gravar_vao_orientado(grupo, conj)
    return grupo


def _gavetas_do_plano(context, conj, g):
    ref = g.get('referencia', Matrix.Identity(3))
    local_ref = conj.matrix_world.to_3x3().inverted() @ ref
    lo, hi = _gavetas.limites_na_referencia(conj, local_ref)
    x0, x1, z0, z1 = g['vao']
    a = local_ref.transposed() @ _local(conj, ref @ Vector((x0, g['plano'], z0)))
    b = local_ref.transposed() @ _local(conj, ref @ Vector((x1, g['plano'], z1)))
    margens = (a.x - lo.x, hi.x - b.x, a.z - lo.z, hi.z - b.z, max(0.0, a.y - lo.y))
    fs = g['frentes']
    E = float(conj.conj_espessura_mm) or 18.0
    if not fs:
        # Basket without a front: a drawer with our front covering the opening.
        p = dict(quantidade=1, lateral_mm=E, espessura_frente_mm=E,
                 profundidade_mm=round(g['profundidade'], 1))
        try:
            return _gavetas.criar_gavetas(context, conj, margens, p, local_ref)
        except ValueError as erro:
            print("[Archy Builder] DXF basket in %s: %s" % (conj.name, erro))
            return None
    cobre = x0 - min(f['lo'][0] for f in fs)
    sobreposta = cobre > 1.0
    folga = (max(0.0, E - cobre) if sobreposta
             else max(0.0, min(f['lo'][0] for f in fs) - x0))
    vaos = [fs[i + 1]['lo'][2] - fs[i]['hi'][2] for i in range(len(fs) - 1)]
    curva = g['curva']
    espessura = max(1.0, min(f['espessura'] for f in fs))
    p = dict(quantidade=len(fs),
             coberturas_mm=[x0 - min(f['lo'][0] for f in fs),
                            max(f['hi'][0] for f in fs) - x1,
                            z0 - min(f['lo'][2] for f in fs),
                            max(f['hi'][2] for f in fs) - z1],
             proporcoes=[_tam(f, 2) for f in fs] if len(fs) > 1 else [],
             cobertura='SOBREPOSTA' if sobreposta else 'EMBUTIDA',
             folga_frontal_mm=round(folga, 1),
             entre_gavetas_mm=round(sum(vaos) / len(vaos), 1) if vaos else 3.0,
             espessura_frente_mm=round(espessura, 1), lateral_mm=E,
             profundidade_mm=round(g['profundidade'], 1),
             frente_curva_mm=(round(max(0.0, max(_tam(f, 1) for f in fs) - espessura), 1)
                              if curva else 0.0),
             puxador='NENHUM' if curva else 'PERFIL')
    try:
        return _gavetas.criar_gavetas(context, conj, margens, p, local_ref)
    except ValueError as erro:
        print("[Archy Builder] DXF drawers in %s: %s" % (conj.name, erro))
        return None


def _cobertura_nossa(borda, vao, E, lados):
    """Map the door edge on HINGE sides to add-on overlay: near full thickness
    = straight (covers E; our clearance is 2 mm), near half = curved. DXF
    leaves 5 mm (covers 10 of 15), which the 75% rule would call curved.
    Leave other sides unchanged, such as a base cabinet plinth."""
    borda = list(borda)
    sinais = (-1.0, 1.0, -1.0, 1.0)            # OUTWARD from the opening.
    for k in lados:
        cobre = sinais[k] * (borda[k] - vao[k])
        if cobre >= 0.6 * E:
            borda[k] = vao[k] + sinais[k] * E
        elif cobre >= 0.2 * E:
            borda[k] = vao[k] + sinais[k] * E / 2.0
    return borda


def _respiro_arremate(conj, p, borda):
    """A fixed coplanar panel must not be mistaken for or touch the leaf.

    Measure only during import using the actual front reference; do not
    move the trim or turn that wood into part of the door."""
    ref = p.get('referencia', Matrix.Identity(3))
    borda = list(borda)
    for obj in _modulos._chapas_do_conjunto(conj):
        pontos = [ref.transposed() @ (obj.matrix_world @ v.co * 1000)
                  for v in obj.data.vertices]
        lo = [min(v[k] for v in pontos) for k in range(3)]
        hi = [max(v[k] for v in pontos) for k in range(3)]
        if (hi[1]-lo[1] > 40 or hi[2] <= borda[2]+1 or lo[2] >= borda[3]-1
                or not lo[1]-.1 <= p['plano'] <= hi[1]+.1):
            continue
        if hi[0] <= borda[0]+TOL_FRENTE_MM and borda[0]-hi[0] < _portas.RESPIRO_PORTA_MM:
            borda[0] = hi[0] + _portas.RESPIRO_PORTA_MM
        if lo[0] >= borda[1]-TOL_FRENTE_MM and lo[0]-borda[1] < _portas.RESPIRO_PORTA_MM:
            borda[1] = lo[0] - _portas.RESPIRO_PORTA_MM
    return borda


def aplicar(context, conj, plano):
    """Create planned doors, drawers, and sliding doors in cabinet `conj`,
    which already contains only the body. Return {'portas', 'gavetas', 'correr'}."""
    feitos = {'portas': 0, 'gavetas': 0, 'correr': 0, 'prateleiras': 0}
    por_frente, vincular = {}, []
    for g in plano['gavetas']:
        if _gavetas_do_plano(context, conj, g) is not None:
            feitos['gavetas'] += 1
    for p in plano['portas']:
        uniao = _uniao(p['folhas'])
        original=[uniao['lo'][0],uniao['hi'][0],uniao['lo'][2],uniao['hi'][2]]
        if not p.get('curva_modelada'):
            original = _respiro_arremate(conj, p, original)
        opcoes = {'folhas': len(p['folhas'])}
        if p['lado'] == 'CIMA':
            opcoes.update(abertura='BASCULANTE', dobradica_lado='CIMA', folhas=1)
        else:
            opcoes.update(abertura='GIRO', dobradica_lado=p['lado'])
        borda = _cobertura_nossa(
            original,
            p['vao'], float(conj.conj_espessura_mm) or 18.0,
            {'CIMA': (3,), 'ESQUERDA': (0,), 'DIREITA': (1,)}[p['lado']]
            if len(p['folhas']) == 1 else (0, 1))
        if p.get('contorno_exato') and len(p['folhas'])>1:
            opcoes['entre_folhas_mm']=sum(b['lo'][0]-a['hi'][0] for a,b in zip(p['folhas'],p['folhas'][1:]))/(len(p['folhas'])-1)
        grupo = _porta(conj, borda, p['vao'], p['plano'],
                       referencia=p.get('referencia'), **opcoes)
        if grupo is not None:
            parametros = dict(grupo['porta_parametros'])
            parametros['espessura_mm'] = round(p['folhas'][0]['espessura'], 3)
            if not p.get('curva_modelada') and not p.get('articulada'):
                parametros['afastamento_mm'] = max(_portas.RESPIRO_PORTA_MM,
                                                   parametros['afastamento_mm'])
            if p.get('contorno_exato'):
                E=parametros['lateral_mm']
                parametros['respiro_original']=True
                parametros['folga_mm']=0
                for chave,b,v,sinal in zip(_portas.COBERTURAS_LADOS,original,p['vao'],(-1,1,-1,1)):
                    parametros[chave]=sinal*(b-v)/E
            if p.get('curva_modelada'):parametros['dobradica']='CURVA'
            if p.get('articulada'):
                parametros['dobradica'] = 'CURVA'
                parametros['dobradica_articulada'] = True
                parametros['dobradica_apoio_plano_mm'] = p['apoio_plano_mm']
            # One list per leaf: measured cup positions as fractions of the
            # edge. Survives resizing without imposing symmetric margins.
            medidas = _portas._calcular_folhas_portas(
                grupo['porta_vao_largura_mm'], grupo['porta_vao_altura_mm'], parametros)
            inverse = grupo.matrix_world.inverted()
            refs = {}
            for i, centros in enumerate(p.get('centros', [])):
                l, a, e, c = medidas[i]
                topo = p['lado'] == 'CIMA'
                inicio, tamanho = (c[0] - l / 2, l) if topo else (c[1] - a / 2, a)
                coords = [inverse @ (p['referencia'] @ centro / 1000) * 1000
                          for centro in centros]
                refs[str(i)] = sorted((v.x if topo else v.y) - inicio for v in coords)
                refs[str(i)] = [max(0, min(1, d / tamanho)) for d in refs[str(i)]]
            if refs:
                parametros['dobradicas_referencia'] = refs
                parametros['dobradicas_qtd'] = len(refs['0'])
            # Straight hinges must not force their 90-degree rig onto a diagonal support.
            prova=dict(parametros,dobradica='CURVA')
            calc=_portas._calcular_folhas_portas(grupo['porta_vao_largura_mm'],grupo['porta_vao_altura_mm'],prova)
            if _portas._ferragens._apoios_obliquos(conj,grupo.matrix_world,prova,
                    grupo['porta_vao_largura_mm'],grupo['porta_vao_altura_mm'],calc):
                parametros['dobradica']='CURVA'
            elif not p.get('articulada') and not p.get('curva_modelada'):
                # Use actual hardware for partial overlay too, without changing
                # the door edge to the standard straight overlay.
                parametros['dobradica_modelo_reta'] = True
            _portas._reaplicar_portas(context, grupo, parametros)
            if p.get('curva_modelada'):
                folha=_portas._folhas_portas(grupo)[0]
                inversa=folha.matrix_world.inverted()
                malha=folha.data
                malha.clear_geometry()
                malha.from_pydata([inversa @ (Vector(v)/1000) for v in p['malha_original']['vertices']],[],p['malha_original']['faces'])
                malha.update()
                folha['porta_curva_modelada']=1
                # Tangential pull handle: a straight horizontal profile does not follow an arc.
                pux=_puxadores.criar_puxador(context,folha,'ALCA',
                    'X+' if parametros['dobradica_lado']=='ESQUERDA' else 'X-',1)
                pux['puxador_curvo']=True
                pux['promob_puxador_automatico']=True
                _puxadores.posicionar_puxador(pux)
                _portas._ferragens._refazer_ferragens(grupo)
            else:
                _puxadores.perfis_na_porta(context,grupo,plano.get('puxador_posicao','BAIXO'))
            for fonte, folha in zip(p['folhas'], _portas._folhas_portas(grupo)):
                folha['porta_origem_promob']=fonte.get('origem','')
                por_frente[fonte.get('origem', '')] = folha
            if p.get('apoio'):
                vincular.append((grupo, p['apoio']))
            feitos['portas'] += 1
    for grupo, origem in vincular:
        apoio = por_frente.get(origem)
        if apoio is not None:
            parametros = _portas._copiar_parametros(grupo['porta_parametros'])
            if parametros.get('dobradica_articulada'):
                p_apoio = apoio.parent['porta_parametros']
                parametros['dobradica_apoio_plano_mm'] += _portas._ferragens._afastamento_porta(p_apoio)
                parametros['dobradica_articulada_sinal'] = (1 if _portas._ferragens._lado_da_folha(
                    p_apoio, int(apoio.get('porta_indice', 0)), len(_portas._folhas_portas(apoio.parent))) == 'ESQUERDA' else -1)
                folha = _portas._folhas_portas(grupo)[0]
                l, a, e, c = _portas._ferragens._dados_da_folha(folha)
                pts = [grupo.matrix_world.inverted() @ (_portas._ferragens._matriz_fechada(apoio) @ Vector(v)) * 1000 for v in apoio.bound_box]
                esquerda = parametros.get('dobradica_lado') == 'ESQUERDA'
                borda = c[0] + (-l / 2 if esquerda else l / 2)
                vizinha = max(v.x for v in pts) if esquerda else min(v.x for v in pts)
                parametros['dobradica_junta_mm'] = min(30, abs(borda - vizinha))
                _portas._reaplicar_portas(context, grupo, parametros)
            _portas.vincular_folha_de_apoio(grupo, apoio, conj)
    for c in plano['correr']:
        n = min(len(c['quadros']), _portas.LIMITES_FOLHAS['CORRER'])
        grupo = _porta(conj, c['vao'], c['vao'], c['plano'], abertura='CORRER',
                       folhas=n, tipo_correr='EMBUTIDA')
        if grupo is not None:
            _portas._editar_parametro_porta(context, grupo, 'folha', 'QUADRO')
            feitos['correr'] += 1
    for ps in plano.get('prateleiras', []):
        for p in ps:
            if p.get('obj') is not None:
                p['obj'][_prateleiras.MARCA_PRATELEIRA] = 1
    for ps in plano.get('prateleiras', []):
        if _prateleiras_do_plano(context, conj, ps) is not None:
            feitos['prateleiras'] += 1
    if plano.get('fechar_traseira'):
        _modulos.adicionar_fundo(conj,context)
    _portas.preferir_esquerda_no_modulo(context,conj)
    return feitos


def _prateleiras_do_plano(context, conj, ps):
    """Adopt original panels and clear heights with UID/material/shape intact."""
    for p in ps:
        if p.get('obj') is not None:
            p['obj'][_prateleiras.MARCA_PRATELEIRA] = 1
    lo, hi = _portas._limites_locais_modulo(conj)
    inv = conj.matrix_world.inverted()
    dados = []
    for p in ps:
        obj = p.get('obj')
        if obj is None:
            continue
        vs = [inv @ (obj.matrix_world @ v.co) * 1000 for v in obj.data.vertices]
        dados.append((obj, Vector(tuple(min(v[k] for v in vs) for k in range(3))),
                      Vector(tuple(max(v[k] for v in vs) for k in range(3)))))
    if not dados:
        return None
    dados.sort(key=lambda d: d[1].z)
    x0, x1 = dados[0][1].x, dados[0][2].x
    y0, y1 = dados[0][1].y, dados[0][2].y
    e = dados[0][2].z - dados[0][1].z
    centro = Vector(((x0 + x1) / 2, (y0 + y1) / 2, 0))
    horizontais = []
    for obj in _modulos._chapas_do_conjunto(conj):
        if obj in [d[0] for d in dados] or abs((inv @ obj.matrix_world).to_3x3().col[2].normalized().z) < .999:
            continue
        vs = [inv @ (obj.matrix_world @ v.co) * 1000 for v in obj.data.vertices]
        a = Vector(tuple(min(v[k] for v in vs) for k in range(3)))
        b = Vector(tuple(max(v[k] for v in vs) for k in range(3)))
        if a.x <= centro.x <= b.x and a.y <= centro.y <= b.y:
            horizontais.append((a.z, b.z))
    baixo = max((b for a, b in horizontais if b <= dados[0][1].z + .1), default=lo.z)
    cima = min((a for a, b in horizontais if a >= dados[-1][2].z - .1), default=hi.z)
    origem_z = baixo
    vaos = []
    for obj, a, b in dados:
        vaos.append(a.z - baixo)
        baixo = b.z
    margens = (x0 - lo.x, hi.x - x1, origem_z - lo.z, hi.z - cima, y0 - lo.y)
    p = dict(quantidade=len(dados), espessura_mm=e, profundidade_mm=y1 - y0,
             espacamento='LIVRE', vaos_mm=vaos, recuo_mm=0, folga_lateral_mm=0)
    return _prateleiras.criar_prateleiras(context, conj, margens, p, [d[0] for d in dados])


def fundos_a_recuar(conj):
    """Actual rear back panel, not an internal partition/lining. Measure from
    the thick box; including the back itself used to make the recess zero."""
    pecas=_modulos._chapas_do_conjunto(conj)
    corpo=[o for o in pecas if o.chapa_espessura_mm>FUNDO_MAXIMO_MM
           and _chapas.MARCA_FUNDO not in o]
    inv=conj.matrix_world.inverted()
    pts=[inv @ (o.matrix_world @ v.co)*1000 for o in corpo for v in o.data.vertices]
    if not pts:return []
    lo=Vector(tuple(min(p[k] for p in pts) for k in range(3)))
    hi=Vector(tuple(max(p[k] for p in pts) for k in range(3)))
    ajustes=[]
    for o in pecas:
        marcado=_chapas.MARCA_FUNDO in o
        if not marcado and o.chapa_espessura_mm>FUNDO_MAXIMO_MM:continue
        n=(inv @ o.matrix_world).to_3x3().col[2].normalized()
        if abs(n.y)<.995:continue
        vs=[inv @ (o.matrix_world @ v.co)*1000 for v in o.data.vertices]
        a=Vector(tuple(min(v[k] for v in vs) for k in range(3)))
        b=Vector(tuple(max(v[k] for v in vs) for k in range(3)))
        if not marcado and ((b.x-a.x)<.5*(hi.x-lo.x) or (b.z-a.z)<100):continue
        recuo=hi.y-b.y
        if -.1 <= recuo < _modulos.RECUO_FUNDO_MM-.05:
            ajustes.append((o,_modulos.RECUO_FUNDO_MM-recuo))
    return ajustes


def ajustar_recuo_fundos(conj):
    """Move only the back, preserving thickness, cutouts, UID, and materials."""
    ajustes=fundos_a_recuar(conj)
    for obj,delta in ajustes:
        m=obj.matrix_world.copy()
        m.translation-=conj.matrix_world.to_3x3() @ Vector((0,delta/1000,0))
        obj.matrix_world=m
        # A back for ONE compartment remains a panel: marking it as the
        # entire back would make ajustar_fundo stretch it across the whole tall cabinet.
    if ajustes:
        conj[_modulos.CHAVE_RECUO_FUNDO]=_modulos.RECUO_FUNDO_MM
        bpy.context.view_layer.update()
        _chapas.detectar_adjacencia(_modulos._chapas_do_conjunto(conj))
    return [(o.name,delta) for o,delta in ajustes]


def ajustar_internos_ao_fundo(conj):
    """Shelves/boxes must not cross the recessed back. Recalculate native
    systems; choose a commercial rail length that fits.
    Return changed group names for the library audit."""
    fundo=_modulos.fundo_do_modulo(conj)
    if fundo is None:return []
    alterados=[]
    for grupo in _prateleiras.grupos_do_modulo(conj):
        ponto=grupo.matrix_world.translation
        disponivel=_prateleiras.profundidade_ate_o_fundo(conj,ponto)
        p=_prateleiras.parametros(grupo)
        if float(p['profundidade_mm'])>disponivel+.05:
            p['profundidade_mm']=disponivel
            grupo[_prateleiras.CHAVE_PARAMETROS]=p
            _prateleiras.montar(grupo)
            alterados.append(grupo.name)
    for grupo in _gavetas.grupos_do_modulo(conj):
        inv=grupo.matrix_world.inverted()
        n=(inv @ fundo.matrix_world).to_3x3().col[2].normalized()
        if abs(n.y)<.995:continue
        limite=min((inv @ (fundo.matrix_world @ v.co)).y*1000 for v in fundo.data.vertices)
        p=_gavetas.parametros(grupo)
        largura,altura,_m=_gavetas.vao(grupo)
        dados=_gavetas.calcular(largura,altura,p)
        novo=grupo[_gavetas.CHAVE_PARAMETROS].to_dict()
        mudou=False
        for i,d in enumerate(dados['gavetas']):
            if max(c[2][3] for c in d['caixa'])<=limite+.05:continue
            q=novo.setdefault('individuais',{}).setdefault(str(i),{})
            q['profundidade_mm']=min(float(_gavetas.parametros_da_unidade(p,i)['profundidade_mm']),limite)
            mudou=True
        if mudou:
            _gavetas.calcular(largura,altura,dict(_gavetas.PARAMETROS_PADRAO,**novo))
            grupo[_gavetas.CHAVE_PARAMETROS]=novo
            _gavetas.montar(grupo)
            alterados.append(grupo.name)
    return alterados


def marcar_dependentes(conj, plano):
    """Thin DXF backs and rails become cabinet dependents, rebuilt from
    the box by `_modulos.ajustar_dependentes`."""
    lo, hi = _modulos._caixa_local_estrutural(conj) or (None, None)
    for p, lado in plano['travessas']:
        tr = p['obj']
        tr[_chapas.MARCA_TRAVESSA] = 1
        tr[_modulos.CHAVE_LADO_TRAVESSA] = lado
        _chapas._ocupado[0] = True
        try:
            # Adjustment changes position only: use the component's own axes.
            tr.chapa_comprimento_mm = _tam(p, 1)
            tr.matrix_world = conj.matrix_world.to_quaternion().to_matrix().to_4x4()
        finally:
            _chapas._ocupado[0] = False
    fundos=plano.get('fundos',[])
    # A single rectangular-box back still uses the standard groove.
    # Two corner planes must never become one rectangle.
    fundos=[p for p in fundos if len(plano.get('fundos',[]))>1
            or _tam(p,2)<.9*(hi.z-lo.z)
            or _tam(p,1 if p['eixo']==0 else 0)<.9*((hi.y-lo.y) if p['eixo']==0 else (hi.x-lo.x))]
    for p in fundos:
        p['obj'][_chapas.MARCA_FUNDO]=1
    for p in fundos:
        _modulos.guardar_formato_fundo(conj,p['obj'])
    fundo = plano['fundo']
    if fundo is not None and hi is not None:
        fundo['obj'][_chapas.MARCA_FUNDO] = 1
        recuo = hi.y - _local(conj, fundo['hi'])[1]
        conj[_modulos.CHAVE_RECUO_FUNDO] = max(_modulos.RECUO_FUNDO_MM, round(recuo, 1))
    if plano['travessas'] or fundo is not None:
        bpy.context.view_layer.update()
        # Cabinet thickness comes from the box, now excluding the back.
        _modulos.sincronizar_medidas_conjunto(conj)
        _modulos.ajustar_dependentes(conj)
