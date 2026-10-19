import { ErroAoCarregar } from "@/components/erro-ao-carregar";
import {
  CLASSE_CONTADOR,
  CorpoDoContador,
  ReguaDeContadores,
} from "@/components/regua-de-contadores";
import { Skeleton } from "@/components/ui/skeleton";
import { formatMoneyRounded, formatPercentPoints } from "@/lib/format";

import type { ResumoDoPeriodo } from "../schemas";
import { textos } from "../textos";
import { notaDaBaseDaReceita } from "../vocabulario";

/**
 * Os números do topo do painel — **uma régua de campos, não uma grelha de
 * cartões** (DESIGN.md §3, e o `components/regua-de-contadores.tsx` tem a razão
 * inteira: três cartões iguais com um número grande são o tell de painel gerado
 * que o §5 proíbe quase pela letra).
 *
 * São **três** e não os quatro da identidade, e a escolha é para não dizer o
 * mesmo número duas vezes: vendas, compras, consumo e variação são as quatro
 * linhas do bloco do dinheiro, que é onde elas têm de estar juntas para a conta
 * fechar à vista. Aqui ficam os três números que não são linhas dessa conta:
 *
 *  - **vendas com IVA**, que é o número que o dono compara com o fecho de
 *    caixa. Mostrar-lhe um líquido onde ele espera um bruto é perder a
 *    confiança por 13% sem nenhum erro de cálculo (ADR 0013, decisão 5);
 *  - **o rácio de mercadoria**, que é o número que a restauração usa e compara
 *    ("a mercadoria está nos 31%"). É accionável, não se confunde com lucro e
 *    não revela nada sobre salários — é por isso que ele existe no lugar do
 *    `goods_margin_eur` que a ADR revogou;
 *  - **o valor de stock**, que é o que está na despensa agora.
 *
 * ## O rácio não se renderiza sem consumo registado
 *
 * É a regra mais importante deste componente e vem da decisão 7: sem consumo
 * registado o painel mostraria 85% de margem, e **um painel optimista por
 * omissão destrói a confiança mais depressa do que um prejuízo falso** — o
 * prejuízo falso faz perguntar, o lucro falso faz acreditar. Por isso o campo
 * desaparece em vez de mostrar um número bonito, e quem diz o que falta
 * registar é o bloco de qualidade de dados, que não é opcional.
 *
 * A régua aguenta dois campos num ecrã e quatro noutro sem reconfigurar uma
 * grelha — os campos empacotam à esquerda e não esticam —, e é por isso que
 * esconder um não deixa um buraco.
 */
export function NumerosDoPeriodo({ resumo }: { readonly resumo: ResumoDoPeriodo }) {
  const { data_quality: qualidade } = resumo;
  const vendas = resumo.revenue_gross_eur;
  const base = resumo.revenue_basis;
  // Duas condições e não uma: o contrato pode mandar o rácio a `null` só porque
  // as vendas foram zero (um domingo fechado), e isso é outra coisa de "não há
  // consumo registado" — mas as duas levam ao mesmo sítio, que é não mostrar
  // um rácio que não existe.
  const comRacio = qualidade.consumption_registered && resumo.goods_cost_ratio_pct !== null;

  return (
    <ReguaDeContadores>
      {/* **Um campo a `null` sai da régua; não fica a traço.** Um "—" de 2rem em
          mono é um número ilegível com o peso de um número, e um `0 €` era uma
          afirmação falsa sobre o negócio (ADR 0029, decisão 1). A régua empacota
          à esquerda e não estica, logo esconder um campo não deixa buraco.

          A frase que diz o que falta **não** se repete aqui: ela é a primeira
          linha da tabela que vem logo a seguir, que é onde "Vendas, sem IVA" se
          procura. Dizê-la duas vezes a 40px de distância era o manual de
          instruções que o dono do produto já recusou uma vez. */}
      {vendas === null || base === null ? null : (
        <div className={CLASSE_CONTADOR}>
          {/* `campo="vendas"` e não "vendas nos últimos 7 dias": um microrótulo
              em caixa alta com 25 caracteres fazia este campo crescer para
              ~330px, e os campos da régua empacotam à esquerda sem esticar — o
              primeiro passava a ocupar um terço da faixa. A janela está dita
              duas vezes na barra logo acima (o período activo e a fronteira
              ecoada), e um microrótulo é um **nome de campo**, como o `<th>` da
              tabela que vem a seguir: um `<th>` não repete o filtro. */}
          <CorpoDoContador
            campo={textos.contadores.vendas}
            figura={formatMoneyRounded(vendas)}
            nota={notaDaBaseDaReceita(base)}
          />
        </div>
      )}

      {comRacio ? (
        <div className={CLASSE_CONTADOR}>
          <CorpoDoContador
            campo={textos.contadores.mercadoria}
            figura={formatPercentPoints(Number(resumo.goods_cost_ratio_pct))}
            nota={textos.contadores.doQueSeVendeu}
          />
        </div>
      ) : null}

      <div className={CLASSE_CONTADOR}>
        <CorpoDoContador
          campo={textos.contadores.valorDeStock}
          figura={formatMoneyRounded(resumo.stock_value_eur)}
          nota={textos.contadores.aoCustoGravado}
        />
      </div>
    </ReguaDeContadores>
  );
}

/** Pendente: um aviso só, no contentor, para quem ouve o ecrã. */
export function EsqueletoDosNumeros() {
  return (
    <ReguaDeContadores aria-busy="true" rotulo={textos.contadores.aCarregar}>
      {[0, 1, 2].map((indice) => (
        <div key={indice} className={CLASSE_CONTADOR}>
          <Skeleton className="h-3 w-24" />
          <Skeleton className="h-8 w-28" />
          <Skeleton className="h-3 w-32" />
        </div>
      ))}
    </ReguaDeContadores>
  );
}

export function ErroDosNumeros({
  mensagem,
  aoTentarOutraVez,
}: {
  readonly mensagem: string;
  readonly aoTentarOutraVez: () => void;
}) {
  return (
    <div className="border-b border-border px-celula-x py-3">
      <ErroAoCarregar
        titulo={textos.contadores.erroDoPeriodo}
        mensagem={mensagem}
        aoTentarOutraVez={aoTentarOutraVez}
      />
    </div>
  );
}
