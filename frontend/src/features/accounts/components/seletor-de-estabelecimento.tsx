import { nomeDoPapel, type Estabelecimento } from "../schemas";

/**
 * O ecrã de escolha do estabelecimento, que a ADR 0007 deixou em aberto no
 * cliente e que a ADR 0010 põe no ramo público.
 *
 * ## Botões e não um `<Select>`, e a razão é de estado e não de gosto
 *
 * Um `<Select>` tem um valor e um submit em dois passos; aqui o clique **é** a
 * escolha e não há um segundo passo que faça sentido ("escolheu, agora
 * confirme"). São também poucos itens — quem pertence a três estabelecimentos é
 * o caso raro —, e a lista aberta mostra o **papel** em cada um, que é a
 * informação que distingue dois nomes parecidos.
 *
 * Note-se o que isto **não** é: não é o seletor de estabelecimento do shell,
 * que vive no pé da sidebar (DESIGN.md §4, ADR 0009), nem o seletor de loja de
 * um ecrã. Parecem a mesma coisa e não são — este corre **antes** de haver
 * âmbito, e é a única coisa que há no ecrã enquanto corre.
 *
 * ## O trilho de 4px
 *
 * É o cromado desta identidade (DESIGN.md §2: "um trilho de 4px em
 * `--color-primary` na linha e no item de menu activos"), e aqui marca a linha
 * sob o ponteiro ou com o foco. Fica em `border` em repouso e acende a
 * `primary`: um trilho que só aparece no hover dava uma lista que salta de
 * largura, e animar largura é proibido (§2, movimento).
 *
 * A altura é `h-linha` (44px, o token), que é ao mesmo tempo a linha de tabela
 * da identidade e o alvo de toque mínimo do §4.
 */
export function SeletorDeEstabelecimento({
  estabelecimentos,
  aEscolher,
  emCurso,
  aoEscolher,
}: {
  readonly estabelecimentos: readonly Estabelecimento[];
  /** Há um pedido a sair: a lista inteira fica inerte. */
  readonly aEscolher: boolean;
  /** `id` do estabelecimento cujo pedido está a sair, para o rótulo mudar só nele. */
  readonly emCurso: string | null;
  readonly aoEscolher: (estabelecimento: Estabelecimento) => void;
}) {
  return (
    <ul className="flex flex-col gap-2">
      {estabelecimentos.map((estabelecimento) => {
        const esteEmCurso = emCurso === estabelecimento.id;
        return (
          <li key={estabelecimento.id}>
            <button
              type="button"
              disabled={aEscolher}
              aria-busy={esteEmCurso}
              onClick={() => {
                aoEscolher(estabelecimento);
              }}
              className="group flex min-h-linha w-full items-center gap-3 overflow-hidden rounded-lg border border-border-strong bg-surface-2 pr-celula-x text-left transition-colors hover:border-primary disabled:pointer-events-none disabled:opacity-50"
            >
              {/* O trilho. Decoração: o que um leitor de ecrã ouve é o nome e o
                  papel, por isso não leva texto alternativo nenhum. */}
              <span
                aria-hidden="true"
                className="h-linha w-trilho shrink-0 bg-border transition-colors group-hover:bg-primary"
              />
              <span className="min-w-0 flex-1 truncate text-sm font-medium">
                {estabelecimento.nome}
              </span>
              <span className="shrink-0 text-xs font-bold tracking-microrotulo text-muted-foreground uppercase">
                {esteEmCurso ? "a entrar…" : nomeDoPapel(estabelecimento.papel)}
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
