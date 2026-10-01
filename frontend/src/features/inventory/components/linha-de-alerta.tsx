import { Link } from "@tanstack/react-router";
import { ChevronRight, CircleAlert, PackageSearch, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { formatMoney } from "@/lib/format";

import type { Alerta, MotivoQuebra } from "../schemas";
import { MOTIVOS_DE_DESPERDICIO, rotuloDeMotivo, textoDeQuantidade } from "../vocabulario";
import { TextoDeValidade } from "./validade";

/**
 * Uma linha de alerta: nome · lote e validade · quantidade em risco · valor € ·
 * e a distinção entre **"consumir até"** e **"consumir de preferência antes
 * de"** (guião §1).
 *
 * Três coisas que não são decoração:
 *
 *  - **a validade reusa o `TextoDeValidade` do ecrã de Stock**, com o
 *    vocabulário que ele já estabeleceu: "expira/expirou" para o `use_by`,
 *    "perde qualidade" para o `best_before`, e o `best_before` **nunca** chega a
 *    vermelho. Sem isto o dono perde a confiança nos alertas na primeira
 *    amêndoa laminada marcada a vermelho, e perde-a para a lista inteira;
 *  - **o limiar está dentro do alerta** ("expira em 2 dias — aviso a 3"), para
 *    ele o contestar em voz alta. Um painel de limiares está proibido (guião
 *    §4, nº 7) e é o que nos faria perder qual devia ser o valor por omissão;
 *  - **a ação principal é um toque na linha: "Deitei fora"**, e o segundo toque
 *    escolhe o motivo. É esta ação que alimenta o número que o dono mais quer,
 *    e os dois toques são também a confirmação — uma linha que deita fora stock
 *    ao primeiro toque, sem dizer porquê, era um movimento irreversível por
 *    acidente (o ledger é append-only: ADR 0006).
 *
 * Uma linha de **falta** não tem esta ação: não se deita fora o que não há. Essa
 * é um `<Link>` para o artigo, que é onde está o histórico e de onde se recebe.
 */

function Corpo({ alerta }: { readonly alerta: Alerta }) {
  const emRisco = alerta.reason === "expiry";
  const rodape = [
    // "lote L-AMD-0928" e não "L. L-AMD-0928": é a mesma forma que o histórico
    // de movimentos do ecrã de Stock usa, e os códigos deste catálogo já
    // começam por "L-" — o prefixo do guião ficaria a dizer duas vezes o mesmo.
    alerta.lot === null ? null : `lote ${alerta.lot.lot_code}`,
    alerta.lot === null || alerta.threshold_days === null
      ? null
      : `aviso a ${String(alerta.threshold_days)} dias`,
    alerta.min_quantity === null ? null : `mínimo ${textoDeQuantidade(alerta.min_quantity)}`,
    alerta.location?.name ?? (alerta.reason === "missing" ? "todas as lojas" : null),
  ].filter((parte): parte is string => parte !== null);

  return (
    <>
      <span className="flex items-baseline gap-3">
        <span className="min-w-0 flex-1 truncate font-medium">{alerta.short_name}</span>
        <span data-numeric className="shrink-0 text-sm">
          {textoDeQuantidade(alerta.quantity)}
        </span>
      </span>

      <span className="flex items-baseline gap-3 text-xs">
        <span className="min-w-0 flex-1">
          {alerta.lot === null ? (
            // Três palavras e não duas: um stock **negativo** não é "sem
            // stock", é um ledger a dizer que saiu mais do que entrou — e é a
            // sonda da Q1 (a nata a −2 L depois de uma quebra registada sem
            // stock). Chamar-lhe "sem stock" apagava a pergunta.
            <span className={alerta.severity === "danger" ? "text-danger" : "text-warning"}>
              {alerta.quantity.base.startsWith("-")
                ? "stock negativo"
                : Number(alerta.quantity.base) === 0
                  ? "sem stock"
                  : "abaixo do mínimo"}
            </span>
          ) : (
            <TextoDeValidade validade={alerta.lot} limiarEmDias={alerta.threshold_days ?? 0} />
          )}
        </span>
        <span data-numeric className="shrink-0">
          {formatMoney(alerta.value_eur)}
        </span>
        <span className="w-14 shrink-0 text-right text-muted-foreground">
          {emRisco ? "em risco" : "a repor"}
        </span>
      </span>

      {rodape.length === 0 ? null : (
        <span className="truncate text-xs text-muted-foreground">{rodape.join(" · ")}</span>
      )}
    </>
  );
}

/**
 * O `scroll-mt-16` não é margem: é o header *sticky* de 48px do shell. Sem ele,
 * a linha que recebe o foco por teclado pode ficar debaixo dele — foco visível
 * mas tapado, que é o mesmo que foco invisível.
 */
const CLASSE_LINHA =
  "flex min-h-14 w-full scroll-mt-16 flex-col justify-center gap-1 px-4 py-2 text-left transition-colors hover:bg-surface-2";

export function LinhaDeAlerta({
  alerta,
  aberto,
  aoAlternar,
  aoDeitarFora,
  aRegistar,
  erro,
  idDoPainel,
}: {
  readonly alerta: Alerta;
  readonly aberto: boolean;
  readonly aoAlternar: () => void;
  readonly aoDeitarFora: (motivo: MotivoQuebra) => void;
  readonly aRegistar: boolean;
  readonly erro: string | null;
  /** O `id` do painel de motivos, para o `aria-controls` do botão. */
  readonly idDoPainel: string;
}) {
  if (alerta.reason === "missing") {
    return (
      <li className="border-b border-border last:border-b-0">
        <Link
          to="/stock/$artigo"
          params={{ artigo: alerta.product }}
          search={{}}
          className={CLASSE_LINHA}
        >
          <Corpo alerta={alerta} />
          <span className="flex items-center gap-1 text-xs text-muted-foreground">
            <PackageSearch aria-hidden="true" className="size-3.5 shrink-0" />
            Ver o artigo
            <ChevronRight aria-hidden="true" className="size-3.5 shrink-0" />
          </span>
        </Link>
      </li>
    );
  }

  const rotulo = `Deitei fora — ${alerta.short_name}, ${
    alerta.lot === null ? "" : `lote ${alerta.lot.lot_code}, `
  }${textoDeQuantidade(alerta.quantity)}`;

  return (
    <li className="border-b border-border last:border-b-0">
      <button
        type="button"
        onClick={aoAlternar}
        aria-expanded={aberto}
        aria-controls={idDoPainel}
        aria-label={rotulo}
        className={CLASSE_LINHA}
      >
        <Corpo alerta={alerta} />
        <span className="flex items-center gap-1 text-xs text-primary">
          <Trash2 aria-hidden="true" className="size-3.5 shrink-0" />
          Deitei fora
          <ChevronRight aria-hidden="true" className="size-3.5 shrink-0" />
        </span>
      </button>

      {aberto ? (
        // Segundo toque: o motivo. Cinco botões e não um `<select>` — escolher
        // num menu nativo com a mão suja é dois gestos e um scroll, e o motivo
        // é obrigatório (`inventory-domain` §8), logo é o passo e não um extra.
        <div
          id={idDoPainel}
          className="flex flex-col gap-2 border-t border-border bg-surface-2 px-4 py-3"
        >
          <p className="text-sm">
            Deitar fora <span data-numeric>{textoDeQuantidade(alerta.quantity)}</span>
            {alerta.lot === null ? "" : ` do lote ${alerta.lot.lot_code}`} — porquê?
          </p>
          <div className="flex flex-wrap gap-2">
            {MOTIVOS_DE_DESPERDICIO.map((motivo) => (
              <Button
                key={motivo}
                variant="outline"
                disabled={aRegistar}
                onClick={() => {
                  aoDeitarFora(motivo);
                }}
              >
                {rotuloDeMotivo(motivo)}
              </Button>
            ))}
          </div>
          <div className="flex items-center gap-3">
            <Button variant="ghost" disabled={aRegistar} onClick={aoAlternar}>
              Cancelar
            </Button>
            <Button asChild variant="ghost">
              <Link to="/stock/$artigo" params={{ artigo: alerta.product }} search={{}}>
                Ver o artigo
              </Link>
            </Button>
            {aRegistar ? (
              <span className="text-sm text-muted-foreground">A registar…</span>
            ) : null}
          </div>
          {erro === null ? null : (
            <p role="alert" className="flex items-start gap-1.5 text-sm text-danger">
              <CircleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
              <span>{erro}</span>
            </p>
          )}
        </div>
      ) : null}
    </li>
  );
}
