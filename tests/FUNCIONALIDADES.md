# Funcionalidades do Cabinet Creator e o teste de cada uma

Apresentacao publica e CC0 (405): README com boas-vindas, aviso de
desenvolvimento, instalacao e contribuicao; historico anterior preservado.
LICENSE usa o texto oficial CC0 1.0 e NOTICE delimita os direitos autorais
do projeto. O ZIP instalavel inclui ambos. Suite empacotamento (2) usa
pasta temporaria: confere licenca/creditos integrais, exclusao de backups,
cache e temporarios, e reconstrucao sem sobras da versao anterior.
Harness completo 4.2/5.2: 3414 testes em 80 execucoes OK
(dist/publicacao405-completo.log); pacote 405 confere LICENSE/NOTICE
integrais. Links locais e XML do banner de boas-vindas verificados.

Biblioteca de Alvenaria e vinculo reversivel (404): Editar primeiro,
laranja; olho nativo a' direita de Teto mostra/esconde os tres tipos,
contornos e nomes. Edicao independe desse olho. Cache numerico em copia
BMesh no timer; undo invalida e o timer normal reconstrui. Miniaturas
PNG das nove blocagens usam o cache de fotos existente; catalogo usa
filhos_de, cascata/lista flutuante e grade compartilhados da biblioteca.
Trilha e niveis independentes da biblioteca inferior. Parede/Piso/Teto
nao filtram modelos: portas podem deitar como alcapao; spots e pendente
associam-se aos tres tipos. Rebaixar teto conserva seu apoio especifico.
Arraste inicia no editor de origem, como preset. Raio nativo compartilhado
ignora a montagem e consulta Alvenaria; previa realca a face inteira com
cor/nome do tipo. DIREITO na peca encaminha ao mesmo posicionador; soltar
troca UID/face/pose e o corte. Original nao se move durante a previa.
Reassociar conserva identidade, modelagem, abertura e energia das luzes;
nao remonta componentes. Destino invalido ou excecao restaura o anterior.
Suite instalacoes (21): layout 190/320/564, olho e edicao forcada,
catalogo/fotos/cascata superior, modelos livres, porta no piso, luzes
nos tres apoios, raio/previa, Esc, soltura esquerda/direita, mesmo objeto
com faces diferentes, transferencia de recorte, rollback, conservacao de
modelagem/energia, salvar/reabrir e undo/redo da criacao/troca/olho. Testes
usam a pilha nativa e conferem o vinculo e os cortes depois de cada undo.
Regressao visual: primeiro suspenso cobria o titulo Instalacoes. Prova
falhou antes (dist/alvenaria404-titulo-antes.log); campo agora inicia
abaixo do titulo e o teste confere o intervalo de 8 px.
Auditoria GPU background 5.2, temas claro/escuro, tres larguras:
dist/alvenaria404-*-modelos.png e *-categorias.png; callbacks do olho em
dist/alvenaria404-faces-cima.png, *-baixo.png e *-ocultas.png.
Icone nativo conferido pelos metadados HIDE_ON/HIDE_OFF (gizmo nao e'
desenhado na prova offscreen). Sem gestos fisicos ou janela de teste;
projeto aberto e biblioteca real preservados.
Harness completo Blender 4.2/5.2: 3410 testes em 78 execucoes OK
(dist/alvenaria404-completo-final.log). Sem alteracoes nos snapshots: os
controles novos aparecem somente no contexto da Alvenaria.

Tipos de Alvenaria (403): aba propria, com Parede/Piso/Teto e instalacoes;
Modulos conserva edicao 2D/categorias. Criar Alvenaria vem primeiro e
somente para malha nao cadastrada. Selecao mista ignora o apoio existente,
inclusive quando ele e' o ativo. Escolher tipo abre o seletor nativo;
cores/nome por face somente durante essa edicao. Confirmar selecao e
Enter gravam a mesma operacao; Esc nao cadastra nem altera os tipos.
Editar preseleciona as faces; retirar uma preserva os outros tipos e a
mesma malha. Legado materializa a classificacao por normal antes de
editar. Categorias de ambiente nao agrupam lados diferentes no seletor
de tipos. Dois cliques com Shift somam duas faces nativas sem repintar
categorias. Suite alvenaria 5 -> 16; interfaces existentes atualizadas.
Regressao: selecionar com A nativo e confirmar antes do proximo timer
recusava a selecao. Confirmacao agora le diretamente a selecao nativa;
teste falhou nas duas versoes antes e passou depois:
dist/alvenaria403-confirmacao-antes.log e *-depois.log.
Auditoria GPU background 5.2: menus em 190/320/564 px, temas Dark/Light,
dist/alvenaria403-*-modelos.png, *-piso.png, *-teto.png, *-confirmar.png,
*-modulos.png, *-porta.png e *-forro.png. Cubo com os tres tipos pelo
callback real: dist/alvenaria403-faces-cima.png e *-baixo.png; escala de
UI 1 na fixture (background retorna 0). Nomes e oclusao conferidos.
Sem janela, gestos fisicos ou mudanca no projeto aberto/biblioteca.
Harness completo Blender 4.2/5.2: 3368 testes em 76 execucoes OK
(dist/alvenaria403-completo-final.log). Pacote 403: 45 fontes identicos
ao repositorio; espelhos e limites dos guias conferidos.

Eletrica e forro (402): tomadas/interruptores com espelho, spots embutidos
ou sobrepostos e pendente vertical. Rebaixo pela regiao do teto ou por
faces selecionadas, inclinado ou plano; tabica e luz linear por lado.
Suite iluminacao: furo e direcao em piso/parede/teto, luzes seguindo
rebaixo e retornando ao teto original, tabica parcial, salvar/reabrir,
undo/redo e cartoes por superficie em 190/320/564 px.
Auditoria GPU em Blender 5.2 background, temas Blender Dark e Light:
dist/instalacoes402-*-modelos.png, *-porta.png e *-forro.png.
Regressao visual: o titulo Instalacoes cobria parte do seletor do apoio.
O teste do painel completo verifica que titulo e seletor nao se sobrepoem.
Regressao: recorte precisa do referencial do apoio (a implementacao de
parede pressupunha Z vertical). Remover forro transfere somente as luzes
com vinculo, antes de excluir a malha ou os cortadores.

Esquadrias (401): porta de giro, janela de correr e porta de sacada com
cartoes arrastaveis, cotas e abertura. Suite esquadrias: corte em casca e
volume, restauracao, vao existente, resize sobre degrau, escala nativa,
inverter/espelhar, colisao no meio do giro, armario alto e layout.
Regressao do corte de casca: o Boolean Exact pode devolver tampas marcadas
do cortador em faces sem volume. Filtro de faces nativo deixa o vao aberto.
Aviso usa a passagem e a varredura da folha sem bloquear o armario.

Alvenaria (400): Parede/Piso/Teto em faces da mesma malha, compatibilidade
por normal, cotas editaveis e vinculo que acompanha o apoio. Suite
alvenaria: classificacao sem recriar malha, normal legada, cota e
translacao, perda de face e menu nas tres larguras.

Categorias e selecao nativa na mesma vista 2D (399): nome aplica a todas
as faces; so' remove quando todas ja' possuem a categoria. Selecao mista
recebe a escolhida. Sem categoria limpa sem quadrado/registro vazio;
repetir nao altera outras faces. Olho ao lado de Sair alterna cores e
nomes sem alterar categorias/selecao. Automatico escolhe area cadastrada
ou superficie plana livre; entrada 2D restringe ao plano clicado.
Shift individual, Ctrl percurso e Shift+Ctrl preenchimento usam motor
nativo. Grade 3x3: percurso 0->8 seleciona 5 faces; preenchimento, 9.
Regressao da integracao nativa: indice apenas da face cancelava o comando
(1 face selecionada); somar vertices+arestas produz 5/9. Capturada em
dist/ambientes399-novos.log, corrigida em ambientes399-corrigido.log.
Alvo original fora do Local View participa so' durante o operador, sem
redraw; camera/isolar/proxy/sessao e ocultacao anterior sao preservados.
Editar categorias no 2D abre lista completa sem sair do 2D. Acerto/previa/
cores recortados na area ativa, inclusive face parcialmente sobreposta;
classificacao continua na face nativa inteira, sem criar geometria.
Furo no centro da grade: Ctrl contorna 5 faces, nao cruza a face excluida.
Ctrl sem caminho nao derruba selecao; modificadores despacham corretamente.
Cenarios extras: cliques rapidos conservam BVH; Tab fecha so' categorias;
undo limpa handlers/proxy, trocar cena conserva a selecao da cena nova.
Suite ambientes 47 -> 61; fixture GUI atualizada para Shift individual.
Dirigidas 4.2/5.2: 908 testes / 18 execucoes OK
(dist/ambientes399-setores.log). Auditoria GPU isolada com tuplas/helpers
reais: dist/ambientes399-menu.png, larguras 190/320/564. Olho nativo
validado pelos metadados HIDE_OFF/HIDE_ON; gizmo nao desenhado nessa prova.
Callbacks reais em dist/ambientes399-faces.png verificam cores limitadas
ao recorte e selecao ainda visivel com olho desligado. Sem abrir janela,
recarregar add-on em uso ou modificar cena real/biblioteca. Gestos fisicos
na GUI nao executados.
Harness completo 4.2/5.2: 3306 testes / 70 execucoes OK
(dist/ambientes399-completo.log). Pacote 399 com 41 fontes identicos;
espelhos e limites conferidos.

Categorias manuais e dois modos da Alvenaria (398): Editar em 2D/Editar
categorias lado a lado, Desagregar Alvenaria vermelho abaixo em linha
inteira; Definir Alvenaria permanece laranja. Nome do comodo aplica nas
faces selecionadas ao SOLTAR, com operador UNDO e nome explicito; nao ha'
Definir como. Quadrado so' edita cor; saida/retorno ocupa toda a linha.
Selecao 2D nao mistura lista de categorias. Tab retorna pelo modo 2D;
reabrir categorias nao confunde esse retorno com uma nova edicao.
Faces existentes mantem categoria ao mover vertices/remover vizinhas.
Novas faces nao herdam categoria por duplicacao (inclusive coincidente)
ou subdivisao; face reaproveitada pelo Blender continua sendo existente.
Captura transitoria de wrappers BMesh nativos e identidade Python, nunca
IDs RNA ou inferencia por coordenadas. Liberada ao sair/undo/save/abrir/
unregister. CustomData FACE novo realoca wrappers: a captura e' renovada
apos criar a camada, antes da pintura. Caches sem mudanca nao releem malha.
Regressao de heranca: teste observa a copia nativa com categoria 1 antes
do update e verifica 0 apos o observador; clique manual muda para Quarto.
Suite ambientes 38 -> 47: layouts 190/320/564, nome no soltar com operador
real, cor vermelha apenas na desagregacao (ramo real do desenho), faces
novas/vizinhas/movidas, liberacao, subdivisao/undo/redo e dois contextos.
Dirigidas 4.2/5.2: 564 testes / 12 execucoes OK (ambientes398-alvos.log).
Regressao adicional: apoio/arraste passa contexto parcial sem mode; sensor
de faces consulta contexto nativo, preservando a API antiga do cache.
Dirigidas finais: 790 testes / 16 execucoes OK (ambientes398-alvos2.log).
Auditorias GPU isoladas: dist/ambientes398-menu.png, com tuplas e ramo de
cor reais; dist/ambientes398-faces.png, callback real confirma cores das
faces existentes intactas e nova face cinza ate' a acao manual. Dados da
cena temporaria passam de [1,2,0] para [1,2,2]. Sem abrir janela/recarregar
o add-on em uso ou alterar a cena real. Gestos ao vivo nao executados.
Harness final 4.2/5.2: 3278 testes / 70 execucoes OK
(dist/ambientes398-final.log). Pacote 398: 41 fontes identicos;
espelhos/limites conferidos.

Entrada unica da Alvenaria (397): retirado Editar ambientes do menu
inicial. Editar parede e Remover Alvenaria continuam lado a lado; contexto
interno de ambientes preservado. Cenarios existentes atualizados ao pedido:
larguras 190/320/564 px, uma unica entrada Editar parede, nenhuma entrada
Editar ambientes e nenhum seletor de metodos/pontos. Suite ambientes
conserva 38 casos; navegacao e selecao nao mudaram.
Dirigidas Blender 4.2/5.2: 420 testes em 6 execucoes OK
(dist/ambientes397-alvos.log). Auditoria visual com tuplas reais e helpers
GPU: dist/ambientes397-menu.png, tres larguras sem a linha redundante.
Sem abrir janela nem alterar a cena em uso; gestos ao vivo nao executados.
Harness completo 4.2/5.2: 3260 testes / 70 execucoes OK
(dist/ambientes397-completo.log). Pacote 397: 41 fontes identicos;
espelhos/limites conferidos.

Selecao unificada da Alvenaria (396): Editar parede conserva vista 2D;
Editar ambientes abre diretamente a lista de comodos no Edit Mode, sem
alinhar camera. Ambos abrem selecao nativa de faces; hover automatico
mostra regiao plana conectada, Ctrl mostra uma face. Clique automatico
escolhe a regiao; Ctrl+clique soma/retira faces individualmente. No caminho
2D, automatico abre a vista e Enter confirma o manual. Nenhum controle
Automatico/Por pontos/Confirmar area/Remover ultimo ponto/Cancelar selecao
no menu. API antiga dos pontos preservada para compatibilidade, sem UI.
Previa e selecao sao independentes; mover ao menu nao perde selecao manual.
BVH e dissolve nativos em copia BMesh, preparados na entrada e no timer
apos invalidacao; hover/clique nao refazem BVH. Selecao vinculada somente
a Alvenaria, ignorando teto/objetos externos. Ctrl respeita faces reais,
sem inferir face vizinha so' por vertices selecionados. Timer/handler/cache
sem referencias RNA, limpos em Tab, Esc, cena, undo e unregister.
Suite ambientes 24 -> 38: layout nas tres larguras, duas invocacoes,
camera, planos conectados, Ctrl soma/retira, origem fixa/ocultacao, hover
sem mutacao/reconstrucao, navegacao/menu, Enter e clique 2D, Tab/undo nativo,
invalidacao apos mover vertices e troca de cena. Teste GUI de pontos foi
atualizado ao novo gesto Ctrl/Enter; sintaxe verificada, janela nao rodada.
Auditoria GPU isolada: dist/ambientes396-menu.png (tuplas reais nas tres
larguras) e dist/ambientes396-previa.png (callback real, regiao de duas
faces vs uma face com Ctrl; 64800/32400 pixels). Sem alterar cena em uso,
abrir janela ou recarregar add-on. Dirigidas: 626 testes / 14 execucoes OK
antes dos casos finais; 74 / 2 depois, Blender 4.2 e 5.2.
Regressao adicional: dissolve nativo conserva varias faces para manter um
furo. A previa agrupava so' uma delas e omitia parte da regiao. Teste
reproduzido antes da correcao (dist/ambientes396-furo-antes.log); agora
8 m2 da regiao aparecem, com abertura real de 1 m2 vazia. Agrupamento so'
na preparacao do cache. Auditoria GPU dist/ambientes396-furo.png mostra
54000 pixels no automatico e 6750 na face manual, sem cobrir o furo.
Dirigidas finais: 166 testes / 4 execucoes OK.
Harness final completo: 3260 testes / 70 execucoes, Blender 4.2 e 5.2,
tudo OK (dist/ambientes396-final.log). Antes da regressao do furo, 3258
tambem passaram (dist/ambientes396-completo.log). Pacote 396: 41 fontes
identicos; espelhos/limites conferidos. Gestos ao vivo nao executados.

Linha de acoes dos ambientes (395): Sair da edicao de ambientes (ou Voltar
a edicao da parede) e Definir como Cozinha/etc lado a lado, laranja padrao
do menu. Colunas iguais, 6 px de intervalo e 28 px de altura; lista de
ambientes abaixo. Operadores existentes, sem mudar atribuicao ou retorno.
Suite ambientes 23 -> 24: cenario com e sem retorno nas larguras de area
190/320/564 px verifica limites, alinhamento, operacao e destaque laranja.
Falha anterior capturada como expectedFailure em dist/ambientes395-antes.log.
Dirigidas Blender 4.2/5.2: 392 testes em 6 execucoes OK.
Auditoria visual GPU isolada em dist/ambientes395-menu.png: mesmas
tuplas reais nas tres larguras, com e sem retorno; botoes laranja e
lado a lado. Nenhuma janela aberta ou alteracao na cena em uso.
Harness completo 4.2/5.2: 3232 testes em 70 execucoes OK
(dist/ambientes395-completo.log). Pacote 395 com 41 fontes identicos;
espelhos/limites conferidos. Gestos na interface ao vivo nao executados.

Realce e menu de ambientes (394): listras reproduzidas como disputa de
profundidade entre a cor e a face nativa, nao como duplicacao da malha.
Prioridade somente no depth pela matriz de projecao GPU nativa; pilha
restaura a matriz inclusive em excecao. Sem deslocar vertices, materiais,
X/Y da projecao ou gerar shaders proprios. Cubo conserva 8 vertices,
6 faces e 12 triangulos unicos no cache. Antes: falha registrada em
dist/ambientes394-antes.log; regressao automatizada cobre as duas projecoes.
Editar parede e Remover Alvenaria ocupam colunas iguais; Definir Alvenaria
continua linha inteira. Editar ambientes aparece dentro da edicao da
parede, usa Edit Mode nativo e volta ao mesmo recorte. Tab nativo conserva
o retorno; falha de entrada restaura a parede; estado numerico/nome e'
limpo na invalidacao existente. Novo operador dispara no SOLTAR.
Suite ambientes 17 -> 23: projecao/restauracao, topologia/cache, layout em
larguras 190/320/564, ida/volta nativa com recorte, Tab e falha simulada.
Auditoria GPU nativa isolada: defeito anterior reproduzido e cobertura de
cor 100% em perspectiva e ortografica, com oclusor frontal preservado
(dist/ambientes394-gpu.png e .json). Tuplas reais do menu renderizadas
pelos helpers GPU em dist/ambientes394-menu.png nas tres larguras.
Sem abrir janela, recarregar add-on ou modificar cena/biblioteca real;
gestos na viewport ao vivo nao executados. Harness completo Blender
4.2/5.2: 3230 testes em 70 execucoes OK (dist/ambientes394-entrega.log).

Alvenaria, apoio e ambientes (393): marco explicito na malha pelo botao
Definir Alvenaria. Raycast nativo ignora todos os objetos nao definidos;
um unico bloco pode conter paredes/faces opostas, piso e teto. Tipo pela
normal mundial; teto nao vira apoio de armario. RMB em parede/piso nao
recusa por tamanho/ocupacao nem deforma o modelo. Biblioteca herda a
mesma regra na face definida. Confirmar reler marco/face; Esc restaura.
Piso conserva giro em Z, base apoiada, roda de 90 graus, segue apoio.
G nativo registra afastamento; zero e movimento negativo respeitam plano,
com cotas dinamicas e Mesh intacta. Undo/redo e salvar/reabrir cobertos.
Sinal numerico de tres pulsos e limpeza do timer reservado a avisos
futuros; nao disparado por tamanho e nao implementa aberturas.
Suite paredes 21 -> 39: marcacao/desmarcacao, alvo nativo atraves de
oclusores, bloco completo, sobra/sobreposicao permitidas, piso horizontal,
G/cotas/zero, cache, roda/Esc, persistencia e pulsos isolados. Regressao
do G que voltava ao plano reproduzida em dist/apoios393-antes.log.
Suite ambientes (17): faces nativas INT/selecionadas sem trocar malha ou
materiais; presets/UIDs/cores; copia compartilhada isolada; selecao vazia;
parede/piso levam a Cozinha, G muda para Quarto, renomear pasta por UID;
lista quadrado/nome; paleta so' no soltar; cor preserva outro ambiente e
propaga a UID comum; retangulo cabe inteiro inclusive contorno concavo;
cache nativo dissolve somente copia e ignora geometria externa; cores
ocultas em Object Mode; salvar/reabrir/undo/redo. Orcamento e Collections
nativos reaproveitados, sem nova hierarquia de modulos ou materiais.
Testes anteriores de entrada agora explicitam marco da Alvenaria;
contrato de recusa nos arrastes foi atualizado para colocacao livre.
Dirigidas: 742 testes / 18 execucoes OK antes dos cenarios finais da paleta.
Auditoria: cena descartavel exporta cache/tuplas reais; callback desenhar
e rotulo executados com captura de primitivas em background. Cozinha e
Quarto presentes; Lavanderia estreita omitida. Conferencia em
dist/alvenaria393-primitivas.png (diagrama de primitivas, nao screenshot).
GPU da instancia aberta indisponivel (conexao recusada); nao abriu janela
nem alterou projeto/biblioteca real. Gestos GUI reais nao executados.
Validacao final: 3218 testes em 70 execucoes, Blender 4.2/5.2, tudo OK
(dist/alvenaria393-fechamento.log). Nova suite ambientes 17, paredes 39;
travas de estrutura/organizacao preservadas, snapshots sem alteracao.
Pacote 393 com 41 fontes Python conferidos; guias espelhados/limites OK.

Edicao previsivel dos campos (392): entrada sem selecao automatica, cursor
no fim; Backspace apaga um caractere. Ctrl+A e Shift+setas/Home/End
selecionam texto, com realce sobre os caracteres editaveis, sem unidade
automatica nem resultado. Clique/Shift+clique nas caixas do menu/HUD
posiciona/estende; seta simples colapsa selecao para a borda. Ctrl+Z e
Ctrl+Shift+Z/Ctrl+Y usam historico local de ate' 80 edicoes, com cursor e
selecao restaurados; nova escrita apos undo descarta redo. Nenhuma escrita
aplica geometria antes de confirmar. Cota de parede nao insere unicode de
atalho. Trocar distancia por quantidade via scroll descarta historico antigo.
Suite medidas sobe 13 -> 21: regressao do Ctrl+Z (antes inseria z ou era
ignorado), entrada/Backspace do menu/HUD, trecho/teclado/undo, realce com
milhar excluindo unidade/resultado, rotas reais de modal do menu/HUD e
duas cotas de parede. Falhas antes: dist/medidas392-antes.log. Cenario de
unidades preserva parser nativo: 100 + 50CM = 600 mm / 150 cm / 100,5 m
conforme opcao MM/CM/M; sem unidade usa padrao, nao unidade do vizinho.
Teste inline antigo agora faz Ctrl+A explicitamente antes de substituir.
Dirigidas 4.2/5.2: 830 testes / 10 execucoes OK (dist/medidas392-alvos2.log).
Auditoria visual GPU: dist/medidas392-campos.png, funcoes reais extraidas
do fonte em namespace isolado. Confere menu e HUD: Backspace, Ctrl+A,
trecho por Shift, conta mista e Ctrl+Z. O teste revelou que wcol_text do
tema era quase preto; usa inner_sel de wcol_regular (botoes nativos), com
contraste sobre caixa preta/cinza. Sem recarregar o add-on em uso, abrir
janela ou alterar cena/biblioteca. Gestos na interface ao vivo nao executados.
GUI preparada: substituicoes digitadas fazem Ctrl+A explicito; cenario do
campo exercita Backspace de 600 para 60, Ctrl+Z para 600, Ctrl+A e seta
para desfazer selecao antes da conta. Sintaxe conferida; janela nao rodada.
Validacao final apos contraste: Blender 4.2/5.2, 3148 testes em 68 execucoes,
tudo OK (dist/medidas392-final.log). Pacote 392 com os 40 fontes Python
identicos ao projeto; espelhos/limites dos guias conferidos. Snapshot intacto.

Medidas durante digitacao e caixas arredondadas (391): apresentacao em
portugues (milhar ponto, decimal virgula), unidade MM/CM/M da configuracao,
zero antes da fracao e sem zeros artificiais. Mantem buffer original para
nao converter 1234 digitado em decimal 1.234 ao exibir o milhar. Mapa do
cursor conserva cliques/setas/insercao/Backspace. Parser nativo conserva
contas/unidades; aceita tambem texto colado com milhar e virgula. Ponto
unico no buffer original continua decimal, por compatibilidade. Previa
da conta editavel ao lado do texto; resultado/cursor cacheados por texto
e unidade (128), limpos no unregister. Incompletas/erros da previa nao
poluem console. Nomes, contadores, pixels e angulos nao recebem mm.
Aplicado a menu, HUD, cotas/guias de paredes; caixa preta reutiliza raio
4 escalado do menu. Snapshot: 28 rotulos mudaram, sem alterar geometria.
Suite medidas (13): exemplos 1/.1/1234/12345/12345.67/comma, MM/CM/M,
conta .2+.5, mistura m/cm, erro/incompleta, mapa do cursor, teclado/colar,
cache (20 desenhos = 1 calculo), troca de unidade, tipos e cantos.
Falhas antes em dist/medidas391-antes.log. Dirigidas: 814 testes / 10
execucoes OK; preflight sem biblioteca: 2964 / 66 OK nos dois Blenders.
Viabilidade da oclusao parcial: prova GPU isolada, sem objetos/cena ou
viewport alterados (dist/provar_gpu391.py; dist/gpu391-parcial.png). BLF
e profundidade nativos esmaecem so' parte de texto/linha encoberta.
RTX 4070 SUPER/OpenGL: mediana de 5 amostras, 40 quadros/amostra, quatro
cotas/quadro: atual 0.2294 ms, duas passagens 0.3853 ms (+0.1559 ms).
Nao e' custo zero; efeito NAO habilitado, conforme a condicao do usuario.
Medicao isolada nao garante mesmo custo em outras GPUs/cenas. Sem janela
nova, gestos ou mudanca no projeto aberto; biblioteca preservada.
Validacao final: Blender 4.2/5.2, harness completo 3132 testes em 68
execucoes, tudo OK (dist/medidas391-entrega.log). Auditoria visual GPU
das caixas reais isoladas: dist/medidas391-caixas.png, seis entradas
conferidas, incluindo cursor, unidade, milhar, fracao e conta. Pacote
391 conferido contra todos os fontes; guias espelhados e limites mantidos.

Encaixe na parede pelo envelope completo do grupo (390):
caixa_local_do_modulo usava portas._limites_locais_modulo, que mede apenas
a carcaca para construir a porta. Agora consulta modulos.pecas_do_envelope
e os cantos nominais compartilhados com a HUD, incluindo molduras/apoios.
Nao modifica o vao interno usado pelas portas. Referencial local evita
inflar a caixa quando o grupo esta girado; giro das costas continua comum.
Arraste, biblioteca, cotas, encaixe e obstaculos herdam a mesma referencia.
Folhas abertas, puxadores e copias de chapas fora do modulo ficam fora.
Regressao: CORRER com moldura 15, rodape 100 e testeira 80. Antes, apoio
lateral atravessava 15 mm e a base 115 mm; teste falha com o codigo antigo
(dist/parede390-antes.log). Suite paredes +5 (piso 16 -> 21): caixa vs
bound_box nativo das pecas, vao estrutural conservado, modulo girado/quatro
costas, exclusoes, limites da parede/cotas e contato entre duas molduras.
Dirigidas: 878 testes / 10 execucoes em 4.2/5.2, tudo OK
(dist/parede390-alvos2.log). Cenas temporarias, projeto aberto conservado.
Cena aberta auditada SO' em leitura: addon carregado 389, seis apoios,
estrutura 1300 x 2503 x 550 mm; envelope aprox. 1330 x 2571.921 x 649.073 mm.
Confirma a divergencia real sem mover objetos/recarregar o add-on na sessao.
Entrega: 3106 testes / 66 execucoes, tudo OK em 4.2/5.2
(dist/parede390-entrega.log). ZIP 390 conferido contra 40 fontes, espelhos
identicos e biblioteca preservada. Sem gestos/alteracoes na janela aberta.

Reposicionar puxadores sem sobreposicao (389): Alt recusa destino ocupado
antes de mudar pai/props ou refazer puxador/madeira. Usa `_lugar_do_puxador`,
a mesma referencia numerica da montagem: compara ancora efetiva (tolerancia
0.1 mm) e intervalos de comprimento na mesma borda/face. Considera o limite
das pontas, inclusive quando duas fracoes diferentes resultam no mesmo lugar.
Mais de um puxador na chapa permitido em posicoes separadas ou face oposta;
outro objeto nao bloqueia. Ocultar o vizinho nao libera sua posicao. Nao
apaga o perfil existente ao confirmar. Esc devolve origem mesmo quando uma
cena legada ja' tinha duplicatas. Mensagem no cabecalho nativo, sem pop-up;
destino recusado conserva o ultimo lugar valido. Sem nova varredura de malhas.
Reproducao em cena temporaria: duas ALCA, Y+ e X+, arrastar primeira a X+
produzia distancia 0.0 (dist/puxador389-antes.log). Oito cenarios novos na
suite puxadores (piso 32 -> 40): coincidencia, proximidade, ponta limitada,
mesma borda separada, face oposta/outra chapa, chapa girada, proprio puxador,
oculto, ALCA/BORDA, perfil conservado e cancelamento com legado. Falhas antes
da correcao em dist/puxador389-regressoes-antes.log; dirigidas 640 testes /
8 execucoes, tudo OK em 4.2/5.2 (dist/puxador389-alvos.log).
Reproducao original passa depois (dist/puxador389-depois.log). Entrega:
3096 testes / 66 execucoes, tudo OK em 4.2/5.2 (dist/puxador389-entrega.log).
ZIP 389 conferido contra as 40 fontes Python e guias espelhados; biblioteca
preservada. Sem gestos com janela nem alteracao no projeto aberto.

Faixa contextual de visibilidade (388): referencia visual com rotulo simples
Visibilidade de objetos a esquerda e dois botoes so' icones (olho/lapis),
36 x 30 px, alinhados a direita; texto curto em coluna estreita. Continua
fixa junto a biblioteca, sem rolar. Somente com modulo/peca compativel
selecionado; objeto comum, sem selecao, aba Puxadores e ferragem isolada nao
mostram nem reservam a faixa. Durante o editor, o alvo fixado conserva os
comandos mesmo selecionando um extra. Reutiliza a classificacao de ferragens
de materiais.protegida_no_grupo. Sem alteracao no arame, snap ou agrupamento.
Suite visibilidade 26: layout em 220/320/480 px, centro nativo dos icones,
selecao compativel/incompativel, reserva condicional e biblioteca no topo.
Registro visual anterior recusado por test_faixa_segue_referencia...
(dist/visibilidade388-antes.log). Snapshot atualizado para o novo contrato.
Auditoria das coordenadas em dist/visibilidade388-layout.png (diagrama,
icones ilustrativos; sem janela). Entrega: 3080 testes / 66 execucoes,
tudo OK em 4.2/5.2 (dist/visibilidade388-entrega.log). ZIP conferido contra
40 fontes; espelhos identicos, 36 snapshots revisados e biblioteca preservada.

Grupos visuais por aba (387): substitui o olho da linha Criar da 386 por
faixa fixa de 38 px junto a divisoria da biblioteca; Esconder/Mostrar partes
e Editar grupo, icones nativos olho/lapis e texto. Biblioteca no topo usa
a faixa acima do rodape. Sem selecao e depois de cancelar, a faixa permanece;
em ferragens isoladas fica desabilitada. Campos e biblioteca rolam sem move-la.
Portas inclui folhas/molduras/bases/trilhos/ferragens; Gavetas inclui caixa,
frente, puxador e trilhos; Prateleiras/Divisorias juntas; Fundos; Modulos
esmaece a estrutura. WIRE nativo branco/opacidade .22; malha, materiais,
espessuras, parentesco e H/Alt+H preservados. Propriedades de arame/overlays
da viewport sao temporarias, inclusive se estavam desligados; alteracao
manual do usuario nao e' sobrescrita ao sair. Nao afeta render final.
Lapis usa view3d.select nativo: esquerdo inclui peca/agregados, direito
retira, Enter/lapis conclui, Esc devolve selecao/configuracao. UIDs guardados
no modulo, sem Collection paralela/reparentear. Navegacao/menu liberados;
erro/undo/load/unregister liberam o editor. Save pre/post suspende/retoma
o visual, sem gravar aparencia temporaria no arquivo. Grupos sobrepostos
restauram uma peca so' depois do ultimo desligar. Pergunta antes dos internos
conservada: Sim esmaece PORTAS pelo mesmo controlador, Nao conserva a vista.
Raio superficial atravessa o arame para acessar o interior; vertices reais
e extras do grupo permanecem nos alvos do snap nativo, sem copias de malha.
Suite visibilidade: 24 cenarios nos dois Blenders; inclui moldura de correr,
gavetas com trilhos, internos, UID renomeado, extra com filhos, sobreposicao,
H/Alt+H, guarda undo, exclusao, save/copia nativa, restauracao, raio nativo,
cancelamento/erro/menu/navegacao do editor e faixa fixa mesmo sem selecao.
Regressao do desaparecimento falhou na 386 (0 botoes, esperados 2):
dist/visibilidade387-antes.log. Areas_criacao conserva piso 58 com contrato
do arame/undo atualizado. Gaveta/estrutura conferem botoes fixos desabilitados,
recorte/rolagem e prioridade do painel de opcoes. Barra curta conserva curso
e clique no trilho. Snapshot revisado: faixa nova e coluna reservada a barra.
Auditoria de layout exporta coordenadas reais em 220/320/480 px; diagrama
dist/visibilidade387-layout.png, com icones ilustrativos. Sem captura/gestos
na janela ou edicao da cena aberta; cenarios temporarios, biblioteca intacta.
Entrega: 3076 testes / 66 execucoes nos Blenders 4.2 e 5.2, tudo OK
(dist/visibilidade387-entrega.log). ZIP 387 conferido byte a byte contra
as 40 fontes Python; espelhos identicos e limites de linhas conservados.

Portas na criacao de internos (386): modulo alvo com portas visiveis recebe
Esconder portas? Sim/Nao antes da captura de pontos ou volume livre.
Sim esconde a montagem inteira (folhas, molduras, puxadores e ferragens);
Nao conserva a visibilidade escolhida pelo usuario. Sem portas visiveis,
seguir direto. O olho divide a linha Criar em texto e icone nativo de 30 px;
fica acessivel durante o assistente e a referencia de volume. Alterna por
hide_set da View Layer, sem manter estado paralelo ou reocultar por timer.
Mostrar e' comando explicito para as portas; nao mostra controles/furos do
rig nem altera hide_render, colecoes, fundo/base/corpo ou outro modulo.
Alvo segue o modulo do assistente, mesmo com referencia temporaria ativa.
Porta ativa oculta devolve o modulo como alvo; contexto antigo e' recusado.
H/Alt+H continuam nativos; cancelamento/undo/load limpa pergunta pendente.
Areas_criacao +16: perguntas antes dos tres dominios e volume, Sim/Nao,
limite do modulo, outro armario preservado, olho/cotas no painel estreito,
icone por visibilidade real, rig protegido, H/Alt+H, undo/redo, alvo da area,
folha ativa, sem portas, pergunta na gaveta, contexto antigo e limpeza.
Captura entre cliques repassa hide_view_set/hide_view_clear pelo matcher do
keymap do usuario, inclusive remapeado. Regressao falhou com a guarda antiga
(portas386-h-repro.log). Responder na gaveta conserva ali as proximas
perguntas, com fluxo real do respondedor e restauracao da origem ao sair.
Cobertura do operador novo e flags SKIP_SAVE.
Auditoria dos retangulos reais em 220/480 px, sem sobreposicao: arquivo
dist/portas386-layout.png (simbolo ilustrativo, nao captura da janela).
Gestos com janela nao executados; cenas temporarias, biblioteca preservada.
Validacao final: 3028 testes / 64 execucoes, tudo OK nos Blenders 4.2/5.2
(dist/portas386-entrega.log). ZIP 386 conferido contra as 39 fontes Python.
Uma execucao intermediaria falhou no undo de paredes 4.2; a rechecagem
isolada e a final passaram sem alterar a suite ou o codigo de paredes.

Hierarquia gaveta/puxador (385): clique no conjunto continua global; duplo
na frente/corpo seleciona so' uma unidade. Esse escopo selecionado libera
clique simples no proprio puxador. Duplo direto no puxador tambem isola;
clicar no acessorio ja' ativo conserva foco. Regra aplicada antes do ramo
da parede, sem contador global de cliques ou alterar selecao nativa comum.
HUD +6: frente e fundo da unidade -> puxador/aba, duplo direto, acessorio
ja' ativo, escopo em parede, puxador de outra unidade sem herdar foco,
PRESS/CLICK em objetos comuns e parede generica pelo caminho nativo.
Tres regressoes falharam antes (gestos385-repro.log); os demais cenarios
preservam contratos. Testes de aba usam cleanup; cena aberta preservada.
Validacao direcionada: 906 testes / 10 execucoes, tudo OK nos Blenders
4.2/5.2 (gestos385-cenarios.log). Gestos fisicos na janela nao executados.
Harness completo: 2996 testes / 64 execucoes, tudo OK nos Blenders 4.2/5.2
(gestos385-completo.log). ZIP 385 conferido contra as 39 fontes Python.

Selecao multipla de unidades de gaveta (384): apos duplo clique isolar uma,
Shift+clique em outra do mesmo vao soma somente essa unidade. Shift+duplo
remove a selecao global daquele vao antes de isolar, pois o primeiro PRESS
pode ter somado o conjunto inteiro; outros objetos/grupos ficam selecionados.
Clique simples sem Shift continua global; portas/puxadores mantem gestos.
HUD +3: sequencia real das props do keymap PRESS/DOUBLE_CLICK/Shift, duas
unidades com Tab nativo sem incluir a terceira, Shift+duplo conservando
objeto externo e selecao individual, volta ao conjunto por clique simples.
As duas primeiras reproduziram a falha anterior (selecao384-repro.log).
Helper restaura a aba do menu por cleanup, sem contaminar os outros testes.
Validacao direcionada: 658 testes / 6 execucoes, tudo OK nos Blenders 4.2/5.2
(selecao384-cenarios.log). Gestos fisicos na janela nao executados.
Harness completo: 2984 testes / 64 execucoes, tudo OK nos Blenders 4.2/5.2
(selecao384-completo.log). ZIP 384 conferido contra as 39 fontes Python.

Tab em gaveta individual (383): selecao.malhas_para_editar reconhece
eh_gaveta, alem do conjunto eh_grupo_gavetas. A mesma entrada de grupos
abre caixa e puxador no Edit Mode multiobjeto nativo, sem incluir outras
gavetas nem subir ao modulo. Selecao/ativo sao restaurados na saida;
varias unidades selecionadas conservam escopo e isolamento de Mesh.
Operadores +3: unidade com caixa/puxador e tres ciclos Tab, duas unidades
com malha compartilhada por objeto externo, undo/redo com recuperacao da
selecao individual. As tres regressoes falharam antes no poll do operador
(tab383-repro.log); 118 testes passaram apos corrigir nos Blenders 4.2/5.2
(tab383-operadores-final.log). Cena aberta consultada somente para leitura;
gesto Tab na janela nao executado.
Harness completo: 2978 testes / 64 execucoes, tudo OK nos Blenders 4.2/5.2
(tab383-completo.log). ZIP 383 conferido contra as 39 fontes Python.

Pintura de grupos preserva ferragens (382): materiais.py filtra puxadores,
dobradicas, acessorios, trilhos de gavetas e descendentes dessas marcas.
Ctrl+L reutiliza o desenho do menu nativo; so' Vincular materiais usa o
operador protegido, que delega ao make_links_data com contexto filtrado.
Selecao/ativo permanecem; mover, ocultar e duplicar continuam com o grupo
inteiro. Sem grupo, material individual segue o operador nativo.
HUD +8: grupo+origem externa, catalogo/filho sem marca, puxador individual,
ferragem como origem, menu/atalho e demais acoes nativas, menu sem grupo,
grupos internos e undo/redo. Materiais comparados por referencia/nome real,
incluindo sufixos .001; sem apagar/acessar biblioteca ou cena reais.
Falha anterior reproduzida em pintura382-repro.log (dois testes falhando).
Validacao direcionada: 650 testes / 10 execucoes nos Blenders 4.2 e 5.2,
tudo OK (pintura382-cenarios-finais.log). Gesto Ctrl+L na janela nao executado.
Auditoria em cena descartavel: sete chapas receberam a cor, 104 malhas de
ferragens conservaram metal e a selecao permaneceu. Renders externos/internos
revisados em Backups/CabinetCreator/pintura382-auditoria/; projeto aberto e
biblioteca preservados. ZIP 382 conferido contra as 39 fontes Python.
Harness completo: 2972 testes / 64 execucoes nos Blenders 4.2 e 5.2,
tudo OK (pintura382-completo.log).

Internos compartilhados e recortes parciais (375): seis abas, Prateleiras /
Divisorias juntas; enums antigos continuam lendo .blend e seguindo selecao.
areas_criacao coordena tipo, pontos/volume, captura numerica unica, quantidade,
lacuna e continuar com outro tipo/Sair. Guarda nomes/numeros por cena, encerra
snap antes de perguntar, nao recaptura pontos nem duplica o tipo ja' criado.
Ambas as ordens detectam lacuna antes de mutar, incluindo prateleiras novas
com divisorias antigas. Cancelar conserva existentes; invalidos nao criam.
Divisorias planeja subconjuntos por nome, permite profundidades/alturas
diferentes e contato coplanar. Mantem restricoes fisicas das gavetas.
Preencher ESQUERDA/DIREITA estende somente o segmento escolhido, face do
apoio e Boolean EXACT nativo; MANTER conserva faixa vazia. BMesh bisect/cap
preserva Mesh/UV/material. Tampas coplanares uniformes evitam a cunha de
float que criava aresta com quatro faces no Boolean, sem folga artificial.
Recorte vivo acompanha editar profundidade; undo/redo conserva referencias.
Divisorias +12: manter/preencher dois lados, criacao depois, coplanar,
espessura parcial, alturas diferentes, limites das gavetas, resize,
undo/redo, rotacao e Mirror; volumes nativos fechados conferidos.
Areas_criacao +7: tipo antes, entrada por volume, continuar sem cliques,
lacuna/cancelar, prateleiras depois, comando/cena invalidos, aba unificada.
GUI existente adaptado para tipo -> volume -> divisorias -> prateleiras
no mesmo volume -> sair; nao executado com janela nesta sessao.
Validacao: 2836 testes / 64 execucoes no Blender 4.2 e 5.2, tudo OK
(internos375-final.log). Textos finais e encaixe no painel estreito: mais
56 testes direcionados nos dois Blenders (internos375-perguntas.log).
Renders manter/esquerda/direita revisados; volume esperado e Mesh preservada
em Backups/CabinetCreator/internos375-auditoria/ (PNG e resultado.json).
Snapshot comparado ao anterior: somente cabecalho muda; campos conservados.
ZIP 375 conferido contra as 39 fontes Python; cena aberta preservada.

Puxadores por folha e troca GIRO/CORRER (374): uma folha selecionada
individualmente vira alvo nominal do criador, com Object.ray_cast nativo;
outra folha na frente nao captura o gesto. Sem alvo, reutiliza raio da HUD
que ignora ocultos. Folha oculta/bloqueada continua protegida. Sem varredura
Python de vertices. GIRO <-> CORRER adapta borda lateral parametrizada,
conserva dono/fracao; correr nas bordas externas, giro no lado livre.
Pose fechada evita inverter a borda com folha aberta. Bordas horizontais,
puxadores nao parametricos e resize sem troca continuam nos contratos atuais.
Puxadores +7 cenarios: converter e voltar sem duplicar, perfil novo em
correr, pose aberta, alvo sobreposto, oculto/bloqueado, ponte HUD visivel,
excluir/recriar na segunda folha sem alterar a primeira.
Cena aberta consultada so' em leitura: folhas ocultas e sem puxadores;
nenhuma tentativa de revelar, reposicionar ou alterar o projeto real.
Auditoria headless: renders GIRO, CORRER e exclusao/recriacao revisados;
contagem final um puxador por folha. Evidencias externas em
Backups/CabinetCreator/puxadores374-auditoria/ (PNG e resultado.json).
Os gestos completos de mouse na janela real nao foram executados.
Validacao final: 2798 testes / 64 execucoes no Blender 4.2 e 5.2, tudo OK;
log externo puxadores374-completo.log. ZIP 374 conferido contra as fontes.

Rolagem dos paineis compartilhados (373): aba e biblioteca exibem barras
verticais do tema somente com excesso, proporcionais ao conteudo e nos seus
limites. Clique no trilho, arraste, roda e touchpad alteram somente o painel
apontado; Esc restaura o arraste. Abas/rodape fixos, opcoes/listas por cima.
Reutiliza os limites/offsets existentes, sem transformar o painel em viewport.
Verbo rolagem intencional: trilho vertical, diferente do slider de tamanho.
Gaveta +5 cenarios: todas as abas/overflow, arraste/limites/Esc/independencia,
roda/touchpad/cabecalho, opcoes sem falsa sobreposicao, proporcao/resize.
Coluna de 12 px nos paineis com excesso reflui campos/fotos sem sobrepor
botoes; preserva cabecalho/divisoria. Regressoes de prateleiras conservam
teste de sobreposicao; biblioteca confere quebra pela largura util.
Limiar da foto que encolhe nao alterna o layout. TRACKPADPAN usa ANY nativo.
Snapshot revisto: barra e reflow do painel estreito; demais entradas e
rotulos conservados, alem das alteracoes pendentes da 372.
GUI +1: arrastar a barra da aba sem rolar biblioteca e cancelar; incluido,
sem abrir janela nem executar o cenario nesta sessao.
Auditoria do layout: primitivas do callback capturadas em cena temporaria,
recortes/cores do tema, inicio/fim independentes e coluna livre conferidos
nas imagens de rolagem373-auditoria/ em Backups/CabinetCreator. Exportacao
2D usa fonte aproximada, nao substitui teste dos gestos na janela real.
Validacao final: 2784 testes / 64 execucoes no Blender 4.2 e 5.2, tudo OK.
Log: Backups/CabinetCreator/rolagem373-entrega.log; pacote 373 conferido.

Areas livres de criacao (372): areas_criacao.py e' o dono do volume/plano
temporario. Um clique em face/interior ou plano da vista, sem exigir vertices;
referencial do modulo selecionado. Empty + limites numericos impedem Edit Mode,
subdivisao/cisalhamento: 8 cantos no volume, 4 no plano. G/R/S, cotas da HUD,
centros de face e B reutilizam os caminhos nativos existentes. Aplicar area
entrega so' numeros/nomes aos assistentes de gavetas/prateleiras/divisorias/
fundos; portas seguem de FOLHAS com plano explicito. E continua no dominio.
Quantidade/profundidade nao voltam ao gesto antigo. Copia/restore das cotas,
cursor e selecao seguem contratos atuais; invalidos conservam a referencia.
Temporarios saem em Esc, undo/redo, save/load e unregister. Campo/G confirmados
com Enter nao aplicam a area por engano; zero no S conserva ultimo volume valido.
21 testes novos em areas_criacao: topologia/ortogonalidade/GRS, plano 4 pontos,
ancoragem dos lados, validacao, HUD e B depois de deslocar, entrega unica,
criacao nos cinco dominios, previa = porta final, primeiro clique/Tab,
campos/menu, cancelamento/undo/redo/save/load e invalidos sem dados parciais.
Snapshot de layout revisto: somente 12 insercoes do botao Definir por plano;
nenhum valor/forma anterior alterado. GUI +1: botao -> clique em face sem
vertice -> Tab bloqueado -> cotas digitadas -> Aplicar -> QUANTIDADE.
Cenario GUI incluido, sem executar janela nesta sessao.
Validacao final: 2774 testes / 64 execucoes no Blender 4.2 e 5.2, tudo OK.
Auditoria headless de geometria: cubo inicial 200 mm, volume ajustado
473 x 600 x 964 mm, plano 473 x 964 mm e prateleira criada no vao direito.
Renders revisados; corpo preservado e nenhum temporario restante. Renders
usam os mesmos cantos numericos, sem afirmar validacao da interacao GPU.
Evidencias externas: Backups/CabinetCreator/area372-entrega.log e
area372-auditoria/ (PNG e resultado.json).

Selecao e recorte de paredes (371): Object.ray_cast consulta SO' a malha
escolhida, sem fallback para a cena; pula teto e backfaces ocultas na mesma
malha. Por pontos usa translate/cursor nativo VERTEX/ONLY_SELECTABLE,
plano da face e confirmacao no RELEASE; guarda/devolve cursor e hide_select.
Fracao visivel e' area do envelope frontal intersectada com a regiao real,
incluindo concavidades/buracos. >=90% na entrada libera pela sessao inteira,
inclusive se sair dos limites depois; novos modulos registrados sao editaveis.
Parciais restantes usam copia BMesh avaliada + Boolean EXACT temporario,
cinza do tema, hide_select e fora das cotas/edicao. Nao altera as fontes.
Restaurar Local View/ocultacao/undo/erro limpa copia, volume e bloqueios.
Portas de entrada por vertices, Automatico e Por pontos partilham a regra.
Paredes_selecao +11 fixtures: teto externo, teto/backface na mesma malha,
parametros/filtro/confirmacao do snap nativo, cancelamento e erro com
restauracao, 90%/89.9%/50% e regiao triangular, geometria cortada imutavel,
permissao retida fora do recorte, parede girada, undo/redo e rollback.
GUI +1: press/drag/release de tres vertices, snap sem teto, cursor devolvido
e confirmacao pelo operador do menu. Cenario incluido; janela nao executada.
Auditoria visual headless: inteiro normal e parcial cinza cortado; oito
malhas originais preservadas, zero temporarios depois de sair. Artefatos
em Backups/CabinetCreator/parede371-*; projeto aberto nao alterado.
Validacao 371: 2732 testes em 62 execucoes (Blender 4.2/5.2), OK.
ZIP verificado contra as 38 fontes Python; espelhos de instrucoes identicos.

Dobradicas e Delete (370): causa real confirmada no projeto aberto:
handler de chapas sem PERSISTENT sumia no load; timer geral permanecia,
mas exclusoes nao agendavam limpeza. Clique nas ferragens esvaziava a
selecao nativa. Observador agora persiste e clique/Shift selecionam so'
ferragens visiveis da camada; menu/Alt restauram a selecao depois de editar.
Indice da folha acompanha tambem ferragens sem rig; exclusao parcial nao
mantem dobradicas da folha removida nem muda o indice de abertura da outra.
Portas +5 fixtures: salvar/reabrir e Delete do grupo; selecao de residuos,
Delete/undo/redo; ocultacao/camada/desmarcar; exclusao de uma folha dupla
com rig e sem rig, preservando a montagem/abertura da sobrevivente.
Na copia descartavel da cena real: 210 pecas de ferragens, 170 selecionadas
nativamente; Delete e limpeza deixam zero residuos, preservando matrizes,
vertices e materiais dos outros 527 objetos. Projeto aberto nao alterado.
Validacao 370: 2710 testes em 62 execucoes (Blender 4.2/5.2), OK.
Auditoria visual por renders antes/depois na copia isolada do armario;
gestos reais na janela aberta nao executados. ZIP confere com as 38 fontes.

Exclusao e selecao (369): no diagnostico real, Peca LAYER89/LAYER90
continuavam em children_recursive, sem cena/colecao. Selecao usa agora
`view_layer.objects` nativo no clique/Shift/porta/Tab, incluindo escolha
segura do ativo quando o pai esta fora da camada. Nenhuma colecao e'
religada para forcar a selecao. ID orfao referenciado e' preservado.
Gatilho do depsgraph observa tambem objetos por cena: Delete pode manter
len(bpy.data.objects), mas tirar a folha da cena. Timer remove ferragens
e grupo vazio, sem refazer uma porta excluida; respeita undo/Edit/modal,
filhos comuns, colecao excluida da View Layer e folha viva em outra cena.
HUD +3 testes nativos: Delete com ID prop, colecao excluida e pai sem
camada. Portas +6: Delete referenciado/limpeza/hover, agendamento sem mudar
contagem de IDs, grupo/folha selecionaveis com outra folha fora, colecao
excluida preservada, undo/redo e folha em outra cena. Fixtures descartaveis.
Validacao 369: 2700 testes em 62 execucoes (Blender 4.2/5.2), OK.
Pacote conferido contra fontes. Diagnostico inicial na cena real somente
leitura; a conexao MCP caiu antes da conferencia final dos cliques reais.

Indicadores da parede (368): A1/A2/A3 com valor sempre no selecionado;
A3 Prof. usa chamada na quina inferior direita e edita profundidade pelo
operador existente. Afastamento e' outro campo. Resize conserva as tres
dimensoes e oculta distancias. Posicoes respeitam a area livre e evitam
os numeros existentes. Fonte/escala de background sem DPI usam escala 1.
Tres testes novos em paredes_composicao: prefixos/valores/linha na quina
sem sobreposicao; hit-test A3, digitar 600 mm e preservar E; bordas da area.
Contrato antigo de duas etapas atualizado pelo pedido explicito; cursor
da HUD continua no valor da cota, sem caixa duplicada. Teste de circulo
usa escala 1 quando background devolve zero; cota curta valida seu centro.
Validacao 368: 2682 testes em 62 execucoes (Blender 4.2/5.2), OK.
Auditoria GPU/BLF offscreen com dados do modulo e area enviados, em vista
normal e junto a' borda inferior. A1/A2/A3 legiveis, A3 na quina separado
do afastamento, objetos preservados. Pacote conferido contra fontes;
gestos reais da nova interface nao simulados.

Base utilizavel da parede (367): a 366 corrigia o parser, mas ainda
mostrava a borda branca/cota 100 mm abaixo do piso real. Ao entrar,
`_regiao_acima_do_apoio` consulta as faces avaliadas por BVH na faixa de
contato e recorta so' bandas inferiores inteiramente ocupadas. Nao muda
a parede nem o armario; proxy, cotas, guias, encaixe e instalacao usam
a mesma regiao. Reentrar recalcula; nao ha consulta adicional no redraw.
Regressoes em paredes_edicao: piso continuo de 100 mm, proxy/guia e cota
zero coerentes sem remontar Mesh, parede girada com Z negativo, piso
parcial/viga suspensa, modulos e objetos afastados. O teste de recuperar
arraste mantem a recusa usando obstaculo parcial de 2,9 m em parede de 3 m;
um piso continuo agora pertence a' base, fora da area apontavel.
Composicao atualiza o teste da 366: zero conclui sobre o apoio, arraste
limita a' base real e penetracao continua recusada.
Validacao 367: 2676 testes em 62 execucoes (Blender 4.2/5.2), OK.
Consulta somente leitura na cena enviada: base sobe 100,00038 mm,
Inferior fica 0,000002 mm e validar zero retorna sem erro. Comparacao
GPU/BLF offscreen antes/depois conferida; objetos e sessao preservados.
Pacote conferido com as fontes. Gestos reais da 367 nao simulados.

Cotas zero na parede (366): digitacao de Inferior/Superior, Anterior/
Posterior e Afastamento aceita 0, inclusive nas guias fora do modo 2D.
Dimensoes zero/medidas negativas continuam recusadas no dominio/parser.
Cinco regressoes: confirmacao modal nos cinco afastamentos sem alterar
vertices/IDs, valores invalidos, piso real de 100 mm bloqueando digitacao
e arraste, quatro guias legadas e ruido float de 0,2 um na borda da face.
Tolerancia existente nao aumenta; consulta corta somente o ruido ja'
aceito antes de amostrar o contorno, mantendo aberturas e colisoes.
Diagnostico somente leitura na cena enviada: `Parede.004` ocupa
100 mm abaixo do armario; o limite da regiao fica abaixo desse apoio.
Validacao 366: 2668 testes em 62 execucoes (Blender 4.2/5.2), OK.
Auditoria da janela e consulta nativa da cena confirmam Inferior 100 mm
e o bloqueador real, sem mover objetos ou alterar a digitacao pendente.
Gestos reais da correcao nao simulados; Blender aberto continua na 365.

Editor proprio (365): CabinetCreatorMenu e CabinetCreatorBiblioteca sao
subtipos nativos NODE_EDITOR com arvore vazia propria para gizmos no 4.2.
Suite editor cobre salvar/reabrir, identidade sem ponteiro, papeis distintos,
arvores comuns intocadas, comando real na viewport com restauracao de
contexto, texto/arraste na origem, erro sem viewport, migracao de legado
inclusive faixa/workspace, clique de aba, undo/redo e limpeza no unregister.
Arraste usa fixture temporaria de modulo e regiao 3D real, sem biblioteca
real nem eventos simulados em background. GUI da faixa passa a conferir
os subtipos nativos, preservando seus testes de gestos.
Validacao 365: 2658 testes em 62 execucoes (Blender 4.2/5.2), OK;
19 regressoes do editor por versao. Trocar o editor nao reabre o menu;
desativar conserva as areas e remove somente arvores/registro proprios.
Pacote conferido contra as fontes. Auditoria visual/gestos GUI nao
executados: instancia Blender/MCP desconectada, sem abrir janela nova.

Referencias da importacao (364): resize pode remover/recriar ferragens ou
controladores. A lista do append e' reconciliada com a hierarquia atual
no finally do ajuste (inclusive quando falha); registro na parede faz a
mesma reconciliacao antes de Local View/fios. Selecao e cancelamento
compartilham a lista atualizada. Tres regressoes em paredes_edicao:
controle nativo removido/recriado com mesmo nome, importacao com/sem caixa
em cache apos resize real, falha na regeneracao sem deixar a nova geracao.
Validacao 364: 2620 testes em 60 execucoes (Blender 4.2/5.2), OK;
paredes_edicao com 81 testes por versao. Sem gestos GUI no projeto real.

Encaixe automatico (363): caso real com parede de 2600 mm, piso elevado
de 100 mm e armario de 2503 mm. Agora reduz a 2500 mm ate limite do menu
(10 mm L/A; zero desliga), preserva E/modelagem/profundidade e o preset.
Dez regressoes em paredes_edicao: piso/deficit 3 mm, largura reduzida no
vao real, modelo e parede girados, limite 0/2/4 mm persistente, topologia/E
conservadas, cache numerico da previa e resize so' na confirmacao, undo/redo
nativo, atach fora do 2D, cancelamento/staging/handlers. Acima do limite, caixa vermelha e
motivo/altura no POST_PIXEL/status; RELEASE relata a restricao real.
Validacao: harness completo 4.2/5.2, 2614 testes/60 execucoes, OK; cache da
biblioteca e carga adiada conferidos nas duas versoes. Auditoria separada
com parede/piso reais e Armario Quarto 01: 2503 -> 2500 mm, dez chapas com
E fisica/parametrica preservada; limite 2 mm recusa. Render Workbench
conferido; projeto original nao gravado. Gestos GUI nao executados.

Abas responsivas (362): sete categorias em linha enquanto as abreviacoes
couberem com fonte 12/margem 18; abaixo disso, suspenso com nome completo
da aba atual e as sete escolhas. Suite gaveta: limite real da fonte,
abertura/troca/fecho pelo despacho normal, prioridade sobre conteudo,
exclusividade com a cascata, rolagem sem perder campos e ida/volta de
largura sem mudar malha/selecao. `test_cabecalho_tem_as_sete_abas` valida
tambem os presets importados; snapshot atualiza apenas o cabecalho.
Regressao do desenho cobre campo apos a limpeza do topo e destaque da
escolha atual. Auditoria visual: renderizador GPU/BLF nativo, offscreen em
564/320/190 px, sem abrir janela ou alterar a cena; gestos GUI nao rodados.
Validacao 362: harness completo 4.2/5.2, 2594 testes em 60 execucoes, OK;
gaveta com 79 testes por versao (oito regressoes novas), snapshot revisado.

Selecao de parede (361): Edit Mode usa vertices/faces BMesh conectados,
mesma orientacao (1 grau) e mesmo plano (2 mm), sem reconstruir a selecao.
Object Mode: Editar parede inicia Automatico por hover; Por pontos marca
poligono com 3+ cantos. Esquerdo adiciona, Backspace remove, Enter confirma,
direito/Esc cancela. Menu lateral tem metodo e acoes equivalentes; eventos
fora da viewport passam, navegacao nativa permanece durante a escolha.
Hover reutiliza raycast e realce do atach; cache por regiao, sem varrer
vertices Python no gesto. Triangulacao e' nativa, recorte respeita concavidade,
buracos e limites reais. Pontos ficam no plano da primeira face escolhida.
Local View mostra somente a exibicao temporaria do trecho e os moveis
REAIS associados por plano/area, incluindo descendentes. A planta original
fica fora dessa viewport, sem modificar sua Mesh, materiais ou modelagem.
Raycast da insercao resolve o UID/face da fonte, nunca associa ao temporario.
Sair/orbitar/salvar/desativar remove a exibicao e restaura estados nativos;
undo/redo remove restos somente no timer normal, depois da guarda nativa.
Se a fonte mudar ou a exibicao desaparecer, encerra e devolve a cena.
Seletores novos aparecem no grupo Paredes de Modulos ou durante a escolha;
nao invadem segmentos dos assistentes de portas/gavetas/prateleiras.
`test_paredes_selecao_blender` (34): planta monolitica com parede frontal
bloqueando o raio antigo, selecao BMesh, conectividade, orientacao, tolerancia,
3+ pontos, concavidade, janela, bordas coincidentes, hover/cache, Enter/
Backspace/Esc/direito, acoes do menu fora da viewport, parede girada,
moveis de outra area/face, fonte nao editavel sem residuos, Local View
anterior, ocultacao manual, restauro, exclusao, fonte movida e undo/redo.
Cenario reproduzivel e renders antes/depois: `D:/Blender/Backups/CabinetCreator/`
`paredes361-cenario.blend`, `paredes361-antes.png`, `paredes361-depois.png`;
script `paredes361-visual.py`. Render aplica os membros da Local View SO'
aos hide_render da cena de teste; projeto do usuario nao foi modificado.
AGENTS/CLAUDE e seus espelhos de tests agora exigem explicitamente cenario
por bug/melhoria, com parametros e resultados, em dados temporarios.
Pendencias anteriores commitadas ANTES desta implementacao: e786876 e
564233d; sem push. Sem consulta ao Home Builder nesta etapa.
Validacao final 361 (2026-10-27): 2578 testes em 60 execucoes, TUDO OK
no Blender 4.2/5.2. Log: `D:/Blender/Backups/CabinetCreator/paredes361-completo.log`.
Pacote dist/cabinet_creator.zip v361 conferido. Novas alteracoes sem commit;
ativacao na instancia aberta exige recarregar o add-on. Sem harness GUI
de gestos reais: validacao visual por render na cena descartavel acima.

Fundos por vao (360): aba Fundos, dois cantos com AssistenteDoVao/snap
nativo, undo unico e selecao da chapa. Canal recuado 6/9 mm usa Boolean
EXACT nos apoios, sem substituir suas malhas; sobreposto pregado fica por
fora; 15 mm escolhe interno rente. Sem simulacao de pregos. Medidas e tipos
editam o mesmo objeto; Esc restaura tipo e parametros dos internos.
Limites de portas/gavetas/prateleiras excluem fundos novos da estrutura.
Vinculo por UID e pai real, com sobreposicao; ponto de profundidade a ate
5 mm identifica o fundo, inclusive legado. Colisao com fundo novo tambem
associa. Fundo mais proximo manda; guarda de capacidade valida todos os
internos antes de montar, sem capacidade restaura pose e mostra a causa.
Timer apos G/Tab conserva frente, altura, espessuras e ajusta profundidade/
trilho; limites individuais tambem respeitam a face interna. UNPINNED
desassocia, conserva medidas e impede reassociacao automatica ao mesmo UID.
Exclusao limpa cortador/modificadores; guardas de Edit Mode/undo impedem
escritas. Legados nao recebem tipo nem recortes automaticamente.
`test_fundos_blender` (30): tres tipos, canal avaliado nativamente, 6/9/15,
invalidos sem residuos, rotacao/resize/E dos apoios, exclusao, link/limites/
snap/distancia/altura/pai, dois fundos, trilhos, escolhas individuais, Esc,
legado sem metadados adicionais, falha sem vinculo/cortador parcial,
novo fundo herda escolhas exibidas e snap de profundidade religa existente,
sem capacidade, menu responsivo/icone, undo/redo e guardas nativas.
Conferencia visual: cena descartavel com tres modulos e lateral direita
oculta SO' no render de auditoria, para ver os internos; PNG/.blend em
`D:/Blender/Backups/CabinetCreator/fundos360-visual.*`. Cena do usuario e
biblioteca preservadas; harness de gestos GUI nao executado.
Espessuras comerciais: catalogos Arauco MDF Trupan/Melamina 2024 mostram
6/9/12/15/18 mm (entre outras), nao 8 mm nesses produtos. Padrao novo 6 mm;
canal limita a 6/9, demais tipos mantem E livre positiva.
Contrato do cabecalho atualizado de seis para sete abas por pedido da
nova criacao; snapshot revisado semanticamente: so' as abas mudaram nos
36 cenarios, conteudos identicos. Legado sem UID nao e' vinculo vazio:
regressao exige UID preenchido e nao permite metadados/reencaixe novos.
Validacao final 360 (2026-10-27): 2510 testes em 58 execucoes, TUDO OK
no Blender 4.2/5.2. Log: `D:/Blender/Backups/CabinetCreator/fundos360-entrega.log`.
Prova adicional com handlers REAIS e transform.translate nativo nas duas
versoes: 545 -> 465 mm; desassociar conserva 465 mm ao mover novamente.
Scripts/logs: `D:/Blender/Backups/CabinetCreator/fundos360-handlers*`.
Pacote dist/cabinet_creator.zip v360 conferido; ativacao na instancia ja'
aberta depende de recarregar o add-on. Sem alterar o projeto aberto.

Solda unica por objetos (359): writer impede registros repetidos em
qualquer ponta/direcao. Cadastro manual valida todos os destinos antes
de substituir uma junta e nao cria soldas automaticas adicionais.
Compatibilidade normaliza uma vez apos carregar, anexar ou undo/redo,
fora de Edit Mode/gestos/guardas nativas. Preserva a origem cadastrada;
restricoes axiais nao redundantes dos dois extremos passam a metadados
da unica aresta. Resize e grupos soltos consultam o mapa em lote.
Migracao explicita usa KDTree em MUNDO para cadastrar o menor gap entre
vertices reais existentes, sem alterar geometria, espessuras ou materiais.
`test_solda_blender` (16): unicidade, reciprocos, minimos reais com giro/
escala, origens/direcoes do mesmo indice, multiplos vizinhos, UID repetido
entre montagens, validacao atomica, guardas e undo/redo. Assinaturas uN
modeladas identificam tambem o parceiro da espessura, sem voltar a sinais.
Revisao independente acrescentou regressao de otimizacao, regravacao,
precedencia primaria no mapa/reset e compatibilidade neg sem face.
`test_soldas_biblioteca_blender` (22): staging, reabertura, idempotencia,
minimo geometricamente independente, integridade protegida, hashes de
fontes/backup/arquivos, publicacao atomica com rollback e reversao.
Sessao aberta: 47 objetos, 10 relacoes e 20 pares inferidos -> 10 pares;
comparacao exata de geometria, poses, materiais e selecao, com backup em
Documentos/Cabinet Creator Backups/soldas359-sessao-20261027/antes.blend.
Conferencia visual na janela existente: quatro fios nas quatro relacoes
da lateral afastada; biblioteca/menu nativos mantidos. Sem cliques GUI.
Relatorio da sessao no mesmo diretorio: relatorio.json.
Contrato de UID em `test_estrutura_blender` verifica a aresta unica,
restricao reversa e resolucao apos renomear; preserva a regra original.
Biblioteca publicada: 328 presets auditados, 265 .blend refinados e 63
intactos. Os 2385 registros viraram 1978 arestas dos mesmos 1978 pares;
zero invalidas/repetidas, com todos os minimos reais conferidos por
produto cartesiano independente (tolerancia 0,001 mm). Coordenadas,
topologia, materiais, pais, UIDs, catalogos, fotos e previews preservados.
Auditor independente reabriu tres modelos, incluindo chapas modeladas,
e conferiu os 52 pares dessas amostras. Backup e manifesto reversivel:
Documentos/Cabinet Creator Backups/soldas359-aceite-20261027-042135Z.
Primeiro harness completo: asserts funcionais passaram; guarda de bytes
da biblioteca reprovou porque os guias de assets foram atualizados durante
a execucao. Reexecucao integral com fontes/recursos estaveis, sem enfraquecer
a guarda; hashes dos assets publicados conferidos separadamente.
Validacao final 359 (2026-10-27): 2450 testes em 56 execucoes, TUDO OK
no Blender 4.2/5.2, incluindo a guarda de integridade. Log:
`D:/Blender/Backups/CabinetCreator/soldas359-completo-estavel.log`.
Pacote dist/cabinet_creator.zip conferido contra fontes e 265 blends
publicados. Harness GUI de gestos nao executado nesta entrega.

Contorno na selecao mista (358): somar um objeto comum a modulo/porta
devolve o overlay nativo que o add-on ocultou. Retirar o objeto comum
retoma a selecao exclusiva da HUD. Componentes sem marca dentro do grupo
selecionado nao tornam a selecao externa. Usa select_get por ViewLayer,
sem ler malhas, alterar selecao ou depender de quem e' o objeto ativo.
Respeita contorno previamente desligado pelo usuario. Duas regressoes
em test_hud_blender cobrem transicoes, componente filho, curva externa,
preferencia manual e Ctrl+L nativo desde malha comum (piso 180).
Aplicada na instancia aberta: Cube mestre e 45 objetos selecionados,
sem alterar selecao/ativo. Conferencia visual da janela existente via
computer-use confirmou o Cube com contorno laranja e a blocagem visivel.
O Blender estava minimizado; as capturas MCP pretas nao serviram de prova.
Validacao 358 (2026-10-27): 2374 testes aprovados em 52 execucoes no 4.2/5.2;
log `D:/Blender/Backups/CabinetCreator/contorno358-completo.log`.
Pacote atualizado e conferido; sem harness GUI de gestos automatizados.

Tab/G do grupo (357): a saida atualiza os rigs em lote, com no maximo
duas avaliacoes explicitas da camada, independentemente da quantidade
de dobradicas. Puxadores participantes conservam a Mesh editada; somente
o contorno numerico se atualiza. Puxador fora da edicao conserva o
reposicionamento parametrico. Entrada registra os nomes imediatamente,
sem depender do tique do timer. Referencias de frente iguais usam o cache.
Regressoes: test_operadores_blender cobre reduzir 2400 para 2100 mm com
G nativo sem reconstruir o perfil e o custo constante das ferragens;
test_puxadores_blender cobre edicao individual, material, UV e undo/redo.
Prova anterior: as duas regressoes falham na implementacao antiga
(reconstrucao indevida e 6 avaliacoes da camada em vez de 2).
Medicao 5.2, preset Armario_Quarto_08_600x2503x550, 276 objetos:
saida do Tab 0.830 -> 0.425 s; saida + tres tiques + conferencia das
ferragens 1.235 -> 0.815 s, com cProfile, sem interacao GUI.
Logs em `D:/Blender/Backups/CabinetCreator/`: `perfil357-extra-antes.log`,
`perfil357-extra-depois.log`, `tab357-prova-anterior.log`.
Validacao 357 (2026-10-26): 2370 testes aprovados em 52 execucoes no 4.2/5.2;
log `tab357-completo.log`. Auditoria visual em render isolado apos Tab/G:
`tab357-visual.png`; perfis continuam unidos as portas e nos limites delas.
Sem janela GUI nem alteracao da cena do usuario; o MCP estava indisponivel.
Pacote `dist/cabinet_creator.zip` conferido com os cinco fontes alterados.

Materiais pela selecao mestre (356): Shift conserva as pecas do grupo
selecionadas, mas usa a chapa/folha clicada como objeto ativo. Ctrl+L >
Vincular materiais permanece inteiramente nativo, sem operador paralelo.
Clique simples sem Shift conserva o Empty ativo; Shift+duplo isola a
origem sem pintar as demais pecas daquele modulo. Quatro regressoes em
test_hud_blender: grupos, origem isolada, chapa solta com multiplos slots
OBJECT e folha de porta; confere materiais, selecao e geometria (piso 178).
O nivel PORTA permanece de grupo mesmo com a folha mestre ativa; o contrato
de Shift em test_portas_blender acompanha a selecao mestre nativa.
Validacao 356 (2026-10-26): 2364 testes aprovados em 52 execucoes no 4.2/5.2.
Log: `D:/Blender/Backups/CabinetCreator/materiais356-final-completo.log`.
Instancia aberta recebeu somente as tres funcoes de selecao, preservando
o objeto ativo, a selecao e os 1146 objetos, sem reiniciar o registro.

Solda 355: criar/reancorar bloqueia desenho e interacao da HUD de geometria
(inclusive setas, cotas e sliders); limpa hover e restaura ao encerrar.
Corrente, regua, distancia e snap da solda continuam ativos. Iniciar e
confirmar Criar solda usam o destaque laranja existente do menu.
Regressoes: bloqueio/restauracao no HUD (piso 174), destaque na gaveta (71).

Solda 354: piloto conserva apenas UM par de vertices por par de pecas ou
modulos distintos, inclusive quando as chapas de origem/destino variam.
Prioriza contato zero; juntas entre chapas do mesmo modulo continuam
independentes. Auditoria nao altera geometria nem soldas da sessao aberta.
Regressoes: limite entre modulos e resolucao do grupo no HUD (piso 173).

Solda 353: corrente/regua/campo numerico tambem na previa sem selecao;
regua por indice zera pela ancora final fixa, corrente remove somente o par
pendente. Gizmos em pools separados mantem bindings e simbolos; modal deixa
passar seus cliques. Marcador e distancia acompanham o cursor do snap nativo,
sem varrer malhas. Auditoria somente leitura e deterministica num modulo:
contato zero primeiro, vertice unico, quinas separadas pela espessura
(ate 25 mm); limite refinado para um unico par de vertices na 354. Proposta
explicita busca contatos reais com KDTree fora do gesto; sem contato exige
revisao. Oito regressoes em test_hud_blender (piso 171). Piloto externo nao
altera a biblioteca real.

Criacao completa da solda (352): painel proprio sem Orcamento/Comodo,
distancia editavel, Resetar distancia, Voltar, Criar/Cancelar e instrucoes.
Direito/Esc cancela e devolve a previa; Backspace/Ctrl+Z volta etapa. Alt
reancora nas mesmas pecas usando o cursor/translate nativo. Reset na criacao
encosta a origem na ancora FINAL fixa, guarda zero como referencia e
permite outros afastamentos. Previa restaura antes do operador definitivo,
cujo undo conserva geometria e metadados. Solda manual continua visivel
em zero, com corrente, regua e numero clicavel por gizmo de campo existente.
Ancoras novas: cantos semanticos em caixas, INT/POINT `cabinet_solda_vertice`
nas malhas modeladas (tokens u; v legado continua aceito). Atributo segue
BMesh/copia de referencia e salvar/anexar; indice reordenado nao muda o
vertice. Ancora apagada/ambigua e' recusada com aviso, sem apagar os dados.
IDs dos objetos continuam por UID/pai; vetores da referencia/direcao ficam
locais ao destino, acompanhando giro e reflexao. Snap sem cache consulta
face nativa, sem construir arvore da malha inteira no clique. Regressao:
cancelar/voltar, zero fixo, parametros, Alt, controles, giro/Mirror, undo/
redo, salvar/anexar/renomear, reordenar/apagar vertices, fallback de snap
(hud, 163; gaveta, 70). Soldas antigas conservam o reset da folga original.

Menu de portas e simbolos de Montagem (351): retirada a linha Reposicionar
no vao / Definir como frente / Espelhar porta. O espelhamento da porta
continua no menu contextual. Corrente e Resetar distancia mostram texto
com icone ao lado e empilham em menu estreito. Pool nativo por simbolo e
ocorrencia: o Button2D fixa o icone no primeiro draw; reaproveitar outro
simbolo trazia a pasta/disquete da biblioteca para Montagem. Regressao
alterna biblioteca/montagem, ordem e dois icones iguais sem remover gizmos
nem crescer a cada redraw (gaveta, 69; portas, 154; snapshots revisados).

Biblioteca sem variantes espelhadas e diagonais curvas (350): 369 modulos
auditados por categoria completa, geometria em 8 orientacoes, materiais e
sistemas internos. Retirados 10 diagonais de frente curva e 34 repetidos/
espelhados; reta/chanfro continuam, mantendo o lado mais visivel na foto
frontal direita. 325 modulos e 3 objetos; nomes/UUID/bytes dos mantidos
conservados. `consolidar_variantes_biblioteca.py` prepara plano externo com
hashes e originais; publica indice atomicamente e retira .blend/.png, com
rollback. Testes temporarios: catalogo/metadados/reta/backup preservados,
recusa se biblioteca/backup mudou e restaura tudo se a exclusao falhar
(migracoes, 11). Backup real: Documentos/Cabinet Creator Backups/variantes350-20261025.
Mirror NATIVO do grupo: reflexao no Empty, sem virar dimensao negativa;
referenciais de forma/porta/internos conservam paridade. Recentrar, editar
medidas repetidamente e S depois de R/Mirror conservam profundidade e
internos. `test_mirror_nativo_do_grupo_preserva_malhas_e_recalculo_dos_internos`
e `test_redimensionar_e_recentrar_modulo_espelhado_girado` (armarios, 20).
Mira angular nativa usa espaco CUSTOM comum; migracao nao remonta malhas,
regressao `test_braco_angular_espelhado_preserva_volume_e_migra_mira_antiga`
(portas, 154). Espelhar o grupo no Object Mode; modificador em cada chapa
duplica geometria e nao substitui esse gesto.
Preset curvo aposentado do quarto conserva fixture em tests/fixtures para
testar append/resize/apoios; testes da biblioteca usam modelos ativos.

Criar solda no menu esquerdo (349): botao textual em Modulos/Montagem,
acima de Corrente/Resetar, disponivel em chapa ou modulo e acionado no soltar.
Reutiliza o assistente e o snap de vertices nativos; modulo escolhe a chapa
de origem no primeiro ponto, chapa individual continua fixa. Confirmar fica
no rodape, e a pergunta de juntar retorna ao menu de origem. Layout a
190/320/564 px, contexto sem selecao, escolha dos dois pontos e limpeza de
timer/handler sao cobertos (gaveta, 68; hud, 152; snapshot atualizado).

Desempenho do clique da solda e montagem dos rigs (348): uma carga do asset
por montagem, demais dobradicas por copias nativas de Object com referencias
internas remapeadas. Pais/inversa, IK, drivers, malhas compartilhadas e abertura
permanecem independentes. Remocao nativa em lote conserva dados ainda usados;
malha modelada com marca igual ao asset nao e' deduplicada como original
(portas, 153). Atributos compativeis sao conferidos antes da comparacao nativa,
evitando o crash do comparador no 4.2. Detector calcula correntes uma vez por evento; gizmos preservam
operadores no redraw e atualizam alvo; despachante conserva CANCELLED e deixa
undo no operador dono (hud, 151). Prova na cena completa do David V2 compara
montagem antiga/nova e confere geometria e matrizes com portas fechadas/abertas.

Regua em soldas contraditorias (347): valida todos os destinos antes de
alterar chapas, portas ou ferragens; a mesma quina nao recebe dois destinos
e as peles da espessura movem juntas. Grupo valida todas as juntas antes
da primeira escrita; erros retornam CANCELLED sem remontar o armario.
Reutiliza o validador de juntar por pares e calcula deltas simultaneamente
(hud, 148). UID duplicado no mesmo modulo usa o nome gravado somente entre
irmaos com aquele UID; mover uma lateral nao troca sua identidade pela
copia mais proxima. UID entre modulos continua prioritario (operadores, 49).

Clique fora encerra a selecao individual (346): vazio, objeto comum ou
outro modulo limpam a memoria do clique/hover e devolvem o modo GRUPO.
O clique simples seguinte seleciona o modulo; isolar a chapa exige novo
duplo clique. Shift no vazio conserva a selecao/contexto individual;
memorias das demais viewports tambem sao invalidadas (hud, 146).

Regua da solda sem remontagem desnecessaria (345): porta Reta de giro
conserva folhas/puxadores/rig quando vao, medidas e poses calculadas ja'
coincidem. Reutiliza calculos nativos existentes, sem novo cache ou solver.
Mudanca de margem, rig apagado/antigo e apoios obliquos continuam sendo
atualizados (portas, 149). Prateleiras evitam escrever a mesma pose/medidas
ou atualizar o depsgraph sem mudanca; detectam e corrigem pose alterada
sem substituir a Mesh (prateleiras, 53). Benchmark na copia do David V2
compara o encaixe da mesma chapa e confere a geometria final da carcaca.

Edicao nativa de dobradicas espelhadas e UV proporcional (344): antes do
Tab do grupo, materializa os Mirror das ferragens em malhas unicas,
respeitando a ordem da pilha. Conserva forma avaliada, rig e outras copias;
arraste nativo nao deixa a metade espelhada presa pelo Clipping. Chapas
sem UV recebem mapa metrico (1 unidade/m); mapas personalizados conservam
orientacao/escala. Correct Face Attributes nativo acompanha G/R/S, mantendo
a densidade da textura nas faces estendidas (operadores, 48).

Selecao na vista isolada e edicao das dobradicas (343): o raio nativo
ignora objetos ocultos na viewport, inclusive paredes fora da vista local,
para o clique continuar selecionando o modulo antes/depois de Tab (hud, 143).
Transladar os vertices de uma peca inteira da dobradica durante o Tab do
grupo desloca a montagem, incluindo armacoes, parafusos, mola e furo do
copo. Conserva a Mesh e modelagens parciais; a posicao persiste ao remontar,
abrir/fechar e desfazer/refazer Tab, sem acumular o deslocamento. Referencia
numerica na Mesh participa do undo e sai ao concluir; trocar a versao do
rig tambem conserva o deslocamento manual (operadores, 45).

Correcao dos internos da biblioteca (342): preparo externo com backup,
restauracao das laterais indevidamente convertidas em gavetas, adocao das
quatro caixas internas do Armario Quarto 08, frentes livres da carcaca,
profundidade limitada pelo ray cast nativo e vaos de prateleiras restritos
ao compartimento. Conserva geometrias, UID e materiais ao unificar
familias; separadores/travessas permanecem estruturais. Recorte booleano
local mantem a Mesh e a topologia reparada conserva recortes vazios.
Confere edicao sem deslocar as chapas, catalogos, reabertura, fotos e
indice antes de publicar com verificacao de hashes e rollback
(correcao_internos, 10; migracoes). Auditoria mede portas e gavetas fechadas
e reconhece tambem a topologia nativa apos pequenos recortes.

Auditoria dos internos e remocao das frentes curvas restantes (341):
`auditar_internos_biblioteca.py` abre TODOS os modulos sem gravar na
biblioteca, mede os vaos nos referenciais reais e distingue sobreposicao
de envelopes de colisao volumetrica das pecas. SAT e BVH nativos,
tolerancia de 0,25 mm, ray cast por paridade, recortes em L e malhas
abertas sem confirmacao de volume; confere excesso das pecas e desalinhamento
de origem/rotacao/escala no vao (auditoria_internos, 9). Balcao 09/15 e
Gaveteiro 01/03 retirados do indice, .blend e fotos; recepcoes curvas e
diagonais chanfrados preservados (biblioteca, 84). Auditoria registra
problemas encontrados: nao remonta automaticamente os presets.

Puxador no duplo clique e guias discretas (340): clique simples no
puxador vale pela peca dele (porta, gavetas); o DUPLO entra na edicao do
puxador (puxadores, 24; gavetas, 50). Guias de altura pontilhadas
(tracos `TRACO_GUIA_M` a cada `PASSO_GUIA_M` na propria malha, snap
mantido) e rotulo cinza; caixa preta so' sob o mouse (`atualizar_guia_hover`)
ou digitando (composicao, 67).

Entrar/sair da parede em destaque (339): "Editar parede" e "Sair da
edicao da parede" no padrao do "Criar Prateleiras" -- 30 px, laranja,
texto centrado; sair no laranja forte (`OPERADORES_DESTAQUE`) (paredes_edicao, 68).

Menu da parede enxuto e digitacao sem sobrepor (338): a secao Composicao
so' mostra a cruz de medidas do selecionado (sem Livre/Fixa, Redistribuir,
Trocar modelo, Desassociar; some sem selecao) e o menu da parede perdeu
as folgas Esquerda/Direita/Espacamento (paredes_edicao, 67). Clique na
bolinha da borda: o texto digitado entra no numero da cota verde
(`digitacao_hud`), sem a caixa da HUD ao lado (composicao, 66).

So' bolinhas na parede (337): no editor de parede a HUD perde as setas
das arestas (`so_faces`); edita so' pela bolinha do centro das bordas,
agora disco cheio de 5 px com halo, 7 px acesa (composicao, 65).

Guias de movimento no meio das faces (336): Anterior/Posterior na meia
altura do modulo, Inferior/Superior no meio da largura, cada uma da face
ate' o vizinho/ponta/piso/teto (composicao, 65).

Cotas da parede em duas etapas (335): selecionado, so' distancias e
afastamento; editando pela HUD (`modulo_em_edicao`), so' largura/altura,
que acompanham o resize. HUD na parede so' no plano (`_geometria_na_parede`,
sem ancora; quina acesa do snap ganha) e o clique nela nao move o modulo.
Pontas de seta dentro da `area_livre` (`recortar_cota`) (composicao, 64).

Circulo do snap de quina (334): na vista da parede, o mouse a ate' 16 px
da quina de um modulo acende um circulo na cor de realce
(`atualizar_quina_hover`, observador); G/arraste com ele aceso pega a
quina, que gruda na quina-alvo mais perto e leva o circulo (composicao, 59).

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

Parafuso no ponto do usuario (329): cabeca 5,78 com o topo 0,876 acima da
peca (origem na superficie), medido na cena refinada dele; `cabinet_versao`
na malha + `_anexar_sem_repetir` por origem e versao: a cena troca a chata
rente (versao 1) pelo timer (portas, 145; puxadores, 23; snapshot BORDA).

Linhas do parafuso na dobradica (328): arame = so' o TOPO da cabeca
(circulo + cruz); selecao das ferragens sem rig desenha o contorno marcado
(`_contorno_da_ferragem`, guardado), nao todas as arestas (a rosca);
malha antiga da cena remarcada uma vez (`marcar_arame_parafuso`) (portas, 145).

Dobradica antiga troca sozinha (327): a Reta original dos presets/cenas
(versao 2) punha o parafuso de REGULAGEM nas placas de fixacao; o timer das
ferragens (`_ferragens_antigas`) refaz UMA vez a porta com rig de outra
versao ou parafuso panela; a regulagem fica no braco (portas, 145).

Parafuso padrao = foto do usuario (326): chipboard 3,5x14 cabeca CHATA
rente a' peca, haste lisa, rosca e ponta, bicromatizado; nome novo (as
cenas nao reusam a panela); arestas abaixo da cabeca com
`cabinet_sem_arame` ficam fora da previa e do contorno do puxador
(puxadores, 23; portas, 144; snapshot BORDA 3 mm mais raso).

Quina sem Alt no mover da parede (325): o mouse a ate' 16 px de uma
quina-alvo gruda a quina mais perto do modulo nela; o Alt so' liga as
laterais (composicao, 57).

Costas na parede = lado OPOSTO a' porta (324): a frente sai da posicao das
folhas/frentes de gaveta, gravada em `parede_costas` ao associar; a roda do
mouse no arraste (direito ou da biblioteca) troca a face de 90 em 90; no
giro de 90 a largura na parede e' a profundidade do modulo (paredes, 15);
o indice grava `costas` na caixa do preset e registro sem ela mede de novo
(paredes_edicao, 66).

Parafuso padrao chipboard 3,5x14 panela (323): 2 nos furos da aba do
BORDA (cabeca na aba, ponta nunca na frente, previa = peca; puxadores, 23),
4 de fixacao da dobradica reta em escala 1 e os da articulada (portas, 144).

Puxador BORDA = slim de aba do usuario em tamanho real (322): 80 mm com
furos a 64 (144 -> 128), aba nas costas e enrolado 20 mm a' frente em
qualquer espessura, furos sem escalar, faces planas sem degrade, previa =
arame do modelo (puxadores, 23).

Cena real pesada (321): regiao da parede em lote e uma vez por parede
(paredes, 13); arraste da biblioteca so' wireframe pela `caixa` do indice,
"Carregando..." e o .blend so' ao soltar; sem caixa, o 1o arraste a grava;
.blend alterado invalida (paredes_edicao, 65).

Snap do mover na parede so' com Alt segurado (320): quinas e laterais;
solto = livre; Ctrl nada faz (composicao, 57).

Mover na parede (319): G ou arraste do esquerdo num modulo da vista 2D
pega a lateral sob o mouse e gruda o lado inteiro (vizinhos, face, guias
Com snap), outro eixo livre; Alt quina com quina no plano; Ctrl sem ima;
Esc restaura (composicao, 57). Arrastar com o direito para fora de
qualquer parede desassocia sem mover; botao "Desassociar da parede" na
Composicao (paredes_edicao, 64; composicao).

Preset solto numa parede fora da edicao 2D (318): costas na parede, cursor
no centro do modulo, pontas/piso/teto grudam, sem sobrepor vizinho, e
associa; fora da parede volta a' rotacao do preset (paredes_edicao, 63).

Ima 2D na parede (317): ao soltar G/R/S, bordas da caixa grudam em vizinhos,
face e guias a ate' 12 px, no plano (sem confundir frente/fundo); modulo
associado volta para dentro da face; medida digitada intacta (composicao, 51).

Biblioteca no menu sem fila de botoes (316): Inserir/Editar/Bloquear so' no
clique direito, como na faixa; grade com vao de 8 px (gaveta, 67).

Cotas Promob e biblioteca no menu (315): Superior/Anterior/Afastamento/
Posterior/Inferior em cruz no menu e na viewport; afastamento resiste ao
timer/G (paredes_composicao, 49). Biblioteca na faixa OU dentro do menu
(`cabinet_lugar_biblioteca`, troca no timer; biblioteca_faixa, 29); no menu
cada nivel e' lista suspensa flutuante (estrutura, 51: lista, colunas,
hover por linha, materiais, escolha). Carrossel do menu removido.

Guias de altura da parede (313): so' na vista 2D, linhas Rodape 150, Bancada
900, Peitoril 1100, Base do aereo 1500 e Altura maxima 2150 (mm do piso da
face), editaveis no rotulo da viewport e no menu, por projeto. Modo Ocultas |
Visiveis | Com snap: o snap NATIVO de aresta usa um objeto temporario so' de
arestas, removido ao sair; marcas limpam objeto e snap restaurados pelo undo.
`test_paredes_composicao_blender.py`: 44 testes, quatro novos.
Rotulo com tamanho fisico (314): 70 mm na parede, teto da cota, some abaixo
de 7 px. Cotas e guias em edicao: barra PISCA na posicao do cursor (0,5 s,
tique do proprio operador) e realce do texto todo selecionado. 46 testes.

Mover modulo na parede (312): na vista 2D, clique simples em QUALQUER peca
(porta, gaveta, prateleira, divisoria, puxador) seleciona o modulo e o G
nativo leva o movel; duplo continua isolando a peca. Snap nativo de vertice
(CLOSEST) ligado so' durante a vista e devolvido ao sair. Cotas seguem o
arraste pelo depsgraph (caixa local guardada + matriz, sem reler malha).
`test_paredes_composicao_blender.py`: 40 testes, tres novos. Resize da
porta curva (311): ida e volta exata (bancada curva 5.2 aprovada).

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
| Porta selecionada: Folhas = campo compacto ao lado do ultimo campo (Entre folhas/planos), arrasta e digita (fora do limite da abertura avisa); sem linha de Reposicionar/Frente/Espelhar no menu | `_eh_campo_contador`, `LARGURA_CAMPO_FOLHAS` | portas |
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

- 376: areas_criacao (40 testes): tres pontos arbitrarios/todas as seis ordens, modulo rotacionado/escalado/espelhado, invalidos/coplanares, seis frentes preservando volume/cantos, raio limitado a previa, fluxo CANTO1/2/3/FRENTE/QUANTIDADE, correcao do terceiro ponto, frente obrigatoria, HUD suspensa, entrega/encerramento do modal pai, criacao real nos tres dominios, Backspace e Esc. Fixtures isoladas; harness completo 4.2/5.2: 2860 testes em 64 execucoes, OK. Auditoria headless: primitivas do callback real e tres prateleiras em caixa 500 x 350 x 700 mm, duas imagens conferidas. GUI atualizada para tres pontos e frente explicita, execucao exige PC livre.

- 377: gavetas (57 testes) / areas_criacao (41): modulo fixo na entrada, filhos internos incluidos, outro modulo/teto invertido/curva excluidos do translate nativo, identificacao limitada aos alvos mesmo com malha externa coincidente, primeiro ponto sem selecao fixa alvo, ativo desselecionado nao fixa, confirmar/Esc/erro restauram flags e cursor sem revelar ocultos. Raio nativo atravessa oclusor externo; volume livre e HUD/B respeitam o modulo. Fixture isolada; macro interativa substituida no alias do dono para nao iniciar gesto em background. Harness completo 4.2/5.2: 2876 testes em 64 execucoes, OK. Auditoria headless: teto intercepta raio global, BVHs do modulo retornam somente Lateral Esquerda/Base; caixa 964 x 600 x 1364 mm e tres gavetas conferidas em renders. Gestos GUI reais nao executados.

- 378: gavetas 61 / areas_criacao 42 / operadores 56 / gaveta 86. Camera livre entre pontos e na frente/volume livre, sem translate no hover; PRESS inicia gesto com release_confirm, confirmacao nao reabre; navigate/walk/fly/pan/zoom pelo keymap, Shift+scroll preserva quantidade. Grupo da porta a partir de folha/puxador, H nativo com agregados; Esconder porta usa mesma descendencia, respeita camada, preserva Mesh, vizinhos, timer e undo/redo; Alt+H nativo. Menu Shift+G conserva grupos do Blender. Volume livre laranja/30 px nas tres larguras; snapshot de altura atualizado/revisado. Harness completo 4.2/5.2: 2900 testes em 64 execucoes, OK. Primitivas do callback de menu renderizadas e conferidas em 190/320/564 px: destaque laranja do volume e acao de esconder porta. GUI inclui Walk/D entre pontos, ainda nao executada; execucao condicionada a PC livre.

- 379: prateleiras 60, divisorias 42, hud 186. Scroll da cota V subdivide vao vazio com apoios fixos, modelo/material/E herdados, estoque nativo sem fonte, reduzir/zero/Esc/undo/redo, falta de espaco atomica e Enter tratando quantidade. Vinculo cabinet_blocagem_uid persistido por particao e sessao comum; HUD/selecao agregam segmentos so' na orientacao ativa; legados via apoio real no timer, blocagens independentes preservadas. Fixture com gavetas a direita verifica Mesh/pose/quantidade do lado oposto. Harness completo 4.2/5.2: 2932 testes em 64 execucoes, OK. Auditoria em cena temporaria: vao inferior 700 mm, tres prateleiras novas e quatro vaos de 161.5 mm; cotas direitas preservadas, divisorias com apenas dois vaos horizontais de 473 mm. GUI de scroll/Enter/Esc preparada, nao executada sem PC livre.

## Regressao de contorno apos Tab e snap de internos (v380)

- `test_tab_em_canto_da_chapa_plana_mantem_cotas_nas_arestas_reais`: aquece o cache de uma chapa 600 x 2000 x 18 mm, entra em Edit Mode nativo, move 80 mm um canto de uma unica pele e sai por Tab. Todas as linhas da HUD precisam coincidir com arestas reais; medida de cada cota e' seu comprimento, E nominal 18 mm. Falha antiga reproduzida com expectedFailure e depois sem marcador: um perfil era projetado no verso distinto.
- `test_seta_do_topo_editado_segue_a_aresta_clicada`: callback de desenho recebe as pontas projetadas da propria aresta, incluindo topo obliquo e verso horizontal.
- `test_contorno_com_peles_diferentes_e_cache_sem_extracao_no_redraw`: desenho/menu somente numericos; Mesh, pose, faces, UV e material preservados.
- `test_segundo_tab_sem_mudar_envelope_atualiza_as_cotas_reais`: nova edicao interna sem mudar L/A/E invalida o cache e conserva cotas sobre a madeira.
- `test_cota_real_de_pele_editada_preserva_mesh_e_undo_redo`: edita a aresta por UID, conserva o par topologico, mesmo ID de Mesh e E nominal; undo/redo restauram medidas e contorno.
- `test_cota_de_pele_editada_isola_mesh_compartilhada_so_apos_validar`: UID invalido nao separa a malha; edicao valida isola apenas o usuario editado.
- `test_b_ativa_snap_nativo_nos_tres_pontos_sem_confirmar_ao_soltar_tecla`: B em CANTO1/2/3 de prateleiras/divisorias/gavetas abre o translate VERTEX/EDGE_MIDPOINT; soltar B nao confirma. Cenario reproduzido como falha esperada antes da correcao. Clique/arraste e navegacao entre pontos continuam cobertos pelas regressoes existentes.
- Auditoria headless em cena descartavel, comparacao antes/depois com arestas numericas da HUD renderizadas: erro maximo anterior 80 mm, corrigido 0 mm. O projeto aberto e a biblioteca real nao foram editados. Gestos de interface ao vivo nao executados nesta entrega.
- AGENTS.md/CLAUDE.md da raiz e dos testes explicitam teste automatizado no mesmo commit para todo bug corrigido, com falha antes da correcao e sucesso depois.
- Validacao final: HUD 192 e gavetas 62 por versao; harness completo Blender 4.2/5.2, 2946 testes em 64 execucoes, tudo OK. Pacote 380 conferido com os 39 arquivos Python identicos ao fonte.

## Fechamento vertical com chapa de moldura (v381)

- `test_tab_afina_moldura_gira_vertical_e_hud_acompanha_malha`: chapa marcada como moldura, 649 x 2531 x 15 mm, cache aquecido; Tab afina X para 64.9 mm fora do centro e R gira 90 graus. Saida atualiza medidas e caixa da HUD sobre arestas reais; conserva Mesh, coordenadas mundiais e parametros do grupo da porta. Reproducao da falha antiga com expectedFailure antes da correcao: molduras eram excluidas da absorcao.
- `test_moldura_ja_editada_corrige_limites_no_timer_sem_novo_tab`: geometria ja' alterada e nenhuma transicao de Edit Mode guardada, como ao reabrir uma cena; o timer reconhece a divergencia pela bound_box nativa e recupera as medidas. Tambem reproduzido como falha esperada no codigo anterior.
- `test_fechamento_mais_estreito_que_E_mantem_contorno_e_espessura`: largura 3 mm e E 15 mm, sem trocar eixos nem engrossar a peca.
- `test_moldura_sincronizada_nao_reextrai_malha_a_cada_timer`: tres verificacoes sem mudanca nao absorvem nem reconhecem a malha novamente.
- `test_undo_redo_do_fechamento_vertical_conserva_cotas_e_geometria`: tres ciclos nativos de undo/redo retornam entre a largura original e a afinada, com contorno real e E preservada.
- Auditoria visual headless com as coordenadas reais da HUD: antes, moldura estreita dentro da caixa de 649 mm; depois, contorno acompanha os 64.9 mm da madeira. Cena descartavel; projeto aberto e biblioteca real preservados. Gestos na interface ao vivo nao executados.
- Validacao final: HUD 197 por versao; harness completo Blender 4.2/5.2 com 2956 testes em 64 execucoes, tudo OK. Pacote 381 conferido com 39 arquivos Python identicos ao fonte; espelhos e limites dos guias conferidos.
