import { createRoute, lazyRouteComponent } from "@tanstack/react-router";

import { rotaDaApp } from "./app";
import { buscaDeDefinicoesSchema } from "./busca-de-definicoes";

/**
 * `/definicoes` — **o** ecrã de definições (ADR 0019, decisão 6).
 *
 * Substitui as três rotas que havia: `/preferencias` (pessoal, fora do registo),
 * `/configuracao` e `/convites` (as duas no menu, restritas ao `owner`). O
 * caminho é copy — a ADR 0008 fixa que "os URLs são em português porque são copy
 * de produto" — logo muda com a palavra: **"Definições" é o termo pt-PT** e
 * "Configurações" é o pt-BR.
 *
 * **Sem redirects das três antigas**, e isso é uma decisão: a app é
 * pré-lançamento e ninguém tem marcadores. O que torna a remoção segura não é
 * essa aposta — é o compilador: o `to` de um `<Link>` é tipado pela árvore de
 * rotas, logo um link esquecido para `/preferencias` **não compila**. A remoção
 * é verificada em vez de procurada.
 *
 * ## Fora do `REGISTO_DE_ROTAS`, e agora pelas duas razões juntas
 *
 * A ADR 0017 já punha o ecrã pessoal fora do registo: uma rota pessoal dentro de
 * uma projecção **por tenant** deixava uma empresa esconder um ecrã pessoal aos
 * seus colaboradores. A isso junta-se a razão da ADR 0019: **definições não
 * respondem a uma pergunta de operação**, e é isso que uma entrada no registo
 * significa — o campo `pergunta` existe para o dizer (DESIGN.md §1). O menu é a
 * projecção de que *ecrãs de operação* uma empresa mostra às suas pessoas, nunca
 * se alguém alcança as suas definições.
 *
 * ## Sem `beforeLoad` a verificar o papel
 *
 * Esconder é apresentação; autorizar é do servidor (ADR 0011). Um `beforeLoad` a
 * reencaminhar quem não é `owner` punha uma terceira verificação no caminho — a
 * da secção, a desta rota e a do endpoint — e a do meio é a que fica
 * desactualizada quando a regra mudar. E não apanhava o caso que importa: o papel
 * é por tenant, e trocar de estabelecimento muda o papel **sem mudar o URL**.
 */
export const rotaDeDefinicoes = createRoute({
  getParentRoute: () => rotaDaApp,
  path: "/definicoes",
  validateSearch: buscaDeDefinicoesSchema,
  // A ligação e não o ecrã: a secção Navegação precisa dos defaults do registo
  // do shell, e um `component` de rota é renderizado sem props. A razão inteira
  // está no `ligacao-de-definicoes.tsx`.
  component: lazyRouteComponent(
    () => import("./ligacao-de-definicoes"),
    "DefinicoesLigadas",
  ),
});
