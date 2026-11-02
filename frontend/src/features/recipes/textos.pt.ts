/**
 * A copy do módulo `recipes`, em **pt-PT**. É a fonte; o inglês é anotado com
 * `typeof PT` e não compila se divergir (ADR 0019, decisão 3).
 *
 * ## A palavra que este ficheiro existe para fixar
 *
 * **"Custo de ingredientes", nunca "custo do prato"** (ADR 0035, decisão 9). É o
 * *food cost*, o número universal da restauração, e é contra ele que um dono
 * compara de cor os 25–30 % do preço de venda. Chamar-lhe "custo do prato" é
 * falso — numa pastelaria por um factor de **2 a 4**, porque num produto com 20
 * cêntimos de matéria a mão-de-obra é o custo dominante. No unitário a frase é
 * "ingredientes por pastel", pela mesma razão.
 *
 * Um catálogo é o sítio certo para esta regra viver: a palavra está escrita uma
 * vez, e um ecrã que a quisesse contrariar teria de inventar uma chave nova.
 */

export const PT = {
  accoes: {
    novaFicha: "Nova ficha",
    criarPrimeira: "Criar a primeira ficha",
    gravar: "Gravar a ficha",
    aGravar: "A gravar…",
    guardar: "Guardar alterações",
    editar: "Editar",
    cancelar: "Cancelar",
    acrescentar: "Acrescentar ingrediente",
    remover: (artigo: string) => `Remover ${artigo}`,
    removerLinha: "Remover esta linha",
    voltar: "Voltar às receitas",
    arquivar: "Arquivar",
    reactivar: "Reactivar",
    aArquivar: "A arquivar…",
    verFichaExistente: "Abrir a ficha que já existe",
    aCarregarLista: "A carregar as fichas técnicas…",
    aCarregarFicha: "A carregar a ficha técnica…",
  },

  lista: {
    titulo: "Receitas",
    tabela: "Fichas técnicas do estabelecimento",
    procurar: "Procurar ficha",
    procurarPista: "Nome ou código do acabado",
    estado: "Fichas a mostrar",
    activas: "Só as activas",
    todas: "Activas e arquivadas",
    erro: "Não foi possível carregar as fichas técnicas.",
    vazioTitulo: "Ainda não há nenhuma ficha técnica",
    vazioCorpo:
      "Uma ficha diz o que entra numa fornada. É dela que sai o custo de ingredientes de tudo o que esta casa produz.",
    semCorrespondenciaTitulo: "Nenhuma ficha corresponde",
    semCorrespondenciaCorpo:
      "A procura é pelo nome ou pelo código do acabado. As fichas arquivadas só aparecem com o filtro em «activas e arquivadas».",
    limparFiltros: "Limpar os filtros",
    /** Só para áudio: a contagem muda a cada tecla e quem ouve tem de a saber. */
    contagem: (n: number) => (n === 1 ? "1 ficha técnica" : `${String(n)} fichas técnicas`),
    /**
     * O rodapé da tabela: a regra de ordenação e, quando a lista está truncada,
     * o total. Fica no fim porque quem chega ao fundo é quem precisa de saber
     * porque é que a ordem é aquela.
     */
    rodape: (mostradas: number, total: number | null) =>
      total === null
        ? `${String(mostradas)} fichas, por ordem alfabética do acabado e com as arquivadas no fim.`
        : `${String(mostradas)} de ${String(total)} fichas. Por ordem alfabética do acabado, com as arquivadas no fim.`,
  },

  colunas: {
    acabado: "Acabado",
    fornada: "Fornada",
    ingredientes: "Ingredientes",
    custoDaFornada: "Ingredientes/fornada",
    custoUnitario: "Ingredientes por unidade",
    certeza: "Certeza",
    ingrediente: "Ingrediente",
    porFornada: "Por fornada",
    saiDoStock: "Sai do stock",
    custoDoIngrediente: "Custo do artigo",
    custoDaLinha: "Custo da linha",
  },

  ficha: {
    tabela: "Ingredientes da ficha técnica",
    numeros: "Os números da ficha",
    naoExisteTitulo: "Esta ficha não existe",
    naoExisteCorpo:
      "O endereço não corresponde a nenhuma ficha deste estabelecimento. Pode ter sido apagada antes de haver fichas, ou ser de outra casa.",
    erro: "Não foi possível carregar esta ficha técnica.",
    arquivada: "Arquivada",
    arquivadaNota:
      "Esta ficha está arquivada: continua a ler-se e não aparece na lista por omissão.",
    campoFornada: "Fornada",
    campoIngredientes: "Ingredientes",
    campoCustoDaFornada: "Ingredientes/fornada",
    campoCustoUnitario: (unidade: string) => `Ingredientes por ${unidade}`,
    /** A segunda linha do campo da fornada, quando a base e a apresentação diferem. */
    notaDaBase: (base: string) => `= ${base}`,
    artigoArquivado: "Artigo arquivado",
    /**
     * A explicação do rendimento, por baixo da tabela: é ela que explica a
     * coluna "sai do stock", e é onde o `yield_factor` vive — fora do caminho
     * principal, como a ADR 0035 (decisão 8) manda.
     */
    rendimentoNeutro: (factor: string) =>
      `Rendimento ${factor}: o que sai do stock é exactamente o que a ficha escreve.`,
    rendimento: (factor: string) =>
      `Rendimento ${factor}: a ficha escreve o que fica no produto, e do stock sai a quantidade a dividir por este factor.`,
  },

  custo: {
    conhecido: "Conhecido",
    estimado: "Estimado",
    desconhecido: "Desconhecido",
    /** O traço de "não sabemos". Nunca aparece onde a chave está **ausente**. */
    semValor: "—",
    rotulo: "Custo de ingredientes:",
    tudoComCusto: "Todos os ingredientes têm custo registado.",
    semNenhumCusto: "Nenhum ingrediente tem custo registado.",
    semCusto: (quantos: number, total: number) =>
      quantos === 1
        ? `1 dos ${String(total)} ingredientes não tem custo registado.`
        : `${String(quantos)} dos ${String(total)} ingredientes não têm custo registado.`,
  },

  formulario: {
    tituloNova: "Nova ficha técnica",
    tituloEditar: "Editar a ficha",
    acabado: "Acabado",
    acabadoAjuda: "O artigo que sai desta ficha. É a identidade dela e não se altera depois.",
    acabadoFixo: "O acabado não se altera: é a identidade da ficha.",
    escolherArtigo: "Escolher…",
    fornada: "Fornada",
    fornadaAjuda:
      "Quanto acabado sai de uma fornada. As quantidades dos ingredientes são as desta fornada — não as de uma unidade.",
    unidade: "Unidade",
    rendimento: "Rendimento",
    rendimentoAjuda:
      "Fica a 1 quase sempre: a perda do processo já está na fornada, e pô-la aqui outra vez conta-a duas vezes. Só muda quando o peso muda por si, como arroz cru a cozido.",
    ingredientes: "Ingredientes",
    ingredientesAjuda:
      "Não escreva a água nem o sal: um artigo sem custo puxa a ficha inteira para «estimado» e fica lá para sempre.",
    procurar: "Procurar artigo",
    procurarPista: "Filtra os artigos oferecidos",
    quantidade: "Quantidade",
    semArtigos: "Nenhum artigo do catálogo corresponde a esta procura.",
    tectoDoCatalogo: (quantos: number) =>
      `O catálogo tem mais artigos do que os ${String(quantos)} que cabem nesta lista. Use a procura para chegar aos outros.`,
    erroAcabado: "Escolha o artigo acabado.",
    erroFornada: "Escreva uma fornada maior do que zero.",
    erroRendimento: "Escreva um rendimento maior do que zero.",
    erroSemLinhas: "Uma ficha precisa de pelo menos um ingrediente.",
    erroArtigoDaLinha: "Escolha o artigo desta linha.",
    erroQuantidade: "Escreva uma quantidade maior do que zero.",
    erroRepetido: "Este artigo já está na ficha.",
    erroAoGravar: "Não foi possível gravar a ficha.",
    semPermissaoTitulo: "Escrever fichas é de quem gere",
    semPermissaoCorpo:
      "A ficha define o produto e o custo dele, e mudar uma quantidade muda o custo de tudo o que dali sair. Quem gere o estabelecimento escreve-a; a lista e a ficha lêem-se com qualquer papel.",
    jaExisteTitulo: "Este artigo já tem ficha técnica",
    jaExisteCorpo:
      "Cada artigo tem uma ficha só. A que já existe está aberta no botão abaixo — edite-a em vez de criar uma segunda.",
  },
};
