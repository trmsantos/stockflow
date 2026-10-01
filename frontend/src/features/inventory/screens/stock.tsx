import { useNavigate, useSearch } from "@tanstack/react-router";
import { useMemo } from "react";

import { mensagemDeErro } from "@/lib/api/errors";

import { useNiveisDeStock, useResumoDeStock } from "../api";
import { BarraDeFiltros } from "../components/barra-de-filtros";
import { ErroDaLista, EsqueletoDaLista, ListaVazia } from "../components/estados-da-lista";
import { LinhaDeStock } from "../components/linha-de-stock";
import {
  ErroDosNumeros,
  EsqueletoDosNumeros,
  NumerosDoTopo,
} from "../components/numeros-do-topo";
import type { Localizacao, NivelDeStock } from "../schemas";

/**
 * O ecrã Stock — "o que é que eu tenho, e quanto?".
 *
 * Três números no topo, uma barra *sticky* para procurar e escolher a
 * localização, e uma linha por artigo com quatro dados: nome curto, quantidade
 * com unidade, estado e validade mais próxima. **A ordem é a do servidor: o que
 * está pior primeiro, nunca alfabética** — filtrar e procurar preserva-a, e o
 * cliente nunca reordena, senão ganhava uma segunda definição de "pior" que
 * divergiria da dos alertas.
 *
 * **Não há um único campo de quantidade editável neste ecrã**, e é a decisão que
 * o define: stock é um ledger, e um lápis ao lado do "3,4 kg" ensinaria o
 * produto errado a quem o vê. Quem quer mexer no número vai ao detalhe do
 * artigo e registra um movimento, que é o que o ledger aceita.
 *
 * Todo o estado que define o ecrã está no URL (`?loja=`, `?filtro=`, `?q=`),
 * validado à entrada pela rota: recarregar a página, voltar atrás e abrir um
 * link mostrado a alguém dão o mesmo ecrã.
 */

/** Minúsculas e sem acentos: quem procura "acucar" tem de encontrar "Açúcar". */
function normalizar(texto: string): string {
  return texto
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase();
}

/**
 * As localizações que o seletor oferece, tiradas dos dados. Ordenadas por nome
 * — aqui a ordem alfabética é a certa, porque é uma lista de escolhas e não a
 * fila de problemas da manhã.
 */
function localizacoesDe(niveis: readonly NivelDeStock[] | undefined): readonly Localizacao[] {
  const porId = new Map<string, Localizacao>();
  for (const nivel of niveis ?? []) {
    for (const parcela of nivel.by_location) {
      porId.set(parcela.location.id, parcela.location);
    }
  }
  return [...porId.values()].sort((a, b) => a.name.localeCompare(b.name, "pt-PT"));
}

/**
 * Os dois filtros do topo e a procura, aplicados **sobre veredictos do
 * servidor**: `status` para "em falta" e `days_away` contra o
 * `expiring_within_days` para "a expirar". Nada aqui recalcula o que é estar em
 * falta — só esconde linhas que o servidor já classificou.
 */
function filtrar(
  niveis: readonly NivelDeStock[],
  filtro: "falta" | "validade" | undefined,
  termo: string,
  limiarEmDias: number,
): readonly NivelDeStock[] {
  const procura = normalizar(termo);

  return niveis.filter((nivel) => {
    if (filtro === "falta" && nivel.status === "ok") return false;
    if (filtro === "validade") {
      const validade = nivel.nearest_expiry;
      if (validade === null || validade.days_away > limiarEmDias) return false;
    }
    if (procura !== "" && !normalizar(nivel.short_name).includes(procura)) return false;
    return true;
  });
}

export function EcraDeStock() {
  const busca = useSearch({ from: "/stock" });
  const navegar = useNavigate({ from: "/stock" });

  // Duas observações da mesma consulta quando não há loja escolhida (a chave é
  // a mesma, logo é um pedido só): a consolidada dá as opções do seletor, a
  // outra dá a lista do âmbito pedido. Só com `?loja=` é que são duas de facto.
  const consolidado = useNiveisDeStock();
  const niveis = useNiveisDeStock({ loja: busca.loja });
  const resumo = useResumoDeStock({ loja: busca.loja });

  const localizacoes = useMemo(() => localizacoesDe(consolidado.data?.results), [consolidado.data]);

  // O limiar é do servidor. Enquanto não chegar, vale 0: o ecrã prefere **não
  // avisar** a inventar um horizonte de dias que divergiria do dos alertas.
  const limiarEmDias = resumo.data?.expiring_within_days ?? 0;

  const termo = busca.q ?? "";
  const comFiltros = busca.filtro !== undefined || termo !== "" || busca.loja !== undefined;

  const linhas = useMemo(
    () => filtrar(niveis.data?.results ?? [], busca.filtro, termo, limiarEmDias),
    [niveis.data, busca.filtro, termo, limiarEmDias],
  );

  // O servidor pagina a 50. Dizê-lo quando acontece é mais honesto do que
  // mostrar "50 artigos" como se fossem todos — e, enquanto não houver segunda
  // página, as 50 que estão à vista são as 50 piores, que é a ordem certa para
  // uma lista truncada.
  const total = niveis.data?.count ?? 0;
  const truncada = niveis.data !== undefined && total > niveis.data.results.length;

  return (
    <section className="flex w-full max-w-2xl flex-col">
      {/* O nome do ecrã já está no header do shell; repeti-lo em grande custava
          uma das sete linhas do orçamento de 360×640. O documento continua a ter
          um `h1`, para quem navega por cabeçalhos. */}
      <h1 className="sr-only">Stock — o que tenho, e quanto</h1>

      <BarraDeFiltros
        termo={termo}
        aoProcurar={(valor) => {
          void navegar({
            search: (anteriores) => ({ ...anteriores, q: valor === "" ? undefined : valor }),
            // `replace` para não encher o histórico com uma entrada por tecla,
            // e sem `resetScroll` para a lista não saltar enquanto se escreve.
            replace: true,
            resetScroll: false,
          });
        }}
        localizacoes={localizacoes}
        lojaAtiva={busca.loja}
        aoEscolherLoja={(id) => {
          void navegar({ search: (anteriores) => ({ ...anteriores, loja: id }) });
        }}
      />

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

      {niveis.isPending ? <EsqueletoDaLista /> : null}

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
          {/* A contagem muda a cada tecla; quem lê por áudio tem de a ouvir sem
              ter de voltar ao topo da lista. */}
          <p aria-live="polite" className="sr-only">
            {linhas.length === 1 ? "1 artigo" : `${String(linhas.length)} artigos`}
          </p>

          {linhas.length === 0 ? (
            <ListaVazia comFiltros={comFiltros} />
          ) : (
            <>
              <ul className="flex flex-col">
                {linhas.map((nivel) => (
                  <li key={nivel.product}>
                    <LinhaDeStock nivel={nivel} limiarEmDias={limiarEmDias} />
                  </li>
                ))}
              </ul>
              {/* A regra de ordenação fica no fim, onde não paga pixéis acima da
                  dobra: quem chega ao fundo da lista é quem precisa de saber
                  porque é que ela não está por ordem alfabética. */}
              <p className="px-4 py-3 text-xs text-muted-foreground">
                {linhas.length === 1 ? "1 artigo" : `${String(linhas.length)} artigos`}
                {truncada ? ` de ${String(total)}` : ""} · ordenados pelo que está pior primeiro
              </p>
            </>
          )}
        </>
      )}
    </section>
  );
}
