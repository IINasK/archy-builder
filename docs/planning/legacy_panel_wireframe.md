# Referencia historica do Archy Builder

O texto abaixo conserva o nome e o desenho de interface da epoca do
Cabinet Creator. O padrao atual esta' em [DESIGN.md](../../DESIGN.md).

---

# Planejamento: wireframe dinamico no painel N

## 1. Objetivo deste documento

Este documento especifica a implementacao de uma representacao visual
procedural das dimensoes de uma chapa ou de um modulo do Cabinet Creator.
A representacao sera exibida no painel N do Blender ao lado dos campos de
medidas.

O texto foi escrito para servir como fonte de verdade para uma IA ou pessoa
que implemente a funcionalidade posteriormente. Ele descreve requisitos,
restricoes, formulas, arquitetura sugerida, integracao com o codigo atual,
etapas de implementacao, casos extremos e criterios de aceite.

Status em 22/09/2026: implementado no add-on 34.0.0. A projecao, o limite de
crescimento, a rasterizacao, o cache, o ciclo register/unregister e a exibicao
real no painel foram validados no Blender 5.2. O carregamento, a rasterizacao e
o ciclo register/unregister tambem foram validados no Blender 4.2.

Refinamento 35.0.0: os campos visuais passaram a usar proxies de comprimento
do Blender, aceitando entradas como `600`, `60cm` e `0.6m`, sem converter o
armazenamento interno em milimetros. Os quatro campos e a lista de espessuras
foram compactados, centralizados e reunidos na coluna esquerda do wireframe.

Refinamento 36.0.0: a coluna de medidas foi ancorada a esquerda e cada campo
passou a ter o rotulo completo acima da caixa de texto. O preview fixo foi
ampliado, centralizado no espaco restante e recebeu indicadores procedurais.
Grupo usa `L`, `A` e `P`; Individual usa `L` e `C`. Espessura nunca recebe
letra no desenho. As abas Individual/Grupo agora tambem aparecem quando o
Empty do modulo esta selecionado. Escolher Individual nesse estado seleciona
a primeira chapa do modulo para tornar a acao funcional.

Refinamento 37.0.0: o canvas passou a ser horizontal, os espacadores verticais
foram removidos e a escala de UI foi reduzida para eliminar os grandes vazios
acima e abaixo dos controles. As linhas do box e os indicadores ficaram mais
finos. O preview permanece uma unica imagem para nao criar emendas nas arestas.

Refinamento 38.0.0: rotulos, caixas de texto e a lista de espessuras passaram
a ficar alinhados a esquerda dentro de uma coluna de controles independente.
O preview continua centralizado somente na coluna restante. A escala-base do
desenho aumentou de 0.26 para 0.46 pixel por milimetro, ainda limitada pelas
margens fixas do canvas, para aproveitar melhor a area sem responder ao
redimensionamento do painel N.

Refinamento 39.0.0: o desenho deixou de usar escala-base e passou a ajustar
sempre a maior extensao projetada a area util do canvas. Objetos pequenos e
grandes ocupam a mesma area maxima; suas proporcoes continuam diferentes. A
escala fixa do componente visual aumentou de 8 para 20 unidades de UI para
aproveitar a coluna normalmente larga do painel N sem crescer alem disso.

Refinamento 40.0.0: o preview usa uma unica imagem quadrada de 160 x 160 pixels
para respeitar a alocacao quadrada obrigatoria de `template_icon`. Exibido com
escala 8.5 de UI, o componente ocupa aproximadamente 170 x 170 pixels. O box
continua proporcional dentro desse canvas: 600 x 400 x 300 ocupa cerca de
140 x 112 pixels na interface e 600 x 2100 x 300 ocupa cerca de 45 x 128. A
margem vertical interna e' 20 pixels e o traco usa 0.45 pixel no buffer. Isso
reduz o vazio inferior e devolve linhas visualmente finas. Os controles
permanecem alinhados a esquerda e centralizados verticalmente ao lado do
desenho.

Refinamento 49.0.0: a margem horizontal passou a ser assimetrica, com 14 pixels
a esquerda para os indicadores e 2 pixels a direita. A escala de UI voltou a
10, mantendo o traco fino de 0.45 pixel. Objetos largos passam a ocupar cerca
de 180 pixels. No modo Individual, `Auto-regenerar` foi
movido para dentro da coluna esquerda de controles; deixa de existir uma linha
adicional abaixo do preview, removendo a faixa inferior sem encolher o desenho.
O indicador `A` recebe limite interno e espaco lateral para nunca ser cortado
ou sobreposto pela aresta vertical.


## 2. Resumo funcional

Adicionar ao painel `N > Cabinet Creator` um desenho wireframe dinamico que:

1. represente um paralelepipedo usando somente suas 12 arestas;
2. use as medidas atualmente exibidas nos campos do painel;
3. preserve a proporcao entre largura, altura e profundidade;
4. mantenha a direcao da profundidade em um angulo fixo de 45 graus;
5. tenha fundo transparente;
6. nao tenha faces preenchidas, sombras, materiais ou texturas;
7. nao tenha portas, puxadores, prateleiras ou divisoes internas;
8. nao tenha pontos coloridos, legendas ou marcadores dentro da imagem;
9. tenha uma area de visualizacao com tamanho fixo;
10. nao aumente quando o usuario alargar o painel N;
11. ocupe a area util maxima, independentemente do tamanho absoluto;
12. nunca ultrapasse ou seja cortado pelos limites do canvas;
13. seja atualizado automaticamente quando as medidas ou o modo mudarem;
14. seja gerado em memoria, sem criar objetos auxiliares na cena;
15. seja leve o suficiente para nao prejudicar a interacao com o Blender.


## 3. Referencia visual consolidada

### 3.1 Layout geral

O painel deve manter esta composicao conceitual:

```text
+---------------------------------------------------------+
|          Individual                  Grupo              |
|                                                         |
|   [ largura             ]          +--------------+     |
|                                  / |              |     |
|   [ altura/comprimento  ]       /  |              |     |
|                                +   |              |     |
|   [ profundidade        ]       \  |              |     |
|                                  \ |              |     |
|                                    +--------------+     |
+---------------------------------------------------------+
```

O desenho acima e' apenas esquematico. O box final deve possuir as 12 arestas
necessarias para representar corretamente o volume tridimensional.

### 3.2 Aparencia do wireframe

- Desenho tecnico simples.
- Somente linhas de contorno.
- Fundo transparente.
- Sem preenchimento das faces.
- Sem gradiente.
- Sem iluminacao.
- Sem sombra.
- Sem perspectiva fotografica.
- Sem portas.
- Sem puxadores.
- Sem prateleiras.
- Sem divisorias.
- Sem representacao individual das chapas de um modulo.
- Sem cotas numericas desenhadas dentro do preview.
- Sem setas ligando os campos ao desenho.
- Sem pontos coloridos. Os pontos presentes na imagem de referencia foram
  usados apenas para explicar a associacao das medidas.

### 3.3 Significado visual das direcoes

No modo Grupo:

- largura: arestas horizontais da face frontal;
- altura: arestas verticais;
- profundidade: arestas diagonais a 45 graus.

No modo Individual:

- largura: `chapa_largura_mm`;
- comprimento: `chapa_comprimento_mm`;
- espessura: `chapa_espessura_mm`;
- a chapa continua sendo um paralelepipedo completo, normalmente mais fino
  em uma das direcoes.

Os nomes exibidos no painel devem continuar coerentes com as propriedades ja'
existentes. Este trabalho nao deve renomear propriedades RNA nem ID props.


## 4. Requisitos obrigatorios

### 4.1 Requisitos de geometria

O wireframe deve ser calculado a partir de tres dimensoes positivas:

- `L`: largura;
- `A`: altura visual;
- `P`: profundidade.

Para Grupo, usar:

- `L = largura externa do modulo`;
- `A = altura externa do modulo`;
- `P = profundidade externa do modulo`.

Para Individual, respeitar os eixos locais definidos pelo projeto:

- X local = largura;
- Y local = comprimento;
- Z local = espessura.

A orientacao visual exata da chapa individual deve ser derivada desses eixos,
sem alterar a geometria real ou os invariantes do objeto na cena.

### 4.2 Requisitos de projecao

A projecao deve ser obliqua, nao uma camera 3D real.

- A face frontal permanece retangular.
- As verticais permanecem verticais.
- As horizontais da face frontal permanecem horizontais.
- As arestas de profundidade usam exatamente 45 graus.
- A profundidade se desloca para cima e para a esquerda, como na referencia.
- O angulo nao muda com as dimensoes.
- O angulo nao muda com a largura do painel N.

### 4.3 Requisitos de tamanho do componente

- O canvas tem dimensoes fixas em unidades de interface.
- Alargar o painel N nao aumenta o canvas.
- Alargar o painel N nao aumenta o wireframe.
- O espaco adicional do painel fica vazio.
- A escala global/DPI do Blender ainda pode alterar o tamanho fisico do
  componente. Isso e' comportamento nativo e nao deve ser contornado.
- O desenho deve ficar centralizado dentro de sua area fixa.
- Deve existir margem transparente em todos os lados.

### 4.4 Requisitos de ajuste e limite

O wireframe deve ocupar automaticamente a maior area possivel do canvas para
qualquer conjunto valido de medidas.

Comportamento exigido:

1. medidas absolutas pequenas e grandes usam a mesma area maxima;
2. alterar a relacao entre as medidas altera a forma visivel do box;
3. pelo menos uma extensao projetada atinge a area util;
4. o desenho permanece sempre dentro do limite;
5. nenhuma linha e' cortada;
6. a proporcao entre as dimensoes permanece preservada;
7. a espessura do traco permanece constante em pixels.

Exemplo importante:

- Se apenas a altura aumentar indefinidamente, a altura desenhada permanece
  no limite vertical.
- Largura e profundidade passam a parecer menores em relacao a altura porque
  a proporcao matematica deve continuar correta.


## 5. Nao objetivos

Nao faz parte desta funcionalidade:

- renderizar a cena atual;
- criar camera;
- criar malha auxiliar;
- criar Grease Pencil;
- usar Geometry Nodes;
- mostrar a composicao interna real do modulo;
- mostrar portas ou puxadores;
- mostrar materiais;
- mostrar espessuras individuais das chapas do modulo;
- permitir orbitar o preview;
- permitir zoom manual no preview;
- redimensionar o preview junto com o painel N;
- permitir clicar nas arestas;
- exportar a imagem;
- salvar um PNG a cada alteracao;
- alterar a geometria real do projeto;
- alterar o sistema de adjacencia;
- alterar presets ou o formato da biblioteca;
- renomear propriedades persistidas em arquivos `.blend`.


## 6. Estado atual relevante do projeto

O add-on esta concentrado em:

```text
archy_builder/__init__.py
```

Recursos existentes que devem ser reutilizados:

- import de `bpy.utils.previews`;
- `_previews = [None]`;
- `_colecao_previews()`;
- remocao da colecao de previews em `unregister()`;
- uso de `layout.template_icon()` nas miniaturas da biblioteca;
- `VIEW3D_PT_archy_builder.desenhar_medidas()`;
- propriedades de chapa em `bpy.types.Object`;
- propriedades de grupo em `bpy.types.Scene`;
- propriedades de conjunto/modulo em `bpy.types.Object`.

Invariantes existentes que nao podem ser quebrados:

- X local da chapa = largura;
- Y local da chapa = comprimento;
- Z local da chapa = espessura;
- propriedades gravadas nos presets nao podem ser renomeadas;
- callbacks que escrevem propriedades devem respeitar `_ocupado[0]`;
- todo recurso registrado deve ser removido em `unregister()`;
- a interface e o codigo usam nomes em portugues;
- a feature nao pode introduzir uma dependencia externa obrigatoria.


## 7. Arquitetura recomendada

### 7.1 Estrategia principal

Gerar um buffer RGBA procedural em memoria e coloca-lo em um item de
`bpy.utils.previews.ImagePreview`.

Fluxo:

```text
medidas atuais
    -> chave canonica de cache
    -> vertices 3D abstratos
    -> projecao obliqua 2D
    -> calculo de escala e enquadramento
    -> rasterizacao das 12 arestas
    -> buffer RGBA transparente
    -> ImagePreview.icon_pixels_float ou icon_pixels
    -> icon_id
    -> UILayout.template_icon()
```

Vantagens:

- nao cria arquivos temporarios;
- nao usa render do Blender;
- nao depende da viewport;
- nao depende de camera;
- nao polui `bpy.data` com imagens persistentes;
- reutiliza a infraestrutura de previews ja' presente;
- permite cache por conjunto de medidas;
- produz resultado deterministico.

### 7.2 Estrategia de contingencia

Durante o prototipo, validar se a versao minima suportada do Blender atualiza
corretamente um preview criado por script ao escrever `icon_size` e
`icon_pixels_float`.

Se alguma versao suportada nao atualizar o `icon_id` de forma confiavel:

1. manter a mesma geracao procedural;
2. salvar o buffer somente em um arquivo temporario controlado;
3. carregar com `ImagePreviewCollection.load(..., 'IMAGE')`;
4. invalidar o preview antigo de maneira segura;
5. remover os temporarios no encerramento, quando possivel.

Essa contingencia e' segunda opcao. A implementacao em memoria deve ser
tentada e validada primeiro.


## 8. Constantes sugeridas

Criar constantes nomeadas, agrupadas perto da secao de previews:

```python
WIREFRAME_LARGURA_PX = 256
WIREFRAME_ALTURA_PX = 192
WIREFRAME_MARGEM_PX = 14
WIREFRAME_ANGULO_GRAUS = 45.0
WIREFRAME_ESPESSURA_LINHA_PX = 2.0
WIREFRAME_ESCALA_UI = 20.0
WIREFRAME_CACHE_MAX = 48
WIREFRAME_ARREDONDAMENTO_MM = 0.1
```

Os valores sao pontos de partida, nao valores finais aprovados. Devem ser
ajustados visualmente no Blender em escala de interface 1.0 e 1.5.

Regras para ajuste:

- nao aumentar a resolucao sem necessidade;
- manter o canvas visualmente fixo;
- usar margem suficiente para antialiasing e espessura do traco;
- fazer o modulo padrao ocupar o limite disponivel;
- assegurar que uma chapa de espessura comum ainda tenha leitura visual.


## 9. Modelo matematico

### 9.1 Vertices do box

Definir os oito vertices abstratos:

```text
V000 = (0, 0, 0)
V100 = (L, 0, 0)
V010 = (0, P, 0)
V110 = (L, P, 0)
V001 = (0, 0, A)
V101 = (L, 0, A)
V011 = (0, P, A)
V111 = (L, P, A)
```

Interpretacao:

- X cresce para a direita;
- Z cresce para cima;
- Y representa a profundidade;
- a face em `Y = 0` e' a face frontal;
- a face em `Y = P` e' a face traseira.

### 9.2 Lista das 12 arestas

Face frontal:

```text
V000--V100
V100--V101
V101--V001
V001--V000
```

Face traseira:

```text
V010--V110
V110--V111
V111--V011
V011--V010
```

Ligacoes de profundidade:

```text
V000--V010
V100--V110
V101--V111
V001--V011
```

Todas as 12 arestas devem ser desenhadas. Nao fazer remocao de linhas ocultas,
pois o requisito e' um wireframe completo.

### 9.3 Projecao obliqua de 45 graus

Usar:

```text
c = cos(45 graus)
s = sin(45 graus)

projetado_x = x - y * c
projetado_y = z + y * s
```

O sinal negativo em X move a profundidade para a esquerda. O sinal positivo
em Y matematico move a profundidade para cima.

Ao gravar em um buffer cuja origem esta no topo, converter Y:

```text
pixel_y = altura_canvas - 1 - y_enquadrado
```

Nao inverter a geometria em outros pontos. Centralizar a conversao de sistema
de coordenadas em uma unica funcao.

### 9.4 Extensao projetada antes da escala

Para este box e esta projecao:

```text
largura_projetada_mm = L + P * cos(45 graus)
altura_projetada_mm = A + P * sin(45 graus)
```

Ainda assim, a implementacao deve preferir calcular `min_x`, `max_x`, `min_y`
e `max_y` a partir dos oito pontos projetados. Isso reduz risco de erro caso a
orientacao seja refinada posteriormente.

### 9.5 Area util

```text
util_largura = canvas_largura - 2 * margem
util_altura = canvas_altura - 2 * margem
```

Validar que ambos sejam maiores que zero.

### 9.6 Escala de ajuste ao limite

```text
escala_largura = util_largura / largura_projetada_mm
escala_altura = util_altura / altura_projetada_mm
escala_final = min(escala_largura, escala_altura)
```

Consequencias intencionais:

- qualquer tamanho absoluto e' ajustado ao mesmo limite visual;
- pelo menos uma dimensao projetada ocupa toda a area util correspondente;
- nenhuma dimensao ultrapassa a area util;
- a escala e' uniforme em X e Y;
- a proporcao nao e' distorcida;
- aumentar todas as medidas pelo mesmo fator produz o mesmo tamanho externo e
  a mesma proporcao visual.

Nunca usar escalas X e Y independentes. Isso distorceria as proporcoes.

### 9.7 Centralizacao

Apos aplicar a escala, obter a caixa 2D do desenho e calcular:

```text
deslocamento_x = (canvas_largura - desenho_largura) / 2 - min_x_escalado
deslocamento_y = (canvas_altura - desenho_altura) / 2 - min_y_escalado
```

Aplicar o mesmo deslocamento a todos os vertices.

O box deve permanecer centralizado depois do ajuste ao limite.


## 10. Rasterizacao

### 10.1 Buffer

Criar um buffer linear RGBA:

```text
tamanho = largura_px * altura_px * 4
valor inicial = (0, 0, 0, 0)
```

O alpha inicial deve ser zero em todos os pixels.

### 10.2 Desenho de linhas

Implementar uma funcao independente, por exemplo:

```python
def _desenhar_segmento_rgba(buffer, largura, altura,
                             x0, y0, x1, y1,
                             cor, espessura):
    ...
```

Opcoes aceitaveis:

- algoritmo de Wu para linha antialias;
- distancia do centro do pixel ate o segmento;
- supersampling 2x seguido de reducao.

Recomendacao inicial:

- usar distancia ao segmento somente na caixa delimitadora da aresta;
- limitar os loops ao retangulo local de cada linha;
- combinar alpha corretamente nas intersecoes;
- evitar percorrer todo o canvas 12 vezes.

### 10.3 Espessura do traco

- A espessura e' definida em pixels de interface.
- A espessura nao depende das medidas.
- A espessura nao depende da escala geometrica.
- A espessura nao cresce quando o box cresce.
- Usar antialiasing para evitar diagonais serrilhadas.

### 10.4 Cor

Preferir uma cor derivada do tema atual do Blender, se houver acesso seguro a
uma cor de texto/linha apropriada.

Fallback obrigatorio:

```text
tema escuro: linha clara opaca
tema claro: linha escura opaca
```

Se a deteccao automatica do tema for instavel, adotar inicialmente uma cor
neutra de alto contraste validada nos temas oficiais claro e escuro.

Nao desenhar fundo. A transparencia deve permitir que o painel apareca atras
do wireframe.

### 10.5 Dimensoes muito finas

Uma chapa pode ter 15 mm de espessura e centenas ou milhares de milimetros nas
outras dimensoes. Em escala proporcional, duas arestas podem ficar separadas
por menos de um pixel.

Regra principal:

- preservar a proporcao matematica.

Regra de rasterizacao inevitavel:

- qualquer aresta deve produzir ao menos cobertura parcial de pixel para nao
  desaparecer por arredondamento.

Nao inflar artificialmente a espessura geometrica sem uma decisao posterior
explicita. Antialiasing e espessura do traco ja' oferecem legibilidade minima.


## 11. Cache e atualizacao

### 11.1 Motivo do cache

O metodo `draw()` do painel pode ser chamado muitas vezes sem alteracao das
medidas. O buffer nao deve ser regenerado em todo redesenho.

### 11.2 Chave canonica

Exemplo de chave:

```text
(
    versao_algoritmo,
    modo,
    round(L, 1),
    round(A, 1),
    round(P, 1),
    largura_canvas,
    altura_canvas,
    identificador_cor_tema
)
```

Transformar a tupla em uma string estavel para uso na colecao de previews.

O arredondamento de 0,1 mm evita criar novas entradas por ruido de ponto
flutuante invisivel ao usuario.

### 11.3 Limite de cache

O usuario pode testar muitas medidas. O cache nao pode crescer para sempre.

Implementar LRU simples ou ordem de uso:

- limite inicial sugerido: 48 previews;
- ao exceder o limite, excluir o menos recentemente usado;
- nunca remover a colecao inteira durante um `draw()`;
- preservar as miniaturas da biblioteca que compartilham `_previews`.

Para evitar colisao com previews da biblioteca, prefixar todas as chaves:

```text
wireframe:v1:...
```

Ao limpar entradas antigas, remover somente chaves com prefixo `wireframe:`.

### 11.4 Invalidacao

Uma mudanca em qualquer item abaixo deve selecionar ou gerar outro preview:

- modo Individual/Grupo;
- largura;
- altura ou comprimento;
- profundidade ou espessura;
- resolucao do canvas;
- escala fixa do componente de UI;
- margem;
- cor do tema;
- versao interna do algoritmo.

Nao e' estritamente necessario manter uma flag global `sujo` se a chave do
cache representar todos os dados de entrada. Comparar a chave atual e' mais
robusto.

### 11.5 Momento da geracao

Opcao recomendada:

1. `draw()` le as medidas atuais;
2. cria a chave canonica;
3. consulta o cache;
4. se existir, usa o `icon_id` existente;
5. se nao existir, gera uma vez e armazena;
6. desenha com `template_icon()`.

O caminho de cache encontrado deve ser praticamente gratuito.

Se testes mostrarem travamento ao arrastar valores continuamente:

- marcar o preview como pendente;
- usar `bpy.app.timers` com debounce curto;
- gerar apenas o ultimo estado solicitado;
- registrar e remover corretamente o timer.

Nao adicionar timer antes de medir a necessidade. A primeira versao deve ser
simples.


## 12. Integracao com os modos atuais

### 12.1 Objeto conjunto selecionado

Quando `MARCA_CONJUNTO in obj`:

- usar `obj.conj_largura_mm`;
- usar `obj.conj_altura_mm`;
- usar `obj.conj_profundidade_mm`;
- mostrar o wireframe de Grupo;
- nao inspecionar as chapas filhas para desenhar detalhes;
- o Empty representa somente a caixa externa proporcional.

### 12.2 Chapa no modo Individual

Quando o objeto ativo for uma chapa e `obj.chapa_modo == 'INDIVIDUAL'`:

- usar `obj.chapa_largura_mm`;
- usar `obj.chapa_comprimento_mm`;
- usar `obj.chapa_espessura_mm`;
- mostrar somente o box proporcional da chapa.

Mapeamento visual recomendado:

```text
L = chapa_largura_mm
A = chapa_espessura_mm
P = chapa_comprimento_mm
```

Esse mapeamento representa visualmente uma chapa deitada, coerente com a
referencia inicial. Ele nao altera os eixos ou a malha real.

### 12.3 Chapa no modo Grupo

Quando uma chapa estiver ativa e `obj.chapa_modo == 'GRUPO'`:

- usar `context.scene.grupo_largura_mm`;
- usar `context.scene.grupo_altura_mm`;
- usar `context.scene.grupo_profundidade_mm`;
- mostrar o mesmo tipo de box externo usado para um conjunto selecionado.

### 12.4 Sem objeto valido

Quando nao houver chapa nem modulo valido:

- manter a mensagem atual de selecao;
- nao gerar preview;
- nao mostrar um box com medidas padrao que possa confundir o usuario.


## 13. Layout do painel

### 13.1 Estrutura recomendada

Dentro do box de medidas:

```python
linha_principal = box.row(align=False)
coluna_campos = linha_principal.column(align=True)
coluna_preview = linha_principal.column(align=False)
```

A coluna de preview deve usar largura visual fixa, quando a API permitir, por
meio de `ui_units_x` e de um `template_icon(..., scale=...)` constante.

### 13.2 Comportamento quando o painel aumenta

- Nao calcular `scale` com base em `context.region.width`.
- Nao calcular resolucao com base na largura disponivel.
- Nao aumentar `template_icon.scale` dinamicamente.
- Manter um valor fixo de `scale`.
- Alinhar a coluna de preview de forma previsivel.
- Aceitar espaco vazio extra.

### 13.3 Comportamento quando o painel fica estreito

O Blender controla parte do layout do painel N. A implementacao deve:

- definir um tamanho minimo pratico para a coluna visual;
- evitar sobrepor campos e preview;
- aceitar que textos nativos sejam abreviados pelo Blender;
- nunca reduzir dinamicamente o wireframe somente porque o painel ficou
  estreito, pois isso violaria o requisito de tamanho fixo;
- validar visualmente a menor largura razoavel da sidebar.

Se o Blender comprimir o layout abaixo do minimo, preferir empilhamento
controlado como contingencia, mantendo o mesmo tamanho do preview. Nao fazer
escala responsiva do desenho.

### 13.4 Abas Individual e Grupo

- Manter a selecao visual nativa do `EnumProperty` com `expand=True`.
- O modo ativo deve continuar destacado pelo tema do Blender.
- A troca de modo deve trocar imediatamente a origem das medidas e o preview.
- Nao desenhar texto `Individual` ou `Grupo` dentro da imagem.


## 14. Funcoes sugeridas

Os nomes abaixo sao propostas e podem ser refinados mantendo portugues:

```python
def _medidas_wireframe(context):
    """Devolve (modo, largura, altura, profundidade) ou None."""


def _projetar_wireframe(largura, altura, profundidade):
    """Devolve os 8 pontos 2D ainda em milimetros projetados."""


def _enquadrar_wireframe(pontos, largura_px, altura_px, margem_px,
                         escala_base):
    """Aplica escala uniforme limitada e centralizacao."""


def _arestas_wireframe():
    """Devolve os 12 pares de indices de vertices."""


def _rasterizar_wireframe(largura, altura, profundidade, cor):
    """Devolve buffer RGBA do box transparente."""


def _chave_wireframe(modo, largura, altura, profundidade, cor):
    """Cria chave canonica, arredondada e versionada."""


def _icone_wireframe(context):
    """Consulta/cria preview e devolve icon_id ou zero."""


def _limpar_cache_wireframe():
    """Remove somente entradas procedurais do cache."""
```

Separar matematica, rasterizacao, cache e UI. Isso facilita testes fora do
Blender para as partes puramente matematicas.


## 15. Sequencia detalhada de implementacao

### Etapa 1: confirmar estado do repositorio

1. Ler `CLAUDE.md`.
2. Verificar `git status`.
3. Preservar arquivos e alteracoes que nao pertencem a esta tarefa.
4. Localizar a versao atual em `bl_info`.
5. Localizar as funcoes de previews e `desenhar_medidas()`.

### Etapa 2: isolar o modelo matematico

1. Definir os oito vertices.
2. Definir as 12 arestas.
3. Implementar a projecao fixa de 45 graus.
4. Calcular os limites 2D a partir dos vertices.
5. Implementar escala natural mais escala limite.
6. Implementar centralizacao.
7. Testar numericamente sem depender da UI.

### Etapa 3: implementar o rasterizador

1. Criar buffer transparente.
2. Implementar um unico segmento antialias.
3. Recortar a caixa de iteracao aos limites do canvas.
4. Desenhar as 12 arestas.
5. Verificar unioes nos cantos.
6. Verificar que nenhum indice sai do buffer.
7. Confirmar orientacao vertical correta dos pixels.

### Etapa 4: integrar com ImagePreview

1. Obter a colecao com `_colecao_previews()`.
2. Criar uma chave com prefixo `wireframe:`.
3. Criar o item de preview quando ausente.
4. Definir `icon_size`.
5. Preencher `icon_pixels_float` ou `icon_pixels`.
6. Obter `icon_id`.
7. Exibir isoladamente com `template_icon()`.
8. Validar recarga e desativacao do add-on.

### Etapa 5: implementar cache limitado

1. Arredondar dimensoes na chave.
2. Registrar ordem de ultimo uso.
3. Limitar somente previews com prefixo `wireframe:`.
4. Nunca apagar previews de fotos da biblioteca.
5. Testar muitas alteracoes consecutivas.

### Etapa 6: integrar as fontes de medidas

1. Conjunto selecionado: propriedades `conj_*`.
2. Chapa Individual: propriedades `chapa_*`.
3. Chapa Grupo: propriedades `grupo_*` da Scene.
4. Sem selecao valida: nenhum preview.
5. Validar troca de selecao.
6. Validar troca de modo.

### Etapa 7: integrar o layout

1. Criar linha com coluna de campos e coluna de preview.
2. Fixar escala visual do `template_icon()`.
3. Nao consultar a largura do painel para escalar.
4. Centralizar o preview em sua coluna.
5. Preservar controles existentes de espessura, sincronizacao e montagem.
6. Garantir que a biblioteca continue abaixo da secao de medidas.

### Etapa 8: validar atualizacao

1. Digitar largura e confirmar troca do preview.
2. Digitar altura/comprimento e confirmar troca.
3. Digitar profundidade/espessura e confirmar troca.
4. Arrastar numericamente os campos.
5. Alternar Individual/Grupo.
6. Selecionar outro objeto.
7. Selecionar o Empty de um modulo.
8. Redimensionar o painel N.

### Etapa 9: validar desempenho

1. Medir sensacao de resposta ao arrastar valores.
2. Confirmar que `draw()` nao rasteriza em cache hit.
3. Confirmar que o cache nao cresce sem limite.
4. Confirmar que nao sao criados arquivos ou datablocks por atualizacao.
5. Adicionar debounce somente se houver problema real.

### Etapa 10: finalizar integracao

1. Incrementar `bl_info["version"]` conforme convencao do projeto.
2. Executar `python -m py_compile archy_builder/__init__.py`.
3. Recarregar o add-on no Blender.
4. Executar a matriz de testes manuais.
5. Atualizar documentacao curta do usuario, se necessario.
6. Nao modificar este plano para afirmar conclusao sem que os testes tenham
   sido executados.


## 16. Casos extremos e comportamento esperado

### 16.1 Dimensao zero ou negativa

As propriedades atuais possuem minimos, mas a funcao deve ser defensiva:

- rejeitar dimensoes menores ou iguais a zero;
- aplicar epsilon somente para evitar divisao por zero;
- preferir nao desenhar e registrar mensagem de diagnostico em vez de gerar
  valores `NaN` ou infinitos.

### 16.2 Dimensoes extremamente grandes

Exemplo: altura de `1e9` mm.

- o desenho deve continuar dentro do canvas;
- nao deve ocorrer overflow pratico;
- a altura projetada deve atingir o limite vertical;
- outras direcoes podem se tornar visualmente muito pequenas;
- nenhuma excecao deve escapar de `draw()`.

### 16.3 Dimensoes extremamente pequenas

- o desenho pode ficar pequeno, de acordo com a escala natural;
- as linhas devem permanecer rasterizadas;
- nao ampliar automaticamente ate preencher o canvas;
- nao falsificar proporcoes.

### 16.4 Chapa muito fina

- manter espessura proporcional;
- aceitar sobreposicao visual parcial de linhas quando a separacao for menor
  que um pixel;
- nao transformar a chapa em uma caixa artificialmente grossa.

### 16.5 Painel muito largo

- tamanho do preview inalterado;
- espaco livre adicional;
- desenho nao esticado;
- linhas nao engrossadas.

### 16.6 Painel muito estreito

- preview continua com o mesmo tamanho solicitado;
- nenhum calculo proporcional usa a largura da regiao;
- layout nao deve provocar excecao;
- se necessario, aplicar contingencia de empilhamento, nao escala responsiva.

### 16.7 Mudanca de tema

- gerar nova chave de cache se a cor depender do tema;
- evitar reutilizar uma linha clara sobre tema claro ou linha escura sobre
  tema escuro;
- nao redesenhar continuamente sem mudanca real de tema.

### 16.8 Mais de uma janela do Blender

- a chave deve conter todos os dados que definem a imagem;
- duas janelas com selecoes diferentes nao devem compartilhar pixels errados;
- o uso de previews imutaveis por chave e' preferivel a sobrescrever um unico
  preview global.

### 16.9 Undo e redo

- apos undo/redo, `draw()` deve derivar a chave das propriedades restauradas;
- nao depender apenas de callbacks para invalidacao;
- o cache por valor torna undo/redo naturalmente consistente.

### 16.10 Desativar e reativar o add-on

- remover a colecao de previews no `unregister()`;
- limpar estruturas Python auxiliares do LRU;
- nao deixar timer registrado;
- reativar deve recriar tudo sob demanda.


## 17. Matriz de testes manuais

### 17.1 Grupo

Testar, no minimo:

```text
600 x 400 x 300 mm
600 x 2400 x 600 mm
2400 x 600 x 600 mm
300 x 300 x 1200 mm
10000 x 10000 x 10000 mm
100 x 1000000 x 100 mm
```

Verificar:

- correspondencia da proporcao;
- profundidade a 45 graus;
- centralizacao;
- limite horizontal;
- limite vertical;
- ausencia de corte;
- somente 12 arestas;
- ausencia de detalhes internos.

### 17.2 Individual

Testar, no minimo:

```text
600 x 400 x 18 mm
2400 x 600 x 15 mm
300 x 300 x 30 mm
100 x 100 x 100 mm
```

Verificar:

- largura, comprimento e espessura coerentes;
- chapa fina reconhecivel;
- nenhuma alteracao na malha real;
- preview atualizado apos mudanca de espessura permitida.

### 17.3 Interface

1. Abrir o painel N na largura inicial.
2. Anotar visualmente o tamanho do preview.
3. Dobrar a largura da sidebar.
4. Confirmar tamanho identico do preview.
5. Reduzir a sidebar ate o menor tamanho razoavel.
6. Confirmar ausencia de sobreposicao destrutiva ou erro.
7. Alterar UI Scale nas preferencias e confirmar apenas a escala nativa.
8. Testar tema claro e tema escuro.

### 17.4 Cache

1. Manter medidas estaticas e provocar varios redraws.
2. Confirmar que o rasterizador nao e' chamado novamente.
3. Percorrer mais valores que o limite do cache.
4. Confirmar descarte das entradas wireframe mais antigas.
5. Confirmar que fotos da biblioteca continuam carregadas.


## 18. Criterios de aceite

A implementacao so' pode ser considerada concluida quando todos os itens
abaixo forem verdadeiros:

- [ ] Existe um wireframe no modo Individual.
- [ ] Existe um wireframe no modo Grupo.
- [ ] O Grupo e' somente uma caixa externa.
- [ ] O desenho possui somente as 12 arestas do paralelepipedo.
- [ ] Nao existem portas, puxadores ou divisoes.
- [ ] Nao existem faces preenchidas.
- [ ] O fundo e' transparente.
- [ ] A profundidade permanece a 45 graus.
- [ ] As tres dimensoes influenciam o desenho.
- [ ] A escala usada em X e Y e' uniforme.
- [ ] Objetos pequenos e grandes ocupam a mesma area maxima.
- [ ] O desenho nao ultrapassa a area util.
- [ ] Nenhuma linha e' cortada nas medidas extremas testadas.
- [ ] O desenho permanece centralizado.
- [ ] A espessura do traco permanece constante.
- [ ] Alargar o painel N nao aumenta o preview.
- [ ] O preview atualiza quando uma medida muda.
- [ ] O preview atualiza ao trocar Individual/Grupo.
- [ ] O preview atualiza ao trocar a selecao.
- [ ] O cache tem limite.
- [ ] O cache nao remove fotos da biblioteca.
- [ ] Nenhum objeto auxiliar e' criado na cena.
- [ ] Nenhum arquivo permanente e' criado para cada atualizacao.
- [ ] Undo/redo apresenta as medidas restauradas.
- [ ] Desativar o add-on remove seus recursos.
- [ ] O add-on passa em `py_compile`.
- [ ] A funcionalidade foi validada dentro do Blender.


## 19. Riscos tecnicos e mitigacoes

### Risco 1: atualizacao de pixels do ImagePreview

Problema:

- diferencas entre versoes do Blender podem afetar a atualizacao imediata de
  previews preenchidos diretamente por Python.

Mitigacao:

- criar preview imutavel por chave;
- validar nas versoes suportadas;
- usar arquivo temporario somente como contingencia.

### Risco 2: custo de rasterizacao em Python

Problema:

- loops Python sobre muitos pixels podem afetar arraste continuo.

Mitigacao:

- canvas pequeno;
- iteracao apenas nas caixas locais das 12 linhas;
- cache por medidas arredondadas;
- debounce opcional;
- evitar regenerar em cache hit.

### Risco 3: layout nativo do painel N

Problema:

- o usuario controla a largura da sidebar e o Blender controla a distribuicao
  final dos widgets.

Mitigacao:

- escala limitada entre minimo e maximo;
- largura em unidades de UI quando possivel;
- empilhamento automatico abaixo de 310 px logicos;
- campos sem largura fixa no modo estreito;
- grade L/A e P/E em duas colunas, com cada rotulo e campo centralizado dentro
  da propria celula e divisao explicita 50/50; o contêiner da grade tambem deve
  usar alinhamento central para nao ser compactado a esquerda pelo Blender;
  sem E, P centralizada pela divisao 25/50/25;
- abaixo de 210 px logicos, cada medida ocupa uma linha propria, centralizada,
  com o campo usando 80% da largura util; a mesma regra vale para Espessura,
  evitando truncamento dos rotulos no painel extremamente fino;
- ao quebrar do layout horizontal para o empilhado, o wireframe permanece na
  escala maxima 9; ele so diminui quando a propria largura disponivel ficar
  menor que a necessaria para esse tamanho;
- no layout horizontal, a divisao invisivel reserva 4.5 unidades de UI para os
  controles e entrega todo o restante ao preview, evitando compressao precoce;
- teto de 7.5 unidades para o preview estreito e 9 para o largo.
- centralizacao final pelo bounding box alfa, incluindo indicadores laterais.

### Risco 4: baixo contraste entre temas

Problema:

- uma linha fixa pode desaparecer em tema claro ou escuro.

Mitigacao:

- derivar a cor do tema;
- incluir a cor na chave de cache;
- manter fallback testado.

### Risco 5: cache compartilhado com biblioteca

Problema:

- limpar previews procedurais pode remover fotos de presets.

Mitigacao:

- prefixo exclusivo `wireframe:`;
- limpeza seletiva;
- teste explicito da biblioteca depois da integracao.


## 20. Decisoes consolidadas nesta fase

As decisoes abaixo vieram diretamente da definicao do produto e nao devem ser
reabertas durante a implementacao sem nova orientacao:

1. A representacao e' dinamica, nao uma imagem fixa.
2. A representacao e' proporcional as medidas digitadas.
3. A profundidade usa angulo fixo de 45 graus.
4. A aparencia e' wireframe.
5. O Grupo e' somente um box externo.
6. Nao desenhar portas.
7. Nao desenhar puxadores.
8. Nao desenhar elementos internos.
9. Nao preencher faces.
10. O tamanho responde a largura: entre 5 e 7.5 unidades no modo estreito e
    ate 9 no largo; abaixo de 310 px controles e desenho quebram de linha.
11. O desenho sempre se ajusta ao limite interno do canvas.
12. A proporcao deve ser preservada durante esse ajuste.
13. Os pontos coloridos da referencia nao fazem parte do resultado.
14. A implementacao nao deve criar objetos auxiliares na cena.


## 21. Questoes que so' exigem decisao durante o refinamento visual

Estas questoes nao bloqueiam o inicio da implementacao e podem ser resolvidas
por prototipo visual:

- resolucao final exata do canvas;
- valor final da escala fixa do componente de UI;
- margem final em pixels;
- espessura final do traco;
- cor exata derivada do tema;
- alinhamento horizontal exato dentro da coluna reservada;
- necessidade real de debounce;
- necessidade da contingencia por arquivo temporario;
- comportamento de layout na menor sidebar possivel.

Ao tomar uma dessas decisoes, registrar o valor final no codigo por meio de
constante nomeada e atualizar este documento se o comportamento funcional
mudar.


## 22. Resultado esperado

O usuario ve os campos de medidas e, quando houver largura, um box wireframe
limpo ao lado. Em painel estreito, o box quebra automaticamente para baixo. Ao
alterar qualquer medida, o box muda de proporcao imediatamente. A profundidade
continua inclinada a 45 graus. O box aumenta enquanto ainda cabe em sua area
natural e para de aumentar ao atingir 9 unidades de UI; nunca fica menor que
5 unidades. No modo Grupo, o box representa somente o volume externo
do modulo agrupado. No modo Individual, representa somente o volume da chapa.

O recurso deve parecer uma parte nativa, previsivel e leve da interface do
Blender, sem alterar a cena e sem interferir nas funcoes existentes do Cabinet
Creator.
