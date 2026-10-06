import type { EstadoNivel, Gravidade } from "./schemas";

/**
 * A tinta de um estado de stock, nos **dois papéis** em que ela aparece: a
 * palavra na coluna do estado e o trilho de 4px na aresta da linha.
 *
 * Vive num módulo próprio e não dentro do componente por duas razões que se
 * somam. A primeira é mecânica: um ficheiro que exporta um componente **e** uma
 * função perde o fast refresh do Vite, e o `react-refresh/only-export-components`
 * do `eslint.config.js` recusa-o — foi ele que mandou isto para aqui.
 *
 * A segunda é a que importa. Os dois papéis têm de concordar: se a palavra
 * dissesse "Baixo" em âmbar e o trilho da mesma linha fosse vermelho, a linha
 * dava dois veredictos. Derivam por isso de **uma** classificação de gravidade,
 * que é a única coisa que se decide aqui — as duas classes são consequência.
 *
 * É a mesma ideia dos três papéis por cor de estado do DESIGN.md §2 (texto,
 * preenchimento, borda): um valor só não serve papéis diferentes, mas a
 * *decisão* é uma só.
 *
 * O estado vem do servidor (`status`), nunca de uma comparação feita no cliente.
 * Se o limiar de "baixo" mudar, muda num sítio e esta lista não passa a
 * discordar dos alertas.
 */
/**
 * A urgência **interna** desta camada. Tem nome próprio e não se chama
 * "gravidade" porque `Gravidade` é o tipo do contrato (`danger`/`warning`/`info`)
 * e são coisas diferentes: aquele é o que o servidor diz, este é o que a tinta
 * precisa de saber. Dois vocabulários do contrato colapsam neste.
 */
export type Urgencia = "grave" | "aviso";

/**
 * O `ok` **não está aqui**, e é deliberado: um nível saudável não tem tinta
 * nenhuma, em nenhum dos dois papéis. Não é cinzento nem é um visto verde — é
 * nada. É o que faz a leitura de dois metros do DESIGN.md §1 funcionar: o ecrã é
 * monocromático até algo estar mal, e por isso o que está mal salta. Um estado
 * novo que o contrato ganhe e esta lista não conheça cai no mesmo sítio que o
 * `ok` — sem cor inventada, com a palavra do servidor à vista.
 */
const URGENCIA_DO_ESTADO = new Map<EstadoNivel, Urgencia>([
  ["negativo", "grave"],
  ["esgotado", "grave"],
  ["baixo", "aviso"],
]);

/** Primeiro papel do §2: a cor de estado como **cor de texto**. */
const TINTA_DO_TEXTO = new Map<Urgencia, string>([
  ["grave", "text-danger"],
  ["aviso", "text-warning"],
]);

/** O trilho é preenchimento, mas de 4px e sem nada por cima: não leva frente. */
const TINTA_DO_TRILHO = new Map<Urgencia, string>([
  ["grave", "bg-danger"],
  ["aviso", "bg-warning"],
]);

function urgenciaDe(estado: EstadoNivel): Urgencia | undefined {
  return URGENCIA_DO_ESTADO.get(estado);
}

export function tintaDoTexto(estado: EstadoNivel): string {
  const urgencia = urgenciaDe(estado);
  return urgencia === undefined ? "" : (TINTA_DO_TEXTO.get(urgencia) ?? "");
}

export function tintaDoTrilho(estado: EstadoNivel): string {
  const urgencia = urgenciaDe(estado);
  return urgencia === undefined ? "" : (TINTA_DO_TRILHO.get(urgencia) ?? "");
}

/**
 * A mesma classificação, a partir da **gravidade de um alerta** em vez do estado
 * de um nível.
 *
 * O contrato tem dois vocabulários para a mesma ideia porque são dois recursos:
 * um `StockLevel` tem `status` (`negativo`/`esgotado`/`baixo`/`ok`) e um alerta
 * tem `severity` (`danger`/`warning`/`info`), as duas decididas no servidor.
 * Traduzir ambos para a **mesma** gravidade interna é o que faz um "baixo" no
 * ecrã de Stock e o alerta que ele gera terem exactamente a mesma cor — se cada
 * ecrã tivesse o seu mapa, divergiam na primeira correção feita só num.
 *
 * O `info` não tem tinta, pela mesma razão que o `ok`. Num ecrã de alertas isso
 * lê-se de forma diferente e vale dizê-lo: ali **todas** as linhas são alertas,
 * logo o trilho não distingue "problema" de "não problema" — distingue
 * **urgência**. Um `info` é um alerta que não se quer ver de dois metros.
 */
const URGENCIA_DO_ALERTA = new Map<Gravidade, Urgencia>([
  ["danger", "grave"],
  ["warning", "aviso"],
]);

export function tintaDoTextoDeGravidade(gravidade: Gravidade): string {
  const urgencia = URGENCIA_DO_ALERTA.get(gravidade);
  return urgencia === undefined ? "" : (TINTA_DO_TEXTO.get(urgencia) ?? "");
}

export function tintaDoTrilhoDeGravidade(gravidade: Gravidade): string {
  const urgencia = URGENCIA_DO_ALERTA.get(gravidade);
  return urgencia === undefined ? "" : (TINTA_DO_TRILHO.get(urgencia) ?? "");
}

/** A urgência de um estado de nível, para se poder compor com outras. */
export function urgenciaDoEstado(estado: EstadoNivel): Urgencia | null {
  return urgenciaDe(estado) ?? null;
}

/**
 * A pior de duas urgências.
 *
 * Existe porque uma linha de stock tem **duas** razões independentes para pedir
 * atenção — a quantidade e o prazo — e o trilho é um só. Sem isto o trilho
 * derivava apenas da quantidade, e uma linha a expirar hoje ficava sem marca
 * nenhuma ao lado de uma linha "baixo" com validade folgada (medido num
 * screenshot a 2026-10-06). O DESIGN.md §1 pede as duas pela letra: "em falta
 * **ou fora de prazo**".
 */
export function piorUrgencia(a: Urgencia | null, b: Urgencia | null): Urgencia | null {
  if (a === "grave" || b === "grave") return "grave";
  if (a === "aviso" || b === "aviso") return "aviso";
  return null;
}

export function tintaDoTrilhoDeUrgencia(urgencia: Urgencia | null): string {
  return urgencia === null ? "" : (TINTA_DO_TRILHO.get(urgencia) ?? "");
}
