import type { PT } from "./textos.pt";

/**
 * A copy do módulo `recipes`, em **inglês**, anotada com o tipo do português.
 *
 * `typeof PT` é o contrato inteiro: uma chave a faltar dá `TS2741`, uma a mais
 * dá `TS2353`, e uma função de interpolação com outra assinatura também não
 * compila (ADR 0019, decisão 3).
 *
 * ## Três escolhas de vocabulário que não são óbvias
 *
 * **"Ingredient cost"** e nunca "dish cost" nem "plate cost" — é a ADR 0035
 * (decisão 9) na outra língua. O termo do sector é *food cost*, e usá-lo cru
 * aqui era trocar uma palavra que qualquer pessoa lê por um jargão que só quem
 * já o conhece reconhece; "ingredient cost" diz exactamente o que o número é.
 *
 * **"Batch"** para `fornada`: é a palavra da produção, e "baking" prendia a
 * tradução à pastelaria quando a mesma ficha serve uma cozinha.
 *
 * **"Yield"** para `rendimento`, que é o termo de receituário em inglês, e
 * **"Certainty"** para `certeza` — não "accuracy", que afirmaria uma medida de
 * erro que esta coluna não tem.
 */

export const EN: typeof PT = {
  accoes: {
    novaFicha: "New recipe",
    criarPrimeira: "Create the first recipe",
    gravar: "Save the recipe",
    aGravar: "Saving…",
    guardar: "Save changes",
    editar: "Edit",
    cancelar: "Cancel",
    acrescentar: "Add ingredient",
    remover: (artigo: string) => `Remove ${artigo}`,
    removerLinha: "Remove this line",
    voltar: "Back to recipes",
    arquivar: "Archive",
    reactivar: "Reactivate",
    aArquivar: "Archiving…",
    verFichaExistente: "Open the recipe that already exists",
    aCarregarLista: "Loading the recipes…",
    aCarregarFicha: "Loading the recipe…",
  },

  lista: {
    titulo: "Recipes",
    tabela: "Recipes of this establishment",
    procurar: "Search recipe",
    procurarPista: "Name or code of the finished item",
    estado: "Recipes to show",
    activas: "Active only",
    todas: "Active and archived",
    erro: "Could not load the recipes.",
    vazioTitulo: "There are no recipes yet",
    vazioCorpo:
      "A recipe says what goes into one batch. It is where the ingredient cost of everything this kitchen produces comes from.",
    semCorrespondenciaTitulo: "No recipe matches",
    semCorrespondenciaCorpo:
      "The search covers the name and the code of the finished item. Archived recipes only show up with the filter on “active and archived”.",
    limparFiltros: "Clear the filters",
    contagem: (n: number) => (n === 1 ? "1 recipe" : `${String(n)} recipes`),
    rodape: (mostradas: number, total: number | null) =>
      total === null
        ? `${String(mostradas)} recipes, in alphabetical order of the finished item, archived ones last.`
        : `${String(mostradas)} of ${String(total)} recipes. In alphabetical order of the finished item, archived ones last.`,
  },

  colunas: {
    acabado: "Finished item",
    fornada: "Batch",
    ingredientes: "Ingredients",
    custoDaFornada: "Ingredients/batch",
    custoUnitario: "Ingredients per unit",
    certeza: "Certainty",
    ingrediente: "Ingredient",
    porFornada: "Per batch",
    saiDoStock: "Leaves stock",
    custoDoIngrediente: "Item cost",
    custoDaLinha: "Line cost",
  },

  ficha: {
    tabela: "Ingredients of this recipe",
    numeros: "The numbers of this recipe",
    naoExisteTitulo: "This recipe does not exist",
    naoExisteCorpo:
      "The address does not match any recipe of this establishment. It may have been removed, or belong to another one.",
    erro: "Could not load this recipe.",
    arquivada: "Archived",
    arquivadaNota:
      "This recipe is archived: it can still be read and does not show up in the list by default.",
    campoFornada: "Batch",
    campoIngredientes: "Ingredients",
    campoCustoDaFornada: "Ingredients/batch",
    campoCustoUnitario: (unidade: string) => `Ingredients per ${unidade}`,
    notaDaBase: (base: string) => `= ${base}`,
    artigoArquivado: "Archived item",
    rendimentoNeutro: (factor: string) =>
      `Yield ${factor}: what leaves stock is exactly what the recipe writes.`,
    rendimento: (factor: string) =>
      `Yield ${factor}: the recipe writes what stays in the product, and what leaves stock is that amount divided by this factor.`,
  },

  custo: {
    conhecido: "Known",
    estimado: "Estimated",
    desconhecido: "Unknown",
    semValor: "—",
    rotulo: "Ingredient cost:",
    tudoComCusto: "Every ingredient has a recorded cost.",
    semNenhumCusto: "No ingredient has a recorded cost.",
    semCusto: (quantos: number, total: number) =>
      quantos === 1
        ? `1 of the ${String(total)} ingredients has no recorded cost.`
        : `${String(quantos)} of the ${String(total)} ingredients have no recorded cost.`,
  },

  formulario: {
    tituloNova: "New recipe",
    tituloEditar: "Edit the recipe",
    acabado: "Finished item",
    acabadoAjuda:
      "The item this recipe produces. It is the identity of the recipe and cannot be changed later.",
    acabadoFixo: "The finished item cannot be changed: it is the identity of the recipe.",
    escolherArtigo: "Choose…",
    fornada: "Batch",
    fornadaAjuda:
      "How much finished product comes out of one batch. The ingredient amounts below are for this batch — not for a single unit.",
    unidade: "Unit",
    rendimento: "Yield",
    rendimentoAjuda:
      "Almost always 1: the process loss is already in the batch, and putting it here again counts it twice. It only changes when the weight changes on its own, such as raw to cooked rice.",
    ingredientes: "Ingredients",
    ingredientesAjuda:
      "Do not list water or salt: an item with no cost drags the whole recipe to “estimated” and keeps it there forever.",
    procurar: "Search item",
    procurarPista: "Filters the items offered",
    quantidade: "Amount",
    semArtigos: "No catalog item matches this search.",
    tectoDoCatalogo: (quantos: number) =>
      `The catalog has more items than the ${String(quantos)} that fit in this list. Use the search to reach the others.`,
    erroAcabado: "Choose the finished item.",
    erroFornada: "Write a batch greater than zero.",
    erroRendimento: "Write a yield greater than zero.",
    erroSemLinhas: "A recipe needs at least one ingredient.",
    erroArtigoDaLinha: "Choose the item of this line.",
    erroQuantidade: "Write an amount greater than zero.",
    erroRepetido: "This item is already in the recipe.",
    erroAoGravar: "Could not save the recipe.",
    semPermissaoTitulo: "Writing recipes is for whoever manages",
    semPermissaoCorpo:
      "A recipe defines the product and its cost, and changing one amount changes the cost of everything that comes out of it. Whoever manages the establishment writes it; the list and the recipe can be read with any role.",
    jaExisteTitulo: "This item already has a recipe",
    jaExisteCorpo:
      "Each item has exactly one recipe. The one that exists is behind the button below — edit it instead of creating a second one.",
  },
};
