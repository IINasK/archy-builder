# Cabinet Creator

Add-on de Blender para gerar armarios de moveis planejados na G3.

## O que resolve

Chapas (paineis de madeira) com **espessura discreta** (15/18/20/30 mm) que
permanece imune a qualquer escala — propria, herdada de um pai, ou aplicada
em selecao multipla. A malha e' real (bmesh), entao continua editavel em
Edit Mode.

## Estrutura

```
cabinet_creator/
  __init__.py        # o add-on inteiro
  biblioteca/        # presets de fabrica (viajam com o add-on)
    *.blend
    indice.json      # catalogo dos presets (3 niveis)
build.py             # gera dist/cabinet_creator.zip
vincular_blender.py  # liga a pasta do projeto ao Blender (junction)
```

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

## Portas parametricas

O Cabinet Creator agora tem uma area propria na esquerda da viewport,
independente do painel N. A alca amarela abre e fecha essa gaveta; aberta,
ela ocupa toda a altura da viewport e reduz a largura da area de modelagem.
Sua borda pode ser arrastada para ajustar a largura. A gaveta contem as
abas **Modulos** e **Portas**, medidas editaveis, wireframe do modulo,
montagem e biblioteca em cascata com fotos e acoes por preset. A barra de
tamanho recebe arraste. O posicionador pode ser iniciado na foto ou nome
do preset e acompanha o cursor ate' a viewport principal. O painel N nao
e' usado pelo addon; continua disponivel para os demais paineis do Blender.
O conteudo da gaveta limita sua largura util, e as fotos da biblioteca
mantem formato quadrado em qualquer largura. A rolagem para no ultimo
controle, sem deixar uma area vazia acima do menu. O fundo cinza das fotos
e' aplicado so' na interface; os PNG originais permanecem transparentes.

1. Selecione a malha do movel ou as duas chapas que contem os cantos.
   Entre em **Modo Edicao**, ative selecao de vertices e desmarque tudo.
2. Selecione exatamente **dois vertices opostos em diagonal**, nos cantos
   **internos** do vao e na mesma borda frontal (como superior esquerdo e
   inferior direito). Podem pertencer a objetos diferentes em edicao conjunta.
3. Na gaveta esquerda, clique em **Portas** no topo do painel
   (ao lado de **Modulos**) e depois em **Criar Portas**.
   Escolha abertura, folhas e espessura. Para giro/basculante, a escolha da
   dobradica e' obrigatoria no dialogo; nenhuma folha e' criada antes de confirmar.
4. Confira **Eixos do vao** e **Frente**: o padrao e' exterior em **-Y**, com
   altura em **Z**, usando a orientacao do pai comum ou do mundo. Para um movel
   inteiro rotacionado sem pai, escolha **Objeto ativo** (Z local = altura).
   Nao use os eixos de uma lateral individual: o Z dela representa a espessura.
5. Selecione o grupo ou uma folha e use **Configurar Portas**, na aba interna
   **Portas**, para modificar
   os parametros depois. A configuracao fica salva no `.blend`; as folhas
   existentes conservam objetos e materiais. Diminuir a quantidade remove as
   folhas excedentes, com suporte a desfazer.

| Abertura | Folhas | Posicionamento |
|---|---|---|
| Abrir (giro) | 1 a 2 | Reta, curva ou super curva |
| Basculante | 1 | Reta, curva ou super curva |
| Correr | 1 a 4 | Sempre embutida, com recuo para trilhos |

Os vertices delimitam o vao livre. A origem do grupo fica no canto inferior
esquerdo visto de frente; inverter a ordem dos vertices nao altera o resultado.
Cada folha e' uma malha fechada com 8 vertices e 6 faces, usando os mesmos
eixos locais de chapa (X = largura, Y = altura, Z = espessura).

- **Reta:** expande o contorno em uma espessura de lateral por borda.
- **Curva:** expande em meia espessura por borda. Como na reta, o verso da
  porta fica na borda frontal mais o afastamento configurado; o que muda
  entre as duas e' a cobertura da lateral.
- **Super curva:** nao expande o vao; a face externa fica alinhada a borda
  frontal, ou mais para dentro quando ha' recuo adicional.
- **Correr:** a face externa da primeira folha fica atras da borda pelo
  recuo configurado (padrao 30 mm, sempre positivo). Duas a quatro folhas
  alternam entre dois planos separados pela espessura mais a folga entre
  planos; ha' sobreposicao horizontal configuravel (padrao 20 mm).

A folga perimetral desconta material nas quatro bordas (padrao zero para
cobertura exata). No giro duplo, a folga entre folhas e' 2 mm por padrao.
As espessuras disponiveis sao 15, 18, 20 e 30 mm. A cobertura usa a espessura
de lateral informada, aplicada uniformemente nas quatro bordas.

O dialogo informa as dimensoes de cada folha e a profundidade ocupada pelas
portas de correr. Dois vertices nao informam a profundidade do armario:
confira o espaco disponivel para as folhas e trilhos. O sistema gera apenas
blocagem fechada, sem dobradicas, trilhos, puxadores ou animacao de abertura.
O vao e' capturado na criacao, sem vinculo vivo aos vertices: para remapear
um vao alterado, crie um novo grupo. Movimentos do pai comum acompanham o grupo.

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

- A gaveta e' uma area separada da viewport; a largura e' ajustada pelo
  usuario arrastando a divisoria entre as duas areas.
- O arraste de presets entre a gaveta e a viewport usa um operador modal
  proprio; o fluxo completo depende de teste interativo no Blender.
- Blender 5.2 tem um bug que impede escrever inputs de modificador Geometry
  Nodes via Python (issue #160038) — por isso a malha e' gerada com bmesh.
