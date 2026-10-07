import { createRoute, lazyRouteComponent } from "@tanstack/react-router";

import { rotaDaApp } from "./app";

/**
 * `/configuracao` — as definições da empresa (ADR 0017).
 *
 * ## Com entrada no registo de rotas, ao contrário do `/preferencias`
 *
 * As duas rotas nasceram da mesma ADR e estão em lados opostos da mesma decisão,
 * e é por isso que vale lê-las juntas. O `/preferencias` é pessoal e **não**
 * entra no registo: uma rota pessoal dentro de uma projecção por tenant deixava
 * uma empresa esconder um ecrã pessoal aos seus colaboradores. Esta é da empresa
 * e entra, com `papeis = {owner}` — e é isso que torna a distinção legível no
 * próprio menu: a um `staff` o item simplesmente não existe, em vez de existir e
 * levar a um 403.
 *
 * ## Sem `beforeLoad` a verificar o papel, e isso é deliberado
 *
 * Esconder é apresentação; autorizar é do servidor (ADR 0011). Um `beforeLoad` a
 * reencaminhar quem não é `owner` punha uma terceira verificação no caminho — a
 * do menu, a desta rota e a do endpoint — e a do meio é a que fica desactualizada
 * quando a regra mudar. O ecrã mostra o que se passa a quem chega por deep link
 * e não dispara pedido nenhum que já se saiba recusado; o 403 do servidor é a
 * rede da pertença revogada a meio da sessão.
 *
 * Sem `validateSearch`: o rascunho de um menu meio reordenado não é uma vista
 * partilhável, e pô-lo no URL dava um link que recria um estado que o servidor
 * nunca aceitou.
 */
export const rotaDeConfiguracao = createRoute({
  getParentRoute: () => rotaDaApp,
  path: "/configuracao",
  component: lazyRouteComponent(
    () => import("@/features/accounts/screens/configuracao"),
    "EcraDeConfiguracao",
  ),
});
