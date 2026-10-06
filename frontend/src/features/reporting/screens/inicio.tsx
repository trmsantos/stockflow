import { Link } from "@tanstack/react-router";
import { CircleCheck } from "lucide-react";

import { ErroAoCarregar } from "@/components/erro-ao-carregar";
import { EstadoVazio } from "@/components/estado-vazio";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useContagemAberta, useResumoDeAlertas } from "@/features/inventory/api";
import { useResumoDeRececoes } from "@/features/purchasing/api";
import { mensagemDeErro } from "@/lib/api/errors";
import { formatCount } from "@/lib/format";

import { CLASSE_DA_LINHA_DA_FILA, CorpoDaLinhaDaFila } from "../components/fila-do-dia";
import { PerguntasDaManha } from "../components/perguntas-da-manha";

/**
 * O ecrã `/` — **o trabalho do dia**, e é o mesmo para os três papéis.
 *
 * ## O que este ecrã já foi, e porque mudou duas vezes
 *
 * Foi uma lista de quatro perguntas com quatro links (`shell/screens/inicio.tsx`).
 * A ADR 0013 fez dele o painel de gestão, com três projecções por papel. A
 * 2026-10-06 o dono do produto desfez metade dessa decisão e com uma razão
 * clara: *"esta aba de dashboard tem de ser outra à parte e não início, porque é
 * apenas para owner do estabelecimento; os outros colaboradores e gerentes no
 * início têm acesso a outra coisa, por exemplo ao que está por expirar, coisas a
 * fazer, descargas a chegar, tarefas do dia"*.
 *
 * O painel foi para `/painel`, fechado ao dono. O que ficou aqui é a fila de
 * trabalho, **igual para todos**: sem projecções, sem papéis, sem parâmetros no
 * URL. Quem entra às sete da manhã vê o que está à espera e o número que o
 * descreve.
 *
 * ## Construído sobre o que já existe, e só sobre isso
 *
 * Três resumos que o backend já serve, e nenhum campo novo: validades e mínimos
 * (`inventory`), mercadoria por dar entrada (`purchasing`), contagem a decorrer
 * (`inventory`). Cada linha é um número do servidor e o caminho que o resolve.
 *
 * **"Tarefas do dia" como entidade não existe e não foi fingida.** Criar,
 * atribuir e concluir uma tarefa é domínio novo — um modelo, uma tabela com
 * `tenant_id` e a sua política RLS, um endpoint — e um Início que o desenhasse
 * com dados falsos prometia uma coisa que o backend não tem. O que esta fila
 * mostra são tarefas **derivadas de factos**: o lote que expira é uma tarefa
 * porque alguém tem de o usar ou deitar fora, não porque alguém a escreveu. Está
 * no relatório como pedido de domínio.
 *
 * ## A fronteira entre features, e porque é que este ecrã vive no `reporting`
 *
 * Lê `@/features/inventory/api` e `@/features/purchasing/api`, que é a **única**
 * porta aberta entre features (ADR 0008, decisão 2) e a que o `eslint.config.js`
 * verifica com um `regex`. O ecrã vive no `reporting` porque é precisamente o
 * módulo que a ADR 0013 (decisão 3) define como **sumidouro**: importa os `api`
 * dos outros, não tem recursos próprios e não escreve nada. Pô-lo no `inventory`
 * dava a uma feature de domínio a composição de outra; pô-lo no `shell` era
 * impossível, porque o shell não conhece features — e este ecrã sabe o que é um
 * lote, uma receção e uma contagem.
 *
 * ## Três consultas independentes, e um erro não leva a fila atrás
 *
 * Cada resumo é uma chave própria. Se o de receções falhar, as linhas de
 * validade continuam lá e aparece **um** aviso com retry para a parte que falta:
 * uma fila incompleta que diz que está incompleta serve; uma fila que
 * desaparece inteira porque um dos três pedidos falhou é um ecrã que não serve
 * para nada ao balcão.
 */

/** Singular ou plural, que numa fila de uma linha é metade da legibilidade. */
function unidade(quantos: number, singular: string, plural: string): string {
  return quantos === 1 ? singular : plural;
}

export function EcraInicial() {
  const alertas = useResumoDeAlertas();
  const rececoes = useResumoDeRececoes();
  const contagem = useContagemAberta();

  const aCarregar = alertas.isPending || rececoes.isPending || contagem.isPending;

  const resumoDeAlertas = alertas.data;
  const resumoDeRececoes = rececoes.data;
  const contagemAberta = contagem.data ?? null;

  const comValidades = resumoDeAlertas !== undefined && resumoDeAlertas.expiring_count > 0;
  const comFaltas = resumoDeAlertas !== undefined && resumoDeAlertas.missing_count > 0;
  const comRececoes = resumoDeRececoes !== undefined && resumoDeRececoes.needs_review_count > 0;
  const comContagem = contagemAberta !== null;

  const comTrabalho = comValidades || comFaltas || comRececoes || comContagem;
  const falhou = alertas.isError || rececoes.isError || contagem.isError;

  return (
    // Sem `max-w`: a fila usa a largura toda da área de conteúdo, como as
    // tabelas do Stock e dos Alertas (DESIGN.md §4). As linhas têm 44px, que é
    // o alvo de toque do §2 — este ecrã também se lê num tablet na copa.
    <section className="flex w-full flex-col">
      <h1 className="sr-only">Início — o trabalho do dia</h1>

      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 border-b border-border px-celula-x py-3">
        <h2 className="text-sm font-semibold">O que está à espera</h2>
        {resumoDeAlertas === undefined ? null : (
          <p className="min-w-0 flex-1 text-xs text-muted-foreground">
            {"o dia de negócio começa às "}
            <span data-numeric className="text-xs">
              {resumoDeAlertas.business_day_starts_at}
            </span>
          </p>
        )}
      </div>

      {aCarregar ? (
        // Skeleton e não spinner (DESIGN.md §3), com a altura das linhas que vão
        // aparecer: quando os números chegam, nada salta.
        <div aria-busy="true" className="flex flex-col">
          <span className="sr-only">A carregar o trabalho do dia…</span>
          {[0, 1, 2].map((indice) => (
            <div
              key={indice}
              className="flex h-linha items-center gap-celula-x border-b border-border px-celula-x"
            >
              <Skeleton className="h-4 w-20" />
              <Skeleton className="h-4 w-full max-w-sm" />
            </div>
          ))}
        </div>
      ) : null}

      {comTrabalho ? (
        // `<ol>` e não `<ul>`: a ordem **é** informação — o que está pior
        // primeiro, como em todas as listas desta app.
        <ol aria-label="Trabalho do dia, do mais urgente para o menos" className="flex flex-col">
          {comValidades ? (
            <li>
              <Link
                to="/alertas"
                search={{ ver: "expira" }}
                className={CLASSE_DA_LINHA_DA_FILA}
              >
                <CorpoDaLinhaDaFila
                  figura={formatCount(
                    resumoDeAlertas.expiring_count,
                    unidade(resumoDeAlertas.expiring_count, "lote", "lotes"),
                  )}
                  frase={`a expirar nos próximos ${String(resumoDeAlertas.expiring_within_days)} dias`}
                  ecra="Alertas"
                  trilho="bg-warning"
                />
              </Link>
            </li>
          ) : null}

          {comFaltas ? (
            <li>
              <Link to="/alertas" search={{ ver: "falta" }} className={CLASSE_DA_LINHA_DA_FILA}>
                <CorpoDaLinhaDaFila
                  figura={formatCount(
                    resumoDeAlertas.missing_count,
                    unidade(resumoDeAlertas.missing_count, "artigo", "artigos"),
                  )}
                  frase="abaixo do mínimo — há encomendas a fazer"
                  ecra="Alertas"
                  trilho="bg-warning"
                />
              </Link>
            </li>
          ) : null}

          {comRececoes ? (
            <li>
              <Link to="/receber" className={CLASSE_DA_LINHA_DA_FILA}>
                <CorpoDaLinhaDaFila
                  figura={formatCount(
                    resumoDeRececoes.needs_review_count,
                    unidade(resumoDeRececoes.needs_review_count, "descarga", "descargas"),
                  )}
                  frase={`por dar entrada, com ${String(resumoDeRececoes.needs_review_lines)} ${unidade(resumoDeRececoes.needs_review_lines, "linha", "linhas")} por rever`}
                  ecra="Receber"
                  trilho="bg-warning"
                />
              </Link>
            </li>
          ) : null}

          {contagemAberta !== null ? (
            <li>
              <Link to="/contar" className={CLASSE_DA_LINHA_DA_FILA}>
                <CorpoDaLinhaDaFila
                  // Dois números do servidor e nenhuma subtracção: "12 de 34" é
                  // o que o contrato manda (`counted_lines`/`total_lines`) e
                  // "22 por contar" seria uma conta feita aqui.
                  figura={`${String(contagemAberta.counted_lines)}/${String(contagemAberta.total_lines)}`}
                  frase="linhas contadas na contagem a decorrer"
                  ecra="Contar"
                  // O acento e não o âmbar: isto não está a correr contra o
                  // tempo, está **em curso** — é o mesmo trilho do item de menu
                  // activo (DESIGN.md §3).
                  trilho="bg-primary"
                />
              </Link>
            </li>
          ) : null}
        </ol>
      ) : null}

      {!aCarregar && !comTrabalho && !falhou ? (
        <EstadoVazio
          icone={CircleCheck}
          titulo="Nada à espera agora"
          descricao="Sem validades próximas, sem artigos abaixo do mínimo, sem mercadoria por dar entrada e sem contagem a decorrer. As quatro perguntas de sempre continuam abaixo, para quando quiser ver por si."
        >
          <Button asChild variant="outline">
            <Link to="/stock">Ver o stock</Link>
          </Button>
        </EstadoVazio>
      ) : null}

      {falhou ? (
        // Uma fila incompleta diz que está incompleta. O retry pede **as três**
        // outra vez: distinguir qual falhou dava três botões e três frases para
        // uma decisão que é sempre a mesma.
        <div className="px-celula-x py-3">
          <ErroAoCarregar
            titulo="Esta fila está incompleta"
            mensagem={`Não foi possível carregar parte do trabalho do dia. ${mensagemDeErro(
              alertas.error ?? rececoes.error ?? contagem.error,
            )}`}
            aoTentarOutraVez={() => {
              void alertas.refetch();
              void rececoes.refetch();
              void contagem.refetch();
            }}
          />
        </div>
      ) : null}

      {/* As quatro portas ficam **sempre** abaixo da fila, e não só quando ela
          está vazia: num dia em que um dos resumos não carregue, é esta lista
          que continua a servir — e é a única parte deste ecrã que não depende de
          pedido nenhum. Enquanto a fila carrega não aparecem, para o ecrã não
          crescer e encolher debaixo do rato. */}
      {aCarregar ? null : (
        <div className="flex flex-col border-t border-border">
          <div className="px-celula-x py-3">
            <h2 className="text-sm font-semibold">As perguntas de sempre</h2>
          </div>
          <PerguntasDaManha />
        </div>
      )}
    </section>
  );
}
