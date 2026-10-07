import { Link, useSearch } from "@tanstack/react-router";
import { PackageOpen } from "lucide-react";

import { ErroAoCarregar } from "@/components/erro-ao-carregar";
import { EstadoVazio } from "@/components/estado-vazio";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { isApiError, mensagemDeErro } from "@/lib/api/errors";
import { formatMonth, formatMoneyRounded } from "@/lib/format";

import { eAbaDeMes, perguntaDaAba } from "../abas";
import { notaDaContagem } from "../contagem";
import { useFechoDoMes, useProjeccaoDoPainel, useResumoDoPeriodo, useSeriesDoPeriodo } from "../api";
import {
  BarraDoPainel,
  FronteiraDoPeriodo,
  SeletorDePeriodo,
} from "../components/barra-do-painel";
import { BlocoDoPainel, FilaDePaineis } from "../components/bloco";
import { DinheiroDoPeriodo, EsqueletoDoDinheiro } from "../components/dinheiro-do-periodo";
import { BotaoDeExplicar } from "../components/explicar";
import {
  AvisoDoMesACorrer,
  EsqueletoDoMes,
  FronteiraDoMes,
  NavegacaoDeMes,
  SemPermissaoParaOPainel,
} from "../components/fecho-do-mes";
import {
  ErroDosNumeros,
  EsqueletoDosNumeros,
  NumerosDoPeriodo,
} from "../components/numeros-do-periodo";
import { EsqueletoDasPerdas, PerdasDoPeriodo } from "../components/perdas-do-periodo";
import { CargosDoMes, NumerosDoMes } from "../components/pessoal-do-mes";
import { QualidadeDosDadosDoPainel } from "../components/qualidade-dos-dados";
import { ResultadoDoMes } from "../components/resultado-do-mes";
import { EsqueletoDaVariacao, VariacaoNoPeriodo } from "../components/variacao-no-periodo";
import { mesCorrente, mesDeFechoPorOmissao } from "../meses";
import {
  eZero,
  type FechoDoMes,
  type Periodo,
  type ResumoDoPeriodo,
  type SeriesDoPeriodo,
} from "../schemas";
import { textos } from "../textos";
import { rotuloDaGranularidade, rotuloDoPeriodo } from "../vocabulario";

/**
 * O ecrã `/painel` — **o painel de gestão do dono** (ADR 0013, com a direcção de
 * 2026-10-06 por cima).
 *
 * ## Duas mudanças de direcção, e as duas foram do dono do produto
 *
 * A ADR 0013 fez o Início passar a painel. A 2026-10-06, depois de o ver a
 * correr, o dono do produto disse duas coisas:
 *
 *  1. *"em termos de UI/UX acho muito confuso, e com demasiado content"*. Media
 *     **3630px** a 1280×900, com nove tabelas, três réguas de contadores e cerca
 *     de trinta frases explicativas numa coluna "O QUE É". Nenhuma dessas frases
 *     estava errada — juntas eram um manual de instruções;
 *  2. *"esta aba de dashboard tem de ser outra à parte e não início, porque é
 *     apenas para owner do estabelecimento; os outros colaboradores e gerentes
 *     no início têm acesso a outra coisa"*.
 *
 * O que isto é agora: uma rota própria, **só do dono**, com três abas, uma régua
 * de contadores por aba, e as frases numa camada que se liga no URL. O Início
 * passou a ser a fila de trabalho do dia (ver `screens/inicio.tsx`), igual para
 * os três papéis.
 *
 * ## Um ecrã e não três projecções
 *
 * Era o primeiro ecrã do repositório em que os **próprios dados** eram
 * restritos por papel dentro do mesmo ecrã: o `staff` via uma lista, o `manager`
 * via o período sem nada que fosse função de salários, o `owner` via tudo. Com o
 * painel fechado ao dono, nenhum bloco sabe quem está a olhar — a projecção
 * decide se o ecrã **existe**, e é tudo. Os três endpoints de `reporting` passam
 * a ser de `{owner}`.
 *
 * O gate continua a ser do servidor. O que este ecrã faz é **não disparar** um
 * pedido que já sabe recusado — e mostrar a recusa se ela chegar, porque pode
 * chegar: basta a pertença ser revogada com a página aberta (ADR 0007).
 *
 * ## A aba decide o que se pede, não só o que se mostra
 *
 * `summary` nas abas do dinheiro e das perdas, `series` só na do dinheiro,
 * `month` só na do pessoal. Um ecrã que busca o que não mostra paga a latência e
 * o erro de uma coisa que ninguém pediu — e o `month` é o pedido mais caro dos
 * três.
 *
 * O **bloco de qualidade de dados fica fora das abas**, no topo: ele diz em que
 * números se pode confiar, e isso vale para as três. Não custa um quarto pedido
 * — o `DataQualityOut` viaja nas três respostas (ADR 0013, decisão 7) —, logo
 * lê-se do resumo ou do mês, conforme a aba que está aberta.
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

/**
 * O ecrã do sistema visual, só em desenvolvimento.
 *
 * Numa constante e não escrito duas vezes porque **é o mesmo caminho** no `href`
 * e no texto do link, e um caminho não é copy: não tem tradução e não entra no
 * catálogo. A constante é também o que o impede de divergir entre os dois sítios.
 */
const CAMINHO_DOS_TOKENS = "/dev/tokens";

/** Nada aconteceu nesta janela: três zeros, e os três do servidor. */
function semAtividade(resumo: ResumoDoPeriodo): boolean {
  return (
    eZero(resumo.revenue_gross_eur) &&
    eZero(resumo.purchases_eur) &&
    eZero(resumo.goods_consumed_eur)
  );
}

/** Nada registado neste mês: as duas pontas da conta a zero. */
function mesSemNada(mes: FechoDoMes): boolean {
  return eZero(mes.revenue_net_eur) && eZero(mes.cost_total_eur);
}

/** Um 403 é a recusa de papel do servidor; qualquer outro erro tem retry. */
function eRecusaDePapel(erro: unknown): boolean {
  return isApiError(erro) && erro.status === 403;
}

export function EcraDoPainel() {
  const busca = useSearch({ from: "/app/painel" });
  const periodo = busca.period ?? "7d";
  const mes = busca.month ?? mesDeFechoPorOmissao();
  const aba = busca.aba ?? "dinheiro";
  const explicar = busca.explicar === 1;

  const projeccao = useProjeccaoDoPainel();
  // `null` é "a sessão ainda não chegou" e não "não é dono": com um default o
  // ecrã ou dispara pedidos que vão ser recusados ou pisca uma recusa a quem
  // tem acesso. Na prática é imediato — o `beforeLoad` da rota do shell já leu
  // a sessão antes de montar o invólucro.
  const dono = projeccao === "dono";
  const abaDeMes = eAbaDeMes(aba);

  const resumo = useResumoDoPeriodo(periodo, dono && !abaDeMes);
  const series = useSeriesDoPeriodo(periodo, dono && aba === "dinheiro");
  const fecho = useFechoDoMes(mes, dono && abaDeMes);

  // A qualidade de dados vem da resposta que esta aba já pediu: é o mesmo
  // `DataQualityOut` nas três, e pedir um quarto recurso para o mostrar seria
  // inventar um pedido que o contrato não precisa.
  const qualidade = abaDeMes ? fecho.data?.data_quality : resumo.data?.data_quality;

  const recusado =
    (projeccao !== null && !dono) ||
    eRecusaDePapel(resumo.error) ||
    eRecusaDePapel(series.error) ||
    eRecusaDePapel(fecho.error);

  return (
    // Sem `max-w`: as tabelas usam a largura toda da área de conteúdo
    // (DESIGN.md §4), como o Stock e os Alertas.
    <section className="flex w-full flex-col">
      {/* O `<h1>` muda com a aba, e é o que diz onde se está a quem ouve o ecrã:
          o realce da aba activa e o trilho de 4px não chegam a quem não vê. */}
      <h1 className="sr-only">{textos.painel.tituloComPergunta(perguntaDaAba(aba))}</h1>

      {/* A barra **não** aparece a quem foi recusado, e isso é deliberado: três
          abas e cinco botões de período são controlos que não fazem nada quando
          o ecrã inteiro é uma recusa. O que ela mostraria era a forma de um ecrã
          que esta sessão não tem. */}
      {recusado ? null : (
        <BarraDoPainel
          aba={aba}
          controlo={
            abaDeMes ? (
              <NavegacaoDeMes mes={mes} limite={mesCorrente()} />
            ) : (
              <SeletorDePeriodo periodo={periodo} />
            )
          }
          eco={
            abaDeMes ? (
              fecho.data === undefined ? null : <FronteiraDoMes mes={fecho.data} />
            ) : (
              <FronteiraDoPeriodo resolvido={resumo.data?.period ?? null} />
            )
          }
        />
      )}

      {recusado ? (
        <SemPermissaoParaOPainel />
      ) : (
        <>
          {/* Fora das abas e no topo: o que o painel não sabe vale para as três
              perguntas, e esconder a declaração quando está tudo bem seria
              deixar sem resposta "o que aparece quando não há nada?" (ADR 0013,
              decisão 7). Compacto: uma linha por declaração, e uma linha só
              quando não há nada a declarar. */}
          <BlocoDoPainel
            titulo={textos.painel.naoSabe}
            acao={<BotaoDeExplicar ligado={explicar} />}
          >
            {qualidade === undefined ? (
              <div aria-busy="true" className="flex flex-col gap-2 px-celula-x pb-3">
                <span className="sr-only">{textos.painel.aCarregarDeclaracoes}</span>
                <Skeleton className="h-4 w-full max-w-md" />
                <Skeleton className="h-4 w-full max-w-sm" />
              </div>
            ) : (
              <QualidadeDosDadosDoPainel qualidade={qualidade} explicar={explicar} />
            )}
          </BlocoDoPainel>

          {aba === "dinheiro" ? (
            <AbaDoDinheiro
              resumo={resumo}
              series={series}
              periodo={periodo}
              explicar={explicar}
            />
          ) : null}
          {aba === "perdas" ? <AbaDasPerdas resumo={resumo} explicar={explicar} /> : null}
          {aba === "pessoal" ? <AbaDoPessoal fecho={fecho} mes={mes} explicar={explicar} /> : null}
        </>
      )}

      {import.meta.env.DEV ? (
        // Em desenvolvimento os dados de domínio vêm do servidor de fixtures
        // (ADR 0008, decisão 3) — a autenticação, não: essa é o backend a sério.
        // Em produção este ramo não existe no bundle.
        <p className="px-celula-x py-3 text-xs text-muted-foreground">
          {textos.painel.demonstracao}{" "}
          <a
            href={CAMINHO_DOS_TOKENS}
            className="text-primary underline underline-offset-4 hover:no-underline"
          >
            {CAMINHO_DOS_TOKENS}
          </a>
          .
        </p>
      ) : null}
    </section>
  );
}

/** O tipo que os três hooks devolvem, sem repetir o genérico em cada aba. */
interface Consulta<T> {
  readonly data: T | undefined;
  readonly isPending: boolean;
  readonly isError: boolean;
  readonly error: unknown;
  readonly refetch: () => unknown;
}

/**
 * **Dinheiro**: a régua, as quatro linhas com a identidade, e o gráfico.
 *
 * A tabela e o gráfico são **duas vidraças da mesma pergunta** (ver
 * `FilaDePaineis`): a tabela é quanto, o gráfico é quando. Lado a lado a partir
 * de 1280px, porque uma tabela de duas colunas a ocupar 1024px de largura
 * desperdiça metade do ecrã e empurra o gráfico para fora dele.
 */
function AbaDoDinheiro({
  resumo,
  series,
  periodo,
  explicar,
}: {
  readonly resumo: Consulta<ResumoDoPeriodo>;
  readonly series: Consulta<SeriesDoPeriodo>;
  readonly periodo: Periodo;
  readonly explicar: boolean;
}) {
  const dados = resumo.data;

  // O pendente desenha a **forma do ecrã** e não um spinner (DESIGN.md §3): a
  // régua, a tabela com as suas quatro linhas de 44px e o gráfico com a sua
  // altura. Quando os dados chegam nada salta — e o que está a carregar é dito
  // uma vez, por bloco, para quem ouve o ecrã.
  if (resumo.isPending) {
    return (
      <>
        <EsqueletoDosNumeros />
        <FilaDePaineis>
          <BlocoDoPainel titulo={textos.painel.dinheiroEMercadoria}>
            <EsqueletoDoDinheiro />
          </BlocoDoPainel>
          <BlocoDoPainel titulo={textos.painel.vendasECompras}>
            <EsqueletoDaVariacao />
          </BlocoDoPainel>
        </FilaDePaineis>
      </>
    );
  }

  if (resumo.isError) {
    return (
      <ErroDosNumeros
        mensagem={mensagemDeErro(resumo.error)}
        aoTentarOutraVez={() => {
          void resumo.refetch();
        }}
      />
    );
  }

  if (dados === undefined) return null;

  if (semAtividade(dados)) {
    return (
      <>
        <NumerosDoPeriodo resumo={dados} />
        <BlocoDoPainel titulo={textos.painel.nadaRegistado(rotuloDoPeriodo(periodo))}>
          <EstadoVazio
            icone={PackageOpen}
            titulo={textos.painel.vazioTitulo}
            descricao={textos.painel.vazioCorpo}
          >
            <Button asChild>
              <Link to="/receber">{textos.painel.receberMercadoria}</Link>
            </Button>
          </EstadoVazio>
        </BlocoDoPainel>
      </>
    );
  }

  return (
    <>
      <NumerosDoPeriodo resumo={dados} />
      <FilaDePaineis>
        <BlocoDoPainel
          titulo={textos.painel.dinheiroEMercadoria}
          acao={<BotaoDeExplicar ligado={explicar} />}
        >
          <DinheiroDoPeriodo resumo={dados} explicar={explicar} />
        </BlocoDoPainel>

        <BlocoDoPainel
          titulo={textos.painel.vendasECompras}
          nota={
            series.data === undefined
              ? undefined
              : // Formatado pelo `Intl` e nunca impresso cru: o `scale_max_eur`
                // chega como `"1300.00"`, que é a forma do `Decimal` do Django e
                // não a forma de o ler em pt-PT.
                textos.painel.notaDoGrafico(
                  rotuloDaGranularidade(series.data.granularity),
                  formatMoneyRounded(series.data.scale_max_eur),
                )
          }
        >
          {series.isPending ? <EsqueletoDaVariacao /> : null}
          {series.isError ? (
            <div className="px-celula-x pb-3">
              <ErroAoCarregar
                titulo={textos.painel.erroDoGrafico}
                mensagem={mensagemDeErro(series.error)}
                aoTentarOutraVez={() => {
                  void series.refetch();
                }}
              />
            </div>
          ) : null}
          {series.data === undefined ? null : <VariacaoNoPeriodo series={series.data} />}
        </BlocoDoPainel>
      </FilaDePaineis>
    </>
  );
}

/**
 * **Perdas**: as duas linhas, e o desperdício por motivo.
 *
 * Não tem régua de contadores, e é de propósito: os dois números que importam
 * são as duas linhas da tabela, e uma régua a repeti-los em grande era dizer o
 * mesmo duas vezes — que é a crítica que o dono do produto fez ao painel antigo.
 *
 * Também não tem o estado vazio global da aba do dinheiro: aqui dois zeros
 * **respondem** à pergunta, desde que venham com a data da última contagem ao
 * lado. "Ninguém contou" é a informação mais valiosa desta aba.
 */
function AbaDasPerdas({
  resumo,
  explicar,
}: {
  readonly resumo: Consulta<ResumoDoPeriodo>;
  readonly explicar: boolean;
}) {
  if (resumo.isPending) {
    return (
      <BlocoDoPainel titulo={textos.painel.perdas}>
        <EsqueletoDasPerdas />
      </BlocoDoPainel>
    );
  }

  if (resumo.isError) {
    return (
      <ErroDosNumeros
        mensagem={mensagemDeErro(resumo.error)}
        aoTentarOutraVez={() => {
          void resumo.refetch();
        }}
      />
    );
  }

  if (resumo.data === undefined) return null;

  const contagem = notaDaContagem(resumo.data);

  return (
    <BlocoDoPainel
      titulo={textos.painel.perdas}
      // A **condição** e não uma explicação: um zero de quebra desconhecida sem
      // a data da última contagem é a afirmação optimista que a ADR 0013
      // (decisão 7) existe para proibir. Fica à vista em qualquer camada.
      nota={<span className={contagem.tinta}>{contagem.texto}</span>}
      acao={<BotaoDeExplicar ligado={explicar} />}
    >
      <PerdasDoPeriodo resumo={resumo.data} explicar={explicar} />
    </BlocoDoPainel>
  );
}

/**
 * **Pessoal**: o fecho do mês, os três rácios, o resultado e o custo por cargo.
 *
 * É a aba onde vive o segundo grão do painel, e por isso é a que traz a
 * navegação de mês na barra do ecrã. Era um bloco no fundo de um scroll de
 * 3630px e tinha 1904px só para si — mais de metade do painel —, com duas
 * tabelas a decompor duas linhas de outra tabela. As duas decomposições são
 * agora notas das linhas que decompõem.
 */
function AbaDoPessoal({
  fecho,
  mes,
  explicar,
}: {
  readonly fecho: Consulta<FechoDoMes>;
  readonly mes: string;
  readonly explicar: boolean;
}) {
  if (fecho.isPending) {
    return (
      <BlocoDoPainel titulo={textos.painel.fechoDe(formatMonth(mes))}>
        <EsqueletoDoMes />
      </BlocoDoPainel>
    );
  }

  if (fecho.isError) {
    return (
      <div className="px-celula-x py-3">
        <ErroAoCarregar
          titulo={textos.painel.erroDoFecho}
          mensagem={mensagemDeErro(fecho.error)}
          aoTentarOutraVez={() => {
            void fecho.refetch();
          }}
        />
      </div>
    );
  }

  const dados = fecho.data;
  if (dados === undefined) return null;

  if (mesSemNada(dados)) {
    return (
      <BlocoDoPainel titulo={textos.painel.fechoDe(formatMonth(mes))}>
        <p className="px-celula-x pb-3 text-sm text-muted-foreground">
          {textos.painel.mesSemNada(formatMonth(mes))}
        </p>
      </BlocoDoPainel>
    );
  }

  return (
    <>
      <AvisoDoMesACorrer mes={dados} />
      <NumerosDoMes mes={dados} />

      <BlocoDoPainel
        titulo={textos.painel.resultadoDe(formatMonth(mes))}
        acao={<BotaoDeExplicar ligado={explicar} />}
      >
        <ResultadoDoMes mes={dados} explicar={explicar} />
      </BlocoDoPainel>

      <BlocoDoPainel titulo={textos.painel.custoPorCargo}>
        <CargosDoMes mes={dados} />
      </BlocoDoPainel>
    </>
  );
}
