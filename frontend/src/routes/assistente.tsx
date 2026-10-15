import { createRoute, lazyRouteComponent } from "@tanstack/react-router";

import { rotaDaApp } from "./app";
import { buscaDeAssistenteSchema } from "./busca-de-assistente";

/**
 * `/assistente` — o chat sobre stock (ADR 0027, decisão 10).
 *
 * Caminho em português porque é copy de produto (ADR 0008). Está no registo de
 * rotas com `campo: false`: funciona por deep link num telemóvel — a lista de
 * conversas vai para uma gaveta — mas é desenhado ao computador, e não é uma
 * rota de campo.
 *
 * Sem `beforeLoad` a verificar o papel: os três papéis usam o assistente (ADR
 * 0027, decisão 8), e o que cada um pode consultar decide-se no servidor, tool a
 * tool.
 */
export const rotaDoAssistente = createRoute({
  getParentRoute: () => rotaDaApp,
  path: "/assistente",
  validateSearch: buscaDeAssistenteSchema,
  component: lazyRouteComponent(
    () => import("@/features/assistente/screens/assistente"),
    "EcraDoAssistente",
  ),
});
