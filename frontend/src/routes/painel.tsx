import { createRoute, lazyRouteComponent } from "@tanstack/react-router";

import { rotaDaApp } from "./app";
import { buscaDoPainelSchema } from "./busca-do-painel";

/**
 * `/painel` — o **painel de gestão**, e é só do dono do estabelecimento.
 *
 * ## Porque é que saiu do Início
 *
 * Esteve em `/` entre a ADR 0013 e 2026-10-06, e o dono do produto mudou a
 * direcção depois de o ver: *"esta aba de dashboard tem de ser outra à parte e
 * não início, porque esta aba de dashboard é apenas para owner do
 * estabelecimento; os outros colaboradores e gerentes no início têm acesso a
 * outra coisa"*. O Início era um ecrã com **três projecções** por papel — o que
 * obrigava cada bloco a saber quem estava a olhar — e passou a ser um ecrã só,
 * igual para todos; o painel passou a ser uma rota própria, fechada ao dono.
 *
 * Isto simplificou o que estava complicado por causa do `manager`: como nenhum
 * bloco do painel é visto por quem não é dono, os **três** endpoints de
 * `reporting` passam a ser de `{owner}` e não só o `/month`.
 *
 * ## O `route_id` é `painel`, e a rota continua a funcionar sem o menu
 *
 * O menu é uma projecção por tenant sobre as rotas que existem (ADR 0009), e
 * quem decide se a linha aparece é o servidor, pelo papel. A rota existe para
 * todos — "esconder é apresentação, não autorização" — e quem a abre sem ser
 * dono não vê um 404: vê a recusa explicada, porque o 403 é do servidor e não
 * deste ficheiro.
 */
export const rotaDoPainel = createRoute({
  getParentRoute: () => rotaDaApp,
  path: "/painel",
  validateSearch: buscaDoPainelSchema,
  component: lazyRouteComponent(
    () => import("@/features/reporting/screens/painel"),
    "EcraDoPainel",
  ),
});
