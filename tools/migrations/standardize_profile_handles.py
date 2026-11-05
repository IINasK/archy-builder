"""Stage standard profile handles across library cabinets.

Keeps the existing handle edge; uses the import placement rule for missing
handles. Profiles are horizontal except on wardrobes; modeled curved leaves
receive front references before rebuilding. Prepare externally before --aplicar."""
from pathlib import Path
import argparse,json,os,shutil,sys
import bpy
RAIZ=str(Path(__file__).resolve().parents[2]);sys.path.insert(0,RAIZ)
from tools.migrations.adjust_fits import addon,carregar,limpar,estado,conferir,digital,publicar
from tools.migrations.adjust_fits import validar_destino
from tools.migrations.audit_and_repair_integration import verificar_funcoes


def _perfis(chapa):
    return [c for c in chapa.children if addon.chapas.MARCA_PUXADOR in c and c.get('puxador_tipo')=='PERFIL']


def _grupos(objs):
    # pelo arquivo, nao pelo modulo: as Portas da biblioteca sao soltas
    return ([o for o in objs if addon.chapas.MARCA_PORTAS in o],
            [o for o in objs if addon.gavetas.MARCA_GRUPO in o])


def padronizar(context,objs,posicao):
    """Devolve (alteracoes, nomes tocados)."""
    P,G,X=addon.puxadores,addon.gavetas,addon.portas
    feitos,tocados=[],set()
    for pux in [o for o in objs if addon.chapas.MARCA_PUXADOR in o and o.get('puxador_tipo')!='PERFIL']:
        feitos.append('troca %s %s'%(pux.parent.name,pux['puxador_tipo']))
        tocados.add(pux.name)
        P._trocar_modelo_puxador(pux,'PERFIL')
        tocados|={pux.name,pux.parent.name}     # de novo: a troca renomeia o puxador
    portas,gavetas=_grupos(objs)
    for g in portas:
        folhas=X._folhas_portas(g)
        zigzag=g['porta_parametros'].get('abertura')=='ZIGZAG'
        if posicao!='LADO' and not zigzag and any(
                p.get('puxador_borda','').startswith('X') for f in folhas for p in _perfis(f)):
            for f in folhas:
                for p in _perfis(f):
                    tocados|={p.name,f.name};G._remover(p)
                P._atualizar_madeira(f)
            feitos.append('horizontal %s'%g.name)
        sem=[f for f in folhas if not _perfis(f)]
        if not sem or (zigzag and len(sem)<len(folhas)):
            continue            # zigzag: puxador SO' na ultima folha
        antes={f.name for f in folhas}-{f.name for f in sem}
        for f in folhas:
            if ((f.get('porta_linha_frente') or f.get('porta_curva_modelada'))
                    and addon.frentes.referencia(f) is None):
                # sem a referencia o perfil horizontal ficava na corda do arco
                addon.frentes.preparar(f,forcar=True);tocados.add(f.name)
        for pux in P.perfis_na_porta(context,g,posicao):
            f=pux.parent
            if f.name in antes and len(_perfis(f))>1:
                G._remover(pux);P._atualizar_madeira(f)     # ja' tinha o seu
                continue
            tocados|={pux.name,f.name};feitos.append('perfil %s'%f.name)
    for grupo in gavetas:
        for d in G.gavetas_do_grupo(grupo):
            if d.get(G.CHAVE_PUXADOR)=='PERFIL':continue
            frente=G.frente_da_gaveta(d)
            tocados|={d.name,frente.name}|{c.name for c in frente.children}
            G.colocar_puxador(d,'PERFIL');feitos.append('gaveta %s'%d.name)
            tocados|={c.name for c in frente.children}
    # Como os perfis que ja' estavam na biblioteca: sem o material do modelo
    # (4 texturas embutidas, ~1 MB por preset); a cena o poe ao refazer.
    for nome in tocados:
        o=bpy.data.objects.get(nome)
        if o is not None and o.get('puxador_tipo')=='PERFIL':o.data.materials.clear()
    return feitos,tocados


def verificar(objs,posicao):
    X,G=addon.portas,addon.gavetas
    for pux in objs:
        if addon.chapas.MARCA_PUXADOR in pux:
            assert pux.get('puxador_tipo')=='PERFIL',pux.name
    portas,gavetas=_grupos(objs)
    assert portas or gavetas or not any(addon.chapas.MARCA_PUXADOR in o for o in objs)
    for g in portas:
        folhas=X._folhas_portas(g)
        alvo=folhas[-1:] if g['porta_parametros'].get('abertura')=='ZIGZAG' else folhas
        for f in alvo:
            assert _perfis(f),'folha sem perfil: '+f.name
            if posicao!='LADO' and len(alvo)==len(folhas):
                assert all(p['puxador_borda'].startswith('Y') for p in _perfis(f)),'perfil vertical: '+f.name
    for grupo in gavetas:
        for d in G.gavetas_do_grupo(grupo):
            assert d.get(G.CHAVE_PUXADOR)=='PERFIL' and _perfis(G.frente_da_gaveta(d)),d.name


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
        posicao=addon.importacao.posicao_do_perfil(it.get('n3',''))
        feitos,tocados=padronizar(bpy.context,objs,posicao)
        m['verificados']+=1
        if not feitos:
            verificar(objs,posicao);continue
        bpy.context.view_layer.update()
        depois=estado(list(bpy.data.collections),list(bpy.data.objects))
        # fora as pecas dos puxadores, nada muda; folha/frente conserva medida e material
        for nome,dados in antes['objetos'].items():
            if nome not in tocados:conferir(dados,depois['objetos'][nome],nome)
            elif dados['medidas'] is not None and nome in depois['objetos']:
                for chave in ('medidas','materiais','matriz'):conferir(dados[chave],depois['objetos'][nome][chave],nome+'/'+chave)
        conferir(antes['assets'],depois['assets'])
        objs=list(bpy.data.objects);verificar(objs,posicao)
        for s in nomes:shutil.copy2(os.path.join(biblioteca,s),os.path.join(originais,s))
        blend,png=[os.path.join(novos,s) for s in nomes]
        bpy.data.libraries.write(blend,set(bpy.data.collections)|set(bpy.data.objects),fake_user=True,compress=True)
        salvar=estado(list(bpy.data.collections),list(bpy.data.objects))
        for g in _grupos(objs)[0]:     # foto FECHADA, como `preparar_abertura_foto`
            for f in addon.portas._folhas_portas(g):
                addon.ferragens._definir_abertura(bpy.context,f,addon.biblioteca.ABERTURA_FOTO)
        bpy.context.view_layer.update()
        ok,msg=addon.biblioteca.fotografar_com_camera(png,list(bpy.data.objects))
        if not ok:raise RuntimeError(msg)
        limpar();ok,msg=addon.biblioteca.aplicar_preview_png(blend,png)
        if not ok:raise RuntimeError(msg)
        cs,objs=carregar(blend);conferir(salvar,estado(cs,objs))
        verificar(objs,posicao)
        # lista antes: editar as gavetas refaz objetos e `objs` envelhece
        for conj in [o for o in objs if addon.chapas.MARCA_CONJUNTO in o]:verificar_funcoes(conj)
        for s in nomes:
            assert digital(os.path.join(biblioteca,s))==hashes[s]
            m['arquivos'].append(dict(nome=s,original=hashes[s],novo=digital(os.path.join(novos,s))))
        m['modulos'].append(dict(arquivo=it['arquivo'],posicao=posicao,alteracoes=feitos))
        print('[perfil]',it['arquivo'],posicao,len(feitos),flush=True)
    limpar();addon.unregister()
    json.dump(m,open(os.path.join(destino,'manifesto.json'),'w',encoding='utf-8'),indent=1)
    print('VERIFICADOS',m['verificados'],'ALTERADOS',len(m['modulos']),flush=True)


def main():
    p=argparse.ArgumentParser();p.add_argument('--destino',required=True)
    p.add_argument('--biblioteca',default=os.path.join(RAIZ,'cabinet_creator','biblioteca'));p.add_argument('--aplicar',action='store_true')
    a=p.parse_args(sys.argv[sys.argv.index('--')+1:])
    validar_destino(a.biblioteca,a.destino)
    if a.aplicar:
        m=json.load(open(os.path.join(a.destino,'manifesto.json'),encoding='utf-8'))
        if m['indice']!=digital(os.path.join(a.biblioteca,'indice.json')):
            raise RuntimeError('Indice da biblioteca mudou desde o preparo')
        publicar(a.destino)
    else:preparar(a.biblioteca,a.destino)


if __name__=='__main__':main()
