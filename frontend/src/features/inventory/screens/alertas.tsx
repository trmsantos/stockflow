import { Link, useSearch } from "@tanstack/react-router";
import { CircleCheck, Trash2 } from "lucide-react";
import { useState } from "react";

import { EstadoVazio } from "@/components/estado-vazio";
import { Button } from "@/components/ui/button";
import { mensagemDeErro } from "@/lib/api/errors";
import { formatMoneyRounded } from "@/lib/format";

import {
  useAlertas,
  useDesperdicio,
  useRegistarDesperdicio,
  useResumoDeAlertas,
} from "../api";
import { ErroDaLista } from "../components/estados-da-lista";
import {
  ErroDosNumerosDeAlertas,
  EsqueletoDosNumerosDeAlertas,
  NumerosDosAlertas,
} from "../components/numeros-dos-alertas";
import {
  EsqueletoDaTabelaDeAlertas,
  TabelaDeAlertas,
} from "../components/tabela-de-alertas";
import {
  EsqueletoDaTabelaDeDesperdicio,
  TabelaDeDesperdicio,
} from "../components/tabela-de-desperdicio";
import type { Alerta, MotivoQuebra } from "../schemas";
import { textos } from "../textos";
import { rotuloDeMotivo, textoDeQuantidade } from "../vocabulario";

/**
 * O ecrã Alertas — "o que expira? o que falta? quanto deitei fora?".
 *
 * Três perguntas numa tab são o maior risco do DESIGN.md, e resolvem-se como o
 * guião manda: **três contadores no topo e uma só lista**. Cada contador é um
 * filtro da mesma lista, no URL; sem filtro, a lista mostra o risco todo —
 * validades e faltas juntas, o pior primeiro, ordenado pelo servidor.
 *
 * O que faz este ecrã merecer confiança são três detalhes, e nenhum é visual:
 *
 *  - **`use_by` e `best_before` não se dizem com as mesmas palavras**, e o
 *    `best_before` nunca chega a vermelho. É o vocabulário que o ecrã de Stock
 *    estabeleceu, reutilizado tal e qual: a amêndoa laminada com a durabilidade
 *    a acabar não é para deitar fora, e uma única linha errada dessas custa a
 *    confiança na lista inteira;
 *  - **o limiar está dentro do alerta** ("expira em 2 dias — aviso a 3 dias"),
 *    porque um painel de configurações é o que nos faria perder qual devia ser
 *    o valor por omissão (guião §4, nº 7);
 *  - **o rótulo do desperdício diz a hora a que o dia de negócio começa** — a
 *    sonda da Q6. Se ele olhar para "05:10 — Pastéis de ontem" e disser "isso é
 *    de ontem", a pergunta está respondida sem ter sido feita.
 *
 * A ação principal é "Deitei fora", e o segundo toque escolhe o motivo. É ela que
 * alimenta o número que o dono mais quer ver.
 *
 * **Era um toque na linha inteira e passou a uma coluna de acção** quando as duas
 * listas deste ecrã viraram tabelas densas (2026-10-06). Não foi preferência: um
 * `<tr>` não se envolve num `<button>`, e a forma certa apareceu por consequência
 * — o nome é um link para o artigo, como no Stock, e o botão existe só nas linhas
 * em que faz efeito. Antes, uma linha de validade era um `<button>` e uma de
 * falta era um `<Link>`, com o mesmo aspecto e comportamentos diferentes.
 */

/** O que se diz depois de registar, para quem não está a olhar para o ecrã. */
function frasePorRegisto(alerta: Alerta, motivo: MotivoQuebra): string {
  return textos.alertas.registado(
    textoDeQuantidade(alerta.quantity),
    alerta.short_name,
    rotuloDeMotivo(motivo),
  );
}

export function EcraDeAlertas() {
  const busca = useSearch({ from: "/app/alertas" });
  const vista = busca.ver;
  const periodo = busca.periodo ?? "hoje";

  const aVerDesperdicio = vista === "desperdicio";

  const resumo = useResumoDeAlertas();
  const alertas = useAlertas(vista === "expira" || vista === "falta" ? vista : undefined);
  // O desperdício só se pede quando é ele que está à vista: é a única das três
  // perguntas que tem lista própria, e carregá-la sempre era um pedido por
  // visita que ninguém ia ver. O número do contador vem no resumo, não daqui.
  const desperdicio = useDesperdicio(periodo, aVerDesperdicio);

  // Uma linha aberta de cada vez: num 360px dois painéis de motivos abertos
  // empurram a lista para fora do ecrã, e o segundo toque passa a ser um toque
  // às cegas.
  const [aberta, setAberta] = useState<string | null>(null);
  const registar = useRegistarDesperdicio();
  const [ultimo, setUltimo] = useState<string | null>(null);

  const linhas = alertas.data?.results;
  const linhasDeDesperdicio = desperdicio.data?.results;

  return (
    // Sem `max-w`: as duas tabelas usam a largura toda da área de conteúdo
    // (DESIGN.md §4), como o ecrã de Stock.
    <section className="flex w-full flex-col">
      <h1 className="sr-only">{textos.alertas.titulo}</h1>

      {resumo.isPending ? <EsqueletoDosNumerosDeAlertas /> : null}
      {resumo.isError ? (
        <ErroDosNumerosDeAlertas
          aoTentarOutraVez={() => {
            void resumo.refetch();
          }}
        />
      ) : null}
      {resumo.data === undefined ? null : (
        <NumerosDosAlertas resumo={resumo.data} vistaAtiva={vista} />
      )}

      {/* O resultado da ação principal, anunciado uma vez: a linha desaparece da
          lista quando o lote deixa de estar em risco, e sem isto quem ouve o
          ecrã só notava que havia uma linha a menos. */}
      <p role="status" className="px-celula-x py-2 text-sm">
        {ultimo === null ? null : (
          <span className="flex items-start gap-1.5">
            <CircleCheck aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-success" />
            <span>{ultimo}</span>
          </span>
        )}
      </p>

      {aVerDesperdicio ? (
        <>
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 border-b border-border px-celula-x py-2">
            {/* O rótulo da Q6, por extenso, onde há largura para ele: é este
                cabeçalho e a hora de cada linha que fazem o dono dizer "isso é
                de ontem" — e aí a pergunta está respondida. */}
            <h2 className="text-sm font-semibold">
              {periodo === "hoje"
                ? textos.alertas.deitadoForaHoje(resumo.data?.business_day_starts_at ?? "04:00")
                : textos.alertas.deitadoForaSemana}
            </h2>
            {/* As duas fronteiras do dia de negócio, as duas no URL: qual delas
                ele escolhe primeiro é, também, resposta à Q6. */}
            <Link
              to="/alertas"
              search={(anteriores) => ({
                ...anteriores,
                periodo: periodo === "hoje" ? "semana" : "hoje",
              })}
              className="text-xs text-primary underline underline-offset-4 hover:no-underline"
            >
              {periodo === "hoje" ? textos.alertas.verSemana : textos.alertas.verHoje}
            </Link>
          </div>

          {desperdicio.isPending ? <EsqueletoDaTabelaDeDesperdicio /> : null}

          {desperdicio.isError ? (
            <ErroDaLista
              titulo={textos.alertas.erroDoDesperdicio}
              mensagem={mensagemDeErro(desperdicio.error)}
              aoTentarOutraVez={() => {
                void desperdicio.refetch();
              }}
            />
          ) : null}

          {linhasDeDesperdicio === undefined ? null : linhasDeDesperdicio.length === 0 ? (
            <EstadoVazio
              icone={Trash2}
              titulo={textos.alertas.vazioDesperdicioTitulo}
              descricao={
                periodo === "hoje"
                  ? textos.alertas.vazioDesperdicioHoje
                  : textos.alertas.vazioDesperdicioSemana
              }
            >
              <Button asChild variant="outline">
                <Link to="/alertas" search={() => ({})}>
                  {textos.alertas.verEmRisco}
                </Link>
              </Button>
            </EstadoVazio>
          ) : (
            <TabelaDeDesperdicio linhas={linhasDeDesperdicio} />
          )}
        </>
      ) : (
        <>
          {alertas.isPending ? <EsqueletoDaTabelaDeAlertas /> : null}

          {alertas.isError ? (
            <ErroDaLista
              titulo={textos.alertas.erroAoCarregar}
              mensagem={mensagemDeErro(alertas.error)}
              aoTentarOutraVez={() => {
                void alertas.refetch();
              }}
            />
          ) : null}

          {linhas === undefined ? null : linhas.length === 0 ? (
            <EstadoVazio
              icone={CircleCheck}
              titulo={
                vista === undefined
                  ? textos.alertas.vazioTitulo
                  : textos.alertas.vazioComFiltroTitulo
              }
              descricao={
                vista === undefined ? textos.alertas.vazioCorpo : textos.alertas.vazioComFiltroCorpo
              }
            >
              {vista === undefined ? (
                <Button asChild variant="outline">
                  <Link to="/stock" search={() => ({})}>
                    {textos.accoes.verOStock}
                  </Link>
                </Button>
              ) : (
                <Button asChild variant="outline">
                  <Link to="/alertas" search={() => ({})}>
                    {textos.alertas.verTudo}
                  </Link>
                </Button>
              )}
            </EstadoVazio>
          ) : (
            <>
              <TabelaDeAlertas
                alertas={linhas}
                abertaEm={aberta}
                aoAlternar={(id) => {
                  setAberta((atual) => (atual === id ? null : id));
                  registar.reset();
                }}
                produtoARegistar={registar.isPending ? registar.variables.product : null}
                erro={registar.isError ? mensagemDeErro(registar.error) : null}
                aoDeitarFora={(alerta, motivo) => {
                  registar.mutate(
                    {
                      product: alerta.product,
                      // Um alerta de validade tem sempre localização e lote: é
                      // **sobre** aquele lote, e deitar fora outro seria deitar
                      // fora o lote errado. A guarda existe porque o contrato os
                      // deixa nulos (uma falta não tem nenhum dos dois), e essa
                      // linha não tem esta ação.
                      location: alerta.location?.id ?? "",
                      quantity: alerta.quantity.base,
                      reason: motivo,
                      ...(alerta.lot === null ? {} : { lot_code: alerta.lot.lot_code }),
                    },
                    {
                      onSuccess: () => {
                        setUltimo(frasePorRegisto(alerta, motivo));
                        setAberta(null);
                      },
                    },
                  );
                }}
              />

              <p className="px-celula-x py-3 text-xs text-muted-foreground">
                {textos.alertas.rodape(linhas.length)}
              </p>
            </>
          )}
        </>
      )}

      {/* O desperdício de hoje tem sempre uma porta, mesmo quando se está a ver
          o risco: é a terceira pergunta, e o contador do topo é a primeira. */}
      {aVerDesperdicio || resumo.data === undefined ? null : (
        <p className="px-celula-x pb-3 text-xs text-muted-foreground">
          {textos.alertas.deitadoForaNaSemana}{" "}
          <span data-numeric>{formatMoneyRounded(resumo.data.wasted_week_eur)}</span>.{" "}
          <Link
            to="/alertas"
            search={(anteriores) => ({ ...anteriores, ver: "desperdicio" })}
            className="text-primary underline underline-offset-4 hover:no-underline"
          >
            {textos.alertas.verOQueFoi}
          </Link>
        </p>
      )}
    </section>
  );
}
