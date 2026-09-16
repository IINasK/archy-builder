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

## Limitacoes conhecidas

- Reordenacao da grade e' por setas: o bpy nao expoe arraste em paineis.
- Icone sobre a imagem nao e' possivel: o layout do bpy nao tem sobreposicao.
- Largura da sidebar e' controlada pelo usuario, nao pelo add-on.
- Blender 5.2 tem um bug que impede escrever inputs de modificador Geometry
  Nodes via Python (issue #160038) — por isso a malha e' gerada com bmesh.
