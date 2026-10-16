import { BotMessageSquare, CircleAlert, RotateCcw } from "lucide-react";
import { useId } from "react";

import { IndicadorDeCarga } from "@/components/indicador-de-carga";
import { CLASSE_MICROROTULO } from "@/components/tabela";
import { textos as textosPartilhados } from "@/components/textos";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { formatTime } from "@/lib/format";

import type { Mensagem } from "../schemas";
import { textos } from "../textos";
import { fraseDoErroDaMensagem, rotuloDaTool } from "../vocabulario";
import { Fontes } from "./fontes";

/**
 * Um turno: a pergunta da pessoa à direita, num bloco com superfície própria;
 * a resposta do assistente à esquerda, como texto sobre a tela, assinada pelo
 * ícone do lançador.
 *
 * ## Quem pergunta e quem responde lê-se sem ler
 *
 * O dono do produto apanhou a versão anterior a não distinguir os dois lados
 * (ADR 0028): pergunta e resposta eram texto sobre o mesmo fundo, e a única
 * diferença era o alinhamento e um cinzento. Agora cada lado tem sinais que
 * não dependem uns dos outros:
 *
 *  - a **pergunta** está à direita, num bloco `surface-2` com canto de 6px
 *    (`rounded-md`: um painel pequeno, não um balão de messenger), limitado a
 *    dois terços do fio, com o nome de quem perguntou e a hora em mono por
 *    cima. O `surface-2` é a pior superfície de cada paleta (DESIGN.md §2),
 *    logo o `foreground` por cima está medido nas três. O texto dentro do
 *    bloco alinha à esquerda: é o bloco que está à direita, não as palavras;
 *  - a **resposta** está à esquerda, sem superfície — é o conteúdo, e a tela é
 *    dela —, assinada pelo ícone `BotMessageSquare` em `primary` (o mesmo do
 *    lançador e do estado inicial), pelo microrótulo «Assistente» e pela hora
 *    a que fechou. O acento ciano aqui é identidade, não estado: marca a voz
 *    do produto, e um ícone de 16px por turno não compete com os sinais;
 *  - entre os dois lados, 12px; entre turnos, 16px de cada lado da régua de
 *    1px. A proximidade agrupa pergunta e resposta, e a régua separa os turnos
 *    para uma conversa longa não virar uma parede.
 *
 * Para quem ouve, cada lado é um `role="group"` com nome próprio («Pergunta de
 * Ana», «Resposta do assistente»), e a ordem do DOM é a ordem de leitura. O
 * nome visível da pessoa está `aria-hidden` porque já é o nome do grupo —
 * dizê-lo duas vezes seguidas é ruído.
 *
 * ## Texto, e só texto
 *
 * A resposta sai em `whitespace-pre-wrap`: as quebras de linha do modelo ficam,
 * e **nada** é interpretado — nem Markdown, nem HTML. O output de um modelo é
 * texto não confiável (CLAUDE.md) e o `dangerouslySetInnerHTML` está proibido
 * pelo lint; um Markdown renderizado era a mesma porta com outro nome.
 *
 * ## O estado é o desenho do lado da resposta, nos quatro casos
 *
 *  - `pendente` e `a_responder`: a identidade do assistente, os três traços e
 *    a frase da última tool — o que a tarefa já gravou no rasto (ADR 0027,
 *    decisão 3) —, numa região `aria-live` que anuncia a resposta quando ela
 *    substituir a frase;
 *  - a **desistência** aos 90 s: um aviso com o botão que volta a sondar, e os
 *    traços apagam-se (um indicador aceso afirma que alguém está a olhar);
 *  - `respondida`: o texto;
 *  - `erro`: o trilho vermelho na aresta **do bloco do assistente**, a palavra
 *    e a frase do `error_code`.
 *
 * O bloco do assistente reserva a coluna do trilho em todos os turnos e só a
 * pinta no erro: todos os trilhos ficam na mesma vertical, e um trilho em
 * todas as respostas seria uma coluna pintada que não distingue nada
 * (DESIGN.md §3).
 */
export function Turno({
  mensagem,
  ultimo,
  desistiu,
  aoRetomar,
}: {
  readonly mensagem: Mensagem;
  /** O último da conversa: é o único cuja resposta nova se anuncia. */
  readonly ultimo: boolean;
  /** O polling desistiu neste turno (ADR 0027, decisão 3). */
  readonly desistiu: boolean;
  readonly aoRetomar: () => void;
}) {
  const idPergunta = useId();
  const emCurso = mensagem.status === "pendente" || mensagem.status === "a_responder";
  const falhou = mensagem.status === "erro";
  const ultimaTool = mensagem.tool_calls.at(-1);
  const fraseDeEspera =
    ultimaTool === undefined
      ? textos.fio.aConsultar
      : textos.fio.aConsultarTool(rotuloDaTool(ultimaTool.name));
  const duracaoMs =
    mensagem.started_at !== null && mensagem.finished_at !== null
      ? Math.max(0, Date.parse(mensagem.finished_at) - Date.parse(mensagem.started_at))
      : null;

  return (
    <li
      aria-labelledby={idPergunta}
      className="flex flex-col gap-3 border-b border-border px-celula-x py-4"
    >
      <div
        role="group"
        aria-label={textos.fio.perguntaDe(mensagem.asked_by_name)}
        className="flex max-w-2/3 min-w-0 flex-col items-end gap-1 self-end"
      >
        <p className="flex items-baseline gap-2 text-xs">
          <span aria-hidden="true" className="font-semibold">
            {mensagem.asked_by_name}
          </span>
          {mensagem.started_at === null ? null : (
            <time dateTime={mensagem.started_at} data-numeric className="text-muted-foreground">
              {formatTime(mensagem.started_at)}
            </time>
          )}
        </p>
        <p
          id={idPergunta}
          className="rounded-md bg-surface-2 px-3 py-2 text-sm text-pretty break-words whitespace-pre-wrap"
        >
          {mensagem.question}
        </p>
      </div>

      <div
        role="group"
        aria-label={textos.fio.respostaDoAssistente}
        className="relative flex flex-col pl-4"
      >
        {falhou ? (
          <span aria-hidden="true" className="absolute inset-y-0 left-0 w-trilho bg-danger" />
        ) : null}

        <p className="flex items-center gap-2">
          <BotMessageSquare aria-hidden="true" className="size-4 shrink-0 text-primary" />
          <span className={CLASSE_MICROROTULO}>{textos.fio.assistente}</span>
          {mensagem.finished_at === null ? null : (
            <time
              dateTime={mensagem.finished_at}
              data-numeric
              className="text-xs text-muted-foreground"
            >
              {formatTime(mensagem.finished_at)}
            </time>
          )}
        </p>

        {/* A mesma região nos quatro estados, para o `aria-live` ver a frase de
            espera virar resposta — se o elemento mudasse, nada seria anunciado. */}
        <div className="mt-2 flex flex-col gap-2" aria-live={ultimo ? "polite" : undefined}>
          {emCurso && !desistiu ? (
            <p className="flex items-center gap-2 text-sm text-muted-foreground">
              <IndicadorDeCarga rotulo={fraseDeEspera} />
              <span aria-hidden="true">{fraseDeEspera}</span>
            </p>
          ) : null}

          {emCurso && desistiu ? (
            <Alert className="max-w-2xl border-warning-border bg-warning-surface">
              <CircleAlert aria-hidden="true" className="text-warning" />
              <AlertTitle>{textos.fio.desistiuTitulo}</AlertTitle>
              <AlertDescription className="flex flex-col items-start gap-2">
                <span className="text-pretty">{textos.fio.desistiuCorpo}</span>
                <Button type="button" variant="outline" onClick={aoRetomar}>
                  <RotateCcw aria-hidden="true" />
                  {textosPartilhados.tentarOutraVez}
                </Button>
              </AlertDescription>
            </Alert>
          ) : null}

          {mensagem.status === "respondida" ? (
            mensagem.answer === "" ? (
              <p className="text-sm text-muted-foreground">{textos.fio.semResposta}</p>
            ) : (
              <p className="max-w-2xl text-sm text-pretty break-words whitespace-pre-wrap">
                {mensagem.answer}
              </p>
            )
          ) : null}

          {falhou ? (
            <p className="flex max-w-2xl items-start gap-1.5 text-sm">
              <CircleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-danger" />
              <span className="text-pretty">
                <span className="font-semibold text-danger">{textos.fio.erroTitulo}</span>
                {". "}
                {fraseDoErroDaMensagem(mensagem.error_code)}
              </span>
            </p>
          ) : null}
        </div>

        {emCurso ? null : <Fontes toolCalls={mensagem.tool_calls} duracaoMs={duracaoMs} />}
      </div>
    </li>
  );
}
