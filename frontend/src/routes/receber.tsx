import { createRoute, lazyRouteComponent } from "@tanstack/react-router";

import { rotaRaiz } from "./root";

export const rotaDeReceber = createRoute({
  getParentRoute: () => rotaRaiz,
  path: "/receber",
  component: lazyRouteComponent(
    () => import("@/features/purchasing/screens/receber"),
    "EcraDeReceber",
  ),
});
