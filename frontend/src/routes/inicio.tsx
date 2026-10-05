import { createRoute, lazyRouteComponent } from "@tanstack/react-router";

import { rotaDaApp } from "./app";

export const rotaInicial = createRoute({
  getParentRoute: () => rotaDaApp,
  path: "/",
  component: lazyRouteComponent(() => import("@/shell/screens/inicio"), "EcraInicial"),
});
