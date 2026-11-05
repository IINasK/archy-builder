"""Integrate DXF library categories with resumable staging and backups.

Prepare outside the library; --apply validates hashes and publishes with rollback.

Supply --source DIRECTORY explicitly for preparation.
--apply uses the source paths recorded in the existing manifest.
"""
from pathlib import Path
import argparse,json,os,re,shutil,sys
import bpy
RAIZ=str(Path(__file__).resolve().parents[2])
sys.path.insert(0,RAIZ)
from tools.migrations.adjust_fits import addon,carregar,limpar,digital,caminho_da_peca
from tools.migrations.adjust_fits import validar_destino


def ler(path):
    with open(path,encoding='utf-8') as f:return json.load(f)


def gravar(path,dados):
    with open(path+'.tmp','w',encoding='utf-8') as f:json.dump(dados,f,indent=1,ensure_ascii=False)
    os.replace(path+'.tmp',path)


def origem(o):
    n=o.get('porta_origem_promob') or o.name
    m=re.match(r'Peca LAYER\d+',n)
    return m.group() if m else ''


def preparar(biblioteca,fonte,destino):
    validar_destino(biblioteca, destino)
    novos,originais=[os.path.join(destino,n) for n in ('novos','originais')]
    status=os.path.join(destino,'progresso.json')
    if not os.path.exists(status):
        os.makedirs(destino,exist_ok=False)
        for p in (novos,originais):shutil.copytree(biblioteca,p,ignore=shutil.ignore_patterns('__pycache__'))
        gravar(status,dict(concluidos=[],categorias=[],fontes={}))
    progresso=ler(status)
    addon.opcoes._pasta_addon=lambda:novos
    addon.biblioteca.pasta_biblioteca=lambda:novos
    addon.register()
    for pasta,_,arqs in sorted(os.walk(fonte)):
        for nome in sorted(arqs):
            if not nome.lower().endswith('.dxf'):continue
            path=os.path.join(pasta,nome);rel=os.path.relpath(path,fonte)
            if rel in progresso['concluidos']:continue
            niveis,prefixo=addon.importacao.destino_categoria_promob(path,fonte)
            indice=ler(os.path.join(novos,'indice.json'))
            existentes=[it for it in indice if addon.biblioteca.caminho_de(it)==niveis]
            antigos=[it for it in ler(os.path.join(originais,'indice.json')) if addon.biblioteca.caminho_de(it)==niveis]
            revisar=bool(antigos) and niveis[-1] in ("Corners","Bifold Corners")
            if antigos and not revisar:continue
            progresso['fontes'][path]=digital(path)
            metadados=[]
            for it in antigos:
                cs,objs=carregar(os.path.join(originais,it['arquivo']))
                slots={origem(o):dict(uid=o.get('chapa_uid'),
                    slots=[(s.link,s.material.name if s.material else None) for s in o.material_slots])
                    for o in objs if o.type=='MESH' and origem(o)}
                metadados.append(dict(item=it,slots=slots,nomes=set(slots)))
            limpar();bpy.context.view_layer.active_layer_collection=bpy.context.view_layer.layer_collection
            if niveis[-2]=="Doors":
                grupos,info=addon.importacao.importar_portas_avulsas(bpy.context,path,prefixo)
            else:
                grupos,info=addon.importacao.importar_dxf_promob(bpy.context,path,prefixo,na_origem=True)
            if not grupos:raise RuntimeError("Category has no model: "+rel)
            vinculos=[]
            for g in grupos:
                nomes={origem(o) for o in g.children_recursive if origem(o)}
                melhor=max(metadados,key=lambda m:len(nomes&m['nomes']),default=None)
                vinculos.append(melhor if melhor and nomes&melhor['nomes'] else None)
            gravar(os.path.join(novos,'indice.json'),[it for it in indice if it not in existentes])
            for it in existentes:
                for n in (it['arquivo'],os.path.splitext(it['arquivo'])[0]+'.png'):
                    p=os.path.join(novos,n)
                    if os.path.isfile(p):os.remove(p)
            for g,meta in zip(grupos,vinculos):
                if meta:
                    it=meta['item'];nome_modulo=it['nome']
                    vezes=sum(m is meta for m in vinculos)
                    if vezes>1:
                        pos=[j for j,m in enumerate(vinculos) if m is meta].index(grupos.index(g))
                        nome_modulo=re.sub(r'(\b\d{2})(?= )',lambda m:m.group()+chr(65+pos),nome_modulo,count=1)
                        nome_modulo=re.sub(r'\d+x\d+x\d+$','%dx%dx%d'%tuple(round(v) for v in
                            (g.conj_largura_mm,g.conj_altura_mm,g.conj_profundidade_mm)),nome_modulo)
                    addon.modulos.nomear_grupo(g,nome_modulo)
                    mats_nomes={n for d in meta['slots'].values() for _,n in d['slots'] if n}
                    with bpy.data.libraries.load(os.path.join(originais,it['arquivo'])) as (de,para):
                        pedidos=[n for n in de.materials if n in mats_nomes];para.materials=pedidos
                    mats=dict(zip(pedidos,para.materials))
                    for obj in g.children_recursive:
                        d=meta['slots'].get(origem(obj))
                        if not d or obj.type!='MESH':continue
                        if d['uid']:obj['chapa_uid']=d['uid']
                        if d['slots']:
                            obj.data.materials.clear()
                            for link,n in d['slots']:
                                obj.data.materials.append(mats.get(n));obj.material_slots[-1].link=link
                                obj.material_slots[-1].material=mats.get(n)
                alvo=os.path.basename(addon.biblioteca._nome_arquivo_seguro(g.name))+'.blend'
                if os.path.isfile(os.path.join(novos,alvo)):
                    raise RuntimeError("Name conflicts with another category: "+g.name)
                addon.biblioteca.gravar_modulo_na_biblioteca(bpy.context,g,g.name,niveis)
            progresso['concluidos'].append(rel)
            progresso['categorias'].append(dict(fonte=rel,niveis=niveis,antes=len(antigos),depois=len(grupos),info=info))
            gravar(status,progresso)
            print("[integration]",rel,'ANTES',len(antigos),'AGORA',len(grupos),flush=True)
            limpar()
    limpar();addon.unregister()
    arquivos=[]
    nomes=set(os.listdir(originais))|set(os.listdir(novos))
    for n in sorted(nomes):
        a,b=os.path.join(originais,n),os.path.join(novos,n)
        if os.path.isdir(a) or os.path.isdir(b):continue
        antes=digital(a) if os.path.isfile(a) else None
        depois=digital(b) if os.path.isfile(b) else None
        if antes!=depois:arquivos.append(dict(nome=n,original=antes,novo=depois))
    gravar(os.path.join(destino,'manifesto.json'),dict(biblioteca=biblioteca,arquivos=arquivos,
        fontes=progresso['fontes'],categorias=progresso['categorias'],publicado=False))
    print('PREPARADOS',len(arquivos),'ARQUIVOS',flush=True)


def publicar(destino):
    m=ler(os.path.join(destino,'manifesto.json'))
    validar_destino(m['biblioteca'],destino)
    for p,sha in m['fontes'].items():
        if digital(p)!=sha:raise RuntimeError("DXF changed: "+p)
    for d in m['arquivos']:
        for pasta,chave in ((m['biblioteca'],'original'),(os.path.join(destino,'originais'),'original'),
                            (os.path.join(destino,'novos'),'novo')):
            p=caminho_da_peca(pasta,d['nome']);sha=digital(p) if os.path.isfile(p) else None
            if sha!=d[chave]:raise RuntimeError("File changed: "+p)
    aplicados=[];alvo=None
    try:
        for d in sorted(m['arquivos'],key=lambda d:d['nome'].endswith(('.json','.txt'))):
            alvo=caminho_da_peca(m['biblioteca'],d['nome'])
            if d['novo'] is None:os.remove(alvo)
            else:
                shutil.copyfile(os.path.join(destino,'novos',d['nome']),alvo+'.integracao')
                os.replace(alvo+'.integracao',alvo)
            aplicados.append(d)
    except Exception:
        # The failed file's temporary copy must not remain in the real library.
        if alvo and os.path.exists(alvo+'.integracao'):os.remove(alvo+'.integracao')
        for d in aplicados:
            alvo=caminho_da_peca(m['biblioteca'],d['nome'])
            if d['original'] is None:os.remove(alvo)
            else:shutil.copy2(os.path.join(destino,'originais',d['nome']),alvo)
        raise
    m['publicado']=True;gravar(os.path.join(destino,'manifesto.json'),m)
    print('PUBLICADOS',len(aplicados),"FILES; BACKUP",destino,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--destination', required=True, dest='destino', metavar='DESTINATION');p.add_argument('--apply', action='store_true', dest='aplicar')
    p.add_argument('--library', default=os.path.join(RAIZ, 'archy_builder', "assets/library"), dest='biblioteca', metavar='LIBRARY')
    p.add_argument('--source', help='Source DXF directory; required for preparation', dest='fonte', metavar='SOURCE')
    a=p.parse_args(sys.argv[sys.argv.index('--')+1:])
    if not a.aplicar and not a.fonte:
        p.error('--source is required for preparation; provide the source DXF directory')
    validar_destino(a.biblioteca, a.destino)
    if a.aplicar:publicar(a.destino)
    else:preparar(a.biblioteca,a.fonte,a.destino)
