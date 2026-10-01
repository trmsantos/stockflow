import { createRoute, lazyRouteComponent } from "@tanstack/react-router";

import { rotaRaiz } from "./root";

export const rotaDeContar = createRoute({
  getParentRoute: () => rotaRaiz,
  path: "/contar",
  component: lazyRouteComponent(
    () => import("@/features/inventory/screens/contar"),
    "EcraDeContar",
  ),
});
