"""Stage reversed curved-door repairs while preserving the modeled wood.

Moves hinges to the actual inside support and adds the requested 15 mm
full-height support where needed. Rebuilds curved-leaf handles and verifies
external copies before --apply publishes the prepared files."""
from pathlib import Path
import argparse,json,os,shutil,sys
import bpy
from mathutils import Matrix,Vector
RAIZ=str(Path(__file__).resolve().parents[2]);sys.path.insert(0,RAIZ)
from tools.migrations.adjust_fits import addon,carregar,limpar,estado,conferir,digital,publicar
from tools.migrations.adjust_fits import validar_destino
from tools.migrations.audit_and_repair_integration import verificar_funcoes

ESPESSURA_APOIO_MM=15.0
FUNDO_APOIO_MM=100.0       # Inward from the leaf back: fits the entire mounting plate.
MINIMO_APOIO_MM=40.0       # A segment shorter than this between other panels cannot hold a screw.
NOME_APOIO="Hinge Support"


def _centro_do_corpo(conj):
    pts=[o.matrix_world@Vector(c) for o in addon.modulos._estruturais(addon.modulos._chapas_do_conjunto(conj)) for c in o.bound_box]
    return sum(pts,Vector())/len(pts)


def _centro_da_folha(folha):
    vs=[folha.matrix_world@v.co for v in folha.data.vertices]
    return sum(vs,Vector())/len(vs)


def abre_para_dentro(grupo,conj):
    """Outward leaf travel in mm at half opening (<0 = inward)."""
    F=addon.ferragens
    folha=addon.portas._folhas_portas(grupo)[0]
    gravada,chaves=float(folha.get(F.CHAVE_ABERTURA,0.0)),set(folha.keys())
    F._definir_abertura(bpy.context,folha,0.0);bpy.context.view_layer.update()
    a=_centro_da_folha(folha)
    F._definir_abertura(bpy.context,folha,0.5);bpy.context.view_layer.update()
    b=_centro_da_folha(folha)
    # Measuring does not change the pose saved in the preset.
    F._definir_abertura(bpy.context,folha,gravada)
    for chave in set(folha.keys())-chaves:del folha[chave]
    bpy.context.view_layer.update()
    fora=a-_centro_do_corpo(conj);fora.z=0
    return (b-a).dot(fora.normalized())*1000


def _caixa_no_grupo(obj,inversa):
    pts=[inversa@(obj.matrix_world@Vector(c))*1000 for c in obj.bound_box]
    return [Vector([f(p[i] for p in pts) for i in range(3)]) for f in (min,max)]


def criar_apoios(context,conj,grupo):
    """Support panel(s) on the inner hinge-side face, cut where another
    body panel crosses. Return created names."""
    X=addon.portas
    p=grupo['porta_parametros'];L=float(grupo['porta_vao_largura_mm'])
    folha=X._folhas_portas(grupo)[0]
    _l,a,e,c=addon.ferragens._dados_da_folha(folha)
    E=ESPESSURA_APOIO_MM
    x0,x1=(-E,0.0) if p['dobradica_lado']=='ESQUERDA' else (L,L+E)
    # z = 0 is the body face (opening plane): the panel rests against it
    # and lies outside the leaf in x, so it does not touch the door.
    z0,z1=-FUNDO_APOIO_MM,0.0
    inversa=grupo.matrix_world.inverted()
    livres=[(c[1]-a/2,c[1]+a/2)]
    for obj in addon.modulos._chapas_do_conjunto(conj):
        lo,hi=_caixa_no_grupo(obj,inversa)
        if hi.x<=x0+.5 or lo.x>=x1-.5 or hi.z<=z0+.5 or lo.z>=z1-.5:continue
        livres=[t for y0,y1 in livres for t in ((y0,min(y1,lo.y)),(max(y0,hi.y),y1)) if t[1]-t[0]>1e-6]
    eixos=grupo.matrix_world.to_3x3().normalized()
    # Panel: X = depth (group Z), Y = height, Z = thickness (rotation, never scale).
    giro=Matrix((eixos.col[2],eixos.col[1],-eixos.col[0])).transposed().to_4x4()
    # Old preset without a marker: use the cabinet's collection; otherwise
    # the panel is excluded from the asset and reopens at the origin.
    colecao=addon.modulos._colecao_do_modulo(conj) or conj.users_collection[0]
    referencia=next((o for o in addon.modulos._estruturais(addon.modulos._chapas_do_conjunto(conj))
                     if o.material_slots and o.material_slots[0].material),None)
    criadas=[]
    caixas=[_caixa_no_grupo(o,inversa) for o in addon.modulos._chapas_do_conjunto(conj)]
    for y0,y1 in livres:
        if y1-y0<MINIMO_APOIO_MM:continue
        # Attached to the body: touches one of its panels within 0.5 mm.
        assert any(max(lo.x-x1,x0-hi.x,lo.y-y1,y0-hi.y,lo.z-z1,z0-hi.z)<=.5 for lo,hi in caixas),\
            "unattached support panel: "+grupo.name
        obj=addon.chapas.nova_chapa(NOME_APOIO,z1-z0,y1-y0,E,(0,0,0),(0,0,0),context)
        centro=grupo.matrix_world@(Vector(((x0+x1)/2,(y0+y1)/2,(z0+z1)/2))/1000)
        obj.matrix_world=Matrix.Translation(centro)@giro
        obj.parent=conj;obj.matrix_parent_inverse=conj.matrix_world.inverted()
        obj.matrix_world=Matrix.Translation(centro)@giro
        if colecao is not None:addon.modulos._mover_para_colecao(obj,colecao)
        if referencia is not None:addon.materiais.aplicar([obj],referencia.material_slots[0].material)
        criadas.append(obj.name)
    bpy.context.view_layer.update()
    return criadas,[t for t in livres if t[1]-t[0]>=MINIMO_APOIO_MM]


def mover_para_os_apoios(grupo,trechos):
    """A hinge over a cut support section (crossed by another panel) moves
    to the nearest free segment, stored as a reference."""
    X,F=addon.portas,addon.ferragens
    p=X._copiar_parametros(grupo['porta_parametros'])
    folhas=[F._dados_da_folha(f) for f in X._folhas_portas(grupo)]
    L,A=float(grupo['porta_vao_largura_mm']),float(grupo['porta_vao_altura_mm'])
    aresta,distancias,_i=F._dobradicas_da_porta(p,L,A,folhas)[0]
    comprimento=(aresta['b']-aresta['a']).length
    meia=X.DOBRADICA_ALTURA_MM/2+2
    novas=[]
    for d in distancias:
        y=aresta['a'].y+d
        if any(y0+meia<=y<=y1-meia for y0,y1 in trechos):
            novas.append(d);continue
        y=min((max(y0+meia,min(y1-meia,y)) for y0,y1 in trechos),key=lambda t:abs(t-y))
        novas.append(y-aresta['a'].y)
    if novas==list(distancias):
        return False
    p['dobradicas_referencia']={'0':[d/comprimento for d in sorted(novas)]}
    p['dobradicas_qtd']=len(novas)
    grupo['porta_parametros']=p
    F._refazer_ferragens(grupo)
    return True


def _bases(grupo):
    nomes=[o.name for o in grupo.children_recursive]
    return (sum(n.startswith("Angled Hinge Base") for n in nomes),
            sum(n.startswith('Dobradica Corpo') for n in nomes))


def corrigir(context,objs):
    """Return (changes, touched names)."""
    feitos,tocados=[],set()
    for conj in [o for o in objs if addon.chapas.MARCA_CONJUNTO in o]:
        for g in list(addon.portas._portas_do_conjunto(conj)):
            p=g.get('porta_parametros') or {}
            folhas=addon.portas._folhas_portas(g)
            if (p.get('abertura')!='GIRO' or len(folhas)!=1
                    or not folhas[0].get('porta_curva_modelada') or abre_para_dentro(g,conj)>=-20):
                continue
            tocados|={g.name}|{o.name for o in g.children_recursive}
            addon.importacao._definir_frente_porta(context,g,-g.matrix_world.to_3x3().col[2])
            q=addon.portas._copiar_parametros(g['porta_parametros']);q['dobradica_apoio_real']=True
            g['porta_parametros']=q
            addon.ferragens._refazer_ferragens(g)
            apoios=[]
            if _bases(g)[1]:
                apoios,trechos=criar_apoios(context,conj,g)
                addon.ferragens._refazer_ferragens(g)
                if _bases(g)[1] and trechos:
                    mover_para_os_apoios(g,trechos)
            # User request: every hinge on these doors rests on the thin panel.
            assert not _bases(g)[1],"hinge has no support: "+g.name
            tocados|={o.name for o in g.children_recursive}|set(apoios)
            feitos.append(dict(grupo=g.name,apoios=apoios,bases=_bases(g)[0],corpos=_bases(g)[1],
                               abre_para_fora_mm=round(abre_para_dentro(g,conj))))
    # Query the scene again: rebuilding hardware deleted components from `objs`.
    for pux in [o for o in bpy.data.objects if addon.chapas.MARCA_PUXADOR in o and o.get('puxador_curvo')]:
        f=pux.parent
        if (not f or not f.get('porta_curva_modelada') or f.get('porta_linha_frente')
                or addon.frentes.referencia(f) is not None or pux.name in tocados):
            continue
        antes=pux.matrix_basis.copy()
        addon.puxadores.posicionar_puxador(pux)
        if pux.get('puxador_tipo')=='PERFIL':
            # Like library profiles (v306): omit the model material, about 1 MB.
            pux.data.materials.clear()
        if max(abs(x-y) for la,lb in zip(antes,pux.matrix_basis) for x,y in zip(la,lb))>1e-5:
            tocados.add(pux.name);feitos.append(dict(puxador=pux.name,folha=f.name))
    bpy.context.view_layer.update()
    return feitos,tocados


def verificar(objs):
    """Every curved door opens outward, with no hinge component outside the body."""
    for conj in [o for o in objs if addon.chapas.MARCA_CONJUNTO in o]:
        inv=conj.matrix_world.inverted()
        pts=[inv@(o.matrix_world@Vector(c)) for o in addon.modulos._estruturais(addon.modulos._chapas_do_conjunto(conj)) for c in o.bound_box]
        lo=Vector([min(q[i] for q in pts) for i in range(3)]);hi=Vector([max(q[i] for q in pts) for i in range(3)])
        for g in addon.portas._portas_do_conjunto(conj):
            folhas=addon.portas._folhas_portas(g)
            if not (len(folhas)==1 and folhas[0].get('porta_curva_modelada')
                    and (g.get('porta_parametros') or {}).get('abertura')=='GIRO'):continue
            assert abre_para_dentro(g,conj)>0,"door opens inward: "+g.name
            for o in g.children_recursive:
                if (o.type!='MESH' or not o.name.startswith("Hinge") or o.hide_render
                        or (o.parent and o.parent.get('eh_folha_porta'))):continue
                for v in o.data.vertices:
                    q=inv@(o.matrix_world@v.co)
                    assert max(lo.x-q.x,q.x-hi.x,lo.y-q.y,q.y-hi.y)<.003,"hinge outside the body: "+o.name


def preparar(biblioteca,destino):
    validar_destino(biblioteca,destino)
    novos,originais=[os.path.join(destino,p) for p in ('novos','originais')]
    os.makedirs(novos,exist_ok=False);os.makedirs(originais,exist_ok=False)
    addon.opcoes._pasta_addon=lambda:novos;addon.biblioteca.pasta_biblioteca=lambda:novos;addon.register()
    indice=os.path.join(biblioteca,'indice.json')
    m=dict(biblioteca=biblioteca,versao=addon.bl_info['version'],indice=digital(indice),
           arquivos=[],modulos=[],verificados=0,publicado=False)
    for it in json.load(open(indice,encoding='utf-8')):
        if it.get('tipo')!='modulo':continue
        nomes=[it['arquivo'],os.path.splitext(it['arquivo'])[0]+'.png']
        hashes={s:digital(os.path.join(biblioteca,s)) for s in nomes}
        cs,objs=carregar(os.path.join(biblioteca,nomes[0]))
        antes=estado(cs,objs)
        madeira={f.name:[f.matrix_world@v.co for v in f.data.vertices]
                 for g in [o for o in objs if addon.chapas.MARCA_PORTAS in o]
                 for f in addon.portas._folhas_portas(g) if f.get('porta_curva_modelada')}
        feitos,tocados=corrigir(bpy.context,objs)
        m['verificados']+=1
        if not feitos:continue
        objs=list(bpy.data.objects)
        depois=estado(list(bpy.data.collections),objs)
        # Nothing changes except reversed doors and rebuilt handles.
        for nome,dados in antes['objetos'].items():
            if nome not in tocados:conferir(dados,depois['objetos'][nome],nome)
        conferir(antes['assets'],depois['assets'])
        for nome,pontos in madeira.items():
            folha=bpy.data.objects[nome]
            addon.ferragens._definir_abertura(bpy.context,folha,0.0)
            bpy.context.view_layer.update()
            erro=max((folha.matrix_world@v.co-q).length for v,q in zip(folha.data.vertices,pontos))
            assert erro<1e-5,"door wood moved: %s %.3f mm"%(nome,erro*1000)
        verificar(objs)
        for s in nomes:shutil.copy2(os.path.join(biblioteca,s),os.path.join(originais,s))
        blend,png=[os.path.join(novos,s) for s in nomes]
        bpy.data.libraries.write(blend,set(bpy.data.collections)|set(bpy.data.objects),fake_user=True,compress=True)
        salvar=estado(list(bpy.data.collections),list(bpy.data.objects))
        for g in [o for o in objs if addon.chapas.MARCA_PORTAS in o]:    # CLOSED photo.
            for f in addon.portas._folhas_portas(g):
                addon.ferragens._definir_abertura(bpy.context,f,addon.biblioteca.ABERTURA_FOTO)
        bpy.context.view_layer.update()
        ok,msg=addon.biblioteca.fotografar_com_camera(png,list(bpy.data.objects))
        if not ok:raise RuntimeError(msg)
        limpar();ok,msg=addon.biblioteca.aplicar_preview_png(blend,png)
        if not ok:raise RuntimeError(msg)
        cs,objs=carregar(blend);conferir(salvar,estado(cs,objs))
        verificar(objs)
        # List first: editing drawers rebuilds objects and makes `objs` stale.
        for conj in [o for o in objs if addon.chapas.MARCA_CONJUNTO in o]:verificar_funcoes(conj)
        for s in nomes:
            assert digital(os.path.join(biblioteca,s))==hashes[s]
            m['arquivos'].append(dict(nome=s,original=hashes[s],novo=digital(os.path.join(novos,s))))
        m['modulos'].append(dict(arquivo=it['arquivo'],alteracoes=feitos))
        print("[curved doors]",it['arquivo'],json.dumps(feitos),flush=True)
    limpar();addon.unregister()
    json.dump(m,open(os.path.join(destino,'manifesto.json'),'w',encoding='utf-8'),indent=1)
    print('VERIFICADOS',m['verificados'],'ALTERADOS',len(m['modulos']),flush=True)


def main():
    p=argparse.ArgumentParser();p.add_argument('--destination', required=True, dest='destino', metavar='DESTINATION')
    p.add_argument('--library', default=os.path.join(RAIZ, 'archy_builder', "assets/library"), dest='biblioteca', metavar='LIBRARY');p.add_argument('--apply', action='store_true', dest='aplicar')
    a=p.parse_args(sys.argv[sys.argv.index('--')+1:])
    validar_destino(a.biblioteca,a.destino)
    if a.aplicar:
        m=json.load(open(os.path.join(a.destino,'manifesto.json'),encoding='utf-8'))
        if m['indice']!=digital(os.path.join(a.biblioteca,'indice.json')):
            raise RuntimeError("Library index changed since preparation")
        publicar(a.destino)
    else:preparar(a.biblioteca,a.destino)


if __name__=='__main__':main()
