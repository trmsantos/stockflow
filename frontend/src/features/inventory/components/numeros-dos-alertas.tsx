import { Link } from "@tanstack/react-router";
import { CircleAlert, Funnel, RotateCcw } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { formatMoneyRounded, formatTime } from "@/lib/format";

import type { ResumoDeAlertas } from "../schemas";
import { CLASSE_MOSAICO, CLASSE_NUMERO, CLASSE_ROTULO } from "./numeros-do-topo";

/**
 * Os três contadores do topo dos Alertas — e a razão de este ecrã não ser três
 * ecrãs.
 *
 * "Três perguntas numa tab é o maior risco do DESIGN.md", e resolve-se com
 * **três contadores e uma só lista**: cada contador é um filtro da mesma lista,
 * no URL, logo o dono nunca tem de escolher um separador para ver o que lhe
 * interessa — toca no número e a lista por baixo passa a ser aquela.
 *
 * O terceiro contador é a sonda da Q6. O rótulo diz **a hora a que o dia de
 * negócio começa** — "hoje (desde as 04:00)" — e a hora vem do servidor, não
 * daqui: na pastelaria a fronteira é o início da produção (~4h) e num
 * restaurante é o fim do serviço (~2h), e é essa diferença que se quer ouvir.
 * O número da semana vai na segunda linha do mesmo mosaico, porque é o que o
 * DESIGN.md §1 pede e porque dois números iguais ("hoje" e "semana") seriam
 * lidos como um erro do ecrã.
 *
 * Os euros aparecem **arredondados ao euro**: vêm de custos médios, e o cêntimo
 * convidaria a discutir o cêntimo em vez do desperdício (guião §4, nº 9).
 */
export type VistaDeAlertas = "expira" | "falta" | "desperdicio" | undefined;

function Mosaico({
  valor,
  rotulo,
  extra,
  titulo,
  ativo,
  vista,
}: {
  readonly valor: string;
  readonly rotulo: string;
  readonly extra?: string;
  readonly titulo: string;
  readonly ativo: boolean;
  readonly vista: "expira" | "falta" | "desperdicio";
}) {
  return (
    <Link
      to="/alertas"
      // Tocar segunda vez no mesmo mosaico limpa o filtro, como no ecrã de
      // Stock: o reducer recebe os filtros actuais já validados pela rota.
      search={(anteriores) => ({ ...anteriores, ver: ativo ? undefined : vista })}
      title={titulo}
      className={`${CLASSE_MOSAICO} transition-colors ${
        ativo
          ? "border-primary bg-surface-2"
          : "border-border-strong bg-surface hover:bg-surface-2"
      }`}
    >
      <span data-numeric className={CLASSE_NUMERO}>
        {valor}
      </span>
      <span className={`flex items-center gap-1 ${CLASSE_ROTULO}`}>
        {ativo ? (
          <>
            <Funnel aria-hidden="true" className="size-3 shrink-0 text-primary" />
            <span className="sr-only">A filtrar por </span>
          </>
        ) : null}
        <span className="text-balance">{rotulo}</span>
      </span>
      {extra === undefined ? null : (
        <span className={`${CLASSE_ROTULO} text-pretty`}>{extra}</span>
      )}
    </Link>
  );
}

export function NumerosDosAlertas({
  resumo,
  vistaAtiva,
}: {
  readonly resumo: ResumoDeAlertas;
  readonly vistaAtiva: VistaDeAlertas;
}) {
  const dias = resumo.expiring_within_days;
  const desde = resumo.business_day_starts_at;

  return (
    <div className="grid grid-cols-3 items-stretch gap-2 px-4 pt-3 pb-2">
      <Mosaico
        valor={String(resumo.expiring_count)}
        rotulo={`lotes a expirar ≤\u00a0${String(dias)} dias`}
        titulo={`Lotes com validade dentro de ${String(dias)} dias — o limiar é do servidor e aparece dentro de cada alerta`}
        ativo={vistaAtiva === "expira"}
        vista="expira"
      />
      <Mosaico
        valor={String(resumo.missing_count)}
        rotulo="em falta"
        titulo="Artigos abaixo do mínimo de stock — o mesmo número do ecrã de Stock"
        ativo={vistaAtiva === "falta"}
        vista="falta"
      />
      {/* O rótulo em duas linhas e não numa: a 360px um mosaico tem ~85px de
          texto, e "deitado fora — hoje (desde as 04:00)" numa linha só dava
          quatro linhas de 12px e empurrava a lista para fora do ecrã. A hora
          fica na segunda linha, que é onde ela se lê melhor de qualquer forma —
          é a parte que se quer que ele conteste. O total da semana vive no pé da
          lista, com o link para a ver. */}
      <Mosaico
        valor={formatMoneyRounded(resumo.wasted_today_eur)}
        rotulo="deitado fora hoje"
        extra={`desde as ${desde}`}
        titulo={`O dia de negócio deste estabelecimento começa às ${desde}, ou seja às ${formatTime(resumo.wasted_since)} de hoje — o que foi deitado fora antes disso conta no dia anterior`}
        ativo={vistaAtiva === "desperdicio"}
        vista="desperdicio"
      />
    </div>
  );
}

/** Pendente: um aviso só, no contentor, para quem ouve o ecrã (medido no Stock). */
export function EsqueletoDosNumerosDeAlertas() {
  return (
    <div aria-busy="true" className="grid grid-cols-3 gap-2 px-4 pt-3 pb-2">
      <span className="sr-only">A carregar os números…</span>
      {[0, 1, 2].map((indice) => (
        <div key={indice} className={`${CLASSE_MOSAICO} border-border bg-surface`}>
          <Skeleton className="h-5 w-12" />
          <Skeleton className="mt-1 h-7 w-full" />
        </div>
      ))}
    </div>
  );
}

export function ErroDosNumerosDeAlertas({
  aoTentarOutraVez,
}: {
  readonly aoTentarOutraVez: () => void;
}) {
  return (
    <div className="px-4 pt-3 pb-2">
      <Alert className="border-danger-border bg-danger-surface">
        <CircleAlert aria-hidden="true" className="text-danger" />
        <AlertTitle>Não foi possível contar os alertas</AlertTitle>
        <AlertDescription className="flex flex-col items-start gap-2">
          <span>A lista abaixo continua a funcionar. Os três números voltam à segunda tentativa.</span>
          <Button variant="outline" onClick={aoTentarOutraVez}>
            <RotateCcw aria-hidden="true" />
            Tentar outra vez
          </Button>
        </AlertDescription>
      </Alert>
    </div>
  );
}
