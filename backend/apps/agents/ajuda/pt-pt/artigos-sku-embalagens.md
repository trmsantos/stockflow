# Artigos, SKU e embalagens

Um artigo tem duas unidades: a **base**, em que se conta (g, ml, un), e a de
**apresentação**, em que se fala (kg, L, un). O factor liga as duas: 1 kg =
1000 g. As quantidades guardam-se sempre na base.

Outros campos do artigo:

- **SKU** — o código interno, único neste estabelecimento;
- **mínimo** — na unidade base; zero é "sem mínimo";
- **exige lote** — se cada entrada tem de trazer um lote;
- **rótulo de validade** — "consumir até" ou "consumir de preferência antes de";
- **conservação** — ambiente, refrigerado ou congelado, que é o que decide se a
  receção pede temperatura.

**Embalagens.** Um artigo pode ter várias ("saco de 25 kg", "caixa de 12"), cada
uma com a quantidade em unidade base e, se houver, o código de barras. Servem
para a receção saber quanto é "2 caixas".

**Códigos de fornecedor.** Cada fornecedor chama ao artigo o que quer. Ao
confirmar uma receção, o sistema aprende o código e da próxima vez já sugere o
artigo.

Ecrã: a ficha de cada artigo está em **Stock → o artigo** (`/stock/<artigo>`).
