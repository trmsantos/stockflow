# Receitas e produção

Uma receita diz o que é preciso para produzir **uma unidade de apresentação** do
artigo acabado: um quilo de massa, uma unidade de pastel.

**Rendimento (`yield_factor`).** É o que sobra depois das perdas de preparação.
Com rendimento de 90 %, para obter 1 kg de acabado gastam-se ingredientes para
1,11 kg. Por isso a ficha tem duas colunas: a quantidade **de lista** (o que a
receita escreve) e o **consumo real** (lista a dividir pelo rendimento), que é o
que sai do stock.

**Produzir.** Uma produção consome os ingredientes pelos lotes que expiram
primeiro e dá entrada do acabado, tudo no mesmo movimento de livro. O custo da
produção é o custo dos ingredientes que de facto saíram, guardado nesse momento.

**Custos.** A ficha mostra dois números e são diferentes: o **teórico** (o que
custaria hoje, com o custo médio actual de cada ingrediente) e o **real da
última produção** (o que custou de facto). Os euros são do dono e do gerente.

Uma receita inactiva não pode ser produzida.

Nesta versão a produção **ainda não tem ecrã próprio**: o assistente lê as
receitas e as produções, e os movimentos aparecem no histórico do artigo
(`/stock/<artigo>`).
