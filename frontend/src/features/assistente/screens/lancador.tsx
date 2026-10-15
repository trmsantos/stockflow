import { useRouterState } from "@tanstack/react-router";
import { BotMessageSquare } from "lucide-react";
import { useState, useSyncExternalStore } from "react";

import { Button } from "@/components/ui/button";
import { Sheet, SheetTrigger } from "@/components/ui/sheet";

import { PainelDoAssistente, type ConversaDoPainel } from "../components/painel-do-assistente";
import { textos } from "../textos";

/** O caminho da página inteira: lá o lançador não existe, porque já lá está. */
const CAMINHO_DA_PAGINA = "/assistente";

/**
 * A altura da barra fixa em baixo do ecrã onde se está, se ele tiver uma.
 *
 * Um ecrã que cole uma barra ao fundo da janela (hoje só o Receber, com a
 * acção de «Novo documento») marca-a com `data-barra-inferior`, e o lançador
 * sobe a altura dela em vez de a tapar. É um contrato de um atributo: o ecrã
 * não sabe que há um lançador e o lançador não sabe que ecrãs existem.
 *
 * Mede-se pelo DOM e não por rota porque os ecrãs carregam tarde
 * (`lazyRouteComponent`): no instante em que o caminho muda a barra ainda não
 * está montada, e é a mutação do `<body>` que diz quando passa a estar. O
 * `useSyncExternalStore` é a forma certa de ler uma coisa de fora do React sem
 * um `setState` dentro de um efeito.
 *
 * A leitura do layout (`offsetHeight`) acontece **nos callbacks** — depois de
 * uma mutação ou de um `resize`, fora do render — e o snapshot devolve o valor
 * guardado: um `getSnapshot` corre em cada render, e medir o DOM lá dentro é
 * forçar um layout por render. Ao subscrever remede-se logo e, se o valor for
 * outro, notifica-se pelo mesmo caminho de uma mutação — o primeiro render
 * saiu com o valor guardado, que pode ser o de outro ecrã.
 */
let alturaGuardada = 0;

function medirABarraInferior(): void {
  alturaGuardada = document.querySelector<HTMLElement>("[data-barra-inferior]")?.offsetHeight ?? 0;
}

function subscreverABarraInferior(aoMudar: () => void): () => void {
  const remedir = () => {
    const antes = alturaGuardada;
    medirABarraInferior();
    if (antes !== alturaGuardada) aoMudar();
  };
  const observador = new MutationObserver(remedir);
  observador.observe(document.body, { childList: true, subtree: true });
  window.addEventListener("resize", remedir);
  remedir();
  return () => {
    observador.disconnect();
    window.removeEventListener("resize", remedir);
  };
}

function alturaDaBarraInferior(): number {
  return alturaGuardada;
}

function semBarra(): number {
  return 0;
}

/**
 * O lançador global do assistente: um botão fixo no canto inferior direito de
 * todos os ecrãs do invólucro autenticado, que abre o assistente numa gaveta à
 * direita sobre o ecrã onde se está (ADR 0027, decisão 10, adenda).
 *
 * ## Painel, não balão
 *
 * A janela flutuante estilo widget de suporte é a estética genérica que o
 * DESIGN.md recusa, e o valor — perguntar sem sair do Stock — é o mesmo numa
 * gaveta. O botão é um controlo com borda forte sobre `surface`, não um círculo
 * com brilho; a gaveta é o `sheet` do shadcn, que dá de graça o foco preso, o
 * Escape e o foco de volta ao botão ao fechar.
 *
 * ## Onde vive o estado, e porquê
 *
 * Aberto/fechado, a conversa escolhida e o rascunho são `useState` **deste**
 * componente, que o `routes/involucro.tsx` monta no invólucro e não numa rota:
 * navegar entre páginas não o desmonta, logo o painel fica onde estava. Nada em
 * `localStorage` nem `sessionStorage` (CLAUDE.md). Trocar de estabelecimento
 * fecha-o e limpa a conversa pelo `key` que o invólucro lhe dá — o estado de um
 * estabelecimento não tem nada que sobreviver ao outro, e um `key` diz isso sem
 * um efeito a repor três estados.
 *
 * A conversa começa em `ultima`: a última da pessoa abre por omissão, e «Nova
 * conversa» começa outra. Depois da primeira pergunta passa a `aberta` com o
 * id — o painel não usa o URL (a página é que o usa, ADR 0008), porque o
 * painel está sobre um ecrã cujo URL é desse ecrã.
 *
 * ## Onde não está
 *
 * Escondido abaixo de `sm`: no telemóvel os fluxos de campo (Receber, Contar)
 * são donos da margem inferior, e aí serve a entrada do menu. Escondido na
 * própria página do assistente, que já é o assistente. E só existe neste
 * invólucro — nunca em `/entrar`, `/ativar` ou na escolha de estabelecimento,
 * que não passam por aqui.
 */
export function LancadorDoAssistente() {
  const caminho = useRouterState({ select: (estado) => estado.location.pathname });
  const subida = useSyncExternalStore(subscreverABarraInferior, alturaDaBarraInferior, semBarra);

  const [aberto, setAberto] = useState(false);
  const [escolha, setEscolha] = useState<ConversaDoPainel>({ modo: "ultima" });
  const [rascunho, setRascunho] = useState("");

  const naPagina = caminho === CAMINHO_DA_PAGINA || caminho.startsWith(`${CAMINHO_DA_PAGINA}/`);
  if (naPagina) return null;

  return (
    <Sheet open={aberto} onOpenChange={setAberto}>
      <SheetTrigger asChild>
        <Button
          type="button"
          variant="outline"
          className="fixed right-4 z-20 hidden h-controlo gap-2 border-border-strong bg-surface px-3 shadow-lg sm:inline-flex"
          // O ritmo de 16px mais a barra do ecrã, se houver: a altura dela só o
          // DOM a sabe, logo é um `calc` e não uma classe.
          style={{ bottom: `calc(var(--spacing) * 4 + ${String(subida)}px)` }}
        >
          <BotMessageSquare aria-hidden="true" />
          {textos.painel.titulo}
        </Button>
      </SheetTrigger>

      <PainelDoAssistente
        escolha={escolha}
        aoEscolher={setEscolha}
        rascunho={rascunho}
        aoMudarRascunho={setRascunho}
        aoFechar={() => {
          setAberto(false);
        }}
      />
    </Sheet>
  );
}
