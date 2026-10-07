import { formatDate, formatDayMonth, formatDaysAway } from "@/lib/format";

import type { EstadoNivel, ValidadeProxima } from "./schemas";
import { textos } from "./textos";
import {
  piorUrgencia,
  tintaDoTrilhoDeUrgencia,
  urgenciaDoEstado,
  type Urgencia,
} from "./tinta-do-estado";

/**
 * A leitura de uma validade: a palavra, a tinta do texto, e a **urgência**.
 *
 * ## Porque saiu do ficheiro de componente
 *
 * Vivia dentro de `components/validade.tsx` e a urgência não existia. Saiu a
 * 2026-10-06 por uma razão medida: o trilho de sinal da tabela de Stock derivava
 * **só** do `status` (quantidade contra mínimo), logo uma linha a expirar hoje
 * ficava com o trilho apagado enquanto uma linha "baixo" sem validade nenhuma
 * levava trilho âmbar. A linha mais urgente não tinha marca.
 *
 * Isso contradizia o DESIGN.md §1 pela letra — "uma linha **em falta ou fora de
 * prazo** vê-se sem se ler" — e só apareceu num screenshot do ecrã a correr, com
 * "Pastéis de nata · expira hoje" a vermelho ao lado de uma goteira escura.
 *
 * Para o trilho poder contar com a validade, a urgência tinha de ser legível fora
 * do componente; e um ficheiro que exporta um componente **e** uma função perde o
 * fast refresh do Vite (`react-refresh/only-export-components`). Daí este módulo.
 *
 * ## A urgência deriva da tinta que já existia, e isso é deliberado
 *
 * `urgenciaDaValidade` lê o `corDoTexto` da **mesma** `Leitura` que o texto usa,
 * em vez de reimplementar as regras de `use_by` contra `best_before` e do limiar.
 * Ler a decisão que já foi tomada é o que garante que o trilho e a palavra da
 * mesma linha nunca discordam — e discordarem era o defeito a sério: um trilho
 * vermelho ao lado de "perde qualidade" dizia ao dono que a amêndoa laminada é
 * para deitar fora, que é exactamente a confiança que o §2 do guião protege.
 */
export interface Leitura {
  readonly texto: string;
  readonly corDoTexto: string;
}

export function leituraDe(validade: ValidadeProxima, limiarEmDias: number): Leitura {
  const dias = validade.days_away;
  const relativo = formatDaysAway(dias);

  if (validade.kind === "use_by") {
    if (dias < 0) {
      return {
        texto: textos.validade.expirou(relativo),
        corDoTexto: "text-danger",
      };
    }
    if (dias === 0) {
      return {
        texto: textos.validade.expiraHoje,
        corDoTexto: "text-danger",
      };
    }
    if (dias <= limiarEmDias) {
      return {
        texto: textos.validade.expiraQuando(relativo),
        corDoTexto: "text-warning",
      };
    }
    return {
      texto: textos.validade.expiraA(formatDayMonth(validade.expires_at)),
      corDoTexto: "text-muted-foreground",
    };
  }

  if (dias < 0) {
    return {
      texto: textos.validade.perdeuQualidade(relativo),
      corDoTexto: "text-warning",
    };
  }
  if (dias <= limiarEmDias) {
    return {
      texto: textos.validade.perdeQualidade(relativo),
      corDoTexto: "text-warning",
    };
  }
  return {
    texto: textos.validade.melhorAntesDe(formatDayMonth(validade.expires_at)),
    corDoTexto: "text-muted-foreground",
  };
}

/** O que se diz em cada caso, por extenso, para quem lê a linha devagar. */
export function tituloDe(validade: ValidadeProxima): string {
  const natureza =
    validade.kind === "use_by"
      ? textos.validade.consumirAte
      : textos.validade.consumirPreferencialmente;
  return textos.validade.titulo(validade.lot_code, natureza, formatDate(validade.expires_at));
}

/**
 * A urgência de uma validade, ou `null` quando não há nenhuma a assinalar.
 *
 * O tecto do `best_before` é o aviso — nunca `grave` — e isso vem de graça: a
 * `leituraDe` nunca lhe dá `text-danger`.
 */
export function urgenciaDaValidade(
  validade: ValidadeProxima | null,
  limiarEmDias: number,
): Urgencia | null {
  if (validade === null) return null;
  const cor = leituraDe(validade, limiarEmDias).corDoTexto;
  if (cor === "text-danger") return "grave";
  if (cor === "text-warning") return "aviso";
  return null;
}

/**
 * O trilho de 4px de **uma linha de stock**, com as suas duas razões compostas.
 *
 * A composição `piorUrgencia(estado, validade)` vivia escrita dentro da
 * `tabela-de-stock.tsx` e passou a estar aqui a 2026-10-06, quando apareceu o
 * segundo sítio que desenha uma linha de stock: a miniatura do ecrã Início. Duas
 * cópias de uma composição de três funções divergem na primeira correcção feita
 * só numa — e o sintoma seria o pior possível, porque é silencioso: a mesma
 * linha com goteira acesa num ecrã e apagada no outro, sem nada a falhar.
 *
 * Fica neste módulo, e não no `tinta-do-estado.ts`, porque é aqui que a
 * **validade** já é legível fora do componente (foi a razão de este ficheiro
 * existir). O inverso obrigava o `tinta-do-estado.ts` a importar a leitura da
 * validade, e os dois passavam a importar-se um ao outro.
 */
export function tintaDoTrilhoDoNivel(
  estado: EstadoNivel,
  validade: ValidadeProxima | null,
  limiarEmDias: number,
): string {
  return tintaDoTrilhoDeUrgencia(
    piorUrgencia(urgenciaDoEstado(estado), urgenciaDaValidade(validade, limiarEmDias)),
  );
}
