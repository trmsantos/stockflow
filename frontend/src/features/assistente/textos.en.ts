import type { PT } from "./textos.pt";

/**
 * A copy do `assistente`, em **inglês**, anotada com o tipo do português: uma
 * chave a faltar dá `TS2741`, uma a mais dá `TS2353` (ADR 0019, decisão 3).
 */
export const EN: typeof PT = {
  ecra: {
    titulo: "Assistant",
    novaConversa: "New conversation",
    abrirConversas: "Open conversations",
    fecharConversas: "Close conversations",
    conversasDescricao: "Your conversations with the assistant in this establishment.",
  },

  lista: {
    titulo: "Conversations",
    aCarregar: "Loading conversations…",
    erroAoCarregar: "Could not load the conversations",
    vazioTitulo: "No conversations yet",
    vazioCorpo: "The first question opens a conversation. Each one is kept for 90 days.",
    ultimaMensagem: (data: string) => `Last message: ${data}`,
    apagar: "Delete",
    apagarPista: "Deletes the conversation. Asks for confirmation, and is final.",
    apagarEFinal: "Deleting is final.",
    aApagar: "Deleting…",
    cancelar: "Cancel",
    aConversa: (titulo: string) => ` the conversation “${titulo}”`,
    erroAoApagar: "Could not delete the conversation",
  },

  painel: {
    titulo: "Assistant",
    descricao: "Ask about this establishment's stock without leaving the screen you are on.",
    abrirEmPagina: "Open as a full page",
    fechar: "Close the assistant",
  },

  inicio: {
    titulo: "Ask about your stock",
    corpo:
      "The assistant answers with this establishment's numbers and says where it got them. Start with one of these questions, or write your own.",
    exemplo1: "How much flour do I have?",
    exemplo2: "What expires this week?",
    exemplo3: "Which items are below minimum?",
  },

  fio: {
    aCarregar: "Loading the conversation…",
    erroAoCarregar: "Could not load this conversation",
    naoExisteTitulo: "This conversation is no longer here",
    naoExisteCorpo:
      "The address points to a conversation that does not exist in this establishment, or that was deleted.",
    assistente: "Assistant",
    perguntaDe: (nome: string) => `Question from ${nome}`,
    respostaDoAssistente: "Assistant's answer",
    aConsultar: "Checking the stock…",
    aConsultarTool: (tool: string) => `Checking: ${tool}…`,
    desistiuTitulo: "I stopped asking",
    desistiuCorpo:
      "A minute and a half has passed and the answer has not arrived. Nothing was lost — it shows up in this conversation when ready. You can ask again if it is still being prepared.",
    erroTitulo: "I could not answer",
    semResposta: "The answer came back empty.",
    fontes: "Sources",
    linhas: (n: number) => (n === 1 ? "1 row" : `${String(n)} rows`),
    truncado: "truncated",
    falhou: "failed",
    semFontes: "No stock lookups.",
  },

  acoes: {
    grupo: "Suggested actions",
    verArtigo: "View the item",
    verFalta: "See what is missing",
    verValidade: "See expiry dates",
    verDesperdicio: "See the waste",
    verAlertas: "See the alerts",
    reverRececoes: "Review deliveries",
    verRececoesDeHoje: "See today's deliveries",
    verRececoes: "See the deliveries",
    verRececao: "Open the delivery",
    verContagens: "Open a count",
    verPainel: "See the dashboard",
    verStock: "See the stock",
    verEquipa: "See the team",
    verEstabelecimento: "See the establishment",
    verInicio: "Go to the home screen",
  },

  temas: {
    receber: "Receiving goods",
    reverLinhas: "Reviewing invoice lines",
    perdasAjustesTransferencias: "Waste and adjustments",
    contar: "Stock counts",
    alertasEMinimos: "Alerts and minimums",
    painel: "Monthly dashboard",
    artigosSkuEmbalagens: "Items and packaging",
    fornecedores: "Suppliers",
    receitasEProducao: "Recipes and production",
    equipaEConvites: "Team and invites",
    definicoes: "Settings",
    assistente: "The assistant",
  },

  errosDaMensagem: {
    tetoDeIteracoes:
      "The question needed more lookups than allowed. Try splitting it into smaller questions.",
    tetoDeCusto: "The assistant's daily budget ran out mid-answer. Come back tomorrow.",
    tempoEsgotado: "The answer took too long and was abandoned. Try again.",
    respostaInvalida: "The assistant returned an answer that cannot be read. Try again.",
    erroDoModelo: "The assistant service failed. Try again in a moment.",
    pertencaRevogada: "You no longer belong to this establishment, so the answer was not computed.",
  },

  recusas: {
    indisponivelTitulo: "The assistant is not set up in this establishment",
    indisponivelCorpo:
      "Whoever manages the account can enable it. Until then, the answers are on the Stock and Alerts screens.",
    tetoTitulo: "Daily limit reached",
    tetoCorpo: "The assistant has already answered today's maximum of questions. It is available again tomorrow.",
    pendenteTitulo: "Still answering",
    pendenteCorpo: "Wait for the previous answer before asking again.",
    cheiaTitulo: "This conversation is full",
    cheiaCorpo: "A conversation holds at most 30 questions. Open a new one to continue.",
    perguntaInvalidaTitulo: "The question was not accepted",
    perguntaInvalidaCorpo: "Write a question of up to 2000 characters.",
    muitasSeguidasTitulo: "Too many questions in a row",
    muitasSeguidasCorpo: "Wait a minute and try again.",
    redeTitulo: "Could not send the question",
    redeCorpo: "Check your connection and try again.",
  },

  compositor: {
    rotulo: "Question",
    contadorAcessivel: (n: number, maximo: number) =>
      `${String(n)} of ${String(maximo)} characters`,
    perguntar: "Ask",
    aPerguntar: "Asking…",
    atalho: "Enter sends. Shift+Enter adds a line.",
    bloqueado: "Waiting for the previous answer. You can ask again once it arrives.",
  },

  tools: {
    procurarArtigos: "Search items",
    procurarFornecedores: "Search suppliers",
    saldoDeArtigo: "Item balance",
    artigosAbaixoDoMinimo: "Items below minimum",
    lotesAVencer: "Lots expiring",
    movimentosDeArtigo: "Item movements",
    comprasPorPeriodo: "Purchases by period",
    rececoes: "Deliveries",
    rececao: "Delivery",
    historicoDePrecos: "Price history",
    contagens: "Stock counts",
    contagem: "Stock count",
    alertas: "Alerts",
    artigo: "Item details",
    receitas: "Recipes",
    receita: "Recipe",
    producoesRecentes: "Recent production",
    equipa: "Team",
    estabelecimento: "Establishment",
    ajudaSobre: "Help",
    dias: (n: number) => (n === 1 ? "1 day" : `${String(n)} days`),
    periodo: (desde: string, ate: string) => `${desde} to ${ate}`,
    desde: (data: string) => `from ${data}`,
    ate: (data: string) => `until ${data}`,
    movimentoEntrada: "receipt",
    movimentoDevolucao: "return",
    movimentoConsumo: "consumption",
    movimentoDesperdicio: "waste",
    movimentoAjuste: "adjustment",
    movimentoTransferenciaSaida: "transfer (out)",
    movimentoTransferenciaEntrada: "transfer (in)",
    movimentoProducaoSaida: "to production",
    movimentoProducaoEntrada: "produced",
  },
};
