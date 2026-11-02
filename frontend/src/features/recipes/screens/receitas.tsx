import { Link, useNavigate, useSearch } from "@tanstack/react-router";
import { CookingPot, Search } from "lucide-react";
import { useCallback } from "react";

import { ErroAoCarregar } from "@/components/erro-ao-carregar";
import { EstadoVazio } from "@/components/estado-vazio";
import { Button } from "@/components/ui/button";
import { mensagemDeErro } from "@/lib/api/errors";

import { usePodeEscreverFicha, useReceitas } from "../api";
import { BarraDaLista } from "../components/barra-da-lista";
import {
  EsqueletoDaTabelaDeReceitas,
  TabelaDeReceitas,
} from "../components/tabela-de-receitas";
import { textos } from "../textos";

/**
 * O ecrã Receitas — "o que entra numa fornada, e quanto custa de ingredientes?".
 *
 * Uma barra *sticky* de âmbito (procurar, estado, e a acção de escrita), e uma
 * **tabela densa à largura toda** com o acabado, a fornada, quantos
 * ingredientes tem, os dois custos e a certeza. É a forma dos ecrãs de lista
 * desta casa (DESIGN.md §3 e §4) e a irmã directa do `/stock`.
 *
 * ## "Custo de ingredientes", nunca "custo do prato"
 *
 * É o *food cost* (ADR 0035, decisão 9), e a diferença não é de estilo: com só
 * ingredientes, "custo do prato" erra por um factor de **2 a 4** numa
 * pastelaria, porque num produto com 20 cêntimos de matéria a mão-de-obra é o
 * custo dominante. A palavra está fixada no catálogo de copy e nenhum ecrã a
 * contradiz sem inventar uma chave.
 *
 * ## Os dois filtros são do servidor, e isso é o que os torna verdadeiros
 *
 * `?q=` é um `WHERE` que casa no nome **ou no SKU** do acabado e `?estado=` é
 * um conjunto fechado de dois valores (um terceiro é 400). Nenhum dos dois é um
 * `filter()` sobre os `results` da página: com a paginação a 50, procurar
 * dentro da página calava em silêncio tudo o que estivesse fora dela — é a
 * lição que a ADR 0034 cobrou no Stock.
 *
 * Todo o estado que define o ecrã está no URL, validado à entrada pela rota:
 * recarregar, voltar atrás e abrir um link mostrado a alguém dão o mesmo ecrã.
 *
 * ## Dois vazios e não um
 *
 * "Ainda não há ficha nenhuma" e "a procura não devolveu nada" são duas
 * situações com dois caminhos seguintes diferentes — criar a primeira, ou
 * limpar os filtros. E o primeiro só oferece o botão a quem o pode usar: a
 * escrita é de `owner|manager` (ADR 0035, decisão 5) e um botão que acaba em
 * 403 é uma promessa que o servidor desmente.
 */
export function EcraDeReceitas() {
  const busca = useSearch({ from: "/app/receitas" });
  const navegar = useNavigate({ from: "/receitas" });

  const termo = busca.q ?? "";
  const estado = busca.estado ?? "activas";
  const podeEscrever = usePodeEscreverFicha();

  const receitas = useReceitas({ q: busca.q, estado: busca.estado });

  const linhas = receitas.data?.results ?? [];
  const total = receitas.data?.count ?? 0;
  const truncada = receitas.data !== undefined && total > linhas.length;
  const comFiltros = termo !== "" || busca.estado !== undefined;

  // Estável de propósito: a barra trava a procura com um temporizador e tem
  // esta função nas dependências. Uma função nova a cada render reiniciava o
  // travão em cada pintura, e o pedido podia nunca sair.
  const aoProcurar = useCallback(
    (valor: string) => {
      void navegar({
        search: (anteriores) => ({ ...anteriores, q: valor === "" ? undefined : valor }),
        // `replace` para não encher o histórico com uma entrada por tecla, e sem
        // `resetScroll` para a lista não saltar enquanto se escreve.
        replace: true,
        resetScroll: false,
      });
    },
    [navegar],
  );

  return (
    // Sem `max-w`: a tabela usa a largura toda da área de conteúdo (DESIGN.md
    // §4), e as regiões encostam às arestas, separadas por réguas de 1px.
    <section className="flex w-full flex-col">
      {/* O nome do ecrã está no header do shell, com o grupo ("Inventário /
          Receitas"). Aqui fica o `h1` do documento, para quem navega por
          cabeçalhos — visível seria a mesma palavra duas vezes. */}
      <h1 className="sr-only">{textos.lista.titulo}</h1>

      <BarraDaLista
        termo={termo}
        aoProcurar={aoProcurar}
        estado={estado}
        aoEscolherEstado={(valor) => {
          void navegar({
            // `activas` é a omissão: limpa-se a chave em vez de a escrever com o
            // valor por omissão, senão há duas representações do mesmo estado.
            search: (anteriores) => ({
              ...anteriores,
              estado: valor === "activas" ? undefined : valor,
            }),
          });
        }}
        podeEscrever={podeEscrever}
      />

      {receitas.isPending ? <EsqueletoDaTabelaDeReceitas /> : null}

      {receitas.isError ? (
        <ErroAoCarregar
          titulo={textos.lista.erro}
          mensagem={mensagemDeErro(receitas.error)}
          aoTentarOutraVez={() => {
            void receitas.refetch();
          }}
        />
      ) : null}

      {receitas.data === undefined ? null : (
        <>
          {/* A contagem muda a cada procura; quem lê por áudio tem de a ouvir
              sem ter de voltar ao topo da lista. */}
          <p aria-live="polite" className="sr-only">
            {textos.lista.contagem(linhas.length)}
          </p>

          {linhas.length === 0 ? (
            <ListaVazia comFiltros={comFiltros} podeEscrever={podeEscrever} />
          ) : (
            <>
              <TabelaDeReceitas receitas={linhas} />
              {/* A regra de ordenação fica no fim, onde não paga pixéis acima da
                  dobra: quem chega ao fundo é quem precisa de saber porque é que
                  a ordem é aquela — e, se a lista estiver truncada, quantas
                  ficam de fora. */}
              <p className="px-celula-x py-3 text-xs text-muted-foreground">
                {textos.lista.rodape(linhas.length, truncada ? total : null)}
              </p>
            </>
          )}
        </>
      )}
    </section>
  );
}

/**
 * O vazio, em duas variantes — porque são duas situações e a acção seguinte não
 * é a mesma.
 *
 * Com filtros, o caminho é limpá-los: um `<Link>` com um reducer que devolve o
 * objecto vazio tira os dois do URL de uma vez, e por ser link funciona com o
 * clique do meio. Sem filtros, o caminho é escrever a primeira ficha — e o
 * botão **só aparece a quem escreve**. Para o `staff` fica a frase sozinha, que
 * é a verdade: não há fichas, e não é ele quem as cria.
 */
function ListaVazia({
  comFiltros,
  podeEscrever,
}: {
  readonly comFiltros: boolean;
  readonly podeEscrever: boolean;
}) {
  if (comFiltros) {
    return (
      <EstadoVazio
        icone={Search}
        titulo={textos.lista.semCorrespondenciaTitulo}
        descricao={textos.lista.semCorrespondenciaCorpo}
      >
        <Button asChild variant="outline">
          <Link to="/receitas" search={() => ({})}>
            {textos.lista.limparFiltros}
          </Link>
        </Button>
      </EstadoVazio>
    );
  }

  return (
    <EstadoVazio
      icone={CookingPot}
      titulo={textos.lista.vazioTitulo}
      descricao={textos.lista.vazioCorpo}
    >
      {podeEscrever ? (
        <Button asChild>
          <Link to="/receitas/nova" search={true}>
            {textos.accoes.criarPrimeira}
          </Link>
        </Button>
      ) : null}
    </EstadoVazio>
  );
}
