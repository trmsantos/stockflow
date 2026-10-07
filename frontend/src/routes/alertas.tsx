import { createRoute, lazyRouteComponent } from "@tanstack/react-router";

import { rotaDaApp } from "./app";
import { buscaDeAlertasSchema } from "./busca-de-alertas";

export const rotaDeAlertas = createRoute({
  getParentRoute: () => rotaDaApp,
  path: "/alertas",
  validateSearch: buscaDeAlertasSchema,
  component: lazyRouteComponent(
    () => import("@/features/inventory/screens/alertas"),
    "EcraDeAlertas",
  ),
});
