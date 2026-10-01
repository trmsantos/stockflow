import { createRoute, lazyRouteComponent } from "@tanstack/react-router";

import { rotaRaiz } from "./root";

export const rotaDeAlertas = createRoute({
  getParentRoute: () => rotaRaiz,
  path: "/alertas",
  component: lazyRouteComponent(
    () => import("@/features/inventory/screens/alertas"),
    "EcraDeAlertas",
  ),
});
