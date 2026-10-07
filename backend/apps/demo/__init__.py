"""O semeador do estabelecimento de demonstração (ADR 0018).

**Um módulo sem models, sem migrações, sem `api.py` e sem endpoints.** Só um
comando de `manage.py`. É um **sumidouro de escrita**: as únicas arestas são de
saída, e um contrato do import-linter proíbe que alguém o importe — o espelho do
`reporting` da ADR 0013, do outro lado.

## Porque é que isto não vive dentro de um módulo de domínio

O `purchasing` podia hospedar o semeador sem nenhuma aresta nova, e é
precisamente por isso que não o hospeda. Um semeador **dentro** de um módulo de
domínio está dentro da casa e pode escrever directamente nos `models.py` dele; de
fora, o import-linter não o deixa fazer outra coisa que não seja entrar pela porta
da frente de cada módulo.

É isso que compra a propriedade que sustenta a decisão 1 da ADR 0018 — "tudo lá se
comporta exactamente como em produção": os dados do demo são produzidos pelos
**mesmos services** que os dados reais, logo o ledger, o FEFO, o CMP e os lotes
comportam-se lá exactamente como aqui. Um semeador que escreva `StockLevel` à mão
produz um estabelecimento que **ensina um produto que não existe**.

## O que este módulo ainda não semeia, e porquê

Hoje semeia o estabelecimento e a pertença, e mais nada — porque mais nada existe:
o `catalog`, o `inventory`, o `purchasing` e o `recipes` são conchas (zero models,
zero migrações). Os artigos, os lotes, as validades, os movimentos, a contagem com
divergência e o desperdício com motivo entram quando as tabelas entrarem, e entram
**por aqui**, pela porta da frente de cada módulo.

A ADR 0018 manda **consultar o `domain-expert`** para esses valores, e o gatilho é
esse: os números são afirmações de domínio e um demo que mostre números que um
pasteleiro não reconhece é pior do que não ter demo. Consultá-lo hoje produzia
respostas que ninguém pode usar durante meses.
"""
