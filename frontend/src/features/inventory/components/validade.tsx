import { CircleAlert, CircleCheck, Clock, type LucideIcon } from "lucide-react";

import { formatDate, formatDayMonth, formatDaysAway } from "@/lib/format";

import type { ValidadeProxima } from "../schemas";

/**
 * A validade mais próxima — o quarto dos quatro dados de uma linha de Stock.
 *
 * Duas regras, e a segunda é a que decide se o dono confia nos alertas:
 *
 *  1. **semáforo por token e texto, nunca só cor.** O ícone e a palavra dizem o
 *     mesmo que a tinta, para quem não distingue vermelho de verde e para quem
 *     lê por áudio. Fora do horizonte o texto fica em `muted-foreground` e só o
 *     ícone leva o `success`: um prazo folgado não é um aviso, e pintar quinze
 *     linhas de verde faria perder as três que importam.
 *
 *  2. **`use_by` e `best_before` não se dizem com as mesmas palavras.**
 *     "Consumir até" é limite legal; "consumir de preferência antes de" é
 *     qualidade. A amêndoa laminada com a durabilidade a acabar não é para
 *     deitar fora, e se o ecrã a marcar como "expira" perde a confiança do dono
 *     na primeira vez (guião da sessão 0, §2). Por isso o `best_before` fala de
 *     **qualidade**, e o seu tecto de cor é o aviso: nunca chega a vermelho.
 *
 * O limiar de dias é o do servidor (`expiring_within_days`) e entra por
 * propriedade — não há aqui uma segunda noção de "a expirar".
 */
interface Leitura {
  readonly texto: string;
  readonly corDoTexto: string;
  readonly icone: LucideIcon;
  readonly corDoIcone: string;
}

function leituraDe(validade: ValidadeProxima, limiarEmDias: number): Leitura {
  const dias = validade.days_away;
  const relativo = formatDaysAway(dias);

  if (validade.kind === "use_by") {
    if (dias < 0) {
      return {
        texto: `expirou ${relativo}`,
        corDoTexto: "text-danger",
        icone: CircleAlert,
        corDoIcone: "text-danger",
      };
    }
    if (dias === 0) {
      return {
        texto: "expira hoje",
        corDoTexto: "text-danger",
        icone: CircleAlert,
        corDoIcone: "text-danger",
      };
    }
    if (dias <= limiarEmDias) {
      return {
        texto: `expira ${relativo}`,
        corDoTexto: "text-warning",
        icone: Clock,
        corDoIcone: "text-warning",
      };
    }
    return {
      texto: `expira a ${formatDayMonth(validade.expires_at)}`,
      corDoTexto: "text-muted-foreground",
      icone: CircleCheck,
      corDoIcone: "text-success",
    };
  }

  if (dias < 0) {
    return {
      texto: `perdeu qualidade ${relativo}`,
      corDoTexto: "text-warning",
      icone: Clock,
      corDoIcone: "text-warning",
    };
  }
  if (dias <= limiarEmDias) {
    return {
      texto: `perde qualidade ${relativo}`,
      corDoTexto: "text-warning",
      icone: Clock,
      corDoIcone: "text-warning",
    };
  }
  return {
    texto: `melhor antes de ${formatDayMonth(validade.expires_at)}`,
    corDoTexto: "text-muted-foreground",
    icone: CircleCheck,
    corDoIcone: "text-success",
  };
}

/** O que se diz em cada caso, por extenso, para quem lê a linha devagar. */
function tituloDe(validade: ValidadeProxima): string {
  const natureza =
    validade.kind === "use_by"
      ? "consumir até (limite legal)"
      : "consumir de preferência antes de (qualidade)";
  return `Lote ${validade.lot_code} · ${natureza} ${formatDate(validade.expires_at)}`;
}

export function TextoDeValidade({
  validade,
  limiarEmDias,
}: {
  readonly validade: ValidadeProxima | null;
  readonly limiarEmDias: number;
}) {
  if (validade === null) {
    return <span className="text-muted-foreground">sem validade</span>;
  }

  const leitura = leituraDe(validade, limiarEmDias);
  const Icone = leitura.icone;

  return (
    <span className={`flex min-w-0 items-center gap-1 ${leitura.corDoTexto}`} title={tituloDe(validade)}>
      <Icone aria-hidden="true" className={`size-3.5 shrink-0 ${leitura.corDoIcone}`} />
      <span className="truncate">{leitura.texto}</span>
    </span>
  );
}
