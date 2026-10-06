import { createRoute, lazyRouteComponent } from "@tanstack/react-router";

import { rotaDaApp } from "./app";

/**
 * `/convites` — a gestão de convites, dentro do ramo da app.
 *
 * O URL é em português porque é copy de produto; a pasta da feature é `accounts`
 * porque é o nome do módulo do backend (ADR 0008, decisão 2). É o mesmo
 * vocabulário que os endpoints usam (`/api/v1/convites`), nas duas pontas.
 *
 * ## Sem `validateSearch`, e não é um esquecimento
 *
 * Não há estado deste ecrã que pertença ao URL. A lista não tem filtros: são
 * poucas linhas, vêm ordenadas pelo servidor ("mais recentes primeiro" — medido)
 * e o que se procura numa lista de convites é uma pessoa, não um recorte. Um
 * `?estado=pendente` seria um filtro que o backend não tem (não há parâmetro de
 * query nestes endpoints além do `page`) e que o cliente teria de aplicar por
 * cima de uma página de 50 — ou seja, um filtro que mente quando houver 51.
 *
 * E o segredo **nunca** pode entrar no URL: o fragmento do convite vive em estado
 * de componente e em mais nada (ADR 0010). Um `validateSearch` aqui era a porta
 * por onde ele passava a estar na barra de endereço e no histórico.
 *
 * ## Sem `beforeLoad` de papel, e isto é uma decisão
 *
 * A ADR 0010 dá os quatro endpoints ao `owner` e seria fácil pôr aqui um portão
 * que redirecciona quem não o é. Não está, por duas razões que apontam para o
 * mesmo lado:
 *
 *  1. a ADR 0009 é explícita — "esconder é apresentação, não autorização" — e a
 *     consequência dela é que **a rota continua a funcionar**: um marcador
 *     guardado, um URL colado num chat ou um papel que mudou com a página aberta
 *     têm de aterrar em algo que explique, não num redireccionamento silencioso
 *     para o início (que não ensina nada) nem num 404 (que é falso: o ecrã
 *     existe);
 *  2. quem autoriza é o servidor, e está medido: `GET` e `POST /api/v1/convites`
 *     com sessão de um `staff` respondem 403. Um portão aqui seria uma **segunda**
 *     definição de autorização no cliente — exactamente o que o registo de rotas
 *     recusa quando recusa um `papelMinimo`.
 *
 * O que o papel decide, decide-o onde é apresentação: a entrada do menu
 * (`routes/involucro.tsx`) e o corpo do ecrã, que mostra a frase e **não dispara**
 * o pedido que já sabe recusado. O portão de sessão continua a ser um só e está
 * no antepassado comum (`rotaDaApp`), onde é exigido uma vez em vez de uma vez
 * por ecrã.
 */
export const rotaDeConvites = createRoute({
  getParentRoute: () => rotaDaApp,
  path: "/convites",
  component: lazyRouteComponent(
    () => import("@/features/accounts/screens/convites"),
    "EcraDeConvites",
  ),
});
