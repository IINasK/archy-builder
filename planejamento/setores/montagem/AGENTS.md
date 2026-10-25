# Setor montagem e associacoes

Consulta explicita para `cabinet_creator/solda.py`, `paredes.py`,
`orcamento.py` e a filiacao em `modulos/`. Este guia nao e' herdado
por arquivos em outras pastas. Pares AGENTS.md/CLAUDE.md identicos.

## Onde alterar

| Tarefa | Entrada | Suite |
|---|---|---|
| Juntar ou desvincular chapa | `solda.juntar_conexao`, `solda.desagregar` | hud |
| Vinculo e pasta do modulo | `modulos.agrupar_chapas`, `_garantir_colecao_modulo` | operadores, hud |
| Regua, corrente, reset e ancora | `solda.py` operadores `cabinet_*`; HUD em `hud.py` | hud |
| Apoio em parede | `paredes.py` | paredes |
| Vista 2D/Local View, previa e distribuir modelos | `paredes_edicao.py` | paredes_edicao, gaveta |
| Cotas de modulo, larguras fixas, redistribuir/trocar modelo | `paredes_composicao.py` | paredes_composicao, hud |
| Comodo e arquivo vendido | `orcamento.py` | orcamento |

Leia tambem `cabinet_creator/modulos/AGENTS.md` para envelope, Collections
compartilhadas e dependentes; `planejamento/setores/interface/AGENTS.md`
para precedencia de clique e gizmos.
Paredes exigem tambem [integracao](../integracao/AGENTS.md): gesto DIREITO,
associacao a' face real, deslizamento G/R e guias editaveis pertencem la'.

## Decisoes e armadilhas

- Parede 2D (296): `paredes_edicao` guarda sessao numerica/nomes; Local
  View nativo preserva isolamento anterior e ocultacao manual. Orbita/Walk/Fly
  encerram; zoom/pan nao. Undo/abrir/salvar/unregister encerram antes de
  invalidar referencias. Getter Local View 4.2 usa objeto avaliado.
  Biblioteca insere pelo ponto de soltura, sem resize; duplo clique poe a'
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
  Cotas Promob (315): `_medir_vaos` da' Inferior/Superior; afastamento em
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
  Costas (324): `caixa_do_modulo` vem no referencial da PAREDE (giro de
  `parede_costas`, oposto a' porta); com ela use `referencial(conj)` e
  `escala_no_referencial`, nunca `matrix_world`. Medidas: `medidas_na_parede`.
  Cotas em 2 etapas (335): `modulo_em_edicao` (HUD) troca as distancias
  por largura/altura; HUD na parede via `_geometria_na_parede`/`_hud_na_parede`
  (so' bolinhas das bordas, `so_faces`; quina do snap ganha); observador
  deixa o clique para o gizmo; digitado vai no numero da cota (`digitacao_hud`).

- Solda manual usa o translate/snap NATIVO compartilhado e identifica MeshVertex por KDTree nativa, sem cantos nominais. Ancorar/Juntar preserva a posicao atual e registra o afastamento 3D por par no referencial do destino (`adj_<ponta>_origens`); Resetar volta a esse gap, nunca o zera. Trocar a ancora por Alt conserva a origem cadastrada da junta.

- Solda (adjacencia): grava a folga = origem. Corrente/regua aparecem pelo DESVIO (> 5 mm
  na viewport, qualquer um no botao). Corrente e regua escolhem a MESMA peca pela selecao, nunca pelo lado que grava o vinculo. Regua: chapa ativa se move (pergunta se mudar medida);
  modulo ativo se adapta. Modulos: solda automatica exige area de apoio positiva (quina/aresta nao basta); chapas soltas mantem fecho legado. Limpar nome E UID da ponta; otimizar_adjacencia preserva ancoras manuais. HUD agrupa controles da mesma junta por espessura, sem apagar vinculos. Ctrl+D numa chapa: sem soldas (UID novo); F3 "Recalcular Ancoragem".

- Ancoras da solda: com Alt, arrastar a bolinha branca so' TROCA o vertice soldado
  (`adj_<ponta>_ancoras`); a geometria vai na regua: a ativa (de qualquer lado) anda pelas soldas
  NORMAIS e entorta o resto (canto + o do outro lado da E). Par encostado some; nova = de fabrica.

- Orcamento (VENDIDO, nada de "ERP"): fim das OPCOES, .txt da empresa, so' Moveis,
  falta = Pendencia. COMODO = PASTA no Outliner (a unica fonte), linha na Modulos.
  `cadastro_do_modulo` (300) le geometria avaliada nos eixos do grupo, folhas
  e gavetas existentes, tipos de dobradica e materiais das faces usadas.
  Nao persiste contagens no preset; portas abertas nao alteram o envelope.
  Material/tipo de dobradica ausente vira pendencia, nunca uma suposicao.
