import { createRoute, lazyRouteComponent } from "@tanstack/react-router";

import { rotaRaiz } from "./root";

export const rotaInicial = createRoute({
  getParentRoute: () => rotaRaiz,
  path: "/",
  component: lazyRouteComponent(() => import("@/shell/screens/inicio"), "EcraInicial"),
});
