import { CircleAlert, RotateCcw } from "lucide-react";
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
 * Um turno: a pergunta, discreta e à direita; a resposta como **texto**, à
 * esquerda, com o rodapé das fontes.
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
 *  - `pendente` e `a_responder`: os três traços e a frase da última tool — o
 *    que a tarefa já gravou no rasto (ADR 0027, decisão 3) —, numa região
 *    `aria-live` que anuncia a resposta quando ela substituir a frase;
 *  - a **desistência** aos 90 s: um aviso com o botão que volta a sondar, e os
 *    traços apagam-se (um indicador aceso afirma que alguém está a olhar);
 *  - `respondida`: o texto;
 *  - `erro`: o trilho vermelho na aresta, a palavra e a frase do `error_code`.
 *
 * O trilho de 4px **só** acende no erro: um trilho em todas as respostas seria
 * uma coluna pintada que não distingue nada (DESIGN.md §3).
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
    <li aria-labelledby={idPergunta} className="relative border-b border-border px-celula-x py-4">
      {falhou ? (
        <span aria-hidden="true" className="absolute inset-y-0 left-0 w-trilho bg-danger" />
      ) : null}

      <div className="flex flex-col items-end gap-1">
        <p className={CLASSE_MICROROTULO}>
          {mensagem.asked_by_name}
          {mensagem.started_at === null ? null : ` · ${formatTime(mensagem.started_at)}`}
        </p>
        <p
          id={idPergunta}
          className="max-w-2xl text-right text-sm text-pretty break-words whitespace-pre-wrap text-muted-foreground"
        >
          <span className="sr-only">{`${textos.fio.pergunta}: `}</span>
          {mensagem.question}
        </p>
      </div>

      {/* A mesma região nos quatro estados, para o `aria-live` ver a frase de
          espera virar resposta — se o elemento mudasse, nada seria anunciado. */}
      <div className="mt-3 flex flex-col gap-2" aria-live={ultimo ? "polite" : undefined}>
        <span className="sr-only">{`${textos.fio.resposta}: `}</span>

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
    </li>
  );
}
