/**
 * A copy do `assistente`, em **pt-PT**. É a fonte; o inglês é anotado com
 * `typeof PT` e não compila se divergir (ADR 0019, decisão 3).
 *
 * Duas famílias de frases que **não** são a mesma coisa, e vivem em secções
 * separadas de propósito:
 *
 *  - `recusas` são respostas HTTP a uma pergunta que **não chegou a ser feita**
 *    (503 sem modelo, 429 no teto, 409 com outra em curso). A pergunta fica no
 *    compositor e a pessoa decide o que fazer com ela;
 *  - `errosDaMensagem` são o `error_code` de um turno que **existiu** e falhou a
 *    meio (ADR 0027, decisão 4). A pergunta já está na conversa, e a frase diz
 *    porque é que a resposta não veio.
 */
export const PT = {
  ecra: {
    titulo: "Assistente",
    novaConversa: "Nova conversa",
    abrirConversas: "Abrir as conversas",
    fecharConversas: "Fechar as conversas",
    conversasDescricao: "As suas conversas com o assistente neste estabelecimento.",
  },

  lista: {
    titulo: "Conversas",
    aCarregar: "A carregar as conversas…",
    erroAoCarregar: "Não foi possível carregar as conversas",
    vazioTitulo: "Ainda não há conversas",
    vazioCorpo: "A primeira pergunta abre uma conversa. Cada conversa fica guardada 90 dias.",
    /** O `title` da linha: a data por extenso, que a coluna encurta. */
    ultimaMensagem: (data: string) => `Última mensagem: ${data}`,
    apagar: "Apagar",
    apagarPista: "Apaga a conversa. Pede confirmação, e é final.",
    apagarEFinal: "Apagar é final.",
    aApagar: "A apagar…",
    cancelar: "Cancelar",
    /** O nome acessível dos botões, para dez «Apagar» não serem iguais. */
    aConversa: (titulo: string) => ` a conversa «${titulo}»`,
    erroAoApagar: "Não foi possível apagar a conversa",
  },

  /**
   * O painel lateral e o seu lançador (ADR 0027, decisão 10, adenda): o mesmo
   * assistente, numa gaveta à direita sobre o ecrã onde se está.
   */
  painel: {
    /** O nome do lançador e o título da gaveta: a mesma palavra do menu. */
    titulo: "Assistente",
    descricao: "Pergunte sobre o stock deste estabelecimento sem sair do ecrã onde está.",
    abrirEmPagina: "Abrir em página inteira",
    fechar: "Fechar o assistente",
  },

  inicio: {
    titulo: "Pergunte sobre o stock",
    corpo:
      "O assistente responde com os números deste estabelecimento e diz onde os foi buscar. Comece por uma destas perguntas, ou escreva a sua.",
    exemplo1: "Quanto tenho de farinha?",
    exemplo2: "O que vence esta semana?",
    exemplo3: "Que artigos estão abaixo do mínimo?",
  },

  fio: {
    aCarregar: "A carregar a conversa…",
    erroAoCarregar: "Não foi possível carregar esta conversa",
    naoExisteTitulo: "Esta conversa já não está aqui",
    naoExisteCorpo:
      "O endereço aponta para uma conversa que não existe neste estabelecimento, ou que foi apagada.",
    /** Os dois lados de um turno, só para quem ouve. */
    pergunta: "Pergunta",
    resposta: "Resposta",
    aConsultar: "A consultar o stock…",
    aConsultarTool: (tool: string) => `A consultar: ${tool}…`,
    desistiuTitulo: "Deixei de perguntar",
    desistiuCorpo:
      "Passou minuto e meio e a resposta ainda não chegou. O trabalho não se perdeu — aparece nesta conversa quando ficar pronta. Pode voltar a perguntar se ela está a ser preparada.",
    erroTitulo: "Não consegui responder",
    semResposta: "A resposta chegou vazia.",
    fontes: "Fontes",
    linhas: (n: number) => (n === 1 ? "1 linha" : `${String(n)} linhas`),
    truncado: "truncado",
    falhou: "falhou",
    semFontes: "Sem consultas ao stock.",
  },

  errosDaMensagem: {
    tetoDeIteracoes:
      "A pergunta precisava de mais consultas do que o permitido. Tente dividi-la em perguntas mais pequenas.",
    tetoDeCusto: "O orçamento diário do assistente esgotou-se a meio da resposta. Volte amanhã.",
    tempoEsgotado: "A resposta demorou demasiado e foi abandonada. Tente outra vez.",
    respostaInvalida: "O assistente devolveu uma resposta que não se consegue ler. Tente outra vez.",
    erroDoModelo: "O serviço do assistente falhou. Tente outra vez daqui a pouco.",
    pertencaRevogada: "Já não pertence a este estabelecimento, por isso a resposta não foi calculada.",
  },

  recusas: {
    indisponivelTitulo: "O assistente não está configurado neste estabelecimento",
    indisponivelCorpo:
      "Quem gere a conta pode activá-lo. Até lá, as respostas estão nos ecrãs de Stock e de Alertas.",
    tetoTitulo: "Teto diário atingido",
    tetoCorpo:
      "O assistente já respondeu ao máximo de perguntas de hoje. Volta a estar disponível amanhã.",
    pendenteTitulo: "Ainda estou a responder",
    pendenteCorpo: "Espere pela resposta anterior antes de perguntar outra vez.",
    cheiaTitulo: "Esta conversa está cheia",
    cheiaCorpo: "Uma conversa tem no máximo 30 perguntas. Abra uma nova para continuar.",
    perguntaInvalidaTitulo: "A pergunta não foi aceite",
    perguntaInvalidaCorpo: "Escreva uma pergunta com até 2000 caracteres.",
    muitasSeguidasTitulo: "Muitas perguntas seguidas",
    muitasSeguidasCorpo: "Aguarde um minuto e tente outra vez.",
    redeTitulo: "Não foi possível enviar a pergunta",
    redeCorpo: "Verifique a ligação e tente outra vez.",
  },

  compositor: {
    rotulo: "Pergunta",
    /** O `aria-label` do contador: os dígitos sozinhos não dizem o que contam. */
    contadorAcessivel: (n: number, maximo: number) =>
      `${String(n)} de ${String(maximo)} caracteres`,
    perguntar: "Perguntar",
    aPerguntar: "A perguntar…",
    atalho: "Enter envia. Shift+Enter muda de linha.",
    bloqueado: "À espera da resposta anterior. Pode perguntar outra vez quando ela chegar.",
  },

  /**
   * Os nomes legíveis das sete tools (ADR 0027, decisão 5) e as palavras dos
   * seus argumentos. O nome técnico fica no `title` para quem quiser.
   */
  tools: {
    procurarArtigos: "Procurar artigos",
    procurarFornecedores: "Procurar fornecedores",
    saldoDeArtigo: "Saldo de artigo",
    artigosAbaixoDoMinimo: "Artigos abaixo do mínimo",
    lotesAVencer: "Lotes a vencer",
    movimentosDeArtigo: "Movimentos de artigo",
    comprasPorPeriodo: "Compras por período",
    dias: (n: number) => (n === 1 ? "1 dia" : `${String(n)} dias`),
    periodo: (desde: string, ate: string) => `${desde} a ${ate}`,
    desde: (data: string) => `desde ${data}`,
    ate: (data: string) => `até ${data}`,
    /** As palavras do produto para os tipos do ledger (as do ecrã de artigo). */
    movimentoEntrada: "entrada",
    movimentoDevolucao: "devolução",
    movimentoConsumo: "consumo",
    movimentoDesperdicio: "desperdício",
    movimentoAjuste: "ajuste",
    movimentoTransferenciaSaida: "transferência (saída)",
    movimentoTransferenciaEntrada: "transferência (entrada)",
    movimentoProducaoSaida: "para produção",
    movimentoProducaoEntrada: "produzido",
  },
};
