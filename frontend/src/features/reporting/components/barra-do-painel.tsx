import { Link } from "@tanstack/react-router";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { formatDayMonthShort, formatTime } from "@/lib/format";

import type { AbaDoPainel } from "../abas";
import type { Periodo, PeriodoResolvido } from "../schemas";
import { textos } from "../textos";
import { PERIODOS, rotuloCurtoDoPeriodo } from "../vocabulario";
import { AbasDoPainel } from "./abas-do-painel";

/**
 * A barra do ecrã: **as abas, o controlo da janela, e a fronteira que ela
 * resolveu**.
 *
 * Vive aqui e não no header do shell pela razão de sempre: o header é do shell
 * e o shell não conhece domínios (ADR 0008, decisão 2). É o mesmo sítio onde o
 * ecrã de Stock põe o seletor de loja — "o seletor de tenant é do shell, o
 * seletor de loja é do ecrã" (DESIGN.md §4) —, e um período é a mesma classe de
 * coisa: define o âmbito do que o ecrã mostra.
 *
 * ## Três coisas numa barra, e a ordem é a da pergunta
 *
 * **Qual é a pergunta** (as abas), **de que janela** (o período ou o mês), e
 * **que janela é essa de facto** (a fronteira ecoada). Lida da esquerda para a
 * direita, é a frase que o ecrã está a responder. O controlo da janela muda com
 * a aba, e isso não é um detalhe: o período não manda no fecho do mês e o mês não
 * manda nas perdas do período. Mostrar os dois controlos ao mesmo tempo era
 * oferecer um que não faz nada.
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
 * Enquanto a janela não chegou do servidor o lugar da fronteira fica **vazio**,
 * e não com um intervalo calculado aqui: o cliente sabe que pediu "7d" e não
 * sabe onde é que o servidor corta os dias. Inventá-lo era mostrar uma fronteira
 * que pode não ser a dos números ao lado.
 */
export function BarraDoPainel({
  aba,
  controlo,
  eco,
}: {
  readonly aba: AbaDoPainel;
  /** O seletor de período ou a navegação de mês, conforme a aba. */
  readonly controlo: ReactNode;
  /** A fronteira que o servidor resolveu. `null` enquanto não respondeu. */
  readonly eco: ReactNode;
}) {
  return (
    // `top-cabecalho`: a barra do shell tem 56px (`--spacing-cabecalho`) e é
    // este o único cabeçalho que acompanha de facto o scroll — um `thead`
    // sticky não funciona dentro do invólucro que desliza na horizontal, e a
    // razão está escrita no `components/tabela.tsx`.
    //
    // `items-stretch` e sem padding vertical no contentor: é o que deixa a aba
    // activa ocupar a barra de cima a baixo e o trilho de 4px assentar na
    // própria aresta de baixo, em vez de flutuar a meio.
    <div className="sticky top-cabecalho z-10 flex flex-wrap items-stretch border-b border-border bg-background">
      <AbasDoPainel ativa={aba} />
      {/* `flex-auto` e não `flex-1`, e a diferença mediu-se a 360px: `flex-1` é
          `flex: 1 1 0%`, logo a base é **zero** e este bloco nunca passa para a
          linha de baixo — ficava espremido em 110px ao lado das abas, com o
          botão "Mês anterior" a sair 10px para fora do viewport e a página
          inteira a deslizar na horizontal. Com `flex-auto` a base é o conteúdo:
          abaixo dos ~400px o bloco quebra para a sua própria linha e os botões
          embrulham lá dentro, e acima disso cresce para encher a barra como
          antes. */}
      <div className="flex min-w-0 flex-auto flex-wrap items-center gap-x-2 gap-y-1 border-l border-border px-celula-x py-2">
        {controlo}
        {eco}
      </div>
    </div>
  );
}

/** O seletor de período — cinco janelas, e a activa um degrau de superfície acima. */
export function SeletorDePeriodo({ periodo }: { readonly periodo: Periodo }) {
  return (
    <nav aria-label={textos.barra.periodo} className="flex flex-wrap items-center gap-1">
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
            size="sm"
          >
            <Link
              to="/painel"
              // O reducer recebe a busca actual já validada pela rota, logo
              // mudar de período **preserva** a aba, o mês e a camada de
              // explicação — são grãos independentes (ADR 0013, decisão 5), e
              // perder um ao mexer no outro seria tratá-los como um.
              search={(anteriores) => ({ ...anteriores, period: chave })}
              aria-current={ativo ? "page" : undefined}
            >
              {rotuloCurtoDoPeriodo(chave)}
            </Link>
          </Button>
        );
      })}
    </nav>
  );
}

/** `30/09 04:00 → 07/10 04:00` — a janela que o servidor resolveu. */
export function FronteiraDoPeriodo({
  resolvido,
}: {
  readonly resolvido: PeriodoResolvido | null;
}) {
  if (resolvido === null) return null;

  return (
    <p className="ml-auto min-w-0 truncate text-xs text-muted-foreground">
      <span className="sr-only">{textos.barra.janela}</span>
      <span data-numeric className="text-xs">
        {formatDayMonthShort(resolvido.since)} {formatTime(resolvido.since)}
      </span>
      {" → "}
      <span data-numeric className="text-xs">
        {formatDayMonthShort(resolvido.until)} {formatTime(resolvido.until)}
      </span>
      <span className="hidden sm:inline">
        {textos.barra.diaDeNegocioDesde(resolvido.business_day_starts_at)}
      </span>
    </p>
  );
}
