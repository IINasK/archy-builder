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
sistemas), solda (correntes), perguntas, hud, gaveta (layout), biblioteca_faixa (topo), paredes, formas, gavetas
(do MOVEL: a "gaveta" e' o menu), prateleiras (internas), geometria (quinas/area),
gaveta_desenho, gaveta_eventos, orcamento, frentes (referencia comum), painel_legado (fora de CLASSES).
Entre modulos, SEMPRE `_modulo.nome` (apelido ligado por `_ligar_modulos`;
`from . import` no topo so' do que se usa AO CARREGAR). Teste troca funcao
NO MODULO dela (`addon.portas.x = ...`): no pacote nao vale.

Idioma: portugues (codigo, UI, commits, NOME de objeto), em ASCII (`e'`, `so'`). Comentario explica o PORQUE.
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
- Testes nunca escrevem na biblioteca real. Cada entrega: `bl_info["version"]` +1 (272).

## Invariantes — NAO quebrar
1. Chapa: X = largura, Y = comprimento, Z = espessura. Orientacao por
   rotacao, nunca escala; `sz` sempre descartado.
2. Nomes gravados nos .blend (renomear quebra a biblioteca): `eh_chapa`,
   `eh_conjunto_chapa`, `chapa_*`, `conj_*`, `adj_*`, `chapa_uid`,
   `eh_grupo_portas`, `eh_folha_porta`, `porta_*`, `eh_acessorio`,
   `eh_puxador`, `puxador_*`, `eh_colecao_modulo`, `eh_colecao_comodo`,
  `eh_moldura_porta`, `eh_fundo_modulo`, `fundo_recuo_mm`, `fundo_margens_mm`, `fundo_recuo_base_mm`, `eh_travessa_modulo`,
  `travessa_lado`, `parede_*`, `cabinet_parede_uid`, `cabinet_canto`, `cabinet_forma_angulo`, `cabinet_material`, `eh_peca_curva`,
  `eh_grupo_gavetas`, `eh_gaveta`, `gaveta_*`, `gavetas_*`, `eh_grupo_prateleiras`, `eh_prateleira`,
  `prateleira_*`, `prateleiras_*`, `forma_edicao`, `chapa_edicao`.
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
- Nao delegar automaticamente a subagentes; usar colaboracao multiagente so' mediante pedido explicito do usuario para a tarefa atual.
- Curvatura de PORTA pertence ao controle explicito do add-on (inclui adocao na importacao). Curvar/deformar uma malha pelo Tab nativo NAO a converte em curva parametrica, nem autoriza solver/reencaixe de curva. Ler contorno real para medidas/puxador nao ativa esse sistema. Conservar a modelagem manual; nao apagar a regressao de resize de portas curvas controladas pelo add-on.
- SNAP: reutilizar SEMPRE o motor nativo do Blender em novas ferramentas quando aplicavel;
  evitar varreduras Python de malhas no clique/arraste, inclusive CRIACAO de gavetas/prateleiras (`cabinet_marcar_ponto_vao`). Cursor temporario: restaurar no confirmar/Esc, undo unico. `translate.orient_matrix` recebe eixos em LINHAS: transpor a Matrix do grupo (colunas), senao arrasta girado ao contrario.
- Sim/Nao (`_perguntar`): pop-up SO' da viewport; botao da gaveta = caixa preta. Excecao: DIREITO na foto/nome da biblioteca = menu no SOLTAR (Inserir/Editar/Bloquear); sem botoes sob modulos.
- Selecao: caixa (laterais/tampo) = modulo; porta = so' porta; puxador = so' ele; duplo = peca, Shift soma; a gaveta vai a' aba
  do item; a SELECAO decide o que edita. Quina arrasta o modulo (Ctrl = snap
  SO' em quina/ponta de curva de outro armario/chapa). PORTA: clique = inteira (nunca o
  modulo), duplo = folha, sem contorno nativo. ESPELHAR PORTA: icone na aba Portas + contexto do botao direito, grupo ou folha; inverter giro, cadeia zigzag (inteira), curso de correr ou basculante com pistoes; puxador acompanha. Nao espelhar a madeira. FERRAGEM so' aparece criando
  ou selecionada (ARAME da peca real): clique = todas do tipo (Shift soma o
  outro), Alt = controlador, duplo = a PECA (nativa: Tab/G/X). PUXADOR: Alt
  arrasta a ancora a outra borda SO' do grupo dele (snap de linha). Clique no puxador = SO' ele e suas funcoes, inclusive nas gavetas; trilhos das gavetas ficam com elas. Tab no Empty do grupo = Edit Mode MULTIOBJETO nativo, so' malhas reais (sem cortadores/controles); tornar malhas compartilhadas unicas antes. Conservar Empties selecionados no Edit Mode (escopo nativo/undo), restaurar selecao/ativo ao sair e invalidar planta; estado SO' nomes. Peca isolada conserva Tab nativo.
- Solda manual usa o translate/snap NATIVO compartilhado e identifica MeshVertex por KDTree nativa, sem cantos nominais. Ancorar/Juntar preserva a posicao atual e registra o afastamento 3D por par no referencial do destino (`adj_<ponta>_origens`); Resetar volta a esse gap, nunca o zera. Trocar a ancora por Alt conserva a origem cadastrada da junta.
- Solda (adjacencia): grava a folga = origem. Corrente/regua aparecem pelo DESVIO (> 5 mm
  na viewport, qualquer um no botao). Corrente e regua escolhem a MESMA peca pela selecao, nunca pelo lado que grava o vinculo. Regua: chapa ativa se move (pergunta se mudar medida);
  modulo ativo se adapta. Modulos: solda automatica exige area de apoio positiva (quina/aresta nao basta); chapas soltas mantem fecho legado. Limpar nome E UID da ponta; otimizar_adjacencia preserva ancoras manuais. HUD agrupa controles da mesma junta por espessura, sem apagar vinculos. Ctrl+D numa chapa: sem soldas (UID novo); F3 "Recalcular Ancoragem".
- Ancoras da solda: com Alt, arrastar a bolinha branca so' TROCA o vertice soldado
  (`adj_<ponta>_ancoras`); a geometria vai na regua: a ativa (de qualquer lado) anda pelas soldas
  NORMAIS e entorta o resto (canto + o do outro lado da E). Par encostado some; nova = de fabrica.
- Vertice de canto: atributo `cabinet_canto` (nao o SINAL); modelada: `v<i>`. E de UMA
  chapa nao mexe em mais nada (so' o do MODULO). Corrente sozinha ate' 5 mm; alem: vertice.
- Grupo = Empty + Collection de MESMO nome (`_nome_livre`), na raiz, com chapas e porta.
  Nome: F3 = dialogo; Corrente juntando SOLTAS = campo. A porta guarda o NOME do modulo. Solda/comodo garantem a Collection ANTES da filiacao; preset sem marca reutiliza SO' a pasta exclusiva de mesmo nome. Pasta compartilhada nunca vira modulo.
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
  FOLHA: Chapa | Quadro de aluminio (perfil 23 x 10 + painel 5, o do Promob). ZIGZAG: 2-8 folhas em cadeia alternada; lado define a primeira, puxador SO' na ultima. Junta = placas/nos/eixo nativos, cada metade na sua folha; slider unico. Fotos da biblioteca: TODAS as portas fechadas (tambem canto, correr e zigzag); nao mudar o lado para fotografar.
- Gaveta sem redundancia (sem nome do item, Sincronizar, Auto-regenerar); Montagem =
  Corrente e Resetar distancia (resto: F3). Campo: ARRASTAR de lado muda; clicar digita.
- Biblioteca: Modulos | Materiais na FAIXA no TOPO, acima do menu E da viewport (`biblioteca_faixa`); menu so' edita. Niveis SEM LIMITE (`niveis` no indice),
  Abas compactas (18/20 px, fonte 10, intervalo 2); altura <160: subniveis na mesma linha (vao 24 + divisor), roda por X/Y; Setas SO' com overflow, no sentido dos ocultos; SEM contagem, ramo vazio some; fotos so' visiveis, cache RGBA8 de 64 MiB e indice invalidavel. Material = COR SOLIDA no slot do OBJETO. Esfera: 1 clique NADA;
  duplo = SELECAO; arrastada = o de baixo; DIREITO = pintura rapida (comodo -> parte). Areas: Screen `cabinet_layout=2`, biblioteca/menu/cena; reconecta/migra. Shift+roda percorre niveis profundos; chaves de rolagem com hash (63 bytes).
- PAREDE (Promob): DIREITO segurado no modulo, solto numa FACE vertical nao-movel
  (realcada) = costas nela, ASSOCIADO A' FACE (anda c/ ela; G/R desliza). Guias editaveis.
- GAVETAS (aba propria): 2 cliques na diagonal do vao (cima-esq -> baixo-dir) -> scroll =
  quantas -> mouse = profundidade (Alt gruda) -> trilho (TELESCOPICO padrao; OCULTO). Os 2 cliques definem a FRENTE, nunca eixo fixo; recuos desencontrados usam o plano mais interno. Pontos sobre chapas usam faces INTERNAS. Profundidade so' projeta no eixo, limitada ao menor espaco livre (ray cast nativo UMA vez); previa conserva cache. Prateleiras usam/gravam a mesma referencia.
  Trilho = BLOCAGEM em tamanho real (modelo nao pronto). Como a porta: clique = todas,
  duplo = uma; SO' elas com linha na HUD; slider ANDA com a frente (nunca coberto);
  Alt = 3 pontos (2 quinas da frente + profundidade), snap NATIVO (translate do cursor; Esc restaura cursor e alvos). Modulo selecionado absorve os filhos;
  redimensionar move pela face proxima sem crescer; faltando espaco, adapta caixa/frente/trilho ate' o minimo fisico e devolve as escolhas ao aumentar. Edicao direta preserva selecao; Esc restaura medidas. Vinculo = PAI real (nome antigo do preset nao manda). Frente CURVA e alturas em PROPORCAO. Borda de CADA gaveta: altura cede/recebe da vizinha, total fixo (externa ancora o limite); uma so' usa seu vao. Duplo = campos individuais L/A/P, Abaixo/Acima, frente/trilho/recuo/puxador; grupo = todas. Previa SO' parametros/contorno, montar uma vez no confirmar; curso e material por unidade.
- PRATELEIRAS (aba propria): o assistente das GAVETAS (`AssistenteDoVao`) com SO' 2 cliques + scroll;
  profundidade ate' o FUNDO, folga da frente = RECUO. Espacamento IGUAL | LIVRE (vao ABAIXO de cada uma; o de cima sobra); mudar UM vao
  anda SO' uma prateleira (o vizinho cede). Clique = todas, duplo = uma (Abaixo/Acima dela); HUD:
  L/A/P do vao + o VALOR de cada vao. Mesmas chapas; Tab no grupo propaga a todas ao concluir (multiobjeto nativo), individual isola a malha. NUNCA trocar o ID de Mesh ao concluir: BMesh.to_mesh na MESMA malha (undo nativo guarda o ID). Undo que volta ao Edit Mode recupera escopo da selecao nativa. Quantidade herda geometria/parametros/material/modificadores da unidade selecionada; tipos diferentes sem unidade ativa pedem "Selecione a prateleira de referencia" ao lado do mouse na viewport, acompanhando o cursor e respeitando as bordas (Esc cancela sem adicionar). Parametros individuais nao movem vizinhas; arrastar quantidade so' exibe previa, monta ao soltar.
- FORMA: MODULO selecionado = sempre CAIXA convencional de 8 cantos/12 cotas nos limites do envelope. Rotulos de medidas = A1, A2... (inclui segmentos da chapa); E so' espessura. L/A/P/R continuam identificadores INTERNOS, nunca rotulos. E da chapa vem de peles correspondentes no eixo transversal local; dobra/flecha NAO vira espessura. Secao ambigua conserva E nominal; resize conserva linha media. Nao inferir forma/angulos do grupo; resize CAIXA. Eventos antigos de formato do grupo recusados, inclusive hover anterior.
  Angulos/contorno real SO' na CHAPA INDIVIDUAL selecionada, pelo plano local da face. Menu e HUD usam as MESMAS cotas editaveis A1...An/E, por chave semantica (nao numero A). Deslocamento transversal da linha media MAIOR que E ganha cota propria (ex.: A6), sem engrossar a madeira; arraste/Esc conserva referencia original. Outra chapa/porta/modulo nao acompanha a edicao individual. Mesh compartilhada isolada antes. Tab nativo; ao sair atualiza medidas/caches, undo invalida. Sem deformacao radial; solver antigo do grupo so' por API, nunca automatico.
  Referencia de resize nao acumula deltas: Mesh nativa, restaurar pais E porta_centro_folha ANTES dos filhos. Vaos de portas/gavetas seguem o mapa do corpo, sem reancorar antes de restaurar; E conservada pela normal. Frente parcial apoia por FACE real (closest_point_on_mesh + poly_3d_calc), pesos guardados uma vez, nunca caixa inteira nem busca no redraw. Cache so' numerico; nada de Mesh/CDT/hull na HUD do modulo.
- GEOMETRIA (`geometria`): quinas (com o ANGULO), pontas e centro de curva = snap (o ima
  mostra o rotulo; o meio do arco sai). Area = volume / E (orcamento; F3 Calcular Areas).

## Armadilhas da API (confirmadas; nao "consertar")
- Erro em callback de desenho/gizmo/timer o Blender so' IMPRIME (a UI some
  calada; o harness GUI reprova). Desenho: nunca hashear acao (dict). Biblioteca/menu: gizmos em pool (so' ocultar); campos conservam operador ligado, atualizam dica. Remover/religar no redraw caia em WM_gizmomap_tooltip_init.
- `popup_menu` em `--background` derruba o Blender: `_abrir_pergunta`.
- Objeto guardado em estado global (hover da HUD) vira memoria liberada
  no Ctrl+Z/abrir/apagar -- o release nao invalida -- e o crash sai em
  lugar aleatorio. Guarde NOME; o hover e' limpo em `undo_pre` e
  conferido por `_alvo_vivo` (so' `as_pointer()`, sem ler o objeto).
- Depsgraph E timer durante Ctrl+Z/Shift+Z (`_desfazendo`): nada de selecao/malhas. Fecho do undo SO' libera a guarda; reconstruir referencias no timer normal. Limpar transicoes antigas de Edit Mode/modal ao invalidar. Absorver Tab so' mede/recentra, NUNCA chama gerar_malha_chapa/BMesh.to_mesh; `Mesh.is_editmode` bloqueia escritas tambem por instancias fora de Edit Mode.
  Selecao dos grupos por `select_get`, nunca `view_layer.objects.selected`.
- Operador MODAL terminado segue vivo (REGISTER): objeto da cena em `self`
  no Ctrl+Z seguinte corrompia a memoria do Python. `_larga_dados_ao_terminar`
  envolve invoke/modal/cancel INCLUSIVE herdados de mixin e solta (inclusive chave de dict). Assistente com excecao encerra handlers/timer/snap antes de propagar.
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
  segue a TABELA; placa/suporte andam ate' a face (`_calco_rig`). `dobradica_modelo_reta` usa esse rig na cobertura parcial SEM mudar vao/borda; copo deve caber na folha. Curva/embutida em apoio obliquo: ray cast da face real + 4 quinas coplanares; preservar cantos do PRISMA (AABB desorienta). Encaixe antigo atualiza uma vez pelo timer, sem mudar folha/abertura/puxador. Parametro de TEXTO novo
  (trilho, folha): nos conjuntos de enum de `_carregar_portas_na_cena` e `_valores_portas`. ID props aninhadas: copiar RECURSIVAMENTE antes de substituir (`dict` e' raso; acesso depois derruba o 5.2).
- Puxador: `posicionar_puxador` refaz pelas PROPS da chapa (nunca delta);
  PERFIL (o PADRAO): pontas/costas ANDAM. Folha nativa tem frente +Z LOCAL; nunca comparar com -Y da caixa, pois inverte o perfil perpendicular no L. LADO segue X da folha FECHADA, nao do modulo. 'MODELO' (do usuario): a BIBLIOTECA e' a fonte;
  de fabrica: PROTEGIDOS. Retratos: `gerar_fotos_padrao.py` (GUI).
- Presets: clique = posicionador; Salvar gera PNG; de fora = chapa pela FORMA. Abertura real ESQUERDA na biblioteca/Promob se TODAS as placas cabem no apoio; cadeias coplanares invertem a ordem sem mover folhas fechadas; canto sem apoio conserva articulacao. Foto: TODAS fechadas, SO' apos salvar, copia descartavel. Quinas com contorno legivel, sem triangulacao; auxiliares/cores restaurados. Migracoes: atualizar_fotos_biblioteca.py / ajustar_abertura_esquerda.py com backup.
- PROMOB = INTEGRACAO, nao copia (`importar_promob.py` -> `promob`): PASTA = aba, ARQUIVO =
  categoria. Quartos preserva ramos (Armarios/Bancadas/Escritorios/Superiores), prefixo unico por ambiente; Portas avulsas viram grupos de portas (madeira modelada ou quadro/painel medidos), SEM carcaca inventada. Contato = BVH nativa depois da caixa; vao vazio do L NAO une modulos. Internos suspensos inteiramente contidos acompanham o corpo. integracao em integrar_bibliotecas_promob.py (preparo retomavel, hashes/backup/rollback). Curva com placa vira folha NATIVA com malha original (Z = flecha, nao achatar), alca tangente; R deforma fechada e reancora. Diagonais: perfil pela maior chapa deitada (travessa nao define frente), pontas das DUAS faces liberam a caixa real em 2 mm por consultas nativas na montagem; normal de fora vem da madeira (centro da caixa inverte curvas), lado exige apoio. FRENTES: referencia comum em frentes.py (FRONTES.md); atributos INT FACE/EDGE semanticos, cache numerico na Mesh, invalidacao por Mesh/undo fora do desenho. porta_linha_frente so' migra legado; indices nao governam contorno/resize. Puxador/Alt/previa usam bordas/normais comuns, PERFIL segue curva; fracao legada migra uma vez. Resize reancora pela tangente SEM refazer vertices/faces editados; fundo fino nao sustenta dobradica. Coberturas/entre-folhas medidos (`respiro_original`), normal da CHAPA (placa tem ruido); apoio diagonal usa dobradica angular. Perfil nosso: superiores BAIXO, inferiores CIMA, torres LADO. COR da camada: 7 = chapa; 253/254/8 (ferragem, aluminio, puxador) NUNCA viram
  peca. Placa/braco da dobradica = UMA referencia (face, lado, alturas por folha); nunca supor frente -Y. L/diagonal = portas nossas no plano real (`porta_vao_orientado`); junta sem apoio vai para a lateral externa existente. Edicao manual de margem/qtd substitui as referencias. Frente c/ caixa ou cesto
  = gavetas NOSSAS por FACE (ilhas viradas tambem); nao converter lateral inteira. Coberturas por lado/alturas preservadas, edicao manual substitui referencia; prateleiras adotam UID/material/recorte e vaos LIVRES. Sistemas DENTRO da montagem do asset, mesmo antiga sem marca; auditoria: `auditar_integracao_promob.py`. Quadro de aluminio = CORRER folha Quadro; fundo fino/travessas do topo
  = dependentes. Trilho e dobradica: SEMPRE os do add-on. Ripas/arremates cor 7: aceitar proporcao 1 e tolerancia 0,05 mm; nao descartar apoio de 40/15 nem 49,9998 mm. Painel fixo NUNCA vira articulacao entre folhas; porta deixa 2 mm do arremate e da face de apoio. Dobradica embaixo: fica chapa. Base/tampo com recuo <=3,1 mm: levar a' quina externa (promob.ajustar_encaixes), sem mudar E/forma/sistemas; refazer ancoras. Biblioteca existente: ajustar_encaixes_promob.py / ajustar_portas_promob.py, preparo validado + backup antes de --aplicar.
- FUNDO (5 mm, canal a 15, entra 7) e TRAVESSAS: dependentes. Promob: recuo MINIMO 15; fundos parciais/ortogonais guardam margens por PLANO, nunca expandir pela caixa toda. Base/tampo deslocados: alongar a divisoria que ENCOSTAVA na face real, fechando a nova fresta. Ilhas: frente unica (+X/-Y da foto), oposta vira fundo; cantos ficam. Migracoes: ajustar_fundos_portas_promob.py / refinar_cantos_promob.py, backup/preparo validado.

## Git e residuos
- Commit em pt (3a pessoa), so' a pedido; fora: dist/ *.blend1 __pycache__.
  Nome antigo "Chapa G3" (tag `chapa-g3`); props de Object/Scene ficam.
