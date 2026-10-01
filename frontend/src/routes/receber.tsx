import { createRoute, lazyRouteComponent } from "@tanstack/react-router";

import { buscaDeRececoesSchema } from "./busca-de-rececoes";
import { rotaRaiz } from "./root";

/** `/receber` — "o que chegou, e está certo?". */
export const rotaDeReceber = createRoute({
  getParentRoute: () => rotaRaiz,
  path: "/receber",
  validateSearch: buscaDeRececoesSchema,
  component: lazyRouteComponent(
    () => import("@/features/purchasing/screens/receber"),
    "EcraDeReceber",
  ),
});

/**
 * `/receber/fotografar` — a ação principal do ecrã, e num shell sem câmara o
 * estado honesto que ela abre.
 *
 * É uma rota e não um painel por duas razões: tem URL próprio (logo o botão de
 * voltar funciona e o que lá está pode ser mostrado a alguém), e o que lá está
 * é **texto sobre os três caminhos por onde a mercadoria entra** — que é
 * conteúdo de sessão, não um diálogo a despachar. Fica antes da rota com
 * parâmetro de propósito: o TanStack Router prefere o caminho literal, e assim
 * `/receber/fotografar` nunca é lido como o id de uma receção.
 */
export const rotaDeFotografar = createRoute({
  getParentRoute: () => rotaRaiz,
  path: "/receber/fotografar",
  validateSearch: buscaDeRececoesSchema,
  component: lazyRouteComponent(
    () => import("@/features/purchasing/screens/fotografar"),
    "EcraDeFotografar",
  ),
});

/**
 * `/receber/<id da receção>` — o documento, que é o ecrã que interessa.
 *
 * Carrega o **mesmo** `validateSearch` da lista, como o detalhe de artigo faz
 * com o do Stock: é assim que o link de voltar devolve a lista no mesmo filtro
 * sem depender do histórico do browser.
 */
export const rotaDeRececao = createRoute({
  getParentRoute: () => rotaRaiz,
  path: "/receber/$rececao",
  validateSearch: buscaDeRececoesSchema,
  component: lazyRouteComponent(
    () => import("@/features/purchasing/screens/rececao"),
    "EcraDeRececao",
  ),
});
