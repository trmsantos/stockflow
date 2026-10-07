/**
 * O que o shell precisa de saber sobre quem está cá e onde — **declarado pelo
 * shell**, satisfeito pela feature, ligado pela rota.
 *
 * ## Porque é que este tipo existe, em vez de o shell chamar `useSessao()`
 *
 * Há uma contradição entre duas ADRs e ela resolve-se aqui, não em silêncio:
 *
 *  - a ADR 0009 e o DESIGN.md §4 dizem que **o seletor de estabelecimento é do
 *    shell** e vive no pé da sidebar;
 *  - a ADR 0008 (decisão 2) diz que **o shell conhece caminhos de rota, nunca
 *    domínios**, e o `eslint.config.js` impõe-o: `src/shell/**` não importa
 *    `@/features/*`. A ADR 0009 só supera a parte da decisão 2 que trata da tab
 *    bar; esta fronteira fica.
 *
 * As duas são verdadeiras ao mesmo tempo de uma maneira só: **o shell declara a
 * interface e a feature satisfaz-na** (inversão de dependência). O shell desenha
 * o seletor — é dele, como o DESIGN.md diz — e não sabe de onde vêm os dados;
 * o `features/accounts` sabe o que é uma sessão e não sabe que há uma sidebar;
 * e quem liga os dois é a **rota**, que é o papel que o próprio shell já lhe
 * dava ("é a rota que liga o ecrã da feature ao invólucro" — `moldura-publica.tsx`).
 *
 * O que torna isto um contrato e não uma esperança: a passagem acontece em
 * `routes/involucro.tsx` (o `component` da rota `app`), que importa os **dois**
 * lados, logo é o `pnpm typecheck` que verifica que o que a feature devolve
 * serve o que o shell pede. Se o hook deixar de trazer `estabelecimentos`, é a
 * rota que deixa de compilar. Desde 2026-10-06 o mesmo ponto verifica uma
 * segunda interface pelo mesmo mecanismo — a `EntradaDaProjeccao` do `menu.ts`,
 * satisfeita pelo `useMenuDaSessao`.
 *
 * Nenhum tipo do domínio atravessa a fronteira: o `papel` chega como **string
 * já traduzida** (`nomeDoPapel`, do `features/accounts/schemas.ts`), porque o
 * `PapelEnum` é do contrato do backend e o shell não tem nada que o conhecer.
 */

export interface EstabelecimentoDoShell {
  readonly id: string;
  readonly nome: string;
  /** O papel por extenso ("dono", "gerente", "colaborador"). */
  readonly papel: string;
}

export interface SessaoDoShell {
  /** O email de quem está autenticado. `null` enquanto a sessão não chegou. */
  readonly email: string | null;
  /** Onde se está a trabalhar agora. */
  readonly ativo: EstabelecimentoDoShell | null;
  /** Tudo a que esta conta tem acesso — a lista do seletor. */
  readonly estabelecimentos: readonly EstabelecimentoDoShell[];
  /** Há uma troca a sair: o seletor fica inerte. */
  readonly aTrocar: boolean;
  /** A frase de uma troca recusada, pronta para mostrar. `null` = sem erro. */
  readonly erroDaTroca: string | null;
  readonly trocar: (id: string) => void;
  readonly aSair: boolean;
  readonly sair: () => void;
}
