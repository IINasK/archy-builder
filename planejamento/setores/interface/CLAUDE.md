# Interface -- guia transversal
Leitura EXPLICITA pela rota do indice/guia raiz para tarefas de interface.
Este AGENTS.md esta' em documentos: NAO se aplica automaticamente ao codigo
em `cabinet_creator/`. Manter este arquivo e `CLAUDE.md` identicos, em ASCII.
Caminhos abaixo partem da raiz do repositorio. Limite: 120 linhas.
Escopo: `cabinet_creator/gaveta.py`, `gaveta_desenho.py`, `gaveta_eventos.py`,
`hud.py`, `selecao.py`, `eventos.py`, `editor.py`, `areas_criacao.py`, `biblioteca_faixa.py` e `materiais.py`.
Nesta etapa, o menu permanece nos caminhos atuais; `gavetas/` e' o movel.
Antes de mexer no visivel, ler `DESIGN.md`; contratos recusados estao la'.
Assets/presets: ler `cabinet_creator/biblioteca/CLAUDE.md` e
`planejamento/setores/integracao/AGENTS.md`.
Fundos (360): aba propria com campos/segmentos existentes e Criar Fundo
no SOLTAR. UNPINNED desassocia na aba Fundos ou nos internos vinculados.
## Rota de trabalho
Suite = `tests/test_<suite>_blender.py`; `gui_*` = `tests/<suite>.py`.
| Tarefa | Arquivo: funcao/classe | Suite |
|---|---|---|
| Contexto/layout | gaveta.py: `_widgets_gaveta`, `_widgets_interativos` | gaveta, estrutura, snapshot |
| Editor persistente/ponte 3D | editor.py: `configurar`, `reparar`, `executar` | editor, biblioteca_faixa |
| Desenho/identidade | gaveta_desenho.py: `_desenhar_gaveta`, `_chave_widget` | gaveta, estrutura, gui_interacao |
| Clique/campo/texto | gaveta_eventos.py: `OBJECT_OT_interagir_gaveta`; gaveta_desenho.py: `_tecla_no_texto` | gaveta, hud, gui_interacao |
| Selecao/aba/Tab | selecao.py: `OBJECT_OT_selecionar`, `_seguir_selecao_na_gaveta`, `OBJECT_OT_editar_grupo` | operadores, hud, gui_interacao |
| Cotas/hover/arraste | hud.py: `campos_cotas`, `_acertar_hud`, `OBJECT_OT_arrastar_hud` | hud, gaveta, snapshot |
| Face da caixa/snap B | hud_volume.py: `controles`, `iniciar`, `atualizar`, `terminar` | hud, gui_interacao |
| Grupo Paredes, edicao 2D e biblioteca na parede | paredes_edicao.py: `widgets`, `iniciar`, `encerrar`, `preparar_modelo` | paredes_edicao, gaveta |
| Elevacao/cotas editaveis dos modulos (menu: so' a cruz do selecionado) | paredes_composicao.py: `widgets`, `desenhar`, `editar_modulo` | paredes_composicao |
| Undo/contorno/timer | eventos.py: `_antes_de_desfazer`, `_fim_do_desfazer`, `sincronizar_contornos`, `verificar_periodicamente` | operadores, hud, estrutura |
| Faixa/niveis/menu | biblioteca_faixa.py: `widgets`, `catalogo`, `rolar`, `abrir_menu_item` | biblioteca_faixa, gui_biblioteca_faixa |
| Fotos/cache | gaveta.py: `_guardar_foto_gaveta`, `_desenhar_foto_gaveta`; biblioteca_faixa.py: `invalidar` | biblioteca_faixa |
| Sim/Nao | gaveta.py: `_pergunta_na_gaveta`; perguntas.py: `_perguntar` | gaveta, biblioteca_faixa, gui_interacao |
## Decisoes de interacao
- Parede 371: alvo fixo ignora outros objetos; pontos usam snap VERTEX nativo so' nele. Parcial inativo cinza, sem avisos/cotas/edicao; elegibilidade fixa na entrada. Edit Mode usa vertices; Object Mode tem Automatico/Por pontos
  no grupo Paredes. Modal repassa eventos do menu/navegacao; esquerdo marca,
  Backspace volta, Enter confirma, direito/Esc cancela; menu oferece iguais
  acoes. Hover reutiliza o desenho do atach, sem inferencia no redraw.
- Parede (299): menu nao exibe nem edita medidas da parede identificada.
  Na edicao 2D, cotas sao dos modulos/vaos; clique digita, Esc cancela.
  Parede e modulos solidos/OBJECT/FLAT com contornos pretos nativos. Estado
  anterior e' devolvido na saida; G/Tab continuam nativos. Redistribuir
  exige comando (fora do menu desde 338); troca so' apos confirmar.
  Orbita volta a PERSP; biblioteca ajusta L/A ate limite do menu (363). Duplo clique
  segue o ultimo para a direita ou centra na parede quando exceder.
  Chapas usam show_wire nativo temporario; ferragens ficam sem a sobreposicao.
  So' nesta vista, clique em qualquer peca seleciona modulo; duplo isola.
  Interior: arestas avaliadas, cinza com alfa so' atras das frentes. Cotas
  proximas da peca; extracao no timer, redraw consulta somente cache numerico.
  Cotas (301): traco do tema sobre halo opaco, setas e fonte minima 14;
  item ativo usa realce da HUD. Numeros apos linhas; A1/A2/A3 sempre, A3 Prof. na quina (368), editavel e separado do afastamento; resize esconde so' distancias.
- Sim/Nao passa por `_perguntar`: pop-up SO' da viewport; botao do menu =
  caixa preta na gaveta; pergunta da biblioteca fica na faixa. Nunca abrir
  `popup_menu` em background. Operador que abre modal/pergunta dispara no
  SOLTAR (`solda.OPERADORES_NO_SOLTAR`), inclusive quando tem icone/gizmo.
- Excecao: DIREITO na foto/nome da biblioteca abre no SOLTAR o menu
  Inserir/Editar/Bloquear; sem botoes sob modulos. Respeitar cadeado/protecao.
- A SELECAO decide o que edita; Shift soma e conserva a malha clicada como mestre (356: Ctrl+L nativo); a gaveta segue a aba do item.
  Caixa (laterais/tampo) seleciona modulo; duplo isola chapa. Quina arrasta
  modulo; Ctrl encaixa SO' em quina/ponta de curva de OUTRO armario/chapa. Clique fora encerra o individual; novo clique simples = grupo (Shift conserva).
- Porta 378: Esconder porta e agregados (28 px) no menu; Shift+G -> Grupo da porta -> H, com agrupamentos nativos preservados. Ocultacao por View Layer/undo, sem mudar geometria. Clique inteira, nunca modulo; duplo folha, sem contorno nativo.
  Sem linha Reposicionar/Frente/Espelhar na aba. Espelhar fica no contexto direito, grupo ou folha; inverter
  giro, cadeia zigzag inteira, curso de correr ou basculante com pistoes;
  puxador acompanha. Nao espelhar madeira.
- Ferragem: so' aparece criando ou selecionada, ARAME da peca real. Clique
  seleciona todas do tipo NATIVAMENTE (370); Shift soma; Alt controlador; duplo PECA
  com Tab/G/X nativos. Trilho das gavetas permanece com elas.
- Puxador: clique = a peca dele (folha/frente); DUPLO = SO' ele e funcoes. Alt arrasta
  ancora para outra borda SO' do grupo dele, com snap de linha.
- Gavetas/prateleiras (379): na cota V selecionada, scroll subdivide so' o vao; campo passa a quantidade e Enter confirma, Esc descarta copias. Prateleiras da mesma blocagem mostram cotas de todos os segmentos; divisorias so' na orientacao ativa, sem poluicao mista. Clique todas do vao, duplo uma; modulo absorve filhos
  na HUD. Divisorias: clique grupo, duplo chapa. Conservar escopo por tipo.
- Tab no Empty (383: inclui uma ou varias unidades de gaveta) = Edit Mode MULTIOBJETO nativo, so' malhas reais, sem
  cortadores/controles; tornar compartilhadas unicas antes. Conservar Empties
  selecionados no Edit Mode, registrar a transicao ja' na entrada (Tab
  rapido nao depende do timer), restaurar selecao/ativo ao sair e invalidar
  planta; estado SO' nomes. Peca isolada conserva Tab nativo.
- Vista local: ray cast ignora ocultos; Tab move rigs por `ferragens`, com referencia na Mesh para undo, espelhos materializados e UVs corrigidas nativamente.
- Area livre (377: modulo selecionado fixa alvo; primeiro clique e HUD/B ignoram externos, sem ocultar cena): 378: Definir por volume/plano laranja (mesmo estilo/30 px do Criar); captura 3D libera a camera entre cliques (translate so' ate RELEASE, navega por keymap nativo). Definir por volume/plano -> um clique sem vertices -> HUD/centros/G/R/S -> Aplicar area -> clique na frente (volumes). Tres pontos 3D aceitam qualquer ordem: caixa min/max ortogonal ao modulo e frente explicita, com realce da propria face sob o raio nativo; HUD de arraste suspensa durante a escolha. Planos 2D conservados. Empty temporario conserva 8/4 cantos ortogonais; entrega numerica aos assistentes, sem reinterpretar apoios. Undo/load/save/unregister limpam. Volume/B: base na geometria ATUAL ao apertar B, nunca na posicao inicial.
  O nativo restaura o cursor; `hud_volume.preparar_base_snap` absorve o ultimo
  movimento e registra o deslocamento acumulado SEM devolver a madeira.
  Repetir B nao duplica o gap; backup/inicio originais continuam para Esc.
  Observador antes do evento nativo; todos os eventos passam. O matcher
  `KeyMapItems.match_event` faz poll de OPERADOR: mapa MODAL tem idname
  vazio e nunca casa! Consultar espelho NORMAL interno com operador valido
  e os mesmos atalhos/modificadores, sem mudar o mapa original. A API
  `new_from_item` recusa modal -> normal; copiar os campos de evento.
  Invalidar ao remapear; remover espelho/cache junto ao observador.
  O timer WM encerra o observador mesmo sem mover o mouse; unregister
  remove-o diretamente. Guardar somente identificador numerico da sessao.
- Undo/redo: nao consultar selecao/malhas durante `_desfazendo`; fecho apenas
  libera guarda, referencias voltam no timer normal. Descartar transicoes
  antigas de Edit Mode/modal. Hover nao pode reter IDs liberados; limpar no
  undo_pre e conferir `_alvo_vivo`. Contorno so' religa o que ELE desligou;
  objeto comum na selecao mista devolve o nativo, mesmo sem ser ativo (358).
- Selecao 369: `selecao.objetos_na_camada` limita clique/Shift/porta/Tab a' View Layer nativa; pai fora dela nao vira ativo. Clique: keyconfig ADDON; objeto comum fica no CLICK
  nativo. `OBJECT_OT_selecionar.poll` recusa fora de Object Mode ou com
  `selecao_por_grupo` desligada; props SKIP_SAVE.
## Gaveta e biblioteca (365: NODE_EDITOR CabinetCreatorMenu/Biblioteca, nunca VIEW_3D)
- Abas (362): sem espaco (BLF/fonte 12/margem 18), suspenso fixo com aba atual; lista flutuante despacha `aba`. Prefixo dinamico. 375: seis abas; Prateleiras / Divisorias unificada, DIVISORIAS legado e' alias so' visual; controles seguem dono selecionado. areas_criacao guarda sessao numerica por cena: tipo -> volume/pontos -> quantidade -> lacuna opcional -> outro tipo/Sair, mesma area; undo/load/save/unregister descartam sessao, preservam criados.
- Gaveta por CONTEXTO em toda aba: sem selecao, SO' criar laranja (Modulos:
  nada); criando, campos etapa a etapa, copia clicavel da caixa atendida
  pelo modal; selecionado, SO' controles do ITEM. Porta sem dobradica;
  ferragens = quantidade/afastamento. Dobradica/Converter ficam no F3.
- Criando/reancorando solda (355), HUD de geometria e hover ficam bloqueados; corrente/regua/snap continuam. Criar/confirmar usa destaque laranja existente. Painel proprio, sem Orcamento; distancia, zero, voltar, aceitar/cancelar. Direito/Esc cancela; Backspace/Ctrl+Z volta; Alt reancora. Sem nome do item, Sincronizar ou Auto-regenerar. Montagem: Criar solda em
  linha inteira, Corrente e Resetar distancia com texto e icone, empilhados se estreito. Arrastar campo muda; clique digita.
- editor.py guarda arvore vazia propria para gizmos nativos 4.2; subtipo salva o papel, marca de ponteiro e' consumida ao migrar legado. `executar` leva comandos a' viewport; texto/arraste ficam na origem.
- Layout devolve `(x, y, w, h, rotulo, acao)`, desenho pinta, evento despacha. Rolagem (373): barra vertical so' com excesso, independente por painel; roda/touchpad/arraste, Esc restaura. Abas/rodape fixos; opcoes cobrem barras. Verbo `rolagem` separa trilho vertical do slider horizontal de tamanho.
  Nao hashear acao com dict. Gizmos em pool: ocultar/reusar; nao remover ou
  religar no redraw. Button2D fixa simbolo no 1o draw: pool por icone/ocorrencia. Campos/corrente/regua conservam operador; atualizar props.
- Biblioteca: FAIXA no topo (`cabinet_layout=2`: faixa/menu/cena) ou NO MENU
  (`cabinet_biblioteca_lugar=MENU`, nao migra; troca no timer): nivel = lista suspensa.
- Niveis sem limite (`niveis`); abas 18 px/fonte 10/intervalo 2. Modos e niveis
  numa linha em qualquer altura; caixas CINZA, juntas cinza claro/vao 12.
  Contorno cinza claro SO' no hover de ABA; sem halo na navegacao.
- Fundo nao rouba clique; roda X/Y. Setas so' com overflow no sentido oculto;
  sem contagem, ramo vazio some. Shift+roda percorre niveis profundos;
  chaves de rolagem com hash, maximo 63 bytes.
- Fotos SO' visiveis, proporcionais a' altura e limitadas pela largura;
  cache RGBA8 de 64 MiB, indice invalidavel. Nada de abrir .blend no redraw.
- Material = COR SOLIDA no slot do OBJETO. Grupo (382): catalogo/Ctrl+L preservam puxadores, ferragens e filhos; selecao completa. Individual nativo permitido.
  Ctrl+L reutiliza menu/motor nativos, filtrando somente MATERIAL. Esfera: clique simples NADA;
  duplo aplica a' SELECAO; arraste ao de baixo; DIREITO pintura rapida (comodo -> parte). Conservar gestos.
Validacao: `tests/CLAUDE.md`; GUI so' com PC livre AGORA autorizado; callback com erro falha.
