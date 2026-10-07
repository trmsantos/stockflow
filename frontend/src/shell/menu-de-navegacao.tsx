import { Link } from "@tanstack/react-router";

import type { GrupoDeMenu } from "./menu";
import { textos } from "./textos";

/**
 * A lista de navegação — **uma**, renderizada em dois contentores.
 *
 * Este componente é a resposta literal à ADR 0009 ("a mesma sidebar como drawer
 * a partir do header em mobile"): a sidebar de desktop e a gaveta de mobile
 * passam-lhe o **mesmo** menu e diferem apenas no invólucro. Duas listas
 * divergiam à primeira pergunta do dono, e a navegação de telemóvel passava a
 * mostrar outra coisa que a de desktop — foi por isso que a ADR 0008 já tinha
 * posto os itens num array só, e a razão sobrevive à saída da tab bar.
 *
 * Não há aqui `useMediaQuery` nenhum, e isso é a decisão 1 da ADR 0008: a
 * sidebar está sempre no DOM e é escondida por breakpoint (`hidden md:flex`).
 * A gaveta é outra coisa — um `Dialog` que só existe enquanto está aberta —, mas
 * o **conteúdo** das duas é este componente, não uma segunda lista.
 *
 * ## O trilho de 4px
 *
 * O cromado desta identidade (DESIGN.md §2: "um trilho de 4px em
 * `--color-primary` na linha e no item de menu activos"). É `absolute` à
 * esquerda e transparente em repouso: um trilho que aparecesse e desaparecesse
 * no fluxo fazia a lista saltar de largura, e animar largura é proibido (§2,
 * movimento). O que anima é a **cor**, que é das duas propriedades permitidas
 * por não forçar layout.
 *
 * O `data-[status=active]` vem do `<Link>` do router, que também põe
 * `aria-current="page"` — medido no `link.js`, não presumido: quem navega por
 * leitor de ecrã ouve qual é o item actual sem depender da cor nem do trilho.
 */
export function MenuDeNavegacao({
  menu,
  id,
  recolhida = false,
  aoNavegar,
}: {
  readonly menu: readonly GrupoDeMenu[];
  /** Prefixo dos `id` dos cabeçalhos de grupo: este menu renderiza duas vezes. */
  readonly id: string;
  readonly recolhida?: boolean;
  /** Chamado ao seguir um link. A gaveta usa-o para se fechar. */
  readonly aoNavegar?: (() => void) | undefined;
}) {
  if (menu.length === 0) {
    // **Alcançável, e medido contra o backend real** — o que até 2026-10-06 era
    // uma previsão ("com a projecção em código isto é inalcançável; com a tabela
    // por tenant deixa de o ser"). O caso não exige que alguém se tranque a si
    // mesmo fora do menu: um `PUT /menu` que deixe visível **só** o item dos
    // convites dá, à sessão de um `staff` do mesmo estabelecimento, cinco itens
    // todos com `visivel: false` — o servidor tira-lhe a linha dos convites por
    // papel e o cliente esconde as outras cinco. Resultado medido: `montarMenu`
    // devolve zero grupos e é esta frase que aparece.
    //
    // Um `<nav>` vazio seria UI partida, e a frase diz a coisa certa: as rotas
    // continuam a existir (esconder é apresentação, não autorização), logo há
    // sempre uma saída.
    return (
      <div className="flex min-h-0 flex-1 flex-col items-start gap-3 p-celula-x">
        <p className="text-pretty text-sm text-muted-foreground">
          {textos.navegacao.semItens}
        </p>
        {/* `min-h-linha` (44px) e não só texto: provar que este estado é
            alcançável (ver acima) tornou real uma pergunta que era teórica — num
            telemóvel, esta é a **única** coisa tocável do menu, e um link de
            `text-sm` tem metade do alvo mínimo do DESIGN.md §4. A regra de
            `pointer: coarse` do `base.css` cobre botões e inputs, não um `<a>`
            de texto. 44px é também a altura da linha de menu, logo é o mesmo
            alvo que os itens que aqui faltam. */}
        <Link
          to="/"
          className="inline-flex min-h-linha items-center text-sm text-primary underline underline-offset-4 hover:no-underline"
          onClick={aoNavegar}
        >
          {textos.navegacao.irParaInicio}
        </Link>
      </div>
    );
  }

  return (
    // `overscroll-contain`: dentro da gaveta, chegar ao fim desta lista não
    // passa o scroll à página que está por baixo (e nem à borracha do iOS).
    <div className="flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto overscroll-contain p-2">
      {menu.map((grupo, indice) => {
        // O id é feito do **índice** e não do nome do grupo: o nome vem da
        // projecção por tenant, e um nome com espaço ("Compras e vendas")
        // partia o `aria-labelledby` em dois tokens — o rótulo deixava de casar
        // e nenhum ecrã mostrava o defeito. Com dados configuráveis, o id tem
        // de ser nosso.
        const idDoGrupo = `${id}-grupo-${String(indice)}`;
        return (
          <div key={grupo.nome} className="flex flex-col gap-0.5">
            {recolhida ? (
              <>
                {/* Recolhida não há espaço para o nome do grupo, e um nome
                    truncado a três letras não é informação: fica a régua que
                    diz "mudou de família", e o nome continua a existir para
                    quem lê por áudio. */}
                <span id={idDoGrupo} className="sr-only">
                  {grupo.nome}
                </span>
                <span aria-hidden="true" className="mx-1 my-1.5 h-px bg-border" />
              </>
            ) : (
              // Um `<span>` e não um `<h2>`: o `<h1>` da página é o do **ecrã**
              // (todos os quatro têm o seu), e estes rótulos vêm antes dele no
              // documento — três `h2` antes do `h1` dariam uma árvore de
              // cabeçalhos ao contrário a quem navega por cabeçalhos. O nome do
              // grupo chega ao leitor de ecrã pelo `aria-labelledby` da lista,
              // que é o que o torna "a lista de Inventário" e não "uma lista".
              <span
                id={idDoGrupo}
                className="px-celula-x pt-3 pb-1 text-xs font-bold tracking-microrotulo text-muted-foreground uppercase"
              >
                {grupo.nome}
              </span>
            )}

            <ul aria-labelledby={idDoGrupo} className="flex flex-col gap-0.5">
              {grupo.itens.map((item) => (
                <li key={item.id}>
                  <Link
                    to={item.caminho}
                    activeOptions={{ exact: item.exacto }}
                    title={recolhida ? `${item.rotulo} — ${item.pergunta}` : item.pergunta}
                    onClick={aoNavegar}
                    className="group relative flex h-linha items-center overflow-hidden rounded-lg text-sm text-muted-foreground transition-colors hover:bg-surface-2 hover:text-foreground data-[status=active]:bg-surface-2 data-[status=active]:font-semibold data-[status=active]:text-foreground"
                  >
                    {/* O trilho. Decoração: o estado é dito pelo `aria-current`. */}
                    <span
                      aria-hidden="true"
                      className="absolute inset-y-0 left-0 w-trilho bg-transparent transition-colors group-hover:bg-border-strong group-data-[status=active]:bg-primary"
                    />
                    <span
                      className={
                        recolhida
                          ? "flex w-full items-center justify-center"
                          : "flex w-full min-w-0 items-center gap-3 px-celula-x"
                      }
                    >
                      <item.icone aria-hidden="true" className="size-4 shrink-0" />
                      <span className={recolhida ? "sr-only" : "truncate"}>{item.rotulo}</span>
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        );
      })}
    </div>
  );
}
