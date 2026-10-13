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
| Orcamento: documento completo no padrao da empresa (so' Moveis), detalhes do 3D (portas, prateleiras, divisorias, puxadores), pendencias; "Gerar orcamento" nas Opcoes salva .txt pelo "Salvar como" e mostra o resultado no painel | `orcamento_da_cena`, `_pecas_internas`, `cabinet_exportar_orcamento`, `_botao_orcamento_opcoes` | orcamento, gaveta, snapshot, gui_interacao |
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
| Mover pela quina com Ctrl: snap so' em quinas de outros armarios/chapas | `_quinas_de_snap`, `_snap_de_quina`, `_mover_pela_quina` | hud, gui |
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
| Botoes Modulos / Materiais ao lado do titulo (estreita: linha de baixo) | `_cabecalho_biblioteca`, `cabinet_bib_modo` | biblioteca, gui |
| Materiais MDF/MDP: catalogo de cores solidas, cascata propria | `ler_materiais`, `filhos_n1`, `cabinet_mat_n1` | biblioteca |
| Pintura rapida: botao DIREITO na esfera -> quais modulos (por comodo, Sem comodo, Todos) -> Tudo / So' a caixa / So' as portas, na caixa preta sob o material; respostas quebram em filas | `cabinet_pintar_modulos`, `perguntar_pintar`, `modulos_por_comodo`, `pecas_do_modulo`, `LARGURA_MIN_RESPOSTA` | biblioteca, gui |
| Esfera: 1 clique nada; DUPLO pinta a selecao (modulo = chapas, porta = folhas + moldura, peca); ARRASTAR e soltar pinta o que esta' embaixo (na selecao = a selecao); acende a da selecao | `cabinet_aplicar_material` (`alvo`), `pecas_dos_alvos`, `pecas_do_solte`, `duplo_clique_na_esfera` | biblioteca, gui |
| Preview em esfera sombreada (sem render) | `esfera_rgba`, `desenhar_esfera` | biblioteca |
| Novo / editar / apagar material ("Apagar?" sob a fila) | `cabinet_novo_material`, `cabinet_editar_material`, `cabinet_apagar_material` | biblioteca |

## Portas

| Funcionalidade | Codigo | Testes |
|---|---|---|
| Calculo das folhas (giro/basculante/correr, dobradicas) | `_calcular_folhas_portas` | portas, snapshot |
| Criar pelo vao (2 cliques, ima) | `cabinet_apanhar_vao`, `cabinet_portas` | portas |
| Wizard de 4 cliques: cobertura por lado, dobradica automatica, margem espelhada, aviso fora do padrao | `_coberturas_dos_cantos`, `_espelhar_margem`, `_lados_fora_do_padrao`, `_dobradica_da_cobertura` | portas, gui |
| Wizard: folhas, abertura, borda das dobradicas (basculante = sempre CIMA, sem perguntar), qtd (scroll), margem (Y), pistoes do basculante (posicao automatica; Y so' sobe, trava no curso) | `_arestas_da_porta`, `_posicoes_ferragens` | portas, gui |
| Caixa e recado do wizard nunca saem cortados pela borda da viewport | `_botoes_assistente`, `_desenhar_assistente_2d` | gaveta, gui |
| Aba Portas = copia clicavel da caixa do wizard, etapa a etapa (refaz dali), com as medidas da porta | `_filas_do_assistente`, `_responder_pela_gaveta`, `ALVO_ASSISTENTE` | gaveta, gui |
| Gaveta por contexto: sem selecao so' o botao de criar; bloco de medidas so' na aba do item | `_selecionado`, `_aba_modulos_gaveta`, `_aba_portas_gaveta`, `_aba_puxadores_gaveta` | gaveta, portas, importacao, snapshot |
| Dobradicas/pistoes editaveis na gaveta: criando e com as ferragens selecionadas (todas as portas do modulo) | `_secao_ferragens_gaveta`, `_editar_assistente`, `_editar_ferragens_selecionadas`, `ALVO_FERRAGENS` | gaveta, portas, gui |
| Previa = wireframe da peca de verdade (rig da Reta pelo contorno do asset, caixas, pistoes, puxador na linha), cor de realce e espessura da HUD | `_arame_dos_itens`, `_arame_ferragens`, `_arame_puxador`, `_desenhar_arame`, `extrair_arame_dobradica.py` | portas, puxadores, gui |
| Alt + arrastar a ancora do puxador: outra borda do grupo dele, snap de linha, virado conforme a borda | `cabinet_arrastar_puxador`, `_chapas_do_grupo_do_puxador`, `_ancora_do_puxador` | puxadores, gui |
| Modelo do puxador: troca criando (posicionador) e no puxador selecionado | `_trocar_modelo`, `_trocar_modelo_puxador`, `ALVO_PUXADOR` | puxadores |
| Carrossel de RETRATOS no lugar dos nomes: modelo do puxador, abertura da porta, dobradica detectada (fotos de fabrica a 45 graus) | `_carrossel_gaveta`, `foto_padrao`, `gerar_fotos_padrao.py` | gaveta, portas, puxadores, gui |
| "Usar como puxador": objeto de fora vira MODELO na biblioteca (Puxadores, foto a 45 graus); encostado numa chapa vira o puxador dela no lugar; solto, clique na face e o criador abre com ele | `cabinet_usar_como_puxador`, `_quadro_do_modelo`, `_chapa_encostada`, `salvar_modelo_puxador` | puxadores, gui |
| Biblioteca e' a fonte dos modelos de puxador (editar la' muda o criador); de fabrica protegidos na cascata; clicar abre o criador | `modelos_do_usuario`, `_malha_modelo_usuario`, `itens_de_fabrica`, `_modelo_do_criador` | puxadores |
| A aba Portas rola ate' a etapa nova do wizard | `_rolar_ate_o_fim` | gui |
| Wizard: aceite VERDE no campo da etapa (quantidade, afastamento, pistoes); tipo da dobradica da borda sob o mouse; linha [abertura][dobradica][contador] (mockup); retrato da abertura volta a' escolha | `_confirmar_etapa`, `CONFIRMAR_ETAPA`, `_secao_ferragens_gaveta`, `_icone_acao_gaveta` | gaveta, portas, gui |
| Arrastar qualquer campo de valor (dir. aumenta, esq. diminui, Shift/Ctrl, Esc devolve, um undo); contador de quantidade (arrastar ou clicar nas metades) | `aplicar_medida`, `_modal_campo`, `_aplicar_contador` | gaveta, portas, gui |
| Correr COM MOLDURA (pedido do usuario): folhas de 18 cobrem a frente inteira do modulo, uma em cada canal do trilho de aluminio do usuario (perfis extrudados, `extrair_trilho_moldura.py`); moldura de chapas de 15 refeita com a porta: revestimento das laterais (das costas a' frente), base do trilho + testeira em cima, base + rodape embaixo, somando acima e abaixo do modulo; E de uma peca vale para todas; Espessura/Rodape/Testeira editaveis na aba | `_pecas_moldura`, `_montar_moldura`, `_avanco_moldura`, `_alturas_moldura`, `_espessura_da_moldura_mudou`, `_trilhos_moldura`, `perfil_trilho_moldura`, `MARCA_MOLDURA` | portas |
| Moldura conta como o armario: L/A/P do modulo e a caixa da HUD sao do ENVELOPE (corpo + moldura); editar L/A/P leva o envelope a' medida (o corpo recebe o alvo menos o que a moldura soma) | `pecas_do_envelope`, `_acrescimo_da_moldura`, `redimensionar_conjunto`, `medir_conjunto` | portas |
| Wizard com moldura pergunta "A porta tem base?" (viewport e gaveta): sem rodape = direto no chao (rodape 0, a peca some) | `OPCOES_BASE`, etapa `BASE` | portas, gui |
| Trilho da moldura perguntado ao criar (e trocavel na aba): PESADO = perfis de aluminio; LEVE = canais fresados nas bases da moldura (`chapa_canais`) com o U de embutir do usuario (`extrair_trilho_leve.py`), folha de 15, aba rente, 5 mm de folga em cima, sem testeira (nem o campo) | `ITENS_TRILHO`, `_trilho_leve`, `_canais_das_bases`, `_malha_com_canais`, `_gravar_canais`, `_trilhos_moldura` | portas, gui |
| Wizard: correr pelos cliques -- 1-2 e 3-4 no mesmo canto de dentro = embutida; de fora para dentro = com moldura; metade-metade pergunta "Porta embutida ou com moldura?" (viewport e gaveta) e ajusta: moldura = medida do modulo, embutida = a de dentro da chapa | `_metade_metade`, `TIPOS_CORRER`, `COBERTURA_DO_TIPO_CORRER`, `_preparar_vao_portas(forcar)` | portas |
| Aba Portas da porta selecionada em CATEGORIAS (Porta, Folhas, Posicao/Trilhos/Moldura, Abertura) com o titulo de Montagem; rotulos curtos que cabem inteiros | `_titulo_secao`, `_campos_em_linhas` | portas |
| Ancoragem: Ctrl+D numa chapa = copia com identidade propria e sem as soldas da original; "Recalcular Ancoragem" (F3) refaz as soldas das selecionadas pelo lugar (ate' 5 mm) | `separar_copias`, `_separar_copias_no_timer`, `recalcular_ancoragem`, `OBJECT_OT_recalcular_ancoragem` | operadores |
| Porta selecionada: Folhas = campo compacto ao lado do ultimo campo (Entre folhas/planos), arrasta e digita (fora do limite da abertura avisa); Reposicionar e Frente em cima das medidas, com icone ao lado do texto | `_eh_campo_contador`, `LARGURA_CAMPO_FOLHAS`, `_icone_ao_lado`, `_centro_icone` | portas |
| Retratos (puxador, abertura, dobradica) no MESMO quadrado; slider ao lado do titulo muda todos (`cabinet_tam_retrato`) | `_lado_retrato`, `_titulo_com_slider`, `_trilho_slider_gaveta` | gaveta |
| Pistao do basculante: modelo real do catalogo e posicao pela conta aberto = 2x fechado; manual limitado ao curso; arame no wizard | `_geometria_pistao`, `_pistao_do_vao`, `_pontas_pistao`, `_caixas_dos_itens_pistao` | portas |
| Dobradica como volume na face interna da chapa (corpo + caneco) | `_caixas_dobradicas` | portas |
| Dobradicas nunca se sobrepoem: margem entre a dobradica inteira na folha e o maximo que deixa 60 mm entre centros; quantidade so' ate' onde cabe (wizard, gaveta, Alt+arraste, porta gravada antes) | `_ajustar_dobradicas`, `_ajustar_dobradicas_wizard`, `_valor_ferragem` | portas |
| Parede (Promob): direito segurado no modulo, solto numa FACE vertical nao-movel (acesa no arraste) = costas nela e ASSOCIADO A' FACE (vizinhas no mesmo plano); gruda nas pontas/piso/teto; clique sem arrastar = menu de contexto | `cabinet_arrastar_na_parede`, `raio_ate_parede`, `regiao_da_parede`, `associar`, `posicao_no_arraste` | paredes, gui |
| Modulo associado: parede que anda/gira leva o modulo; G/R no modulo = volta ao plano (timer); F3 Desassociar | `manter_nas_paredes`, `cabinet_desassociar_parede` | paredes |
| Guias da parede (esquerda, direita, piso, teto) do modulo ativo: numero clicado digita, arrastado muda | `calcular_guias`, `aplicar_guia`, `cabinet_guia_parede`, `VIEW3D_GGT_guias_parede` | paredes, gui |
| Modulo de bancada (balcao, gabinete) com topo ABERTO: duas travessas de 70 mm (frente e tras) entre as laterais, refeitas pela caixa (L/P/E), sem solda | `criar_armario(topo='TRAVESSAS')`, `adicionar_travessas`, `ajustar_travessas`, `ajustar_dependentes`, `TOPO_POR_TIPO`, `MARCA_TRAVESSA` | armarios |
| Modulos do Promob: DXF exportado (camada = peca) vira modulos nativos so' com as chapas (piso, ferragens e placas finas saem; peca recortada fica com a malha), um por grupo de pecas que se encostam; script grava a biblioteca por ambiente/categoria | `ler_dxf_promob`, `importar_dxf_promob`, `importar_promob_para_biblioteca`, `cabinet_importar_promob`, `importar_promob.py` | importacao |
| Promob: porta/frente CURVA entra como acessorio que deforma (`eh_peca_curva`); prateleira de contorno curvo e' chapa; micro-ondas/cesto nao; piso fino sai mesmo com modulos fora dele; PASTA = aba e ARQUIVO = categoria ("Inferiores - Cantos", nome com a aba fora de Inferiores) | `_eh_peca_curva`, `FACES_PRINCIPAIS_MINIMO`, `_eh_piso`, `categoria_promob`, `CATEGORIAS_PROMOB` | importacao |
| Formato no menu (aba Modulos): P1, P2, Raio e o ANGULO da diagonal (a frente do canto fica, P1 anda); arrastar/digitar como as medidas | `_secao_forma_gaveta`, `aplicar_medida('forma')`, `forma_angulo_*`, `aplicar(('ANG', k))` | formas |
| Promob = INTEGRACAO: a COR da camada separa chapa (7) de ferragem/aluminio/puxador (que nunca viram peca); frente com dobradica vira porta nativa (lado da dobradica, Reta/Curva nossa; par = dupla; em cima = basculante), com caixa ou cesto atras vira gavetas nativas (pilha, alturas em proporcao, frente curva), quadro de aluminio vira correr com folha Quadro; fundo fino e travessas do topo viram dependentes; o E do modulo e' o mais comum da caixa | `cores_dxf_promob`, `promob.planejar`, `vao_atras`, `promob.aplicar`, `marcar_dependentes`, `_espessura_de` | importacao |
| Correr com folha QUADRO DE ALUMINIO (perfil 23 x 10 em volta de painel de 5 a 6 mm da frente; 2 materiais) e de volta a' chapa; escolha na aba Portas | `ITENS_FOLHA_CORRER`, `_vestir_folha`, `_chapas._malha_quadro`, `porta_folha` | portas |
| Gavetas: frente CURVA (flecha do arco, malha concentrica) e alturas em PROPORCAO (somem ao mudar a quantidade); campo Curva na aba | `frente_curva_mm`, `_chapas._malha_arco`, `proporcoes`, `frentes` | gavetas |
| Geometria: quinas com o angulo (reta 90/270, chanfro 135), pontas e centro de curva; o meio do arco sai do ima, o ponto pego ganha rotulo na tela; Ctrl do modulo gruda nas quinas/pontas de peca modelada/curva; area = volume/E e borda; F3 Calcular Areas | `pontos_notaveis`, `_alvos_do_ima`, `rotulo_do_ponto`, `marcar_rotulo`, `_quinas_de_snap`, `medidas_da_chapa`, `areas`, `cabinet_calcular_areas` | geometria |
| Gavetas do movel: frente, caixa (laterais, contrafrente, traseira, fundo) e trilho em BLOCAGEM real (telescopico 12,7/lado, oculto 5/lado; maior comprimento de linha que cabe); sobreposta/embutida, espacamento frontal, entre gavetas, recuo; refeitas pelo vao (margens fixas ao modulo) guardando abertura, puxador e material | `calcular`, `criar_gavetas`, `montar`, `editar`, `atualizar_gavetas_do_conjunto` | gavetas |
| Gavetas: assistente (2 cliques na diagonal, scroll = quantas, mouse = profundidade com Alt, trilho), aba Gavetas (campos, contador, trilho, puxador de uma ou de todas), selecao como a porta (so' elas na HUD, L/A/P editaveis), slider na frente e 3 pontos com Alt | `cabinet_criar_gavetas`, `_aba_gavetas_gaveta`, `selecionar`, `linhas_hud`, `cabinet_abrir_gaveta`, `VIEW3D_GGT_slider_gaveta`, `cabinet_arrastar_ponto_gaveta` | gavetas, gui |
| Prateleiras internas: grupo num vao do modulo (margens fixas, segue o modulo), espessura, recuo, folga lateral; espacamento IGUAL ou LIVRE (vao abaixo de cada uma, o de cima sobra); mudar um vao anda so' uma prateleira; "entre" igual para todas; refeitas nas mesmas chapas; desfaz o que nao cabe; orcamento conta; profundidade para no fundo | `calcular`, `vaos`, `mover_vao`, `criar_prateleiras`, `montar`, `editar`, `atualizar_do_conjunto`, `profundidade_ate_o_fundo`, `quantas_no_modulo` | prateleiras |
| Prateleiras: assistente das gavetas (`AssistenteDoVao`) com so' 2 cliques + scroll (profundidade ate' o fundo, folga da frente = Recuo), aba Prateleiras (contador, Chapa, Igual/Livre, Entre, Vao 1..n+1; uma = Abaixo/Acima), selecao clique = todas / duplo = uma, HUD com L/A/P e o valor de cada vao (arrastar/digitar; Esc devolve) | `cabinet_criar_prateleiras`, `_aba_prateleiras_gaveta`, `selecionar`, `linhas_hud`, `aplicar`, `copia`/`restaurar` | prateleiras, gui |
| Biblioteca SEM limite de niveis: `niveis` no indice (n1/n2/n3 = os 3 primeiros), catalogo do caminho inteiro, um carrossel por nivel, sem contagem, ramo vazio some; Promob em Armarios > Ambiente > Aba > Categoria | `caminho_de`, `filhos_de`, `itens_em`, `trilha_da_cena`, `registrar_no_indice`, `cabinet_navegar`, `chapa_n_mais` | biblioteca |
| Ponta da diagonal AFIADA (vai ate' a quina; modulo triangular) ou na ESPESSURA de uma chapa (para onde a peca para; o trecho da espessura e' so' contorno e o arco mede com o lado seguinte) | `PONTA_AFIADA_MM`, `ESPESSURA_PONTA_MM`, `_arcos_da_diagonal`, `_mm_por_pixel` (arco pequeno: raio fixo na tela, <= 1/4 do lado) | formas |
| Diagonal do LADO INTEIRO vira chanfro; arco do ANGULO nas duas pontas da diagonal (graus de dentro da planta, editavel) | `_feicao`, `_arcos_da_diagonal`, `_angulo_da_ponta`, `_eh_angulo`, `aplicar(('ANG', k))` | formas |
| Forma de planta (canto em L, diagonal, curvo): a linha branca da HUD segue a planta; P1/P2 mudam a profundidade de CADA braco; R da diagonal (porta gira e estica) e da curva (anda na radial, porta curva mantem a espessura); L/P totais esticam sem deformar o canto; clicar digita | `forma_do_modulo`, `segmentos`, `aplicar`, `_linhas_da_forma`, `_mover_perna`, `_esticar_total`, `_mudar_raio` | formas |
| Fundo do modulo: 5 mm em canal a 15 mm da borda de tras (entra 7 mm); acompanha L/A/P/E, fora da adjacencia; F3 Fundo do Modulo (recuo, espessura, remover) | `ajustar_fundo`, `adicionar_fundo`, `cabinet_fundo_modulo`, `MARCA_FUNDO` | armarios |
| Armarios nativos na biblioteca (39: balcoes, aereos de giro e basculantes, torres, roupeiros, gabinetes) COM PORTA Reta (1 folha ate' 500 mm, 2 acima) e PERFIL (balcao/gabinete em cima, aereo embaixo, torre/roupeiro na vertical do lado da abertura); foto sem janela, porta entreaberta; puxador padrao da ferramenta = Perfil | `criar_armario`, `porta_no_modulo`, `perfis_na_porta`, `PERFIL_POR_TIPO`, `ARMARIOS_NATIVOS`, `gerar_armario_nativo`, `fotografar_com_camera`, `gerar_armarios_nativos.py` | armarios, biblioteca |
| Duplo clique = so' a folha, com o contorno BRANCO dela (o nativo fica desligado); clique no trilho do correr = arame, como as dobradicas | `_folhas_com_contorno`, `TIPOS_SELECAO_FERRAGEM` | gui |
| Porta selecionada: folhas (branco), vao (amarelo) e fios dos 4 cantos (sem as dobradicas); Alt arrasta um canto e refaz a porta | `_desenho_da_porta`, `_cantos_da_porta`, `cabinet_arrastar_canto_porta`, `cabinet_cantos_porta` | portas, gui |
| Dobradica Reta = modelo + rig do usuario (asset de `extrair_dobradica.py`): uma copia por dobradica (driver + IK dele, malha dividida), Boolean do copo na folha (furo medido no copo), a folha segue a tabela medida no rig e o controlador gira a copia junto; folga minima do modelo ate' o modulo; sem o asset, caixas e eixo fixo | `_instanciar_rig`, `_passo_rig`, `_movimento_rig`, `_furar_folhas`, `_girar_rigs`, `_afastamento_porta` | portas |
| Placa base e suporte da Reta na face interna da lateral (o "parafuso de cobertura": so' eles andam, copo e porta ficam), na peca e na previa | `_calco_rig`, `FACE_PECAS_CALCO`, `MALHAS_CALCO` | portas |
| Ferragens de verdade (Fase 3): dobradica = corpo no modulo + caneco na folha; pistoes com mira (Damped Track), corpo/haste no diametro real e suportes; trilho do correr; o Blender nao as seleciona; conferidas ao apagar/duplicar | `_ferragens_da_porta`, `_montar_ferragens`, `_conferir_ferragens` | portas, hud |
| Ferragens selecionadas: duplo clique = a peca (selecao nativa, Tab edita); clique = todas do tipo no modulo, Shift soma o outro, so' elas acesas (arame); Alt = controlador (dobradica na borda = margem espelhada; pistao na lateral, trava no curso) | `_selecionar_ferragem`, `_selecionar_peca`, `_ferragens_em_edicao`, `_caixas_ferragens`, `_controles_ferragens`, `_valor_do_controle`, `cabinet_arrastar_ferragem` | portas |
| Abertura por folha (giro na quina das costas da borda da dobradica -- da frente na embutida --, basculante, correr; aberta sem vao ate' o modulo) que sobrevive a redimensionar; slider na base da folha (direita abre, Ctrl+Z desfaz) | `_matriz_abertura`, `_definir_abertura`, `cabinet_abrir_porta` | portas, gui |
| Puxador PERFIL = modelo de aluminio do usuario (asset de `extrair_puxador.py`): pontas e costas andam inteiras (chanfro nunca deforma; so' o trecho reto acomoda), material e UV dele, malha do modelo carregada uma vez | `_dados_perfil`, `_malha_modelo_perfil`, `_malha_perfil_do_modelo`, `_corte_do_perfil`, `_deformar_perfil`, `_altura_perfil_mm` | puxadores, snapshot |
| Nomes de objeto em portugues e sem sublinhado (folhas, puxadores, ferragens, rig); copia de rig de asset antigo trocada pela atual | `_padronizar_nome`, `NOMES_FERRAGEM`, `_anexar_sem_repetir` | portas |
| Porta de correr: um trilho por folha (plano proprio, corre o vao inteiro); unica = METADE do vao; largura da folha editavel no L da gaveta (volta ao padrao ao trocar folhas/abertura; nunca passa do vao; sem campo de sobreposicao); trilhos como os de verdade: cima = U com um canal fundo por folha (folga para levantar), baixo = chapa com uma guia sob cada folha (ela fica em pe' nela); slider do curso. Sem "Folga no perimetro". Cobrindo a chapa (cliques de fora para dentro) vira COM MOLDURA (ver abaixo) | `_correr_sobreposta`, `_largura_folha_correr`, `_plano_correr`, `_curso_correr`, `_trilhos_correr`, `altura_trilho_baixo`, `_inicios_porta`, `CHAVE_LARGURA_CORRER`, `_curso_do_slider` | portas, gaveta |
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
