import { CircleCheck, TriangleAlert } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { formatDate, formatMoney, formatRate, formatTime } from "@/lib/format";

import type { Rececao } from "../schemas";
import { textos } from "../textos";
import { nomeDoDocumento, textoDeNif } from "../vocabulario";
import {
  BadgeDeConfirmada,
  BadgeDeNifDiferente,
  BadgeDeRevisao,
  BadgeSemFatura,
  BadgeDeTipo,
} from "./badges-de-rececao";

/**
 * O cabeçalho do documento: quem o emitiu, que documento é, quando chegou, e
 * quanto diz que custou.
 *
 * O total está em cima porque é o número que ele compara com o papel; os
 * totais por taxa ficam no rodapé da lista, que é onde estão impressos.
 */

/**
 * O adquirente, quando **não** é a empresa — a sonda da Q10 por extenso, uma
 * linha abaixo do badge.
 *
 * Sem drama e sem cor de aviso: a frase diz o que está no documento e o que
 * está na empresa, e cala-se. A reação dele é a resposta à pergunta que ninguém
 * faria em abstracto.
 */
function Adquirente({ rececao }: { readonly rececao: Rececao }) {
  if (rececao.customer_nif === null || rececao.customer_nif === rececao.company_nif) return null;

  return (
    // Duas funções do catálogo e não uma frase: os dois NIF vão em
    // `data-numeric` e ficam entre elas.
    <p className="text-pretty text-xs text-muted-foreground">
      {textos.cabecalho.emitidaA(rececao.customer_name ?? textos.comuns.outroAdquirente)}{" "}
      <span data-numeric>{textoDeNif(rececao.customer_nif)}</span>.{" "}
      {textos.cabecalho.aEmpresaE(rececao.company_name)}{" "}
      <span data-numeric>{textoDeNif(rececao.company_nif)}</span>.
    </p>
  );
}

/**
 * O aviso de totais que não batem — **suave, e sem bloquear nada**.
 *
 * "Confirmar uma fatura cujos totais não batem tem de ser possível" (guião §4,
 * proibição 3): quem bloqueia aqui está a responder pelo dono à Q1. A diferença
 * costuma ser um desconto de rodapé ou portes, e dizer isso poupa-lhe o tempo
 * de procurar o erro nas linhas.
 */
export function AvisoDeTotais({ rececao }: { readonly rececao: Rececao }) {
  const impresso = rececao.document_total;
  const somado = rececao.lines_total;
  if (impresso === null || somado === null) return null;
  if (Number(impresso) === Number(somado)) return null;

  return (
    <div className="px-4">
      <Alert className="border-warning-border bg-warning-surface">
        <TriangleAlert aria-hidden="true" className="text-warning" />
        <AlertTitle>{textos.cabecalho.totaisNaoBatemTitulo}</AlertTitle>
        {/* Três partes nomeadas: os dois valores do meio são `data-numeric`, e
            uma frase só tirava o mono aos algarismos que ele vai comparar. */}
        <AlertDescription className="text-pretty">
          {textos.cabecalho.totaisNaoBatemInicio}{" "}
          <span data-numeric>{formatMoney(impresso)}</span>{" "}
          {textos.cabecalho.totaisNaoBatemMeio}{" "}
          <span data-numeric>{formatMoney(somado)}</span>
          {textos.cabecalho.totaisNaoBatemFim}
        </AlertDescription>
      </Alert>
    </div>
  );
}

export function CabecalhoDaRececao({ rececao }: { readonly rececao: Rececao }) {
  const porRever = rececao.status === "needs_review";

  return (
    <header className="flex flex-col gap-2 px-4">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h1 className="min-w-0 text-2xl font-semibold text-balance">{rececao.supplier.name}</h1>
        {rececao.document_total === null ? null : (
          <span data-numeric className="text-xl font-semibold">
            {formatMoney(rececao.document_total)}
          </span>
        )}
      </div>

      <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-muted-foreground">
        <BadgeDeTipo tipo={rececao.doc_type} />
        <span>
          {nomeDoDocumento(rececao.doc_type)}{" "}
          {rececao.doc_number ?? <span className="italic">{textos.comuns.semNumero}</span>}
        </span>
        <span>
          · {textos.cabecalho.recebida}{" "}
          <span data-numeric>{formatDate(rececao.received_at)}</span> {textos.comuns.as}{" "}
          <span data-numeric>{formatTime(rececao.received_at)}</span>
        </span>
      </p>

      <div className="flex flex-wrap items-center gap-1.5">
        {porRever ? <BadgeDeRevisao linhas={rececao.lines_to_review} /> : <BadgeDeConfirmada />}
        {rececao.awaiting_invoice ? <BadgeSemFatura /> : null}
        <BadgeDeNifDiferente rececao={rececao} />
      </div>

      <Adquirente rececao={rececao} />

      {rececao.awaiting_invoice ? (
        // A guia de remessa: a mercadoria entra antes de existir fatura, e a
        // fatura de fim de mês reconcilia N entregas. É o normal de quem compra
        // a distribuidores, por isso a frase é informativa e não um aviso.
        <p className="text-pretty text-xs text-muted-foreground">{textos.comuns.entrouPorGuia}</p>
      ) : null}

      {rececao.doc_type === "NC" ? (
        // Uma nota de crédito credita valor; não dá entrada de mercadoria. No
        // seed é a devolução de duas grades vazias — vasilhame, que não é stock
        // consumível —, e por isso confirmá-la não cria movimento nenhum. É o
        // caso que separa "confirmar um documento" de "dar entrada de
        // mercadoria", e é dito aqui porque é aqui que ele o pergunta.
        <p className="text-pretty text-xs text-muted-foreground">
          {textos.cabecalho.notaDeCredito}
        </p>
      ) : null}

      <p className="text-xs text-muted-foreground">
        {/* "Em" e não "entra em": o mesmo texto serve um documento que dá
            entrada de mercadoria e um que não dá. */}
        {textos.cabecalho.em}{" "}
        {rececao.locations.map((local, indice) => (
          <span key={local.id}>
            {indice === 0 ? "" : " · "}
            {local.name}
          </span>
        ))}
        {rececao.confirmed_at === null ? null : (
          <>
            {" · "}
            {textos.cabecalho.confirmada}{" "}
            <span data-numeric>{formatDate(rececao.confirmed_at)}</span>{" "}
            {textos.comuns.as}{" "}
            <span data-numeric>{formatTime(rececao.confirmed_at)}</span>
            {rececao.confirmed_by === null ? null : (
              <> {textos.cabecalho.por(rececao.confirmed_by)}</>
            )}
          </>
        )}
      </p>
    </header>
  );
}

/**
 * O rodapé do documento: a base e o **IVA por taxa**, como está impresso.
 *
 * Está aqui e não no cabeçalho porque é aqui que está no papel, e porque a
 * linha que interessa ao ecrã é a frase do fim: as taxas são as da fatura.
 * Nenhum artigo deste catálogo "tem" uma taxa — ela muda entre o Continente e
 * as Regiões Autónomas, e muda de fornecedor para fornecedor no mesmo artigo.
 */
export function TotaisDaRececao({ rececao }: { readonly rececao: Rececao }) {
  if (rececao.lines_total === null) {
    return (
      <p className="px-4 py-3 text-xs text-muted-foreground">{textos.cabecalho.guiaSemPrecos}</p>
    );
  }

  return (
    <div className="flex flex-col gap-1 border-t border-border px-4 py-3">
      {rececao.vat_breakdown.map((taxa) => (
        <p key={taxa.rate} className="flex items-baseline justify-between gap-3 text-xs">
          <span className="text-muted-foreground">
            {textos.cabecalho.baseAIva} <span data-numeric>{formatRate(taxa.rate)}</span>
          </span>
          <span className="flex items-baseline gap-3">
            <span data-numeric className="text-muted-foreground">
              {formatMoney(taxa.base)}
            </span>
            <span data-numeric className="w-20 text-right">
              {formatMoney(taxa.vat)}
            </span>
          </span>
        </p>
      ))}
      <p className="flex items-baseline justify-between gap-3 text-sm font-medium">
        <span>{textos.cabecalho.total}</span>
        <span data-numeric>{formatMoney(rececao.lines_total)}</span>
      </p>
      <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <CircleCheck aria-hidden="true" className="size-3 shrink-0" />
        {textos.cabecalho.taxasDaLinha}
      </p>
    </div>
  );
}
