import { Link } from "@tanstack/react-router";
import { EyeOff } from "lucide-react";
import type { ReactNode } from "react";

import { Skeleton } from "@/components/ui/skeleton";

import type { Contagem, ProgressoDeZona } from "../schemas";
import { textos } from "../textos";

/**
 * O topo do ecrã Contar: **progresso** e **zona actual** (guião §1).
 *
 * Duas decisões de orçamento, que num 360×640 são a mesma decisão:
 *
 *  - **não há barra de progresso.** O "3 de 9" é o progresso, e as pastilhas
 *    das zonas repetem-no zona a zona — uma barra acrescentava 12px e nenhuma
 *    informação. Gráficos decorativos estão proibidos (guião §4, nº 14) e uma
 *    barra que diz o mesmo que o número ao lado é decoração;
 *  - **as pastilhas são links e levam o `?zona=` ao URL.** Contar é andar de
 *    zona em zona: recarregar o telemóvel no meio da arca tem de devolver a
 *    arca, e é por isso que o estado está no URL e não num `useState` (ADR
 *    0008, decisão 1).
 *
 * A zona cega diz que é cega, aqui e na linha: é a sonda do guião §3 e tem de
 * ser visível antes de ele começar a contar, não depois de estranhar a falta do
 * número.
 */

function Pastilha({
  children,
  ativa,
  para,
  titulo,
}: {
  readonly children: ReactNode;
  readonly ativa: boolean;
  readonly para: string | undefined;
  readonly titulo: string;
}) {
  return (
    <Link
      to="/contar"
      search={(anteriores) => ({ ...anteriores, zona: para })}
      title={titulo}
      className={`flex min-h-11 scroll-mt-16 items-center gap-1.5 rounded-lg border px-2.5 text-xs transition-colors ${
        ativa
          ? "border-primary bg-surface-2 font-medium text-foreground"
          : "border-border-strong bg-surface text-muted-foreground hover:bg-surface-2 hover:text-foreground"
      }`}
    >
      {children}
    </Link>
  );
}

export function ProgressoDaContagem({
  contagem,
  zonaAtiva,
}: {
  readonly contagem: Contagem;
  readonly zonaAtiva: string | undefined;
}) {
  const zonaMostrada: ProgressoDeZona | null =
    contagem.zones.find((zona) => zona.slug === zonaAtiva) ?? contagem.current_zone;

  return (
    <div className="flex flex-col gap-2 border-b border-border px-4 pt-3 pb-2">
      <div className="flex items-baseline justify-between gap-3">
        {/* O progresso muda a cada número escrito, e quem está a contar pode
            não estar a olhar para o topo do ecrã: tem de o ouvir. */}
        <p aria-live="polite" className="flex items-baseline gap-1.5">
          <span data-numeric className="text-2xl leading-none font-semibold">
            {contagem.counted_lines}
          </span>
          <span className="text-sm text-muted-foreground">
            {textos.contagem.de} <span data-numeric>{contagem.total_lines}</span>{" "}
            {textos.contagem.contados}
          </span>
        </p>
        <p className="min-w-0 truncate text-sm">
          {zonaMostrada === null ? (
            <span className="text-muted-foreground">{textos.contagem.tudoContado}</span>
          ) : (
            <>
              <span className="text-muted-foreground">{textos.contagem.zonaPrefixo}{" "}</span>
              <span className="font-medium">{zonaMostrada.name}</span>
            </>
          )}
        </p>
      </div>

      {/* `flex-wrap` e não um carrossel horizontal: com quatro zonas a 360px a
          quarta ficaria fora do ecrã, e uma zona escondida é uma zona que não
          se conta. */}
      <nav aria-label={textos.contagem.zonas} className="flex flex-wrap gap-1.5">
        <Pastilha
          ativa={zonaAtiva === undefined}
          para={undefined}
          titulo={textos.contagem.todasAsZonasPista}
        >
          {textos.contagem.todasAsZonas}
        </Pastilha>
        {contagem.zones.map((zona) => (
          <Pastilha
            key={zona.slug}
            ativa={zona.slug === zonaAtiva}
            para={zona.slug}
            titulo={
              zona.blind
                ? textos.contagem.zonaCegaPista(zona.name)
                : textos.contagem.zonaAbertaPista(zona.name)
            }
          >
            {zona.blind ? <EyeOff aria-hidden="true" className="size-3.5 shrink-0" /> : null}
            <span>{zona.name}</span>
            <span data-numeric className="text-muted-foreground">
              {zona.counted_lines}/{zona.total_lines}
            </span>
            {zona.blind ? <span className="sr-only">{textos.contagem.cegaSrOnly}</span> : null}
          </Pastilha>
        ))}
      </nav>
    </div>
  );
}

/** O mesmo bloco enquanto não há dados, com a mesma altura. */
export function EsqueletoDoProgresso() {
  return (
    <div
      aria-busy="true"
      className="flex flex-col gap-2 border-b border-border px-4 pt-3 pb-2"
    >
      <span className="sr-only">{textos.contagem.aCarregarContagem}</span>
      <div className="flex items-center justify-between gap-3">
        <Skeleton className="h-7 w-32" />
        <Skeleton className="h-4 w-24" />
      </div>
      <div className="flex gap-1.5">
        <Skeleton className="h-11 w-20" />
        <Skeleton className="h-11 w-24" />
        <Skeleton className="h-11 w-24" />
      </div>
    </div>
  );
}
