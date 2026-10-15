import { CLASSE_MICROROTULO } from "@/components/tabela";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

import type { Recusa } from "../recusas";
import { PERGUNTA_MAXIMA } from "../schemas";
import { textos } from "../textos";
import { BannerDeRecusa } from "./banner-de-recusa";

/**
 * O compositor: um `<form>` com rótulo acima, contador à direita, a área de
 * texto e o botão. Enter envia; Shift+Enter muda de linha.
 *
 * ## Bloqueado, mas com foco
 *
 * Enquanto há um turno em curso o compositor não envia (o servidor recusaria
 * com 409 `resposta_pendente`), e a forma de o dizer é `readOnly` +
 * `aria-disabled`, **não** `disabled`. Um `<textarea disabled>` não recebe foco,
 * e o foco tem de voltar aqui depois de enviar — senão quem navega por teclado
 * é largado no `<body>` a cada pergunta. Com `readOnly` o campo mantém o foco,
 * fica visivelmente inerte, o leitor de ecrã anuncia-o como indisponível, e a
 * frase de ajuda diz porquê; quando a resposta chega, a pessoa já está a
 * escrever a seguinte.
 *
 * ## O `id` entra por propriedade, e é por ele que o ecrã foca
 *
 * Por `id` e não por `ref`, pela razão medida no Contar: os primitivos do
 * shadcn são funções que espalham props e nesta versão do React um `ref`
 * passado a uma função **não chega ao DOM**. A primeira versão disto era um
 * `forwardRef`, compilava, e a sonda do 503 trouxe `activeElement: BODY` — um
 * foco que ninguém mede e que não acontece.
 *
 * ## O contador conta o que o servidor aceita
 *
 * `PERGUNTA_MAXIMA` é a coluna (ADR 0027, decisão 1) e o `maxLength` do campo é
 * o mesmo número: o 400 de validação continua a existir, mas só para quem o
 * contornar. O contador é mono e tabular, como todo o número deste produto, e
 * tem um nome acessível porque "12/2000" sozinho não diz o que conta.
 */
export function Compositor({
  id,
  valor,
  aoMudar,
  aoEnviar,
  aEnviar,
  bloqueado,
  recusa,
  aoRepetir,
  aoNovaConversa,
}: {
  /** O `id` do `<textarea>`: é por ele que o ecrã devolve o foco. */
  readonly id: string;
  readonly valor: string;
  readonly aoMudar: (valor: string) => void;
  readonly aoEnviar: (pergunta: string) => void;
  /** O `POST` está em voo. */
  readonly aEnviar: boolean;
  /** Há um turno em curso: não se envia, mas escreve-se. */
  readonly bloqueado: boolean;
  readonly recusa: Recusa | null;
  readonly aoRepetir: () => void;
  readonly aoNovaConversa: () => void;
}) {
  const idContador = `${id}-contador`;
  const idAjuda = `${id}-ajuda`;
  const pergunta = valor.trim();
  const podeEnviar = pergunta !== "" && pergunta.length <= PERGUNTA_MAXIMA && !aEnviar && !bloqueado;

  const submeter = () => {
    if (!podeEnviar) return;
    aoEnviar(pergunta);
  };

  return (
    <form
      className="shrink-0 border-t border-border bg-surface px-celula-x pt-3"
      // Em baixo, `max(…)` entre o ritmo normal e a barra de gestos do
      // telemóvel: o compositor é full-bleed no fundo do ecrã, e o valor só o
      // aparelho o conhece — logo é `env()` e não um token (é o idioma da
      // gaveta do shell). Em desktop é zero e fica o `pb-3`.
      style={{ paddingBottom: "max(0.75rem, env(safe-area-inset-bottom))" }}
      onSubmit={(evento) => {
        evento.preventDefault();
        submeter();
      }}
    >
      <div className="mx-auto flex w-full max-w-4xl flex-col gap-2">
        {recusa === null ? null : (
          <BannerDeRecusa recusa={recusa} aoRepetir={aoRepetir} aoNovaConversa={aoNovaConversa} />
        )}

        <div className="flex items-baseline justify-between gap-3">
          <Label htmlFor={id} className={CLASSE_MICROROTULO}>
            {textos.compositor.rotulo}
          </Label>
          <span data-numeric aria-hidden="true" className="text-xs text-muted-foreground">
            {`${String(valor.length)}/${String(PERGUNTA_MAXIMA)}`}
          </span>
          <span id={idContador} className="sr-only">
            {textos.compositor.contadorAcessivel(valor.length, PERGUNTA_MAXIMA)}
          </span>
        </div>

        <Textarea
          id={id}
          name="question"
          value={valor}
          rows={2}
          maxLength={PERGUNTA_MAXIMA}
          readOnly={bloqueado}
          aria-disabled={bloqueado ? true : undefined}
          aria-describedby={`${idAjuda} ${idContador}`}
          enterKeyHint="send"
          autoComplete="off"
          className="max-h-48 min-h-controlo resize-none aria-disabled:opacity-50"
          onChange={(evento) => {
            aoMudar(evento.target.value);
          }}
          onKeyDown={(evento) => {
            // `isComposing`: um Enter a fechar uma composição de IME não é um
            // envio.
            if (evento.key !== "Enter" || evento.shiftKey || evento.nativeEvent.isComposing) {
              return;
            }
            evento.preventDefault();
            submeter();
          }}
        />

        <div className="flex items-center justify-between gap-3">
          <p id={idAjuda} className="text-xs text-pretty text-muted-foreground">
            {bloqueado ? textos.compositor.bloqueado : textos.compositor.atalho}
          </p>
          <Button type="submit" disabled={!podeEnviar} aria-busy={aEnviar} className="shrink-0">
            {aEnviar ? textos.compositor.aPerguntar : textos.compositor.perguntar}
          </Button>
        </div>
      </div>
    </form>
  );
}
