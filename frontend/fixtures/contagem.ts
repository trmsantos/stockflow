import {
  contagemDeLinhaSchema,
  contagemParaIniciarSchema,
  contagemSchema,
  fechoDeContagemSchema,
  fechoParaRegistarSchema,
  linhaDeContagemSchema,
  type Contagem,
  type FechoDeContagem,
  type LinhaDeContagem,
  type ProgressoDeZona,
  type Zona,
} from "../src/features/inventory/schemas.ts";
import { paginated } from "../src/lib/api/pagination.ts";
import { AUTORES, horaDeHoje, type ArtigoFalso } from "./aurora.ts";
import { milesimosDe, stringDeCentimos } from "./decimal.ts";
import {
  acrescentar,
  artigoDe,
  centimosDoArtigo,
  ledger,
  localizacaoDe,
  lojaDe,
  loteFefo,
  numeroDoArtigo,
  quantidade,
  stockDe,
  type Loja,
} from "./ledger.ts";
import { resposta, type Contexto, type Rota } from "./servidor.ts";

/**
 * dados-falsos-stockflow — o recurso `counts` do módulo `inventory`: a contagem
 * física.
 *
 * Uma contagem é uma **vista do ledger** com uma coluna por cima: o esperado
 * sai do ledger a cada pedido, o contado é o que ele escreveu, e ao fechar a
 * diferença entra no ledger como `adjustment`. Em nenhum momento se reescreve
 * um nível — é por isso que existe aqui um campo numérico sem contradizer a
 * proibição nº 1 do guião §4, que é sobre um lápis ao lado do número no ecrã de
 * Stock.
 *
 * **A ordem é a do percurso físico** — Balcão → Frigorífico → Arca → Armazém —
 * e é decidida aqui, no servidor, como todas as outras ordens desta API. Quem
 * conta anda pela cozinha, não pelo alfabeto (guião §1: "é regra, não
 * preferência").
 *
 * Apagabilidade: no dia em que o Django servir `/api/v1/stock/counts`, apaga-se
 * este ficheiro e a sua linha no `servidor.ts`.
 */

/**
 * As zonas, na ordem do percurso. **Uma é cega** e as outras não, que é a sonda
 * do guião §3 ("uma zona com o esperado visível, outra sem"): a boa prática é
 * cega, para evitar ancoragem, e a intuição do dono costuma ser o contrário. A
 * hipótese marcada no §5 é "esperado visível", por isso é essa a maioria — a
 * zona cega está lá para ele ver a alternativa e escolher, não para o shell
 * escolher por ele.
 *
 * O Frigorífico é a zona cega porque é a que tem peso variável (queijo ao kg,
 * fiambre ao kg): é onde a ancoragem num número do sistema mais estraga uma
 * contagem, e onde a diferença mais vale dinheiro.
 */
interface ZonaFalsa {
  readonly slug: string;
  readonly nome: string;
  readonly cega: boolean;
  /** Os artigos desta zona, na ordem por que se passa por eles. */
  readonly percurso: readonly number[];
}

const ZONAS: readonly ZonaFalsa[] = [
  { slug: "balcao", nome: "Balcão", cega: false, percurso: [22, 8, 19, 20] },
  {
    slug: "frigorifico",
    nome: "Frigorífico",
    cega: true,
    percurso: [14, 15, 3, 6, 7, 5, 13, 12, 18],
  },
  { slug: "arca", nome: "Arca", cega: false, percurso: [21, 16, 9] },
  { slug: "armazem", nome: "Armazém", cega: false, percurso: [1, 2, 4, 10, 11, 17] },
];

/** Acima disto, ao fechar, a justificação é obrigatória. Em cêntimos. */
const LIMIAR_DE_MOTIVO_EM_CENTIMOS = 500;

/**
 * Quem fecha. É um **rótulo** e não uma permissão: o shell não bloqueia nada
 * (guião §4, proibição 3). Mostra a quem a ação pertence, e a pergunta que se
 * faz depois é "a Ana podia ter feito isto?" (Q7).
 */
const PAPEL_QUE_FECHA = "responsável de loja";

interface LinhaFalsa {
  readonly id: string;
  readonly artigo: number;
  readonly zona: string;
  readonly posicao: number;
  /** Contado, em milésimos da unidade **base**. `null` = por contar. */
  contados: number | null;
  autor: string | null;
  quando: string | null;
  /**
   * O esperado no instante do fecho. É a única coisa que esta estrutura guarda
   * em vez de derivar: depois de o ajuste entrar no ledger, o esperado passa a
   * ser igual ao contado, e sem este retrato a contagem fechada mostraria zero
   * diferenças — exactamente as que a fizeram existir.
   */
  esperadoAoFechar: number | null;
}

interface ContagemFalsa {
  readonly id: string;
  readonly loja: Loja;
  readonly iniciada: string;
  readonly linhas: readonly LinhaFalsa[];
  estado: "open" | "closed";
  fechada: string | null;
  motivo: string | null;
}

function linhasDe(loja: Loja): LinhaFalsa[] {
  const linhas: LinhaFalsa[] = [];
  for (const zona of ZONAS) {
    zona.percurso.forEach((numero, posicao) => {
      // Só entra na contagem o artigo de que esta loja tem história: um artigo
      // que nunca passou por aqui não está nesta prateleira, e sete linhas a
      // zero no topo da lista eram ruído onde só cabem sete linhas (guião §0).
      const temHistoria = ledger().some((mov) => mov.artigo === numero && mov.loja === loja);
      if (!temHistoria) return;
      linhas.push({
        id: crypto.randomUUID(),
        artigo: numero,
        zona: zona.slug,
        posicao,
        contados: null,
        autor: null,
        quando: null,
        esperadoAoFechar: null,
      });
    });
  }
  return linhas;
}

/**
 * Uma contagem a meio, para o ecrã ter o que mostrar sem se ter de o encenar:
 * o Balcão quase contado, com uma falta de café que vale dinheiro, três caixas
 * de bolo a menos e doze pastéis **a mais** (o sinal positivo tem de aparecer
 * em algum sítio, e aqui vem da transferência em trânsito que ninguém lançou —
 * a Q4). As saquetas de açúcar ficam por contar de propósito: é o artigo que
 * ninguém vai contar, e vê-se se ele o diz em voz alta.
 */
function semearContagem(): ContagemFalsa {
  const linhas = linhasDe("centro");
  const contado = new Map<number, { quantidade: string; quando: string }>([
    [8, { quantidade: "1.200", quando: horaDeHoje(11, 36) }],
    [19, { quantidade: "35", quando: horaDeHoje(11, 38) }],
    [22, { quantidade: "12", quando: horaDeHoje(11, 34) }],
  ]);

  for (const linha of linhas) {
    const valor = contado.get(linha.artigo);
    const artigo = artigoDe(linha.artigo);
    if (valor === undefined || artigo === undefined) continue;
    linha.contados = milesimosDe(valor.quantidade) * artigo.fatorApresentacao;
    linha.autor = AUTORES.ana;
    linha.quando = valor.quando;
  }

  return {
    id: "c0a70000-0000-4000-8000-000000000001",
    loja: "centro",
    iniciada: horaDeHoje(11, 30),
    linhas,
    estado: "open",
    fechada: null,
    motivo: null,
  };
}

const contagens: ContagemFalsa[] = [semearContagem()];

// ---------------------------------------------------------------------------
// Derivação.
// ---------------------------------------------------------------------------

function zonaFalsaDe(slug: string): ZonaFalsa | undefined {
  return ZONAS.find((zona) => zona.slug === slug);
}

function paraZona(zona: ZonaFalsa): Zona {
  return {
    slug: zona.slug,
    name: zona.nome,
    position: ZONAS.indexOf(zona),
    blind: zona.cega,
  };
}

/** O esperado desta linha: do ledger enquanto está aberta, do retrato depois. */
function esperadoDe(contagem: ContagemFalsa, linha: LinhaFalsa): number {
  return contagem.estado === "closed"
    ? (linha.esperadoAoFechar ?? 0)
    : stockDe(linha.artigo, contagem.loja);
}

/**
 * Se o esperado pode ser mostrado. Numa zona cega **não viaja na resposta**
 * enquanto se conta; no fecho revela-se, porque mostrar as diferenças é o que o
 * fecho é — esconder ali o desvio da zona cega seria esconder metade da
 * contagem a quem a vai assinar.
 */
function esperadoVisivel(contagem: ContagemFalsa, zona: ZonaFalsa, revelar: boolean): boolean {
  return revelar || !zona.cega || contagem.estado === "closed";
}

function paraLinha(
  contagem: ContagemFalsa,
  linha: LinhaFalsa,
  artigo: ArtigoFalso,
  zona: ZonaFalsa,
  revelar = false,
): LinhaDeContagem {
  const visivel = esperadoVisivel(contagem, zona, revelar);
  const esperado = esperadoDe(contagem, linha);
  const diferenca =
    visivel && linha.contados !== null ? linha.contados - esperado : null;

  return {
    id: linha.id,
    product: artigo.id,
    short_name: artigo.nomeCurto,
    zone: paraZona(zona),
    position: linha.posicao,
    count_unit: artigo.unidadeApresentacao,
    expected: visivel ? quantidade(artigo, esperado) : null,
    counted: linha.contados === null ? null : quantidade(artigo, linha.contados),
    difference: diferenca === null ? null : quantidade(artigo, diferenca),
    difference_eur:
      diferenca === null ? null : stringDeCentimos(centimosDoArtigo(artigo, diferenca)),
    counted_by: linha.autor,
    counted_at: linha.quando,
  };
}

function linhasSerializadas(contagem: ContagemFalsa): LinhaDeContagem[] {
  const linhas: LinhaDeContagem[] = [];
  for (const linha of contagem.linhas) {
    const artigo = artigoDe(linha.artigo);
    const zona = zonaFalsaDe(linha.zona);
    if (artigo === undefined || zona === undefined) continue;
    linhas.push(paraLinha(contagem, linha, artigo, zona));
  }
  return linhas;
}

function progressoDasZonas(contagem: ContagemFalsa): ProgressoDeZona[] {
  return ZONAS.filter((zona) => contagem.linhas.some((linha) => linha.zona === zona.slug)).map(
    (zona) => {
      const linhas = contagem.linhas.filter((linha) => linha.zona === zona.slug);
      return {
        ...paraZona(zona),
        counted_lines: linhas.filter((linha) => linha.contados !== null).length,
        total_lines: linhas.length,
      };
    },
  );
}

function paraContagem(contagem: ContagemFalsa): Contagem {
  const zonas = progressoDasZonas(contagem);
  return {
    id: contagem.id,
    location: localizacaoDe(contagem.loja),
    status: contagem.estado,
    started_at: contagem.iniciada,
    closed_at: contagem.fechada,
    counted_lines: contagem.linhas.filter((linha) => linha.contados !== null).length,
    total_lines: contagem.linhas.length,
    // A zona actual é a primeira, **na ordem do percurso**, que ainda tem
    // linhas por contar: é onde ele está, não onde ele tocou pela última vez.
    current_zone: zonas.find((zona) => zona.counted_lines < zona.total_lines) ?? null,
    zones: zonas,
    closing_role: PAPEL_QUE_FECHA,
    closing_reason: contagem.motivo,
  };
}

interface Desvio {
  readonly linha: LinhaDeContagem;
  /** Em cêntimos, com sinal. Inteiro: a aritmética não passa por `float`. */
  readonly centimos: number;
}

/**
 * O fecho: as diferenças em quantidade **e em euros**, as duas somadas em
 * aritmética de inteiros (`decimal.ts`), e o limiar acima do qual a
 * justificação é obrigatória.
 *
 * Aqui o esperado é sempre revelado, inclusive na zona cega.
 */
function fechoDe(contagem: ContagemFalsa): FechoDeContagem {
  const desvios: Desvio[] = [];
  for (const linha of contagem.linhas) {
    const artigo = artigoDe(linha.artigo);
    const zona = zonaFalsaDe(linha.zona);
    if (artigo === undefined || zona === undefined || linha.contados === null) continue;
    const diferenca = linha.contados - esperadoDe(contagem, linha);
    if (diferenca === 0) continue;
    desvios.push({
      linha: paraLinha(contagem, linha, artigo, zona, true),
      centimos: centimosDoArtigo(artigo, diferenca),
    });
  }

  // A maior em euros primeiro: é por ela que a conversa começa.
  desvios.sort((a, b) => Math.abs(b.centimos) - Math.abs(a.centimos));

  let perda = 0;
  let ganho = 0;
  for (const desvio of desvios) {
    if (desvio.centimos < 0) perda -= desvio.centimos;
    else ganho += desvio.centimos;
  }

  return {
    count: contagem.id,
    status: contagem.estado,
    counted_lines: contagem.linhas.filter((linha) => linha.contados !== null).length,
    total_lines: contagem.linhas.length,
    differences: desvios.map((desvio) => desvio.linha),
    loss_eur: stringDeCentimos(perda),
    gain_eur: stringDeCentimos(ganho),
    net_eur: stringDeCentimos(ganho - perda),
    reason_required_above_eur: stringDeCentimos(LIMIAR_DE_MOTIVO_EM_CENTIMOS),
    reason_required: perda + ganho > LIMIAR_DE_MOTIVO_EM_CENTIMOS,
    closing_role: PAPEL_QUE_FECHA,
    closing_reason: contagem.motivo,
  };
}

function contagemPedida(ctx: Contexto): ContagemFalsa | undefined {
  const id = ctx.variaveis.get("contagem");
  return contagens.find((contagem) => contagem.id === id);
}

const NAO_ENCONTRADA = {
  code: "nao_encontrada",
  detail: "Esta contagem não existe neste estabelecimento.",
};

// ---------------------------------------------------------------------------
// Escrita.
// ---------------------------------------------------------------------------

function iniciarContagem(ctx: Contexto) {
  const corpo = contagemParaIniciarSchema.safeParse(ctx.corpo);
  if (!corpo.success) {
    return resposta(400, {
      code: "invalido",
      detail: "Diga em que localização quer contar.",
    });
  }
  const loja = lojaDe(corpo.data.location);
  if (loja === null) {
    return resposta(400, { code: "invalido", detail: "Localização desconhecida." });
  }

  // Já havia uma aberta nesta loja: devolve-se essa em vez de abrir uma
  // segunda. Duas contagens abertas da mesma prateleira não são um caso de
  // negócio, são um duplo clique.
  const aberta = contagens.find(
    (contagem) => contagem.estado === "open" && contagem.loja === loja,
  );
  if (aberta) return resposta(200, paraContagem(aberta), contagemSchema);

  const nova: ContagemFalsa = {
    id: crypto.randomUUID(),
    loja,
    iniciada: new Date().toISOString(),
    linhas: linhasDe(loja),
    estado: "open",
    fechada: null,
    motivo: null,
  };
  contagens.unshift(nova);
  return resposta(201, paraContagem(nova), contagemSchema);
}

function registarLinha(ctx: Contexto) {
  const contagem = contagemPedida(ctx);
  if (!contagem) return resposta(404, NAO_ENCONTRADA);
  if (contagem.estado === "closed") {
    return resposta(409, {
      code: "contagem_fechada",
      detail: "Esta contagem já foi fechada. Comece uma nova para contar outra vez.",
    });
  }

  const corpo = contagemDeLinhaSchema.safeParse(ctx.corpo);
  if (!corpo.success) {
    return resposta(400, {
      code: "invalido",
      detail: "O corpo do pedido não tem a forma de uma contagem de linha.",
    });
  }

  const numero = numeroDoArtigo(corpo.data.product);
  const artigo = artigoDe(numero);
  const linha = contagem.linhas.find((item) => item.artigo === numero);
  const zona = linha === undefined ? undefined : zonaFalsaDe(linha.zona);
  if (artigo === undefined || linha === undefined || zona === undefined) {
    return resposta(400, {
      code: "invalido",
      detail: "Este artigo não faz parte desta contagem.",
    });
  }

  // Uma quantidade negativa na prateleira não existe. Não é um bloqueio de
  // negócio (esses estão proibidos): é um valor que não pode ser observado.
  if (corpo.data.quantity.startsWith("-")) {
    return resposta(400, {
      code: "invalido",
      detail: "A quantidade contada não pode ser negativa.",
    });
  }

  // A conversão da unidade de contagem para a base é **aqui**, no servidor.
  linha.contados = milesimosDe(corpo.data.quantity) * artigo.fatorApresentacao;
  linha.autor = AUTORES.ana;
  linha.quando = new Date().toISOString();

  return resposta(201, paraLinha(contagem, linha, artigo, zona), linhaDeContagemSchema);
}

function fecharContagem(ctx: Contexto) {
  const contagem = contagemPedida(ctx);
  if (!contagem) return resposta(404, NAO_ENCONTRADA);
  if (contagem.estado === "closed") {
    return resposta(200, fechoDe(contagem), fechoDeContagemSchema);
  }

  const corpo = fechoParaRegistarSchema.safeParse(ctx.corpo ?? {});
  if (!corpo.success) {
    return resposta(400, {
      code: "invalido",
      detail: "A justificação tem de ter entre 1 e 200 caracteres.",
    });
  }

  const previsto = fechoDe(contagem);
  const motivo = corpo.data.reason;
  if (previsto.reason_required && motivo === undefined) {
    // Recusa do **servidor**, com o limiar na frase. O botão do ecrã nunca fica
    // desativado por causa disto: fechar uma contagem com diferenças tem de ser
    // possível, e a exigência é a justificação, não a ausência de diferenças.
    return resposta(400, {
      code: "motivo_obrigatorio",
      detail: `As diferenças desta contagem somam mais de ${previsto.reason_required_above_eur} € — escreva o que aconteceu antes de fechar.`,
    });
  }

  // O retrato do esperado, **antes** de os ajustes entrarem no ledger.
  for (const linha of contagem.linhas) {
    linha.esperadoAoFechar = stockDe(linha.artigo, contagem.loja);
  }

  const quando = new Date().toISOString();
  for (const linha of contagem.linhas) {
    if (linha.contados === null) continue;
    const diferenca = linha.contados - (linha.esperadoAoFechar ?? 0);
    if (diferenca === 0) continue;
    // Uma contagem **cria um movimento de ajuste**; não reescreve um nível. O
    // sinal é explícito porque um ajuste corrige nos dois sentidos.
    acrescentar({
      tipo: "adjustment",
      artigo: linha.artigo,
      loja: contagem.loja,
      lote: loteFefo(linha.artigo, contagem.loja),
      milesimos: Math.abs(diferenca),
      sinal: diferenca > 0 ? 1 : -1,
      motivo: null,
      autor: AUTORES.dono,
      quando,
      referencia: motivo === undefined ? "Contagem" : `Contagem · ${motivo}`,
    });
  }

  contagem.estado = "closed";
  contagem.fechada = quando;
  contagem.motivo = motivo ?? null;

  return resposta(201, fechoDe(contagem), fechoDeContagemSchema);
}

// ---------------------------------------------------------------------------
// As rotas.
// ---------------------------------------------------------------------------

const PAGINA_VAZIA = { count: 0, next: null, previous: null, results: [] };

export const ROTAS_DE_CONTAGEM: readonly Rota[] = [
  {
    metodo: "GET",
    caminho: "/api/v1/stock/counts",
    atrasoMs: 150,
    responder: () =>
      resposta(
        200,
        {
          count: contagens.length,
          next: null,
          previous: null,
          results: contagens.map(paraContagem),
        },
        paginated(contagemSchema),
      ),
    // Sem contagem nenhuma: é o estado vazio do ecrã Contar, e tem ação
    // própria ("Começar contagem"), que é o que o DESIGN.md §3 exige.
    vazio: () => resposta(200, PAGINA_VAZIA, paginated(contagemSchema)),
  },
  {
    metodo: "POST",
    caminho: "/api/v1/stock/counts",
    responder: iniciarContagem,
  },
  {
    metodo: "GET",
    caminho: "/api/v1/stock/counts/:contagem/lines",
    responder: (ctx) => {
      const contagem = contagemPedida(ctx);
      if (!contagem) return resposta(404, NAO_ENCONTRADA);
      const zonaPedida = ctx.parametros.get("zona");
      const linhas = linhasSerializadas(contagem).filter(
        (linha) => zonaPedida === null || linha.zone.slug === zonaPedida,
      );
      return resposta(
        200,
        { count: linhas.length, next: null, previous: null, results: linhas },
        paginated(linhaDeContagemSchema),
      );
    },
    vazio: () => resposta(200, PAGINA_VAZIA, paginated(linhaDeContagemSchema)),
  },
  {
    metodo: "POST",
    caminho: "/api/v1/stock/counts/:contagem/lines",
    atrasoMs: 120,
    responder: registarLinha,
  },
  {
    metodo: "GET",
    caminho: "/api/v1/stock/counts/:contagem/closing",
    responder: (ctx) => {
      const contagem = contagemPedida(ctx);
      if (!contagem) return resposta(404, NAO_ENCONTRADA);
      return resposta(200, fechoDe(contagem), fechoDeContagemSchema);
    },
  },
  {
    metodo: "POST",
    caminho: "/api/v1/stock/counts/:contagem/closing",
    responder: fecharContagem,
  },
];
