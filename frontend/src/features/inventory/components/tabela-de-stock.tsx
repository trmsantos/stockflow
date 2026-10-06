import { Link } from "@tanstack/react-router";

import {
  CLASSE_CELULA,
  CLASSE_LINHA,
  EsqueletoDeTabela,
  MolduraDeTabela,
  TrilhoDaLinha,
  type ColunaDeTabela,
} from "@/components/tabela";

import type { NivelDeStock } from "../schemas";
import { tintaDoTrilho } from "../tinta-do-estado";
import { textoDeQuantidade } from "../vocabulario";
import { EstadoDoNivel } from "./estado-do-nivel";
import { TextoDeValidade } from "./validade";

/**
 * O ecrã Stock como **tabela densa**, que é o que o DESIGN.md §1 e §4 sempre
 * pediram e o que o repositório não tinha.
 *
 * ## O que isto substitui, e porquê
 *
 * Era `linha-de-stock.tsx`: uma `<ul>` de `<Link>`s de 56px, cada um com o nome
 * à esquerda, a quantidade à direita, e uma segunda linha com um chip de estado e
 * a validade — dentro de uma coluna de `max-w-2xl` (672px) numa área de conteúdo
 * de 1024px. Quatro dados por linha, 352px de vazio à direita, e três cartões
 * arredondados por cima.
 *
 * O §4 descrevia essa dívida e explicava a ordem de a pagar: "alargar o cap sem
 * passar as linhas a tabela densa é pior do que o que está", e a reestruturação
 * ficava para depois da sessão 0. **A ordem inverteu-se a 2026-10-06 por decisão
 * do dono do produto**, por uma razão que não estava prevista: aquele desenho
 * lê-se como UI gerada por IA, e um ecrã que o dono não quer mostrar não serve
 * de instrumento para a sessão 0 que depende dele. A dívida bloqueava o que a
 * havia de resolver.
 *
 * O que a sessão 0 **ainda** decide são as *colunas* — se o mínimo é por artigo
 * ou por artigo-e-loja, que unidades existem. Não decide se isto é uma tabela ou
 * uma lista de cartões, e é por isso que esta obra não é refazer duas vezes:
 * acrescentar ou tirar uma coluna a uma tabela que existe é uma linha no array
 * `COLUNAS`.
 *
 * ## Duas colunas novas, e as duas já estavam no contrato
 *
 * **Mínimo** nunca foi mostrado em sítio nenhum, e é o que explica a coluna do
 * estado: "Baixo" sozinho é um veredicto para aceitar, "1,2 kg" ao lado de
 * "mínimo 3 kg" é um veredicto para verificar. A densidade de um ERP não é
 * apertar o que já havia — é caber o que estava a faltar.
 *
 * **Onde** passou a ter coluna própria em vez de aparecer numa terceira linha só
 * quando o artigo estava repartido. Com uma localização diz qual é, o que antes
 * não se via nunca; com várias, diz quais, e as quantidades por localização vão
 * para o `title` e para o ecrã de detalhe. É menos do que a lista antiga mostrava
 * num caso e mais do que ela mostrava em todos os outros, e mantém viva a sonda
 * da Q2 — o dono continua a ver que o mesmo artigo vive em dois sítios e a poder
 * dizer "quero a divisão à frente".
 *
 * ## A linha não é um link; o nome é
 *
 * A lista antiga fazia da linha inteira um `<Link>`. Numa `<table>` isso não
 * existe — não se envolve um `<tr>` num `<a>` — e a alternativa habitual (um
 * `<a>` esticado com `absolute inset-0`) rouba a selecção de texto a todas as
 * outras células. Numa tabela de ERP isso é uma perda real: quem tem o rato em
 * cima de "3,400 kg" quer copiar o número.
 *
 * Fica o nome como link, que é a convenção de qualquer tabela de dados, e o
 * `group-hover` devolve a descoberta: passar o rato em qualquer célula acende a
 * linha **e** sublinha o nome, logo o destino continua a anunciar-se sem roubar
 * o resto da linha.
 *
 * ## O que continua a não existir, e é a decisão mais importante do ecrã
 *
 * **Nenhuma célula de quantidade é editável.** Nem stepper, nem input, nem
 * duplo-clique para editar. Stock é um ledger: corrige-se com um movimento e não
 * com um lápis. Numa tabela a tentação é maior do que numa lista — uma grelha
 * pede uma folha de cálculo — e é precisamente por isso que fica escrito aqui.
 */

/**
 * `min-w-4xl` (56rem) é o que impede as seis colunas de se esmagarem. A 1280px a
 * área de conteúdo tem ~1024px, logo não há scroll em desktop; a 360px há, e o
 * DESIGN.md §4 declara-o — Stock não é rota de campo.
 */
const LARGURA_MINIMA = "min-w-4xl";

const ROTULO = "Níveis de stock, ordenados pelo que está pior primeiro";

/**
 * As seis colunas. As três de largura previsível — duas quantidades e o estado —
 * levam-na escrita; as três de texto (`artigo`, `validade`, `onde`) repartem o
 * que sobra.
 *
 * **Sem as larguras explícitas a distribuição estava errada, e só se viu
 * medindo.** O layout automático de uma tabela dá espaço a quem tem o conteúdo
 * mais largo, e aqui o conteúdo mais largo de uma coluna numérica é o seu
 * **cabeçalho**: "QUANTIDADE" em caixa alta com tracking de 0.08em é mais largo
 * do que "24,400 kg". Medido a 1280px: quantidade 246px e mínimo 212px para
 * números de ~90px, contra 140px para "Onde", que truncava "Armazém, Copa" com
 * espaço de sobra ao lado. Uma tabela de ERP que desperdiça 200px em duas
 * colunas e corta a terceira parece desenhada por quem não a usou.
 */
const COLUNAS: readonly ColunaDeTabela[] = [
  { chave: "artigo", rotulo: "Artigo" },
  { chave: "quantidade", rotulo: "Quantidade", classe: "w-36 text-right" },
  { chave: "minimo", rotulo: "Mínimo", classe: "w-32 text-right" },
  { chave: "estado", rotulo: "Estado", classe: "w-28" },
  { chave: "validade", rotulo: "Validade" },
  { chave: "onde", rotulo: "Onde" },
];

/**
 * As localizações de um artigo, para o `title` da célula: aqui sim com as
 * quantidades, porque um `title` é lido devagar e por inteiro.
 */
function detalheDasLocalizacoes(nivel: NivelDeStock): string {
  return nivel.by_location
    .map((parcela) => `${parcela.location.name}: ${textoDeQuantidade(parcela.quantity)}`)
    .join("\n");
}

function LinhaDeStock({
  nivel,
  limiarEmDias,
}: {
  readonly nivel: NivelDeStock;
  readonly limiarEmDias: number;
}) {
  const repartido = nivel.by_location.length > 1;
  const nomes = nivel.by_location.map((parcela) => parcela.location.name).join(", ");

  // A única cor que a quantidade recebe, e vem do veredicto do servidor: um
  // negativo lê-se a vermelho. A palavra na coluna do estado diz "Negativo",
  // logo a cor não está sozinha.
  const corDaQuantidade = nivel.status === "negativo" ? "text-danger" : "";

  return (
    <tr className={`group ${CLASSE_LINHA} transition-colors hover:bg-surface-2`}>
      <TrilhoDaLinha tinta={tintaDoTrilho(nivel.status)} />

      <th scope="row" className={`${CLASSE_CELULA} max-w-0 text-left font-medium`}>
        <Link
          to="/stock/$artigo"
          params={{ artigo: nivel.product }}
          // Mantém os filtros no URL ao abrir o detalhe: é assim que o link de
          // voltar devolve a lista como estava, sem depender do histórico.
          search={true}
          className="block truncate hover:underline group-hover:underline"
        >
          {nivel.short_name}
        </Link>
      </th>

      <td data-numeric className={`${CLASSE_CELULA} text-right ${corDaQuantidade}`}>
        {textoDeQuantidade(nivel.quantity)}
      </td>

      {/* O mínimo em `muted-foreground`: é a régua contra a qual se lê a
          quantidade, não um segundo número com o mesmo peso. */}
      <td data-numeric className={`${CLASSE_CELULA} text-right text-muted-foreground`}>
        {textoDeQuantidade(nivel.min_quantity)}
      </td>

      <td className={CLASSE_CELULA}>
        <EstadoDoNivel estado={nivel.status} />
      </td>

      <td className={`${CLASSE_CELULA} max-w-0`}>
        <TextoDeValidade validade={nivel.nearest_expiry} limiarEmDias={limiarEmDias} />
      </td>

      <td
        className={`${CLASSE_CELULA} max-w-0 text-muted-foreground`}
        {...(repartido ? { title: detalheDasLocalizacoes(nivel) } : {})}
      >
        <span className="block truncate">{nomes}</span>
      </td>
    </tr>
  );
}

export function TabelaDeStock({
  niveis,
  limiarEmDias,
}: {
  readonly niveis: readonly NivelDeStock[];
  readonly limiarEmDias: number;
}) {
  return (
    <MolduraDeTabela
      colunas={COLUNAS}
      larguraMinima={LARGURA_MINIMA}
      comTrilho
      rotulo={ROTULO}
    >
      <tbody>
        {niveis.map((nivel) => (
          <LinhaDeStock key={nivel.product} nivel={nivel} limiarEmDias={limiarEmDias} />
        ))}
      </tbody>
    </MolduraDeTabela>
  );
}

/**
 * O pendente da tabela, com as **mesmas** colunas e a mesma largura mínima.
 *
 * Vive aqui e não no ecrã para não haver duas listas de colunas: um esqueleto
 * com cinco colunas e uma tabela com seis é um salto de layout no momento em que
 * os dados chegam, e é o tipo de divergência que ninguém vê até ver.
 */
export function EsqueletoDaTabelaDeStock() {
  return (
    <EsqueletoDeTabela
      colunas={COLUNAS}
      larguraMinima={LARGURA_MINIMA}
      comTrilho
      rotulo="A carregar o stock…"
    />
  );
}
