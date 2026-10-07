import { LogOut } from "lucide-react";

import { Button } from "@/components/ui/button";

import { useSair } from "../api";
import { mensagemDaRecusa } from "../erros";
import { textos } from "../textos";

/**
 * Terminar sessão, a partir do ramo público.
 *
 * Aparece em três sítios e por três razões diferentes, o que é precisamente a
 * razão para ser um componente: no seletor de estabelecimento (entrou e quer
 * sair), no `sem_estabelecimento` (entrou numa conta que não dá acesso a nada,
 * e sair é a **única** ação possível) e no `convite_de_outra_conta` (a sessão é
 * de outra conta e sair é o passo que o servidor pede).
 *
 * O rótulo entra por propriedade e é obrigatório nos dois últimos casos, porque
 * "Terminar sessão" e "Sair e entrar com a conta convidada" são a mesma
 * operação com instruções diferentes — e é a instrução que diz o que acontece a
 * seguir.
 *
 * Variante `outline` e não `ghost`: no `sem_estabelecimento` e no convite de
 * outra conta este botão é a **única** saída do ecrã, e um botão fantasma num
 * fundo preto não parece um botão. A fronteira vem do `border-strong`, por uma
 * regra do `base.css` que vale para todos os `outline` — um controlo delimitado
 * com o separador decorativo é um bug de acessibilidade (DESIGN.md §2).
 */
export function BotaoDeSair({ rotulo }: { readonly rotulo: string }) {
  const sair = useSair();

  return (
    <div className="flex flex-col items-start gap-1.5">
      <Button
        type="button"
        variant="outline"
        className="h-controlo"
        disabled={sair.isPending}
        aria-busy={sair.isPending}
        onClick={() => {
          sair.mutate();
        }}
      >
        <LogOut aria-hidden="true" />
        {sair.isPending ? textos.accoes.aSair : rotulo}
      </Button>
      {sair.isError ? (
        // Um logout que falha é quase sempre rede. Dizê-lo em texto, aqui, em
        // vez de deixar o botão a não fazer nada.
        <p role="alert" className="text-sm text-danger">
          {mensagemDaRecusa(sair.error)}
        </p>
      ) : null}
    </div>
  );
}
