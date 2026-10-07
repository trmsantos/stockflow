import { createRoute, lazyRouteComponent } from "@tanstack/react-router";

import { rotaDaApp } from "./app";

/**
 * `/preferencias` — as definições desta pessoa (ADR 0016 e ADR 0017).
 *
 * ## A única rota da app **sem** entrada no registo de rotas, e é deliberado
 *
 * Todas as outras têm um `route_id` do `RotaIdEnum` e uma entrada no
 * `REGISTO_DE_ROTAS` do shell, porque todas aparecem no menu — que é uma
 * projecção **por tenant** (ADR 0011). Esta não: o tema é preferência da pessoa,
 * e uma rota pessoal dentro de uma projecção por estabelecimento deixava uma
 * empresa esconder um ecrã pessoal aos seus colaboradores. O ponto de entrada é
 * o pé da sidebar, ao lado do email e da saída da conta.
 *
 * A consequência é visível e está tratada no ecrã: o `rotuloDoCaminho` não
 * conhece este caminho, logo a barra de topo não o nomeia, logo o `<h1>` do ecrã
 * é **visível** em vez de `sr-only`.
 *
 * Gatilho para reverter, da ADR 0017: se na sessão 0 alguém a procurar no menu.
 * Aí é uma entrada no registo dos dois lados, no mesmo commit — o
 * `Record<RotaId, EntradaDoRegisto>` é exaustivo nos dois sentidos e um id só num
 * dos lados não compila.
 *
 * Dentro do ramo da app e portanto atrás do portão de sessão: é uma preferência
 * **de uma conta**, logo não há nada a mostrar sem conta. Sem `validateSearch`,
 * porque o ecrã não tem estado nenhum que valha um URL — a paleta escolhida vive
 * na conta e não na barra de endereço.
 */
export const rotaDePreferencias = createRoute({
  getParentRoute: () => rotaDaApp,
  path: "/preferencias",
  component: lazyRouteComponent(
    () => import("@/features/accounts/screens/preferencias"),
    "EcraDePreferencias",
  ),
});
