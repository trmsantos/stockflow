/**
 * A copy dos componentes **partilhados**, em pt-PT.
 *
 * São quatro palavras e um catálogo só para elas parece muito — mas o que está
 * aqui é a copy que aparece em **todos** os ecrãs (o botão de "tentar outra vez"
 * de um erro, o anúncio de um esqueleto, o prefixo que diz a quem ouve que uma
 * régua está a filtrar), e ela não pode viver no catálogo de uma feature: o
 * `src/components/` é importado por todas e não importa nenhuma.
 *
 * Foram encontradas a 2026-10-07 pela regra 1a do `check-textos.mjs`, no dia em
 * que ela passou a contar palavras em vez de acentos. Nenhuma delas tem acento
 * no sítio que o critério antigo olhava, e por isso nenhuma tinha sido vista.
 */
export const PT = {
  /** O verbo de recuperar de um erro. Um só, em toda a aplicação. */
  tentarOutraVez: "Tentar outra vez",
  /** O que um esqueleto diz a quem não o vê. */
  aCarregar: "A carregar…",
  /**
   * O prefixo do campo activo numa régua de contadores, para quem ouve. Acaba
   * com espaço de propósito: o que se lê a seguir é o nome do campo.
   */
  aFiltrarPor: "A filtrar por ",
  /**
   * O cabeçalho da coluna da barra, só para quem ouve: a barra não tem eixo,
   * logo um rótulo visível em cima dela era uma etiqueta sem conteúdo.
   */
  proporcao: "Proporção",
};
