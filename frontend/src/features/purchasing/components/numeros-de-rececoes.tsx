import { Link } from "@tanstack/react-router";

import { ErroAoCarregar } from "@/components/erro-ao-carregar";
import {
  CLASSE_CONTADOR,
  CLASSE_CONTADOR_ATIVO,
  CLASSE_CONTADOR_TOCAVEL,
  CorpoDoContador,
  ReguaDeContadores,
} from "@/components/regua-de-contadores";
import { Skeleton } from "@/components/ui/skeleton";

import type { ResumoDeRececoes } from "../schemas";

/**
 * Os dois números do topo: o que falta rever e o que já foi confirmado hoje
 * (guião §1).
 *
 * **Dois e não três.** O terceiro candidato — "1 entrou sem fatura" — diz-se
 * melhor onde acontece, num badge na linha da guia de remessa. Os dois que ficam
 * são os dois que o dono pergunta de manhã.
 *
 * Os dois são filtros, e o filtro vive no URL: tocar no número põe `?estado=` e
 * a lista de baixo passa a ser aquela. Tocar outra vez limpa. É a mesma mecânica
 * dos outros ecrãs, e é o que faz um recarregamento, o botão de voltar e um link
 * mostrado a alguém reproduzirem o mesmo ecrã.
 *
 * O segundo contador diz **a hora a que o dia de negócio começa**, porque
 * "confirmadas hoje" tem de significar o dia de negócio e não o dia civil: uma
 * entrega lançada às 05:30 pertence ao dia que começou às 04:00, e é a mesma
 * fronteira que o ecrã Alertas usa. A hora vem do servidor.
 *
 * ## Eram mosaicos, e passaram a régua a 2026-10-06
 *
 * A razão está no `components/regua-de-contadores.tsx`. Aqui há uma consequência
 * própria: a régua **não estica para encher a linha**, e com dois contadores isso
 * nota-se mais do que com três. É deliberado — dois campos com 192px e o resto
 * vazio é mais honesto do que dois cartões de 500px, e é o que deixa esta régua e
 * as de três contadores terem a mesma densidade em vez de cada ecrã inventar uma
 * grelha com o número de colunas que lhe dá jeito.
 */
export type VistaDeRececoes = "revisao" | "hoje" | undefined;

function ContadorDeVista({
  figura,
  campo,
  nota,
  titulo,
  ativo,
  vista,
}: {
  readonly figura: string;
  readonly campo: string;
  readonly nota: string;
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
      // contador certo (compara também a search params). O `ativo` fica para a
      // tinta e para saber que um segundo toque **limpa** o filtro.
      className={`${CLASSE_CONTADOR} ${CLASSE_CONTADOR_TOCAVEL} ${ativo ? CLASSE_CONTADOR_ATIVO : ""}`}
    >
      <CorpoDoContador campo={campo} figura={figura} nota={nota} ativo={ativo} />
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
    <ReguaDeContadores>
      <ContadorDeVista
        figura={String(resumo.needs_review_count)}
        campo="por rever"
        nota={linhas === 1 ? "1 linha por rever" : `${String(linhas)} linhas por rever`}
        titulo="Documentos que ainda não deram entrada no stock — nada entra sem revisão"
        ativo={vistaAtiva === "revisao"}
        vista="revisao"
      />
      <ContadorDeVista
        figura={String(resumo.confirmed_today_count)}
        campo="confirmadas hoje"
        nota={`desde as ${resumo.business_day_starts_at}`}
        titulo={`O dia de negócio deste estabelecimento começa às ${resumo.business_day_starts_at} — o que foi confirmado antes dessa hora conta no dia anterior`}
        ativo={vistaAtiva === "hoje"}
        vista="hoje"
      />
    </ReguaDeContadores>
  );
}

/** Pendente: um aviso só, no contentor, para quem ouve o ecrã. */
export function EsqueletoDosNumerosDeRececoes() {
  return (
    <ReguaDeContadores aria-busy="true" rotulo="A carregar os números…">
      {[0, 1].map((indice) => (
        <div key={indice} className={CLASSE_CONTADOR}>
          <Skeleton className="h-3 w-24" />
          <Skeleton className="h-8 w-12" />
        </div>
      ))}
    </ReguaDeContadores>
  );
}

export function ErroDosNumerosDeRececoes({
  aoTentarOutraVez,
}: {
  readonly aoTentarOutraVez: () => void;
}) {
  return (
    <div className="border-b border-border px-celula-x py-3">
      <ErroAoCarregar
        titulo="Não foi possível contar as receções"
        mensagem="A lista abaixo continua a funcionar. Os dois números voltam à segunda tentativa."
        aoTentarOutraVez={aoTentarOutraVez}
      />
    </div>
  );
}
