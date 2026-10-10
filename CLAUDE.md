# CLAUDE.md — Cabinet Creator

> So' o que NAO se deduz lendo o codigo: armadilhas, decisoes do usuario e
> limites da API. Maximo 200 linhas; enxugue antes de acrescentar.
> `AGENTS.md` e' COPIA deste arquivo (mesmo conteudo): mude os dois juntos.
> Detalhe de area: `tests/CLAUDE.md` (harness), `cabinet_creator/
> biblioteca/CLAUDE.md` (presets/catalogos). UI: LEIA `DESIGN.md` antes de
> mexer em qualquer coisa visivel -- la' estao as alternativas recusadas.

## Projeto

Add-on de Blender (bl_info 4.0, testado em 4.2 e 5.2) para moveis
planejados: chapas (malha bmesh) agrupadas em modulos (Empty pai) e uma
biblioteca de presets. UI = "gaveta": area VIEW_3D desenhada por GPU a
esquerda (nao existe UILayout ali). `cabinet_creator/__init__.py` e' o
add-on INTEIRO, arquivo unico por decisao.

Idioma: portugues (codigo, UI, commits, NOME de objeto). Texto em ASCII:
`e'`, `so'`, `ja'` no lugar de acento. Comentario explica o PORQUE.

## Comandos e verificacao

```
python vincular_blender.py [versao]  # junction cabinet_creator/ -> addons (mklink /J)
python build.py                       # dist/cabinet_creator.zip (TUDO da pasta)
blender --background --factory-startup --python tests/rodar_testes.py [-- --gui]
```

- Nao ha' `python` no PATH: use o do Blender
  (`C:/Program Files/Blender Foundation/Blender 5.2/5.2/python/bin/python.exe
  -m py_compile cabinet_creator/__init__.py`).
- O harness roda todas as suites em todas as versoes instaladas e falha se
  algo quebrar, sumir ou ficar sem teste. Funcionalidade nova = teste novo
  (`tests/FUNCIONALIDADES.md`). Regras em `tests/CLAUDE.md`.
- `--gui` ABRE o Blender na tela: so' com permissao do usuario na sessao.
- Falha em `test_estrutura_blender.py` = "isto era de proposito": confirme
  com o usuario antes de mudar; nao conserte o teste.
- Testes nunca escrevem na biblioteca real (`cabinet_creator/biblioteca`).
- Cada entrega: `bl_info["version"]` +1 (hoje 182.0.0).

## Invariantes — NAO quebrar

1. Chapa: X = largura, Y = comprimento, Z = espessura. Orientacao por
   rotacao, nunca escala; `sz` sempre descartado.
2. Nomes gravados nos .blend (renomear quebra a biblioteca): `eh_chapa`,
   `eh_conjunto_chapa`, `chapa_*`, `conj_*`, `adj_*`, `chapa_uid`,
   `eh_grupo_portas`, `eh_folha_porta`, `porta_*`, `eh_acessorio`,
   `eh_puxador`, `puxador_*`, `eh_colecao_modulo`, `eh_colecao_comodo`,
  atributo `cabinet_canto`.
3. Marcadores sao ID props (`MARCA_CHAPA in obj`); props de `bpy.props`
   sao RNA e NAO aparecem em `"x" in obj`. Nao troque um pelo outro.
4. Escrita de prop com `update=` feita por codigo: dentro de
   `_ocupado[0] = True; try/finally`. Callbacks `_upd_*` e o handler voltam
   cedo com `_ocupado[0]`. Regenere malha DEPOIS do `finally`.
5. Geometria em MUNDO (`_eixos`, `_centro`, `_cantos`); grave posicao com
   `_definir_centro` (respeita pai e `matrix_parent_inverse`).
6. `view_layer.update()` antes de ler `matrix_world` depois de mexer.
7. Vizinho por UID, nao por nome (preset inserido vira `.001`).
8. Espessura LIVRE (`_espessura_livre`, so' > 0); acima de 60 mm o campo
   fica vermelho. Nao arredondar para `ESPESSURAS_PERMITIDAS`.
9. Malha por bmesh: o 5.2 nao escreve input de Geometry Nodes (#160038).
10. Malha modelada nunca e' substituida: `_esticar_malha` estica;
    `gerar_malha_chapa` so' refaz a caixa padrao. `chapa_auto` e' residuo.
11. `bpy.ops` nao roda em `register()`: adie com `bpy.app.timers`.
12. Tudo registrado sai no `unregister()`: classe em `CLASSES`, prop,
    handler, TIMER, keymap. Estado global em lista de 1 elemento, zerado ali.
13. Uma biblioteca so' (`pasta_biblioteca()`); ao registrar, limpar as
    entradas antigas ANTES do add. Catalogo mora DENTRO do .blend
    (`catalog_id`); mover = regravar (`refiliar_preset`). UUID de catalogo
    nunca muda (`CAT_RAIZ`, `RAIZES_ANTIGAS` migram com o UUID). O
    .cats.txt so' se grava se mudou e atomico (`_gravar_se_mudou`): com
    "w" direto, dois Blenders juntos davam UUID novo a tudo.
14. `_niveis_de` aceita o indice antigo `categoria/subcategoria`: manter.
15. Clique esquerdo na viewport e' do add-on (keyconfig ADDON). O `poll` de
    `OBJECT_OT_selecionar` devolve False fora do Object Mode ou com
    `selecao_por_grupo` desligada -- e' assim que o clique nativo volta.
    Props dele SKIP_SAVE. Objeto comum e' do CLICK nativo: nao recriar.
16. `sincronizar_contornos` so' religa o overlay que ELE desligou.

## Decisoes do usuario (nao "melhorar")

- Sim/Nao (`_perguntar`): pop-up SO' da viewport; botao da gaveta = caixa preta.
- Selecao: clique = modulo, duplo = peca, Shift soma; a gaveta vai a' aba
  do item; a SELECAO decide o que edita. Quina arrasta o modulo (Ctrl = snap
  SO' em quina de outro armario/chapa). PORTA: clique = inteira (nunca o
  modulo), duplo = folha, sem contorno nativo. FERRAGEM so' aparece criando
  ou selecionada (ARAME da peca real): clique = todas do tipo (Shift soma o
  outro), Alt = controlador, duplo = a PECA (nativa: Tab/G/X). PUXADOR: Alt
  arrasta a ancora a outra borda SO' do grupo dele (snap de linha).
- Solda (adjacencia): grava a folga = origem. Corrente/regua aparecem pelo
  DESVIO dela (> 5 mm na viewport, qualquer um no botao). Regua: chapa
  ativa se move (pergunta se mudar medida); modulo ativo se adapta.
- Ancoras da solda: com Alt, arrastar a bolinha branca so' TROCA o
  vertice soldado (`adj_<ponta>_ancoras`); a geometria vai la' na regua:
  quem se move (a ativa, de qualquer lado da solda) anda pelas soldas
  NORMAIS e entorta o resto (canto + o do outro lado da espessura). O par
  que ja' encostou some. Solda nova ou redetectada volta as de fabrica.
- Vertice de canto: atributo `cabinet_canto` (pelo SINAL da coordenada erra
  ao cruzar a origem). Malha modelada: ancora = qualquer vertice, `v<i>`.
- Espessura de UMA chapa nao mexe em mais nada; so' o E do MODULO acomoda.
- Grupo (armario) = Empty + Collection com o MESMO nome (`_nome_livre`), na
  raiz da cena: chapas e a porta ("Porta Dupla"... `_nome_da_porta`). Nome
  ao agrupar: F3 = dialogo; Corrente juntando SOLTAS = campo na gaveta.
  Desagrupar manda a chapa a' raiz. A porta guarda o NOME do modulo.
- Orcamento do ERP (`orcamento_da_cena`, aba Modulos): documento COMPLETO
  no padrao do prompt do usuario, so' Moveis. Modulo = NOME do grupo,
  detalhes so' do 3D; o que falta vira Pendencia. COMODO = PASTA no Outliner
  (Collection marcada com as dos armarios; a unica fonte), escolhido numa
  linha que EXPANDE (+ "Outro nome..."). Copiar mostra o resultado NA gaveta.
- Gaveta por CONTEXTO (toda aba): sem selecao, so' o botao laranja de criar
  (Modulos: so' o Orcamento); criando, os campos etapa a etapa (copia
  clicavel da caixa; o modal atende); selecionado, so' o do ITEM (porta sem
  dobradica; ferragens = qtd/afastamento). Sem Dobradica/Converter (F3).
- Wizard de portas (`cabinet_apanhar_vao`, porta NOVA): 4 CLIQUES = canto
  da porta, canto do vao, vao oposto, porta oposta (fio laranja = cobertura,
  branco = vao). Cobertura por lado em FRACAO da espessura (`cobertura_*_e`):
  1 = Reta, 0.5 = Curva, 0 = Super Curva -- dobradica AUTOMATICA; NUNCA
  rente a' borda: padrao deixa 2 mm (`RESPIRO_PORTA_MM`). Par 1-2 (ou 3-4)
  no mesmo ponto: margem do outro. Fora do padrao: "As medidas estao corretas?".
  Depois, caixas do modal (popup_menu nao: o release responderia): Folhas
  -> abertura -> borda das dobradicas (clique; basculante = CIMA) -> scroll
  = qtd -> mouse Y = margem -> pistoes (qtd; posicao AUTO por aberto = 2x
  fechado, Y so' sobe). Caixa nunca cortada. Reposicionar = diagonal de 2.
- Porta selecionada POR SI (clique nela; o modulo selecionado nao mostra
  nada disto): contorno branco, vao amarelo, fios dos cantos e
  um slider por folha. Alt arrasta as bolinhas e refaz a porta
  (`_cantos_da_porta`: REFEITOS de vao + cobertura, nunca gravados).
- Corrente conecta sozinha ate' 5 mm (`ALCANCE_CONEXAO_AUTOMATICA`); alem: vertice.
- Empties do add-on (modulo, porta, pistao) FICAM, invisiveis (`_ocultar_empty`).
- Gaveta sem redundancia: sem nome do item, Sincronizar, Auto-regenerar nem
  correntes entre abas; Montagem = Corrente e Resetar distancia (resto: F3).

## Armadilhas da API (confirmadas; nao "consertar")

- Erro em callback de desenho/gizmo/timer o Blender so' IMPRIME: a UI
  some calada. O harness GUI reprova por isso; em codigo de desenho,
  nunca hashear acao de widget (preset/item levam dict).
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
- `bpy.ops` dentro de operador ve a janela (ja' no RELEASE?): `esperar_soltar`.
- Modal nunca recebe DOUBLE_CLICK (vira PRESS): `_duplo_clique_na_foto`.
- Keyconfig do USUARIO guarda a ordem dele: `head=True` nao poe a entrada
  do add-on antes da selecao. Clique que tem de ganhar dela e' GIZMO
  (avaliado antes de keymap), como a bolinha do slider da porta.
- `GIZMO_GT_button_2d` nao aceita clique com modificador: Alt+clique na
  corrente/regua e' do keymap `cabinet_clique_corrente`.
- O bpy nao mede texto fora do desenho: largura vem de estimativas `PX_*`.
- Nao da' para criar widget interativo novo no UILayout nem fixar largura
  em pixels (`ui_units_x` ignorado); `template_asset_view` saiu no 5.x.
- `asset_generate_preview()` e' assincrono e perde o `libraries.write`:
  use `aplicar_preview_png` (grave tambem `icon_size`/`icon_pixels_float`).
- `Window.width/height` read-only: Asset Browser entra como AREA
  (`screen.area_split`); `show_region_asset_shelf` idem: `region_toggle`.
- `bound_box` de curva/texto/meta: medida por `to_mesh()` (`TIPOS_BBOX_INFIEL`).
- Escala no modal `S` nao se intercepta: o handler age quando ele termina.

## Armadilhas por area

- Portas: parametros vivem na Scene, nao no operador; `cabinet_portas` e'
  chamado com `EXEC_DEFAULT` (INVOKE traz o dialogo de volta) e
  `_parametros_portas_da_cena` tem que cobrir `_PARAMETROS_PORTAS` inteiro.
  Folgas da porta ao modulo em ESPESSURAS (`CHAVE_FOLGAS_PORTA`), nao mm.
  Frente sempre automatica (`_frente_automatica`): grave-a ja' resolvida.
  Os dois caminhos de captura do vao usam o MESMO `_referencia_do_par`.
  Abertura na `matrix_basis` da folha (centrada, filha do grupo; mede-se
  por `_matriz_fechada`). Nada de `hide_select` (tudo editavel); ferragem
  refeita por `_conferir_ferragens`. Vertices do vao lidos UMA vez.
  Reta = modelo+rig do USUARIO (`ferragens/`, `extrair_dobradica.py` no
  4.2): nao refazer (so' o furo do copo, medido); folha segue a TABELA.
- Puxador parametrico: `posicionar_puxador` refaz pelas PROPS da chapa pai
  no fim de `gerar_malha_chapa`, nunca por delta. PERFIL do usuario: pontas
  e costas ANDAM (chanfro intacto); corta so' a malha, props/HUD nominais.
- Presets: clique no nome/foto = posicionador (clique-para-posicionar e' o
  uso normal, nao remover). Salvar sempre gera o PNG; falha na foto
  cancela o cadastro. Conversao de objeto de fora pela FORMA
  (`converter_em_chapa`), nunca por `obj.dimensions` em eixos de mundo.

## Git

- Commit em portugues, verbo no presente, 3a pessoa, so' a pedido do
  usuario. `.blend`/`.png` binarios; `dist/`, `*.blend1`, `__pycache__` fora.

## Residuos conhecidos

- Nome antigo "Chapa G3" (tag `chapa-g3`, descricao "Modulo G3 - ...").
- `VIEW3D_PT_cabinet_creator` (painel N) e' legado, fora de `CLASSES` de
  proposito. `unregister()` nao remove as props de Object/Scene.
