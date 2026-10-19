/**
 * Formatação via `Intl`. Nenhum formato à mão.
 *
 * Quantidades e dinheiro vêm da API como strings (`Decimal` no Django, para
 * não perder precisão em JSON). Aqui só se formatam para mostrar — nenhuma
 * conta é feita em `number`.
 *
 * O espaço entre o número e a unidade é um espaço inquebrável: "12,5 kg" não
 * se parte no fim da linha.
 *
 * ## Dois locales, e a divisão é "forma de dado" contra "palavra" (ADR 0019)
 *
 * **A forma do número e da data fica em pt-PT, em qualquer língua.** Vírgula
 * decimal, euro em sufixo, dia primeiro. Não é inércia — são três razões que se
 * somam:
 *
 *  - é a forma dos dados do **negócio**: a factura que a pessoa tem na mão diz
 *    `1.234,56 €`, e um ecrã que diga `$1,234.56` obriga-a a traduzir de cabeça
 *    enquanto confere;
 *  - as **larguras de coluna** do DESIGN.md §3 foram medidas nesta forma, e a
 *    vírgula decimal e o ponto de milhares não ocupam o mesmo que o contrário;
 *  - o `<input>` do Contar tem **um** parser. Duas formas de escrever `12,5` são
 *    duas leituras possíveis de uma quantidade de stock, e a que estiver errada
 *    entra no ledger.
 *
 * **As palavras que o `Intl` produz seguem a língua**, e são três: o nome do mês
 * (`mesEAno`), o mês abreviado (`diaEMesCurto`) e o relativo ("ontem", "em 3
 * dias"). Um ecrã inglês com "setembro de 2026" e "ontem" está meio traduzido no
 * sítio mais visível que existe — o título de um painel.
 *
 * **Consultar `domain-expert`** antes de mexer nisto: a decisão de manter a
 * vírgula decimal nas duas línguas toca em quantidades de stock e no campo de
 * contagem, e é afirmação de domínio e não de estilo.
 */
import { LINGUA } from "./i18n";

/** A forma dos **dados**. Fixa, em qualquer língua. Ver o docstring. */
const LOCALE = "pt-PT";

/** A língua das **palavras** que o `Intl` produz. Segue o browser. */
const LOCALE_DAS_PALAVRAS = LINGUA;

const NBSP = " ";

const quantidade = new Intl.NumberFormat(LOCALE, {
  minimumFractionDigits: 3,
  maximumFractionDigits: 3,
});

const dinheiro = new Intl.NumberFormat(LOCALE, {
  style: "currency",
  currency: "EUR",
});

const dinheiroRedondo = new Intl.NumberFormat(LOCALE, {
  style: "currency",
  currency: "EUR",
  maximumFractionDigits: 0,
});

const dinheiroComSinal = new Intl.NumberFormat(LOCALE, {
  style: "currency",
  currency: "EUR",
  signDisplay: "exceptZero",
});

const inteiro = new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 0 });

/** Uma casa decimal: o tamanho de um ficheiro em MiB, e mais nada por agora. */
const umaCasa = new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 1 });

const taxa = new Intl.NumberFormat(LOCALE, {
  style: "percent",
  maximumFractionDigits: 1,
});

const pontos = new Intl.NumberFormat(LOCALE, {
  maximumFractionDigits: 0,
  signDisplay: "exceptZero",
});

const data = new Intl.DateTimeFormat(LOCALE, {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
});

const diaEMes = new Intl.DateTimeFormat(LOCALE, { day: "2-digit", month: "2-digit" });

// Três formatadores com `LOCALE_DAS_PALAVRAS` e não `LOCALE`: são os únicos que
// produzem **palavras** em vez de dígitos. "setembro" e "Sep" são texto, e texto
// segue a língua de quem lê.
const mesEAno = new Intl.DateTimeFormat(LOCALE_DAS_PALAVRAS, {
  month: "long",
  year: "numeric",
});

const diaEMesCurto = new Intl.DateTimeFormat(LOCALE_DAS_PALAVRAS, {
  day: "numeric",
  month: "short",
});

const hora = new Intl.DateTimeFormat(LOCALE, { hour: "2-digit", minute: "2-digit" });

/**
 * `2026-10-02` é uma **data civil**, não um instante: o `new Date` lê-a como
 * meia-noite UTC e num fuso a oeste de Greenwich mostra o dia anterior. Uma
 * validade que aparece um dia mais cedo é um alerta falso, por isso as datas sem
 * hora levam uma hora local antes de se formatarem.
 */
function paraData(valor: Date | string): Date {
  if (valor instanceof Date) return valor;
  return new Date(valor.length === 10 ? `${valor}T00:00:00` : valor);
}

const relativo = new Intl.RelativeTimeFormat(LOCALE_DAS_PALAVRAS, { numeric: "auto" });

/** `12,500 kg` — três decimais, como o ledger guarda, e unidade sempre visível. */
export function formatQuantity(value: string | number, unit: string): string {
  return `${quantidade.format(Number(value))}${NBSP}${unit}`;
}

/**
 * `"24.000"` → `"24"`, `"0.500"` → `"0,5"` — um decimal da API como se **escreve
 * num campo**, e não como se mostra numa tabela.
 *
 * Duas diferenças face ao `formatQuantity`, e as duas são sobre o `<input>` do
 * Contar:
 *
 *  1. **sem separador de milhares.** O `Intl` escreveria `24 000` ou `24.000`
 *     para vinte e quatro mil, e o parser do campo — um `replace(",", ".")`
 *     seguido de um regex decimal — não o sabe ler. Um campo que mostra o que
 *     não aceita de volta é um campo que perde o valor no primeiro `onBlur`;
 *  2. **sem zeros à direita.** O servidor manda `"24.000"` para 24 kg, e
 *     `24.000` lido por um português é **vinte e quatro mil**. Era a leitura
 *     errada do número mais importante do ecrã, e a forma de a matar é não a
 *     escrever: `24` é exacto, curto, e é o que a pessoa escreveu.
 *
 * Por isso é manual e não `Intl`: aqui o que se quer é a forma **de entrada**,
 * que tem menos liberdade do que a de leitura. A vírgula é a de pt-PT nas duas
 * línguas, pela razão do topo deste ficheiro — o campo tem um parser só.
 */
export function formatDecimalField(value: string): string {
  const [inteiro = "", decimais = ""] = value.split(".");
  const significativas = decimais.replace(/0+$/, "");
  return significativas === "" ? inteiro : `${inteiro},${significativas}`;
}

/** `78,40 €` */
export function formatMoney(value: string | number): string {
  return dinheiro.format(Number(value));
}

/**
 * `1240 €` — euros sem cêntimos.
 *
 * Para totais de leitura (valor de stock, desperdício da semana), onde o cêntimo
 * é precisão falsa: o número vem de custos médios ponderados e de quantidades
 * estimadas, e mostrá-lo ao cêntimo convida a discutir o cêntimo em vez da
 * ordem de grandeza. Onde o valor é exacto — um total de fatura — usa-se o
 * `formatMoney`.
 */
export function formatMoneyRounded(value: string | number): string {
  return dinheiroRedondo.format(Number(value));
}

/**
 * `+1 150,00 €` — um valor **com sinal**, para uma variação.
 *
 * Existe para a variação de stock do painel (ADR 0013, decisão 4), e o sinal é
 * do número e não da cor: `+1 150,00 €` lê-se igual a preto e branco, e a
 * palavra ao lado ("encheu-se a despensa") é que diz o significado. É a mesma
 * regra do `formatPercentChange`.
 *
 * Com cêntimos, ao contrário do `formatMoneyRounded`: este número aparece na
 * linha que o ecrã usa para **mostrar a identidade a fechar**
 * (`variação == compras − consumo − quebra`), e com os três termos arredondados
 * ao euro a soma podia divergir num euro à vista de quem está a verificá-la.
 * Onde o valor é uma leitura e não uma prova, continua a usar-se o arredondado.
 */
export function formatMoneyChange(value: string | number): string {
  return dinheiroComSinal.format(Number(value));
}

/**
 * `23 %` — uma taxa que vem do servidor como **fração** decimal (`"0.230"`).
 *
 * A fração é a forma em que uma taxa de IVA viaja no contrato (é um `Decimal`
 * no Django, como o resto); a percentagem é só a forma de a ler. A conversão
 * é do `Intl`, pela mesma razão que o `formatMoney` não multiplica nada à mão.
 */
export function formatRate(value: string | number): string {
  return taxa.format(Number(value));
}

/**
 * `+21 %` — uma **variação** já em pontos percentuais inteiros, com sinal.
 *
 * O sinal faz parte do número e não da cor: "+21 %" lê-se igual a preto e
 * branco. Os pontos vêm inteiros do servidor de propósito — uma variação de
 * preço com casas decimais convida a discutir a casa decimal.
 */
export function formatPercentChange(points: number): string {
  return `${pontos.format(points)}${NBSP}%`;
}

/** `10 %` — pontos percentuais **sem** sinal, para um limiar. */
export function formatPercentPoints(points: number): string {
  return `${inteiro.format(points)}${NBSP}%`;
}

/** `360 un` — para unidades que não se contam em frações. */
export function formatCount(value: string | number, unit: string): string {
  return `${inteiro.format(Number(value))}${NBSP}${unit}`;
}

/**
 * `11,4 MiB` · `840 KiB` — o tamanho de um ficheiro enviado.
 *
 * **MiB e não MB**, e isso não é pedantismo: o teto do serializer são
 * 11 × 1024 × 1024 bytes e a recusa dele diz "11 MiB". Um ecrã que mostrasse
 * "11,9 MB" ao lado dessa frase parecia estar a contradizer-se, e quem está a
 * tentar enviar uma fotografia grande ficava sem saber qual dos dois acreditar.
 *
 * Abaixo de 1 MiB arredonda-se ao KiB inteiro (um ficheiro de fatura nunca tem
 * um tamanho interessante na terceira casa) e nunca desce a zero: `0 KiB` para
 * um ficheiro que existe é um número errado, e um ficheiro de zero bytes é
 * recusado antes de chegar aqui.
 *
 * A unidade fica **sempre visível**, como em todo o número deste produto, e com
 * o espaço inquebrável do resto do ficheiro.
 */
const KIB = 1024;
const MIB = 1024 * 1024;

export function formatFileSize(bytes: number): string {
  if (bytes >= MIB) return `${umaCasa.format(bytes / MIB)}${NBSP}MiB`;
  return `${inteiro.format(Math.max(1, Math.round(bytes / KIB)))}${NBSP}KiB`;
}

/** `29/09/2026` */
export function formatDate(value: Date | string): string {
  return data.format(paraData(value));
}

/** `29/09` — numa linha de 56px a validade não tem espaço para o ano. */
export function formatDayMonth(value: Date | string): string {
  return diaEMes.format(paraData(value));
}

/**
 * `setembro de 2026` — o mês de negócio de que o fecho fala.
 *
 * Aceita o `"2026-09"` do contrato, que **não** é uma data: `new Date("2026-09")`
 * é lido como UTC e num fuso a oeste de Greenwich devolve agosto. O dia 1 às
 * 12:00 locais é seguro em qualquer fuso, e o dia nunca é mostrado.
 */
export function formatMonth(month: string): string {
  const [ano, mes] = month.split("-").map(Number);
  return mesEAno.format(new Date(ano ?? 0, (mes ?? 1) - 1, 1, 12));
}

/** `1 set` — a fronteira de um mês de negócio, onde o ano é redundante. */
export function formatDayMonthShort(value: Date | string): string {
  return diaEMesCurto.format(paraData(value));
}

/** `06:40` — a hora a que um movimento aconteceu. */
export function formatTime(value: Date | string): string {
  return hora.format(paraData(value));
}

/** `em 2 dias`, `ontem`, `hoje`. É o texto que acompanha o semáforo de validade. */
export function formatDaysAway(days: number): string {
  return relativo.format(days, "day");
}

/**
 * `4,2 s` — quanto demorou uma resposta do assistente, a partir de
 * milissegundos.
 *
 * Uma casa decimal, como o tamanho de ficheiro: a segunda casa de uma espera de
 * vários segundos é precisão falsa, e o que a pessoa compara é "quatro segundos"
 * contra "vinte". A unidade fica visível, com o espaço inquebrável do resto do
 * ficheiro.
 */
export function formatSeconds(ms: number): string {
  return `${umaCasa.format(ms / 1000)}${NBSP}s`;
}
