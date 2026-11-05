"""Repair cabinet internals in external copies and publish only verified files.

Supply --fontes DIRECTORY explicitly for preparation.
--aplicar uses the source paths recorded in the existing manifest.
"""
import argparse
import itertools
import json
from pathlib import Path
import shutil
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector
from mathutils.geometry import intersect_point_line

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
import tools.migrations.adjust_fits as _base
import tools.audit.audit_library_internals as _auditoria
import tools.migrations.audit_and_repair_integration as _integracao
import tools.library.integrate_dxf_library as _publicacao


def limites(obj, inversa=None):
    inversa = inversa if inversa is not None else Matrix.Identity(4)
    pontos = [inversa @ (obj.matrix_world @ v.co) * 1000 for v in obj.data.vertices]
    return (Vector(tuple(min(v[k] for v in pontos) for k in range(3))),
            Vector(tuple(max(v[k] for v in pontos) for k in range(3))))


def reparentear(obj, pai):
    mundo = obj.matrix_world.copy()
    obj.parent = pai
    obj.matrix_parent_inverse = Matrix.Identity(4)
    obj.matrix_world = mundo


def tornar_estrutural(obj, conj):
    reparentear(obj, conj)
    for chave in ('eh_prateleira', 'prateleira_indice', 'prateleira_detalhamento_uid'):
        obj.pop(chave, None)


def _reparar_topologia_uma_vez(obj):
    """Solda costuras coincidentes e elimina faces duplicadas, sem preencher recortes."""
    bm = bmesh.new()
    try:
        bm.from_mesh(obj.data)
        contagem = (len(bm.verts), len(bm.edges), len(bm.faces),sum(len(f.verts) for f in bm.faces))
        bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=.000001)
        # DXF triangulado pode apoiar dois segmentos num lado unico da
        # face vizinha. Dividir o lado solda a costura sem tapar o recorte.
        bordas=[v for v in bm.verts if any(e.is_boundary for e in v.link_edges)]
        for vertice in bordas:
            for aresta in list(bm.edges):
                if not aresta.is_boundary or vertice in aresta.verts:
                    continue
                a,b=aresta.verts
                if (b.co-a.co).length<.000002:
                    continue
                ponto,fator=intersect_point_line(vertice.co,a.co,b.co)
                if .000001<fator<.999999 and (ponto-vertice.co).length<.000001:
                    _e,novo=bmesh.utils.edge_split(aresta,a,fator)
                    novo.co=vertice.co
        bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=.000001)
        bm.verts.index_update()
        vistas, repetidas = set(), []
        for face in bm.faces:
            chave = tuple(sorted(v.index for v in face.verts))
            if chave in vistas:
                repetidas.append(face)
            vistas.add(chave)
        if repetidas:
            bmesh.ops.delete(bm, geom=repetidas, context='FACES_ONLY')
        internas=[f for f in bm.faces if all(len(e.link_faces)>2 for e in f.edges)]
        if internas:
            bmesh.ops.delete(bm,geom=internas,context='FACES_ONLY')
        # Duas falhas triangulares podem compartilhar apenas uma quina;
        # o preenchedor nativo nao encontra um loop unico nessa bifurcacao.
        z0,z1=min(v.co.z for v in bm.verts),max(v.co.z for v in bm.verts)
        for v in list(bm.verts):
            vizinhos=[e.other_vert(v) for e in v.link_edges if e.is_boundary]
            for a,b in itertools.combinations(vizinhos,2):
                arestas=[bm.edges.get((v,a)),bm.edges.get((a,b)),bm.edges.get((b,v))]
                if any(e is None or not e.is_boundary for e in arestas):continue
                vs=(v,a,b)
                if max(w.co.z for w in vs)-min(w.co.z for w in vs)>.000001:continue
                if min(abs(v.co.z-z0),abs(v.co.z-z1))>.000001:continue
                if (a.co-v.co).cross(b.co-v.co).length<1e-12:continue
                if not any(abs(e.other_vert(w).co.z-w.co.z)>.0001 for w in vs for e in w.link_edges):continue
                bm.faces.new(vs)
        bordas=[e for e in bm.edges if e.is_boundary]
        if bordas:
            novas=bmesh.ops.holes_fill(bm,edges=bordas,sides=0)['faces']
            grandes=[f for f in novas if f.calc_area()>.000002]
            usadas=set()
            def centro_limites(f):
                return Vector(tuple((min(v.co[k] for v in f.verts)+max(v.co[k] for v in f.verts))/2 for k in range(3)))
            def mesma_borda(f,g):
                a,b=centro_limites(f),centro_limites(g)
                if max(abs(a.x-b.x),abs(a.y-b.y))>.000001 or abs(a.z-b.z)<.000001:return False
                for v in f.verts:
                    p=v.co-a
                    distancias=[]
                    for e in g.edges:
                        c,d=[w.co-b for w in e.verts]
                        _q,t=intersect_point_line(p,c,d)
                        distancias.append((p-c.lerp(d,max(0.,min(1.,t)))).length)
                    if min(distancias)>.000001:return False
                return True
            for face in grandes:
                if id(face) in usadas:continue
                normal=face.normal.normalized()
                borda_externa=any(abs((e.other_vert(v).co-v.co).dot(normal))>.0001
                    for v in face.verts for e in v.link_edges if e not in face.edges)
                z=face.verts[0].co.z
                extremo=min(abs(z-min(v.co.z for v in bm.verts)),abs(z-max(v.co.z for v in bm.verts)))<.000001
                if abs(normal.z)>.999 and extremo and borda_externa:
                    usadas.add(id(face))
                    continue
                outra=next((f for f in grandes if f!=face and id(f) not in usadas
                    and abs(f.calc_area()-face.calc_area())<max(.0000001,face.calc_area()*.00001)
                    and mesma_borda(face,f) and mesma_borda(f,face)),None)
                if outra is None:continue
                arestas=list(face.edges)+list(outra.edges)
                usadas.update((id(face),id(outra)))
                # Um recorte atraves da chapa continua VAZIO: unir as
                # bordas das duas peles repoe so' suas paredes ausentes.
                bmesh.ops.delete(bm,geom=[face,outra],context='FACES_ONLY')
                bmesh.ops.bridge_loops(bm,edges=arestas)
            restantes=[f for f in grandes if id(f) not in usadas]
            if restantes:bmesh.ops.delete(bm,geom=restantes,context='FACES_ONLY')
        mudou = contagem != (len(bm.verts),len(bm.edges),len(bm.faces),sum(len(f.verts) for f in bm.faces))
        if mudou:
            bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
            bm.to_mesh(obj.data)
            obj.data.update()
        return mudou
    finally:
        bm.free()


def reparar_topologia(obj):
    mudou=False
    for _ in range(3):
        if not _reparar_topologia_uma_vez(obj):break
        mudou=True
    return mudou


def recortar(obj, obstaculo):
    """Diferenca nativa apenas no trecho invadido, mantendo o ID da Mesh original."""
    copia = obj.copy()
    copia.data = obj.data.copy()
    copia.modifiers.clear()
    bpy.context.scene.collection.objects.link(copia)
    ferramenta=obstaculo.copy()
    ferramenta.data=obstaculo.data.copy()
    ferramenta.modifiers.clear()
    bpy.context.scene.collection.objects.link(ferramenta)
    bm_ferramenta=bmesh.new()
    try:
        bm_ferramenta.from_mesh(ferramenta.data)
        bmesh.ops.recalc_face_normals(bm_ferramenta,faces=list(bm_ferramenta.faces))
        bm_ferramenta.to_mesh(ferramenta.data)
    finally:bm_ferramenta.free()
    folga=ferramenta.modifiers.new('Folga do recorte','DISPLACE')
    folga.direction='NORMAL';folga.strength=.0002;folga.mid_level=0.
    modificador = copia.modifiers.new('Recorte da interferencia', 'BOOLEAN')
    modificador.operation = 'DIFFERENCE'
    modificador.solver = 'EXACT'
    modificador.object = ferramenta
    try:
        bpy.context.view_layer.update()
        avaliado = copia.evaluated_get(bpy.context.evaluated_depsgraph_get())
        mesh = avaliado.to_mesh()
        bm = bmesh.new()
        try:
            bm.from_mesh(mesh)
            if not bm.faces:
                raise RuntimeError('O recorte removeria a peca inteira: '+obj.name)
            bm.to_mesh(obj.data)
            obj.data.update()
        finally:
            bm.free()
            avaliado.to_mesh_clear()
        reparar_topologia(obj)
    finally:
        mesh_copia = copia.data
        bpy.data.objects.remove(copia, do_unlink=True)
        bpy.data.meshes.remove(mesh_copia)
        mesh_ferramenta=ferramenta.data
        bpy.data.objects.remove(ferramenta,do_unlink=True)
        bpy.data.meshes.remove(mesh_ferramenta)


def restaurar_laterais(conj, dados_fonte):
    """Os dois presets sem laterais foram reconhecidos como tres gaveteiros."""
    addon = _base.addon
    if dados_fonte is None:
        return []
    planos, geometria = dados_fonte
    nomes = {o.name for o in addon.modulos._chapas_do_conjunto(conj)}
    dados = max(planos, key=lambda d:len(nomes & d['pecas'].keys()))
    offset = _integracao.deslocamento_do_preset(conj,dados)
    inv=conj.matrix_world.inverted()
    altura_corpo=max(limites(o,inv)[1].z for o in addon.modulos._chapas_do_conjunto(conj))
    restauradas = []
    for grupo in list(addon.gavetas.grupos_do_modulo(conj)):
        if abs(addon.gavetas.referencia(grupo).col[1].x) < .99:
            continue
        frente = addon.gavetas.frente_da_gaveta(addon.gavetas.gavetas_do_grupo(grupo)[0])
        centro = frente.matrix_world.translation*1000+offset
        normal = frente.matrix_world.to_3x3().col[2].normalized()
        candidatos = [((Vector(tuple((p['lo'][k]+p['hi'][k])/2 for k in range(3)))-centro).length,nome)
                      for nome,p in dados['pecas'].items() if p.get('normal') is not None
                      and abs(normal.dot(Vector(p['normal'])))>.995]
        distancia,nome = min(candidatos)
        if distancia > 35:
            raise RuntimeError('Lateral nao identificada no DXF: '+grupo.name)
        slots=[(s.link,s.material) for s in frente.material_slots]
        uid=frente.get('chapa_uid')
        for obj in list(reversed(grupo.children_recursive)):
            addon.gavetas._remover(obj)
        addon.gavetas._remover(grupo)
        vs,fs = geometria[nome.removeprefix('Peca ')]
        obj=addon.importacao._objeto_da_peca(bpy.context,nome,
            [tuple(Vector(v)-offset) for v in vs],fs,conj.users_collection[0])
        addon.importacao.converter_em_chapa(obj)
        reparentear(obj,conj)
        bpy.context.view_layer.update()
        a,b=limites(obj,inv)
        if b.z>altura_corpo+.25:
            eixo=max((0,1),key=lambda i:abs((inv@obj.matrix_world).to_3x3().col[i].z))
            prop='chapa_largura_mm' if eixo==0 else 'chapa_comprimento_mm'
            addon.chapas._ocupado[0]=True
            try:
                setattr(obj,prop,getattr(obj,prop)-(b.z-altura_corpo))
                obj.matrix_world.translation-=conj.matrix_world.to_3x3()@Vector((0,0,(b.z-altura_corpo)/2000))
            finally:addon.chapas._ocupado[0]=False
            addon.chapas.gerar_malha_chapa(obj)
        if uid:obj['chapa_uid']=uid
        for link,material in slots:
            obj.data.materials.append(material)
            obj.material_slots[-1].link=link
            obj.material_slots[-1].material=material
        restauradas.append(nome)
    bpy.context.view_layer.update()
    return restauradas


def acertar_gaveta_cabeceira(conj,nome):
    if not nome.startswith('Mesas_de_Cabeceira_Quarto_04_'):
        return
    addon=_base.addon
    grupo,=addon.gavetas.grupos_do_modulo(conj)
    margens=list(grupo[addon.gavetas.CHAVE_MARGENS]);margens[:2]=[15.,15.]
    grupo[addon.gavetas.CHAVE_MARGENS]=margens
    p=addon.gavetas.parametros(grupo)
    p['cobertura']='SOBREPOSTA'
    p['coberturas_mm']=[15.,15.,*p['coberturas_mm'][2:]]
    grupo[addon.gavetas.CHAVE_PARAMETROS]=p
    uid=addon.gavetas.frente_da_gaveta(addon.gavetas.gavetas_do_grupo(grupo)[0]).get('chapa_uid')
    addon.gavetas.montar(grupo)
    if uid:addon.gavetas.frente_da_gaveta(addon.gavetas.gavetas_do_grupo(grupo)[0])['chapa_uid']=uid


def adotar_gavetas_internas(conj, nome):
    addon = _base.addon
    if nome != 'Armario_Quarto_08_600x2503x550.blend':
        return []
    inv=conj.matrix_world.inverted()
    grupo=next(g for g in addon.prateleiras.grupos_do_modulo(conj)
               if addon.prateleiras.parametros(g)['espessura_mm']<8)
    fundos=addon.prateleiras.prateleiras_do_grupo(grupo)
    corpo=addon.modulos._chapas_do_conjunto(conj)
    conjuntos=[]
    for fundo in fundos:
        a,b=limites(fundo,inv)
        laterais=[]
        for obj in corpo:
            c,d=limites(obj,inv)
            if (abs(c.z-(a.z-10))<.25 and c.x>=a.x-11 and d.x<=b.x+11
                    and c.y>=a.y-11 and d.y<=b.y+14 and d.z-c.z>60):
                laterais.append((obj,c,d))
        if len(laterais)!=4:
            raise RuntimeError('Caixa interna incompleta: '+fundo.name)
        frente=min(laterais,key=lambda q:q[1].y)
        conjuntos.append(dict(fundo=fundo,pecas=laterais,frente=frente))
    conjuntos.sort(key=lambda q:q['frente'][1].z)
    f0,a0,b0=conjuntos[0]['frente']
    z0=a0.z;z1=max(limites(o,inv)[0].z for o in corpo
                   if abs(limites(o,inv)[0].z-757.94098)<.1)
    # A moldura original tem faces internas a 13 mm da frente de cada lado.
    x0,x1=a0.x-13,b0.x+13
    lo,hi=addon.gavetas._limites(conj)
    p=dict(quantidade=len(conjuntos),cobertura='EMBUTIDA',puxador='NENHUM',
           profundidade_mm=457.,espessura_frente_mm=15.,lateral_mm=15.,
           entre_gavetas_mm=conjuntos[1]['frente'][1].z-b0.z,
           proporcoes=[q['frente'][2].z-q['frente'][1].z for q in conjuntos],
           coberturas_mm=[x0-a0.x,b0.x-x1,0.,conjuntos[-1]['frente'][2].z-z1])
    fontes=[]
    for q in conjuntos:
        f=q['frente'][0]
        fontes.append(dict(nome=f.name,uid=f.get('chapa_uid'),slots=[(s.link,s.material) for s in f.material_slots]))
    for q in conjuntos:
        for obj,*_ in q['pecas']:addon.gavetas._remover(obj)
        addon.gavetas._remover(q['fundo'])
    addon.gavetas._remover(grupo)
    margens=[x0-lo.x,hi.x-x1,z0-lo.z,hi.z-z1,a0.y-lo.y]
    novo=addon.gavetas.criar_gavetas(bpy.context,conj,margens,p)
    for gaveta,fonte in zip(addon.gavetas.gavetas_do_grupo(novo),fontes):
        f=addon.gavetas.frente_da_gaveta(gaveta)
        f.name=fonte['nome']
        if fonte['uid']:f['chapa_uid']=fonte['uid']
        f.data.materials.clear()
        for link,mat in fonte['slots']:
            f.data.materials.append(mat)
            f.material_slots[-1].link=link;f.material_slots[-1].material=mat
    return [novo.name]


def fixar_separadores(conj):
    addon = _base.addon
    grupos = addon.prateleiras.grupos_do_modulo(conj)
    inv = conj.matrix_world.inverted()
    corpo = addon.modulos._chapas_do_conjunto(conj)
    gavetas = []
    for g in addon.gavetas.grupos_do_modulo(conj):
        l, a, m = addon.gavetas.vao(g)
        pontos = [inv @ (conj.matrix_world @ m @ (Vector(v)/1000))*1000
                  for v in itertools.product((0, l), (0, addon.gavetas.parametros(g)['profundidade_mm']), (0, a))]
        gavetas.append((Vector(tuple(min(v[k] for v in pontos) for k in range(3))),
                        Vector(tuple(max(v[k] for v in pontos) for k in range(3)))))
    alteradas = []
    for grupo in grupos:
        ps = addon.prateleiras.prateleiras_do_grupo(grupo)
        caixas = [(p, *limites(p, inv)) for p in ps]
        for obj, lo, hi in caixas:
            toca_outra = any(p != obj and min(abs(a.z-hi.z), abs(b.z-lo.z)) < .25
                             for p, a, b in caixas)
            separa_gaveta = any(min(hi.x, b.x)-max(lo.x, a.x) > .8*(hi.x-lo.x)
                and min(hi.y, b.y)-max(lo.y, a.y) > .5*(hi.y-lo.y)
                and (-.25 <= lo.z-b.z <= 20 or -.25 <= a.z-hi.z <= 20) for a, b in gavetas)
            apoia = False
            for chapa in corpo:
                normal = (inv @ chapa.matrix_world).to_3x3().col[2].normalized()
                if abs(normal.z) > .1:
                    continue
                a, b = limites(chapa, inv)
                if b.z-a.z < 100 or min(hi.x,b.x)-max(lo.x,a.x) <= .25 or min(hi.y,b.y)-max(lo.y,a.y) <= .25:
                    continue
                if min(abs(a.z-hi.z), abs(b.z-lo.z)) <= 6:
                    apoia = True
                    break
            if toca_outra or separa_gaveta or apoia:
                tornar_estrutural(obj, conj)
                alteradas.append(obj.name)
        if not addon.prateleiras.prateleiras_do_grupo(grupo):
            bpy.data.objects.remove(grupo, do_unlink=True)
    bpy.context.view_layer.update()
    return alteradas


def ajustar_frentes(conj):
    addon = _base.addon
    alteradas = []
    for g in addon.gavetas.grupos_do_modulo(conj):
        inv = g.matrix_world.inverted()
        frente = [addon.gavetas.frente_da_gaveta(d) for d in addon.gavetas.gavetas_do_grupo(g)]
        mover = 0.
        for f in frente:
            lo, hi = limites(f, inv)
            for chapa in addon.modulos._chapas_do_conjunto(conj):
                a, b = limites(chapa, inv)
                if (min(hi.x,b.x)-max(lo.x,a.x) > .25 and min(hi.z,b.z)-max(lo.z,a.z) > .25
                        and min(hi.y,b.y)-max(lo.y,a.y) > .25):
                    mover = max(mover, hi.y-a.y)
        if mover > .25:
            margens = list(g[addon.gavetas.CHAVE_MARGENS])
            margens[4] -= mover
            g[addon.gavetas.CHAVE_MARGENS] = margens
            _l, _a, matriz = addon.gavetas.vao(g)
            g.matrix_basis = matriz
            alteradas.append(dict(grupo=g.name, deslocamento_frente_mm=mover))
            bpy.context.view_layer.update()
    return alteradas


def reunir_prateleiras(conj):
    addon = _base.addon
    grupos = addon.prateleiras.grupos_do_modulo(conj)
    inv = conj.matrix_world.inverted()
    alteradas = []
    for ng, nh in itertools.combinations([g.name for g in grupos], 2):
        g,h = bpy.data.objects.get(ng),bpy.data.objects.get(nh)
        if g is None or h is None:
            continue
        a, b = [addon.prateleiras.prateleiras_do_grupo(x) for x in (g, h)]
        if not a or not b:
            continue
        ca, cb = [limites(x, inv) for x in a], [limites(x, inv) for x in b]
        if any(min(y.z, w.z)-max(x.z, z.z) > .25 for x,y in ca for z,w in cb):
            continue
        ax0, ax1 = min(x.x for x,y in ca), max(y.x for x,y in ca)
        bx0, bx1 = min(x.x for x,y in cb), max(y.x for x,y in cb)
        ay0, ay1 = min(x.y for x,y in ca), max(y.y for x,y in ca)
        by0, by1 = min(x.y for x,y in cb), max(y.y for x,y in cb)
        if (min(ax1,bx1)-max(ax0,bx0) < .8*min(ax1-ax0,bx1-bx0)
                or min(ay1,by1)-max(ay0,by0) < .5*min(ay1-ay0,by1-by0)):
            continue
        for p in b:
            reparentear(p, g)
        alteradas.append([g.name,h.name])
        bpy.data.objects.remove(h, do_unlink=True)
        bpy.context.view_layer.update()
    return alteradas


def acertar_vao_prateleiras(grupo):
    addon = _base.addon
    conj = addon.prateleiras.modulo_do_grupo(grupo)
    ref = addon.gavetas.referencia(grupo) if grupo.get('gavetas_referencia') else Matrix.Identity(3)
    valores = grupo.get(addon.prateleiras.CHAVE_REFERENCIA)
    if valores:
        ref = Matrix([valores[i:i+3] for i in (0,3,6)])
    mundo = conj.matrix_world @ ref.to_4x4()
    inv = mundo.inverted()
    ps = sorted(addon.prateleiras.prateleiras_do_grupo(grupo), key=lambda p:limites(p,inv)[0].z)
    caixas = [(p,*limites(p,inv)) for p in ps]
    x0,x1 = min(a.x for p,a,b in caixas),max(b.x for p,a,b in caixas)
    y0,y1 = min(a.y for p,a,b in caixas),max(b.y for p,a,b in caixas)
    baixo,cima = addon.gavetas.limites_na_referencia(conj,ref)
    z0,z1 = baixo.z,cima.z
    for chapa in addon.modulos._chapas_do_conjunto(conj):
        a,b = limites(chapa,inv)
        normal = (inv @ chapa.matrix_world).to_3x3().col[2].normalized()
        if abs(normal.z) < .99 or min(x1,b.x)-max(x0,a.x) < .5*(x1-x0) or min(y1,b.y)-max(y0,a.y) < .25:
            continue
        if b.z <= caixas[0][1].z+.1:
            z0=max(z0,b.z)
        if a.z >= caixas[-1][2].z-.1:
            z1=min(z1,a.z)
    for gavetas in addon.gavetas.grupos_do_modulo(conj):
        l,a,m = addon.gavetas.vao(gavetas)
        pt = [inv@(conj.matrix_world@m@(Vector(v)/1000))*1000
              for v in itertools.product((0,l),(0,addon.gavetas.parametros(gavetas)['profundidade_mm']),(0,a))]
        a=Vector(tuple(min(v[k] for v in pt) for k in range(3)))
        b=Vector(tuple(max(v[k] for v in pt) for k in range(3)))
        if min(x1,b.x)-max(x0,a.x) < .25 or min(y1,b.y)-max(y0,a.y) < .25:
            continue
        if b.z <= caixas[0][1].z+.1:z0=max(z0,b.z)
        if a.z >= caixas[-1][2].z-.1:z1=min(z1,a.z)
    if z1-z0 < .1:
        raise RuntimeError('Vao sem altura: '+grupo.name)
    matrizes = {p:p.matrix_world.copy() for p in ps}
    grupo[addon.prateleiras.CHAVE_MARGENS] = [x0-baixo.x,cima.x-x1,z0-baixo.z,cima.z-z1,y0-baixo.y]
    grupo.matrix_parent_inverse = Matrix.Identity(4)
    grupo.matrix_basis = ref.to_4x4() @ Matrix.Translation(Vector((x0,y0,z0))/1000)
    bpy.context.view_layer.update()
    for p,mat in matrizes.items():p.matrix_world=mat
    p=addon.prateleiras.parametros(grupo)
    p.update(quantidade=len(ps),espacamento='LIVRE',profundidade_mm=y1-y0,recuo_mm=0.,folga_lateral_mm=0.)
    p['vaos_mm']=[];p['individuais']=[]
    anterior=z0
    for i,(obj,a,b) in enumerate(caixas):
        obj[addon.prateleiras.CHAVE_INDICE]=i
        p['vaos_mm'].append(max(0.,a.z-anterior))
        p['individuais'].append(dict(espessura_mm=b.z-a.z,largura_mm=b.x-a.x,
            x_mm=a.x-x0,profundidade_mm=b.y-y0,recuo_mm=a.y-y0,folga_lateral_mm=0.))
        anterior=b.z
    p['espessura_mm']=p['individuais'][0]['espessura_mm']
    grupo[addon.prateleiras.CHAVE_PARAMETROS]=p
    grupo[addon.prateleiras.CHAVE_VAO]=[x1-x0,z1-z0]
    bpy.context.view_layer.update()
    return dict(grupo=grupo.name,origem=[x0,y0,z0],dimensoes=[x1-x0,y1-y0,z1-z0])


def limitar_profundidades(conj):
    addon=_base.addon
    alterados=[]
    for grupo in addon.gavetas.grupos_do_modulo(conj):
        l,a,_m=addon.gavetas.vao(grupo)
        p=addon.gavetas.parametros(grupo)
        disponivel=addon.gavetas.profundidade_disponivel(conj,grupo.matrix_world,l,a,p['profundidade_mm'])
        if disponivel >= p['profundidade_mm']-.25:
            continue
        antes=addon.gavetas.calcular(l,a,p)
        p['profundidade_mm']=disponivel
        for valores in (p.get('individuais') or {}).values():
            if 'profundidade_mm' in valores:valores['profundidade_mm']=min(valores['profundidade_mm'],disponivel)
        depois=addon.gavetas.calcular(l,a,p)
        grupo[addon.gavetas.CHAVE_PARAMETROS]=p
        if [g['trilho_mm'] for g in antes['gavetas']] != [g['trilho_mm'] for g in depois['gavetas']]:
            addon.gavetas.montar(grupo)
        alterados.append(dict(grupo=grupo.name,profundidade_mm=disponivel))
    return alterados


def acertar_vao_gavetas(conj):
    addon=_base.addon
    inv=conj.matrix_world.inverted()
    for grupo in addon.gavetas.grupos_do_modulo(conj):
        ref=addon.gavetas.referencia(grupo)
        lo,hi=addon.gavetas.limites_na_referencia(conj,ref)
        origem=ref.transposed()@(inv@grupo.matrix_world.translation)*1000
        l,a=grupo[addon.gavetas.CHAVE_VAO]
        grupo[addon.gavetas.CHAVE_MARGENS]=[origem.x-lo.x,hi.x-origem.x-l,
            origem.z-lo.z,hi.z-origem.z-a,origem.y-lo.y]
    bpy.context.view_layer.update()


def conferir_edicao_prateleiras(conj):
    addon=_base.addon
    ps=[p for g in addon.prateleiras.grupos_do_modulo(conj) for p in addon.prateleiras.prateleiras_do_grupo(g)]
    antes={p.name:([p.matrix_world@v.co for v in p.data.vertices],p.get('chapa_uid')) for p in ps}
    for grupo in addon.prateleiras.grupos_do_modulo(conj):
        addon.prateleiras.montar(grupo)
        addon.chapas._ocupado[0]=True
    bpy.context.view_layer.update()
    for p in ps:
        pontos,uid=antes[p.name]
        if len(pontos)!=len(p.data.vertices) or p.get('chapa_uid')!=uid:
            raise RuntimeError('A edicao trocou a identidade da prateleira: '+p.name)
        erro=max(((p.matrix_world@v.co)-a).length*1000 for a,v in zip(pontos,p.data.vertices))
        if erro>.01:
            raise RuntimeError('A edicao deslocou a prateleira: %s (%g mm)'%(p.name,erro))


def corrigir_modulo(nome, objetos, dados_fonte=None):
    addon = _base.addon
    conj=next(o for o in objetos if o.get('eh_conjunto_chapa'))
    acoes=dict(laterais=restaurar_laterais(conj,dados_fonte),
               gavetas_internas=adotar_gavetas_internas(conj,nome))
    acertar_vao_gavetas(conj)
    acertar_gaveta_cabeceira(conj,nome)
    acoes['booleanos']=[]
    for obj in bpy.data.objects:
        for mod in obj.modifiers:
            if mod.type=='BOOLEAN' and mod.solver!='EXACT':
                mod.solver='EXACT'
                acoes['booleanos'].append([obj.name,mod.name])
    acoes['topologia']=[o.name for o in list(bpy.data.objects)
                        if o.type=='MESH' and o.get('eh_chapa') and reparar_topologia(o)]
    acoes['frentes']=ajustar_frentes(conj)
    acoes['profundidades']=limitar_profundidades(conj)
    # Recortar apenas prateleiras que realmente atravessam outra peca.
    antes=_auditoria.auditar_modulo(list(bpy.data.objects))
    acoes['recortes']=[]
    for colisao in antes['colisoes_de_pecas']:
        a,b=[bpy.data.objects[n] for n in colisao['pecas']]
        if a.get('eh_prateleira'):alvo,obstaculo=a,b
        elif b.get('eh_prateleira'):alvo,obstaculo=b,a
        else:continue
        recortar(alvo,obstaculo)
        addon.chapas.absorver_malha_editada(alvo,reorientar=False)
        addon.chapas._ocupado[0]=True
        acoes['recortes'].append([alvo.name,obstaculo.name])
    acoes['separadores']=fixar_separadores(conj)
    acertar_vao_gavetas(conj)
    acoes['unioes']=reunir_prateleiras(conj)
    acoes['vaos']=[acertar_vao_prateleiras(g) for g in addon.prateleiras.grupos_do_modulo(conj)]
    conferir_edicao_prateleiras(conj)
    addon.chapas._ocupado[0]=True
    bpy.context.view_layer.update()
    resultado=_auditoria.auditar_modulo(list(bpy.data.objects))
    conferir_auditoria(resultado,nome)
    return acoes,resultado


def conferir_auditoria(resultado,nome):
    problemas={k:resultado[k] for k in ('sobreposicoes_de_envelopes','colisoes_de_pecas','malhas_nao_fechadas') if resultado[k]}
    grupos=[g for g in resultado['grupos'] if g['pecas_fora_do_vao'] or g['desvio_referencial_mm']>.25]
    if problemas or grupos:
        raise RuntimeError('Preset ainda tem interferencias: '+nome+' '+json.dumps(dict(problemas=problemas,grupos=grupos),ensure_ascii=True))


def preparar(biblioteca,fontes,destino):
    _base.validar_destino(str(biblioteca),str(destino))
    biblioteca,fontes,destino=[Path(p).resolve() for p in (biblioteca,fontes,destino)]
    if destino.exists():
        raise ValueError('O destino de preparo ja existe; use uma pasta nova')
    destino.mkdir(parents=True)
    antes=_auditoria.auditar(biblioteca,destino/'auditoria_antes')
    itens=json.loads((biblioteca/'indice.json').read_text(encoding='utf-8'))
    selecionados={m['arquivo'] for m in antes['modulos'] if m['grupos']
                  and (m['sobreposicoes_de_envelopes'] or m['colisoes_de_pecas'] or m['malhas_nao_fechadas'])}
    originais,novos=destino/'originais',destino/'novos'
    originais.mkdir();novos.mkdir()
    # A copia completa permite repetir a varredura tambem nos presets
    # que nao mudaram, sem qualquer escrita na biblioteca de trabalho.
    for arq in biblioteca.iterdir():
        if arq.is_file() and not arq.name.endswith(('.blend1','.blend2')):
            shutil.copy2(arq,novos/arq.name)
    nomes_backup={'indice.json'} | selecionados | {Path(n).with_suffix('.png').name for n in selecionados}
    for nome in nomes_backup:shutil.copy2(biblioteca/nome,originais/nome)
    manifesto=dict(biblioteca=str(biblioteca),versao=_base.addon.bl_info['version'],
                   fontes={},arquivos=[],modulos=[],publicado=False)
    for nome in nomes_backup:
        if _base.digital(biblioteca/nome)!=_base.digital(originais/nome):
            raise RuntimeError('Original mudou durante o backup: '+nome)
    addon=_base.addon
    addon.opcoes._pasta_addon=lambda:str(destino/'guarda')
    addon.biblioteca.pasta_biblioteca=lambda:str(destino/'guarda')
    addon.register();addon.chapas._ocupado[0]=True
    try:
        referencias={}
        for nome,caminho in [('Gaveteiro_19_400x186x550.blend','Cozinha/Bifond/Gaveteiros.dxf'),
                             ('Mesas_de_Cabeceira_Quarto_04_470x487x400.blend','Quartos/Mesas de Cabeceira/Mesas de Cabeceira.dxf')]:
            if nome in selecionados:
                fonte=fontes/caminho
                manifesto['fontes'][str(fonte)]=_base.digital(fonte)
                referencias[nome]=_integracao.capturar(str(fonte))
        for item in itens:
            nome=item['arquivo']
            if nome not in selecionados:continue
            colecoes,objetos=_base.carregar(str(originais/nome))
            catalogos={c.name:c.asset_data.catalog_id for c in colecoes if c.asset_data}
            acoes,resultado=corrigir_modulo(nome,objetos,referencias.get(nome))
            conferir_auditoria(resultado,nome)
            colecoes,objetos=list(bpy.data.collections),list(bpy.data.objects)
            if catalogos!={c.name:c.asset_data.catalog_id for c in colecoes if c.asset_data}:
                raise RuntimeError('Catalogos mudaram: '+nome)
            addon.ferragens.ocultar_pecas_do_rig()
            bpy.context.view_layer.update()
            esperado=_base.estado(colecoes,objetos)
            blend=novos/nome
            bpy.data.libraries.write(str(blend),set(colecoes)|set(objetos),fake_user=True,compress=True)
            png=novos/Path(nome).with_suffix('.png').name
            ok,msg=addon.biblioteca.fotografar_com_camera(str(png),objetos)
            if not ok:raise RuntimeError(nome+': '+msg)
            _base.limpar()
            ok,msg=addon.biblioteca.aplicar_preview_png(str(blend),str(png))
            if not ok:raise RuntimeError(nome+': '+msg)
            cols,objs=_base.carregar(str(blend))
            _base.conferir(esperado,_base.estado(cols,objs))
            conferir_auditoria(_auditoria.auditar_modulo(objs),nome)
            conj=next(o for o in objs if o.get('eh_conjunto_chapa'))
            raizes=[o for o in objs if o.parent is None]
            lo,hi=addon.biblioteca.medir_caixa(bpy.context,objs,raizes)
            item['caixa']=addon.biblioteca.registro_da_caixa(str(blend),lo,hi,conj)
            for n in (nome,png.name):
                manifesto['arquivos'].append(dict(nome=n,original=_base.digital(originais/n),novo=_base.digital(novos/n)))
            manifesto['modulos'].append(dict(arquivo=nome,acoes=acoes,auditoria=resultado))
            (destino/'manifesto.json').write_text(json.dumps(manifesto,ensure_ascii=False,indent=2),encoding='utf-8')
            print('[internos corrigidos]',len(manifesto['modulos']),'/',len(selecionados),nome,flush=True)
    finally:
        _base.limpar();addon.chapas._ocupado[0]=False;addon.unregister()
    (novos/'indice.json').write_text(json.dumps(itens,ensure_ascii=False,indent=1)+'\n',encoding='utf-8',newline='\n')
    manifesto['arquivos'].append(dict(nome='indice.json',original=_base.digital(originais/'indice.json'),novo=_base.digital(novos/'indice.json')))
    (destino/'manifesto.json').write_text(json.dumps(manifesto,ensure_ascii=False,indent=2),encoding='utf-8')
    depois=_auditoria.auditar(novos,destino/'auditoria_depois')
    for m in depois['modulos']:
        if m['arquivo'] in selecionados:conferir_auditoria(m,m['arquivo'])
    if depois['resumo']['modulos_com_colisao'] or depois['resumo']['modulos_com_sobreposicao']:
        raise RuntimeError('A varredura completa ainda tem interferencias')
    manifesto['verificado']=True
    manifesto['resumo_depois']=depois['resumo']
    (destino/'manifesto.json').write_text(json.dumps(manifesto,ensure_ascii=False,indent=2),encoding='utf-8')
    return manifesto


def publicar(destino):
    manifesto=json.loads((Path(destino)/'manifesto.json').read_text(encoding='utf-8'))
    if not manifesto.get('verificado'):
        raise RuntimeError('Preparo sem validacao completa')
    _publicacao.publicar(str(destino))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--biblioteca',default=str(RAIZ/'cabinet_creator/biblioteca'))
    parser.add_argument('--fontes',help='Source DXF directory; required for preparation')
    parser.add_argument('--destino',required=True)
    parser.add_argument('--aplicar',action='store_true')
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    if not args.aplicar and not args.fontes:
        parser.error('--fontes is required for preparation; provide the source DXF directory')
    if args.aplicar:publicar(args.destino)
    else:preparar(args.biblioteca,args.fontes,args.destino)


if __name__=='__main__':
    main()
