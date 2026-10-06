import { Link } from "@tanstack/react-router";
import type { ReactNode } from "react";

import { formatDate, formatDaysAway, formatMoney } from "@/lib/format";

import { eZero, type QualidadeDosDados } from "../schemas";
import { rotuloDaOrigemDaReceita } from "../vocabulario";

/**
 * **O painel declara o que não sabe**, e a declaração é parte do contrato (ADR
 * 0013, decisão 7). Este bloco não é opcional e não se esconde quando está tudo
 * bem: é a leitura do `DataQualityOut`, que viaja nas três respostas.
 *
 * A razão é a mais forte de toda a ADR: como o `sales` v1 não escreve no
 * ledger, pode não existir consumo registado nenhum — e aí o painel mostraria
 * 85% de margem. **Um painel optimista por omissão destrói a confiança mais
 * depressa do que um prejuízo falso**, porque o prejuízo falso faz perguntar e
 * o lucro falso faz acreditar.
 *
 * ## Quatro linhas, e cada uma tem uma consequência escrita
 *
 * Não é uma lista de estados: é uma lista de **consequências**. "Sem consumo
 * registado" sozinho não diz nada a quem está a olhar; "sem consumo registado,
 * logo o rácio de mercadoria não aparece" diz o que falta e o que isso custa.
 * Quando há uma acção, ela é um link para o ecrã que a faz — um aviso sem saída
 * é um beco, que é a mesma regra do estado vazio.
 *
 * ## Não é um banner de alerta, e isso é deliberado
 *
 * Estas linhas usam a cor de estado como **cor de texto** (o primeiro dos três
 * papéis do DESIGN.md §2) e a palavra diz sempre o mesmo que a cor. Um banner
 * com tinta e borda por cada aviso dava quatro cartões coloridos no meio de um
 * painel escuro — o §5 quase pela letra — e, pior, dava ao "está tudo
 * registado" o mesmo peso visual que ao "ninguém contou há três meses".
 */

function Declaracao({
  campo,
  valor,
  consequencia,
  tinta = "",
}: {
  readonly campo: string;
  readonly valor: string;
  readonly consequencia: ReactNode;
  readonly tinta?: string;
}) {
  return (
    <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 border-t border-border px-celula-x py-3 first:border-t-0">
      <span className="w-full shrink-0 text-xs font-bold tracking-microrotulo text-muted-foreground uppercase sm:w-56">
        {campo}
      </span>
      {/* `text-left` explícito: o `[data-numeric]` do `base.css` alinha à
          direita, que é o certo numa célula de tabela e o errado numa linha de
          leitura — aqui o valor vem logo depois do rótulo. */}
      <span data-numeric className={`shrink-0 text-left text-sm ${tinta}`}>
        {valor}
      </span>
      <span className="min-w-0 flex-1 text-sm text-muted-foreground">{consequencia}</span>
    </div>
  );
}

/** Quantos dias faz hoje que isto aconteceu. Dias, não dinheiro. */
function diasDesde(instante: string): number {
  const umDia = 24 * 60 * 60 * 1000;
  return Math.round((new Date(instante).getTime() - Date.now()) / umDia);
}

export function QualidadeDosDadosDoPainel({
  qualidade,
}: {
  readonly qualidade: QualidadeDosDados;
}) {
  const semFatura = !eZero(qualidade.purchases_awaiting_invoice_eur);

  return (
    <div className="flex flex-col">
      <Declaracao
        campo="consumo registado"
        valor={qualidade.consumption_registered ? "sim" : "não"}
        tinta={qualidade.consumption_registered ? "" : "text-warning"}
        consequencia={
          qualidade.consumption_registered ? (
            "A mercadoria consumida vem do ledger, ao custo gravado em cada movimento."
          ) : (
            <>
              Sem consumo no ledger não há mercadoria consumida nem rácio de mercadoria — e sem eles
              este painel mostraria uma margem que não existe.{" "}
              <Link
                to="/contar"
                className="text-primary underline underline-offset-4 hover:no-underline"
              >
                Registar o que saiu
              </Link>
              .
            </>
          )
        }
      />

      <Declaracao
        campo="mercadoria sem fatura"
        valor={formatMoney(qualidade.purchases_awaiting_invoice_eur)}
        tinta={semFatura ? "text-warning" : ""}
        consequencia={
          semFatura ? (
            <>
              Entrou por guia de remessa e está valorizada ao último preço conhecido; a diferença
              aparece quando a fatura chegar.{" "}
              <Link
                to="/receber"
                className="text-primary underline underline-offset-4 hover:no-underline"
              >
                Ver as receções
              </Link>
              .
            </>
          ) : (
            "Toda a mercadoria deste período tem fatura: as compras estão ao preço certo."
          )
        }
      />

      <Declaracao
        campo="última contagem"
        valor={
          qualidade.last_count_at === null ? "nunca" : formatDate(qualidade.last_count_at)
        }
        tinta={qualidade.last_count_at === null ? "text-warning" : ""}
        consequencia={
          qualidade.last_count_at === null ? (
            <>
              Sem nenhuma contagem, a quebra desconhecida é zero por falta de medida e não por falta
              de quebra.{" "}
              <Link
                to="/contar"
                className="text-primary underline underline-offset-4 hover:no-underline"
              >
                Contar agora
              </Link>
              .
            </>
          ) : (
            `Contou-se ${formatDaysAway(diasDesde(qualidade.last_count_at))}. A quebra desconhecida só mede o que foi contado até aí.`
          )
        }
      />

      <Declaracao
        campo="origem das vendas"
        valor={qualidade.revenue_source === "none" ? "nenhuma" : qualidade.revenue_source === "pos" ? "POS" : "à mão"}
        tinta={qualidade.revenue_source === "none" ? "text-warning" : ""}
        consequencia={`${rotuloDaOrigemDaReceita(qualidade.revenue_source)}. Os rácios são sobre vendas sem IVA; o valor com IVA é o do fecho de caixa.`}
      />
    </div>
  );
}
