import { Link } from "@tanstack/react-router";

import { formatDayMonth, formatMoney, formatTime } from "@/lib/format";

import type { Rececao } from "../schemas";
import {
  BadgeDeConfirmada,
  BadgeDeNifDiferente,
  BadgeDeRevisao,
  BadgeSemFatura,
  BadgeDeTipo,
} from "./badges-de-rececao";

/**
 * Uma linha da lista de receções: **fornecedor · tipo · nº do documento e data
 * · total · badge** (guião §1), em três filas de texto dentro de um alvo de
 * toque único.
 *
 * A linha inteira é um `<Link>` para o documento e não um `div` com `onClick`:
 * dá de graça o Cmd+clique, o clique do meio e o teclado, e o destino aparece
 * na barra de estado antes de se tocar. Não há ação nenhuma na linha — nem
 * "confirmar" nem "apagar": uma receção confirma-se **dentro**, depois de se
 * olhar para as linhas, que é a regra que este ecrã existe para encarnar.
 *
 * O total é exacto e por isso leva cêntimos: é um total de fatura, não uma
 * estimativa de custo médio. Onde os euros vêm de CMP (valor de stock,
 * desperdício) o DESIGN.md manda arredondar; aqui arredondar seria esconder o
 * número que ele vai comparar com o papel que tem na mão.
 */
export function LinhaDeRececao({ rececao }: { readonly rececao: Rececao }) {
  const porRever = rececao.status === "needs_review";

  return (
    <Link
      to="/receber/$rececao"
      params={{ rececao: rececao.id }}
      search={true}
      className="flex min-h-14 flex-col justify-center gap-1 border-b border-border px-4 py-2 transition-colors hover:bg-surface-2"
    >
      <span className="flex items-baseline gap-3">
        <span className="min-w-0 flex-1 truncate font-medium">{rececao.supplier.name}</span>
        {rececao.document_total === null ? (
          // A guia de remessa não traz preços: a mercadoria entra antes de
          // existir fatura. Dizê-lo é mais honesto do que um "0,00 €".
          <span className="shrink-0 text-xs text-muted-foreground">sem valor</span>
        ) : (
          <span data-numeric className="shrink-0 text-sm">
            {formatMoney(rececao.document_total)}
          </span>
        )}
      </span>

      <span className="flex min-w-0 items-center gap-2 text-xs text-muted-foreground">
        <BadgeDeTipo tipo={rececao.doc_type} />
        <span className="min-w-0 truncate">
          {rececao.doc_number ?? "sem número"}
          {" · "}
          <span data-numeric>{formatDayMonth(rececao.received_at)}</span>{" "}
          <span data-numeric>{formatTime(rececao.received_at)}</span>
        </span>
      </span>

      <span className="flex flex-wrap items-center gap-1.5">
        {porRever ? <BadgeDeRevisao linhas={rececao.lines_to_review} /> : <BadgeDeConfirmada />}
        {rececao.awaiting_invoice ? <BadgeSemFatura /> : null}
        <BadgeDeNifDiferente rececao={rececao} />
      </span>
    </Link>
  );
}
