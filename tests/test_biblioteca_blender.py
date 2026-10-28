"""Execute: blender --background --factory-startup --python-exit-code 1 --python tests/test_biblioteca_blender.py

Suite "biblioteca": indice.json, catalogos, gravacao de presets e insercao.

SEGURANCA: a biblioteca real mora DENTRO do repositorio
(cabinet_creator/biblioteca). Nenhum teste escreve la': cada teste
trabalha numa COPIA em pasta temporaria, e `addon.biblioteca.pasta_biblioteca` e'
trocada antes mesmo do register() -- o timer que register() agenda
(registrar_bibliotecas) tambem cairia numa pasta descartavel. No fim,
a impressao digital da pasta real e' conferida; se mudou, a suite falha.
"""
import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest

import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cabinet_creator as addon

PASTA_REAL = os.path.normpath(addon.opcoes._pasta_addon())
ARQ_CATS = "blender_assets.cats.txt"

# Rede de seguranca GLOBAL: antes de qualquer register(), toda chamada a
# pasta_biblioteca()/_pasta_addon() cai numa pasta descartavel.
_PASTA_GUARDA = tempfile.mkdtemp(prefix="cabinet_bib_guarda_")
addon.biblioteca.pasta_biblioteca = lambda: _PASTA_GUARDA
addon.opcoes._pasta_addon = lambda: _PASTA_GUARDA
_CAPTURAR_ORIGINAL = addon.biblioteca.capturar_viewport


def impressao_digital(pasta):
    """Nome + sha1 de cada arquivo: muda se QUALQUER byte mudar."""
    saida = {}
    for raiz, dirs, arqs in os.walk(pasta):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for a in arqs:
            cam = os.path.join(raiz, a)
            with open(cam, "rb") as f:
                saida[os.path.relpath(cam, pasta)] = hashlib.sha1(
                    f.read()).hexdigest()
    return saida


DIGITAL_REAL = impressao_digital(PASTA_REAL)

# AMOSTRA da biblioteca real para os testes que gravam: ate' N presets por
# categoria (a biblioteca do Promob tem ~190 .blend e ~90 MB -- copiar
# tudo a cada teste e regerar todas as fotos estourava o limite da suite).
# A integridade de TODOS os presets reais e' conferida, so' lendo, em
# `TestPresetsDeFabrica` (a impressao digital no fim garante que nada mudou).
AMOSTRA_POR_CATEGORIA = 2


def copiar_amostra(destino, completa=True):
    """Copia a biblioteca real com ate' AMOSTRA_POR_CATEGORIA presets por
    categoria (n1/n2/n3) e o indice so' com eles; o resto (catalogos...)
    vai inteiro."""
    os.makedirs(destino)
    with open(os.path.join(PASTA_REAL, addon.biblioteca.NOME_INDICE), encoding="utf-8") as f:
        itens = json.load(f)
    contagem, escolhidos = {}, []
    for it in itens:
        if not completa and it['arquivo'] not in ('Nicho_600x400x300.blend',
                'Chapa_600x400x18.blend','Cube.blend','Cube_001.blend'):
            continue
        chave = addon.biblioteca.caminho_de(it)
        if contagem.get(chave, 0) < AMOSTRA_POR_CATEGORIA:
            contagem[chave] = contagem.get(chave, 0) + 1
            escolhidos.append(it)
    presets = {it["arquivo"] for it in itens}
    levar = {it["arquivo"] for it in escolhidos}
    for nome in os.listdir(PASTA_REAL):
        base, ext = os.path.splitext(nome)
        origem = os.path.join(PASTA_REAL, nome)
        if (os.path.isdir(origem) or ext == ".md"
                or nome == addon.biblioteca.NOME_INDICE):
            continue
        dono = base + ".blend"
        if ext in (".blend", ".png", ".blend1") and dono in presets and dono not in levar:
            continue
        shutil.copy2(origem, os.path.join(destino, nome))
    with open(os.path.join(destino, addon.biblioteca.NOME_INDICE), "w",
              encoding="utf-8", newline="\n") as f:
        json.dump(escolhidos, f, ensure_ascii=False, indent=1)
        f.write("\n")

# Presets gerados pelo proprio teste (ver criar_presets_de_teste)
NOME_CHAPA_T = "Chapa Teste"
CHAPA_T = "Chapa_Teste.blend"
NOME_NICHO_T = "Nicho Teste"
NICHO_T = "Nicho_Teste.blend"


def ler_cats(pasta):
    """{caminho: uuid} do blender_assets.cats.txt."""
    saida = {}
    with open(os.path.join(pasta, ARQ_CATS), encoding="utf-8") as f:
        for linha in f:
            linha = linha.strip()
            if not linha or linha.startswith(("#", "VERSION")):
                continue
            partes = linha.split(":")
            saida[partes[1]] = partes[0]
    return saida


def ler_blend(caminho):
    """Abre o .blend e devolve [(nome_no_arquivo, info)] dos assets.

    O nome vem de `de.objects` -- e' o nome GRAVADO, antes de o append
    renomear por colisao com a cena. Tudo que foi carregado e' removido.
    """
    antes_col = set(bpy.data.collections)
    antes_obj = set(bpy.data.objects)
    with bpy.data.libraries.load(caminho) as (de, para):
        nomes_col = list(de.collections)
        nomes_obj = list(de.objects)
        para.collections = list(de.collections)
        para.objects = list(de.objects)
    saida = []
    for nome, d in list(zip(nomes_col, para.collections)) + list(
            zip(nomes_obj, para.objects)):
        if d is None:
            continue
        info = {"tipo_id": type(d).__name__, "asset": d.asset_data is not None,
                "catalogo": d.asset_data.catalog_id if d.asset_data else "",
                "props": {k: d[k] for k in d.keys()},
                "vertices": (len(d.data.vertices) if getattr(d, "data", None)
                             is not None and hasattr(d.data, "vertices")
                             else 0),
                "preview": None}
        pv = d.preview
        if pv is not None:
            info["preview"] = (tuple(pv.image_size), tuple(pv.icon_size),
                               tuple(pv.image_pixels_float[0:4])
                               if pv.image_size[0] else ())
        saida.append((nome, info))
    # O lote evita recalcular vinculos para cada ID anexado; malhas ficam
    # para a mesma purga de orfaos que ja' ocorre na limpeza da cena.
    novos = ([c for c in bpy.data.collections if c not in antes_col]
             + [o for o in bpy.data.objects if o not in antes_obj])
    bpy.data.batch_remove(novos)
    return saida


def png_solido(caminho, cor, lado=8):
    """PNG RGBA de uma cor so', feito pelo proprio Blender."""
    img = bpy.data.images.new("tmp_png_teste", lado, lado, alpha=True)
    img.pixels = list(cor) * (lado * lado)
    img.filepath_raw = caminho
    img.file_format = 'PNG'
    img.save()
    bpy.data.images.remove(img)


def selecionar(*objs):
    for o in bpy.context.selected_objects:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
    if objs:
        bpy.context.view_layer.objects.active = objs[0]


def limpar_cena():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    padrao = bpy.context.scene.collection.children.get("Collection")
    for c in list(bpy.data.collections):
        if c is not padrao:
            bpy.data.collections.remove(c)
    try:
        bpy.data.orphans_purge(do_recursive=True)
    except Exception:
        pass
    if padrao is not None:
        bpy.context.view_layer.active_layer_collection = (
            bpy.context.view_layer.layer_collection.children[padrao.name])


class BaseBiblioteca(unittest.TestCase):
    """Cada teste ganha a sua copia da biblioteca real."""

    def setUp(self):
        limpar_cena()
        self.tmp = tempfile.mkdtemp(prefix="cabinet_bib_teste_")
        self.pasta = os.path.join(self.tmp, "biblioteca")
        # Testes de indice/operadores criam suas proprias montagens.
        # Copiar cem armarios em cada um multiplicava o I/O por 81;
        # a integracao real abaixo conserva a amostra de CADA categoria.
        copiar_amostra(self.pasta, completa=getattr(self,'AMOSTRA_COMPLETA',False))
        pasta = self.pasta
        addon.biblioteca.pasta_biblioteca = lambda: pasta
        addon.biblioteca.capturar_viewport = _CAPTURAR_ORIGINAL
        s = bpy.context.scene
        s.chapa_n1 = s.chapa_n2 = s.chapa_n3 = ""
        s.cursor.location = (0.0, 0.0, 0.0)

    def tearDown(self):
        addon.biblioteca.pasta_biblioteca = lambda: _PASTA_GUARDA
        addon.biblioteca.capturar_viewport = _CAPTURAR_ORIGINAL
        limpar_cena()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def indice(self):
        with open(os.path.join(self.pasta, addon.biblioteca.NOME_INDICE),
                  encoding="utf-8") as f:
            return json.load(f)

    def texto(self, nome):
        with open(os.path.join(self.pasta, nome), "rb") as f:
            return f.read()

    def chapa(self, nome="Placa", loc=(0, 0, 0)):
        return addon.chapas.nova_chapa(nome, 600.0, 400.0, 18.0, loc, (0, 0, 0),
                                bpy.context)

    def criar_presets_de_teste(self):
        """Grava CHAPA_T e NICHO_T na copia, pelo proprio add-on.

        Os .blend de fabrica foram gravados no formato do Blender 5.x e
        o 4.x nao os abre (ver TestPresetsDeFabrica); presets gerados
        aqui valem em qualquer versao. O nicho reproduz o de fabrica:
        4 chapas sob um Empty de conjunto, com adjacencia por UID.
        """
        dx, dy = 100.0, 50.0          # Empty fora da origem de proposito
        placa = self.chapa(NOME_CHAPA_T, (dx + 10, dy + 20, 30))
        addon.biblioteca.salvar_na_biblioteca([placa], NOME_CHAPA_T, False,
                                   niveis=("Chapas", "Avulsas", ""))
        addon.biblioteca.registrar_no_indice(self.pasta, NOME_CHAPA_T, CHAPA_T,
                                  "Chapas", "Avulsas", "", "objeto")
        C = bpy.context
        base = addon.chapas.nova_chapa("Base", 600, 400, 18, (dx, dy, 9),
                                (0, 0, 0), C)
        tampo = addon.chapas.nova_chapa("Tampo", 600, 400, 18, (dx, dy, 291),
                                 (0, 0, 0), C)
        esq = addon.chapas.nova_chapa("Lateral_Esq", 264, 400, 18,
                               (dx - 291, dy, 150), (0, 90, 0), C)
        dir_ = addon.chapas.nova_chapa("Lateral_Dir", 264, 400, 18,
                                (dx + 291, dy, 150), (0, 90, 0), C)
        C.view_layer.update()
        conj = addon.modulos.agrupar_chapas(C, [base, tampo, esq, dir_])
        conj.name = NOME_NICHO_T
        addon.biblioteca.salvar_na_biblioteca([conj, base, tampo, esq, dir_],
                                   NOME_NICHO_T, True,
                                   niveis=("Armarios", "Cozinha",
                                           "Inferiores"))
        addon.biblioteca.registrar_no_indice(self.pasta, NOME_NICHO_T, NICHO_T,
                                  "Armarios", "Cozinha", "Inferiores",
                                  "modulo")
        limpar_cena()


# ====================================================== INDICE
class TestIndice(BaseBiblioteca):
    def test_ler_indice_ausente_ou_corrompido_devolve_lista_vazia(self):
        vazia = os.path.join(self.tmp, "vazia")
        os.makedirs(vazia)
        self.assertEqual(addon.biblioteca._ler_indice(vazia), [])
        with open(os.path.join(vazia, addon.biblioteca.NOME_INDICE), "w") as f:
            f.write("{ isto nao e' json")
        # indice quebrado nao pode derrubar o painel
        self.assertEqual(addon.biblioteca._ler_indice(vazia), [])

    def test_indice_ilegivel_nao_e_regravado_com_um_item(self):
        # Ler "vazio" e gravar so' o novo apagava os outros presets.
        quebrada = os.path.join(self.tmp, "quebrada")
        os.makedirs(quebrada)
        arq = os.path.join(quebrada, addon.biblioteca.NOME_INDICE)
        with open(arq, "w") as f:
            f.write("[ pela metade")
        with self.assertRaises(ValueError):
            addon.biblioteca.registrar_no_indice(quebrada, "Novo", "Novo.blend",
                                                 "Armarios", "objeto")
        with open(arq) as f:
            self.assertEqual(f.read(), "[ pela metade")

    def test_biblioteca_sem_portas_curvas(self):
        # Pedido do usuario (333): os 21 presets com folha de porta CURVA
        # sairam de todas as bibliotecas (as diagonais de porta reta
        # chanfrada ficam). O codigo da curva segue nos testes de importacao.
        curvas = ('Diagonal_01_300x703x562', 'Diagonal_Sup_Baixo_02_300x356x369',
                  'Canto_08B_901x703x963', 'Canto_Sup_Medio_03_600x706x600',
                  'Diagonal_Quarto_Armario_01_350x2503x550', 'Bancada_Quarto_01_300x720x550',
                  'Bancada_Quarto_05_700x720x631', 'Canto_Quarto_Superior_02_666x506x685',
                  'Diagonal_03_306x703x550','Diagonal_06_306x703x550',
                  'Diagonal_Sup_Baixo_01_300x356x350','Diagonal_Sup_Baixo_06_300x356x350',
                  'Diagonal_Sup_Alto_03_300x1056x350','Diagonal_Sup_Alto_05_300x1056x350',
                  'Diagonal_Sup_Medio_03_300x706x350','Diagonal_Sup_Medio_06_300x706x350',
                  'Diagonal_Quarto_Armario_04_350x2503x550','Diagonal_Quarto_Armario_06_350x2503x550')
        # a biblioteca REAL, so' leitura (a de self.pasta e' uma amostra)
        arquivos = {i["arquivo"] for i in addon.biblioteca._ler_indice(PASTA_REAL)}
        for base in curvas:
            self.assertNotIn(base + ".blend", arquivos)
            for ext in ('.blend','.png'):
                self.assertFalse(os.path.exists(os.path.join(PASTA_REAL,base+ext)),base)
        # os de porta reta da mesma familia continuam
        for nome in ('Diagonal_04_367x703x559.blend','Diagonal_05_300x703x550.blend',
                     'Diagonal_Sup_Baixo_04_469x356x494.blend'):
            self.assertIn(nome, arquivos)

    def test_frentes_curvas_restantes_saem_mas_recepcoes_ficam(self):
        # Regra 341: curvas em chapas comuns e em gavetas tambem saem;
        # as recepcoes curvas foram mantidas por escolha do usuario.
        arquivos = {i['arquivo'] for i in addon.biblioteca._ler_indice(PASTA_REAL)}
        for base in ('Balcao_09_811x703x737', 'Balcao_15_817x703x614',
                     'Gaveteiro_01_400x703x600', 'Gaveteiro_03_400x703x550'):
            self.assertNotIn(base + '.blend', arquivos)
            for extensao in ('.blend', '.png'):
                self.assertFalse(os.path.exists(os.path.join(PASTA_REAL, base + extensao)))
        for base in ('Recepcao_Quarto_Escritorio_01_1690x1000x1553',
                     'Recepcao_Quarto_Escritorio_02_2900x1000x1776',
                     'Recepcao_Quarto_Escritorio_03_1692x1000x1553',
                     'Recepcao_Quarto_Escritorio_04_2898x1000x1669'):
            self.assertIn(base + '.blend', arquivos)
        self.assertIn('Diagonal_Sup_Baixo_04_469x356x494.blend', arquivos)

    def test_ler_indice_le_a_copia_da_biblioteca(self):
        itens = addon.biblioteca._ler_indice(self.pasta)
        arquivos = {i["arquivo"] for i in itens}
        self.assertIn("Nicho_600x400x300.blend", arquivos)
        self.assertIn("Chapa_600x400x18.blend", arquivos)
        for i in itens:
            # pasta/origem sao so' de memoria (biblioteca/CLAUDE.md)
            self.assertNotIn("pasta", i)
            self.assertNotIn("origem", i)

    def test_gravar_indice_formato_lf_utf8_indent1(self):
        nome = "Cozinha A" + chr(0xE7) + "o"     # fonte fica ASCII
        itens = [{"nome": nome, "arquivo": "x.blend", "n1": "Armarios",
                  "n2": "Cozinha", "n3": "", "tipo": "objeto"}]
        addon.biblioteca._gravar_indice(self.pasta, itens)
        bruto = self.texto(addon.biblioteca.NOME_INDICE)
        self.assertNotIn(b"\r\n", bruto)
        self.assertTrue(bruto.endswith(b"\n"))
        # ensure_ascii=False: o acento vai em UTF-8, nao escapado
        self.assertIn(nome.encode("utf-8"), bruto)
        self.assertNotIn(b"\\u00e7", bruto)
        self.assertIn(b'[\n {\n  "nome"', bruto)    # indent=1
        self.assertEqual(addon.biblioteca._ler_indice(self.pasta), itens)

    def test_indice_completo_acrescenta_pasta_e_origem_so_em_memoria(self):
        antes = self.texto(addon.biblioteca.NOME_INDICE)
        itens = addon.biblioteca.indice_completo()
        self.assertEqual(len(itens), len(self.indice()))
        for it in itens:
            self.assertEqual(it["pasta"], self.pasta)
            self.assertEqual(it["origem"], "biblioteca")
        self.assertEqual(self.texto(addon.biblioteca.NOME_INDICE), antes)

    def test_registrar_no_indice_acrescenta_e_substitui_pelo_basename(self):
        n_antes = len(self.indice())
        caminho = os.path.join(self.pasta, "Novo_Item.blend")
        addon.biblioteca.registrar_no_indice(self.pasta, "Novo Item", caminho,
                                  "Portas", "Abrir", "", "objeto")
        itens = self.indice()
        self.assertEqual(len(itens), n_antes + 1)
        novo = [i for i in itens if i["arquivo"] == "Novo_Item.blend"]
        self.assertEqual(len(novo), 1)
        self.assertEqual(novo[0], {"nome": "Novo Item",
                                   "arquivo": "Novo_Item.blend",
                                   "n1": "Portas", "n2": "Abrir", "n3": "",
                                   "tipo": "objeto"})
        # regravar o mesmo arquivo SUBSTITUI, nao duplica
        addon.biblioteca.registrar_no_indice(self.pasta, "Renomeado", caminho,
                                  "Chapas", "Avulsas", "", "modulo")
        itens = self.indice()
        self.assertEqual(len(itens), n_antes + 1)
        novo = [i for i in itens if i["arquivo"] == "Novo_Item.blend"][0]
        self.assertEqual((novo["nome"], novo["n1"], novo["tipo"]),
                         ("Renomeado", "Chapas", "modulo"))
        # os outros itens ficam intactos
        self.assertIn("Nicho_600x400x300.blend",
                      [i["arquivo"] for i in itens])

    def test_niveis_de_formato_novo(self):
        self.assertEqual(addon.biblioteca._niveis_de(
            {"n1": "Armarios", "n2": "Sala", "n3": "Cantos"}),
            ("Armarios", "Sala", "Cantos"))
        self.assertEqual(addon.biblioteca._niveis_de({"n1": "Chapas", "n2": "Avulsas"}),
                         ("Chapas", "Avulsas", ""))
        # n1 presente manda, mesmo com as chaves antigas sobrando
        self.assertEqual(addon.biblioteca._niveis_de(
            {"n1": "Portas", "n2": "Abrir", "n3": "",
             "categoria": "Cozinha", "subcategoria": "Torres"}),
            ("Portas", "Abrir", ""))

    def test_niveis_de_aceita_formato_legado(self):
        # INVARIANTE 12: categoria/subcategoria continua legivel
        self.assertEqual(addon.biblioteca._niveis_de(
            {"categoria": "Cozinha", "subcategoria": "Inferiores"}),
            ("Armarios", "Cozinha", "Inferiores"))
        for amb in addon.biblioteca.AMBIENTES:
            self.assertEqual(addon.biblioteca._niveis_de({"categoria": amb})[0:2],
                             ("Armarios", amb))
        self.assertEqual(addon.biblioteca._niveis_de(
            {"categoria": "Portas", "subcategoria": "Correr"}),
            ("Portas", "Correr", ""))
        self.assertEqual(addon.biblioteca._niveis_de({}), ("", "", ""))

    def test_item_legado_conta_na_arvore_e_vira_catalogo(self):
        itens = self.indice()
        itens.append({"nome": "Velho", "arquivo": "Velho.blend",
                      "categoria": "Quarto", "subcategoria": "Sapateiras",
                      "tipo": "objeto"})
        addon.biblioteca._gravar_indice(self.pasta, itens)
        self.assertIn("Sapateiras", addon.biblioteca._filhos_n3("Armarios", "Quarto"))
        self.assertEqual(addon.biblioteca._conta(addon.biblioteca.indice_completo(), "Armarios",
                                      "Quarto", "Sapateiras"), 1)
        self.assertIn("Cabinet Creator/Armarios/Quarto/Sapateiras",
                      addon.biblioteca.caminhos_catalogo())

    def test_achar_item_exige_pasta_e_arquivo(self):
        it = addon.biblioteca._achar_item(self.pasta, "Nicho_600x400x300.blend")
        self.assertIsNotNone(it)
        self.assertEqual(it["nome"], "Nicho 600x400x300")
        self.assertEqual(it["pasta"], self.pasta)
        self.assertIsNone(addon.biblioteca._achar_item(self.pasta, "nao_existe.blend"))
        self.assertIsNone(addon.biblioteca._achar_item(self.tmp,
                                            "Nicho_600x400x300.blend"))

    def test_atualizar_item_mescla_so_no_item_certo(self):
        antes = {i["arquivo"]: dict(i) for i in self.indice()}
        addon.biblioteca._atualizar_item(self.pasta, "Cube.blend",
                              {"bloqueado": True, "nome": "Cubo"})
        depois = {i["arquivo"]: i for i in self.indice()}
        self.assertEqual(depois["Cube.blend"]["nome"], "Cubo")
        self.assertTrue(depois["Cube.blend"]["bloqueado"])
        # o resto do item foi preservado
        self.assertEqual(depois["Cube.blend"]["n2"], antes["Cube.blend"]["n2"])
        for arq, it in antes.items():
            if arq != "Cube.blend":
                self.assertEqual(depois[arq], it)

    def test_item_bloqueado_e_por_item(self):
        self.assertFalse(addon.biblioteca.item_bloqueado({}))
        self.assertFalse(addon.biblioteca.item_bloqueado({"bloqueado": False}))
        self.assertTrue(addon.biblioteca.item_bloqueado({"bloqueado": True}))
        # nada e' bloqueado so' por estar na pasta da biblioteca
        for it in addon.biblioteca.indice_completo():
            self.assertEqual(addon.biblioteca.item_bloqueado(it),
                             bool(it.get("bloqueado", False)))


# ====================================================== CATALOGOS
class TestCatalogos(BaseBiblioteca):
    def test_catalogo_de_monta_o_caminho_mais_fundo(self):
        R = addon.biblioteca.CAT_RAIZ
        self.assertEqual(addon.biblioteca.catalogo_de("Armarios", "Sala", "Cantos"),
                         R + "/Armarios/Sala/Cantos")
        self.assertEqual(addon.biblioteca.catalogo_de("Chapas", "Avulsas", ""),
                         R + "/Chapas/Avulsas")
        self.assertEqual(addon.biblioteca.catalogo_de("Portas"), R + "/Portas")
        self.assertEqual(addon.biblioteca.catalogo_de("", "", ""), "")

    def test_caminhos_catalogo_cobre_a_arvore_em_cascata(self):
        cams = addon.biblioteca.caminhos_catalogo()
        self.assertEqual(cams[0], addon.biblioteca.CAT_RAIZ)
        self.assertEqual(len(cams), len(set(cams)))
        for n1, filhos in addon.biblioteca.ARVORE.items():
            self.assertIn(addon.biblioteca.catalogo_de(n1), cams)
            for n2, netos in filhos.items():
                self.assertIn(addon.biblioteca.catalogo_de(n1, n2), cams)
                for n3 in netos:
                    self.assertIn(addon.biblioteca.catalogo_de(n1, n2, n3), cams)
        for c in cams:
            self.assertTrue(c == addon.biblioteca.CAT_RAIZ
                            or c.startswith(addon.biblioteca.CAT_RAIZ + "/"), c)
        # os catalogos por TIPO sao so' fallback: nao entram na cascata
        self.assertNotIn(addon.biblioteca.CAT_MODULOS, cams)

    def test_caminhos_catalogo_inclui_categoria_nova_do_indice(self):
        addon.biblioteca.registrar_no_indice(self.pasta, "X", "X.blend", "Armarios",
                                  "Lavanderia", "Tanques", "objeto")
        cams = addon.biblioteca.caminhos_catalogo()
        self.assertIn("Cabinet Creator/Armarios/Lavanderia", cams)
        self.assertIn("Cabinet Creator/Armarios/Lavanderia/Tanques", cams)

    def test_migrar_raiz(self):
        R = addon.biblioteca.CAT_RAIZ
        for velha in addon.biblioteca.RAIZES_ANTIGAS:
            self.assertEqual(addon.biblioteca._migrar_raiz(velha), R)
            self.assertEqual(addon.biblioteca._migrar_raiz(velha + "/Chapas/Avulsas"),
                             R + "/Chapas/Avulsas")
            # prefixo sem a barra NAO e' a mesma raiz
            self.assertEqual(addon.biblioteca._migrar_raiz(velha + "X/a"), velha + "X/a")
        self.assertEqual(addon.biblioteca._migrar_raiz(R + "/Portas"), R + "/Portas")
        self.assertEqual(addon.biblioteca._migrar_raiz("Outra/Coisa"), "Outra/Coisa")

    def test_garantir_catalogos_e_idempotente_na_biblioteca_real(self):
        # o .cats.txt commitado e' GERADO por _garantir_catalogos: rodar
        # de novo sobre a copia nao pode mudar um byte nem um UUID
        antes = self.texto(ARQ_CATS)
        uuids = ler_cats(self.pasta)
        ids = addon.biblioteca._garantir_catalogos(self.pasta)
        self.assertEqual(self.texto(ARQ_CATS), antes)
        for cam, u in uuids.items():
            self.assertEqual(ids[cam], u)

    def test_catalogos_so_regravam_se_mudar_e_de_uma_vez(self):
        # REGRESSAO (2026-10-09): cada registro reabria o .cats.txt com "w";
        # dois Blenders juntos (harness em paralelo) liam o arquivo ja'
        # zerado e davam UUID NOVO a todos os catalogos da biblioteca.
        arq = os.path.join(self.pasta, ARQ_CATS)
        antes = os.path.getmtime(arq)
        addon.biblioteca._garantir_catalogos(self.pasta)
        self.assertEqual(os.path.getmtime(arq), antes)   # nada mudou
        texto = self.texto(ARQ_CATS).decode('utf-8')
        self.assertFalse(addon.biblioteca._gravar_se_mudou(arq, texto))
        self.assertTrue(addon.biblioteca._gravar_se_mudou(arq, texto + "\n"))
        self.assertTrue(addon.biblioteca._gravar_se_mudou(arq, texto))
        self.assertEqual(self.texto(ARQ_CATS).decode('utf-8'), texto)
        # sem sobra do temporario da troca atomica
        self.assertFalse([n for n in os.listdir(self.pasta)
                          if n.endswith('.tmp')])

    def test_garantir_catalogos_preserva_uuid_e_cria_faltantes(self):
        pasta = os.path.join(self.tmp, "nova")
        os.makedirs(pasta)
        u_sala = "11111111-1111-1111-1111-111111111111"
        with open(os.path.join(pasta, ARQ_CATS), "w", encoding="utf-8") as f:
            f.write("VERSION 1\n\n%s:Cabinet Creator/Armarios/Sala:x\n"
                    % u_sala)
        ids = addon.biblioteca._garantir_catalogos(pasta, extras=("Cabinet Creator/Extra",
                                                       ""))
        cats = ler_cats(pasta)
        self.assertEqual(cats["Cabinet Creator/Armarios/Sala"], u_sala)
        self.assertEqual(ids["Cabinet Creator/Armarios/Sala"], u_sala)
        self.assertIn("Cabinet Creator/Extra", cats)
        for cam in addon.biblioteca.caminhos_catalogo():
            self.assertIn(cam, cats)
        self.assertEqual(len(set(cats.values())), len(cats))
        bruto = open(os.path.join(pasta, ARQ_CATS), "rb").read()
        self.assertTrue(bruto.startswith(b"VERSION 1\n"))
        self.assertNotIn(b"\r\n", bruto)
        # nome simples = caminho com tracos
        self.assertIn(("%s:Cabinet Creator/Armarios/Sala:"
                       "Cabinet Creator-Armarios-Sala\n" % u_sala).encode(),
                      bruto)
        # segunda passada: nenhum UUID novo
        self.assertEqual(addon.biblioteca._garantir_catalogos(pasta), ids)

    def test_raiz_antiga_migra_com_o_uuid_intacto(self):
        # INVARIANTES 15/16: renomear o CAMINHO preserva o asset; trocar
        # o UUID o orfana
        pasta = os.path.join(self.tmp, "legada")
        os.makedirs(pasta)
        velha = addon.biblioteca.RAIZES_ANTIGAS[0]
        u_raiz = "aaaaaaaa-0000-0000-0000-000000000001"
        u_coz = "aaaaaaaa-0000-0000-0000-000000000002"
        u_custom = "aaaaaaaa-0000-0000-0000-000000000003"
        with open(os.path.join(pasta, ARQ_CATS), "w", encoding="utf-8") as f:
            f.write("VERSION 1\n\n")
            f.write("%s:%s:%s\n" % (u_raiz, velha, velha))
            f.write("%s:%s/Armarios/Cozinha:x\n" % (u_coz, velha))
            f.write("%s:%s/Coisa/Antiga:x\n" % (u_custom, velha))
        addon.biblioteca._garantir_catalogos(pasta)
        cats = ler_cats(pasta)
        R = addon.biblioteca.CAT_RAIZ
        self.assertEqual(cats[R], u_raiz)
        self.assertEqual(cats[R + "/Armarios/Cozinha"], u_coz)
        self.assertEqual(cats[R + "/Coisa/Antiga"], u_custom)
        for cam in cats:
            self.assertFalse(cam == velha or cam.startswith(velha + "/"),
                             "raiz antiga sobrou: " + cam)


# ====================================================== GRAVACAO
class TestGravacao(BaseBiblioteca):
    def test_salvar_objeto_grava_asset_no_catalogo_da_categoria(self):
        placa = self.chapa("Placa Teste")
        arq = addon.biblioteca.salvar_na_biblioteca([placa], "Placa Teste", False,
                                         niveis=("Portas", "Abrir", ""))
        self.assertEqual(os.path.dirname(arq), self.pasta)
        self.assertEqual(os.path.basename(arq), "Placa_Teste.blend")
        self.assertTrue(os.path.exists(arq))
        u = ler_cats(self.pasta)["Cabinet Creator/Portas/Abrir"]
        lidos = dict(ler_blend(arq))
        self.assertIn("Placa Teste", lidos)
        info = lidos["Placa Teste"]
        self.assertTrue(info["asset"])
        self.assertEqual(info["catalogo"], u)
        self.assertEqual(info["props"].get(addon.chapas.MARCA_CHAPA), 1)
        self.assertEqual(info["vertices"], len(placa.data.vertices))

    def test_salvar_sem_niveis_cai_no_catalogo_por_tipo(self):
        a = self.chapa("A")
        arq = addon.biblioteca.salvar_na_biblioteca([a], "Sem Categoria", False)
        cats = ler_cats(self.pasta)
        self.assertIn(addon.biblioteca.CAT_CHAPAS, cats)
        self.assertEqual(dict(ler_blend(arq))["A"]["catalogo"],
                         cats[addon.biblioteca.CAT_CHAPAS])

    def test_salvar_modulo_marca_a_colecao_e_nao_suja_a_cena(self):
        a = self.chapa("Lado A", (0, 0, 0))
        b = self.chapa("Lado B", (700, 0, 0))
        cols_antes = set(bpy.data.collections)
        arq = addon.biblioteca.salvar_na_biblioteca([a, b], "Modulo Teste", True,
                                         niveis=("Armarios", "Sala",
                                                 "Cantos"))
        # a Collection era so' embalagem: nao pode sobrar na cena
        self.assertEqual(set(bpy.data.collections), cols_antes)
        lidos = ler_blend(arq)
        cols = [(n, i) for n, i in lidos if i["tipo_id"] == "Collection"]
        self.assertEqual(len(cols), 1)
        nome, info = cols[0]
        self.assertEqual(nome, "Modulo Teste")
        self.assertTrue(info["asset"])
        self.assertEqual(info["catalogo"], ler_cats(self.pasta)[
            "Cabinet Creator/Armarios/Sala/Cantos"])
        objs = {n: i for n, i in lidos if i["tipo_id"] == "Object"}
        self.assertEqual(set(objs), {"Lado A", "Lado B"})
        for i in objs.values():
            self.assertFalse(i["asset"])     # so' a colecao e' asset

    def test_nome_de_arquivo_seguro(self):
        self.assertEqual(addon.biblioteca._nome_arquivo_seguro("Nicho 60/40: x"),
                         "Nicho_60_40__x")
        self.assertEqual(addon.biblioteca._nome_arquivo_seguro("  "), "sem_nome")
        self.assertNotIn("..", addon.biblioteca._nome_arquivo_seguro("../../fora"))

    def test_refiliar_move_o_catalogo_sem_perder_o_asset(self):
        self.criar_presets_de_teste()
        cam = os.path.join(self.pasta, CHAPA_T)
        uuids_antes = ler_cats(self.pasta)
        antes = dict(ler_blend(cam))
        ok, msg = addon.biblioteca.refiliar_preset(cam, ("Portas", "Abrir", ""))
        self.assertTrue(ok, msg)
        self.assertEqual(msg, "Cabinet Creator/Portas/Abrir")
        depois_cats = ler_cats(self.pasta)
        # nenhum UUID existente mudou
        for c, u in uuids_antes.items():
            self.assertEqual(depois_cats[c], u)
        depois = dict(ler_blend(cam))
        self.assertEqual(len(depois), len(antes))
        for nome, info in antes.items():
            novo = depois[nome]
            self.assertTrue(novo["asset"])
            self.assertEqual(novo["catalogo"],
                             depois_cats["Cabinet Creator/Portas/Abrir"])
            self.assertEqual(novo["props"], info["props"])
            self.assertEqual(novo["vertices"], info["vertices"])

    def test_refiliar_modulo_categoria_nova_ganha_catalogo(self):
        self.criar_presets_de_teste()
        cam = os.path.join(self.pasta, NICHO_T)
        ok, msg = addon.biblioteca.refiliar_preset(cam, ("Armarios", "Lavanderia", ""))
        self.assertTrue(ok, msg)
        cats = ler_cats(self.pasta)
        self.assertIn("Cabinet Creator/Armarios/Lavanderia", cats)
        lidos = ler_blend(cam)
        col = [i for n, i in lidos if i["tipo_id"] == "Collection"][0]
        self.assertEqual(col["catalogo"],
                         cats["Cabinet Creator/Armarios/Lavanderia"])
        # as chapas do modulo continuam la', com marcador e UID
        chapas = [i for n, i in lidos
                  if addon.chapas.MARCA_CHAPA in i["props"]]
        self.assertEqual(len(chapas), 4)
        self.assertTrue(all(i["props"].get("chapa_uid") for i in chapas))

    def test_refiliar_recusa_sem_categoria_sem_arquivo_e_sem_asset(self):
        self.criar_presets_de_teste()
        cam = os.path.join(self.pasta, CHAPA_T)
        antes = self.texto(CHAPA_T)
        self.assertFalse(addon.biblioteca.refiliar_preset(cam, ("", "", ""))[0])
        self.assertEqual(self.texto(CHAPA_T), antes)
        self.assertFalse(addon.biblioteca.refiliar_preset(
            os.path.join(self.pasta, "nao_existe.blend"), ("Portas",))[0])
        # .blend sem nenhum asset marcado
        o = self.chapa("Sem Asset")
        sem = os.path.join(self.pasta, "sem_asset.blend")
        bpy.data.libraries.write(sem, {o, o.data}, fake_user=True)
        ok, msg = addon.biblioteca.refiliar_preset(sem, ("Portas",))
        self.assertFalse(ok)
        self.assertIn("nenhum asset", msg)

    # BUG: refiliar_preset (e aplicar_preview_png, mesmo padrao) faz
    # append do .blend na cena aberta; se ja' existe um objeto com o mesmo
    # nome, o append renomeia para ".001" e o arquivo e' regravado com o
    # nome NOVO -- o asset muda de nome a cada reorganizacao.
    @unittest.expectedFailure
    def test_refiliar_preserva_o_nome_do_asset_com_homonimo_na_cena(self):
        self.criar_presets_de_teste()
        self.chapa(NOME_CHAPA_T)          # homonimo na cena
        cam = os.path.join(self.pasta, CHAPA_T)
        ok, msg = addon.biblioteca.refiliar_preset(cam, ("Portas", "Abrir", ""))
        self.assertTrue(ok, msg)
        self.assertEqual([n for n, _i in ler_blend(cam)],
                         [NOME_CHAPA_T])

    def test_aplicar_preview_png_grava_pixels_no_asset(self):
        self.criar_presets_de_teste()
        cam = os.path.join(self.pasta, CHAPA_T)
        png = os.path.join(self.tmp, "foto.png")
        cor = (1.0, 0.0, 1.0, 1.0)
        png_solido(png, cor)
        ok, msg = addon.biblioteca.aplicar_preview_png(cam, png)
        self.assertTrue(ok, msg)
        lidos = dict(ler_blend(cam))
        info = lidos[NOME_CHAPA_T]
        self.assertTrue(info["asset"])
        self.assertIsNotNone(info["preview"])
        img_size, icon_size, px = info["preview"]
        lado = (addon.biblioteca.LADO_PREVIEW, addon.biblioteca.LADO_PREVIEW)
        self.assertEqual(img_size, lado)
        # sem o nivel de icone o Asset Browser mostra o icone generico
        self.assertEqual(icon_size, lado)
        for a, b in zip(px, cor):
            self.assertAlmostEqual(a, b, delta=0.02)
        # catalogo nao foi tocado pela preview
        self.assertEqual(info["catalogo"], ler_cats(self.pasta)[
            "Cabinet Creator/Chapas/Avulsas"])

    def test_aplicar_preview_png_recusa_sem_arquivos(self):
        self.criar_presets_de_teste()
        cam = os.path.join(self.pasta, CHAPA_T)
        antes = self.texto(CHAPA_T)
        ok, _ = addon.biblioteca.aplicar_preview_png(cam, os.path.join(self.tmp,
                                                            "nada.png"))
        self.assertFalse(ok)
        self.assertEqual(self.texto(CHAPA_T), antes)
        png = os.path.join(self.tmp, "foto.png")
        png_solido(png, (0, 0, 0, 1))
        ok, _ = addon.biblioteca.aplicar_preview_png(
            os.path.join(self.pasta, "nada.blend"), png)
        self.assertFalse(ok)


# ====================================================== OPERADORES
class TestOperadores(BaseBiblioteca):
    def test_salvar_sem_foto_cancela_e_nao_cadastra(self):
        # Em --background o render OpenGL nao existe: a captura falha de
        # verdade, que e' justamente o caminho que precisa ser guardado.
        if not bpy.app.background:
            self.skipTest("so' faz sentido sem GPU (--background)")
        antes_indice = self.texto(addon.biblioteca.NOME_INDICE)
        placa = self.chapa("Sem Foto")
        selecionar(placa)
        with self.assertRaises(RuntimeError) as cm:
            bpy.ops.object.cabinet_salvar_biblioteca(
                'EXEC_DEFAULT', nome="Sem Foto", n1="Chapas",
                como_modulo=False)
        self.assertIn("Foto obrigatoria falhou", str(cm.exception))
        self.assertEqual(self.texto(addon.biblioteca.NOME_INDICE), antes_indice)
        self.assertFalse(os.path.exists(
            os.path.join(self.pasta, "Sem_Foto.png")))
        # a cena do usuario sobrevive a falha
        self.assertIn("Sem Foto", bpy.data.objects)

    # BUG: o .blend e' gravado (salvar_na_biblioteca) ANTES da foto; se a
    # foto falha o cadastro e' cancelado mas o arquivo fica orfao na
    # pasta da biblioteca -- invisivel no painel e visivel no Asset Browser.
    @unittest.expectedFailure
    def test_salvar_sem_foto_nao_deixa_blend_orfao(self):
        if not bpy.app.background:
            self.skipTest("so' faz sentido sem GPU (--background)")
        arquivos_antes = sorted(os.listdir(self.pasta))
        placa = self.chapa("Orfao")
        selecionar(placa)
        try:
            bpy.ops.object.cabinet_salvar_biblioteca(
                'EXEC_DEFAULT', nome="Orfao", n1="Chapas", como_modulo=False)
        except RuntimeError:
            pass
        self.assertEqual(sorted(os.listdir(self.pasta)), arquivos_antes)

    def _foto_simulada(self):
        """Troca a captura por um PNG solido: exercita o resto do fluxo."""
        def capturar(destino, camera=None, isolar=None):
            png_solido(destino, (0.0, 1.0, 0.0, 1.0))
            return True, destino
        addon.biblioteca.capturar_viewport = capturar

    def test_salvar_com_foto_cadastra_grava_preview_e_catalogo(self):
        self._foto_simulada()
        placa = self.chapa("Prateleira")
        selecionar(placa)
        r = bpy.ops.object.cabinet_salvar_biblioteca(
            'EXEC_DEFAULT', nome="Prateleira", n1="Chapas",
            como_modulo=False)
        self.assertEqual(r, {'FINISHED'})
        arq = os.path.join(self.pasta, "Prateleira.blend")
        self.assertTrue(os.path.exists(arq))
        self.assertTrue(os.path.exists(
            os.path.join(self.pasta, "Prateleira.png")))
        item = [i for i in self.indice()
                if i["arquivo"] == "Prateleira.blend"]
        self.assertEqual(len(item), 1)
        # n2 vazio resolve para o primeiro filho da categoria
        self.assertEqual((item[0]["n1"], item[0]["n2"], item[0]["n3"],
                          item[0]["tipo"]),
                         ("Chapas", "Avulsas", "", "objeto"))
        u = ler_cats(self.pasta)["Cabinet Creator/Chapas/Avulsas"]
        assets = [i for _n, i in ler_blend(arq) if i["asset"]]
        self.assertEqual(len(assets), 1)
        self.assertEqual(assets[0]["catalogo"], u)
        self.assertIsNotNone(assets[0]["preview"])
        self.assertEqual(assets[0]["preview"][0],
                         (addon.biblioteca.LADO_PREVIEW, addon.biblioteca.LADO_PREVIEW))
        self.assertAlmostEqual(assets[0]["preview"][2][1], 1.0, delta=0.02)

    def test_salvar_modulo_inclui_filhos_do_conjunto(self):
        self._foto_simulada()
        a = self.chapa("Lateral", (0, 0, 0))
        b = self.chapa("Outra", (700, 0, 0))
        pai = bpy.data.objects.new("Conjunto X", None)
        bpy.context.collection.objects.link(pai)
        pai[addon.chapas.MARCA_CONJUNTO] = 1
        for f in (a, b):
            f.parent = pai
        selecionar(pai)               # so' o Empty selecionado
        r = bpy.ops.object.cabinet_salvar_biblioteca(
            'EXEC_DEFAULT', nome="Conjunto X", n1="Armarios", n2="Sala",
            n3="Estantes", como_modulo=True)
        self.assertEqual(r, {'FINISHED'})
        arq = os.path.join(self.pasta, "Conjunto_X.blend")
        nomes = {n for n, i in ler_blend(arq) if i["tipo_id"] == "Object"}
        self.assertTrue({"Lateral", "Outra"} <= {n.split(".")[0]
                                                 for n in nomes})
        item = [i for i in self.indice()
                if i["arquivo"] == "Conjunto_X.blend"][0]
        self.assertEqual((item["n1"], item["n2"], item["n3"], item["tipo"]),
                         ("Armarios", "Sala", "Estantes", "modulo"))

    # BUG: o fluxo de salvar chama aplicar_preview_png com o objeto
    # original AINDA na cena; o append do .blend renomeia a copia para
    # ".001" e o arquivo e' regravado assim -- todo preset salvo pela UI
    # nasce com o asset chamado "<nome>.001".
    @unittest.expectedFailure
    def test_salvar_com_foto_preserva_o_nome_do_objeto(self):
        self._foto_simulada()
        placa = self.chapa("Tampo Unico")
        selecionar(placa)
        bpy.ops.object.cabinet_salvar_biblioteca(
            'EXEC_DEFAULT', nome="Tampo Unico", n1="Chapas",
            como_modulo=False)
        arq = os.path.join(self.pasta, "Tampo_Unico.blend")
        self.assertEqual([n for n, _i in ler_blend(arq)], ["Tampo Unico"])

    def test_salvar_sem_selecao_cancela(self):
        selecionar()
        antes = impressao_digital(self.pasta)
        r = bpy.ops.object.cabinet_salvar_biblioteca(
            'EXEC_DEFAULT', nome="Nada", n1="Chapas", como_modulo=False)
        self.assertEqual(r, {'CANCELLED'})
        self.assertEqual(impressao_digital(self.pasta), antes)

    def test_bloqueio_alterna_o_cadeado_do_item(self):
        arq = "Chapa_600x400x18.blend"
        it = addon.biblioteca._achar_item(self.pasta, arq)
        self.assertFalse(addon.biblioteca.item_bloqueado(it))
        self.assertEqual(bpy.ops.object.cabinet_bloqueio(
            pasta=self.pasta, arquivo=arq), {'FINISHED'})
        self.assertTrue(addon.biblioteca.item_bloqueado(
            addon.biblioteca._achar_item(self.pasta, arq)))
        # os outros itens nao foram trancados junto
        for outro in addon.biblioteca.indice_completo():
            if outro["arquivo"] != arq:
                self.assertFalse(addon.biblioteca.item_bloqueado(outro))
        self.assertEqual(bpy.ops.object.cabinet_bloqueio(
            pasta=self.pasta, arquivo=arq), {'FINISHED'})
        self.assertFalse(addon.biblioteca.item_bloqueado(
            addon.biblioteca._achar_item(self.pasta, arq)))

    def test_bloqueio_de_item_inexistente_cancela_sem_gravar(self):
        antes = self.texto(addon.biblioteca.NOME_INDICE)
        self.assertEqual(bpy.ops.object.cabinet_bloqueio(
            pasta=self.pasta, arquivo="fantasma.blend"), {'CANCELLED'})
        self.assertEqual(self.texto(addon.biblioteca.NOME_INDICE), antes)

    def test_editar_modelo_renomeia_e_muda_categoria_no_indice(self):
        arq = "Cube.blend"
        r = bpy.ops.object.cabinet_editar_modelo(
            'EXEC_DEFAULT', pasta=self.pasta, arquivo=arq,
            nome="Cubo Renomeado", n1="Portas", n2="Correr", n3="")
        self.assertEqual(r, {'FINISHED'})
        it = addon.biblioteca._achar_item(self.pasta, arq)
        self.assertEqual(it["nome"], "Cubo Renomeado")
        self.assertEqual(addon.biblioteca._niveis_de(it), ("Portas", "Correr", ""))
        # os demais itens nao foram mexidos
        self.assertEqual(addon.biblioteca._achar_item(
            self.pasta, "Nicho_600x400x300.blend")["nome"],
            "Nicho 600x400x300")

    def test_editar_modelo_converte_item_legado(self):
        itens = self.indice()
        itens.append({"nome": "Velho", "arquivo": "Velho.blend",
                      "categoria": "Cozinha", "subcategoria": "Torres",
                      "tipo": "objeto"})
        addon.biblioteca._gravar_indice(self.pasta, itens)
        bpy.ops.object.cabinet_editar_modelo(
            'EXEC_DEFAULT', pasta=self.pasta, arquivo="Velho.blend",
            nome="Velho", n1="Armarios", n2="Cozinha", n3="Torres")
        it = [i for i in self.indice() if i["arquivo"] == "Velho.blend"][0]
        self.assertNotIn("categoria", it)
        self.assertNotIn("subcategoria", it)
        self.assertEqual((it["n1"], it["n2"], it["n3"]),
                         ("Armarios", "Cozinha", "Torres"))

    def test_editar_modelo_bloqueado_nao_muda_nada(self):
        arq = "Cube.blend"
        addon.biblioteca._atualizar_item(self.pasta, arq, {"bloqueado": True})
        antes = self.texto(addon.biblioteca.NOME_INDICE)
        r = bpy.ops.object.cabinet_editar_modelo(
            'EXEC_DEFAULT', pasta=self.pasta, arquivo=arq,
            nome="Nao Pode", n1="Portas", n2="Abrir", n3="")
        self.assertEqual(r, {'CANCELLED'})
        self.assertEqual(self.texto(addon.biblioteca.NOME_INDICE), antes)

    def test_editar_modelo_inexistente_reporta_erro(self):
        antes = self.texto(addon.biblioteca.NOME_INDICE)
        with self.assertRaises(RuntimeError):
            bpy.ops.object.cabinet_editar_modelo(
                'EXEC_DEFAULT', pasta=self.pasta, arquivo="fantasma.blend",
                nome="X", n1="Portas")
        self.assertEqual(self.texto(addon.biblioteca.NOME_INDICE), antes)

    # BUG: editar_modelo troca a categoria so' no indice.json. Pela
    # invariante 15 o catalogo mora dentro do .blend e mover exige
    # regravar (refiliar_preset); sem isso o Asset Browser continua
    # mostrando o preset na categoria antiga ate' alguem rodar
    # "Reorganizar Catalogos".
    @unittest.expectedFailure
    def test_editar_modelo_move_o_asset_de_catalogo(self):
        self.criar_presets_de_teste()
        arq = CHAPA_T
        r = bpy.ops.object.cabinet_editar_modelo(
            'EXEC_DEFAULT', pasta=self.pasta, arquivo=arq,
            nome=NOME_CHAPA_T, n1="Portas", n2="Abrir", n3="")
        self.assertEqual(r, {'FINISHED'})
        u = ler_cats(self.pasta)["Cabinet Creator/Portas/Abrir"]
        assets = [i for _n, i in ler_blend(os.path.join(self.pasta, arq))
                  if i["asset"]]
        self.assertEqual(len(assets), 1)
        self.assertEqual(assets[0]["catalogo"], u)

    def test_navegar_em_cascata(self):
        s = bpy.context.scene
        nav = bpy.ops.object.cabinet_navegar
        nav(nivel=1, valor="Armarios")
        nav(nivel=2, valor="Cozinha")
        nav(nivel=3, valor="Torres")
        self.assertEqual((s.chapa_n1, s.chapa_n2, s.chapa_n3),
                         ("Armarios", "Cozinha", "Torres"))
        # repetir o MESMO valor no nivel 3 limpa so' o 3
        nav(nivel=3, valor="Torres")
        self.assertEqual((s.chapa_n1, s.chapa_n2, s.chapa_n3),
                         ("Armarios", "Cozinha", ""))
        nav(nivel=3, valor="Cantos")
        # trocar o nivel 2 zera o 3
        nav(nivel=2, valor="Sala")
        self.assertEqual((s.chapa_n1, s.chapa_n2, s.chapa_n3),
                         ("Armarios", "Sala", ""))
        nav(nivel=3, valor="Estantes")
        # repetir o nivel 2 limpa o 2 e o 3
        nav(nivel=2, valor="Sala")
        self.assertEqual((s.chapa_n1, s.chapa_n2, s.chapa_n3),
                         ("Armarios", "", ""))
        nav(nivel=2, valor="Sala")
        nav(nivel=3, valor="Cantos")
        # trocar o nivel 1 zera tudo abaixo
        nav(nivel=1, valor="Portas")
        self.assertEqual((s.chapa_n1, s.chapa_n2, s.chapa_n3),
                         ("Portas", "", ""))
        nav(nivel=1, valor="Portas")
        self.assertEqual((s.chapa_n1, s.chapa_n2, s.chapa_n3), ("", "", ""))

    def test_niveis_sem_limite_na_cascata_e_sem_contagem(self):
        # pedido do usuario: a biblioteca nao tem limite de niveis (Altos e'
        # um ramo, Despenseiros outro carrossel abaixo) e o botao da
        # categoria nao leva a quantidade de itens (ocupava espaco)
        B = addon.biblioteca
        trilha = ("Armarios", "Cozinha", "Altos", "Despenseiros", "Com Gaveta")
        B.registrar_no_indice(self.pasta, "Fundo", "Fundo.blend", *trilha, "modulo")
        it = next(i for i in self.indice() if i["arquivo"] == "Fundo.blend")
        self.assertEqual(it["niveis"], list(trilha))
        self.assertEqual((it["n1"], it["n2"], it["n3"]), trilha[:3])
        self.assertEqual(B.caminho_de(it), trilha)
        self.assertEqual(B._niveis_de(it), trilha[:3])
        self.assertIn(B.catalogo_de(*trilha), B.caminhos_catalogo())
        self.assertIn("Altos", B.filhos_de(B.indice_completo(), trilha[:2]))
        # ramo sem preset nao aparece (sem a contagem, levaria a nada)
        self.assertNotIn("Portas", B.filhos_de(B.indice_completo(), ()))
        s = bpy.context.scene
        s.cabinet_bib_modo = 'MODULOS'
        nav = bpy.ops.object.cabinet_navegar
        for nivel, valor in enumerate(trilha, 1):
            nav(nivel=nivel, valor=valor)
        self.assertEqual(B.trilha_da_cena(s), trilha)
        self.assertEqual(s.chapa_n_mais, "Despenseiros/Com Gaveta")
        itens = []
        addon.gaveta._biblioteca_gaveta(bpy.context, itens, 0, 2000, 900)
        niveis = {}
        for item in itens:
            if item[5] and item[5][0] == 'suspenso' and len(item[5]) > 3:
                niveis.setdefault(item[5][3], []).extend(item[5][4])
        self.assertEqual(sorted(niveis), [1, 2, 3, 4, 5])      # uma lista por nivel
        for rotulos in niveis.values():
            self.assertFalse([r for r in rotulos if '(' in r], rotulos)
        self.assertIn('Fundo', [i[4] for i in itens if i[5] and i[5][0] == 'preset'])
        # fechar o nivel 4 limpa o 4 e o 5
        nav(nivel=4, valor="Despenseiros")
        self.assertEqual(B.trilha_da_cena(s), trilha[:3])
        self.assertEqual(s.chapa_n_mais, "")


# ====================================================== INSERCAO
def local_no_arquivo(caminho, nome):
    """location gravada no .blend, sem passar pelo add-on."""
    antes = set(bpy.data.objects)
    with bpy.data.libraries.load(caminho) as (de, para):
        para.objects = [nome]
    loc = para.objects[0].location.copy()
    for o in list(bpy.data.objects):
        if o not in antes:
            bpy.data.objects.remove(o, do_unlink=True)
    return loc


def legivel(caminho):
    """O Blender em execucao consegue abrir este .blend?"""
    try:
        with bpy.data.libraries.load(caminho) as (de, _para):
            list(de.objects)
        return True
    except OSError:
        return False


class InsercaoBase(BaseBiblioteca):
    def assertPerto(self, a, b, delta=1e-5):
        for x, y in zip(a, b):
            self.assertAlmostEqual(x, y, delta=delta)

    def _medidas(self, objs):
        return {o.name: (round(o.chapa_largura_mm, 3),
                         round(o.chapa_comprimento_mm, 3),
                         tuple(round(v, 5)
                               for v in o.matrix_world.translation))
                for o in objs}

    def conferir_duas_copias(self, arquivo, n_chapas):
        # INVARIANTE 7: a segunda copia ganha ".001" nos nomes, mas os
        # adj_* gravados ainda apontam os nomes SEM sufixo. A resolucao
        # tem de achar o vizinho pelo UID entre os irmaos -- senao a
        # copia 2 estica ate' as chapas da copia 1.
        n1, _r1, e1 = addon.biblioteca.inserir_preset(
            bpy.context, self.pasta, arquivo, "modulo",
            destino=Vector((0, 0, 0)))
        n2, _r2, e2 = addon.biblioteca.inserir_preset(
            bpy.context, self.pasta, arquivo, "modulo",
            destino=Vector((3.0, 0, 0)))
        self.assertEqual((e1, e2), ("", ""))
        c1 = [o for o in n1 if addon.chapas.MARCA_CHAPA in o]
        c2 = [o for o in n2 if addon.chapas.MARCA_CHAPA in o]
        self.assertEqual(len(c1), n_chapas)
        self.assertEqual(len(c2), n_chapas)
        self.assertTrue(all(o.name.endswith(".001") for o in c2),
                        [o.name for o in c2])
        pai2 = c2[0].parent
        self.assertIsNotNone(pai2)
        self.assertTrue(all(o.parent is pai2 for o in c2))
        self.assertIsNot(pai2, c1[0].parent)
        bpy.context.view_layer.update()
        resolvidos = 0
        for C in c2:
            for k in addon.chapas.PONTAS:
                uid = C.get("adj_%s_uid" % k, "")
                nome = C.get("adj_%s" % k, "")
                if not uid:
                    continue
                # o nome gravado aponta para a copia 1 -- de proposito
                self.assertNotEqual(nome[-4:], ".001")
                N = addon.chapas._resolver_vizinho(C, uid, nome)
                self.assertIsNotNone(N)
                self.assertIs(N.parent, pai2, "%s %s -> %s" % (
                    C.name, k, N.name))
                self.assertEqual(N.get("chapa_uid"), uid)
                resolvidos += 1
        self.assertGreater(resolvidos, 0)
        # e aplicar a adjacencia nao deforma nenhuma das duas copias
        antes = self._medidas(c1 + c2)
        addon.chapas.aplicar_adjacencia()
        bpy.context.view_layer.update()
        depois = self._medidas(c1 + c2)
        for nome, (l, c, p) in antes.items():
            l2, c2_, p2 = depois[nome]
            self.assertAlmostEqual(l, l2, delta=0.01, msg=nome)
            self.assertAlmostEqual(c, c2_, delta=0.01, msg=nome)
            self.assertPerto(p, p2, delta=1e-4)


class TestInsercao(InsercaoBase):
    def test_append_conserva_subcolecao_sem_religa_la_na_raiz(self):
        raiz=bpy.data.collections.new('Montagem teste')
        filha=bpy.data.collections.new('Ferragens teste');raiz.children.link(filha)
        objeto=bpy.data.objects.new('Auxiliar teste',None);filha.objects.link(objeto)
        arquivo='Teste_subcolecao.blend'
        bpy.data.libraries.write(os.path.join(self.pasta,arquivo),{raiz})
        bpy.data.objects.remove(objeto,do_unlink=True)
        bpy.data.collections.remove(raiz);bpy.data.collections.remove(filha)
        novos,raizes,erro=addon.biblioteca.inserir_preset(bpy.context,self.pasta,arquivo,'modulo')
        self.assertFalse(erro)
        self.assertEqual(len(novos),1)
        sub=bpy.data.collections['Ferragens teste']
        self.assertNotIn(sub.name,bpy.context.scene.collection.children)
        self.assertIn(sub.name,bpy.data.collections['Montagem teste'].children)

    def setUp(self):
        super().setUp()
        self.criar_presets_de_teste()

    def test_inserir_objeto_no_destino_selecionado_e_marcado(self):
        base = local_no_arquivo(os.path.join(self.pasta, CHAPA_T),
                                NOME_CHAPA_T)
        self.assertGreater(base.length, 0.01)   # a origem do arquivo conta
        outro = self.chapa("Ja Estava")
        selecionar(outro)
        destino = Vector((1.0, -2.0, 0.5))
        novos, raizes, erro = addon.biblioteca.inserir_preset(
            bpy.context, self.pasta, CHAPA_T, "objeto", destino=destino)
        self.assertEqual(erro, "")
        self.assertEqual(len(novos), 1)
        self.assertEqual(raizes, novos)
        o = novos[0]
        self.assertEqual(o.name, NOME_CHAPA_T)
        self.assertIn(addon.chapas.MARCA_CHAPA, o)
        self.assertAlmostEqual(o.chapa_espessura_mm, 18.0)
        self.assertIn(o.name, bpy.context.scene.objects)
        self.assertPerto(o.location, base + destino)
        # so' o que chegou fica selecionado
        self.assertEqual(set(bpy.context.selected_objects), {o})

    def test_inserir_sem_destino_usa_o_cursor_3d(self):
        base = local_no_arquivo(os.path.join(self.pasta, CHAPA_T),
                                NOME_CHAPA_T)
        bpy.context.scene.cursor.location = (0.3, 0.4, 1.2)
        novos, _r, erro = addon.biblioteca.inserir_preset(
            bpy.context, self.pasta, CHAPA_T, "objeto")
        self.assertEqual(erro, "")
        self.assertPerto(novos[0].location, base + Vector((0.3, 0.4, 1.2)))

    def test_inserir_arquivo_inexistente_devolve_erro(self):
        n = len(bpy.data.objects)
        novos, raizes, erro = addon.biblioteca.inserir_preset(
            bpy.context, self.pasta, "fantasma.blend", "objeto")
        self.assertEqual((novos, raizes), ([], []))
        self.assertIn("nao encontrado", erro)
        self.assertEqual(len(bpy.data.objects), n)

    def test_inserir_nao_altera_a_biblioteca(self):
        antes = impressao_digital(self.pasta)
        addon.biblioteca.inserir_preset(bpy.context, self.pasta, NICHO_T, "modulo")
        addon.biblioteca.inserir_preset(bpy.context, self.pasta, CHAPA_T, "objeto")
        self.assertEqual(impressao_digital(self.pasta), antes)

    def test_operador_inserir_modulo_no_cursor(self):
        base = local_no_arquivo(os.path.join(self.pasta, NICHO_T),
                                NOME_NICHO_T)
        self.assertGreater(base.length, 0.01)
        bpy.context.scene.cursor.location = (2.0, 1.0, 0.0)
        r = bpy.ops.object.cabinet_inserir_preset(
            pasta=self.pasta, arquivo=NICHO_T, tipo="modulo")
        self.assertEqual(r, {'FINISHED'})
        vazio = bpy.data.objects[NOME_NICHO_T]
        self.assertIn(addon.chapas.MARCA_CONJUNTO, vazio)
        self.assertPerto(vazio.location, base + Vector((2.0, 1.0, 0.0)))
        # o modulo chega pela Collection-asset, ligada a cena
        self.assertIn(NOME_NICHO_T, bpy.context.scene.collection.children)
        chapas = [o for o in bpy.data.objects if o.parent is vazio]
        self.assertEqual(len(chapas), 4)
        for c in chapas:
            self.assertIn(addon.chapas.MARCA_CHAPA, c)
            self.assertTrue(c.get("chapa_uid"))
            self.assertTrue(c.select_get())
            self.assertIn(c.name, bpy.context.scene.objects)
        self.assertTrue(vazio.select_get())
        # as chapas nao saem do lugar relativo ao Empty
        bpy.context.view_layer.update()
        base_ch = [c for c in chapas if c.name == "Base"][0]
        self.assertPerto(base_ch.matrix_world.translation - vazio.location,
                         Vector((0, 0, 0.009)), delta=1e-4)

    def test_operador_inserir_inexistente_reporta_erro(self):
        n = len(bpy.data.objects)
        with self.assertRaises(RuntimeError):
            bpy.ops.object.cabinet_inserir_preset(
                pasta=self.pasta, arquivo="fantasma.blend", tipo="modulo")
        self.assertEqual(len(bpy.data.objects), n)

    def test_inserir_duas_vezes_resolve_vizinho_por_uid(self):
        self.conferir_duas_copias(NICHO_T, 4)


# INCOMPATIBILIDADE CONHECIDA: os .blend de fabrica foram gravados pelo
# Blender 5.x (formato de arquivo novo) e o 4.x responde "not a blend
# file" -- embora o bl_info prometa blender (4, 0, 0). Por decisao do
# projeto, os testes que abrem os presets REAIS sao pulados no 4.x; os
# demais usam presets gerados pelo proprio teste e rodam nas duas.
def pular_no_4x(caso):
    if bpy.app.version < (5, 0, 0):
        caso.skipTest('biblioteca gravada no formato do 5.x')


class TestPresetsDeFabrica(InsercaoBase):
    AMOSTRA_COMPLETA = True
    def test_reducao_extrema_e_retorno_preservam_chapas_dos_presets(self):
        if bpy.app.version<(5,):self.skipTest('Presets gravados no Blender 5.x')
        from mathutils.kdtree import KDTree
        nomes=('Cantoneira_04_300x706x550.blend','Diagonal_04_367x703x559.blend',
               'Gaveteiro_02_400x703x550.blend','Canto_02_1245x703x550.blend',
               'Canto_05B_1142x703x1142.blend')
        for nome in nomes:
            limpar_cena()
            novos,rs,erro=addon.biblioteca.inserir_preset(bpy.context,PASTA_REAL,nome,'modulo')
            self.assertFalse(erro)
            conj=next(o for o in novos if addon.chapas.MARCA_CONJUNTO in o)
            antes={o:[o.matrix_world @ v.co for v in o.data.vertices]
                   for o in addon.modulos._chapas_do_conjunto(conj)}
            for prop in ('conj_profundidade_mm','conj_altura_mm','conj_largura_mm'):
                original=getattr(conj,prop)
                setattr(conj,prop,100);setattr(conj,prop,original)
            bpy.context.view_layer.update()
            for o,vs in antes.items():
                kd=KDTree(len(o.data.vertices))
                for i,v in enumerate(o.data.vertices):kd.insert(o.matrix_world @ v.co,i)
                kd.balance()
                self.assertLess(max(kd.find(p)[2] for p in vs),.00005,msg=nome+' / '+o.name)

    """Os arquivos REAIS da biblioteca: a integridade de TODOS, so' lendo
    da pasta real; o que grava, na amostra (copia temporaria)."""

    def exigir_legivel(self, arquivo):
        pular_no_4x(self)
        self.assertTrue(legivel(os.path.join(self.pasta, arquivo)), arquivo)

    def indice_real(self):
        with open(os.path.join(PASTA_REAL, addon.biblioteca.NOME_INDICE),
                  encoding="utf-8") as f:
            return json.load(f)

    def test_amostra_tem_cada_categoria_da_biblioteca(self):
        reais = {addon.biblioteca.caminho_de(i) for i in self.indice_real()}
        copia = {addon.biblioteca.caminho_de(i) for i in self.indice()}
        self.assertEqual(reais, copia)

    def test_indice_de_fabrica_e_consistente(self):
        itens = self.indice_real()        # a pasta REAL, so' lendo
        self.assertTrue(itens)
        arquivos = [i["arquivo"] for i in itens]
        self.assertEqual(len(arquivos), len(set(arquivos)))
        for it in itens:
            self.assertEqual(it["arquivo"], os.path.basename(it["arquivo"]))
            self.assertTrue(os.path.exists(
                os.path.join(PASTA_REAL, it["arquivo"])), it["arquivo"])
            # todo preset nasce com foto (CLAUDE.md, armadilhas por area)
            png = os.path.splitext(it["arquivo"])[0] + ".png"
            self.assertTrue(os.path.exists(os.path.join(PASTA_REAL, png)),
                            png)
            self.assertIn(it.get("tipo"), ("modulo", "objeto"))
            self.assertIn(addon.biblioteca._niveis_de(it)[0], addon.biblioteca.ARVORE)
            self.assertNotIn("pasta", it)
            self.assertNotIn("origem", it)
        # todo .blend da pasta esta' no indice (nenhum orfao commitado)
        soltos = [a for a in os.listdir(PASTA_REAL)
                  if a.endswith(".blend") and a not in arquivos]
        self.assertEqual(soltos, [])

    def test_cats_de_fabrica_tem_uuid_unico_e_raiz_unica(self):
        cats = ler_cats(PASTA_REAL)
        self.assertEqual(len(set(cats.values())), len(cats))
        for cam in cats:
            self.assertTrue(cam == addon.biblioteca.CAT_RAIZ
                            or cam.startswith(addon.biblioteca.CAT_RAIZ + "/"), cam)
        for cam in addon.biblioteca.caminhos_catalogo():
            self.assertIn(cam, cats)

    def test_presets_de_fabrica_abrem_nesta_versao(self):
        pular_no_4x(self)
        for it in self.indice_real():
            self.assertTrue(legivel(os.path.join(PASTA_REAL, it["arquivo"])),
                            it["arquivo"])

    def test_catalogo_de_cada_preset_bate_com_o_indice(self):
        pular_no_4x(self)
        cats = ler_cats(PASTA_REAL)
        for it in self.indice_real():
            esperado = cats[addon.biblioteca.catalogo_de(*addon.biblioteca.caminho_de(it))]
            assets = [i for _n, i in ler_blend(
                os.path.join(PASTA_REAL, it["arquivo"])) if i["asset"]]
            self.assertTrue(assets, it["arquivo"])
            for a in assets:
                self.assertEqual(a["catalogo"], esperado, it["arquivo"])
            if it["tipo"] == "modulo":
                self.assertEqual({a["tipo_id"] for a in assets},
                                 {"Collection"})

    def test_nicho_de_fabrica_inserido_duas_vezes(self):
        self.exigir_legivel("Nicho_600x400x300.blend")
        self.conferir_duas_copias("Nicho_600x400x300.blend", 4)

    def test_chapa_de_fabrica_chega_marcada_no_cursor(self):
        self.exigir_legivel("Chapa_600x400x18.blend")
        bpy.context.scene.cursor.location = (0.5, 0.0, 0.0)
        r = bpy.ops.object.cabinet_inserir_preset(
            pasta=self.pasta, arquivo="Chapa_600x400x18.blend",
            tipo="objeto")
        self.assertEqual(r, {'FINISHED'})
        sel = bpy.context.selected_objects
        self.assertEqual(len(sel), 1)
        self.assertIn(addon.chapas.MARCA_CHAPA, sel[0])

    def test_refiliar_na_biblioteca_de_fabrica_mantem_catalogos(self):
        pular_no_4x(self)
        uuids = ler_cats(self.pasta)
        r = bpy.ops.object.cabinet_refiliar('EXEC_DEFAULT')
        self.assertEqual(r, {'FINISHED'})
        cats = ler_cats(self.pasta)
        for cam, u in uuids.items():
            self.assertEqual(cats[cam], u)
        for it in self.indice():
            esperado = cats[addon.biblioteca.catalogo_de(*addon.biblioteca.caminho_de(it))]
            assets = [(n, i) for n, i in ler_blend(
                os.path.join(self.pasta, it["arquivo"])) if i["asset"]]
            self.assertTrue(assets, it["arquivo"])
            for _n, a in assets:
                self.assertEqual(a["catalogo"], esperado, it["arquivo"])

    def test_regerar_previews_na_biblioteca_de_fabrica(self):
        pular_no_4x(self)
        r = bpy.ops.object.cabinet_regerar_previews('EXEC_DEFAULT')
        self.assertEqual(r, {'FINISHED'})
        lado = (addon.biblioteca.LADO_PREVIEW, addon.biblioteca.LADO_PREVIEW)
        for it in self.indice():
            png = os.path.join(self.pasta,
                               os.path.splitext(it["arquivo"])[0] + ".png")
            esperado = addon.biblioteca._pixels_png(png)
            for _n, a in ler_blend(os.path.join(self.pasta, it["arquivo"])):
                if not a["asset"]:
                    continue
                self.assertIsNotNone(a["preview"], it["arquivo"])
                self.assertEqual(a["preview"][0], lado, it["arquivo"])
                self.assertEqual(a["preview"][1], lado, it["arquivo"])
                for x, y in zip(a["preview"][2], esperado[0:4]):
                    self.assertAlmostEqual(x, y, delta=0.02)


class TestOperadoresDeLote(InsercaoBase):
    """Reorganizar Catalogos e Regerar Previews: varrem o indice inteiro
    e REGRAVAM os .blend -- sempre na copia temporaria."""

    def setUp(self):
        super().setUp()
        self.criar_presets_de_teste()
        # so' os presets gerados aqui: valem em qualquer versao
        addon.biblioteca._gravar_indice(self.pasta, [
            i for i in self.indice() if i["arquivo"] in (CHAPA_T, NICHO_T)])

    def catalogo_no_arquivo(self, arquivo):
        assets = [i for _n, i in ler_blend(os.path.join(self.pasta, arquivo))
                  if i["asset"]]
        self.assertEqual(len(assets), 1, arquivo)
        return assets[0]

    def test_refiliar_rearquiva_conforme_o_indice(self):
        addon.biblioteca._atualizar_item(self.pasta, CHAPA_T,
                              {"n1": "Portas", "n2": "Abrir", "n3": ""})
        addon.biblioteca._atualizar_item(self.pasta, NICHO_T,
                              {"n1": "Armarios", "n2": "Lavanderia",
                               "n3": ""})
        r = bpy.ops.object.cabinet_refiliar('EXEC_DEFAULT')
        self.assertEqual(r, {'FINISHED'})
        cats = ler_cats(self.pasta)
        self.assertEqual(self.catalogo_no_arquivo(CHAPA_T)["catalogo"],
                         cats["Cabinet Creator/Portas/Abrir"])
        nicho = self.catalogo_no_arquivo(NICHO_T)
        self.assertEqual(nicho["tipo_id"], "Collection")
        # categoria nova vira catalogo e recebe o modulo
        self.assertEqual(nicho["catalogo"],
                         cats["Cabinet Creator/Armarios/Lavanderia"])
        # as chapas continuam dentro do .blend, com UID
        chapas = [i for _n, i in ler_blend(os.path.join(self.pasta, NICHO_T))
                  if addon.chapas.MARCA_CHAPA in i["props"]]
        self.assertEqual(len(chapas), 4)
        self.assertTrue(all(i["props"].get("chapa_uid") for i in chapas))

    def test_refiliar_com_item_sem_arquivo_segue_com_os_outros(self):
        itens = self.indice()
        itens.append({"nome": "Fantasma", "arquivo": "Fantasma.blend",
                      "n1": "Portas", "n2": "Abrir", "n3": "",
                      "tipo": "objeto"})
        addon.biblioteca._gravar_indice(self.pasta, itens)
        addon.biblioteca._atualizar_item(self.pasta, CHAPA_T,
                              {"n1": "Puxadores", "n2": "Perfil", "n3": ""})
        # falha parcial e' WARNING (nao derruba o operador)
        r = bpy.ops.object.cabinet_refiliar('EXEC_DEFAULT')
        self.assertEqual(r, {'FINISHED'})
        self.assertEqual(self.catalogo_no_arquivo(CHAPA_T)["catalogo"],
                         ler_cats(self.pasta)[
                             "Cabinet Creator/Puxadores/Perfil"])
        self.assertFalse(os.path.exists(
            os.path.join(self.pasta, "Fantasma.blend")))

    def test_regerar_previews_grava_a_foto_de_cada_preset(self):
        cores = {CHAPA_T: (1.0, 0.0, 0.0, 1.0), NICHO_T: (0.0, 0.0, 1.0, 1.0)}
        for arq, cor in cores.items():
            png_solido(os.path.join(
                self.pasta, os.path.splitext(arq)[0] + ".png"), cor)
        cat_antes = {a: self.catalogo_no_arquivo(a)["catalogo"]
                     for a in cores}
        r = bpy.ops.object.cabinet_regerar_previews('EXEC_DEFAULT')
        self.assertEqual(r, {'FINISHED'})
        lado = (addon.biblioteca.LADO_PREVIEW, addon.biblioteca.LADO_PREVIEW)
        for arq, cor in cores.items():
            info = self.catalogo_no_arquivo(arq)
            self.assertIsNotNone(info["preview"], arq)
            img, icone, px = info["preview"]
            self.assertEqual(img, lado)
            self.assertEqual(icone, lado)
            for a, b in zip(px, cor):
                self.assertAlmostEqual(a, b, delta=0.02, msg=arq)
            # a preview nao mexe no catalogo
            self.assertEqual(info["catalogo"], cat_antes[arq])

    def test_regerar_previews_sem_foto_nao_toca_no_blend(self):
        png_solido(os.path.join(self.pasta, "Nicho_Teste.png"),
                   (0.0, 1.0, 0.0, 1.0))
        antes = self.texto(CHAPA_T)           # Chapa_Teste.png nao existe
        r = bpy.ops.object.cabinet_regerar_previews('EXEC_DEFAULT')
        self.assertEqual(r, {'FINISHED'})
        self.assertEqual(self.texto(CHAPA_T), antes)
        img, _i, px = self.catalogo_no_arquivo(NICHO_T)["preview"]
        self.assertEqual(img, (addon.biblioteca.LADO_PREVIEW, addon.biblioteca.LADO_PREVIEW))
        self.assertAlmostEqual(px[1], 1.0, delta=0.02)


# ====================================================== MATERIAIS
class TestMateriais(BaseBiblioteca):
    """Biblioteca de materiais (MDF/MDP): catalogo, cascata, aplicar a
    cor solida na selecao, criar/editar/apagar e a grade na gaveta."""

    def setUp(self):
        super().setUp()
        s = bpy.context.scene
        s.cabinet_bib_modo = 'MATERIAIS'
        s.cabinet_mat_n1 = s.cabinet_mat_n2 = s.cabinet_mat_n3 = ""
        addon.perguntas._pergunta_atual[0] = None
        addon.materiais._apagar_pendente[0] = None
        addon.materiais._pintar_pendente[0] = None
        for mat in list(bpy.data.materials):
            bpy.data.materials.remove(mat)

    def test_pintura_rapida_por_comodo_e_por_parte(self):
        # pedido do usuario: botao direito no material (cabinet_pintar_modulos)
        # -> quais modulos (por comodo) -> tudo, so' a caixa ou so' as portas
        M = addon.modulos
        cozinha = M.criar_armario(bpy.context, "Balcao", 800, 720, 550)
        porta = addon.portas.porta_no_modulo(cozinha, 2)
        quarto = M.criar_armario(bpy.context, "Roupeiro", 600, 2400, 550)
        solto = M.criar_armario(bpy.context, "Solto", 400, 600, 450)
        cena = bpy.context.scene
        addon.orcamento.definir_comodo(cena, [cozinha], 'Cozinha')
        addon.orcamento.definir_comodo(cena, [quarto], 'Quarto')
        grafite = self.item('MDF', 'Unicolores', 'Grafite')
        P = addon.materiais

        def cor(pecas):
            return {p.material_slots[0].material.name
                    if p.material_slots and p.material_slots[0].material else None
                    for p in pecas}

        def responder(rotulo):
            pergunta = addon.perguntas._pergunta_atual[0]
            rotulos = [o[0] for o in pergunta['opcoes']]
            return bpy.ops.object.cabinet_responder_pergunta(opcao=rotulos.index(rotulo))
        self.assertTrue(P.perguntar_pintar(bpy.context, grafite))
        pergunta = addon.perguntas._pergunta_atual[0]
        self.assertTrue(pergunta['na_gaveta'] and pergunta['biblioteca'])
        self.assertEqual([o[0] for o in pergunta['opcoes']],
                         ['Cozinha (1)', 'Quarto (1)', 'Sem comodo (1)', 'Todos (3)',
                          'Cancelar'])
        self.assertEqual(responder('Cozinha (1)'), {'CANCELLED'})   # so' perguntou
        pergunta = addon.perguntas._pergunta_atual[0]
        self.assertEqual([o[0] for o in pergunta['opcoes']],
                         ['Tudo', "So' a caixa", "So' as portas", 'Cancelar'])
        self.assertEqual(P._pintar_pendente[0], grafite['chave'])
        self.assertEqual(responder("So' a caixa"), {'FINISHED'})
        self.assertIsNone(P._pintar_pendente[0])
        caixa = P.pecas_do_modulo(cozinha, 'CAIXA')
        folhas = P.pecas_do_modulo(cozinha, 'PORTAS')
        self.assertEqual(len(caixa), 5)                   # com o fundo
        self.assertEqual(set(folhas), set(addon.portas._folhas_portas(porta)))
        self.assertEqual(cor(caixa), {'MDF Grafite'})
        self.assertEqual(cor(folhas), {None})             # porta nao
        self.assertEqual(cor(P.pecas_do_modulo(quarto, 'TUDO')), {None})
        # todos os modulos, so' as portas
        areia = self.item('MDF', 'Unicolores', 'Areia')
        P.perguntar_pintar(bpy.context, areia)
        responder('Todos (3)')
        self.assertEqual(responder("So' as portas"), {'FINISHED'})
        self.assertEqual(cor(folhas), {'MDF Areia'})
        self.assertEqual(cor(caixa), {'MDF Grafite'})
        # tudo do quarto; e Cancelar nao pinta nada
        P.perguntar_pintar(bpy.context, areia)
        responder('Quarto (1)')
        responder('Tudo')
        self.assertEqual(cor(P.pecas_do_modulo(quarto, 'TUDO')), {'MDF Areia'})
        P.perguntar_pintar(bpy.context, grafite)
        self.assertEqual(responder('Cancelar'), {'CANCELLED'})
        self.assertIsNone(P._pintar_pendente[0])
        self.assertEqual(cor(P.pecas_do_modulo(solto, 'TUDO')), {None})

    def test_caixa_da_pintura_abre_sob_o_material_e_quebra_as_respostas(self):
        M = addon.modulos
        cena = bpy.context.scene
        for nome in ('Cozinha', 'Quarto', 'Sala', 'Banheiro'):
            conj = M.criar_armario(bpy.context, nome, 400, 600, 450)
            addon.orcamento.definir_comodo(cena, [conj], nome)
        it = self.item('MDP', 'Unicolores', 'Grafite')
        cena.cabinet_mat_n1, cena.cabinet_mat_n2 = 'MDP', 'Unicolores'
        addon.materiais.perguntar_pintar(bpy.context, it)
        self.assertEqual(len(addon.perguntas._pergunta_atual[0]['opcoes']), 6)
        for largura in (190, 320, 564):
            ws = addon.gaveta._widgets_gaveta(bpy.context, largura, 1400)
            (caixa,) = [w for w in ws if w[5] == ('pergunta',)]
            alvo = next(w for w in ws if w[5] and w[5][0] == 'material'
                        and w[5][1]['chave'] == it['chave'])
            self.assertLess(caixa[1] + caixa[3], alvo[1] - 24)   # logo abaixo
            respostas = [w for w in ws if w[5] and w[5][0] == 'resposta']
            self.assertEqual(len(respostas), 6)
            for r in respostas:
                # dentro da caixa e nunca espremida
                self.assertGreaterEqual(r[0], caixa[0])
                self.assertLessEqual(r[0] + r[2], caixa[0] + caixa[2] + 0.01)
                self.assertGreaterEqual(r[1], caixa[1])
                self.assertGreaterEqual(r[2], addon.gaveta.LARGURA_MIN_RESPOSTA - 0.01)
            for a in respostas:
                for b in respostas:
                    if a is not b:
                        self.assertFalse(a[0] < b[0] + b[2] and b[0] < a[0] + a[2]
                                         and a[1] < b[1] + b[3] and b[1] < a[1] + a[3])

    def tearDown(self):
        bpy.context.scene.cabinet_bib_modo = 'MODULOS'
        addon.perguntas._pergunta_atual[0] = None
        super().tearDown()

    def arquivo(self):
        return os.path.join(self.pasta, addon.materiais.NOME_ARQUIVO)

    def item(self, n1, n2, nome):
        return addon.materiais.achar("%s/%s//%s" % (n1, n2, nome))

    def selecionar(self, obj):
        for o in bpy.context.selected_objects:
            o.select_set(False)
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        return obj

    def modulo(self):
        bpy.ops.object.cabinet_criar_nicho()
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.cabinet_agrupar()
        return self.selecionar(bpy.context.object)

    def test_catalogo_de_fabrica_sem_arquivo(self):
        self.assertFalse(os.path.exists(self.arquivo()))
        itens = addon.materiais.ler_materiais()
        self.assertEqual(addon.materiais.filhos_n1(itens), ['MDF', 'MDP'])
        self.assertEqual(len({it['chave'] for it in itens}), len(itens))
        for it in itens:
            self.assertRegex(it['cor'], r'^#[0-9A-F]{6}$')
        self.assertIsNotNone(self.item('MDF', 'Unicolores', 'Branco TX'))
        self.assertIsNotNone(self.item('MDP', 'Madeirados', 'Freijo'))

    def test_navegar_usa_a_cascata_dos_materiais(self):
        s = bpy.context.scene
        s.chapa_n1 = 'Armarios'
        bpy.ops.object.cabinet_navegar(nivel=1, valor='MDF')
        bpy.ops.object.cabinet_navegar(nivel=2, valor='Madeirados')
        self.assertEqual((s.cabinet_mat_n1, s.cabinet_mat_n2), ('MDF', 'Madeirados'))
        self.assertEqual(s.chapa_n1, 'Armarios')       # a outra nao muda
        bpy.ops.object.cabinet_navegar(nivel=1, valor='MDP')
        self.assertEqual((s.cabinet_mat_n1, s.cabinet_mat_n2), ('MDP', ''))

    def test_aplicar_no_modulo_pinta_todas_as_chapas(self):
        modulo = self.modulo()
        it = self.item('MDF', 'Unicolores', 'Grafite')
        r = bpy.ops.object.cabinet_aplicar_material(chave=it['chave'])
        self.assertEqual(r, {'FINISHED'})
        mat = addon.materiais.material_da_chave(it['chave'])
        self.assertEqual(mat.name, 'MDF Grafite')
        for c, esperado in zip(mat.diffuse_color[:3],
                               addon.materiais.rgb_linear(it['cor'])):
            self.assertAlmostEqual(c, esperado, places=4)
        chapas = [o for o in modulo.children_recursive
                  if addon.chapas.MARCA_CHAPA in o]
        self.assertEqual(len(chapas), 4)
        for chapa in chapas:
            self.assertEqual([s.link for s in chapa.material_slots], ['OBJECT'])
            self.assertIs(chapa.material_slots[0].material, mat)
        self.assertEqual(addon.materiais.chave_aplicada(modulo), it['chave'])
        # outro material troca; reaplicar nao duplica o Material
        outro = self.item('MDP', 'Madeirados', 'Carvalho')
        bpy.ops.object.cabinet_aplicar_material(chave=outro['chave'])
        self.assertEqual(chapas[0].material_slots[0].material.name, 'MDP Carvalho')
        bpy.ops.object.cabinet_aplicar_material(chave=it['chave'])
        self.assertEqual(len(bpy.data.materials), 2)
        self.assertIs(chapas[0].material_slots[0].material, mat)

    def test_aplicar_sem_selecao_cancela(self):
        self.modulo().select_set(False)
        it = self.item('MDF', 'Unicolores', 'Grafite')
        r = bpy.ops.object.cabinet_aplicar_material(chave=it['chave'])
        self.assertEqual(r, {'CANCELLED'})
        self.assertEqual(len(bpy.data.materials), 0)

    def test_material_sobrevive_a_malha_refeita(self):
        chapa = self.selecionar(self.chapa())
        it = self.item('MDF', 'Madeirados', 'Freijo')
        bpy.ops.object.cabinet_aplicar_material(chave=it['chave'])
        chapa.chapa_largura_mm = 750.0
        addon.chapas.gerar_malha_chapa(chapa)
        self.assertEqual(chapa.material_slots[0].material.get(
            addon.materiais.CHAVE_MATERIAL), it['chave'])

    def test_porta_pinta_folhas_e_moldura_nunca_ferragem_nem_puxador(self):
        grupo = bpy.data.objects.new('Porta', None)
        grupo[addon.chapas.MARCA_PORTAS] = 1
        bpy.context.scene.collection.objects.link(grupo)
        pecas = {}
        for nome, marca in (('Folha', addon.chapas.MARCA_FOLHA),
                            ('Moldura', addon.chapas.MARCA_MOLDURA),
                            ('Dobradica', addon.ferragens.CHAVE_FERRAGEM),
                            ('Puxador', addon.chapas.MARCA_PUXADOR)):
            obj = bpy.data.objects.new(nome, bpy.data.meshes.new(nome))
            obj[marca] = 1
            obj.parent = grupo
            bpy.context.scene.collection.objects.link(obj)
            pecas[nome] = obj
        self.assertEqual(set(addon.materiais.pecas_dos_alvos([grupo])),
                         {pecas['Folha'], pecas['Moldura']})
        # duplo clique: a folha sozinha
        self.assertEqual(addon.materiais.pecas_dos_alvos([pecas['Folha']]),
                         [pecas['Folha']])
        self.assertEqual(addon.materiais.pecas_dos_alvos([pecas['Puxador']]), [])
        # solta sobre a folha (fora da selecao): a porta inteira
        for o in bpy.context.selected_objects:
            o.select_set(False)
        self.assertEqual(set(addon.materiais.pecas_do_solte(pecas['Folha'], [])),
                         {pecas['Folha'], pecas['Moldura']})

    def test_um_clique_na_esfera_nao_aplica_so_o_duplo(self):
        # pedido do usuario: um clique errado nao pode pintar nada
        duplo = addon.materiais.duplo_clique_na_esfera
        a, b = 'MDF/Unicolores//Areia', 'MDF/Unicolores//Fendi'
        self.assertFalse(duplo(a, 100, 100, 350, agora=10.0))
        self.assertTrue(duplo(a, 104, 103, 350, agora=10.2))
        # o 3o clique comeca outro duplo
        self.assertFalse(duplo(a, 104, 103, 350, agora=10.3))
        # devagar, longe ou em outra esfera: e' um 1o clique de novo
        self.assertFalse(duplo(a, 104, 103, 350, agora=11.0))
        self.assertFalse(duplo(a, 140, 103, 350, agora=11.1))
        self.assertFalse(duplo(b, 140, 103, 350, agora=11.2))
        self.assertTrue(duplo(b, 140, 103, 350, agora=11.3))
        self.assertIsNone(addon.materiais._clique_esfera[0])

    def test_soltar_a_esfera_pinta_o_que_esta_embaixo(self):
        a = self.modulo()
        chapas_a = [o for o in a.children_recursive if addon.chapas.MARCA_CHAPA in o]
        antes = set(bpy.data.objects)
        bpy.ops.object.cabinet_criar_nicho()
        for o in bpy.data.objects:
            o.select_set(o not in antes)
        bpy.ops.object.cabinet_agrupar()
        b = bpy.context.object
        chapas_b = [o for o in b.children_recursive if addon.chapas.MARCA_CHAPA in o]
        self.assertTrue(chapas_b and not set(chapas_a) & set(chapas_b))
        grafite = self.item('MDF', 'Unicolores', 'Grafite')
        areia = self.item('MDF', 'Unicolores', 'Areia')

        def nomes(chapas):
            return {c.material_slots[0].material.name if c.material_slots
                    else None for c in chapas}
        # B selecionado, solta sobre uma chapa de A: pinta A, nao B
        self.selecionar(b)
        r = bpy.ops.object.cabinet_aplicar_material(
            chave=grafite['chave'], alvo=chapas_a[0].name)
        self.assertEqual(r, {'FINISHED'})
        self.assertEqual(nomes(chapas_a), {'MDF Grafite'})
        self.assertEqual(nomes(chapas_b), {None})
        # peca isolada (duplo clique) e solta sobre ela: so' ela
        self.selecionar(chapas_a[1])
        bpy.ops.object.cabinet_aplicar_material(
            chave=areia['chave'], alvo=chapas_a[1].name)
        self.assertEqual(chapas_a[1].material_slots[0].material.name, 'MDF Areia')
        self.assertEqual(nomes(chapas_a[:1] + chapas_a[2:]), {'MDF Grafite'})
        # nada embaixo que leve material: cancela sem pintar
        r = bpy.ops.object.cabinet_aplicar_material(
            chave=areia['chave'], alvo='Nao Existe')
        self.assertEqual(r, {'CANCELLED'})
        self.assertEqual(nomes(chapas_b), {None})

    def test_novo_material_grava_na_biblioteca(self):
        r = bpy.ops.object.cabinet_novo_material(
            'EXEC_DEFAULT', nome='Verde Salvia', cor=(0.5, 0.6, 0.5),
            n1='MDF', n2='Unicolores', n3='')
        self.assertEqual(r, {'FINISHED'})
        with open(self.arquivo(), encoding='utf-8') as f:
            gravados = json.load(f)
        self.assertEqual(len(gravados), len(addon.materiais.MATERIAIS_PADRAO) + 1)
        novo = self.item('MDF', 'Unicolores', 'Verde Salvia')
        self.assertEqual(novo['cor'], '#809980')
        # mesmo nome na mesma categoria: recusado, nada gravado
        antes = self.texto(addon.materiais.NOME_ARQUIVO)
        with self.assertRaises(RuntimeError):
            bpy.ops.object.cabinet_novo_material(
                'EXEC_DEFAULT', nome='Verde Salvia', n1='MDF', n2='Unicolores')
        self.assertEqual(self.texto(addon.materiais.NOME_ARQUIVO), antes)

    def test_editar_material_acompanha_o_material_aplicado(self):
        chapa = self.selecionar(self.chapa())
        it = self.item('MDF', 'Unicolores', 'Areia')
        bpy.ops.object.cabinet_aplicar_material(chave=it['chave'])
        r = bpy.ops.object.cabinet_editar_material(
            'EXEC_DEFAULT', chave=it['chave'], nome='Areia Clara',
            cor=(0.9, 0.85, 0.8), n1='MDF', n2='Unicolores', n3='')
        self.assertEqual(r, {'FINISHED'})
        self.assertIsNone(self.item('MDF', 'Unicolores', 'Areia'))
        novo = self.item('MDF', 'Unicolores', 'Areia Clara')
        mat = chapa.material_slots[0].material
        self.assertEqual(mat.get(addon.materiais.CHAVE_MATERIAL), novo['chave'])
        self.assertEqual(mat.name, 'MDF Areia Clara')
        self.assertAlmostEqual(mat.diffuse_color[0],
                               addon.materiais.rgb_linear(novo['cor'])[0], places=4)

    def test_apagar_pergunta_na_biblioteca_e_so_apaga_no_sim(self):
        it = self.item('MDP', 'Unicolores', 'Grafite')
        s = bpy.context.scene
        s.cabinet_mat_n1, s.cabinet_mat_n2 = 'MDP', 'Unicolores'
        addon.materiais.perguntar_apagar(bpy.context, it)
        pergunta = addon.perguntas._pergunta_atual[0]
        self.assertTrue(pergunta['na_gaveta'] and pergunta['biblioteca'])
        ws = addon.gaveta._widgets_gaveta(bpy.context, 480, 1400)
        caixa = [w for w in ws if w[5] == ('pergunta',)]
        self.assertEqual(len(caixa), 1)            # so' na biblioteca
        alvo = next(w for w in ws if w[5] and w[5][0] == 'material'
                    and w[5][1]['chave'] == it['chave'])
        # logo abaixo da fila do material (e dos botoes dela)
        topo_caixa = caixa[0][1] + caixa[0][3]
        self.assertLess(topo_caixa, alvo[1] - 24)
        self.assertGreater(topo_caixa, alvo[1] - 40)
        bpy.ops.object.cabinet_responder_pergunta(opcao=1)      # Nao
        self.assertIsNotNone(self.item('MDP', 'Unicolores', 'Grafite'))
        addon.materiais.perguntar_apagar(bpy.context, it)
        bpy.ops.object.cabinet_responder_pergunta(opcao=0)      # Sim
        self.assertIsNone(self.item('MDP', 'Unicolores', 'Grafite'))
        self.assertIsNone(addon.materiais._apagar_pendente[0])
        # direto, sem a pergunta: "Nao" cancela; material que nao existe tambem
        preto = self.item('MDP', 'Unicolores', 'Preto TX')
        apagar = bpy.ops.object.cabinet_apagar_material
        self.assertEqual(apagar(chave=preto['chave'], apagar=False), {'CANCELLED'})
        self.assertEqual(apagar(chave='MDP/Unicolores//Fantasma'), {'CANCELLED'})
        self.assertEqual(apagar(chave=preto['chave']), {'FINISHED'})
        self.assertIsNone(self.item('MDP', 'Unicolores', 'Preto TX'))

    def test_esfera_sombreada_com_fundo_transparente(self):
        lado = 32
        px = addon.materiais.esfera_rgba((0.2, 0.4, 0.8), lado)
        self.assertEqual(len(px), lado * lado * 4)

        def pixel(linha, coluna):
            i = (linha * lado + coluna) * 4
            return px[i:i + 4]
        self.assertEqual(pixel(0, 0)[3], 0.0)                     # canto: fundo
        self.assertEqual(pixel(lado // 2, lado // 2)[3], 1.0)     # meio: esfera
        # a luz vem de cima a' esquerda (linha 0 embaixo): ali e' mais claro
        claro = pixel(lado * 3 // 4, lado // 4)
        escuro = pixel(lado // 4, lado * 3 // 4)
        self.assertGreater(claro[2], escuro[2])

    def test_gaveta_mostra_cascata_e_esferas_dos_materiais(self):
        s = bpy.context.scene
        self.selecionar(self.chapa())
        it = self.item('MDF', 'Madeirados', 'Nogueira')
        bpy.ops.object.cabinet_aplicar_material(chave=it['chave'])
        s.cabinet_mat_n1, s.cabinet_mat_n2 = 'MDF', 'Madeirados'
        madeirados = sum(1 for m in addon.materiais.MATERIAIS_PADRAO
                         if m[:2] == ('MDF', 'Madeirados'))
        for largura in (190, 320, 480, 564):
            ws = addon.gaveta._widgets_gaveta(bpy.context, largura, 1400)
            limite = min(largura - 12, 552)
            self.assertFalse([w[4] for w in ws if w[0] + w[2] > limite + 0.01])
            modos = [w for w in ws if w[5] and w[5][0] == 'biblioteca']
            titulo = next(w for w in ws if w[4] == 'Biblioteca' and w[5] is None)
            self.assertEqual([m[5][1] for m in modos], ['MODULOS', 'MATERIAIS'])
            self.assertEqual([m[5][2] for m in modos], [False, True])  # aceso
            # ao lado do titulo quando cabe; senao, na linha de baixo
            reserva = 12 if any(w[5] and w[5][:2] ==
                ('rolagem', addon.gaveta._CHAVE_ROLAGEM_BIB) for w in ws) else 0
            self.assertEqual(abs(modos[0][1] - titulo[1]) < 1, largura - reserva >= 320,
                             largura)
            esferas = [w for w in ws if w[5] and w[5][0] == 'material']
            self.assertEqual(len(esferas), madeirados)
            self.assertEqual([e[4] for e in esferas if e[5][2]], ['Nogueira'])
            botoes = [w for w in ws if w[5] and w[5][0] == 'material_item']
            self.assertEqual(len(botoes), 2 * len(esferas))
            self.assertEqual([addon.gaveta_eventos._icone_acao_gaveta(b[5])
                              for b in botoes[:2]], ['GREASEPENCIL', 'TRASH'])
            self.assertIn('object.cabinet_novo_material',
                          [w[5][1] for w in ws if w[5] and w[5][0] == 'operador'])
        # Modulos: a cascata dos presets volta, com o "Salvar +"
        s.cabinet_bib_modo = 'MODULOS'
        ws = addon.gaveta._widgets_gaveta(bpy.context, 480, 1400)
        self.assertFalse([w for w in ws if w[5] and w[5][0] == 'material'])
        self.assertIn('object.cabinet_salvar_biblioteca',
                      [w[5][1] for w in ws if w[5] and w[5][0] == 'operador'])


# ====================================================== execucao
addon.register()
CASOS = (TestIndice, TestCatalogos, TestGravacao, TestOperadores,
         TestInsercao, TestPresetsDeFabrica, TestOperadoresDeLote,
         TestMateriais)
suite = unittest.TestSuite(
    unittest.defaultTestLoader.loadTestsFromTestCase(c) for c in CASOS)
resultado = unittest.TextTestRunner(verbosity=2).run(suite)
addon.unregister()
shutil.rmtree(_PASTA_GUARDA, ignore_errors=True)
intacta = impressao_digital(PASTA_REAL) == DIGITAL_REAL
if not intacta:
    print("[biblioteca] A PASTA REAL DA BIBLIOTECA MUDOU:", PASTA_REAL)
if not resultado.wasSuccessful() or not intacta:
    raise RuntimeError('Falha nos testes de biblioteca')
