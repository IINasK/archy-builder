> Historical technical notes. Current instructions: [architecture](../../ARCHITECTURE.md) and local sector guides. Source paths below are retained only where historically relevant.

# Integracao -- guia transversal

Leitura EXPLICITA pela rota do indice/guia raiz para tarefas de integracao.
Este AGENTS.md esta' em documentos: NAO se aplica automaticamente ao codigo
em outra pasta. Manter este arquivo e `CLAUDE.md` identicos, em ASCII.
Caminhos abaixo partem da raiz do repositorio. Limite: 120 linhas.

Escopo: `archy_builder/integrations/native_conversion.py`, `importacao.py`, `paredes.py`,
`biblioteca.py` e scripts importar/integrar/ajustar/auditar/refinar da raiz.
Nesta etapa, esses modulos e recursos continuam nos caminhos atuais.
`biblioteca.py` usa `__file__` para fotos; `biblioteca/` guarda assets,
nao e' pacote Python. Preservar imports/recarga.
Para formatos, indice, catalogos e historico dos assets, ler explicitamente
`archy_builder/biblioteca/CLAUDE.md`; nao manter outra copia desse contrato.
Frentes: ler `FRONT_GEOMETRY.md`; mudanca visivel: `DESIGN.md` e
`docs/reference/interface.md`.

## Rota de trabalho

Suite = `tests/test_<suite>_blender.py`. Scripts da raiz nao sao suites.

| Tarefa | Arquivo: funcao | Suite |
|---|---|---|
| DXF/categorias | importacao.py: `ler_dxf_promob`, `destino_categoria_promob`, `importar_dxf_promob` | importacao |
| Portas avulsas/assets | importacao.py: `importar_portas_avulsas`, `importar_promob_para_biblioteca` | importacao, biblioteca |
| Sistemas nativos | promob.py: `planejar`, `aplicar`, `marcar_dependentes` | importacao |
| Encaixes/fundos | promob.py: `ajustar_encaixes`, `reencaixar_verticais`, `ajustar_recuo_fundos` | importacao |
| Salvar/inserir/foto | biblioteca.py: `salvar_na_biblioteca`, `inserir_preset`, `gravar_modulo_na_biblioteca`, `preparar_abertura_foto` | biblioteca |
| Face de parede/guias | paredes.py: `associar`, `manter_nas_paredes`, `aplicar_guia` | paredes |
| Lote/publicacao | tools/library/integrate_dxf_library.py: `preparar`, `publicar`; tools/migrations/adjust_fits.py: `validar_destino`, `publicar` | migracoes |
| Retirar variantes auditadas com backup e rollback | tools/migrations/consolidate_library_variants.py: `preparar`, `publicar` | migracoes, biblioteca |
| Corrigir internos dos presets com backup e validacao | tools/migrations/repair_library_internals.py: `preparar`, `publicar` | correcao_internos, migracoes, biblioteca |
| Auditoria dos vaos/colisoes de internos (so leitura) | tools/audit/audit_library_internals.py: `auditar`, `auditar_modulo` | auditoria_internos, biblioteca |
| Soldas unicas/menor gap, backup e publicacao | `tools/migrations/refine_library_joints.py`: `preparar`, `publicar` | solda, soldas_biblioteca, migracoes |
| Auditoria/reparo | tools/migrations/audit_and_repair_integration.py: `capturar`, `verificar_funcoes`, `preparar`; tools/migrations/adjust_doors.py: `preparar` | importacao, migracoes |

## Presets e publicacao

- Editor 365: arraste nasce no NODE_EDITOR proprio, preservando coordenadas globais e destino VIEW_3D. Outros comandos do menu usam `editor.executar`; nao trocar a origem do modal do preset.
- Importacao 364: `novos` do append pode conter RNAs removidos apos resize; sincronizar pela hierarquia nativa no finally, incluindo recriados. Nao apenas ignorar ReferenceError: selecao/Local View/rollback precisam da lista atual.
- Uma SO' biblioteca (`biblioteca.pasta_biblioteca`), fonte unica tambem dos
  modelos do usuario. Limpar entradas antigas antes de registrar a unica.
  Regras de UUID, catalogo no .blend, indice legado e bloqueio: guia de assets.
- Arraste 363: encaixe reduz L/A ate Ajuste maximo (10 mm; zero desliga), sem mudar E/profundidade. Previa numerica; resize so' ao confirmar, sem editar preset. Recusa mostra vermelho/causa; cache so' do modal.
- Clique no preset = posicionador; Salvar gera PNG; objeto de fora vira
  chapa pela FORMA. Abertura real ESQUERDA so' se TODAS as placas couberem
  no apoio; cadeias coplanares invertem ordem sem mover folhas fechadas;
  canto sem apoio conserva articulacao.
- Foto SO' depois de salvar, em copia descartavel, TODAS portas fechadas
  (canto/correr/zigzag tambem), sem mudar lado para fotografar. Quinas com
  contorno legivel, sem triangulacao; restaurar auxiliares/cores.
- `tools/library/integrate_dxf_library.py`: preparo retomavel, hashes/backup/rollback.
  Preparar fora da biblioteca, validar/reabrir .blend/foto/preview e guardar
  originais ANTES de `--aplicar`; conferir hashes antes da primeira escrita.
  Validar caminho real, junction/case e nomes de manifesto; conservar nomes,
  UID, materiais e UUIDs. Atualizar asset nao atualiza exemplares ja' inseridos.
- Migracoes: `tools/migrations/adjust_fits.py`, `tools/migrations/adjust_doors.py`,
  `tools/migrations/adjust_hinges.py`, `tools/migrations/adjust_backs_and_doors.py`,
  `tools/migrations/refine_corners.py`, `tools/migrations/refresh_library_photos.py` e
  `tools/migrations/adjust_left_opening.py`: mesmo preparo validado/backup/publicacao.

## Contratos DXF

- INTEGRACAO, nao copia: `tools/library/import_dxf_library.py` -> importacao -> promob.
  PASTA = aba, ARQUIVO = categoria; Quartos preserva ramos Armarios/Bancadas/
  Escritorios/Superiores, prefixo unico por ambiente. Porta avulsa vira grupo
  de portas (madeira modelada ou quadro/painel medidos), SEM carcaca inventada.
- Contato = BVH nativa depois da caixa; vao vazio do L NAO une modulos.
  Internos suspensos inteiramente contidos acompanham corpo. Sistemas ficam
  DENTRO da montagem do asset, mesmo antiga sem marca; auditar integracao.
- COR de camada: 7 = chapa; 253/254/8 (ferragem/aluminio/puxador) NUNCA viram
  peca de madeira. Trilho/dobradica SEMPRE nossos; quadro de aluminio vira
  CORRER folha Quadro. Fundo fino/travessas do topo = dependentes.
- Ripas/arremates cor 7: aceitar proporcao 1, tolerancia 0,05 mm; nao perder
  apoio 40/15 nem 49,9998 mm. Painel fixo NUNCA articula folhas; porta deixa
  2 mm do arremate E da face de apoio. Dobradica embaixo continua chapa.
- Placa/braco da dobradica = UMA referencia de face/lado/alturas por folha;
  nunca supor frente -Y. L/diagonal usa plano real (`porta_vao_orientado`);
  junta sem apoio vai para lateral externa existente. Editar margem/qtd
  manualmente substitui referencias. Fundo fino nao sustenta dobradica.
- Curva com placa vira folha NATIVA com malha original: Z = flecha, nao
  achatar; alca tangente; R deforma fechada e reancora. Controle explicito
  do add-on, inclusive na adocao; Tab nativo nao ativa solver parametrico.
  Ler contorno real para medidas/puxador tambem nao ativa esse sistema.
- Diagonal: perfil pela maior chapa deitada, nunca travessa; pontas das DUAS
  faces liberam caixa real em 2 mm por consultas nativas na montagem. Normal
  de fora vem da madeira (centro da caixa inverte curvas); lado exige apoio.
- Referencia comum em frentes.py: atributos INT FACE/EDGE semanticos, cache
  numerico na Mesh, invalidacao por Mesh/undo FORA do desenho.
  `porta_linha_frente` so' migra legado; indices nao governam contorno/resize.
  Puxador/Alt/previa usam bordas/normais comuns; PERFIL segue curva; fracao
  legada migra uma vez. Resize reancora pela tangente SEM refazer vertices/
  faces editados. Preservar modelagem e regressao de resize da curva controlada.
- Coberturas/entre-folhas medidos (`respiro_original`), normal da CHAPA
  (placa tem ruido); apoio diagonal usa dobradica angular. Perfil nosso:
  superiores BAIXO, inferiores CIMA, torres LADO.
- Frente com caixa/cesto = gavetas NOSSAS por FACE, inclusive ilhas viradas;
  nunca converter lateral inteira. Preservar coberturas por lado/alturas;
  edicao manual substitui referencia. Prateleiras adotam UID/material/recorte
  e vaos LIVRES. Auditoria: `tools/migrations/audit_and_repair_integration.py`.
- Base/tampo com recuo <=3,1 mm vai a' quina externa por `ajustar_encaixes`,
  sem mudar E/forma/sistemas; refazer ancoras. Alongar divisoria que ENCOSTAVA
  na face real para fechar fresta. Fundo 5 mm, canal a 15, entra 7; DXF
  exige recuo MINIMO 15. Fundo parcial/ortogonal guarda margens por PLANO,
  nunca expande pela caixa inteira. Ilha: frente unica (+X/-Y da foto),
  oposta vira fundo; conservar cantos.
- ALVENARIA (393): usuario define uma malha no menu; raycast nativo ignora
  as nao definidas. DIREITO no modulo, solto em face vertical = costas;
  horizontal para cima = base no piso, em pe. Sem limite de tamanho/vao;
  folga pelo G, cota Afast. e zero. Teto e' referencia, nao apoio de armario.
  Guias editaveis; `OBJECT_OT_arrastar_na_parede` conserva esse gesto.

Validacao: ler `tests/CLAUDE.md`; testes NUNCA escrevem na biblioteca real.
Redirecionar `pasta_biblioteca`/`opcoes._pasta_addon` antes de register e usar
fixtures/temporarios; integridade real so' leitura. Preset 5.x nao abre em
4.2: pular teste incompativel. GUI so' com autorizacao de PC livre AGORA.
