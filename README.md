# Cabinet Creator

Add-on de Blender para gerar armarios de moveis planejados na G3.

## O que resolve

Chapas (paineis de madeira) com **espessura livre positiva** que
permanece imune a qualquer escala — propria, herdada de um pai, ou aplicada
em selecao multipla. A malha e' real (bmesh), entao continua editavel em
Edit Mode.

## Estrutura

Fundos (360): nova aba com criacao por dois cantos e snap nativo. Oferece
canal recuado (6/9 mm, recorte booleano nos apoios), sobreposto pregado e
interno rente (15 mm). Gavetas e prateleiras vinculadas acompanham a face
interna; Desassociar fundo usa o icone de alfinete solto e conserva medidas.
Os fundos existentes conservam a modelagem e o comportamento legado.

Soldas (359): cada par de objetos tem uma unica conexao e um par de
vertices. Solda manual respeita o destino escolhido; arquivos antigos
preservam o gap cadastrado. A migracao da biblioteca usa os vertices
reais mais proximos sem mudar a modelagem.
Biblioteca revisada: 328 presets auditados, 265 atualizados; 407 registros
redundantes removidos, conservando todos os pares, geometria e materiais.

Selecao mista (358): somar com Shift um objeto comum ao modulo devolve
o contorno nativo do Blender para identificar a origem do material.
Retirar esse objeto retoma o contorno do add-on.

Edicao nativa do grupo (357): reduzir a altura pelo Tab/G conserva a
malha dos puxadores editados junto com as chapas. Ferragens atualizam em
lote, sem recalcular a cena inteira para cada dobradica.

Materiais nativos (356): selecione o modulo de destino e, com Shift,
clique na chapa de origem por ultimo. Ctrl+L > Vincular materiais usa
a malha clicada como mestre, mantendo as pecas dos grupos selecionadas.
Para copiar somente de uma chapa pertencente a outro modulo, use
Shift+duplo clique nela. A transferencia e o undo usam o comando nativo
do Blender. Em Solid, Cor > Material exibe o material vinculado.

Posicionamento em parede (301): biblioteca, duplo clique e arraste direito
usam a mesma area livre. O volume completo para na borda e nos vizinhos
da mesma face/altura; sem espaco, a insercao e' recusada e o reposicionamento
e' cancelado. Nao redimensiona para caber. A caixa da previa usa o envelope
do modulo e a mira fica no centro aceito, inclusive junto a quinas.
Cotas usam traco duplo contrastante, setas e numeros maiores sobre fundo;
a cota do item ativo acompanha o realce escolhido para a HUD.

Orcamento (300): em Opcoes > Gerar orcamento, o .txt no padrao existente
recebe automaticamente medidas gerais do corpo/moldura (largura x altura x
profundidade, em mm), portas por abertura, tipos de dobradica, gavetas internas,
prateleiras, divisorias, puxadores e materiais efetivamente utilizados.
A ficha e' lida do modelo a cada exportacao; exclusoes e edicoes nao dependem
das contagens antigas do preset. Modulo girado conserva seus eixos; abrir
portas/gavetas nao aumenta a medida. Material misto e' listado sem incluir
ferragens; falta de material ou identificacao de dobradica gera pendencia.
Comodos continuam sendo as pastas marcadas no Outliner.

Edicao de parede (299): selecione uma malha vertical e use Paredes >
Editar parede no menu esquerdo, ou Cabinet Creator > Editar parede no
botao direito. A vista ortografica isola a face e seus modulos pelo Local
View nativo. Orbitar ou iniciar Walk/Fly sai; zoom e pan permanecem.
Arraste da biblioteca e solte na parede, ou use o botao direito para
reposicionar um modulo existente. O ponto de soltura determina a posicao,
conservando as dimensoes originais. Duplo clique na foto insere a' direita
do ultimo modulo posicionado; sem espaco a' direita, volta ao centro da
parede. Sem modulo anterior, tambem comeca no centro. Nao estica para preencher.
Na composicao existente, clique nas cotas da elevacao para digitar ou use
os campos do modulo no menu. Livre/Fixa controla quais larguras recebem
o espaco restante em Redistribuir composicao. G e exclusao recalculam os
vaos, preservando os vizinhos. Trocar modelo pede uma escolha na biblioteca
e so' substitui ao confirmar, mantendo tamanho/posicao/associacao.
Parede nao mostra nem aceita medidas pelo menu; sua modelagem usa as
ferramentas nativas do Blender. Parede e modulos usam superficies solidas com contornos pretos,
sem origens ou linhas de parentesco. Ao orbitar, volta a' perspectiva;
as demais configuracoes visuais anteriores sao restauradas ao sair.
Nesta vista, clique numa porta seleciona o modulo; duplo isola a folha.
O interior aparece em arestas reais cinza semitransparentes atras das frentes.
Cotas ficam junto da peca selecionada; a representacao nao altera malhas.

```
cabinet_creator/
  __init__.py        # carga, ligacao e registro
  chapas/            # malha e espessura da peca
  modulos/           # corpo, envelope e dependentes
  portas/            # vao, cobertura e folhas
  gavetas/           # gavetas do movel e assistente compartilhado
  prateleiras/       # unidades e espacamentos
  divisorias/        # chapas verticais e segmentacao de sistemas
  gaveta*.py         # MENU: layout, desenho e eventos
  hud.py             # cotas e interacao na viewport
  promob.py          # integracao de objetos importados
  paredes_edicao.py  # vista local de parede e distribuicao de presets
  paredes_composicao.py # cotas, larguras fixas e troca de modelo na parede
  biblioteca/        # presets de fabrica (viajam com o add-on)
    *.blend
    indice.json      # catalogo dos presets (niveis sem limite)
build.py             # gera dist/cabinet_creator.zip
vincular_blender.py  # liga a pasta do projeto ao Blender (junction)
```

Para desenvolvimento, comece pelo [mapa de setores](ARQUITETURA.md):
tarefa, arquivo dono, guia local e suite de testes. Os seis pacotes conservam
os nomes publicos anteriores; cada um possui instrucoes AGENTS.md/CLAUDE.md.

## Desenvolvimento

1. `python vincular_blender.py` — cria um junction de `cabinet_creator/` para a
   pasta de add-ons do Blender. A partir dai, editar o codigo aqui altera
   o add-on carregado.
2. No Blender, recarregue o add-on (desabilitar/habilitar em Preferences,
   ou reiniciar).
3. `python build.py` — empacota `dist/cabinet_creator.zip` para instalar em outras
   maquinas.

## Conceitos centrais

- **Eixos locais da chapa:** X = largura, Y = comprimento, **Z = espessura**.
  Para orientar uma peca use rotacao, nunca escala.
- **Normalizacao:** apos o `S` terminar, a escala acumulada vira medida em mm
  e o componente Z e' descartado — e' o que torna a espessura imune.
- **Adjacencia:** cada ponta memoriza o vizinho e a folga, para fechar as
  juntas depois de redimensionar.
- **Espaco de mundo:** toda a geometria usa `matrix_world`. Usar `location`
  local quebra assim que o Empty pai sai da origem.

## Interface e portas

O menu esquerdo e' uma area VIEW_3D propria desenhada por GPU, com as abas
Modulos, Portas, Gavetas, Prateleiras, Divisorias e Puxadores. A biblioteca
fica numa faixa separada no topo. Selecao e contexto determinam os campos
exibidos; desenho e recusas de interface estao em [DESIGN.md](DESIGN.md).

Para criar uma porta em Object Mode:

1. Na aba Portas, clique em Criar Portas.
2. Marque dois cantos opostos nos limites desejados da porta. O solver
   normaliza o vao e calcula a cobertura: inteira no canto externo, meia
   no meio da espessura, embutida no canto interno. A dobradica e' automatica.
3. Escolha folhas/abertura e confirme as etapas de ferragens aplicaveis.
   A gaveta mostra as mesmas etapas da viewport. Esc cancela; direito volta.
4. Depois, clique na porta para editar o conjunto; duplo clique isola a
   folha. Reposicionar tambem usa dois cantos. O Tab continua nativo.

Aberturas: giro, basculante, correr e zigzag. Correr pode ser embutida ou
com moldura; os limites mistos pedem a escolha. Valores e opcoes vivem
nas propriedades existentes, sem um segundo modelo de dados para a UI.
Os campos permitem arrastar ou clicar para digitar; Enter confirma e Esc
restaura. As malhas modeladas e os materiais devem ser preservados.

Para trabalhar no codigo: [guia de portas](cabinet_creator/portas/AGENTS.md),
[guia de interface](planejamento/setores/interface/AGENTS.md) e
[mapa completo](ARQUITETURA.md).

### Testes no Blender

```powershell
& 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' --background --factory-startup --python-exit-code 1 --python tests/test_portas_blender.py
& 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' --background --factory-startup --python-exit-code 1 --python tests/test_gaveta_blender.py
```

Executa os testes em uma cena descartavel: coberturas, recuos, limites de
folhas, colisao entre planos, selecao BMesh conjunta, transformacoes do pai,
malhas fechadas, edicao e preservacao de materiais. Nao execute esse script
na cena de trabalho: ele limpa a cena de testes.

## Limitacoes conhecidas

- No Blender 4.2, redo de lote na parede pode restaurar a segunda Collection
  sem religar a cena; o teste continua ativo. Ocorre tambem sem desenho interno.

- A gaveta e' uma area separada da viewport; a largura e' ajustada pelo
  usuario arrastando a divisoria entre as duas areas. Ao soltar, o limite
  de 564 px e' reaplicado por `screen.area_move` quando ha' uma viewport
  adjacente. Nao e' uma trava durante o gesto: `Area.width` e' somente leitura.
- O arraste de presets entre a gaveta e a viewport usa um operador modal
  proprio; o fluxo completo depende de teste interativo no Blender.
- Blender 5.2 tem um bug que impede escrever inputs de modificador Geometry
  Nodes via Python (issue #160038) — por isso a malha e' gerada com bmesh.
