import { Link } from "@tanstack/react-router";
import { Maximize2, MessageSquareOff, Plus, X } from "lucide-react";
import { useId, useState } from "react";

import { ErroAoCarregar } from "@/components/erro-ao-carregar";
import { EstadoVazio } from "@/components/estado-vazio";
import { CLASSE_MICROROTULO } from "@/components/tabela";
import { Button } from "@/components/ui/button";
import {
  SheetClose,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { isApiError, mensagemDeErro } from "@/lib/api/errors";

import { useConversa } from "../hooks/use-conversa";
import { useConversas } from "../hooks/use-conversas";
import { useAbrirConversa, usePerguntar } from "../hooks/use-escritas";
import { lerRecusa, type Recusa } from "../recusas";
import { textos } from "../textos";
import { Compositor } from "./compositor";
import { EsqueletoDoFio } from "./esqueletos";
import { EstadoInicial } from "./estado-inicial";
import { FioDeTurnos } from "./fio-de-turnos";

/**
 * Que conversa o painel mostra. Três estados e não um `string | null`, porque
 * "ainda não escolhi" e "quero uma nova" são coisas diferentes com o mesmo
 * `null`: a primeira abre **a última conversa da pessoa** quando a lista chegar,
 * a segunda abre o compositor vazio.
 */
export type ConversaDoPainel =
  | { readonly modo: "ultima" }
  | { readonly modo: "nova" }
  | { readonly modo: "aberta"; readonly id: string };

/**
 * O assistente numa gaveta à direita, sobre o ecrã onde se está (ADR 0027,
 * decisão 10, adenda).
 *
 * ## Os mesmos componentes e os mesmos hooks da página
 *
 * O fio, o compositor, os esqueletos, o vazio com as três perguntas-exemplo, as
 * recusas e a sondagem a 2 s com desistência aos 90 s são os da
 * `screens/assistente.tsx`, importados e não copiados. As query keys são as
 * mesmas, logo página e painel partilham a cache: uma conversa aberta aqui está
 * quente quando se abre em página inteira, e vice-versa.
 *
 * O que o painel **não** tem é a lista de conversas: abre a última por omissão
 * e «Nova conversa» começa outra. Quem quiser escolher entre dez abre a página.
 *
 * ## O estado que sobrevive ao fecho vive no lançador
 *
 * O conteúdo de um `Dialog` desmonta-se ao fechar, logo a conversa escolhida e
 * o rascunho entram por propriedade — vêm do `screens/lancador.tsx`, que está
 * montado no invólucro e não numa rota. A recusa (503, 429, 409, rede) fica
 * aqui e morre com o fecho: é a resposta a um envio, e ao reabrir já não há
 * envio nenhum a que responda.
 *
 * ## Cromado em `surface`, tela em `background`
 *
 * A mesma regra do invólucro (DESIGN.md §2): o cabeçalho e o compositor são
 * cromado, o fio é tela. Sem isso o compositor não se distinguia do fio senão
 * pela régua de 1px.
 */
export function PainelDoAssistente({
  escolha,
  aoEscolher,
  rascunho,
  aoMudarRascunho,
  aoFechar,
}: {
  readonly escolha: ConversaDoPainel;
  readonly aoEscolher: (escolha: ConversaDoPainel) => void;
  readonly rascunho: string;
  readonly aoMudarRascunho: (valor: string) => void;
  /** Fecha a gaveta — a ligação para a página inteira chama-o ao navegar. */
  readonly aoFechar: () => void;
}) {
  const idDoCompositor = useId();

  const conversas = useConversas();
  const ultima = conversas.data?.results[0]?.id ?? null;
  const aberta =
    escolha.modo === "aberta" ? escolha.id : escolha.modo === "ultima" ? ultima : null;
  const aEsperarPelaLista = escolha.modo === "ultima" && conversas.isPending;
  const listaFalhou = escolha.modo === "ultima" && conversas.isError;

  const { consulta, emCurso, desistiu, retomar } = useConversa(aberta);
  const abrir = useAbrirConversa();
  const perguntar = usePerguntar();

  const [recusaEm, setRecusaEm] = useState<{
    readonly conversa: string | null;
    readonly recusa: Recusa;
  } | null>(null);

  const aEnviar = abrir.isPending || perguntar.isPending;
  const recusa = recusaEm !== null && recusaEm.conversa === aberta ? recusaEm.recusa : null;

  const focarCompositor = () => {
    // Por `id` e não por `ref`, pela razão medida no `Compositor`.
    const campo = document.getElementById(idDoCompositor);
    if (campo instanceof HTMLTextAreaElement) campo.focus();
  };

  const novaConversa = () => {
    aoEscolher({ modo: "nova" });
    focarCompositor();
  };

  const enviar = (pergunta: string) => {
    if (aberta === null) {
      abrir.mutate(pergunta, {
        onSuccess: (conversa) => {
          aoMudarRascunho("");
          setRecusaEm(null);
          aoEscolher({ modo: "aberta", id: conversa.id });
          focarCompositor();
        },
        onError: (erro) => {
          setRecusaEm({ conversa: null, recusa: lerRecusa(erro) });
          focarCompositor();
        },
      });
      return;
    }
    perguntar.mutate(
      { conversa: aberta, question: pergunta },
      {
        onSuccess: () => {
          aoMudarRascunho("");
          setRecusaEm(null);
          focarCompositor();
        },
        onError: (erro) => {
          setRecusaEm({ conversa: aberta, recusa: lerRecusa(erro) });
          focarCompositor();
        },
      },
    );
  };

  const conversaNaoExiste =
    consulta.isError && isApiError(consulta.error) && consulta.error.status === 404;
  const aCarregarOFio = aEsperarPelaLista || (aberta !== null && consulta.isPending);
  // O título só se afirma quando se sabe: enquanto a lista ou a conversa
  // carregam, «Nova conversa» era uma mentira de meio segundo.
  const tituloDaConversa = aCarregarOFio ? null : (consulta.data?.title ?? textos.ecra.novaConversa);

  return (
    <SheetContent
      side="right"
      showCloseButton={false}
      className="gap-0 bg-surface p-0 data-[side=right]:sm:max-w-lg"
      onOpenAutoFocus={(evento) => {
        // O foco vai para onde se escreve, e não para o primeiro botão do
        // cabeçalho: a pessoa abriu o painel para perguntar.
        evento.preventDefault();
        focarCompositor();
      }}
    >
      <SheetHeader className="h-cabecalho shrink-0 flex-row items-center gap-2 border-b border-border px-celula-x py-0">
        <span aria-hidden="true" className="h-chip w-trilho shrink-0 bg-primary" />
        <SheetTitle className={`${CLASSE_MICROROTULO} shrink-0`}>{textos.painel.titulo}</SheetTitle>
        <span aria-hidden="true" className="shrink-0 text-muted-foreground">
          /
        </span>
        {tituloDaConversa === null ? (
          <Skeleton className="h-4 w-40" />
        ) : (
          <p className="min-w-0 flex-1 truncate text-sm font-semibold" title={tituloDaConversa}>
            {tituloDaConversa}
          </p>
        )}
        <SheetDescription className="sr-only">{textos.painel.descricao}</SheetDescription>

        <span className="ml-auto flex shrink-0 items-center gap-1">
          <Button
            type="button"
            variant="ghost"
            size="icon"
            title={textos.ecra.novaConversa}
            onClick={novaConversa}
          >
            <Plus aria-hidden="true" />
            <span className="sr-only">{textos.ecra.novaConversa}</span>
          </Button>
          <Button asChild variant="ghost" size="icon">
            <Link
              to="/assistente"
              search={aberta === null ? {} : { conversa: aberta }}
              title={textos.painel.abrirEmPagina}
              onClick={aoFechar}
            >
              <Maximize2 aria-hidden="true" />
              <span className="sr-only">{textos.painel.abrirEmPagina}</span>
            </Link>
          </Button>
          <SheetClose asChild>
            <Button type="button" variant="ghost" size="icon" title={textos.painel.fechar}>
              <X aria-hidden="true" />
              <span className="sr-only">{textos.painel.fechar}</span>
            </Button>
          </SheetClose>
        </span>
      </SheetHeader>

      <div className="min-h-0 flex-1 overflow-y-auto overscroll-y-contain bg-background">
        {aCarregarOFio ? <EsqueletoDoFio /> : null}

        {listaFalhou ? (
          <ErroAoCarregar
            titulo={textos.lista.erroAoCarregar}
            mensagem={mensagemDeErro(conversas.error)}
            aoTentarOutraVez={() => {
              void conversas.refetch();
            }}
          />
        ) : null}

        {aberta === null && !aEsperarPelaLista && !listaFalhou ? (
          <EstadoInicial
            aoEscolher={(pergunta) => {
              aoMudarRascunho(pergunta);
              focarCompositor();
            }}
          />
        ) : null}

        {conversaNaoExiste ? (
          <EstadoVazio
            icone={MessageSquareOff}
            titulo={textos.fio.naoExisteTitulo}
            descricao={textos.fio.naoExisteCorpo}
          >
            <Button type="button" variant="outline" onClick={novaConversa}>
              {textos.ecra.novaConversa}
            </Button>
          </EstadoVazio>
        ) : null}

        {consulta.isError && !conversaNaoExiste ? (
          <ErroAoCarregar
            titulo={textos.fio.erroAoCarregar}
            mensagem={mensagemDeErro(consulta.error)}
            aoTentarOutraVez={() => {
              void consulta.refetch();
            }}
          />
        ) : null}

        {aberta !== null && consulta.data !== undefined ? (
          <FioDeTurnos conversa={consulta.data} desistiu={desistiu} aoRetomar={retomar} />
        ) : null}
      </div>

      <Compositor
        id={idDoCompositor}
        valor={rascunho}
        aoMudar={aoMudarRascunho}
        aoEnviar={enviar}
        aEnviar={aEnviar}
        bloqueado={emCurso}
        recusa={recusa}
        aoRepetir={() => {
          enviar(rascunho.trim());
        }}
        aoNovaConversa={novaConversa}
      />
    </SheetContent>
  );
}
