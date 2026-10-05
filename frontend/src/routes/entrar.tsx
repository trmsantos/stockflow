import { createRoute, lazyRouteComponent, redirect } from "@tanstack/react-router";

import { EsqueletoDePainel } from "@/components/esqueleto-de-painel";
import { opcoesDaSessao, sincronizarEstabelecimentoAtivo } from "@/features/accounts/api";
import { ErroPublico } from "@/shell/moldura-publica";

import { buscaDeEntradaSchema } from "./busca-de-entrada";
import { rotaPublica } from "./publico";

/**
 * `/entrar` — o URL é em português porque é copy de produto; a pasta da feature
 * é `accounts` porque é o nome do módulo do backend (ADR 0008, decisão 2).
 *
 * O `beforeLoad` aqui é o **simétrico** do da rota da app, e os dois juntos são
 * o que impede os dois becos: sem sessão não se entra na app, e com sessão não
 * se fica preso num formulário de login.
 *
 * ## Porque este `beforeLoad` engole o erro e o da app não
 *
 * A diferença não é de estilo, é de consequência. Na rota da app, falhar a ler a
 * sessão tem de parar a navegação: montar o shell sem saber quem está lá era
 * disparar pedidos que o servidor recusa. Aqui, falhar a ler a sessão não impede
 * nada — ninguém está a ser deixado entrar — e deixar o erro subir trocava o
 * formulário de entrada por um ecrã de erro no primeiro soluço de rede, que é o
 * pior momento possível para não haver um botão de "Entrar" no ecrã.
 *
 * Quem mostra esse erro é o próprio ecrã, com retry, porque ele sabe uma coisa
 * que esta rota não sabe: sem `GET /auth/sessao` não há cookie `csrftoken`, logo
 * o formulário também não funcionaria. O ecrã mostra o retry em vez do
 * formulário, e não as duas coisas.
 */
export const rotaDeEntrada = createRoute({
  getParentRoute: () => rotaPublica,
  path: "/entrar",
  validateSearch: buscaDeEntradaSchema,
  beforeLoad: async ({ context, search, location }) => {
    // `query({ staleTime: "static" })` é o substituto do `ensureQueryData`, que
    // está deprecado na versão instalada — a razão, a medição e a diferença de
    // semântica entre os dois estão no `app.tsx`.
    const sessao = await context.queryClient
      .query({ ...opcoesDaSessao(), staleTime: "static" })
      .catch(() => null);
    if (sessao === null) return;

    sincronizarEstabelecimentoAtivo(sessao);

    // `escolha_pendente` e `sem_estabelecimento` **ficam** aqui: são dois dos
    // quatro estados deste ecrã, não dois casos de "já entrou". Só `ativa`
    // passa, e é a única em que há um sítio para onde ir.
    if (sessao.estado === "ativa") {
      // `href` e não `to`: o destino vem do URL, já validado como caminho
      // relativo desta aplicação pelo `busca-de-entrada.ts`, e não é um literal
      // que o router conheça em tipo. `throw: true` pela razão do `app.tsx`.
      redirect({ href: alvoDoRegresso(search.destino, location.hash), replace: true, throw: true });
    }
  },
  component: lazyRouteComponent(
    () => import("@/features/accounts/screens/entrar"),
    "EcraDeEntrada",
  ),
  // O painel público tem os seus estados: o skeleton e o erro do shell são
  // desenhados para uma página com sidebar e header, e dentro deste painel
  // ficavam uma caixa dentro de uma caixa.
  pendingComponent: EsqueletoDePainel,
  errorComponent: ErroPublico,
});

/**
 * Para onde vai quem chega a `/entrar` **já com sessão**, arrastando o fragmento
 * quando ele é devido.
 *
 * O caso é estreito e vale a pena nomeá-lo, porque sem estas três linhas produz
 * uma mensagem falsa: alguém com sessão aberta num separador abre o link de um
 * convite noutro, o `/ativar` manda-o a `/entrar?destino=/ativar#<fragmento>`,
 * este `beforeLoad` vê a sessão ativa e redirecciona para `/ativar` **sem o
 * fragmento** — e o ecrã de activação diz "convite inválido" sobre um convite
 * perfeitamente válido.
 *
 * Só para o `/ativar`: o fragmento é um segredo, e levá-lo para qualquer outro
 * destino deixava um token de convite na barra de endereço e no histórico de
 * quem já está dentro da aplicação.
 *
 * **Isto é três linhas duplicadas**, e a duplicação é dita e não escondida: a
 * mesma regra existe no `alvoDepoisDeEntrar` do ecrã (que é quem navega depois
 * de um login bem-sucedido), e a fronteira da ADR 0008 não deixa os dois
 * partilharem-na — uma feature não importa de `src/routes/`, e uma rota só
 * importa `screens/*` e `api` de uma feature. Um módulo partilhado para três
 * linhas seria uma camada nova de que nenhuma das duas é dona; o que impede as
 * duas cópias de divergirem em silêncio é este parágrafo e o do ecrã.
 */
function alvoDoRegresso(destino: string | undefined, hash: string): string {
  const alvo = destino ?? "/";
  if (alvo !== "/ativar") return alvo;
  // O `location.hash` do router vem **sem** o `#` (medido no `router-core`).
  const fragmento = hash.replace(/^#/, "");
  return fragmento === "" ? alvo : `${alvo}#${fragmento}`;
}
