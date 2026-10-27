import { ScrollText } from "lucide-react";

import { ErroAoCarregar } from "@/components/erro-ao-carregar";
import {
  CLASSE_CELULA,
  CLASSE_LINHA,
  EsqueletoDeTabela,
  MolduraDeTabela,
  type ColunaDeTabela,
} from "@/components/tabela";
import { formatTime } from "@/lib/format";

import type { Movimento } from "../schemas";
import { textos } from "../textos";
import {
  diaDe,
  eEventoEconomico,
  rotuloDeMotivo,
  rotuloDeMovimento,
  textoDeQuantidade,
} from "../vocabulario";

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
 *
 * ## Tabela desde 2026-10-06, e o que a conversão arrumou
 *
 * Era uma `<ul>` de cartões com dois rodapés de factos juntos por pontos médios:
 * "07:40 · Rui (produção) · Cozinha · quebra" e "lote L-MOR-0930 · Produção de
 * hoje". Sete factos em três linhas empilhadas, e nenhum comparável com o da
 * linha acima — para saber se foi sempre a mesma pessoa a registar, tinha de se
 * ler as sete linhas inteiras. Em colunas isso vê-se de uma vez, e é precisamente
 * a sonda da Q7.
 *
 * **O agrupamento por dia sobreviveu**, como uma linha de cabeçalho com
 * `colSpan` em vez de um `<h3>` entre listas: a data repetida doze vezes gastava
 * a largura que o autor e o motivo precisam, e isso continua verdade.
 *
 * ## As pernas de produção lêem-se mais fracas, e é a ADR 0014
 *
 * Uma fornada escreve duas linhas que se anulam — os ingredientes saem
 * (`production_out`) e o produto acabado entra (`production_in`) — e **não são
 * eventos económicos**: o valor não sai do negócio, muda de forma. Numa
 * pastelaria o histórico de um artigo é dominado por elas, e mostrá-las com o
 * mesmo peso de uma quebra ensina o produto errado a quem o lê. Ficam em
 * `muted-foreground`, com o predicado `eEventoEconomico` do `vocabulario.ts` a
 * decidir — não uma segunda lista de tipos aqui dentro.
 */

/**
 * O cabeçalho de um grupo: o mesmo dia do `vocabulario.ts`, com maiúscula.
 *
 * A conta dos dias civis e a escolha entre "ontem" e a data vivem lá desde a
 * ADR 0033, quando a lista das contagens a decorrer passou a precisar das
 * duas — e duas cópias no mesmo módulo divergem na primeira correcção feita
 * só numa delas. Aqui fica só a caixa, que é decisão deste ecrã: início de
 * linha leva maiúscula, dentro de uma frase não.
 */
function rotuloDoDia(iso: string): string {
  const texto = diaDe(iso);
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

const COLUNAS: readonly ColunaDeTabela[] = [
  { chave: "hora", rotulo: textos.colunas.hora, classe: "w-24 text-right" },
  { chave: "movimento", rotulo: textos.colunas.movimento, classe: "w-52" },
  { chave: "quantidade", rotulo: textos.colunas.quantidade, classe: "w-32 text-right" },
  { chave: "motivo", rotulo: textos.colunas.motivo, classe: "w-32" },
  { chave: "quem", rotulo: textos.colunas.quem },
  { chave: "onde", rotulo: textos.colunas.onde },
  { chave: "lote", rotulo: textos.colunas.lote, classe: "w-32" },
];

const LARGURA_MINIMA = "min-w-4xl";
const ROTULO = textos.movimentos.tabela;

function LinhaDeMovimento({ movimento }: { readonly movimento: Movimento }) {
  // Uma perna de produção ou de transferência não é perda nem ganho (ADR 0014).
  const economico = eEventoEconomico(movimento.movement_type);

  return (
    <tr className={`${CLASSE_LINHA} transition-colors hover:bg-surface-2`}>
      <td data-numeric className={`${CLASSE_CELULA} w-24 text-right text-muted-foreground`}>
        {formatTime(movimento.occurred_at)}
      </td>

      {/* O **rótulo** da referência ("Contagem de 24/10, Armazém") fica no
          `title` e não numa coluna: a sete colunas não sobra largura para ele
          sem apertar o autor. Quando as fornadas existirem em dados reais, uma
          coluna "Operação" entra aqui — e fica nomeado em vez de esquecido.

          **Nunca o `reference` cru.** Num ajuste de fecho de contagem ele é o
          `id` da contagem em texto, e este `title` imprimia um uuid a quem lhe
          passasse o rato por cima. O servidor serve os dois lados desde a ADR
          0034 — o cru, porque há lookups e um índice parcial por ele, e o
          rótulo, que é o que se mostra. O que vem de fora deste módulo chega
          sem rótulo, e sem rótulo não se escreve nada. */}
      <td
        className={`${CLASSE_CELULA} w-52 ${economico ? "" : "text-muted-foreground"}`}
        {...(movimento.reference_label === null ? {} : { title: movimento.reference_label })}
      >
        {rotuloDeMovimento(movimento.movement_type)}
      </td>

      <td
        data-numeric
        className={`${CLASSE_CELULA} w-32 text-right ${economico ? "" : "text-muted-foreground"}`}
      >
        {textoDeQuantidade(movimento.quantity)}
      </td>

      <td className={`${CLASSE_CELULA} w-32 text-muted-foreground`}>
        {movimento.reason === null ? "" : rotuloDeMotivo(movimento.reason)}
      </td>

      {/* Toda a linha tem autor, e é a sonda da Q7: numa coluna vê-se se é sempre
          a mesma pessoa a registar, o que numa lista de cartões exigia ler sete
          linhas inteiras.

          Vazia quando quem agiu já não tem nome neste estabelecimento — o autor
          é o `display_name` da pertença e **nunca** o email, logo sem pertença
          não há nada a imprimir. É o caso raro; a coluna continua a existir
          porque a ausência num sítio é, ela própria, a resposta à Q7. */}
      <td className={`${CLASSE_CELULA} max-w-0`}>
        <span className="block truncate">{movimento.created_by ?? ""}</span>
      </td>

      <td className={`${CLASSE_CELULA} max-w-0 text-muted-foreground`}>
        <span className="block truncate">{movimento.location.name}</span>
      </td>

      <td data-numeric className={`${CLASSE_CELULA} w-32 text-left text-muted-foreground`}>
        {movimento.lot_code ?? ""}
      </td>
    </tr>
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
      <h2 className="px-celula-x text-sm font-semibold">{textos.movimentos.titulo}</h2>

      {aCarregar ? (
        <EsqueletoDeTabela
          colunas={COLUNAS}
          larguraMinima={LARGURA_MINIMA}
          rotulo={textos.movimentos.aCarregar}
          linhas={4}
        />
      ) : null}

      {mensagemDeErro === null ? null : (
        <div className="px-celula-x">
          <ErroAoCarregar
            titulo={textos.movimentos.erroAoCarregar}
            mensagem={mensagemDeErro}
            aoTentarOutraVez={aoTentarOutraVez}
          />
        </div>
      )}

      {movimentos === undefined ? null : movimentos.length === 0 ? (
        <div className="flex flex-col items-start gap-2 px-celula-x py-6">
          <ScrollText aria-hidden="true" className="size-6 text-muted-foreground" />
          <p className="font-medium">{textos.movimentos.vazioTitulo}</p>
          <p className="text-pretty text-sm text-muted-foreground">
            {textos.movimentos.vazioCorpo}
          </p>
        </div>
      ) : (
        <>
          <MolduraDeTabela colunas={COLUNAS} larguraMinima={LARGURA_MINIMA} rotulo={ROTULO}>
            {agrupar(movimentos).map((grupo) => (
              // Um `<tbody>` por dia: é o agrupamento que o HTML de tabelas tem
              // para isto, e dá o cabeçalho do dia sem o fingir com uma linha de
              // dados. O `colSpan` atravessa as sete colunas.
              <tbody key={grupo.rotulo}>
                <tr>
                  <th
                    scope="colgroup"
                    colSpan={COLUNAS.length}
                    className="bg-surface-2 px-celula-x py-1 text-left text-xs font-medium text-muted-foreground"
                  >
                    {grupo.rotulo}
                  </th>
                </tr>
                {grupo.movimentos.map((movimento) => (
                  <LinhaDeMovimento key={movimento.id} movimento={movimento} />
                ))}
              </tbody>
            ))}
          </MolduraDeTabela>
          {total > movimentos.length ? (
            <p className="px-celula-x py-2 text-xs text-muted-foreground">
              {textos.movimentos.rodape(movimentos.length, total)}
            </p>
          ) : null}
        </>
      )}
    </section>
  );
}
