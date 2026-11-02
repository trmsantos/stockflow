import { createRoute, lazyRouteComponent } from "@tanstack/react-router";

import { rotaDaApp } from "./app";
import { buscaDeReceitasSchema } from "./busca-de-receitas";

/**
 * As três rotas das fichas técnicas (ADR 0035, fatia A).
 *
 * `/receitas` — o URL é em português porque é copy de produto; a pasta da
 * feature é `recipes` porque é o nome do módulo do backend (ADR 0008,
 * decisão 2).
 *
 * ## Três irmãs, e não uma mãe com duas filhas
 *
 * As três penduram-se directamente na `rotaDaApp` e declaram o caminho inteiro,
 * como o `/stock` e o `/stock/$artigo` já fazem. A forma alternativa — a
 * `/receitas` com `addChildren([nova, $receita])` — parece mais arrumada e
 * **tem um modo de falhar silencioso**: uma rota-mãe com `component` só mostra
 * a filha se o componente dela render um `<Outlet/>`, e um ecrã de lista que
 * não o faça serve a lista no endereço da ficha sem um erro em lado nenhum.
 * Está medido no repositório: o `/produtos` tem duas filhas e o ecrã dele não
 * tem `<Outlet/>`. Três irmãs não têm esse estado.
 *
 * A ordem entre `/receitas/nova` e `/receitas/$receita` não depende da ordem do
 * array: o router ordena o segmento estático à frente do dinâmico, logo
 * `/receitas/nova` nunca é lido como uma ficha com o id "nova".
 *
 * ## O mesmo `validateSearch` nas três, e não por simetria
 *
 * É assim que o botão de voltar devolve a lista exactamente como estava — mesma
 * procura, mesmo filtro — sem depender do histórico do browser, e que um link
 * para uma ficha mostrado a alguém reproduz também o contexto de onde saiu. Os
 * parâmetros **não filtram a ficha**: o `GET /recipes/<id>` não os aceita e o
 * cliente não os envia. Ver `busca-de-receitas.ts` para a forma de cada campo.
 *
 * O `?editar=1` é o que distingue ler de escrever na mesma ficha, e só a rota do
 * detalhe o usa — a lista e o ecrã de criar ignoram-no, que é o preço de ter um
 * schema só e é mais barato do que três.
 */
export const rotaDeReceitas = createRoute({
  getParentRoute: () => rotaDaApp,
  path: "/receitas",
  validateSearch: buscaDeReceitasSchema,
  component: lazyRouteComponent(
    () => import("@/features/recipes/screens/receitas"),
    "EcraDeReceitas",
  ),
});

/**
 * `/receitas/nova` — criar é **outra página** e não um `?editar=1`, porque aí
 * ainda não há documento nenhum: não há cabeçalho para mostrar, não há custo
 * para calcular, e o acabado ainda se escolhe (num `PATCH` ele nem sequer é
 * aceite — é a identidade da ficha).
 *
 * Escrever é de `owner|manager` (ADR 0035, decisão 5) e **quem recusa é o
 * servidor**, com 403 em cada pedido. Esta rota existe para todos os papéis, e
 * tem de existir: esconder é apresentação, não autorização (ADR 0009). O que o
 * `staff` não vê é o botão que leva aqui.
 */
export const rotaDeNovaReceita = createRoute({
  getParentRoute: () => rotaDaApp,
  path: "/receitas/nova",
  validateSearch: buscaDeReceitasSchema,
  component: lazyRouteComponent(
    () => import("@/features/recipes/screens/nova-receita"),
    "EcraDeNovaReceita",
  ),
});

/**
 * `/receitas/<id>` — a ficha técnica, que é o mesmo documento a ler e a editar.
 *
 * Uma ficha **inactiva** responde 200 e nunca 404 (ADR 0035, decisão 7):
 * mercadoria que existiu continua auditável, e por isso o ecrã distingue
 * "arquivada" de "não existe".
 */
export const rotaDeFichaTecnica = createRoute({
  getParentRoute: () => rotaDaApp,
  path: "/receitas/$receita",
  validateSearch: buscaDeReceitasSchema,
  component: lazyRouteComponent(
    () => import("@/features/recipes/screens/ficha"),
    "EcraDaFichaTecnica",
  ),
});
