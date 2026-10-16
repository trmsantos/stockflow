# Contar o stock

Ecrã: **Contar** (`/contar`).

Uma contagem compara o que está na prateleira com o que o sistema diz.

1. Escolhe a loja e toca em "Começar contagem".
2. A contagem percorre a loja por **zonas**, na ordem física (balcão,
   frigorífico, arca, armazém). O filtro de zona está no URL
   (`/contar?zona=...`).
3. Em cada linha escreve-se quantos estão na prateleira. Uma linha sem valor
   está **por contar** — zero é "contei e não havia nada", que é diferente.
4. Numa zona cega o esperado só aparece no fim.

**Fechar.** Com tudo contado, o fecho mostra as diferenças e grava um movimento
de ajuste por cada uma, com o autor e a justificação. Antes do fecho, uma
contagem **não mexe no stock**.

O esperado de cada linha é uma fotografia do momento em que a contagem foi
aberta: numa contagem antiga pode já não ser o saldo de agora.

Para corrigir uma contagem fechada não se reescreve nada — conta-se outra vez.
