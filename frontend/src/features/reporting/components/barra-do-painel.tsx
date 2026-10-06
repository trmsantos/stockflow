import { Link } from "@tanstack/react-router";

import { Button } from "@/components/ui/button";
import { formatDayMonthShort, formatTime } from "@/lib/format";

import type { Periodo, PeriodoResolvido } from "../schemas";
import { PERIODOS, rotuloCurtoDoPeriodo } from "../vocabulario";

/**
 * A barra do ecrã: **o seletor de período e a fronteira que ele resolveu**.
 *
 * Vive aqui e não no header do shell pela razão de sempre: o header é do shell
 * e o shell não conhece domínios (ADR 0008, decisão 2). É o mesmo sítio onde o
 * ecrã de Stock põe o seletor de loja — "o seletor de tenant é do shell, o
 * seletor de loja é do ecrã" (DESIGN.md §4) —, e um período é a mesma classe de
 * coisa: define o âmbito do que o ecrã mostra.
 *
 * ## A fronteira ecoada, que é metade do valor desta barra
 *
 * O `PeriodOut` existe para "mostrar a fronteira, não esconder" (ADR 0013,
 * decisão 5), e esta barra é onde ela aparece: `30/09 04:00 → 07/10 04:00`. Não
 * é zelo — é a diferença entre um número que se pode contestar e um número que
 * se tem de acreditar. O dia de negócio começa às **04:00** e isso não é um
 * detalhe de implementação: uma venda das 02:00 pertence ao dia anterior, e é
 * por isso que a hora aparece ao lado da data em vez de se assumir meia-noite.
 *
 * Enquanto o período não chegou do servidor o lugar da fronteira fica
 * **vazio**, e não com um intervalo calculado aqui: o cliente sabe que pediu
 * "7d" e não sabe onde é que o servidor corta os dias. Inventá-lo era mostrar
 * uma fronteira que pode não ser a dos números ao lado.
 */
export function BarraDoPainel({
  periodo,
  resolvido,
}: {
  readonly periodo: Periodo;
  /** O que o servidor diz que esta janela é. `null` enquanto não respondeu. */
  readonly resolvido: PeriodoResolvido | null;
}) {
  return (
    // `top-cabecalho`: a barra do shell tem 56px (`--spacing-cabecalho`) e é
    // este o único cabeçalho que acompanha de facto o scroll — um `thead`
    // sticky não funciona dentro do invólucro que desliza na horizontal, e a
    // razão está escrita no `components/tabela.tsx`.
    <div className="sticky top-cabecalho z-10 flex flex-wrap items-center gap-x-2 gap-y-1 border-b border-border bg-background px-celula-x py-2">
      <nav aria-label="Período do painel" className="flex flex-wrap items-center gap-1">
        {PERIODOS.map((chave) => {
          const ativo = chave === periodo;
          return (
            <Button
              key={chave}
              asChild
              // Dois dos cinco variantes do §3, e nenhum componente novo: o
              // activo um degrau de superfície acima (`secondary`), os outros
              // sem moldura (`ghost`). O que diz qual é o activo a quem lê por
              // áudio é o `aria-current`, não a tinta.
              variant={ativo ? "secondary" : "ghost"}
            >
              <Link
                to="/"
                // O reducer recebe a busca actual já validada pela rota, logo
                // mudar de período **preserva o mês** que está a ser visto no
                // bloco de fecho — são dois grãos independentes (ADR 0013,
                // decisão 5), e perder um ao mexer no outro seria tratá-los
                // como um.
                search={(anteriores) => ({ ...anteriores, period: chave })}
                aria-current={ativo ? "page" : undefined}
              >
                {rotuloCurtoDoPeriodo(chave)}
              </Link>
            </Button>
          );
        })}
      </nav>

      {resolvido === null ? null : (
        <p className="ml-auto min-w-0 truncate text-xs text-muted-foreground">
          <span className="sr-only">Janela: </span>
          <span data-numeric className="text-xs">
            {formatDayMonthShort(resolvido.since)} {formatTime(resolvido.since)}
          </span>
          {" → "}
          <span data-numeric className="text-xs">
            {formatDayMonthShort(resolvido.until)} {formatTime(resolvido.until)}
          </span>
          <span className="hidden sm:inline">
            {" · dia de negócio desde as "}
            {resolvido.business_day_starts_at}
          </span>
        </p>
      )}
    </div>
  );
}
