import { CircleAlert, LoaderCircle } from "lucide-react";
import { useId } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

/**
 * A tela de entrar — a primeira coisa que o cliente vê, e por isso a primeira
 * que a identidade tem de resolver. É rota pública (ADR 0010: `/entrar`, fora
 * do `AppShell`).
 *
 * **Não há aqui autenticação, e isso é deliberado.** Não há `useMutation`, não
 * há `fetch`, o `onSubmit` cancela o evento e os três estados são uma
 * propriedade. A ADR 0010 explica porquê: o servidor de fixtures não finge uma
 * sessão, porque uma sessão falsa é a única mentira que muda **autorização** em
 * vez de forma de dados, e nenhum dos gates a apanharia. Uma tela é uma tela.
 *
 * Os três estados são mostrados **lado a lado** e não por clique: quem decide
 * está a olhar, não a interagir, e um erro que só aparece depois de escrever
 * uma password errada não entra na comparação.
 *
 * O que a identidade não escolhe, porque é regra: o rótulo fica acima do campo,
 * o erro abaixo **em texto** e não só em cor, o `aria-invalid` e o
 * `aria-describedby` ligam o campo à mensagem, e o botão a submeter fica
 * `disabled` com `aria-busy` em vez de desaparecer.
 */
export type EstadoDaTela = "normal" | "erro" | "a-submeter";

export function TelaDeEntrar({ estado }: { readonly estado: EstadoDaTela }) {
  // Três instâncias desta tela vivem na mesma página; sem `useId` os três
  // `<label for>` apontavam todos para o primeiro campo.
  const idEmail = useId();
  const idPassword = useId();
  const idErro = useId();

  const comErro = estado === "erro";
  const aSubmeter = estado === "a-submeter";

  return (
    <div data-painel className="flex w-full max-w-sm flex-col overflow-hidden">
      <form
        className="flex flex-col gap-4 p-6"
        onSubmit={(evento) => {
          // Uma maqueta não submete. Sem isto o browser recarregava a página.
          evento.preventDefault();
        }}
      >
        <div className="flex flex-col gap-1">
          {/* `translate="no"`: um nome de marca traduzido automaticamente fica
              irreconhecível, e é por ele que o cliente sabe onde está. */}
          <span translate="no" className="font-heading text-xl font-semibold">
            StockFlow
          </span>
          <span data-microrotulo className="text-xs text-muted-foreground">
            {/* O nome da empresa não aparece antes de alguém entrar: diria a um
                estranho que aquela conta existe. */}
            Gestão de stock
          </span>
        </div>

        {/* `h3` e não `h1` porque esta tela está embutida numa página de
            comparação, debaixo do `h2` da secção. Na rota `/entrar` da ADR 0010
            é o `h1` do documento. O nível não muda o aspecto. */}
        <h3 className="font-heading text-2xl font-semibold">Entrar</h3>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor={idEmail}>Email</Label>
          <Input
            data-controlo
            id={idEmail}
            name="email"
            type="email"
            autoComplete="username"
            // Um corrector ortográfico num email sublinha-o todo a vermelho e
            // ensina o utilizador a ignorar sublinhados vermelhos.
            spellCheck={false}
            placeholder="nome@pastelaria.pt"
            defaultValue={comErro ? "encarregado@belaflor.pt" : ""}
            aria-invalid={comErro}
            aria-describedby={comErro ? idErro : undefined}
            disabled={aSubmeter}
          />
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor={idPassword}>Palavra-passe</Label>
          <Input
            data-controlo
            id={idPassword}
            name="password"
            type="password"
            autoComplete="current-password"
            defaultValue={comErro ? "••••••••" : ""}
            aria-invalid={comErro}
            aria-describedby={comErro ? idErro : undefined}
            disabled={aSubmeter}
          />
        </div>

        {comErro ? (
          // A mensagem é deliberadamente genérica: dizer "este email não
          // existe" confirma a um estranho quais os emails que são clientes.
          <p
            id={idErro}
            role="alert"
            className="flex items-start gap-1.5 text-sm text-danger"
          >
            <CircleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
            <span>Email ou palavra-passe incorretos. Tente outra vez.</span>
          </p>
        ) : null}

        <Button data-controlo type="submit" disabled={aSubmeter} aria-busy={aSubmeter}>
          {aSubmeter ? (
            <>
              <LoaderCircle aria-hidden="true" className="animate-spin" />
              A entrar…
            </>
          ) : (
            "Entrar"
          )}
        </Button>

        <a
          href="#esqueci-me"
          className="self-start rounded-md text-sm text-primary underline underline-offset-4 hover:text-foreground"
        >
          Esqueci-me da palavra-passe
        </a>
      </form>

      <p className="border-t border-border bg-surface-2 px-6 py-4 text-xs text-muted-foreground">
        {/* ADR 0010: não há registo self-service no v1. Quem cria o tenant é o
            operador, e a entrada de uma pessoa nova é um link de activação. */}
        O acesso ao StockFlow é por convite. Se não tem conta, peça o link de
        activação a quem administra a da sua empresa.
      </p>
    </div>
  );
}
