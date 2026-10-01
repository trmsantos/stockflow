import { formatMoney, formatTime } from "@/lib/format";

import type { Desperdicio } from "../schemas";
import { rotuloDeMotivo, textoDeQuantidade } from "../vocabulario";

/**
 * Uma linha do que foi deitado fora: **hora**, artigo, quantidade e euros.
 *
 * É a sonda da Q6 e por isso a hora vem primeiro: "05:10 — Pastéis de ontem,
 * 12 un, 4,20 €" é uma linha que o dono reconhece, e é a partir dela que ele
 * diz "isso é de ontem" — que é a resposta à pergunta sobre a hora a que o dia
 * de negócio começa, sem ela ter sido feita.
 *
 * **Não há ação nenhuma nesta linha, e é de propósito.** Um movimento é
 * append-only (ADR 0006: `REVOKE UPDATE, DELETE`): corrige-se com um movimento
 * inverso, nunca com um botão de apagar — que é a proibição nº 2 do guião §4.
 */
export function LinhaDeDesperdicio({ linha }: { readonly linha: Desperdicio }) {
  return (
    <li className="flex min-h-14 flex-col justify-center gap-0.5 border-b border-border px-4 py-2 last:border-b-0">
      <span className="flex items-baseline gap-3">
        <span data-numeric className="shrink-0 text-sm text-muted-foreground">
          {formatTime(linha.occurred_at)}
        </span>
        <span className="min-w-0 flex-1 truncate font-medium">{linha.short_name}</span>
        <span data-numeric className="shrink-0 text-sm">
          {textoDeQuantidade(linha.quantity)}
        </span>
        <span data-numeric className="w-20 shrink-0 text-sm">
          {formatMoney(linha.value_eur)}
        </span>
      </span>
      <span className="truncate text-xs text-muted-foreground">
        {rotuloDeMotivo(linha.reason)} · {linha.created_by} · {linha.location.name}
        {linha.lot_code === null ? "" : ` · lote ${linha.lot_code}`}
      </span>
    </li>
  );
}
