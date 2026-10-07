/**
 * Para onde voltar depois de entrar.
 *
 * O `href` traz caminho **e** search params (`/stock?loja=…`), que é o que faz
 * um deep link funcionar de verdade: voltar a `/stock` sem o filtro era voltar a
 * outro ecrã. A raiz não viaja — `?destino=%2F` é ruído num URL que alguém pode
 * ter de ler ao telefone.
 *
 * `replace: true` no redireccionamento: sem ele, o botão de voltar a partir do
 * login voltava ao URL protegido, que redirecciona outra vez para o login — um
 * ciclo que o utilizador experimenta como "o botão de voltar não funciona".
 *
 * ## Porque é que isto tem ficheiro próprio desde 2026-10-06
 *
 * Duas razões, e as duas são boas. A primeira é que ganhou um **segundo
 * consumidor**: o tratador da sessão perdida (`router.tsx`) faz a mesma
 * pergunta — "para onde volta quem foi mandado ao login?" — e duas cópias de
 * três linhas divergiriam na primeira correcção.
 *
 * A segunda foi medida: com a função exportada **e** um componente no
 * `app.tsx`, o `react-refresh/only-export-components` do `pnpm lint` dá exit 1
 * ("fast refresh only works when a file only exports components"). A rota passou
 * a ter um componente nesta sessão (a ligação da sessão ao invólucro), logo a
 * função tinha de sair. A casa não suprime lint (CLAUDE.md): muda-se a forma, e
 * neste caso a forma é melhor.
 */
export function destinoDoRegresso(href: string): { destino?: string } {
  return href === "/" ? {} : { destino: href };
}
