"""Tira as fotos dos modelos de FABRICA (carrosseis da gaveta).

    blender --factory-startup --python gerar_fotos_padrao.py

ABRE O BLENDER (a foto e' o render OpenGL de uma viewport: em
--background nao ha' viewport) e fecha sozinho. Grava em
`cabinet_creator/fotos/` um PNG por modelo -- puxador_<tipo>,
abertura_<tipo>, dobradica_<tipo> --, cada cena montada pelo proprio
add-on e fotografada na mesma vista a 45 graus das fotos da biblioteca
(`VISTA_FOTO`). Rode de novo quando um modelo de fabrica mudar.
"""
import os
import sys
import traceback

import bpy
from mathutils import Vector

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import cabinet_creator as addon  # noqa: E402

PASTA = os.path.join(AQUI, 'cabinet_creator', 'fotos')
LADO_PNG = 256                   # a gaveta desenha ate' ~84 px
# Cores no modo solido (cor do OBJETO): madeira, porta e metal separados
COR_MODULO = (0.78, 0.62, 0.43, 1.0)
COR_PORTA = (0.93, 0.93, 0.91, 1.0)
COR_METAL = (0.30, 0.30, 0.33, 1.0)
# sozinha, a dobradica aparece sobre o fundo ESCURO da gaveta: mais clara
COR_DOBRADICA = (0.66, 0.66, 0.70, 1.0)


def limpar():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)


def colorir(objs, cor):
    for obj in objs:
        obj.color = cor


def modulo(largura=None, altura=None):
    bpy.ops.object.cabinet_criar_nicho()
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.cabinet_agrupar()
    conj = next(o for o in bpy.data.objects if addon.chapas.MARCA_CONJUNTO in o)
    if largura:
        conj.conj_largura_mm = largura
    if altura:
        conj.conj_altura_mm = altura
    bpy.context.view_layer.update()
    return conj


def porta(conj, **opcoes):
    """A mesma porta do snapshot: o vao inteiro do nicho, por EXEC."""
    L, A = conj.conj_largura_mm, conj.conj_altura_mm
    P, E = conj.conj_profundidade_mm, conj.conj_espessura_mm
    a = conj.matrix_world @ (Vector((-L / 2 + E, -P / 2, E)) / 1000.0)
    b = conj.matrix_world @ (Vector((L / 2 - E, -P / 2, A - E)) / 1000.0)
    parametros = dict(frente='NEG_Y', dobradica='RETA', folhas=1)
    parametros.update(opcoes)
    bpy.ops.object.cabinet_portas(
        'EXEC_DEFAULT', capturado=True, ponto_a=a, ponto_b=b,
        referencia=tuple(v for linha in
                         conj.matrix_world.to_quaternion().to_matrix()
                         for v in linha),
        pai_nome=conj.name, modulo_nome=conj.name, **parametros)
    return addon.portas._portas_do_conjunto(conj)[0]


def cena_puxador(tipo):
    # um pedaco de porta em pe' (face +Z local virada para a frente) com
    # o puxador na borda de cima
    chapa = addon.chapas.nova_chapa('Porta', 260.0, 170.0, 18.0, (0, 0, 0),
                                    (90, 0, 0), bpy.context)
    pux = addon.puxadores.criar_puxador(bpy.context, chapa, tipo, 'Y+', 1, 0.5)
    colorir([chapa], COR_PORTA)
    colorir([pux], COR_METAL)
    return [chapa, pux]


def cena_porta(abertura=None, dobradica='RETA', folhas=1, fracao=0.35,
               medidas=(None, None)):
    conj = modulo(*medidas)
    opcoes = dict(dobradica=dobradica, folhas=folhas)
    if abertura:
        opcoes['abertura'] = abertura
    grupo = porta(conj, **opcoes)
    folhas_ = addon.portas._folhas_portas(grupo)
    for folha in folhas_[:1]:
        addon.ferragens._definir_abertura(bpy.context, folha, fracao)
    colorir([o for o in bpy.data.objects if addon.chapas.MARCA_CHAPA in o], COR_MODULO)
    colorir(folhas_, COR_PORTA)
    colorir([o for o in bpy.data.objects if addon.ferragens.CHAVE_FERRAGEM in o
             or addon.chapas.MARCA_PUXADOR in o], COR_METAL)
    return [o for o in bpy.data.objects if o.type == 'MESH' and o.visible_get()]


def cena_dobradica():
    """So' a dobradica (pedido do usuario: isolada, sem o modulo), meio
    aberta: as pecas da primeira do rig da Reta."""
    conj = modulo(220.0, 180.0)
    grupo = porta(conj, dobradica='RETA', abertura='GIRO')
    for folha in addon.portas._folhas_portas(grupo):
        addon.ferragens._definir_abertura(bpy.context, folha, 0.5)
    F = addon.ferragens
    pecas = [o for o in bpy.data.objects if o.visible_get()
             and o.type in {'MESH', 'CURVE'} and F.CHAVE_FERRAGEM in o
             and str(o.get(F.CHAVE_ID_FERRAGEM, '')).split(':')[0].endswith('_0')]
    colorir(pecas, COR_DOBRADICA)
    return pecas


def reduzir(caminho):
    img = bpy.data.images.load(caminho, check_existing=False)
    try:
        img.scale(LADO_PNG, LADO_PNG)
        img.filepath_raw = caminho
        img.file_format = 'PNG'
        img.save()
    finally:
        bpy.data.images.remove(img)


CENAS = (
    [('puxador_' + t, lambda t=t: cena_puxador(t))
     for t in addon.puxadores.MODELOS_PADRAO]
    + [('abertura_GIRO', lambda: cena_porta('GIRO', fracao=0.3)),
       ('abertura_BASCULANTE', lambda: cena_porta('BASCULANTE', fracao=0.45)),
       ('abertura_CORRER', lambda: cena_porta('CORRER', 'RETA', 2, 0.0))]
    # Curva e Super Curva ainda nao tem modelo proprio: usam a foto da
    # Reta (`FOTOS_PENDENTES` em biblioteca.py)
    + [('dobradica_RETA', cena_dobradica)])


def fotografar():
    os.makedirs(PASTA, exist_ok=True)
    janela = bpy.context.window_manager.windows[0]
    erros = []
    with bpy.context.temp_override(window=janela, screen=janela.screen):
        for area in janela.screen.areas:
            if area.type == 'VIEW_3D':
                area.spaces.active.shading.type = 'SOLID'
                area.spaces.active.shading.color_type = 'OBJECT'
        for nome, montar in CENAS:
            try:
                limpar()
                objs = montar()
                bpy.context.view_layer.update()
                destino = os.path.join(PASTA, nome + '.png')
                ok, msg = addon.biblioteca.capturar_viewport(
                    destino, None, isolar=objs,
                    rotacao=addon.biblioteca.VISTA_FOTO)
                if not ok:
                    raise RuntimeError(msg)
                reduzir(destino)
                print('[fotos] ok', nome)
            except Exception:
                erros.append(nome)
                traceback.print_exc()
    print('[fotos] FIM', 'erros: %s' % erros if erros else 'tudo ok')


def rodar():
    try:
        fotografar()
    finally:
        bpy.ops.wm.quit_blender()
    return None


addon.register()
bpy.app.timers.register(rodar, first_interval=2.0)
