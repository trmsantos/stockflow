import { createRoute } from "@tanstack/react-router";

import { MolduraPublica } from "@/shell/moldura-publica";

import { rotaRaiz } from "./root";

/**
 * O ramo público: `/entrar` e `/ativar`, **fora** do `AppShell` (ADR 0010).
 *
 * Uma rota de layout sem caminho (`id` e não `path`): os URLs são `/entrar` e
 * `/ativar` e não `/publico/entrar`. O que ela dá aos dois filhos é o
 * invólucro — um painel centrado, sem sidebar, sem header e sem seletor de
 * estabelecimento — e o que ela **não** dá é o `beforeLoad` que exige sessão.
 * É a única parte da aplicação que funciona sem sessão, e é por isso que está
 * separada em vez de ter uma condição dentro do shell.
 *
 * Não tem `beforeLoad` nenhum, e é de propósito: o que cada um dos dois filhos
 * faz com a sessão é diferente (o `/entrar` redirecciona quem já a tem, o
 * `/ativar` serve os dois casos), e um `beforeLoad` comum teria de ser o
 * denominador dos dois, que é não fazer nada.
 *
 * O ramo das reposições de password (`/password/...`, ADR 0010) é o terceiro
 * filho desta rota no dia em que os dois endpoints existirem. Hoje não existem,
 * e uma rota para um endpoint que não existe é um ecrã que não pode funcionar.
 */
export const rotaPublica = createRoute({
  getParentRoute: () => rotaRaiz,
  id: "publico",
  component: MolduraPublica,
});
