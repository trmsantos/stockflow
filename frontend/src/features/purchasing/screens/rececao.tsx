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
import { textos } from "../textos";
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
          {textos.comuns.receber}
        </Link>
      </Button>

      {documento.isPending ? <EsqueletoDoCabecalho /> : null}

      {documento.isError ? (
        <ErroAoCarregar
          titulo={textos.rececao.erroAoCarregar}
          mensagem={mensagemDeErro(documento.error)}
          aoTentarOutraVez={() => {
            void documento.refetch();
          }}
        />
      ) : null}

      {dados === null ? (
        <EstadoVazio
          icone={FileQuestion}
          titulo={textos.rececao.naoExisteTitulo}
          descricao={textos.rececao.naoExisteCorpo}
        >
          <Button asChild variant="outline">
            <Link to="/receber" search={() => ({})}>
              {textos.comuns.verAsRececoes}
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
              <>
                {dados.locations.some((l) => l.name === "Refrigerado") && (
                  <TemperaturaAEntrega
                    rececao={dados}
                    conservation="chilled"
                    aGuardar={temperatura.isPending}
                    erroDoServidor={temperatura.isError ? mensagemDeErro(temperatura.error) : null}
                    aoGuardar={(conservation, celsius) => {
                      temperatura.mutate({ rececao: dados.id, conservation, celsius });
                    }}
                  />
                )}
                {dados.locations.some((l) => l.name === "Congelado") && (
                  <TemperaturaAEntrega
                    rececao={dados}
                    conservation="frozen"
                    aGuardar={temperatura.isPending}
                    erroDoServidor={temperatura.isError ? mensagemDeErro(temperatura.error) : null}
                    aoGuardar={(conservation, celsius) => {
                      temperatura.mutate({ rececao: dados.id, conservation, celsius });
                    }}
                  />
                )}
              </>
            ) : null}

            {dados.status === "confirmed" ? (
              <div className="px-celula-x">
                <Alert className="border-success-border bg-success-surface">
                  <CircleCheck aria-hidden="true" className="text-success" />
                  <AlertTitle>{textos.rececao.noStockTitulo}</AlertTitle>
                  <AlertDescription className="flex flex-col items-start gap-2 text-pretty">
                    <span>{textos.rececao.noStockCorpo}</span>
                    <Button asChild variant="outline">
                      <Link to="/stock" search={() => ({})}>
                        {textos.rececao.verNoStock}
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
            {textos.rececao.linhasDoDocumento}
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
              titulo={textos.rececao.erroDasLinhas}
              mensagem={mensagemDeErro(linhas.error)}
              aoTentarOutraVez={() => {
                void linhas.refetch();
              }}
            />
          ) : null}

          {resultados === undefined ? null : resultados.length === 0 ? (
            <EstadoVazio
              icone={FileQuestion}
              titulo={textos.rececao.semLinhasTitulo}
              descricao={textos.rececao.semLinhasCorpo}
            >
              <Button asChild variant="outline">
                <Link to="/receber" search={() => ({})}>
                  {textos.comuns.verAsRececoes}
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
                        setUltimo(textos.rececao.linhaRevista(nomeDaLinha(linha)));
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
                        setUltimo(textos.rececao.linhaDeFora(nomeDaLinha(linha)));
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
                        setUltimo(textos.rececao.linhaVoltaARever(nomeDaLinha(linha)));
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
                        ? textos.rececao.nadaEntraAinda
                        : textos.rececao.oQueEntra}
                    </h2>
                    {entram.length === 0 ? (
                      <p className="text-pretty text-sm text-muted-foreground">
                        {textos.rececao.nenhumaRevista}
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
                            {textos.rececao.entraNoStock(linha.product_name, linha.location.name)}
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
                      <AlertTitle>{textos.rececao.linhasDeFora(foram.length)}</AlertTitle>
                      <AlertDescription className="text-pretty">
                        {textos.rececao.linhasDeForaCorpo}
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
                    {confirmar.isPending
                      ? textos.rececao.aDarEntrada
                      : textos.rececao.confirmarEDarEntrada}
                  </Button>

                  <p className="text-pretty text-xs text-muted-foreground">
                    {textos.rececao.esteToqueCria}
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
                {confirmar.isSuccess ? textos.rececao.confirmada : null}
              </p>
            </>
          )}
        </>
      )}
    </section>
  );
}
