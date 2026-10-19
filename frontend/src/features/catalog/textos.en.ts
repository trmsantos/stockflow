import type { PT } from "./textos.pt";

/**
 * A copy do módulo `catalog`, em **en**. Tem o tipo de PT e não compila se divergir.
 */

export const EN: typeof PT = {
  accoes: {
    novoArtigo: "New item",
    criarPrimeiroArtigo: "Create first item",
    aCriarArtigo: "Creating item…",
  },

  colunas: {
    artigo: "Item",
    unidadeBase: "Base unit",
    apresentacao: "Display",
    lotes: "Lots",
    minimo: "Minimum",
    estado: "Status",
  },

  catalogo: {
    titulo: "Catalog",
    procurar: "Search item…",
    procurarAriaLabel: "Search items",
    nenhum: "No items created",
    nenhumDescricao: "Start by adding an item to the catalog.",
    erroAoCarregar: "Error loading catalog",
    tentarOutraVez: "Try again",
    sim: "Yes",
    nao: "No",
  },

  novo: {
    titulo: "Create new item",
    embreve: "This feature will be implemented soon.",
  },

  detalhe: {
    titulo: "Item details",
    embreve: "This feature will be implemented soon.",
  },
};
