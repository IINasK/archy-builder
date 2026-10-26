# Setor gavetas

## Papel e fronteiras

Gavetas do MOVEL: frente, caixa, trilhos, vao, curso e edicao por unidade.
O menu GPU e' `../gaveta.py`, nao este setor.
`AssistenteDoVao` tambem atende [prateleiras](../prateleiras/AGENTS.md) e
[divisorias](../divisorias/AGENTS.md); corrigir o gesto comum aqui, sem copiar.
Puxadores e referencia da frente: [portas](../portas/AGENTS.md), `../frentes.py`.

## Localizar tarefas

| Tarefa | Funcao / arquivo |
|---|---|
| Calculo e montagem | `calcular`, `montar`, `criar_gavetas` em `__init__.py` |
| Frente, referencia e profundidade | `referencia_do_vao`, `pontos_internos_do_vao`, `profundidade_disponivel` em `__init__.py` |
| Editar grupo/unidade/altura | `editar`, `editar_individual`, `normalizar_alturas` em `__init__.py` |
| Adaptar ao corpo | `acompanhar_redimensionamento`, `limitar_medidas`, `_adaptar_espaco` em `__init__.py` |
| Gesto comum e snap | `AssistenteDoVao`, `OBJECT_OT_marcar_ponto_vao` em `__init__.py` |
| Curso/slider/Alt | `definir_abertura`, `OBJECT_OT_abrir_gaveta`, `OBJECT_OT_arrastar_ponto_gaveta` em `__init__.py` |

## Decisoes e armadilhas

- Aba propria; 2 cliques na diagonal do vao (cima-esq -> baixo-dir), scroll =
  quantas, mouse = profundidade (Alt gruda), depois trilho: TELESCOPICO
  padrao ou OCULTO. Os cliques definem a FRENTE, nunca eixo fixo.
- Recuos desencontrados usam o plano mais interno; pontos sobre chapas
  usam faces INTERNAS. Profundidade so' projeta no eixo, limitada ao MENOR
  espaco livre por ray cast nativo UMA vez; previa conserva o cache.
  Prateleiras usam E gravam a mesma referencia.
- Trilho e' BLOCAGEM em tamanho real; o modelo definitivo nao esta' pronto.
- Clique = todas, duplo = uma; SO' elas com linha na HUD. Slider ANDA com
  a frente e nunca fica coberto. Modulo selecionado absorve os filhos.
- Alt edita 3 pontos: duas quinas da frente + profundidade. Snap NATIVO pelo
  translate do cursor; Esc restaura cursor E alvos.
- Redimensionar move pela face proxima sem crescer. Consumir a folga real
  entre as faces de apoio antes de diminuir; `espaco_disponivel` usa caixas
  nativas fora da HUD. Adaptar so' quando nao couber, ate' o minimo fisico;
  devolver escolhas ao aumentar. Largura individual menor tambem se conserva.
  `sincronizar_margens` atende gavetas E prateleiras apos o transporte.
- Referenciais conservam reflexao do Mirror do grupo: normalizar colunas, nao converter em quaternion.
- Edicao direta preserva selecao; Esc restaura medidas. Vinculo e' PAI real:
  nome antigo gravado no preset nao manda.
- Frente CURVA e alturas em PROPORCAO. Borda de CADA gaveta cede/recebe altura
  da vizinha, total fixo; externa ancora limite. Gaveta unica usa seu vao.
- Duplo abre campos individuais L/A/P, Abaixo/Acima, frente/trilho/recuo/puxador;
  grupo edita todas. Curso e material sao por unidade.
- Previa SO' parametros/contorno; montar UMA vez no confirmar.
- Criar gavetas depois de divisorias tambem chama `particionar_grupo`;
  rejeicao de vao nao deve deixar conjunto parcialmente criado.
- Protocolo compartilhado: `cabinet_marcar_ponto_vao` usa snap nativo,
  sem varredura Python de malhas no clique/arraste. Restaurar cursor no
  confirmar/Esc, undo unico. `translate.orient_matrix` recebe eixos em LINHAS:
  transpor a Matrix do grupo (colunas), senao arrasta girado ao contrario.

## Suites

Em `../../tests/`: `test_gavetas_blender.py`; gesto compartilhado/particao:
`test_prateleiras_blender.py`, `test_divisorias_blender.py`.
Selecao, slider e filhos: suites hud, operadores e portas.
Harness e eventos reais: [tests](../../tests/AGENTS.md).
