import {
  CLASSE_CELULA,
  CLASSE_LINHA,
  EsqueletoDeTabela,
  MolduraDeTabela,
  type ColunaDeTabela,
} from "@/components/tabela";
import { formatMoney, formatUnitMoney } from "@/lib/format";

import { EstadoDoCustoDaFicha } from "./estado-do-custo";
import { linhasMostramEuros } from "../euros-da-ficha";
import type { LinhaDaReceita } from "../schemas";
import { textos } from "../textos";
import { textoDeQuantidade } from "../vocabulario";

/**
 * Os ingredientes de uma ficha, com as **duas** quantidades.
 *
 * ## Porque são duas colunas e não uma
 *
 * `quantity` é o que a ficha escreve, **por fornada**; `quantity_real` é
 * `quantity ÷ yield_factor`, o que de facto sai do stock. São números diferentes
 * e a confusão entre eles é o erro clássico do rendimento — a ADR 0035 manda os
 * dois no payload exactamente para o cliente não ter de escolher um e não ter de
 * calcular o outro. Com `yield_factor = 1`, que é o caso normal (decisão 8), as
 * duas colunas são iguais — e isso **também** é informação: diz que nada se
 * perde pelo caminho. Uma coluna que aparecesse só às vezes era pior: o leitor
 * deixava de saber qual das duas estava a ler.
 *
 * **Nada se divide aqui.** Nem por `batch_size`, nem por `yield_factor`, nem
 * pelo `display_factor`: converter unidades no cliente é a fonte nº 1 de bugs de
 * stock (`inventory-domain` §2), e a aritmética do servidor tem a divisão no fim
 * — uma conta refeita aqui daria outro número.
 *
 * ## As duas colunas de euros saem pela **decisão das linhas**, não pela da ficha
 *
 * São dois serializers e dois `CAMPOS_DE_DINHEIRO`, e a ADR 0035 (decisão 6)
 * proíbe a subclasse de os redeclarar precisamente porque é essa a porta irmã
 * por onde o dinheiro já saiu duas vezes nesta casa. O ecrã lê as duas decisões
 * em separado: a régua pergunta à ficha, esta tabela pergunta às linhas.
 */

/** Seis colunas, cabem a 1280px. A 360px a tabela desliza, e o §4 declara-o. */
const LARGURA_MINIMA = "min-w-4xl";

function colunasDe(comEuros: boolean): readonly ColunaDeTabela[] {
  return [
    { chave: "ingrediente", rotulo: textos.colunas.ingrediente },
    { chave: "porFornada", rotulo: textos.colunas.porFornada, classe: "w-36 text-right" },
    { chave: "saiDoStock", rotulo: textos.colunas.saiDoStock, classe: "w-36 text-right" },
    ...(comEuros
      ? [
          {
            chave: "custoDoArtigo",
            rotulo: textos.colunas.custoDoIngrediente,
            classe: "w-40 text-right",
          },
          {
            chave: "custoDaLinha",
            rotulo: textos.colunas.custoDaLinha,
            classe: "w-36 text-right",
          },
        ]
      : []),
    { chave: "certeza", rotulo: textos.colunas.certeza, classe: "w-28" },
  ];
}

/** O mesmo traço da lista, pela mesma razão: `null` é *não sabemos*. */
function Euro({
  valor,
  formatar,
}: {
  readonly valor: string | null | undefined;
  readonly formatar: (valor: string) => string;
}) {
  if (valor === undefined) return null;
  if (valor === null) {
    return <span className="text-muted-foreground">{textos.custo.semValor}</span>;
  }
  return <>{formatar(valor)}</>;
}

function LinhaDeIngrediente({
  linha,
  comEuros,
}: {
  readonly linha: LinhaDaReceita;
  readonly comEuros: boolean;
}) {
  return (
    <tr className={`${CLASSE_LINHA} transition-colors hover:bg-surface-2`}>
      <th scope="row" className={`${CLASSE_CELULA} max-w-0 text-left font-medium`}>
        <span className="flex items-baseline gap-2">
          <span className="min-w-0 truncate">{linha.short_name}</span>
          {/* Um artigo arquivado **dentro** de uma ficha activa aceita-se, e
              assinala-se: arquivar um artigo não pode partir uma ficha que já o
              continha, e quem recusa é a produção (fatia B), onde a decisão tem
              consequência no ledger. */}
          {linha.ingredient_is_active ? null : (
            <span className="shrink-0 text-xs text-warning">
              {textos.ficha.artigoArquivado}
            </span>
          )}
        </span>
      </th>

      <td data-numeric className={`${CLASSE_CELULA} text-right`}>
        {textoDeQuantidade(linha.quantity)}
      </td>

      {/* O que sai do stock, em `muted-foreground`: é a consequência do
          rendimento e não um segundo número com o mesmo peso. A frase por baixo
          da tabela explica a coluna. */}
      <td data-numeric className={`${CLASSE_CELULA} text-right text-muted-foreground`}>
        {textoDeQuantidade(linha.quantity_real)}
      </td>

      {comEuros ? (
        <>
          {/* O custo do artigo é por unidade **base** — a mesma definição do
              `/stock/levels`, pela mesma função do servidor (decisão 3): o dono
              que compare a ficha com o Stock vê o mesmo número. Daí a unidade
              escrita ao lado. */}
          <td data-numeric className={`${CLASSE_CELULA} text-right text-muted-foreground`}>
            <Euro
              valor={linha.unit_cost}
              formatar={(valor) => `${formatUnitMoney(valor)}/${linha.quantity.base_unit}`}
            />
          </td>
          <td data-numeric className={`${CLASSE_CELULA} text-right`}>
            <Euro valor={linha.line_cost} formatar={formatMoney} />
          </td>
        </>
      ) : null}

      <td className={CLASSE_CELULA}>
        <EstadoDoCustoDaFicha estado={linha.cost_status} />
      </td>
    </tr>
  );
}

export function TabelaDeIngredientes({
  linhas,
}: {
  readonly linhas: readonly LinhaDaReceita[];
}) {
  const comEuros = linhasMostramEuros(linhas);

  return (
    <MolduraDeTabela
      colunas={colunasDe(comEuros)}
      larguraMinima={LARGURA_MINIMA}
      rotulo={textos.ficha.tabela}
    >
      <tbody>
        {linhas.map((linha) => (
          <LinhaDeIngrediente key={linha.ingredient} linha={linha} comEuros={comEuros} />
        ))}
      </tbody>
    </MolduraDeTabela>
  );
}

/** O pendente, com as **mesmas** colunas e a mesma largura mínima. */
export function EsqueletoDaTabelaDeIngredientes() {
  return (
    <EsqueletoDeTabela
      colunas={colunasDe(false)}
      larguraMinima={LARGURA_MINIMA}
      rotulo={textos.accoes.aCarregarFicha}
      linhas={5}
    />
  );
}
