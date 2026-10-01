import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

/**
 * O estado vazio, com ação.
 *
 * Existe como componente e não como JSX repetido porque "o que aparece quando
 * não há nada?" é **uma das perguntas da sessão 0**, logo o vazio é tanto
 * produto como a lista cheia — e três vazios desenhados em três sítios
 * divergem na primeira correção. A ação é obrigatória por construção: um vazio
 * sem saída é um beco, e quem está em pé na cozinha não tem onde clicar a
 * seguir.
 *
 * O ícone é decoração (`aria-hidden`): quem lê por áudio ouve o título.
 */
export function EstadoVazio({
  icone: Icone,
  titulo,
  descricao,
  children,
}: {
  readonly icone: LucideIcon;
  readonly titulo: string;
  readonly descricao: string;
  /** A ação. Um `<Button>`, um `<Link>` dentro de um, ou os dois. */
  readonly children: ReactNode;
}) {
  return (
    <div className="flex flex-col items-start gap-3 px-4 py-8">
      <Icone aria-hidden="true" className="size-6 text-muted-foreground" />
      <div className="flex flex-col gap-1">
        <p className="font-medium">{titulo}</p>
        <p className="text-pretty text-sm text-muted-foreground">{descricao}</p>
      </div>
      {children}
    </div>
  );
}
