import {
  movimentoSchema,
  nivelDeStockSchema,
  quebraParaRegistarSchema,
  resumoDeStockSchema,
  type EstadoNivel,
  type Movimento,
  type MotivoQuebra,
  type NivelDeStock,
  type Quantidade,
  type TipoMovimento,
  type TipoValidade,
} from "../src/features/inventory/schemas.ts";
import { paginated } from "../src/lib/api/pagination.ts";
import {
  ARTIGOS,
  AUTORES,
  LOCALIZACOES,
  dataEmDias,
  diasAte,
  horaDeHoje,
  horaDeOntem,
  type ArtigoFalso,
} from "./aurora.ts";
import {
  centimosDe,
  decimilesimosDe,
  milesimosDe,
  milesimosParaApresentacao,
  stringDeCentimos,
  stringDeMilesimos,
} from "./decimal.ts";
import { resposta, type Contexto, type Rota } from "./servidor.ts";

/**
 * dados-falsos-stockflow — o recurso `stock` do módulo `inventory`.
 *
 * **Stock é um ledger, também na mentira** (ADR 0008, decisão 3). O estado em
 * memória deste ficheiro são `StockMovement`s; os níveis, o estado da linha, a
 * validade mais próxima e o valor em euros são **derivados** deles a cada
 * pedido. Não há campo de quantidade que se escreva em sítio nenhum, e isso não
 * é purismo: um shell onde se corrige um número ensina o produto errado ao dono
 * na sessão 0 e ao próximo agente na sessão seguinte.
 *
 * Apagabilidade: no dia em que o Django servir `/api/v1/stock/…`, apaga-se este
 * ficheiro e a sua linha no `servidor.ts`. O middleware deixa de conhecer o
 * caminho, o `next()` leva o pedido ao backend e nenhum ecrã muda uma linha.
 *
 * Tudo o que sai daqui é validado pelo **mesmo** schema Zod que o cliente usa à
 * chegada (`src/features/inventory/schemas.ts`), logo um fixture que não
 * poderia sair do endpoint real falha alto, aqui, em vez de passar por bom.
 */

type Loja = "centro" | "mercado" | "cozinha";

interface MovimentoFalso {
  readonly id: string;
  readonly tipo: TipoMovimento;
  /** O `n` do artigo em `aurora.ts`. */
  readonly artigo: number;
  readonly loja: Loja;
  readonly lote: string | null;
  /** Valor absoluto em milésimos da unidade base. O sinal vem do tipo. */
  readonly milesimos: number;
  readonly motivo: MotivoQuebra | null;
  readonly autor: string;
  readonly quando: string;
  readonly referencia: string | null;
}

/** Sinal pelo tipo de movimento (`inventory-domain` §1). */
const SINAL_POR_TIPO = new Map<TipoMovimento, 1 | -1>([
  ["receipt", 1],
  ["transfer_in", 1],
  ["consumption", -1],
  ["waste", -1],
  ["transfer_out", -1],
  ["return", -1],
  // `adjustment` não tem sinal fixo: uma contagem pode corrigir para cima ou
  // para baixo. Neste ledger falso só aparece por POST, onde o sinal é o da
  // quebra que o origina.
  ["adjustment", -1],
]);

function sinalDe(tipo: TipoMovimento): number {
  return SINAL_POR_TIPO.get(tipo) ?? -1;
}

/**
 * Os lotes e as suas validades, **relativas a hoje**. Uma data congelada mata a
 * credibilidade no primeiro ecrã (guião §2), e a distinção `use_by` (limite
 * legal) / `best_before` (qualidade) é a condição para o dono confiar nos
 * alertas — a amêndoa laminada está aqui só por causa dela.
 */
interface LoteFalso {
  readonly codigo: string;
  readonly artigo: number;
  readonly dias: number;
  readonly tipo: TipoValidade;
}

const LOTES: readonly LoteFalso[] = [
  { codigo: "L-T65-1142", artigo: 1, dias: 180, tipo: "best_before" },
  { codigo: "L-OVL-0914", artigo: 3, dias: 3, tipo: "use_by" },
  { codigo: "L-MNT-0902", artigo: 5, dias: 38, tipo: "best_before" },
  { codigo: "L-NAT-0921", artigo: 6, dias: 6, tipo: "use_by" },
  { codigo: "L-LTE-0803", artigo: 7, dias: 95, tipo: "best_before" },
  { codigo: "L-MSF-0715", artigo: 9, dias: 210, tipo: "best_before" },
  // O alerta amarelo que **não** é para deitar fora. Ver guião §2.
  { codigo: "L-AMD-0928", artigo: 11, dias: 4, tipo: "best_before" },
  { codigo: "L-MOR-0930", artigo: 12, dias: 2, tipo: "use_by" },
  { codigo: "L-FER-0929", artigo: 13, dias: 5, tipo: "use_by" },
  { codigo: "L-QJF-0925", artigo: 14, dias: 7, tipo: "use_by" },
  { codigo: "L-FMB-0929", artigo: 15, dias: 3, tipo: "use_by" },
  { codigo: "L-BAC-0611", artigo: 21, dias: 300, tipo: "best_before" },
  // Produção própria: validade no **mesmo dia** (a sonda da Q6 do guião).
  { codigo: "L-PN-HOJE", artigo: 22, dias: 0, tipo: "use_by" },
  { codigo: "L-PN-ONTEM", artigo: 22, dias: -1, tipo: "use_by" },
];

function id(n: number): string {
  return `b0a70000-0000-4000-8000-${String(n).padStart(12, "0")}`;
}

let contador = 0;

function movimento(
  tipo: TipoMovimento,
  artigo: number,
  loja: Loja,
  base: string,
  lote: string | null,
  autor: string,
  quando: string,
  referencia: string | null,
  motivo: MotivoQuebra | null = null,
): MovimentoFalso {
  contador += 1;
  return {
    id: id(contador),
    tipo,
    artigo,
    loja,
    lote,
    milesimos: milesimosDe(base),
    motivo,
    autor,
    quando,
    referencia,
  };
}

/**
 * O ledger inicial. Cada linha é uma afirmação de domínio, e as que estão aqui
 * por uma razão nomeada no guião estão comentadas. Reiniciar o `pnpm dev` volta
 * a este estado, e isso é honesto: o shell demonstra o fluxo, não guarda dados.
 */
function semear(): MovimentoFalso[] {
  const ontem = horaDeOntem;
  const hoje = horaDeHoje;

  return [
    // --- entradas de mercadoria, a maioria por fatura do fornecedor
    movimento("receipt", 1, "cozinha", "50000", "L-T65-1142", AUTORES.rui, ontem(7, 20), "FT 2026/4471"),
    movimento("receipt", 2, "cozinha", "25000", null, AUTORES.rui, ontem(7, 20), "FT 2026/4471"),
    movimento("receipt", 3, "cozinha", "6000", "L-OVL-0914", AUTORES.rui, ontem(7, 25), "FT 2026/4471"),
    movimento("receipt", 4, "cozinha", "180", null, AUTORES.rui, ontem(7, 25), "FT 2026/4471"),
    movimento("receipt", 5, "cozinha", "7500", "L-MNT-0902", AUTORES.rui, ontem(7, 30), "FT 2026/4471"),
    // Guia de remessa sem fatura: os lácteos entram antes de existir fatura, e
    // a fatura de fim de mês reconcilia N entregas (guião §2, prática 2).
    movimento("receipt", 6, "cozinha", "12000", "L-NAT-0921", AUTORES.rui, ontem(8, 5), "Guia 4471"),
    movimento("receipt", 7, "cozinha", "24000", "L-LTE-0803", AUTORES.rui, ontem(8, 5), "Guia 4471"),
    movimento("receipt", 8, "centro", "4000", null, AUTORES.ana, ontem(9, 10), "FS 2026/114570"),
    // Receção parcial: 5 rolos encomendados, vieram 3 (guião §2).
    movimento("receipt", 9, "cozinha", "6000", "L-MSF-0715", AUTORES.rui, ontem(8, 40), "FT 2026/4502"),
    movimento("receipt", 10, "cozinha", "5000", null, AUTORES.rui, ontem(8, 40), "FT 2026/4502"),
    movimento("receipt", 11, "cozinha", "2000", "L-AMD-0928", AUTORES.rui, ontem(8, 40), "FT 2026/4502"),
    movimento("receipt", 12, "cozinha", "2000", "L-MOR-0930", AUTORES.rui, hoje(7, 5), "Fatura manuscrita"),
    movimento("receipt", 13, "cozinha", "1000", "L-FER-0929", AUTORES.rui, ontem(7, 30), "FT 2026/4471"),
    // Peso variável na fatura: a bola veio a 3,480 kg e não a 3,5 (guião §2).
    movimento("receipt", 14, "centro", "3480", "L-QJF-0925", AUTORES.ana, ontem(9, 10), "FS 2026/114570"),
    movimento("receipt", 15, "centro", "4120", "L-FMB-0929", AUTORES.ana, ontem(9, 10), "FS 2026/114570"),
    movimento("receipt", 16, "centro", "200", null, AUTORES.ana, ontem(9, 15), "FS 2026/114570"),
    movimento("receipt", 17, "cozinha", "10000", null, AUTORES.rui, ontem(9, 15), "FS 2026/114570"),
    movimento("receipt", 18, "centro", "96", null, AUTORES.ana, ontem(9, 15), "FS 2026/114570"),
    movimento("receipt", 19, "centro", "60", null, AUTORES.ana, ontem(9, 15), "FS 2026/114570"),
    movimento("receipt", 20, "centro", "1000", null, AUTORES.ana, ontem(9, 15), "FS 2026/114570"),
    movimento("receipt", 21, "centro", "5000", "L-BAC-0611", AUTORES.ana, ontem(9, 20), "FS 2026/114570"),

    // --- produção e venda
    // A produção própria entra no ledger como entrada. O `tipoMovimentoSchema`
    // não tem um `production` próprio, e **não** o invento aqui: se o domínio
    // quiser distinguir "comprei" de "produzi", é decisão da sessão do backend
    // e muda o schema, não o fixture (ADR 0008 — os fixtures são o rascunho do
    // contrato, não a sua fonte).
    movimento("receipt", 22, "cozinha", "300", "L-PN-HOJE", AUTORES.rui, hoje(6, 30), "Produção de hoje"),
    movimento("consumption", 1, "cozinha", "18000", "L-T65-1142", AUTORES.rui, hoje(6, 30), "Produção de hoje"),
    movimento("consumption", 3, "cozinha", "4500", "L-OVL-0914", AUTORES.rui, hoje(6, 30), "Produção de hoje"),
    movimento("consumption", 5, "cozinha", "5200", "L-MNT-0902", AUTORES.rui, hoje(6, 30), "Produção de hoje"),
    // A nata fica a zero: 12 L entraram, 10 L foram à produção e 2 L vinham
    // furados. É a sonda da Q1 — o ecrã deixa registar mais uma quebra e mostra
    // o negativo com aviso suave, sem bloquear.
    movimento("consumption", 6, "cozinha", "10000", "L-NAT-0921", AUTORES.rui, hoje(6, 35), "Produção de hoje"),
    movimento("waste", 6, "cozinha", "2000", "L-NAT-0921", AUTORES.rui, hoje(6, 40), null, "breakage"),
    movimento("consumption", 2, "cozinha", "9000", null, AUTORES.rui, hoje(6, 35), "Produção de hoje"),
    movimento("consumption", 12, "cozinha", "800", "L-MOR-0930", AUTORES.rui, hoje(7, 40), "Produção de hoje"),
    movimento("consumption", 8, "centro", "2200", null, AUTORES.ana, hoje(11, 2), "Vendas de hoje"),
    movimento("consumption", 20, "centro", "520", null, AUTORES.ana, hoje(11, 2), "Vendas de hoje"),
    movimento("consumption", 19, "centro", "22", null, AUTORES.ana, hoje(11, 2), "Vendas de hoje"),

    // --- transferência em trânsito: saiu da Cozinha e ainda não entrou na loja
    // (guião §3, Q4). O `transfer_in` não existe de propósito.
    movimento("transfer_out", 22, "cozinha", "40", "L-PN-HOJE", AUTORES.rui, hoje(8, 40), "Cozinha → Loja Centro"),

    // --- ontem, do princípio ao fim: produção, transferência **concluída** para
    // a loja, vendas, e o que sobrou ao fecho. É este contraste que faz a
    // transferência em trânsito de hoje ler-se como tal (guião §3, Q4) — e sem
    // ele a loja aparecia a deitar fora pastéis que nunca recebeu, que era um
    // negativo por acidente ao lado do negativo de propósito da nata.
    movimento("receipt", 22, "cozinha", "300", "L-PN-ONTEM", AUTORES.rui, ontem(6, 30), "Produção de ontem"),
    movimento("transfer_out", 22, "cozinha", "120", "L-PN-ONTEM", AUTORES.rui, ontem(8, 30), "Cozinha → Loja Centro"),
    movimento("transfer_in", 22, "centro", "120", "L-PN-ONTEM", AUTORES.ana, ontem(9, 5), "Cozinha → Loja Centro"),
    movimento("consumption", 22, "cozinha", "180", "L-PN-ONTEM", AUTORES.rui, ontem(19, 0), "Vendas de ontem"),
    movimento("consumption", 22, "centro", "108", "L-PN-ONTEM", AUTORES.ana, ontem(19, 0), "Vendas de ontem"),

    // --- 05:10 de hoje: os 12 que sobraram ao fecho de ontem, deitados fora
    // antes de o dia começar. A sonda da Q6: na pastelaria a fronteira do dia
    // de negócio é o início da produção, não o fim do serviço.
    movimento("waste", 22, "centro", "12", "L-PN-ONTEM", AUTORES.ana, hoje(5, 10), null, "expired"),
  ];
}

const movimentos: MovimentoFalso[] = semear();

// ---------------------------------------------------------------------------
// Derivação. Tudo o que o ecrã vê sai destas funções — nunca de um campo.
// ---------------------------------------------------------------------------

function artigoDe(n: number): ArtigoFalso | undefined {
  return ARTIGOS.at(n - 1);
}

function localizacaoDe(loja: Loja) {
  const encontrada = LOCALIZACOES.find((local) => local.slug === loja);
  // O seed é escrito à mão; um slug errado é um erro de programação e não um
  // caso a tratar em runtime.
  if (!encontrada) throw new Error(`Localização desconhecida no fixture: ${loja}`);
  return { id: encontrada.id, name: encontrada.nome };
}

function quantidade(artigo: ArtigoFalso, milesimos: number): Quantidade {
  return {
    base: stringDeMilesimos(milesimos),
    base_unit: artigo.unidadeBase,
    display: stringDeMilesimos(milesimosParaApresentacao(milesimos, artigo.fatorApresentacao)),
    display_unit: artigo.unidadeApresentacao,
  };
}

/** Soma do ledger por artigo e loja. É a projeção `StockLevel`, derivada. */
function somarPorArtigoELoja(lojas: readonly Loja[]): Map<number, Map<Loja, number>> {
  const total = new Map<number, Map<Loja, number>>();
  for (const mov of movimentos) {
    if (!lojas.includes(mov.loja)) continue;
    const porLoja = total.get(mov.artigo) ?? new Map<Loja, number>();
    porLoja.set(mov.loja, (porLoja.get(mov.loja) ?? 0) + sinalDe(mov.tipo) * mov.milesimos);
    total.set(mov.artigo, porLoja);
  }
  return total;
}

/** Soma do ledger por lote, para saber que validade ainda tem stock atrás. */
function somarPorLote(lojas: readonly Loja[]): Map<string, number> {
  const total = new Map<string, number>();
  for (const mov of movimentos) {
    if (mov.lote === null || !lojas.includes(mov.loja)) continue;
    total.set(mov.lote, (total.get(mov.lote) ?? 0) + sinalDe(mov.tipo) * mov.milesimos);
  }
  return total;
}

/**
 * O estado da linha, decidido **no servidor** (schemas.ts): se o limiar de
 * "baixo" mudar, muda num sítio, e a UI não ganha uma segunda definição de "em
 * falta" que divirja da dos alertas.
 */
function estadoDe(milesimos: number, minimo: number): EstadoNivel {
  if (milesimos < 0) return "negativo";
  if (milesimos === 0) return "esgotado";
  if (milesimos < minimo) return "baixo";
  return "ok";
}

function validadeMaisProxima(artigo: number, porLote: Map<string, number>) {
  const candidatos = LOTES.filter(
    (lote) => lote.artigo === artigo && (porLote.get(lote.codigo) ?? 0) > 0,
  ).sort((a, b) => a.dias - b.dias);
  const proximo = candidatos[0];
  if (!proximo) return null;
  const expiresAt = dataEmDias(proximo.dias);
  return {
    lot_code: proximo.codigo,
    expires_at: expiresAt,
    days_away: diasAte(expiresAt),
    kind: proximo.tipo,
  };
}

/** "O que está pior primeiro. **Nunca alfabética**" (guião §1). */
const ORDEM_DO_ESTADO = new Map<EstadoNivel, number>([
  ["negativo", 0],
  ["esgotado", 1],
  ["baixo", 2],
  ["ok", 3],
]);

/**
 * O `?loja=` do ecrã Stock — o search param que a decisão 1 do ADR 0008 existe
 * para tipar. Um valor desconhecido degrada para "todas" em vez de explodir.
 */
function lojasPedidas(ctx: Contexto): readonly Loja[] {
  const todas = LOCALIZACOES.map((local) => local.slug);
  const pedida = ctx.parametros.get("loja");
  const encontrada = todas.find((slug) => slug === pedida);
  return encontrada === undefined ? todas : [encontrada];
}

function niveis(ctx: Contexto): NivelDeStock[] {
  const lojas = lojasPedidas(ctx);
  const porArtigo = somarPorArtigoELoja(lojas);
  const porLote = somarPorLote(lojas);

  const linhas: NivelDeStock[] = [];
  for (const [numero, porLoja] of porArtigo) {
    const artigo = artigoDe(numero);
    if (!artigo) continue;
    const total = [...porLoja.values()].reduce((soma, valor) => soma + valor, 0);
    const minimo = milesimosDe(artigo.minimo);
    linhas.push({
      product: artigo.id,
      short_name: artigo.nomeCurto,
      quantity: quantidade(artigo, total),
      min_quantity: quantidade(artigo, minimo),
      status: estadoDe(total, minimo),
      nearest_expiry: validadeMaisProxima(numero, porLote),
      by_location: [...porLoja.entries()].map(([loja, valor]) => ({
        location: localizacaoDe(loja),
        quantity: quantidade(artigo, valor),
      })),
    });
  }

  return linhas.sort((a, b) => {
    const porEstado = (ORDEM_DO_ESTADO.get(a.status) ?? 9) - (ORDEM_DO_ESTADO.get(b.status) ?? 9);
    if (porEstado !== 0) return porEstado;
    const diasA = a.nearest_expiry?.days_away ?? Number.MAX_SAFE_INTEGER;
    const diasB = b.nearest_expiry?.days_away ?? Number.MAX_SAFE_INTEGER;
    return diasA - diasB;
  });
}

/** O limiar viaja com o número para o ecrã o poder mostrar (guião §4, nº 7). */
const HORIZONTE_DE_VALIDADE_EM_DIAS = 3;

function resumo(ctx: Contexto) {
  const linhas = niveis(ctx);
  const emFalta = linhas.filter((linha) => linha.status !== "ok").length;
  const aExpirar = linhas.filter(
    (linha) =>
      linha.nearest_expiry !== null &&
      linha.nearest_expiry.days_away <= HORIZONTE_DE_VALIDADE_EM_DIAS,
  ).length;

  const lojas = lojasPedidas(ctx);
  const porArtigo = somarPorArtigoELoja(lojas);
  let centimos = 0;
  for (const [numero, porLoja] of porArtigo) {
    const artigo = artigoDe(numero);
    if (!artigo) continue;
    const total = [...porLoja.values()].reduce((soma, valor) => soma + valor, 0);
    if (total <= 0) continue;
    centimos += centimosDe(total, decimilesimosDe(artigo.custoUnitario));
  }

  return {
    below_min_count: emFalta,
    expiring_count: aExpirar,
    expiring_within_days: HORIZONTE_DE_VALIDADE_EM_DIAS,
    stock_value_eur: stringDeCentimos(centimos),
  };
}

function paraMovimento(mov: MovimentoFalso): Movimento | null {
  const artigo = artigoDe(mov.artigo);
  if (!artigo) return null;
  return {
    id: mov.id,
    movement_type: mov.tipo,
    quantity: quantidade(artigo, sinalDe(mov.tipo) * mov.milesimos),
    location: localizacaoDe(mov.loja),
    lot_code: mov.lote,
    reason: mov.motivo,
    created_by: mov.autor,
    occurred_at: mov.quando,
    reference: mov.referencia,
  };
}

function linhasDoLedger(ctx: Contexto): Movimento[] {
  const artigoPedido = ctx.parametros.get("artigo");
  return movimentos
    .filter((mov) => {
      if (artigoPedido === null) return true;
      return artigoDe(mov.artigo)?.id === artigoPedido;
    })
    .slice()
    .sort((a, b) => b.quando.localeCompare(a.quando))
    .map(paraMovimento)
    .filter((mov): mov is Movimento => mov !== null);
}

// ---------------------------------------------------------------------------
// Escrita. Só append: não há rota para alterar nem para apagar um movimento, e
// é de propósito (ADR 0006 — `inventory_stockmovement` é append-only na própria
// base de dados, com `REVOKE UPDATE, DELETE`).
// ---------------------------------------------------------------------------

function registarQuebra(ctx: Contexto) {
  const corpo = quebraParaRegistarSchema.safeParse(ctx.corpo);
  if (!corpo.success) {
    return resposta(400, {
      code: "invalido",
      detail: "O corpo do pedido não tem a forma de um registo de quebra.",
      errors: corpo.error.issues.map((erro) => ({
        campo: erro.path.join("."),
        mensagem: erro.message,
      })),
    });
  }

  const artigo = ARTIGOS.findIndex((item) => item.id === corpo.data.product);
  const local = LOCALIZACOES.find((item) => item.id === corpo.data.location);
  if (artigo === -1 || !local) {
    return resposta(400, {
      code: "invalido",
      detail: "Artigo ou localização desconhecidos neste estabelecimento.",
    });
  }

  // O lote é o mais próximo de expirar que ainda tem stock — a mesma escolha
  // que o serializer real terá de fazer (FEFO, `inventory-domain` §4).
  const porLote = somarPorLote([local.slug]);
  const lote =
    LOTES.filter((item) => item.artigo === artigo + 1 && (porLote.get(item.codigo) ?? 0) > 0).sort(
      (a, b) => a.dias - b.dias,
    )[0] ?? null;

  const novo: MovimentoFalso = {
    id: crypto.randomUUID(),
    tipo: "waste",
    artigo: artigo + 1,
    loja: local.slug,
    lote: lote?.codigo ?? null,
    milesimos: milesimosDe(corpo.data.quantity),
    motivo: corpo.data.reason,
    // Sem autenticação no shell, o autor é quem está à frente do balcão. O
    // campo existe sempre porque é a sonda da Q7 (guião §3).
    autor: AUTORES.ana,
    quando: new Date().toISOString(),
    referencia: null,
  };
  movimentos.push(novo);

  const serializado = paraMovimento(novo);
  if (serializado === null) {
    return resposta(500, { detail: "Movimento criado sem artigo correspondente." });
  }
  return resposta(201, serializado, movimentoSchema);
}

// ---------------------------------------------------------------------------
// As rotas. Uma linha por endpoint que o Django ainda não tem.
// ---------------------------------------------------------------------------

/** Lote vazio: "o que aparece quando não há nada?" é uma pergunta da sessão. */
const PAGINA_VAZIA = { count: 0, next: null, previous: null, results: [] };

export const ROTAS_DE_STOCK: readonly Rota[] = [
  {
    metodo: "GET",
    caminho: "/api/v1/stock/levels",
    responder: (ctx) => {
      const linhas = niveis(ctx);
      return resposta(
        200,
        { count: linhas.length, next: null, previous: null, results: linhas },
        paginated(nivelDeStockSchema),
      );
    },
    vazio: () => resposta(200, PAGINA_VAZIA, paginated(nivelDeStockSchema)),
  },
  {
    metodo: "GET",
    caminho: "/api/v1/stock/summary",
    // O resumo é o primeiro pedido do ecrã e carrega acima da dobra: um atraso
    // menor que o default, para o skeleton dos três números não ficar mais
    // tempo no ecrã do que a lista que vem atrás dele.
    atrasoMs: 150,
    responder: (ctx) => resposta(200, resumo(ctx), resumoDeStockSchema),
    vazio: () =>
      resposta(
        200,
        {
          below_min_count: 0,
          expiring_count: 0,
          expiring_within_days: HORIZONTE_DE_VALIDADE_EM_DIAS,
          stock_value_eur: "0.00",
        },
        resumoDeStockSchema,
      ),
  },
  {
    metodo: "GET",
    caminho: "/api/v1/stock/movements",
    responder: (ctx) => {
      const linhas = linhasDoLedger(ctx);
      return resposta(
        200,
        { count: linhas.length, next: null, previous: null, results: linhas },
        paginated(movimentoSchema),
      );
    },
    vazio: () => resposta(200, PAGINA_VAZIA, paginated(movimentoSchema)),
  },
  {
    metodo: "POST",
    caminho: "/api/v1/stock/movements",
    responder: registarQuebra,
  },
];
