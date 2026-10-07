import { createRoute, lazyRouteComponent } from "@tanstack/react-router";

import { EsqueletoDePainel } from "@/components/esqueleto-de-painel";
import { opcoesDaSessao } from "@/features/accounts/api";
import { ErroPublico } from "@/shell/moldura-publica";

import { rotaPublica } from "./publico";

/**
 * `/ativar` — onde o link do convite aterra. O caminho casa com o nome da rota
 * do backend (`auth/ativar`) de propósito: é o mesmo verbo nos dois lados.
 *
 * Sem `validateSearch`, e **não** é um esquecimento: esta rota não tem search
 * params porque o que ela recebe vem no **fragmento**
 * (`/ativar#<uuid-do-tenant>.<token>`), que não é search, não chega ao servidor
 * e portanto não tem nada que ser validado à entrada de uma rota. Quem o lê é o
 * ecrã, do `location.hash`, e quem o valida é o servidor — o formato do segredo
 * tem uma definição e ela não é do cliente (ADR 0010).
 *
 * ## O `beforeLoad` não decide nada, e ainda assim tem de estar aqui
 *
 * Esta rota serve os dois casos — uma conta nova chega anónima, uma conta que já
 * existe tem de chegar com sessão — logo não há nada para decidir antes de
 * montar. O que ele faz é **uma** coisa: garantir que o `GET /auth/sessao` já
 * correu. Esse pedido leva `ensure_csrf_cookie`, e sem o cookie `csrftoken` o
 * `http.ts` recusa-se — de propósito — a enviar o `POST /auth/ativar`, com um
 * `csrf_ausente` e uma instrução para recarregar a página.
 *
 * O ecrã também lê a sessão (`useSessao`), pelo que o pedido aconteceria de
 * qualquer maneira; a diferença é o **momento**. Sem isto, quem abre o link e
 * escreve a password em dois segundos podia submeter antes de o cookie chegar, e
 * o primeiro erro que via era um erro de CSRF numa página que acabou de abrir.
 * Não é uma corrida teórica: o campo está em branco e o formulário é curto.
 *
 * O `.catch` engole a falha pela razão do `/entrar`: se a sessão não lê, o ecrã
 * diz-no quando o POST falhar, e trocar o formulário de activação por um ecrã de
 * erro deixava sem saída quem tem um link de uso único na mão.
 */
export const rotaDeAtivacao = createRoute({
  getParentRoute: () => rotaPublica,
  path: "/ativar",
  beforeLoad: async ({ context }) => {
    // `query({ staleTime: "static" })` é o substituto do `ensureQueryData`, que
    // está deprecado na versão instalada — a razão e a medição estão no
    // `app.tsx`.
    await context.queryClient.query({ ...opcoesDaSessao(), staleTime: "static" }).catch(() => null);
  },
  component: lazyRouteComponent(
    () => import("@/features/accounts/screens/ativar"),
    "EcraDeAtivacao",
  ),
  pendingComponent: EsqueletoDePainel,
  errorComponent: ErroPublico,
});
