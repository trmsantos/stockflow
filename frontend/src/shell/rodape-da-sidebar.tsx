import { Building2, CircleAlert, LogOut } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
} from "@/components/ui/select";

import type { SessaoDoShell } from "./sessao-do-shell";

/**
 * O pé da sidebar: **o estabelecimento ativo, com troca sem sair**, e a saída da
 * conta.
 *
 * ## O que vive aqui, e o que não
 *
 * O DESIGN.md §4 separa duas coisas que parecem a mesma: o **seletor de tenant**
 * é do shell e vive aqui; o **seletor de loja** é do ecrã e fica na barra do
 * ecrã (é o `barra-de-filtros.tsx` do `inventory`). Confundi-los dava duas
 * formas de responder à mesma pergunta — "que dados estou a ver?" — em dois
 * sítios diferentes.
 *
 * ## Um `<Select>` aqui, e uma lista de botões no `/entrar`
 *
 * O `features/accounts/components/seletor-de-estabelecimento.tsx` **não** é
 * reutilizado, e a razão é de estado e não de arrumação. Lá, o clique **é** a
 * entrada: é a única coisa no ecrã, a lista está aberta porque não há mais nada
 * para mostrar, e cada linha tem 44px porque é o alvo de toque de quem acabou de
 * escrever uma password. Aqui já se está dentro: o pé da sidebar tem de mostrar
 * **onde se está** em repouso e só abrir a lista a pedido, senão a navegação
 * fica em segundo plano atrás de uma lista de estabelecimentos que muda uma vez
 * por semana. Descer o componente uma camada obrigava-o a servir os dois
 * comportamentos com uma propriedade a dizer qual — duas UIs num componente.
 *
 * O primitivo do shadcn dá o que um popover feito à mão não dá de graça:
 * fecho com Escape, clique fora, navegação por teclado, foco devolvido ao
 * botão e `aria-expanded` correcto.
 *
 * ## O estado recolhido
 *
 * Com a sidebar recolhida (56px) não cabe nome nem email, e não se finge que
 * cabe: ficam dois alvos com ícone, cada um com o seu texto para quem lê por
 * áudio (`sr-only`) e o `title` para quem usa o rato. O nome do estabelecimento
 * vai no `aria-label` do seletor, porque "qual" é a informação e não "qual
 * ícone".
 */
export function RodapeDaSidebar({
  sessao,
  id,
  recolhida = false,
}: {
  readonly sessao: SessaoDoShell;
  /**
   * Prefixo dos `id` dos controlos. **Obrigatório**: este pé renderiza duas
   * vezes no mesmo documento — na sidebar de desktop (escondida por breakpoint,
   * logo presente no DOM) e dentro da gaveta de mobile — e dois `htmlFor` iguais
   * ligam o rótulo ao controlo errado.
   */
  readonly id: string;
  readonly recolhida?: boolean;
}) {
  const { ativo, estabelecimentos, aTrocar, erroDaTroca, trocar, aSair, sair } = sessao;
  const idDoSeletor = `${id}-estabelecimento`;
  // Um estabelecimento só não é uma escolha. Fica visível (é informação) e
  // inerte (não é uma acção), que é o estado `disabled` do DESIGN.md §3.
  const soUm = estabelecimentos.length < 2;
  const nomeDoAtivo = ativo?.nome ?? "";

  return (
    <div className="flex shrink-0 flex-col gap-2 border-t border-border p-2">
      {erroDaTroca === null ? null : (
        <p
          role="alert"
          title={erroDaTroca}
          className={`flex gap-1.5 text-xs text-danger ${
            recolhida ? "justify-center" : "items-start"
          }`}
        >
          <CircleAlert aria-hidden="true" className="mt-0.5 size-3.5 shrink-0" />
          <span className={recolhida ? "sr-only" : "text-pretty"}>{erroDaTroca}</span>
        </p>
      )}

      {ativo === null ? null : (
        <div className="flex flex-col gap-1">
          <Label
            htmlFor={idDoSeletor}
            className={
              recolhida
                ? "sr-only"
                : "text-xs font-bold tracking-microrotulo text-muted-foreground uppercase"
            }
          >
            Estabelecimento
          </Label>
          <Select
            value={ativo.id}
            disabled={soUm || aTrocar}
            onValueChange={(escolhido) => {
              // Escolher o que já está activo é um POST que muda nada.
              if (escolhido !== ativo.id) trocar(escolhido);
            }}
          >
            <SelectTrigger
              id={idDoSeletor}
              // Só recolhida: aí o rótulo é `sr-only` e o conteúdo do botão é um
              // ícone, logo quem ouve não tem como saber **qual**. Aberta, o
              // `aria-label` seria pior do que nada — sobrepõe-se ao `<Label>` e
              // ao texto do botão, que já dizem "Estabelecimento" e o nome.
              aria-label={recolhida ? `Estabelecimento: ${nomeDoAtivo}` : undefined}
              aria-busy={aTrocar}
              title={soUm ? nomeDoAtivo : "Trocar de estabelecimento"}
              className={recolhida ? "w-full justify-center px-1.5" : "w-full"}
            >
              {/* O nome, e **não** um `<SelectValue/>`: o primitivo envolve os
                  filhos do item num `ItemText`, logo o valor seleccionado
                  arrastava também o papel para dentro do botão ("Aurora
                  dono") e os dois truncavam-se um ao outro num botão de
                  240px. O papel é informação da **lista**, onde se compara um
                  estabelecimento com outro; no botão o que interessa é onde
                  se está. O valor é controlado, logo o nome é sabido aqui. */}
              {recolhida ? (
                <Building2 aria-hidden="true" />
              ) : (
                <span className="truncate text-left">{nomeDoAtivo}</span>
              )}
            </SelectTrigger>
            <SelectContent>
              {estabelecimentos.map((estabelecimento) => (
                <SelectItem key={estabelecimento.id} value={estabelecimento.id}>
                  <span className="truncate">{estabelecimento.nome}</span>
                  {/* O papel distingue dois nomes parecidos, e é o que diz o que
                      a pessoa pode fazer lá dentro. */}
                  <span className="shrink-0 text-xs text-muted-foreground">
                    {estabelecimento.papel}
                  </span>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}

      <div className={recolhida ? "flex flex-col items-center" : "flex items-center gap-2"}>
        {recolhida || sessao.email === null ? null : (
          // Em `font-mono` como qualquer dado que se compara carácter a
          // carácter (DESIGN.md §2): um email é código, não prosa.
          <span className="min-w-0 flex-1 truncate font-mono text-xs text-muted-foreground">
            {sessao.email}
          </span>
        )}
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="shrink-0"
          title={sessao.email === null ? "Terminar sessão" : `Terminar sessão (${sessao.email})`}
          disabled={aSair}
          aria-busy={aSair}
          onClick={sair}
        >
          <LogOut aria-hidden="true" />
          <span className="sr-only">{aSair ? "A sair…" : "Terminar sessão"}</span>
        </Button>
      </div>
    </div>
  );
}
