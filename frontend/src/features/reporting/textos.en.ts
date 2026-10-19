import type { PT } from "./textos.pt";

/**
 * A copy do módulo `reporting`, em **inglês**, anotada com o tipo do português.
 *
 * Servida desde 2026-10-07 a um browser que peça inglês, e verificada pelo
 * compilador desde sempre: o `typeof PT` é o contrato inteiro, e uma função com
 * outra assinatura não compila.
 *
 * ## O vocabulário financeiro, e as escolhas que foram decisões
 *
 * **`food cost` e não "goods ratio"** para o contador `mercadoria`: é a palavra
 * que a restauração usa e compara, e é precisamente por isso que ela existe no
 * painel. A linha da tabela continua "Goods consumed", porque aí é uma rubrica
 * em euros e não um rácio.
 *
 * **`unknown shrinkage`** para a quebra desconhecida e **`stocktake surplus`**
 * para o excedente: é a mesma distinção de sinal que o português faz, e sem ela
 * o excedente lia-se como "desperdício negativo".
 *
 * **`owner's pay`** para a remuneração do dono, e a palavra "profit" não entra
 * em frase nenhuma deste ficheiro: a razão é a mesma do pt-PT (ADR 0013,
 * decisão 6) e não sobrevive a uma tradução distraída — "what the owner draws is
 * a distribution of profit" põe o substantivo ao lado de um número.
 *
 * ## Três termos fiscais portugueses que ficam em português
 *
 * **TSU**, **duodécimos** e **TPA** não têm equivalente inglês. Cada um fica
 * como está e é explicado **uma vez** entre parênteses, no sítio onde aparece
 * primeiro: `Social Security (TSU)`, `Allowances, in twelfths (duodécimos)` e
 * `TPA (card terminal)` na nota dos custos fixos. O **IRC** segue a mesma regra
 * (`IRC (corporate income tax)`), porque é o nome do imposto e não a sua
 * descrição.
 */
export const EN: typeof PT = {
  inicio: {
    titulo: "Home — today's work",
    oQueEstaAEspera: "What is waiting",

    alertasExpira: "Alerts — what expires",
    aCarregarExpira: "Loading what is expiring…",
    vazioExpira: "nothing expiring",

    alertasFalta: "Alerts — what is missing",
    aCarregarFalta: "Loading what is running out…",
    vazioFalta: "nothing below the minimum",
    minimo: (quantidade: string) => `min. ${quantidade}`,

    receber: "Receiving",
    aCarregarRececoes: "Loading what is waiting to be booked in…",
    vazioRececoes: "nothing waiting to be booked in",
    semValor: "no amount",

    contar: "Stocktake",
    aCarregarContagem: "Loading the stocktake in progress…",
    vazioSemContagem: "no stocktake in progress — start one",
    vazioSemZonas: "stocktake open, with no zones to count",

    stock: "Stock",
    aCarregarStock: "Loading the worst stock lines…",
    vazioStock: "no stock recorded",

    painel: "Dashboard",
    aCarregarGrafico: "Loading the purchases chart…",
    vazioSemAcesso: "no access to the dashboard",
    vazioUmIntervalo: "a single interval — nothing to compare",
    rotuloDoGrafico: (maximo: string) =>
      `Purchases over the last seven days, with the axis maximum at ${maximo}`,
  },

  painel: {
    tituloComPergunta: (pergunta: string) => `Management dashboard — ${pergunta}`,
    naoSabe: "What this dashboard does not know",
    aCarregarDeclaracoes: "Loading what the dashboard declares…",
    dinheiroEMercadoria: "Money and goods",
    aoLongoDoPeriodo: "Over the period",
    notaDoGrafico: (grao: string, maximo: string) => `${grao} · up to ${maximo}`,
    erroDoGrafico: "Could not load the chart",
    nadaRegistado: (periodo: string) => `Nothing recorded ${periodo}`,
    vazioTitulo: "No purchases and no consumption in this window",
    vazioCorpo:
      "There are no rows of zeros here because zeros answer nothing. Start by booking in the goods that arrived: purchases appear on the dashboard on the day the receipt is confirmed.",
    receberMercadoria: "Receive goods",
    perdas: "Waste and unknown shrinkage",
    fechoDe: (mes: string) => `${mes} close`,
    erroDoFecho: "Could not load the month close",
    mesSemNada: (mes: string) =>
      `Nothing is recorded in ${mes}. Use the month navigation, in the bar above, to reach a month with activity.`,
    resultadoDe: (mes: string) => `${mes} result`,
    custoPorCargo: "Cost by role",
  },

  falta: {
    campo: "not yet included",
    lista: (nomes: readonly string[]) => {
      const ultima = nomes.at(-1) ?? "";
      return nomes.length <= 1 ? ultima : `${nomes.slice(0, -1).join(", ")} and ${ultima}`;
    },
    vendasCampo: "Sales",
    vendasCurto: "no sales are recorded in this application yet",
    vendasFrase:
      "No sales are recorded in this application yet. Without them there is no revenue, no margin and no food cost ratio — and a zero in their place would be a false statement about the business.",
    pessoalCampo: "Payroll cost",
    pessoalCurto: "wages arrive once there is a people area",
    pessoalFrase:
      "Wages arrive once there is a people area. Until then there is no payroll cost, no total cost and no result for the month.",
    fixosCampo: "Fixed costs",
    fixosCurto: "rent, energy and the other fixed costs are not recorded here yet",
    fixosFrase:
      "Rent, energy, water, gas, the card terminal, licences and the accountant are not recorded in this application yet, so they count towards no cost on this screen.",
    semRazao: "not known yet — the server does not say why",
    frase: (campo: string, razao: string) => `${campo}: ${razao}.`,
  },

  rodape: {
    rotulo: "How to read these figures",
    valorDeStock: (dia: string, hora: string) => `Stock value as of ${dia} at ${hora}.`,
    ultimaContagem: (dia: string) => `Last stocktake: ${dia}.`,
    nuncaSeContou: "Never counted.",
    baseDasCompras:
      "Purchases is what came into stock, at the cost recorded on each movement — not what the invoices added up to.",
    semIva:
      "Figures exclude VAT; under this regime the VAT paid on purchases is not included in the cost.",
  },

  abas: {
    regua: "Dashboard sections",
    dinheiro: "Money",
    dinheiroPergunta: "How much came in and how much went out in this period?",
    perdas: "Losses",
    perdasPergunta: "What was lost, and is it even known how much?",
    pessoal: "Payroll",
    pessoalPergunta: "How much does the team cost, and how did the month close?",
  },

  periodos: {
    hojeCurto: "Today",
    hoje: "today",
    seteDiasCurto: "7 days",
    seteDias: "over the last 7 days",
    trintaDiasCurto: "30 days",
    trintaDias: "over the last 30 days",
    esteMesCurto: "This month",
    esteMes: "this month",
    mesAnteriorCurto: "Last month",
    mesAnterior: "last month",
  },

  barra: {
    periodo: "Dashboard period",
    janela: "Window: ",
    mesDeNegocio: "Business month: ",
    diaDeNegocioDesde: (hora: string) => ` · business day from ${hora}`,
  },

  fecho: {
    navegacao: "Close month",
    mesAnterior: "Previous month",
    mesSeguinte: "Next month",
    semMesSeguinte: "The current month is the last one with data: the next has not happened yet.",
    mesFechado: " · month closed",
    aCorrer: (decorridos: number, total: number) =>
      ` · in progress: ${String(decorridos)} of ${String(total)} days`,
    avisoTitulo: (decorridos: number, total: number) =>
      `Month in progress: ${String(decorridos)} of ${String(total)} days`,
    avisoCorpo:
      "Payroll and fixed costs are for the whole month — a salary is a monthly fact and does not divide by days. Sales and goods are those of the days that have passed, so the result and the ratios on this tab only become comparable once the month closes.",
    semPermissaoTitulo: "The management dashboard belongs to the establishment owner",
    semPermissaoCorpo:
      "It includes salaries and cost by role, and a cost by role with one person in it is that person's salary under another name. The day's work — what expires, what is missing, what arrived and is waiting to be booked in — is on Home, and it is the same for everyone.",
    irParaOInicio: "Go to Home",
    decideOServidor: "This is decided by the server, not by this screen.",
    aCarregar: "Loading the month close…",
  },

  rubricas: {
    vendasSemIva: "Sales, excluding VAT",
    comIva: (valor: string) => `the base for the ratios; including VAT it is ${valor}`,
    variacaoDeStock: "Stock change",
    totalDeGastos: "Total costs",
    resultado: "Result",
    explicar: "explain",
    menos: "less",
    dosQuais: "of which ",
    coluna: "Item",
    colunaDoValor: "Amount",
  },

  custos: {
    comprasRotulo: "Supplier purchases",
    comprasNota: "money that went out to suppliers",
    consumoRotulo: "Goods consumed",
    consumoNota: "what left the stock, at the cost recorded on the movement",
    desperdicioRotulo: "Waste",
    desperdicioNota: "already inside the goods consumed",
    quebraRotulo: "Unknown shrinkage",
    quebraNota: "the net of the stocktakes",
    pessoalRotulo: "Payroll",
    pessoalNota: "employer cost for the month, never apportioned by day",
    fixosRotulo: "Fixed costs",
    fixosNota: "rent, energy, water, gas, TPA (card terminal), licences, accountant",
  },

  contadores: {
    vendas: "sales",
    mercadoria: "food cost",
    doQueSeVendeu: "of what was sold, excluding VAT",
    valorDeStock: "stock value",
    aoCustoGravado: "at the cost recorded on the movement",
    pessoal: "payroll",
    semRemuneracaoDoDono: "excluding the owner's pay",
    mercadoriaMaisPessoal: "food cost + payroll",
    sobreVendasSemIva: "on sales excluding VAT",
    aCarregar: "Loading the period figures…",
    erroDoPeriodo: "Could not load the period",
  },

  dinheiro: {
    tabela: "The money and the goods for the period, with the stock change",
    semConsumo:
      "no consumption recorded in this period — see what is missing, under «What this dashboard does not know»",
    aContaFecha: (periodo: string) =>
      `The sum checks out: stock change = purchases − goods consumed − unknown shrinkage ${periodo}.`,
    aCarregar: "Loading the money for the period…",
    variacaoIgual: "as much came in as went out",
    variacaoGastou: "the larder was run down: more stock left than came in",
    variacaoEncheu: "the larder was filled: more stock came in than left",
  },

  perdas: {
    excedenteDeContagem: "Stocktake surplus",
    excedenteNota: "more was found than the system said — the net of the stocktakes in the house's favour",
    tabela: "The two losses for the period: waste and unknown shrinkage",
    vazio:
      "Nothing thrown away in this period. Waste appears here by reason, from the largest to the smallest, as it is recorded.",
    notaDasBarras: (total: string) => `Waste by reason, ${total} in total — the order is the size.`,
    campoMotivo: "Reason",
    rotuloDasBarras: "Waste by reason, from the largest to the smallest",
    rotuloDaBarra: (motivo: string, movimentos: number) =>
      `${motivo} · ${String(movimentos)} ${movimentos === 1 ? "movement" : "movements"}`,
    aCarregar: "Loading the losses for the period…",
  },

  motivos: {
    expirado: "expired",
    estragado: "spoiled",
    quebra: "breakage",
    perdaDePreparacao: "prep loss",
    outro: "other",
  },

  pessoal: {
    avisoDoRacio:
      "This ratio is not comparable with the ones in the trade: the owner's pay does not count towards payroll costs. When the owner works in the business without paying themselves, the real payroll cost is 4 to 5 points higher than this figure.",
    cargosVazio:
      "Cost by role appears once there is a people area: it is what holds who works, in which job, and on what pay.",
    semRacios:
      "The month ratios compare costs with sales, and the payroll ones also need wages. While both sources are missing, none of the three exists.",
    cargoNaoEPapel: "A role is the job someone does, not the access they have to the application.",
    campoCargo: "Role",
    custo: "Cost",
    rotuloDosCargos: "Payroll cost by role, from the largest to the smallest",
    rotuloDoCargo: (cargo: string, pessoas: number) =>
      `${cargo} · ${String(pessoas)} ${pessoas === 1 ? "person" : "people"}`,
  },

  salarios: {
    base: "Base gross pay",
    tsu: "Social Security (TSU)",
    subsidios: "Allowances, in twelfths (duodécimos)",
    alimentacao: "Meal allowance",
    seguro: "Workplace accident insurance",
    custoEmpresa: "employer cost",
    custoEmpresaNota: "employer cost: the gross pay plus what the employer pays on top",
    bruto: "gross",
    brutoNota: "gross: what the employee receives before deductions",
    origemContrato: "from the contract",
    origemContratoNota: "from the contract, without overtime",
    origemProcessamento: "from the payroll run",
    origemProcessamentoNota: "from the month's payroll run",
  },

  outrosCustos: {
    renda: "Rent",
    energia: "Energy",
    agua: "Water",
    gas: "Gas",
    cartoes: "Card terminal and cards",
    licencas: "Licences",
    contabilista: "Accountant",
    outros: "Other",
  },

  exclusoes: {
    amortizacoes: "depreciation",
    financiamento: "financing",
    irc: "IRC (corporate income tax)",
    remuneracaoDoDono: "owner's pay",
    naoInclui: (palavras: readonly string[]) => {
      const ultima = palavras.at(-1) ?? "";
      const frase =
        palavras.length === 1 ? ultima : `${palavras.slice(0, -1).join(", ")} and ${ultima}`;
      return `Does not include ${frase}.`;
    },
  },

  resultado: {
    tabela: "Sales, costs and result for the month",
    naoEntraNoTotal: (nota: string) => `does not count towards the total — ${nota}`,
    totalDeGastosNota: "goods, losses, payroll and fixed costs — added up by the server",
    notaFechado: "sales excluding VAT minus the total costs",
    notaACorrer: "month in progress: payroll and fixed costs are for the whole month",
    dependeDoPessoal:
      "only exists once there is a payroll cost and fixed costs — adding up goods alone and calling it a total would treat the sum as settled",
    semResultado: "without a total cost there is no result, and what the total is missing is two whole items",
    negativo: "Negative result this month. ",
    comExclusoes: (exclusoes: string) =>
      `${exclusoes} It is what is left of what is in this table, and nothing else.`,
    notaDasBarras: "Breakdown of the costs already recorded, from the largest to the smallest.",
    campoGasto: "Cost item",
    rotuloDasBarras: "Month costs by category, from the largest to the smallest",
  },

  qualidade: {
    campoConsumo: "consumption recorded",
    sim: "yes",
    nao: "no",
    consumoSim: "Goods consumed come from the ledger, at the cost recorded on each movement.",
    consumoNao:
      "Without consumption in the ledger there are no goods consumed and no food cost ratio — and without them this dashboard would show a margin that does not exist.",
    portaRegistar: "Record what went out",

    campoSemFatura: "goods without an invoice",
    semFaturaHa:
      "It came in on a delivery note and is valued at the last known price; the difference appears when the invoice arrives.",
    semFaturaNenhuma: "All the goods in this period have an invoice: the purchases are at the right price.",
    portaRececoes: "See the receipts",

    campoUltimaContagem: "last stocktake",
    nunca: "never",
    semContagem:
      "With no stocktake at all, unknown shrinkage is zero for lack of measurement and not for lack of shrinkage.",
    contouSe: (quando: string) =>
      `Counted ${quando}. Unknown shrinkage only measures what was counted up to then.`,
    portaContar: "Count now",

    campoOrigemDasVendas: "sales source",
    nenhuma: "none",
    pos: "POS",
    aMao: "by hand",
    origemDasVendas: (origem: string) =>
      `${origem}. The ratios are on sales excluding VAT; the amount including VAT is the one from the till close.`,
    sabeTudo: "The dashboard knows everything it needs. Last stocktake on ",
  },

  grafico: {
    serieVendas: "Sales",
    serieCompras: "Purchases",
    diaADia: "day by day",
    semanaASemana: "week by week",
    valor: "Amount",
    umSoIntervalo:
      "A single interval in this period: there is no variation to draw. The totals are above, and the other periods in the top bar give seven days or more.",
    rotuloDaSerie: (serie: string, total: string) => `${serie} — ${total} in total`,
    rotulo: (series: readonly string[], grao: string, maximo: string) => {
      const ultima = series.at(-1) ?? "";
      const lista =
        series.length <= 1 ? ultima : `${series.slice(0, -1).join(", ")} and ${ultima}`;
      return `${lista}, ${grao}, with the axis maximum at ${maximo}`;
    },
    aCarregar: "Loading the period chart…",
  },

  receita: {
    brutoNota: "recorded including VAT, as at the till close",
    liquidoNota: "recorded excluding VAT",
    origemNenhuma: "sales are not recorded yet",
    origemManual: "sales recorded by hand",
    origemPos: "sales coming from the POS",
  },

  contagem: {
    nuncaSeContou:
      "no stocktake has ever been done: the zero shrinkage is a missing stocktake, not missing shrinkage",
    semContagemNoPeriodo: (data: string) =>
      `no stocktake in this period — the last one was on ${data}, and the whole gap shows up in the next one`,
    ultima: (data: string) => `last stocktake on ${data}`,
  },
};
