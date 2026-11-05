> Historical technical notes. Current instructions: [architecture](../../ARCHITECTURE.md) and local sector guides. Source paths below are retained only where historically relevant.

# Setor montagem e associacoes
Consulta explicita para `cabinet_creator/cabinetry/welding.py`, `paredes.py`,
`ambientes.py`, `orcamento.py` e a filiacao em `modulos/`. Este guia nao e' herdado
por arquivos em outras pastas. Pares AGENTS.md/CLAUDE.md identicos.
## Onde alterar
| Tarefa | Entrada | Suite |
|---|---|---|
| Juntar ou desvincular chapa | `solda.juntar_conexao`, `solda.desagregar` | hud |
| Vinculo e pasta do modulo | `modulos.agrupar_chapas`, `_garantir_colecao_modulo` | operadores, hud |
| Regua, corrente, reset e ancora | `solda.py` operadores `cabinet_*`; HUD em `hud.py` | hud |
| Alvenaria, apoio e ambientes | `paredes.py`: marco/piso/G; `ambientes.py`: faces/cor/Collection | paredes, ambientes |
| Vista 2D/Local View, previa e distribuir modelos | `paredes_edicao.py` | paredes_edicao, gaveta |
| Cotas de modulo, larguras fixas, redistribuir/trocar modelo | `paredes_composicao.py` | paredes_composicao, hud |
| Comodo e arquivo vendido | `orcamento.py` | orcamento |
Leia tambem `cabinet_creator/cabinetry/cabinets/AGENTS.md` para envelope, Collections
compartilhadas e dependentes; `docs/reference/interface.md` para precedencia de clique e gizmos.
Paredes exigem tambem [integracao](integration.md): gesto DIREITO,
associacao a' face real, deslizamento G/R e guias editaveis pertencem la'.

## Decisoes e armadilhas
- Alvenaria 404: Editar laranja primeiro; olho junto a Teto, forcado ao editar. Catalogo de instalacoes reutiliza cascata/grade/fotos; arraste nasce na origem. Direito usa mesmo posicionador; reassociacao valida antes de escrever, transfere so' o corte proprio, preserva componentes. Undo/redo invalida cache numerico; suite instalacoes. Alvenaria 403: tipos por faces na aba propria; seletor nativo sem agrupar categorias de comodos. Previa numerica em copia BMesh no timer; Editar substitui so' o tipo escolhido e preserva os demais. Confirmar le selecao nativa atual; legado materializa normais antes de editar. Instalacoes 402: apoio por UID e face original, cotas no plano; Boolean Exact reversivel, filtro das faces do cortador so' em casca; esquadria, tabica e luz tem dono proprio. Alvenaria 399: selecao automatica por categoria/plano; Shift individual, Ctrl percurso/Shift+Ctrl preenchimento nativos. Mistas aplicam; so' todas iguais removem; Sem categoria limpa. Olho alterna cores/nomes. Categorias em 2D conservam sessao e proxy; BVH do recorte limita acerto/previa, faces nativas inteiras sem corte. 398: modos 2D/categorias lado a lado, desagregar vermelho abaixo; nome aplica categoria no soltar (sem Definir como). Normal mundial distingue parede/piso/teto; associacao livre e piso em pe. Categoria das faces existentes permanece; novas faces nativas ficam em 0 ate' cadastro manual. Captura de wrappers BMesh so' no Edit Mode, limpa antes de undo/save/abrir/unregister; sem IDs RNA. Criar camada FACE realoca wrappers: renovar captura antes de pintar. INT FACE/mapa UID, cache em copia e realce com bias de projecao. Orcamento filia Collections por UID; pulsos reservados.
- Parede 371: escolha consulta SO' o objeto fixado, pulando teto/backfaces ocultas. Pontos usam cursor/translate nativo VERTEX/ONLY_SELECTABLE, com restauracao. Area visivel >=90% na entrada libera edicao pela sessao inteira; demais usam copia avaliada/Boolean EXACT cinza, bloqueada. Fontes intactas, estados/temporarios limpos na saida/undo/save.
- Base 367: ao entrar, apoio continuo na faixa de contato da parede recorta a area enterrada. Proxy/cotas/guias/arraste partilham a regiao recortada; parciais/suspensos e modulos nao levantam a base. Cotas 366 aceitam zero; dimensoes validam no dono e ruido <=1 um nao libera colisoes.
- Importacao 364: resize pode recriar componentes; `aplicar_ajuste_do_modelo` atualiza `novos` no finally pela hierarquia nativa. Registro/Local View usam a mesma geracao viva; rollback inclui recriados.
- Parede 361: paredes_selecao valida vertices BMesh conectados (1 grau/2 mm),
  poligono de 3+ pontas e hover pelo raio/realce do atach. Local View mostra
  somente exibicao temporaria da regiao + moveis reais associados por area;
  malha original fica intacta. Proxy resolve fonte/UID no raio e e' limpo
  ao sair/salvar/unregister, ou no timer apos undo.
- Parede 2D (296): `paredes_edicao` guarda sessao numerica/nomes; Local
  View nativo preserva isolamento anterior e ocultacao manual. Orbita/Walk/Fly
  encerram; zoom/pan nao. Undo/abrir/salvar/unregister encerram antes de
  invalidar referencias. Getter Local View 4.2 usa objeto avaliado.
  Biblioteca ajusta L/A ate limite (363: 10 mm; zero desliga), E constante; duplo clique poe a'
  direita do ultimo ou no centro se exceder. Redistribuicao e' explicita.
  Folgas/espacamentos e obstaculos por altura/face entram
  no planejamento; BVH/raycast nativos consultam retornos. Desenho so' le
  previa numerica calculada no timer. Falha limpa somente dados da tentativa.
- Composicao (297): `paredes_composicao` publica fichas numericas de modulo
  e vaos; resize orientado pertence a `modulos.redimensionar_orientado`.
  `parede_largura_fixa` e' ID prop persistente do modulo. Redistribuicao
  e' explicita; mover/deletar so' recalcula vaos. Troca valida o novo antes
  de remover o original. Parede nao recebe cotas no menu. SOLID temporario
  usa `cabinet_parede_exibicao_2d`: undo pode restaura-lo, limpar no timer.
  Observador passivo da parede nao bloqueia o timer/handler apos G/Tab.
  Em 298, orbita volta a PERSP; contorno preto nativo e' temporario.
  `parede_ordem_posicionamento` conserva o ultimo entre sessoes; staging
  oculto usa caixa anterior, pois seus filhos nao atualizam no depsgraph.
  `cabinet_parede_arestas_2d` restaura show_wire das chapas ao sair/undo;
  ferragens ficam fora. Arestas nativas, sem extrair malha para desenhar.
  Interior (299): copia BMesh da geometria avaliada no timer; quinas reais,
  sem triangulos coplanares. Cache so' numerico, invalidado pelo depsgraph;
  POST_VIEW/GREATER mostra linhas ocultas com alfa sem alterar a Mesh.
  Encaixe (301): `faixas_livres` e `encaixar_na_face` sao comuns ao arraste
  direito, biblioteca, insercao, cotas e distribuicao. Excluir o proprio
  modulo; respeitar sobreposicao vertical, face, buracos e profundidade.
  Previa e mira usam o envelope/centro aceito, nunca o alvo bruto do mouse.
  Mover (312): clique em qualquer peca = modulo (G nativo leva tudo);
  snap VERTEX/CLOSEST temporario em `visual['snap']`, devolvido ao sair.
  `acompanhar_arraste` (depsgraph) refaz so' numeros com `_caixas`; o
  timer segue dono da lista de modulos, interiores e caixas.
  Guias (313): alturas na cena (`parede_guias`, `parede_guias_modo`);
  snap nas guias = objeto SO' de arestas (`MARCA_OBJETO_GUIAS`,
  hide_select) + EDGE; sem snap, `use_snap_selectable` o exclui.
  Snap anterior em `cabinet_parede_snap_2d` na cena: undo devolve a
  marca e o timer restaura; objeto marcado sem sessao e' removido.
  Cotas DXF (315): `_medir_vaos` da' Inferior/Superior; afastamento em
  `parede_afastamento_mm` (CHAVES_ASSOCIACAO): ponto gravado fica NO plano
  e `matriz_na_parede` soma a folga -- timer, arraste e insercao respeitam.
  Ima 2D (317): `acompanhar_arraste` so' marca `_movidos` sob `_transformando`;
  `encaixar_movidos` (timer, sem modal) gruda bordas e limita a' face.
  Preset solto em parede FORA do 2D (318): `_mover_contra_parede` usa
  `encaixar_na_face` + `matriz_na_parede` e associa no `_confirmar`.
  Mover 2D (319): o observador manda G (keymap do usuario) e PRESS num
  modulo a `OBJECT_OT_mover_na_parede`: `lado_sob` + `posicao_com_ima`
  (caixas, sem malha; o snap nativo nao pega "lado inteiro" e confundia
  quina da frente/fundo) e `encaixar_na_face`. Arraste espera o limiar.
  Cena real (321): `regiao_da_parede` em numpy (atributos `.corner_*`) e
  cache por FACE da regiao; `faixas_da_face` em lote. Nada de laco por face.
  Envelope 390: `caixa_local_do_modulo` usa `modulos.pecas_do_envelope` e cantos nominais, como a HUD; inclui apoios/molduras da porta pesada, exclui folhas abertas/puxadores. Nao usar o vao interno de portas para encaixar o grupo. Costas (324): `caixa_do_modulo` vem no referencial da PAREDE (giro de
  `parede_costas`, oposto a' porta); com ela use `referencial(conj)` e
  `escala_no_referencial`, nunca `matrix_world`. Medidas: `medidas_na_parede`.
  Cotas (368): A1/A2/A3 sempre no selecionado; A3 Prof. com chamada na quina.
  Resize oculta distancias; HUD via `_geometria_na_parede`/`_hud_na_parede`
  (so' bolinhas das bordas, `so_faces`; quina do snap ganha); observador
  deixa o clique para o gizmo; digitado vai no numero da cota (`digitacao_hud`).
- Solda manual usa translate/snap NATIVO compartilhado; cache KDTree ou consulta nativa da face, nunca varrer a malha no clique. Ancorar/Juntar registra afastamento 3D local ao destino (`adj_<ponta>_origens`). Legado: reset volta ao gap gravado. Criacao 352: reset zera pela ancora FINAL fixa, e esse zero vira a referencia futura; Alt reancora, sem trocar a referencia.
- Criacao 353: controladores e distancia tambem na previa; corrente remove so par pendente, regua por indice zera pela ancora final. Marcador/distancia leem cursor nativo. Auditoria de um modulo e somente leitura: menor distancia primeiro; um vertice pode atender destinos distintos. Refinamento 359: UM registro e UM par de vertices por par nao ordenado de OBJETOS. Juntas distintas continuam independentes, mesmo usando o mesmo vertice. Biblioteca usa KDTree em mundo para menor gap real; nao move malhas.
- Criacao: painel proprio sem Orcamento, distancia/zero/confirmar/cancelar/voltar. Direito/Esc cancela, Backspace/Ctrl+Z volta etapa; Alt escolhe outro vertice na mesma peca. Snap inicia no PRESS e confirma no RELEASE; entre gestos o modal recebe os atalhos. Previa numerica restaura antes de confirmar e no cancelar; so' `cabinet_juntar_modulo` grava undo da geometria final.
- `adj_<ponta>_manual` conserva corrente/regua/campo de distancia mesmo em zero; `direcoes` e origens sao locais ao destino. Caixa usa `cabinet_canto`; malha modelada usa INT POINT `cabinet_solda_vertice` (u), legado v aceito. ID apagado/ambiguo avisa, nunca escolhe outro por proximidade. Desligar/substituir limpa manual/direcoes tambem.
- `normalizar_ligacoes`: False preserva ancora/origem/direcao; True cadastra
  o menor gap atual na migracao explicita. `adj_<ponta>_restricoes` conserva
  encaixes axiais antigos nos dois extremos, sem outro fio ou registro.
  Manual nao cria juntas automaticas extras; destino repetido e' recusado.
- Regua (345): coordenador conserva a ordem dos dominios; portas/prateleiras
  evitam remontagens sem mudanca nos dados calculados, preservando BVHs e modelagem.
- Regua (347): valida destinos repetidos e pares da espessura ANTES de mover
  chapas ou atualizar sistemas. Junta impossivel cancela sem alteracoes;
  grupo valida todas as juntas antes da primeira escrita. Reusa o validador
  de `_puxar_por_pares`; deformacao calcula todos os deltas antes de aplicar.
- Clique (348): detector compartilha as correntes no evento; nome/UID/pai
  validos evitam buscas repetidas. Despachante nao grava undo: cada operador
  dono grava o seu; cancelamento da regua continua CANCELLED no clique externo.
- Criar solda (349): acesso proprio em Modulos/Montagem, no SOLTAR. Modulo
  escolhe a origem no primeiro snap; chapa individual a fixa. Estado so' nomes;
  snap/cursor/confirmacao sao os existentes, mantendo a pergunta no menu de origem.

- Solda (adjacencia): grava a folga = origem. Corrente/regua aparecem pelo DESVIO (> 5 mm
  na viewport, qualquer um no botao). Corrente e regua escolhem a MESMA peca pela selecao, nunca pelo lado que grava o vinculo. Regua: chapa ativa se move (pergunta se mudar medida);
  modulo ativo se adapta. Modulos: solda automatica exige area de apoio positiva (quina/aresta nao basta); chapas soltas mantem fecho legado. Limpar nome E UID da ponta; otimizar_adjacencia preserva ancoras manuais. HUD agrupa controles da mesma junta por espessura, sem apagar vinculos. Ctrl+D numa chapa: sem soldas (UID novo); F3 "Recalcular Ancoragem".

- Ancoras da solda: com Alt, arrastar a bolinha branca so' TROCA o vertice soldado
  (`adj_<ponta>_ancoras`); a geometria vai na regua: a ativa (de qualquer lado) anda pelas soldas
  NORMAIS e entorta o resto (canto + o do outro lado da E). Par encostado some; nova = de fabrica.

- Orcamento (VENDIDO, nada de "ERP"): fim das OPCOES, .txt da empresa, so' Moveis,
  falta = Pendencia. COMODO = PASTA no Outliner (a unica fonte), linha na Modulos.
  `cadastro_do_modulo` (300) le geometria avaliada nos eixos do grupo, folhas/gavetas existentes, tipos de dobradica e materiais das faces usadas.
  Nao persiste contagens no preset; portas abertas nao alteram o envelope.
  Material/tipo de dobradica ausente vira pendencia, nunca uma suposicao.
