import { Link, useNavigate, useParams, useSearch } from "@tanstack/react-router";
import { ArrowLeft, CircleAlert, Pencil } from "lucide-react";
import type { ReactNode } from "react";

import { ErroAoCarregar } from "@/components/erro-ao-carregar";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { eNaoEncontrado, mensagemDeErro } from "@/lib/api/errors";
import { formatDecimalField } from "@/lib/format";

import { useActualizarReceita, usePodeEscreverFicha, useReceita } from "../api";
import {
  EsqueletoDaTabelaDeIngredientes,
  TabelaDeIngredientes,
} from "../components/tabela-de-ingredientes";
import {
  EsqueletoDosNumerosDaFicha,
  FraseDoCusto,
  NumerosDaFicha,
} from "../components/numeros-da-ficha";
import { FormularioDeReceita, type FichaGravavel } from "../components/formulario-de-receita";
import { erroDaFornada, erroDasLinhas, erroDoRendimento } from "../recusas-de-receita";
import type { ReceitaDetalhe } from "../schemas";
import { textos } from "../textos";

/**
 * A ficha técnica de uma receita — o que entra numa fornada, e quanto custa de
 * ingredientes.
 *
 * Lê-se de cima para baixo como uma folha de ledger: o acabado, a régua de
 * números (fornada, ingredientes e — só para quem vê euros — os dois custos), a
 * frase da certeza, e a tabela dos ingredientes com as **duas** quantidades.
 *
 * ## Ler é dos três papéis; escrever é do gabinete
 *
 * É a assimetria da ADR 0035 (decisão 5), e é o **espelho** da das contagens:
 * ali o campo abre e o gabinete fecha; aqui o gabinete escreve a ficha e o campo
 * produz a partir dela (fatia B). Quem está na cozinha precisa das quantidades,
 * e o que lhe falta são os **euros** — que são colunas e campos que desaparecem
 * do payload, não o recurso.
 *
 * Os botões de escrita escondem-se para o `staff` **por apresentação**: quem
 * autoriza é o servidor, com 403 em cada pedido (ADR 0009).
 *
 * ## Ausente e `null` são dois factos, e o ecrã não os colapsa
 *
 * Com a chave **ausente** (o `staff`) o campo e a coluna **desaparecem**; com a
 * chave a **`null`** (o degrau 5 da escada do custo) ficam, com "—" lá dentro e
 * o `cost_status` ao lado a dizer porquê. Quem decide isso é o payload e não o
 * papel da sessão — ver o `euros-da-ficha.ts`.
 *
 * ## Editar é o mesmo documento, e por isso é um `?editar=1`
 *
 * A ficha continua a ser o mesmo documento, com o mesmo cabeçalho; o que muda é
 * a forma de lhe tocar. Criar é que é outra página (`/receitas/nova`), porque aí
 * ainda não há documento nenhum. O `PATCH` manda sempre as linhas — a ficha é um
 * documento e grava-se inteira (decisão 4) —, e o botão de arquivar manda **só**
 * `{is_active}`: reescrever o documento para mudar um estado seria
 * last-write-wins em silêncio sobre o que outra pessoa gravou entretanto.
 */
export function EcraDaFichaTecnica() {
  const { receita } = useParams({ from: "/app/receitas/$receita" });
  const busca = useSearch({ from: "/app/receitas/$receita" });
  const navegar = useNavigate({ from: "/receitas/$receita" });

  const ficha = useReceita(receita);
  const podeEscrever = usePodeEscreverFicha();
  const actualizar = useActualizarReceita();

  // **Três estados e não dois** (o precedente é a ADR 0034, decisão 13, no
  // detalhe do artigo): o endereço não corresponde a nenhuma ficha deste
  // estabelecimento é o **vazio** deste ecrã; o servidor não respondeu é um
  // **erro**, e tem retry porque a causa mais provável é a ligação.
  const naoExiste = eNaoEncontrado(ficha.error);

  // O `?editar=1` só abre o formulário a quem o pode usar: um deep link com o
  // parâmetro posto chega aqui tanto para o `staff` como para quem mudou de
  // papel a meio, e um formulário que acaba em 403 é pior do que não o mostrar.
  const aEditar = busca.editar === 1 && podeEscrever;

  function fecharEdicao() {
    void navegar({
      params: { receita },
      search: (anteriores) => ({ ...anteriores, editar: undefined }),
      replace: true,
    });
  }

  return (
    <section className="flex w-full flex-col">
      <div className="px-celula-x py-3">
        <Button asChild variant="ghost" className="-ml-3">
          {/* `search={true}` leva de volta a procura e o filtro que estavam no
              URL: a lista reaparece exactamente como estava, sem depender do
              histórico do browser. */}
          <Link to="/receitas" search={true}>
            <ArrowLeft aria-hidden="true" />
            {textos.accoes.voltar}
          </Link>
        </Button>
      </div>

      {ficha.isPending ? <Esqueleto /> : null}

      {/* **O 404 antes do erro genérico**, e a ordem é a correcção: o `detail`
          que o DRF manda num 404 é "Não encontrado.", e essa é a frase que o
          `mensagemDeErro` imprimia. Sem botão de repetir — o endereço não
          melhora à segunda —, mas com saída: a lista. */}
      {naoExiste ? (
        <div className="px-celula-x pb-3">
          <Alert className="border-danger-border bg-danger-surface">
            <CircleAlert aria-hidden="true" className="text-danger" />
            <AlertTitle>{textos.ficha.naoExisteTitulo}</AlertTitle>
            {/* **Sem botão de saída aqui**, ao contrário do detalhe do artigo:
                o "Voltar às receitas" está 48px acima, em todos os estados
                deste ecrã. Repeti-lo dentro do aviso punha a mesma palavra duas
                vezes no mesmo campo de visão, a fazer quase a mesma coisa. */}
            <AlertDescription>{textos.ficha.naoExisteCorpo}</AlertDescription>
          </Alert>
        </div>
      ) : ficha.isError ? (
        <ErroAoCarregar
          titulo={textos.ficha.erro}
          mensagem={mensagemDeErro(ficha.error)}
          aoTentarOutraVez={() => {
            void ficha.refetch();
          }}
        />
      ) : null}

      {ficha.data === undefined ? null : (
        <>
          <Cabecalho
            ficha={ficha.data}
            aEditar={aEditar}
            accoes={
              podeEscrever ? (
                <>
                  {aEditar ? null : (
                    <Button asChild variant="outline">
                      {/* O `search` é o objecto **tipado** desta rota e não um
                          reducer sobre o anterior: num `<Link>` sem `from` o
                          argumento do reducer é a união das search params da
                          árvore inteira, e o `estado` do `/receber` (`hoje` e
                          `revisao`) não é o `estado` desta lista. */}
                      <Link
                        to="/receitas/$receita"
                        params={{ receita }}
                        search={{ ...busca, editar: 1 }}
                      >
                        <Pencil aria-hidden="true" />
                        {textos.accoes.editar}
                      </Link>
                    </Button>
                  )}
                  <Button
                    variant="ghost"
                    disabled={actualizar.isPending}
                    onClick={() => {
                      actualizar.mutate({
                        receita,
                        // **Só o estado.** As linhas não viajam: mandá-las para
                        // arquivar era reescrever o documento inteiro para
                        // mudar um booleano, e um `PATCH` que reescreve é
                        // last-write-wins em silêncio sobre quem gravou antes.
                        is_active: !ficha.data.is_active,
                      });
                    }}
                  >
                    {actualizar.isPending
                      ? textos.accoes.aArquivar
                      : ficha.data.is_active
                        ? textos.accoes.arquivar
                        : textos.accoes.reactivar}
                  </Button>
                </>
              ) : null
            }
          />

          {/* A régua fecha-se por uma régua de 1px e o formulário fecha-se pela
              mesma: sem ela, o botão de gravar encostava ao microrótulo do
              primeiro campo da régua e lia-se como parte dele. */}
          {aEditar ? (
            <div className="border-b border-border pb-6">
              <FormularioDeReceita
                ficha={ficha.data}
                pendente={actualizar.isPending}
                aoGravar={(valores: FichaGravavel) => {
                  actualizar.mutate(
                    {
                      receita,
                      batch_size: valores.batch_size,
                      batch_unit: valores.batch_unit,
                      yield_factor: valores.yield_factor,
                      // O schema do contrato pede um array mutável; o que o
                      // formulário entrega é `readonly`, e a cópia é a conversão
                      // honesta — nada se reordena nem se converte.
                      lines: [...valores.lines],
                    },
                    { onSuccess: fecharEdicao },
                  );
                }}
                aoCancelar={fecharEdicao}
              />
            </div>
          ) : null}

          {/* A recusa do servidor fica **por cima do documento** e não debaixo de
              uma linha: o ciclo de receitas e a unidade errada chegam com a
              frase e o campo, e o corpo do erro da unidade é uma lista com um
              dicionário por linha — o que ele permite afirmar é "está aqui", não
              "é nesta linha". */}
          {actualizar.isError ? <Recusa erro={actualizar.error} /> : null}

          <NumerosDaFicha receita={ficha.data} />
          <FraseDoCusto receita={ficha.data} />
          <TabelaDeIngredientes linhas={ficha.data.lines} />

          {/* O rendimento vive aqui, fora do caminho principal (decisão 8): é o
              que explica a coluna "sai do stock", e o caso normal — 1,000 — diz
              que nada se perde pelo caminho, que também é informação. */}
          <p className="px-celula-x py-3 text-xs text-muted-foreground">
            {Number(ficha.data.yield_factor) === 1
              ? textos.ficha.rendimentoNeutro(formatDecimalField(ficha.data.yield_factor))
              : textos.ficha.rendimento(formatDecimalField(ficha.data.yield_factor))}
          </p>
        </>
      )}
    </section>
  );
}

/**
 * O acabado, o código, o estado e as acções.
 *
 * O `sku` ao lado do nome porque é por ele que se procura na lista, e a palavra
 * "Arquivada" ao lado e não em vez dele: uma ficha arquivada **continua a
 * ler-se** e o que muda é não aparecer na lista por omissão. A cor nunca
 * comunica sozinha — aqui nem sequer há cor, há a palavra.
 */
function Cabecalho({
  ficha,
  aEditar,
  accoes,
}: {
  readonly ficha: ReceitaDetalhe;
  readonly aEditar: boolean;
  /** Os botões de escrita, ou nada: quem decide o papel é quem monta o ecrã. */
  readonly accoes: ReactNode;
}) {
  return (
    <header className="flex w-full max-w-6xl flex-col gap-3 px-celula-x pb-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-1">
          <h1 className="text-2xl font-semibold text-balance">
            {aEditar ? textos.formulario.tituloEditar : ficha.short_name}
          </h1>
          <p className="flex items-baseline gap-2 text-sm text-muted-foreground">
            <span data-numeric>{ficha.sku}</span>
            {ficha.is_active ? null : <span>{textos.ficha.arquivada}</span>}
          </p>
        </div>

        <div className="flex shrink-0 items-center gap-2">{accoes}</div>
      </div>

      {/* A nota só existe no estado em que informa. Permanente seria cromado que
          ninguém lê quando importa. */}
      {ficha.is_active ? null : (
        <p className="text-sm text-muted-foreground">{textos.ficha.arquivadaNota}</p>
      )}
    </header>
  );
}

/** A frase com que o servidor recusou a gravação, com o campo que ele nomeou. */
function Recusa({ erro }: { readonly erro: unknown }) {
  const detalhe =
    erroDasLinhas(erro) ?? erroDaFornada(erro) ?? erroDoRendimento(erro) ?? mensagemDeErro(erro);

  return (
    <div className="px-celula-x pb-3">
      <Alert className="border-danger-border bg-danger-surface">
        <CircleAlert aria-hidden="true" className="text-danger" />
        <AlertTitle>{textos.formulario.erroAoGravar}</AlertTitle>
        <AlertDescription>{detalhe}</AlertDescription>
      </Alert>
    </div>
  );
}

/**
 * O pendente: **esqueleto e não indicador** (DESIGN.md §3) — há forma a
 * reservar, e cada região já nasce com a altura que vai ter. A régua e a tabela
 * desenham-se **sem** as colunas de euros: antes da resposta o cliente não sabe
 * quem vê dinheiro, e campos que desaparecessem eram um salto maior do que
 * campos que aparecem.
 */
function Esqueleto() {
  return (
    <>
      <div aria-busy="true" className="flex flex-col gap-2 px-celula-x pb-4">
        <span className="sr-only">{textos.accoes.aCarregarFicha}</span>
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-4 w-32" />
      </div>
      <EsqueletoDosNumerosDaFicha />
      <EsqueletoDaTabelaDeIngredientes />
    </>
  );
}
