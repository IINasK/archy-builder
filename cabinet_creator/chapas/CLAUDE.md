# Setor chapas

## Papel e fronteiras

Malha e medidas da chapa; forma individual e geometria derivada passam por
[formas.py](../formas.py), [geometria.py](../geometria.py) e [frentes.py](../frentes.py).
O envelope do armario pertence a [modulos](../modulos/AGENTS.md).
Solda/ancoras: [montagem](../../planejamento/setores/montagem/AGENTS.md).
Referencia das frentes: [FRONTES.md](../../FRONTES.md).

## Localizar tarefas

| Tarefa | Funcao / arquivo |
|---|---|
| Criar, medir ou absorver Tab | `nova_chapa`, `absorver_malha_editada` em `__init__.py` |
| Malha, E e secao | `gerar_malha_chapa`, `preparar_espessura`, `_esticar_malha` em `__init__.py` |
| Cota ou angulo individual | `definir_aresta`, `definir_angulo_arestas`, `definir_deslocamento` em `__init__.py` |
| Forma/resize e apoio real | `estrutura_hud`, `_deformar`, `_apoios_dos_paineis` em `../formas.py` |
| Quinas e area | `OBJECT_OT_calcular_areas` e reconhecimento em `../geometria.py` |

## Decisoes e armadilhas

- MODULO selecionado: sempre caixa convencional, 8 cantos/12 cotas nos
  limites do envelope. Nao inferir forma/angulos do grupo; resize e' CAIXA.
  Eventos antigos de formato do grupo foram recusados, inclusive hover anterior.
- Rotulos de medidas: A1, A2... inclusive segmentos da chapa; E so' espessura.
  L/A/P/R sao identificadores internos, nunca rotulos. Menu/HUD usam as
  MESMAS cotas editaveis A1..An/E por chave semantica, nao pelo numero A.
- E vem de peles correspondentes no eixo transversal local. Dobra/flecha
  nao vira espessura; secao ambigua conserva E nominal; resize conserva linha media.
- Angulos/contorno real so' na CHAPA INDIVIDUAL selecionada, pelo plano local
  da face. Outra chapa, porta ou modulo nao acompanha essa edicao.
- Deslocamento transversal da linha media MAIOR que E recebe cota propria
  (ex.: A6), sem engrossar a madeira; arraste/Esc conserva referencia original.
- `normalizar_chapas` adia escala herdada de modulo ainda escalado: o
  timer de modulos converte S com internos pelo resize comum; absorver
  antes aplicava a escala proporcionalmente a gavetas/prateleiras.
- Isolar Mesh compartilhada antes da edicao individual. Tab e' nativo;
  sair atualiza medidas/caches, undo invalida. Sem deformacao radial;
  solver antigo do grupo so' por API, nunca automatico.
- Saida do Tab acompanha tambem puxadores: se participaram da edicao,
  conservar vertices/materiais/UV e atualizar so' contorno numerico.
  Frente inalterada reaproveita o cache, sem forcar reconhecimento.
- Tab do grupo prepara UV metrico onde falta (1 unidade/m), conserva mapas
  existentes e usa Correct Face Attributes nativo para nao esticar texturas.
- Referencia de resize nao acumula deltas: usar Mesh nativa e restaurar pais
  E `porta_centro_folha` ANTES dos filhos. Vaos de portas/gavetas seguem
  o mapa do corpo; nao reancorar antes de restaurar. E se conserva pela normal.
- `formas.matriz_do_modulo` conserva reflexao do Mirror; remover so' magnitudes da escala, nunca a paridade.
- Frente parcial apoia na FACE real (`closest_point_on_mesh` +
  `poly_3d_calc`), com pesos guardados uma vez; nunca caixa inteira nem
  busca no redraw. Cache numerico: nada de Mesh/CDT/hull na HUD do modulo.
- Vertice de canto vem do atributo `cabinet_canto`, nao do SINAL; novas soldas em malha
  modelada usam `cabinet_solda_vertice` (INT POINT, u; v legado aceito). E de UMA chapa nao mexe nas demais; so' E do MODULO
  tem esse alcance. Corrente sozinha ate' 5 mm; alem disso, mostrar vertice.
- Snap geometrico: quinas COM ANGULO, pontas e centro de curva. O ima mostra
  o rotulo; o meio do arco sai. Area = volume / E para orcamento e F3 Calcular Areas.
- Vizinho: UID entre irmaos primeiro; duplicatas antigas do UID no mesmo pai
  usam o nome gravado so' para desempatar. Distancia e' o ultimo recurso.

## Suites

Em `../../tests/`: `test_formas_blender.py`, `test_geometria_blender.py`,
`test_frentes_blender.py`, `test_hud_blender.py`, `test_operadores_blender.py`.
Resize com filhos: tambem portas/gavetas; harness em [tests](../../tests/AGENTS.md).
