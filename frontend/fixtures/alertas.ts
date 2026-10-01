import {
  alertaSchema,
  desperdicioSchema,
  resumoDeAlertasSchema,
  type Alerta,
  type Desperdicio,
  type Gravidade,
} from "../src/features/inventory/schemas.ts";
import { paginated } from "../src/lib/api/pagination.ts";
import { LOCALIZACOES, dataEmDias, diasAte, inicioDeHoje } from "./aurora.ts";
import { milesimosDe, stringDeCentimos } from "./decimal.ts";
import {
  HORIZONTE_DE_VALIDADE_EM_DIAS,
  LOTES,
  artigoDe,
  centimosDoArtigo,
  ledger,
  localizacaoDe,
  niveis,
  numeroDoArtigo,
  quantidade,
  somarPorLoteELoja,
  todasAsLojas,
} from "./ledger.ts";
import { resposta, type Contexto, type Rota } from "./servidor.ts";

/**
 * dados-falsos-stockflow — o recurso `alerts` do módulo `inventory`.
 *
 * Três perguntas numa tab ("o que expira? o que falta? quanto deitei fora?") e
 * **uma** lista. As três são vistas do mesmo ledger: os lotes em risco são a
 * soma por lote, as faltas são a mesma projeção que o ecrã de Stock usa — logo
 * o número aqui e o número lá não podem divergir — e o desperdício é a leitura
 * dos movimentos de quebra desde o início do dia de negócio.
 *
 * Apagabilidade: no dia em que o Django servir `/api/v1/stock/alerts`,
 * apaga-se este ficheiro e a sua linha no `servidor.ts`.
 */

/**
 * A hora a que o dia de negócio começa — a sonda da Q6, e **dado do servidor**,
 * não constante do cliente.
 *
 * Numa pastelaria a fronteira é o **início da produção** (~4h) e não o fim do
 * serviço (~2h) de um restaurante: os pastéis que sobraram ao fecho de ontem
 * são deitados fora às 05:10, antes de o dia abrir, e com uma fronteira à
 * meia-noite apareciam como desperdício de hoje — o que faz o dono dizer "isso
 * é de ontem" e responder à pergunta sem ela ser feita. Que a resposta possa
 * ser diferente por tipo de negócio é, em si, o achado.
 *
 * O §5 do guião marca a hipótese às 05:00 e o §3 escreve o rótulo com 04:00. Às
 * 04:00 a quebra das 05:10 fica dentro do dia, que é a condição da sonda; às
 * 05:00 também, por dez minutos. Fica 04:00, que é o que o rótulo diz.
 */
const INICIO_DO_DIA_EM_HORAS = 4;

/** `"04:00"` — o rótulo que o ecrã mostra, derivado da mesma constante. */
const INICIO_DO_DIA = `${String(INICIO_DO_DIA_EM_HORAS).padStart(2, "0")}:00`;

/** Os sete dias de negócio que "esta semana" cobre. */
const DIAS_DA_SEMANA = 7;

/**
 * O instante em que o dia de negócio corrente começou. Antes das 04:00 ainda
 * se está no dia de negócio anterior — é essa a diferença entre um dia civil e
 * um dia de negócio, e é toda a pergunta.
 */
function inicioDoDiaDeNegocio(): Date {
  const agora = new Date();
  const inicio = inicioDeHoje();
  inicio.setHours(INICIO_DO_DIA_EM_HORAS, 0, 0, 0);
  if (agora.getTime() < inicio.getTime()) inicio.setDate(inicio.getDate() - 1);
  return inicio;
}

function inicioDaSemanaDeNegocio(): Date {
  const inicio = inicioDoDiaDeNegocio();
  inicio.setDate(inicio.getDate() - (DIAS_DA_SEMANA - 1));
  return inicio;
}

// ---------------------------------------------------------------------------
// Os alertas: uma lista, dois motivos.
// ---------------------------------------------------------------------------

/**
 * Ids estáveis entre pedidos, derivados da posição do lote e da localização.
 *
 * Não é estética: a linha expande para escolher o motivo, e com um id aleatório
 * a cada resposta o painel aberto fechava-se sozinho à primeira revalidação da
 * cache — e o toque seguinte caía noutra linha.
 */
function idDeAlerta(familia: number, primeiro: number, segundo: number): string {
  const sufixo = `${String(primeiro).padStart(6, "0")}${String(segundo).padStart(6, "0")}`;
  return `a1e70000-0000-4000-800${String(familia)}-${sufixo}`;
}

/**
 * O tecto de cor do `best_before`: **nunca** chega a `danger`.
 *
 * É a regra que o ecrã de Stock estabeleceu ("expira/expirou" contra "perde
 * qualidade"), aqui no contrato em vez de na folha de estilos: uma amêndoa
 * laminada com a durabilidade mínima a acabar não é para deitar fora, e se o
 * ecrã a marcar a vermelho o dono deixa de confiar na lista inteira — na
 * primeira linha, e para sempre.
 */
function gravidadeDaValidade(dias: number, tipo: "use_by" | "best_before"): Gravidade {
  if (tipo === "best_before") return "warning";
  return dias <= 0 ? "danger" : "warning";
}

function alertasDeValidade(): Alerta[] {
  const porLote = somarPorLoteELoja();
  const alertas: Alerta[] = [];

  LOTES.forEach((lote, indiceDoLote) => {
    if (lote.dias > HORIZONTE_DE_VALIDADE_EM_DIAS) return;
    const artigo = artigoDe(lote.artigo);
    if (artigo === undefined) return;
    const expiresAt = dataEmDias(lote.dias);

    LOCALIZACOES.forEach((local, indiceDaLoja) => {
      const milesimos = porLote.get(lote.codigo)?.get(local.slug) ?? 0;
      // Um lote sem stock atrás não é um alerta: já foi consumido ou já foi
      // deitado fora, e repeti-lo na lista era ensinar o dono a ignorá-la.
      if (milesimos <= 0) return;

      alertas.push({
        id: idDeAlerta(1, indiceDoLote, indiceDaLoja),
        product: artigo.id,
        short_name: artigo.nomeCurto,
        reason: "expiry",
        severity: gravidadeDaValidade(lote.dias, lote.tipo),
        location: localizacaoDe(local.slug),
        quantity: quantidade(artigo, milesimos),
        value_eur: stringDeCentimos(centimosDoArtigo(artigo, milesimos)),
        lot: {
          lot_code: lote.codigo,
          expires_at: expiresAt,
          days_away: diasAte(expiresAt),
          kind: lote.tipo,
        },
        // O limiar **dentro** do alerta: é assim que ele o contesta em voz alta
        // ("três dias é pouco") em vez de o ir mudar num painel que o guião §4
        // nº 7 proíbe — e é o painel que nos faria perder qual devia ser o
        // valor por omissão.
        threshold_days: HORIZONTE_DE_VALIDADE_EM_DIAS,
        min_quantity: null,
      });
    });
  });

  return alertas;
}

function alertasDeFalta(): Alerta[] {
  const alertas: Alerta[] = [];

  // A **mesma** projeção que o ecrã de Stock lê. Se "em falta" fosse recalculado
  // aqui, o número do Stock e o número dos Alertas divergiam no dia em que o
  // limiar mudasse, e o dono descobria-o antes de nós.
  niveis(todasAsLojas()).forEach((nivel) => {
    if (nivel.status === "ok") return;
    const numero = numeroDoArtigo(nivel.product);
    const artigo = artigoDe(numero);
    if (artigo === undefined) return;

    // O que custa voltar ao mínimo. Num alerta de validade o euro é o valor em
    // risco; aqui é o valor a repor, e o ecrã diz qual dos dois é. Em milésimos
    // e por subtração de inteiros, como tudo o que é quantidade nesta pasta.
    const aRepor = Math.max(
      0,
      milesimosDe(nivel.min_quantity.base) - milesimosDe(nivel.quantity.base),
    );

    alertas.push({
      id: idDeAlerta(2, numero, 0),
      product: nivel.product,
      short_name: nivel.short_name,
      reason: "missing",
      severity: nivel.status === "baixo" ? "warning" : "danger",
      // Sem localização: o mínimo é do artigo e vale sobre o consolidado. Uma
      // loja a apontar aqui seria uma precisão que o dado não tem.
      location: null,
      quantity: nivel.quantity,
      value_eur: stringDeCentimos(centimosDoArtigo(artigo, aRepor)),
      lot: null,
      threshold_days: null,
      min_quantity: nivel.min_quantity,
    });
  });

  return alertas;
}

const PESO_DA_GRAVIDADE = new Map<Gravidade, number>([
  ["danger", 0],
  ["warning", 1],
  ["info", 2],
]);

/**
 * "O que está pior primeiro", como em todo o resto desta API. Dentro da mesma
 * gravidade, quem tem relógio vem antes: um lote que expira hoje é mais urgente
 * do que uma prateleira vazia, que espera pela próxima entrega.
 */
function ordenar(alertas: Alerta[]): Alerta[] {
  return alertas.sort((a, b) => {
    const gravidade = (PESO_DA_GRAVIDADE.get(a.severity) ?? 9) - (PESO_DA_GRAVIDADE.get(b.severity) ?? 9);
    if (gravidade !== 0) return gravidade;
    const diasA = a.lot?.days_away ?? Number.MAX_SAFE_INTEGER;
    const diasB = b.lot?.days_away ?? Number.MAX_SAFE_INTEGER;
    if (diasA !== diasB) return diasA - diasB;
    return Number(b.value_eur) - Number(a.value_eur);
  });
}

function listaDeAlertas(ctx: Contexto): Alerta[] {
  const risco = ctx.parametros.get("risco");
  const todos = [
    ...(risco === "falta" ? [] : alertasDeValidade()),
    ...(risco === "expira" ? [] : alertasDeFalta()),
  ];
  return ordenar(todos);
}

// ---------------------------------------------------------------------------
// O desperdício: a vista do ledger que responde à terceira pergunta.
// ---------------------------------------------------------------------------

function desperdicioDesde(desde: Date): Desperdicio[] {
  const linhas: Desperdicio[] = [];
  for (const mov of ledger()) {
    if (mov.tipo !== "waste" || mov.motivo === null) continue;
    if (new Date(mov.quando).getTime() < desde.getTime()) continue;
    const artigo = artigoDe(mov.artigo);
    if (artigo === undefined) continue;
    linhas.push({
      id: mov.id,
      product: artigo.id,
      short_name: artigo.nomeCurto,
      lot_code: mov.lote,
      quantity: quantidade(artigo, mov.milesimos),
      value_eur: stringDeCentimos(centimosDoArtigo(artigo, mov.milesimos)),
      reason: mov.motivo,
      location: localizacaoDe(mov.loja),
      created_by: mov.autor,
      occurred_at: mov.quando,
    });
  }
  // Do mais recente para o mais antigo: a última coisa que se deitou fora é a
  // que se reconhece ("os pastéis de ontem, às 05:10").
  return linhas.sort((a, b) => b.occurred_at.localeCompare(a.occurred_at));
}

function centimosDeDesperdicio(desde: Date): number {
  let centimos = 0;
  for (const mov of ledger()) {
    if (mov.tipo !== "waste") continue;
    if (new Date(mov.quando).getTime() < desde.getTime()) continue;
    const artigo = artigoDe(mov.artigo);
    if (artigo === undefined) continue;
    centimos += centimosDoArtigo(artigo, mov.milesimos);
  }
  return centimos;
}

function resumo() {
  const alertas = ordenar([...alertasDeValidade(), ...alertasDeFalta()]);
  const desde = inicioDoDiaDeNegocio();

  return {
    // Conta **lotes**, que é o que a lista mostra: um número no topo que não
    // dá as linhas de baixo é a primeira coisa que faz o dono desconfiar. O
    // número de *artigos* a expirar é o do ecrã de Stock, e os dois rótulos
    // dizem qual é qual.
    expiring_count: alertas.filter((alerta) => alerta.reason === "expiry").length,
    expiring_within_days: HORIZONTE_DE_VALIDADE_EM_DIAS,
    missing_count: alertas.filter((alerta) => alerta.reason === "missing").length,
    wasted_today_eur: stringDeCentimos(centimosDeDesperdicio(desde)),
    wasted_week_eur: stringDeCentimos(centimosDeDesperdicio(inicioDaSemanaDeNegocio())),
    business_day_starts_at: INICIO_DO_DIA,
    wasted_since: desde.toISOString(),
  };
}

// ---------------------------------------------------------------------------
// As rotas.
// ---------------------------------------------------------------------------

const PAGINA_VAZIA = { count: 0, next: null, previous: null, results: [] };

export const ROTAS_DE_ALERTAS: readonly Rota[] = [
  {
    metodo: "GET",
    caminho: "/api/v1/stock/alerts/summary",
    // Carrega acima da dobra, como o resumo do Stock: atraso menor para o
    // skeleton dos três números não durar mais do que a lista atrás dele.
    atrasoMs: 150,
    responder: () => resposta(200, resumo(), resumoDeAlertasSchema),
    vazio: () =>
      resposta(
        200,
        {
          expiring_count: 0,
          expiring_within_days: HORIZONTE_DE_VALIDADE_EM_DIAS,
          missing_count: 0,
          wasted_today_eur: "0.00",
          wasted_week_eur: "0.00",
          business_day_starts_at: INICIO_DO_DIA,
          wasted_since: inicioDoDiaDeNegocio().toISOString(),
        },
        resumoDeAlertasSchema,
      ),
  },
  {
    metodo: "GET",
    caminho: "/api/v1/stock/alerts",
    responder: (ctx) => {
      const linhas = listaDeAlertas(ctx);
      return resposta(
        200,
        { count: linhas.length, next: null, previous: null, results: linhas },
        paginated(alertaSchema),
      );
    },
    vazio: () => resposta(200, PAGINA_VAZIA, paginated(alertaSchema)),
  },
  {
    metodo: "GET",
    caminho: "/api/v1/stock/alerts/waste",
    responder: (ctx) => {
      const semana = ctx.parametros.get("periodo") === "semana";
      const linhas = desperdicioDesde(semana ? inicioDaSemanaDeNegocio() : inicioDoDiaDeNegocio());
      return resposta(
        200,
        { count: linhas.length, next: null, previous: null, results: linhas },
        paginated(desperdicioSchema),
      );
    },
    vazio: () => resposta(200, PAGINA_VAZIA, paginated(desperdicioSchema)),
  },
];
