import { createRoute, lazyRouteComponent } from "@tanstack/react-router";

import { rotaDaApp } from "./app";

/**
 * `/` — o Início, que desde 2026-10-06 é a **fila de trabalho do dia**.
 *
 * O caminho, o nome e o `route_id` fechado (`inicio`, do `RotaIdEnum` gerado)
 * não mudaram, e a rota continua aberta aos três papéis. O que mudou foi o que
 * ela mostra, por decisão do dono do produto: o painel de gestão saiu para
 * `/painel` (só do dono) e o Início passou a ser *"o que está por expirar,
 * coisas a fazer, descargas a chegar"* — com números, e não só portas.
 *
 * ## Sem `validateSearch`, e isso é uma afirmação
 *
 * Tinha quatro parâmetros enquanto foi o painel. A fila do dia **não tem
 * estado**: não tem período, não tem mês, não tem camadas e não tem filtros. É a
 * mesma pergunta todos os dias e a resposta é o que o servidor contou — logo não
 * há nada para pôr no URL, e um parâmetro a mais seria estado que ninguém muda.
 * Os quatro mudaram-se para a rota `/painel`, com o `busca-do-painel.ts` inteiro.
 */
export const rotaInicial = createRoute({
  getParentRoute: () => rotaDaApp,
  path: "/",
  component: lazyRouteComponent(
    () => import("@/features/reporting/screens/inicio"),
    "EcraInicial",
  ),
});
