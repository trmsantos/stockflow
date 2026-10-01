import { createRoute, lazyRouteComponent } from "@tanstack/react-router";

import { rotaRaiz } from "./root";

/**
 * `/stock` — o URL é em português porque é copy de produto; a pasta da feature
 * é `inventory` porque é o nome do módulo do backend (ADR 0008, decisão 2).
 *
 * O `validateSearch` do horizonte, da loja e do "só abaixo do mínimo" entra com
 * o ecrã a sério, com um schema Zod: é esse estado no URL que faz um
 * recarregamento, o botão de voltar e um link mostrado ao dono reproduzirem o
 * ecrã que se estava a ver — e é a razão de se ter escolhido este router.
 */
export const rotaDeStock = createRoute({
  getParentRoute: () => rotaRaiz,
  path: "/stock",
  component: lazyRouteComponent(() => import("@/features/inventory/screens/stock"), "EcraDeStock"),
});
