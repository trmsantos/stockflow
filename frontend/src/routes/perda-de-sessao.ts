import type { QueryClient } from "@tanstack/react-query";
import type { RegisteredRouter } from "@tanstack/react-router";

import { esquecerSessao } from "@/features/accounts/api";
import { registarPerdaDeSessao } from "@/lib/api/sessao-perdida";

import { rotaDaApp } from "./app";
import { destinoDoRegresso } from "./destino";

/**
 * A sessão que expira a meio: o 403 `sem_sessao` que leva a pessoa de volta a
 * `/entrar` **com o `destino` preenchido**.
 *
 * Fecha o que a tarefa do login deixou devido de propósito (`app.tsx`: "um 403
 * `sem_sessao` num pedido de dados tem de trazer a pessoa de volta a `/entrar`,
 * e isso é do shell, não deste portão"). Sem isto a aplicação ficava num estado
 * morto: os ecrãs mostravam o erro de cada query, o portão não voltava a correr
 * (ele é cache-first e **não revalida**, de propósito) e a única saída era um F5.
 *
 * ## Isto não é um controlo de acesso, e a diferença importa
 *
 * Quem autoriza é o servidor, em cada endpoint com âmbito. Este tratador reage a
 * uma **recusa que já aconteceu**; não decide nada e não pode conceder nada. É
 * por isso que ele vive aqui e não no `beforeLoad`: pôr uma revalidação no
 * portão dava a ilusão de ser o controlo sem o ser, e custava um round-trip por
 * navegação.
 *
 * ## As três coisas que faz, e a ordem
 *
 * 1. **esquece a sessão e os dados do estabelecimento** (`esquecerSessao`). Tem
 *    de ser `removeQueries` e não `invalidateQueries`, e a razão está escrita no
 *    `accounts/api.ts`: os portões leem com `staleTime: "static"`, logo uma
 *    entrada invalidada **mas presente** mandava o `/entrar` de volta para o
 *    ecrã protegido — um ciclo;
 * 2. **não navega fora do ramo da app.** Se a recusa aparecer no ramo público
 *    não há para onde ir (já se está no login), e há uma segunda razão de peso:
 *    é no ramo público que o `location` pode levar um **fragmento de convite**, e
 *    o `href` inclui o fragmento (medido no `router-core`: `href = pathname +
 *    search + hash`). Mandá-lo para `?destino=` punha um token de uso único na
 *    query string, que é exactamente o que a ADR 0010 evita ao pôr o segredo no
 *    fragmento;
 * 3. **reencaminha com `replace`**, pela razão do `destinoDoRegresso`: sem ele o
 *    botão de voltar volta ao URL que acabou de recusar.
 *
 * O registo é devolvido para o `App.tsx` o poder desfazer: o tratador fecha
 * sobre **este** router, e um remount em desenvolvimento deixaria o anterior
 * registado.
 *
 * ## Porque é que isto tem ficheiro próprio, e `RegisteredRouter` e não
 * `ReturnType<typeof criarRouter>`
 *
 * As duas coisas são a mesma medição. Dentro do `router.tsx`, anotar o
 * parâmetro com `ReturnType<typeof criarRouter>` é uma **circularidade**: o tipo
 * de retorno do `criarRouter` é inferido da árvore de rotas, que depende da
 * augmentação `Register`, que é declarada a partir do próprio `criarRouter`. O
 * `tsc` não se queixa — resolve para um tipo de erro em silêncio — e quem
 * apanhou foi o `pnpm lint`: `@typescript-eslint/no-unsafe-call` em
 * `router.state.matches.some(...)`, porque o tipo "não se conseguiu resolver".
 * Visto de fora do módulo, o `RegisteredRouter` resolve-se, e é o nome que a
 * própria biblioteca usa nos seus hooks.
 */
export function ligarPerdaDeSessao(
  router: RegisteredRouter,
  queryClient: QueryClient,
): () => void {
  return registarPerdaDeSessao(() => {
    esquecerSessao(queryClient);

    const dentroDaApp = router.state.matches.some((match) => match.routeId === rotaDaApp.id);
    if (!dentroDaApp) return;

    void router.navigate({
      to: "/entrar",
      search: destinoDoRegresso(router.state.location.href),
      replace: true,
    });
  });
}
