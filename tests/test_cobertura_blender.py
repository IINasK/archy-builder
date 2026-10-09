"""Execute: blender --background --factory-startup --python-exit-code 1 --python tests/test_cobertura_blender.py

TRAVA DE COBERTURA do harness. Falha quando:
- uma classe registrada (operador, gizmo, painel, prateleira...) nao e'
  citada por NENHUM teste e nao esta' em SEM_TESTE_ACEITO com motivo;
- uma entrada de SEM_TESTE_ACEITO ja' ganhou teste (a lista so' encolhe);
- uma suite nao tem piso no executor (teste apagado passaria calado);
- um snapshot gravado nao e' mais conferido por ninguem.

Funcionalidade nova sem teste quebra AQUI, no dia em que entra -- nao
meses depois, quando alguem percebe que parou de funcionar.
"""
import glob
import os
import re
import sys
import unittest

import bpy  # noqa: F401  (o executor roda tudo dentro do Blender)

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
import cabinet_creator as addon  # noqa: E402

# Classe -> por que ainda nao tem teste. So' pode ENCOLHER: ao cobrir
# uma delas, apague a linha (o teste abaixo cobra isso).
SEM_TESTE_ACEITO = {
    'CabinetCreatorPreferences':
        "AddonPreferences so' existe com o add-on HABILITADO; os testes "
        "carregam o modulo direto (fallback `_opcao`, que e' testado)",
    'OBJECT_OT_abrir_pasta_biblioteca':
        'abre o Explorer do Windows: efeito fora do Blender',
    'OBJECT_OT_abrir_asset_browser':
        "so' o painel legado (nao registrado) chama; divide area",
    'OBJECT_OT_prateleira': 'alterna a AssetShelf: precisa de janela',
    'VIEW3D_AST_cabinet_creator': 'AssetShelf: arraste nativo do Blender',
    'OBJECT_OT_registrar_bibliotecas':
        'mexe nas preferencias do USUARIO (asset_libraries)',
    'OBJECT_OT_modo_medidas':
        "so' o painel legado (nao registrado) chama",
    'OBJECT_OT_definir_tamanho':
        "so' o painel legado (nao registrado) chama",
}


def _texto_dos_testes():
    arquivos = [c for c in glob.glob(os.path.join(AQUI, '*.py'))
                if os.path.basename(c) != os.path.basename(__file__)]
    textos = []
    for caminho in arquivos:
        with open(caminho, encoding='utf-8') as f:
            textos.append(f.read())
    return '\n'.join(textos)


def _chaves(classe):
    chaves = {classe.__name__}
    idname = getattr(classe, 'bl_idname', '') or ''
    if '.' in idname:
        chaves.add(idname.split('.', 1)[1])      # cabinet_xxx
    elif idname and idname not in (classe.__name__, addon.__name__):
        # o bl_idname das Preferencias e' o nome do PACOTE, que aparece em
        # todo 'import cabinet_creator': contaria como teste sem ser
        chaves.add(idname)
    return chaves


class TestCobertura(unittest.TestCase):

    def setUp(self):
        self.texto = _texto_dos_testes()

    def citado(self, classe):
        return any(re.search(r'\b%s\b' % re.escape(k), self.texto)
                   for k in _chaves(classe))

    def test_toda_classe_registrada_tem_teste(self):
        sem = sorted(c.__name__ for c in addon.CLASSES
                     if not self.citado(c)
                     and c.__name__ not in SEM_TESTE_ACEITO)
        self.assertFalse(sem, 'classe(s) sem NENHUM teste: %s -- escreva o '
                         'teste (ou justifique em SEM_TESTE_ACEITO)' % sem)

    def test_lista_de_excecoes_so_encolhe(self):
        nomes = {c.__name__ for c in addon.CLASSES}
        sobrando = sorted(n for n in SEM_TESTE_ACEITO if n not in nomes)
        self.assertFalse(sobrando, 'excecao para classe que nao existe '
                         'mais: %s' % sobrando)
        ja_cobertas = sorted(c.__name__ for c in addon.CLASSES
                             if c.__name__ in SEM_TESTE_ACEITO
                             and self.citado(c))
        self.assertFalse(ja_cobertas, "ja' tem teste, tire de "
                         'SEM_TESTE_ACEITO: %s' % ja_cobertas)

    def test_toda_suite_tem_piso_no_executor(self):
        with open(os.path.join(AQUI, 'rodar_testes.py'), encoding='utf-8') as f:
            executor = f.read()
        piso = re.search(r'PISO = \{(.*?)\}', executor, re.S).group(1)
        suites = [re.match(r'test_(.+)_blender\.py', os.path.basename(c)).group(1)
                  for c in glob.glob(os.path.join(AQUI, 'test_*_blender.py'))]
        suites += [os.path.splitext(os.path.basename(c))[0]
                   for c in glob.glob(os.path.join(AQUI, 'gui_*.py'))]
        sem_piso = sorted(s for s in suites if "'%s'" % s not in piso)
        self.assertFalse(sem_piso, 'suite sem piso em rodar_testes.PISO: %s'
                         % sem_piso)

    def test_todo_snapshot_e_conferido(self):
        with open(os.path.join(AQUI, 'test_snapshot_blender.py'),
                  encoding='utf-8') as f:
            suite = f.read()
        orfaos = sorted(
            os.path.splitext(os.path.basename(c))[0]
            for c in glob.glob(os.path.join(AQUI, 'snapshots', '*.json'))
            if "'%s'" % os.path.splitext(os.path.basename(c))[0] not in suite)
        self.assertFalse(orfaos, 'snapshot que ninguem confere: %s' % orfaos)


addon.register()
suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestCobertura)
resultado = unittest.TextTestRunner(verbosity=2).run(suite)
addon.unregister()
if not resultado.wasSuccessful():
    raise RuntimeError('Falha na trava de cobertura')
