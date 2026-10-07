import { CircleAlert, TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";

/**
 * O banner de uma recusa ou de uma instrução, no fluxo do formulário.
 *
 * ## Os três papéis da cor, e porque o texto não é da cor do estado
 *
 * O DESIGN.md §2 dá a cada cor de estado três papéis e proíbe um quarto: a cor
 * é **texto e ícone**, o `-surface` é o **preenchimento** do banner e o
 * `-border` é a **borda**. O texto por cima do preenchimento é `foreground` e
 * nunca a cor de estado — sobre a própria tinta ela não tem contraste. Aqui a
 * cor fica portanto só no ícone, e o que comunica a gravidade a quem não a
 * distingue é a frase.
 *
 * ## Dois tons e não três, e a diferença é a ação
 *
 * `danger` é "isto não aconteceu e não há nada a fazer com este formulário":
 * credenciais recusadas, convite inválido. `warning` é "isto não aconteceu
 * **ainda** e o passo seguinte é teu": o convite que exige sessão, o convite de
 * outra conta, a conta temporariamente bloqueada. A distinção não é estética —
 * é a diferença entre um beco e uma instrução, e é a única coisa que o ícone
 * acrescenta ao texto.
 *
 * Não há tom `success`: a única coisa boa que pode acontecer nestes ecrãs é
 * entrar, e quando isso acontece o ecrã deixa de existir.
 *
 * Os dois tons escolhem-se com ternários e não com um `Record` indexado por
 * variável: com dois membros o ternário é exaustivo por construção, e o
 * `security/detect-object-injection` do `eslint.config.js` recusa — e bem — um
 * `OBJETO[chave]` com chave dinâmica.
 */
export type TomDoAviso = "danger" | "warning";

export function Aviso({
  tom,
  titulo,
  mensagem,
  children,
}: {
  readonly tom: TomDoAviso;
  readonly titulo: string;
  /**
   * A frase do servidor, já pronta para mostrar. **Não se reescreve aqui**: o
   * `detail` do backend já diz o passo seguinte, e `credenciais_invalidas` é
   * genérico de propósito — dizer mais confirmava a um estranho quais os emails
   * são clientes.
   */
  readonly mensagem: string;
  /** A ação, quando o tom é `warning` e há uma. */
  readonly children?: ReactNode;
}) {
  const Icone = tom === "danger" ? CircleAlert : TriangleAlert;
  const tinta =
    tom === "danger"
      ? "border-danger-border bg-danger-surface"
      : "border-warning-border bg-warning-surface";
  const corDoIcone = tom === "danger" ? "text-danger" : "text-warning";

  return (
    // O `role="alert"` vem do primitivo: quem submete e falha ouve a frase sem
    // ter de ir procurá-la.
    <Alert className={tinta}>
      <Icone aria-hidden="true" className={corDoIcone} />
      <AlertTitle>{titulo}</AlertTitle>
      <AlertDescription className="flex flex-col items-start gap-3 text-foreground">
        <span className="text-pretty">{mensagem}</span>
        {children}
      </AlertDescription>
    </Alert>
  );
}
