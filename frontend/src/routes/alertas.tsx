import { createRoute, lazyRouteComponent } from "@tanstack/react-router";

import { buscaDeAlertasSchema } from "./busca-de-alertas";
import { rotaRaiz } from "./root";

export const rotaDeAlertas = createRoute({
  getParentRoute: () => rotaRaiz,
  path: "/alertas",
  validateSearch: buscaDeAlertasSchema,
  component: lazyRouteComponent(
    () => import("@/features/inventory/screens/alertas"),
    "EcraDeAlertas",
  ),
});
