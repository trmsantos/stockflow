import { Link, useSearch } from "@tanstack/react-router";

import { SecaoAparencia } from "../components/secao-aparencia";
import { SecaoEquipa } from "../components/secao-equipa";
import { SecaoEstabelecimento } from "../components/secao-estabelecimento";
import { SecaoNavegacao, type DefaultDaRota } from "../components/secao-navegacao";
import {
  perguntaDaSecao,
  rotuloDaSecao,
  secaoAMostrar,
  secoesVisiveis,
  PRIMEIRA_SECAO_DA_EMPRESA,
  type SecaoDeDefinicoes,
} from "../secoes";
import { useSessao } from "../api";

/**
 * `/definicoes` — **um** ecrã com todas as definições, em secções (ADR 0019).
 *
 * Substitui o `/preferencias`, o `/configuracao` e o `/convites`, por pedido do
 * dono do produto: *"as definições têm de ser todas num sítio… e lá existem as
 * várias abas de definições"*. A entrada é o pé da sidebar, onde está a pessoa.
 *
 * ## O que isto desfaz, e porque não é uma reversão em silêncio
 *
 * A ADR 0017 tinha decidido **dois** ecrãs e rejeitado por escrito "um ecrã com
 * abas e um 403 por aba", com o argumento de que a autorização passava a estar
 * no desenho da navegação. A ADR 0019 supersede essa decisão e **responde à
 * objecção**, que não desaparece por o dono ter mudado de ideias. Três peças:
 *
 * **1. A secção é um search param com queda para o default**, como o `?aba=` do
 * painel. Um papel que não pode ver uma secção é, para este efeito, o mesmo que
 * um URL malformado — e a ADR 0008 já decidiu o que fazer com esses. **Não há
 * 403 por secção porque não há pedido**: o papel vem na sessão antes de o ecrã
 * montar, as secções da empresa não são renderizadas e os seus hooks não
 * disparam. O 403 do servidor fica onde a ADR 0017 o punha — a rede do deep link
 * e da pertença revogada a meio da sessão.
 *
 * **2. A queda vive no render**, e é a única peça disto que não é cópia de um
 * padrão existente. O papel é **por tenant**, e o seletor de estabelecimento
 * vive no mesmo pé da sidebar que a entrada para este ecrã: quem é `owner` de A
 * e `staff` de B, parado em `?secao=estabelecimento`, troca de casa e fica com
 * uma secção que o papel novo não tem — **sem o URL mudar**, logo sem nada que um
 * `beforeLoad` ou o `validateSearch` possam observar.
 *
 * **3. A fronteira entre as duas famílias continua legível**, e a ADR 0017
 * punha-a no menu (uma era item restrito, a outra não) — resposta que morre
 * aqui. Substitui-se por duas coisas que não são um ícone a explicar uma regra: a
 * régua tem a secção **pessoal primeiro** e uma **separação visível** antes das
 * da empresa, e cada secção da empresa nomeia o **estabelecimento** no seu
 * `<h2>` — que é também a resposta a "qual destas casas é que eu estou a
 * configurar?" para quem tem duas.
 *
 * ## Com uma secção só não há régua
 *
 * Um `staff` vê "Definições" com a Aparência e mais nada, sem régua nenhuma: uma
 * régua de um segmento é um controlo que não escolhe. É também a razão de a
 * Aparência ser a primeira — é a única que os três papéis vêem, logo é o default
 * de todos.
 *
 * ## A régua é `<nav>` + `<Link>`, e não `role="tablist"`
 *
 * A forma copia-se do painel ponta a ponta, incluindo esta escolha: um
 * `role="tablist"` promete ao leitor de ecrã navegação por setas entre tabs, que
 * um conjunto de links não faz. O que isto é mesmo é navegação — cada secção tem
 * URL próprio —, e o `aria-current="page"` diz onde se está. Sem primitivo novo
 * do shadcn.
 */

/** As secções, e o componente de cada uma. Exaustivo nos dois sentidos. */
function Conteudo({
  secao,
  defaultsDasRotas,
}: {
  readonly secao: SecaoDeDefinicoes;
  readonly defaultsDasRotas: readonly DefaultDaRota[];
}) {
  // `switch` sobre a união fechada e não um `Record` de elementos: um `Record`
  // construía os quatro componentes a cada render para mostrar um, e a secção
  // `equipa` dispara pedidos quando monta.
  switch (secao) {
    case "aparencia":
      return <SecaoAparencia />;
    case "estabelecimento":
      return <SecaoEstabelecimento />;
    case "navegacao":
      return <SecaoNavegacao defaults={defaultsDasRotas} />;
    case "equipa":
      return <SecaoEquipa />;
  }
}

export function EcraDeDefinicoes({
  defaultsDasRotas,
}: {
  /**
   * Os nomes e grupos por omissão das rotas, do registo do **shell**.
   *
   * Entra por prop porque uma feature não importa do `shell` (a fronteira do
   * `eslint.config.js` recusa-o) e porque esses valores são copy do produto, que
   * vive no registo do cliente e não no contrato (ADR 0019, decisão 5). Quem os
   * entrega é a rota, a única camada que pode importar os dois lados — a mesma
   * inversão de dependência do `SessaoDoShell`.
   */
  readonly defaultsDasRotas: readonly DefaultDaRota[];
}) {
  const { secao: pedida } = useSearch({ from: "/app/definicoes" });
  const sessao = useSessao();
  const papel = sessao.data?.tenant_ativo?.papel;
  const nomeDaCasa = sessao.data?.tenant_ativo?.nome ?? "";

  const visiveis = secoesVisiveis(papel);
  const secao = secaoAMostrar(pedida ?? "aparencia", papel);
  const daEmpresa = !visiveis.includes("aparencia") || secao !== "aparencia";

  return (
    <div className="flex flex-col gap-5 p-4">
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold text-balance">Definições</h1>
        <p className="max-w-prose text-sm text-muted-foreground">
          A aparência é sua e segue a sua conta. O resto é desta casa e vale para toda a equipa.
        </p>
      </header>

      {visiveis.length > 1 ? (
        <nav aria-label="Secções das definições" className="flex min-w-0 overflow-x-auto">
          <span className="flex divide-x divide-border border-b border-border">
            {visiveis.map((candidata) => (
              <SegmentoDaRegua
                key={candidata}
                secao={candidata}
                activa={candidata === secao}
                /* A separação antes da primeira secção da empresa: é o que
                   substitui a fronteira que a ADR 0017 punha no menu. Derivada e
                   não escrita à mão — ver `PRIMEIRA_SECAO_DA_EMPRESA`. */
                abreAEmpresa={candidata === PRIMEIRA_SECAO_DA_EMPRESA}
              />
            ))}
          </span>
        </nav>
      ) : null}

      <section aria-labelledby="titulo-da-secao" className="flex min-w-0 flex-col gap-3">
        <div className="flex flex-col gap-0.5">
          <h2 id="titulo-da-secao" className="text-lg font-semibold">
            {rotuloDaSecao(secao)}
            {/* O nome da casa no `<h2>` das secções da empresa, e não no da
                pessoal: é a resposta a "qual destas casas é que eu estou a
                configurar?" para quem tem duas, e é metade do que substitui a
                fronteira que vivia no menu. */}
            {daEmpresa && nomeDaCasa !== "" ? (
              <span className="font-normal text-muted-foreground"> · {nomeDaCasa}</span>
            ) : null}
          </h2>
          <p className="text-sm text-muted-foreground">{perguntaDaSecao(secao)}</p>
        </div>

        <Conteudo secao={secao} defaultsDasRotas={defaultsDasRotas} />
      </section>
    </div>
  );
}

/**
 * Um segmento da régua. O mesmo vocabulário do selector de paleta: sem radius,
 * sem borda individual, e o **trilho de 4px** a marcar o escolhido.
 */
function SegmentoDaRegua({
  secao,
  activa,
  abreAEmpresa,
}: {
  readonly secao: SecaoDeDefinicoes;
  readonly activa: boolean;
  readonly abreAEmpresa: boolean;
}) {
  return (
    <Link
      to="/definicoes"
      search={{ secao }}
      aria-current={activa ? "page" : undefined}
      className={
        "relative shrink-0 px-celula-x py-2 text-sm font-semibold transition-colors " +
        (abreAEmpresa ? "ml-2 border-l-2 border-border-strong pl-4 " : "") +
        (activa ? "bg-surface-2" : "text-muted-foreground hover:bg-surface-2")
      }
    >
      {activa ? (
        <span aria-hidden="true" className="absolute inset-x-0 bottom-0 h-trilho bg-primary" />
      ) : null}
      {rotuloDaSecao(secao)}
    </Link>
  );
}
