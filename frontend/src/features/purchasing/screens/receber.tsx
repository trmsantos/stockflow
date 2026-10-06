import { Link, useSearch } from "@tanstack/react-router";
import { Camera, Search, Truck } from "lucide-react";

import { ErroAoCarregar } from "@/components/erro-ao-carregar";
import { EstadoVazio } from "@/components/estado-vazio";
import { Button } from "@/components/ui/button";
import { mensagemDeErro } from "@/lib/api/errors";

import { useRececoes, useResumoDeRececoes } from "../api";
import { EsqueletoDasRececoes } from "../components/esqueletos";
import { LinhaDeRececao } from "../components/linha-de-rececao";
import {
  ErroDosNumerosDeRececoes,
  EsqueletoDosNumerosDeRececoes,
  NumerosDeRececoes,
} from "../components/numeros-de-rececoes";

/**
 * O ecrã Receber — "o que chegou, e está certo?".
 *
 * Dois números no topo, uma linha por documento, e **a ação principal é a
 * câmara**: fotografar a fatura, a um toque, sem passar por um menu. A barra da
 * ação fica colada ao fundo, onde o polegar chega — é a única barra fixa do
 * shell, e está aqui porque esta é a única das quatro tabs onde a ação vem
 * **antes** de olhar para a lista: a mercadoria está no balcão e a fatura na
 * mão.
 *
 * **Nada na lista dá entrada de nada.** Não há "confirmar" numa linha, nem
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
    <section className="flex w-full max-w-2xl flex-1 flex-col">
      {/* O nome do ecrã já está no header do shell; repeti-lo em grande custava
          uma das linhas do orçamento de 360×640. */}
      <h1 className="sr-only">Receber — o que chegou, e está certo?</h1>

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

      {rececoes.isPending ? <EsqueletoDasRececoes /> : null}

      {rececoes.isError ? (
        <ErroAoCarregar
          titulo="Não foi possível carregar as receções"
          mensagem={mensagemDeErro(rececoes.error)}
          aoTentarOutraVez={() => {
            void rececoes.refetch();
          }}
        />
      ) : null}

      {linhas === undefined ? null : (
        <>
          <p aria-live="polite" className="sr-only">
            {linhas.length === 1 ? "1 receção" : `${String(linhas.length)} receções`}
          </p>

          {linhas.length === 0 ? (
            vista === undefined ? (
              <EstadoVazio
                icone={Truck}
                titulo="Ainda não entrou mercadoria"
                descricao="Cada entrada começa num documento do fornecedor — uma fatura, uma fatura simplificada do cash & carry, ou uma guia de remessa. Nada entra no stock sem alguém confirmar as linhas."
              >
                <Button asChild>
                  <Link to="/receber/fotografar" search={true}>
                    <Camera aria-hidden="true" />
                    Fotografar fatura
                  </Link>
                </Button>
              </EstadoVazio>
            ) : (
              <EstadoVazio
                icone={Search}
                titulo="Nenhuma receção neste filtro"
                descricao={
                  vista === "revisao"
                    ? "Não há documentos à espera de revisão. Tudo o que chegou já deu entrada no stock."
                    : "Nenhuma receção foi confirmada no dia de negócio de hoje."
                }
              >
                <Button asChild variant="outline">
                  <Link to="/receber" search={() => ({})}>
                    Ver tudo
                  </Link>
                </Button>
              </EstadoVazio>
            )
          ) : (
            <>
              <ul className="flex flex-col">
                {linhas.map((rececao) => (
                  <li key={rececao.id}>
                    <LinhaDeRececao rececao={rececao} />
                  </li>
                ))}
              </ul>
              <p className="px-4 py-3 text-xs text-muted-foreground">
                {linhas.length === 1 ? "1 documento" : `${String(linhas.length)} documentos`}
                {truncada ? ` de ${String(total)}` : ""} · o que precisa de revisão primeiro ·
                nenhum entra no stock sem ser confirmado
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
        className="sticky bottom-0 z-10 mt-auto flex flex-col items-start gap-1 border-t border-border bg-background px-4 pt-2"
        style={{ paddingBottom: "calc(var(--spacing) * 2 + env(safe-area-inset-bottom))" }}
      >
        <Button asChild>
          <Link to="/receber/fotografar" search={true}>
            <Camera aria-hidden="true" />
            Fotografar fatura
          </Link>
        </Button>
      </div>
    </section>
  );
}
