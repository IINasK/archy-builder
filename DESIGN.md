# DESIGN.md — como desenhar UI no Cabinet Creator

> **REGRA DESTE ARQUIVO:** NAO pode passar de 200 linhas.
>
> **LEIA ANTES DE:** criar tela, botao, campo, secao, icone ou
> qualquer coisa visivel. Vale para humano e para IA. Travado por
> `tests/test_estrutura_blender.py`: teste de la' que falha quer dizer
> "isto era de proposito, confirme antes de mudar", nunca "conserte o
> teste".

## 1. A gaveta NAO e' um painel do Blender

A UI vive no **editor Cabinet Creator**, subtipo nativo `NODE_EDITOR`
(`CabinetCreatorMenu`, v365). O subtipo salva sua identidade no .blend;
toolbar, regiao N e overlays ficam desligados. Header nativo conserva o
seletor de editor. Corpo sem `UILayout`: GPU e gizmos reutilizam o layout
atual. Arvore vazia propria habilita os gizmos no 4.2, sem nos do usuario.
Comandos de cena usam `editor.executar`; texto/arraste ficam na origem.

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
`Armarios (3)` vira `arm (3)`, nunca `Armarios (`. A CASCATA da biblioteca
nao tem contagem (pedido do usuario: ocupava espaco) nem limite de niveis:
ramo sem preset nao aparece. LUGAR (pedido do usuario): faixa superior
ou DENTRO do menu (padrao), embaixo da divisoria interativa (metade);
botao `cabinet_lugar_biblioteca` no cabecalho da faixa e no pe' do menu,
trocado no timer. No menu, cada nivel e' um campo SUSPENSO como no Promob
("Escolha..."); a lista FLUTUA embaixo (em cima/colunas sem espaco),
atende primeiro e tira do clique o que cobre. A faixa mantem suas filas.

HUD do MODULO: sempre uma caixa convencional com 8 cantos e 12 arestas
nos limites do envelope; rotulos A1/A2/A3. Vale para L, diagonal, curvo e chapas
inclinadas, inclusive depois de Tab. Nada de P1/P2/R, arcos ou inferencia
de formato no grupo, na HUD ou no menu. A1/A2/A3 usam resize de CAIXA.

CHAPA INDIVIDUAL selecionada (duplo clique): contorno/angulos da propria
face, com cotas A1, A2... editaveis tambem no menu, pelos mesmos alvos da HUD; E mede peles correspondentes. Chapa deformada em 3D usa as bordas das duas peles reais, nunca uma planta extrudada ou caixa nominal; triangulacao interna nao vira cota. Deslocamento transversal > E ganha cota propria junto a uma borda baixa (ex.: A6). So' ela muda;
vizinhas e modulo nao recebem propagacao angular. O arco e' pequeno e
colado na quina, com vertice e lados reais; raio na tela (~26 px), ate'
1/4 do lado menor. Clicar digita, arrastar gira; E/UV/recortes conservados.
A seta consulta a aresta atual. Tab continua a edicao nativa; ao sair,
medidas/cache atualizam. Porta selecionada conserva seu contorno proprio.

Frentes curvas/facetadas: a linha de referencia do puxador acompanha cada
segmento real da borda, inclusive no Alt; a alca usa a tangente do trecho.

## 6. Responsividade

Prateleiras / Divisorias compartilham uma aba e a area de criacao. Perguntar
o tipo antes de marcar; ao concluir, oferecer o outro tipo no mesmo volume
ou Sair. Descontar a espessura nos encontros. Divisoria menor nao exige
alinhar profundidades: perguntar preencher lacuna pela esquerda/direita
ou manter vao. Cada grupo conserva seus campos de edicao e selecao nativa.

Paineis compartilhados do menu: controles e biblioteca rolam separadamente.
Barra vertical do tema so' com excesso; alca proporcional, clique no trilho
e arraste, roda e touchpad vertical. Cabecalho/divisoria/rodape ficam fixos.
O painel sob o mouse recebe a rolagem; Esc no arraste devolve a posicao.

Largura util dividida por `ui_scale`; os cortes sao por **largura
logica**:

| Largura logica | Campos de medida |
|---|---|
| >= 480 px | cotas basicas em uma linha; cotas dinamicas em ate' 3 colunas |
| >= 240 px | duas colunas |
| < 240 px | coluna unica |

Botoes de Montagem: `colunas = min(3, max(1, w // 36))`. A gaveta
**abre na menor largura com L/A/P na mesma linha**
(`LARGURA_MEDIDAS_EM_LINHA` x escala + 2, `_largura_inicial_gaveta`;
teto de metade da viewport) e **para de crescer em 564 px**
(`_LARGURA_MAX_GAVETA`, nunca abaixo da inicial): texto
em coluna larga fica ilegivel e a miniatura vira faixa. Como
`Area.width` e' somente leitura, quem corrige e' o timer
`_limitar_largura_gaveta`, **depois** do resize — nunca um modal.
Regra de ouro, com teste: widget nenhum termina fora de
`min(largura - 12, 552)`.

**Biblioteca no topo (versao 229; referencia do usuario em 13/10/2026).**
Editor `Biblioteca Cabinet Creator` dedicado, atravessando menu e cena. Primeiro split
HORIZONTAL, depois VERTICAL na parte inferior. A faixa tem Modulos |
Materiais, categorias em abas por nivel e UMA fila de fotos com nome e
tooltip. Abas compactas: altura 18, passo 20, fonte 10, intervalo 2 px
logicos (escala do usuario). Altura inicial da faixa: 180 px. Sem botoes
sob os MODULOS: direito na foto OU no nome abre menu flutuante junto ao
mouse com Inserir, Editar e Bloquear/Desbloquear. Abre no SOLTAR; editar
bloqueado fica desabilitado; modelos de fabrica continuam protegidos.
Este menu contextual e' uma excecao explicita a' regra de pop-ups;
confirmacoes continuam na caixa preta da faixa. Ferramentas do catalogo
ficam no cabecalho. Setas SO' quando a fila excede a largura util, e so'
no sentido que ainda tem itens ocultos; sem setas, categorias/fotos usam
a largura liberada. Resize recalcula a necessidade (inclusive offsets
antigos). Roda e setas rolam a fila apontada; Shift+roda percorre os niveis
profundos sem empurrar as fotos para fora. Perguntas longas rolam na faixa. Recolher/Expandir libera altura sem fechar o menu. Altura
ajustavel pela fronteira nativa entre areas. Modulos/Materiais E todos os
niveis ficam numa unica linha em QUALQUER altura: caixas separadas por
divisorias CINZA CLARO de 2 px (derivadas do tema) em TODAS as
juntas, inclusive os primeiros grupos. Cada caixa realca inteira no hover
de uma das abas; o contorno cinza claro fica OCULTO fora desse hover. SEM halo nos
botoes de navegacao, sem capturar o clique das abas. Intervalo 12 px
entre caixas, 2 px entre irmaos. Cada nivel conserva carrossel/roda; Shift+
roda percorre os niveis que nao couberem na largura. Miniaturas crescem
PROPORCIONALMENTE a' altura da area, limitadas tambem pela largura para
caberem com as setas; o ajuste de tamanho conserva sua proporcao da faixa.
Sem alvos fora da faixa. Tema e escala do usuario.
Menu esquerdo: so' as abas e os controles da selecao, sem biblioteca nem
divisoria interna. Layout antigo ainda pode ser lido, mas e' migrado ao
reconectar/abrir. Os cliques da faixa nunca chegam a' cena. Perguntas da
biblioteca ficam na propria faixa. Materiais conservam clique simples
sem pintar, duplo clique, arraste e pintura rapida com o direito.
Fotos RGBA8 com cache LRU de 64 MiB; so' itens visiveis geram widgets e
texturas. Catalogo cacheado por caminho/mtime; abrir .blend e' so' ao
inserir/editar, nunca ao desenhar. Ver `PLANO_BIBLIOTECA.md`.

## 7. Icones vem do GizmoGroup, nao da GPU

GPU desenha retangulo e texto, **nao icone do tema**. Para um icone
nativo, `draw_prepare` cria um `GIZMO_GT_button_2d` em cima do
retangulo e `_icone_acao_gaveta(acao)` diz qual usar; icone deslocado
costuma ser `matrix_basis`, nao o layout.
Na biblioteca/menu, gizmos sao reutilizados/ocultados, nunca removidos
no redraw: tooltip pendente nativo caia em `WM_gizmomap_tooltip_init`.
Campos conservam o operador ligado no setup; no redraw muda so' `dica`.

## 8. HUD parametrica na viewport

Opcoes (engrenagem): "Origens no grupo" = Ocultar/Mostrar; Ocultar por
padrao. Grupos de modulo, portas, gavetas, prateleiras e divisorias escondem
os pontos de origem NATIVOS pela viewport, sem mudar objetos ou malhas.
Peca/folha individual e selecao vazia devolvem o estado anterior. Respeitar
origens ja' ocultas pelo usuario e mudancas manuais por viewport. Salvar/
abrir/desligar devolve o estado nativo, como o contorno; controle independente.

"Bolinhas de apoio" e "Guias nas quinas" = Ligado/Desligado, independentes,
ligados por padrao. Bolinhas desligadas somem do desenho E do clique.
Guias desligadas escondem setas/realces de hover nas cotas e quinas;
os campos de medidas e a edicao continuam disponiveis.

A representacao do armario agora vive na viewport principal: `gpu`
em `POST_VIEW` desenha os contornos e `blf` em `POST_PIXEL` as letras.
O mini-wireframe da gaveta foi descontinuado; os campos continuam nela.
Na chapa individual com peles editadas separadamente (380), contorno e
cotas usam as arestas reais de cada pele, sem projetar o perfil no verso.
E continua nominal quando a secao nao permite medir espessura uniforme.
Moldura afinada/girada por Tab (381) atualiza cotas e centro pela malha,
preservando a madeira no mundo e os parametros do grupo da porta.

A HUD e seus eventos so' funcionam em Object Mode. Clique seleciona o
modulo; duplo clique na mesma chapa isola essa chapa. Shift soma, como
no Blender (`_somar_peca`): Shift+clique soma o grupo inteiro, ou so' a
chapa se o grupo dela ja' esta' em selecao individual (Shift+clique na
chapa ativa a tira); Shift+duplo isola a chapa DENTRO da selecao -- o
resto do grupo dela sai, os outros grupos/chapas ficam. A HUD mostra
TODOS os itens da selecao, sem ordem de hierarquia (`_itens_da_selecao`:
modulo com o Empty selecionado = grupo; outra chapa = individual), e
setas e quinas valem em qualquer um deles (`_acertar_hud` pega o mais
perto do mouse; so' o item do alvo acende). Grupo mostra
A1/A2/A3; E aparece SOMENTE na chapa individual, inclusive ao passar nas
faces estreitas. Espessura do modulo fica no menu lateral.
`_geometria_hud` alimenta desenho e hit-test: hover em uma aresta acende
as quatro do eixo; o contorno da porta e o gap sao alvos separados.
Quina: arrastar move o modulo; com Ctrl (a qualquer momento do arraste)
a quina gruda na de OUTRO armario (caixa da HUD) ou chapa ao alcance de
`RAIO_SNAP_QUINA_HUD` px -- snap especial, so' quinas (nada de vertice,
aresta ou grade); grudada, ganha bolinha cheia no circulo laranja.
Linha A1/A2/A3... (e a E da chapa individual):
No envelope convencional de modulos e grupos internos ha' seis circulos,
um no centro de cada face (raio 2 px, hover 3 px, multiplicados pela escala
da interface; manter area de clique maior). Arrastar move aquela face, fixando a oposta.
Circulos e setas lineares da caixa usam translate NATIVO do cursor:
arraste inicia SEM snap, inclusive com ima global ligado; B ativa o snap
de vertice nativo e a escolha da base. Preservar os atalhos nativos e a
entrada numerica nativa de DESLOCAMENTO (aceita unidade, ex.: 50mm).
Ao apertar B, preservar a geometria ATUAL, inclusive o ultimo movimento
ainda nao desenhado pelo timer. O cursor nativo volta ao inicio, mas o
resize registra o deslocamento acumulado e passa a partir da medida atual.
Base/destino sao escolhidos na madeira que esta' na tela; repetir B nao
duplica deslocamentos. Esc/undo conservam a referencia original do gesto.
O observador consulta o matcher do keymap nativo e repassa todos os eventos.
A HUD abre uma caixa com A1/A2/A3 e a dimensao RESULTANTE durante o gesto;
clique sem arraste continua digitando dimensao ABSOLUTA. Esc restaura
geometria/cursor/selecao; confirmar e' um unico undo. Angulos e segmentos
modelados conservam seus editores. O vao cadastrado nao e' redistribuido
automaticamente por sobrepor outro sistema; os controles permitem corrigi-lo.
seta sai da quina mais perto (`lado`), que fica PARADA; arrastar estica,
clicar digita (Enter/Esc). Caixa de digitar (HUD e gaveta, um nucleo so':
`_tecla_no_texto`): abre com tudo selecionado, mas um OPERADOR continua
a conta ("600" e '+' -> "600 + "); clicar DENTRO da caixa so' move o
cursor (`_cursor_no_x`), fora confirma; "500 + cm" = 500 cm e "51cm00"
= 5100 cm (`_arrumar_texto_medida`). Na E a face da quina fica e a chapa engrossa
para o outro lado (`_redimensionar_chapa_ancorada`, eixo 2).
Medidas (391): milhares com ponto, decimais com virgula, unidade da opcao
MM/CM/M e sem zeros decimais artificiais. Aceitar ponto ou virgula decimal
no texto original; separar apresentacao e buffer, com mapa para o cursor.
Ex.: .1 -> 0,1 mm; 12345.67 -> 12.345,67 mm. Conta continua editavel e
mostra previa: 0,2 + 0,5 = 0,7 mm; confirmar usa o parser nativo existente.
Previa em cache por texto/unidade (128 entradas), sem repetir calculo no redraw;
erros/incompletas nao imprimem excecoes enquanto se digita. Contadores,
nomes, angulos e pixels conservam seu tipo. Caixa preta conserva cor e
tipografia, com raio 4 px escalado, pelo mesmo desenho arredondado do menu.
Seta com teto fixo na tela (`COMPRIMENTO_SETA_HUD`), nunca maior que a aresta; letras somem se o
item fica menor que `FATOR_ROTULO_HUD` x o rotulo (so' a acesa fica).
Letra = aresta do eixo mais FORA na tela, empurrada para longe do centro
da peca (nunca sobre a face); letras que se encostam afastam-se mais.
Modulo que nao e' caixa (canto em L, diagonal, curvo -- os do Promob): a
linha branca segue a PLANTA em baixo e em cima, nunca a caixa envolvente
(pedido do usuario: no L a quina vazia tinha linha). L e P nos lados
inteiros; P1/P2 nos lados que chegam no canto = profundidade de CADA braco
(o outro nao mexe); R na diagonal e no arco (arrasta para dentro = maior);
A nas quinas. Recorte < 100 mm (quina de tras aberta) nao muda o desenho.
Na aba Modulos o mesmo modulo ganha a secao FORMATO (P1, P2, Raio e o
Angulo da diagonal, que deixa a frente do canto parada).

**Gavetas (aba propria, pedido do usuario).** Cabecalho com 7 abas (Modulos | Portas | Fundos | Gavetas | Prateleiras | Divisorias | Puxadores; estreita: Mod. | Portas | Fundo | Gav. | Prat. | Div. | Pux.). Se nem as abreviacoes couberem, substitui a linha por um suspenso fixo com o nome completo da aba atual. Limite medido por BLF com a mesma fonte 12 e margem lateral 9 do desenho, sem corte fixo por largura. Lista flutuante oferece as sete categorias, atende antes do conteudo e fecha ao escolher, clicar no campo ou fora; a troca conserva o contexto e zera a rolagem da aba. Alargar devolve a linha sem alterar a selecao. Separacao cabecalho/conteudo usa prefixo dinamico, nao sete widgets fixos. Fundos: Criar Fundo no topo, dois pontos/snap nativo; tipos Em canal/Sobreposto (pregado)/Interno rente, espessuras 6/9/15 e campos existentes. Desassociar fundo usa UNPINNED com texto, sem corrente/regua; tambem nos internos vinculados. Rotulo completo quando a medicao BLF couber. "Criar Gavetas" laranja no topo;
Criacao 3D (378: translate so' no clique/RELEASE, camera livre entre pontos; view3d.navigate/walk/fly pelo keymap nativo; Definir por volume/plano laranja, 30 px): tres pontos sem ordem -> caixa min/max nos eixos do modulo -> clique na face da frente com realce do tema -> quantidade. Aplicar volume livre tambem exige frente; Backspace volta, Esc cancela. As alcas da HUD ficam suspensas na escolha. Planos de portas/fundos permanecem 2D. Scroll define quantas gavetas; depois vem a caixa
do trilho (Telescopico | Oculto). Modulo selecionado absorve gavetas e prateleiras na HUD (sem segunda seta); ambos acompanham a face proxima sem crescer. Reduzir a caixa consome a folga antes de diminuir os internos, comparando a escolha com o espaco livre entre as faces reais de apoio (desconta E). Frente/caixa/trilho se adaptam ate' o minimo fisico; devolver espaco restaura a escolha original. Gaveta individual menor tambem conserva sua largura enquanto couber. Vale nos campos, HUD e S nativo; a conversao de S com internos conclui no timer normal, nunca dentro do depsgraph. Esc restaura vao/margens/parametros E malhas. Selecionadas (clique na frente = todas
do vao, duplo = uma): so' elas tem linha branca; L/A/P da HUD mudam o vao
(a quina perto do mouse fica) e a profundidade; Alt mostra 3 bolinhas --
as quinas de cima a' esquerda e de baixo a' direita da frente e a da
profundidade. O arraste usa o snap nativo do Blender (vertice/meio de aresta), sem varrer malhas em Python; a propria gaveta e ferragens nao sao alvos, e Esc restaura o cursor e a selecao. O slider fica NA frente (um pouco a' frente dela, no meio da
altura) e anda com ela: a gaveta aberta nunca o cobre. Na aba: Gavetas
(L/A/P + contador), Frente (Sobreposta | Embutida, Espacamento frontal,
Entre gavetas, Recuo, Espessura, Curva), Trilho e o carrossel do Puxador -- de
UMA gaveta (duplo clique) ou de todas. Curva = flecha do arco da frente
(0 = reta), a do gaveteiro de canto do Promob; as alturas desiguais que a
importacao traz somem ao mudar a quantidade. Borda de cada segmento ganha
a seta de L/A/P (altura redistribui com a vizinha, preservando o total;
extremidades ancoram o limite externo). Duplo clique mostra somente a
unidade na HUD e seus campos: L/A/P, Abaixo/Acima, frente, trilho e puxador,
sem contador do conjunto. "Normalizar alturas" abaixo de L/A/P (duas ou
mais gavetas, grupo ou unidade selecionada): iguala as frentes do conjunto
sem mudar o vao, espacamentos ou escolhas individuais. Arraste usa contorno de previa; confirmar refaz
as pecas uma vez; Esc restaura parametros, materiais, abertura e selecao.

Visibilidade (388): faixa fixa de 38 px acima da divisoria da biblioteca; rotulo simples Visibilidade de objetos a esquerda, dois botoes de 36 x 30 px a direita, so' olho e lapis, centralizados. Texto curto Visibilidade em coluna estreita; acoes explicadas pelos tooltips nativos. Biblioteca no topo: faixa acima do rodape. Aparece somente com modulo/peca compativel selecionado; nao aparece sem selecao, em objeto comum, puxador/ferragem isolado ou na aba Puxadores. Sem faixa tambem nao reserva espaco nem desloca os campos. Cancelar criacao conserva o controle se ha' selecao compativel; nao rola com os campos. Opcoes/listas abertas ficam sobre ela. Segue a aba: Portas inclui folhas/molduras/bases/trilhos/ferragens; Gavetas inclui caixas/frentes/trilhos/puxadores; Prateleiras e Divisorias juntas; Fundos; Modulos inclui estrutura. Esmaecer usa WIRE nativo, cor branca e opacidade .22, sem alterar malha, materiais, parentesco, solda, selecao ou H/Alt+H. Raio de superficie atravessa o arame para acessar o interior, mas quinas/vertices reais continuam no snap nativo. Cor/opacidade de arames da viewport sao temporarias e restauradas ao desligar; alteracoes manuais sao conservadas. Nao modifica o render final.

Editar grupo fixa modulo/categoria; seletor nativo do Blender no esquerdo inclui a peca e agregados, direito retira. Enter ou novo clique no lapis conclui em um undo; Esc devolve configuracao e selecao. Guardar inclusoes/exclusoes por UID no modulo, nunca reparentear. Navegacao e menu continuam nativos. Undo/load/unregister limpam o editor, salvar o projeto suspende a exibicao e retoma depois, sem gravar a aparencia temporaria no arquivo. Criacao de internos conserva a pergunta "Esconder portas?" Sim/Nao; Sim aciona este mesmo grupo PORTAS, Nao conserva a vista; sem portas solidas visiveis, segue direto.

**Prateleiras (379).** Cota V em edicao + scroll cria previa de novas unidades so' naquele vao (Enter confirma, Esc cancela; apoios preservados). Mesma blocagem: moldura comum de leitura, cotas de todos os segmentos da orientacao selecionada; nao misturar prateleiras/divisorias. Portas podem ser ocultadas com agregados pelo menu (28 px) ou Shift+G -> Grupo da porta -> H; nao remonta, Alt+H/undo nativos. O assistente das
gavetas com os mesmos tres pontos sem ordem e frente explicita (376). Scroll define quantas; o clique cria. A profundidade vem da caixa escolhida, sem trilho; folga
da frente e' o Recuo da aba. Selecionadas (clique = todas do vao, duplo = uma): a HUD tem o
L/A/P do vao e uma linha por VAO entre as prateleiras, no meio da largura,
com o VALOR ao lado (sao varios; uma letra so' nao diria qual). Arrastar ou
clicar e digitar um vao anda SO' a prateleira de cima dele. Na aba:
Prateleiras (L/A/P + contador), Chapa (Espessura, Recuo, Folga lateral).
Na largura padrao, A1/A2/A3 tem a MESMA largura com o contador ao lado; estreita conserva colunas iguais, movendo o contador para outra linha se necessario.
Espacamento: botao de 37 px com simbolo proprio (seta para esquerda, barra vertical, seta para direita; GPU, excecao pedida pelo usuario) e texto "Centralizar espacamento" a' direita; abaixo, campos E do escopo selecionado, numerados de baixo para cima. Sem Igual/Livre, Entre prateleiras ou Abaixo/Acima.
Excluir uma unidade atualiza quantidade/vaos sem mover as demais; centralizar e' explicito, sem botao ao lado do contador.
Centralizar com uma unidade sem subdivisoes selecionada iguala apenas os vaos acima e abaixo dela, entre as faces vizinhas ou os limites do vao; conserva as outras. Com o grupo selecionado, distribui todas.
Editar um campo E anda so' a prateleira correspondente (o vao do topo anda a ultima).
Mover com G nativo atualiza os mesmos campos E e cotas da HUD apos confirmar (Objeto) ou sair do Tab (individual/grupo), sem redistribuir. Se as unidades trocarem de ordem, E continua de baixo para cima e os ajustes acompanham a chapa.
Detalhamento: grupo selecionado usa quantidade total e blocagem completa. Unidade selecionada usa quantidade local (ela e suas copias) e subdivide so' o intervalo entre os apoios externos inferior/superior; fora dele, preservar chapas/gavetas. Qualquer copia selecionada reencontra o mesmo trecho. Parametros/Centralizar valem para as copias; reduzir preserva a ativa, zero exclui apenas o trecho. Contador, cotas E visiveis e moldura seguem esse escopo; a moldura local nao redimensiona a caixa global. Ultimo E local move a ultima copia, nunca o apoio. Tab individual conserva o escopo nativo da malha.

**Divisorias (aba propria).** "Criar Divisorias" no topo; dois cantos e scroll (quantidade), mesmos snap e cancelamento nativos das prateleiras. Chapas verticais segmentam os sistemas que atravessam o vao: 3 gavetas viram 6 com uma divisoria central; prateleiras sao partidas sem mudar a altura. Aba: A1/A2/A3 do vao, Espessura/Recuo, E1..En+1 da esquerda para direita. Os dois lados continuam editaveis nas abas de origem. Clique seleciona divisorias, duplo isola a chapa; Tab/G nativos.

**Porta de correr: a folha.** Na porta de correr selecionada, uma fila
Chapa | Quadro de aluminio (depois do trilho, com ou sem moldura). Quadro =
o perfil de aluminio do despenseiro do Promob em volta de um painel fino,
que tem material proprio (o vidro/espelho); o trilho continua o nosso.

**Snap = o nativo do Blender (v304).** Assistentes, cantos e Ctrl da
quina usam o snap do Blender (vertice/meio de aresta). O detector de
angulos com rotulos ("Quina reta", "Fim da curva") saiu na v309.
Posicionar puxador (`OBJECT_OT_posicionar_puxador`): 1o a linha (borda da
face sob o mouse), depois o ponto; scroll = n snaps (k/(n+1)); botao
direito volta a linha. Linhas grossas em triangulos (`_quad_2d`).
Reposicionar com Alt (389): recusar ancora ocupada e intervalos sobrepostos
na mesma borda/face da chapa; considerar a posicao efetiva ja' limitada nas
pontas, nao so' a fracao digitada. Usar a referencia numerica compartilhada,
sem extrair malhas no arraste. Outros puxadores, mesmo ocultos, conservados;
nao substituir/remover perfil do destino ao soltar. Destino ocupado mantem
o ultimo lugar valido e avisa no cabecalho nativo. Mais de um puxador na
mesma chapa continua permitido em posicoes separadas ou na face oposta.
Esc devolve a origem inclusive em cenas legadas com sobreposicao inicial.
Puxador PERFIL = o modelo de aluminio do usuario (arquivo dele, extraido
por `extrair_puxador.py`: malha, material e texturas como sao), na borda
inteira, SEM deformar chanfro nem arredondado (pedido do usuario): na
largura as PONTAS andam inteiras; na espessura, a escala antiga esticava
os cantos das costas -- agora a secao se divide no maior vao sem vertice
(`_corte_do_perfil`, o trecho reto): as costas andam inteiras e so' o
reto acomoda. Porta tao fina que o reto sumiria: volta a' escala. A
frente, o labio e a cava sao os dele.
Tira 34,81 mm da madeira (o J de caixas, sem o asset, tira 30).
Puxador BORDA (v322) = o slim de aba do usuario (`extrair_puxador_borda.py`):
tampo de 1,1 mm na borda, enrolado 20 mm a' frente, aba de 13,4 mm nas
costas com 2 furos (~4,3 mm). Padrao comercial pesquisado: 80 mm, furos a
64 (8 mm das pontas: 144 -> 128). Comprimento e espessura da porta so'
andam trechos retos (vaos sem vertice); furo/chanfro/enrolado nunca
escalam. Weighted Normal no objeto (faces planas sem degrade).
PARAFUSO padrao (v323; v326 = foto do usuario, `gerar_parafuso.py`):
chipboard 3,5 x 14 cabeca CHATA escareada Phillips, haste lisa curta,
rosca e ponta, bicromatizado, tamanho real; cabeca de 5,78 que NAO afunda
ate' o fim, topo 0,876 acima da peca (v329, refinamento do usuario na cena
dele; origem na superficie, `cabinet_versao` troca a malha velha); o
arame (previa e selecao) e' so' o TOPO da cabeca, circulo e cruz (v328:
fundo da cruz, borda dupla, cone e rosca por cima de tudo embaralhavam). Vai
nos 2 furos da aba do BORDA (cabeca para tras, haste na porta; porta fina:
a ponta para 3 mm antes da frente), nos 4 de fixacao da dobradica reta
(placa e copo; o de regulagem e' o do modelo) e nas placas da articulada.
Nomes de objeto em portugues e sem sublinhado (pedido do usuario):
"Folha 01", "Puxador Perfil", "Pistao Corpo", "Dobradica Copo"...; o rig
importado tambem (objetos, malhas, ossos, modificadores, material).
Correntes (soldas): cada ligacao de adjacencia associa 2 quinas e grava
a folga do momento -- a ORIGEM da solda. Com a tecla das opcoes
segurada (`tecla_corrente`) aparecem TODAS as quinas soldadas do item
cujo DESVIO da origem passa de `LIMIAR_CORRENTE_VIEWPORT` (5 mm); o
"so' a mais perto da camera" foi descontinuado. Cada linha tem a
corrente (clique DESAGREGA a peca inteira, `desagregar`) e, a direita,
a regua (`cabinet_resetar_distancia`). O Alt+clique e' de
`cabinet_clique_corrente` (o gizmo nativo nao aceita modificador).
PERGUNTAS (regra do usuario para todo o design): pop-up SO' quando a
acao veio da VIEWPORT (atalho, Alt+corrente/regua, Enter no modo de
vertices). Veio de um botao da GAVETA: a pergunta aparece DENTRO dela,
logo abaixo do botao, numa caixa preta com as respostas lado a lado
(`_pergunta_na_gaveta`, verbos `pergunta`/`resposta`). Tudo passa por
`_perguntar` (`_na_gaveta` diz a origem) e se responde por
`cabinet_responder_pergunta`; nunca `popup_menu` direto.
Edicao da solda (355): criar/reancorar esconde e bloqueia os controles da HUD de geometria e limpa o hover; encerrar restaura. Corrente, regua, distancia e snap da solda permanecem ativos. Criar solda e confirmar usam o destaque laranja ja existente no menu.
Criacao da solda (353): controladores corrente/regua e numero editavel ja na previa; corrente remove somente aquele par, regua zera pela ancora final. Mira branca/laranja acompanha o cursor nativo durante o gesto, com distancia desde o primeiro ponto.
Criacao da solda (352): painel proprio, sem Orcamento/Comodo; distancia editavel, reset para zero pela ancora FINAL fixa, voltar, Criar/Cancelar. Direito/Esc cancela e restaura a previa; Backspace/Ctrl+Z volta etapa. Alt reancora na mesma peca pelo snap nativo (PRESS/RELEASE); confirmado, corrente/regua e distancia numerica continuam visiveis/editaveis, mesmo em zero. O zero definido na criacao vira a referencia futura. Soldas antigas conservam a origem anterior. Ancora removida/ambigua exige reparo explicito, sem trocar silenciosamente por outro vertice.
Montagem tem Criar solda em linha inteira, acima de Corrente e Resetar distancia
(regua); Agrupar e Converter seguem no F3. Criar reutiliza o assistente nativo:
modulo selecionado escolhe a chapa no primeiro ponto; chapa individual ja' a define. A regua fica AZUL
com qualquer solda fora da origem; quem se mexe sai da selecao:
chapa unica ativa = ELA se move ate' todas as soldas voltarem
(`_plano_reset_chapa`); se so' voltar mudando de medida, pergunta
"Mover mesmo assim?" (pop-up so' depois do SOLTAR: `esperar_soltar`).
Modulo ativo = o MODULO se adapta a chapa: as pontas soldadas esticam
ate' ela (`resetar_ponta`) e o modulo se redimensiona. Na viewport a
regua passa a peca da linha (a ativa, ou a que se afastou:
`_peca_afastada`) e volta todas as soldas dela. Corrente e regua usam essa MESMA peca: chapa individual ativa, ou a que se afastou quando o grupo esta' selecionado. A ponta que guarda o registro nao decide quem sai; desagregar a lateral retira ela do pai/colecao e dos limites/vaos do modulo, sem soltar base/tampo por engano.
Bolinhas brancas nas pontas das linhas (Alt) sao as ANCORAS: arrastar
uma ate' outro vertice das duas pecas (ima por tela; na malha modelada,
qualquer vertice dela -- o chanfro --, gravado como `v<indice>`) so' grava qual
vertice esta' soldado em qual (`OBJECT_OT_arrastar_ancora`); a regua
leva ate' la' a peca que se move (a ativa, de qualquer lado da solda):
ela anda pelas soldas normais e o que sobra DEFORMA a ponta ou a face
dela (`_deformar_ancoras`), mesmo torta. Par que ja' encostou some da
viewport (nao sobrepoe linha, bolinha e botoes). Bolinha e botao disputam o clique
pelo mais perto do mouse (`_alvo_da_corrente`).
Botao Corrente da gaveta (no lugar do ima), pela SELECAO
(`_acao_corrente`): azul = o clique desagrega, cinza = associa.
UMA peca (individual) agregada -> "Voce realmente deseja desagregar
esse objeto do grupo?"; o GRUPO (clique no modulo) -> "Voce tem
certeza que deseja desagregar todos os itens deste grupo?" (o modulo
que esvazia e' apagado, `desagregar_grupo`). Peca solta sozinha -> modo
"selecionar vertice" direto. Alvo(s) primeiro e a peca de fora POR
ULTIMO (o ativo): conecta por distancia ate' 5 mm
(`ALCANCE_CONEXAO_AUTOMATICA`), so' com os alvos; mais longe, o mesmo
"selecionar vertice", so' nos vertices REAIS dos alvos -- vertice da peca,
depois o canto alvo, repetindo; Enter ou "Confirmar" no pe' -> "Juntar
ao modulo?". Usa o translate/snap NATIVO compartilhado para marcar vertices, nao cantos de uma caixa. Sim entra no modulo sem mover a madeira. Solda 359: um registro, um par de vertices e um fio por par de objetos; destino manual repetido e recusado. Cada conexao conserva o afastamento 3D atual no referencial local do destino (`adj_<ponta>_origens`), que acompanha o giro do modulo. Resetar recupera esse gap cadastrado; o valor zero deixou de ser o destino automatico. Uma translacao compativel com todas as soldas conserva a malha inteira; restricoes distintas conservam os pares de E. Juntas antigas continuam usando a folga escalar. Associa
sem zerar as ligacoes dos outros (`associar_por_distancia`). Pop-ups
aqui sao pedido explicito. O botao dispara no SOLTAR
(`OPERADORES_NO_SOLTAR`): no PRESS o pop-up nascia sob o mouse e o
proprio RELEASE escolhia "Sim".
Esc restaura. Durante G/R/S a HUD some inteira (`_transformando`). Cores, espessura
(`POLYLINE_UNIFORM_COLOR`, ate' 50 px) e rotulos vem da engrenagem; o
realce "Gizmo" pinta L/P/A com os eixos X/Y/Z do tema e E de laranja.
A gaveta segue as cores do tema.
Varios itens selecionados (`_itens_da_selecao`, Shift soma): a SELECAO
diz o que se edita -- grupo inteiro, uma chapa, ou so' os selecionados.
NAO ha' "Editar como? Individual | Grupo" nem "Adicionar | Finalizar"
(recusado pelo usuario). Clicada a seta de um item, os que ainda nao
tem seta dao duas piscadas de luz nas linhas (`_piscar_pendentes`,
`DURACAO_PISCADA_HUD`); cada clique numa linha deles escolhe a quina
parada (o escolhido some da escolha) e o ultimo leva a digitar: o valor
vale para todos, cada um ancorado na sua quina. Esc desfaz tudo.
Individual/Grupo da gaveta so' indica.
Modulo/porta selecionado desliga `show_outline_selected` (nao ha' contorno
por objeto) e o devolve como era: so' religa o que o add-on desligou
(`sincronizar_contornos`; salvar/abrir/desligar devolvem antes).

O hover vem de `VIEW3D_GT_campo_gaveta`, Gizmo invisivel por widget
(secao 11). Widget com icone tem dois gizmos: o do icone (tooltip e
clique) e o retangular (hover), que exclui o disco do icone para nao
roubar o pick; o glow soma os dois `is_highlight`.

**O glow vale para QUALQUER botao.** `_chave_widget(acao)` da' a
identidade (None = decoracao) e `_glow_gaveta` pinta o halo -- a mesma
funcao da alca, nunca uma copia. Botao de texto cujo operador recusa a
selecao (`_operador_apagado`) sai cinza, sem halo e sem clique. Nada de
nome do item nem medida repetida em rotulo, e nada de botao que so'
repete o que o add-on ja' faz sozinho (Sincronizar, Recalcular): a
gaveta mostra o estado, o timer o mantem. Duas regras caras:

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
**Gaveta por CONTEXTO** (conceito do usuario, TODAS as abas): sem nada
selecionado a aba mostra SO' o botao laranja de criar ("Criar Portas" /
"Criar Puxador"; a Modulos, cuja criacao e' a biblioteca, nao mostra
nada -- o orcamento, da cena inteira, mora nas Opcoes). Criando, os campos nascem etapa a
etapa. Selecionado, so' o que vale para AQUELE item (`_selecionado`:
ativo sem selecao nao conta): o bloco de medidas e' da aba dona do item
(modulo/chapa/objeto de fora = Modulos, porta = Portas, puxador =
Puxadores), nao fixo nas tres; porta sem dobradica; ferragens
selecionadas = so' a quantidade e o afastamento delas.
"Criar Portas" fica no TOPO da aba Portas, logo abaixo das abas, largura
inteira e texto centralizado (backlog do usuario, Epico 2.3); o bloco de
medidas desce 38 px nessa aba. Sem porta selecionada a aba nao mostra
folga/afastamento/vaos (Epico 2.1/2.4): os campos vem com a porta.
Wizard de criacao: DOIS cliques nos limites opostos da porta; fio branco
na diagonal e previa das folhas. O mesmo solver encontra o vao interno,
sem pedir outros pontos. Dai' saem medida da folha, vao, espessura e a
dobradica, que e' AUTOMATICA (borda no limite do modulo = Reta, na
metade da chapa = Curva, dentro do vao = Super Curva) e nao aparece
como escolha nem na aba. Canto invalido pode ser remarcado sem perder
o primeiro; botao direito em Folhas volta ao segundo. Cobertura fora
dos tres padroes pergunta "As medidas estao corretas?" (Nao = marcar de
novo). Depois, caixas desenhadas ao lado do clique (popup nativo nao, o
release respondia) que NUNCA saem cortadas (`_botoes_assistente` mede a
regiao: perto da borda a caixa vai para o outro lado do mouse ou
sobe/desce; o recado que segue o mouse idem), na ordem: Folhas (1 | 2) -> abertura so' com o que
nao se deduz (Giro | Basculante, ou Giro | Correr na embutida; 2 folhas
por cima = giro direto) -> clique na borda das dobradicas (verde; 2
folhas de giro = as duas; basculante = sempre CIMA, sem perguntar) ->
scroll = quantidade (padrao pela altura: 2/3/4/5) -> mouse em Y = margem
das quinas (padrao 100 mm) -> basculante: scroll = quantidade de pistoes
e a posicao nasce AUTOMATICA (modelo real do catalogo; aberta = pistao no
dobro do fechado); o mouse em Y so' SOBE o pistao (descer passaria do
curso). Esc cancela, botao direito volta uma etapa.
Previa de dobradica, pistao e puxador = o WIREFRAME da peca de verdade
(pedido do usuario; antes caixas de volume e, no puxador, so' o ponto da
ancora), na cor de realce e na espessura das linhas da HUD, raio-X
(`_desenhar_arame`, POLYLINE em 3D). O wizard planeja pelas MESMAS
ferragens que a porta monta (`_ferragens_da_porta`): a Reta e' o rig do
usuario, desenhado pelo CONTORNO (vincos > 30 graus, sem a subdivisao:
~4 mil segmentos em vez de 190 mil) gravado no .json do asset por
`extrair_arame_dobradica.py`, em lote na GPU peca a peca; caixas,
canecos e pistoes pela forma deles. O pistao aberto ganha um fio branco.
O posicionador do puxador mostra o puxador na linha sob o mouse.
Aba Portas criando (blocagem do usuario): marcada a area, as medidas da
porta (so' leitura: saem dos cliques); depois a COPIA da caixa -- cada
pergunta APARECE quando o wizard chega nela (Medidas corretas?, Folhas,
Abertura), clicavel como a da viewport: o MODAL atende o clique na gaveta
(`_responder_pela_gaveta`); responder de novo uma fila refaz dali. Depois,
Dobradicas e Pistoes EDITAVEIS (`_secao_ferragens_gaveta`): quantidade em
segmentos e afastamento/distancia do topo em campo; digitado na etapa do
mouse em Y, o 1o movimento parte do valor. A mesma secao, com as
ferragens SELECIONADAS, edita todas as portas do modulo (o clique numa
ferragem leva a gaveta a' aba Portas). Porta pronta selecionada: sem a linha
Reposicionar no vao / Definir como frente / Espelhar porta (pedido v351).
Comeca diretamente nas CATEGORIAS com o titulo de Montagem
(`_titulo_secao`, auditoria do usuario: campos compactos, claros, rotulo
inteiro): **Porta** (L/A/E), **Folhas** (Entre folhas/planos e o campo
COMPACTO das folhas na ponta -- contador com rotulo: arrasta e digita; os
segmentos 1 2 3 4 sairam), **Posicao** (Afastamento ou Recuo), **Trilhos**
(Recuo, correr embutido) ou **Moldura** (Espessura, Rodape, Testeira) e
**Abertura** (slider dos retratos no titulo). Rotulo curto dentro da
categoria ("Recuo", nao "Recuo para trilhos"): o titulo ja' diz de que e'.
Dobradica (automatica) e Converter
em porta/dupla sairam da aba (pedido do usuario; F3 segue).
Correr: dois cantos de DENTRO = embutido; limites externos =
COM MOLDURA -- folhas de 18 na frente do modulo, cobrindo a
frente inteira, num trilho de aluminio do usuario (dois canais, a 1a na
frente), e a moldura de chapas de 15 refeita com a porta (revestimento das
laterais, base do trilho + testeira em cima, base + rodape embaixo; soma
acima e abaixo do modulo). Limites mistos (cobertura em alguns lados)
PERGUNTAM "Porta embutida ou com moldura?" -- moldura usa o modulo
inteiro, embutida a medida de dentro da chapa.
Com moldura vem mais uma caixa: "A porta tem base?" -- sem rodape a
moldura vai direto no chao (rodape 0). A moldura passa a SER a caixa do
armario: L/A/P do modulo e a caixa da HUD contam com ela (envelope).
Depois da base, "Qual trilho?": PESADO (perfis de aluminio) ou LEVE
(canais fresados nas bases + U de embutir, folha de 15, SEM testeira: a
folha corre a' vista ate' a base de cima); na porta pronta,
os dois segmentos ficam no fim da categoria Moldura.
Porta pronta: o clique simples (a porta inteira) mostra, em raio-X, o
contorno BRANCO de cada folha, as linhas internas do vao em AMARELO e
os mesmos fios dos 4 cantos (as dobradicas nao: ver Ferragens); segurando Alt aparecem as 4 bolinhas brancas e arrastar
uma ate' outro vertice refaz a porta como se o clique tivesse sido
dado ali (cobertura e dobradica automaticas; fora do padrao pergunta).
Abertura (Epico 4): um SLIDER por folha, so' com a porta ou a folha
selecionada, na base da folha FECHADA e 30 mm a' frente (parado enquanto
ela abre, nao foge do mouse), por cima de tudo. GROSSO (pedido do
usuario): trilho de 13 mm com pontas redondas e borda clara, parte
aberta na cor de realce, bolinha branca de 12 mm de raio e o valor numa
caixa preta acima dela (graus; mm no correr). Medidas em MM do mundo,
nao pixels (pedido do usuario): afastar o zoom encolhe tudo na mesma
proporcao da porta; perto para no teto de 2 px/mm; o valor some abaixo
de 7 px (ilegivel). Recuado das pontas da folha
(40 mm ou 12% dela): numa porta dupla os dois NUNCA se encostam, sobra
folga no meio. CORRER: o slider vai do centro da folha fechada ao da
aberta (a bolinha anda embaixo dela), um degrau de 40 mm acima por
trilho -- os de uma porta de varias folhas nao se sobrepoem. So' a
BOLINHA pega o clique (gizmo do tamanho dela, que
acende sob o mouse); o trilho nao. Pegar fora do centro nao a faz pular. Arrastar para a DIREITA abre, para a esquerda fecha, seja qual
for o lado da dobradica (pedido do usuario). Esc/botao direito volta.
A folha NUNCA fica rente a' borda do armario (prints do usuario), em
nenhum cenario: toda cobertura padrao deixa 2 mm de respiro -- Reta cobre
a espessura menos 2, Curva a metade menos 2 (duas portas na mesma chapa
do meio nao se encostam), embutida e correr ficam 2 mm para dentro do
vao. Nao ha' "Folga no perimetro" (pedido do usuario: sempre zero; so'
a porta importada guarda uma, por dentro). Cobertura fora do padrao,
marcada e confirmada pelo usuario, vale como marcada. Correr: sem campo
de sobreposicao -- com a largura da folha editavel ela e' consequencia
(o usuario nao via a diferenca entre as duas).
Dobradica RETA = o modelo e o rig do usuario (arquivo dele, extraido por
`extrair_dobradica.py`), importados tal e qual -- nada refeito: a folha
abre como a dele (gira E anda, 91,7 graus no fim) e o copo fura a folha
(Boolean -- o cortador e' a unica peca refeita: o do modelo era um
octogono menor que o copo e fora do centro, sobravam lascas da porta
dentro do copo; agora e' um cilindro medido no copo, com 0,2 mm de folga).
A folha fica no minimo a 1,86 mm do modulo, a folga do modelo
dele: encostada, o canto da folha aberta entrava no tampo (print do
usuario). Curva e embutida seguem com o volume em caixa e eixo fixo.
Ferragens (dobradica, caneco, pistao, trilho) sao malhas de verdade, e
NADA fica fora da edicao nativa (pedido do usuario): duplo clique numa
peca seleciona so' ela, como objeto do Blender (Tab, G/R/S, X,
modificadores). Elas so' nao acendem junto com a porta nem com o modulo.
A malha de uma peca do rig e' dividida entre as copias (editar uma muda
todas); a das caixas e' refeita quando a porta muda. Dobradicas e pistoes so'
APARECEM criando a porta ou SELECIONADOS (pedido do usuario): clique numa
dobradica = todas as dobradicas do modulo, num pistao = todos os pistoes,
Shift soma (ou tira) o outro tipo. Nesse modo so' elas ficam acesas
(o arame delas, raio-X): porta sem contorno branco, modulo e puxadores
apagados. Segurando Alt, um controlador (bolinha branca) por porta e
tipo: o da dobradica corre na BORDA (margem; passar do meio conta da
outra ponta, espelhada), o do pistao na LATERAL (distancia do topo, trava
no curso; voltar ao ponto automatico grava 0). Arrastando, aparece o
trilho; Esc/botao direito devolve. Trilho do correr: o clique vale pela
folha.
Varios itens selecionados: o ATIVO (a selecao principal, que manda nas
funcoes) tem as linhas da HUD levemente mais grossas (+40%, min. 1 px;
`_principal_hud`). Com um item so', nada muda.
Modulo selecionado (clique nas CHAPAS, que leva a porta junto):
nada do desenho da porta aparece -- vao amarelo,
diagonal, cantos e sliders; fica so' a HUD do modulo (pedido do
usuario: visao mais limpa).
Selecao de porta (Epico 3): clique = a porta inteira, nunca o modulo;
duplo = uma folha. Folha sozinha tambem desliga o contorno nativo.
Opcoes: engrenagem FIXA no pe' da gaveta (`_rodape_gaveta`), painel que
sobe dela por cima do conteudo, uma linha por opcao (`LINHAS_OPCOES`,
rotulo | controle; empilha < 250 px). EXCECAO pedida pelo usuario, so'
ali: lista suspensa (`suspenso`, itens apos o widget `fundo`, desenhados
por ultimo e atendidos primeiro), `faixa` 1-50 (arrasta; clique digita)
e `cor` (atalhos + quadro S/V + matiz, aberto na propria linha).

Nome do grupo (pedido do usuario): ao agrupar, F3 (viewport) abre o
dialogo do Blender com "Armario LxAxP" ja' escrito; a Corrente juntando
pecas soltas pela gaveta mostra a MESMA caixa preta das perguntas, com o
campo "Nome do grupo: ...|" (digita direto, Enter/OK confirma, Esc/Manter
fica a sugestao). Outliner: cada armario e' uma Collection com o nome dele;
dentro, o Empty, as chapas e a porta ("Porta Dupla", "Porta de Correr"...).

Comodo do orcamento, no fim da aba Modulos (so' com armario
selecionado): titulo "Orcamento" como o de Montagem (sem separador: os da aba sao da cascata). Com armario
selecionado, o COMODO e' UMA linha "Comodo: Cozinha" com a seta da lista
suspensa (a grade fixa de 14 segmentos ocupava a aba -- RECUSADA pelo
usuario). O clique EXPANDE a lista dentro da aba, empurrando o resto
(nao flutua: sem conflito com o recorte do painel): os comodos do
prompt, os ja' digitados na cena, "Sem comodo" (se ha' um) e "Outro
nome...", que abre o campo da caixa preta logo abaixo (Enter/OK,
Esc/Cancelar). Escolher fecha a lista e vale para todos os armarios
selecionados. O comodo e' uma PASTA no Outliner (Collection na raiz com
as dos armarios dentro).

"Gerar orcamento (.txt)": ULTIMA linha do painel de Opcoes (engrenagem),
largura inteira -- e' da cena inteira e o add-on e' vendido, entao nada
de "ERP" nem de copiar para a area de transferencia (RECUSADO: o
usuario quer o arquivo). Dispara no SOLTAR e abre o "Salvar como" do
Blender (sugere "Orcamento - <nome do .blend>.txt" ao lado do .blend).
Salvo, o botao ACENDE com o que fez ("Salvo: N modulo(s)") e as
pendencias aparecem numa caixa preta logo abaixo, dentro do painel, por
30 s -- so' o relatorio da barra de status passava despercebido.

"Criar Puxador": mesmo padrao do "Criar Portas" -- LARANJA, no topo da
aba Puxadores, largura inteira, texto centralizado, mais forte enquanto
posiciona ("Posicionando o puxador... (Esc cancela)"). Saiu do pe' fixo.
"Editar parede" / "Sair da edicao da parede" (v361): tres entradas -- vertices BMesh conectados em Edit Mode (1 grau/2 mm), Automatico por hover e Por pontos (3+ pontas) em Object Mode. Esquerdo marca, Backspace volta, Enter aceita, direito/Esc cancela; menu lateral oferece as mesmas acoes. Hover reaproveita o realce do atach. Local View usa exibicao temporaria SO' da area, mantendo moveis reais associados; a malha original nao muda e as outras partes da mesma planta deixam de bloquear a camera. Sair restaura isolamento/ocultacao; limpeza de undo no timer normal. Seletores de metodo ficam em Modulos ou durante a escolha, sem invadir outros assistentes. Entrar/sair continuam:
o mesmo padrao, 30 px, laranja para entrar e laranja forte para sair
(`OPERADORES_DESTAQUE`, tupla: a acao nunca e' hasheada).
Encaixe na parede (390): a referencia e' o envelope do grupo, incluindo
molduras e chapas de apoio de portas de trilho pesado. Usar a mesma lista
de pecas e medidas nominais da HUD; nao o vao interno de montagem da porta.
Vale para arraste, quinas, cotas, limites da parede e obstaculos entre
modulos, nos quatro lados de costas. Folhas abertas/puxadores e chapas
fora do grupo nao ampliam a referencia. Dimensoes e malhas nao sao alteradas.
Posicionando, aparece o MODELO num carrossel de RETRATOS (pedido do
usuario: a foto a 45 graus, como na biblioteca, no lugar dos nomes; setas
quando nao cabem): os de fabrica e os do usuario (categoria Puxadores da
biblioteca). O posicionador atende o clique e troca a previa na hora. Reposicionar (pedido do usuario): com Alt, a ancora de
cada puxador da selecao vira bolinha branca; arrastar leva-o a outra
borda SO' das chapas do grupo dele (folhas da porta, ou chapas do
modulo), snap de LINHA na face virada para quem olha, e ele sai virado
conforme a borda; o perfil devolve a madeira e corta a nova (um por
borda). Esc devolve. Clique simples no puxador vale pela peca em que ele esta' (porta, gavetas); DUPLO clique (v340) seleciona SOMENTE ele e abre Puxadores; trilhos das gavetas permanecem com elas. Puxador do add-on selecionado: medidas e o modelo
(`_trocar_modelo_puxador` refaz AQUELE); objeto de fora: "Usar como
puxador" -- encostado numa chapa vira o puxador dela no mesmo lugar;
solto, a gaveta pede o clique na face que encosta na porta e o criador
abre com o modelo novo. "Converter em puxador" (so' marcar) ficou no F3.

TODO retrato (puxador, abertura, dobradica) tem o MESMO quadrado
(`_lado_retrato`, pedido do usuario): o do slider pequeno ao lado do
titulo da fila (`cabinet_tam_retrato`, 40-128 px); so' encolhe para
caber tres lado a lado.
Retratos em toda escolha de MODELO: abertura (Giro/Basculante/Correr)
criando e com a porta selecionada; a dobradica, que e' AUTOMATICA, so'
mostra o retrato do tipo detectado, pequeno e sem clique (tres retratos
empurravam os campos para baixo da divisoria) -- na etapa da borda, o da
borda sob o mouse. O retrato e' SO' a dobradica, sem o modulo (pedido do
usuario); Curva e Super Curva usam o da Reta ate' terem modelo proprio
(`FOTOS_PENDENTES`). Layout do usuario (mockup): na linha "Abertura" ficam o
retrato da abertura ESCOLHIDA (clicar volta a' escolha das tres), o da
dobradica e, ao lado, "Dobradicas:" com o CONTADOR (< 2 >: arrastar ou
clicar na metade direita/esquerda) -- nao mais cinco segmentos; embaixo,
o afastamento. O "aceitar" da etapa e' um quadrado VERDE com visto, colado
a' direita do campo que ela edita (o mesmo do clique na viewport; a etapa
seguinte parte do mouse quando ele volta). Gaveta estreita (< 260 px):
empilha. Qualquer campo de valor ARRASTA: direita aumenta, esquerda
diminui (1 mm/px; Shift fino, Ctrl grosso; Esc devolve; um undo so');
clicar sem arrastar continua digitando. A cada etapa nova do
wizard a aba rola ate' o fim, onde a etapa nasce (`_rolar_ate_o_fim`).
Na biblioteca, Puxadores e Dobradicas mostram tambem os de fabrica,
TRAVADOS (moram no add-on, fora do indice); clicar num puxador dela (foto
ou Inserir do clique direito) abre o "Criar Puxador" com ele -- o arrasto
nativo do Asset Browser traz so' o 3D. Faixa e menu: modulo SEM fila de
botoes embaixo; Inserir/Editar/Bloquear no clique DIREITO (v316).

**Modulos | Materiais** (pedido do usuario): dois segmentos AO LADO do
titulo "Biblioteca" (verbo `biblioteca`, nao `escolha`: a fila e' do
cabecalho, nao da aba), com a contagem dentro; sem espaco (< 2 x
`PX_MIN_NIVEL` depois dos icones) descem para a linha de baixo. Os icones
seguem a biblioteca aberta (Materiais: pasta e "+"). Materiais usam a
MESMA cascata e a MESMA grade (slider "Tamanho das miniaturas"); no lugar
da foto, a esfera da cor (`esfera_rgba`: difusa + brilho, sem render); a
esfera do material da selecao acende. UM clique na esfera NAO faz nada
(pedido do usuario: o clique errado pintava o que nao devia); o DUPLO
pinta a selecao e ARRASTAR (pincel no cursor) pinta, ao soltar, o que
esta' sob o mouse -- recusado: clique simples aplicando. Botao DIREITO
na esfera = PINTURA RAPIDA (pedido do usuario): a caixa preta abre sob o
material (nao pop-up: regra da gaveta) com "quais modulos?" -- um botao por
COMODO que tem armario, "Sem comodo", "Todos" e "Cancelar" -- e depois
"pintar o que?": Tudo, So' a caixa (corpo + fundo), So' as portas
(folhas + moldura). Muitas respostas quebram em filas
(`LARGURA_MIN_RESPOSTA`); a 1a resposta nao gera passo de desfazer. Embaixo:
Editar e Apagar; o
"Apagar?" abre sob a fila e a biblioteca rola ate' ele
(`_rolar_biblioteca_ate_pergunta`).
Pintura do grupo (382): catalogo e Ctrl+L preservam puxadores, dobradicas,
trilhos e malhas filhas de ferragens. Ctrl+L reutiliza o menu e o operador
nativos; somente o material recebe alvos filtrados. A selecao completa
permanece para mover/ocultar/duplicar. Sem grupo, editar o material de uma
ferragem individual continua nativo.

**Paredes (como no Promob, pedido do usuario).** Botao DIREITO segurado
num modulo o arrasta; solto numa superficie VERTICAL que nao seja movel
do add-on, as COSTAS (+Y do modulo) encostam nela e ele fica ASSOCIADO
A' FACE, nao ao objeto (pedido do usuario: a sala inteira e' um objeto
so'): parede = a face sob o mouse mais as vizinhas no MESMO plano ligadas
por aresta (`regiao_da_parede`). Durante o arraste essa face ACENDE (veu
e contorno grosso na cor de realce); fora de parede, a barra de status
diz por que (movel, nao vertical). Gravado: UID no objeto, indice da face,
ponto das costas e normal no referencial dele. O raio, achado o objeto,
e' refeito so' contra ele (`raio_ate_parede`): as costas ficam NO plano
da parede e pular o modulo atravessava a face (o modulo piscava). O cursor fica no meio das costas; pontas, piso e teto grudam a
`SNAP_PX`. Clique sem arrastar = o menu de contexto de sempre (no
SOLTAR). Parede = QUALQUER superficie (escolha do usuario: nada de
ferramenta "Criar parede" nem marcar a malha); os limites sao as faces
da face. Associado de verdade: a parede que anda leva o modulo; G/R
no modulo o devolvem ao plano (so' desliza) -- pelo timer de seguranca,
nunca no handler do depsgraph. Selecionado: contorno da parede e 4 guias
(esquerda, direita, piso, teto, esq./dir. de quem olha a parede) na cor
de realce; o NUMERO e' gizmo (ganha da selecao): clique digita, arrastar
ao longo da guia muda. Solta (v319): arrastar com o direito e soltar
FORA de qualquer parede (o limbo) desassocia e o movel fica onde estava;
F3 "Desassociar da Parede" (v338: a secao Composicao do menu so' tem a
cruz de medidas do selecionado; Livre/Fixa, Redistribuir, Trocar modelo e
Desassociar sairam do menu a pedido do usuario; tambem os campos de folga
Esquerda/Direita/Espacamento -- a distribuicao usa os valores da sessao).
Cotas do modulo na parede, como no Promob (v315): A1/A2/A3 e, em CRUZ,
Superior (cima), Anterior/Afastamento/Posterior (meio), Inferior (baixo);
colunas de ate' 84 px (5 digitos), rotulos curtos abaixo de 76. Anterior/
Posterior = vizinho na mesma altura ou ponta da face; Inferior/Superior =
modulo na mesma faixa ou piso/teto; Afastamento = folga costas-parede,
numero editavel no meio do modulo (profundidade nao tem linha de frente).
Na viewport (v368), A1 largura/A2 altura/A3 profundidade ficam visiveis no
selecionado e editaveis pelo mesmo dominio do menu. A3 Prof. tem chamada na
quina inferior direita, sem simular projecao de profundidade frontal. Campos
ficam na area livre e se afastam de numeros existentes. Resize esconde as
distancias (Anterior/Posterior, Inferior/Superior, Afastamento), conservando
as tres dimensoes. A HUD volta na parede reduzida:
so' as bolinhas do centro das bordas NO plano (v337: cheias, 5 px, halo do
tema; sem setas nas arestas, profundidade, letras, linhas da caixa nem
ancora -- a quina e' do circulo do snap). Sem selecao,
nenhuma cota. Guias de movimento (v336, linhas azuis do usuario): cada
distancia sai do MEIO da sua face (laterais na meia altura, inferior e
superior no meio da largura). Ponta fora da tela ou sob toolbar/cabecalho/
prateleira vem para a borda da area livre, inteira.
Na vista 2D (Editar parede), GUIAS DE ALTURA como no Promob: linhas da
face inteira, DISCRETAS (v340): pontilhadas (tracos de 10 mm a cada 40 mm
da propria malha, o snap continua) e rotulo "150 - Rodape" em texto cinza
na ponta esquerda; a caixa preta da HUD so' com o mouse em cima
(ou digitando); clicar digita. Menu: secao Guias com a fila Ocultas | Visiveis |
Com snap, um campo por guia e "Restaurar guias padrao". Fora da vista
2D nada aparece. Com snap, o G gruda a lateral do modulo na linha.
Ao soltar o G/R/S na vista 2D, ima NO PLANO da parede (v317): as bordas da
CAIXA do modulo grudam nas dos vizinhos, pontas/piso/teto e guias a ate'
12 px, e o modulo associado volta para dentro da face. Sem profundidade:
a quina da frente nao gruda na de tras de outro movel nem em vertice
interno (fundo recuado). Medida digitada e distribuicao nao recebem ima.
Mover na vista 2D (v319, `OBJECT_OT_mover_na_parede`): G com UM modulo
selecionado, ou clique esquerdo + arraste num modulo. QUINA sem Alt
(v325): o mouse a ate' 16 px de uma quina-alvo leva a quina mais perto
da caixa ate' ela. CIRCULO de quina (v334, desenho do usuario): com o
mouse a ate' 16 px da quina de um modulo, um circulo na cor de realce
(7 px) acende nela; G/arraste com ele aceso PEGA essa quina, que gruda na
quina-alvo mais perto dela e leva o circulo junto (com Alt, as laterais
dela). O resto e' LIVRE; SEGURANDO Alt (v320) ligam tambem as
laterais, soltar o Alt desliga; Ctrl nada faz. Com Alt, fora de quina,
a LATERAL pega (a ate' 24 px do mouse ao comecar:
esquerda, direita, base, topo; frente e fundo nao contam) gruda o LADO
INTEIRO nos vizinhos, pontas/piso/teto e guias Com snap, o outro eixo
livre; longe das laterais, a borda mais perto de cada eixo. Tudo no
plano. Esc/direito cancela. A lateral pega e a linha-alvo acendem
na cor de realce. Varios modulos: G e arraste nativos (ima ao soltar).
Guias Visiveis so' orientam; quem gruda e' Com snap.
O rotulo da guia tem tamanho fisico (70 mm): diminui com o zoom ate' o
teto da cota e some abaixo de 7 px. Digitando cota ou guia, a barra do
cursor pisca na posicao; o texto todo selecionado ganha realce.
Arrastar da biblioteca (v321, como o BlenderKit): so' o WIREFRAME, pela
`caixa` gravada no indice; nada e' carregado ate' soltar. Solto, o
wireframe fica parado com "Carregando <nome>..." (caixa preta da HUD) e o
.blend carrega no tique seguinte, ja' no lugar (parede/associacao
inclusive). Preset sem `caixa`: o 1o arraste carrega antes e a grava.
Encaixe no arraste (363): Ajuste maximo no grupo Paredes, padrao 10 mm por
dimensao (L/A); zero desliga. Reduz so' o necessario, sem aumentar ou mudar
profundidade/E. Apoios/obstaculos reais e aberturas definem o vao sob o
cursor; nao saltar para outra fileira. Previa numerica mostra tamanho e
aviso Ajustado; so' confirmar chama o resize do dominio. Piso/teto/objetos
fora da vista continuam limitando fisicamente. Limite excedido = caixa
vermelha e aviso preto/branco com altura/causa, tambem na barra de status.
Vale no 2D e atach fora dele; soltar invalido cancela so' a tentativa.
Cache numerico pertence ao modal; confirmar recalcula. Sair da viewport
limpa a previa antiga. POST_PIXEL compartilhado com o carregamento sai
no encerramento; o preset da biblioteca nao e' modificado.

Zig-zag (pedido do usuario): o assistente oferece 1-8 folhas e filtra as
aberturas pela quantidade; Zig-zag aceita 2-8. Escolher a borda determina
onde comeca a cadeia. As folhas dobram alternadamente, com placas e eixo
das dobradicas presos as folhas correspondentes. Um slider na ultima
folha controla o conjunto; o puxador PERFIL nasce somente nessa ponta
livre e continua nela ao mudar quantidade/lado. Os retratos incluem
Zig-zag. Fotos da biblioteca: todas as portas FECHADAS, inclusive cantos,
correr, basculantes e zig-zag. Fotografar nao muda lado, vao nem ferragens.

## 10. Animacao

O glow corre num timer so' (`_animar_realces`, 60 fps), que se
desregistra sozinho. Nao crie um segundo. O carrossel deslizante do
menu foi substituido pela lista suspensa (v315, pedido do usuario).

- As posicoes saem de `_widgets_gaveta`, nunca do desenho — o
  retangulo de clique e o glow acendem a peca certa.
- Todo `scissor_set` ligado tem que ser desligado no mesmo laco.

## 11. Nunca faca

- **Cor literal** na gaveta no lugar do tema (secao 5).
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
1. Rodar o harness inteiro: `tests/rodar_testes.py` (com `--gui` quando
   puder abrir janela). Mudou o layout de proposito? `--atualizar` e
   revise o diff dos snapshots (`tests/CLAUDE.md`).
2. Conferir em **tres larguras** (190, 320, 564) e nos dois temas:
   bug de layout quase sempre so' aparece num extremo (o snapshot da
   gaveta ja' grava 190/320/482/564).
3. Incrementar `bl_info["version"]`.

Captura vale mais que leitura de codigo aqui:
`bpy.ops.screen.screenshot()` num Blender de verdade pega o que o
teste nao pega — halo opaco, texto cortado, icone fora do lugar.

## 13. Alternativas ja' avaliadas e RECUSADAS
A antiga restricao contra overlay foi substituida pela HUD da secao 8,
por solicitacao explicita do usuario. A biblioteca foi movida a uma faixa superior propria (secao 6).

- **Pop-up / `invoke_props_dialog`**: fecha quando o mouse sai, e
  clicar na viewport e' a acao seguinte do posicionador. Nao existe
  popup fixo no bpy. O dialogo das Portas virou a aba (secao 9).
- **Voltar ao painel N com `UILayout`**: o handler de UI come o evento
  antes de qualquer keymap, o icone nao passa de 16 px e nao da' para
  fixar largura em pixels. Foi o que motivou a gaveta.

Tab num grupo selecionado abre as malhas reais no Edit Mode multiobjeto nativo do Blender. Gaveta individual (383) tambem e' grupo: Tab abre caixa/puxador somente das unidades selecionadas; nao amplia ao conjunto de gavetas nem ao modulo. Selecao multipla (384): apos duplo clique isolar uma gaveta, Shift+clique soma outra do mesmo vao; Shift+duplo reduz so' o vao clicado, conservando objetos externos. Clique simples sem Shift continua global. Hierarquia (385): duplo na frente/corpo isola a gaveta; depois, um clique no proprio puxador seleciona so' o acessorio. Duplo direto no puxador tambem isola. Esse escopo vale antes da regra de modulo na parede, sem alterar o clique simples nativo dos objetos comuns/paredes; nao ha' contador global de cliques. Cortadores/controles do rig ficam fora; malhas compartilhadas com outros modulos sao isoladas antes. Prateleiras: escopo global propaga a todas ao concluir na MESMA Mesh (undo nativo guarda o ID); individual edita so' aquela unidade. Quantidade sempre disponivel: herda a unidade selecionada, ou pede "Selecione a prateleira de referencia" na HUD ao lado do mouse na viewport, seguindo o cursor e respeitando as bordas, se houver tipos diferentes sem selecao individual (Esc cancela). Arrastar exibe so' o numero previsto, monta ao soltar. Parametros individuais conservam as vizinhas. Porta selecionada (grupo ou folha): Espelhar Porta no menu contextual nativo. Montagem: Corrente e Resetar distancia com texto e icone ao lado, uma coluna no menu estreito; Button2D reutilizado so' com o mesmo simbolo, fixado pelo Blender no primeiro desenho. Inverte dobradicas/abertura e puxador; zigzag inverte a cadeia, basculante inclui pistoes, correr troca o sentido no trilho.
