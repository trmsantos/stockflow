import { createRoute, lazyRouteComponent } from "@tanstack/react-router";

import { rotaDaApp } from "./app";
import { buscaDeFotografarSchema } from "./busca-de-fotografar";
import { buscaDeRececoesSchema } from "./busca-de-rececoes";

/** `/receber` — "o que chegou, e está certo?". */
export const rotaDeReceber = createRoute({
  getParentRoute: () => rotaDaApp,
  path: "/receber",
  validateSearch: buscaDeRececoesSchema,
  component: lazyRouteComponent(
    () => import("@/features/purchasing/screens/receber"),
    "EcraDeReceber",
  ),
});

/**
 * `/receber/fotografar` — a entrada do documento de fornecedor.
 *
 * É uma rota e não um painel por duas razões: tem URL próprio (logo o botão de
 * voltar funciona e o que lá está pode ser mostrado a alguém), e o que lá está é
 * trabalho a sério — a zona de ficheiro, o documento que entrou e o que o modelo
 * leu —, não um diálogo a despachar. Fica antes da rota com parâmetro de
 * propósito: o TanStack Router prefere o caminho literal, e assim
 * `/receber/fotografar` nunca é lido como o id de uma receção.
 *
 * **É a única das três que não carrega o `buscaDeRececoesSchema` tal e qual.**
 * Carrega o `buscaDeFotografarSchema`, que o estende com o documento escolhido
 * (ADR 0020, decisão 2b): o filtro continua a viajar para o link de voltar, e o
 * uuid do documento fica só nesta rota em vez de aparecer no tipo da lista e do
 * detalhe.
 */
export const rotaDeFotografar = createRoute({
  getParentRoute: () => rotaDaApp,
  path: "/receber/fotografar",
  validateSearch: buscaDeFotografarSchema,
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
  getParentRoute: () => rotaDaApp,
  path: "/receber/$rececao",
  validateSearch: buscaDeRececoesSchema,
  component: lazyRouteComponent(
    () => import("@/features/purchasing/screens/rececao"),
    "EcraDeRececao",
  ),
});
