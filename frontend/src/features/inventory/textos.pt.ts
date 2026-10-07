/**
 * A copy do módulo `inventory`, em **pt-PT**. É a fonte; o inglês é anotado com
 * `typeof PT` e não compila se divergir (ADR 0019, decisão 3).
 *
 * Por feature e não num ficheiro central, pela razão da ADR 0013 (decisão 5): a
 * copy vive ao lado do `vocabulario.ts` da feature que a usa.
 *
 * ## O que fica **fora** deste ficheiro, e porquê
 *
 * As mensagens de Zod do `schemas.ts` deste módulo validam a **forma da
 * resposta** (`"decimal inválido"`, `"hora inválida"`) e ninguém as lê: um
 * contrato partido vira `ErroDeContrato` e o ecrã mostra a frase do `erros.ts`.
 * Estão declaradas no `NAO_E_COPY` do `scripts/check-textos.mjs` e ficam lá. As
 * mensagens que **se leem** — as dos formulários de desperdício, de contagem e
 * de fecho — são escritas à mão nos componentes e estão todas aqui.
 *
 * Os `Map` do `vocabulario.ts` e os arrays de colunas das tabelas também ficam
 * onde estão: é lá que o contrato se amarra (um `EstadoNivel` novo tem de passar
 * pelo `Map`), e o que vem para cá são só as palavras.
 *
 * ## Sem `as const`
 *
 * Os valores querem-se `string` e não literais: com `as const` o `typeof PT` do
 * inglês exigiria as mesmas palavras portuguesas. As funções de interpolação é
 * que fazem parte do contrato, e essas são tipadas pela assinatura.
 */
export const PT = {
  /**
   * O que aparece em mais do que um ficheiro, definido **uma vez**. Não é uma
   * gaveta de sobras: é a regra de escrita do DESIGN.md — a mesma acção mantém o
   * mesmo nome em todo o produto — e duas chaves `aRegistar` eram dois sítios
   * onde ela se podia perder.
   */
  accoes: {
    verOStock: "Ver o stock",
    aRegistar: "A registar…",
    aCarregarStock: "A carregar o stock…",
    /**
     * O sinal de uma diferença, **só para áudio**: o número já traz o "−" e a
     * cor nunca comunica sozinha. As mesmas duas palavras servem a linha de
     * contagem e a lista de diferenças do fecho.
     */
    aMenos: "a menos",
    aMais: "a mais",
  },

  /**
   * Os rótulos de coluna das quatro tabelas e do cabeçalho da contagem, num
   * sítio só: a mesma coluna quer dizer a mesma coisa nas quatro, e quatro
   * cópias de "Quantidade" divergiam na primeira correcção feita só numa.
   *
   * Os arrays `COLUNAS` continuam nos componentes — é lá que se decide a largura
   * e a ordem, que não são copy.
   */
  colunas: {
    artigo: "Artigo",
    quantidade: "Quantidade",
    minimo: "Mínimo",
    estado: "Estado",
    validade: "Validade",
    onde: "Onde",
    valor: "Valor",
    porque: "Porquê",
    lote: "Lote",
    accao: "Acção",
    hora: "Hora",
    motivo: "Motivo",
    quem: "Quem",
    movimento: "Movimento",
    contado: "Contado",
    esperado: "Esperado",
    diferenca: "Diferença",
  },

  /**
   * O vocabulário do domínio: os enums do contrato por extenso.
   *
   * Em chaves planas e não em objectos aninhados, como no `accounts`: os `Map`
   * sobre as uniões geradas ficam no `vocabulario.ts`, que é onde um valor novo
   * no contrato tem de passar. O catálogo guarda palavras.
   */
  vocabulario: {
    estadoNegativo: "Negativo",
    estadoEsgotado: "Esgotado",
    estadoBaixo: "Baixo",
    /** Não se traduz: são as duas letras nas duas línguas. */
    estadoOk: "OK",
    movimentoEntrada: "Entrada",
    movimentoConsumo: "Consumo",
    movimentoDesperdicio: "Desperdício",
    movimentoAjuste: "Ajuste",
    movimentoTransferenciaSaida: "Transferência (saída)",
    movimentoTransferenciaEntrada: "Transferência (entrada)",
    movimentoDevolucao: "Devolução",
    /**
     * As duas pernas de uma fornada (ADR 0014). "Produção" e não "Fabrico": é a
     * palavra que se usa numa pastelaria, e é a que o guião da sessão 0 usa.
     */
    movimentoProducaoConsumo: "Produção (consumo)",
    movimentoProducaoEntrada: "Produção (entrada)",
    motivoExpirado: "expirado",
    motivoEstragado: "estragado",
    motivoQuebra: "quebra",
    motivoPerdaDePreparacao: "perda de preparação",
    motivoOutro: "outro",
  },

  /**
   * A leitura de uma validade. São funções porque interpolam o prazo ou a data,
   * e a assinatura faz parte do contrato: mudar `(quando: string)` numa língua e
   * não na outra não compila.
   *
   * `use_by` e `best_before` **não se dizem com as mesmas palavras**, e isso é
   * produto e não estilo: "consumir até" é limite legal, "perde qualidade" é
   * durabilidade mínima, e uma amêndoa laminada marcada como "expira" custa a
   * confiança do dono na lista inteira (guião da sessão 0, §2). O rodapé dos
   * Alertas cita estas duas palavras, logo elas mudam **juntas**.
   */
  validade: {
    semValidade: "sem validade",
    expirou: (quando: string) => `expirou ${quando}`,
    expiraHoje: "expira hoje",
    expiraQuando: (quando: string) => `expira ${quando}`,
    expiraA: (data: string) => `expira a ${data}`,
    perdeuQualidade: (quando: string) => `perdeu qualidade ${quando}`,
    perdeQualidade: (quando: string) => `perde qualidade ${quando}`,
    melhorAntesDe: (data: string) => `melhor antes de ${data}`,
    consumirAte: "consumir até (limite legal)",
    consumirPreferencialmente: "consumir de preferência antes de (qualidade)",
    /** No `title`: o lote, a natureza do prazo e a data exacta, por extenso. */
    titulo: (lote: string, natureza: string, data: string) =>
      `Lote ${lote} · ${natureza} ${data}`,
  },

  filtros: {
    procurar: "Procurar artigo",
    procurarPista: "Procurar artigo…",
    localizacao: "Localização",
    localizacaoPista: "Ver uma localização ou o total consolidado",
    todas: "Todas",
  },

  lista: {
    erroDeStock: "Não foi possível carregar o stock",
    semCorrespondenciaTitulo: "Nenhum artigo corresponde",
    semCorrespondenciaCorpo:
      "A procura e os filtros do topo não deixaram passar nada. O stock continua lá.",
    limparFiltros: "Limpar filtros",
    vazioTitulo: "Ainda não há stock registado",
    vazioCorpo:
      "O stock aparece aqui à medida que a mercadoria entra. Comece por uma entrada de fornecedor.",
    receberMercadoria: "Receber mercadoria",
  },

  /**
   * As duas réguas de contadores — a do Stock e a dos Alertas. Dois campos e uma
   * nota são os mesmos nas duas (`emFalta`, `abaixoDoMinimo`), e os `title` é que
   * diferem, porque cada um diz de onde vem o número.
   */
  numeros: {
    aCarregar: "A carregar os números…",
    erroDeStockTitulo: "Não foi possível contar os artigos em falta",
    erroDeStockCorpo:
      "A tabela abaixo continua a funcionar. Os três números voltam à segunda tentativa.",
    erroDeAlertasTitulo: "Não foi possível contar os alertas",
    erroDeAlertasCorpo:
      "A lista abaixo continua a funcionar. Os três números voltam à segunda tentativa.",
    emFalta: "em falta",
    abaixoDoMinimo: "abaixo do mínimo",
    artigosAbaixoDoMinimo: "Artigos abaixo do mínimo de stock",
    aExpirar: "a expirar",
    dentroDeDias: (dias: string) => `dentro de ${dias} dias`,
    artigosComValidade: (dias: string) =>
      `Artigos com validade dentro de ${dias} dias — o limiar é do servidor`,
    valorDeStock: "valor de stock",
    lotesAExpirar: "lotes a expirar",
    lotesComValidade: (dias: string) =>
      `Lotes com validade dentro de ${dias} dias — o limiar é do servidor e aparece dentro de cada alerta`,
    artigosAbaixoDoMinimoNosAlertas:
      "Artigos abaixo do mínimo de stock — o mesmo número do ecrã de Stock",
    deitadoForaHoje: "deitado fora hoje",
    desdeAs: (hora: string) => `desde as ${hora}`,
    diaDeNegocio: (hora: string, inicio: string) =>
      `O dia de negócio deste estabelecimento começa às ${hora}, ou seja às ${inicio} de hoje — o que foi deitado fora antes disso conta no dia anterior`,
  },

  stock: {
    titulo: "Stock — o que tenho, e quanto",
    tabela: "Níveis de stock, ordenados pelo que está pior primeiro",
    /** A contagem anunciada a cada tecla, em `aria-live`. */
    artigos: (quantos: number) => (quantos === 1 ? "1 artigo" : `${String(quantos)} artigos`),
    /**
     * O pé da tabela: quantos, de quantos, e a regra de ordenação. Uma função e
     * não três chaves porque a frase **é** uma: muda de forma no singular, e o
     * "de N" só aparece quando a página está truncada.
     */
    rodape: (quantos: number, total: number | null) => {
      const contagem = quantos === 1 ? "1 artigo" : `${String(quantos)} artigos`;
      const de = total === null ? "" : ` de ${String(total)}`;
      return `${contagem}${de}, ordenados pelo que está pior primeiro`;
    },
  },

  alertas: {
    titulo: "Alertas — o que expira, o que falta, quanto deitei fora",
    tabela: "Alertas de validade e de falta, o pior primeiro",
    aCarregar: "A carregar os alertas…",
    erroAoCarregar: "Não foi possível carregar os alertas",
    /**
     * As três frases de uma falta, e são **três** e não duas: um stock negativo
     * não é "sem stock", é um ledger a dizer que saiu mais do que entrou. Ficam
     * juntas porque são uma escolha de três, e separar uma delas para o
     * `numeros` perdia isso de vista.
     */
    stockNegativo: "stock negativo",
    semStock: "sem stock",
    abaixoDoMinimo: "abaixo do mínimo",
    minimoAbreviado: "mín.",
    /**
     * O limiar debaixo da frase da validade, em partes nomeadas: o número vai
     * num `<span data-numeric>` para ser mono (DESIGN.md §2), logo a frase tem
     * um elemento no meio e não cabe numa string. É a mesma razão de um
     * `<strong>`, com outro motivo.
     */
    avisoAInicio: "aviso a",
    avisoAFim: "dias",
    /** Na coluna "Onde": o cabeçalho já diz "onde", logo não se repete "lojas". */
    todasAsLojas: "todas",
    deitarFora: "Deitei fora",
    /**
     * O nome acessível do botão. Numa tabela de dez linhas, dez botões chamados
     * "Deitei fora" são dez botões indistinguíveis para quem navega por lista de
     * controlos. Duas funções e não uma com o lote vazio: um alerta de falta não
     * tem lote, e uma frase com um buraco no meio não se traduz.
     */
    deitarForaAccao: (artigo: string, quantidade: string) =>
      `Deitei fora — ${artigo}, ${quantidade}`,
    deitarForaAccaoComLote: (artigo: string, lote: string, quantidade: string) =>
      `Deitei fora — ${artigo}, lote ${lote}, ${quantidade}`,
    /** A pergunta do segundo toque, com a quantidade em mono pelo meio. */
    deitarForaInicio: "Deitar fora",
    doLote: (lote: string) => ` do lote ${lote}`,
    deitarForaPorque: " — porquê?",
    cancelar: "Cancelar",
    deitadoForaHoje: (hora: string) => `Deitado fora — hoje (desde as ${hora})`,
    deitadoForaSemana: "Deitado fora — últimos 7 dias",
    verSemana: "ver os últimos 7 dias",
    verHoje: "ver só hoje",
    erroDoDesperdicio: "Não foi possível carregar o desperdício",
    vazioDesperdicioTitulo: "Nada deitado fora neste período",
    vazioDesperdicioHoje:
      "O dia de negócio começou e ainda não se registou nenhuma quebra. As de antes dessa hora contam no dia anterior.",
    vazioDesperdicioSemana: "Nenhuma quebra registada nos últimos sete dias.",
    verEmRisco: "Ver o que está em risco",
    vazioTitulo: "Nada em risco agora",
    vazioComFiltroTitulo: "Nada em risco com este filtro",
    vazioCorpo:
      "Nenhum lote dentro do horizonte de validade e nenhum artigo abaixo do mínimo. Os alertas aparecem aqui sozinhos.",
    vazioComFiltroCorpo:
      "Os outros dois contadores do topo podem ter linhas. Toque para ver tudo.",
    verTudo: "Ver tudo",
    /** O pé da lista cita as duas palavras do `validade`: mudam juntas. */
    rodape: (quantos: number) => {
      const contagem = quantos === 1 ? "1 alerta" : `${String(quantos)} alertas`;
      return `${contagem}, o pior primeiro. «Consumir até» é limite legal; «perde qualidade» é durabilidade mínima.`;
    },
    /** O que se diz depois de registar, para quem não está a olhar para o ecrã. */
    registado: (quantidade: string, artigo: string, motivo: string) =>
      `Deitado fora: ${quantidade} de ${artigo} — ${motivo}.`,
    deitadoForaNaSemana: "Deitado fora nos últimos 7 dias:",
    verOQueFoi: "Ver o que foi, e a que horas",
  },

  desperdicio: {
    tabela: "Movimentos de desperdício, do mais recente para o mais antigo",
    aCarregar: "A carregar o desperdício…",
    /** O título da secção e o botão dizem o mesmo, de propósito: é a mesma acção. */
    registar: "Registar desperdício",
    semLocalizacao:
      "Este artigo não tem nenhuma localização com movimentos, por isso não há de onde registar desperdício.",
    escrevaAQuantidade: (unidade: string) =>
      `Escreva a quantidade em ${unidade}, maior do que zero.`,
    escolhaOMotivo: "Escolha o motivo do desperdício.",
    localizacaoPrefixo: "Localização:",
    localizacao: "Localização",
    quantidadeEm: (unidade: string) => `Quantidade em ${unidade}`,
    exemploDeQuantidade: (unidade: string) => `por exemplo, 2000 ${unidade}`,
    /**
     * As duas unidades na mesma frase: a de apresentação e a base. Converter
     * unidades no cliente é a fonte nº 1 de bugs de stock (`inventory-domain`
     * §2), por isso o ecrã diz qual é em vez de multiplicar às escondidas.
     */
    unidadeDeRegisto: (mostrada: string, base: string) =>
      `A lista mostra este artigo em ${mostrada}; o ledger guarda-o em ${base}, e é nesta unidade que se regista.`,
    motivo: "Motivo",
    escolhaOMotivoPista: "Escolha o motivo",
    registado: "Desperdício registado.",
    registadoNoLote: (lote: string) => `Desperdício registado no lote ${lote}.`,
  },

  artigo: {
    voltar: "Stock",
    aCarregar: "A carregar o artigo…",
    minimoERegisto: (minimo: string, unidade: string) =>
      `mínimo ${minimo}, registado ao ${unidade}`,
    negativoTitulo: "Ficou negativo",
    negativoCorpo:
      "O stock registado está abaixo de zero. Costuma ser uma entrada que falta registar, ou uma saída lançada a mais. Corrige-se com um movimento novo — nada se apaga.",
    erroAoCarregar: "Não foi possível carregar o artigo",
    tentarOutraVez: "Tentar outra vez",
    semArtigoTitulo: "Este artigo não está no stock",
    semArtigoCorpo:
      "Ou nunca teve movimentos, ou o endereço aponta para um artigo de outro estabelecimento.",
  },

  movimentos: {
    titulo: "Movimentos",
    tabela: "Movimentos do artigo, do mais recente para o mais antigo",
    aCarregar: "A carregar os movimentos…",
    erroAoCarregar: "Não foi possível carregar os movimentos",
    vazioTitulo: "Sem movimentos",
    vazioCorpo: "Este artigo ainda não tem entradas, consumos nem desperdício registados.",
    rodape: (quantos: number, total: number) =>
      `Os ${String(quantos)} movimentos mais recentes, de ${String(total)}.`,
  },

  contagem: {
    titulo: "Contar — o que está na prateleira é o que o sistema diz?",
    /**
     * Os dois algarismos de "3 de 9 contados" vão em mono, logo a frase tem
     * elementos pelo meio e parte-se em palavras nomeadas. O mesmo `de` serve as
     * três contagens do módulo — o progresso, o fecho e a última contagem
     * fechada —, que é o que impede três traduções diferentes da mesma palavra.
     */
    de: "de",
    contados: "contados",
    linhas: "linhas",
    tudoContado: "tudo contado",
    zonaPrefixo: "zona:",
    zonas: "Zonas da contagem",
    todasAsZonas: "Todas",
    todasAsZonasPista: "Ver as linhas de todas as zonas, na ordem do percurso",
    zonaCegaPista: (zona: string) => `${zona} — contagem cega: o esperado não aparece`,
    zonaAbertaPista: (zona: string) => `${zona} — o esperado aparece ao lado do campo`,
    cegaSrOnly: "(contagem cega)",
    aCarregarContagem: "A carregar a contagem…",
    aCarregarLinhas: "A carregar as linhas…",
    escrevaQuantos: (unidade: string) => `Escreva quantos ${unidade} estão na prateleira.`,
    /**
     * A mesma frase em três comprimentos, porque a coluna tem 7rem em desktop e
     * a 360px não há cabeçalho nenhum a dizer "Esperado": a longa fica para o
     * telemóvel, a curta para a coluna, e o `title` leva a longa nas duas.
     */
    cegaPista: "Contagem cega: o esperado só aparece ao fechar",
    cegaLonga: "contagem cega: o esperado só aparece ao fechar",
    cega: "cega",
    esperadoPrefixo: "esperado",
    confere: "confere",
    aGuardar: "a guardar…",
    semContagemTitulo: "Nenhuma contagem a decorrer",
    /**
     * As quatro zonas são um **exemplo** do percurso físico, não dados: por isso
     * traduzem-se, como os `placeholder` de exemplo do `accounts`.
     */
    semContagemCorpo:
      "Uma contagem percorre uma loja por zonas, na ordem física: Balcão, Frigorífico, Arca, Armazém. Escolha onde quer contar.",
    ondeContar: "Onde quer contar",
    escolhaALoja: "Escolha a loja",
    aComecar: "A começar…",
    comecar: "Começar contagem",
    ultimaFechada: "Última contagem fechada",
    dataEHora: (data: string, hora: string) => `${data} às ${hora}`,
    /** A justificação é texto do tenant: vai entre aspas e não se traduz. */
    justificacao: (motivo: string) => ` · «${motivo}»`,
    verAsDiferencas: "Ver as diferenças",
    erroDaContagem: "Não foi possível carregar a contagem",
    erroDasLinhas: "Não foi possível carregar as linhas",
    zonaVaziaTitulo: "Esta zona não tem nada para contar",
    zonaVaziaCorpo:
      "Nenhum artigo desta contagem está nesta zona. As outras zonas continuam no topo.",
    verTodasAsZonas: "Ver todas as zonas",
    /** O papel vem do servidor (`closing_role`) e entra por interpolação. */
    soOPapelFecha: (papel: string) =>
      `só o ${papel} fecha a contagem, e as diferenças aparecem antes`,
  },

  fecho: {
    fechar: "Fechar contagem",
    fechada: "Contagem fechada",
    voltar: "Contar",
    semContagemTitulo: "Não há contagem para fechar",
    semContagemCorpo:
      "Este endereço aponta para uma contagem que já não existe, ou não há nenhuma a decorrer.",
    irParaContar: "Ir para Contar",
    aCarregar: "A carregar as diferenças…",
    erroAoCalcular: "Não foi possível calcular as diferenças",
    fechadaTitulo: "Fechada, e o ajuste está no ledger",
    fechadaCorpo:
      "Cada diferença gerou um movimento de ajuste com o autor e a justificação. Nada foi reescrito: para corrigir, conta-se outra vez.",
    justificacao: (motivo: string) => ` Justificação: «${motivo}».`,
    voltarAContar: "Voltar a Contar",
    totalEmFalta: "em falta",
    totalAMais: "a mais",
    totalLiquido: "diferença líquida",
    linhasContadas: "linhas contadas",
    porContarSemAjuste: ". As que ficaram por contar não geram ajuste.",
    /** O número de linhas por contar vai em mono: daí as duas partes. */
    ficam: "Ficam",
    linhasPorContar: "linhas por contar",
    porContarCorpo:
      "O stock delas não muda: sem contagem não há diferença, e sem diferença não há ajuste. Pode fechar assim.",
    semDiferencas: "Nenhuma diferença até agora. O que está na prateleira é o que o sistema diz.",
    diferencasTitulo: "Diferenças, a maior primeiro",
    contadoPrefixo: "contado",
    esperadoPrefixo: "esperado",
    motivoObrigatorio: (valor: string) =>
      `As diferenças somam mais de ${valor} — escreva o que aconteceu.`,
    oQueAconteceu: "O que aconteceu",
    opcional: " (opcional)",
    exemploDeMotivo: "por exemplo, faltou lançar a transferência da manhã…",
    ajudaObrigatoria: (valor: string) =>
      `Obrigatório: as diferenças somam mais de ${valor}. Vai com o ajuste para o histórico.`,
    ajudaOpcional: (valor: string) =>
      `Fica no histórico ao lado do ajuste. Obrigatório acima de ${valor} de diferenças.`,
    aFechar: "A fechar…",
    soOPapelFecha: (papel: string) => `só o ${papel} fecha a contagem`,
  },
};
