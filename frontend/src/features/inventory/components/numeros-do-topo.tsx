import { Link } from "@tanstack/react-router";
import { CircleAlert, Funnel, RotateCcw } from "lucide-react";
import type { ReactNode } from "react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { formatMoneyRounded } from "@/lib/format";

import type { ResumoDeStock } from "../schemas";

/**
 * Os três números do topo (guião da sessão 0, §1): artigos em falta · a expirar
 * dentro do horizonte · valor de stock em euros.
 *
 * **Dois são filtros e o terceiro é uma leitura.** Os dois primeiros são
 * `<Link>`s que põem o filtro no URL — logo recarregar a página, voltar atrás e
 * mostrar o link a alguém dão o mesmo ecrã, e o Cmd+clique abre noutro
 * separador. O valor em euros não é tocável porque não há destino honesto para
 * ele neste shell: o que lá estaria — valor por artigo, CMP, margem — é
 * precisão falsa em euros, proibida pelo guião §4. O guião pede "3 números
 * tocáveis"; ficam dois, e a razão está escrita aqui em vez de um terceiro
 * destino inventado.
 *
 * **O limiar de dias vem do servidor e está no rótulo**, não num painel de
 * configurações: é assim que o dono o contesta em voz alta ("três dias é pouco")
 * em vez de o ir mudar sozinho (guião §4, proibição 7).
 *
 * O número em euros é arredondado ao euro. Um cêntimo num total calculado a
 * partir de custos médios é precisão que não existe, e convida a discutir o
 * cêntimo em vez do desperdício.
 */
export type FiltroDeStock = "falta" | "validade" | undefined;

const CLASSE_MOSAICO =
  "flex min-h-14 flex-col items-end justify-center gap-0.5 rounded-xl border px-2.5 py-2 text-right";

const CLASSE_NUMERO = "text-lg leading-none font-semibold sm:text-2xl";

const CLASSE_ROTULO = "text-xs leading-tight text-muted-foreground";

function Mosaicos({
  children,
  rotulo,
  ...resto
}: {
  readonly children: ReactNode;
  readonly rotulo?: string;
  readonly "aria-busy"?: "true";
}) {
  return (
    <div className="grid grid-cols-3 gap-2 px-4 pt-3 pb-2" {...resto}>
      {rotulo === undefined ? null : <span className="sr-only">{rotulo}</span>}
      {children}
    </div>
  );
}

export function EsqueletoDosNumeros() {
  return (
    // O aviso de "a carregar" é **um**, no contentor: medido numa renderização,
    // um por mosaico dava três anúncios iguais a quem ouve o ecrã.
    <Mosaicos aria-busy="true" rotulo="A carregar os números…">
      {[0, 1, 2].map((indice) => (
        <div key={indice} className={`${CLASSE_MOSAICO} border-border bg-surface`}>
          <Skeleton className="h-5 w-12" />
          <Skeleton className="mt-1 h-7 w-full" />
        </div>
      ))}
    </Mosaicos>
  );
}

export function ErroDosNumeros({ aoTentarOutraVez }: { readonly aoTentarOutraVez: () => void }) {
  return (
    <div className="px-4 pt-3 pb-2">
      <Alert className="border-danger-border bg-danger-surface">
        <CircleAlert aria-hidden="true" className="text-danger" />
        <AlertTitle>Não foi possível contar os artigos em falta</AlertTitle>
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

/** Um mosaico que também é filtro. O estado ativo não é só cor: leva ícone. */
function MosaicoDeFiltro({
  valor,
  rotulo,
  titulo,
  ativo,
  filtro,
}: {
  readonly valor: number;
  readonly rotulo: string;
  readonly titulo: string;
  readonly ativo: boolean;
  readonly filtro: "falta" | "validade";
}) {
  return (
    <Link
      to="/stock"
      // O reducer recebe os filtros actuais já validados pela rota: tocar
      // segunda vez no mesmo mosaico limpa o filtro do URL em vez de o deixar lá.
      search={(anteriores) => ({ ...anteriores, filtro: ativo ? undefined : filtro })}
      title={titulo}
      // Sem `aria-current` à mão: medido, o `<Link>` põe `aria-current="page"`
      // no mosaico certo (compara também a search params) e sobrepõe-se a
      // qualquer valor nosso. O `ativo` fica para a tinta e para saber que um
      // segundo toque **limpa** o filtro.
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
        <span>{rotulo}</span>
      </span>
    </Link>
  );
}

export function NumerosDoTopo({
  resumo,
  filtroAtivo,
}: {
  readonly resumo: ResumoDeStock;
  readonly filtroAtivo: FiltroDeStock;
}) {
  const dias = resumo.expiring_within_days;

  return (
    <Mosaicos>
      <MosaicoDeFiltro
        valor={resumo.below_min_count}
        rotulo="em falta"
        titulo="Artigos abaixo do mínimo de stock"
        ativo={filtroAtivo === "falta"}
        filtro="falta"
      />
      <MosaicoDeFiltro
        valor={resumo.expiring_count}
        rotulo={`a expirar ≤\u00a0${String(dias)} dias`}
        titulo={`Artigos com validade dentro de ${String(dias)} dias — o limiar é do servidor`}
        ativo={filtroAtivo === "validade"}
        filtro="validade"
      />
      {/* Leitura, não filtro: um `<div>` sem `onClick`, para não prometer um
          toque que não existe. */}
      <div className={`${CLASSE_MOSAICO} border-border bg-surface`}>
        <span data-numeric className={CLASSE_NUMERO}>
          {formatMoneyRounded(resumo.stock_value_eur)}
        </span>
        <span className={CLASSE_ROTULO}>valor de stock</span>
      </div>
    </Mosaicos>
  );
}
