# DESIGN.md — como desenhar UI no Cabinet Creator

> **REGRA DESTE ARQUIVO:** NAO pode passar de 200 linhas.
>
> **LEIA ANTES DE:** criar tela, botao, campo, secao, icone ou
> qualquer coisa visivel. Vale para humano e para IA. Travado por
> `tests/test_estrutura_blender.py`: teste de la' que falha quer dizer
> "isto era de proposito, confirme antes de mudar", nunca "conserte o
> teste".

## 1. A gaveta NAO e' um painel do Blender

A UI vive numa **area `VIEW_3D` propria** (`screen.area_split` a
esquerda), com header, toolbar, regiao N e overlays desligados. Nao
existe `UILayout` la' dentro: cada pixel e' desenhado por GPU num
handler `POST_PIXEL`.

Consequencia direta: **nada de `layout.prop`, `layout.operator`,
`row()`, `column()`, `grid_flow`, `ui_units_x`, `scale_x`** — essas
APIs nao existem aqui. Quem vier do painel N legado
(`VIEW3D_PT_cabinet_creator`, no arquivo mas NAO registrado) vai
tentar usa-las por reflexo.

Em troca, aqui `blf.dimensions()` **mede texto de verdade**: nao
estime largura com constantes `PX_*`, isso era remendo do UILayout.

## 2. As tres camadas

| Camada | Funcao | Responsabilidade |
|---|---|---|
| Layout | `_widgets_gaveta` | decide ONDE cada coisa fica |
| Desenho | `_desenhar_gaveta` | pinta o que o layout decidiu |
| Evento | `OBJECT_OT_interagir_gaveta` | despacha o clique |

`_widgets_gaveta(context, largura, altura)` devolve tuplas de
**exatamente 6 elementos**: `(x, y, w, h, rotulo, acao)`. `x`/`y` em
pixels da regiao, origem embaixo a esquerda; `acao` e' `None`
(decorativo) ou uma tupla cujo `[0]` e' o **verbo**. O layout nao
desenha nem le evento — da' para testa-lo sem abrir janela. Misturar
duas camadas na mesma funcao e' o erro mais comum aqui.

## 3. Receita para acrescentar um widget

1. Em `_widgets_gaveta`, `itens.append(...)` e desca `y` pela altura
   mais o respiro (secao 4).
2. Use um **verbo ja' existente** se couber. Verbo novo entra em
   `VERBOS` no teste de estrutura — que existe para te obrigar a
   confirmar que nao e' duplicata — e em `_chave_widget`, se acender.
3. Em `_desenhar_gaveta`, trate o verbo no laco; sem tratamento ele
   cai no `_botao_gaveta` generico, que costuma bastar.
4. Em `OBJECT_OT_interagir_gaveta`, trate o clique. Verbo decorativo
   entra na lista que retorna `{'FINISHED'}` sem agir.

## 4. Metricas

| Elemento | Altura | Passo em `y` |
|---|---|---|
| Aba (Modulos/Portas) | 29 | topo em `altura - 40` |
| Aba de modo / segmento | 25 | 33 / 29 |
| Campo de medida | 37 | 43 |
| Botao de operador | 28 | 34 |
| Titulo de secao / rotulo | 23 / 20 | 31 / 26 |
| Linha da cascata | 25 | 39 |
| Rodape (Chapa/Auto/nome) | 26 | 29 quebrando, 35 no fim |

Margem lateral `x = 12`, `w = max(24, min(540, largura - 24))`; 6 px
entre itens da mesma linha (4 na cascata); raio 4 no botao e 3 no
preenchimento; miniatura de preset `w - 10 == h - 27`; separador de
1 px em `y + 31.5`. Nao invente numero novo: reaproveite a linha mais
parecida.

## 5. Cor e tipografia sempre do tema

`_cores_gaveta()` devolve `(wcol_regular, fundo)` do tema do usuario:
`cores.inner`, `cores.inner_sel`, `cores.outline`, `cores.text`.
**Nunca escreva uma cor literal** — o add-on acompanha o tema claro e
o escuro, e cores cruas ja' foram removidas uma vez da alca.

Texto: `_texto_gaveta` para rotulo fixo, `_texto_cabivel_gaveta` para
o que possa nao caber (reduz a fonte de 12 a 9 antes de cortar).

Ao abreviar rotulo com contagem, use `_abreviar` **so' no nome**:
`Armarios (3)` vira `arm (3)`, nunca `Armarios (`.

## 6. Responsividade

Largura util dividida por `ui_scale`; os cortes sao por **largura
logica**:

| Largura logica | Campos de medida |
|---|---|
| >= 480 px | uma linha, todos lado a lado |
| >= 240 px | duas colunas |
| < 240 px | coluna unica |

Botoes de Montagem: `colunas = min(3, max(1, w // 36))`. A gaveta
**para de crescer em 564 px** (`_LARGURA_MAX_GAVETA`): texto
em coluna larga fica ilegivel e a miniatura vira faixa. Como
`Area.width` e' somente leitura, quem corrige e' o timer
`_limitar_largura_gaveta`, **depois** do resize — nunca um modal.
Regra de ouro, com teste: widget nenhum termina fora de
`min(largura - 12, 552)`.

## 7. Icones vem do GizmoGroup, nao da GPU

GPU desenha retangulo e texto, **nao icone do tema**. Para um icone
nativo, `draw_prepare` cria um `GIZMO_GT_button_2d` em cima do
retangulo e `_icone_acao_gaveta(acao)` diz qual usar; icone deslocado
costuma ser `matrix_basis`, nao o layout.

## 8. Grid de medidas na cena

Passar o mouse num campo de medida (ou abri-lo para edicao) desenha a
caixa envolvente do alvo **na viewport vizinha** e acende as quatro
arestas do eixo daquele campo. Tres partes que precisam concordar:
`EIXOS_MEDIDA[modo][rotulo]` (rotulo sem entrada nao acende); a caixa
de `_caixa_da_medida`, que em `INDIVIDUAL` e' orientada **pela chapa**
(girada, a Espessura nao e' a vertical do mundo); e
`_desenhar_grid_medidas`, handler **`POST_VIEW`**.

O hover vem de `VIEW3D_GT_campo_gaveta`, Gizmo invisivel por widget
(secao 11). Widget com icone tem dois gizmos: o do icone (tooltip e
clique) e o retangular (hover), que exclui o disco do icone para nao
roubar o pick; o glow soma os dois `is_highlight`.

**O glow vale para QUALQUER botao.** `_chave_widget(acao)` da' a
identidade (None = decoracao) e `_glow_gaveta` pinta o halo -- a mesma
funcao da alca, nunca uma copia. Duas regras caras:

- O halo vai **antes** do corpo do botao. Por cima, lava o texto.
- `_glow_gaveta` liga o **proprio** `blend_set('ALPHA')`: `blf.draw`
  altera o estado e o halo sai OPACO do segundo widget em diante.
  Vale para todo desenho com alfa depois de um texto.

## 9. Enum sem dropdown

Nao ha' menu suspenso aqui, e popup e' o que sai da frente do
usuario. Enum vira **fila de segmentos** (`_linha_escolha_gaveta`):
rotulo em cima, uma opcao por botao, a escolhida acesa com
`inner_sel` -- mostra tudo sem clique nenhum. Cuidado com a altura:
segmento tem 25 px e passo 29, campo de medida tem 37; emendar sem
respiro faz o campo cobrir a fila de cima (ha' teste par a par).

## 10. Animacao

Glow e carrossel correm no MESMO timer (`_animar_realces`, 60 fps),
que se desregistra sozinho. Nao crie um segundo. O carrossel desliza
como roleta: o indice INTEIRO em `screen['cabinet_carrossel_*']` e' a verdade,
`_deslizes` guarda so' a intermediaria. Tres regras:

- Em repouso `_deslizar` devolve o proprio alvo: o layout parado fica
  identico ao de antes e o teste ve posicoes inteiras.
- As posicoes saem de `_widgets_gaveta`, nunca do desenho — o
  retangulo de clique anda junto com a peca, senao o usuario erra o
  alvo em movimento e o glow acende a peca errada.
- O trilho e' recortado com `scissor_set`, senao a peca que entra
  aparece por cima das setas; todo scissor ligado tem que ser
  desligado no mesmo laco.

Decaimento exponencial, nao passo fixo.

## 11. Nunca faca

- **Cor literal** no lugar do tema (secao 5).
- **Operador modal persistente** para capturar clique: roubaria evento
  de outros add-ons. Use Gizmo + `test_select` (a alca e' o modelo).
  Modal so' para interacao transitoria — arraste de slider, edicao de
  campo — que termina sozinha.
- **Deixar estado de GPU ligado**, ou supor o estado que veio de
  antes. Todo caminho de saida de `_desenhar_gaveta` fecha com
  `blend_set('NONE')`, e quem desenha com alfa liga o seu.
- **Desenhar a mesma coisa em dois lugares** (o Gizmo da alca tem
  `draw()` vazio de proposito) ou **duplicar geometria entre desenho
  e hit-test** — ha' teste disso.
- **Estimar largura de texto.** Use `blf.dimensions()`.

## 12. Antes de entregar

1. Rodar as tres suites de `tests/` (ver CLAUDE.md).
2. Conferir em **tres larguras** (190, 320, 564) e nos dois temas:
   bug de layout quase sempre so' aparece num extremo.
3. Incrementar `bl_info["version"]`.

Captura vale mais que leitura de codigo aqui:
`bpy.ops.screen.screenshot()` num Blender de verdade pega o que o
teste nao pega — halo opaco, texto cortado, icone fora do lugar.

## 13. Alternativas ja' avaliadas e RECUSADAS

Nao reabrir sem falar com o dono do projeto.

- **Overlay na viewport principal** (jeito do BlenderKit): dividiria
  pilha de evento, estado de GPU e o canto superior esquerdo com
  outros add-ons. A area propria e' imune aos tres.
- **Pop-up / `invoke_props_dialog`**: fecha quando o mouse sai, e
  clicar na viewport e' a acao seguinte do posicionador. Nao existe
  popup fixo no bpy. O dialogo das Portas virou a aba (secao 9).
- **Voltar ao painel N com `UILayout`**: o handler de UI come o evento
  antes de qualquer keymap, o icone nao passa de 16 px e nao da' para
  fixar largura em pixels. Foi o que motivou a gaveta.
