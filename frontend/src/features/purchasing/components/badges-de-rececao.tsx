import { CircleCheck, FileClock, Info, TriangleAlert } from "lucide-react";

import { Badge } from "@/components/ui/badge";

import type { Rececao, TipoDeDocumento } from "../schemas";
import { nomeDoDocumento, siglaDeDocumento, textoDeNif } from "../vocabulario";

/**
 * Os quatro badges de uma receção. Vivem juntos porque a lista e o detalhe
 * mostram **os mesmos**, e um badge que diga outra coisa num ecrã do que no
 * outro é como o dono deixa de confiar na lista.
 *
 * Nenhum comunica só por cor: os quatro têm texto, e o texto é o que se lê em
 * voz alta ("precisa de revisão", "NIF diferente do da empresa"). A tinta é o
 * `-surface` do estado com o texto em `foreground`, que é o segundo dos três
 * papéis do DESIGN.md §2.
 */

/** O tipo de documento, como vem impresso: FT · FR · FS · NC · guia. */
export function BadgeDeTipo({ tipo }: { readonly tipo: TipoDeDocumento }) {
  return (
    <Badge variant="outline" title={nomeDoDocumento(tipo)} className="shrink-0 font-mono">
      {siglaDeDocumento(tipo)}
      <span className="sr-only"> ({nomeDoDocumento(tipo)})</span>
    </Badge>
  );
}

/**
 * "precisa de revisão (2 linhas)" — e o número é o que **falta**, não o que
 * existe. É este badge que diz que o documento ainda não deu entrada no stock.
 */
export function BadgeDeRevisao({ linhas }: { readonly linhas: number }) {
  return (
    <Badge className="bg-warning-surface text-foreground">
      <TriangleAlert aria-hidden="true" className="text-warning" />
      precisa de revisão
      {linhas === 0 ? null : <> ({linhas === 1 ? "1 linha" : `${String(linhas)} linhas`})</>}
    </Badge>
  );
}

/** Já deu entrada no stock. Cinzento, porque o que se procura são os outros. */
export function BadgeDeConfirmada() {
  return (
    <Badge className="bg-surface-2 text-muted-foreground">
      <CircleCheck aria-hidden="true" className="text-success" />
      no stock
    </Badge>
  );
}

/**
 * A mercadoria entrou por guia e a fatura vem a fim de mês. Não é um erro — é o
 * normal de quem compra a distribuidores, e é por isso que o badge é neutro.
 */
export function BadgeSemFatura() {
  return (
    <Badge className="bg-surface-2 text-muted-foreground">
      <FileClock aria-hidden="true" />
      entrou sem fatura
    </Badge>
  );
}

/**
 * A sonda da Q10, e é toda a razão de ela existir neste ecrã: **um badge
 * discreto, sem drama**.
 *
 * Ninguém oferece em abstracto que leva faturas da empresa ao NIF pessoal; um
 * badge põe o facto à frente dele em dois segundos, e a reação é a resposta.
 * Por isso é cinzento e não vermelho: pintá-lo de aviso transformava a
 * observação numa acusação, e a conversa que se seguia era sobre o ecrã.
 */
export function BadgeDeNifDiferente({ rececao }: { readonly rececao: Rececao }) {
  if (rececao.customer_nif === null || rececao.customer_nif === rececao.company_nif) return null;

  return (
    <Badge
      className="bg-surface-2 text-muted-foreground"
      title={`Documento emitido a ${rececao.customer_name ?? "outro adquirente"}, NIF ${textoDeNif(rececao.customer_nif)}. A empresa é ${rececao.company_name}, NIF ${textoDeNif(rececao.company_nif)}.`}
    >
      <Info aria-hidden="true" />
      NIF diferente do da empresa
    </Badge>
  );
}
