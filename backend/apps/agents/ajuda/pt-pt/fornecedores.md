# Fornecedores

Ecrã: **Receber** (`/receber`) — é nas receções que um fornecedor aparece.

Um fornecedor tem nome e, quando se sabe, NIF. O NIF serve para o reconhecer num
documento; o assistente não o diz a ninguém.

Numa receção, o fornecedor pode estar de duas maneiras:

- **ligado ao catálogo** — a receção aponta para o fornecedor, e então conta
  para o histórico de preços e para a memória de códigos;
- **só impresso** — o nome veio no documento e ninguém o ligou ainda. Nesse caso
  a receção aparece na mesma, mas fica fora do histórico desse fornecedor.

**Memória de códigos.** Ao confirmar uma receção, o par (fornecedor, código do
artigo no documento) fica guardado. Na receção seguinte do mesmo fornecedor, as
linhas já vêm sugeridas.

**Preços.** O histórico de preços de um artigo é por fornecedor e por mês, só com
receções confirmadas e sem IVA. As guias de remessa não têm preço; as notas de
crédito e de débito são correcções e ficam de fora da média.
