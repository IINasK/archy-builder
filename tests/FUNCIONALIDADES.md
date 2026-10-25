# Funcionalidades do Cabinet Creator e o teste de cada uma

Biblioteca sem portas curvas (333): os 21 presets com folha curva sairam
(376 restam; diagonais de porta reta ficam); os testes da curva legada
usam copias em tests/fixtures (biblioteca, 83; importacao, 80).

Lugar da biblioteca lembrado (331): a escolha faixa/menu vai para as
preferencias do add-on (`biblioteca_lugar`) e vale em todo arquivo; a
screen marcada de arquivo antigo vira a preferencia uma vez; o botao troca
o que esta' aberto (biblioteca_faixa, 31). Padrao (332): 'MENU', na
lateral esquerda (pedido do usuario).

Botao "Assets" descontinuado (330): saiu da faixa, do menu e do painel
legado, com o operador `object.cabinet_prateleira`; a AssetShelf continua
no menu Ver do Blender (biblioteca_faixa, 30).

Costas na parede = lado OPOSTO a' porta (324): a frente sai da posicao das
folhas/frentes de gaveta, gravada em `parede_costas` ao associar; a roda do
mouse no arraste (direito ou da biblioteca) troca a face de 90 em 90; no
giro de 90 a largura na parede e' a profundidade do modulo (paredes, 15);
o indice grava `costas` na caixa do preset e registro sem ela mede de novo
(paredes_edicao, 66).

Cena real pesada (321): regiao da parede em lote e uma vez por parede
(paredes, 13); arraste da biblioteca so' wireframe pela `caixa` do indice,
"Carregando..." e o .blend so' ao soltar; sem caixa, o 1o arraste a grava;
.blend alterado invalida (paredes_edicao, 65).

Preset solto numa parede fora da edicao 2D (318): costas na parede, cursor
no centro do modulo, pontas/piso/teto grudam, sem sobrepor vizinho, e
associa; fora da parede volta a' rotacao do preset (paredes_edicao, 63).

Biblioteca no menu sem fila de botoes (316): Inserir/Editar/Bloquear so' no
clique direito, como na faixa; grade com vao de 8 px (gaveta, 67).

Cotas Promob e biblioteca no menu (315): Superior/Anterior/Afastamento/
Posterior/Inferior em cruz no menu e na viewport; afastamento resiste ao
timer/G (paredes_composicao, 49). Biblioteca na faixa OU dentro do menu
(`cabinet_lugar_biblioteca`, troca no timer; biblioteca_faixa, 29); no menu
cada nivel e' lista suspensa flutuante (estrutura, 51: lista, colunas,
hover por linha, materiais, escolha). Carrossel do menu removido.

Encaixe e cotas em parede (301): sete regressoes novas em paredes_edicao
(62 testes) para colisao, parede cheia/rollback, limites nas quinas, preset
girado/previa/mira/confirmacao, arraste direito e altura/face oposta.
Composicao (36 testes) cobre tema claro/escuro, halo, setas e desenho do
numero depois da linha. `faixas_livres` e' comum aos posicionadores,
distribuicao e edicao; nenhuma geometria e' encolhida para caber.
Validacao 301 (2026-10-22): 322 testes dirigidos aprovados em 4.2/5.2.
Harness completo: 2003 testes contabilizados, 46/48 execucoes aprovadas;
persistem a bancada curva 5.2 e o limite de 300 s da biblioteca nas previews.
Log: `D:/Blender/Backups/CabinetCreator/paredes301-completo.log`.
Auditoria na cena 5.2: cotas legiveis sobre parede branca/grade escura;
previa na quina inferior direita terminou exatamente nos limites e a mira
coincidiu com seu centro. Alvo sobre movel foi para vao livre adjacente.
Os 347 objetos conservaram matrizes e vertices; selecao/vista restauradas.
Backup: `D:/Blender/Backups/CabinetCreator/antes-paredes301.blend`.

Cadastro automatico do orcamento (300): medidas da geometria avaliada nos
eixos do modulo, quantidades reais de folhas/gavetas, tipos de dobradica e
materiais usados nas faces. Sem contagens persistentes nem mudanca no 3D;
porta aberta nao aumenta dimensoes. Material ausente/parcial e dobradica
nao identificada geram pendencias. Slots sem faces e ferragens ficam fora.
`test_orcamento_blender.py`: 16 testes, seis novos para medidas/edicoes,
rotacao e leitura sem alteracoes, exclusao, dobradicas e materiais mistos.
Validacao 300 (2026-10-21): 174 testes dirigidos aprovados em 4.2/5.2.
Harness completo: 1985 testes contabilizados, 46/48 execucoes aprovadas;
bancada curva 5.2 continua falhando e biblioteca 5.2 excedeu 300 segundos.
Registro: `D:/Blender/Backups/CabinetCreator/orcamento300-completo.log`.
A repeticao isolada da biblioteca 5.2 aprovou a refiliacao, mas tambem
excedeu 300 segundos, agora na regeneracao de previews. Sem reduzir o piso
ou aumentar o limite: `D:/Blender/Backups/CabinetCreator/orcamento300-biblioteca.log`.

Leitura frontal da parede (299): clique em porta seleciona modulo; duplo
isola folha. Shift e PRESS/CLICK conservam selecao multipla; fora do modo,
porta continua selecionando seu grupo. Interior usa quinas reais da malha
avaliada, desenhadas cinza com alfa apenas quando ocultas, sem editar a Mesh.
Cache invalida por geometria/pose e e' descartado ao sair/undo; redraw nao
extrai geometria. Cotas junto a' peca, sem usar o fim de toda a composicao.
`test_paredes_composicao_blender.py`: 34 testes, seis novos para estes casos.
Validacao 299 (2026-10-21): 1054 testes dirigidos passaram nas duas versoes;
auditoria na cena 5.2 confirmou modulo/folha e cinza interno, mantendo os 157
objetos e sua geometria. Ultimo harness: 2054 testes, unica falha nessa execucao
na bancada curva 5.2. Uma execucao anterior acusou tambem redo de lote no 4.2:
os dois modulos existem, mas a segunda Collection pode voltar sem vinculo
com a cena. Reproduzido em 2/24 execucoes inclusive DESATIVANDO o interior;
permanece pendente, sem ignorar teste ou enfraquecer suas assercoes. Logs em
`D:/Blender/Backups/CabinetCreator/299-repeticao-*.log` e `299-sem-interior-*.log`.

Insercao e saida da parede (298): orbita devolve PERSP preservando o gesto;
parede e modulos solidos com contornos pretos, estado visual restaurado.
Biblioteca arrastada/clique e arraste direito conservam malha/dimensoes no
ponto de soltura. Duplo clique segue o ultimo a' direita; se exceder, centra
na parede; ordem persiste entre sessoes. Staging oculto usa limites anteriores
e sincroniza filhos ao confirmar. `test_paredes_edicao_blender.py`: 55 testes,
inclusive arraste com RELEASE final, multiplos movimentos em parede girada,
duplo clique do posicionador, cancelamento/limpeza, arestas nativas temporarias
com restauracao/undo e modelo que nao cabe. Auditoria visual em cena temporaria
na janela 5.2 com tres presets reais 600x1356x550, sem alterar a cena original.
Validacao 298 (2026-10-21): 2042 testes em 48 execucoes, 2041 passaram.
Permanece somente a falha preexistente de importacao da bancada curva no 5.2
descrita abaixo; sem alteracao da tolerancia ou do teste.

Composicao de paredes (297): cotas de largura/altura e vaos E1/E2 clicaveis,
campos locais no menu, larguras Livre/Fixa e redistribuicao explicita no
vao, separando linhas superiores. G/adicionar/excluir recalculam vaos sem
mover vizinhos. Troca de modelo preserva tamanho/posicao/associacao e so'
remove o original apos validar o substituto. Parede sem medidas no menu;
visual solido/OBJECT/FLAT com parede em contorno e restauracao apos sair,
undo e redo. Observador passivo nao bloqueia sincronizacao nativa.
`test_paredes_composicao_blender.py`: 28 testes, inclusive parede girada,
espessura/Mesh, encaixes invalidos, rollback, troca/Esc e undo/redo.

Validacao 297 (2026-10-20): suites dirigidas em Blender 4.2/5.2 e auditoria
visual na janela 5.2, em cena descartavel; cena original preservada.
Harness completo: 2006 testes em 48 execucoes, 2005 passaram; unica falha preexistente em 5.2,
`importacao::test_curva_bancada_encaixa_sem_apagar_modelagem_e_abre_fora_do_corpo`
(desvio 0.000677527 m, tolerancia 0.00005 m). Nao houve alteracao do teste.

Edicao 2D de paredes (296): grupo contextual Paredes e menu direito
Cabinet Creator, face clicada ou maior face voltada para a vista, Local
View nativo e restauracao do isolamento/ocultacao anterior. Orbita/Walk/Fly
saem; pan/zoom ficam. Modelo da biblioteca, quantidade/folgas/espacamento,
previa no vao, contorno real com aberturas, obstaculos por altura/face e
retornos por BVH/raycast. Confirmacao independente com E preservada e
rollback isolado; undo/redo/salvar/apagar parede encerram a sessao.
`test_paredes_edicao_blender.py`: 37 testes em 4.2/5.2; desenho/gesto sem solver.

Organizacao por setores (284): seis pacotes homonimos com imports publicos preservados, recarga mantendo objetos/malhas e aliases entre dominios. `test_organizacao_blender.py` verifica identidade/recarga; `TestPacote` enumera arquivos e pacotes sem aceitar fontes homonimas concorrentes. Mapa em ARQUITETURA.md e guias AGENTS.md/CLAUDE.md por setor.

Divisorias (282): aba propria e `OBJECT_OT_criar_divisorias` reutilizam AssistenteDoVao/snap nativos. Particao valida os vaos antes de mutar, desconta E e produz gavetas/prateleiras independentes, inclusive apos criar a divisoria; apoios por UID acompanham espacamentos e resize. BMesh conserva Mesh/material/E/altura/recortes de prateleiras. Clique simples seleciona o grupo e exibe cotas do vao e distancias laterais editaveis; duplo isola a chapa, Tab conserva escopo nativo. `test_divisorias_blender.py`: exemplo 3->6/maleiro, multiplas, prateleiras parcialmente atingidas, outro modulo/giro, parametros/abertura/puxadores, vao invalido, campos/limites, clique/HUD/hit-test, restaurar/Esc com dependentes e undo/redo.

Limpeza de embalagens de assets legados (280): tag nativa `chapa-g3` identifica a Collection do preset mesmo sem a marca da montagem, renomeada e com fake user. Delete limpa pastas aninhadas de dentro para fora; objetos/pastas comuns e assets de terceiros permanecem. Arquivo da biblioteca intocado; undo/redo preservam asset/tag/fake user. `test_append_delete_limpa_embalagem_asset_legada_com_fake_user`, `test_embalagem_asset_nao_vazia_e_assets_alheios_sao_preservados`, `test_embalagens_asset_aninhadas_limpam_de_dentro_para_fora`, `test_undo_redo_restaura_embalagem_asset_e_sua_identificacao` (portas).

Normalizar alturas (v235): botao na aba Gavetas para o conjunto ou uma unidade; iguala frentes, preserva vao total, folgas, materiais, abertura, trilhos, recuos, puxadores e selecao. Valida antes, cancela sem mutacao se nao couber; uma gaveta so' nao oferece botao. `test_botao_normaliza_alturas_preservando_total_folgas_e_ajustes`, `test_normalizar_que_nao_cabe_preserva_estado_e_uma_so_nao_tem_botao` (gavetas); operador `OBJECT_OT_normalizar_gavetas`.

Gavetas individuais (v234): `test_altura_individual_reencaixa_vizinha_sem_mudar_conjunto`, `test_unidade_tem_profundidade_trilho_largura_e_espacamentos_proprios`, `test_hud_segmentos_individuais_hover_e_selecao_isolada`, `test_previa_individual_nao_reconstroi_e_esc_restaura`, `test_menu_da_unidade_mostra_medidas_e_escolhas_somente_dela`, `test_edicao_preserva_madeira_abertura_e_puxador_individuais` (gavetas). Eventos reais: `test_altura_de_uma_gaveta_com_previa_esc_e_digitacao` (gui_interacao). Altura redistribui com a vizinha, total/folgas preservados; campos individuais e curso por unidade; previa sem reconstruir malhas, confirmar uma vez, Esc restaura. Uma gaveta so' edita seu vao.

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
| Mover pela quina: cursor + translate NATIVO, o Ctrl dele liga o snap de vertice (outros armarios/chapas; nunca as pecas do proprio modulo) | `_preparar_quina_nativa`, `cabinet_mover_quina_hud`, `cabinet_confirmar_quina_hud` | hud, gui |
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
| Wizard de 2 cliques (283): limites opostos da porta, vao/cobertura/dobradica automaticos, previa igual a execucao, diagonal invalida refeita e voltar conserva primeiro canto; API antiga de quatro pontos preservada | `_cliques`, `_previa`, `_concluir`, `_coberturas_dos_cantos`, `_dobradica_da_cobertura` | portas, gui |
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
| Geometria: area = volume/E e borda; F3 Calcular Areas (o detector de angulos saiu na v309) | `medidas_da_chapa`, `areas`, `cabinet_calcular_areas` | geometria |
| Gavetas do movel: frente, caixa (laterais, contrafrente, traseira, fundo) e trilho em BLOCAGEM real (telescopico 12,7/lado, oculto 5/lado; maior comprimento de linha que cabe); sobreposta/embutida, espacamento frontal, entre gavetas, recuo; edicao direta pelo vao; redimensionar o modulo move o bloco com a face mais proxima (base/topo), preservando medidas, abertura, puxador e material; filhos nao viram alvos independentes na selecao do modulo | `calcular`, `criar_gavetas`, `montar`, `editar`, `atualizar_gavetas_do_conjunto`, `acompanhar_redimensionamento` | gavetas |
| Gavetas: assistente (2 cliques na diagonal, scroll = quantas, mouse = profundidade com Alt, trilho), aba Gavetas (campos, contador, trilho, puxador de uma ou de todas), selecao como a porta (so' elas na HUD, L/A/P editaveis com quina fixa nos dois sentidos; Esc restaura parametros sem deslocar apos renomear/mover/redimensionar o modulo; pai real prevalece sobre nome antigo; selecao sobrevive as pecas refeitas), slider na frente e 3 pontos com Alt | `cabinet_criar_gavetas`, `_aba_gavetas_gaveta`, `selecionar`, `linhas_hud`, `cabinet_abrir_gaveta`, `VIEW3D_GGT_slider_gaveta`, `cabinet_arrastar_ponto_gaveta` | gavetas, gui |
| Prateleiras internas: grupo num vao do modulo (margens fixas, segue o modulo), espessura, recuo, folga lateral; espacamento IGUAL ou LIVRE (vao abaixo de cada uma, o de cima sobra); mudar um vao anda so' uma prateleira; "entre" igual para todas; refeitas nas mesmas chapas; desfaz o que nao cabe; orcamento conta; profundidade para no fundo | `calcular`, `vaos`, `mover_vao`, `criar_prateleiras`, `montar`, `editar`, `atualizar_do_conjunto`, `profundidade_ate_o_fundo`, `quantas_no_modulo` | prateleiras |
| Promob: fundos em L guardam formato/margens de cada plano (nao atravessam o canto), resize/recuo/remover; divisorias encostadas acompanham base/tampo; porta curva com placa conserva malha/flecha e ganha abertura nativa, alca tangente, reancoragem apos deformar; planos/folgas medidos, perfil nativo por categoria | `fundos_do_modulo`, `guardar_formato_fundo`, `_ajustar_fundo_por_formato`, `reencaixar_verticais`, `_portas_curvas_referenciadas`, `adotar_contorno_modelado`, `refinar_cantos_promob.py` | armarios, importacao |
| Prateleiras: assistente das gavetas (`AssistenteDoVao`) com so' 2 cliques + scroll (profundidade ate' o fundo, folga da frente = Recuo), aba Prateleiras (contador, Chapa, Igual/Livre, Entre, Vao 1..n+1; uma = Abaixo/Acima), selecao clique = todas / duplo = uma, HUD com L/A/P e o valor de cada vao (arrastar/digitar; Esc devolve) | `cabinet_criar_prateleiras`, `_aba_prateleiras_gaveta`, `selecionar`, `linhas_hud`, `aplicar`, `copia`/`restaurar` | prateleiras, gui |
| Criacao de gavetas/prateleiras: marcacao pelo snap NATIVO, sem projetar vertices avaliados em Python; segundo clique recupera o modulo do estado; confirmar/Esc/excecao restauram cursor, bloqueios, desenhos e timer; mixin modal libera referencias ao encerrar | `cabinet_marcar_ponto_vao`, `cabinet_confirmar_ponto_vao`, `_aceitar_canto`, `_terminar_snap_criacao`, `_larga_dados_ao_terminar` | gavetas, gui_interacao |
| Biblioteca SEM limite de niveis: `niveis` no indice (n1/n2/n3 = os 3 primeiros), catalogo do caminho inteiro, um carrossel por nivel, sem contagem, ramo vazio some; Promob em Armarios > Ambiente > Aba > Categoria | `caminho_de`, `filhos_de`, `itens_em`, `trilha_da_cena`, `registrar_no_indice`, `cabinet_navegar`, `chapa_n_mais` | biblioteca |
| Ponta da diagonal AFIADA (vai ate' a quina; modulo triangular) ou na ESPESSURA de uma chapa (para onde a peca para; o trecho da espessura e' so' contorno e o arco mede com o lado seguinte) | `PONTA_AFIADA_MM`, `ESPESSURA_PONTA_MM`, `_arcos_da_diagonal`, `_mm_por_pixel` (arco pequeno: raio fixo na tela, <= 1/4 do lado) | formas |
| Diagonal do LADO INTEIRO vira chanfro; arco do ANGULO nas duas pontas da diagonal (graus de dentro da planta, editavel) | `_feicao`, `_arcos_da_diagonal`, `_angulo_da_ponta`, `_eh_angulo`, `aplicar(('ANG', k))` | formas |
| Forma de planta: L e diagonal com P1/P2, R so da diagonal e angulos retos/inclinados; curvas modeladas ficam em blocagem, contorno por segmentos reais em cache, sem inferencia circular ou deformacao radial; L/A/P e Tab preservados | `forma_do_modulo`, `segmentos`, `aplicar`, `_linhas_da_forma`, `estrutura_hud`, `_mover_perna`, `_esticar_total` | formas |
| Fundo do modulo: 5 mm em canal a 15 mm da borda de tras (entra 7 mm); acompanha L/A/P/E, fora da adjacencia; F3 Fundo do Modulo (recuo, espessura, remover) | `ajustar_fundo`, `adicionar_fundo`, `cabinet_fundo_modulo`, `MARCA_FUNDO` | armarios |
| Armarios nativos na biblioteca (39: balcoes, aereos de giro e basculantes, torres, roupeiros, gabinetes) COM PORTA Reta (1 folha ate' 500 mm, 2 acima) e PERFIL (balcao/gabinete em cima, aereo embaixo, torre na horizontal perto de 1 m, roupeiro na vertical do lado da abertura); foto sem janela, porta entreaberta; puxador padrao da ferramenta = Perfil | `criar_armario`, `porta_no_modulo`, `perfis_na_porta`, `PERFIL_POR_TIPO`, `ARMARIOS_NATIVOS`, `gerar_armario_nativo`, `fotografar_com_camera`, `gerar_armarios_nativos.py` | armarios, biblioteca |
| Duplo clique = so' a folha, com o contorno BRANCO dela (o nativo fica desligado); clique no trilho do correr = arame, como as dobradicas | `_folhas_com_contorno`, `TIPOS_SELECAO_FERRAGEM` | gui |
| Porta selecionada: folhas (branco), vao (amarelo) e a diagonal dos 2 cliques (sem as dobradicas); Alt arrasta um dos 2 cliques (`CANTOS_DO_GESTO`, v309: eram 4) e refaz a porta como a criacao, pela chapa de cada clique | `_desenho_da_porta`, `_cantos_da_porta`, `cabinet_arrastar_canto_porta` (snap nativo: `cabinet_mover_canto_porta`), `cabinet_cantos_porta` | portas, gui |
| Dobradica Reta = modelo + rig do usuario (asset de `extrair_dobradica.py`): uma copia por dobradica (driver + IK dele, malha dividida), Boolean do copo na folha (furo medido no copo), a folha segue a tabela medida no rig e o controlador gira a copia junto; folga minima do modelo ate' o modulo; sem o asset, caixas e eixo fixo | `_instanciar_rig`, `_passo_rig`, `_movimento_rig`, `_furar_folhas`, `_girar_rigs`, `_afastamento_porta` | portas |
| Placa base e suporte da Reta na face interna da lateral (o "parafuso de cobertura": so' eles andam, copo e porta ficam), na peca e na previa | `_calco_rig`, `FACE_PECAS_CALCO`, `MALHAS_CALCO` | portas |
| Ferragens de verdade (Fase 3): dobradica = corpo no modulo + caneco na folha; pistoes com mira (Damped Track), corpo/haste no diametro real e suportes; trilho do correr; o Blender nao as seleciona; conferidas ao apagar/duplicar | `_ferragens_da_porta`, `_montar_ferragens`, `_conferir_ferragens` | portas, hud |
| Ferragens selecionadas: duplo clique = a peca (selecao nativa, Tab edita); clique = todas do tipo no modulo, Shift soma o outro, so' elas acesas (arame); Alt = controlador (dobradica na borda = margem espelhada; pistao na lateral, trava no curso) | `_selecionar_ferragem`, `_selecionar_peca`, `_ferragens_em_edicao`, `_caixas_ferragens`, `_controles_ferragens`, `_valor_do_controle`, `cabinet_arrastar_ferragem` | portas |
| Abertura por folha (giro na quina das costas da borda da dobradica -- da frente na embutida --, basculante, correr; aberta sem vao ate' o modulo) que sobrevive a redimensionar; slider na base da folha (direita abre, Ctrl+Z desfaz) | `_matriz_abertura`, `_definir_abertura`, `cabinet_abrir_porta` | portas, gui |
| Puxador PERFIL = modelo de aluminio do usuario (asset de `extrair_puxador.py`): pontas e costas andam inteiras (chanfro nunca deforma; so' o trecho reto acomoda), material e UV dele, malha do modelo carregada uma vez | `_dados_perfil`, `_malha_modelo_perfil`, `_malha_perfil_do_modelo`, `_corte_do_perfil`, `_deformar_perfil`, `_altura_perfil_mm` | puxadores, snapshot |
| Nomes de objeto em portugues e sem sublinhado (folhas, puxadores, ferragens, rig); copia de rig de asset antigo trocada pela atual | `_padronizar_nome`, `NOMES_FERRAGEM`, `_anexar_sem_repetir` | portas |
| Porta de correr: um trilho por folha (plano proprio, corre o vao inteiro); unica = METADE do vao; largura da folha editavel no L da gaveta (volta ao padrao ao trocar folhas/abertura; nunca passa do vao; sem campo de sobreposicao); trilhos como os de verdade: cima = U com um canal fundo por folha (folga para levantar), baixo = chapa com uma guia sob cada folha (ela fica em pe' nela); slider do curso. Sem "Folga no perimetro". Cobrindo a chapa (cliques de fora para dentro) vira COM MOLDURA (ver abaixo) | `_correr_sobreposta`, `_largura_folha_correr`, `_plano_correr`, `_curso_correr`, `_trilhos_correr`, `altura_trilho_baixo`, `_inicios_porta`, `CHAVE_LARGURA_CORRER`, `_curso_do_slider` | portas, gaveta |
| Folha nunca rente a' borda: toda cobertura padrao (reta, meia, embutida, correr) deixa 2 mm de respiro | `_cobertura_mm`, `RESPIRO_PORTA_MM` | portas, snapshot |
| Snap nativo no meio da espessura (EDGE_MIDPOINT) = porta cobre meia chapa menos 2 mm de respiro (e acompanha o modulo) | `_iniciar_snap_nativo`, `_meias_do_vao`, `_inicios_porta` | portas |
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
| Perfil na folha curva antiga (305): borda X reta pela linha da frente (borda inteira) ou pelo raio 1 mm dentro da ponta; biblioteca toda em PERFIL por `padronizar_puxador_perfil.py` (alca vira perfil na mesma borda; porta sem puxador pela regra da importacao, curva na lateral; gaveta NENHUM vira perfil) | `test_perfil_na_borda_reta_da_folha_curva_senta_na_madeira`, `test_perfil_na_folha_curva_sem_linha_senta_na_madeira`, `_lugar_do_puxador` | importacao |
| Porta curva com frente invertida (307): "Definir como Frente" vira a modelada sem mexer na madeira (lado/coberturas trocam, abre para fora); puxador curvo acha a ponta pelos vertices dela; biblioteca por `corrigir_portas_curvas_invertidas.py` (dobradica por dentro na face real, chapa de apoio 15 mm na altura da porta onde a ponta segue a lateral) | `_virar_porta_modelada`, `test_virar_frente_da_porta_curva_nao_mexe_na_madeira`, `posicionar_puxador` | importacao |
| Perfil SEMPRE horizontal salvo guarda-roupa (308): `posicao_do_perfil` (Altos/Torres = ALTURA: borda de cima ou de baixo mais perto de 1 m, por folha; Quartos > Armarios = LADO); porta solta usa a altura dela como cima; biblioteca refeita por `padronizar_puxador_perfil.py` (folha curva ganha referencia de frentes) | `perfis_na_porta`, `ALTURA_MAO_MM`, `test_perfil_sempre_horizontal_salvo_guarda_roupa` | armarios, puxadores |
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

| Desempenho dos arrastes com Alt (gavetas, canto da porta, ancora da solda) e do wizard de porta: cursor + snap NATIVO, nenhum vertice lido ou projetado em Python; proprias pecas fora do snap | `iniciar_cursor_nativo`, `acompanhar_cursor_nativo`, `_iniciar_snap_nativo` | gavetas, portas, hud, gui |

| Ancora Alt das gavetas usa translate NATIVO do cursor, exclui proprias pecas/ferragens temporariamente; confirmar/Esc restaura cursor/overlay/alvos; undo/redo unico | `OBJECT_OT_mover_ancora_gaveta`, `OBJECT_OT_confirmar_ancora_gaveta` | gavetas, gui_interacao |

| Clique no puxador de gaveta isola o acessorio e abre Puxadores; Shift soma; trilhos selecionam gavetas; modelo e ajustes individuais sobrevivem ao redimensionar | `_selecionar_puxador`, `_trocar_modelo_puxador`, `montar` | gavetas, gui_interacao |

| Faixa de biblioteca acima de menu e viewport; categorias/miniaturas horizontais, recolher/expandir, areas reconectadas e migracao legada, alvo do preset, tooltip, cache limitado e indice reutilizado | `biblioteca_faixa`, `OBJECT_OT_recolher_biblioteca` | biblioteca_faixa, gui_biblioteca_faixa, gui_interacao |
| Categorias compactas de 18 px; modulos sem botoes inferiores; direito na foto/nome abre menu no soltar, Inserir/Editar/Bloquear, protecao reconferida e modelos usam o criador | `abrir_menu_item`, `OBJECT_OT_acao_item_biblioteca` | biblioteca_faixa, gui_biblioteca_faixa |
| Setas de categorias/fotos apenas com overflow e no sentido dos itens ocultos; resize recupera a largura e revela todos, mesmo com offset antigo | `biblioteca_faixa._linha`, `biblioteca_faixa.widgets` | biblioteca_faixa, gui_biblioteca_faixa |
| Borda da faixa arrastada para cima: abaixo de 160 px, subcategorias lado a lado, espaco/divisor por nivel, rolagem independente por X/Y e fotos acessiveis | `_subcategorias_em_linha`, `biblioteca_faixa.widgets` | biblioteca_faixa, gui_biblioteca_faixa |
| Encaixe Promob: base/tampo com recuo de ate' 3,1 mm vai ate' a quina externa; preserva E, malha modelada, UID, vao interno maior e sistemas; idempotente e modulo girado | `promob.ajustar_encaixes`, `importar_dxf_promob` | importacao |
| Portas Promob por face real (L/diagonal/perpendicular): placa/braco = uma dobradica; alturas assimetricas por folha; dupla articula fora; lado curto perto do topo nao vira basculante; junta sem apoio/ciclo usa lateral externa; referencias resistem a resize/reordenacao de vertices e cedem a edicao manual; folha articulada acompanha apoio com placa nativa em contato e ferragens separadas por grupo | `_referencias_dobradicas`, `_portas_referenciadas`, `gravar_vao_orientado`, `_vao_orientado`, `_gravar_assinaturas_vao`, `_dobradicas_da_porta`, `vincular_folha_de_apoio`, `_matriz_fechada`, `_ferragens_portas` | importacao |
# Portas Zig-zag (v231)

- Vao/orientacao (v239): `test_assistente_deduz_frente_lateral_e_a_preserva_ao_editar`, `test_assistente_deduz_face_oposta_e_modulo_girado`, `test_assistente_gap_usa_frente_interna_e_profundidade_mais_curta`, `test_assistente_frente_diagonal_nao_usa_caixa_inflada_do_modulo`, `test_assistente_previa_nao_reconsulta_malhas_nem_raios`, `test_ancora_de_profundidade_lateral_projeta_so_no_eixo_e_para_no_fundo`, `test_translate_nativo_usa_eixo_real_da_ancora_girada` (gavetas); `test_prateleiras_do_assistente_conservam_referencia_da_face_lateral` (prateleiras). Ray cast e caixa capturados ao definir vao; recuo desigual considera frente mais interna, snap de profundidade nao muda L/A/orientacao. Matriz do translate nativo transposta.

- Abertura real esquerda (v238): `test_padrao_esquerdo_preserva_alturas_material_uid_e_puxador`, `test_padrao_esquerdo_nao_cria_dobradica_sem_lateral_de_apoio` (portas), `test_promob_cadeia_da_direita_inverte_apoio_para_esquerda` (importacao). Todas as placas com apoio real; alturas/materiais/folhas preservados; cadeias coplanares invertidas, articulacoes de canto conservadas. Migracao com backup/releitura: `ajustar_abertura_esquerda.py`.

- Miniaturas (v237): `test_foto_da_porta_direita_abre_copia_a_esquerda_e_preset_fica_original` (portas); `test_contorno_da_foto_ignora_diagonais_de_triangulacao`, `test_foto_com_linhas_restaura_cor_render_e_nao_deixa_objetos` (armarios). `atualizar_fotos_biblioteca.py` prepara PNG/preview com releitura da montagem original e backup antes de publicar.

- Fundos/ilhas (v236): `test_promob_recuo_preserva_fundo_girado_espessura_material_e_uid`, `test_promob_fundo_parcial_recuado_nao_vira_fundo_da_torre`, `test_promob_fundo_recuado_reencaixa_prateleiras_e_trilhos` (armarios); `test_promob_ilha_duas_frentes_fica_com_porta_e_fundo_nativos`, `test_promob_frentes_perpendiculares_de_canto_sao_preservadas`, `test_promob_fundo_rente_na_fonte_importa_recuado_sem_atravessar_prateleira` (importacao). Migracao/releitura com backup: `ajustar_fundos_portas_promob.py`.

- `test_zigzag_espelha_a_cadeia_e_mantem_eixos_coincidentes`: 3, 4 e 8 folhas, esquerda/direita, juntas coaxiais nas poses fechada/meia/aberta.
- `test_zigzag_puxador_ultima_folha_abertura_e_edicao`: criar, abrir e mudar quantidade/lado preserva o puxador terminal e o slider unico.
- `test_zigzag_volumes_presos_as_duas_folhas`: rig do usuario na carcaca, volumetria nativa nas juntas e malhas preservadas ao abrir.
- `test_assistente_oferece_zigzag_tres_folhas`: escolha na criacao.
- `test_foto_de_canto_abre_uma_inteira_e_a_outra_metade`: pose da miniatura.
- Encaixe obliquo (v232): `test_dobradica_de_135_encosta_com_a_face_inteira_sem_penetrar`, `test_braco_angular_segue_o_copo_sem_refazer_malhas`, `test_prisma_angular_e_arame_preservam_o_plano_real`, `test_atualiza_preset_antigo_sem_alterar_porta_puxador_ou_abertura` (portas).
- Integracao (v233): `test_promob_gavetas_na_face_lateral_tem_selecao_abertura_e_edicao`, `test_promob_lateral_inteira_nao_vira_gaveta_e_metais_so_referenciam`, `test_promob_frente_alta_estreita_com_caixas_em_dois_niveis`, `test_promob_prateleiras_adotam_uid_material_forma_e_funcoes`, `test_promob_prateleira_recortada_preserva_malha_material_e_edicao` (importacao); `test_sistemas_em_montagem_antiga_sobrevivem_a_reinsercao` (gavetas). Audita presets com `auditar_integracao_promob.py`: esperado/antes/depois, selecao, sliders, abertura, editar/restaurar; preserva geometria mundial, UID, materiais e catalogos antes de publicar com backup.

| Redimensionamento reversivel (242): 550 -> 100 -> 550; referencia nativa/topologia; gavetas e vaos livres reencaixam; limites dos trilhos, Esc, giro, append e HUD sem trabalho duplicado | `test_formas_blender.py`, `test_gavetas_blender.py`, `test_prateleiras_blender.py`, `test_operadores_blender.py`, `test_biblioteca_blender.py`, `test_hud_blender.py` |

| Cantos (243): porta acompanha vao interno sem ancora/envelope; gaveta segue largura e giro da frente, Esc devolve referencia; fotos fecham giro/correr/basculante/zigzag sem trocar lado | `test_formas_blender.py`, `test_portas_blender.py` |

| Canto cego (244): conserva ripa 40x15/arremate 49,9998 mm, usa dobradica de movel sem articulacao de painel fixo e deixa folga de 2 mm; abrir/fechar reversivel | `test_canto_cego_preserva_ripas_e_arremate_com_dobradica_de_movel` (importacao) |

| Porta parcial (245): ripa/lateral por face interpolada nativa; reduz/retorna largura, referencia no meio da face, canto L em etapas; copo do rig Reta dentro da folha | `test_porta_parcial_segue_ripa_e_lateral_ao_reduzir_largura`, `test_ancora_da_porta_no_meio_da_face_usa_interpolacao_nativa`, `test_dobradica_reta_real_na_porta_parcial_cabe_na_folha`, `test_canto_real_reduz_largura_em_etapas_sem_perder_referencia` (importacao) |

| Bibliotecas e selecao (246): contato por BVH sem unir no vazio do L; destinos por ambiente; portas avulsas; puxador perpendicular na frente; Tab do grupo em Edit Mode nativo com malhas unicas | importacao, puxadores, operadores (`cabinet_editar_grupo`) |
| Prateleiras (247): Tab global propaga na MESMA Mesh e isola outros modulos; Tab individual conserva vizinhas; undo/redo recuperam escopo nativo; parametros por unidade; quantidade herda geometria/parametros/material/modificadores, reparte vaos pela espessura real; tipos diferentes sem selecao pedem referencia na viewport, clique valida grupo e Esc cancela; arraste exibe numero sem montar, Esc preserva; profundidade individual reduz/retorna com o modulo | `iniciar_edicao`, `concluir_edicao`, `editar_individual`, `cabinet_referencia_prateleira`, `resolver_referencia` | prateleiras |

| Aviso de referencia (248): acompanha o mouse na viewport ativa, converte coordenadas da janela, muda de viewport e some no menu/fora da regiao; usa o recado do assistente com limite nas bordas | `atualizar_aviso_referencia`, `_desenhar_assistente_2d` | prateleiras |

| Espelhar porta (249): grupo ou folha; giro/dupla, zigzag com madeira fechada no mesmo lugar e puxador terminal, basculante com pistoes e correr com curso invertido; duas vezes restaura; icone no menu esquerdo e contexto; referencias por folha sobrevivem a editar E/redimensionar | `cabinet_espelhar_porta`, `espelhar_porta`, `menu_contexto_porta` | portas |
| Conexoes (249): suporte por area positiva nos modulos; pontas limpas tambem apagam UID; migracao preserva ancoras manuais e geometria; controles de juntas proximas agrupados sem apagar vinculos; ripa vertical com recuo de exportacao chega as quinas, divisorias internas preservadas | `otimizar_adjacencia`, `_correntes_sem_repeticao`, `alinhar_arremates`, `refinar_biblioteca249.py` | hud, armarios |
| Diagonal e Tab (250): linha/arcos/edicao do angulo pela aresta real da chapa deitada, com espessura nas duas pontas; Tab conserva Empties no Edit Mode nativo, restaura selecao/ativo ao sair e invalida planta; seletor nativo de modo, varios grupos, selecao posterior e undo/redo preservados | `pontas_diagonal`, `angulo_diagonal`, `concluir_edicao_grupo`, `recuperar_edicao_grupo` | formas, operadores |

| Diagonais (251): perfil segue tampo real; normal externa, lado com apoio e base em contato; frentes sem placa reconhecida viram portas; puxador/Alt seguem cada segmento; resize preserva vertices/faces editados, centro fechado e abertura | `alinhar_frente_ao_corpo`, `integrar_frentes_diagonais`, `_reancorar_perfil_modelado`, `_bordas_da_face`, `_lugar_no_perfil`, `refinar_diagonais251.py` | importacao, formas, portas, puxadores |
| Diagonais (252): contorno acompanha perfil e abertura sem corda; previa Y+ segmentada coincide com puxador criado; extremidades das duas faces liberam laterais/tampos reais; regressao no Sup Alto 02 e auditoria BVH dos 32 presets | `_contorno_da_folha`, `_limitar_pontas_frente`, `_lugar_do_puxador`, `refinar_diagonais252.py` | importacao |
| Frentes (253): referencia comum FACE/EDGE local, curvas/facetas/quadros, normal real, topologia/recortes; cache sem varredura no redraw/hover, invalidacao Mesh/undo/renomeacao; madeira versus borda de montagem; migracao unica e pintura OBJECT preservada; PERFIL acompanha borda; preparo precede captura/deformacao inclusive append nativo com porta aberta | `frentes.py`, `FRONTES.md`, `test_frentes_blender.py`, `test_diagonal_quarto_append_sem_cache_resize_preserva_apoios_e_geometria`, `test_previa_em_movimento_reutiliza_geometria_preparada`, `test_material_do_objeto_sobrevive_migracao_e_redimensionamento` | frentes, portas, puxadores, importacao |

| Contorno do modulo (254): HUD usa a geometria real de cada folha, sem caixa agregada em frentes curvas/facetadas; desenho e porta isolada compartilham referencia | `hud.py`, `test_hud_blender.py` | hud |

| Forma/angulo (255): angulo interno pelas duas arestas nativas, extremos ortogonais, ida/volta; fundo dependente segue apoio e recuo normal; Tab reorienta chapa plana sem mudar mundo/UV/material/filhos nem arredondar E | `formas.py`, `chapas/`, `hud.py`, `test_formas_blender.py` | formas, hud, operadores, importacao |

| Inclinacao vertical (256): solver comum XY/XZ/YZ, angulos reais e comprimento da diagonal, fundo/E/UV/material preservados; ida/volta com modulo girado, Tab invalida cache, Esc restaura; edicao individual isola Mesh compartilhada; cotas recortadas pelo perfil e referencia nativa sobrevive a append com nomes duplicados | `test_formas_blender.py` | formas, hud |

| Contorno livre (257): grupo/Tab/G/Tab nativo com canto obliquo e ripas; uniao CDT preserva concavidades, ilhas, furos e sobreposicao; linhas sobre a madeira com grupo girado, sem Mesh/BMesh/CDT no redraw; preserva Mesh/UV/material e permite medidas, seta, arraste e Esc | `test_formas_blender.py` | formas, hud, operadores |
| Perfis reais (259): inclinacoes compostas e prateleiras desencontradas nao inventam curva/diagonal; blocagem arredondada com base elevada usa segmentos nativos em cache e conserva IDs/poses | `test_inclinacao_composta_nao_inventa_curva_nem_diagonal_sem_apoio`, `test_curva_com_base_elevada_usa_arestas_nativas_sem_arco_aproximado` | formas, hud |
| Contorno/resize (259): perfil arredondado nao inventa diagonal entre as pontas; elimina diagonais coplanares com normais invertidas; perder o perfil no limite conserva o canal/referencia XY ao voltar pelo campo de medida | `test_perfil_arredondado_nao_inventa_diagonal_entre_pontas`, `test_contorno_ignora_diagonais_coplanares_com_normais_invertidas`, `test_resize_pelo_campo_recupera_referencia_se_perfil_some_no_limite` | formas, modulos, hud |
| Frente curva torcida (258): tessellacao nativa evita ray cast na propria face; migracao recupera rotulos/cache truncados; reancoragem aberta preserva Mesh/topologia/UV/material/modificador e canecos atras da madeira | `test_curva_torcida_reconhece_superficies_inteiras`, `test_curva_recupera_cache_antigo_truncado_sem_recriar_mesh`, `test_reancorar_curva_torcida_aberta_preserva_madeira_e_dados` | frentes, portas |
| Escopo do perfil (259): chanfros validam todas as chapas e cantos independentes | `test_perfil_reto_valida_todos_os_cantos_da_caixa` | formas |
| Sem sistema de curvatura (259): curvas existentes sao blocagem com arestas retas, sem inferencia circular ou deformacao radial; comando R legado nao modifica a geometria, menu sem raio, L/A/P e Tab mantidos | `test_contorno_curvo_modelado_nao_cria_parametro_radial`, `test_comando_radial_antigo_nao_deforma_blocagem`, `test_rotulos_da_forma_aparecem` | formas, hud |

| Blocagem e junta (260): grupo usa 8 cantos de duas laterais e 12 cotas principais, frente curva usa envolvente retangular desde 262; sem facetas/folhas/prateleiras internas; laterais assimetricas oferecem angulo na quina INTERNA. Rotacao 3D, planos XZ/YZ, laterais inclinadas, ida/volta, E real/UV/mesmo ID Mesh/cortes no apoio e cache sem Mesh/CDT/BMesh no redraw | `blocagem_do_modulo`, `dados_junta`, `aplicar_angulo_junta`, `_deformar_chapa_com_secao`, `_linhas_da_blocagem`, `test_blocagem_assimetrica_e_corda_reta_sem_segmentos_da_madeira`, `test_angulo_da_blocagem_preserva_secao_contato_uv_mesh_e_retorno`, `test_junta_em_lateral_inclinada_preserva_espessura_e_angulo_exato`, `test_blocagem_curva_retangular_sem_diagonal_falsa_nem_mudar_madeira` | formas, hud |

| Inclinacoes multiplas (261): XY/XZ/YZ compoem um corpo 3D; 12 cotas sem extrusoes fantasmas; arcos e valores pelos vetores espaciais, centro/pontas tocam a madeira mesmo com grupo rotacionado e base inclinada. Angulo edita pela intersecao com a reta espacial do apoio, preservando secao e ida/volta. Hull nativo em cache valida os apoios sem fechar um L; nada de Mesh/hull no redraw | `blocagem_cobre_estrutura`, `_delta_da_junta`, `test_inclinacoes_multiplas_desenham_um_corpo_3d_e_arcos_nas_arestas`, `test_juntas_com_inclinacao_composta_editam_o_angulo_real_sem_mudar_secao`, `test_inclinacoes_compostas_cacheiam_o_corpo_e_preservam_topologia_em_l` | formas, hud |

| Referencia estrutural (262): curvas usam caixa retangular local por plano principal, sem diagonal/arco ficticio; contorno real ignora triangulacao, retas subdivididas, portas e arremates pequenos. Inclinacao vertical continua editavel com E preservada; cache invalidado ao sair do Tab e no handler de restauracao | `planos_curvos`, `contorno_tem_curva`, `test_blocagem_curva_retangular_sem_diagonal_falsa_nem_mudar_madeira`, `test_gatilho_curvo_ignora_subdivisoes_quina_l_e_arremate_pequeno`, `test_frente_curva_nao_apaga_inclinacao_vertical_real`, `test_curvatura_da_porta_isolada_nao_muda_referencia_da_carcaca`, `test_prateleira_curva_direta_no_modulo_nao_troca_o_tipo_da_caixa`, `test_classificacao_curva_cacheia_e_invalida_apos_tab_e_restauracao` | formas, frentes, hud |

| Escopo simplificado (263, substitui os controles de grupo descritos em 259-262): qualquer modulo usa caixa convencional de 8 cantos/12 arestas L/A/P, sem inferencia de forma, P1/P2/R ou angulo no menu/HUD. Resize CAIXA sem aplicar solver angular; eventos antigos recusados. Angulo so na chapa individual, preservando vizinhas e isolamento de Mesh. Testes do solver de grupo antigo mantidos apenas como compatibilidade por API | `test_inclinacoes_multiplas_usam_caixa_sem_angulo_no_modulo`, `test_menu_modulo_nao_oferece_formato_nem_aceita_evento_angular_antigo`, `test_hud_do_l_so_oferece_caixa_e_redimensionamento_convencional`, `test_angulo_so_aparece_com_selecao_individual_da_chapa`, `test_evento_hud_antigo_nao_edita_angulo_do_modulo`, `test_diagonal_inteira_so_mostra_angulos_na_chapa_individual` | formas, hud, gaveta, modulos |

| Undo apos chanfro/Tab (264): absorcao manual nao regenera a Mesh, conserva mundo/topologia/UV/material/ID; timer bloqueado durante undo, fecho adia escrita de referencias e limpa transicoes anteriores. Mesh compartilhada em Edit Mode protegida pela propria `is_editmode`. Chanfro nativo + mover + Tab + 4 ciclos undo/redo, copia nativa da Mesh; testes de contratos reprovam codigo 263 | `test_absorver_chanfro_modelado_nao_reconstroi_malha_do_undo`, `test_timer_nao_consulta_cena_enquanto_undo_esta_restaurando`, `test_fecho_do_undo_nao_escreve_malhas_e_descarta_transicao_antiga`, `test_chanfrar_mover_tab_undo_redo_conserva_topologia_e_copia_nativa`, `test_instancia_nao_altera_mesh_que_outra_instancia_esta_editando`, `test_instancia_fora_do_edit_mode_nao_escreve_mesh_em_edicao` | operadores, frentes |
| Cotas neutras e E fisica (265): HUD/menu usam A1/A2... sem mudar props/identificadores salvos. Chapa dobrada/chanfrada mede peles correspondentes, conserva E nominal se ambiguo e linha media ao redimensionar. HUD E usa arestas reais em cache, sem extracao no redraw | `test_cotas_numeradas_preservam_alvos_e_edicao_dos_eixos`, `test_chapa_dobrada_oferece_E_nas_arestas_reais_sem_medir_no_redraw`, `test_medidas_exibem_A1_A2_A3_sem_renomear_props_salvas`, `test_dobra_chanfrada_mede_pele_e_resize_preserva_linha_media`, `test_secao_ambigua_nao_inventa_espessura_pelo_envelope` | hud, gaveta, operadores |
| Cotas dinamicas no menu (266): A1...An/E da chapa usam os mesmos alvos/valores/realce da HUD, por chave semantica. Deslocamento transversal da linha media > E ganha cota independente (A6 no exemplo). Editar conserva madeira/Mesh; arraste usa backup original, Esc restaura geometria/cache e operador aceita undo/redo nativo. Modulo conserva blocagem convencional | `test_deslocamento_transversal_ganha_A6_com_E_independente`, `test_todas_as_cotas_da_viewport_sao_editaveis_pelo_menu`, `test_escape_do_campo_deslocamento_restaura_malha_e_cache`, `test_realce_do_menu_acende_a_mesma_cota_na_viewport`, `test_edicao_de_A6_pelo_operador_aceita_undo_redo_nativo`, `test_menu_chapa_chanfrada_exibe_cotas_da_viewport_com_campos_proprios` | hud, gaveta |
| Cotas de chanfros multiplos (266): duas diagonais em cantos diferentes recebem campos A independentes, enquanto a mesma aresta na frente/verso conserva uma cota so' | `test_dois_chanfros_tem_cotas_independentes_no_menu` | hud |

| Contorno espacial real (267): lateral torcida/chanfrada usa bordas 3D de ambas as peles, sem caixa plana flutuante nem diagonais de triangulacao. Cotas semanticas no menu medem comprimento espacial; edicao move um par, conserva Mesh/UV/E, aceita Ctrl+Z/redo. Angulo real aceita 90 exatos, Esc restaura; arco limitado em pixels; deslocamento junto a borda baixa; redraw so' usa cache | `test_chapa_quadrada_torcida_nao_usa_caixa_plana`, `test_chanfro_com_desvio_usa_as_duas_peles_reais`, `test_triangulacao_interna_nao_cria_cota_ou_diagonal`, `test_contorno_3D_nao_consulta_mesh_ou_forma_no_redraw`, `test_editar_aresta_3D_move_so_um_par_e_preserva_ID_E_UV`, `test_angulo_3D_aceita_90_exatos_sem_mudar_E_ou_Mesh`, `test_aresta_real_editada_pelo_menu_aceita_undo_redo`, `test_guia_de_deslocamento_fica_na_borda_baixa_sem_exceder_envelope`, `test_arco_3D_converte_mm_em_metros_e_fica_colado_na_quina`, `test_cancelar_angulo_3D_restaura_contorno_cotas_e_mesma_Mesh` | hud |

| Solda nativa e encaixe por ancora (268): pontos de MeshVertex reais em chapas torcidas/chanfradas; snap VERTEX pelo translate do cursor compartilhado com gavetas/prateleiras, KDTree nativa fora do desenho; confirmar restaura cursor/selecionabilidade. Ancorar conserva forma e posicao; afastamento cadastrado por par, sem fechar o gap (269); solver de restricoes distintas conserva E/Mesh; referencias e undo/redo preservados | `test_selecao_de_solda_usa_todos_os_vertices_nativos_sem_caixa`, `test_snap_de_solda_reutiliza_translate_nativo_sem_projecao_de_vertices`, `test_snap_compartilhado_da_solda_devolve_cursor_e_alvos_ao_confirmar`, `test_fim_da_escolha_resolve_destino_na_malha_real`, `test_juntar_chapa_torcida_preserva_forma_e_cadastra_afastamento`, `test_juntar_varias_ancoras_reais_chega_a_zero_sem_media`, `test_ancoras_incompativeis_nao_deformam_espessura`, `test_parceiro_de_espessura_nao_depende_do_sinal_do_Z`, `test_solda_automatica_tambem_aponta_vertices_reais_da_chapa_torcida`, `test_undo_redo_de_juntar_preserva_vertices_e_ancora` | hud |
| Fluxo nativo da solda (268): depois de cada par, Enter conclui sem ser consumido pelo proximo snap; clique inicia novo par no soltar. Agrupar duas soltas conserva as ancoras manuais, sem a deteccao automatica apaga-las | `test_escolha_de_solda_pausa_apos_par_para_concluir_com_enter`, `test_juntar_duas_soltas_conserva_ancoras_ao_criar_modulo` | hud |

| Origem da ancora (269): afastamento 3D cadastrado sem mover; Resetar restaura o gap em ambos os lados, varios pares sem media; referencial acompanha giro do modulo; limpeza e undo/redo preservados | `test_gap_cadastrado_nao_move_nem_acende_reset`, `test_reset_restaura_gap_3D_sem_mudar_forma_E_Mesh_ou_alvo`, `test_reset_do_destino_tambem_restaura_gap_cadastrado`, `test_gap_acompanha_rotacao_e_translacao_do_modulo`, `test_origens_da_ancora_saem_ao_desligar_ou_substituir_junta`, `test_reset_de_gaps_distintos_recupera_vertices_sem_media`, `test_undo_redo_do_reset_preserva_origem_cadastrada` | hud |

| Corrente por selecao (270): Alt e gizmo desvinculam a chapa ativa, mesmo como destino da solda; grupo usa a peca afastada. HUD/menu e vao das prateleiras ignoram a peca solta no resize dos tres eixos; undo/redo conserva pai e envelope | `test_alt_corrente_desvincula_lateral_ativa_e_nao_a_base`, `test_gizmo_corrente_desvincula_o_mesmo_alvo_que_a_regua`, `test_corrente_no_grupo_remove_a_lateral_afastada_mesmo_sendo_destino`, `test_hud_e_menu_redimensionam_so_o_modulo_apos_desvincular`, `test_undo_redo_da_corrente_conserva_o_escopo_real_do_modulo` | hud |

| Soldar novamente em preset legado (271): recupera a marca da Collection exclusiva ou cria uma propria sem mover itens alheios; mesma normalizacao para comodos; prepara antes de filiar e aceita parentesco parcial de erro anterior; conserva gap/forma e undo/redo | `test_soldar_novamente_reconhece_colecao_importada_sem_marca`, `test_nova_solda_recupera_parentesco_parcial_de_tentativa_que_falhou`, `test_solda_sem_colecao_propria_cria_montagem_sem_tomar_itens_alheios`, `test_soldar_modulo_antigo_na_raiz_cria_colecao_propria`, `test_undo_redo_de_nova_solda_restaura_marca_colecao_e_parentesco` | hud, orcamento |

| Ferramentas de manutencao (272): 12 CLIs com ajuda sem migracao; preparo externo por caminho real/case do Windows; publicacao verifica hashes antes de escrever, conserva backup e restaura arquivos se uma copia falha; testes so em temporarios | `TestMigracoes` em `test_migracoes_blender.py` | migracoes |
| Prateleiras (273/274): exclusao nativa atualiza contador e vaos sem mover/recriar sobreviventes, remapeia ajustes e encaixe; zero unidades nao reaparece no resize. Secao Espacamento: Centralizar espacamento (setas opostas/barra, altura 37) e campos E1..En+1, grupo ou unidade, sem Igual/Livre/Abaixo/Acima. Conserva malhas/espessuras individuais; layout em tres larguras e undo/redo | `sincronizar_exclusoes`, `OBJECT_OT_alinhar_prateleiras`, `test_excluir_qualquer_unidade_preserva_posicoes_e_recalcula_hud_e_menu`, `test_secao_espacamento_tem_campos_E_e_botao_sem_sobreposicao_em_tres_larguras`, `test_undo_redo_de_excluir_e_alinhar_restaura_quantidade_e_posicoes` | prateleiras |
| Categorias da biblioteca (276/277): modos e niveis em uma unica linha em qualquer altura, caixas com hover cinza e contornos/divisorias cinza claro do tema em todas as juntas; navegacao sem halo. Fundo nao intercepta abas, roda no padding afeta so seu nivel, Shift+roda conserva acesso aos niveis profundos | `test_todos_os_grupos_incluindo_modos_tem_caixa_e_divisoria_na_mesma_linha`, `test_hover_de_aba_realca_so_a_caixa_daquela_categoria`, `test_caixa_tem_hover_no_espaco_vazio_sem_roubar_o_hit_test_da_aba`, `test_roda_no_padding_da_caixa_rola_apenas_seu_nivel` | biblioteca_faixa |
| Biblioteca responsiva (278): miniaturas crescem proporcionalmente a' altura da area, cabem com as setas mesmo em faixa alta/estreita e conservam ajuste/caminho; contorno da categoria SO' durante hover de uma aba, nunca permanente ou pelo fundo vazio | `test_miniaturas_crescem_com_a_area_sem_ultrapassar_altura_ou_largura`, `test_hover_de_aba_realca_so_a_caixa_daquela_categoria` | biblioteca_faixa |
| Organizacao apos Delete nativo (279): remove controles ocultos das dobradicas, Empties e pasta marcada do modulo sem pecas; exclusao parcial preserva sobreviventes, dados compartilhados e objetos/pastas comuns. Adia em Tab/modal/undo; undo/redo restauram montagem/Collection | `test_delete_pecas_limpa_rig_empties_e_pasta`, `test_delete_so_folha_limpa_rig_e_preserva_carcaca`, `test_delete_pai_deixa_subgrupos_mas_limpeza_remove_pasta`, `test_delete_parcial_preserva_porta_e_dobradicas`, `test_limpeza_preserva_objeto_comum_na_pasta_e_grupo`, `test_limpeza_rig_preserva_filho_comum_e_dados_compartilhados`, `test_limpeza_so_remove_pastas_marcadas_e_comodos_vazios`, `test_limpeza_adiada_em_undo_edicao_ocupado_e_modal`, `test_delete_undo_redo_restauram_modulo_e_pasta` | portas |
## Volume visual (v285)

Origens no grupo (v287): opcao Ocultar/Mostrar, padrao oculto, flags nativas
por viewport e restauracao ao isolar peca/salvar/desligar; respeita mudancas
manuais e origens previamente ocultas. TestHUD: `test_origens_grupo_restaura_flags_nativas_e_opcao_muda_na_hora`,
`test_origens_respeita_viewport_e_intervencao_manual`, `test_origens_somem_em_todos_os_grupos_mas_nao_na_folha_individual`,
`test_menu_oferece_ocultar_e_mostrar_origens_no_grupo`.

v286: arraste inicia sem snap (B ativa a base nativa), mesmo com ima global
ligado; circulos de face com raio 2 px/hover 3 px, area de clique preservada.

- Seis centros de face, picking e caixa girada: `TestHUD.test_volume_seis_centros_reais_e_hit_test_em_caixa_girada`.
- Translate nativo, filtro de vertices, estado sem IDs: `TestHUD.test_volume_translate_nativo_vertice_base_b_e_estado_sem_ids` e `test_volume_macro_executa_translate_real_e_confirma`.
- Referencia unica/Esc: `TestHUD.test_volume_previa_reparte_da_origem_e_esc_restaura_malha`.
- Limite fisico invalido permite voltar a uma medida valida sem abandonar o modal: `TestHUD.test_volume_medida_invalida_nao_abandona_translate_e_pode_recuperar`.
- Corrigir vao de prateleiras sem mover corpo: `TestHUD.test_volume_prateleiras_corrige_topo_e_base_sem_mover_corpo`.
- Frente movel/fundo fixo e filhos refeitos: `TestHUD.test_volume_prateleiras_frente_movel_preserva_costas` e `test_volume_gavetas_e_divisorias_previa_repetida_com_filhos_refeitos`.
- Escopo de angulos/unidades: `TestHUD.test_volume_nao_intercepta_angulo_e_cota_de_unidade`.
- Eventos reais B/Esc/numero/undo: `gui_interacao.test_circulo_da_face_translate_b_esc_e_undo` (requer GUI autorizada).

## Opcoes e encaixe dos internos (v288)

- Bolinhas/guias independentes, sem alvos invisiveis e com preferencias RNA: `TestHUD.test_opcoes_independentes_escondem_bolinhas_e_guias_sem_alvo_fantasma`, `test_menu_tem_controles_ligado_desligado_para_bolinhas_e_guias`.
- Consumir folga antes de diminuir; restaurar escolha ao devolver espaco: `TestGavetas.test_reducao_com_folga_preserva_gavetas_ate_faltar_espaco`, `TestPrateleiras.test_reducao_com_folga_preserva_prateleiras_e_so_adapta_ao_encostar`.
- Escala nativa S, dimensao fisica das malhas e recuperacao: `TestGavetas.test_escala_nativa_conserva_internos_ate_faltar_espaco`.
- Largura individual menor preservada: `TestGavetas.test_gaveta_individual_menor_nao_encolhe_junto_com_o_vao`.
- Cancelar HUD restaura metadados e geometria: `TestPrateleiras.test_cancelar_resize_do_modulo_restaura_vao_parametros_e_geometria`.

## Base do snap depois da previa (v289/290)

- v290 substitui o retorno a' origem da v289: B preserva a geometria ATUAL e absorve o ultimo movimento antes do timer. Tres eixos/duas direcoes, vertice chega ao destino, cursor intacto na preparacao, translate real e Esc: `TestHUD.test_volume_base_snap_apos_arraste_preserva_geometria_atual_em_todos_os_eixos`.
- B repetido/confirmacao da mesma base conserva o deslocamento acumulado, sem somar duas vezes; Esc recupera origem e malha: `TestHUD.test_volume_base_snap_repetida_acumula_so_arrastes_e_esc_restaura_origem`.
- Observador repassa os eventos/undo, consulta o matcher nativo (atalhos remapeados), instala depois do translate e libera timer: `TestHUD.test_volume_observador_repassa_base_nativa_e_termina_sem_consumir_undo`, `test_volume_observador_abre_depois_do_translate_e_libera_timer`.
- Arrastar 60 px -> B (conserva posicao atual) -> vertice atual da base -> B -> vertice destino fixo -> Enter/soltar -> undo: `gui_interacao.test_snap_b_depois_de_arrastar_face_nao_soma_deslocamento_anterior` (GUI autorizada).

## Dono explicito da atualizacao do modulo (v295)

- `modulos.atualizar_sistemas_do_conjunto`: portas -> gavetas -> prateleiras, uma chamada por dominio; `internos=False` preserva encaixes. Portas conserva seu aplicador e a fachada publica antiga, sem coordenar internos.
- `test_coordenador_atualiza_portas_gavetas_prateleiras_uma_vez_nesta_ordem`, `test_api_legada_delega_ao_mesmo_coordenador_sem_duplicar`: ordem e compatibilidade da assinatura antiga.
- `test_atualizar_apenas_portas_preserva_internos_reais`, `test_coordenador_ignora_alvo_ausente_ou_sem_marca`: escopo e alvos validos.
- `test_resize_sem_porta_usa_coordenador_e_preserva_malhas_modeladas`: resize real, internos sem porta, cada dominio uma vez, mesmos IDs/recortes de Mesh.
- `test_producao_nao_coordena_sistemas_pela_api_legada_de_portas`: chamadores internos nao voltam a depender da fachada antiga.
- `test_undo_redo_do_resize_coordenado_restaura_corpo_e_internos`, `test_recarga_religa_setores_e_preserva_objetos_da_cena`: undo/redo, recarga e ligacoes dinamicas preservadas (suite organizacao).

## Detalhamento local de prateleiras (v294)

- Grupo: quantidade total e blocagem inteira; unidade: quantidade de suas subdivisoes, apenas entre apoios externos, contador/cotas/moldura locais. UID persistente por copia, sem nova hierarquia.
- `test_quantidade_local_subdivide_so_entre_os_apoios_e_reutiliza_a_familia`: dividir 1 em 2/3/1, ativa preservada, apoios parados, ultimo E nao move apoio, Centralizar redistribui so' o trecho.
- `test_selecao_local_tem_contador_e_caixa_limitados_e_grupo_tem_total`: alternancia de contador, campos E e limites da HUD por selecao.
- `test_detalhamento_preserva_quatro_gavetas_e_herda_madeira_em_modulo_girado`: quatro gavetas preservadas, giro 3D, IDs/recorte/material/modificador e parametros das copias.
- `test_contador_local_digitado_arrastado_e_esc_mantem_escopo`: alvo por nome, previa sem copiar, Esc cancela e digitacao respeita o trecho.
- `test_detalhamento_inviavel_nao_altera_cena_e_zero_remove_so_o_trecho`: capacidade fisica validada antes de alterar; zero preserva apoios.
- `test_undo_redo_de_detalhar_preserva_vinculo_e_apoios`, `test_detalhamento_gravado_em_blend_reabre_com_escopo_local`: undo/redo, salvar/reabrir e grupos independentes com o mesmo UID.

## Posicao nativa de prateleiras e cotas (v293)

- `test_g_nativo_em_tab_individual_e_global_atualiza_cotas_sem_mover_vizinhas`: transform.translate nativo, movimento para cima/baixo, modulo girado em 3D, HUD/menu E, mesmos IDs Mesh e remontagem sem salto.
- `test_g_nativo_em_objeto_sincroniza_so_apos_confirmar_e_conserva_encaixe`: sem sincronizar durante modal; descarta encaixe antigo sem remontar no timer.
- `test_g_cruzando_prateleira_reordena_cotas_e_conserva_parametros_individuais`: ordem real de baixo para cima, ajustes e selecao seguem a chapa.
- `test_undo_redo_do_g_nativo_restaura_malha_posicao_e_cotas`: undo/redo recuperam geometria/cotas, com guarda ate' o timer normal.

## Centralizar prateleira individual (v292)

- Uma selecionada iguala apenas seus vaos acima/abaixo, entre faces de apoio reais ou limites do vao; grupo selecionado continua distribuindo todas.
- `test_centralizar_individual_iguala_so_vaos_vizinhos_e_preserva_madeira`: primeira/intermediaria/ultima/unica, espessura individual, recorte e ID Mesh, vizinhas e selecao preservados.
- `test_centralizar_individual_absorve_exclusao_e_remapeia_indice`: exclusao pendente do timer e indice compactado antes de escolher os apoios.
- `test_centralizar_individual_undo_redo_restaura_posicao_e_selecao`: undo/redo nativos recuperam as alturas e a unidade ativa.

## Reconhecimento real de B no resize (v291)

- Matcher modal direto nao funciona (idname vazio/poll); espelho normal interno preserva atalhos/modificadores e remapeamento, com limpeza no fim/unregister: `TestHUD.test_volume_mapa_snap_nativo_tem_operador_valido_e_copia_atalhos_modais`. Fixture usa itens RNA nativos, sem substituir o matcher por Mock. Prova em Blender aberto: item vazio rejeitado; item valido e reconhecido pelo matcher com evento real; evento de outro atalho rejeitado.
- Corpo dobrado, quatro gavetas e rotacao 90 graus: tamanho inicial preservado; arraste antes de B, referencia atual e nova translacao mantem medida; Esc restaura: `TestHUD.test_volume_gavetas_em_corpo_dobrado_e_girado_preservam_previa_ao_ancorar`.
- Gesto completo ate' a quina real do corpo e undo: `gui_interacao.test_snap_b_gavetas_em_corpo_dobrado_e_girado_alinha_vertice_real` (GUI autorizada); o teste confere tambem se B chegou ao observador.
