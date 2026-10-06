import { createRoute, lazyRouteComponent } from "@tanstack/react-router";

import { rotaDaApp } from "./app";
import { buscaDoPainelSchema } from "./busca-do-painel";

/**
 * `/` — o Início, que desde a ADR 0013 é o **painel de gestão**.
 *
 * O caminho, o nome e o `route_id` fechado (`inicio`, do `RotaIdEnum` gerado)
 * não mudaram, e a rota continua aberta aos **três** papéis: um `staff` aterra
 * aqui e vê a lista das perguntas da manhã, que é o que ele já via. O que mudou
 * é de onde vem o ecrã — `@/features/reporting/screens/painel` em vez de
 * `@/shell/screens/inicio` —, porque o Início deixou de ser um ecrã sem
 * domínio e o shell não pode importar features (ADR 0008, decisão 2).
 *
 * O `validateSearch` é o que faz desta rota mais do que um caminho: o período e
 * o mês entram tipados e validados, e um URL malformado degrada para o default
 * em vez de explodir dentro do ecrã. Ver `busca-do-painel.ts` para a forma e
 * para a razão de cada campo.
 */
export const rotaInicial = createRoute({
  getParentRoute: () => rotaDaApp,
  path: "/",
  validateSearch: buscaDoPainelSchema,
  component: lazyRouteComponent(
    () => import("@/features/reporting/screens/painel"),
    "EcraDoPainel",
  ),
});
