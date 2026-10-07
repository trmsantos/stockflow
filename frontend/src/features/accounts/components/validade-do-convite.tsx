import { CircleCheck, CircleSlash, Clock, type LucideIcon } from "lucide-react";

import { formatDate, formatDayMonth, formatDaysAway } from "@/lib/format";

import type { Convite } from "../schemas";
import { textos } from "../textos";

/**
 * Quando é que este link deixa de servir — **semáforo por token e texto, nunca
 * só cor** (DESIGN.md §2 e a regra de validades).
 *
 * Um convite tem uma validade como um lote tem: 7 dias, do servidor, e o que
 * interessa a quem olha é "ainda dá?" e não a data. Por isso a linha lê-se como
 * a coluna de validades do Stock — ícone, palavra e tinta a dizerem o mesmo —, e
 * a data absoluta vai no `title`, para quem precisa do dia exacto.
 *
 * ## O que decide a cor é o `estado`, não a aritmética da data
 *
 * O `estado` é derivado **no servidor** dos três timestamps (ADR 0010). Comparar
 * aqui o `expira_em` com o relógio do browser daria uma segunda definição de
 * "expirado", e as duas divergiriam exactamente onde dói: num separador aberto
 * desde ontem, ou num portátil com a hora errada. Então:
 *
 *  - `aceite` e `revogado` **não mostram validade nenhuma.** Não é falta de
 *    dados: a data continua na resposta, e deixou de querer dizer alguma coisa.
 *    Mostrar "expira em 5 dias" num convite já aceite é a frase que faz alguém
 *    pensar que há um link vivo por aí;
 *  - `expirado` é um aviso e não um erro: tem saída (reenviar), logo é `warning`
 *    e nunca vermelho. O vermelho desta paleta é para o que não tem volta, e
 *    nesta lista isso é o `revogado` — que é o `BadgeDeEstadoDoConvite` a dizer,
 *    não esta coluna;
 *  - `pendente` com pouco tempo é `warning`, com folga é `muted-foreground` com
 *    o visto em `success`. Pintar de verde todas as linhas folgadas faria perder
 *    as duas que estão a acabar, que é o mesmo argumento da coluna de validades
 *    do Stock.
 *
 * O limiar de "pouco tempo" é **dois dias** e é uma decisão desta sessão, não de
 * uma ADR: o TTL são 7 dias (ADR 0010) e o servidor não manda limiar nenhum
 * neste contrato — ao contrário do stock, onde o `expiring_within_days` vem na
 * resposta. Dois dias é o que sobra para alguém reagir a um link que ninguém
 * usou. Está nomeado no relatório como decisão do cliente; no dia em que o
 * contrato trouxer um limiar, esta constante sai.
 */
const DIAS_PARA_AVISAR = 2;

/** Dias até ao instante dado, contados em dias civis locais. */
function diasAte(instante: string): number {
  const alvo = new Date(instante);
  const agora = new Date();
  // Compara **dias civis** e não milissegundos: "expira amanhã" é uma afirmação
  // sobre o calendário de quem lê, e um `Math.ceil` sobre a diferença em horas
  // dizia "em 1 dia" às 23h de hoje para um prazo que acaba às 2h da manhã.
  const diaDoAlvo = Date.UTC(alvo.getFullYear(), alvo.getMonth(), alvo.getDate());
  const diaDeHoje = Date.UTC(agora.getFullYear(), agora.getMonth(), agora.getDate());
  return Math.round((diaDoAlvo - diaDeHoje) / 86_400_000);
}

interface Leitura {
  readonly texto: string;
  readonly corDoTexto: string;
  readonly icone: LucideIcon;
  readonly corDoIcone: string;
}

function leituraDe(convite: Convite): Leitura | null {
  if (convite.estado === "aceite" || convite.estado === "revogado") return null;

  const dias = diasAte(convite.expira_em);

  if (convite.estado === "expirado") {
    return {
      texto:
        dias === 0 ? textos.validade.expirouHoje : textos.validade.expirouQuando(formatDaysAway(dias)),
      corDoTexto: "text-warning",
      icone: CircleSlash,
      corDoIcone: "text-warning",
    };
  }

  if (dias <= 0) {
    // `pendente` com a data passada: a corrida entre a lista que está no ecrã e
    // o relógio do servidor. Diz-se o que se sabe ("acaba hoje") em vez de se
    // escolher entre duas afirmações, e o `estado` ao lado é a autoridade.
    return {
      texto: textos.validade.acabaHoje,
      corDoTexto: "text-warning",
      icone: Clock,
      corDoIcone: "text-warning",
    };
  }

  if (dias <= DIAS_PARA_AVISAR) {
    return {
      texto: textos.validade.expiraQuando(formatDaysAway(dias)),
      corDoTexto: "text-warning",
      icone: Clock,
      corDoIcone: "text-warning",
    };
  }

  return {
    texto: textos.validade.validoAte(formatDayMonth(convite.expira_em)),
    corDoTexto: "text-muted-foreground",
    icone: CircleCheck,
    corDoIcone: "text-success",
  };
}

export function ValidadeDoConvite({ convite }: { readonly convite: Convite }) {
  const leitura = leituraDe(convite);

  if (leitura === null) {
    return (
      <span className="text-muted-foreground">
        {/* Um travessão sozinho é lido como "menos" por alguns leitores de ecrã,
            e aqui o que falta não é um valor — é o significado. A palavra está
            à vista para todos e não escondida num `sr-only`. */}
        {textos.validade.semPrazo}
      </span>
    );
  }

  const Icone = leitura.icone;

  return (
    <span
      className={`flex min-w-0 items-center gap-1.5 ${leitura.corDoTexto}`}
      title={textos.validade.linkExpiraA(formatDate(convite.expira_em))}
    >
      <Icone aria-hidden="true" className={`size-3.5 shrink-0 ${leitura.corDoIcone}`} />
      <span className="truncate">{leitura.texto}</span>
    </span>
  );
}
