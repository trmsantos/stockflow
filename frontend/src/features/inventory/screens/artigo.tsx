import { Link, useParams } from "@tanstack/react-router";
import { ArrowLeft, CircleAlert, PackageSearch, RotateCcw, TriangleAlert } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { mensagemDeErro } from "@/lib/api/errors";

import { useArtigoEmStock, useMovimentosDoArtigo, useResumoDeStock } from "../api";
import { BadgeDeEstado } from "../components/badge-de-estado";
import { FormularioDeDesperdicio } from "../components/formulario-de-desperdicio";
import { HistoricoDeMovimentos } from "../components/historico-de-movimentos";
import { TextoDeValidade } from "../components/validade";
import type { NivelDeStock } from "../schemas";
import { textoDeQuantidade } from "../vocabulario";

/**
 * O detalhe de um artigo — e não é um extra do ecrã de Stock: é aqui que vivem
 * duas das sondas da sessão 0.
 *
 *  - **Q1 (bloquear ou avisar).** A nata está a 0 L, o formulário deixa registar
 *    a quebra de 2 L e o resultado aparece aqui: `−2,0 L` a vermelho, com um
 *    aviso **suave** — "ficou negativo" — e não um bloqueio nem um modal de
 *    erro. Quem conduz a sessão observa se o dono passa ao lado ou se pára.
 *  - **Q7 (papéis).** Toda a linha do histórico tem autor: "Desperdício
 *    −2,000 L · Ana (balcão) · quebra".
 *
 * Nada aqui edita um número e nada apaga um movimento. O stock muda porque se
 * acrescenta uma linha ao ledger, e é a única forma de o mudar.
 */

function Voltar() {
  return (
    <Button asChild variant="ghost" className="self-start">
      {/* `search={true}` leva de volta os filtros que estavam no URL: a lista
          reaparece na mesma loja, com o mesmo filtro e a mesma procura. */}
      <Link to="/stock" search={true}>
        <ArrowLeft aria-hidden="true" />
        Stock
      </Link>
    </Button>
  );
}

function Esqueleto() {
  return (
    <div aria-busy="true" className="flex flex-col gap-3 px-4">
      <span className="sr-only">A carregar o artigo…</span>
      <Skeleton className="h-7 w-48" />
      <Skeleton className="h-9 w-32" />
      <Skeleton className="h-4 w-full max-w-xs" />
    </div>
  );
}

function Cabecalho({ nivel, limiarEmDias }: { nivel: NivelDeStock; limiarEmDias: number }) {
  const negativo = nivel.status === "negativo";

  return (
    <header className="flex flex-col gap-2 px-4">
      <h1 className="text-2xl font-semibold text-balance">{nivel.short_name}</h1>

      <div className="flex items-baseline justify-between gap-3">
        <span
          data-numeric
          className={`text-3xl font-semibold ${negativo ? "text-danger" : ""}`}
        >
          {textoDeQuantidade(nivel.quantity)}
        </span>
        <BadgeDeEstado estado={nivel.status} />
      </div>

      {/* O limiar de "baixo" fica **dentro** do ecrã e não num painel de
          configurações, para o dono o contestar em voz alta (guião §4, nº 7). A
          unidade de registo também está à vista: é a pergunta do leite ao ml. */}
      <p className="text-xs text-muted-foreground">
        mínimo {textoDeQuantidade(nivel.min_quantity)} · unidade de registo:{" "}
        {nivel.quantity.base_unit}
      </p>

      <div className="text-sm">
        <TextoDeValidade validade={nivel.nearest_expiry} limiarEmDias={limiarEmDias} />
      </div>

      {nivel.by_location.length === 0 ? null : (
        <p className="text-sm text-muted-foreground">
          {nivel.by_location.map((parcela, indice) => (
            <span key={parcela.location.id}>
              {indice === 0 ? "" : " · "}
              {parcela.location.name} <span data-numeric>{textoDeQuantidade(parcela.quantity)}</span>
            </span>
          ))}
        </p>
      )}

      {negativo ? (
        // Aviso **suave**: tinta de aviso, não de erro, e dentro do fluxo. Um
        // modal aqui responderia pelo dono à pergunta que a sessão quer fazer.
        <Alert className="border-warning-border bg-warning-surface">
          <TriangleAlert aria-hidden="true" className="text-warning" />
          <AlertTitle>Ficou negativo</AlertTitle>
          <AlertDescription>
            O stock registado está abaixo de zero. Costuma ser uma entrada que falta registar, ou
            uma saída lançada a mais. Corrige-se com um movimento novo — nada se apaga.
          </AlertDescription>
        </Alert>
      ) : null}
    </header>
  );
}

export function EcraDeArtigo() {
  const { artigo } = useParams({ from: "/app/stock/$artigo" });

  const nivel = useArtigoEmStock(artigo);
  const movimentos = useMovimentosDoArtigo(artigo);
  // O limiar de validade é do servidor. O resumo consolidado é o mesmo pedido
  // que o ecrã de Stock já fez, logo quase sempre vem da cache.
  const resumo = useResumoDeStock();
  const limiarEmDias = resumo.data?.expiring_within_days ?? 0;

  return (
    <section className="flex w-full max-w-2xl flex-col gap-4 py-3">
      <Voltar />

      {nivel.isPending ? <Esqueleto /> : null}

      {nivel.isError ? (
        <div className="px-4">
          <Alert className="border-danger-border bg-danger-surface">
            <CircleAlert aria-hidden="true" className="text-danger" />
            <AlertTitle>Não foi possível carregar o artigo</AlertTitle>
            <AlertDescription className="flex flex-col items-start gap-2">
              <span>{mensagemDeErro(nivel.error)}</span>
              <Button
                variant="outline"
                onClick={() => {
                  void nivel.refetch();
                }}
              >
                <RotateCcw aria-hidden="true" />
                Tentar outra vez
              </Button>
            </AlertDescription>
          </Alert>
        </div>
      ) : null}

      {nivel.data === null ? (
        <div className="flex flex-col items-start gap-3 px-4 py-6">
          <PackageSearch aria-hidden="true" className="size-6 text-muted-foreground" />
          <div className="flex flex-col gap-1">
            <p className="font-medium">Este artigo não está no stock</p>
            <p className="text-pretty text-sm text-muted-foreground">
              Ou nunca teve movimentos, ou o endereço aponta para um artigo de outro
              estabelecimento.
            </p>
          </div>
          <Button asChild variant="outline">
            <Link to="/stock" search={() => ({})}>
              Ver o stock
            </Link>
          </Button>
        </div>
      ) : null}

      {/* Sem artigo não há histórico para mostrar: medido numa renderização, um
          "artigo não encontrado" com um esqueleto de movimentos por baixo é um
          ecrã a contradizer-se. */}
      {nivel.data === null || nivel.data === undefined ? null : (
        <>
          <Cabecalho nivel={nivel.data} limiarEmDias={limiarEmDias} />
          <FormularioDeDesperdicio nivel={nivel.data} />
          <HistoricoDeMovimentos
            movimentos={movimentos.data?.results}
            total={movimentos.data?.count ?? 0}
            aCarregar={movimentos.isPending}
            mensagemDeErro={movimentos.isError ? mensagemDeErro(movimentos.error) : null}
            aoTentarOutraVez={() => {
              void movimentos.refetch();
            }}
          />
        </>
      )}
    </section>
  );
}
