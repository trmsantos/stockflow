import { Link } from "@tanstack/react-router";

import {
  CLASSE_CELULA,
  CLASSE_LINHA,
  EsqueletoDeTabela,
  MolduraDeTabela,
  TrilhoDaLinha,
  type ColunaDeTabela,
} from "@/components/tabela";
import { formatMoney, formatUnitMoney } from "@/lib/format";

import { EstadoDoCustoDaFicha } from "./estado-do-custo";
import { fichaMostraEuros } from "../euros-da-ficha";
import type { ReceitaResumo } from "../schemas";
import { textos } from "../textos";
import { tintaDoTrilhoDoCusto } from "../tinta-do-custo";
import { textoDeQuantidade } from "../vocabulario";

/**
 * A lista de fichas técnicas como **tabela densa**, à largura toda — a forma dos
 * ecrãs de lista desta casa (DESIGN.md §3 e §4), com a moldura, as réguas e o
 * trilho de sinal do `components/tabela.tsx`.
 *
 * ## As colunas de euros existem ou não existem, e não ficam vazias
 *
 * O `staff` não recebe `batch_cost`, `unit_cost` nem `display_cost`: as chaves
 * ficam **ausentes** do JSON. A reacção certa é a coluna **desaparecer** — uma
 * coluna "Ingredientes/fornada" cheia de traços é uma pergunta sem resposta a
 * cada linha, e um traço quer dizer outra coisa (*não sabemos*, o degrau 5 da
 * escada do custo). Por isso as colunas vêm de uma função do payload
 * (`fichaMostraEuros`) e não do papel da sessão, pelo argumento inteiro do
 * `euros-da-ficha.ts`.
 *
 * O que fica para os três papéis é o que importa a quem produz: o acabado, a
 * **fornada**, quantos ingredientes tem e a **certeza** do custo — a palavra,
 * que não é euro.
 *
 * ## O trilho marca uma coisa só: a ficha que não responde
 *
 * `desconhecido` é o único estado em que a pergunta deste ecrã — *quanto me
 * custa de ingredientes?* — fica sem resposta, e é a linha que se tem de ver de
 * dois metros sem a ler. `estimado` **não** leva trilho: é informação e não
 * avaria, e num dia sem produções seriam todas (ver `tinta-do-custo.ts`).
 *
 * ## A linha não é um link; o nome é
 *
 * Numa `<table>` não se envolve um `<tr>` num `<a>`, e o `<a>` esticado com
 * `absolute inset-0` rouba a selecção de texto a todas as outras células — numa
 * tabela de custos isso é uma perda real, porque quem tem o rato em cima de
 * "14,20 €" quer copiar o número. Fica o nome como link, e o `group-hover`
 * devolve a descoberta.
 */

/**
 * `min-w-4xl` (56rem) impede as seis colunas de se esmagarem. A 1280px a área de
 * conteúdo tem ~1024px, logo não há scroll em desktop; a 360px há, e o
 * DESIGN.md §4 declara-o — Receitas não é rota de campo (uma ficha escreve-se
 * sentado; o que se anda com o telemóvel na mão é contar e receber).
 */
const LARGURA_MINIMA = "min-w-4xl";

/**
 * As colunas, com largura explícita em tudo o que tem largura previsível.
 *
 * O layout automático de uma tabela dá espaço a quem tem o conteúdo mais largo,
 * e numa coluna numérica o conteúdo mais largo é o **cabeçalho**:
 * "INGREDIENTES/FORNADA" em caixa alta com tracking de 0.08em é muito mais
 * largo do que "14,20 €". Sem as larguras, as quatro colunas da direita comiam
 * a do acabado, que é a única cujo conteúdo é um nome a sério.
 */
function colunasDe(comEuros: boolean): readonly ColunaDeTabela[] {
  return [
    { chave: "acabado", rotulo: textos.colunas.acabado },
    { chave: "fornada", rotulo: textos.colunas.fornada, classe: "w-36 text-right" },
    { chave: "ingredientes", rotulo: textos.colunas.ingredientes, classe: "w-28 text-right" },
    ...(comEuros
      ? [
          {
            chave: "custoDaFornada",
            rotulo: textos.colunas.custoDaFornada,
            classe: "w-40 text-right",
          },
          {
            chave: "custoUnitario",
            rotulo: textos.colunas.custoUnitario,
            classe: "w-44 text-right",
          },
        ]
      : []),
    { chave: "certeza", rotulo: textos.colunas.certeza, classe: "w-28" },
  ];
}

/**
 * Um euro da ficha: o número, o traço, ou **nada**.
 *
 * Os três casos são os três factos, e é aqui que eles não se colapsam:
 *
 *  - **um número** — o custo;
 *  - **`null`** — *não sabemos* (degrau 5 da escada): imprime "—", e a palavra
 *    da coluna da certeza diz porquê ao lado;
 *  - **ausente** — *não te compete*: célula vazia. Em princípio inalcançável,
 *    porque quem decide a coluna é o `colunasDe` e a decisão é por página; se
 *    uma resposta vier misturada, uma célula vazia continua a ser verdade e um
 *    traço já não seria.
 *
 * O formatador entra por propriedade e não o texto já formatado: um total de
 * fornada lê-se ao cêntimo (`formatMoney`) e um custo por unidade precisa das
 * casas significativas (`formatUnitMoney`), e formatar antes de saber se há
 * número era formatar um zero para o deitar fora.
 */
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

function LinhaDeReceita({
  receita,
  comEuros,
}: {
  readonly receita: ReceitaResumo;
  readonly comEuros: boolean;
}) {
  return (
    <tr className={`group ${CLASSE_LINHA} transition-colors hover:bg-surface-2`}>
      <TrilhoDaLinha tinta={tintaDoTrilhoDoCusto(receita.cost_status)} />

      <th scope="row" className={`${CLASSE_CELULA} max-w-0 text-left font-medium`}>
        <span className="flex items-baseline gap-2">
          <Link
            to="/receitas/$receita"
            params={{ receita: receita.id }}
            // Mantém a procura e o filtro no URL: é assim que o link de voltar
            // devolve a lista como estava, sem depender do histórico.
            search={true}
            className="min-w-0 truncate hover:underline group-hover:underline"
          >
            {receita.short_name}
          </Link>
          {/* A arquivada entra **marcada** e nunca escondida: esconder uma ficha
              arquivada fazia «não tenho essa receita» mentir. Numa linha só,
              porque uma sub-linha de 13px numa célula de 44px cresce a linha e
              desfaz o ritmo da tabela (DESIGN.md §4). */}
          {receita.is_active ? null : (
            <span className="shrink-0 text-xs text-muted-foreground">
              {textos.ficha.arquivada}
            </span>
          )}
        </span>
      </th>

      <td data-numeric className={`${CLASSE_CELULA} text-right`}>
        {textoDeQuantidade(receita.batch_size)}
      </td>

      <td data-numeric className={`${CLASSE_CELULA} text-right text-muted-foreground`}>
        {String(receita.line_count)}
      </td>

      {comEuros ? (
        <>
          <td data-numeric className={`${CLASSE_CELULA} text-right`}>
            <Euro valor={receita.batch_cost} formatar={formatMoney} />
          </td>
          {/* O custo por unidade de **apresentação** — a pergunta do dono é
              literalmente "quanto me custa um pastel", e um pastel é uma unidade
              de apresentação. A unidade fica visível ao lado do número porque
              ela varia de linha para linha e o cabeçalho não a pode nomear. */}
          <td data-numeric className={`${CLASSE_CELULA} text-right`}>
            <Euro
              valor={receita.display_cost}
              formatar={(valor) => `${formatUnitMoney(valor)}/${receita.display_unit}`}
            />
          </td>
        </>
      ) : null}

      <td className={CLASSE_CELULA}>
        <EstadoDoCustoDaFicha estado={receita.cost_status} />
      </td>
    </tr>
  );
}

export function TabelaDeReceitas({ receitas }: { readonly receitas: readonly ReceitaResumo[] }) {
  // **Uma pergunta por página e não por linha.** A decisão do servidor é a mesma
  // para todas as linhas da resposta (é o mesmo papel e o mesmo pedido), e
  // perguntar por linha dava uma tabela com colunas diferentes em linhas
  // diferentes no dia em que uma resposta viesse misturada. A primeira linha
  // decide; sem linhas não há tabela.
  const comEuros = receitas.some(fichaMostraEuros);

  return (
    <MolduraDeTabela
      colunas={colunasDe(comEuros)}
      larguraMinima={LARGURA_MINIMA}
      comTrilho
      rotulo={textos.lista.tabela}
    >
      <tbody>
        {receitas.map((receita) => (
          <LinhaDeReceita key={receita.id} receita={receita} comEuros={comEuros} />
        ))}
      </tbody>
    </MolduraDeTabela>
  );
}

/**
 * O pendente da lista: **esqueleto e não indicador** (DESIGN.md §3) — tem forma
 * a reservar, e as linhas já nascem com os 44px que vão ter.
 *
 * Desenha **sem** as colunas de euros, e isso é uma escolha: antes da resposta o
 * cliente não sabe quem vê dinheiro, e um esqueleto com seis colunas que depois
 * ficassem quatro era um salto de layout exactamente no instante em que os dados
 * chegam — pior do que o inverso, porque as duas colunas que aparecem empurram
 * para a direita o que já estava lido.
 */
export function EsqueletoDaTabelaDeReceitas() {
  return (
    <EsqueletoDeTabela
      colunas={colunasDe(false)}
      larguraMinima={LARGURA_MINIMA}
      comTrilho
      rotulo={textos.accoes.aCarregarLista}
    />
  );
}
