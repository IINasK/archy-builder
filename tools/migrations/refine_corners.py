"""Rebuild a DXF corner category with native systems and verified external backups.

Preserves preset names, index entries and catalog UUIDs; reopens before publication.

Supply --fonte FILE explicitly for preparation.
--aplicar uses the source paths recorded in the existing manifest.
"""
from pathlib import Path
import argparse,json,os,re,shutil,sys
import bpy
from mathutils import Vector
RAIZ=str(Path(__file__).resolve().parents[2])
sys.path.insert(0,RAIZ)
from tools.migrations.adjust_fits import addon,carregar,limpar,estado,conferir,digital,publicar,valor_json
from tools.migrations.adjust_fits import validar_destino


def preparar(biblioteca,fonte,destino):
    validar_destino(biblioteca, destino)
    novos,originais,brutos=[os.path.join(destino,n) for n in ('novos','originais','brutos')]
    for p in (novos,originais,brutos):os.makedirs(p,exist_ok=False)
    addon.opcoes._pasta_addon=lambda:novos
    addon.biblioteca.pasta_biblioteca=lambda:novos
    addon.register()
    indice=json.load(open(os.path.join(biblioteca,'indice.json'),encoding='utf-8'))
    aba,categoria,prefixo=addon.importacao.categoria_promob(fonte)
    itens=[it for it in indice if addon.biblioteca.caminho_de(it)==('Armarios','Cozinha',aba,categoria)]
    if not itens:raise ValueError('Categoria sem presets correspondentes ao DXF')
    m=dict(biblioteca=biblioteca,versao=addon.bl_info['version'],arquivos=[],modulos=[],publicado=False,
           fontes={fonte:digital(fonte)},indice=digital(os.path.join(biblioteca,'indice.json')))
    limpar()
    grupos,info=addon.importacao.importar_dxf_promob(bpy.context,fonte,prefixo,na_origem=True)
    if len(grupos)!=len(itens):raise ValueError('Quantidade de montagens mudou no DXF')
    for i,g in enumerate(grupos,1):
        col=addon.modulos._colecao_do_modulo(g)
        col.asset_mark()
        bpy.data.libraries.write(os.path.join(brutos,'%02d.blend'%i),{col,g,*g.children_recursive},fake_user=True,compress=True)
    for it in itens:
        num=int(re.search(r'\b(\d{2})\b',it['nome']).group(1))
        nomes=[it['arquivo'],os.path.splitext(it['arquivo'])[0]+'.png']
        hashes={n:digital(os.path.join(biblioteca,n)) for n in nomes}
        cs,objs=carregar(os.path.join(biblioteca,it['arquivo']))
        asset=next(c for c in cs if c.asset_data)
        antigo=next(o for o in objs if addon.chapas.MARCA_CONJUNTO in o)
        # Esta migracao corrige montagem de PORTAS. Os dois recortes
        # antigos sem folhas funcionais nao podem ser reconstruidos aqui
        # e validados como se tivessem ferragens.
        if not addon.portas._portas_do_conjunto(antigo):
            print('[cantos] sem portas funcionais, preservado:',it['nome'],flush=True)
            continue
        catalogo,nome_asset=asset.asset_data.catalog_id,asset.name
        props_asset=valor_json(dict(asset.items()))
        uids={o.name:o.get('chapa_uid') for o in objs if addon.chapas.MARCA_CHAPA in o}
        # Presets de fabrica: conservar tambem os materiais pintados por
        # slot, sem reduzir a um RGB (o .blend antigo e' a fonte).
        materiais={o.name:[(s.link,s.material.name if s.material else None) for s in o.material_slots] for o in objs if o.type=='MESH'}
        nomes_mats={n for slots in materiais.values() for _,n in slots if n}
        for n in nomes:shutil.copy2(os.path.join(biblioteca,n),os.path.join(originais,n))
        cs,objs=carregar(os.path.join(brutos,'%02d.blend'%num))
        g=next(o for o in objs if addon.chapas.MARCA_CONJUNTO in o)
        addon.modulos.nomear_grupo(g,it['nome'])
        col=addon.modulos._colecao_do_modulo(g)
        col.name=nome_asset
        for k,v in props_asset.items():col[k]=v
        if col.asset_data is None:col.asset_mark()
        col.asset_data.catalog_id=catalogo
        with bpy.data.libraries.load(os.path.join(biblioteca,it['arquivo']),link=False) as (de,para):
            pedidos=[n for n in de.materials if n in nomes_mats]
            para.materials=pedidos
        mats={n:mat for n,mat in zip(pedidos,para.materials) if mat}
        for o in objs:
            if o.name in uids and uids[o.name]:o['chapa_uid']=uids[o.name]
            if o.name not in materiais or o.type!='MESH':continue
            o.data.materials.clear()
            for link,n in materiais[o.name]:
                o.data.materials.append(mats.get(n))
                o.material_slots[-1].link=link
                o.material_slots[-1].material=mats.get(n)
        addon.chapas.detectar_adjacencia(addon.modulos._chapas_do_conjunto(g))
        addon.ferragens.ocultar_pecas_do_rig()
        bpy.context.view_layer.update()
        validar(g)
        blend,png=[os.path.join(novos,n) for n in nomes]
        bpy.data.libraries.write(blend,{col,g,*g.children_recursive},fake_user=True,compress=True)
        antes=estado(list(bpy.data.collections),list(bpy.data.objects))
        # Foto fechada de comparacao, fora da biblioteca.
        ok,msg=addon.biblioteca.fotografar_com_camera(os.path.join(destino,'fechado-%02d.png'%num),list(bpy.data.objects))
        if not ok:raise RuntimeError(msg)
        addon.biblioteca.preparar_abertura_foto(bpy.context,g)
        ok,msg=addon.biblioteca.fotografar_com_camera(png,list(bpy.data.objects))
        if not ok:raise RuntimeError(msg)
        limpar()
        ok,msg=addon.biblioteca.aplicar_preview_png(blend,png)
        if not ok:raise RuntimeError(msg)
        cs,objs=carregar(blend)
        conferir(antes,estado(cs,objs))
        g=next(o for o in objs if addon.chapas.MARCA_CONJUNTO in o)
        auditoria=validar(g)
        for n in nomes:
            if digital(os.path.join(biblioteca,n))!=hashes[n]:raise RuntimeError('Original mudou: '+n)
            m['arquivos'].append(dict(nome=n,original=hashes[n],novo=digital(os.path.join(novos,n))))
        m['modulos'].append(dict(arquivo=it['arquivo'],auditoria=auditoria))
        print('[cantos]',it['nome'],auditoria,flush=True)
    limpar();addon.unregister()
    json.dump(m,open(os.path.join(destino,'manifesto.json'),'w',encoding='utf-8'),indent=1,ensure_ascii=False)
    return m


def validar(conj):
    grupos=addon.portas._portas_do_conjunto(conj)
    folhas=[f for g in grupos for f in addon.portas._folhas_portas(g)]
    if not folhas:raise AssertionError('Modulo sem porta funcional: '+conj.name)
    sem_puxador=[f.name for f in folhas if not any(addon.chapas.MARCA_PUXADOR in o for o in f.children)]
    if sem_puxador:raise AssertionError('Folhas sem puxador: '+repr(sem_puxador))
    for g in grupos:
        for f in addon.portas._folhas_portas(g):
            if f.get('porta_curva_modelada'):
                pontos=[f.matrix_world@v.co for v in f.data.vertices]
                addon.portas._reaplicar_portas(bpy.context,g,dict(g['porta_parametros']))
                bpy.context.view_layer.update()
                if max((f.matrix_world@v.co-p).length for v,p in zip(f.data.vertices,pontos))>.00001:
                    raise AssertionError('Reaplicar achatou a porta curva')
            fechada=f.matrix_world.copy()
            addon.ferragens._definir_abertura(bpy.context,f,.5)
            bpy.context.view_layer.update()
            if (f.matrix_world.translation-fechada.translation).length<.001:raise AssertionError('Folha nao abre')
            addon.ferragens._definir_abertura(bpy.context,f,0)
            bpy.context.view_layer.update()
            if max(abs(a-b) for r,s in zip(fechada,f.matrix_world) for a,b in zip(r,s))>1e-5:raise AssertionError('Folha nao fecha')
    corpos=[o for o in addon.modulos.fundos_do_modulo(conj) if 'fundo_margens_mm' in o]
    antes={o.name:[o.matrix_world@v.co for v in o.data.vertices] for o in corpos}
    addon.modulos.ajustar_fundo(conj);bpy.context.view_layer.update()
    for o in corpos:
        if max(((o.matrix_world@v.co)-p).length for v,p in zip(o.data.vertices,antes[o.name]))>.00001:
            raise AssertionError('Fundo mudou ao recalcular: '+o.name)
    madeiras=addon.modulos._chapas_do_conjunto(conj)+folhas
    placas=[o for o in conj.children_recursive if o.type=='MESH' and
            (o.get(addon.ferragens.CHAVE_FERRAGEM)=='DOBRADICA' or o.name.startswith('Dobradica Suporte')
             or o.name.startswith('Dobradica Base')) and
            not any(t in o.name for t in ('Braco','Eixo','No ','Parafuso'))]
    contatos=[]
    for obj in placas:
        distancias=[]
        for apoio in madeiras:
            inv=apoio.matrix_world.inverted()
            for v in obj.data.vertices:
                pt=obj.matrix_world@v.co
                hit,co,_n,_face=apoio.closest_point_on_mesh(inv@pt)
                if hit:distancias.append((apoio.matrix_world@co-pt).length*1000)
        menor=min(distancias,default=1e9)
        if menor>.05:raise AssertionError('Dobradica sem contato: '+obj.name+' '+str(menor))
        contatos.append(menor)
    return dict(portas=len(folhas),fundos=len(addon.modulos.fundos_do_modulo(conj)),
                puxadores=sum(addon.chapas.MARCA_PUXADOR in o for f in folhas for o in f.children),
                curvas=sum(bool(f.get('porta_curva_modelada')) for f in folhas),
                apoios=len(contatos),erro_contato_max_mm=max(contatos,default=0))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--destino',required=True);p.add_argument('--aplicar',action='store_true')
    p.add_argument('--biblioteca',default=os.path.join(RAIZ,'archy_builder','biblioteca'))
    p.add_argument('--fonte',help='Source corner-category DXF file; required for preparation')
    a=p.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    if not a.aplicar and not a.fonte:
        p.error('--fonte is required for preparation; provide the source DXF file')
    validar_destino(a.biblioteca, a.destino)
    if a.aplicar:
        m=json.load(open(os.path.join(a.destino,'manifesto.json'),encoding='utf-8'))
        if digital(os.path.join(a.biblioteca,'indice.json'))!=m['indice']:raise RuntimeError('Indice mudou')
        for path,sha in m['fontes'].items():
            if digital(path)!=sha:raise RuntimeError('DXF mudou')
        publicar(a.destino)
    else:preparar(a.biblioteca,a.fonte,a.destino)


if __name__=='__main__':main()
