import { Link } from "@tanstack/react-router";

import { ErroAoCarregar } from "@/components/erro-ao-carregar";
import {
  CLASSE_CONTADOR,
  CLASSE_CONTADOR_ATIVO,
  CLASSE_CONTADOR_TOCAVEL,
  CorpoDoContador,
  ReguaDeContadores,
} from "@/components/regua-de-contadores";
import { Skeleton } from "@/components/ui/skeleton";
import { formatMoneyRounded } from "@/lib/format";

import type { ResumoDeStock } from "../schemas";

/**
 * Os três números do topo do Stock: artigos em falta · a expirar dentro do
 * horizonte · valor de stock em euros.
 *
 * **Dois são filtros e o terceiro é uma leitura.** Os dois primeiros são
 * `<Link>`s que põem o filtro no URL — logo recarregar a página, voltar atrás e
 * mostrar o link a alguém dão o mesmo ecrã, e o Cmd+clique abre noutro
 * separador. O valor em euros não é tocável porque não há destino honesto para
 * ele neste shell: o que lá estaria — valor por artigo, CMP, margem — é precisão
 * falsa em euros, proibida pelo guião §4.
 *
 * **O limiar de dias vem do servidor e está à vista**, não num painel de
 * configurações: é assim que o dono o contesta em voz alta ("três dias é pouco")
 * em vez de o ir mudar sozinho (guião §4, proibição 7). Mudou de sítio a
 * 2026-10-06 — era parte do rótulo ("a expirar ≤ 3 dias") e passou a ser a nota
 * por baixo da figura. A razão é de forma e não de conteúdo: um microrótulo em
 * caixa alta com 24 caracteres parte em duas linhas e desalinha a régua toda.
 * Continua no ecrã, continua a ser do servidor, e lê-se melhor onde está.
 *
 * O número em euros é arredondado ao euro. Um cêntimo num total calculado a
 * partir de custos médios é precisão que não existe, e convida a discutir o
 * cêntimo em vez do desperdício.
 */
export type FiltroDeStock = "falta" | "validade" | undefined;

export function EsqueletoDosNumeros() {
  return (
    // O aviso de "a carregar" é **um**, no contentor: medido numa renderização,
    // um por campo dava três anúncios iguais a quem ouve o ecrã.
    <ReguaDeContadores aria-busy="true" rotulo="A carregar os números…">
      {[0, 1, 2].map((indice) => (
        <div key={indice} className={CLASSE_CONTADOR}>
          <Skeleton className="h-3 w-20" />
          <Skeleton className="h-8 w-16" />
        </div>
      ))}
    </ReguaDeContadores>
  );
}

export function ErroDosNumeros({ aoTentarOutraVez }: { readonly aoTentarOutraVez: () => void }) {
  return (
    <div className="border-b border-border px-celula-x py-3">
      <ErroAoCarregar
        titulo="Não foi possível contar os artigos em falta"
        mensagem="A tabela abaixo continua a funcionar. Os três números voltam à segunda tentativa."
        aoTentarOutraVez={aoTentarOutraVez}
      />
    </div>
  );
}

/** Um campo da régua que também é filtro. */
function ContadorDeFiltro({
  figura,
  campo,
  nota,
  titulo,
  ativo,
  filtro,
}: {
  readonly figura: string;
  readonly campo: string;
  readonly nota?: string;
  readonly titulo: string;
  readonly ativo: boolean;
  readonly filtro: "falta" | "validade";
}) {
  return (
    <Link
      to="/stock"
      // O reducer recebe os filtros actuais já validados pela rota: tocar
      // segunda vez no mesmo campo limpa o filtro do URL em vez de o deixar lá.
      search={(anteriores) => ({ ...anteriores, filtro: ativo ? undefined : filtro })}
      title={titulo}
      // Sem `aria-current` à mão: medido, o `<Link>` põe `aria-current="page"`
      // no campo certo (compara também a search params) e sobrepõe-se a
      // qualquer valor nosso. O `ativo` fica para a tinta e para saber que um
      // segundo toque **limpa** o filtro.
      className={`${CLASSE_CONTADOR} ${CLASSE_CONTADOR_TOCAVEL} ${ativo ? CLASSE_CONTADOR_ATIVO : ""}`}
    >
      <CorpoDoContador campo={campo} figura={figura} ativo={ativo} {...(nota === undefined ? {} : { nota })} />
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
    <ReguaDeContadores>
      <ContadorDeFiltro
        figura={String(resumo.below_min_count)}
        campo="em falta"
        nota="abaixo do mínimo"
        titulo="Artigos abaixo do mínimo de stock"
        ativo={filtroAtivo === "falta"}
        filtro="falta"
      />
      <ContadorDeFiltro
        figura={String(resumo.expiring_count)}
        campo="a expirar"
        nota={`dentro de ${String(dias)} dias`}
        titulo={`Artigos com validade dentro de ${String(dias)} dias — o limiar é do servidor`}
        ativo={filtroAtivo === "validade"}
        filtro="validade"
      />
      {/* Leitura, não filtro: um `<div>` sem `onClick` e sem `hover`, para não
          prometer um toque que não existe. */}
      <div className={CLASSE_CONTADOR}>
        <CorpoDoContador campo="valor de stock" figura={formatMoneyRounded(resumo.stock_value_eur)} />
      </div>
    </ReguaDeContadores>
  );
}
