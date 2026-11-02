import type { PT } from "./textos.pt";

/**
 * A copy do módulo `inventory`, em **inglês**, anotada com o tipo do português.
 *
 * Servida desde 2026-10-07 a um browser que peça inglês, e verificada pelo
 * compilador desde sempre: o `typeof PT` é o contrato inteiro, e uma função com
 * outra assinatura não compila.
 *
 * ## Cinco escolhas de vocabulário
 *
 * **"Item"** para `artigo`: é a palavra de stock ("item below minimum"), e
 * "article" ou "product" diriam outra coisa num produto que já tem `product` como
 * campo do contrato.
 *
 * **"Lot"** para `lote`, e não "batch": o campo do contrato é `lot_code`. Numa
 * pastelaria diz-se "batch" para uma fornada, e é exactamente por isso que ela
 * não serve aqui — a fornada é o `production_*` da ADR 0014, não o lote.
 *
 * **"Throw away"/"thrown away"** para `deitar fora`, como o `pergunta` da rota no
 * `shell/textos.en.ts` ("How much did I throw away?"). Duas formas para o mesmo
 * gesto no mesmo produto é o que faz uma app parecer montada por duas pessoas
 * que não falaram.
 *
 * **"Loses quality"/"lost quality"** para o `best_before`, e **não** "past its
 * best": o rodapé dos Alertas **cita** as palavras que a célula mostra, logo as
 * duas frases têm de ser a mesma. É a mesma amarra que existe em português.
 *
 * **"Location"** para `localização` **e** para a `loja` do seletor da contagem: o
 * contrato chama-lhe `Location` (ADR 0005), e um segundo nome inglês para a mesma
 * coisa era uma distinção que o domínio não tem.
 */
export const EN: typeof PT = {
  accoes: {
    verOStock: "See the stock",
    aRegistar: "Recording…",
    aCarregarStock: "Loading the stock…",
    aMenos: "short",
    aMais: "over",
  },

  colunas: {
    artigo: "Item",
    quantidade: "Quantity",
    minimo: "Minimum",
    estado: "Status",
    validade: "Expiry",
    onde: "Where",
    valor: "Value",
    porque: "Why",
    lote: "Lot",
    accao: "Action",
    hora: "Time",
    motivo: "Reason",
    quem: "Who",
    movimento: "Movement",
    contado: "Counted",
    esperado: "Expected",
    diferenca: "Difference",
  },

  vocabulario: {
    estadoNegativo: "Negative",
    estadoEsgotado: "Out of stock",
    estadoBaixo: "Low",
    estadoOk: "OK",
    movimentoEntrada: "Receipt",
    movimentoConsumo: "Consumption",
    movimentoDesperdicio: "Waste",
    movimentoAjuste: "Adjustment",
    movimentoTransferenciaSaida: "Transfer (out)",
    movimentoTransferenciaEntrada: "Transfer (in)",
    movimentoDevolucao: "Return",
    /**
     * As duas pernas de uma fornada. "Ingredients" e "output" e não "out"/"in":
     * numa produção o que sai e o que entra são coisas diferentes, ao contrário
     * de uma transferência, onde é o mesmo artigo a mudar de sítio.
     */
    movimentoProducaoConsumo: "Production (ingredients)",
    movimentoProducaoEntrada: "Production (output)",
    motivoExpirado: "expired",
    motivoEstragado: "spoiled",
    motivoQuebra: "breakage",
    motivoPerdaDePreparacao: "prep loss",
    motivoOutro: "other",
  },

  validade: {
    semValidade: "no expiry date",
    expirou: (quando: string) => `expired ${quando}`,
    expiraHoje: "expires today",
    expiraQuando: (quando: string) => `expires ${quando}`,
    expiraA: (data: string) => `expires on ${data}`,
    perdeuQualidade: (quando: string) => `lost quality ${quando}`,
    perdeQualidade: (quando: string) => `loses quality ${quando}`,
    melhorAntesDe: (data: string) => `best before ${data}`,
    semRotulo: "expiry date",
    consumirAte: "use by (legal limit)",
    consumirPreferencialmente: "best before (quality)",
    titulo: (lote: string, natureza: string, data: string) =>
      `Lot ${lote} · ${natureza} ${data}`,
    tituloSemLote: (natureza: string, data: string) => `No lot · ${natureza} ${data}`,
  },

  filtros: {
    procurar: "Search item",
    procurarPista: "Search item…",
    localizacao: "Location",
    localizacaoPista: "See one location or the consolidated total",
    todas: "All",
  },

  lista: {
    erroDeStock: "Could not load the stock",
    semCorrespondenciaTitulo: "No item matches",
    semCorrespondenciaCorpo:
      "The search and the filters at the top let nothing through. The stock is still there.",
    limparFiltros: "Clear filters",
    vazioTitulo: "No stock recorded yet",
    vazioCorpo:
      "Stock appears here as goods come in. Start with a goods receipt from a supplier.",
    receberMercadoria: "Receive goods",
  },

  numeros: {
    aCarregar: "Loading the figures…",
    erroDeStockTitulo: "Could not count the items that are missing",
    erroDeStockCorpo:
      "The table below still works. The three figures come back on the second try.",
    erroDeAlertasTitulo: "Could not count the alerts",
    erroDeAlertasCorpo:
      "The list below still works. The three figures come back on the second try.",
    emFalta: "missing",
    abaixoDoMinimo: "below minimum",
    artigosAbaixoDoMinimo: "Items below their minimum stock",
    aExpirar: "expiring",
    dentroDeDias: (dias: string) => `within ${dias} days`,
    artigosComValidade: (dias: string) =>
      `Items with an expiry date within ${dias} days — the threshold comes from the server`,
    valorDeStock: "stock value",
    lotesAExpirar: "lots expiring",
    lotesComValidade: (dias: string) =>
      `Lots with an expiry date within ${dias} days — the threshold comes from the server and appears inside each alert`,
    artigosAbaixoDoMinimoNosAlertas:
      "Items below their minimum stock — the same figure as the Stock screen",
    deitadoForaHoje: "thrown away today",
    quebrasHoje: "waste lines today",
    desdeAs: (hora: string) => `since ${hora}`,
    desdeAsSemPreco: (hora: string, quantas: string) =>
      `since ${hora} · ${quantas} with no known price`,
    diaDeNegocio: (hora: string, inicio: string) =>
      `The business day of this establishment starts at ${hora}, that is at ${inicio} today — anything thrown away before that counts towards the previous day`,
  },

  stock: {
    titulo: "Stock — what I have, and how much",
    tabela: "Stock levels, worst first",
    minimoDoEstabelecimento:
      "You are looking at one location. The quantity and the expiry date are that location's; the establishment minimum and the status are the whole establishment's.",
    artigos: (quantos: number) => (quantos === 1 ? "1 item" : `${String(quantos)} items`),
    rodape: (quantos: number, total: number | null) => {
      const contagem = quantos === 1 ? "1 item" : `${String(quantos)} items`;
      const de = total === null ? "" : ` of ${String(total)}`;
      return `${contagem}${de}, worst first`;
    },
  },

  alertas: {
    titulo: "Alerts — what expires, what is missing, how much I threw away",
    tabela: "Expiry and shortage alerts, worst first",
    aCarregar: "Loading the alerts…",
    erroAoCarregar: "Could not load the alerts",
    stockNegativo: "negative stock",
    semStock: "no stock",
    abaixoDoMinimo: "below minimum",
    minimoAbreviado: "min.",
    semPreco: "no price",
    avisoAInicio: "warning at",
    avisoAFim: "days",
    todasAsLojas: "all",
    deitarFora: "Threw it away",
    deitarForaAccao: (artigo: string, quantidade: string) =>
      `Threw it away — ${artigo}, ${quantidade}`,
    deitarForaAccaoComLote: (artigo: string, lote: string, quantidade: string) =>
      `Threw it away — ${artigo}, lot ${lote}, ${quantidade}`,
    deitarForaInicio: "Throw away",
    doLote: (lote: string) => ` from lot ${lote}`,
    deitarForaPorque: " — why?",
    cancelar: "Cancel",
    deitadoForaHoje: (hora: string) => `Thrown away — today (since ${hora})`,
    deitadoForaSemana: "Thrown away — last 7 days",
    verSemana: "see the last 7 days",
    verHoje: "see today only",
    erroDoDesperdicio: "Could not load the waste",
    vazioDesperdicioTitulo: "Nothing thrown away in this period",
    vazioDesperdicioHoje:
      "The business day has started and no waste has been recorded yet. Anything before that hour counts towards the previous day.",
    vazioDesperdicioSemana: "No waste recorded in the last seven days.",
    verEmRisco: "See what is at risk",
    vazioTitulo: "Nothing at risk right now",
    vazioComFiltroTitulo: "Nothing at risk with this filter",
    vazioCorpo:
      "No lot within the expiry horizon and no item below its minimum. Alerts appear here on their own.",
    vazioComFiltroCorpo: "The other two counters at the top may have lines. Tap to see everything.",
    rodape: (quantos: number) => {
      const contagem = quantos === 1 ? "1 alert" : `${String(quantos)} alerts`;
      return `${contagem}, worst first. “Use by” is a legal limit; “loses quality” is minimum durability.`;
    },
    verTudo: "See everything",
    registado: (quantidade: string, artigo: string, motivo: string) =>
      `Thrown away: ${quantidade} of ${artigo} — ${motivo}.`,
    deitadoForaNaSemana: "Thrown away in the last 7 days:",
    quebrasNaSemana: (quantas: number) =>
      quantas === 1
        ? "1 waste line recorded in the last 7 days"
        : `${String(quantas)} waste lines recorded in the last 7 days`,
    verOQueFoi: "See what it was, and at what time",
  },

  desperdicio: {
    tabela: "Waste movements, most recent first",
    semPreco: "no price",
    aCarregar: "Loading the waste…",
    registar: "Record waste",
    semLocalizacao:
      "This item has no location with movements, so there is nowhere to record waste from.",
    escrevaAQuantidade: (unidade: string) =>
      `Enter the quantity in ${unidade}, greater than zero.`,
    escolhaOMotivo: "Choose the waste reason.",
    localizacaoPrefixo: "Location:",
    localizacao: "Location",
    quantidade: "Quantity",
    unidade: "Unit",
    exemploDeQuantidade: (unidade: string) => `for example, 2 ${unidade}`,
    unidadeAEscolher: (mostrada: string, base: string) =>
      `Enter it in the unit you speak in: ${mostrada} or ${base}. The server does the conversion.`,
    unidadeUnica: (unidade: string) => `This item is counted in ${unidade}.`,
    motivo: "Reason",
    escolhaOMotivoPista: "Choose the reason",
    registado: "Waste recorded.",
    registadoNoLote: (lote: string) => `Waste recorded in lot ${lote}.`,
    registadoNosLotes: (lotes: string) => `Waste recorded in lots ${lotes}.`,
  },

  artigo: {
    voltar: "Stock",
    aCarregar: "Loading the item…",
    minimoERegisto: (minimo: string, unidade: string) =>
      `minimum ${minimo}, recorded in ${unidade}`,
    emTodoOEstabelecimento: "across the whole establishment",
    negativoTitulo: "It went negative",
    negativoCorpo:
      "The recorded stock is below zero. It is usually a receipt that was never entered, or an issue entered twice. Fix it with a new movement — nothing is deleted.",
    erroAoCarregar: "Could not load the item",
    tentarOutraVez: "Try again",
    nuncaEntrouTitulo: (artigo: string) => `${artigo} has not been received into stock yet.`,
    nuncaEntrouCorpo: "The first entry is made from the supplier invoice.",
    naoExisteTitulo: "This item does not exist",
    naoExisteCorpo: "The address does not point to any item in this establishment.",
  },

  movimentos: {
    titulo: "Movements",
    tabela: "Item movements, most recent first",
    aCarregar: "Loading the movements…",
    erroAoCarregar: "Could not load the movements",
    vazioTitulo: "No movements",
    vazioCorpo: "This item has no receipts, consumption or waste recorded yet.",
    rodape: (quantos: number, total: number) =>
      `The ${String(quantos)} most recent movements, of ${String(total)}.`,
  },

  contagem: {
    titulo: "Count — is what is on the shelf what the system says?",
    de: "of",
    contados: "counted",
    linhas: "lines",
    tudoContado: "Everything is counted — it only needs closing.",
    aContar: "counting",
    as: "at",
    zonas: "Count zones",
    todasAsZonas: "All",
    todasAsZonasPista: "See the lines from every zone, in walking order",
    zonaPista: (zona: string) => `See only the lines in ${zona}`,
    aCarregarContagem: "Loading the count…",
    aCarregarLinhas: "Loading the lines…",
    escrevaQuantos: (unidade: string) => `Enter how many ${unidade} are on the shelf.`,
    esperadoPrefixo: "expected",
    confere: "matches",
    aGuardar: "saving…",
    naoFoiGuardado: "Could not save that. Check the connection and enter it again.",
    semContagemTitulo: "No count in progress",
    semContagemCorpo:
      "Pick where to count and start. Each location has its own count: the chest freezer and the pantry can be counted at the same time.",
    erroDasLocalizacoes: "Could not load the locations",
    ondeContar: "Where to count",
    escolhaALoja: "Choose the location",
    aComecar: "Starting…",
    comecar: "Start count",
    ultimaFechada: "Last closed count",
    dataEHora: (data: string, hora: string) => `${data} at ${hora}`,
    justificacao: (motivo: string) => ` · “${motivo}”`,
    verAsDiferencas: "See the differences",
    erroDaContagem: "Could not load the count",
    erroDasLinhas: "Could not load the lines",
    zonaVaziaTitulo: "Nothing to count here",
    zonaVaziaCorpo:
      "This count has no item under this filter. Items with stock in this location are in the full list.",
    verTudo: "See the whole count",
    jaHaviaAbertaTitulo: "That location is already being counted",
    jaHaviaAbertaCorpo: (localizacao: string) =>
      `There is already an open count in ${localizacao}, started by you or by someone else. Carry on with that one — two counts of the same location would correct the same stock twice.`,
    irParaEssaContagem: "Go to that count",
    aDecorrer: "Counts in progress",
    aCarregarAbertas: "Loading the counts in progress…",
    abertaDesde: (dia: string, hora: string) => `open since ${dia} at ${hora}`,
    contarOutra: "Count another location",
    naoEstaAbertaTitulo: "That count is no longer in progress",
    naoEstaAbertaCorpo:
      "Someone may have closed it while this screen was open. The ones in progress are in the list.",
    fechouAMeioTitulo: "This count has already been closed",
    fechouAMeioCorpo:
      "Someone closed it while you were counting. The last number you entered did not go in — go back to Count to see the current state.",
    soOPapelFecha: (papel: string) => `who closes the count: ${papel}`,
  },

  fecho: {
    fechar: "Close count",
    fechada: "Count closed",
    voltar: "Count",
    semContagemTitulo: "No count to close",
    semContagemCorpo:
      "This address does not say which count to close, or it points to one that no longer exists. Pick it from the list of counts in progress.",
    irParaContar: "Go to Count",
    aCarregar: "Loading the differences…",
    erroAoCalcular: "Could not work out the differences",
    fechadaTitulo: "Closed, and the adjustment is in the ledger",
    fechadaCorpo:
      "Each difference produced an adjustment movement with its author and justification. Nothing was rewritten: to correct it, count again.",
    justificacao: (motivo: string) => ` Justification: “${motivo}”.`,
    voltarAContar: "Back to Count",
    totalEmFalta: "short",
    totalAMais: "over",
    totalLiquido: "net difference",
    linhasContadas: "lines counted",
    porContarSemAjuste: ". The ones left uncounted produce no adjustment.",
    ficam: "There are",
    linhasPorContar: "left to count",
    porContarCorpo:
      "The stock of these items does not change: no count means no difference, and no difference means no adjustment. Not having counted is not the same as having counted zero. You can close it like this.",
    fecharComPorContar: (quantas: number) =>
      quantas === 1 ? "Close with 1 left to count" : `Close with ${String(quantas)} left to count`,
    semPapelTitulo: "Closing belongs to the owner or the manager",
    semPapelCorpo:
      "Closing writes one stock adjustment per difference, and those movements cannot be deleted. Counting is everyone's; closing is not.",
    semDiferencas: "No differences so far. What is on the shelf is what the system says.",
    diferencasTitulo: "Differences, largest first",
    contadoPrefixo: "counted",
    esperadoPrefixo: "expected",
    motivoObrigatorio: "Write down what happened — the count does not close without it.",
    oQueAconteceu: "What happened",
    exemploDeMotivo: "for example, the morning transfer was never entered…",
    ajudaObrigatoria: "It stays in the history, next to every adjustment this closing writes.",
    aFechar: "Closing…",
    soOPapelFecha: (papel: string) => `who closes the count: ${papel}`,
  },
};
