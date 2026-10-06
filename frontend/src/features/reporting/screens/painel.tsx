import { Link, useSearch } from "@tanstack/react-router";
import { PackageOpen } from "lucide-react";

import { ErroAoCarregar } from "@/components/erro-ao-carregar";
import { EstadoVazio } from "@/components/estado-vazio";
import { Button } from "@/components/ui/button";
import { isApiError, mensagemDeErro } from "@/lib/api/errors";
import { formatMonth, formatMoneyRounded } from "@/lib/format";

import { useFechoDoMes, useProjeccaoDoPainel, useResumoDoPeriodo, useSeriesDoPeriodo } from "../api";
import { BarraDoPainel } from "../components/barra-do-painel";
import { BlocoDoPainel, SubBloco } from "../components/bloco";
import { DinheiroDoPeriodo, EsqueletoDoDinheiro } from "../components/dinheiro-do-periodo";
import {
  AvisoDoMesACorrer,
  EsqueletoDoMes,
  FronteiraDoMes,
  NavegacaoDeMes,
  SemPermissaoParaOMes,
} from "../components/fecho-do-mes";
import {
  ErroDosNumeros,
  EsqueletoDosNumeros,
  NumerosDoPeriodo,
} from "../components/numeros-do-periodo";
import { PerdasDoPeriodo } from "../components/perdas-do-periodo";
import { PerguntasDaManha } from "../components/perguntas-da-manha";
import { PessoalDoMes } from "../components/pessoal-do-mes";
import { QualidadeDosDadosDoPainel } from "../components/qualidade-dos-dados";
import { ResultadoDoMes } from "../components/resultado-do-mes";
import { EsqueletoDaVariacao, VariacaoNoPeriodo } from "../components/variacao-no-periodo";
import { mesCorrente, mesDeFechoPorOmissao } from "../meses";
import { eZero, type ResumoDoPeriodo } from "../schemas";
import { rotuloDaGranularidade, rotuloDoPeriodo } from "../vocabulario";

/**
 * O ecrã Início — **o painel de gestão** (ADR 0013).
 *
 * Era a lista das perguntas da manhã e passou a isto; a lista sobreviveu como
 * último bloco, e é o ecrã inteiro de um `staff`. O ficheiro mudou de
 * `src/shell/screens/` para cá porque o Início deixou de ser um ecrã sem
 * domínio: passou a saber o que é uma venda, uma compra e uma folha salarial, e
 * o shell não pode importar features (ADR 0008, decisão 2). A rota `inicio` e o
 * `route_id` fechado **não mudaram**.
 *
 * ## Três projecções, e a do encarregado não é a do dono com uma barra escondida
 *
 * É o primeiro ecrã do repositório em que os **próprios dados** são restritos
 * por papel. Até aqui o papel só mudava a projecção do menu, e a ADR 0011 diz —
 * bem — que "esconder é apresentação, não autorização". Um painel com salários
 * visto por uma conta `staff` é uma fuga de dados pessoais, não um detalhe de UI.
 *
 *  - **`staff`**: as perguntas da manhã, que é o que ele já via. Não é um
 *    painel degradado: é o ecrã certo para quem está ao balcão;
 *  - **`manager`**: o bloco de período inteiro e nada que seja função de
 *    salários. Não precisa de nada escondido, porque **nenhum campo fora do
 *    `/reporting/month` é função de `people`** — nem o `prime_cost_pct`, que com
 *    o rácio de mercadoria ao lado daria a folha salarial por subtracção de
 *    rácios (ADR 0013, decisão 6);
 *  - **`owner`**: tudo, mais o fecho do mês.
 *
 * O gate é do servidor: o `/month` responde 403 a quem não é dono. O que este
 * ecrã faz é **não disparar** um pedido que já sabe recusado — e mostrar a
 * recusa se ela chegar, porque pode chegar: basta a pertença ser revogada com a
 * página aberta.
 *
 * ## Dois grãos, dois parâmetros no URL
 *
 * `period` (o que está a acontecer) e `month` (o fecho, com salários), os dois
 * validados em Zod na rota e independentes um do outro — mudar de período
 * preserva o mês. Um salário é um facto mensal e ratear 30 dias por 7 inventa
 * precisão que ninguém tem.
 *
 * ## O vazio é produto
 *
 * Um período sem vendas, sem compras e sem consumo não desenha quatro blocos de
 * zeros: diz o que falta e dá a porta. O bloco de qualidade de dados **fica**,
 * porque é ele que diz porquê — "o que aparece quando não há nada?" é uma das
 * perguntas da sessão 0, e um painel optimista por omissão é a única coisa pior
 * do que um painel vazio.
 */

/** Nada aconteceu nesta janela: três zeros, e os três do servidor. */
function semAtividade(resumo: ResumoDoPeriodo): boolean {
  return (
    eZero(resumo.revenue_gross_eur) &&
    eZero(resumo.purchases_eur) &&
    eZero(resumo.goods_consumed_eur)
  );
}

export function EcraDoPainel() {
  const busca = useSearch({ from: "/app/" });
  const periodo = busca.period ?? "7d";
  const mes = busca.month ?? mesDeFechoPorOmissao();

  const projeccao = useProjeccaoDoPainel();
  const comPainel = projeccao === "dono" || projeccao === "encarregado";
  const comFechoDoMes = projeccao === "dono";

  const resumo = useResumoDoPeriodo(periodo, comPainel);
  const series = useSeriesDoPeriodo(periodo, comPainel);
  const fecho = useFechoDoMes(mes, comFechoDoMes);

  // Quem está ao balcão vê as perguntas e mais nada. Sem pedidos, sem
  // skeletons: é um ecrã completo e não um painel sem permissões.
  if (projeccao === "operacao") {
    return (
      <section className="flex w-full flex-col">
        <h1 className="sr-only">Início — as perguntas da manhã</h1>
        <PerguntasDaManha />
      </section>
    );
  }

  const dados = resumo.data;
  // Um 403 no fecho do mês é a recusa de papel do servidor; qualquer outro erro
  // é uma falha de rede ou do servidor, e essa tem retry.
  const recusaDoMes = fecho.isError && isApiError(fecho.error) && fecho.error.status === 403;

  return (
    // Sem `max-w`: as tabelas usam a largura toda da área de conteúdo
    // (DESIGN.md §4), como o Stock e os Alertas.
    <section className="flex w-full flex-col">
      <h1 className="sr-only">Painel de gestão — o que está a acontecer, e como fechou o mês</h1>

      <BarraDoPainel periodo={periodo} resolvido={dados?.period ?? null} />

      {/* O pendente desenha a **forma do ecrã** e não um spinner (DESIGN.md
          §3): a régua, a tabela do dinheiro com as suas quatro linhas de 44px e
          o gráfico com a sua altura. Quando os dados chegam nada salta — e o
          que está a carregar é dito uma vez, por bloco, para quem ouve o ecrã. */}
      {resumo.isPending ? (
        <>
          <EsqueletoDosNumeros />
          <BlocoDoPainel titulo="O dinheiro e a mercadoria">
            <EsqueletoDoDinheiro />
          </BlocoDoPainel>
          <BlocoDoPainel titulo="Vendas e compras">
            <EsqueletoDaVariacao />
          </BlocoDoPainel>
        </>
      ) : null}
      {resumo.isError ? (
        <ErroDosNumeros
          mensagem={mensagemDeErro(resumo.error)}
          aoTentarOutraVez={() => {
            void resumo.refetch();
          }}
        />
      ) : null}
      {dados === undefined ? null : <NumerosDoPeriodo resumo={dados} />}

      {dados !== undefined && semAtividade(dados) ? (
        <BlocoDoPainel
          titulo={`Nada registado ${rotuloDoPeriodo(periodo)}`}
          nota="o painel enche-se à medida que a mercadoria entra e as vendas são registadas"
        >
          <EstadoVazio
            icone={PackageOpen}
            titulo="Sem vendas, sem compras e sem consumo nesta janela"
            descricao="Não há aqui quatro linhas de zeros porque zeros não respondem a nada. Comece por dar entrada à mercadoria que chegou: as compras aparecem no painel no dia em que a receção é confirmada."
          >
            <Button asChild>
              <Link to="/receber">Receber mercadoria</Link>
            </Button>
          </EstadoVazio>
        </BlocoDoPainel>
      ) : null}

      {dados !== undefined && !semAtividade(dados) ? (
        <>
          <BlocoDoPainel
            titulo="O dinheiro e a mercadoria"
            nota="compras é o dinheiro que saiu; mercadoria consumida é o que saiu do stock. As duas são verdadeiras, e a diferença tem nome."
          >
            <DinheiroDoPeriodo resumo={dados} />
          </BlocoDoPainel>

          <BlocoDoPainel
            titulo="Vendas e compras"
            nota={
              series.data === undefined
                ? undefined
                : // Formatado pelo `Intl` e nunca impresso cru: o `scale_max_eur`
                  // chega como `"1300.00"`, que é a forma do `Decimal` do
                  // Django e não a forma de o ler em pt-PT.
                  `${rotuloDaGranularidade(series.data.granularity)} · o eixo vai até ${formatMoneyRounded(series.data.scale_max_eur)}`
            }
          >
            {series.isPending ? <EsqueletoDaVariacao /> : null}
            {series.isError ? (
              <div className="px-celula-x pb-3">
                <ErroAoCarregar
                  titulo="Não foi possível carregar o gráfico"
                  mensagem={mensagemDeErro(series.error)}
                  aoTentarOutraVez={() => {
                    void series.refetch();
                  }}
                />
              </div>
            ) : null}
            {series.data === undefined ? null : <VariacaoNoPeriodo series={series.data} />}
          </BlocoDoPainel>

          <BlocoDoPainel
            titulo="Perdas"
            nota="duas linhas, e a segunda nunca aparece sem a data da última contagem"
          >
            <PerdasDoPeriodo resumo={dados} />
          </BlocoDoPainel>
        </>
      ) : null}

      {dados === undefined ? null : (
        <BlocoDoPainel
          titulo="O que este painel não sabe"
          nota="um painel optimista por omissão destrói a confiança mais depressa do que um prejuízo falso"
        >
          <QualidadeDosDadosDoPainel qualidade={dados.data_quality} />
        </BlocoDoPainel>
      )}

      {comFechoDoMes ? (
        <BlocoDoPainel
          titulo={`Fecho de ${formatMonth(mes)}`}
          nota={fecho.data === undefined ? undefined : <FronteiraDoMes mes={fecho.data} />}
          acao={<NavegacaoDeMes mes={mes} limite={mesCorrente()} />}
        >
          {fecho.isPending ? <EsqueletoDoMes /> : null}

          {recusaDoMes ? <SemPermissaoParaOMes /> : null}
          {fecho.isError && !recusaDoMes ? (
            <div className="px-celula-x pb-3">
              <ErroAoCarregar
                titulo="Não foi possível carregar o fecho do mês"
                mensagem={mensagemDeErro(fecho.error)}
                aoTentarOutraVez={() => {
                  void fecho.refetch();
                }}
              />
            </div>
          ) : null}

          {fecho.data === undefined ? null : eZero(fecho.data.revenue_net_eur) &&
            eZero(fecho.data.cost_total_eur) ? (
            <p className="px-celula-x pb-3 text-sm text-muted-foreground">
              Não há nada registado em {formatMonth(mes)}. Use a navegação acima para um mês com
              movimento.
            </p>
          ) : (
            <>
              <AvisoDoMesACorrer mes={fecho.data} />
              <ResultadoDoMes mes={fecho.data} />
              <SubBloco
                titulo="Pessoal"
                nota="custo-empresa do mês, nunca rateado por dias — um salário é um facto mensal"
              >
                <PessoalDoMes mes={fecho.data} />
              </SubBloco>
            </>
          )}
        </BlocoDoPainel>
      ) : null}

      <BlocoDoPainel
        titulo="As perguntas da manhã"
        nota="num dia em que os dados não carreguem, é esta lista que continua a servir"
      >
        <PerguntasDaManha />
      </BlocoDoPainel>

      {import.meta.env.DEV ? (
        // Em desenvolvimento os dados de domínio vêm do servidor de fixtures
        // (ADR 0008, decisão 3) — a autenticação, não: essa é o backend a sério.
        // Em produção este ramo não existe no bundle.
        <p className="px-celula-x py-3 text-xs text-muted-foreground">
          Os números do painel, o stock, as receções e as contagens são de demonstração. O sistema
          visual está em{" "}
          <a
            href="/dev/tokens"
            className="text-primary underline underline-offset-4 hover:no-underline"
          >
            /dev/tokens
          </a>
          .
        </p>
      ) : null}
    </section>
  );
}
