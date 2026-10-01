import type {
  EstadoNivel,
  Movimento,
  MotivoQuebra,
  NivelDeStock,
  Quantidade,
  TipoMovimento,
  TipoValidade,
} from "../src/features/inventory/schemas.ts";
import {
  ARTIGOS,
  AUTORES,
  LOCALIZACOES,
  dataEmDias,
  diasAte,
  horaDeHoje,
  horaDeOntem,
  horaEmDias,
  type ArtigoFalso,
} from "./aurora.ts";
import {
  centimosDe,
  decimilesimosDe,
  milesimosDe,
  milesimosParaApresentacao,
  stringDeMilesimos,
} from "./decimal.ts";
import type { Contexto } from "./servidor.ts";

/**
 * dados-falsos-stockflow — **o ledger**, e tudo o que se deriva dele.
 *
 * Este ficheiro existe porque os três ecrãs de inventário são **vistas do mesmo
 * ledger**, não estados paralelos: o Stock soma-o por artigo, os Alertas
 * somam-no por lote, e a Contagem compara-o com o que está na prateleira. Se
 * cada recurso guardasse o seu próprio número, fechar uma contagem não mudaria
 * o stock e deitar fora um lote não mudaria o alerta — e o shell ensinaria
 * exactamente o produto errado ao dono na sessão 0.
 *
 * **Stock é um ledger, também na mentira** (ADR 0008, decisão 3). O estado em
 * memória são `StockMovement`s; os níveis, o estado da linha, a validade mais
 * próxima, o valor em euros e as diferenças de uma contagem são todos
 * derivados a cada pedido. Não há campo de quantidade que se escreva em sítio
 * nenhum.
 *
 * Apagabilidade: este ficheiro não serve rota nenhuma — são os `*.ts` ao lado
 * (`stock.ts`, `contagem.ts`, `alertas.ts`) que têm as rotas e que se apagam um
 * a um quando o Django servir cada recurso. Quando sair o último, sai também
 * este.
 */

export type Loja = "centro" | "mercado" | "cozinha";

export interface MovimentoFalso {
  readonly id: string;
  readonly tipo: TipoMovimento;
  /** O `n` do artigo em `aurora.ts`. */
  readonly artigo: number;
  readonly loja: Loja;
  readonly lote: string | null;
  /** Valor absoluto em milésimos da unidade base. O sinal vem do tipo... */
  readonly milesimos: number;
  /**
   * ... excepto quando é explícito. Um `adjustment` de contagem não tem sinal
   * fixo — corrige para cima ou para baixo —, e é a única forma de movimento
   * deste ledger onde o tipo não basta para o saber.
   */
  readonly sinal: 1 | -1 | null;
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
  // `adjustment` entra aqui com -1 por defeito, mas quem o cria passa o sinal:
  // ver o campo `sinal` acima.
  ["adjustment", -1],
]);

export function sinalDe(mov: MovimentoFalso): number {
  return mov.sinal ?? SINAL_POR_TIPO.get(mov.tipo) ?? -1;
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

export const LOTES: readonly LoteFalso[] = [
  { codigo: "L-T65-1142", artigo: 1, dias: 180, tipo: "best_before" },
  { codigo: "L-OVL-0914", artigo: 3, dias: 3, tipo: "use_by" },
  { codigo: "L-MNT-0902", artigo: 5, dias: 38, tipo: "best_before" },
  { codigo: "L-NAT-0921", artigo: 6, dias: 6, tipo: "use_by" },
  { codigo: "L-LTE-0803", artigo: 7, dias: 95, tipo: "best_before" },
  { codigo: "L-MSF-0715", artigo: 9, dias: 210, tipo: "best_before" },
  // O alerta amarelo que **não** é para deitar fora, e por isso tem de estar
  // **dentro** do horizonte: a dois dias, ao lado do morango que expira
  // também a dois dias, as duas linhas leem-se "perde qualidade em 2 dias" e
  // "expira em 2 dias" — a mesma distância, palavras e cores diferentes. É
  // assim que a distinção se mostra em vez de se explicar (guião §2).
  { codigo: "L-AMD-0928", artigo: 11, dias: 2, tipo: "best_before" },
  { codigo: "L-MOR-0930", artigo: 12, dias: 2, tipo: "use_by" },
  { codigo: "L-FER-0929", artigo: 13, dias: 5, tipo: "use_by" },
  // Duas bolas da mesma ida ao Makro, abertas ontem em lojas diferentes: são
  // duas vezes "7 dias depois de aberta" (guião §2) e portanto dois lotes, não
  // um. Abertas ontem, logo expiram daqui a 6 dias e não a 7.
  { codigo: "L-QJF-0925", artigo: 14, dias: 6, tipo: "use_by" },
  { codigo: "L-QJF-0926", artigo: 14, dias: 6, tipo: "use_by" },
  { codigo: "L-FMB-0929", artigo: 15, dias: 3, tipo: "use_by" },
  { codigo: "L-BAC-0611", artigo: 21, dias: 300, tipo: "best_before" },
  // Produção própria: validade no **mesmo dia** (a sonda da Q6 do guião).
  { codigo: "L-PN-HOJE", artigo: 22, dias: 0, tipo: "use_by" },
  { codigo: "L-PN-ONTEM", artigo: 22, dias: -1, tipo: "use_by" },
  // O lote da produção de há três dias, já todo escoado: é dele que vem o
  // desperdício que faz "esta semana" ser maior do que "hoje" no ecrã Alertas.
  { codigo: "L-PN-D3", artigo: 22, dias: -3, tipo: "use_by" },
];

export function loteDe(codigo: string): LoteFalso | undefined {
  return LOTES.find((lote) => lote.codigo === codigo);
}

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
    sinal: null,
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
    // --- há três dias: um dia de pastéis do princípio ao fim, que fecha a zero.
    // Existe por uma razão só: sem ele "deitado fora esta semana" seria igual a
    // "deitado fora hoje", e dois números iguais ao lado um do outro leem-se
    // como um erro do ecrã em vez de como a pergunta da Q6.
    movimento("receipt", 22, "cozinha", "300", "L-PN-D3", AUTORES.rui, horaEmDias(-3, 6, 30), "Produção do dia"),
    movimento("consumption", 22, "cozinha", "285", "L-PN-D3", AUTORES.rui, horaEmDias(-3, 19, 0), "Vendas do dia"),
    movimento("waste", 22, "cozinha", "15", "L-PN-D3", AUTORES.rui, horaEmDias(-2, 5, 5), null, "expired"),

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
    // Peso variável na fatura: duas bolas na mesma ida ao Makro, pesadas uma a
    // uma — 3,480 kg e 2,960 kg, nenhuma a 3,5 (guião §2). Uma fica no Centro, a
    // outra segue na carrinha para o Mercado: uma viagem, duas lojas, que é o
    // caso normal de quem tem duas lojas e vai ao cash & carry. É daqui que vem
    // o stock repartido da Q2 — e é esta linha que faz a Loja Mercado existir no
    // seletor de loja, que o deriva das localizações que aparecem nos dados.
    // Quem dá entrada é quem está na loja onde a mercadoria fica; no Mercado não
    // há ninguém de balcão nos dados, é a gerência que o cobre.
    movimento("receipt", 14, "centro", "3480", "L-QJF-0925", AUTORES.ana, ontem(9, 10), "FS 2026/114570"),
    movimento("receipt", 14, "mercado", "2960", "L-QJF-0926", AUTORES.dono, ontem(9, 40), "FS 2026/114570"),
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
    // Tostas nas duas lojas, ~25 g de queijo cada (guião §2), cada uma do lote
    // da bola aberta naquela loja. Sobram 1,300 kg no Centro e 0,800 kg no
    // Mercado — 2,100 kg repartidos e **nenhuma parcela a zero**. É essa a
    // condição da sonda da Q2: a linha lê-se "Loja Centro 1,300 kg · Loja
    // Mercado 0,800 kg" e a pergunta "consolidado ou separado?" tem as duas
    // respostas no ecrã ao mesmo tempo. Com um zero numa das parcelas não tinha.
    movimento("consumption", 14, "centro", "1100", "L-QJF-0925", AUTORES.ana, ontem(13, 10), "Vendas de ontem"),
    movimento("consumption", 14, "mercado", "1250", "L-QJF-0926", AUTORES.dono, ontem(13, 20), "Vendas de ontem"),
    movimento("consumption", 14, "centro", "1080", "L-QJF-0925", AUTORES.ana, hoje(11, 2), "Vendas de hoje"),
    movimento("consumption", 14, "mercado", "910", "L-QJF-0926", AUTORES.dono, hoje(11, 15), "Vendas de hoje"),
    // Um litro de leite estragado ontem à tarde. Entra no desperdício da semana
    // e não no de hoje, que é o contraste que o contador do topo precisa.
    movimento("waste", 7, "cozinha", "1000", "L-LTE-0803", AUTORES.rui, ontem(14, 30), null, "spoiled"),

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

/** Leitura do ledger. Devolve a lista como está, da mais antiga para a mais nova. */
export function ledger(): readonly MovimentoFalso[] {
  return movimentos;
}

/**
 * A única escrita que existe: **append**. Não há função para alterar nem para
 * apagar, e é de propósito (ADR 0006 — `inventory_stockmovement` é append-only
 * na própria base de dados, com `REVOKE UPDATE, DELETE`).
 */
export function acrescentar(mov: Omit<MovimentoFalso, "id">): MovimentoFalso {
  const novo: MovimentoFalso = { id: crypto.randomUUID(), ...mov };
  movimentos.push(novo);
  return novo;
}

// ---------------------------------------------------------------------------
// Derivação. Tudo o que o ecrã vê sai destas funções — nunca de um campo.
// ---------------------------------------------------------------------------

export function artigoDe(n: number): ArtigoFalso | undefined {
  return ARTIGOS.at(n - 1);
}

/** O `n` de `aurora.ts` a partir do `id` que o cliente manda. `-1` se não existe. */
export function numeroDoArtigo(idDoProduto: string): number {
  const indice = ARTIGOS.findIndex((item) => item.id === idDoProduto);
  return indice === -1 ? -1 : indice + 1;
}

export function localizacaoDe(loja: Loja) {
  const encontrada = LOCALIZACOES.find((local) => local.slug === loja);
  // O seed é escrito à mão; um slug errado é um erro de programação e não um
  // caso a tratar em runtime.
  if (!encontrada) throw new Error(`Localização desconhecida no fixture: ${loja}`);
  return { id: encontrada.id, name: encontrada.nome };
}

export function quantidade(artigo: ArtigoFalso, milesimos: number): Quantidade {
  return {
    base: stringDeMilesimos(milesimos),
    base_unit: artigo.unidadeBase,
    display: stringDeMilesimos(milesimosParaApresentacao(milesimos, artigo.fatorApresentacao)),
    display_unit: artigo.unidadeApresentacao,
  };
}

/** O valor em cêntimos de uma quantidade em milésimos, ao CMP do artigo. */
export function centimosDoArtigo(artigo: ArtigoFalso, milesimos: number): number {
  return centimosDe(milesimos, decimilesimosDe(artigo.custoUnitario));
}

/** Soma do ledger por artigo e loja. É a projeção `StockLevel`, derivada. */
export function somarPorArtigoELoja(lojas: readonly Loja[]): Map<number, Map<Loja, number>> {
  const total = new Map<number, Map<Loja, number>>();
  for (const mov of movimentos) {
    if (!lojas.includes(mov.loja)) continue;
    const porLoja = total.get(mov.artigo) ?? new Map<Loja, number>();
    porLoja.set(mov.loja, (porLoja.get(mov.loja) ?? 0) + sinalDe(mov) * mov.milesimos);
    total.set(mov.artigo, porLoja);
  }
  return total;
}

/** Soma do ledger por lote, para saber que validade ainda tem stock atrás. */
export function somarPorLote(lojas: readonly Loja[]): Map<string, number> {
  const total = new Map<string, number>();
  for (const mov of movimentos) {
    if (mov.lote === null || !lojas.includes(mov.loja)) continue;
    total.set(mov.lote, (total.get(mov.lote) ?? 0) + sinalDe(mov) * mov.milesimos);
  }
  return total;
}

/** O mesmo, por lote **e** loja: é o que um alerta de validade precisa. */
export function somarPorLoteELoja(): Map<string, Map<Loja, number>> {
  const total = new Map<string, Map<Loja, number>>();
  for (const mov of movimentos) {
    if (mov.lote === null) continue;
    const porLoja = total.get(mov.lote) ?? new Map<Loja, number>();
    porLoja.set(mov.loja, (porLoja.get(mov.loja) ?? 0) + sinalDe(mov) * mov.milesimos);
    total.set(mov.lote, porLoja);
  }
  return total;
}

/** Quanto deste artigo está nesta loja, em milésimos da unidade base. */
export function stockDe(numero: number, loja: Loja): number {
  let total = 0;
  for (const mov of movimentos) {
    if (mov.artigo !== numero || mov.loja !== loja) continue;
    total += sinalDe(mov) * mov.milesimos;
  }
  return total;
}

/**
 * O estado da linha, decidido **no servidor** (schemas.ts): se o limiar de
 * "baixo" mudar, muda num sítio, e a UI não ganha uma segunda definição de "em
 * falta" que divirja da dos alertas.
 */
export function estadoDe(milesimos: number, minimo: number): EstadoNivel {
  if (milesimos < 0) return "negativo";
  if (milesimos === 0) return "esgotado";
  if (milesimos < minimo) return "baixo";
  return "ok";
}

export function validadeMaisProxima(artigo: number, porLote: Map<string, number>) {
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

/** O lote mais próximo de expirar que ainda tem stock nesta loja (FEFO). */
export function loteFefo(numero: number, loja: Loja): string | null {
  const porLote = somarPorLote([loja]);
  const candidatos = LOTES.filter(
    (lote) => lote.artigo === numero && (porLote.get(lote.codigo) ?? 0) > 0,
  ).sort((a, b) => a.dias - b.dias);
  return candidatos[0]?.codigo ?? null;
}

/** "O que está pior primeiro. **Nunca alfabética**" (guião §1). */
const ORDEM_DO_ESTADO = new Map<EstadoNivel, number>([
  ["negativo", 0],
  ["esgotado", 1],
  ["baixo", 2],
  ["ok", 3],
]);

export function pesoDoEstado(estado: EstadoNivel): number {
  return ORDEM_DO_ESTADO.get(estado) ?? 9;
}

/** O limiar viaja com o número para o ecrã o poder mostrar (guião §4, nº 7). */
export const HORIZONTE_DE_VALIDADE_EM_DIAS = 3;

/** Todas as lojas, na ordem em que `aurora.ts` as declara. */
export function todasAsLojas(): readonly Loja[] {
  return LOCALIZACOES.map((local) => local.slug);
}

/**
 * O `?loja=` dos ecrãs — o search param que a decisão 1 do ADR 0008 existe
 * para tipar. Um valor desconhecido degrada para "todas" em vez de explodir.
 */
export function lojasPedidas(ctx: Contexto): readonly Loja[] {
  return lojaOuTodas(ctx.parametros.get("loja"));
}

export function lojaOuTodas(pedida: string | null): readonly Loja[] {
  const encontrada = lojaDe(pedida);
  return encontrada === null ? todasAsLojas() : [encontrada];
}

/** Casa pelo **id** e pelo slug. `null` se não reconhece nenhum dos dois. */
export function lojaDe(pedida: string | null): Loja | null {
  // O id porque é o único identificador de localização que a API manda ao
  // cliente (`localizacaoSchema` é `{id, name}`, sem slug): o `?loja=` que sai
  // de um ecrã só pode ser o id, senão o frontend passava a guardar um catálogo
  // de lojas que não é dele. O slug porque é o que se escreve à mão num `curl`
  // e já estava documentado como tal.
  const encontrada = LOCALIZACOES.find(
    (local) => local.id === pedida || local.slug === pedida,
  );
  return encontrada?.slug ?? null;
}

export function niveis(lojas: readonly Loja[]): NivelDeStock[] {
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
    const porEstado = pesoDoEstado(a.status) - pesoDoEstado(b.status);
    if (porEstado !== 0) return porEstado;
    const diasA = a.nearest_expiry?.days_away ?? Number.MAX_SAFE_INTEGER;
    const diasB = b.nearest_expiry?.days_away ?? Number.MAX_SAFE_INTEGER;
    return diasA - diasB;
  });
}

export function paraMovimento(mov: MovimentoFalso): Movimento | null {
  const artigo = artigoDe(mov.artigo);
  if (!artigo) return null;
  return {
    id: mov.id,
    movement_type: mov.tipo,
    quantity: quantidade(artigo, sinalDe(mov) * mov.milesimos),
    location: localizacaoDe(mov.loja),
    lot_code: mov.lote,
    reason: mov.motivo,
    created_by: mov.autor,
    occurred_at: mov.quando,
    reference: mov.referencia,
  };
}
