# Funcionalidades do Cabinet Creator e o teste de cada uma

Inventario da versao 126. Coluna "Testes" = suite(s) que exercitam a
funcionalidade (`test_<suite>_blender.py`, `gui_interacao.py`,
`snapshot` = golden master). A trava `test_cobertura_blender.py` cobra
que toda classe registrada apareca aqui por algum teste.

## Chapa (unidade basica)

| Funcionalidade | Codigo | Testes |
|---|---|---|
| Malha real por bmesh, eixos X=L Y=C Z=E | `gerar_malha_chapa`, `nova_chapa` | estrutura, snapshot |
| Malha modelada nunca e' substituida (estica) | `_malha_e_caixa`, `_esticar_malha` | estrutura |
| Espessura livre; alerta vermelho > 60 mm | `_espessura_livre`, `_medida_em_alerta` | estrutura, hud, portas |
| Escala (S) vira medida, Z descartado | `normalizar_chapas`, handler, timer | estrutura, operadores, gui (S no modulo) |
| Sair do Modo Edicao atualiza as medidas | `absorver_edicoes_de_malha` | estrutura |
| Marcar/desmarcar chapa | `cabinet_marcar` | gaveta, importacao |

## Modulo / adjacencia

| Funcionalidade | Codigo | Testes |
|---|---|---|
| Agrupar chapas num Empty com medidas | `cabinet_agrupar`, `agrupar_chapas` | hud, portas, operadores |
| Grupo com nome: Empty + Collection iguais, nome pedido (F3 dialogo / caixa na gaveta ao a Corrente juntar soltas), porta nomeada pelo modelo, desagrupar vai a' raiz | `nomear_grupo`, `_nome_da_porta`, `cabinet_nomear_grupo`, `cabinet_digitar_nome_grupo` | portas, hud |
| Orcamento do ERP: documento completo no padrao do prompt (so' Moveis), detalhes do 3D (portas, prateleiras, divisorias, puxadores), pendencias; resultado da copia NA gaveta | `orcamento_da_cena`, `_pecas_internas`, `cabinet_exportar_orcamento` | orcamento, snapshot, gui_interacao |
| Comodo = pasta no Outliner (Collection com as dos armarios), linha que expande na aba Modulos, "Outro nome..." digitado, Varanda = Sacada, armario antigo ganha Collection | `definir_comodo`, `cabinet_definir_comodo`, `_abrir_caixa_comodo` | orcamento, gui_interacao |
| "Criar Puxador" laranja no topo da aba Puxadores (padrao do Criar Portas) | `_botao_criar_puxador` | gaveta, puxadores, gui_interacao |
| L/A/P do modulo reacomodam as pecas | `redimensionar_grupo`, `conj_*` | hud, portas, snapshot |
| Espessura do modulo engrossa para dentro | `aplicar_espessura_grupo` | operadores, snapshot |
| Espessura de UMA chapa ancora na face externa | `aplicar_espessura_chapa` | operadores |
| Grupo solto (sem Empty) pelos campos da cena | `grupo_*_mm`, `redimensionar_grupo_da_cena` | operadores, portas |
| S no Empty do modulo (era bug, v126) | `absorver_conjuntos` | operadores, gui |
| Adjacencia: memoriza e fecha o vao | `detectar_adjacencia`, `aplicar_adjacencia` | estrutura, operadores |
| Vizinho por UID (copias .001) | `_resolver_vizinho` | operadores, biblioteca |
| Correntes (Alt): todas as quinas soldadas com desvio > 5 mm, corrente (desagrega) + regua (resetar) | `_ligacoes_adjacencia`, `desagregar`, `VIEW3D_GGT_correntes_cabinet`, `cabinet_clique_corrente`, `cabinet_tecla_corrente` | hud, gui |
| Botao Corrente da gaveta pela selecao: grupo/peca -> "tem certeza?" e desagrega; alvos + peca de fora (ativo) -> conecta ate' 5 mm ou selecionar vertices; Juntar ao modulo (alvo parado); dispara no soltar | `_acao_corrente`, `cabinet_corrente_objeto`, `cabinet_desagregar_selecao`, `desagregar_grupo`, `cabinet_conectar_distancia`, `cabinet_conectar_vertices`, `cabinet_confirmar_conexao`, `cabinet_juntar_modulo`, `_puxar_por_pares`, `associar_por_distancia` | hud, gui |
| Ancoras da solda: arrastar a bolinha (Alt) troca o vertice; a regua deforma ate' la' | `cabinet_arrastar_ancora`, `_ancoras_da_ligacao`, `_deformar_ancoras`, `_medida_solda` | hud, gui |
| Resetar distancia (regua): chapa ativa volta a solda (pergunta se muda a medida); modulo ativo se adapta | `cabinet_resetar_distancia`, `_plano_reset_chapa`, `resetar_ponta`, `_peca_afastada` | hud, gaveta, gui |
| Medidas relidas sozinhas (sem "Sincronizar") | `_sincronizar_medidas_ativas` | gaveta |

## Selecao e HUD na viewport

| Funcionalidade | Codigo | Testes |
|---|---|---|
| Clique = modulo; duplo = peca. Porta: clique = porta inteira, duplo = folha | `cabinet_selecionar`, `_selecionar_porta_hud`, `_ENTRADAS_KEYMAP` | hud, portas, gui |
| Aba Portas: Criar Portas no topo; campos de folga so' com porta | `_aba_portas_gaveta`, `_botao_criar_portas` | gaveta, portas |
| Espessura de UMA chapa nao puxa as soldas | `aplicar_espessura_chapa` | operadores |
| Clique num de varios selecionados deixa so' ele | PRESS/CLICK pass-through | hud |
| Shift+clique soma grupo (ou so' a chapa, se o grupo ja' esta' individual); Shift+duplo isola a chapa dentro da selecao | `_somar_peca`, entrada Shift+DOUBLE_CLICK | hud, gui |
| Poll: so' Object Mode / preferencia | `OBJECT_OT_selecionar.poll` | operadores |
| Contorno nativo some no modulo e volta como era | `sincronizar_contornos` | hud |
| HUD em TODOS os itens selecionados, sem ordem (grupos e chapas); seta e quina em qualquer item | `_itens_da_selecao`, `_itens_hud`, `_acertar_hud`, `_alvo_e_do_item` | hud, gui |
| Ctrl+Z com o mouse na HUD nao desenha objeto liberado (crash do usuario) | `_esquecer_referencias`, `_alvo_vivo` | hud, operadores, gui |
| Ctrl+Z logo apos criar a porta: modal terminado solta os objetos da cena | `_larga_dados_ao_terminar` | operadores |
| Linhas L/A/P/E, rotulos, seta com teto | `_geometria_hud`, `_rotulos_hud`, `_triangulos_seta_hud` | hud, snapshot |
| Arrastar a seta: quina parada | `cabinet_arrastar_hud`, `_aplicar_valor_hud` | hud, gui |
| Clicar na seta e digitar | `OBJECT_OT_arrastar_hud._digitar` | hud, gui |
| Caixa de digitar: operador continua a conta, clique move o cursor, unidade solta/no meio vale para o numero | `_tecla_no_texto`, `_cursor_no_x`, `_arrumar_texto_medida` | hud, gui |
| E com seta nas quinas | `_redimensionar_chapa_ancorada` (eixo 2) | hud |
| Varios itens: sem pop-up; os sem seta piscam; uma seta por item e o valor vale para todos | `_itens_da_selecao`, `_piscar_pendentes`, `_brilho_piscada` | hud, gui |

## Gaveta (interface lateral)

| Funcionalidade | Codigo | Testes |
|---|---|---|
| Abre na menor largura com L/A/P em linha | `cabinet_alternar_gaveta`, `_largura_inicial_gaveta` | estrutura, gui |
| Abas Modulos / Portas / Puxadores | `('aba', ...)` | gaveta, gui |
| Bloco de medidas fixo, campos editaveis | `_bloco_medidas_gaveta`, `cabinet_editar_medida_gaveta` | gaveta, portas, gui |
| Biblioteca fixa embaixo, divisoria arrastavel | `_paineis_gaveta`, `_divisa_gaveta` | gaveta, gui |
| Cada painel rola sozinho | `_limites_rolagem_gaveta` | gaveta, gui |
| Widget cortado clica na parte visivel | `_recortar_ao_painel` | gaveta |
| Hover/glow por gizmo invisivel | `VIEW3D_GGT_cabinet_gaveta`, `VIEW3D_GT_campo_gaveta` | estrutura, gui |
| Engrenagem: opcoes, cores, faixas, suspensos | `_rodape_gaveta`, `cabinet_opcoes_gaveta` | gaveta |
| Pergunta de botao da gaveta DENTRO dela (caixa preta); pop-up so' na viewport | `_perguntar`, `_pergunta_na_gaveta`, `cabinet_responder_pergunta` | gaveta, hud, gui |
| Botao invalido apagado (cinza, sem clique) | `_operador_apagado` | gaveta |
| Layout completo nas larguras 190/320/482/564 | `_widgets_gaveta` | snapshot |

## Biblioteca de presets

| Funcionalidade | Codigo | Testes |
|---|---|---|
| Indice, niveis (com formato antigo) | `_ler_indice`, `_niveis_de`, `registrar_no_indice` | biblioteca |
| Catalogos: raiz unica, migracao com UUID | `_garantir_catalogos`, `_migrar_raiz` | biblioteca |
| Salvar preset (.blend + foto + indice) | `cabinet_salvar_biblioteca`, `salvar_na_biblioteca` | biblioteca |
| Foto como preview do asset | `aplicar_preview_png`, `cabinet_regerar_previews` | biblioteca |
| Reorganizar catalogos | `cabinet_refiliar`, `refiliar_preset` | biblioteca |
| Editar / cadeado do preset | `cabinet_editar_modelo`, `cabinet_bloqueio` | biblioteca |
| Navegar na cascata | `cabinet_navegar` | biblioteca |
| Inserir no cursor | `cabinet_inserir_preset`, `inserir_preset` | biblioteca |
| Clique na foto -> posicionador -> clique na viewport | `cabinet_arrastar_preset` | gui |
| Duplo clique na foto -> no cursor 3D | `_duplo_clique_na_foto` | gaveta, gui |

## Portas

| Funcionalidade | Codigo | Testes |
|---|---|---|
| Calculo das folhas (giro/basculante/correr, dobradicas) | `_calcular_folhas_portas` | portas, snapshot |
| Criar pelo vao (2 cliques, ima) | `cabinet_apanhar_vao`, `cabinet_portas` | portas |
| Wizard de 4 cliques: cobertura por lado, dobradica automatica, margem espelhada, aviso fora do padrao | `_coberturas_dos_cantos`, `_espelhar_margem`, `_lados_fora_do_padrao`, `_dobradica_da_cobertura` | portas, gui |
| Wizard: folhas, abertura, borda das dobradicas (basculante = sempre CIMA, sem perguntar), qtd (scroll), margem (Y), pistoes do basculante (posicao automatica; Y so' sobe, trava no curso) | `_arestas_da_porta`, `_posicoes_ferragens` | portas, gui |
| Pistao do basculante: modelo real do catalogo e posicao pela conta aberto = 2x fechado; manual limitado ao curso; volume laranja no wizard | `_geometria_pistao`, `_pistao_do_vao`, `_pontas_pistao`, `_caixas_dos_itens_pistao` | portas |
| Dobradica como volume na face interna da chapa (corpo + caneco) | `_caixas_dobradicas` | portas |
| Porta selecionada: folhas (branco), vao (amarelo) e fios dos 4 cantos (sem as dobradicas); Alt arrasta um canto e refaz a porta | `_desenho_da_porta`, `_cantos_da_porta`, `cabinet_arrastar_canto_porta`, `cabinet_cantos_porta` | portas, gui |
| Dobradica Reta = modelo + rig do usuario (asset de `extrair_dobradica.py`): uma copia por dobradica (driver + IK dele, malha dividida), Boolean do copo na folha (furo medido no copo), a folha segue a tabela medida no rig e o controlador gira a copia junto; folga minima do modelo ate' o modulo; sem o asset, caixas e eixo fixo | `_instanciar_rig`, `_passo_rig`, `_movimento_rig`, `_furar_folhas`, `_girar_rigs`, `_afastamento_porta` | portas |
| Ferragens de verdade (Fase 3): dobradica = corpo no modulo + caneco na folha; pistoes com mira (Damped Track), corpo/haste no diametro real e suportes; trilho do correr; o Blender nao as seleciona; conferidas ao apagar/duplicar | `_ferragens_da_porta`, `_montar_ferragens`, `_conferir_ferragens` | portas, hud |
| Ferragens selecionadas: duplo clique = a peca (selecao nativa, Tab edita); clique = todas do tipo no modulo, Shift soma o outro, so' elas acesas (volume laranja); Alt = controlador (dobradica na borda = margem espelhada; pistao na lateral, trava no curso) | `_selecionar_ferragem`, `_selecionar_peca`, `_ferragens_em_edicao`, `_caixas_ferragens`, `_controles_ferragens`, `_valor_do_controle`, `cabinet_arrastar_ferragem` | portas |
| Abertura por folha (giro na quina das costas da borda da dobradica -- da frente na embutida --, basculante, correr; aberta sem vao ate' o modulo) que sobrevive a redimensionar; slider na base da folha (direita abre, Ctrl+Z desfaz) | `_matriz_abertura`, `_definir_abertura`, `cabinet_abrir_porta` | portas, gui |
| Folha nunca rente a' borda: toda cobertura padrao (reta, meia, embutida, correr) deixa 2 mm de respiro | `_cobertura_mm`, `RESPIRO_PORTA_MM` | portas, snapshot |
| Ima no meio da espessura = porta cobre meia chapa menos 2 mm de respiro (e acompanha o modulo) | `_alvos_do_ima`, `_meias_do_vao`, `_inicios_porta` | portas |
| Porta vinculada acompanha o modulo | `atualizar_portas_do_conjunto` | portas, snapshot |
| Porta no modulo/no mundo (so' F3; correntes entre as abas descontinuadas) | `cabinet_corrente_porta` | portas, importacao |
| Varios selecionados: o ativo com a linha da HUD mais grossa | `_principal_hud`, `_espessura_principal_hud` | hud |
| Editar parametro de porta colocada | `_editar_parametro_porta` | portas, gaveta |
| Definir a frente com clique | `cabinet_definir_frente` | importacao, gui |
| Converter em porta / porta dupla / vincular | `cabinet_folha_de_objetos`, `cabinet_porta_dupla`, `cabinet_vincular_porta` | importacao |

## Importacao e puxadores

| Funcionalidade | Codigo | Testes |
|---|---|---|
| Classificar peca (chapa x acessorio) | `_analisar_peca`, `cabinet_converter_modulo` | importacao |
| Converter em puxador / vincular a folha | `cabinet_converter_puxador`, `cabinet_vincular_puxador` | operadores |
| Puxador importado com cadeados L/A/P | `_ajustar_puxadores` | importacao |
| Puxadores parametricos (perfil/alca/borda) | `criar_puxador`, `posicionar_puxador` | puxadores, snapshot |
| Ferramenta de linha + snaps | `cabinet_posicionar_puxador`, `_snaps` | puxadores |

## Registro

| Funcionalidade | Codigo | Testes |
|---|---|---|
| Toda classe em CLASSES, unregister limpa tudo | `register`/`unregister` | estrutura, operadores |
| Toda classe com teste | trava | cobertura |

## Sem teste (aceito, com motivo -- ver `SEM_TESTE_ACEITO`)

Preferencias do add-on (so' existem com ele habilitado), abrir pasta no
Explorer, Asset Browser e prateleira (dependem de area/arraste nativo),
registrar bibliotecas (mexe nas preferencias do USUARIO), operadores do
painel legado (`modo_medidas`, `definir_tamanho`). Desenho por GPU so'
e' visto na GUI (sem comparacao de imagem ainda).
