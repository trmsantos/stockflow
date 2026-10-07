/**
 * A copy do módulo `reporting`, em **pt-PT**. É a fonte; o inglês é anotado com
 * `typeof PT` e não compila se divergir (ADR 0019, decisão 3).
 *
 * Por feature e não num ficheiro central, pela razão da ADR 0013 (decisão 5): a
 * copy vive ao lado do `vocabulario.ts` da feature que a usa.
 *
 * ## O vocabulário fica aqui; a **exaustividade** fica onde estava
 *
 * Os `Record<União, …>` do `vocabulario.ts` e do `abas.ts` não se mudam de
 * sítio: é deles que vem a garantia de que um id novo no contrato deixa de
 * compilar até alguém lhe dar uma palavra. O que mudou de sítio são só as
 * palavras, e **cada folha é nomeada individualmente** no `Record` que a
 * consome — o `check-textos.mjs` conta uma chave como usada quando alguém a
 * nomeia, e entregar um objecto inteiro deixava as folhas sem uso visível.
 *
 * ## Uma frase com valores é uma função, e a assinatura é parte do contrato
 *
 * É o que o `typeof PT` compra sobre um `Record<Chave, string>`: mudar
 * `(valor: string)` para `(valor: string, moeda: string)` numa língua e não na
 * outra não compila. O plural e a junção de uma enumeração vivem dentro dessas
 * funções, porque são regras **da língua** e não do ecrã.
 */
export const PT = {
  /* -------------------------------------------------------------------------
   * O ecrã Início e os seis cartões de pré-visualização.
   * ---------------------------------------------------------------------- */
  inicio: {
    titulo: "Início — o trabalho do dia",
    oQueEstaAEspera: "O que está à espera",

    alertasExpira: "Alertas — o que expira",
    aCarregarExpira: "A carregar o que está a expirar…",
    vazioExpira: "nada a expirar",

    alertasFalta: "Alertas — o que falta",
    aCarregarFalta: "A carregar o que está em falta…",
    vazioFalta: "nada abaixo do mínimo",
    /** A régua contra a qual se lê a quantidade da linha, abreviada. */
    minimo: (quantidade: string) => `mín. ${quantidade}`,

    receber: "Receber",
    aCarregarRececoes: "A carregar o que está por dar entrada…",
    vazioRececoes: "nada por dar entrada",
    semValor: "sem valor",

    contar: "Contar",
    aCarregarContagem: "A carregar a contagem a decorrer…",
    vazioSemContagem: "nenhuma contagem a decorrer — comece uma",
    vazioSemZonas: "contagem aberta, sem zonas para contar",

    stock: "Stock",
    aCarregarStock: "A carregar as piores linhas de stock…",
    vazioStock: "sem stock registado",

    painel: "Painel",
    aCarregarGrafico: "A carregar o gráfico de vendas e compras…",
    vazioSemAcesso: "sem acesso ao painel",
    vazioUmIntervalo: "um só intervalo — nada para comparar",
    rotuloDoGrafico: (maximo: string) =>
      `Vendas e compras dos últimos sete dias, com o máximo do eixo em ${maximo}`,
  },

  /* -------------------------------------------------------------------------
   * O ecrã do painel: os títulos dos blocos e os seus estados.
   * ---------------------------------------------------------------------- */
  painel: {
    tituloComPergunta: (pergunta: string) => `Painel de gestão — ${pergunta}`,
    naoSabe: "O que este painel não sabe",
    aCarregarDeclaracoes: "A carregar o que o painel declara…",
    dinheiroEMercadoria: "O dinheiro e a mercadoria",
    vendasECompras: "Vendas e compras",
    notaDoGrafico: (grao: string, maximo: string) => `${grao} · até ${maximo}`,
    erroDoGrafico: "Não foi possível carregar o gráfico",
    nadaRegistado: (periodo: string) => `Nada registado ${periodo}`,
    vazioTitulo: "Sem vendas, sem compras e sem consumo nesta janela",
    vazioCorpo:
      "Não há aqui quatro linhas de zeros porque zeros não respondem a nada. Comece por dar entrada à mercadoria que chegou: as compras aparecem no painel no dia em que a receção é confirmada.",
    receberMercadoria: "Receber mercadoria",
    perdas: "Desperdício e quebra desconhecida",
    fechoDe: (mes: string) => `Fecho de ${mes}`,
    erroDoFecho: "Não foi possível carregar o fecho do mês",
    mesSemNada: (mes: string) =>
      `Não há nada registado em ${mes}. Use a navegação de mês, na barra acima, para um mês com movimento.`,
    resultadoDe: (mes: string) => `Resultado de ${mes}`,
    custoPorCargo: "Custo por cargo",
    /** Só em desenvolvimento: o caminho que vem a seguir não é copy. */
    demonstracao: "Os números do painel são de demonstração. O sistema visual está em",
  },

  /* -------------------------------------------------------------------------
   * As três abas: o nome e a pergunta que cada uma responde.
   * ---------------------------------------------------------------------- */
  abas: {
    regua: "Secções do painel",
    dinheiro: "Dinheiro",
    dinheiroPergunta: "Quanto entrou e quanto saiu neste período?",
    perdas: "Perdas",
    perdasPergunta: "O que se perdeu, e sabe-se mesmo quanto?",
    pessoal: "Pessoal",
    pessoalPergunta: "Quanto custa a equipa, e como fechou o mês?",
  },

  /**
   * Os períodos, em **duas** formas: a curta é um controlo da barra e a longa é
   * a frase que o cabeçalho de um bloco escreve ("Nada registado nos últimos 7
   * dias"). As duas são precisas, e é por isso que são duas chaves e não uma.
   */
  periodos: {
    hojeCurto: "Hoje",
    hoje: "hoje",
    seteDiasCurto: "7 dias",
    seteDias: "nos últimos 7 dias",
    trintaDiasCurto: "30 dias",
    trintaDias: "nos últimos 30 dias",
    esteMesCurto: "Este mês",
    esteMes: "neste mês",
    mesAnteriorCurto: "Mês anterior",
    mesAnterior: "no mês anterior",
  },

  /* -------------------------------------------------------------------------
   * A barra do ecrã: o seletor e a fronteira que o servidor resolveu.
   * ---------------------------------------------------------------------- */
  barra: {
    periodo: "Período do painel",
    /** Prefixo só-para-áudio do intervalo. Acaba com espaço de propósito. */
    janela: "Janela: ",
    mesDeNegocio: "Mês de negócio: ",
    diaDeNegocioDesde: (hora: string) => ` · dia de negócio desde as ${hora}`,
  },

  /* -------------------------------------------------------------------------
   * O fecho do mês: a navegação, a moldura do mês a correr e a recusa.
   * ---------------------------------------------------------------------- */
  fecho: {
    navegacao: "Mês do fecho",
    /**
     * O botão de navegação, que **não** é o período `prev_month`: aqui "Mês
     * anterior" é um passo para trás no calendário, e lá é a janela escolhida.
     * Em inglês são duas palavras diferentes, e foi essa a razão de separá-las.
     */
    mesAnterior: "Mês anterior",
    mesSeguinte: "Mês seguinte",
    semMesSeguinte: "O mês corrente é o último com dados: o seguinte ainda não aconteceu.",
    mesFechado: " · mês fechado",
    aCorrer: (decorridos: number, total: number) =>
      ` · a correr: ${String(decorridos)} de ${String(total)} dias`,
    avisoTitulo: (decorridos: number, total: number) =>
      `Mês a correr: ${String(decorridos)} de ${String(total)} dias`,
    avisoCorpo:
      "O pessoal e os custos fixos são do mês inteiro — um salário é um facto mensal e não se divide por dias. As vendas e a mercadoria são as dos dias que já passaram, logo o resultado e os rácios desta aba só ficam comparáveis quando o mês fechar.",
    semPermissaoTitulo: "O painel de gestão é do dono do estabelecimento",
    semPermissaoCorpo:
      "Inclui salários e custo por cargo, e um custo por cargo com uma pessoa é o salário dessa pessoa com outro nome. O trabalho do dia — o que expira, o que falta, o que chegou por dar entrada — está no Início, e é igual para toda a gente.",
    irParaOInicio: "Ir para o Início",
    decideOServidor: "Quem decide isto é o servidor, não este ecrã.",
    aCarregar: "A carregar o fecho do mês…",
  },

  /**
   * As rubricas que aparecem em mais do que uma das três tabelas de dinheiro,
   * definidas **uma vez**: uma rubrica mantém o mesmo nome em todo o painel.
   */
  rubricas: {
    vendasSemIva: "Vendas, sem IVA",
    comIva: (valor: string) => `a base dos rácios; com IVA são ${valor}`,
    variacaoDeStock: "Variação de stock",
    totalDeGastos: "Total de gastos",
    resultado: "Resultado",
    /**
     * As cinco que o gate não via: duas palavras minúsculas dentro de uma
     * expressão de JSX (`{ligado ? "menos" : "explicar"}`), o prefixo de uma
     * sub-rubrica, e dois `<th>` de uma palavra sem acento. É a cobertura
     * parcial da regra 1b do `check-textos.mjs`, dita no cabeçalho dele — estas
     * estão aqui porque alguém as leu, não porque o gate as pediu.
     */
    explicar: "explicar",
    menos: "menos",
    /** Acaba em espaço: a rubrica vem a seguir. */
    dosQuais: "dos quais ",
    coluna: "Rubrica",
    colunaDoValor: "Valor",
  },

  /**
   * As seis parcelas de custo: o rótulo e a nota de cada uma. A nota é o
   * `← dinheiro que saiu` da ADR 0013 (decisão 4) — o que impede o mês do
   * stock-up de ser lido como prejuízo.
   */
  custos: {
    comprasRotulo: "Compras a fornecedores",
    comprasNota: "dinheiro que saiu para fornecedores",
    consumoRotulo: "Mercadoria consumida",
    consumoNota: "o que saiu do stock, ao custo gravado no movimento",
    desperdicioRotulo: "Desperdício",
    desperdicioNota: "já está dentro da mercadoria consumida",
    quebraRotulo: "Quebra desconhecida",
    quebraNota: "o líquido das contagens",
    pessoalRotulo: "Pessoal",
    pessoalNota: "custo-empresa do mês, nunca rateado por dias",
    fixosRotulo: "Custos fixos",
    fixosNota: "renda, energia, água, gás, TPA, licenças, contabilista",
  },

  /**
   * Os campos da régua de contadores. São **nomes de campo** e não frases: um
   * microrótulo em caixa alta com 25 caracteres fazia o campo crescer para
   * ~330px, e os campos da régua empacotam à esquerda sem esticar.
   */
  contadores: {
    vendas: "vendas",
    mercadoria: "mercadoria",
    doQueSeVendeu: "do que se vendeu, sem IVA",
    valorDeStock: "valor de stock",
    aoCustoGravado: "ao custo gravado no movimento",
    pessoal: "pessoal",
    semRemuneracaoDoDono: "sem a remuneração do dono",
    mercadoriaMaisPessoal: "mercadoria + pessoal",
    sobreVendasSemIva: "sobre vendas sem IVA",
    aCarregar: "A carregar os números do período…",
    erroDoPeriodo: "Não foi possível carregar o período",
  },

  /* -------------------------------------------------------------------------
   * O bloco do dinheiro: as quatro linhas e a conta que fecha à vista.
   * ---------------------------------------------------------------------- */
  dinheiro: {
    tabela: "O dinheiro e a mercadoria do período, com a variação de stock",
    semConsumo:
      "sem consumo registado neste período — ver o que falta, em «O que este painel não sabe»",
    /**
     * A identidade, **numa frase só**: a ordem dos termos é a da conta e parti-la
     * em pedaços deixava alguém montá-la ao contrário noutra língua.
     */
    aContaFecha: (periodo: string) =>
      `A conta fecha: variação de stock = compras − mercadoria consumida − quebra desconhecida ${periodo}.`,
    aCarregar: "A carregar o dinheiro do período…",
    /** Nenhuma das três tem cor: um `+1 150 €` não é bom nem mau. */
    variacaoIgual: "entrou tanto quanto saiu",
    variacaoGastou: "gastou-se a despensa: saiu mais stock do que entrou",
    variacaoEncheu: "encheu-se a despensa: entrou mais stock do que saiu",
  },

  /* -------------------------------------------------------------------------
   * O bloco das perdas: as duas linhas e o desperdício por motivo.
   * ---------------------------------------------------------------------- */
  perdas: {
    /** Quando o líquido das contagens é a favor da casa, não é uma perda. */
    excedenteDeContagem: "Excedente de contagem",
    tabela: "As duas perdas do período: desperdício e quebra desconhecida",
    vazio:
      "Nada deitado fora neste período. O desperdício aparece aqui por motivo, do maior para o menor, à medida que for registado.",
    notaDasBarras: (total: string) =>
      `Desperdício por motivo, ${total} no total — a ordem é a grandeza.`,
    campoMotivo: "Motivo",
    rotuloDasBarras: "Desperdício por motivo, do maior para o menor",
    /** "uma quebra grande de uma vez é um acidente, dezoito pequenas são um processo". */
    rotuloDaBarra: (motivo: string, movimentos: number) =>
      `${motivo} · ${String(movimentos)} ${movimentos === 1 ? "movimento" : "movimentos"}`,
    aCarregar: "A carregar as perdas do período…",
  },

  /** Os cinco motivos de quebra, com as mesmas palavras do `inventory`. */
  motivos: {
    expirado: "expirado",
    estragado: "estragado",
    quebra: "quebra",
    perdaDePreparacao: "perda de preparação",
    outro: "outro",
  },

  /* -------------------------------------------------------------------------
   * A aba do pessoal: o aviso do rácio e o custo por cargo.
   * ---------------------------------------------------------------------- */
  pessoal: {
    /**
     * A palavra "lucro" **não entra nesta frase**: a explicação de contabilidade
     * é "o que o dono tira é distribuição de lucro, não despesa", e bastava
     * escrevê-la assim para pôr a palavra ao lado de um número. Quem passa os
     * olhos lê o substantivo e não o "não".
     */
    avisoDoRacio:
      "Este rácio não é comparável com os do sector: a remuneração do dono não entra nos custos de pessoal. Quando o dono trabalha no negócio sem se pagar, o custo de pessoal real é 4 a 5 pontos mais alto do que este número.",
    cargosVazio:
      "Não há cargos com custo neste mês. O custo por cargo aparece aqui à medida que houver remunerações registadas.",
    cargoNaoEPapel: "O cargo é a função de quem trabalha, não o acesso que tem à aplicação.",
    campoCargo: "Cargo",
    custo: "Custo",
    rotuloDosCargos: "Custo de pessoal por cargo, do maior para o menor",
    rotuloDoCargo: (cargo: string, pessoas: number) =>
      `${cargo} · ${String(pessoas)} ${pessoas === 1 ? "pessoa" : "pessoas"}`,
  },

  /**
   * O vocabulário dos salários. **TSU** e **duodécimos** não têm equivalente
   * inglês e por isso o termo português fica, explicado uma vez entre
   * parênteses na outra língua.
   */
  salarios: {
    base: "Bruto base",
    tsu: "Segurança Social (TSU)",
    subsidios: "Subsídios, em duodécimos",
    alimentacao: "Subsídio de alimentação",
    seguro: "Seguro de acidentes de trabalho",
    custoEmpresa: "custo-empresa",
    custoEmpresaNota: "custo-empresa: o bruto mais o que a empresa paga por cima",
    bruto: "bruto",
    brutoNota: "bruto: o que o trabalhador recebe antes de descontos",
    origemContrato: "do contrato",
    origemContratoNota: "do contrato, sem trabalho suplementar",
    origemProcessamento: "do processamento",
    origemProcessamentoNota: "do processamento do mês",
  },

  /** As oito categorias de custo fixo. */
  outrosCustos: {
    renda: "Renda",
    energia: "Energia",
    agua: "Água",
    gas: "Gás",
    cartoes: "TPA e cartões",
    licencas: "Licenças",
    contabilista: "Contabilista",
    outros: "Outros",
  },

  /**
   * O que o resultado **não** inclui, e a frase que enumera as palavras.
   *
   * A junção vive na função porque é regra da língua: o português separa por
   * vírgula e remata com "e", e a última palavra não leva vírgula antes.
   */
  exclusoes: {
    amortizacoes: "amortizações",
    financiamento: "financiamento",
    irc: "IRC",
    remuneracaoDoDono: "remuneração do dono",
    naoInclui: (palavras: readonly string[]) => {
      const ultima = palavras.at(-1) ?? "";
      const frase =
        palavras.length === 1 ? ultima : `${palavras.slice(0, -1).join(", ")} e ${ultima}`;
      return `Não inclui ${frase}.`;
    },
  },

  /* -------------------------------------------------------------------------
   * O resultado do mês: a tabela, o que fica de fora e a repartição.
   * ---------------------------------------------------------------------- */
  resultado: {
    tabela: "Vendas, gastos e resultado do mês",
    /** Dito na nota e não deduzido da indentação: as compras não somam. */
    naoEntraNoTotal: (nota: string) => `não entra no total — ${nota}`,
    totalDeGastosNota: "mercadoria, perdas, pessoal e custos fixos — somado pelo servidor",
    notaFechado: "vendas sem IVA menos o total de gastos",
    notaACorrer: "mês a correr: o pessoal e os custos fixos são do mês inteiro",
    /** Acaba com espaço: o que se lê a seguir é a frase das exclusões. */
    negativo: "Resultado negativo neste mês. ",
    comExclusoes: (exclusoes: string) =>
      `${exclusoes} É o que sobra do que está nesta tabela, e só isso.`,
    notaDasBarras: "Repartição dos gastos que somam ao total, do maior para o menor.",
    campoGasto: "Gasto",
    rotuloDasBarras: "Gastos do mês por categoria, do maior para o menor",
  },

  /* -------------------------------------------------------------------------
   * O que o painel declara não saber (ADR 0013, decisão 7).
   * ---------------------------------------------------------------------- */
  qualidade: {
    campoConsumo: "consumo registado",
    sim: "sim",
    nao: "não",
    consumoSim: "A mercadoria consumida vem do ledger, ao custo gravado em cada movimento.",
    consumoNao:
      "Sem consumo no ledger não há mercadoria consumida nem rácio de mercadoria — e sem eles este painel mostraria uma margem que não existe.",
    portaRegistar: "Registar o que saiu",

    campoSemFatura: "mercadoria sem fatura",
    semFaturaHa:
      "Entrou por guia de remessa e está valorizada ao último preço conhecido; a diferença aparece quando a fatura chegar.",
    semFaturaNenhuma: "Toda a mercadoria deste período tem fatura: as compras estão ao preço certo.",
    portaRececoes: "Ver as receções",

    campoUltimaContagem: "última contagem",
    nunca: "nunca",
    semContagem:
      "Sem nenhuma contagem, a quebra desconhecida é zero por falta de medida e não por falta de quebra.",
    contouSe: (quando: string) =>
      `Contou-se ${quando}. A quebra desconhecida só mede o que foi contado até aí.`,
    portaContar: "Contar agora",

    campoOrigemDasVendas: "origem das vendas",
    nenhuma: "nenhuma",
    pos: "POS",
    aMao: "à mão",
    origemDasVendas: (origem: string) =>
      `${origem}. Os rácios são sobre vendas sem IVA; o valor com IVA é o do fecho de caixa.`,
    /** Acaba com espaço: o que se lê a seguir é a data, em mono. */
    sabeTudo: "O painel sabe tudo o que precisa. Última contagem a ",
  },

  /* -------------------------------------------------------------------------
   * O gráfico de vendas e compras.
   * ---------------------------------------------------------------------- */
  grafico: {
    serieVendas: "Vendas",
    serieCompras: "Compras",
    diaADia: "dia a dia",
    semanaASemana: "semana a semana",
    valor: "Valor",
    umSoIntervalo:
      "Um só intervalo neste período: não há variação para desenhar. Os totais estão em cima, e os outros períodos da barra do topo dão sete dias ou mais.",
    rotuloDaSerie: (serie: string, total: string) => `${serie} — ${total} no total`,
    rotulo: (grao: string, maximo: string) =>
      `Vendas e compras ${grao}, com o máximo do eixo em ${maximo}`,
    aCarregar: "A carregar o gráfico do período…",
  },

  /** A receita: em que base está registada, e de onde vem. */
  receita: {
    brutoNota: "registado com IVA, como no fecho de caixa",
    liquidoNota: "registado sem IVA",
    origemNenhuma: "as vendas ainda não estão registadas",
    origemManual: "vendas registadas à mão",
    origemPos: "vendas vindas do POS",
  },

  /**
   * A condição que acompanha a quebra desconhecida. Nunca aparece sem a data da
   * última contagem (ADR 0013, decisão 7).
   */
  contagem: {
    nuncaSeContou:
      "nunca se contou: o zero da quebra é ausência de contagem, não ausência de quebra",
    semContagemNoPeriodo: (data: string) =>
      `sem contagem neste período — a última foi a ${data}, e o desvio aparece todo na próxima`,
    ultima: (data: string) => `última contagem a ${data}`,
  },
};
