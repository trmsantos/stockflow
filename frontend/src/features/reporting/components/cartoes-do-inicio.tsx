import { Link } from "@tanstack/react-router";

import { BarrasPorPeriodo, type SerieDeBarras } from "@/components/barras-por-periodo";
import {
  leituraDaValidade,
  textoDeQuantidade,
  tintaDoTrilhoDeGravidade,
  tintaDoTrilhoDoNivel,
  useAlertas,
  useContagensAbertas,
  useNiveisDeStock,
} from "@/features/inventory/api";
import { tintaDoTrilhoDoEstado, useRececoes } from "@/features/purchasing/api";
import { isApiError, mensagemDeErro } from "@/lib/api/errors";
import { formatDayMonth, formatMoney, formatMoneyRounded } from "@/lib/format";

import { useSeriesDoPeriodo } from "../api";
import { textos } from "../textos";
import { tintaDeSerie } from "../tinta-do-painel";
import { rotuloDeSerie } from "../vocabulario";
import { CartaoDeEcra, CLASSE_DO_DESTINO, LinhaDoCartao } from "./cartao-de-ecra";

/**
 * Os seis cartões do ecrã Início — cada um a pré-visualizar **um** ecrã com as
 * suas próprias linhas.
 *
 * ## Cada cartão lê a sua chave, e isso é a forma e não um detalhe
 *
 * São seis consultas independentes, cada uma com a chave por tenant que o ecrã
 * de destino já usa — `useAlertas("expira")` é literalmente a mesma entrada de
 * cache que o `/alertas?ver=expira` lê. Duas consequências, e as duas são a
 * razão desta forma existir:
 *
 *  1. **um cartão em erro não derruba os outros cinco.** O Início antigo tinha
 *     um aviso só, no fundo, para três pedidos: falhava um e o ecrã inteiro
 *     dizia que estava incompleto sem dizer onde, e o retry pedia os três;
 *  2. **tocar num cartão abre um ecrã já carregado.** A miniatura paga o pedido
 *     que o destino ia pagar, não um a mais.
 *
 * O custo honesto: são seis pedidos onde antes eram três resumos. É a troca de
 * "contei cinco lotes" por "quais são os cinco", e é a troca que o dono do
 * produto pediu ao pedir pré-visualizações. Quem está num Wi-Fi mau vê seis
 * esqueletos a encher em vez de um ecrã em branco.
 *
 * ## A fronteira entre features continua fechada
 *
 * Tudo o que vem do `inventory` e do `purchasing` entra pelo `api.ts` de cada um
 * (ADR 0008, decisão 2) — hooks e funções puras de leitura, nunca schemas,
 * componentes ou tipos de payload. As linhas são tipadas por inferência dos
 * hooks: este ficheiro não sabe escrever a palavra `Alerta`.
 */

/**
 * Três linhas por cartão. É o que cabe numa vidraça com a altura das outras e o
 * que uma pré-visualização tem de ser — a quarta linha já é a tabela, e a tabela
 * está a um toque de distância.
 */
const LINHAS_DE_PREVIA = 3;

/* ---------------------------------------------------------------------------
 * Alertas — o que expira.
 * ------------------------------------------------------------------------- */

export function CartaoDoQueExpira() {
  const alertas = useAlertas("expira");
  const linhas = (alertas.data?.results ?? []).slice(0, LINHAS_DE_PREVIA);

  return (
    <CartaoDeEcra
      destino={
        <Link to="/alertas" search={{ ver: "expira" }} className={CLASSE_DO_DESTINO}>
          {textos.inicio.alertasExpira}
        </Link>
      }
      aCarregar={alertas.isPending}
      rotuloDeCarga={textos.inicio.aCarregarExpira}
      erro={alertas.isError ? mensagemDeErro(alertas.error) : null}
      aoTentarOutraVez={() => {
        void alertas.refetch();
      }}
      // Sem guardas de `isPending`/`isError`: a precedência dos três estados é
      // do `CartaoDeEcra` — esqueleto, depois erro, depois vazio — e repeti-la
      // aqui seis vezes era seis sítios onde ela pode divergir.
      vazio={linhas.length === 0 ? textos.inicio.vazioExpira : null}
    >
      <ul className="flex flex-col">
        {linhas.map((alerta) => {
          // O limiar é o que vem **naquele alerta**, como na tabela de Alertas:
          // é ele que explica a frase ("expira amanhã", com aviso a 3 dias), e
          // lê-lo do resumo seria um segundo pedido para um número que já
          // viajou aqui.
          const leitura =
            alerta.lot === null ? null : leituraDaValidade(alerta.lot, alerta.threshold_days ?? 0);
          return (
            <LinhaDoCartao
              key={alerta.id}
              nome={alerta.short_name}
              trilho={tintaDoTrilhoDeGravidade(alerta.severity)}
            >
              {/* A frase reparte a largura com o nome, e **o que ela corta é a
                  cauda**. É a aplicação possível do §4 ("um nome truncado
                  lê-se, a razão de um alerta não") numa vidraça de 314px, onde
                  "perde qualidade depois de amanhã" sozinha gasta 236: com a
                  frase intocável o nome ficava em "A…", e um alerta sem artigo
                  não é melhor do que um artigo sem a data. O que a cauda leva é
                  o **quando**; o que fica é o **quê** — "perde qualidade"
                  contra "expira" —, que é a distinção que o guião da sessão 0
                  §2 protege, e o texto inteiro está no `title` e no ecrã a um
                  toque. */}
              {/* `null` só quando o alerta de validade vem sem lote, que o
                  contrato permite e o domínio não produz. Fica a célula vazia e
                  o trilho, que continuam a dizer que há um alerta — inventar
                  uma frase para um caso que não existe era pior. */}
              {leitura === null ? null : (
                <span className={`min-w-0 truncate ${leitura.corDoTexto}`} title={leitura.texto}>
                  {leitura.texto}
                </span>
              )}
            </LinhaDoCartao>
          );
        })}
      </ul>
    </CartaoDeEcra>
  );
}

/* ---------------------------------------------------------------------------
 * Alertas — o que falta.
 * ------------------------------------------------------------------------- */

export function CartaoDoQueFalta() {
  const alertas = useAlertas("falta");
  const linhas = (alertas.data?.results ?? []).slice(0, LINHAS_DE_PREVIA);

  return (
    <CartaoDeEcra
      destino={
        <Link to="/alertas" search={{ ver: "falta" }} className={CLASSE_DO_DESTINO}>
          {textos.inicio.alertasFalta}
        </Link>
      }
      aCarregar={alertas.isPending}
      rotuloDeCarga={textos.inicio.aCarregarFalta}
      erro={alertas.isError ? mensagemDeErro(alertas.error) : null}
      aoTentarOutraVez={() => {
        void alertas.refetch();
      }}
      vazio={linhas.length === 0 ? textos.inicio.vazioFalta : null}
    >
      <ul className="flex flex-col">
        {linhas.map((alerta) => (
          <LinhaDoCartao
            key={alerta.id}
            nome={alerta.short_name}
            trilho={tintaDoTrilhoDeGravidade(alerta.severity)}
          >
            {/* A quantidade e o mínimo **lado a lado**, que é a comparação que
                este cartão existe para mostrar. Lado a lado e não empilhados:
                uma sub-linha de 13px dentro de uma célula de 44px cresce a
                linha (DESIGN.md §4, lição 3). O mínimo fica em `muted` porque é
                a régua contra a qual se lê o número, não um segundo número com
                o mesmo peso. */}
            <span data-numeric className="shrink-0 text-sm">
              {textoDeQuantidade(alerta.quantity)}
            </span>
            {alerta.min_quantity === null ? null : (
              <span data-numeric className="shrink-0 text-xs text-muted-foreground">
                {textos.inicio.minimo(textoDeQuantidade(alerta.min_quantity))}
              </span>
            )}
          </LinhaDoCartao>
        ))}
      </ul>
    </CartaoDeEcra>
  );
}

/* ---------------------------------------------------------------------------
 * Receber — os documentos por rever.
 * ------------------------------------------------------------------------- */

/**
 * Dois e não três, e é o único cartão com outro número.
 *
 * Um documento ocupa uma linha com três factos — fornecedor, total e quantas
 * linhas faltam rever — e três documentos a essa densidade deixam o nome do
 * fornecedor em 60px. Dois cabem, e é raro haver mais: uma pastelaria recebe
 * duas ou três entregas por dia, não quinze.
 */
const DOCUMENTOS_DE_PREVIA = 2;

export function CartaoDeReceber() {
  // `"revisao"` e não sem filtro: é a mesma chave que o `/receber?estado=revisao`
  // lê, logo tocar no cartão abre a lista já carregada e com o mesmo filtro.
  const rececoes = useRececoes("revisao");
  const linhas = (rececoes.data?.results ?? []).slice(0, DOCUMENTOS_DE_PREVIA);

  return (
    <CartaoDeEcra
      destino={
        <Link to="/receber" search={{ estado: "revisao" }} className={CLASSE_DO_DESTINO}>
          {textos.inicio.receber}
        </Link>
      }
      aCarregar={rececoes.isPending}
      rotuloDeCarga={textos.inicio.aCarregarRececoes}
      erro={rececoes.isError ? mensagemDeErro(rececoes.error) : null}
      aoTentarOutraVez={() => {
        void rececoes.refetch();
      }}
      vazio={linhas.length === 0 ? textos.inicio.vazioRececoes : null}
      linhasDoEsqueleto={DOCUMENTOS_DE_PREVIA}
    >
      <ul className="flex flex-col">
        {linhas.map((rececao) => (
          <LinhaDoCartao
            key={rececao.id}
            nome={rececao.supplier.name ?? textos.inicio.semFornecedor}
            trilho={tintaDoTrilhoDoEstado(rececao.status)}
          >
            {/* Três estados e não dois, e o terceiro é o silêncio. Uma guia de
                remessa entra sem preços (`null`) e dizê-lo é mais honesto do que
                um "0,00 €"; a quem não vê euros a chave **não vem**
                (`undefined`) e a miniatura não escreve nada no lugar — "sem
                valor" seria uma afirmação sobre a fatura, e a fatura tem valor.
                A linha continua a dar o fornecedor e as linhas por rever, que é
                o trabalho dele. É a mesma decisão da tabela do Receber. */}
            {rececao.document_total === undefined ? null : rececao.document_total === null ? (
              <span className="shrink-0 text-xs text-muted-foreground">
                {textos.inicio.semValor}
              </span>
            ) : (
              <span data-numeric className="shrink-0 text-sm">
                {formatMoney(rececao.document_total)}
              </span>
            )}
            <span data-numeric className="shrink-0 text-xs text-muted-foreground">
              {rececao.lines_to_review}/{rececao.line_count}
            </span>
          </LinhaDoCartao>
        ))}
      </ul>
    </CartaoDeEcra>
  );
}

/* ---------------------------------------------------------------------------
 * Contar — as contagens a decorrer.
 * ------------------------------------------------------------------------- */

/**
 * As contagens **a decorrer**, uma linha por localização.
 *
 * Era uma contagem só, e o cartão mostrava as **zonas** dela. Com a ADR 0033 a
 * exclusividade passou a ser por localização e podem estar três abertas ao
 * mesmo tempo — e como nesta fatia a zona *é* a localização (ADR 0030, decisão
 * 3), as zonas de uma contagem eram sempre uma. A linha passa a ser a contagem:
 * mesma forma, mais verdade.
 *
 * O trilho marca a contagem que já tem **tudo contado** — a que só falta
 * fechar, e a única sobre a qual alguém tem de fazer alguma coisa daqui. As
 * outras estão a decorrer e uma linha a decorrer não é um problema; um trilho
 * em todas era uma coluna pintada que não distingue nada (DESIGN.md §3). A cor
 * não comunica sozinha: os dois números ao lado dizem `9 de 9`.
 */
export function CartaoDeContar() {
  const contagem = useContagensAbertas();
  const abertas = (contagem.data?.results ?? []).slice(0, LINHAS_DE_PREVIA);

  return (
    <CartaoDeEcra
      destino={
        <Link to="/contar" search={{}} className={CLASSE_DO_DESTINO}>
          {textos.inicio.contar}
        </Link>
      }
      aCarregar={contagem.isPending}
      rotuloDeCarga={textos.inicio.aCarregarContagem}
      erro={contagem.isError ? mensagemDeErro(contagem.error) : null}
      aoTentarOutraVez={() => {
        void contagem.refetch();
      }}
      // O convite é o cartão: ele inteiro é o link para o Contar, e é lá que
      // está a acção de começar. A frase diz o que não há; a saída é o toque.
      //
      // Um vazio só, desde a ADR 0033: o segundo ("há contagem e ela não tem
      // zonas") era sobre a lista de zonas de uma contagem, e a lista passou a
      // ser das contagens. Sem contagens a decorrer há uma frase, e ela convida
      // a começar uma — que é, desde esta ADR, coisa que toda a gente pode.
      vazio={abertas.length === 0 ? textos.inicio.vazioSemContagem : null}
    >
      <ul className="flex flex-col">
        {abertas.map((aberta) => (
          <LinhaDoCartao
            key={aberta.id}
            nome={aberta.location.name}
            trilho={aberta.counted_lines === aberta.total_lines ? "bg-warning" : ""}
          >
            {/* Dois números do servidor e **nenhuma barra de progresso**. O
                `progresso-da-contagem.tsx` já decidiu isto e a razão vale aqui
                em dobro: "3/4" é o progresso, e uma barra ao lado diz o mesmo
                em desenho — é decoração, que o guião da sessão 0 §4 nº 14
                proíbe. Numa miniatura, uma barra também gastaria metade da
                largura da célula para repetir seis caracteres. */}
            <span data-numeric className="shrink-0 text-sm text-muted-foreground">
              {aberta.counted_lines}/{aberta.total_lines}
            </span>
          </LinhaDoCartao>
        ))}
      </ul>
    </CartaoDeEcra>
  );
}

/* ---------------------------------------------------------------------------
 * Stock — as piores linhas.
 * ------------------------------------------------------------------------- */

export function CartaoDeStock() {
  // **Um pedido e não dois desde a ADR 0034.** Havia aqui um `useResumoDeStock`
  // só para o limiar de dias, porque o trilho precisava dele para recalcular a
  // urgência da validade. Agora ela vem no `severity` do lote, decidida pela
  // mesma função do servidor que decide a do alerta — logo o limiar deixou de
  // ter leitor neste cartão, e um pedido que não alimenta nada é um pedido a
  // menos num Wi-Fi mau.
  const niveis = useNiveisDeStock();
  const linhas = (niveis.data?.results ?? []).slice(0, LINHAS_DE_PREVIA);

  return (
    <CartaoDeEcra
      destino={
        <Link to="/stock" search={{}} className={CLASSE_DO_DESTINO}>
          {textos.inicio.stock}
        </Link>
      }
      aCarregar={niveis.isPending}
      rotuloDeCarga={textos.inicio.aCarregarStock}
      erro={niveis.isError ? mensagemDeErro(niveis.error) : null}
      aoTentarOutraVez={() => {
        void niveis.refetch();
      }}
      vazio={linhas.length === 0 ? textos.inicio.vazioStock : null}
    >
      <ul className="flex flex-col">
        {linhas.map((nivel) => (
          <LinhaDoCartao
            key={nivel.product}
            nome={nivel.short_name}
            // As duas razões compostas numa, pela função que a tabela de Stock
            // também usa: quantidade contra mínimo **e** prazo.
            trilho={tintaDoTrilhoDoNivel(nivel.status, nivel.nearest_expiry)}
          >
            <span
              data-numeric
              className={`shrink-0 text-sm ${nivel.status === "negativo" ? "text-danger" : ""}`}
            >
              {textoDeQuantidade(nivel.quantity)}
            </span>
          </LinhaDoCartao>
        ))}
      </ul>
    </CartaoDeEcra>
  );
}

/* ---------------------------------------------------------------------------
 * Painel — a miniatura do gráfico. **Só do dono.**
 * ------------------------------------------------------------------------- */

/**
 * O período da miniatura. `7d` é o default do painel (`screens/painel.tsx`), e
 * tem de ser o mesmo: com outro, a miniatura pedia uma série que o ecrã de
 * destino não ia usar — dois pedidos para um gráfico.
 */
const PERIODO_DA_PREVIA = "7d";

/**
 * Este componente **só é montado para o dono** (ver `screens/inicio.tsx`), e é
 * isso que faz o pedido não sair para mais ninguém: um hook não se chama
 * condicionalmente, logo a condição vive em quem o renderiza.
 *
 * Isto não é autorização — quem recusa é o servidor, com `permission_classes` na
 * view, e `/reporting/series` responde 403 a quem não é dono. O que isto faz é
 * não bater numa porta fechada. O 403 continua a poder chegar (basta a pertença
 * ser revogada com a página aberta) e tem o seu ramo abaixo, sem "tentar outra
 * vez": uma recusa de papel não se resolve a insistir.
 */
export function CartaoDoPainel() {
  const series = useSeriesDoPeriodo(PERIODO_DA_PREVIA, true);
  const dados = series.data;
  const recusado = isApiError(series.error) && series.error.status === 403;

  const paraDesenhar: SerieDeBarras[] = (dados?.series ?? []).map((serie) => ({
    id: serie.id,
    rotulo: rotuloDeSerie(serie.id),
    tinta: tintaDeSerie(serie.id),
    // A única aritmética é `Number(share)`, e é mandada pelo contrato: o `share`
    // e o `scale_max_eur` vêm do servidor para o desenho ser uma multiplicação
    // (ADR 0013, decisão 5). Nenhum euro é somado nem dividido aqui.
    pontos: serie.points.map((ponto) => ({
      share: Number(ponto.share),
      valor: formatMoneyRounded(ponto.value_eur),
    })),
  }));

  const semDesenho = dados !== undefined && (dados.buckets.length < 2 || paraDesenhar.length === 0);

  return (
    <CartaoDeEcra
      destino={
        <Link to="/painel" search={{}} className={CLASSE_DO_DESTINO}>
          {textos.inicio.painel}
        </Link>
      }
      aCarregar={series.isPending}
      rotuloDeCarga={textos.inicio.aCarregarGrafico}
      erro={series.isError && !recusado ? mensagemDeErro(series.error) : null}
      aoTentarOutraVez={() => {
        void series.refetch();
      }}
      vazio={
        recusado
          ? textos.inicio.vazioSemAcesso
          : semDesenho
            ? textos.inicio.vazioUmIntervalo
            : null
      }
      linhasDoEsqueleto={2}
      // Duas colunas a 2xl: é o único cartão cuja leitura melhora com largura,
      // e é também o que deixa seis cartões encherem uma grelha de quatro.
      largo
    >
      {dados === undefined ? null : (
        <div className="flex flex-1 flex-col justify-center py-3">
          <BarrasPorPeriodo
            compacto
            intervalos={dados.buckets.map((intervalo) => formatDayMonth(intervalo.since))}
            series={paraDesenhar}
            maximo={formatMoneyRounded(dados.scale_max_eur)}
            rotulo={textos.inicio.rotuloDoGrafico(formatMoneyRounded(dados.scale_max_eur))}
            // Lado a lado e não empilhadas: são grandezas a comparar e não
            // partes de um todo. Empilhar vendas sobre compras somava dinheiro
            // que entrou com dinheiro que saiu. Hoje a série é uma só (ADR 0029,
            // decisão 5) e o modo não se nota; fica declarado porque é o que
            // continua certo no dia em que a segunda chegar.
            empilhado={false}
          />
        </div>
      )}
    </CartaoDeEcra>
  );
}
