/**
 * A copy do módulo `purchasing`, em **pt-PT**. É a fonte; o inglês é anotado com
 * `typeof PT` e não compila se divergir (ADR 0019, decisão 3).
 *
 * Por feature e não num ficheiro central, pela razão da ADR 0013 (decisão 5): a
 * copy vive ao lado do `vocabulario.ts` da feature que a usa.
 *
 * ## O que **não** vem para cá
 *
 * As mensagens de Zod do `schemas.ts` deste módulo validam a **forma da
 * resposta** do servidor (`"decimal inválido"`, `"hora inválida"`,
 * `"NIF inválido"`): ninguém as lê — um contrato partido vira `ErroDeContrato` e
 * o ecrã mostra a frase do `erros.ts` —, e por isso estão declaradas no
 * `NAO_E_COPY` do `scripts/check-textos.mjs` em vez de traduzidas. As do
 * `formularios` abaixo são as outras: o que aparece debaixo de um input quando
 * alguém submete.
 *
 * ## As siglas dos documentos não estão aqui
 *
 * `FT`, `FR`, `FS` e `NC` são o que vem impresso no papel e são a chave do
 * contrato: ficam no `vocabulario.ts`. A única que é copy é a da guia — diz-se
 * "guia" em voz alta e não "GR" —, e essa está no `vocabulario` abaixo.
 */
export const PT = {
  /**
   * O que aparece em mais do que um ficheiro, definido **uma vez**.
   *
   * Não é economia de linhas: a lista, o cabeçalho e a tabela têm de chamar a
   * mesma coisa à fatura manuscrita da frutaria, e três chaves com a mesma
   * palavra divergem na primeira tradução feita só numa delas.
   */
  comuns: {
    receber: "Receber",
    fotografarFatura: "Fotografar fatura",
    verAsRececoes: "Ver as receções",
    aGuardar: "A guardar…",
    semNumero: "sem número",
    outroAdquirente: "outro adquirente",
    /**
     * A preposição entre uma data e uma hora, em três sítios. É uma parte
     * nomeada e não uma frase porque as duas metades são `data-numeric`: juntá-las
     * numa string tirava o mono aos algarismos.
     */
    as: "às",
    /**
     * A mesma junção, **em função**, para um `title` — que não leva marcação e
     * por isso não parte as duas metades. As duas formas existem de propósito:
     * fundi-las obrigava a escolher entre perder o mono e perder o `title`.
     */
    dataEHora: (data: string, hora: string) => `${data} às ${hora}`,
    /** O `title` da sonda do adquirente: os dois NIF por extenso. */
    nifDoDocumento: (
      adquirente: string,
      nifDoAdquirente: string,
      empresa: string,
      nifDaEmpresa: string,
    ) =>
      `Documento emitido a ${adquirente}, NIF ${nifDoAdquirente}. A empresa é ${empresa}, NIF ${nifDaEmpresa}.`,
    entrouPorGuia:
      "Entrou por guia de remessa, sem preços. A fatura do fornecedor vem a fim de mês e reconcilia as entregas do período.",
    linhasPorRever: (quantas: number) =>
      quantas === 1 ? "1 linha por rever" : `${String(quantas)} linhas por rever`,
  },

  receber: {
    titulo: "Receber — o que chegou, e está certo?",
    erroAoCarregar: "Não foi possível carregar as receções",
    contagem: (quantas: number) =>
      quantas === 1 ? "1 receção" : `${String(quantas)} receções`,
    vazioTitulo: "Ainda não entrou mercadoria",
    vazioCorpo:
      "Cada entrada começa num documento do fornecedor — uma fatura, uma fatura simplificada do cash & carry, ou uma guia de remessa. Nada entra no stock sem alguém confirmar as linhas.",
    filtroVazioTitulo: "Nenhuma receção neste filtro",
    filtroVazioRevisao:
      "Não há documentos à espera de revisão. Tudo o que chegou já deu entrada no stock.",
    filtroVazioHoje: "Nenhuma receção foi confirmada no dia de negócio de hoje.",
    verTudo: "Ver tudo",
    /**
     * O pé da lista: quantos, de quantos, a ordem e a regra do produto.
     *
     * Uma função e não três chaves porque a frase **é** uma: muda de forma no
     * singular, e o "de N" só aparece quando o servidor truncou a página.
     */
    rodapeDaLista: (quantos: number, total: number | null) => {
      const contagem = quantos === 1 ? "1 documento" : `${String(quantos)} documentos`;
      const de = total === null ? "" : ` de ${String(total)}`;
      return `${contagem}${de}, o que precisa de revisão primeiro. Nenhum entra no stock sem ser confirmado.`;
    },
  },

  fotografar: {
    semCamaraTitulo: "Neste ecrã ainda não há câmara",
    semCamaraCorpo:
      "No telemóvel este botão abre a câmara e a fotografia fica anexada ao documento. Aqui não há câmara nem leitura do documento: a receção que está à espera de revisão foi preenchida à mão, para se poder percorrer a revisão de ponta a ponta — que é a parte que decide se o stock muda.",
    porOndeEntra: "Por onde é que a mercadoria entra",
    /**
     * Os três caminhos por onde a mercadoria entra, cada um em **duas partes**
     * nomeadas: o nome do documento vai num `<strong>` e o resto da frase
     * continua fora dele. Juntar cada par numa string só perdia o negrito, e
     * pôr HTML numa string pedia um `dangerouslySetInnerHTML`, que o
     * `eslint.config.js` proíbe.
     */
    faturaEnfase: "Fatura ou fatura simplificada",
    faturaFim:
      ", de uma ida ao cash & carry: sem encomenda, sem guia, a mercadoria vem na carrinha e o documento vem na mão.",
    guiaEnfase: "Guia de remessa",
    guiaFim:
      ", do distribuidor: a mercadoria entra primeiro e a fatura vem a fim de mês, a reconciliar várias entregas.",
    semDocumentoEnfase: "Sem documento nenhum",
    semDocumentoFim:
      ", ou com um escrito à mão no mercado: também tem de dar entrada, e o documento aparece depois.",
    aProcurar: "A procurar receções por revisar…",
    semRevisaoTitulo: "Não há nada à espera de revisão",
    semRevisaoCorpo:
      "Quando um documento novo entrar, aparece na lista a precisar de revisão — e o stock só muda depois de alguém confirmar as linhas.",
    rever: (fornecedor: string) => `Rever ${fornecedor}`,
  },

  rececao: {
    aCarregar: "A carregar a receção…",
    erroAoCarregar: "Não foi possível carregar esta receção",
    naoExisteTitulo: "Esta receção não existe",
    naoExisteCorpo:
      "O endereço aponta para um documento que já não está neste estabelecimento.",
    noStockTitulo: "A mercadoria está no stock",
    noStockCorpo:
      "Cada linha confirmada gerou um movimento de entrada com o lote, a validade e o autor. Nada se reescreve: para corrigir, regista-se um movimento novo.",
    verNoStock: "Ver no stock",
    linhasDoDocumento: "Linhas do documento",
    erroDasLinhas: "Não foi possível carregar as linhas",
    semLinhasTitulo: "Este documento não tem linhas",
    semLinhasCorpo:
      "Sem linhas não há nada para rever nem nada para dar entrada. Costuma ser um documento fotografado ao contrário.",
    /** O que se anuncia a quem não está a olhar para o ecrã, por `role="status"`. */
    linhaRevista: (nome: string) => `Linha revista: ${nome}.`,
    linhaDeFora: (nome: string) => `${nome} fica fora desta entrada — não gera movimento.`,
    linhaVoltaARever: (nome: string) => `${nome} volta a precisar de revisão.`,
    nadaEntraAinda: "Nada entra no stock ainda",
    oQueEntra: "O que entra no stock quando confirmar",
    nenhumaRevista:
      "Nenhuma linha está revista. Confirme as linhas acima — o lote e a validade estão na embalagem, não no documento.",
    /**
     * Uma linha do resumo do que entra. A quantidade fica fora da frase porque
     * é `data-numeric`; o nome do artigo é anulável no contrato e um artigo sem
     * nome mostra o mesmo vazio que mostrava antes de a frase vir para cá.
     */
    entraNoStock: (artigo: string | null, local: string) => `de ${artigo ?? ""} em ${local}`,
    linhasDeFora: (quantas: number) =>
      quantas === 1 ? "1 linha fica de fora" : `${String(quantas)} linhas ficam de fora`,
    linhasDeForaCorpo:
      "Sem revisão não há movimento, logo essa mercadoria não aparece no stock. Pode confirmar assim e tratar dela depois — ou rever as linhas primeiro.",
    aDarEntrada: "A dar entrada…",
    confirmarEDarEntrada: "Confirmar e dar entrada",
    esteToqueCria:
      "É este toque que cria os movimentos de entrada. Até aqui, o stock deste estabelecimento é o mesmo que era antes de a mercadoria chegar.",
    confirmada: "Receção confirmada: a mercadoria entrou no stock.",
  },

  numeros: {
    porReverTitulo:
      "Documentos que ainda não deram entrada no stock — nada entra sem revisão",
    confirmadasHoje: "confirmadas hoje",
    desdeAs: (hora: string) => `desde as ${hora}`,
    /**
     * A frase da hora do dia de negócio, **uma função** porque a hora vem do
     * servidor. A assinatura faz parte do contrato `typeof PT`, logo mudá-la
     * numa língua e não na outra não compila.
     */
    diaDeNegocio: (hora: string) =>
      `O dia de negócio deste estabelecimento começa às ${hora} — o que foi confirmado antes dessa hora conta no dia anterior`,
    aCarregar: "A carregar os números…",
    erroTitulo: "Não foi possível contar as receções",
    erroCorpo:
      "A lista abaixo continua a funcionar. Os dois números voltam à segunda tentativa.",
  },

  tabela: {
    colunas: {
      fornecedor: "Fornecedor",
      tipo: "Tipo",
      documento: "Documento",
      chegou: "Chegou",
      total: "Total",
      linhas: "Linhas",
      estado: "Estado",
      onde: "Onde",
    },
    rotulo: "Receções, as que precisam de revisão primeiro",
    aCarregar: "A carregar as receções…",
    emitidaA: (adquirente: string) => `emitida a ${adquirente}`,
    semValor: "sem valor",
    /** A sub-linha da coluna das linhas: "2 por rever" de 5 é outra coisa que "2" de 2. */
    porRever: (quantas: number) => `${String(quantas)} por rever`,
    semFatura: "sem fatura",
  },

  badges: {
    precisaDeRevisao: "precisa de revisão",
    quantasLinhas: (quantas: number) =>
      quantas === 1 ? "1 linha" : `${String(quantas)} linhas`,
    entrouSemFatura: "entrou sem fatura",
    nifDiferente: "NIF diferente do da empresa",
  },

  cabecalho: {
    /**
     * A sonda do adquirente, em duas funções e não numa: os dois NIF vão em
     * `data-numeric` e ficam entre elas.
     */
    emitidaA: (adquirente: string) => `Emitida a ${adquirente} · NIF`,
    aEmpresaE: (empresa: string) => `A empresa é ${empresa} · NIF`,
    totaisNaoBatemTitulo: "Os totais não batem",
    /** Três partes nomeadas: os dois valores no meio são `data-numeric`. */
    totaisNaoBatemInicio: "O total impresso é",
    totaisNaoBatemMeio: "e a soma das linhas dá",
    totaisNaoBatemFim:
      ". Costuma ser um desconto de rodapé ou portes que ficaram de fora. Pode confirmar assim.",
    recebida: "recebida",
    confirmada: "confirmada",
    por: (autor: string) => `por ${autor}`,
    /** Abre a lista de lojas onde o documento entrou: "Em Cozinha · Bar". */
    em: "Em",
    notaDeCredito: "Uma nota de crédito credita valor; não dá entrada de mercadoria.",
    guiaSemPrecos:
      "Esta guia não traz preços — não há totais para conferir. O valor chega com a fatura.",
    baseAIva: "base a IVA",
    total: "total",
    taxasDaLinha: "as taxas são as de cada linha da fatura — não são deduzidas do artigo",
  },

  linhas: {
    colunas: {
      artigo: "Artigo",
      recebido: "Recebido",
      stock: "Stock",
      valor: "Valor",
      lote: "Lote",
      validade: "Validade",
      estado: "Estado",
      accao: "Acção",
    },
    tabela: "Linhas do documento, na ordem em que estão impressas nele",
    aCarregar: "A carregar as linhas da fatura…",
    /** O rótulo do campo da validade quando a embalagem diz qual das duas é. */
    validadeCom: (tipo: string) => `Validade (${tipo})`,
    lotePlaceholder: "como está na embalagem",
    confirmarLinha: "Confirmar linha",
    semArtigo: "sem artigo no catálogo",
    semArtigoCorpo:
      "A fatura traz isto e o catálogo não tem. Sem artigo não há conversão para a unidade de stock, por isso a linha não entra — fica fora desta entrada, ou cria-se o artigo no catálogo primeiro.",
    deixarFora: "Deixar fora desta entrada",
    voltarARever: "Voltar a rever",
    ficaDeFora: "Fica fora desta entrada — não gera movimento.",
    /** Abreviatura de "faturado", na sub-linha de uma célula de uma linha de 44px. */
    faturadoCurto: "fat.",
    pesoVariavelNota: "peso variável",
    semConversao: "sem conversão",
    naoEStock: "não é stock",
    jaNoStock: "já no stock",
    semPreco: "sem preço",
    ivaDaLinha: (taxa: string) => `IVA ${taxa} — a taxa que vem na linha da fatura`,
    rever: "Rever",
    ver: "Ver",
    /**
     * O nome acessível do botão, numa função por verbo e não com o verbo
     * interpolado: numa frase inglesa o verbo não fica onde está na portuguesa.
     */
    reverALinha: (descricao: string) => `Rever a linha ${descricao}`,
    verALinha: (descricao: string) => `Ver a linha ${descricao}`,
    /**
     * A conversão, em partes nomeadas porque as duas quantidades vão em
     * `data-numeric`: "1 caixa 12×1 L **dão** 12 000 ml **no stock, que é a
     * unidade em que o ledger guarda.**"
     */
    conversaoMeio: "dão",
    conversaoFim: "no stock, que é a unidade em que o ledger guarda.",
    guiaSemPrecos: "Esta guia não traz preços.",
    aFaturaCobra: "A fatura cobra",
    /** A preposição entre a quantidade e o preço: "2 caixas a 44,50 €/caixa". */
    aoPreco: "a",
    comIvaDe: ", com IVA de",
    taxaDaLinha: " — a taxa que vem na linha, não a do artigo",
    totalDaLinha: ". Total da linha:",
    /**
     * A receção parcial tem **duas** formas da mesma frase, e é de propósito: no
     * dossier as quantidades vão em `data-numeric` (três partes nomeadas) e no
     * `title` da célula não há marcação (uma função). Fundi-las obrigava a
     * perder o mono ou o `title`.
     */
    faturadosInicio: "Faturados",
    faturadosMeio: ", entraram",
    faturadosFim: " — a fatura cobra os que faturou.",
    faturados: (faturados: string, entraram: string) =>
      `Faturados ${faturados}, entraram ${entraram} — a fatura cobra os que faturou.`,
    /**
     * A variação contra as últimas compras, em partes pela mesma razão: "+21 %
     * acima das últimas compras (44,50 €/saco em março). O aviso aparece acima
     * de 15 p.p." — a percentagem, o preço e o limiar são todos `data-numeric`.
     */
    acima: "acima",
    abaixo: "abaixo",
    dasUltimasCompras: "das últimas compras",
    historicoEm: "em",
    oAvisoApareceAcimaDe: "O aviso aparece acima de",
    /**
     * As frases do dossier que se somam numa só linha de texto, e por isso
     * **acabam em espaço**: cada uma só aparece quando a linha a tem, e a que
     * vem depois encosta-se-lhe.
     */
    vasilhame: "Vasilhame: linha com valor que não é stock consumível. ",
    encargo: "Encargo: valor sem mercadoria. ",
    conservaSe: (como: string) => `Conserva-se ${como}. `,
    pesoVariavel: "Peso variável: pesado peça a peça na fatura. ",
    aValidadeDestaLinha: (tipo: string) => `A validade desta linha é «${tipo}». `,
    entraEm: (local: string) => `Entra em ${local}.`,
    revistaPor: (autor: string) => `Revista por ${autor}`,
    semMovimentoAinda: ". O movimento só existe quando o documento for confirmado.",
    jaEstaNoStock: ". Já está no stock.",
  },

  temperatura: {
    rotulo: "Temperatura à entrega (°C)",
    guardar: "Guardar",
    registada: "registada",
  },

  /**
   * O vocabulário do domínio: os enums do contrato em palavras.
   *
   * Em chaves planas, como no `accounts`: os `Map` sobre as uniões geradas ficam
   * no `vocabulario.ts`, que é onde um valor novo no contrato tem de deixar de
   * compilar. O catálogo guarda palavras.
   */
  vocabulario: {
    documentoFatura: "Fatura",
    documentoFaturaRecibo: "Fatura-recibo",
    documentoFaturaSimplificada: "Fatura simplificada",
    documentoNotaDeCredito: "Nota de crédito",
    documentoGuiaDeRemessa: "Guia de remessa",
    /** A única sigla que é copy: diz-se "guia" em voz alta, e não "GR". */
    siglaDeGuia: "guia",
    /**
     * A mesma palavra nos dois graus — o documento e a linha — e no contador do
     * topo, porque é a mesma coisa: ainda não passou por ninguém. Separá-la em
     * três chaves era deixar a lista e o detalhe divergirem na primeira correção
     * feita só num deles.
     */
    porRever: "por rever",
    noStock: "no stock",
    linhaRevista: "revista",
    linhaDeFora: "de fora",
    congelado: "congelado",
    refrigerado: "refrigerado",
    ambiente: "ambiente",
    mercadoria: "mercadoria",
    vasilhame: "vasilhame",
    encargo: "encargo",
    /**
     * Os dois rótulos que a lei distingue. O "consumir até" é o mesmo na forma
     * por extenso e na curta — é curto de nascença —, e o outro tem as duas: a
     * legal, onde a validade é escrita, e a de 12 caracteres, que é a que cabe
     * numa célula de 44px.
     */
    consumirAte: "consumir até",
    consumirDePreferenciaAntesDe: "consumir de preferência antes de",
    melhorAntes: "melhor antes",
  },

  /**
   * O plural das unidades de compra, **em singular e plural**, para a frase da
   * conversão não ler "2 bloco 2,5 kg".
   *
   * O singular vem daqui e não de um literal no `vocabulario.ts` porque é a
   * **chave** com que se procura: o rótulo da embalagem é texto que o fornecedor
   * escreveu na fatura, logo a palavra procurada pertence à língua do catálogo
   * tanto como a resposta.
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

  /** As mensagens que aparecem debaixo de um campo, quando alguém submete. */
  formularios: {
    escrevaOLote: "Escreva o lote que está na embalagem, como está impresso.",
    escrevaAValidade: "Escreva a validade da embalagem.",
    escrevaOsGraus: "Escreva os graus, por exemplo -18 ou 4,5.",
  },
};
