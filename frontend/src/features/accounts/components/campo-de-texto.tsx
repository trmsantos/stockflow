import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

/**
 * Um campo de formulário com o rótulo **acima** e o erro **abaixo, em texto**.
 *
 * Existe como componente e não como JSX repetido por uma razão de
 * acessibilidade e não de arrumação: a ligação entre o input, o seu rótulo e a
 * sua mensagem de erro são três atributos que têm de concordar (`htmlFor`/`id`,
 * `aria-describedby`/`id`, `aria-invalid`), e três campos escritos à mão são
 * três oportunidades de os desalinhar. Aqui o `id` entra uma vez e os outros
 * dois derivam dele.
 *
 * O erro é **texto**, nunca só cor (DESIGN.md §3): a cor `text-danger` é
 * redundante com a frase, e é essa redundância que serve quem não a distingue.
 * O `role="alert"` não está no parágrafo de propósito — um `alert` por campo
 * fazia um leitor de ecrã anunciar três erros ao mesmo tempo no submit; quem
 * anuncia é o banner do topo, e o `aria-describedby` faz o campo dizer o seu
 * erro quando recebe foco, que é quando interessa.
 *
 * **Não há `autoFocus`, e é uma decisão e não um esquecimento.** O campo de
 * email de um ecrã de entrada é o caso em que o `autofocus` é mais defensável,
 * e mesmo assim o `jsx-a11y/no-autofocus` recusa-o: um foco que salta no
 * primeiro paint faz um leitor de ecrã começar a ler a meio da página, antes do
 * título que diz onde a pessoa está. A alternativa — um `ref` com `.focus()`
 * num efeito — tem exactamente o mesmo efeito para quem ouve e serve só para o
 * linter não ver, e suprimir lint não se faz nesta casa (CLAUDE.md). Quem entra
 * por teclado chega ao campo com um Tab.
 */
export function CampoDeTexto({
  id,
  rotulo,
  tipo,
  valor,
  aoMudar,
  erro,
  pista,
  autoComplete,
  desativado = false,
}: {
  readonly id: string;
  readonly rotulo: string;
  readonly tipo: "email" | "password" | "text";
  readonly valor: string;
  readonly aoMudar: (valor: string) => void;
  /** A frase do servidor ou do cliente. Ausente = campo sem erro. */
  readonly erro?: string | undefined;
  /** Uma linha de ajuda permanente, acima do erro. Opcional. */
  readonly pista?: string | undefined;
  /** Obrigatório: um campo de credencial sem isto quebra os gestores de passwords. */
  readonly autoComplete: string;
  readonly desativado?: boolean;
}) {
  const idDoErro = `${id}-erro`;
  const idDaPista = `${id}-pista`;
  const descricoes = [pista === undefined ? null : idDaPista, erro === undefined ? null : idDoErro]
    .filter((valor): valor is string => valor !== null)
    .join(" ");

  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id} className="text-sm">
        {rotulo}
      </Label>
      <Input
        id={id}
        type={tipo}
        value={valor}
        onChange={(evento) => {
          aoMudar(evento.target.value);
        }}
        disabled={desativado}
        autoComplete={autoComplete}
        // Um teclado de telemóvel capitaliza a primeira letra e corrige
        // palavras: num email e numa password as duas coisas são sabotagem.
        autoCapitalize="none"
        autoCorrect="off"
        spellCheck={false}
        aria-invalid={erro === undefined ? undefined : true}
        aria-describedby={descricoes === "" ? undefined : descricoes}
        className="h-controlo"
      />
      {pista === undefined ? null : (
        <p id={idDaPista} className="text-xs text-muted-foreground">
          {pista}
        </p>
      )}
      {erro === undefined ? null : (
        <p id={idDoErro} className="text-sm text-danger">
          {erro}
        </p>
      )}
    </div>
  );
}
