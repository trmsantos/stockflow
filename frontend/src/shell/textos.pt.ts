/**
 * A copy do invólucro, em **pt-PT**. É a fonte: o inglês é anotado com
 * `typeof PT` e não compila se divergir (ADR 0019, decisão 3).
 *
 * ## Porque é que os rótulos das rotas estão aqui
 *
 * O `rotulo`, o `grupo` e a `pergunta` de cada rota são **copy do produto** e é
 * aqui que se traduzem. Vinham do servidor até 2026-10-07 — o `grupo` resolvido
 * e obrigatório, o que fazia a primeira gravação do menu congelá-lo na linha do
 * tenant (ADR 0019, decisão 5) — e agora o contrato manda `null` e o cliente
 * resolve contra o registo, que lê daqui.
 *
 * O que o **tenant** escrever continua a não se traduzir nunca: é texto dele,
 * numa língua só, e a distinção lê-se no `montarMenu` (`entrada.rotulo ??
 * registo.rotulo`).
 *
 * ## Sem `as const`
 *
 * Os valores querem-se `string` e não literais: com `as const`, o `typeof PT` do
 * inglês exigiria **as mesmas palavras portuguesas**, que é o oposto do que se
 * quer. As funções de interpolação é que fazem parte do contrato, e essas são
 * tipadas pela assinatura.
 */
export const PT = {
  /** O nome do produto. Não se traduz, e está aqui para não ser um literal. */
  marca: "StockFlow",

  /** O atalho de teclado para quem navega sem rato. */
  saltarParaConteudo: "Saltar para o conteúdo",

  cabecalho: {
    /** A faixa de tenant: a palavra inteira a partir de `sm`. */
    demonstracao: "Estabelecimento de demonstração",
    /** E a curta num telemóvel, onde a barra tem 56px e o nome do ecrã. */
    demonstracaoCurta: "Demonstração",
    /** O badge de **ambiente**, que não existe no bundle de produção. */
    dadosDeDemonstracao: "dados de demonstração",
  },

  gaveta: {
    abrir: "Abrir o menu",
    fechar: "Fechar o menu",
    descricao: "Escolha um ecrã do StockFlow.",
  },

  navegacao: {
    principal: "Navegação principal",
    expandir: "Expandir o menu",
    recolher: "Recolher o menu",
    semItens: "Este estabelecimento não tem itens de menu configurados.",
    irParaInicio: "Ir para o início",
  },

  rodape: {
    estabelecimento: "Estabelecimento",
    /**
     * O sufixo que marca o estabelecimento de demonstração no seletor, **só para
     * quem ouve a página**: o ícone é decorativo e o papel sozinho não distingue
     * um demo de uma casa a sério com o mesmo nome. A cor nunca comunica sozinha
     * (DESIGN.md §2).
     */
    sufixoDeDemonstracao: " (demonstração)",
    /**
     * O nome acessível do seletor quando a sidebar está recolhida: aí o rótulo
     * é `sr-only` e o botão é um ícone, logo quem ouve não tem como saber qual.
     */
    estabelecimentoRecolhido: (nome: string) => `Estabelecimento: ${nome}`,
    trocar: "Trocar de estabelecimento",
    definicoes: "Definições",
    terminarSessao: "Terminar sessão",
    /** Com o email, quando ele é sabido: num `title`, diz de que conta se sai. */
    terminarSessaoDe: (email: string) => `Terminar sessão (${email})`,
    aSair: "A sair…",
  },

  estados: {
    aCarregar: "A carregar…",
    erroTitulo: "Não foi possível abrir este ecrã.",
    erroGenerico: "Erro inesperado. Verifique a ligação e tente outra vez.",
    tentarOutraVez: "Tentar outra vez",
    naoEncontradoTitulo: "Este ecrã não existe",
    naoEncontradoCorpo: "O endereço que abriu não corresponde a nenhum ecrã do StockFlow.",
    voltarAoInicio: "Voltar ao início",
  },

  publico: {
    tagline: "Gestão de stock, validades e compras para restauração.",
    erroTitulo: "Não foi possível continuar",
    erroCorpo: "Verifique a ligação e tente outra vez.",
  },

  /**
   * Os nomes dos grupos do menu. **Três e não quatro** desde que as definições
   * saíram da sidebar: o grupo "Equipa" desapareceu com elas (ADR 0019).
   *
   * "Equipa" e não "Contas" era a regra que o backend tinha escrito, e vale
   * guardá-la: o nome de um grupo é copy de produto e não o nome do módulo — é o
   * que a pessoa vai fazer ali.
   */
  grupos: {
    painel: "Painel",
    inventario: "Inventário",
    compras: "Compras",
  },

  /**
   * As sete rotas de operação. A `pergunta` é a do DESIGN.md §1 — o que o ecrã
   * responde — e aparece na gaveta e nos títulos só-para-áudio.
   */
  rotas: {
    inicio: { rotulo: "Início", pergunta: "O que é que tenho de fazer hoje?" },
    painel: {
      rotulo: "Painel",
      pergunta: "Quanto entrou, quanto saiu, e como fechou o mês?",
    },
    alertas: {
      rotulo: "Alertas",
      pergunta: "O que expira? O que falta? Quanto deitei fora?",
    },
    assistente: {
      rotulo: "Assistente",
      pergunta: "Quanto tenho de farinha? O que vence esta semana?",
    },
    stock: { rotulo: "Stock", pergunta: "O que é que eu tenho, e quanto?" },
    contar: {
      rotulo: "Contar",
      pergunta: "O que está na prateleira é o que o sistema diz?",
    },
    receber: { rotulo: "Receber", pergunta: "O que chegou, e está certo?" },
  },
};
