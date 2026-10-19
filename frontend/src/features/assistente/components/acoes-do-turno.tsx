import { Link } from "@tanstack/react-router";
import { ArrowUpRight } from "lucide-react";
import type { ReactElement, ReactNode } from "react";

import { Button } from "@/components/ui/button";

import type { Acao } from "../schemas";
import { textos } from "../textos";
import { rotuloDaAcao } from "../vocabulario";

/**
 * Os botões de uma resposta: para onde se vai a seguir (ADR 0028, decisão 4).
 *
 * ## São ligações, e não "o modelo mandou abrir um ecrã"
 *
 * O modelo **nunca escreve URLs**. O servidor deriva as acções das tools que o
 * turno chamou, por um mapa fechado, e filtra-as pelos papéis de quem pergunta
 * (`apps/agents/navegacao.py`); o cliente valida-as contra o contrato e monta
 * um `<Link>` tipado pela árvore de rotas. Não há caminho entre o texto do
 * modelo e a barra de endereço — por construção, não por confiança.
 *
 * Cada botão é uma **ligação a sério**: navega-se por teclado, abre-se noutro
 * separador com o meio do rato e o texto do botão diz sozinho para onde vai
 * («Rever receções», não «Ver»). O grupo tem nome próprio para quem ouve, senão
 * três ligações seguidas anunciam-se como três «link».
 *
 * ## Secundárias, porque a acção principal do ecrã não é esta
 *
 * `outline` com a fronteira forte (`border-border-strong`, DESIGN.md §2: um
 * controlo delimitado com `--color-border` é um bug de acessibilidade) sobre o
 * `surface`. O acento ciano fica para a identidade do assistente — um botão
 * cheio a seguir a cada resposta competia com o trilho de sinal das tabelas, e
 * o §3 só gasta a ousadia desta identidade lá.
 *
 * Em linha e com quebra: a 1280px cabem os três lado a lado, no painel lateral
 * (≈512px) empilham sem cortar — o `max-w-full` com `truncate` no texto é o que
 * impede «Ver as receções de hoje» de empurrar a gaveta para o lado.
 *
 * ## Três, e os três primeiros
 *
 * O servidor já deduplica por destino e a ordem é a das chamadas, logo os três
 * primeiros são os das tools que a resposta de facto usou primeiro. Mais do que
 * três deixa de ser uma sugestão e passa a ser um menu — e um menu depois de
 * cada resposta é a parede que o fio da conversa existe para não ser.
 */
const MAXIMO_DE_ACOES = 3;

export function AcoesDoTurno({
  acoes,
  aoNavegar,
}: {
  readonly acoes: readonly Acao[];
  /**
   * Chamado ao carregar num botão. No painel lateral fecha a gaveta — a
   * navegação acontece por baixo dela e um painel aberto sobre o ecrã para onde
   * se acabou de ir é o ecrã escondido pela resposta que lá levou. Na página
   * não é passado: não há nada a fechar.
   */
  readonly aoNavegar?: (() => void) | undefined;
}) {
  const visiveis = acoes
    .map((acao) => ({ acao, rotulo: rotuloDaAcao(acao.rotulo_id) }))
    .filter((par): par is { acao: Acao; rotulo: string } => par.rotulo !== undefined)
    .slice(0, MAXIMO_DE_ACOES);

  if (visiveis.length === 0) return null;

  return (
    <ul aria-label={textos.acoes.grupo} className="mt-3 flex flex-wrap gap-2">
      {visiveis.map(({ acao, rotulo }, indice) => (
        // O índice como chave: a lista é derivada do turno e não se reordena,
        // e dois destinos iguais não existem (o servidor deduplica).
        <li key={indice} className="flex min-w-0 max-w-full">
          <Button
            asChild
            variant="outline"
            className="h-controlo min-w-0 max-w-full gap-1.5 border-border-strong bg-surface px-3"
          >
            {ligacao(acao, aoNavegar, rotulo)}
          </Button>
        </li>
      ))}
    </ul>
  );
}

/** O texto do botão mais a seta de "leva-te a outro ecrã". */
function Palavra({ rotulo }: { readonly rotulo: string }): ReactNode {
  return (
    <>
      <span className="min-w-0 truncate">{rotulo}</span>
      <ArrowUpRight aria-hidden="true" className="text-muted-foreground" />
    </>
  );
}

/**
 * A ligação de uma acção, **uma rota por ramo**.
 *
 * O `switch` é o preço de ter `to`, `params` e `search` verificados pelo
 * compilador contra a árvore de rotas real: no ramo do `alertas` o `search`
 * recebe o `{ver?, periodo?}` que o `validateSearch` daquela rota declara, e um
 * parâmetro trocado não compila. Um `to` dinâmico dava `string` e não verificava
 * nada — que é exactamente o que esta fatia não pode permitir-se.
 *
 * O ramo final é um `never`: uma rota nova no contrato (depois do
 * `pnpm gen:api`) alarga a união do `acaoSchema` e **deixa este ficheiro de
 * compilar** até alguém lhe dar um caminho.
 */
function ligacao(acao: Acao, aoNavegar: (() => void) | undefined, rotulo: string): ReactElement {
  const comuns = { onClick: aoNavegar, children: <Palavra rotulo={rotulo} /> };

  switch (acao.rota) {
    case "inicio":
      return <Link {...comuns} to="/" />;
    case "painel":
      return <Link {...comuns} to="/painel" search={acao.parametros} />;
    case "alertas":
      return <Link {...comuns} to="/alertas" search={acao.parametros} />;
    case "assistente":
      return <Link {...comuns} to="/assistente" search={acao.parametros} />;
    case "stock":
      return <Link {...comuns} to="/stock" search={acao.parametros} />;
    case "artigo":
      return (
        <Link
          {...comuns}
          to="/stock/$artigo"
          params={{ artigo: acao.parametros.artigo }}
          search={{}}
        />
      );
    case "contar":
      return <Link {...comuns} to="/contar" search={acao.parametros} />;
    case "receber":
      return <Link {...comuns} to="/receber" search={acao.parametros} />;
    case "rececao":
      return (
        <Link
          {...comuns}
          to="/receber/$rececao"
          params={{ rececao: acao.parametros.rececao }}
          search={{}}
        />
      );
    case "definicoes":
      return <Link {...comuns} to="/definicoes" search={acao.parametros} />;
    default: {
      const naoHaMais: never = acao;
      return naoHaMais;
    }
  }
}
