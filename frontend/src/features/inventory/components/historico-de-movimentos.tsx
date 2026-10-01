import { CircleAlert, RotateCcw, ScrollText } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDate, formatDaysAway, formatTime } from "@/lib/format";

import type { Movimento } from "../schemas";
import { rotuloDeMotivo, rotuloDeMovimento, textoDeQuantidade } from "../vocabulario";

/**
 * O histórico de movimentos de um artigo — o ledger, tal como está.
 *
 * **Toda a linha tem autor**, e isso é a sonda da Q7 do guião: "Ajuste −2,0 kg ·
 * Ana (balcão) · quebra" é concreto, e é a partir dele que se pergunta "a Ana
 * podia ter feito isto? e apagar?". Perguntar "quantos papéis queres" em
 * abstracto não funciona.
 *
 * **Não há botão de editar nem de apagar, em linha nenhuma.** Um movimento é
 * append-only na própria base de dados (ADR 0006: `REVOKE UPDATE, DELETE` em
 * `inventory_stockmovement`) e corrige-se com um movimento inverso. O servidor
 * de fixtures também não tem rota para alterar — de propósito.
 */

/** A diferença em dias civis entre um instante e hoje, hora local. */
function diferencaEmDias(iso: string): number {
  const momento = new Date(iso);
  const dia = new Date(momento.getFullYear(), momento.getMonth(), momento.getDate());
  const agora = new Date();
  const hoje = new Date(agora.getFullYear(), agora.getMonth(), agora.getDate());
  const milissegundosPorDia = 24 * 60 * 60 * 1000;
  return Math.round((dia.getTime() - hoje.getTime()) / milissegundosPorDia);
}

function rotuloDoDia(iso: string): string {
  const dias = diferencaEmDias(iso);
  const texto = Math.abs(dias) <= 1 ? formatDaysAway(dias) : formatDate(iso);
  return texto.charAt(0).toUpperCase() + texto.slice(1);
}

interface Grupo {
  readonly rotulo: string;
  readonly movimentos: readonly Movimento[];
}

/**
 * Agrupa por dia **mantendo a ordem do servidor** (do mais recente para o mais
 * antigo). Um cabeçalho por dia em vez da data em cada linha: a data repetida
 * doze vezes gasta a largura que o autor e o motivo precisam.
 */
function agrupar(movimentos: readonly Movimento[]): readonly Grupo[] {
  // Um `Map` preserva a ordem de inserção, logo a ordem do servidor (do mais
  // recente para o mais antigo) atravessa o agrupamento sem ser reordenada.
  const porDia = new Map<string, Movimento[]>();

  for (const movimento of movimentos) {
    const rotulo = rotuloDoDia(movimento.occurred_at);
    const grupo = porDia.get(rotulo);
    if (grupo === undefined) porDia.set(rotulo, [movimento]);
    else grupo.push(movimento);
  }

  return [...porDia.entries()].map(([rotulo, lista]) => ({ rotulo, movimentos: lista }));
}

function LinhaDeMovimento({ movimento }: { readonly movimento: Movimento }) {
  const rodape = [
    movimento.lot_code === null ? null : `lote ${movimento.lot_code}`,
    movimento.reference,
  ].filter((parte): parte is string => parte !== null);

  return (
    <li className="flex flex-col gap-0.5 border-b border-border px-4 py-2 last:border-b-0">
      <span className="flex items-baseline gap-3">
        <span className="min-w-0 flex-1 truncate font-medium">
          {rotuloDeMovimento(movimento.movement_type)}
        </span>
        <span data-numeric className="shrink-0 text-sm">
          {textoDeQuantidade(movimento.quantity)}
        </span>
      </span>
      <span className="truncate text-xs text-muted-foreground">
        {formatTime(movimento.occurred_at)} · {movimento.created_by} ·{" "}
        {movimento.location.name}
        {movimento.reason === null ? "" : ` · ${rotuloDeMotivo(movimento.reason)}`}
      </span>
      {rodape.length === 0 ? null : (
        <span className="truncate text-xs text-muted-foreground">{rodape.join(" · ")}</span>
      )}
    </li>
  );
}

export function HistoricoDeMovimentos({
  movimentos,
  total,
  aCarregar,
  mensagemDeErro,
  aoTentarOutraVez,
}: {
  readonly movimentos: readonly Movimento[] | undefined;
  /** O total do servidor. Maior que o que está à vista = página truncada. */
  readonly total: number;
  readonly aCarregar: boolean;
  readonly mensagemDeErro: string | null;
  readonly aoTentarOutraVez: () => void;
}) {
  return (
    <section className="flex flex-col gap-2">
      <h2 className="px-4 text-sm font-semibold">Movimentos</h2>

      {aCarregar ? (
        <div aria-busy="true" className="flex flex-col">
          <span className="sr-only">A carregar os movimentos…</span>
          {[0, 1, 2, 3].map((indice) => (
            <div key={indice} className="flex flex-col gap-1.5 border-b border-border px-4 py-2">
              <div className="flex items-center justify-between gap-3">
                <Skeleton className="h-4 w-24" />
                <Skeleton className="h-4 w-20" />
              </div>
              <Skeleton className="h-3 w-48" />
            </div>
          ))}
        </div>
      ) : null}

      {mensagemDeErro === null ? null : (
        <div className="px-4">
          <Alert className="border-danger-border bg-danger-surface">
            <CircleAlert aria-hidden="true" className="text-danger" />
            <AlertTitle>Não foi possível carregar os movimentos</AlertTitle>
            <AlertDescription className="flex flex-col items-start gap-2">
              <span>{mensagemDeErro}</span>
              <Button variant="outline" onClick={aoTentarOutraVez}>
                <RotateCcw aria-hidden="true" />
                Tentar outra vez
              </Button>
            </AlertDescription>
          </Alert>
        </div>
      )}

      {movimentos === undefined ? null : movimentos.length === 0 ? (
        <div className="flex flex-col items-start gap-2 px-4 py-6">
          <ScrollText aria-hidden="true" className="size-6 text-muted-foreground" />
          <p className="font-medium">Sem movimentos</p>
          <p className="text-pretty text-sm text-muted-foreground">
            Este artigo ainda não tem entradas, consumos nem desperdício registados.
          </p>
        </div>
      ) : (
        <>
          {agrupar(movimentos).map((grupo) => (
            <div key={grupo.rotulo} className="flex flex-col">
              <h3 className="bg-surface-2 px-4 py-1 text-xs font-medium text-muted-foreground">
                {grupo.rotulo}
              </h3>
              <ul className="flex flex-col">
                {grupo.movimentos.map((movimento) => (
                  <LinhaDeMovimento key={movimento.id} movimento={movimento} />
                ))}
              </ul>
            </div>
          ))}
          {total > movimentos.length ? (
            <p className="px-4 py-2 text-xs text-muted-foreground">
              Os {movimentos.length} movimentos mais recentes, de {total}.
            </p>
          ) : null}
        </>
      )}
    </section>
  );
}
