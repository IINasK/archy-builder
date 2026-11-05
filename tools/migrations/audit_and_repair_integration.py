"""Audit preset functions against DXF sources and stage repairs with backups.

This tool can modify staged presets and publish with --aplicar; it is not
a read-only audit. The manifest retains expected/before/after functional checks.

Supply --fontes DIRECTORY explicitly for preparation.
--aplicar uses the source paths recorded in the existing manifest.
"""
from pathlib import Path
import argparse, json, os, shutil, sys
import bpy
from mathutils import Matrix, Vector
from mathutils.kdtree import KDTree
RAIZ = str(Path(__file__).resolve().parents[2])
sys.path.insert(0, RAIZ)
from tools.migrations.adjust_fits import (addon, carregar, limpar, estado, conferir,
                                    digital, publicar, caminho_da_peca)
from tools.migrations.adjust_fits import validar_destino
from tools.migrations.adjust_doors import deslocamento, nome_fonte


def numerico(v):
    if isinstance(v, (Matrix, Vector)):
        return [numerico(x) for x in v]
    if isinstance(v, dict):
        return {k:numerico(x) for k,x in v.items() if k not in ('obj','original','pontos')}
    if isinstance(v, (list, tuple)):
        return [numerico(x) for x in v]
    return v


def capturar(path):
    orig = addon.promob.planejar
    aplicar, marcar, ajustar = addon.promob.aplicar, addon.promob.marcar_dependentes, addon.promob.ajustar_encaixes
    planos = []
    def plano(ps, fs):
        p = orig(ps, fs)
        planos.append(dict(plano=numerico(p), pecas={q['origem']:numerico(q) for q in ps}, ferragens=numerico(fs)))
        return dict(portas=[],gavetas=[],correr=[],remover=[],fundo=None,travessas=[])
    try:
        limpar()
        addon.promob.planejar=plano
        addon.promob.aplicar=lambda *args:dict(portas=0,gavetas=0,correr=0,prateleiras=0)
        addon.promob.marcar_dependentes=lambda *args:None
        addon.promob.ajustar_encaixes=lambda *args:[]
        addon.importacao.importar_dxf_promob(bpy.context,path)
    finally:
        addon.promob.planejar=orig
        addon.promob.aplicar,addon.promob.marcar_dependentes,addon.promob.ajustar_encaixes=aplicar,marcar,ajustar
        limpar()
    return planos, addon.importacao.ler_dxf_promob(path)


def esperado(p):
    return dict(gavetas=sum(len(g['frentes']) or 1 for g in p['gavetas']),
                portas=sum(len(g['folhas']) for g in p['portas']),
                correr=sum(min(4,len(g['quadros'])) for g in p['correr']),
                prateleiras=sum(len(g) for g in p.get('prateleiras',[])))


def atual(conj):
    portas=addon.portas._portas_do_conjunto(conj)
    return dict(gavetas=sum(len(addon.gavetas.gavetas_do_grupo(g)) for g in addon.gavetas.grupos_do_modulo(conj)),
        portas=sum(len(addon.portas._folhas_portas(g)) for g in portas if g['porta_parametros']['abertura']!='CORRER'),
        correr=sum(len(addon.portas._folhas_portas(g)) for g in portas if g['porta_parametros']['abertura']=='CORRER'),
        prateleiras=sum(len(addon.prateleiras.prateleiras_do_grupo(g)) for g in addon.prateleiras.grupos_do_modulo(conj)))


def deslocamento_do_preset(conj,dados):
    try:return deslocamento(conj,dados)
    except ValueError:
        # Categoria tambem contem chapas avulsas, sem lateral vertical.
        # Elas continuam componentes; nao inventar uma gaveta sem frente.
        deltas=[]
        for o in addon.modulos._chapas_do_conjunto(conj):
            p=dados['pecas'].get(nome_fonte(o))
            if p is None:continue
            vs=[o.matrix_world @ v.co * 1000 for v in o.data.vertices]
            centro=Vector(tuple((min(v[k] for v in vs)+max(v[k] for v in vs))/2 for k in range(3)))
            deltas.append(Vector(tuple((p['lo'][k]+p['hi'][k])/2 for k in range(3)))-centro)
        if not deltas:raise
        return Vector(tuple(sorted(v[k] for v in deltas)[len(deltas)//2] for k in range(3)))


def gavetas_correspondem(conj,p,offset):
    fs=[addon.gavetas.frente_da_gaveta(d) for g in addon.gavetas.grupos_do_modulo(conj) for d in addon.gavetas.gavetas_do_grupo(g)]
    fontes=[(Matrix(g.get('referencia',Matrix.Identity(3))),f) for g in p['gavetas'] for f in g['frentes']]
    if len(fs)!=sum(len(g['frentes']) or 1 for g in p['gavetas']):
        return False
    for ref,f in fontes:
        centro=ref @ Vector(tuple((f['lo'][k]+f['hi'][k])/2 for k in range(3)))/1000-offset/1000
        if not any((o.matrix_world.translation-centro).length<.001 and
                   abs(o.matrix_world.to_3x3().col[2].normalized().dot(ref.col[1]))>.995
                   and abs(o.chapa_largura_mm-(f['hi'][0]-f['lo'][0]))<.25
                   and abs(o.chapa_comprimento_mm-(f['hi'][2]-f['lo'][2]))<.25 for o in fs):
            return False
    return True


def corrigir_gavetas(conj,dados,geometria,offset):
    plano=dados['plano']
    antigas=addon.gavetas.grupos_do_modulo(conj)
    fontes={f['origem'] for g in plano['gavetas'] for f in g['frentes']+g.get('caixa',[]) if f.get('origem')}
    chapas={nome_fonte(o):o for o in addon.modulos._chapas_do_conjunto(conj)}
    restauradas, mats=[],[]
    for g in antigas:
        for d in addon.gavetas.gavetas_do_grupo(g):
            f=addon.gavetas.frente_da_gaveta(d)
            centro=f.matrix_world.translation*1000+offset
            n=f.matrix_world.to_3x3().col[2].normalized()
            candidatos=[((Vector(tuple((p['lo'][k]+p['hi'][k])/2 for k in range(3)))-centro).length,nome)
                for nome,p in dados['pecas'].items() if 'normal' in p and abs(n.dot(Vector(p['normal'])))>.995]
            if candidatos:
                dist,nome=min(candidatos)
                if dist<35 and nome not in fontes and nome not in chapas:
                    restauradas.append((nome,[(s.link,s.material) for s in f.material_slots]))
            mats.append((f.matrix_world.translation.copy(),[(s.link,s.material) for s in f.material_slots]))
        for obj in list(g.children_recursive)[::-1]:
            addon.gavetas._remover(obj)
        addon.gavetas._remover(g)
    for nome,material in restauradas:
        vs,fs=geometria[nome.removeprefix('Peca ')]
        obj=addon.importacao._objeto_da_peca(bpy.context,nome,[tuple(Vector(v)-offset) for v in vs],fs,conj.users_collection[0])
        addon.importacao.converter_em_chapa(obj)
        mundo=obj.matrix_world.copy()
        obj.parent=conj
        obj.matrix_parent_inverse=conj.matrix_world.inverted()
        obj.matrix_world=mundo
        for link,mat in material:
            obj.data.materials.append(mat)
            obj.material_slots[-1].link=link
            obj.material_slots[-1].material=mat
    for nome in fontes:
        if nome in chapas:
            obj=chapas[nome]
            if any(f['origem']==nome for g in plano['gavetas'] for f in g['frentes']):
                mats.append((obj.matrix_world.translation.copy(),[(s.link,s.material) for s in obj.material_slots]))
            addon.gavetas._remover(obj)
    bpy.context.view_layer.update()
    qs=[]
    for g in plano['gavetas']:
        ref=Matrix(g.get('referencia',Matrix.Identity(3)))
        delta=ref.transposed() @ offset
        q=dict(g,referencia=ref,plano=g['plano']-delta.y,
               vao=[v-d for v,d in zip(g['vao'],(delta.x,delta.x,delta.z,delta.z))],
               frentes=[dict(f,lo=[v-delta[k] for k,v in enumerate(f['lo'])],
                                hi=[v-delta[k] for k,v in enumerate(f['hi'])]) for f in g['frentes']])
        qs.append(q)
    porta_refs=[dict(p,referencia=Matrix(p.get('referencia',Matrix.Identity(3)))) for p in plano['portas']]
    addon.promob.orientar_modulo(conj,dict(portas=porta_refs,gavetas=qs))
    for q in qs:
        grupo=addon.promob._gavetas_do_plano(bpy.context,conj,q)
        if grupo is None:
            raise RuntimeError('Gavetas nao integradas: '+conj.name)
        for d in addon.gavetas.gavetas_do_grupo(grupo):
            f=addon.gavetas.frente_da_gaveta(d)
            if mats:
                _,slots=min(mats,key=lambda a:(a[0]-f.matrix_world.translation).length)
                f.data.materials.clear()
                for link,mat in slots:
                    f.data.materials.append(mat)
                    f.material_slots[-1].link=link
                    f.material_slots[-1].material=mat
    return [nome for nome,material in restauradas]


def verificar_funcoes(conj):
    funcoes=[]
    for g in addon.gavetas.grupos_do_modulo(conj):
        ds=addon.gavetas.gavetas_do_grupo(g)
        p=addon.gavetas.parametros(g)
        assert len(ds)==p['quantidade']
        for d in ds:
            f=addon.gavetas.frente_da_gaveta(d)
            addon.gavetas.selecionar(bpy.context,f,'GRUPO')
            assert bpy.context.object==g
            assert len(addon.gavetas.gavetas_com_slider(bpy.context))==len(ds)
            a=f.matrix_world.translation.copy()
            addon.gavetas.definir_abertura(d,1)
            bpy.context.view_layer.update()
            assert (f.matrix_world.translation-a).length>.2
            addon.gavetas.definir_abertura(d,0)
        margem=list(g[addon.gavetas.CHAVE_MARGENS])
        assert addon.gavetas.editar(bpy.context,g,'entre_gavetas_mm',p['entre_gavetas_mm']+1) is None
        assert addon.gavetas.editar(bpy.context,g,'entre_gavetas_mm',p['entre_gavetas_mm']) is None
        assert max(abs(a-b) for a,b in zip(margem,g[addon.gavetas.CHAVE_MARGENS]))<.001
        funcoes.append('gavetas: selecao, slider, abertura, editar/restaurar, trilhos e puxadores')
    for g in addon.prateleiras.grupos_do_modulo(conj):
        ps=addon.prateleiras.prateleiras_do_grupo(g)
        p=addon.prateleiras.parametros(g)
        assert len(ps)==p['quantidade']
        ids=[o.get('chapa_uid') for o in ps]
        addon.prateleiras.selecionar(bpy.context,ps[0],'GRUPO')
        assert bpy.context.object==g
        assert addon.prateleiras.editar(bpy.context,g,'espessura_mm',p['espessura_mm']) is None
        assert ids==[o.get('chapa_uid') for o in addon.prateleiras.prateleiras_do_grupo(g)]
        funcoes.append('prateleiras: selecao, editar, UID, vao livre')
    for g in addon.portas._portas_do_conjunto(conj):
        for f in addon.portas._folhas_portas(g):
            addon.ferragens._definir_abertura(bpy.context,f,1)
            addon.ferragens._definir_abertura(bpy.context,f,0)
        funcoes.append('portas: abertura/restaurar, ferragens nativas')
    bpy.context.view_layer.update()
    return funcoes


def preparar(biblioteca,fontes,destino):
    validar_destino(biblioteca, destino)
    novos,originais=[os.path.join(destino,p) for p in ('novos','originais')]
    os.makedirs(novos,exist_ok=False);os.makedirs(originais,exist_ok=False)
    addon.opcoes._pasta_addon=lambda:novos
    addon.biblioteca.pasta_biblioteca=lambda:novos
    addon.register()
    indice=json.load(open(os.path.join(biblioteca,'indice.json'),encoding='utf-8'))
    m=dict(biblioteca=biblioteca,versao=addon.bl_info['version'],arquivos=[],modulos=[],auditoria=[],fontes={},publicado=False)
    caminhos={}
    for pasta,_,nomes in os.walk(fontes):
        for nome in nomes:
            if nome.lower().endswith('.dxf'):
                path=os.path.join(pasta,nome)
                aba,categoria,prefixo=addon.importacao.categoria_promob(path)
                caminhos[(os.path.relpath(pasta,fontes).split(os.sep)[0],aba,categoria)]=path
    for cat,path in sorted(caminhos.items()):
        itens=[it for it in indice if tuple(addon.biblioteca.caminho_de(it)[1:])==cat and it.get('tipo')=='modulo']
        if not itens:continue
        m['fontes'][path]=digital(path)
        planos,geo=capturar(path)
        for it in itens:
            nomes=[it['arquivo'],os.path.splitext(it['arquivo'])[0]+'.png']
            hashes={s:digital(caminho_da_peca(biblioteca,s)) for s in nomes}
            cols,objs=carregar(caminho_da_peca(biblioteca,nomes[0]))
            conj,=[o for o in objs if addon.chapas.MARCA_CONJUNTO in o]
            # Pelas camadas de origem, como o integrar: o numero do nome nao
            # e' o indice do plano ("Canto 05A/05B" divide um modulo em dois).
            fontes_preset={nome_fonte(o) for o in addon.modulos._chapas_do_conjunto(conj)}
            d=max(planos,key=lambda d:len(fontes_preset&d['pecas'].keys()))
            p=d['plano'];exp=esperado(p)
            offset=deslocamento_do_preset(conj,d)
            a=atual(conj);antes=estado(cols,objs)
            pontos_antes={o.name:[o.matrix_world @ v.co for v in o.data.vertices]
                          for o in objs if o.type=='MESH' and addon.chapas.MARCA_CHAPA in o}
            linha=dict(arquivo=it['arquivo'],categoria=cat,esperado=exp,antes=a)
            modificado=False;restauradas=[]
            if not gavetas_correspondem(conj,p,offset):
                restauradas=corrigir_gavetas(conj,d,geo,offset);modificado=True
            existentes={nome_fonte(o) for g in addon.prateleiras.grupos_do_modulo(conj) for o in addon.prateleiras.prateleiras_do_grupo(g)}
            chapas={nome_fonte(o):o for o in addon.modulos._chapas_do_conjunto(conj)}
            adotadas=[]
            for pilha in p.get('prateleiras',[]):
                for v in pilha:
                    if v['origem'] in chapas:chapas[v['origem']][addon.prateleiras.MARCA_PRATELEIRA]=1
            for pilha in p.get('prateleiras',[]):
                nomes_ps=[v['origem'] for v in pilha]
                if all(s in existentes for s in nomes_ps):continue
                if not all(s in chapas for s in nomes_ps):
                    json.dump(dict(fonte=d,existentes=list(chapas),antes=antes),open(os.path.join(destino,'ausentes.json'),'w'),indent=1)
                    raise RuntimeError('Prateleira sem correspondencia: '+it['arquivo']+str(nomes_ps))
                ps=[dict(v,obj=chapas[v['origem']]) for v in pilha]
                addon.promob._prateleiras_do_plano(bpy.context,conj,ps)
                adotadas+=nomes_ps;modificado=True
            linha['depois']=atual(conj)
            for k in exp:
                if linha['depois'][k]!=exp[k]:
                    raise RuntimeError('Sistema diverge do DXF: '+it['arquivo']+' '+k+str(linha))
            bpy.context.view_layer.update()
            linha['funcoes']=verificar_funcoes(conj)
            if modificado:
                depois=estado(list(bpy.data.collections),list(bpy.data.objects))
                removidos={f['origem'] for g in p['gavetas'] for f in g['frentes']+g.get('caixa',[]) if f.get('origem')}
                for obj in addon.modulos._chapas_do_conjunto(conj):
                    if obj.name in antes['objetos'] and nome_fonte(obj) not in removidos:
                        conferir(antes['objetos'][obj.name]['malha'],depois['objetos'][obj.name]['malha'],obj.name)
                preservadas = addon.modulos._chapas_do_conjunto(conj) + [o for g in addon.prateleiras.grupos_do_modulo(conj)
                    for o in addon.prateleiras.prateleiras_do_grupo(g)]
                for obj in preservadas:
                    if obj.name not in pontos_antes or nome_fonte(obj) in removidos:continue
                    pts=[obj.matrix_world @ v.co for v in obj.data.vertices]
                    referencia=KDTree(len(pontos_antes[obj.name]))
                    for i,v in enumerate(pontos_antes[obj.name]):referencia.insert(v,i)
                    referencia.balance()
                    if len(pts)!=len(pontos_antes[obj.name]) or any(referencia.find(v)[2]>1e-5 for v in pts):
                        json.dump(dict(arquivo=it['arquivo'],objeto=obj.name,
                            antes=[list(v) for v in pontos_antes[obj.name]],depois=[list(v) for v in pts],
                            medidas=depois['objetos'][obj.name]['medidas'],parametros=numerico(addon.prateleiras.parametros(obj.parent))),
                            open(os.path.join(destino,'geometria-divergente.json'),'w'),indent=1)
                        raise AssertionError('Geometria mundial mudou: '+obj.name)
                    conferir(antes['objetos'][obj.name]['materiais'],depois['objetos'][obj.name]['materiais'],obj.name+'/materiais')
                    if antes['objetos'][obj.name]['props'].get('chapa_uid')!=obj.get('chapa_uid'):
                        raise AssertionError('UID mudou: '+obj.name)
                conferir(antes['assets'],depois['assets'],'Catalogos')
                for s in nomes:shutil.copy2(caminho_da_peca(biblioteca,s),os.path.join(originais,s))
                blend,png=[os.path.join(novos,s) for s in nomes]
                bpy.data.libraries.write(blend,set(bpy.data.collections)|set(bpy.data.objects),fake_user=True)
                guardar=estado(list(bpy.data.collections),list(bpy.data.objects))
                addon.biblioteca.preparar_abertura_foto(bpy.context,conj)
                ok,msg=addon.biblioteca.fotografar_com_camera(png,list(bpy.data.objects))
                if not ok:raise RuntimeError(msg)
                limpar();ok,msg=addon.biblioteca.aplicar_preview_png(blend,png)
                if not ok:raise RuntimeError(msg)
                cols,objs=carregar(blend)
                relido=estado(cols,objs)
                try:conferir(guardar,relido)
                except AssertionError:
                    json.dump(dict(antes=guardar,depois=relido),open(os.path.join(destino,'divergencia.json'),'w'),indent=1)
                    raise
                for s in nomes:
                    if digital(caminho_da_peca(biblioteca,s))!=hashes[s]:raise RuntimeError('Biblioteca mudou: '+s)
                    m['arquivos'].append(dict(nome=s,original=hashes[s],novo=digital(os.path.join(novos,s))))
                m['modulos'].append(dict(arquivo=it['arquivo'],restauradas=restauradas,prateleiras=adotadas))
            m['auditoria'].append(linha)
            print('[auditoria]',len(m['auditoria']),it['arquivo'],a,'->',linha['depois'],flush=True)
    limpar();addon.unregister()
    json.dump(m,open(os.path.join(destino,'manifesto.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=1)
    print('AUDITADOS',len(m['auditoria']),'CORRIGIDOS',len(m['modulos']),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--destino',required=True)
    p.add_argument('--biblioteca',default=os.path.join(RAIZ,'archy_builder','biblioteca'))
    p.add_argument('--fontes',help='Source DXF directory; required for preparation');p.add_argument('--aplicar',action='store_true')
    a=p.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    if not a.aplicar and not a.fontes:
        p.error('--fontes is required for preparation; provide the source DXF directory')
    validar_destino(a.biblioteca, a.destino)
    if a.aplicar:
        m=json.load(open(os.path.join(a.destino,'manifesto.json'),encoding='utf-8'))
        for path,hash_fonte in m['fontes'].items():
            if digital(path)!=hash_fonte:raise RuntimeError('Fonte mudou: '+path)
        publicar(a.destino)
    else:preparar(a.biblioteca,a.fontes,a.destino)


if __name__=='__main__':main()
