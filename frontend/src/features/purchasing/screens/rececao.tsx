import { Link, useParams, useSearch } from "@tanstack/react-router";
import { ArrowLeft, CircleAlert, CircleCheck, FileQuestion, TriangleAlert } from "lucide-react";

import { ErroAoCarregar } from "@/components/erro-ao-carregar";
import { EstadoVazio } from "@/components/estado-vazio";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { mensagemDeErro } from "@/lib/api/errors";

import {
  useConfirmarRececao,
  useLinhasDaRececao,
  useRececao,
  useRegistarTemperatura,
  useRevisarLinha,
} from "../api";
import {
  AvisoDeTotais,
  CabecalhoDaRececao,
  TotaisDaRececao,
} from "../components/cabecalho-da-rececao";
import { EsqueletoDasLinhas, EsqueletoDoCabecalho } from "../components/esqueletos";
import { LinhaDeFatura } from "../components/linha-de-fatura";
import { TemperaturaAEntrega } from "../components/temperatura-a-entrega";
import type { LinhaDeRececao } from "../schemas";
import { textoNaUnidadeBase } from "../vocabulario";

/**
 * **O ecrã que interessa**: uma receção, linha a linha.
 *
 * É aqui que a regra do CLAUDE.md deixa de ser uma frase e passa a ser o
 * produto: "toda a extração de fatura passa por revisão humana antes de gerar
 * movimentos". Logo este documento é um **rascunho** — lê-se, corrige-se linha a
 * linha, escreve-se o lote e a validade que estão na embalagem (que nenhum
 * documento traz), e **só o último toque** cria stock. Antes dele, o nível do
 * artigo no ecrã de Stock é o mesmo; depois dele, mudou. É o que separa este
 * produto de um que inventa stock a partir de um OCR.
 *
 * Duas coisas que o ecrã **não** faz, e as duas são decisões:
 *
 *  - **não bloqueia.** Totais que não batem, uma entrega parcial, um preço 21 %
 *    acima do histórico, linhas por rever — tudo avisa, nada impede. Bloquear é
 *    a Q1 da sessão 0, e quem bloqueia aqui responde pelo dono (guião §4,
 *    proibição 3). O que o ecrã garante é que ninguém confirma sem ver;
 *  - **não fala de extração.** Não há percentagens de confiança nem "lido
 *    automaticamente": uma linha ou precisa de revisão ou está revista, e quem a
 *    reviu assina com nome e hora.
 */

/** O que vai entrar no stock quando se confirmar. Só o que já foi revisto. */
function entramNoStock(linhas: readonly LinhaDeRececao[]): LinhaDeRececao[] {
  return linhas.filter(
    (linha) =>
      linha.kind === "goods" &&
      linha.status === "confirmed" &&
      linha.product !== null &&
      linha.stock_quantity !== null,
  );
}

/** O que fica de fora, e porquê. Dito antes do toque, não depois. */
function ficamDeFora(linhas: readonly LinhaDeRececao[]): LinhaDeRececao[] {
  return linhas.filter(
    (linha) =>
      linha.kind === "goods" && (linha.status !== "confirmed" || linha.product === null),
  );
}

export function EcraDeRececao() {
  const { rececao: id } = useParams({ from: "/app/receber/$rececao" });
  const busca = useSearch({ from: "/app/receber/$rececao" });

  const documento = useRececao(id);
  const linhas = useLinhasDaRececao(id);

  const revisar = useRevisarLinha();
  const temperatura = useRegistarTemperatura();
  const confirmar = useConfirmarRececao();

  const dados = documento.data;
  const resultados = linhas.data?.results;
  const porRever = dados?.status === "needs_review";

  const entram = entramNoStock(resultados ?? []);
  const foram = ficamDeFora(resultados ?? []);

  return (
    <section className="flex w-full max-w-2xl flex-col gap-3 py-3">
      <Button asChild variant="ghost" className="self-start">
        {/* `search={busca}` devolve a lista no mesmo filtro em que estava. */}
        <Link to="/receber" search={busca}>
          <ArrowLeft aria-hidden="true" />
          Receber
        </Link>
      </Button>

      {documento.isPending ? <EsqueletoDoCabecalho /> : null}

      {documento.isError ? (
        <ErroAoCarregar
          titulo="Não foi possível carregar esta receção"
          mensagem={mensagemDeErro(documento.error)}
          aoTentarOutraVez={() => {
            void documento.refetch();
          }}
        />
      ) : null}

      {dados === null ? (
        <EstadoVazio
          icone={FileQuestion}
          titulo="Esta receção não existe"
          descricao="O endereço aponta para um documento que já não está neste estabelecimento."
        >
          <Button asChild variant="outline">
            <Link to="/receber" search={() => ({})}>
              Ver as receções
            </Link>
          </Button>
        </EstadoVazio>
      ) : dados === undefined ? null : (
        <>
          <CabecalhoDaRececao rececao={dados} />
          <AvisoDeTotais rececao={dados} />

          {dados.cold_chain ? (
            <TemperaturaAEntrega
              rececao={dados}
              aGuardar={temperatura.isPending}
              erroDoServidor={temperatura.isError ? mensagemDeErro(temperatura.error) : null}
              aoGuardar={(celsius) => {
                temperatura.mutate({ rececao: dados.id, celsius });
              }}
            />
          ) : null}

          {dados.status === "confirmed" ? (
            <div className="px-4">
              <Alert className="border-success-border bg-success-surface">
                <CircleCheck aria-hidden="true" className="text-success" />
                <AlertTitle>A mercadoria está no stock</AlertTitle>
                <AlertDescription className="flex flex-col items-start gap-2 text-pretty">
                  <span>
                    Cada linha confirmada gerou um movimento de entrada com o lote, a validade e o
                    autor. Nada se reescreve: para corrigir, registra-se um movimento novo.
                  </span>
                  <Button asChild variant="outline">
                    <Link to="/stock" search={() => ({})}>
                      Ver no stock
                    </Link>
                  </Button>
                </AlertDescription>
              </Alert>
            </div>
          ) : null}

          <h2 className="bg-surface-2 px-4 py-1 text-xs font-medium text-muted-foreground">
            Linhas do documento
          </h2>

          {linhas.isPending ? <EsqueletoDasLinhas /> : null}

          {linhas.isError ? (
            <ErroAoCarregar
              titulo="Não foi possível carregar as linhas"
              mensagem={mensagemDeErro(linhas.error)}
              aoTentarOutraVez={() => {
                void linhas.refetch();
              }}
            />
          ) : null}

          {resultados === undefined ? null : resultados.length === 0 ? (
            <EstadoVazio
              icone={FileQuestion}
              titulo="Este documento não tem linhas"
              descricao="Sem linhas não há nada para rever nem nada para dar entrada. Costuma ser um documento fotografado ao contrário."
            >
              <Button asChild variant="outline">
                <Link to="/receber" search={() => ({})}>
                  Ver as receções
                </Link>
              </Button>
            </EstadoVazio>
          ) : (
            <>
              <ul className="flex flex-col">
                {resultados.map((linha) => (
                  <LinhaDeFatura
                    key={linha.id}
                    linha={linha}
                    aRevisar={revisar.isPending && revisar.variables.linha === linha.id}
                    erro={
                      revisar.isError && revisar.variables.linha === linha.id
                        ? mensagemDeErro(revisar.error)
                        : null
                    }
                    aoConfirmar={(lote, validade) => {
                      revisar.mutate({
                        rececao: dados.id,
                        linha: linha.id,
                        ...(lote === undefined ? {} : { lot_code: lote }),
                        ...(validade === undefined ? {} : { expires_at: validade }),
                      });
                    }}
                    aoDeixarFora={() => {
                      revisar.mutate({ rececao: dados.id, linha: linha.id, skip: true });
                    }}
                    aoVoltarARever={() => {
                      revisar.mutate({ rececao: dados.id, linha: linha.id, skip: false });
                    }}
                  />
                ))}
              </ul>

              <TotaisDaRececao rececao={dados} />

              {porRever ? (
                <div className="flex flex-col items-start gap-3 border-t border-border px-4 py-4">
                  <div className="flex flex-col gap-1">
                    <h2 className="text-sm font-semibold">
                      {entram.length === 0
                        ? "Nada entra no stock ainda"
                        : "O que entra no stock quando confirmar"}
                    </h2>
                    {entram.length === 0 ? (
                      <p className="text-pretty text-sm text-muted-foreground">
                        Nenhuma linha está revista. Confirme as linhas acima — o lote e a validade
                        estão na embalagem, não no documento.
                      </p>
                    ) : (
                      <ul className="flex flex-col text-sm">
                        {entram.map((linha) => (
                          <li key={linha.id} className="flex items-baseline gap-2">
                            <CircleCheck
                              aria-hidden="true"
                              className="mt-1 size-3.5 shrink-0 text-success"
                            />
                            <span className="min-w-0">
                              <span data-numeric>
                                {linha.stock_quantity === null
                                  ? ""
                                  : textoNaUnidadeBase(linha.stock_quantity)}
                              </span>{" "}
                              de {linha.product_name} em {linha.location.name}
                            </span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>

                  {foram.length === 0 ? null : (
                    // Aviso **suave**: confirmar com linhas de fora é legítimo —
                    // um artigo que o catálogo não tem não pode entrar — e o que
                    // o ecrã faz é dizer o que vai acontecer, não impedir.
                    <Alert className="border-warning-border bg-warning-surface">
                      <TriangleAlert aria-hidden="true" className="text-warning" />
                      <AlertTitle>
                        {foram.length === 1
                          ? "1 linha fica de fora"
                          : `${String(foram.length)} linhas ficam de fora`}
                      </AlertTitle>
                      <AlertDescription className="text-pretty">
                        Sem revisão não há movimento, logo essa mercadoria não aparece no stock.
                        Pode confirmar assim e tratar dela depois — ou rever as linhas primeiro.
                      </AlertDescription>
                    </Alert>
                  )}

                  <Button
                    disabled={confirmar.isPending}
                    onClick={() => {
                      confirmar.mutate(dados.id);
                    }}
                  >
                    <CircleCheck aria-hidden="true" />
                    {confirmar.isPending ? "A dar entrada…" : "Confirmar e dar entrada"}
                  </Button>

                  <p className="text-pretty text-xs text-muted-foreground">
                    É este toque que cria os movimentos de entrada. Até aqui, o stock deste
                    estabelecimento é o mesmo que era antes de a mercadoria chegar.
                  </p>

                  {confirmar.isError ? (
                    <p role="alert" className="flex items-start gap-1.5 text-sm text-danger">
                      <CircleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
                      <span>{mensagemDeErro(confirmar.error)}</span>
                    </p>
                  ) : null}
                </div>
              ) : null}

              {/* O resultado anunciado uma vez, para quem não está a olhar para
                  o ecrã: a lista de linhas muda de estado em silêncio. */}
              <p role="status" className="px-4 text-sm">
                {confirmar.isSuccess ? "Receção confirmada: a mercadoria entrou no stock." : null}
              </p>
            </>
          )}
        </>
      )}
    </section>
  );
}
