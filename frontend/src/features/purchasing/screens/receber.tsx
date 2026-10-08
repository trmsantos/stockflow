import { Link, useSearch } from "@tanstack/react-router";
import { FilePlus2, Search, Truck } from "lucide-react";

import { ErroAoCarregar } from "@/components/erro-ao-carregar";
import { EstadoVazio } from "@/components/estado-vazio";
import { Button } from "@/components/ui/button";
import { mensagemDeErro } from "@/lib/api/errors";

import { useRececoes, useResumoDeRececoes } from "../api";
import {
  ErroDosNumerosDeRececoes,
  EsqueletoDosNumerosDeRececoes,
  NumerosDeRececoes,
} from "../components/numeros-de-rececoes";
import {
  EsqueletoDaTabelaDeRececoes,
  TabelaDeRececoes,
} from "../components/tabela-de-rececoes";
import { textos } from "../textos";

/**
 * O ecrã Receber — "o que chegou, e está certo?".
 *
 * Dois números no topo, uma **tabela densa à largura toda** com os documentos, e
 * **a ação principal é a câmara**: fotografar a fatura, a um toque, sem passar
 * por um menu. A barra da ação fica colada ao fundo, onde o polegar chega — é a
 * única barra fixa do shell, e está aqui porque esta é a única das rotas onde a
 * ação vem **antes** de olhar para a lista: a mercadoria está no balcão e a
 * fatura na mão.
 *
 * ## A largura toda, desde 2026-10-06
 *
 * Era uma `<ul>` de cartões de 56px dentro de um `max-w-2xl` — 672px alinhados à
 * esquerda numa área de conteúdo de 1024px —, cada um com três filas de texto e
 * uma tira de badges. O DESIGN.md §4 ainda descreve este ecrã como um dos que
 * "mantêm o cap", e a razão era defensável: Receber é rota de campo, desenhada
 * para 360px.
 *
 * Mudou pela razão que já tinha invertido a ordem no Stock e nos Alertas:
 * **aquele desenho lê-se como UI gerada por IA**, e é isso que o dono do produto
 * não quer mostrar. E a rota de campo não perde nada — o que se faz a 360px
 * neste ecrã é **fotografar a fatura**, e esse botão continua colado ao fundo, ao
 * alcance do polegar. Conferir sete documentos em colunas é trabalho de
 * escritório, e é aí que a tabela paga.
 *
 * **Nada na tabela dá entrada de nada.** Não há "confirmar" numa linha, nem
 * gesto para despachar um documento: uma receção confirma-se dentro, depois de
 * se olhar para as linhas. É a regra do CLAUDE.md — a extração passa por revisão
 * humana antes de gerar movimentos — e a lista é onde ela se vê primeiro: um
 * documento por rever é um documento cujo stock **ainda não existe**.
 *
 * A ordem é a do servidor: o que precisa de revisão primeiro, depois o mais
 * recente. O cliente não reordena, como em todos os outros ecrãs.
 */
export function EcraDeReceber() {
  const busca = useSearch({ from: "/app/receber" });
  const vista = busca.estado;

  const resumo = useResumoDeRececoes();
  const rececoes = useRececoes(vista);

  const linhas = rececoes.data?.results;
  // O servidor pagina a 50. Dizê-lo quando acontece é mais honesto do que
  // mostrar as 50 como se fossem todas.
  const total = rececoes.data?.count ?? 0;
  const truncada = rececoes.data !== undefined && total > rececoes.data.results.length;

  return (
    // Sem `max-w`: a tabela usa a largura toda da área de conteúdo (DESIGN.md
    // §4), e as três regiões — régua, tabela, barra da ação — encostam às
    // arestas e separam-se por réguas de 1px.
    <section className="flex w-full flex-1 flex-col">
      {/* O nome do ecrã está no header do shell, com o grupo. Aqui fica o `h1` do
          documento, para quem navega por cabeçalhos — visível seria a mesma
          palavra duas vezes a 40px de distância. */}
      <h1 className="sr-only">{textos.receber.titulo}</h1>

      {resumo.isPending ? <EsqueletoDosNumerosDeRececoes /> : null}
      {resumo.isError ? (
        <ErroDosNumerosDeRececoes
          aoTentarOutraVez={() => {
            void resumo.refetch();
          }}
        />
      ) : null}
      {resumo.data === undefined ? null : (
        <NumerosDeRececoes resumo={resumo.data} vistaAtiva={vista} />
      )}

      {rececoes.isPending ? <EsqueletoDaTabelaDeRececoes /> : null}

      {rececoes.isError ? (
        <ErroAoCarregar
          titulo={textos.receber.erroAoCarregar}
          mensagem={mensagemDeErro(rececoes.error)}
          aoTentarOutraVez={() => {
            void rececoes.refetch();
          }}
        />
      ) : null}

      {linhas === undefined ? null : (
        <>
          <p aria-live="polite" className="sr-only">
            {textos.receber.contagem(linhas.length)}
          </p>

          {linhas.length === 0 ? (
            vista === undefined ? (
              <EstadoVazio
                icone={Truck}
                titulo={textos.receber.vazioTitulo}
                descricao={textos.receber.vazioCorpo}
              >
                <Button asChild>
                  <Link to="/receber/fotografar" search={true}>
                    <FilePlus2 aria-hidden="true" />
                    {textos.comuns.novoDocumento}
                  </Link>
                </Button>
              </EstadoVazio>
            ) : (
              <EstadoVazio
                icone={Search}
                titulo={textos.receber.filtroVazioTitulo}
                descricao={
                  vista === "revisao"
                    ? textos.receber.filtroVazioRevisao
                    : textos.receber.filtroVazioHoje
                }
              >
                <Button asChild variant="outline">
                  <Link to="/receber" search={() => ({})}>
                    {textos.receber.verTudo}
                  </Link>
                </Button>
              </EstadoVazio>
            )
          ) : (
            <>
              <TabelaDeRececoes rececoes={linhas} />
              {/* A regra de ordenação e a regra do produto ficam no fim, onde não
                  pagam pixéis acima da dobra: quem chega ao fundo da tabela é
                  quem precisa de saber porque é que ela não está por data. */}
              <p className="px-celula-x py-3 text-xs text-muted-foreground">
                {textos.receber.rodapeDaLista(linhas.length, truncada ? total : null)}
              </p>
            </>
          )}
        </>
      )}

      {/* A ação principal, colada ao fundo e ao alcance do polegar.
          **A tab bar saiu** (ADR 0009), e com ela os `3.5rem` que este `bottom`
          descontava — eram a altura dela, e este era o único sítio fora do shell
          onde ela estava escrita. Fica `bottom-0`: a barra assenta no fundo da
          janela nas duas larguras.
          O que **não** sai é a barra de gestos do telemóvel, que só o
          dispositivo conhece e que taparia o botão: entra como `env()` no
          `style`, porque não é uma decisão de design e portanto não é um token
          (é a mesma razão, e a mesma forma, que a tab bar usava).
          O `mt-auto` mantém a barra em baixo quando a lista é curta, em vez de a
          deixar a meio do ecrã. */}
      <div
        className="sticky bottom-0 z-10 mt-auto flex flex-col items-start gap-1 border-t border-border bg-background px-celula-x pt-2"
        style={{ paddingBottom: "calc(var(--spacing) * 2 + env(safe-area-inset-bottom))" }}
      >
        <Button asChild>
          <Link to="/receber/fotografar" search={true}>
            <FilePlus2 aria-hidden="true" />
            {textos.comuns.novoDocumento}
          </Link>
        </Button>
      </div>
    </section>
  );
}
