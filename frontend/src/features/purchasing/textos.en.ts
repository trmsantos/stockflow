import type { PT } from "./textos.pt";

/**
 * A copy do módulo `purchasing`, em **inglês**, anotada com o tipo do português.
 *
 * Servida desde 2026-10-07 a um browser que peça inglês, e verificada pelo
 * compilador desde sempre: o `typeof PT` é o contrato, e o `escolher` é um
 * `Record` sobre a união das línguas — faltar uma entrada aqui não compila.
 *
 * ## O vocabulário de compras numa cozinha portuguesa
 *
 * **"Goods receipt"** para `receção`: é a entrada de mercadoria, e distingue-se
 * de `recibo` (receipt), que é um documento de pagamento. O verbo da rota fica
 * **"Receive"**, como no menu.
 *
 * **Os documentos** são os do mercado português: `invoice` (FT),
 * `invoice-receipt` (FR), `simplified invoice` (FS), `credit note` (NC) e
 * `delivery note` (a guia de remessa, GR).
 *
 * **"NIF" fica NIF.** É o número de identificação fiscal português, está
 * impresso assim na fatura, e traduzi-lo por "tax number" tirava-lhe a única
 * propriedade útil: ser o que a pessoa procura no papel que tem na mão. Pela
 * mesma razão fica **"cash & carry"**, que é como se diz nas duas línguas.
 *
 * **"Item"** para `artigo`: é o artigo do catálogo de stock, e separa-se de
 * `line` (a linha do documento), que nesta feature é outra coisa.
 */
export const EN: typeof PT = {
  comuns: {
    receber: "Receive",
    fotografarFatura: "Photograph the invoice",
    verAsRececoes: "View goods receipts",
    aGuardar: "Saving…",
    semNumero: "no number",
    outroAdquirente: "another customer",
    as: "at",
    dataEHora: (data: string, hora: string) => `${data} at ${hora}`,
    nifDoDocumento: (
      adquirente: string,
      nifDoAdquirente: string,
      empresa: string,
      nifDaEmpresa: string,
    ) =>
      `Document issued to ${adquirente}, NIF ${nifDoAdquirente}. The company is ${empresa}, NIF ${nifDaEmpresa}.`,
    entrouPorGuia:
      "It arrived on a delivery note, without prices. The supplier invoice comes at the end of the month and reconciles the deliveries for the period.",
    linhasPorRever: (quantas: number) =>
      quantas === 1 ? "1 line to review" : `${String(quantas)} lines to review`,
  },

  receber: {
    titulo: "Receive — what arrived, and is it right?",
    erroAoCarregar: "Could not load the goods receipts",
    contagem: (quantas: number) =>
      quantas === 1 ? "1 goods receipt" : `${String(quantas)} goods receipts`,
    vazioTitulo: "No goods have arrived yet",
    vazioCorpo:
      "Every entry starts from a supplier document — an invoice, a simplified invoice from the cash & carry, or a delivery note. Nothing enters stock until someone confirms the lines.",
    filtroVazioTitulo: "No goods receipt in this filter",
    filtroVazioRevisao:
      "There are no documents waiting for review. Everything that arrived has already entered stock.",
    filtroVazioHoje: "No goods receipt was confirmed in today's business day.",
    verTudo: "Show all",
    rodapeDaLista: (quantos: number, total: number | null) => {
      const contagem = quantos === 1 ? "1 document" : `${String(quantos)} documents`;
      const de = total === null ? "" : ` of ${String(total)}`;
      return `${contagem}${de}, the ones needing review first. None enters stock until it is confirmed.`;
    },
  },

  fotografar: {
    semCamaraTitulo: "There is no camera on this screen yet",
    semCamaraCorpo:
      "On a phone this button opens the camera and the photograph is attached to the document. Here there is no camera and no document reading: the goods receipt waiting for review was filled in by hand, so that the review can be walked end to end — which is the part that decides whether stock changes.",
    porOndeEntra: "How goods come in",
    faturaEnfase: "Invoice or simplified invoice",
    faturaFim:
      ", from a trip to the cash & carry: no order, no delivery note, the goods come in the van and the document comes in your hand.",
    guiaEnfase: "Delivery note",
    guiaFim:
      ", from the distributor: the goods come in first and the invoice arrives at the end of the month, reconciling several deliveries.",
    semDocumentoEnfase: "No document at all",
    semDocumentoFim:
      ", or one written by hand at the market: it still has to be entered, and the document shows up later.",
    aProcurar: "Looking for goods receipts to review…",
    semRevisaoTitulo: "There is nothing waiting for review",
    semRevisaoCorpo:
      "When a new document arrives, it shows up in the list needing review — and stock only changes once someone confirms the lines.",
    rever: (fornecedor: string) => `Review ${fornecedor}`,
  },

  rececao: {
    aCarregar: "Loading the goods receipt…",
    erroAoCarregar: "Could not load this goods receipt",
    naoExisteTitulo: "This goods receipt does not exist",
    naoExisteCorpo:
      "The address points to a document that is no longer in this establishment.",
    noStockTitulo: "The goods are in stock",
    noStockCorpo:
      "Every confirmed line generated an incoming movement with the lot, the expiry date and the author. Nothing is rewritten: to correct it, record a new movement.",
    verNoStock: "View in stock",
    linhasDoDocumento: "Document lines",
    erroDasLinhas: "Could not load the lines",
    semLinhasTitulo: "This document has no lines",
    semLinhasCorpo:
      "With no lines there is nothing to review and nothing to enter. It is usually a document photographed upside down.",
    linhaRevista: (nome: string) => `Line reviewed: ${nome}.`,
    linhaDeFora: (nome: string) => `${nome} is left out of this entry — it generates no movement.`,
    linhaVoltaARever: (nome: string) => `${nome} needs review again.`,
    nadaEntraAinda: "Nothing enters stock yet",
    oQueEntra: "What enters stock when you confirm",
    nenhumaRevista:
      "No line has been reviewed. Confirm the lines above — the lot and the expiry date are on the packaging, not on the document.",
    entraNoStock: (artigo: string | null, local: string) => `of ${artigo ?? ""} in ${local}`,
    linhasDeFora: (quantas: number) =>
      quantas === 1 ? "1 line is left out" : `${String(quantas)} lines are left out`,
    linhasDeForaCorpo:
      "Without review there is no movement, so those goods do not show up in stock. You can confirm like this and deal with them later — or review the lines first.",
    aDarEntrada: "Entering…",
    confirmarEDarEntrada: "Confirm and enter into stock",
    esteToqueCria:
      "It is this tap that creates the incoming movements. Until now, the stock of this establishment is the same as it was before the goods arrived.",
    confirmada: "Goods receipt confirmed: the goods entered stock.",
  },

  numeros: {
    porReverTitulo:
      "Documents that have not entered stock yet — nothing enters without review",
    confirmadasHoje: "confirmed today",
    desdeAs: (hora: string) => `since ${hora}`,
    diaDeNegocio: (hora: string) =>
      `The business day of this establishment starts at ${hora} — anything confirmed before that hour counts towards the previous day`,
    aCarregar: "Loading the numbers…",
    erroTitulo: "Could not count the goods receipts",
    erroCorpo: "The list below still works. The two numbers come back on the second attempt.",
  },

  tabela: {
    colunas: {
      fornecedor: "Supplier",
      tipo: "Type",
      documento: "Document",
      chegou: "Arrived",
      total: "Total",
      linhas: "Lines",
      estado: "State",
      onde: "Where",
    },
    rotulo: "Goods receipts, the ones needing review first",
    aCarregar: "Loading the goods receipts…",
    emitidaA: (adquirente: string) => `issued to ${adquirente}`,
    semValor: "no value",
    porRever: (quantas: number) => `${String(quantas)} to review`,
    semFatura: "no invoice",
  },

  badges: {
    precisaDeRevisao: "needs review",
    quantasLinhas: (quantas: number) => (quantas === 1 ? "1 line" : `${String(quantas)} lines`),
    entrouSemFatura: "arrived without an invoice",
    nifDiferente: "NIF differs from the company's",
  },

  cabecalho: {
    emitidaA: (adquirente: string) => `Issued to ${adquirente} · NIF`,
    aEmpresaE: (empresa: string) => `The company is ${empresa} · NIF`,
    totaisNaoBatemTitulo: "The totals do not match",
    totaisNaoBatemInicio: "The printed total is",
    totaisNaoBatemMeio: "and the lines add up to",
    totaisNaoBatemFim:
      ". It is usually a footer discount or carriage left out of the lines. You can confirm like this.",
    recebida: "received",
    confirmada: "confirmed",
    por: (autor: string) => `by ${autor}`,
    em: "In",
    notaDeCredito: "A credit note credits value; it does not bring goods in.",
    guiaSemPrecos:
      "This delivery note carries no prices — there are no totals to check. The value arrives with the invoice.",
    baseAIva: "base at VAT",
    total: "total",
    taxasDaLinha: "the rates are those of each invoice line — they are not taken from the item",
  },

  linhas: {
    colunas: {
      artigo: "Item",
      recebido: "Received",
      stock: "Stock",
      valor: "Value",
      lote: "Lot",
      validade: "Expiry",
      estado: "State",
      accao: "Action",
    },
    tabela: "Document lines, in the order they are printed on it",
    aCarregar: "Loading the invoice lines…",
    validadeCom: (tipo: string) => `Expiry (${tipo})`,
    lotePlaceholder: "as printed on the packaging",
    confirmarLinha: "Confirm line",
    semArtigo: "no item in the catalogue",
    semArtigoCorpo:
      "The invoice brings this and the catalogue does not have it. With no item there is no conversion to the stock unit, so the line does not enter — leave it out of this entry, or create the item in the catalogue first.",
    deixarFora: "Leave out of this entry",
    voltarARever: "Send back for review",
    ficaDeFora: "Left out of this entry — it generates no movement.",
    faturadoCurto: "inv.",
    pesoVariavelNota: "variable weight",
    semConversao: "no conversion",
    naoEStock: "not stock",
    jaNoStock: "already in stock",
    semPreco: "no price",
    ivaDaLinha: (taxa: string) => `VAT ${taxa} — the rate that comes on the invoice line`,
    rever: "Review",
    ver: "View",
    reverALinha: (descricao: string) => `Review the line ${descricao}`,
    verALinha: (descricao: string) => `View the line ${descricao}`,
    conversaoMeio: "become",
    conversaoFim: "in stock, which is the unit the ledger keeps.",
    guiaSemPrecos: "This delivery note carries no prices.",
    aFaturaCobra: "The invoice charges",
    aoPreco: "at",
    comIvaDe: ", with VAT of",
    taxaDaLinha: " — the rate that comes on the line, not the item's",
    totalDaLinha: ". Line total:",
    faturadosInicio: "Invoiced",
    faturadosMeio: ", received",
    faturadosFim: " — the invoice charges what it invoiced.",
    faturados: (faturados: string, entraram: string) =>
      `Invoiced ${faturados}, received ${entraram} — the invoice charges what it invoiced.`,
    acima: "above",
    abaixo: "below",
    dasUltimasCompras: "the last purchases",
    historicoEm: "in",
    oAvisoApareceAcimaDe: "The warning appears above",
    vasilhame: "Deposit: a line with value that is not consumable stock. ",
    encargo: "Charge: value without goods. ",
    conservaSe: (como: string) => `Kept ${como}. `,
    pesoVariavel: "Variable weight: weighed piece by piece on the invoice. ",
    aValidadeDestaLinha: (tipo: string) => `The expiry date of this line is «${tipo}». `,
    entraEm: (local: string) => `Enters ${local}.`,
    revistaPor: (autor: string) => `Reviewed by ${autor}`,
    semMovimentoAinda: ". The movement only exists once the document is confirmed.",
    jaEstaNoStock: ". It is already in stock.",
  },

  temperatura: {
    rotulo: "Temperature on delivery (°C)",
    guardar: "Save",
    registada: "recorded",
  },

  vocabulario: {
    documentoFatura: "Invoice",
    documentoFaturaRecibo: "Invoice-receipt",
    documentoFaturaSimplificada: "Simplified invoice",
    documentoNotaDeCredito: "Credit note",
    documentoGuiaDeRemessa: "Delivery note",
    /**
     * A sigla fica em português: é a palavra que está impressa no documento que
     * a pessoa tem na mão, e é por ela que o procura. Traduzi-la dava um rótulo
     * que não existe em papel nenhum.
     */
    siglaDeGuia: "guia",
    porRever: "to review",
    noStock: "in stock",
    linhaRevista: "reviewed",
    linhaDeFora: "left out",
    congelado: "frozen",
    refrigerado: "chilled",
    ambiente: "ambient",
    mercadoria: "goods",
    vasilhame: "deposit",
    encargo: "charge",
    consumirAte: "use by",
    /**
     * **As duas formas dão a mesma frase em inglês, e está certo.** O português
     * tem a legal por extenso ("consumir de preferência antes de") e uma curta
     * que cabe numa célula ("melhor antes"); a inglesa é "best before" nos dois
     * papéis, e é o que está impresso na embalagem. Igualá-las não é um descuido
     * — inventar uma distinção que o inglês não faz é que seria.
     */
    consumirDePreferenciaAntesDe: "best before",
    melhorAntes: "best before",
  },

  /**
   * **Não se traduz, e é a entrada inglesa certa.** A chave da procura é o
   * rótulo da embalagem, que é texto que o fornecedor escreveu na fatura em
   * português: num ecrã inglês continua a dizer "caixa 12×1 L", logo é "caixa"
   * que tem de ser procurado e "caixas" que tem de ser escrito. Traduzir isto
   * dava um mapa que nunca acerta em chave nenhuma.
   */
  plurais: {
    caixa: { singular: "caixa", plural: "caixas" },
    bloco: { singular: "bloco", plural: "blocos" },
    saco: { singular: "saco", plural: "sacos" },
    pacote: { singular: "pacote", plural: "pacotes" },
    rolo: { singular: "rolo", plural: "rolos" },
    grade: { singular: "grade", plural: "grades" },
    garrafao: { singular: "garrafão", plural: "garrafões" },
    plateau: { singular: "plateau", plural: "plateaus" },
    peca: { singular: "peça", plural: "peças" },
    lata: { singular: "lata", plural: "latas" },
    embalagem: { singular: "embalagem", plural: "embalagens" },
    bola: { singular: "bola", plural: "bolas" },
  },

  formularios: {
    escrevaOLote: "Write the lot that is on the packaging, exactly as printed.",
    escrevaAValidade: "Write the expiry date on the packaging.",
    escrevaOsGraus: "Write the degrees, for example -18 or 4.5.",
  },
};
