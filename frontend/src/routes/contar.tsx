import { createRoute, lazyRouteComponent } from "@tanstack/react-router";

import { rotaDaApp } from "./app";
import { buscaDeContagemSchema, buscaDeFechoSchema } from "./busca-de-contagem";

export const rotaDeContar = createRoute({
  getParentRoute: () => rotaDaApp,
  path: "/contar",
  validateSearch: buscaDeContagemSchema,
  component: lazyRouteComponent(
    () => import("@/features/inventory/screens/contar"),
    "EcraDeContar",
  ),
});

/**
 * `/contar/fechar` — o fecho é uma rota e não um painel dentro do ecrã de
 * contar.
 *
 * A razão é o orçamento de ecrã: as diferenças em quantidade **e** em euros,
 * os três totais e a justificação não cabem debaixo de nove linhas de contagem
 * num 360×640 (guião §0), e empilhá-los lá obrigava a esconder um dos dois —
 * ou as linhas, ou o resultado. Sendo rota, o botão "Fechar contagem" é uma
 * navegação com botão de voltar, e o resultado tem URL próprio.
 */
export const rotaDeFechoDeContagem = createRoute({
  getParentRoute: () => rotaDaApp,
  path: "/contar/fechar",
  validateSearch: buscaDeFechoSchema,
  component: lazyRouteComponent(
    () => import("@/features/inventory/screens/fecho-de-contagem"),
    "EcraDeFechoDeContagem",
  ),
});
