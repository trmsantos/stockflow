import { Link } from "@tanstack/react-router";

import {
  CLASSE_CELULA,
  CLASSE_LINHA,
  EsqueletoDeTabela,
  MolduraDeTabela,
  TrilhoDaLinha,
  type ColunaDeTabela,
} from "@/components/tabela";
import { formatDate, formatDayMonth, formatMoney, formatTime } from "@/lib/format";

import { rececaoMostraEuros } from "../euros-do-papel";
import type { Rececao } from "../schemas";
import { textos } from "../textos";
import { tintaDoTextoDoEstado, tintaDoTrilhoDoEstado } from "../tinta-do-estado";
import {
  nomeDoDocumento,
  rotuloDeEstadoDeRececao,
  siglaDeDocumento,
  textoDeNif,
} from "../vocabulario";

/**
 * Os documentos que chegaram, como **tabela densa à largura toda** — a mesma
 * linguagem do ecrã de Stock e do de Alertas.
 *
 * ## O que isto substitui, e porquê
 *
 * Era `linha-de-rececao.tsx`: um `<Link>` de 56px por documento, com três filas
 * de texto dentro de uma coluna de `max-w-2xl` (672px) numa área de conteúdo de
 * 1024px. A terceira fila era uma tira de **badges** (precisa de revisão, entrou
 * sem fatura, NIF diferente) e a segunda juntava o número do documento, a data e
 * a hora com pontos médios. Cinco factos por linha, 352px de vazio à direita, e
 * três pílulas por cima.
 *
 * Os pontos médios eram o problema maior, e não era estético: para comparar a
 * hora a que dois documentos chegaram era preciso ler as duas linhas inteiras e
 * encontrar o número no meio da frase. Em colunas, cada facto tem sítio fixo e
 * compara-se na vertical — o que é a leitura de dois metros do DESIGN.md §1.
 *
 * Os badges saíram pela razão do §3: um chip de 28px com tinta, borda e radius
 * próprios dentro de uma célula de 44px é um cartão pequeno a competir com a
 * régua de 1px que já delimita a célula. **O estado é a palavra.** Os badges
 * continuam a existir no cabeçalho do documento (`badges-de-rececao.tsx`), onde
 * há uma superfície para eles e não uma grelha.
 *
 * ## Três campos do contrato que a lista nunca mostrou
 *
 * **`line_count`** — quantas linhas o documento tem. O badge antigo só dizia
 * quantas faltavam rever ("precisa de revisão (2 linhas)"), e "2" sem o "de 5"
 * não diz se o documento está quase pronto ou quase intacto.
 *
 * **`locations`** — onde a mercadoria entrou. Estava só no cabeçalho do
 * documento, logo era invisível até se abrir cada um. Numa coluna vê-se que a
 * ida ao cash & carry repartiu a compra por duas lojas, que é a sonda da Q2.
 *
 * **`customer_name`/`customer_nif`** passaram de um badge com `title` a uma
 * frase debaixo do número do documento ("emitida a Sofia M. Aurora"). É a sonda
 * da Q10 e continua a ser **discreta e sem drama** — cinzento, não aviso:
 * pintá-la de vermelho transformava a observação numa acusação, e a conversa que
 * se seguia era sobre o ecrã.
 *
 * ## A linha não é um link; o fornecedor é
 *
 * A lista antiga fazia da linha inteira um `<Link>`. Numa `<table>` isso não
 * existe, e a alternativa habitual (um `<a>` esticado com `absolute inset-0`)
 * rouba a selecção de texto às outras células — numa tabela de ERP copiar o
 * número de uma fatura ou um total é uma utilização real. Fica o fornecedor como
 * link, e o `group-hover` devolve a descoberta: o rato em qualquer célula acende
 * a linha **e** sublinha o nome.
 *
 * **Nada nesta tabela dá entrada de nada**, e isso não mudou com a forma: não há
 * "confirmar" numa linha nem gesto para despachar um documento. Uma receção
 * confirma-se dentro, depois de se olhar para as linhas (CLAUDE.md: a extração
 * passa por revisão humana antes de gerar movimentos). Numa grelha a tentação é
 * maior do que numa lista, e é por isso que fica escrito aqui.
 */

/**
 * As colunas: **oito com euros, sete sem eles**. Todas menos duas — o fornecedor
 * e o "onde" — levam largura escrita, e essas duas repartem o que sobra.
 *
 * **As larguras são escritas porque numa coluna numérica o conteúdo mais largo é
 * o cabeçalho**, não o dado: "DOCUMENTO" em caixa alta com tracking de 0.08em é
 * mais largo do que metade dos números de fatura, e sem a largura declarada o
 * layout automático dá-lhe o espaço que o nome do fornecedor precisava. É a
 * razão que está escrita em `tabela-de-stock.tsx`, aplicada outra vez aqui
 * porque os cabeçalhos são outros.
 *
 * A conta das larguras (soma do que está declarado acima, não uma medição num
 * ecrã — o ensaio headless não correu nesta sessão): trilho e seis fixas somam
 * 724px, logo a 1280px, onde a área de conteúdo tem ~1024px, sobram ~150px para
 * cada uma das duas colunas de texto, e a 1440px ~230px. O nome do fornecedor
 * trunca no primeiro caso e está inteiro no `title` do link.
 */
function colunasDasRececoes(comEuros: boolean): readonly ColunaDeTabela[] {
  return [
    { chave: "fornecedor", rotulo: textos.tabela.colunas.fornecedor },
    { chave: "tipo", rotulo: textos.tabela.colunas.tipo, classe: "w-20" },
    // `w-32` e não `w-40`: medido, "FT 2026/4471" precisa de 132px dos 160 que a
    // coluna tinha, e os 32 de folga eram a largura que faltava ao fornecedor e ao
    // "onde" — os dois truncavam.
    { chave: "documento", rotulo: textos.tabela.colunas.documento, classe: "w-32" },
    { chave: "chegou", rotulo: textos.tabela.colunas.chegou, classe: "w-32 text-right" },
    // **A coluna do total só existe se algum documento trouxer o total.** Para
    // quem não vê euros ela estaria vazia de alto a baixo, e uma coluna "TOTAL"
    // com oito traços é uma afirmação sobre as faturas em vez de uma sobre o
    // papel de quem olha. Os 112px vão para as duas colunas de texto, que são as
    // que truncam a 1280px.
    ...(comEuros
      ? [{ chave: "total", rotulo: textos.tabela.colunas.total, classe: "w-28 text-right" }]
      : []),
    { chave: "linhas", rotulo: textos.tabela.colunas.linhas, classe: "w-28 text-right" },
    { chave: "estado", rotulo: textos.tabela.colunas.estado, classe: "w-32" },
    { chave: "onde", rotulo: textos.tabela.colunas.onde },
  ];
}

/**
 * `min-w-5xl` (64rem) é o que impede as oito colunas de se esmagarem. A 1280px
 * não há scroll; a 360px há, e o DESIGN.md §4 declara-o em vez de o tratar como
 * defeito — esconder colunas em mobile foi a alternativa rejeitada, porque a
 * coluna que se esconde é sempre a que faltava. Receber é rota de campo, mas o
 * que se faz nela a 360px é **fotografar a fatura** (o botão está colado ao
 * fundo, ao alcance do polegar), não conferir sete documentos em colunas.
 */
const LARGURA_MINIMA = "min-w-5xl";

const ROTULO = textos.tabela.rotulo;

function LinhaDeRececao({
  rececao,
  comEuros,
}: {
  readonly rececao: Rececao;
  /** Esta lista traz totais. Decide a célula do total, não o conteúdo dela. */
  readonly comEuros: boolean;
}) {
  const porRever = rececao.status === "needs_review";
  const nifDiferente =
    rececao.customer_nif !== null && rececao.customer_nif !== rececao.company_nif;
  const onde = rececao.locations.map((local) => local.name).join(", ");

  return (
    <tr className={`group ${CLASSE_LINHA} transition-colors hover:bg-surface-2`}>
      <TrilhoDaLinha tinta={tintaDoTrilhoDoEstado(rececao.status)} />

      <th scope="row" className={`${CLASSE_CELULA} max-w-0 text-left font-medium`}>
        <Link
          to="/receber/$rececao"
          params={{ rececao: rececao.id }}
          // Mantém o filtro no URL ao abrir o documento: é assim que o link de
          // voltar devolve a lista como estava, sem depender do histórico.
          search={true}
          className="block truncate hover:underline group-hover:underline"
          title={rececao.supplier.name ?? textos.comuns.semFornecedor}
        >
          {/* O nome vem vazio num documento que ainda não o tem, e um `<Link>`
              sem texto não tem nome acessível — a palavra entra no lugar, em
              itálico e a cinzento para não se ler como um nome de fornecedor.
              É o mesmo tratamento do "sem número" na coluna ao lado. */}
          {rececao.supplier.name ?? (
            <span className="italic text-muted-foreground">{textos.comuns.semFornecedor}</span>
          )}
        </Link>
      </th>

      {/* A sigla como vem impressa (`guia` em vez de `GR`, que é como se diz em
          voz alta). Mono e à esquerda, como qualquer código: o `data-numeric`
          alinha à direita, e por isso leva `text-left` por cima. */}
      <td
        data-numeric
        className={`${CLASSE_CELULA} w-20 text-left`}
        title={nomeDoDocumento(rececao.doc_type)}
      >
        {siglaDeDocumento(rececao.doc_type)}
        <span className="sr-only"> ({nomeDoDocumento(rececao.doc_type)})</span>
      </td>

      <td data-numeric className={`${CLASSE_CELULA} w-40 text-left`}>
        {rececao.doc_number ?? (
          // Uma fatura manuscrita da frutaria não tem número, e existem. Dizê-lo
          // é mais honesto do que uma célula vazia.
          <span className="font-sans text-muted-foreground">{textos.comuns.semNumero}</span>
        )}
        {nifDiferente ? (
          // A sonda da Q10, debaixo do número porque é do documento que se
          // trata. O `title` leva os dois NIF por extenso, que é a informação
          // que o badge antigo guardava.
          <span
            className="block truncate font-sans text-xs text-muted-foreground"
            title={textos.comuns.nifDoDocumento(
              rececao.customer_name ?? textos.comuns.outroAdquirente,
              textoDeNif(rececao.customer_nif ?? ""),
              rececao.company_name,
              textoDeNif(rececao.company_nif),
            )}
          >
            {textos.tabela.emitidaA(rececao.customer_name ?? textos.comuns.outroAdquirente)}
          </span>
        ) : null}
      </td>

      {/* Dia, mês e hora são **um** instante e não dois factos: separá-los em
          duas colunas duplicava o cromado para a mesma coisa. Em mono e à
          direita, as horas alinham na vertical — e é aí que se vê que três
          entregas chegaram todas antes das oito. O ano está no `title`. */}
      <td
        data-numeric
        className={`${CLASSE_CELULA} w-32 text-right`}
        title={textos.comuns.dataEHora(
          formatDate(rececao.received_at),
          formatTime(rececao.received_at),
        )}
      >
        {formatDayMonth(rececao.received_at)} {formatTime(rececao.received_at)}
      </td>

      {/* A célula só existe se a coluna existir — e a coluna só existe se os
          euros vierem. Dentro dela ficam os dois estados que **são** sobre o
          documento: o total impresso, e a guia que não traz preços. */}
      {comEuros ? (
        rececao.document_total === null || rececao.document_total === undefined ? (
          // A guia de remessa não traz preços: a mercadoria entra antes de existir
          // fatura. Dizê-lo é mais honesto do que um "0,00 €".
          <td className={`${CLASSE_CELULA} w-28 text-right text-xs text-muted-foreground`}>
            {textos.tabela.semValor}
          </td>
        ) : (
          // O total é exacto e por isso leva cêntimos: é um total de fatura, não
          // uma estimativa de custo médio. Arredondá-lo esconderia o número que
          // ele vai comparar com o papel que tem na mão.
          <td data-numeric className={`${CLASSE_CELULA} w-28 text-right`}>
            {formatMoney(rececao.document_total)}
          </td>
        )
      ) : null}

      <td data-numeric className={`${CLASSE_CELULA} w-28 text-right`}>
        {String(rececao.line_count)}
        {rececao.lines_to_review === 0 ? null : (
          // O número que o badge antigo trazia, agora debaixo do total de linhas
          // que ele qualifica: "2 por rever" de 5 é outra coisa que "2" de 2.
          // `font-sans`: a célula é `data-numeric` e a sub-linha herdava o mono,
          // onde "3 por rever" precisa de mais do que os 112px da coluna e
          // passava a linha a duas — a sub-linha de 13px a crescer uma linha de
          // 44px é o defeito que o DESIGN.md §4 nomeia.
          <span
            className={`block font-sans text-xs ${tintaDoTextoDoEstado(rececao.status)}`}
          >
            {textos.tabela.porRever(rececao.lines_to_review)}
          </span>
        )}
      </td>

      <td className={`${CLASSE_CELULA} w-32`}>
        {/* Um estado saudável devolve a palavra **só para áudio**: silêncio
            visual, não silêncio total (DESIGN.md §3). Quem navega a tabela por
            teclado ouviria "Estado" e nada, e não saberia distinguir um
            documento confirmado de um dado que falta. */}
        {porRever ? (
          <span className={tintaDoTextoDoEstado(rececao.status)}>
            {rotuloDeEstadoDeRececao(rececao.status)}
          </span>
        ) : (
          <span className="sr-only">{rotuloDeEstadoDeRececao(rececao.status)}</span>
        )}
        {rececao.awaiting_invoice ? (
          // Entrou por guia e a fatura vem a fim de mês. **Não é um aviso** — é o
          // normal de quem compra a distribuidores —, por isso é cinzento e fica
          // debaixo do estado, que é o que ele qualifica.
          <span className="block text-xs text-muted-foreground" title={textos.comuns.entrouPorGuia}>
            {textos.tabela.semFatura}
          </span>
        ) : null}
      </td>

      <td
        className={`${CLASSE_CELULA} max-w-0 text-muted-foreground`}
        {...(rececao.locations.length > 1 ? { title: onde } : {})}
      >
        <span className="block truncate">{onde}</span>
      </td>
    </tr>
  );
}

export function TabelaDeRececoes({ rececoes }: { readonly rececoes: readonly Rececao[] }) {
  // Lida da **resposta** e não do papel da sessão: é o servidor que decide quem
  // vê euros, e a forma do payload não pode divergir de si própria (ver
  // `euros-do-papel.ts`). `some` e não `every`: se um documento trouxer o total,
  // a coluna existe e os outros dizem "sem valor" — que é o que já faziam.
  const comEuros = rececoes.some(rececaoMostraEuros);

  return (
    <MolduraDeTabela
      colunas={colunasDasRececoes(comEuros)}
      larguraMinima={LARGURA_MINIMA}
      comTrilho
      rotulo={ROTULO}
    >
      <tbody>
        {rececoes.map((rececao) => (
          <LinhaDeRececao key={rececao.id} rececao={rececao} comEuros={comEuros} />
        ))}
      </tbody>
    </MolduraDeTabela>
  );
}

/**
 * O pendente da tabela, com as **mesmas** colunas e a mesma largura mínima.
 *
 * Vive aqui e não no ecrã para não haver duas listas de colunas: um esqueleto
 * com sete colunas e uma tabela com oito é um salto de layout no momento em que
 * os dados chegam. O número de linhas deixou de ser o que cabia num 360×640 (o
 * esqueleto de lista tinha seis, contadas para esse ecrã) e passa a ser o default
 * do módulo de tabela.
 */
export function EsqueletoDaTabelaDeRececoes() {
  return (
    <EsqueletoDeTabela
      // Com a coluna do total, que é a forma que vem para quem gere. É um
      // palpite declarado e não um descuido: antes da primeira resposta ninguém
      // sabe quantas colunas vêm, e a alternativa — perguntar o papel à sessão —
      // era escrever a política de euros uma segunda vez no cliente. O custo é
      // uma coluna a menos no primeiro desenho de quem não vê euros.
      colunas={colunasDasRececoes(true)}
      larguraMinima={LARGURA_MINIMA}
      comTrilho
      rotulo={textos.tabela.aCarregar}
    />
  );
}
