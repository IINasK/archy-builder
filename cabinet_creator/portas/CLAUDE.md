# Setor portas

## Papel e fronteiras

Folhas, vao, cobertura, vinculo e reaplicacao. Gesto em [assistente.py](../assistente.py),
rig/abertura em [ferragens.py](../ferragens.py), alcas em [puxadores.py](../puxadores.py),
slider/cantos em [portas_viewport.py](../portas_viewport.py); referencia comum em
[frentes.py](../frentes.py) e [FRONTES.md](../../FRONTES.md).
Menu/gestos gerais: [interface](../../planejamento/setores/interface/AGENTS.md).
Adocao/importacao: [integracao](../../planejamento/setores/integracao/AGENTS.md).

## Localizar tarefas

| Tarefa | Funcao / arquivo |
|---|---|
| Vao, cobertura e folhas | `_preparar_vao_portas`, `_calcular_folhas_portas` em `__init__.py` |
| Montagem/resize/espelhar | `_aplicar_portas`, `atualizar_do_conjunto`, `espelhar_porta` em `__init__.py` |
| Criar/repor e etapas | `OBJECT_OT_apanhar_vao_portas`, `OBJECT_OT_portas_parametricas` em `../assistente.py` |
| Rig e pose fechada | `_montar_ferragens`, `_matriz_fechada`, `_definir_abertura` em `../ferragens.py` |
| Puxador/modelo/Alt | `posicionar_puxador`, `OBJECT_OT_arrastar_puxador` em `../puxadores.py` |
| Contorno/borda comum | `preparar`, `bordas`, `lugar`, `transportar` em `../frentes.py` |

## Decisoes e armadilhas

- Limites internos (360): fundo novo nao amplia a caixa de apoio das portas.
- Portas atualiza SO' folhas/apoios em `atualizar_do_conjunto`. A ordem
  portas -> gavetas -> prateleiras pertence a `modulos.atualizar_sistemas_do_conjunto`.
  `atualizar_portas_do_conjunto(conj, sistemas=True)` e' fachada externa
  compativel; `sistemas=False` mapeia para `internos=False`. Nao coordenar
  internos nem usar essa fachada nos chamadores de producao.
- Curvatura exige controle EXPLICITO do add-on, inclusive adocao na importacao.
  Curvar/deformar via Tab nao converte em curva parametrica nem autoriza
  solver/reencaixe. Ler contorno para medida/puxador nao ativa esse sistema.
  Preservar modelagem manual E a regressao de resize das curvas controladas.
- Wizard `cabinet_apanhar_vao`, criar/repor: 2 CLIQUES nos limites opostos,
  pelo snap NATIVO (`AssistenteDoVao._iniciar_snap_nativo`).
  Solver normaliza vao interno; `cobertura_*_e` e' FRACAO da espessura:
  1 = Reta, 0.5 = Curva, 0 = Super Curva; dobradica AUTOMATICA.
  Nunca rente a' borda: padrao 2 mm (`RESPIRO_PORTA_MM`).
- Correr com limites mistos pergunta embutida ou moldura; fora do padrao
  confirma medidas. API de quatro pontos preservada, nao e' gesto da UI.
- Caixas do modal: Folhas -> abertura -> borda (basculante = CIMA) ->
  scroll = quantidade -> mouse Y = margem -> pistoes. Posicao AUTO:
  aberto = 2x fechado, Y so' sobe. Gaveta: aceite VERDE na etapa; caixa
  nunca cortada. Reposicionar = 2 cliques. Nao usar popup_menu: release responderia.
- Clique = porta inteira, nunca modulo; duplo = folha, sem contorno nativo.
  Selecionada POR SI: contorno branco, vao amarelo, fios e slider por folha.
  Alt arrasta SO' os 2 cliques (`CANTOS_DO_GESTO`) de `_cantos_da_porta`: refeitas, nunca gravadas;
  o destino e' o snap NATIVO do cursor (macro `cabinet_mover_canto_porta`).
- Espelhar: contexto direito, grupo ou folha; sem linha Reposicionar/Frente/Espelhar na aba. Inverter
  giro, cadeia zigzag INTEIRA, curso de correr ou basculante com pistoes.
  Puxador acompanha; nao espelhar a madeira.
- CORRER: um TRILHO por folha, percorre vao inteiro; folha unica = METADE
  do vao. Largura = L da gaveta; sem sobreposicao nem "Folga no perimetro".
- Cobrindo chapa = COM MOLDURA: chapas 15 refeitas com porta; perguntar BASE
  (sem = rodape 0) e TRILHO. Pesado = aluminio/folha 18; leve = canais
  fresados + U/folha 15, sem testeira. Conta no modulo (L/A/P e HUD).
- FOLHA: Chapa ou Quadro de aluminio, perfil 23 x 10 + painel 5 do Promob.
  ZIGZAG: 2-8 folhas alternadas; lado define primeira, puxador SO' na ultima.
  Junta com placas/nos/eixo nativos, cada metade na sua folha; slider unico.
  Fotos: TODAS fechadas, tambem canto/correr/zigzag; nao mudar lado para foto.
- Parametros na Scene, nao no operador; `cabinet_portas` com EXEC_DEFAULT
  (INVOKE abre dialogo). `_parametros_portas_da_cena` cobre `_PARAMETROS_PORTAS`
  inteiro; folgas ao modulo em ESPESSURAS (`CHAVE_FOLGAS_PORTA`).
- Frente sempre automatica (`_frente_automatica`), gravada resolvida. Os dois
  caminhos de captura usam o MESMO `_referencia_do_par`; vertices lidos UMA vez.
- Abertura na `matrix_basis` da folha centrada, filha do grupo; medir por
  `_matriz_fechada`. Nada de hide_select; conferir por `_conferir_ferragens`.
  hide_set do rig e' da CAMADA e se perde no anexo/preset: timer
  `ocultar_pecas_do_rig` deve restaurar os auxiliares.
- Reta = rig do USUARIO (`extrair_dobradica.py`, Blender 4.2): nao refazer,
  so' furo do copo; folha segue TABELA, placa/suporte vao a' face (`_calco_rig`).
  `dobradica_modelo_reta` usa o rig na cobertura parcial sem mudar vao/borda;
  copo precisa caber na folha. Curva/embutida obliqua: ray cast da face real +
  4 quinas coplanares; conservar cantos do PRISMA (AABB desorienta).
- Encaixe antigo atualiza UMA vez pelo timer, sem mudar folha/abertura/puxador.
  Rig de outra versao/parafuso panela tambem (`_ferragens_antigas`, 327).
- Reta de giro com vao/folhas/rig iguais nao remonta no reset da solda.
  Conferir poses calculadas e offsets manuais; rig faltando/antigo atualiza.
- Montagem do rig (348): asset carregado UMA vez por chamada; demais copias
  usam Object.copy, com pais/inversa, IK, modificadores e drivers remapeados.
  Fonte SO' da montagem atual, nunca rig modelado da cena nem cache RNA global.
  Remocao em lote conserva dados compartilhados ainda usados; deduplicacao
  de Mesh exige igualdade pelo comparador nativo, pois Tab conserva a marca.
  Conferir atributos antes desse comparador: conjuntos diferentes caem no 4.2.
- Frente da porta CURVA modelada (`_virar_porta_modelada`): gira o referencial
  e reescreve os vertices no mesmo mundo; `_vao_inverso` (caixa da folha) a
  deslocava. Frente invertida = dobradica por fora e abrindo para dentro.
  Texto novo (trilho/folha) entra nos enums de `_carregar_portas_na_cena` E
  `_valores_portas` em `../gaveta.py`. Copiar ID props aninhadas RECURSIVAMENTE
  antes de substituir: dict raso e acesso posterior derrubavam Blender 5.2.
- Ferragem aparece so' criando ou selecionada, arame da PECA real. Clique =
  todas do tipo, Shift soma o outro, Alt = controlador, duplo = PECA (Tab/G/X nativos).
- Tab/G (357): rigs em lote; puxador editado conserva Mesh e atualiza so' contorno.
- Tab do grupo: translacao rigida de pecas inteiras move a raiz da dobradica,
  com furo/IK/mola. Modelagem parcial fica nativa; deslocamento no referencial
  da porta persiste na raiz. Referencia numerica na Mesh recupera undo do Tab.
- Espelhos das ferragens viram vertices antes do Tab, em copia unica e na
  ordem da pilha: Clipping nao pode prender metade da dobradica no arraste.
- Puxador: clique seleciona SO' ele e suas funcoes, inclusive nas gavetas;
  trilhos das gavetas ficam com elas. Alt move ancora para borda SO' do
  proprio grupo, com snap de linha. `posicionar_puxador` refaz por PROPS da
  chapa, nunca delta. PERFIL e' padrao, SEMPRE horizontal salvo guarda-roupa
  (`importacao.posicao_do_perfil`); pontas/costas ANDAM. BORDA (322) e' o
  slim do usuario (`_deformar_borda`): metades e aba andam; furos nao escalam.
  PARAFUSO padrao (323): `ferragens.malha_parafuso`; dobradica reta v3
  (`trocar_parafusos_dobradica.py`; arame: parte do calco pelo PAI).
- Folha nativa: frente +Z LOCAL, nunca comparar com -Y da caixa (inverte no L).
- Mirror do grupo conserva paridade do vao; braco angular usa mira CUSTOM no grupo, migrada no timer sem refazer malhas.
  LADO segue X da folha FECHADA, nao modulo. MODELO do usuario vem da
  BIBLIOTECA; modelos de fabrica PROTEGIDOS. Retratos: `gerar_fotos_padrao.py` (GUI).
- Frentes: atributos INT FACE/EDGE semanticos e cache numerico na Mesh;
  invalidar por Mesh/undo fora do desenho. `porta_linha_frente` so' migra
  legado; indices nao governam contorno/resize. Puxador/Alt/previa compartilham
  bordas/normais; PERFIL segue curva, fracao legada migra uma vez. Resize
  reancora pela tangente sem refazer vertices/faces editados.
## Suites

Em `../../tests/`: `test_portas_blender.py`, `test_puxadores_blender.py`,
`test_frentes_blender.py`; consumidores: importacao, hud, gaveta e gavetas.
Preservar testes de curva controlada E modelagem manual. [Harness](../../tests/AGENTS.md).
