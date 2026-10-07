import { Check, Copy, KeyRound, X } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

import { nomeDoPapel, type Convite } from "../schemas";

/**
 * O link de activação, **a única vez que ele existe** — e o painel que este ecrã
 * existe para desenhar bem.
 *
 * ## Porque é que isto não é um "toast de sucesso"
 *
 * O `ConviteCriadoOut` traz o `fragmento` e o `ConviteOut` da listagem **não traz
 * token nenhum, nem forma de o ter**: o que a tabela guarda é um SHA-256, e um
 * token mostrável depois teria de ser guardado em claro (ADR 0010). Isto é uma
 * chave de API: sai uma vez e nunca mais. Logo o pior desenho possível é uma
 * notificação que se fecha sozinha, e o segundo pior é um painel que desaparece
 * ao criar o convite seguinte.
 *
 * Daí as quatro propriedades deste componente, e cada uma fecha um modo de
 * perder o segredo por acidente:
 *
 *  1. **só sai por acção explícita** ("Já guardei"), nunca por tempo nem por
 *     navegação dentro do painel;
 *  2. **o valor está num `<input readOnly>` e não num parágrafo**: é seleccionável
 *     com um triplo clique e com teclado, logo o botão de copiar é uma
 *     conveniência e não o único caminho. Num browser sem `navigator.clipboard`
 *     — ou numa origem não segura, onde ele não existe — continua a dar;
 *  3. **a consequência está escrita**, não implícita: "este link não volta a
 *     aparecer; se o perderes, reenvia". É a frase que diz o que fazer no dia em
 *     que já aconteceu;
 *  4. **o email de quem foi convidado viaja ao lado do link.** Com dois convites
 *     criados seguidos, um link sem nome é um link que se entrega à pessoa
 *     errada — e entregar um convite à pessoa errada é dar-lhe uma pertença.
 *
 * ## O link é composto aqui, e é por isso que o backend manda um fragmento
 *
 * `${origin}/ativar#${fragmento}`. Quem conhece a origem da SPA é a SPA: o
 * backend não tem essa configuração, e em dev, em CI e em produção ela é
 * diferente (ADR 0010, ponto 1). O segredo vai **depois do `#`** porque o
 * fragmento não chega ao servidor, não entra no log de acesso do proxy, não
 * viaja em `Referer` e um pre-fetch do cliente de email não consegue queimar um
 * token de uso único.
 *
 * ## Não há email a ser enviado, e o ecrã diz-no
 *
 * Zero eventos e zero Celery no v1, porque não há consumidor da outbox (ADR
 * 0010). Quem convida **entrega o link à mão**. Um ecrã que não diga isto deixa
 * o dono à espera de um email que nunca sai, e a pessoa convidada sem nada.
 */

/** O caminho onde o link aterra. É a rota `/ativar` do ramo público. */
const ROTA_DE_ATIVACAO = "/ativar";

/**
 * O que acabou de sair do servidor: o convite e o segredo.
 *
 * Um tipo próprio e não o `ConviteCriado` do `schemas.ts` porque o ecrã
 * acrescenta uma coisa que o contrato não tem — a razão pela qual este segredo
 * existe (criado ou reenviado) —, e ela muda a frase: num reenvio há um link
 * **anterior** que deixou de funcionar, e isso tem de ser dito.
 */
export interface SegredoEmitido {
  readonly chave: string;
  readonly convite: Convite;
  readonly fragmento: string;
  readonly origem: "criado" | "reenviado";
}

export function SegredoDoConvite({
  segredo,
  aoGuardar,
}: {
  readonly segredo: SegredoEmitido;
  readonly aoGuardar: () => void;
}) {
  const [copiado, setCopiado] = useState(false);
  const [falhouACopia, setFalhouACopia] = useState(false);

  const idDoCampo = `link-de-convite-${segredo.chave}`;
  const link = `${window.location.origin}${ROTA_DE_ATIVACAO}#${segredo.fragmento}`;

  async function copiar() {
    try {
      await navigator.clipboard.writeText(link);
      setCopiado(true);
      setFalhouACopia(false);
    } catch {
      // A área de transferência não está disponível (origem não segura, ou
      // permissão recusada). Não é um erro deste ecrã e não se mostra como tal:
      // o valor está à vista num campo seleccionável, e a instrução é usá-lo.
      setCopiado(false);
      setFalhouACopia(true);
    }
  }

  return (
    // `warning` e não `success`: o tom certo não é "feito" — é "o passo seguinte
    // é teu, e é agora". O preenchimento é o `-surface` do estado e o texto é
    // `foreground`, que é o segundo dos três papéis do DESIGN.md §2; a cor de
    // estado fica no ícone.
    <li className="flex flex-col gap-3 rounded-xl border border-warning-border bg-warning-surface p-celula-x">
      <div className="flex items-start gap-2">
        <KeyRound aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-warning" />
        <div className="flex min-w-0 flex-col gap-1">
          <p className="text-sm font-semibold">
            {segredo.origem === "criado"
              ? "Convite criado. Entregue este link a quem convidou."
              : "Link novo. O link anterior deixou de funcionar."}
          </p>
          <p className="text-pretty text-sm">
            Para{" "}
            <span className="font-mono" translate="no">
              {segredo.convite.email}
            </span>
            , como{" "}
            {nomeDoPapel(segredo.convite.papel)}
            {segredo.convite.nome === "" ? null : <> ({segredo.convite.nome})</>}. Não é enviado
            nenhum email: copie o link e entregue-o você.
          </p>
        </div>
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor={idDoCampo} className="text-xs font-bold tracking-microrotulo uppercase">
          Link de activação
        </Label>
        <div className="flex flex-col gap-2 sm:flex-row sm:items-start">
          <Input
            id={idDoCampo}
            // `readOnly` e não `disabled`: um campo desactivado não é
            // seleccionável nem focável, e este valor tem de poder ser copiado à
            // mão quando o botão não serve.
            readOnly
            value={link}
            // `type="text"` e não `url`: um `type=url` convida o browser a
            // sugerir URLs visitados, e este é um segredo de uso único.
            type="text"
            spellCheck={false}
            autoComplete="off"
            // O link **é** o segredo: nem o corrector nem o tradutor lhe tocam.
            // Um token "traduzido" é um token que não casa com nada, e a recusa
            // que isso produz é a genérica — indistinguível de um link expirado.
            translate="no"
            onFocus={(evento) => {
              // Focar selecciona tudo: quem chega aqui por Tab copia com um
              // Ctrl+C e não tem de caçar as pontas de uma linha de 90
              // caracteres.
              evento.currentTarget.select();
            }}
            className="h-controlo min-w-0 flex-1 bg-background font-mono text-xs"
          />
          <Button
            type="button"
            variant="outline"
            className="h-controlo shrink-0"
            aria-live="polite"
            onClick={() => {
              void copiar();
            }}
          >
            {copiado ? (
              <Check aria-hidden="true" className="text-success" />
            ) : (
              <Copy aria-hidden="true" />
            )}
            {copiado ? "Copiado" : "Copiar link"}
          </Button>
        </div>
        {falhouACopia ? (
          <p className="text-sm text-muted-foreground">
            O browser não deixou copiar automaticamente. Seleccione o texto do campo e copie com{" "}
            {/* `&nbsp;` no atalho: "Ctrl+C" partido ao fim da linha deixa de ser
                um atalho e passa a ser duas letras perdidas. */}
            <span className="whitespace-nowrap">Ctrl&nbsp;+&nbsp;C</span>.
          </p>
        ) : null}
      </div>

      <div className="flex flex-col items-start gap-2 border-t border-warning-border pt-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-pretty text-sm">
          <strong className="font-semibold">Este link não volta a aparecer.</strong> Se o perder,
          use <em>Reenviar</em> na linha do convite — isso cria um link novo e invalida este.
        </p>
        <Button
          type="button"
          variant="secondary"
          className="h-controlo shrink-0"
          onClick={aoGuardar}
        >
          <X aria-hidden="true" />
          Já guardei
        </Button>
      </div>
    </li>
  );
}
