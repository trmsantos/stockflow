import { Link } from "@tanstack/react-router";
import { Funnel } from "lucide-react";

import { ErroAoCarregar } from "@/components/erro-ao-carregar";
import {
  CLASSE_GRELHA,
  CLASSE_MOSAICO,
  CLASSE_NUMERO,
  CLASSE_ROTULO,
} from "@/components/mosaico";
import { Skeleton } from "@/components/ui/skeleton";

import type { ResumoDeRececoes } from "../schemas";

/**
 * Os dois números do topo: "1 receção a precisar de revisão · 3 confirmadas
 * hoje" (guião §1).
 *
 * **Dois e não três.** O orçamento de 360×640 é de três números *ou* uma linha a
 * mais na lista (guião §0), e o terceiro candidato — "1 entrou sem fatura" —
 * diz-se melhor onde acontece, num badge na linha da guia de remessa. Os dois
 * que ficam são os dois que o dono pergunta de manhã: o que falta rever, e o que
 * já está feito.
 *
 * Os dois são filtros, e o filtro vive no URL: tocar no número põe `?estado=` e
 * a lista de baixo passa a ser aquela. Tocar outra vez limpa. É a mesma mecânica
 * dos outros ecrãs, e é o que faz um recarregamento, o botão de voltar e um link
 * mostrado a alguém reproduzirem o mesmo ecrã.
 *
 * O segundo mosaico diz **a hora a que o dia de negócio começa**, porque
 * "confirmadas hoje" tem de significar o dia de negócio e não o dia civil: uma
 * entrega lançada às 05:30 pertence ao dia que começou às 04:00, e é a mesma
 * fronteira que o ecrã Alertas usa. A hora vem do servidor.
 */
export type VistaDeRececoes = "revisao" | "hoje" | undefined;

function Mosaico({
  valor,
  rotulo,
  extra,
  titulo,
  ativo,
  vista,
}: {
  readonly valor: number;
  readonly rotulo: string;
  readonly extra: string;
  readonly titulo: string;
  readonly ativo: boolean;
  readonly vista: "revisao" | "hoje";
}) {
  return (
    <Link
      to="/receber"
      search={(anteriores) => ({ ...anteriores, estado: ativo ? undefined : vista })}
      title={titulo}
      // Sem `aria-current` à mão: o `<Link>` põe `aria-current="page"` no
      // mosaico certo (compara também a search params). O `ativo` fica para a
      // tinta e para saber que um segundo toque **limpa** o filtro.
      className={`${CLASSE_MOSAICO} transition-colors ${
        ativo
          ? "border-primary bg-surface-2"
          : "border-border-strong bg-surface hover:bg-surface-2"
      }`}
    >
      <span data-numeric className={CLASSE_NUMERO}>
        {valor}
      </span>
      <span className={`flex items-center gap-1 ${CLASSE_ROTULO}`}>
        {ativo ? (
          <>
            <Funnel aria-hidden="true" className="size-3 shrink-0 text-primary" />
            <span className="sr-only">A filtrar por </span>
          </>
        ) : null}
        <span className="text-balance">{rotulo}</span>
      </span>
      <span className={`${CLASSE_ROTULO} text-pretty`}>{extra}</span>
    </Link>
  );
}

export function NumerosDeRececoes({
  resumo,
  vistaAtiva,
}: {
  readonly resumo: ResumoDeRececoes;
  readonly vistaAtiva: VistaDeRececoes;
}) {
  const linhas = resumo.needs_review_lines;

  return (
    <div className={`${CLASSE_GRELHA} grid-cols-2`}>
      <Mosaico
        valor={resumo.needs_review_count}
        rotulo="a precisar de revisão"
        extra={linhas === 1 ? "1 linha por rever" : `${String(linhas)} linhas por rever`}
        titulo="Documentos que ainda não deram entrada no stock — nada entra sem revisão"
        ativo={vistaAtiva === "revisao"}
        vista="revisao"
      />
      <Mosaico
        valor={resumo.confirmed_today_count}
        rotulo="confirmadas hoje"
        extra={`desde as ${resumo.business_day_starts_at}`}
        titulo={`O dia de negócio deste estabelecimento começa às ${resumo.business_day_starts_at} — o que foi confirmado antes dessa hora conta no dia anterior`}
        ativo={vistaAtiva === "hoje"}
        vista="hoje"
      />
    </div>
  );
}

/** Pendente: um aviso só, no contentor, para quem ouve o ecrã. */
export function EsqueletoDosNumerosDeRececoes() {
  return (
    <div aria-busy="true" className={`${CLASSE_GRELHA} grid-cols-2`}>
      <span className="sr-only">A carregar os números…</span>
      {[0, 1].map((indice) => (
        <div key={indice} className={`${CLASSE_MOSAICO} border-border bg-surface`}>
          <Skeleton className="h-5 w-10" />
          <Skeleton className="mt-1 h-7 w-full" />
        </div>
      ))}
    </div>
  );
}

export function ErroDosNumerosDeRececoes({
  aoTentarOutraVez,
}: {
  readonly aoTentarOutraVez: () => void;
}) {
  return (
    <ErroAoCarregar
      titulo="Não foi possível contar as receções"
      mensagem="A lista abaixo continua a funcionar. Os dois números voltam à segunda tentativa."
      aoTentarOutraVez={aoTentarOutraVez}
    />
  );
}
