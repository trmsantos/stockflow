import { EcraDeDefinicoes } from "@/features/accounts/screens/definicoes";
import { REGISTO_DE_ROTAS } from "@/shell/registo-de-rotas";

/**
 * O ecrã de Definições com os defaults das rotas ligados — **a ponte entre a
 * feature e o shell**, e o sítio onde o `pnpm typecheck` a verifica.
 *
 * É a mesma forma do `involucro.tsx` e pela mesma razão. A secção Navegação
 * precisa do nome e do grupo **por omissão** de cada rota, para mostrar "o que
 * esta rota se chama se ninguém lhe mexer" ao lado de um campo vazio. Esses
 * valores vivem no registo do **shell** — são copy do produto, e é lá que se
 * traduzem (ADR 0019, decisão 5) — e uma feature não importa do `shell`: a
 * fronteira do `eslint.config.js` recusa-o, e recusou-o à primeira tentativa
 * deste ecrã.
 *
 * As duas afirmações só são verdadeiras ao mesmo tempo com a feature a
 * **declarar** o que precisa (`DefaultDaRota`, em
 * `features/accounts/components/secao-navegacao.tsx`) e esta camada — a única que
 * pode importar os dois lados — a satisfazê-la. Se o registo perder o `grupo`, ou
 * se a feature pedir um quarto campo, é este ficheiro que deixa de compilar.
 *
 * ## Porque é que existe um ficheiro e não seis linhas na rota
 *
 * O `component` de uma rota é renderizado **sem props** (medido: um
 * `lazyRouteComponent` de um componente com props dá `TS2375`), logo a ligação
 * tem de ser um componente próprio. E vive em ficheiro separado para continuar a
 * entrar por `lazyRouteComponent`: escrita dentro de `definicoes.tsx`, arrastava
 * o ecrã e as quatro secções para o chunk principal — o code-splitting deste
 * repositório é manual, rota a rota, e esquecê-lo é silencioso (ADR 0008).
 *
 * O `Object.entries` corre a cada render e isso é deliberado: são seis entradas,
 * e um `useMemo` aqui era memoização de um `map` de seis elementos num
 * componente que monta uma vez por navegação. A `SecaoNavegacao` memoiza o que
 * importa — o `Map` que ela constrói a partir desta lista.
 */
export function DefinicoesLigadas() {
  const defaults = Object.entries(REGISTO_DE_ROTAS).map(([route_id, entrada]) => ({
    route_id,
    rotulo: entrada.rotulo,
    grupo: entrada.grupo,
  }));

  return <EcraDeDefinicoes defaultsDasRotas={defaults} />;
}
