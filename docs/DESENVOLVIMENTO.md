# Guia de desenvolvimento

[Guia do usuario](../README.md) | **Desenvolvedores**

Esta pagina e' para quem deseja estudar, modificar ou contribuir com o
Archy Builder. Para apenas usar o add-on, siga o [guia do usuario](../README.md).

## Obtenha o codigo

Clone o repositorio ou use Code -> Download ZIP e extraia o projeto:

```sh
git clone https://github.com/IINasK/archy-builder.git
cd archy-builder
```

Antes de alterar arquivos, leia [AGENTS.md](../AGENTS.md) e consulte
[ARQUITETURA.md](../ARQUITETURA.md) para localizar o setor responsavel.

## Execute o codigo durante o desenvolvimento

No Windows, o comando abaixo cria uma junction entre o repositorio e a
pasta de add-ons da versao indicada do Blender:

```sh
python vincular_blender.py 5.2
```

Depois, reinicie o Blender e ative Archy Builder nas preferencias. Alteracoes
passam a ser lidas do repositorio. Use uma cena de teste, separada do seu
projeto de trabalho. O script recusa substituir uma instalacao comum que
possa conter modelos do usuario.

## Gere o pacote de instalacao

Na raiz do projeto, execute:

```sh
python build.py
```

O resultado e' **`dist/archy_builder.zip`**, pronto para instalar. O ZIP
automatico de codigo-fonte do GitHub inclui o repositorio completo e precisa
ser extraido e empacotado antes da instalacao como add-on.

Se Python nao estiver no PATH, use o interpretador da sua instalacao:

```powershell
& 'C:\Program Files\Blender Foundation\Blender 5.2\5.2\python\bin\python.exe' build.py
```

O pacote inclui a biblioteca, LICENSE e NOTICE e descarta caches, backups
e temporarios. A pasta interna **`cabinet_creator`**, os tipos de editor,
propriedades e identificadores persistidos devem ser preservados para
manter a compatibilidade com arquivos existentes.

## Teste as alteracoes

O harness usa cenas e pastas temporarias e executa as suites nas versoes
instaladas do Blender. Para rodar tudo sem abrir janelas:

```powershell
& 'C:\Program Files\Blender Foundation\Blender 5.2\5.2\python\bin\python.exe' tests/rodar_testes.py
```

Durante o trabalho, limite a execucao ao setor alterado:

```powershell
& 'C:\Program Files\Blender Foundation\Blender 5.2\5.2\python\bin\python.exe' tests/rodar_testes.py -- --suites editor empacotamento
```

Antes da entrega, execute a suite completa. Testes de interacao com `--gui`
abrem janelas e exigem autorizacao de quem estiver usando o computador.
Nao execute testes sobre a cena aberta nem sobre a biblioteca real.
Detalhes em [tests/AGENTS.md](../tests/AGENTS.md).

O codigo e' testado em Blender 4.2 e 5.2. Presets salvos em Blender 5.x
podem nao abrir no 4.2; os testes distinguem codigo e arquivos compativeis.

## Envie uma contribuicao

1. Faca um fork e uma branch para uma alteracao delimitada.
2. Siga o guia do setor e preserve os dados ja' salvos nos projetos.
3. Inclua um teste de regressao para cada bug corrigido. Para melhorias,
   descreva os parametros e resultados esperados.
4. Registre o cenario em [FUNCIONALIDADES.md](../tests/FUNCIONALIDADES.md).
5. No pull request, explique o problema, a mudanca e a validacao realizada.

Codigo, comentarios, UI e commits seguem o portugues ASCII do projeto.
Para interface, consulte [DESIGN.md](../DESIGN.md) e a skill
[cabinet-design](../planejamento/skills/cabinet-design/SKILL.md).

## Licenca e documentacao

O conteudo autoral do projeto esta' disponivel sob [CC0 1.0](../LICENSE).
Envie apenas conteudo que voce possa disponibilizar nesses termos.
Recursos externos devem manter origem, creditos e licenca identificados;
consulte [NOTICE](../NOTICE).

- [Arquitetura e setores](../ARQUITETURA.md)
- [Instrucoes gerais](../AGENTS.md)
- [Biblioteca e presets](../cabinet_creator/biblioteca/AGENTS.md)
- [Testes e cenarios](../tests/FUNCIONALIDADES.md)
- [Historico tecnico](HISTORICO.md)
