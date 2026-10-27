import { useNavigate, useSearch } from "@tanstack/react-router";
import { useCallback } from "react";

import { mensagemDeErro } from "@/lib/api/errors";

import { useLocalizacoes, useNiveisDeStock, useResumoDeStock } from "../api";
import { BarraDeFiltros } from "../components/barra-de-filtros";
import { ErroDaLista, ListaVazia } from "../components/estados-da-lista";
import {
  ErroDosNumeros,
  EsqueletoDosNumeros,
  NumerosDoTopo,
} from "../components/numeros-do-topo";
import { EsqueletoDaTabelaDeStock, TabelaDeStock } from "../components/tabela-de-stock";
import { textos } from "../textos";

/**
 * O ecrã Stock — "o que é que eu tenho, e quanto?".
 *
 * Uma barra *sticky* de âmbito (procurar, escolher localização), uma régua de
 * contadores, e uma **tabela densa à largura toda** com seis colunas: artigo,
 * quantidade, mínimo, estado, validade e onde. **A ordem é a do servidor: o que
 * está pior primeiro, nunca alfabética** — e desde a ADR 0034 a **filtragem**
 * também é dele.
 *
 * ## Os três filtros deixaram de ser JavaScript, e isso corrigiu um defeito
 *
 * `?q=`, `?filtro=` e `?loja=` eram aplicados aqui sobre os `results` da página.
 * Com paginação a sério (50) isso procurava **só nas 50 piores linhas** e calava
 * as outras em silêncio — e porque a ordem é "o pior primeiro", calava-as
 * exactamente onde ninguém nota: um artigo procurado que estivesse fora da
 * primeira página simplesmente não aparecia. Agora são `WHERE` no servidor, o
 * `filtrar()` e o `normalizar()` deste ficheiro desapareceram, e com eles a
 * segunda definição de "em falta" de que o próprio docstring desconfiava.
 *
 * ## O mínimo é do estabelecimento, e o ecrã tem de o dizer
 *
 * Com `?loja=` posto, o `?loja=` escopa a quantidade, a repartição e a validade
 * — **não** o mínimo nem o estado, porque o mínimo é por artigo (ADR 0024) e
 * compará-lo contra o saldo de uma loja inventava faltas. A consequência é uma
 * linha legítima a dizer "0,4 kg · ok" ao lado de "mínimo 3 kg", que sem
 * explicação se lê como erro de cálculo. Daí a nota por cima da tabela, que só
 * aparece quando há loja escolhida: é nesse estado, e só nesse, que a frase
 * informa.
 *
 * **Não há um único campo de quantidade editável neste ecrã**, e é a decisão que
 * o define: stock é um ledger, e um lápis ao lado do "3,4 kg" ensinaria o
 * produto errado a quem o vê. Quem quer mexer no número vai ao detalhe do
 * artigo e regista um movimento, que é o que o ledger aceita.
 *
 * Todo o estado que define o ecrã está no URL (`?loja=`, `?filtro=`, `?q=`),
 * validado à entrada pela rota: recarregar a página, voltar atrás e abrir um
 * link mostrado a alguém dão o mesmo ecrã.
 */
export function EcraDeStock() {
  const busca = useSearch({ from: "/app/stock" });
  const navegar = useNavigate({ from: "/stock" });

  const termo = busca.q ?? "";

  // As opções do seletor vêm do **catálogo de localizações** e não dos dados da
  // lista. Era o contrário, e com os filtros no servidor isso partia-se de duas
  // maneiras de uma vez: as opções encolhiam à medida que se procurava (uma
  // loja sem resultados desaparecia do seletor), e evitá-lo obrigava a uma
  // segunda consulta de níveis sem filtros a cada tecla. Pelo caminho
  // resolve-se o preço que o `barra-de-filtros.tsx` tinha nomeado — uma
  // localização sem movimentos nenhuns nunca aparecia aqui.
  const localizacoes = useLocalizacoes();
  const niveis = useNiveisDeStock({ loja: busca.loja, q: busca.q, filtro: busca.filtro });
  const resumo = useResumoDeStock({ loja: busca.loja });

  // O limiar é do servidor. Enquanto não chegar, vale 0: o ecrã prefere **não
  // avisar** a inventar um horizonte de dias que divergiria do dos alertas.
  const limiarEmDias = resumo.data?.expiring_within_days ?? 0;

  const comFiltros = busca.filtro !== undefined || termo !== "" || busca.loja !== undefined;
  const linhas = niveis.data?.results ?? [];

  // O servidor pagina a 50. Dizê-lo quando acontece é mais honesto do que
  // mostrar "50 artigos" como se fossem todos — e, enquanto não houver segunda
  // página, as 50 que estão à vista são as 50 piores, que é a ordem certa para
  // uma lista truncada.
  const total = niveis.data?.count ?? 0;
  const truncada = niveis.data !== undefined && total > linhas.length;

  // Estável de propósito: a barra de filtros trava a procura com um temporizador
  // e tem esta função nas dependências. Uma função nova a cada render reiniciava
  // o travão em cada pintura, e o pedido podia nunca sair.
  const aoProcurar = useCallback(
    (valor: string) => {
      void navegar({
        search: (anteriores) => ({ ...anteriores, q: valor === "" ? undefined : valor }),
        // `replace` para não encher o histórico com uma entrada por procura, e
        // sem `resetScroll` para a lista não saltar enquanto se escreve.
        replace: true,
        resetScroll: false,
      });
    },
    [navegar],
  );

  return (
    // Sem `max-w`: a tabela usa a largura toda da área de conteúdo (DESIGN.md
    // §4), e as três regiões — barra, régua, tabela — encostam às arestas e
    // separam-se por réguas de 1px. É o painel de operação do §1, não três
    // cartões a flutuar.
    <section className="flex w-full flex-col">
      {/* O nome do ecrã está no header do shell, com o grupo ("Inventário /
          Stock"). Aqui fica o `h1` do documento, para quem navega por
          cabeçalhos — visível seria a mesma palavra duas vezes a 40px de
          distância. */}
      <h1 className="sr-only">{textos.stock.titulo}</h1>

      <BarraDeFiltros
        termo={termo}
        aoProcurar={aoProcurar}
        localizacoes={localizacoes.data?.results ?? []}
        lojaAtiva={busca.loja}
        aoEscolherLoja={(id) => {
          void navegar({ search: (anteriores) => ({ ...anteriores, loja: id }) });
        }}
      />

      {/* O seletor de loja perde as opções se o catálogo de localizações
          falhar, e sem isto a falha era **silenciosa**: um seletor desactivado
          com "Todas" lê-se como "este estabelecimento só tem uma loja". A
          tabela continua a funcionar — é por isso que a recusa é uma linha e
          não um bloco que empurre a lista para baixo. */}
      {localizacoes.isError ? (
        <ErroDaLista
          titulo={textos.contagem.erroDasLocalizacoes}
          mensagem={mensagemDeErro(localizacoes.error)}
          aoTentarOutraVez={() => {
            void localizacoes.refetch();
          }}
        />
      ) : null}

      {resumo.isPending ? <EsqueletoDosNumeros /> : null}
      {resumo.isError ? (
        <ErroDosNumeros
          aoTentarOutraVez={() => {
            void resumo.refetch();
          }}
        />
      ) : null}
      {resumo.data === undefined ? null : (
        <NumerosDoTopo resumo={resumo.data} filtroAtivo={busca.filtro} />
      )}

      {/* A frase que impede "0,4 kg · ok" de se ler como erro de cálculo. Só com
          loja escolhida, porque sem ela não há discrepância nenhuma a explicar —
          e uma nota permanente seria cromado que ninguém lê quando importa. */}
      {busca.loja === undefined ? null : (
        <p className="border-b border-border px-celula-x py-2 text-xs text-muted-foreground">
          {textos.stock.minimoDoEstabelecimento}
        </p>
      )}

      {niveis.isPending ? <EsqueletoDaTabelaDeStock /> : null}

      {niveis.isError ? (
        <ErroDaLista
          mensagem={mensagemDeErro(niveis.error)}
          aoTentarOutraVez={() => {
            void niveis.refetch();
          }}
        />
      ) : null}

      {niveis.data === undefined ? null : (
        <>
          {/* A contagem muda a cada procura; quem lê por áudio tem de a ouvir
              sem ter de voltar ao topo da lista. */}
          <p aria-live="polite" className="sr-only">
            {textos.stock.artigos(linhas.length)}
          </p>

          {linhas.length === 0 ? (
            <ListaVazia comFiltros={comFiltros} />
          ) : (
            <>
              <TabelaDeStock niveis={linhas} limiarEmDias={limiarEmDias} />
              {/* A regra de ordenação fica no fim, onde não paga pixéis acima da
                  dobra: quem chega ao fundo da tabela é quem precisa de saber
                  porque é que ela não está por ordem alfabética. */}
              <p className="px-celula-x py-3 text-xs text-muted-foreground">
                {textos.stock.rodape(linhas.length, truncada ? total : null)}
              </p>
            </>
          )}
        </>
      )}
    </section>
  );
}
