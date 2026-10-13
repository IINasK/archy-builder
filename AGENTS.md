# AGENTS.md — Cabinet Creator

> So' o que NAO se deduz lendo o codigo: armadilhas, decisoes do usuario e
> limites da API. Maximo 200 linhas; enxugue antes de acrescentar.
> Copia de `CLAUDE.md` (mesmo conteudo, para outros agentes): mude os dois juntos.
> Detalhe de area: `tests/CLAUDE.md` (harness), `cabinet_creator/biblioteca/CLAUDE.md`
> (presets). UI: LEIA `DESIGN.md` antes de mexer no visivel -- la' estao as recusadas.

## Projeto

Add-on de Blender (bl_info 4.0, testado em 4.2 e 5.2) para moveis
planejados: chapas (malha bmesh) agrupadas em modulos (Empty pai) e uma
biblioteca de presets. UI = "gaveta": area VIEW_3D desenhada por GPU a
esquerda (nao existe UILayout ali). O add-on e' um PACOTE, um modulo por
area (o `__init__` so' carrega, liga e registra): chapas, modulos
(conjunto), opcoes, biblioteca, materiais, eventos, selecao, portas, assistente
(wizard), ferragens, portas_viewport, puxadores, arame, importacao, promob (DXF ->
sistemas), solda (correntes), perguntas, hud, gaveta (layout), paredes, formas, gavetas
(do MOVEL: a "gaveta" e' o menu), prateleiras (internas), geometria (quinas/area),
gaveta_desenho, gaveta_eventos, orcamento, painel_legado (fora de CLASSES).
Entre modulos, SEMPRE `_modulo.nome` (apelido ligado por `_ligar_modulos`;
`from . import` no topo so' do que se usa AO CARREGAR). Teste troca funcao
NO MODULO dela (`addon.portas.x = ...`): no pacote nao vale.

Idioma: portugues (codigo, UI, commits, NOME de objeto), em ASCII (`e'`, `so'`).
Comentario explica o PORQUE.
## Comandos e verificacao

```
python vincular_blender.py [versao]  # junction cabinet_creator/ -> addons (mklink /J)
python build.py                       # dist/cabinet_creator.zip (TUDO da pasta)
blender --background --factory-startup --python tests/rodar_testes.py [-- --gui]
```

- Sem `python` no PATH: `.../Blender 5.2/5.2/python/bin/python.exe -m compileall`.
- O harness roda todas as suites em todas as versoes instaladas e falha se
  algo quebrar, sumir ou ficar sem teste. Funcionalidade nova = teste novo
  (`tests/FUNCIONALIDADES.md`). Regras em `tests/CLAUDE.md`.
- `--gui` ABRE o Blender: so' com o usuario dizendo que o PC esta' livre AGORA.
- Falha em `test_estrutura_blender.py` = "era de proposito": confirme antes.
- Testes nunca escrevem na biblioteca real. Cada entrega: `bl_info["version"]` +1 (225).

## Invariantes — NAO quebrar
1. Chapa: X = largura, Y = comprimento, Z = espessura. Orientacao por
   rotacao, nunca escala; `sz` sempre descartado.
2. Nomes gravados nos .blend (renomear quebra a biblioteca): `eh_chapa`,
   `eh_conjunto_chapa`, `chapa_*`, `conj_*`, `adj_*`, `chapa_uid`,
   `eh_grupo_portas`, `eh_folha_porta`, `porta_*`, `eh_acessorio`,
   `eh_puxador`, `puxador_*`, `eh_colecao_modulo`, `eh_colecao_comodo`,
  `eh_moldura_porta`, `eh_fundo_modulo`, `fundo_recuo_mm`, `eh_travessa_modulo`,
  `travessa_lado`, `parede_*`, `cabinet_parede_uid`, `cabinet_canto`, `cabinet_material`, `eh_peca_curva`,
  `eh_grupo_gavetas`, `eh_gaveta`, `gaveta_*`, `gavetas_*`, `eh_grupo_prateleiras`, `eh_prateleira`,
  `prateleira_*`, `prateleiras_*`.
3. Marcadores sao ID props (`MARCA_CHAPA in obj`); props de `bpy.props`
   sao RNA e NAO aparecem em `"x" in obj`. Nao troque um pelo outro.
4. Escrita de prop com `update=` feita por codigo: dentro de `_ocupado[0] = True; try/finally`.
   Callbacks `_upd_*` e o handler voltam cedo com `_ocupado[0]`. Malha DEPOIS do `finally`.
5. Geometria em MUNDO (`_eixos`, `_centro`, `_cantos`); posicao por `_definir_centro` (pai).
6. `view_layer.update()` antes de ler `matrix_world` depois de mexer.
7. Vizinho por UID, nao por nome (preset inserido vira `.001`).
8. Espessura LIVRE (`_espessura_livre`, > 0; > 60 mm = campo vermelho): nada de arredondar.
9. Malha por bmesh: o 5.2 nao escreve input de Geometry Nodes (#160038).
10. Malha modelada nunca e' substituida (`_esticar_malha` estica). `chapa_auto` e' residuo.
11. `bpy.ops` nao roda em `register()`: adie com `bpy.app.timers`.
12. Tudo registrado sai no `unregister()`: classe em `CLASSES`, prop,
    handler, TIMER, keymap. Estado global em lista de 1 elemento, zerado ali.
13. Uma biblioteca so' (`pasta_biblioteca()`), entradas antigas limpas ANTES
    do add. Catalogo DENTRO do .blend (`catalog_id`; mover = `refiliar_preset`)
    e UUID que nunca muda (`RAIZES_ANTIGAS` migram). O .cats.txt e' atomico e
    so' se muda (`_gravar_se_mudou`): dois Blenders davam UUID novo a tudo.
14. `_niveis_de` aceita o indice antigo `categoria/subcategoria`: manter.
15. Clique esquerdo na viewport e' do add-on (keyconfig ADDON). O `poll` de `OBJECT_OT_selecionar`
    da' False fora do Object Mode ou com `selecao_por_grupo` desligada -- e' assim que o clique
    nativo volta. Props dele SKIP_SAVE. Objeto comum e' do CLICK nativo: nao recriar.
16. `sincronizar_contornos` so' religa o overlay que ELE desligou.

## Decisoes do usuario (nao "melhorar")
- SNAP: reutilizar SEMPRE o motor nativo do Blender em novas ferramentas quando aplicavel;
  evitar varreduras Python de malhas no clique/arraste. Cursor temporario: restaurar no confirmar/Esc, undo unico.
- Sim/Nao (`_perguntar`): pop-up SO' da viewport; botao da gaveta = caixa preta.
- Selecao: caixa (laterais/tampo) = modulo; porta = so' porta; puxador = so' ele; duplo = peca, Shift soma; a gaveta vai a' aba
  do item; a SELECAO decide o que edita. Quina arrasta o modulo (Ctrl = snap
  SO' em quina/ponta de curva de outro armario/chapa). PORTA: clique = inteira (nunca o
  modulo), duplo = folha, sem contorno nativo. FERRAGEM so' aparece criando
  ou selecionada (ARAME da peca real): clique = todas do tipo (Shift soma o
  outro), Alt = controlador, duplo = a PECA (nativa: Tab/G/X). PUXADOR: Alt
  arrasta a ancora a outra borda SO' do grupo dele (snap de linha). Clique no puxador = SO' ele e suas funcoes, inclusive nas gavetas; trilhos das gavetas ficam com elas.
- Solda (adjacencia): grava a folga = origem. Corrente/regua aparecem pelo DESVIO (> 5 mm
  na viewport, qualquer um no botao). Regua: chapa ativa se move (pergunta se mudar medida);
  modulo ativo se adapta. Ctrl+D numa chapa: sem soldas (UID novo); F3 "Recalcular Ancoragem".
- Ancoras da solda: com Alt, arrastar a bolinha branca so' TROCA o vertice soldado
  (`adj_<ponta>_ancoras`); a geometria vai na regua: a ativa (de qualquer lado) anda pelas soldas
  NORMAIS e entorta o resto (canto + o do outro lado da E). Par encostado some; nova = de fabrica.
- Vertice de canto: atributo `cabinet_canto` (nao o SINAL); modelada: `v<i>`. E de UMA
  chapa nao mexe em mais nada (so' o do MODULO). Corrente sozinha ate' 5 mm; alem: vertice.
- Grupo = Empty + Collection de MESMO nome (`_nome_livre`), na raiz, com chapas e porta.
  Nome: F3 = dialogo; Corrente juntando SOLTAS = campo. A porta guarda o NOME do modulo.
- Orcamento (VENDIDO, nada de "ERP"): fim das OPCOES, .txt da empresa, so' Moveis,
  falta = Pendencia. COMODO = PASTA no Outliner (a unica fonte), linha na Modulos.
- Gaveta por CONTEXTO (toda aba): sem selecao, so' o botao laranja de criar
  (Modulos: nada); criando, os campos etapa a etapa (copia clicavel da caixa; o
  modal atende); selecionado, so' o do ITEM (porta sem dobradica; ferragens =
  qtd/afastamento). Sem Dobradica/Converter (F3).
- Wizard de portas (`cabinet_apanhar_vao`, porta NOVA): 4 CLIQUES = canto
  da porta, canto do vao, vao oposto, porta oposta (fio laranja = cobertura,
  branco = vao). Cobertura por lado em FRACAO da espessura (`cobertura_*_e`):
  1 = Reta, 0.5 = Curva, 0 = Super Curva -- dobradica AUTOMATICA; NUNCA
  rente a' borda: padrao deixa 2 mm (`RESPIRO_PORTA_MM`). Par 1-2 (ou 3-4)
  no mesmo ponto: margem do outro (CORRER metade-metade: PERGUNTA embutida ou
  com moldura). Fora do padrao: "As medidas estao corretas?".
  Depois, caixas do modal (popup_menu nao: o release responderia): Folhas
  -> abertura -> borda (basculante = CIMA) -> scroll = qtd -> mouse Y =
  margem -> pistoes (posicao AUTO: aberto = 2x fechado, Y so' sobe); na
  gaveta, aceite VERDE no campo da etapa. Caixa nunca cortada. Reposicionar = 2.
- Porta selecionada POR SI (nao com o modulo): contorno branco, vao amarelo, fios, slider
  por folha; Alt arrasta as bolinhas (`_cantos_da_porta`: REFEITOS, nunca gravados).
- CORRER: um TRILHO por folha (corre o vao inteiro); unica = METADE do vao;
  largura = L da gaveta; SEM sobreposicao nem "Folga no perimetro" (recusadas).
  Cobrindo a chapa = COM MOLDURA (chapas 15 refeitas com a porta; pergunta
  BASE, sem = rodape 0, e TRILHO: pesado = aluminio/folha 18, leve = canais
  fresados + U/folha 15, sem testeira); CONTA no modulo (L/A/P, HUD). Duplo = folha.
  FOLHA: Chapa | Quadro de aluminio (perfil 23 x 10 + painel 5, o do Promob).
- Gaveta sem redundancia (sem nome do item, Sincronizar, Auto-regenerar); Montagem =
  Corrente e Resetar distancia (resto: F3). Campo: ARRASTAR de lado muda; clicar digita.
- Biblioteca: Modulos | Materiais; niveis SEM LIMITE (carrossel por nivel; `niveis` no indice),
  SEM contagem, ramo vazio some. Material = COR SOLIDA no slot do OBJETO. Esfera: 1 clique NADA;
  duplo = SELECAO; arrastada = o de baixo; DIREITO = pintura rapida (comodo -> parte).
- PAREDE (Promob): DIREITO segurado no modulo, solto numa FACE vertical nao-movel
  (realcada) = costas nela, ASSOCIADO A' FACE (anda c/ ela; G/R desliza). Guias editaveis.
- GAVETAS (aba propria): 2 cliques na diagonal do vao (cima-esq -> baixo-dir) -> scroll =
  quantas -> mouse = profundidade (Alt gruda) -> trilho (TELESCOPICO padrao; OCULTO).
  Trilho = BLOCAGEM em tamanho real (modelo nao pronto). Como a porta: clique = todas,
  duplo = uma; SO' elas com linha na HUD; slider ANDA com a frente (nunca coberto);
  Alt = 3 pontos (2 quinas da frente + profundidade), snap NATIVO (translate do cursor; Esc restaura cursor e alvos). Modulo selecionado absorve os filhos;
  redimensionar MOVE as gavetas com a face proxima, SEM esticar. Edicao direta preserva selecao; Esc restaura medidas. Vinculo = PAI real (nome antigo do preset nao manda). Frente CURVA e alturas em PROPORCAO.
- PRATELEIRAS (aba propria): o assistente das GAVETAS (`AssistenteDoVao`) com SO' 2 cliques + scroll;
  profundidade ate' o FUNDO, folga da frente = RECUO. Espacamento IGUAL | LIVRE (vao ABAIXO de cada uma; o de cima sobra); mudar UM vao
  anda SO' uma prateleira (o vizinho cede). Clique = todas, duplo = uma (Abaixo/Acima dela); HUD:
  L/A/P do vao + o VALOR de cada vao. Refeitas nas MESMAS chapas (a selecao sobrevive).
- FORMA (L/diagonal/curvo, `formas`, lida da geometria): linha branca segue a PLANTA; P1/P2 =
  CADA braco; R = diagonal (porta GIRA e estica)/curva (radial); L/P: plano fora do canto.
  Diagonal (ate' a do lado INTEIRO; ponta AFIADA ou na ESPESSURA de uma chapa, que vira so'
  contorno): ARCO do angulo nas 2 pontas, com o lado DEPOIS da espessura; clicar digita.
- GEOMETRIA (`geometria`): quinas (com o ANGULO), pontas e centro de curva = snap (o ima
  mostra o rotulo; o meio do arco sai). Area = volume / E (orcamento; F3 Calcular Areas).

## Armadilhas da API (confirmadas; nao "consertar")
- Erro em callback de desenho/gizmo/timer o Blender so' IMPRIME (a UI some
  calada; o harness GUI reprova). Desenho: nunca hashear acao (dict).
- `popup_menu` em `--background` derruba o Blender: `_abrir_pergunta`.
- Objeto guardado em estado global (hover da HUD) vira memoria liberada
  no Ctrl+Z/abrir/apagar -- o release nao invalida -- e o crash sai em
  lugar aleatorio. Guarde NOME; o hover e' limpo em `undo_pre` e
  conferido por `_alvo_vivo` (so' `as_pointer()`, sem ler o objeto).
- Handler do depsgraph logo apos Ctrl+Z/Shift+Z (`_desfazendo`, ate' o
  proximo tique): nao le selecao nem mexe em dado -- derrubava o Blender.
  Selecao dos grupos por `select_get`, nunca `view_layer.objects.selected`.
- Operador MODAL terminado segue vivo (REGISTER): objeto da cena em `self`
  no Ctrl+Z seguinte corrompia a memoria do Python. `_larga_dados_ao_terminar`
  envolve invoke/modal/cancel e solta (inclusive chave de dict).
- Pop-up aberto num PRESS nasce sob o mouse e o RELEASE do mesmo clique
  responde a 1a opcao. Botao da gaveta que abre pop-up/modal dispara no
  SOLTAR (`OPERADORES_NO_SOLTAR`); o gizmo de icone tambem dispara no
  PRESS e, se abrir modal, prende os cliques da gaveta.
- `bpy.ops` em operador: `esperar_soltar`. Modal sem DOUBLE_CLICK: `_duplo_clique_na_foto`.
- Keyconfig do USUARIO guarda a ordem dele (`head=True` nao adianta): clique
  que tem de ganhar da selecao e' GIZMO (antes do keymap), como o slider.
- `GIZMO_GT_button_2d` nao aceita clique com modificador: Alt+clique na
  corrente/regua e' do keymap `cabinet_clique_corrente`.
- UILayout: sem widget novo nem px (`ui_units_x`); `template_asset_view` saiu no 5.x.
  `asset_generate_preview()` e' assincrono (perde o `libraries.write`): `aplicar_preview_png`.
- `Window.width/height` read-only: Asset Browser = AREA (`area_split`); shelf: `region_toggle`.
  `bound_box` de curva/texto/meta: por `to_mesh()` (`TIPOS_BBOX_INFIEL`). Escala no modal `S`
  nao se intercepta: o handler age quando ele termina.

## Armadilhas por area
- Portas: parametros na Scene (nao no operador); `cabinet_portas` com `EXEC_DEFAULT` (INVOKE
  traz o dialogo) e `_parametros_portas_da_cena` cobre `_PARAMETROS_PORTAS` inteiro. Folgas ao
  modulo em ESPESSURAS (`CHAVE_FOLGAS_PORTA`). Frente sempre automatica (`_frente_automatica`):
  grave-a resolvida. Os 2 caminhos de captura do vao: o MESMO `_referencia_do_par`. Abertura na
  `matrix_basis` da folha (centrada, filha do grupo; mede-se por `_matriz_fechada`). Nada de
  `hide_select`; ferragem por `_conferir_ferragens`. Aux. do rig: `hide_set` e' da CAMADA,
  preset/anexo o perdem -- `ocultar_pecas_do_rig` (timer). Vertices do vao lidos UMA vez.
  Reta = rig do USUARIO (`extrair_dobradica.py`, 4.2): nao refazer (so' o furo do copo); folha
  segue a TABELA; placa/suporte andam ate' a face (`_calco_rig`). Parametro de TEXTO novo
  (trilho, folha): nos conjuntos de enum de `_carregar_portas_na_cena` e `_valores_portas`.
- Puxador: `posicionar_puxador` refaz pelas PROPS da chapa (nunca delta);
  PERFIL (o PADRAO): pontas/costas ANDAM. 'MODELO' (do usuario): a BIBLIOTECA e' a fonte;
  de fabrica: PROTEGIDOS. Retratos: `gerar_fotos_padrao.py` (GUI).
- Presets: clique = posicionador; Salvar gera o PNG; de fora = chapa pela FORMA.
- PROMOB = INTEGRACAO, nao copia (`importar_promob.py` -> `promob`): PASTA = aba, ARQUIVO =
  categoria. COR da camada: 7 = chapa; 253/254/8 (ferragem, aluminio, puxador) NUNCA viram
  peca. Frente c/ dobradica = porta NOSSA (o lado dela: Reta/Curva nossa); c/ caixa ou cesto
  = gavetas NOSSAS; quadro de aluminio = CORRER folha Quadro; fundo fino/travessas do topo
  = dependentes. Trilho e dobradica: SEMPRE os do add-on. Dobradica embaixo: fica chapa.
- FUNDO (5 mm, canal a 15, entra 7) e TRAVESSAS (topo aberto): DEPENDENTES, refeitos pela caixa.

## Git e residuos
- Commit em pt (3a pessoa), so' a pedido; fora: dist/ *.blend1 __pycache__.
  Nome antigo "Chapa G3" (tag `chapa-g3`); props de Object/Scene ficam.
