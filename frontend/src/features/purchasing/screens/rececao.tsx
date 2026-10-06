import { Link, useParams, useSearch } from "@tanstack/react-router";
import { ArrowLeft, CircleAlert, CircleCheck, FileQuestion, TriangleAlert } from "lucide-react";
import { useState } from "react";

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
import { EsqueletoDoCabecalho } from "../components/esqueletos";
import {
  EsqueletoDaTabelaDeLinhas,
  TabelaDeLinhasDeFatura,
} from "../components/tabela-de-linhas-de-fatura";
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
 *
 * ## Duas larguras no mesmo ecrã, desde 2026-10-06
 *
 * As linhas eram uma `<ul>` de cartões de até sete filas de texto dentro de um
 * `max-w-2xl`; passaram a **tabela densa à largura toda**, como o Stock e os
 * Alertas. O resto do ecrã **não** foi atrás: o cabeçalho do documento, os
 * avisos, o rodapé de IVA e o bloco de confirmação são leitura e formulário, e o
 * DESIGN.md §4 dá-lhes 72rem — uma frase a 1400px de largura não se lê, e um
 * rodapé de totais com a etiqueta à esquerda e o número a 1300px de distância não
 * é um rodapé, é dois textos. Tabelas usam a largura toda; prosa não.
 *
 * O rodapé de totais fica **alinhado à direita**, debaixo das colunas de
 * dinheiro da tabela: é onde ele está no papel e é onde a vista já está.
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

/** Como uma linha se chama em voz alta: o artigo, ou o que a fatura escreveu. */
function nomeDaLinha(linha: LinhaDeRececao): string {
  return linha.product_name ?? linha.description;
}

export function EcraDeRececao() {
  const { rececao: id } = useParams({ from: "/app/receber/$rececao" });
  const busca = useSearch({ from: "/app/receber/$rececao" });

  const documento = useRececao(id);
  const linhas = useLinhasDaRececao(id);

  const revisar = useRevisarLinha();
  const temperatura = useRegistarTemperatura();
  const confirmar = useConfirmarRececao();

  // Um painel de linha aberto de cada vez: dois formulários de lote abertos
  // empurram a tabela para fora do ecrã, e o segundo toque passa a ser um toque
  // às cegas. É a mesma regra do painel de motivos do ecrã Alertas.
  const [aberta, setAberta] = useState<string | null>(null);
  // O resultado de uma revisão, para quem não está a olhar para o ecrã: o painel
  // fecha-se e a linha muda de estado em silêncio.
  const [ultimo, setUltimo] = useState<string | null>(null);

  const dados = documento.data;
  const resultados = linhas.data?.results;
  const porRever = dados?.status === "needs_review";

  const entram = entramNoStock(resultados ?? []);
  const foram = ficamDeFora(resultados ?? []);

  return (
    // Sem `max-w` na secção: a tabela das linhas usa a largura toda da área de
    // conteúdo (DESIGN.md §4). O cap de leitura está nos blocos de prosa, não
    // aqui.
    <section className="flex w-full flex-col gap-3 py-3">
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
          {/* Leitura e formulário: 72rem (DESIGN.md §4). */}
          <div className="flex w-full max-w-6xl flex-col gap-3">
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
              <div className="px-celula-x">
                <Alert className="border-success-border bg-success-surface">
                  <CircleCheck aria-hidden="true" className="text-success" />
                  <AlertTitle>A mercadoria está no stock</AlertTitle>
                  <AlertDescription className="flex flex-col items-start gap-2 text-pretty">
                    <span>
                      Cada linha confirmada gerou um movimento de entrada com o lote, a validade e
                      o autor. Nada se reescreve: para corrigir, registra-se um movimento novo.
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
          </div>

          {/* A faixa que abre a região da tabela: sem tinta própria e com uma
              régua abaixo. Era `bg-surface-2`, que é o degrau do **cabeçalho de
              coluna** da tabela — duas faixas da mesma tinta encostadas uma à
              outra lêem-se como um bloco só, e o cabeçalho deixava de se ver
              como cabeçalho. É a mesma razão do "cromado contado" do §2. */}
          <h2 className="border-b border-border px-celula-x py-2 text-sm font-semibold">
            Linhas do documento
          </h2>

          {/* O resultado de cada revisão, anunciado uma vez: o painel fecha-se
              quando o pedido passa, e sem isto quem ouve o ecrã só notava que
              havia um painel a menos. */}
          <p role="status" className="px-celula-x py-2 text-sm">
            {ultimo}
          </p>

          {linhas.isPending ? <EsqueletoDaTabelaDeLinhas /> : null}

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
              <TabelaDeLinhasDeFatura
                linhas={resultados}
                abertaEm={aberta}
                aoAlternar={(linhaId) => {
                  setAberta((atual) => (atual === linhaId ? null : linhaId));
                  // Um erro de um pedido anterior não pertence ao painel que se
                  // acaba de abrir.
                  revisar.reset();
                }}
                linhaARevisar={revisar.isPending ? revisar.variables.linha : null}
                erro={revisar.isError ? mensagemDeErro(revisar.error) : null}
                aoConfirmar={(linha, lote, validade) => {
                  revisar.mutate(
                    {
                      rececao: dados.id,
                      linha: linha.id,
                      ...(lote === undefined ? {} : { lot_code: lote }),
                      ...(validade === undefined ? {} : { expires_at: validade }),
                    },
                    // Escrito, o painel fecha-se: o que havia para fazer naquela
                    // linha está feito, e o estado dela passa a ler-se na coluna.
                    {
                      onSuccess: () => {
                        setAberta(null);
                        setUltimo(`Linha revista: ${nomeDaLinha(linha)}.`);
                      },
                    },
                  );
                }}
                aoDeixarFora={(linha) => {
                  revisar.mutate(
                    { rececao: dados.id, linha: linha.id, skip: true },
                    {
                      onSuccess: () => {
                        setAberta(null);
                        setUltimo(
                          `${nomeDaLinha(linha)} fica fora desta entrada — não gera movimento.`,
                        );
                      },
                    },
                  );
                }}
                aoVoltarARever={(linha) => {
                  revisar.mutate(
                    { rececao: dados.id, linha: linha.id, skip: false },
                    {
                      onSuccess: () => {
                        setAberta(null);
                        setUltimo(`${nomeDaLinha(linha)} volta a precisar de revisão.`);
                      },
                    },
                  );
                }}
              />

              {/* O rodapé do documento, alinhado à direita e com medida de
                  leitura: é onde ele está no papel, debaixo das colunas de
                  dinheiro. */}
              <div className="flex w-full justify-end">
                <div className="w-full max-w-md">
                  <TotaisDaRececao rececao={dados} />
                </div>
              </div>

              {porRever ? (
                <div className="flex w-full max-w-6xl flex-col items-start gap-3 border-t border-border px-celula-x py-4">
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
                      // Sem um visto verde por item: eram quinze ícones iguais
                      // numa coluna a dizer o que a frase já diz, e é a terceira
                      // linha do §5. A quantidade é que leva mono.
                      <ul className="flex flex-col text-sm">
                        {entram.map((linha) => (
                          <li key={linha.id} className="min-w-0">
                            <span data-numeric>
                              {linha.stock_quantity === null
                                ? ""
                                : textoNaUnidadeBase(linha.stock_quantity)}
                            </span>{" "}
                            de {linha.product_name} em {linha.location.name}
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
                  o ecrã: a tabela muda de estado em silêncio. */}
              <p role="status" className="px-celula-x text-sm">
                {confirmar.isSuccess ? "Receção confirmada: a mercadoria entrou no stock." : null}
              </p>
            </>
          )}
        </>
      )}
    </section>
  );
}
