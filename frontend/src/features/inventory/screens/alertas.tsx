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
import { ErroDaLista, EsqueletoDaLista } from "../components/estados-da-lista";
import { LinhaDeAlerta } from "../components/linha-de-alerta";
import { LinhaDeDesperdicio } from "../components/linha-de-desperdicio";
import {
  ErroDosNumerosDeAlertas,
  EsqueletoDosNumerosDeAlertas,
  NumerosDosAlertas,
} from "../components/numeros-dos-alertas";
import type { Alerta, MotivoQuebra } from "../schemas";
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
 * A ação principal é um toque na linha, "Deitei fora", e o segundo toque escolhe
 * o motivo. É ela que alimenta o número que o dono mais quer ver.
 */

/** O que se diz depois de registar, para quem não está a olhar para o ecrã. */
function frasePorRegisto(alerta: Alerta, motivo: MotivoQuebra): string {
  return `Deitado fora: ${textoDeQuantidade(alerta.quantity)} de ${alerta.short_name} — ${rotuloDeMotivo(motivo)}.`;
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
    <section className="flex w-full max-w-2xl flex-col">
      <h1 className="sr-only">Alertas — o que expira, o que falta, quanto deitei fora</h1>

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
      <p role="status" className="px-4 text-sm">
        {ultimo === null ? null : (
          <span className="flex items-start gap-1.5">
            <CircleCheck aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-success" />
            <span>{ultimo}</span>
          </span>
        )}
      </p>

      {aVerDesperdicio ? (
        <>
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 border-b border-border px-4 py-2">
            {/* O rótulo da Q6, por extenso, onde há largura para ele: é este
                cabeçalho e a hora de cada linha que fazem o dono dizer "isso é
                de ontem" — e aí a pergunta está respondida. */}
            <h2 className="text-sm font-semibold">
              Deitado fora —{" "}
              {periodo === "hoje"
                ? `hoje (desde as ${resumo.data?.business_day_starts_at ?? "04:00"})`
                : "últimos 7 dias"}
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
              {periodo === "hoje" ? "ver os últimos 7 dias" : "ver só hoje"}
            </Link>
          </div>

          {desperdicio.isPending ? (
            <EsqueletoDaLista rotulo="A carregar o desperdício…" linhas={4} />
          ) : null}

          {desperdicio.isError ? (
            <ErroDaLista
              titulo="Não foi possível carregar o desperdício"
              mensagem={mensagemDeErro(desperdicio.error)}
              aoTentarOutraVez={() => {
                void desperdicio.refetch();
              }}
            />
          ) : null}

          {linhasDeDesperdicio === undefined ? null : linhasDeDesperdicio.length === 0 ? (
            <EstadoVazio
              icone={Trash2}
              titulo="Nada deitado fora neste período"
              descricao={
                periodo === "hoje"
                  ? "O dia de negócio começou e ainda não se registou nenhuma quebra. As de antes dessa hora contam no dia anterior."
                  : "Nenhuma quebra registada nos últimos sete dias."
              }
            >
              <Button asChild variant="outline">
                <Link to="/alertas" search={() => ({})}>
                  Ver o que está em risco
                </Link>
              </Button>
            </EstadoVazio>
          ) : (
            <ul className="flex flex-col">
              {linhasDeDesperdicio.map((linha) => (
                <LinhaDeDesperdicio key={linha.id} linha={linha} />
              ))}
            </ul>
          )}
        </>
      ) : (
        <>
          {alertas.isPending ? <EsqueletoDaLista rotulo="A carregar os alertas…" /> : null}

          {alertas.isError ? (
            <ErroDaLista
              titulo="Não foi possível carregar os alertas"
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
                vista === undefined ? "Nada em risco agora" : "Nada em risco com este filtro"
              }
              descricao={
                vista === undefined
                  ? "Nenhum lote dentro do horizonte de validade e nenhum artigo abaixo do mínimo. Os alertas aparecem aqui sozinhos."
                  : "Os outros dois contadores do topo podem ter linhas. Toque para ver tudo."
              }
            >
              {vista === undefined ? (
                <Button asChild variant="outline">
                  <Link to="/stock" search={() => ({})}>
                    Ver o stock
                  </Link>
                </Button>
              ) : (
                <Button asChild variant="outline">
                  <Link to="/alertas" search={() => ({})}>
                    Ver tudo
                  </Link>
                </Button>
              )}
            </EstadoVazio>
          ) : (
            <>
              <ul className="flex flex-col">
                {linhas.map((alerta) => (
                  <LinhaDeAlerta
                    key={alerta.id}
                    alerta={alerta}
                    idDoPainel={`motivos-${alerta.id}`}
                    aberto={aberta === alerta.id}
                    aoAlternar={() => {
                      setAberta((atual) => (atual === alerta.id ? null : alerta.id));
                      registar.reset();
                    }}
                    aRegistar={registar.isPending && registar.variables.product === alerta.product}
                    erro={
                      registar.isError && aberta === alerta.id
                        ? mensagemDeErro(registar.error)
                        : null
                    }
                    aoDeitarFora={(motivo) => {
                      registar.mutate(
                        {
                          product: alerta.product,
                          // Um alerta de validade tem sempre localização e lote:
                          // é **sobre** aquele lote, e deitar fora outro seria
                          // deitar fora o lote errado. A guarda existe porque o
                          // contrato os deixa nulos (uma falta não tem nenhum
                          // dos dois), e essa linha não tem esta ação.
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
                ))}
              </ul>

              <p className="px-4 py-3 text-xs text-muted-foreground">
                {linhas.length === 1 ? "1 alerta" : `${String(linhas.length)} alertas`} · o pior
                primeiro · «consumir até» é limite legal, «perde qualidade» é durabilidade mínima
              </p>
            </>
          )}
        </>
      )}

      {/* O desperdício de hoje tem sempre uma porta, mesmo quando se está a ver
          o risco: é a terceira pergunta, e o contador do topo é a primeira. */}
      {aVerDesperdicio || resumo.data === undefined ? null : (
        <p className="px-4 pb-3 text-xs text-muted-foreground">
          Deitado fora nos últimos 7 dias:{" "}
          <span data-numeric>{formatMoneyRounded(resumo.data.wasted_week_eur)}</span>.{" "}
          <Link
            to="/alertas"
            search={(anteriores) => ({ ...anteriores, ver: "desperdicio" })}
            className="text-primary underline underline-offset-4 hover:no-underline"
          >
            Ver o que foi, e a que horas
          </Link>
        </p>
      )}
    </section>
  );
}
