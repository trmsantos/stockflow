import {
  fechoDoMesSchema,
  mesSchema,
  periodoSchema,
  resumoDoPeriodoSchema,
  seriesDoPeriodoSchema,
  type ComponenteDeCusto,
  type DesperdicioPorMotivo,
  type FechoDoMes,
  type IdDeCusto,
  type Intervalo,
  type MotivoDeQuebra,
  type Periodo,
  type PeriodoResolvido,
  type PontoDaSerie,
  type QualidadeDosDados,
  type ResumoDoPeriodo,
  type Serie,
  type SeriesDoPeriodo,
} from "../src/features/reporting/schemas.ts";
import { centimosDe, decimilesimosDe, stringDeCentimos, stringDeMilesimos } from "./decimal.ts";
import {
  INICIO_DO_DIA,
  artigoDe,
  centimosDoArtigo,
  inicioDoDiaDeNegocio,
  ledger,
  somarPorArtigoELoja,
  todasAsLojas,
} from "./ledger.ts";
import { resposta, type Contexto, type Rota } from "./servidor.ts";

/**
 * dados-falsos-stockflow — o módulo `reporting`: os três endpoints do painel de
 * gestão (ADR 0013, decisão 5).
 *
 * ## O que este ficheiro é obrigado a conter, e porquê
 *
 * A ADR 0013 não pede um mês bonito: pede **os dois modos de falha nomeados**,
 * porque é isso que torna o painel um instrumento em vez de uma brochura.
 *
 *  - **um mês com stock-up** (compras muito acima do consumo), para a variação
 *    de stock aparecer grande e positiva e o dono reconhecer o seu próprio
 *    gesto em vez de ler um prejuízo. É o mês anterior (`prev_month`), logo
 *    está a um toque no seletor de período;
 *  - **um mês sem contagem**, para a quebra desconhecida vir a zero com uma
 *    data de última contagem antiga ao lado. "Zero quebra desconhecida não é
 *    boa notícia, é ausência de contagem" (decisão 7), e um zero sem a data é
 *    mentira. É o mês `-2`.
 *
 * Mais um terceiro, que não estava pedido e que a decisão 7 descreve: um mês
 * com o **líquido dos ajustes positivo**, onde o rótulo passa a "excedente de
 * contagem" em vez de desperdício negativo. É o mês `-3`.
 *
 * ## A identidade fecha por construção, não por sorte
 *
 * O servidor afirma, ao cêntimo:
 * `stock_change_eur == purchases_eur − goods_consumed_eur − unknown_shrinkage_eur`.
 * Aqui ela não é somada a partir de três números escolhidos à mão: os três
 * termos são gerados e a variação é **derivada** deles, em aritmética de
 * inteiros (cêntimos, como manda o `decimal.ts`). Em `number` com casas
 * decimais, `0.1 + 0.2` dava `0.30000000000000004` e a afirmação mais visível
 * do ecrã não fechava à vista — que é precisamente o defeito que a ADR 0013
 * manda tratar como teste e não como frase.
 *
 * ## De onde vêm os números
 *
 * De um **gerador determinístico por dia de negócio**: um padrão por dia da
 * semana (numa pastelaria o sábado e o domingo são o dobro da segunda), um
 * jitter de ±7% derivado de um hash do dia, e entregas de fornecedor às
 * segundas, quartas e sextas. Determinístico e não aleatório por uma razão
 * concreta: com `Math.random()` o painel mudava de números a cada pedido, e o
 * mesmo ecrã mostrado duas vezes ao dono contaria duas histórias.
 *
 * **Duas coisas vêm do ledger a sério** (`ledger.ts`), e não do gerador:
 *
 *  - o **valor de stock**, calculado como o ecrã Stock o calcula. Um painel que
 *    diz "valor de stock: 1 480 €" ao lado de um ecrã de Stock que diz outra
 *    coisa perde a credibilidade antes de alguém olhar para o resto;
 *  - o **desperdício dos últimos 7 dias**, movimento a movimento e por motivo,
 *    que é o que faz o "deitado fora hoje" do painel ser **o mesmo número** do
 *    contador do ecrã Alertas. O gerador só produz desperdício em dias com mais
 *    de 7 dias, onde o ledger não tem nada.
 *
 * O preço está dito: num período de 30 dias ou num mês fechado, o desperdício é
 * gerado e não existe no ledger — logo não há como abrir o movimento. E o valor
 * de stock é sempre o **de hoje**, também para um mês fechado, porque o fixture
 * não tem histórico de valorização; o servidor real tem-no, pelo `unit_cost`
 * gravado em cada movimento (ADR 0014).
 *
 * Apagabilidade: no dia em que o Django servir `/api/v1/reporting/*`, apaga-se
 * este ficheiro e a sua linha no `servidor.ts`.
 */

/* ---------------------------------------------------------------------------
 * Aritmética de cêntimos e de repartições.
 * ------------------------------------------------------------------------- */

/**
 * Reparte um total de cêntimos por pesos, **sem perder nem inventar um
 * cêntimo**: o resto da divisão vai para a maior parcela (convenção do maior
 * resto).
 *
 * Existe porque uma repartição que não soma ao total é a forma mais fácil de o
 * ecrã mentir sem ninguém dar por isso: os cinco motivos de desperdício têm de
 * somar o `waste_eur` que está na linha acima deles.
 */
function repartir(total: number, pesos: readonly number[]): number[] {
  const somaDosPesos = pesos.reduce((soma, peso) => soma + peso, 0);
  if (somaDosPesos === 0 || total === 0) return pesos.map(() => 0);

  const partes = pesos.map((peso) => Math.trunc((total * peso) / somaDosPesos));
  const resto = total - partes.reduce((soma, parte) => soma + parte, 0);
  let maior = 0;
  pesos.forEach((peso, indice) => {
    if (peso > (pesos.at(maior) ?? 0)) maior = indice;
  });
  return partes.map((parte, indice) => (indice === maior ? parte + resto : parte));
}

/** `0.350` — a fração que o contrato chama `share`, em milésimos. */
function share(parte: number, todo: number): string {
  if (todo === 0) return "0.000";
  return stringDeMilesimos(Math.round((parte * 1000) / todo));
}

/** `"31.4"` — pontos percentuais com uma casa, de uma divisão de cêntimos. */
function pontosPercentuais(parte: number, base: number): string | null {
  // `null` e não `"0.0"`: sem vendas o rácio **não existe**, e um zero lê-se
  // como "a mercadoria não custou nada" (ADR 0013: `None` quando vendas == 0).
  if (base === 0) return null;
  const decimos = Math.round((parte * 1000) / base);
  const sinal = decimos < 0 ? "-" : "";
  const absoluto = Math.abs(decimos);
  return `${sinal}${String(Math.trunc(absoluto / 10))}.${String(absoluto % 10)}`;
}

/* ---------------------------------------------------------------------------
 * O dia de negócio: a fronteira de tudo neste painel (ADR 0013, decisão 8).
 *
 * O mês é `[dia 1 às 04:00, dia 1 do mês seguinte às 04:00)`, logo uma venda
 * das 02:00 de 1 de maio é de abril — e o invariante que isso compra é
 * `Σ(dias de negócio do mês) == mês`. Com a fronteira do dia às 04:00 e a do
 * mês à meia-noite, as barras diárias deixavam de somar o total mensal, e um
 * gráfico cujas barras não somam o número ao lado perde credibilidade mais
 * depressa do que um sinal trocado.
 * ------------------------------------------------------------------------- */

const INICIO_DO_DIA_EM_HORAS = Number(INICIO_DO_DIA.slice(0, 2));

/** O instante em que o dia de negócio de uma data civil começa. */
function diaDeNegocio(ano: number, mes: number, dia: number): Date {
  return new Date(ano, mes, dia, INICIO_DO_DIA_EM_HORAS, 0, 0, 0);
}

function diaSeguinte(data: Date): Date {
  const proximo = new Date(data.getTime());
  proximo.setDate(proximo.getDate() + 1);
  return proximo;
}

/** O dia de negócio corrente — o último que tem dados. */
function hoje(): Date {
  return inicioDoDiaDeNegocio();
}

/**
 * `"2026-10"` — o mês de negócio corrente.
 *
 * Derivado do **dia de negócio** e não do dia civil: antes das 04:00 ainda se
 * está no dia anterior, e no dia 1 isso muda o mês (ADR 0013, decisão 8). É a
 * mesma fronteira em todo o painel, e é esse o invariante.
 */
function mesDeHoje(): string {
  const dia = hoje();
  return `${String(dia.getFullYear())}-${String(dia.getMonth() + 1).padStart(2, "0")}`;
}

/**
 * Os dias de negócio de uma janela, **sem nunca passar do dia corrente**.
 *
 * Um mês a correr não tem dados no futuro, e gerar vendas para os dias que
 * ainda não aconteceram é a mentira mais inútil que um fixture pode contar: o
 * dono olha para o dia 20 no gráfico, sabe que ainda é dia 6, e deixa de
 * acreditar no resto do ecrã.
 */
function diasDaJanela(since: Date, until: Date): Date[] {
  const limite = Math.min(until.getTime(), diaSeguinte(hoje()).getTime());
  const dias: Date[] = [];
  for (let dia = new Date(since.getTime()); dia.getTime() < limite; dia = diaSeguinte(dia)) {
    dias.push(new Date(dia.getTime()));
  }
  return dias;
}

/** Um ordinal estável por dia civil, para o hash do jitter. */
function ordinal(data: Date): number {
  return data.getFullYear() * 372 + data.getMonth() * 31 + data.getDate();
}

/**
 * Jitter determinístico de ±7%, em milésimos.
 *
 * Determinístico e não aleatório: o painel tem de contar a mesma história duas
 * vezes seguidas. Sete por cento porque é o que faz uma semana parecer uma
 * semana — com todos os dias iguais, o gráfico de barras parece um erro de
 * renderização.
 */
function jitter(data: Date): number {
  return 1000 + ((ordinal(data) * 7919) % 141) - 70;
}

function comJitter(base: number, data: Date): number {
  return Math.round((base * jitter(data)) / 1000);
}

/* ---------------------------------------------------------------------------
 * Os modos de mês — os dois modos de falha que a ADR exige, mais o excedente.
 * ------------------------------------------------------------------------- */

type ModoDoMes = "normal" | "stock_up" | "sem_contagem" | "excedente";

/**
 * Quantos meses separam esta data do mês corrente. `0` é este mês, `-1` o
 * anterior.
 */
function desvioDoMes(data: Date): number {
  const agora = hoje();
  return (data.getFullYear() - agora.getFullYear()) * 12 + (data.getMonth() - agora.getMonth());
}

/**
 * O modo de cada mês, por desvio e não por data fixa: uma data congelada mata a
 * credibilidade no primeiro ecrã (guião da sessão 0, §2), e um "stock-up em
 * dezembro de 2025" deixava de ser alcançável a partir de fevereiro.
 */
const MODO_POR_DESVIO = new Map<number, ModoDoMes>([
  [0, "normal"],
  // O mês anterior é o do stock-up: está a um toque no seletor de período
  // (`prev_month`) e é o caso que a ADR nomeia como o maior risco de leitura.
  [-1, "stock_up"],
  // Dois meses atrás ninguém contou: a quebra desconhecida vem a zero e a data
  // da última contagem é de três meses atrás.
  [-2, "sem_contagem"],
  // Três meses atrás a contagem encontrou **mais** do que o sistema dizia.
  [-3, "excedente"],
]);

function modoDoMes(data: Date): ModoDoMes {
  return MODO_POR_DESVIO.get(desvioDoMes(data)) ?? "normal";
}

/** Contou-se neste dia? A contagem é no dia 1, e não há nos meses sem contagem. */
function temContagem(data: Date): boolean {
  return data.getDate() === 1 && modoDoMes(data) !== "sem_contagem";
}

/**
 * A última contagem **antes** do fim desta janela, ou `null` se nunca houve.
 *
 * Caminha para trás dia a dia e não calcula: a regra de qual mês tem contagem é
 * a do `temContagem`, e duas versões dela divergiam no mês em que isso
 * importasse. Treze meses de horizonte, que é mais do que qualquer janela do
 * painel.
 */
function ultimaContagemAntesDe(until: Date): string | null {
  const limite = Math.min(until.getTime(), diaSeguinte(hoje()).getTime());
  for (let passo = 0; passo < 400; passo += 1) {
    const dia = new Date(limite);
    dia.setDate(dia.getDate() - passo);
    const inicio = diaDeNegocio(dia.getFullYear(), dia.getMonth(), dia.getDate());
    if (inicio.getTime() >= limite) continue;
    if (!temContagem(inicio)) continue;
    // A contagem é às 07:00: depois da produção da manhã e antes de o balcão
    // abrir, que é quando se conta de facto numa pastelaria.
    const contagem = new Date(inicio.getTime());
    contagem.setHours(7, 0, 0, 0);
    return contagem.toISOString();
  }
  return null;
}

/* ---------------------------------------------------------------------------
 * O gerador de um dia de negócio.
 * ------------------------------------------------------------------------- */

interface DiaDoPainel {
  readonly vendasBrutas: number;
  readonly vendasLiquidas: number;
  readonly compras: number;
  readonly comprasSemFatura: number;
  /** Consumo **sem** o desperdício: o desperdício soma-se por cima. */
  readonly consumoBase: number;
  readonly desperdicio: ReadonlyMap<MotivoDeQuebra, number>;
  /** Positivo = quebra; negativo = excedente de contagem. */
  readonly quebraDesconhecida: number;
}

const DIA_VAZIO: DiaDoPainel = {
  vendasBrutas: 0,
  vendasLiquidas: 0,
  compras: 0,
  comprasSemFatura: 0,
  consumoBase: 0,
  desperdicio: new Map(),
  quebraDesconhecida: 0,
};

/**
 * Vendas brutas por dia da semana, em cêntimos.
 *
 * O padrão é de pastelaria e não de restaurante: o fim de semana é o dobro da
 * segunda, e a segunda é o dia fraco. Serve o gráfico de barras — com um padrão
 * plano não há "qual é o pior dia" para perguntar, que é a pergunta que o
 * gráfico existe para responder.
 */
const VENDAS_POR_DIA_DA_SEMANA = new Map<number, number>([
  [0, 134_000],
  [1, 68_000],
  [2, 74_000],
  [3, 76_000],
  [4, 79_000],
  [5, 96_000],
  [6, 128_000],
]);

/**
 * Entregas de fornecedor: segunda, quarta e sexta. Em cêntimos.
 *
 * A soma da semana é propositadamente **próxima do consumo da semana**, e isso
 * não é estética: num mês normal a variação de stock tem de ficar perto de zero
 * (±200 €, o jitter), senão o mês do stock-up deixa de se distinguir de
 * qualquer outro e o ecrã perde a afirmação que a ADR 0013 lhe manda fazer. Um
 * negócio que compra sistematicamente 30% mais do que consome não existe: ou a
 * despensa cresce sem fim, ou os números estão errados.
 */
const COMPRAS_POR_DIA_DA_SEMANA = new Map<number, number>([
  [1, 60_000],
  [3, 55_000],
  [5, 70_000],
]);

/**
 * A taxa de IVA **misturada** que este fixture usa para derivar o líquido do
 * bruto: 9,5%.
 *
 * É uma simplificação do fixture e está dita como tal. Numa pastelaria há 6%
 * (pão, leite), 13% (restauração) e 23% (bebidas) na mesma venda, e por isso a
 * ADR 0013 decide que o IVA se guarda **por taxa** na linha de venda
 * (`sales_saleline`): o bruto não se reparte para trás. No servidor real o
 * líquido é a soma dos `net_eur` das linhas; aqui é uma divisão, porque não há
 * linhas.
 */
const MILESIMOS_COM_IVA = 1095;

const PESO_DO_MOTIVO: readonly { readonly motivo: MotivoDeQuebra; readonly peso: number }[] = [
  { motivo: "expired", peso: 44 },
  { motivo: "spoiled", peso: 20 },
  { motivo: "prep_loss", peso: 18 },
  { motivo: "breakage", peso: 12 },
  { motivo: "other", peso: 6 },
];

/** Quantos dias para trás o ledger a sério cobre. Ver o bloco do topo. */
const HORIZONTE_DO_LEDGER_EM_DIAS = 7;

function dentroDoHorizonteDoLedger(dia: Date): boolean {
  const limite = new Date(hoje().getTime());
  limite.setDate(limite.getDate() - (HORIZONTE_DO_LEDGER_EM_DIAS - 1));
  return dia.getTime() >= limite.getTime();
}

/**
 * O desperdício de um dia **do ledger a sério**, por motivo e em cêntimos.
 *
 * É a mesma leitura que o `alertas.ts` faz para o contador "deitado fora hoje",
 * e é por isso que os dois ecrãs mostram o mesmo número: há uma fonte só.
 */
function desperdicioDoLedger(dia: Date): Map<MotivoDeQuebra, number> {
  const fim = diaSeguinte(dia).getTime();
  const centimosPorMotivo = new Map<MotivoDeQuebra, number>();

  for (const mov of ledger()) {
    if (mov.tipo !== "waste" || mov.motivo === null) continue;
    const quando = new Date(mov.quando).getTime();
    if (quando < dia.getTime() || quando >= fim) continue;
    const artigo = artigoDe(mov.artigo);
    if (artigo === undefined) continue;
    const anterior = centimosPorMotivo.get(mov.motivo) ?? 0;
    centimosPorMotivo.set(mov.motivo, anterior + centimosDoArtigo(artigo, mov.milesimos));
  }

  return centimosPorMotivo;
}

/** O desperdício gerado de um dia antigo: ~2,6% do consumo, por motivo. */
function desperdicioGerado(consumoBase: number, dia: Date): Map<MotivoDeQuebra, number> {
  const total = comJitter(Math.round((consumoBase * 26) / 1000), dia);
  const partes = repartir(
    total,
    PESO_DO_MOTIVO.map((entrada) => entrada.peso),
  );
  const porMotivo = new Map<MotivoDeQuebra, number>();
  PESO_DO_MOTIVO.forEach((entrada, indice) => {
    const valor = partes.at(indice) ?? 0;
    if (valor > 0) porMotivo.set(entrada.motivo, valor);
  });
  return porMotivo;
}

function somar(valores: Iterable<number>): number {
  let total = 0;
  for (const valor of valores) total += valor;
  return total;
}

/** Um dia de negócio, inteiro. Dias no futuro vêm vazios. */
function diaDoPainel(dia: Date): DiaDoPainel {
  if (dia.getTime() > hoje().getTime()) return DIA_VAZIO;

  const semana = dia.getDay();
  const modo = modoDoMes(dia);

  const vendasBrutas = comJitter(VENDAS_POR_DIA_DA_SEMANA.get(semana) ?? 0, dia);
  const vendasLiquidas = Math.round((vendasBrutas * 1000) / MILESIMOS_COM_IVA);

  const comprasBase = COMPRAS_POR_DIA_DA_SEMANA.get(semana) ?? 0;
  // O stock-up: enche-se a despensa, e é o gesto que o dono tem de reconhecer
  // em vez de ler um prejuízo. +25% nas compras de um mês inteiro leva a
  // variação de stock de ±200 € (o jitter de um mês normal) a mais de 2 000 €
  // positivos — uma ordem de grandeza acima do ruído, que é o que faz a linha
  // "encheu-se a despensa" ser uma afirmação e não uma flutuação.
  const compras = comJitter(
    modo === "stock_up" ? Math.round((comprasBase * 125) / 100) : comprasBase,
    dia,
  );
  // A guia de remessa a fim de mês: mercadoria que entrou sem preço e cuja
  // fatura ainda não chegou. Só nos últimos dias, porque é essa a prática —
  // entra ao último preço conhecido e a diferença fica à vista, em
  // `purchases_awaiting_invoice_eur` (ADR 0013, decisão 8).
  const comprasSemFatura = dentroDoHorizonteDoLedger(dia)
    ? Math.round((compras * 35) / 100)
    : 0;

  const consumoBase = comJitter(Math.round((vendasLiquidas * 290) / 1000), dia);

  const desperdicio = dentroDoHorizonteDoLedger(dia)
    ? desperdicioDoLedger(dia)
    : desperdicioGerado(consumoBase, dia);

  // A quebra desconhecida só existe no dia em que se contou: é o líquido dos
  // `adjustment` daquela contagem, e sem contagem é **ausência** e não zero.
  const quebraDesconhecida = temContagem(dia)
    ? modo === "excedente"
      ? -comJitter(3_100, dia)
      : comJitter(2_600, dia)
    : 0;

  return {
    vendasBrutas,
    vendasLiquidas,
    compras,
    comprasSemFatura,
    consumoBase,
    desperdicio,
    quebraDesconhecida,
  };
}

/* ---------------------------------------------------------------------------
 * Agregação de uma janela.
 * ------------------------------------------------------------------------- */

interface AgregadoDaJanela {
  readonly dias: readonly Date[];
  readonly vendasBrutas: number;
  readonly vendasLiquidas: number;
  readonly compras: number;
  readonly comprasSemFatura: number;
  readonly desperdicioPorMotivo: ReadonlyMap<MotivoDeQuebra, number>;
  readonly desperdicio: number;
  readonly consumo: number;
  readonly quebraDesconhecida: number;
  /** Derivada, nunca escolhida: é a identidade da decisão 4. */
  readonly variacaoDeStock: number;
}

function agregar(since: Date, until: Date): AgregadoDaJanela {
  const dias = diasDaJanela(since, until);
  const desperdicioPorMotivo = new Map<MotivoDeQuebra, number>();
  let vendasBrutas = 0;
  let vendasLiquidas = 0;
  let compras = 0;
  let comprasSemFatura = 0;
  let consumoBase = 0;
  let quebraDesconhecida = 0;

  for (const dia of dias) {
    const valores = diaDoPainel(dia);
    vendasBrutas += valores.vendasBrutas;
    vendasLiquidas += valores.vendasLiquidas;
    compras += valores.compras;
    comprasSemFatura += valores.comprasSemFatura;
    consumoBase += valores.consumoBase;
    quebraDesconhecida += valores.quebraDesconhecida;
    for (const [motivo, centimos] of valores.desperdicio) {
      desperdicioPorMotivo.set(motivo, (desperdicioPorMotivo.get(motivo) ?? 0) + centimos);
    }
  }

  const desperdicio = somar(desperdicioPorMotivo.values());
  // O desperdício **está dentro** da mercadoria consumida (ADR 0014): é
  // decomposição e nunca parcela a somar. Se estivesse fora, o balanço de stock
  // não fechava.
  const consumo = consumoBase + desperdicio;

  return {
    dias,
    vendasBrutas,
    vendasLiquidas,
    compras,
    comprasSemFatura,
    desperdicioPorMotivo,
    desperdicio,
    consumo,
    quebraDesconhecida,
    // A identidade, **derivada** e não escolhida:
    // variação = compras − consumo − quebra desconhecida.
    variacaoDeStock: compras - consumo - quebraDesconhecida,
  };
}

/** O valor de stock de hoje, calculado como o ecrã Stock o calcula. */
function valorDeStockEmCentimos(): number {
  const porArtigo = somarPorArtigoELoja(todasAsLojas());
  let centimos = 0;
  for (const [numero, porLoja] of porArtigo) {
    const artigo = artigoDe(numero);
    if (artigo === undefined) continue;
    const total = somar(porLoja.values());
    if (total <= 0) continue;
    centimos += centimosDe(total, decimilesimosDe(artigo.custoUnitario));
  }
  return centimos;
}

/* ---------------------------------------------------------------------------
 * Resolução do período.
 * ------------------------------------------------------------------------- */

interface Janela {
  readonly since: Date;
  readonly until: Date;
}

function inicioDoMes(data: Date): Date {
  return diaDeNegocio(data.getFullYear(), data.getMonth(), 1);
}

function inicioDoMesSeguinte(data: Date): Date {
  return diaDeNegocio(data.getFullYear(), data.getMonth() + 1, 1);
}

function janelaDoPeriodo(periodo: Periodo): Janela {
  const agora = hoje();
  const amanha = diaSeguinte(agora);

  if (periodo === "today") return { since: agora, until: amanha };
  if (periodo === "7d" || periodo === "30d") {
    const since = new Date(agora.getTime());
    since.setDate(since.getDate() - (periodo === "7d" ? 6 : 29));
    return { since, until: amanha };
  }
  if (periodo === "month") {
    return { since: inicioDoMes(agora), until: inicioDoMesSeguinte(agora) };
  }
  const mesAnterior = diaDeNegocio(agora.getFullYear(), agora.getMonth() - 1, 1);
  return { since: mesAnterior, until: inicioDoMes(agora) };
}

function periodoResolvido(periodo: Periodo, janela: Janela): PeriodoResolvido {
  return {
    key: periodo,
    since: janela.since.toISOString(),
    // A fronteira do mês **ecoa o mês**, mesmo num mês a correr: é a janela que
    // o número representa, e mostrar "até hoje" escondia que falta mês. O que
    // diz o que já decorreu são os `days_elapsed`/`days_in_month` do `/month`.
    until: janela.until.toISOString(),
    business_day_starts_at: INICIO_DO_DIA,
  };
}

/* ---------------------------------------------------------------------------
 * Qualidade dos dados — o bloco que declara o que o painel não sabe.
 * ------------------------------------------------------------------------- */

function qualidadeDosDados(
  agregado: AgregadoDaJanela,
  janela: Janela,
): QualidadeDosDados {
  return {
    // Com consumo a zero o painel mostraria 85% de margem, e um painel
    // optimista por omissão destrói a confiança mais depressa do que um
    // prejuízo falso (ADR 0013, decisão 7).
    consumption_registered: agregado.consumo > 0,
    purchases_awaiting_invoice_eur: stringDeCentimos(agregado.comprasSemFatura),
    last_count_at: ultimaContagemAntesDe(janela.until),
    revenue_source: agregado.vendasBrutas > 0 ? "manual" : "none",
  };
}

/* ---------------------------------------------------------------------------
 * As parcelas de custo. O servidor decide o que soma e quem contém quem.
 * ------------------------------------------------------------------------- */

interface ParcelaCrua {
  readonly id: IdDeCusto;
  readonly centimos: number;
  readonly soma: boolean;
  readonly dentroDe: IdDeCusto | null;
}

/**
 * Transforma as parcelas cruas na lista do contrato.
 *
 * O `share` tem o **maior componente** como denominador, e não um total: o
 * `summary` não tem total de gastos de propósito (decisão 6 — um total com
 * mercadoria discriminada dá a folha salarial por subtracção), logo um share
 * sobre um total seria uma divisão por um número que não viaja. A ADR fixa o
 * denominador do `share` só para os pontos de série; esta escolha está no
 * relatório como lacuna do contrato.
 */
function componentesDeCusto(parcelas: readonly ParcelaCrua[]): ComponenteDeCusto[] {
  const maior = parcelas.reduce((maximo, parcela) => Math.max(maximo, Math.abs(parcela.centimos)), 0);
  return parcelas.map((parcela) => ({
    id: parcela.id,
    amount_eur: stringDeCentimos(parcela.centimos),
    share: share(Math.abs(parcela.centimos), maior),
    is_part_of_total: parcela.soma,
    part_of: parcela.dentroDe,
  }));
}

function desperdicioPorMotivo(agregado: AgregadoDaJanela): DesperdicioPorMotivo[] {
  const movimentosPorMotivo = contarMovimentosDeDesperdicio(agregado.dias);

  return (
    [...agregado.desperdicioPorMotivo.entries()]
      .filter(([, centimos]) => centimos > 0)
      // Ordenada **pelo servidor**, a maior parcela primeiro: no gráfico de
      // barras é a ordem que diz a grandeza, e uma segunda ordenação no cliente
      // seria uma segunda definição de "maior". Ordena-se em cêntimos e só
      // depois se formata — ordenar strings de decimal dava "9.00" acima de
      // "48.00".
      .sort(([, a], [, b]) => b - a)
      .map(([motivo, centimos]) => ({
        reason: motivo,
        amount_eur: stringDeCentimos(centimos),
        share: share(centimos, agregado.desperdicio),
        movements: movimentosPorMotivo.get(motivo) ?? 1,
      }))
  );
}

/**
 * Quantos movimentos por motivo. Do ledger quando ele cobre os dias; estimado
 * em um movimento por dia com desperdício quando não cobre — e isso está dito
 * no bloco do topo deste ficheiro, porque um número de movimentos que não tem
 * movimentos atrás não se pode abrir.
 */
function contarMovimentosDeDesperdicio(dias: readonly Date[]): Map<MotivoDeQuebra, number> {
  const contagem = new Map<MotivoDeQuebra, number>();
  for (const dia of dias) {
    const porMotivo = dentroDoHorizonteDoLedger(dia)
      ? desperdicioDoLedger(dia)
      : desperdicioGerado(diaDoPainel(dia).consumoBase, dia);
    for (const [motivo, centimos] of porMotivo) {
      if (centimos <= 0) continue;
      contagem.set(motivo, (contagem.get(motivo) ?? 0) + 1);
    }
  }
  return contagem;
}

/* ---------------------------------------------------------------------------
 * `GET /reporting/summary`
 * ------------------------------------------------------------------------- */

function resumoDoPeriodo(periodo: Periodo): ResumoDoPeriodo {
  const janela = janelaDoPeriodo(periodo);
  const agregado = agregar(janela.since, janela.until);

  return {
    period: periodoResolvido(periodo, janela),
    revenue_net_eur: stringDeCentimos(agregado.vendasLiquidas),
    revenue_gross_eur: stringDeCentimos(agregado.vendasBrutas),
    // O dono diz "fiz 1 800 € ontem" e esse número é **com** IVA, porque é o
    // fecho de caixa: é o bruto que está registado e o líquido que é derivado.
    revenue_basis: "gross",
    purchases_eur: stringDeCentimos(agregado.compras),
    goods_consumed_eur: stringDeCentimos(agregado.consumo),
    stock_change_eur: stringDeCentimos(agregado.variacaoDeStock),
    waste_eur: stringDeCentimos(agregado.desperdicio),
    unknown_shrinkage_eur: stringDeCentimos(agregado.quebraDesconhecida),
    goods_cost_ratio_pct: pontosPercentuais(agregado.consumo, agregado.vendasLiquidas),
    stock_value_eur: stringDeCentimos(valorDeStockEmCentimos()),
    costs: componentesDeCusto([
      {
        id: "goods_consumed",
        centimos: agregado.consumo,
        soma: true,
        dentroDe: null,
      },
      // Dentro da mercadoria consumida, e por isso **não soma**: é
      // decomposição. "Dos quais 420 € foram desperdício."
      { id: "waste", centimos: agregado.desperdicio, soma: false, dentroDe: "goods_consumed" },
      { id: "unknown_shrinkage", centimos: agregado.quebraDesconhecida, soma: true, dentroDe: null },
      // As compras não somam com o consumo: são a **outra** base de custo, e
      // somá-las contava a mesma mercadoria duas vezes.
      { id: "purchases", centimos: agregado.compras, soma: false, dentroDe: null },
    ]),
    waste_by_reason: desperdicioPorMotivo(agregado),
    data_quality: qualidadeDosDados(agregado, janela),
  };
}

/* ---------------------------------------------------------------------------
 * `GET /reporting/series`
 * ------------------------------------------------------------------------- */

/** `day` para janelas curtas, `week` para as longas. Derivada pelo servidor. */
function granularidadeDe(periodo: Periodo): "day" | "week" {
  return periodo === "today" || periodo === "7d" ? "day" : "week";
}

function intervalosDa(janela: Janela, granularidade: "day" | "week"): Janela[] {
  const dias = diasDaJanela(janela.since, janela.until);
  if (granularidade === "day") {
    return dias.map((dia) => ({ since: dia, until: diaSeguinte(dia) }));
  }

  const intervalos: Janela[] = [];
  for (let indice = 0; indice < dias.length; indice += 7) {
    const since = dias.at(indice);
    if (since === undefined) continue;
    const ultimo = dias.at(Math.min(indice + 6, dias.length - 1));
    intervalos.push({ since, until: diaSeguinte(ultimo ?? since) });
  }
  return intervalos;
}

/** O máximo do eixo, arredondado para cima a um passo legível. */
function escalaDe(valores: readonly number[]): number {
  const maior = valores.reduce((maximo, valor) => Math.max(maximo, valor), 0);
  if (maior === 0) return 0;
  const passo = maior >= 100_000 ? 10_000 : 5_000;
  return Math.ceil(maior / passo) * passo;
}

function seriesDoPeriodo(periodo: Periodo): SeriesDoPeriodo {
  const janela = janelaDoPeriodo(periodo);
  const granularidade = granularidadeDe(periodo);
  const intervalos = intervalosDa(janela, granularidade);

  const porIntervalo = intervalos.map((intervalo) => agregar(intervalo.since, intervalo.until));
  const vendas = porIntervalo.map((agregado) => agregado.vendasLiquidas);
  const compras = porIntervalo.map((agregado) => agregado.compras);
  const escala = escalaDe([...vendas, ...compras]);

  const pontos = (valores: readonly number[]): PontoDaSerie[] =>
    valores.map((valor) => ({
      value_eur: stringDeCentimos(valor),
      // `share = value / scale_max`, e é este campo que torna o desenho do
      // gráfico uma multiplicação: sem ele o cliente procurava o máximo e
      // dividia euros em `number` (ADR 0013, decisão 5).
      share: share(valor, escala),
    }));

  const buckets: Intervalo[] = intervalos.map((intervalo) => ({
    since: intervalo.since.toISOString(),
    until: intervalo.until.toISOString(),
  }));

  const series: Serie[] = [
    {
      id: "revenue",
      unit: "eur",
      total_eur: stringDeCentimos(somar(vendas)),
      points: pontos(vendas),
    },
    {
      id: "purchases",
      unit: "eur",
      total_eur: stringDeCentimos(somar(compras)),
      points: pontos(compras),
    },
  ];

  return {
    period: periodoResolvido(periodo, janela),
    granularity: granularidade,
    buckets,
    scale_max_eur: stringDeCentimos(escala),
    series,
  };
}

/* ---------------------------------------------------------------------------
 * `GET /reporting/month` — o fecho, com salários. Só do dono.
 * ------------------------------------------------------------------------- */

/**
 * A equipa da Pastelaria Aurora, por **cargo** — que não é o papel de acesso
 * (ADR 0013, decisão 2).
 *
 * Os brutos são de uma pastelaria pequena em 2026 e os ids são uuid estáveis,
 * para um link a um mês continuar a valer entre reinícios.
 */
const CARGOS: readonly {
  readonly id: string;
  readonly nome: string;
  readonly pessoas: number;
  readonly brutoMensal: number;
}[] = [
  { id: "ca7a0000-0000-4000-8000-000000000001", nome: "Pasteleiro", pessoas: 1, brutoMensal: 125_000 },
  { id: "ca7a0000-0000-4000-8000-000000000002", nome: "Balcão", pessoas: 2, brutoMensal: 184_000 },
  { id: "ca7a0000-0000-4000-8000-000000000003", nome: "Ajudante de cozinha", pessoas: 1, brutoMensal: 87_000 },
];

/**
 * O custo-empresa do mês, parcela a parcela — e **não** uma flag por subsídio.
 *
 * Os subsídios de férias e de Natal entram em **duodécimos** (2/12 do bruto),
 * independentemente de como são pagos: senão junho e novembro parecem
 * catástrofes e os outros dez meses parecem bons (ADR 0013, decisão 2). A TSU
 * (23,75%) e o seguro de acidentes (1,25%) incidem sobre o bruto mais os
 * duodécimos. O subsídio de alimentação é 5,50 € × 22 dias × 3,5 FTE e entra
 * **por inteiro**: o v1 não calcula a TSU sobre o excesso acima do limite legal
 * de isenção, e a ADR orçamenta esse erro (é 23,75% *do excesso*, zero para
 * quem paga até ao limite).
 *
 * O que fica **fora**, de propósito: o IRS retido e os 11% de TSU do
 * trabalhador, que já estão dentro do bruto — somá-los inflacionava o custo em
 * ~11%.
 */
function salariosDoMes() {
  const bruto = CARGOS.reduce((soma, cargo) => soma + cargo.brutoMensal, 0);
  const duodecimos = Math.round((bruto * 2) / 12);
  const base = bruto + duodecimos;
  const tsu = Math.round((base * 2375) / 10_000);
  const seguro = Math.round((base * 125) / 10_000);
  const alimentacao = Math.round((550 * 22 * 35) / 10);
  const total = bruto + duodecimos + tsu + seguro + alimentacao;

  return {
    total,
    parcelas: [
      { id: "base" as const, centimos: bruto },
      { id: "subsidies" as const, centimos: duodecimos },
      { id: "social_security" as const, centimos: tsu },
      { id: "insurance" as const, centimos: seguro },
      { id: "meal_allowance" as const, centimos: alimentacao },
    ],
  };
}

/**
 * Os custos fixos mensais, que vivem em `purchasing_othercost` (ADR 0013,
 * decisão 3) e são a condição para a palavra "resultado" ser defensável.
 */
const OUTROS_CUSTOS: readonly {
  readonly categoria:
    | "rent"
    | "energy"
    | "water"
    | "gas"
    | "card_fees"
    | "licences"
    | "accounting";
  readonly centimos: number;
  readonly nota: string | null;
}[] = [
  { categoria: "rent", centimos: 85_000, nota: "Loja Centro e Cozinha" },
  { categoria: "energy", centimos: 42_000, nota: null },
  { categoria: "water", centimos: 4_800, nota: null },
  { categoria: "gas", centimos: 9_500, nota: null },
  { categoria: "card_fees", centimos: 11_200, nota: "1,1% sobre o que passou no TPA" },
  { categoria: "licences", centimos: 3_500, nota: null },
  { categoria: "accounting", centimos: 15_000, nota: null },
];

/**
 * O mês pedido, validado pelo **schema do contrato** e não por um regex local.
 *
 * É o mesmo mecanismo que a decisão 3 da ADR 0008 celebra para as respostas,
 * aplicado ao pedido: um parâmetro que este servidor aceitasse e o serializer
 * recusasse era uma forma de dados que só existe em desenvolvimento.
 */
function mesValido(mes: string): boolean {
  return mesSchema.safeParse(mes).success;
}

function janelaDoMes(mes: string): Janela {
  const [ano, numeroDoMes] = mes.split("-").map(Number);
  const since = diaDeNegocio(ano ?? 0, (numeroDoMes ?? 1) - 1, 1);
  return { since, until: inicioDoMesSeguinte(since) };
}

function diasDoMes(since: Date): number {
  return new Date(since.getFullYear(), since.getMonth() + 1, 0).getDate();
}

function fechoDoMes(mes: string): FechoDoMes {
  const janela = janelaDoMes(mes);
  const agregado = agregar(janela.since, janela.until);
  const salarios = salariosDoMes();
  const outros = OUTROS_CUSTOS.reduce((soma, custo) => soma + custo.centimos, 0);

  const fechado = janela.until.getTime() <= hoje().getTime();
  const dias = diasDoMes(janela.since);
  const decorridos = Math.min(agregado.dias.length, dias);

  // Um mês sem nada (anterior ao negócio, ou no futuro) não tem salários nem
  // custos fixos: inventá-los era pôr despesa num mês que não existiu.
  const comAtividade = agregado.vendasBrutas > 0 || agregado.compras > 0;
  const pessoal = comAtividade ? salarios.total : 0;
  const custosFixos = comAtividade ? outros : 0;

  // O total é do **servidor**, e é a razão pela qual ele só existe aqui: com
  // mercadoria discriminada e um total, a folha salarial sai por subtracção
  // (ADR 0013, decisão 6).
  const totalDeGastos = agregado.consumo + agregado.quebraDesconhecida + pessoal + custosFixos;
  const resultado = agregado.vendasLiquidas - totalDeGastos;

  const pesosDosCargos = CARGOS.map((cargo) => cargo.brutoMensal);
  const porCargo = repartir(pessoal, pesosDosCargos);

  return {
    month: mes,
    since: janela.since.toISOString(),
    until: janela.until.toISOString(),
    business_day_starts_at: INICIO_DO_DIA,
    closed: fechado,
    days_elapsed: decorridos,
    days_in_month: dias,

    revenue_net_eur: stringDeCentimos(agregado.vendasLiquidas),
    revenue_gross_eur: stringDeCentimos(agregado.vendasBrutas),
    revenue_basis: "gross",
    purchases_eur: stringDeCentimos(agregado.compras),
    goods_consumed_eur: stringDeCentimos(agregado.consumo),
    stock_change_eur: stringDeCentimos(agregado.variacaoDeStock),
    waste_eur: stringDeCentimos(agregado.desperdicio),
    unknown_shrinkage_eur: stringDeCentimos(agregado.quebraDesconhecida),
    stock_value_eur: stringDeCentimos(valorDeStockEmCentimos()),

    payroll_eur: stringDeCentimos(pessoal),
    payroll_basis: "employer_cost",
    payroll_source: "contractual",
    payroll_breakdown: salarios.parcelas.map((parcela) => ({
      id: parcela.id,
      amount_eur: stringDeCentimos(comAtividade ? parcela.centimos : 0),
    })),
    roles: CARGOS.map((cargo, indice) => ({
      role_id: cargo.id,
      name: cargo.nome,
      headcount: cargo.pessoas,
      payroll_eur: stringDeCentimos(porCargo.at(indice) ?? 0),
      share: share(porCargo.at(indice) ?? 0, pessoal),
    })),
    other_costs: OUTROS_CUSTOS.map((custo) => ({
      category: custo.categoria,
      amount_eur: stringDeCentimos(comAtividade ? custo.centimos : 0),
      note: custo.nota,
    })),
    costs: componentesDeCusto([
      { id: "goods_consumed", centimos: agregado.consumo, soma: true, dentroDe: null },
      { id: "waste", centimos: agregado.desperdicio, soma: false, dentroDe: "goods_consumed" },
      { id: "unknown_shrinkage", centimos: agregado.quebraDesconhecida, soma: true, dentroDe: null },
      { id: "payroll", centimos: pessoal, soma: true, dentroDe: null },
      { id: "other", centimos: custosFixos, soma: true, dentroDe: null },
      { id: "purchases", centimos: agregado.compras, soma: false, dentroDe: null },
    ]),
    cost_total_eur: stringDeCentimos(totalDeGastos),
    result_eur: stringDeCentimos(resultado),
    // `owner_compensation` está sempre aqui porque a Sofia não se paga, que é a
    // prática do sector e a decisão do dono: o que ele tira é distribuição de
    // lucro e não despesa. A consequência — o rácio de pessoal deixa de ser
    // comparável com benchmarks — tem de ficar **visível** no ecrã.
    result_excludes: ["depreciation", "financing", "income_tax", "owner_compensation"],
    goods_cost_ratio_pct: pontosPercentuais(agregado.consumo, agregado.vendasLiquidas),
    labour_cost_ratio_pct: pontosPercentuais(pessoal, agregado.vendasLiquidas),
    prime_cost_pct: pontosPercentuais(agregado.consumo + pessoal, agregado.vendasLiquidas),
    data_quality: qualidadeDosDados(agregado, janela),
  };
}

/* ---------------------------------------------------------------------------
 * As variantes vazias — "o que aparece quando não há nada?" é uma pergunta da
 * sessão 0, logo o vazio é tanto produto como o painel cheio.
 *
 * E é aqui que o ramo mais importante da decisão 7 se vê: **sem consumo
 * registado o rácio de mercadoria não se renderiza**. O vazio não é só uma
 * lista sem linhas — é o painel a dizer o que falta registar.
 * ------------------------------------------------------------------------- */

const QUALIDADE_VAZIA: QualidadeDosDados = {
  consumption_registered: false,
  purchases_awaiting_invoice_eur: "0.00",
  last_count_at: null,
  revenue_source: "none",
};

function resumoVazio(periodo: Periodo): ResumoDoPeriodo {
  const janela = janelaDoPeriodo(periodo);
  return {
    period: periodoResolvido(periodo, janela),
    revenue_net_eur: "0.00",
    revenue_gross_eur: "0.00",
    revenue_basis: "gross",
    purchases_eur: "0.00",
    goods_consumed_eur: "0.00",
    stock_change_eur: "0.00",
    waste_eur: "0.00",
    unknown_shrinkage_eur: "0.00",
    goods_cost_ratio_pct: null,
    stock_value_eur: "0.00",
    costs: [],
    waste_by_reason: [],
    data_quality: QUALIDADE_VAZIA,
  };
}

function seriesVazias(periodo: Periodo): SeriesDoPeriodo {
  const janela = janelaDoPeriodo(periodo);
  return {
    period: periodoResolvido(periodo, janela),
    granularity: granularidadeDe(periodo),
    buckets: [],
    scale_max_eur: "0.00",
    series: [],
  };
}

function mesVazio(mes: string): FechoDoMes {
  const janela = janelaDoMes(mes);
  return {
    month: mes,
    since: janela.since.toISOString(),
    until: janela.until.toISOString(),
    business_day_starts_at: INICIO_DO_DIA,
    closed: janela.until.getTime() <= hoje().getTime(),
    days_elapsed: 0,
    days_in_month: diasDoMes(janela.since),
    revenue_net_eur: "0.00",
    revenue_gross_eur: "0.00",
    revenue_basis: "gross",
    purchases_eur: "0.00",
    goods_consumed_eur: "0.00",
    stock_change_eur: "0.00",
    waste_eur: "0.00",
    unknown_shrinkage_eur: "0.00",
    stock_value_eur: "0.00",
    payroll_eur: "0.00",
    payroll_basis: "employer_cost",
    payroll_source: "contractual",
    payroll_breakdown: [],
    roles: [],
    other_costs: [],
    costs: [],
    cost_total_eur: "0.00",
    result_eur: "0.00",
    result_excludes: ["depreciation", "financing", "income_tax", "owner_compensation"],
    goods_cost_ratio_pct: null,
    labour_cost_ratio_pct: null,
    prime_cost_pct: null,
    data_quality: QUALIDADE_VAZIA,
  };
}

/* ---------------------------------------------------------------------------
 * As rotas.
 * ------------------------------------------------------------------------- */

/**
 * O período pedido, validado pelo **schema do contrato**.
 *
 * Ausente é o default, como em toda esta API, e o default é `7d` — o mesmo que
 * o do ecrã, pela razão que está escrita no `routes/busca-do-painel.ts`: é a
 * única janela que tem **sempre** gráfico (sete intervalos diários) e é a que
 * responde à pergunta da manhã. Um valor desconhecido é 400 e não um default
 * silencioso — a rota do cliente já degrada o URL malformado
 * (`.catch(undefined)`), logo um `period` inválido a chegar aqui vem de um
 * `curl` e merece a resposta que o serializer daria.
 */
function periodoPedido(ctx: Contexto): Periodo | null {
  const pedido = periodoSchema.safeParse(ctx.parametros.get("period") ?? "7d");
  return pedido.success ? pedido.data : null;
}

const RECUSA_DE_PARAMETRO = {
  code: "invalido",
  detail: "O período pedido não existe. Use today, 7d, 30d, month ou prev_month.",
} as const;

const RECUSA_DE_MES = {
  code: "invalido",
  detail: "O mês pedido não tem a forma YYYY-MM.",
} as const;

/**
 * O 403 do `/month` — a **recusa de papel**, na forma exacta do DRF.
 *
 * `detail` e **sem `code`**, que é o que o DRF devolve quando um
 * `permission_classes` recusa (medido no `GET /convites` com uma sessão que não
 * é de dono, e escrito assim na ADR 0013 decisão 6: "a forma do 403 é a mesma —
 * `detail` do DRF, sem `code` novo").
 *
 * Isto **não é fingir uma sessão** (que a ADR 0010 proíbe): é devolver uma
 * recusa, na mesma direcção do `RECUSA_SEM_SESSAO` do `servidor.ts`. A
 * diferença entre as duas coisas é toda: uma sessão falsa **concede** o que o
 * servidor recusaria; uma recusa falsa recusa o que o servidor recusa.
 */
const RECUSA_DE_PAPEL = {
  detail: "Não tem permissão para executar esta ação.",
} as const;

export const ROTAS_DO_PAINEL: readonly Rota[] = [
  {
    metodo: "GET",
    caminho: "/api/v1/reporting/summary",
    // Carrega acima da dobra, como os resumos do Stock e dos Alertas: atraso
    // menor para o skeleton dos números não ficar mais tempo no ecrã do que os
    // blocos que vêm atrás dele.
    atrasoMs: 150,
    responder: (ctx) => {
      const periodo = periodoPedido(ctx);
      if (periodo === null) return resposta(400, RECUSA_DE_PARAMETRO);
      return resposta(200, resumoDoPeriodo(periodo), resumoDoPeriodoSchema);
    },
    vazio: (ctx) => {
      const periodo = periodoPedido(ctx) ?? "7d";
      return resposta(200, resumoVazio(periodo), resumoDoPeriodoSchema);
    },
  },
  {
    metodo: "GET",
    caminho: "/api/v1/reporting/series",
    responder: (ctx) => {
      const periodo = periodoPedido(ctx);
      if (periodo === null) return resposta(400, RECUSA_DE_PARAMETRO);
      return resposta(200, seriesDoPeriodo(periodo), seriesDoPeriodoSchema);
    },
    vazio: (ctx) => {
      const periodo = periodoPedido(ctx) ?? "7d";
      return resposta(200, seriesVazias(periodo), seriesDoPeriodoSchema);
    },
  },
  {
    metodo: "GET",
    caminho: "/api/v1/reporting/month",
    responder: (ctx) => {
      const mes = ctx.parametros.get("month") ?? mesDeHoje();
      if (!mesValido(mes)) return resposta(400, RECUSA_DE_MES);
      return resposta(200, fechoDoMes(mes), fechoDoMesSchema);
    },
    vazio: (ctx) => {
      const mes = ctx.parametros.get("month") ?? mesDeHoje();
      return mesValido(mes) ? resposta(200, mesVazio(mes), fechoDoMesSchema) : resposta(400, RECUSA_DE_MES);
    },
    // A **terceira** variante, e é só deste caminho: o painel do dono visto por
    // quem não é dono. É a rede do deep link e da pertença revogada a meio da
    // sessão, que é o caso que a ADR 0007 fez ser verificado por pedido.
    restrito: () => resposta(403, RECUSA_DE_PAPEL),
  },
];

