import type { EstadoNivel } from "./schemas";

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
type Gravidade = "grave" | "aviso";

/**
 * O `ok` **não está aqui**, e é deliberado: um nível saudável não tem tinta
 * nenhuma, em nenhum dos dois papéis. Não é cinzento nem é um visto verde — é
 * nada. É o que faz a leitura de dois metros do DESIGN.md §1 funcionar: o ecrã é
 * monocromático até algo estar mal, e por isso o que está mal salta. Um estado
 * novo que o contrato ganhe e esta lista não conheça cai no mesmo sítio que o
 * `ok` — sem cor inventada, com a palavra do servidor à vista.
 */
const GRAVIDADE = new Map<EstadoNivel, Gravidade>([
  ["negativo", "grave"],
  ["esgotado", "grave"],
  ["baixo", "aviso"],
]);

/** Primeiro papel do §2: a cor de estado como **cor de texto**. */
const TINTA_DO_TEXTO = new Map<Gravidade, string>([
  ["grave", "text-danger"],
  ["aviso", "text-warning"],
]);

/** O trilho é preenchimento, mas de 4px e sem nada por cima: não leva frente. */
const TINTA_DO_TRILHO = new Map<Gravidade, string>([
  ["grave", "bg-danger"],
  ["aviso", "bg-warning"],
]);

function gravidadeDe(estado: EstadoNivel): Gravidade | undefined {
  return GRAVIDADE.get(estado);
}

export function tintaDoTexto(estado: EstadoNivel): string {
  const gravidade = gravidadeDe(estado);
  return gravidade === undefined ? "" : (TINTA_DO_TEXTO.get(gravidade) ?? "");
}

export function tintaDoTrilho(estado: EstadoNivel): string {
  const gravidade = gravidadeDe(estado);
  return gravidade === undefined ? "" : (TINTA_DO_TRILHO.get(gravidade) ?? "");
}
