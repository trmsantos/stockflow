import { formatDate, formatDayMonth, formatDaysAway } from "@/lib/format";

import type { EstadoNivel, ValidadeProxima } from "./schemas";
import { textos } from "./textos";
import {
  piorUrgencia,
  tintaDoTextoDeGravidade,
  tintaDoTrilhoDeUrgencia,
  urgenciaDeGravidade,
  urgenciaDoEstado,
  type Urgencia,
} from "./tinta-do-estado";

/**
 * A leitura de uma validade: a **palavra** é daqui, a **cor** é do servidor.
 *
 * ## Porque é que esta divisão existe, e o que ela corrigiu
 *
 * Até à ADR 0034 esta função decidia as duas coisas, e era a **quarta**
 * definição de gravidade de validade da casa — a única que o utilizador via, por
 * decidir a cor do trilho da linha. Não existia por desleixo: o `nearest_expiry`
 * não trazia gravidade nenhuma, logo o cliente era **obrigado** a recalculá-la
 * para pintar o trilho, e unificar as três do servidor sem lhe dar o campo
 * deixava esta de pé.
 *
 * Agora o `nearest_expiry` (e o `Alerta.lot` com ele) trazem `severity`, pela
 * tabela da decisão 9 — onde um `best_before` nunca chega a `danger`, por ser
 * DDM e não DLC, e onde o limiar de dias decide **o que aparece** e a gravidade
 * decide **como aparece**. O que fica deste lado é a palavra, porque i18n é do
 * cliente: "expira hoje" e "perde qualidade em 2 dias" são a distinção que o
 * dono precisa de ver, e não se dizem com as mesmas palavras.
 *
 * ## O `kind` nulo lê-se pela coluna estrita
 *
 * Um artigo sem rótulo de validade (`expiry_kind` vazio no catálogo) chega com
 * `kind: null`. A palavra é a do `use_by` — "expira" e não "perde qualidade" —
 * pela mesma razão que o servidor lhe dá a gravidade estrita: sub-avisar é o
 * erro caro, e a app ainda não conhece a validade secundária depois de aberto.
 */
export interface Leitura {
  readonly texto: string;
  readonly corDoTexto: string;
}

/**
 * A tinta de uma validade.
 *
 * Deriva do `severity` do servidor pelo **mesmo** mapa que pinta o trilho de um
 * alerta, logo a palavra e a goteira da mesma linha não podem discordar. O
 * `info` não tem tinta de sinal — é a regra do `tinta-do-estado.ts`, e num ecrã
 * monocromático até algo estar mal é o que faz o que está mal saltar — e aqui
 * escreve-se em `muted-foreground`: um prazo calmo é texto de apoio ao lado da
 * quantidade, não um sinal apagado.
 */
function tintaDaLeitura(validade: ValidadeProxima): string {
  const sinal = tintaDoTextoDeGravidade(validade.severity);
  return sinal === "" ? "text-muted-foreground" : sinal;
}

/**
 * A palavra. O limiar continua a entrar porque é ele que decide entre o
 * relativo ("expira amanhã") e a data ("expira a 12/11") — dentro do horizonte
 * conta-se em dias, fora dele lê-se a data, que é como se fala de um prazo
 * folgado. Não decide cor nenhuma desde a ADR 0034.
 */
export function leituraDe(validade: ValidadeProxima, limiarEmDias: number): Leitura {
  const dias = validade.days_away;
  const relativo = formatDaysAway(dias);
  const corDoTexto = tintaDaLeitura(validade);

  if (validade.kind === "best_before") {
    if (dias < 0) {
      return { texto: textos.validade.perdeuQualidade(relativo), corDoTexto };
    }
    if (dias <= limiarEmDias) {
      return { texto: textos.validade.perdeQualidade(relativo), corDoTexto };
    }
    return {
      texto: textos.validade.melhorAntesDe(formatDayMonth(validade.expires_at)),
      corDoTexto,
    };
  }

  if (dias < 0) {
    return { texto: textos.validade.expirou(relativo), corDoTexto };
  }
  if (dias === 0) {
    return { texto: textos.validade.expiraHoje, corDoTexto };
  }
  if (dias <= limiarEmDias) {
    return { texto: textos.validade.expiraQuando(relativo), corDoTexto };
  }
  return {
    texto: textos.validade.expiraA(formatDayMonth(validade.expires_at)),
    corDoTexto,
  };
}

/**
 * O que se diz em cada caso, por extenso, para quem lê a linha devagar.
 *
 * Duas frases e não uma com buracos: um lote sintético não tem código e um
 * artigo sem rótulo não tem natureza legal. Uma frase montada por pedaços com
 * "Lote sem lote" lá dentro não se traduz nem se lê.
 */
export function tituloDe(validade: ValidadeProxima): string {
  const natureza =
    validade.kind === "use_by"
      ? textos.validade.consumirAte
      : validade.kind === "best_before"
        ? textos.validade.consumirPreferencialmente
        : textos.validade.semRotulo;
  const data = formatDate(validade.expires_at);
  return validade.lot_code === null
    ? textos.validade.tituloSemLote(natureza, data)
    : textos.validade.titulo(validade.lot_code, natureza, data);
}

/**
 * A urgência de uma validade, ou `null` quando não há nenhuma a assinalar.
 *
 * **Lê o `severity` do servidor** e não recalcula nada. O tecto do
 * `best_before` continua a vir de graça, agora pela tabela da ADR 0034 d9, que
 * nunca lhe dá `danger`.
 */
export function urgenciaDaValidade(validade: ValidadeProxima | null): Urgencia | null {
  return validade === null ? null : urgenciaDeGravidade(validade.severity);
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
 * **O limiar saiu desta assinatura com a ADR 0034.** Ele servia para o cliente
 * calcular a urgência da validade; agora ela vem no `severity` do lote, e um
 * parâmetro que já não decide nada é um convite a passá-lo errado.
 */
export function tintaDoTrilhoDoNivel(
  estado: EstadoNivel,
  validade: ValidadeProxima | null,
): string {
  return tintaDoTrilhoDeUrgencia(
    piorUrgencia(urgenciaDoEstado(estado), urgenciaDaValidade(validade)),
  );
}
