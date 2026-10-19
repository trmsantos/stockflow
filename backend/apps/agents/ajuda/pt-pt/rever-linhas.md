# Rever e confirmar as linhas de uma receção

Ecrã: **Receber → a receção** (`/receber/<id>`), ou a lista filtrada em
`/receber?estado=revisao`.

Cada linha do documento precisa de quatro coisas antes de entrar no stock:

- **o artigo** do catálogo a que corresponde (o sistema sugere pelo código do
  fornecedor que já aprendeu);
- **a quantidade recebida**, que pode ser menor do que a faturada;
- **o lote**, se o artigo exigir lote;
- **a validade**, se o artigo tiver rótulo de validade.

O lote e a validade estão **na embalagem**, não no documento: escreve-os como
estão impressos.

Uma linha pode ser confirmada ou deixada de fora. Uma linha de fora não gera
movimento nenhum — a mercadoria dela não aparece no stock.

Se a receção trouxer refrigerados ou congelados, regista a temperatura à entrega
de cada classe presente.

No fim, "Confirmar e dar entrada" grava os movimentos de entrada com o lote, a
validade e o autor. Nada se reescreve depois: para corrigir, regista-se um
movimento novo.
