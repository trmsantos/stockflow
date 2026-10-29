import { Link, useParams } from "@tanstack/react-router";
import { ArrowLeft, CircleAlert, PackageSearch, RotateCcw, TriangleAlert } from "lucide-react";

import { EstadoVazio } from "@/components/estado-vazio";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { eNaoEncontrado, mensagemDeErro } from "@/lib/api/errors";

import { useArtigoEmStock, useMovimentosDoArtigo, useResumoDeStock } from "../api";
import { EstadoDoNivel } from "../components/estado-do-nivel";
import { FormularioDeDesperdicio } from "../components/formulario-de-desperdicio";
import { HistoricoDeMovimentos } from "../components/historico-de-movimentos";
import { TextoDeValidade } from "../components/validade";
import type { NivelDeStock } from "../schemas";
import { textos } from "../textos";
import { textoDeQuantidade } from "../vocabulario";

/**
 * O detalhe de um artigo — e não é um extra do ecrã de Stock: é aqui que vivem
 * duas das sondas da sessão 0.
 *
 *  - **Q1 (bloquear ou avisar).** A nata está a 0 L, o formulário deixa registar
 *    a quebra de 2 L e o resultado aparece aqui: `−2,0 L` a vermelho, com um
 *    aviso **suave** — "ficou negativo" — e não um bloqueio nem um modal de
 *    erro. Quem conduz a sessão observa se o dono passa ao lado ou se pára.
 *  - **Q7 (papéis).** Toda a linha do histórico tem autor, e desde 2026-10-06
 *    numa **coluna** — o que torna a sonda mais afiada do que era: numa coluna
 *    vê-se se é sempre a mesma pessoa a registar, o que numa lista de cartões com
 *    o autor no meio de um rodapé exigia ler as linhas uma a uma.
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
        {textos.artigo.voltar}
      </Link>
    </Button>
  );
}

function Esqueleto() {
  return (
    <div aria-busy="true" className="flex flex-col gap-3 px-4">
      <span className="sr-only">{textos.artigo.aCarregar}</span>
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
        {/* O saldo **com o âmbito escrito ao lado** (ADR 0034, adenda de 29,
            decisão 16). O detalhe é sempre do estabelecimento inteiro, também
            para quem veio da lista com uma loja filtrada: sem a palavra, "2 kg"
            na lista e "12 kg" aqui lê-se como erro de cálculo. Fica na mesma
            linha de base do número, porque é a mesma frase. */}
        <p className="flex items-baseline gap-2">
          <span
            data-numeric
            className={`text-3xl font-semibold ${negativo ? "text-danger" : ""}`}
          >
            {textoDeQuantidade(nivel.quantity)}
          </span>
          <span className="text-xs text-muted-foreground">
            {textos.artigo.emTodoOEstabelecimento}
          </span>
        </p>
        <EstadoDoNivel estado={nivel.status} />
      </div>

      {/* O limiar de "baixo" fica **dentro** do ecrã e não num painel de
          configurações, para o dono o contestar em voz alta (guião §4, nº 7). A
          unidade de registo também está à vista: é a pergunta do leite ao ml. */}
      <p className="text-xs text-muted-foreground">
        {textos.artigo.minimoERegisto(
          textoDeQuantidade(nivel.min_quantity),
          nivel.quantity.base_unit,
        )}
      </p>

      <div className="text-sm">
        <TextoDeValidade validade={nivel.nearest_expiry} limiarEmDias={limiarEmDias} />
      </div>

      {nivel.by_location.length === 0 ? null : (
        <p className="text-sm text-muted-foreground">
          {nivel.by_location.map((parcela, indice) => (
            <span key={parcela.location.id}>
              {indice === 0 ? "" : ", "}
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
          <AlertTitle>{textos.artigo.negativoTitulo}</AlertTitle>
          <AlertDescription>{textos.artigo.negativoCorpo}</AlertDescription>
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

  // **Três estados e não dois** (ADR 0034, adenda de 29, decisão 13). Até aqui
  // o ecrã tinha um ramo só — o `find()` na lista não encontrou — e escrevia
  // "este artigo não está no stock" tanto sobre mercadoria que existe e nunca
  // entrou como sobre um endereço de outro estabelecimento. São factos
  // diferentes e têm saídas diferentes: um é o **vazio** deste ecrã, o outro é
  // um **erro**.
  const naoExiste = eNaoEncontrado(nivel.error);

  return (
    // Sem `max-w` na secção, **e com um cap no que é leitura**: o histórico é uma
    // tabela de sete colunas e usa a largura toda (DESIGN.md §4), mas o cabeçalho
    // do artigo e o formulário de desperdício são leitura e formulário, e o §4
    // dá-lhes 72rem. Uma linha de "mínimo 4,000 kg, registado ao g" esticada a
    // 1280px é pior do que a mesma linha a 1152.
    <section className="flex w-full flex-col gap-4 py-3">
      <Voltar />

      {nivel.isPending ? <Esqueleto /> : null}

      {/* **O 404 antes do erro genérico**, e a ordem é a correcção: o `detail`
          que o DRF manda num 404 é "Não encontrado.", e é essa a frase que o
          `mensagemDeErro` imprimia a quem está numa cozinha. Sem botão de
          repetir — o endereço não melhora à segunda —, mas com saída: a lista. */}
      {naoExiste ? (
        <div className="px-4">
          <Alert className="border-danger-border bg-danger-surface">
            <CircleAlert aria-hidden="true" className="text-danger" />
            <AlertTitle>{textos.artigo.naoExisteTitulo}</AlertTitle>
            <AlertDescription className="flex flex-col items-start gap-2">
              <span>{textos.artigo.naoExisteCorpo}</span>
              <Button asChild variant="outline">
                <Link to="/stock" search={() => ({})}>
                  {textos.accoes.verOStock}
                </Link>
              </Button>
            </AlertDescription>
          </Alert>
        </div>
      ) : nivel.isError ? (
        <div className="px-4">
          <Alert className="border-danger-border bg-danger-surface">
            <CircleAlert aria-hidden="true" className="text-danger" />
            <AlertTitle>{textos.artigo.erroAoCarregar}</AlertTitle>
            <AlertDescription className="flex flex-col items-start gap-2">
              <span>{mensagemDeErro(nivel.error)}</span>
              <Button
                variant="outline"
                onClick={() => {
                  void nivel.refetch();
                }}
              >
                <RotateCcw aria-hidden="true" />
                {textos.artigo.tentarOutraVez}
              </Button>
            </AlertDescription>
          </Alert>
        </div>
      ) : null}

      {/* O artigo existe e **nunca deu entrada**: é o vazio deste ecrã, não um
          erro. Pára aqui de propósito — nem cabeçalho, nem formulário de
          quebra, nem histórico. Não se dá baixa do que nunca deu entrada: um
          `waste` aqui escrevia uma saída sem entrada num ledger append-only.
          E não se escreve "esgotado", apesar de o `status` vir com essa
          palavra: é uma afirmação sobre consumo — tínhamos e acabou — e sobre
          o que nunca entrou é falsa no sentido que importa (decisão 13). */}
      {nivel.data?.never_stocked === true ? (
        <EstadoVazio
          icone={PackageSearch}
          titulo={textos.artigo.nuncaEntrouTitulo(nivel.data.short_name)}
          descricao={textos.artigo.nuncaEntrouCorpo}
        >
          <Button asChild variant="outline">
            <Link to="/stock" search={() => ({})}>
              {textos.accoes.verOStock}
            </Link>
          </Button>
        </EstadoVazio>
      ) : null}

      {/* Sem artigo não há histórico para mostrar: medido numa renderização, um
          "artigo não encontrado" com um esqueleto de movimentos por baixo é um
          ecrã a contradizer-se. O mesmo vale para o artigo que nunca entrou —
          um histórico vazio por baixo de "ainda não deu entrada" é o ecrã a
          responder duas vezes à mesma pergunta. */}
      {nivel.data === undefined || nivel.data.never_stocked ? null : (
        <>
          <div className="flex w-full max-w-6xl flex-col gap-4">
            <Cabecalho nivel={nivel.data} limiarEmDias={limiarEmDias} />
            <FormularioDeDesperdicio nivel={nivel.data} />
          </div>
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
