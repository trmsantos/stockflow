import { CircleAlert } from "lucide-react";

import { CLASSE_MICROROTULO } from "@/components/tabela";
import { formatMoney, formatPercentPoints } from "@/lib/format";

import { conferenciasQueNaoBatem } from "../qualidade-da-leitura";
import type { Extracao } from "../schemas-de-documento";
import { textos } from "../textos";
import { rotuloDoCampoDoCabecalho } from "../vocabulario-de-documento";

/**
 * **O que o papel diz contra o que o QR diz.**
 *
 * O QR de uma fatura portuguesa é gerado por software certificado; o "papel" é o
 * que um modelo leu de uma fotografia. Quando os dois discordam **ganha o QR**, e
 * o valor que o cabeçalho acima mostra já é o dele. As `divergences` não são uma
 * lista de coisas por decidir: são a **prova** de que ele ganhou, e lêem-se
 * exactamente assim — *"o papel diz X, o QR diz Y"*.
 *
 * ## O que acontece sem QR, e porque é uma linha e não silêncio
 *
 * `qr_read: false` é o caso **normal** — a maioria dos documentos não vai ter um
 * QR legível, e isso não é um problema deste documento nem desta leitura. Logo
 * não há painel vazio e não há alarme: há **uma linha discreta**, em
 * `text-muted-foreground`, sem ícone, sem tinta e sem borda.
 *
 * E é uma linha em vez de silêncio por uma razão concreta: sem ela, um cabeçalho
 * certificado e um cabeçalho adivinhado de uma fotografia tremida são
 * **indistinguíveis** no ecrã. Quem está a decidir se confia no NIF e no total
 * antes de dar entrada a mercadoria precisa de saber qual dos dois está a ver, e
 * essa diferença não aparece em mais lado nenhum do painel. O custo de a dizer é
 * uma linha de 13px; o custo de a calar é alguém confiar num número por engano.
 *
 * ## A hierarquia de ênfase deste painel, de cima para baixo
 *
 * Três níveis, e são três por decisão e não por acaso:
 *
 *  1. **`cancelled`** — o `E=A` do QR diz que o emissor anulou o documento.
 *     `danger`, com a palavra: um documento anulado não dá entrada a nada e o
 *     servidor recusa a receção com esse código. É o único ramo deste painel que
 *     é uma recusa e não uma leitura;
 *  2. **`vat_checks` com `matches: false`** — a soma das linhas lidas numa taxa
 *     não bate com a base dessa taxa no QR. A ADR 0031 chama-lhe *"o sinal mais
 *     forte que esta feature produz sobre a qualidade de uma leitura — mais
 *     forte do que a `confidence`"*, e é por isso que tem **mais peso visual do
 *     que o marcador de confiança baixa**: aquele é um trilho de 4px e uma
 *     palavra dentro de uma célula, este é um bloco com tinta própria, a taxa, as
 *     duas bases e a diferença ao cêntimo. A diferença de peso é de forma
 *     **e** de cor: a confiança é a opinião de um modelo sobre si próprio
 *     (`warning`), isto é aritmética contra um número certificado (`danger`);
 *  3. **`divergences`** — campos em que o papel e o QR não coincidem. Informação
 *     e não aviso: o valor certo já está a ser mostrado, logo não há nada a
 *     corrigir. Fica em texto, sem tinta de estado.
 *
 * A cor nunca comunica sozinha em nenhum dos três (DESIGN.md §3): cada bloco
 * leva a palavra ao lado, e lê-se igual a preto e branco.
 *
 * ## E a quem não vê euros, o segundo bloco **continua a existir**
 *
 * As três bases da conferência são dinheiro e saem por ausência (ADR 0031,
 * adenda dos euros); a taxa e o veredicto não, e ficam. É a divisão que faz este
 * painel degradar em vez de rebentar: a linha passa a dizer *"IVA 23 % — não
 * bate"*, sem um único valor. Esconder o bloco inteiro era tirar a quem recebe o
 * sinal mais forte que esta feature produz — e quem recebe tem a fatura em papel
 * na mão, que é onde os números estão.
 */
export function PainelDoQr({ extracao }: { readonly extracao: Extracao }) {
  if (!extracao.qr_read) {
    return (
      <p className="max-w-prose text-pretty border-t border-border px-celula-x py-3 text-xs text-muted-foreground">
        {textos.documento.qr.semQr}
      </p>
    );
  }

  const naoBatem = conferenciasQueNaoBatem(extracao);

  return (
    <div className="flex flex-col gap-3 border-t border-border px-celula-x py-3">
      <h3 className={CLASSE_MICROROTULO}>{textos.documento.qr.titulo}</h3>

      <p className="max-w-prose text-pretty text-sm text-muted-foreground">
        {textos.documento.qr.oQrGanha}
      </p>

      {/* O ATCUD e o espaço fiscal: o que só o QR traz, e que o papel quase
          nunca dá a ler. Mono, porque são códigos. */}
      {extracao.atcud === "" && extracao.fiscal_space === "" ? null : (
        <dl className="flex min-w-0 flex-wrap gap-x-8 gap-y-2">
          {extracao.atcud === "" ? null : (
            <div className="flex flex-col gap-0.5">
              <dt className={CLASSE_MICROROTULO}>{textos.documento.qr.atcud}</dt>
              <dd data-numeric className="text-left text-sm break-all">
                {extracao.atcud}
              </dd>
            </div>
          )}
          {extracao.fiscal_space === "" ? null : (
            <div className="flex flex-col gap-0.5">
              <dt className={CLASSE_MICROROTULO}>{textos.documento.qr.espacoFiscal}</dt>
              <dd data-numeric className="text-left text-sm">
                {extracao.fiscal_space}
              </dd>
            </div>
          )}
        </dl>
      )}

      {/* 1. Anulado pelo emissor. O bloco mais forte do painel, e o único que
             fala de uma recusa em vez de uma leitura. */}
      {extracao.cancelled ? (
        <p className="flex items-start gap-2 border border-danger-border bg-danger-surface px-celula-x py-2 text-sm">
          <CircleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-danger" />
          <span className="text-pretty">
            <span className="font-semibold">{textos.documento.qr.anuladoTitulo}</span>
            {" — "}
            {textos.documento.qr.anuladoCorpo}
          </span>
        </p>
      ) : null}

      {/* 2. O IVA que não bate. Mais peso do que o marcador de confiança, por
             forma e por cor — a razão está no cabeçalho deste ficheiro. */}
      {naoBatem.length === 0 ? null : (
        <div className="flex flex-col gap-1.5 border border-danger-border bg-danger-surface px-celula-x py-2">
          <p className="flex items-start gap-2 text-sm">
            <CircleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-danger" />
            <span className="text-pretty">
              <span className="font-semibold">{textos.documento.qr.ivaNaoBateTitulo}</span>
              {" — "}
              {textos.documento.qr.ivaNaoBateCorpo}
            </span>
          </p>
          <ul className="flex flex-col gap-1">
            {naoBatem.map((conferencia) => (
              <li
                key={conferencia.rate}
                className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 text-sm"
              >
                {/* **Pontos e não fracção**, e isto foi apanhado numa
                    fotografia: com o `formatRate` a linha dizia "IVA 2300 %". A
                    taxa deste módulo viaja em **percentagem impressa** —
                    `TAXAS_POR_ESPACO` do QR são 6, 13 e 23, e o prompt da
                    extração pede `6.000` e nunca `0.06` —, logo é a mesma
                    convenção da coluna IVA da tabela ao lado. */}
                <span className="font-medium">
                  {textos.documento.qr.taxa(formatPercentPoints(Number(conferencia.rate)))}
                </span>
                {/* **O veredicto sobrevive à ausência dos valores, e é esse o
                    ponto deste bloco.** Quem não vê euros não recebe as três
                    bases (`euros-do-papel.ts`) — mas a `rate` e o `matches`
                    continuam a vir, de propósito: um `matches: false` é *"o
                    sinal mais forte que esta feature produz sobre a qualidade de
                    uma leitura"* (ADR 0031), e é marcação qualitativa, que é
                    exactamente o trabalho de quem recebe. Logo a linha diz "IVA
                    23 % — não bate" e cala os números, em vez de desaparecer: o
                    colaborador continua a saber que as contas não fecham, e vai
                    buscar o papel.

                    Em `font-semibold` e não em `text-danger`: isto já está
                    dentro de um bloco com a tinta `danger-surface`, e o DESIGN.md
                    §2 manda o texto por cima de uma tinta de estado ser o
                    `foreground` — a cor de estado sobre a própria tinta não tem
                    contraste. O peso é o que dá ênfase; o aviso já está dito no
                    título do bloco, acima. */}
                {conferencia.lines_base === undefined ? (
                  <span className="font-semibold">{textos.documento.qr.naoBate}</span>
                ) : (
                  <>
                    <span className="text-muted-foreground">
                      {textos.documento.qr.somaDasLinhas}
                    </span>
                    <span data-numeric>{formatMoney(conferencia.lines_base)}</span>
                    <span className="text-muted-foreground">{textos.documento.qr.baseDoQr}</span>
                    <span data-numeric>
                      {conferencia.qr_base === null || conferencia.qr_base === undefined
                        ? "—"
                        : formatMoney(conferencia.qr_base)}
                    </span>
                    {conferencia.difference === null ||
                    conferencia.difference === undefined ? null : (
                      <>
                        <span className="text-muted-foreground">
                          {textos.documento.qr.diferenca}
                        </span>
                        <span data-numeric className="font-semibold text-danger">
                          {formatMoney(conferencia.difference)}
                        </span>
                      </>
                    )}
                  </>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* 3. As divergências de cabeçalho. Informação, não aviso: o valor certo
             já é o que está lá em cima. */}
      {extracao.divergences.length === 0 ? null : (
        <div className="flex flex-col gap-1">
          <h4 className={CLASSE_MICROROTULO}>{textos.documento.qr.divergenciasTitulo}</h4>
          <ul className="flex flex-col gap-1">
            {extracao.divergences.map((divergencia) => (
              <li
                key={divergencia.field}
                className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 text-sm"
              >
                <span className="font-medium">
                  {rotuloDoCampoDoCabecalho(divergencia.field)}
                </span>
                <span className="text-muted-foreground">{textos.documento.qr.oPapelDiz}</span>
                {/* `break-all` e não `truncate`: um NIF ou um número de
                    documento mal lido tem de ser legível por inteiro, senão a
                    comparação que esta linha existe para permitir não se faz.
                    É texto de uma fatura — entrada não confiável — e entra como
                    nó de texto, nunca como HTML. */}
                <span data-numeric className="break-all">
                  {divergencia.paper}
                </span>
                <span className="text-muted-foreground">{textos.documento.qr.oQrDiz}</span>
                <span data-numeric className="font-semibold break-all">
                  {divergencia.qr}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
