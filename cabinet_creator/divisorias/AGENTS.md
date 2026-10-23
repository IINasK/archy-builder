# Setor divisorias

## Papel e fronteiras

Divisorias verticais segmentam os sistemas internos que atravessam.
[Prateleiras](../prateleiras/AGENTS.md) e [gavetas](../gavetas/AGENTS.md)
continuam donos dos grupos resultantes; apoio pertence a' chapa real.
O gesto e' `gavetas.AssistenteDoVao`; nao criar outro assistente ou modulo.

## Localizar tarefas

| Tarefa | Funcao / arquivo |
|---|---|
| Medidas e montagem | `calcular`, `montar`, `vao` em `__init__.py` |
| Criar/editar | `criar_divisorias`, `editar`, `OBJECT_OT_criar_divisorias` em `__init__.py` |
| Validar e partir | `_plano`, `_partir`, `_separar_prateleiras` em `__init__.py` |
| Cortar chapa existente | `_cortar_chapa` em `__init__.py` |
| Sistemas criados depois | `particionar_grupo` em `__init__.py` |
| Apoios/resize/exclusao | `_apoios`, `limitar_vao`, `atualizar_dependentes` em `__init__.py` |

## Decisoes e armadilhas

- Mesmo `AssistenteDoVao`/SNAP nativo das prateleiras, na vertical.
  Seguir o protocolo compartilhado de gavetas, sem varreduras no gesto.
- Segmentar gavetas/prateleiras atravessadas, inclusive criadas DEPOIS,
  descontando E da divisoria. Apoios por UID da chapa REAL; sem modulo novo.
- Validar TODOS os vaos ANTES de mutar. Uma metade valida nao autoriza
  deixar sistemas parcialmente divididos quando outra metade falha.
- Prateleira: bisect/cap BMesh na MESMA Mesh, preservando altura, material
  E recortes. Nao reconstruir como caixa nem trocar IDs sobreviventes.
- Grupos resultantes continuam editaveis E independentes; manter
  os contratos individuais de gavetas/prateleiras.
- Excluir apoio conserva o ULTIMO limite; nao fundir sistemas editados.
- Conjunto de gavetas exige divisoria atravessando altura E profundidade
  INTEIRAS; prateleiras permitem selecao PARCIAL do grupo.

## Suites

Em `../../tests/`: `test_divisorias_blender.py`, `test_gavetas_blender.py`,
`test_prateleiras_blender.py`. Conferir tambem sistemas criados depois,
falha sem mutacao parcial, malha recortada e exclusao de apoio.
Harness e fixtures: [tests](../../tests/AGENTS.md).
