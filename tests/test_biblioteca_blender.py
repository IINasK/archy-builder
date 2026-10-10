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
    for c in bpy.data.collections:
        if c not in antes_col:
            bpy.data.collections.remove(c)
    for o in list(bpy.data.objects):
        if o not in antes_obj:
            bpy.data.objects.remove(o, do_unlink=True)
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
        shutil.copytree(PASTA_REAL, self.pasta,
                        ignore=shutil.ignore_patterns("__pycache__", "*.md"))
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
    """Os arquivos REAIS da biblioteca (sempre pela copia temporaria)."""

    def exigir_legivel(self, arquivo):
        pular_no_4x(self)
        self.assertTrue(legivel(os.path.join(self.pasta, arquivo)), arquivo)

    def test_indice_de_fabrica_e_consistente(self):
        itens = self.indice()
        self.assertTrue(itens)
        arquivos = [i["arquivo"] for i in itens]
        self.assertEqual(len(arquivos), len(set(arquivos)))
        for it in itens:
            self.assertEqual(it["arquivo"], os.path.basename(it["arquivo"]))
            self.assertTrue(os.path.exists(
                os.path.join(self.pasta, it["arquivo"])), it["arquivo"])
            # todo preset nasce com foto (CLAUDE.md, armadilhas por area)
            png = os.path.splitext(it["arquivo"])[0] + ".png"
            self.assertTrue(os.path.exists(os.path.join(self.pasta, png)),
                            png)
            self.assertIn(it.get("tipo"), ("modulo", "objeto"))
            self.assertIn(addon.biblioteca._niveis_de(it)[0], addon.biblioteca.ARVORE)
            self.assertNotIn("pasta", it)
            self.assertNotIn("origem", it)
        # todo .blend da pasta esta' no indice (nenhum orfao commitado)
        soltos = [a for a in os.listdir(self.pasta)
                  if a.endswith(".blend") and a not in arquivos]
        self.assertEqual(soltos, [])

    def test_cats_de_fabrica_tem_uuid_unico_e_raiz_unica(self):
        cats = ler_cats(self.pasta)
        self.assertEqual(len(set(cats.values())), len(cats))
        for cam in cats:
            self.assertTrue(cam == addon.biblioteca.CAT_RAIZ
                            or cam.startswith(addon.biblioteca.CAT_RAIZ + "/"), cam)
        for cam in addon.biblioteca.caminhos_catalogo():
            self.assertIn(cam, cats)

    def test_presets_de_fabrica_abrem_nesta_versao(self):
        pular_no_4x(self)
        for it in self.indice():
            self.assertTrue(legivel(os.path.join(self.pasta, it["arquivo"])),
                            it["arquivo"])

    def test_catalogo_de_cada_preset_bate_com_o_indice(self):
        cats = ler_cats(self.pasta)
        for it in self.indice():
            self.exigir_legivel(it["arquivo"])
            esperado = cats[addon.biblioteca.catalogo_de(*addon.biblioteca._niveis_de(it))]
            assets = [i for _n, i in ler_blend(
                os.path.join(self.pasta, it["arquivo"])) if i["asset"]]
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
            esperado = cats[addon.biblioteca.catalogo_de(*addon.biblioteca._niveis_de(it))]
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


# ====================================================== execucao
addon.register()
CASOS = (TestIndice, TestCatalogos, TestGravacao, TestOperadores,
         TestInsercao, TestPresetsDeFabrica, TestOperadoresDeLote)
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
