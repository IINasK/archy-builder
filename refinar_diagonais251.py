"""Repara frentes diagonais com backup, releitura e publicacao atomica.

Blender --background --factory-startup --python este_arquivo --
  --destino PASTA [--aplicar]
"""
import argparse,json,os,shutil,sys
import bpy
from mathutils import Vector
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from ajustar_encaixes_promob import addon,carregar,limpar,estado,conferir,digital,publicar
from ajustar_encaixes_promob import validar_destino


def validar(conj):
    grupos=addon.portas._portas_do_conjunto(conj)
    registros=[]
    for g in grupos:
        if not g.get('porta_perfil_corpo'):
            raise AssertionError('Perfil nao integrado: '+conj.name)
        folha,=addon.portas._folhas_portas(g)
        antes=[addon.ferragens._matriz_fechada(folha)@v.co for v in folha.data.vertices]
        addon.portas._reaplicar_portas(bpy.context,g,addon.portas._copiar_parametros(g['porta_parametros']))
        bpy.context.view_layer.update()
        atuais=[addon.ferragens._matriz_fechada(folha)@v.co for v in folha.data.vertices]
        erro=max(min((p-v).length for v in atuais) for p in antes)
        if erro>.00005:raise AssertionError('Reaplicar mudou o perfil: '+conj.name+' '+str(erro))
        for abertura in (.5,0):
            addon.ferragens._definir_abertura(bpy.context,folha,abertura)
            bpy.context.view_layer.update()
        bases=[o for o in g.children if o.type=='MESH' and o.get('porta_ferragem_apoio')]
        if not bases:raise AssertionError('Sem apoio real: '+conj.name)
        contatos=[]
        for base in bases:
            apoio=base['porta_ferragem_apoio'];inv=apoio.matrix_world.inverted()
            dist=[]
            for v in base.data.vertices:
                pt=base.matrix_world@v.co
                hit,co,_n,_i=apoio.closest_point_on_mesh(inv@pt)
                if hit:dist.append((apoio.matrix_world@co-pt).length*1000)
            if min(dist,default=999)>.05:raise AssertionError('Base sem contato: '+conj.name)
            contatos.append(min(dist))
        for pux in folha.children:
            if pux.get('puxador_tipo')!='ALCA':continue
            pt=pux.matrix_basis.translation
            hit,co,no,_i=folha.closest_point_on_mesh(pt)
            if not hit or (co-pt).length>.0001 or no.dot(pux.matrix_basis.to_3x3().col[2])<.99:
                raise AssertionError('Puxador fora da face: '+conj.name)
        registros.append(dict(curva=bool(folha.get('porta_curva_modelada')),bases=len(bases),
            contato_max_mm=max(contatos),vertices=len(folha.data.vertices),lado=g['porta_parametros']['dobradica_lado']))
    return registros


def preparar(biblioteca,destino):
    validar_destino(biblioteca, destino)
    novos,originais=[os.path.join(destino,n) for n in ('novos','originais')]
    for p in (novos,originais):os.makedirs(p,exist_ok=True)
    indice=os.path.join(biblioteca,'indice.json');manifesto=os.path.join(destino,'manifesto.json')
    m=json.load(open(manifesto,encoding='utf-8')) if os.path.exists(manifesto) else dict(
        biblioteca=biblioteca,indice=digital(indice),versao=addon.bl_info['version'],
        publicado=False,arquivos=[],modulos=[],auditados=[])
    if m['publicado'] or m['indice']!=digital(indice):raise RuntimeError('Preparo/indice mudou')
    addon.opcoes._pasta_addon=lambda:novos;addon.biblioteca.pasta_biblioteca=lambda:novos
    addon.register()
    itens=[it for it in json.load(open(indice,encoding='utf-8')) if 'Diagonais' in addon.biblioteca.caminho_de(it)]
    for it in itens:
        nome=it['arquivo']
        if nome in m['auditados']:continue
        fonte=os.path.join(biblioteca,nome);sha=digital(fonte)
        cs,objs=carregar(fonte)
        conj=next(o for o in objs if addon.chapas.MARCA_CONJUNTO in o)
        corpo=addon.modulos._chapas_do_conjunto(conj)
        antes_corpo=estado([],corpo)
        portas_antes=len(addon.portas._portas_do_conjunto(conj))
        grupos=addon.promob.integrar_frentes_diagonais(conj)
        if not grupos:
            print('[diagonais251] sem frente funcional:',nome,flush=True)
            m['auditados'].append(nome)
            continue
        conferir(antes_corpo,estado([],corpo))
        auditoria=validar(conj)
        for f in [o for g in grupos for o in addon.portas._folhas_portas(g)]:
            addon.ferragens._definir_abertura(bpy.context,f,0)
        addon.ferragens.ocultar_pecas_do_rig();bpy.context.view_layer.update()
        pngnome=os.path.splitext(nome)[0]+'.png'
        for n in (nome,pngnome):shutil.copy2(os.path.join(biblioteca,n),os.path.join(originais,n))
        blend=os.path.join(novos,nome);png=os.path.join(novos,pngnome)
        objetos=list(bpy.data.objects);colecoes=list(bpy.data.collections)
        bpy.data.libraries.write(blend,set(colecoes)|set(objetos),fake_user=True,compress=True)
        esperado=estado(colecoes,objetos)
        ok,msg=addon.biblioteca.fotografar_com_camera(png,objetos)
        if not ok:raise RuntimeError(msg)
        limpar();ok,msg=addon.biblioteca.aplicar_preview_png(blend,png)
        if not ok:raise RuntimeError(msg)
        cs,objs=carregar(blend);conferir(esperado,estado(cs,objs))
        conj=next(o for o in objs if addon.chapas.MARCA_CONJUNTO in o)
        validar(conj)
        for n in (nome,pngnome):
            original=digital(os.path.join(originais,n))
            if digital(os.path.join(biblioteca,n))!=original:raise RuntimeError('Original mudou: '+n)
            m['arquivos'].append(dict(nome=n,original=original,novo=digital(os.path.join(novos,n))))
        m['auditados'].append(nome)
        m['modulos'].append(dict(arquivo=nome,portas_antes=portas_antes,auditoria=auditoria))
        json.dump(m,open(manifesto,'w',encoding='utf-8'),indent=1,ensure_ascii=True)
        print('[diagonais251]',len(m['auditados']),'/',len(itens),nome,auditoria,flush=True)
    limpar();addon.unregister()
    json.dump(m,open(manifesto,'w',encoding='utf-8'),indent=1,ensure_ascii=True)


def main():
    p=argparse.ArgumentParser();p.add_argument('--destino',required=True);p.add_argument('--aplicar',action='store_true')
    p.add_argument('--biblioteca',default=os.path.join(os.path.dirname(__file__),'cabinet_creator','biblioteca'))
    a=p.parse_args(sys.argv[sys.argv.index('--')+1:])
    validar_destino(a.biblioteca, a.destino)
    if a.aplicar:
        m=json.load(open(os.path.join(a.destino,'manifesto.json'),encoding='utf-8'))
        if m['indice']!=digital(os.path.join(a.biblioteca,'indice.json')):raise RuntimeError('Indice mudou')
        publicar(a.destino)
    else:preparar(a.biblioteca,a.destino)


if __name__=='__main__':main()
