import { useIsFetching } from "@tanstack/react-query";
import { useRouterState } from "@tanstack/react-router";
import { FlaskConical } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { IndicadorDeCarga } from "@/components/indicador-de-carga";

import { GavetaDeNavegacao } from "./gaveta-de-navegacao";
import { localizarNoMenu, type GrupoDeMenu } from "./menu";
import { rotuloDoCaminho } from "./registo-de-rotas";
import type { SessaoDoShell } from "./sessao-do-shell";
import { textos } from "./textos";

/**
 * A barra de topo: 56px (`h-cabecalho`, DESIGN.md §2), fixa, e o único sítio de
 * onde a navegação de mobile se abre.
 *
 * ## O que está aqui e porquê
 *
 * **O botão da gaveta** (`md:hidden`): em mobile a sidebar está escondida por
 * breakpoint, e a ADR 0009 diz que a navegação de telemóvel é a **mesma**
 * sidebar aberta daqui — não uma tab bar, não uma terceira superfície.
 *
 * **Onde se está, com o grupo**: "Inventário / Stock". O grupo vem da projecção
 * do tenant e o rótulo do item também, pelo que uma empresa que renomeie um
 * item vê o nome dela aqui. Num menu que cresce, o nome do ecrã sozinho não
 * situa.
 *
 * Não é um `<h1>`, e isso é deliberado: **todos** os ecrãs já têm o seu
 * (`sr-only` nos que são listas, visível nos de detalhe). Um segundo `<h1>` no
 * invólucro dava dois títulos de página a quem navega por cabeçalhos, e o que o
 * leitor de ecrã deve anunciar é o do ecrã — não o do cromado.
 *
 * **O indicador de carga**, desde 2026-10-06: três traços que acendem enquanto
 * houver **qualquer** pedido em voo, do `useIsFetching` do TanStack Query. É o
 * sinal que faltava e que o dono do produto pediu duas vezes — os esqueletos
 * dizem que forma vem, e não diziam nada quando a forma já está no ecrã e os
 * dados estão a ser revalidados por trás.
 *
 * Um contador global e não um por ecrã: o shell não sabe que consultas existem
 * (não conhece domínios, ADR 0008 d2) e não precisa de saber — a pergunta que ele
 * responde é "está a acontecer alguma coisa?", que é global por natureza. E
 * porque é uma contagem, não há estado a sincronizar: quando a última consulta
 * assenta, o indicador desaparece sozinho.
 *
 * ## Dois sinais de "dados a fingir", e **não** se juntam num badge só
 *
 * É a parte fácil de "simplificar" para o lado errado, e a ADR 0018 escreveu-a
 * antes de alguém a tentar. As duas afirmações são diferentes:
 *
 *  - **"o servidor de fixtures respondeu"** é sobre o ambiente de
 *    desenvolvimento. É o `Badge` de `import.meta.env.DEV`, que em produção não
 *    existe no bundle;
 *  - **"estás no estabelecimento de demonstração"** é sobre o **tenant**, e tem
 *    de funcionar **em produção**, que é onde ela importa.
 *
 * Colapsá-las dava um sinal de produção que só é testável num ambiente onde está
 * sempre ligado — e o modo de falha é ele nunca aparecer onde interessa e
 * ninguém notar. Em desenvolvimento, num demo, aparecem os dois, e isso é
 * correcto: são duas coisas verdadeiras ao mesmo tempo.
 *
 * A faixa vive **aqui** e não em cada ecrã porque esta barra é `sticky`: está
 * sempre à vista, em todos os ecrãs, e é isso que a torna o que limita alguém a
 * registar no demo uma quebra que era a sério (ADR 0018, decisão 8 — o demo é
 * escrevível de propósito, e o que o protege é a sinalização).
 *
 * Usa os papéis de banner que já existem (`warning-surface`, `warning-border`),
 * porque não se inventam cores (DESIGN.md §2) e porque o amarelo é o registo
 * certo: é um aviso, não um erro.
 *
 * **O que não está aqui**: o seletor de estabelecimento (é do pé da sidebar,
 * DESIGN.md §4) e o seletor de loja (é da barra do **ecrã** — parecem a mesma
 * coisa e não são).
 */
export function AppHeader({
  menu,
  sessao,
}: {
  readonly menu: readonly GrupoDeMenu[];
  readonly sessao: SessaoDoShell;
}) {
  const caminho = useRouterState({
    select: (estado) => estado.location.pathname,
  });
  const aCarregar = useIsFetching() > 0;
  const local = localizarNoMenu(menu, caminho);
  // Um item escondido pela projecção continua a ter rota e a ter nome: o
  // registo é a rede (ver `registo-de-rotas.ts`).
  const rotulo = local?.item.rotulo ?? rotuloDoCaminho(caminho);

  return (
    <header className="sticky top-0 z-20 flex h-cabecalho shrink-0 items-center gap-2 border-b border-border bg-surface px-2 md:px-celula-x">
      <GavetaDeNavegacao menu={menu} sessao={sessao} />

      {rotulo === null ? null : (
        <p className="flex min-w-0 items-center gap-2">
          {local === null ? null : (
            <>
              <span className="hidden shrink-0 text-xs font-bold tracking-microrotulo text-muted-foreground uppercase md:inline">
                {local.grupo}
              </span>
              <span
                aria-hidden="true"
                className="hidden shrink-0 text-muted-foreground md:inline"
              >
                /
              </span>
            </>
          )}
          <span className="truncate text-sm font-semibold">{rotulo}</span>
        </p>
      )}

      {/* `ml-auto` aqui e não no badge: o indicador é o primeiro elemento da
          direita e tem de o ser com ou sem os badges, que são condicionais. */}
      <span className="ml-auto flex shrink-0 items-center gap-3">
        {aCarregar ? <IndicadorDeCarga /> : null}

        {sessao.ativo?.demonstracao === true ? (
          // `role="status"` e não um `<Badge>` decorativo: quem navega por áudio
          // tem de saber que está num estabelecimento de demonstração antes de
          // registar uma quebra lá. Não é `role="alert"` — não houve um evento, é
          // uma condição permanente do ecrã.
          <span
            role="status"
            className="flex shrink-0 items-center gap-1.5 rounded-lg border border-warning-border bg-warning-surface px-2 py-0.5 text-xs font-semibold"
          >
            <FlaskConical aria-hidden="true" className="size-3.5" />
            {/* A palavra inteira a partir de `sm`, e "Demo" num telemóvel: a
                barra tem 56px e o nome do ecrã à esquerda, e um rótulo que
                empurre o nome para fora é pior do que um rótulo curto. */}
            <span className="hidden sm:inline">{textos.cabecalho.demonstracao}</span>
            <span className="sm:hidden">{textos.cabecalho.demonstracaoCurta}</span>
          </span>
        ) : null}

        {import.meta.env.DEV ? (
          // Em desenvolvimento os dados de domínio vêm do servidor de fixtures
          // (ADR 0008, decisão 3) — a autenticação, não: essa é o backend a
          // sério. Dizê-lo no ecrã é a mesma honestidade da abertura da sessão 0.
          // Em produção este ramo não existe.
          <Badge variant="outline" className="shrink-0">
            {textos.cabecalho.dadosDeDemonstracao}
          </Badge>
        ) : null}
      </span>
    </header>
  );
}
