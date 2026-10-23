"""Orcamento em .txt (botao nas Opcoes) e comodos (pastas no Outliner)."""

import os
import re

import bpy
from bpy.props import BoolProperty, StringProperty
from bpy.types import Operator
from bpy_extras.io_utils import ExportHelper

# usados so' ao RODAR (import circular): o __init__ liga estes
# apelidos depois de carregar todos (`_ligar_modulos`)
_chapas = _modulos = _eventos = _portas = _solda = _perguntas = None
_prateleiras = _gavetas = _materiais = None

# ======================================================== ORCAMENTO
# O add-on e' vendido: nada de "ERP" na tela. O botao "Gerar orcamento"
# (painel da engrenagem) pede onde salvar e grava um .txt -- o conteudo
# segue o padrao da empresa do usuario, que o ERP dela ja' le: Markdown
# no padrao de um prompt de ditado, um bloco ```markdown e, fora dele,
# as Pendencias. Daqui sai SO'
# a marcenaria; o resto do documento fica como o prompt manda quando nada
# foi dito (Limpeza geral, Valores e Pagamento vazios, perfil investidor).
# Nada se inventa: a linha do modulo e' o NOME do grupo e os detalhes
# (portas, prateleiras, divisorias, puxadores) saem do 3D.
# O COMODO e' uma PASTA no Outliner (pedido do usuario): Collection
# marcada, na raiz da cena, com as Collections dos armarios dentro. Ela
# e' a unica fonte: arrastar o armario para outra pasta no Outliner
# tambem muda o comodo do orcamento.
MARCA_COLECAO_COMODO = "eh_colecao_comodo"
ALVO_COMODO = '@comodo'                  # alvo da 'escolha' que grava o comodo
SUSPENSO_COMODO = 'comodo'               # lista que expande na aba Modulos
COMODO_NENHUM = ''                       # volta o armario a' raiz
COMODO_OUTRO = '@outro'                  # abre o campo do nome digitado
OP_EXPORTAR_ORCAMENTO = 'object.cabinet_exportar_orcamento'
# Os comodos do prompt, na ORDEM do orcamento (os digitados vem depois,
# em ordem alfabetica). Varanda e' Sacada (regra do prompt). Com acento:
# e' o nome da pasta e o texto que o ERP le.
COMODOS = (
    'Cozinha', 'Copa', 'Sala', 'Quarto', 'Su\u00edte', 'Quarto su\u00edte',
    'Banheiro', 'Banheiro da su\u00edte', 'Lavabo', 'Lavanderia',
    '\u00c1rea de servi\u00e7o', 'Sacada', 'Escrit\u00f3rio', 'Closet',
)
SINONIMOS_COMODO = {'varanda': 'Sacada'}
# depois de salvar: o botao mostra o que fez e as pendencias ficam a'
# vista ate' o proximo, uma troca de comodo ou este tempo
SEGUNDOS_ORCAMENTO_GERADO = 30.0
_orcamento_gerado = [None]       # {'modulos': n, 'pendencias': [...], 'arquivo'}
ARQUIVO_ORCAMENTO = 'Orçamento'     # nome sugerido no "Salvar como"
# Nome que o add-on deu sozinho: o usuario nao disse que modulo e'.
NOME_AUTOMATICO_MODULO = re.compile(r'^(Armario \d+x\d+x\d+|Conjunto)$')
# (singular, plural) por modelo de porta e de puxador
PALAVRAS_PORTA = {
    'CORRER': ('porta de correr', 'portas de correr'),
    'BASCULANTE': ('porta basculante', 'portas basculantes'),
    'EMBUTIDA': ('porta embutida', 'portas embutidas'),
    'GIRO': ('porta', 'portas'),
}
PALAVRAS_PUXADOR = {'PERFIL': 'perfil', 'ALCA': 'al\u00e7a', 'BORDA': 'borda'}
NOMES_DOBRADICA = {'RETA': 'reta', 'CURVA': 'curva',
                  'SUPER_CURVA': 'super curva', 'ARTICULADA': 'articulada'}


def _modulo_do_objeto(obj):
    """Modulo de qualquer coisa nossa: ele mesmo, uma chapa dele, a porta
    ligada a ele (folha ou grupo) ou o puxador de uma delas."""
    if obj is None:
        return None
    if _chapas.MARCA_CONJUNTO in obj:
        return obj
    if _chapas.MARCA_PUXADOR in obj:
        obj = obj.parent
    grupo = _portas._grupo_portas(obj)
    if grupo is not None:
        modulo = bpy.data.objects.get(grupo.get(_portas.CHAVE_MODULO_PORTA, ''))
        return modulo if modulo is not None and _chapas.MARCA_CONJUNTO in modulo else None
    return _portas._modulo_da_chapa(obj)


def _modulos_da_selecao(context):
    modulos = []
    for obj in [context.object, *(getattr(context, 'selected_objects', ())
                                   or ())]:
        modulo = _modulo_do_objeto(obj)
        if modulo is not None and modulo not in modulos:
            modulos.append(modulo)
    return modulos


def _nome_comodo(colecao):
    return _portas._sem_sufixo(colecao.name) if colecao is not None else ''


def _limpar_nome_comodo(nome):
    nome = ' '.join((nome or '').split())
    return SINONIMOS_COMODO.get(nome.casefold(), nome)


def _pais_da_colecao(colecao, cena):
    return [c for c in (cena.collection, *bpy.data.collections)
            if colecao.name in c.children]


def _comodo_do_modulo(conj):
    """Pasta de comodo onde mora a Collection do armario, ou None."""
    colecao = _modulos._colecao_do_modulo(conj)
    if colecao is None:
        return None
    return next((c for c in bpy.data.collections
                 if c.get(MARCA_COLECAO_COMODO)
                 and colecao.name in c.children), None)


def _comodos_da_cena(cena):
    """Pastas de comodo que estao na cena (por nome sem o .001)."""
    pastas = {}
    for c in cena.collection.children_recursive:
        if c.get(MARCA_COLECAO_COMODO):
            pastas.setdefault(_nome_comodo(c), c)
    return pastas


def _comodos_da_lista(cena):
    """O que a lista oferece: os do prompt e os ja' digitados na cena."""
    digitados = sorted((n for n in _comodos_da_cena(cena) if n not in COMODOS),
                       key=str.casefold)
    return [*COMODOS, *digitados]


def _ordem_comodo(nome):
    return ((0, COMODOS.index(nome), '') if nome in COMODOS
            else (1, 0, nome.casefold()))


def _colecao_do_comodo(cena, nome):
    pasta = _comodos_da_cena(cena).get(nome)
    if pasta is None:
        pasta = bpy.data.collections.new(nome)
        pasta[MARCA_COLECAO_COMODO] = 1
        cena.collection.children.link(pasta)
    return pasta


def _garantir_colecao_modulo(cena, conj):
    """Solda e comodo usam a mesma migracao da montagem legada."""
    return _modulos._garantir_colecao_modulo(cena, conj)


def _limpar_comodos_vazios():
    for pasta in [c for c in bpy.data.collections
                  if c.get(MARCA_COLECAO_COMODO)
                  and not c.all_objects and not c.children]:
        bpy.data.collections.remove(pasta)


def definir_comodo(cena, modulos, nome):
    """Poe a Collection de cada armario na pasta `nome` (vazio = raiz da
    cena). Devolve quantos armarios mudaram de lugar ou ja' estavam la'."""
    nome = _limpar_nome_comodo(nome)
    feitos = 0
    for conj in modulos:
        if conj is None or _chapas.MARCA_CONJUNTO not in conj:
            continue
        colecao = _garantir_colecao_modulo(cena, conj)
        destino = (_colecao_do_comodo(cena, nome) if nome
                   else cena.collection)
        # liga antes de desligar: a Collection nunca fica sem dono
        if colecao.name not in destino.children:
            destino.children.link(colecao)
        for pai in _pais_da_colecao(colecao, cena):
            if pai != destino:
                pai.children.unlink(colecao)
        feitos += 1
    _limpar_comodos_vazios()
    _orcamento_gerado[0] = None
    return feitos


def _abrir_caixa_comodo(context):
    """"Outro nome...": o mesmo campo da caixa do nome do grupo, logo
    abaixo da linha do comodo. Guarda os armarios: o clique fora pode
    mudar a selecao antes do Enter."""
    nomes = [m.name for m in _modulos_da_selecao(context)]
    _solda._nome_grupo_gaveta[0] = {'comodo': nomes, 'grupo': '', 'texto': '',
                             'cursor': 0, 'selecionado': False}
    op = 'object.cabinet_definir_comodo'
    _perguntas._pergunta_atual[0] = {
        'texto': 'Nome do comodo', 'campo': True, 'na_gaveta': True,
        'comodo': True,
        'opcoes': [('OK', 'CHECKMARK', op, {'digitado': True}),
                   ('Cancelar', 'X', op, {'manter': True})]}


def _confirmar_campo_gaveta(estado):
    """Enter/OK no campo da caixa preta: nome do grupo ou do comodo."""
    if estado.get('comodo') is not None:
        modulos = [bpy.data.objects.get(n) for n in estado['comodo']]
        nome = _limpar_nome_comodo(estado['texto'])
        return bool(nome) and bool(definir_comodo(
            bpy.context.scene, modulos, nome))
    return _modulos.nomear_grupo(bpy.data.objects.get(estado['grupo']), estado['texto'])


class OBJECT_OT_definir_comodo(Operator):
    """Poe os armarios selecionados na pasta do comodo (Outliner)"""
    bl_idname = 'object.cabinet_definir_comodo'
    bl_label = 'Comodo do Armario'
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}

    nome: StringProperty(name='Comodo', options={'SKIP_SAVE'})
    # OK / Cancelar da caixa do "Outro nome..."
    digitado: BoolProperty(options={'SKIP_SAVE', 'HIDDEN'})
    manter: BoolProperty(options={'SKIP_SAVE', 'HIDDEN'})

    def execute(self, context):
        estado = _solda._nome_grupo_gaveta[0]
        _eventos._redesenhar_viewports(context)
        if self.digitado or self.manter:
            _solda._nome_grupo_gaveta[0] = _perguntas._pergunta_atual[0] = None
            if self.manter or estado is None:
                return {'CANCELLED'}
            return ({'FINISHED'} if _confirmar_campo_gaveta(estado)
                    else {'CANCELLED'})
        if not definir_comodo(context.scene, _modulos_da_selecao(context),
                              self.nome):
            self.report({'WARNING'}, "Selecione um armario")
            return {'CANCELLED'}
        return {'FINISHED'}


def _quantos(n, palavras):
    singular, plural = palavras
    return '%d %s' % (n, singular if n == 1 else plural)


def _pecas_internas(conj):
    """(prateleiras, divisorias) no referencial do MODULO (girado vale):
    chapa deitada entre a de baixo e a de cima e chapa em pe' entre a da
    esquerda e a da direita. As das pontas sao base, tampo e laterais."""
    inversa = conj.matrix_world.to_3x3().normalized().inverted()
    posicoes = {0: [], 2: []}
    for chapa in _modulos._chapas_do_conjunto(conj):
        normal = inversa @ _chapas._eixos(chapa)[2]
        eixo = max(range(3), key=lambda i: abs(normal[i]))
        if eixo in posicoes:
            posicoes[eixo].append((inversa @ _chapas._centro(chapa))[eixo])

    def entre(valores):
        if len(valores) < 3:
            return 0
        baixo, alto = min(valores), max(valores)
        return sum(1 for v in valores
                   if baixo + _modulos.TOL_BORDA < v < alto - _modulos.TOL_BORDA)
    # mais as da aba Prateleiras (filhas do grupo delas, nao do modulo)
    return (entre(posicoes[2]) + _prateleiras.quantas_no_modulo(conj),
            entre(posicoes[0]))


def cadastro_do_modulo(conj):
    """Ficha atual do 3D, sem gravar contagens que envelhecem no preset."""
    bpy.context.view_layer.update()
    dep = bpy.context.evaluated_depsgraph_get()
    inversa = conj.matrix_world.to_quaternion().inverted().to_matrix()
    origem = conj.matrix_world.translation
    # O referencial tira so' a rotacao: escala real e edicoes da malha
    # entram na medida, sem incluir portas/gavetas abertas ou ferragens.
    pontos = []
    for peca in _modulos.pecas_do_envelope(conj):
        avaliada = peca.evaluated_get(dep)
        matriz = avaliada.matrix_world
        pontos.extend(inversa @ (matriz @ v.co - origem)
                      for v in avaliada.data.vertices)
    medidas = (tuple((max(p[i] for p in pontos) - min(p[i] for p in pontos))
                     * 1000.0 for i in (0, 2, 1)) if pontos else None)
    portas, dobradicas = {}, set()
    dobradicas_pendentes = False
    grupos = _portas._portas_do_conjunto(conj)
    for grupo in grupos:
        folhas = _portas._folhas_portas(grupo)
        if not folhas:
            continue
        p = grupo.get('porta_parametros') or {}
        abertura = p.get('abertura', 'GIRO')
        tipo = ('EMBUTIDA' if abertura == 'GIRO'
                and p.get('dobradica') == 'SUPER_CURVA' else abertura)
        portas[tipo] = portas.get(tipo, 0) + len(folhas)
        if abertura != 'CORRER':
            dobradica = p.get('dobradica')
            if dobradica in NOMES_DOBRADICA:
                dobradicas.add(dobradica)
            else:
                dobradicas_pendentes = True
            if p.get('dobradica_articulada') or (abertura == 'ZIGZAG' and len(folhas) > 1):
                dobradicas.add('ARTICULADA')
    gavetas = sum(1 for grupo in _gavetas.grupos_do_modulo(conj)
                  for gaveta in _gavetas.gavetas_do_grupo(grupo)
                  if any(_chapas.MARCA_CHAPA in o for o in gaveta.children_recursive))
    materiais, sem_material = set(), 0
    for peca in _materiais.pecas_dos_alvos([conj, *grupos]):
        # Slots guardados sem faces nao representam material utilizado.
        indices = {p.material_index for p in peca.data.polygons}
        faltando = not indices
        for i in indices:
            mat = peca.material_slots[i].material if i < len(peca.material_slots) else None
            if mat is None:
                faltando = True
                continue
            chave = mat.get(_materiais.CHAVE_MATERIAL, '')
            partes = chave.split('/') if isinstance(chave, str) else []
            nome = ('%s %s' % (partes[0], partes[-1])
                    if len(partes) >= 2 and partes[0] and partes[-1] else mat.name)
            materiais.add(nome)
        sem_material += int(faltando)
    prateleiras, divisorias = _pecas_internas(conj)
    return dict(medidas_mm=medidas, portas=portas,
                dobradicas=sorted(dobradicas), dobradicas_pendentes=dobradicas_pendentes,
                gavetas=gavetas, materiais=sorted(materiais, key=str.casefold),
                pecas_sem_material=sem_material,
                prateleiras=prateleiras, divisorias=divisorias)


def _detalhes_do_modulo(conj, puxadores, cadastro=None):
    """O 3o andar do orcamento: so' o que o modelo 3D TEM."""
    cadastro = cadastro if cadastro is not None else cadastro_do_modulo(conj)
    medidas = cadastro['medidas_mm']
    detalhes = [('Medidas gerais (largura x altura x profundidade): %s mm'
                 % ' x '.join(format(round(v, 2), '.2f').rstrip('0').rstrip('.')
                              for v in medidas)) if medidas else 'Medidas gerais nao identificadas']
    for tipo, n in cadastro['portas'].items():
        if n:
            detalhes.append(_quantos(n, PALAVRAS_PORTA.get(
                tipo, PALAVRAS_PORTA['GIRO'])))
    if not cadastro['portas']:
        detalhes.append('Sem portas')
    dobradicas = [NOMES_DOBRADICA[t] for t in cadastro['dobradicas']]
    if cadastro['dobradicas_pendentes']:
        dobradicas.append('nao identificada')
    detalhes.append('Dobradicas: ' + ', '.join(dobradicas) if dobradicas else 'Sem dobradicas')
    n = cadastro['gavetas']
    detalhes.append(_quantos(n, ('gaveta interna', 'gavetas internas'))
                    if n else 'Sem gavetas internas')
    prateleiras, divisorias = cadastro['prateleiras'], cadastro['divisorias']
    detalhes.append(_quantos(prateleiras, ('prateleira interna',
                                           'prateleiras internas'))
                    if prateleiras else 'Sem prateleiras internas')
    if divisorias:
        detalhes.append(_quantos(divisorias, ('divis\u00f3ria interna',
                                              'divis\u00f3rias internas')))
    for tipo, n in puxadores.items():
        palavra = PALAVRAS_PUXADOR.get(tipo, '')
        detalhes.append(_quantos(n, ('puxador ' + palavra, 'puxadores '
                                     + palavra)).strip())
    materiais = cadastro['materiais']
    detalhes.append('Materiais: ' + ', '.join(materiais) if materiais else 'Material nao identificado')
    if materiais and cadastro['pecas_sem_material']:
        detalhes.append(_quantos(cadastro['pecas_sem_material'],
                                 ('peca sem material', 'pecas sem material')))
    return detalhes


def _puxadores_por_modulo(objetos):
    """{modulo: {tipo: quantidade}} -- importado (sem tipo) conta como ''."""
    contas = {}
    for pux in objetos:
        if _chapas.MARCA_PUXADOR not in pux:
            continue
        modulo = _modulo_do_objeto(pux)
        if modulo is not None:
            tipos = contas.setdefault(modulo.name, {})
            tipo = pux.get('puxador_tipo', '')
            tipos[tipo] = tipos.get(tipo, 0) + 1
    return contas


def orcamento_da_cena(cena):
    """(texto, modulos exportados, pendencias) no padrao da empresa."""
    objetos = list(cena.objects)
    puxadores = _puxadores_por_modulo(objetos)
    por_comodo = {}
    pendencias = []
    modulos = sorted((o for o in objetos if _chapas.MARCA_CONJUNTO in o
                      and _modulos._chapas_do_conjunto(o)),
                     key=lambda o: o.name.casefold())
    for conj in modulos:
        nome = _portas._sem_sufixo(conj.name)
        comodo = _nome_comodo(_comodo_do_modulo(conj)) or None
        if NOME_AUTOMATICO_MODULO.match(nome):
            pendencias.append('- %s%s: n\u00e3o foi dito que m\u00f3dulo '
                              '\u00e9 (o nome do grupo ainda \u00e9 o '
                              'autom\u00e1tico).'
                              % (comodo + ', ' if comodo else '', nome))
        if comodo is None:
            pendencias.append('- %s: n\u00e3o foi dito o c\u00f4modo; o '
                              'm\u00f3dulo ficou fora do or\u00e7amento.'
                              % nome)
            continue
        cadastro = cadastro_do_modulo(conj)
        if cadastro['pecas_sem_material']:
            pendencias.append('- %s, %s: material nao identificado em %s.' % (
                comodo, nome, _quantos(cadastro['pecas_sem_material'], ('peca', 'pecas'))))
        if cadastro['dobradicas_pendentes']:
            pendencias.append('- %s, %s: tipo de dobradica nao identificado.' % (comodo, nome))
        por_comodo.setdefault(comodo, []).append(
            (nome, _detalhes_do_modulo(conj, puxadores.get(conj.name, {}), cadastro)))
    soltas = [o for o in objetos if _chapas.MARCA_CHAPA in o and _chapas.MARCA_FOLHA not in o
              and _portas._modulo_da_chapa(o) is None]
    if soltas:
        pendencias.append('- %s, fora de um arm\u00e1rio: n\u00e3o foi dito '
                          'a qual m\u00f3dulo pertence%s; ficou%s fora do '
                          'or\u00e7amento.' % (
                              _quantos(len(soltas), ('chapa solta',
                                                     'chapas soltas')),
                              'm' if len(soltas) > 1 else '',
                              'aram' if len(soltas) > 1 else ''))

    linhas = ['# Or\u00e7amento', 'cliente:', 'endereco:',
              'perfil: investidor', '']
    exportados = sum(len(v) for v in por_comodo.values())
    if exportados:
        # bloco sem conteudo nao tem cabecalho (regra do prompt)
        linhas += ['## M\u00f3veis', '']
        for comodo in sorted(por_comodo, key=_ordem_comodo):
            itens = por_comodo[comodo]
            linhas.append('### ' + comodo)
            for nome, detalhes in itens:
                linhas.append('- ' + nome)
                linhas += ['  - ' + d for d in detalhes]
            linhas.append('')
    # Limpeza: a unica coisa que entra sem pedir; sem Obras, e' a geral
    linhas += ['## Outros', '', '### Geral', '- Limpeza geral.', '',
               '## Valores', '- moveis:', '- obras:', '- eletros:',
               '- outros:', '',
               '## Pagamento', '- modalidade: entrada+parcelas',
               '- entrada:', '- parcelas:']
    texto = '```markdown\n' + '\n'.join(linhas) + '\n```\n\n'
    if pendencias:
        texto += ('Pend\u00eancias\n' + '\n'.join(pendencias)
                  + '\n\nQuer atualizar algum destes antes de eu refazer o '
                  'or\u00e7amento?\n')
    else:
        texto += 'Sem pend\u00eancias.\n'
    return texto, exportados, pendencias


def _apagar_orcamento_gerado():
    _orcamento_gerado[0] = None
    for janela in bpy.context.window_manager.windows:
        for area in janela.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
    return None


def _arquivo_sugerido():
    """Ao lado do .blend, com o nome dele; sem .blend salvo, na pasta do
    usuario (o "Salvar como" do Blender abriria na pasta do executavel)."""
    if bpy.data.filepath:
        pasta, nome = os.path.split(bpy.data.filepath)
        return os.path.join(pasta, '%s - %s.txt' % (
            ARQUIVO_ORCAMENTO, os.path.splitext(nome)[0]))
    return os.path.join(os.path.expanduser('~'), ARQUIVO_ORCAMENTO + '.txt')


class OBJECT_OT_exportar_orcamento(Operator, ExportHelper):
    """Salva o orcamento dos moveis da cena num arquivo de texto (.txt)"""
    bl_idname = OP_EXPORTAR_ORCAMENTO
    bl_label = "Gerar orcamento"

    filename_ext = '.txt'
    filter_glob: StringProperty(default='*.txt', options={'HIDDEN'})

    def invoke(self, context, event):
        if not self.filepath:
            self.filepath = _arquivo_sugerido()
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        texto, exportados, pendencias = orcamento_da_cena(context.scene)
        caminho = bpy.path.ensure_ext(bpy.path.abspath(self.filepath), '.txt')
        try:
            # UTF-8 (acentos dos comodos) e quebra de linha do sistema: o
            # Bloco de Notas abre direto
            with open(caminho, 'w', encoding='utf-8') as arquivo:
                arquivo.write(texto)
        except OSError as e:
            self.report({'ERROR'}, "Nao deu para salvar o orcamento: %s" % e)
            return {'CANCELLED'}
        # a gaveta mostra o que aconteceu (so' o relatorio na barra de
        # status passava despercebido: "copiar e nada acontece")
        _orcamento_gerado[0] = {'modulos': exportados,
                                'pendencias': list(pendencias),
                                'arquivo': os.path.basename(caminho)}
        if bpy.app.timers.is_registered(_apagar_orcamento_gerado):
            bpy.app.timers.unregister(_apagar_orcamento_gerado)
        bpy.app.timers.register(_apagar_orcamento_gerado,
                                first_interval=SEGUNDOS_ORCAMENTO_GERADO)
        _eventos._redesenhar_viewports(context)
        self.report({'WARNING'} if pendencias else {'INFO'},
                    "Orcamento salvo em %s: %d modulo(s)%s" % (
                        caminho, exportados, ", %d pendencia(s)"
                        % len(pendencias) if pendencias else ""))
        return {'FINISHED'}
