/**
 * Os dados das duas propostas de identidade visual, e o conteúdo que as duas
 * rotas mostram. **Um** ficheiro, porque o valor da comparação está em as duas
 * rotas mostrarem exactamente o mesmo conteúdo: se cada rota trouxesse a sua
 * lista de artigos, a diferença que se vê deixava de ser só a identidade.
 *
 * Nada aqui vem da API nem das fixtures. As fixtures são um plugin de `serve`
 * fora do `src/` e nada em `src/` as importa (ADR 0008, decisão 3); esta
 * página não é produto e não tem camada de dados — é uma maqueta estática.
 *
 * O domínio dos dados é o que sobrevive à mudança visual (ADR 0009): a ordem
 * "o pior primeiro", a distinção entre "consumir até" (limite legal) e
 * "consumir de preferência antes de" (qualidade), o estado vindo de um
 * veredicto e não de uma comparação feita no ecrã, e a unidade sempre visível.
 */

export type ChaveDeIdentidade = "a" | "b";

export interface FichaDeIdentidade {
  readonly chave: ChaveDeIdentidade;
  readonly nome: string;
  /** A app ou família de produtos, com nome. Sem isto não há decisão. */
  readonly referencia: string;
  /** O ecrã concreto dessa referência. */
  readonly ecra: string;
  /** Porque serve um dono de pastelaria a olhar para tabelas ao computador. */
  readonly razao: string;
  /** O que esta identidade recusa. É o par da razão. */
  readonly recusa: string;
  readonly tipografia: readonly (readonly [string, string])[];
  readonly forma: readonly (readonly [string, string])[];
  /** O efeito medido na densidade de uma tabela de ERP e no peso do cromado. */
  readonly consequencias: readonly string[];
  /** O que custa, se for esta a escolhida. */
  readonly custos: readonly string[];
}

export const FICHAS: Readonly<Record<ChaveDeIdentidade, FichaDeIdentidade>> = {
  a: {
    chave: "a",
    nome: "Caderno de Caixa",
    referencia: "Dashboard da Stripe",
    ecra: "a lista de Pagamentos: filetes de 1px, zero cartões, uma coluna de valores a correr pela direita",
    razao:
      "É a tabela financeira densa que um dono de negócio já lê todos os meses sem ninguém lhe ter explicado. A hierarquia está na tipografia e no alinhamento, não em caixas: trinta linhas de stock leem-se como uma página de livro de caixa, e o olho desce a coluna das quantidades sem atravessar uma única borda. O acento aparece duas vezes em todo o ecrã, por isso quando aparece quer dizer algo.",
    recusa:
      "Recusa o cartão como unidade de composição. Não há um cartão por número, nem uma grelha de três: há uma folha com filetes.",
    tipografia: [
      ["Família (UI e títulos)", "Source Sans 3 — humanista, desenhada para corpo pequeno"],
      ["Dados (quantidades, dinheiro)", "a mesma família, com algarismos tabulares — sem mono"],
      ["Pesos", "400 corpo · 500 rótulos e cabeçalhos de coluna · 600 títulos"],
      ["Escala", "12 · 13 · 14 · 16 · 18 · 22 · 28 · 36 · 48 px (célula da tabela a 13)"],
      ["Entrelinha", "1,45 no corpo · 1,2 nos títulos · tracking −0,01 a −0,02em nos grandes"],
    ],
    forma: [
      ["Raio", "3px de base (2 · 3 · 4) — quase recto, como um campo impresso"],
      ["Sombras", "nenhuma em painéis; uma só, discreta, no que flutua"],
      ["Separação", "filete de 1px em --color-border; nunca uma sombra a separar superfícies"],
      ["Grelha", "4px, com célula a 4px na vertical e 12px na horizontal"],
    ],
    consequencias: [
      "Linha de tabela a 32px: dez artigos ocupam 320px, e num portátil de 1280×800 cabem 18 linhas sem rolar.",
      "Célula a 13px com 4px de ar em cima e em baixo — a linha é o texto mais o mínimo.",
      "Zero réguas verticais e cabeçalho de coluna sem banda de cor (o mesmo branco da folha): numa tabela de sete colunas não há uma única linha vertical a cortar o nome do artigo.",
      "Barra lateral de 208px no mesmo branco do conteúdo, separada por um filete; cabeçalho de 48px. O cromado ocupa 208px de largura e nenhuma tinta.",
      "O item activo do menu é tinta de acento sobre uma tinta clara, sem trilho: a cor do texto é o sinal.",
    ],
    custos: [
      "Um modo escuro é trabalho por fazer: estes dezoito tokens são a versão clara e o espelho escuro ainda não foi medido.",
      "Troca de fontes, medida: Source Sans 3 em três pesos são 47,0 kB de woff2 latin, e saem o IBM Plex Sans (71,0 kB) e o IBM Plex Mono (14,7 kB) porque esta identidade não usa mono. Dá 38,7 kB menos de letra do que hoje.",
      "A 13px, um ecrã de 360px aguenta os fluxos de campo, mas a tabela de escritório continua a precisar de rolamento horizontal — é o que a ADR 0009 já declara.",
    ],
  },
  b: {
    chave: "b",
    nome: "Cabine",
    referencia: "Bloomberg Terminal e os ecrãs de cozinha (KDS) do Toast e do Square",
    ecra:
      "o painel de cotações do Terminal e o quadro de talões de um KDS: fundo preto, colunas regueadas, números em mono, a excepção a saltar por cor e por peso",
    razao:
      "A pergunta da manhã não é «quanto tenho de tudo», é «o que está mal». Num painel escuro com colunas regueadas e algarismos mono, uma linha em falta ou fora de prazo vê-se sem se ler — e vê-se de dois metros, que é a distância a que o dono olha para o monitor do escritório com a porta aberta para a copa. É também a identidade que aguenta um monitor barato e uma sala com a persiana meia fechada, onde um ecrã branco encandeia.",
    recusa:
      "Recusa o cromado invisível. A barra lateral é mais escura que o conteúdo, o cabeçalho da tabela tem fundo e as colunas têm régua: quem precisa de saber em que coluna está não tem de contar.",
    tipografia: [
      ["Família (UI e títulos)", "Archivo — grotesca de sinalética, alta e firme em peso médio"],
      ["Dados (quantidades, dinheiro)", "IBM Plex Mono — a família de mono que o projeto já traz"],
      ["Pesos", "500 corpo · 600 rótulos · 700 títulos e cabeçalhos de coluna (sem peso 400)"],
      ["Escala", "13 · 15 · 16 · 18 · 20 · 24 · 32 · 40 · 52 px (célula da tabela a 15)"],
      ["Entrelinha", "1,45 no corpo · 1,15 nos títulos · micro-rótulos em caixa alta a +0,08em"],
    ],
    forma: [
      ["Raio", "8px de base (4 · 6 · 8 · 12) — painéis com canto, como cartões de um KDS"],
      ["Sombras", "um fio de luz na aresta de cima do painel, mais uma sombra profunda; nenhuma colorida"],
      ["Separação", "fundo um degrau acima mais régua de 1px; a separação é de tinta, não de filete"],
      ["Grelha", "4px, com célula a 12px na vertical e 16px na horizontal"],
    ],
    consequencias: [
      "Linha de tabela a 44px: dez artigos ocupam 440px, 38% mais que a A, e num portátil de 1280×800 cabem 13 linhas sem rolar — cinco menos.",
      "Célula a 15px com 12px de ar: a linha é também um alvo de toque, logo a mesma tabela serve num tablet na copa sem um segundo desenho.",
      "Réguas verticais de 1px em todas as colunas e cabeçalho com fundo em surface-2: a tabela é uma grelha, não uma lista.",
      "Barra lateral de 256px em background (mais escura que os painéis em surface) e cabeçalho de 56px: o cromado ocupa 256px e um degrau de tinta.",
      "A linha e o item de menu activos levam um trilho de 4px na cor de acento, à esquerda: a posição é o sinal, e sobrevive a um ecrã mal calibrado.",
    ],
    custos: [
      "Um modo claro é trabalho por fazer: estes dezoito tokens são a versão escura e o espelho claro ainda não foi medido.",
      "Troca de fontes, medida: Archivo em três pesos são 42,9 kB de woff2 latin e o IBM Plex Mono (14,7 kB) fica; sai o IBM Plex Sans (71,0 kB). Dá 28,1 kB menos de letra do que hoje.",
      "A 44px por linha, o ecrã de Alertas deixa de ser uma lista longa e passa a pedir paginação mais cedo — 13 linhas por dobra em vez de 18.",
    ],
  },
};

/* -------------------------------------------------------------------------
 * O menu lateral. **Uma lista com um nível de agrupamento** e não uma árvore,
 * tal como a projecção por tenant da ADR 0009 (`route_id, grupo, ordem,
 * visivel, rotulo`). Aqui é literal e estático: é o que uma empresa veria, não
 * o registo de rotas.
 * ---------------------------------------------------------------------- */

export interface GrupoDeMenu {
  readonly grupo: string;
  readonly itens: readonly { readonly rotulo: string; readonly activo?: boolean }[];
}

export const MENU: readonly GrupoDeMenu[] = [
  {
    grupo: "Operação",
    itens: [
      { rotulo: "Stock", activo: true },
      { rotulo: "Receber" },
      { rotulo: "Contar" },
      { rotulo: "Alertas" },
      { rotulo: "Desperdício" },
    ],
  },
  {
    grupo: "Compras",
    itens: [{ rotulo: "Fornecedores" }, { rotulo: "Encomendas" }, { rotulo: "Faturas" }],
  },
  {
    grupo: "Produção",
    itens: [{ rotulo: "Receitas" }, { rotulo: "Fichas técnicas" }, { rotulo: "Produções" }],
  },
  {
    grupo: "Configuração",
    itens: [
      { rotulo: "Artigos" },
      { rotulo: "Localizações" },
      { rotulo: "Unidades" },
      { rotulo: "Utilizadores" },
    ],
  },
];

/* -------------------------------------------------------------------------
 * As linhas de stock da maqueta. Oito a dez, pela ordem do servidor — **o
 * pior primeiro**, nunca alfabética.
 * ---------------------------------------------------------------------- */

export type EstadoDeLinha = "negativo" | "esgotado" | "baixo" | "ok";

/**
 * `consumir_ate` é limite legal e pode chegar a vermelho; `qualidade` é
 * durabilidade mínima e o seu tecto de cor é o aviso — a amêndoa laminada com
 * a durabilidade a acabar não é para deitar fora, e marcá-la como "expira"
 * perde a confiança do dono na primeira vez.
 */
export type NaturezaDeValidade = "consumir_ate" | "qualidade";

export interface ValidadeDeMaqueta {
  readonly natureza: NaturezaDeValidade;
  /** Dias até à data. Negativo é passado. */
  readonly dias: number;
  readonly data: string;
  readonly lote: string;
}

export interface LinhaDeMaqueta {
  readonly id: string;
  readonly artigo: string;
  readonly localizacao: string;
  readonly quantidade: string;
  readonly unidade: string;
  readonly estado: EstadoDeLinha;
  readonly validade: ValidadeDeMaqueta | null;
  readonly valor: string;
}

/** O horizonte de "a expirar" é do servidor; aqui é um número fixo da maqueta. */
export const LIMIAR_EM_DIAS = 5;

export const LINHAS: readonly LinhaDeMaqueta[] = [
  {
    id: "nata-35",
    artigo: "Nata 35% m.g.",
    localizacao: "Câmara 2",
    quantidade: "-2.500",
    unidade: "L",
    estado: "negativo",
    validade: { natureza: "consumir_ate", dias: -1, data: "2026-09-30", lote: "L-2609-A" },
    valor: "-9",
  },
  {
    id: "ovo-past",
    artigo: "Ovo pasteurizado",
    localizacao: "Câmara 1",
    quantidade: "0.000",
    unidade: "L",
    estado: "esgotado",
    validade: null,
    valor: "0",
  },
  {
    id: "levedura",
    artigo: "Levedura fresca",
    localizacao: "Câmara 1",
    quantidade: "1.500",
    unidade: "kg",
    estado: "baixo",
    validade: { natureza: "consumir_ate", dias: 0, data: "2026-10-01", lote: "L-2809-C" },
    valor: "5",
  },
  {
    id: "manteiga-82",
    artigo: "Manteiga 82% m.g.",
    localizacao: "Câmara 1",
    quantidade: "8.400",
    unidade: "kg",
    estado: "baixo",
    validade: { natureza: "consumir_ate", dias: 3, data: "2026-10-04", lote: "L-2409-B" },
    valor: "76",
  },
  {
    id: "gelatina",
    artigo: "Gelatina em folha",
    localizacao: "Despensa",
    quantidade: "0.800",
    unidade: "kg",
    estado: "baixo",
    validade: null,
    valor: "22",
  },
  {
    id: "amendoa",
    artigo: "Amêndoa laminada",
    localizacao: "Despensa",
    quantidade: "3.200",
    unidade: "kg",
    estado: "ok",
    validade: { natureza: "qualidade", dias: 4, data: "2026-10-05", lote: "L-1208-D" },
    valor: "41",
  },
  {
    id: "farinha-t65",
    artigo: "Farinha de trigo T65",
    localizacao: "Armazém",
    quantidade: "142.000",
    unidade: "kg",
    estado: "ok",
    validade: { natureza: "qualidade", dias: 162, data: "2027-03-12", lote: "L-1509-E" },
    valor: "114",
  },
  {
    id: "chocolate-70",
    artigo: "Chocolate negro 70%",
    localizacao: "Despensa",
    quantidade: "18.000",
    unidade: "kg",
    estado: "ok",
    validade: { natureza: "qualidade", dias: 288, data: "2027-07-16", lote: "L-0507-F" },
    valor: "216",
  },
  {
    id: "acucar",
    artigo: "Açúcar branco granulado",
    localizacao: "Armazém",
    quantidade: "95.000",
    unidade: "kg",
    estado: "ok",
    validade: null,
    valor: "76",
  },
  {
    id: "leite-uht",
    artigo: "Leite UHT meio-gordo",
    localizacao: "Armazém",
    quantidade: "240.000",
    unidade: "L",
    estado: "ok",
    validade: { natureza: "consumir_ate", dias: 94, data: "2027-01-03", lote: "L-2209-G" },
    valor: "182",
  },
];

/** O nome da empresa da maqueta. O seletor de tenant vive no pé da barra
 * lateral e o de loja na barra do ecrã — são coisas diferentes (ADR 0009). */
export const EMPRESA = "Pastelaria Bela Flor";
export const LOJA = "Loja da Praça";
