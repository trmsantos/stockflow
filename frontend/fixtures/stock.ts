import {
  movimentoSchema,
  nivelDeStockSchema,
  quebraParaRegistarSchema,
  resumoDeStockSchema,
} from "../src/features/inventory/schemas.ts";
import { paginated } from "../src/lib/api/pagination.ts";
import { AUTORES } from "./aurora.ts";
import { centimosDe, decimilesimosDe, milesimosDe, stringDeCentimos } from "./decimal.ts";
import {
  HORIZONTE_DE_VALIDADE_EM_DIAS,
  acrescentar,
  artigoDe,
  ledger,
  lojaDe,
  lojasPedidas,
  loteDe,
  loteFefo,
  niveis,
  numeroDoArtigo,
  paraMovimento,
  somarPorArtigoELoja,
} from "./ledger.ts";
import { resposta, type Contexto, type Rota } from "./servidor.ts";
import type { Movimento } from "../src/features/inventory/schemas.ts";

/**
 * dados-falsos-stockflow — o recurso `stock` do módulo `inventory`.
 *
 * O ledger e tudo o que se deriva dele vivem no `ledger.ts`, porque os três
 * ecrãs de inventário são vistas do **mesmo** ledger. Aqui ficam as rotas deste
 * recurso e a única escrita que ele aceita.
 *
 * Apagabilidade: no dia em que o Django servir `/api/v1/stock/levels`,
 * `summary` e `movements`, apaga-se este ficheiro e a sua linha no
 * `servidor.ts`. O middleware deixa de conhecer os caminhos, o `next()` leva o
 * pedido ao backend e nenhum ecrã muda uma linha.
 *
 * Tudo o que sai daqui é validado pelo **mesmo** schema Zod que o cliente usa à
 * chegada (`src/features/inventory/schemas.ts`), logo um fixture que não
 * poderia sair do endpoint real falha alto, aqui, em vez de passar por bom.
 */

function resumo(ctx: Contexto) {
  const lojas = lojasPedidas(ctx);
  const linhas = niveis(lojas);
  const emFalta = linhas.filter((linha) => linha.status !== "ok").length;
  const aExpirar = linhas.filter(
    (linha) =>
      linha.nearest_expiry !== null &&
      linha.nearest_expiry.days_away <= HORIZONTE_DE_VALIDADE_EM_DIAS,
  ).length;

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

function linhasDoLedger(ctx: Contexto): Movimento[] {
  const artigoPedido = ctx.parametros.get("artigo");
  return ledger()
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

  const numero = numeroDoArtigo(corpo.data.product);
  const loja = lojaDe(corpo.data.location);
  if (numero === -1 || loja === null) {
    return resposta(400, {
      code: "invalido",
      detail: "Artigo ou localização desconhecidos neste estabelecimento.",
    });
  }

  // O lote pedido, quando quem registra já o sabe — é o caso do ecrã Alertas,
  // onde o alerta **é** sobre um lote. Sem ele, o mais próximo de expirar que
  // ainda tem stock, que é a mesma escolha que o serializer real terá de fazer
  // (FEFO, `inventory-domain` §4) e o que o ecrã de Stock precisa, porque lá a
  // ação parte do artigo e não de um lote.
  const pedido = corpo.data.lot_code;
  const lote =
    pedido !== undefined && loteDe(pedido)?.artigo === numero
      ? pedido
      : loteFefo(numero, loja);

  const novo = acrescentar({
    tipo: "waste",
    artigo: numero,
    loja,
    lote,
    milesimos: milesimosDe(corpo.data.quantity),
    sinal: null,
    motivo: corpo.data.reason,
    // Sem autenticação no shell, o autor é quem está à frente do balcão. O
    // campo existe sempre porque é a sonda da Q7 (guião §3).
    autor: AUTORES.ana,
    quando: new Date().toISOString(),
    referencia: null,
  });

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
      const linhas = niveis(lojasPedidas(ctx));
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
