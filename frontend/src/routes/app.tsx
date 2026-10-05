import { createRoute, redirect } from "@tanstack/react-router";

import { opcoesDaSessao, sincronizarEstabelecimentoAtivo } from "@/features/accounts/api";
import { AppShell } from "@/shell/app-shell";

import { rotaRaiz } from "./root";

/**
 * A rota de layout da aplicação: o `AppShell` **e o `beforeLoad` que a ADR 0008
 * deixou em aberto**.
 *
 * A ADR 0008 escreveu-o assim: "o shell não tem autenticação e portanto não tem
 * rota protegida: o `beforeLoad` que redirecciona para o login entra com a
 * sessão da autenticação, e é lá que se decide o ecrã de escolha de tenant que a
 * ADR 0007 deixou em aberto no cliente". É esta rota que fecha as duas pontas.
 *
 * Uma rota de layout sem caminho (`id` e não `path`), logo os URLs dos ecrãs não
 * mudam: `/stock` continua a ser `/stock`. O que muda é que todos eles passam a
 * ter um antepassado comum onde a sessão é exigida **uma** vez, em vez de uma
 * verificação por ecrã — que é a forma de a esquecer no décimo.
 *
 * ## Porque `beforeLoad` e não um `useEffect` no shell
 *
 * Um redireccionamento num efeito corre **depois** do primeiro paint: um deep
 * link para `/stock` sem sessão mostrava a sidebar, o header e os skeletons do
 * ecrã, disparava pedidos que o servidor recusa com 403, e só depois ia para o
 * login. O `beforeLoad` corre antes de montar qualquer componente e o ecrã
 * protegido nunca existe.
 *
 * ## O que ele lê, e de onde
 *
 * A **única** cache que existe. Na primeira entrada é este `GET /auth/sessao`
 * que corre, e é ele que põe o cookie `csrftoken` de que o `http.ts` precisa
 * para deixar sair qualquer escrita; nas navegações seguintes a resposta vem da
 * cache e não há pedido nenhum.
 *
 * ## Uma contradição entre a ADR e a biblioteca, resolvida em favor da semântica
 *
 * A ADR 0010 diz, com estas palavras, que este `beforeLoad` "lê a sessão da
 * cache do TanStack Query (`ensureQueryData`)". Na versão instalada
 * (`@tanstack/react-query` 5.104.0) o `ensureQueryData` está **deprecado** e o
 * `@typescript-eslint/no-deprecated` do `pnpm lint` recusa-o — medido, exit 1.
 * O substituto que a própria deprecação indica é
 * `queryClient.query({ ...options, staleTime: "static" })`.
 *
 * O `staleTime: "static"` não é decoração e a diferença foi medida no código da
 * biblioteca: `query()` **sem** ele avalia `isStaleByTime(staleTime)` e espera
 * por um `fetch` quando a entrada passou dos 30s do `query-client.ts`, ou seja
 * bloqueava a navegação num round-trip a cada minuto de uso; com ele, devolve o
 * que está em cache sempre que exista — que é exactamente o que o
 * `ensureQueryData` fazia, e é a semântica que a ADR nomeia.
 *
 * E é a semântica certa, não só a compatível: o papel deste portão é "há
 * sessão?", não "revalidar a sessão". Quem autoriza é o servidor, em cada
 * endpoint com âmbito, e um portão de cliente que vai perguntar outra vez a cada
 * navegação dá a ilusão de ser o controlo sem o ser. **Fica devido** o caminho
 * da sessão que expira a meio: um 403 `sem_sessao` num pedido de dados tem de
 * trazer a pessoa de volta a `/entrar`, e isso é do shell (a tarefa seguinte),
 * não deste portão.
 *
 * ## O invariante que se usa aqui
 *
 * Testar `estado !== "ativa"` é suficiente, e não há um segundo teste a
 * `tenant_ativo === null`: `estado === "ativa"` ⟺ `tenant_ativo !== null` está
 * testado no backend (ADR 0010) **e** verificado à chegada pelo `sessaoSchema`.
 * Dois testes aqui davam dois ramos, e um deles seria o que nunca corre.
 *
 * Os três estados que não são `ativa` vão todos para `/entrar`, e é lá que se
 * distinguem: `anonimo` vê o formulário, `escolha_pendente` vê o seletor de
 * estabelecimento, `sem_estabelecimento` vê a frase própria. Ramificar aqui
 * daria três redireccionamentos para três rotas que teriam o mesmo invólucro e o
 * mesmo pedido de sessão por baixo.
 */
export const rotaDaApp = createRoute({
  getParentRoute: () => rotaRaiz,
  id: "app",
  component: AppShell,
  beforeLoad: async ({ context, location }) => {
    const sessao = await context.queryClient.query({
      ...opcoesDaSessao(),
      staleTime: "static",
    });

    // Redundante com o `queryFn` (que já o faz em cada resposta) e deliberado:
    // é aqui que o `X-Tenant-ID` tem de estar certo, porque é a partir desta
    // linha que os ecrãs pedem dados. Chamá-lo também no portão é o que torna o
    // ponto 5 da ADR 0010 visível no sítio onde ele importa, em vez de depender
    // de a cache ter sido preenchida por um caminho que o fez.
    sincronizarEstabelecimentoAtivo(sessao);

    if (sessao.estado !== "ativa") {
      // `throw: true` e não `throw redirect(...)`: o `redirect()` devolve um
      // `Response` e não um `Error`, logo o `@typescript-eslint/only-throw-error`
      // recusa — e com razão — ver um `throw` de um objeto qualquer no nosso
      // código. A opção é da própria biblioteca e existe exactamente para isto,
      // o que a torna preferível a desligar a regra para a árvore de rotas.
      redirect({
        to: "/entrar",
        search: destinoDoRegresso(location.href),
        replace: true,
        throw: true,
      });
    }
  },
});

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
 */
function destinoDoRegresso(href: string): { destino?: string } {
  return href === "/" ? {} : { destino: href };
}
