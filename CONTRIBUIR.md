# Como contribuir

Obrigado por ajudar a melhorar o Cabinet Creator. O projeto e' gratuito,
esta' em desenvolvimento e aceita relatos, sugestoes e pull requests.

## Relatar um problema

Abra uma issue informando:

- Versao do Blender e sistema operacional.
- Passos para reproduzir, desde a criacao de uma cena simples.
- Resultado esperado e o que aconteceu.
- Imagem ou arquivo minimo de exemplo, sem dados privados de clientes.

## Alterar o codigo

1. Faca um fork e crie uma branch para uma alteracao delimitada.
2. Leia [AGENTS.md](AGENTS.md) e consulte o setor correspondente em
   [ARQUITETURA.md](ARQUITETURA.md). Nao e' necessario carregar todos os guias.
3. Preserve as malhas, materiais, propriedades publicas e arquivos existentes.
4. Para corrigir um bug, inclua um teste que reproduza a falha. Para uma
   melhoria, descreva os parametros e o resultado esperado.
5. Registre o cenario em [tests/FUNCIONALIDADES.md](tests/FUNCIONALIDADES.md)
   e execute as suites pertinentes. Antes da entrega, execute o harness completo.
6. No pull request, explique o problema, a mudanca e o que foi testado.

Os testes usam cenas e pastas temporarias; nao escrevem na biblioteca real
nem no projeto aberto. Testes que abrem uma janela do Blender exigem
autorizacao de quem estiver usando o computador.

Com o Blender disponivel:

```sh
blender --background --factory-startup --python tests/rodar_testes.py
```

O harness procura as instalacoes do Blender 4.2 e 5.2 no Windows. Consulte
[tests/AGENTS.md](tests/AGENTS.md) para comandos por suite e por versao.

## Licenca das contribuicoes

Envie apenas conteudo que voce possa disponibilizar sob [CC0 1.0](LICENSE).
Recursos externos precisam ter origem e licenca identificadas; preserve
seus avisos. Veja tambem [NOTICE](NOTICE).
