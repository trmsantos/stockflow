import { useIsFetching } from "@tanstack/react-query";
import { useRouterState } from "@tanstack/react-router";
import { FlaskConical } from "lucide-react";

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
 * ## Eram dois sinais de "dados a fingir". Ficou **um**, e o que o outro dizia
 *
 * A regra que os separava continua certa e é por isso que está escrita: as duas
 * afirmações eram diferentes, e colapsá-las num badge só dava um sinal de
 * produção testável apenas onde está sempre ligado.
 *
 *  - **"o servidor de fixtures respondeu"** era sobre o ambiente de
 *    desenvolvimento — um `Badge` dentro de `import.meta.env.DEV`, que em
 *    produção não existia no bundle. **Saiu a 2026-10-27 com a pasta
 *    `fixtures/`** (ADR 0034, decisão 7): o Django serve os últimos sete
 *    recursos, nada mais responde a fingir, e um badge a dizer que sim é a
 *    única coisa que restava a mentir sobre a origem dos dados. Um sinal cujo
 *    referente foi apagado não se mantém "por via das dúvidas" — é
 *    exactamente o inventário que apodrece sozinho;
 *  - **"estás no estabelecimento de demonstração"** é sobre o **tenant**, tem
 *    de funcionar **em produção**, que é onde importa, e fica.
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
          direita e tem de o ser com ou sem a faixa, que é condicional. */}
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
      </span>
    </header>
  );
}
