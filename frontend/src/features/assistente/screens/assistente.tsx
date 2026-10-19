import { Link, useNavigate, useSearch } from "@tanstack/react-router";
import { MessageSquareOff, Plus } from "lucide-react";
import { useId, useState } from "react";

import { ErroAoCarregar } from "@/components/erro-ao-carregar";
import { EstadoVazio } from "@/components/estado-vazio";
import { CLASSE_MICROROTULO } from "@/components/tabela";
import { Button } from "@/components/ui/button";
import { isApiError, mensagemDeErro } from "@/lib/api/errors";

import { Compositor } from "../components/compositor";
import { EsqueletoDoFio } from "../components/esqueletos";
import { EstadoInicial } from "../components/estado-inicial";
import { FioDeTurnos } from "../components/fio-de-turnos";
import { GavetaDeConversas } from "../components/gaveta-de-conversas";
import { PainelDeConversas } from "../components/painel-de-conversas";
import { useConversa } from "../hooks/use-conversa";
import { useConversas } from "../hooks/use-conversas";
import { useAbrirConversa, useApagarConversa, usePerguntar } from "../hooks/use-escritas";
import { lerRecusa, type Recusa } from "../recusas";
import { textos } from "../textos";

/**
 * `/assistente` — "quanto tenho de farinha? o que vence esta semana?", por
 * palavras (ADR 0027, decisão 10).
 *
 * ## Dois painéis, um instrumento
 *
 * À esquerda as conversas em linhas de 44px, à direita o fio de turnos com o
 * compositor em baixo. Desktop-primeiro (DESIGN.md §4): a 1280px as duas
 * colunas estão à vista; abaixo de `md` a lista vai para uma gaveta aberta da
 * barra do ecrã, e o fio ocupa a largura toda. Uma rota, dois enquadramentos —
 * layout, nunca routing (ADR 0008, decisão 1).
 *
 * ## O único ecrã preso ao viewport
 *
 * Os outros ecrãs deslizam com a página e têm a barra `sticky`. Este tem o
 * compositor **em baixo** e o fio a deslizar por dentro, porque é assim que uma
 * conversa se lê: a pergunta nova escreve-se sempre no mesmo sítio e a resposta
 * nova aparece sempre logo acima. A altura é a do viewport menos a barra de
 * topo — escrita com o token da barra (`--spacing-cabecalho`), e não com um
 * número solto.
 *
 * ## A conversa aberta está no URL, o rascunho não
 *
 * `?conversa=<uuid>` define o ecrã, logo pertence ao URL (ADR 0008): voltar
 * atrás, recarregar e mostrar um link reproduzem-no. A pergunta a meio de ser
 * escrita é um rascunho e vive em memória, como o estado de edição das
 * Definições.
 *
 * ## A recusa é guardada com a conversa a que pertence
 *
 * Uma recusa (503, 429, 409, rede) fica por cima do compositor até a pessoa
 * enviar outra vez ou trocar de conversa. Guarda-se **com o id** da conversa em
 * que aconteceu e mostra-se por comparação — é o que evita repor estado num
 * efeito quando o URL muda, o mesmo idioma do `desistidoEm` da sondagem.
 */
export function EcraDoAssistente() {
  const busca = useSearch({ from: "/app/assistente" });
  // `from` é o **caminho** da rota e não o id dela: o `useSearch` acima lê por
  // id (`/app/...`) e o `useNavigate` tipa-se pelo caminho.
  const navegar = useNavigate({ from: "/assistente" });
  const aberta = busca.conversa ?? null;
  const idLista = useId();

  const conversas = useConversas();
  const { consulta, emCurso, desistiu, retomar } = useConversa(aberta);
  const abrir = useAbrirConversa();
  const perguntar = usePerguntar();
  const apagar = useApagarConversa();

  const [rascunho, setRascunho] = useState("");
  const [recusaEm, setRecusaEm] = useState<{
    readonly conversa: string | null;
    readonly recusa: Recusa;
  } | null>(null);
  const idDoCompositor = useId();

  const aEnviar = abrir.isPending || perguntar.isPending;
  const recusa = recusaEm !== null && recusaEm.conversa === aberta ? recusaEm.recusa : null;

  const focarCompositor = () => {
    // Por `id` e não por `ref` (ver o `Compositor`): nesta versão do React um
    // `ref` passado a um primitivo do shadcn não chega ao DOM.
    const campo = document.getElementById(idDoCompositor);
    if (campo instanceof HTMLTextAreaElement) campo.focus();
  };

  const novaConversa = () => {
    void navegar({ search: {} });
    focarCompositor();
  };

  const enviar = (pergunta: string) => {
    if (aberta === null) {
      abrir.mutate(pergunta, {
        onSuccess: (conversa) => {
          setRascunho("");
          setRecusaEm(null);
          void navegar({ search: { conversa: conversa.id } });
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
          setRascunho("");
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

  const apagarConversa = (id: string) => {
    apagar.mutate(id, {
      onSuccess: () => {
        // Sai-se primeiro: a entrada velha da cache morre pelo `gcTime` e não
        // por um `removeQueries` que o observador ainda aberto refaria.
        if (id === aberta) void navegar({ search: {} });
      },
    });
  };

  const painelDeConversas = (aoNavegar?: () => void) => (
    <PainelDeConversas
      conversas={conversas}
      ativa={aberta}
      aApagar={apagar.isPending ? apagar.variables : null}
      erroAoApagar={apagar.isError ? mensagemDeErro(apagar.error) : null}
      aoApagar={apagarConversa}
      aoNavegar={aoNavegar}
      aoNovaConversa={() => {
        aoNavegar?.();
        novaConversa();
      }}
    />
  );

  const conversaNaoExiste = consulta.isError && isApiError(consulta.error) && consulta.error.status === 404;

  return (
    <section className="flex h-[calc(100dvh_-_var(--spacing-cabecalho))] w-full min-w-0">
      <h1 className="sr-only">{textos.ecra.titulo}</h1>

      <aside
        aria-labelledby={idLista}
        className="hidden w-72 shrink-0 flex-col border-r border-border bg-surface md:flex"
      >
        <header className="flex h-cabecalho shrink-0 items-center justify-between gap-2 border-b border-border px-celula-x">
          <h2 id={idLista} className={CLASSE_MICROROTULO}>
            {textos.lista.titulo}
          </h2>
          <Button asChild variant="outline" size="sm">
            <Link to="/assistente" search={{}} onClick={focarCompositor}>
              <Plus aria-hidden="true" />
              {textos.ecra.novaConversa}
            </Link>
          </Button>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto">{painelDeConversas()}</div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-cabecalho shrink-0 items-center gap-2 border-b border-border bg-background px-2 md:px-celula-x">
          <GavetaDeConversas>{(fechar) => painelDeConversas(fechar)}</GavetaDeConversas>
          <h2 className="min-w-0 flex-1 truncate text-sm font-semibold">
            {consulta.data?.title ?? textos.ecra.novaConversa}
          </h2>
          {/* Só o ícone abaixo de `md`: a coluna com o botão escrito está
              escondida, e o título da barra já diz «Nova conversa» quando não
              há nenhuma aberta — a palavra duas vezes a 8px de distância era o
              que a fotografia a 360px mostrou. O nome fica para quem ouve. */}
          <Button asChild variant="outline" size="icon" className="md:hidden">
            <Link
              to="/assistente"
              search={{}}
              title={textos.ecra.novaConversa}
              onClick={focarCompositor}
            >
              <Plus aria-hidden="true" />
              <span className="sr-only">{textos.ecra.novaConversa}</span>
            </Link>
          </Button>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto overscroll-y-contain">
          {aberta === null ? (
            <EstadoInicial
              aoEscolher={(pergunta) => {
                setRascunho(pergunta);
                focarCompositor();
              }}
            />
          ) : null}

          {aberta !== null && consulta.isPending ? <EsqueletoDoFio /> : null}

          {conversaNaoExiste ? (
            <div className="mx-auto w-full max-w-4xl">
              <EstadoVazio
                icone={MessageSquareOff}
                titulo={textos.fio.naoExisteTitulo}
                descricao={textos.fio.naoExisteCorpo}
              >
                <Button asChild variant="outline">
                  <Link to="/assistente" search={{}}>
                    {textos.ecra.novaConversa}
                  </Link>
                </Button>
              </EstadoVazio>
            </div>
          ) : null}

          {consulta.isError && !conversaNaoExiste ? (
            <div className="mx-auto w-full max-w-4xl">
              <ErroAoCarregar
                titulo={textos.fio.erroAoCarregar}
                mensagem={mensagemDeErro(consulta.error)}
                aoTentarOutraVez={() => {
                  void consulta.refetch();
                }}
              />
            </div>
          ) : null}

          {aberta !== null && consulta.data !== undefined ? (
            <FioDeTurnos conversa={consulta.data} desistiu={desistiu} aoRetomar={retomar} />
          ) : null}
        </div>

        <Compositor
          id={idDoCompositor}
          valor={rascunho}
          aoMudar={setRascunho}
          aoEnviar={enviar}
          aEnviar={aEnviar}
          bloqueado={emCurso}
          recusa={recusa}
          aoRepetir={() => {
            enviar(rascunho.trim());
          }}
          aoNovaConversa={novaConversa}
        />
      </div>
    </section>
  );
}
