import { CircleAlert, Lock, TriangleAlert } from "lucide-react";
import { useId, useState, type FormEvent } from "react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  CLASSE_CONTADOR,
  CorpoDoContador,
  ReguaDeContadores,
} from "@/components/regua-de-contadores";
import { mensagemDeErro } from "@/lib/api/errors";
import { formatMoney, formatMoneyRounded } from "@/lib/format";

import type { FechoDeContagem } from "../schemas";
import { textos } from "../textos";
import { textoDeQuantidade } from "../vocabulario";

/**
 * O fecho da contagem: as diferenças **em quantidade e em euros**, e a
 * justificação obrigatória acima de um limiar (guião §1).
 *
 * Duas regras que se tocam e não são a mesma:
 *
 *  - **fechar com diferenças tem de ser possível.** Bloquear é a Q1, e o shell
 *    não responde por ela (guião §4, proibição 3). O botão nunca fica desativado
 *    por haver desvios, e não há modal a perguntar se tem a certeza;
 *  - **acima do limiar a justificação é obrigatória**, porque isso o guião pede
 *    explicitamente e o `inventory-domain` §5 também. Quem recusa é o servidor,
 *    com o limiar na frase; o ecrã mostra-o antes ("motivo obrigatório acima de
 *    5 €") para ele poder discutir o valor em vez de o ir mudar num painel que
 *    o §4 nº 7 proíbe.
 */

/**
 * Um total em euros: arredondado, porque é uma soma de custos médios.
 *
 * **Era um mosaico `rounded-xl` com borda própria, numa grelha de três** — a
 * última do repositório, e o cartão de estatística que o DESIGN.md §5 proíbe.
 * Passou a campo da régua de contadores a 2026-10-06, pela mesma razão que os
 * dos outros ecrãs: sem ela, este ecrã era o único que não parecia do mesmo
 * produto.
 *
 * Este ecrã **continua a ser um formulário e não uma tabela**, e não foi
 * convertido: as três células são totais e o resto é uma justificação e um botão.
 * É também uma rota de campo — fecha-se a contagem onde ela foi feita, no
 * telemóvel — e o §4 dá a 360px a prioridade do desenho aqui.
 */
function Total({
  rotulo,
  valor,
  cor,
}: {
  readonly rotulo: string;
  readonly valor: string;
  readonly cor: string;
}) {
  return (
    <div className={CLASSE_CONTADOR}>
      <CorpoDoContador campo={rotulo} figura={formatMoneyRounded(valor)} tinta={cor} />
    </div>
  );
}

export function ResumoDoFecho({ fecho }: { readonly fecho: FechoDeContagem }) {
  const porContar = fecho.total_lines - fecho.counted_lines;

  return (
    <section className="flex flex-col gap-3">
      <ReguaDeContadores>
        <Total rotulo={textos.fecho.totalEmFalta} valor={fecho.loss_eur} cor="text-danger" />
        <Total rotulo={textos.fecho.totalAMais} valor={fecho.gain_eur} cor="text-success" />
        <Total rotulo={textos.fecho.totalLiquido} valor={fecho.net_eur} cor="" />
      </ReguaDeContadores>

      <p className="px-celula-x text-xs text-muted-foreground">
        <span data-numeric>{fecho.counted_lines}</span> {textos.contagem.de}{" "}
        <span data-numeric>{fecho.total_lines}</span> {textos.fecho.linhasContadas}
        {porContar === 0 ? "" : textos.fecho.porContarSemAjuste}
      </p>

      {porContar === 0 ? null : (
        // Aviso **suave**, no fluxo: fechar sem contar tudo é legítimo (ninguém
        // conta as saquetas de açúcar) e o que o ecrã faz é dizer o que
        // acontece, não impedir.
        <div className="px-4">
          <Alert className="border-warning-border bg-warning-surface">
            <TriangleAlert aria-hidden="true" className="text-warning" />
            <AlertTitle>
              {textos.fecho.ficam} <span data-numeric>{porContar}</span>{" "}
              {textos.fecho.linhasPorContar}
            </AlertTitle>
            <AlertDescription>{textos.fecho.porContarCorpo}</AlertDescription>
          </Alert>
        </div>
      )}

      {fecho.differences.length === 0 ? (
        <p className="px-4 text-sm text-muted-foreground">{textos.fecho.semDiferencas}</p>
      ) : (
        <div className="flex flex-col">
          <h2 className="bg-surface-2 px-4 py-1 text-xs font-medium text-muted-foreground">
            {textos.fecho.diferencasTitulo}
          </h2>
          <ul className="flex flex-col">
            {fecho.differences.map((linha) => {
              const emFalta = linha.difference?.base.startsWith("-") ?? false;
              return (
                <li
                  key={linha.id}
                  className="flex min-h-14 flex-col justify-center gap-0.5 border-b border-border px-4 py-2"
                >
                  <span className="flex items-baseline gap-3">
                    <span className="min-w-0 flex-1 truncate font-medium">
                      {linha.short_name}
                    </span>
                    <span
                      data-numeric
                      className={`shrink-0 text-sm ${emFalta ? "text-danger" : "text-success"}`}
                    >
                      {linha.difference === null ? "" : textoDeQuantidade(linha.difference)}
                    </span>
                    <span className="sr-only">
                      {emFalta ? textos.accoes.aMenos : textos.accoes.aMais}
                    </span>
                    <span
                      data-numeric
                      className={`w-20 shrink-0 text-sm ${emFalta ? "text-danger" : "text-success"}`}
                    >
                      {linha.difference_eur === null ? "" : formatMoney(linha.difference_eur)}
                    </span>
                  </span>
                  <span className="truncate text-xs text-muted-foreground">
                    {linha.zone.name} · {textos.fecho.contadoPrefixo}{" "}
                    <span data-numeric>
                      {linha.counted === null ? "" : textoDeQuantidade(linha.counted)}
                    </span>
                    {linha.expected === null ? null : (
                      <>
                        {` · ${textos.fecho.esperadoPrefixo} `}
                        <span data-numeric>{textoDeQuantidade(linha.expected)}</span>
                      </>
                    )}
                  </span>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </section>
  );
}

export function FormularioDeFecho({
  fecho,
  aFechar,
  erroDoServidor,
  aoFechar,
}: {
  readonly fecho: FechoDeContagem;
  readonly aFechar: boolean;
  readonly erroDoServidor: unknown;
  readonly aoFechar: (motivo: string | undefined) => void;
}) {
  const idMotivo = useId();
  const idAjuda = useId();
  const idErro = useId();
  const [erro, setErro] = useState<string | null>(null);

  function aoSubmeter(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    const escrito = new FormData(evento.currentTarget).get("motivo");
    const motivo = (typeof escrito === "string" ? escrito : "").trim();

    if (fecho.reason_required && motivo === "") {
      setErro(textos.fecho.motivoObrigatorio(formatMoney(fecho.reason_required_above_eur)));
      const campo = document.getElementById(idMotivo);
      if (campo instanceof HTMLInputElement) campo.focus();
      return;
    }

    setErro(null);
    aoFechar(motivo === "" ? undefined : motivo);
  }

  return (
    <form onSubmit={aoSubmeter} className="flex flex-col gap-3 px-4">
      <div className="flex flex-col gap-1.5">
        <Label htmlFor={idMotivo}>
          {textos.fecho.oQueAconteceu}
          {fecho.reason_required ? "" : textos.fecho.opcional}
        </Label>
        <Input
          id={idMotivo}
          name="motivo"
          type="text"
          autoComplete="off"
          maxLength={200}
          placeholder={textos.fecho.exemploDeMotivo}
          aria-describedby={erro === null ? idAjuda : `${idAjuda} ${idErro}`}
          aria-invalid={erro === null ? undefined : true}
        />
        <p id={idAjuda} className="text-xs text-muted-foreground">
          {fecho.reason_required
            ? textos.fecho.ajudaObrigatoria(formatMoney(fecho.reason_required_above_eur))
            : textos.fecho.ajudaOpcional(formatMoney(fecho.reason_required_above_eur))}
        </p>
        {erro === null ? null : (
          <p id={idErro} className="text-sm text-danger">
            {erro}
          </p>
        )}
      </div>

      <div className="flex flex-col items-start gap-1.5">
        <Button type="submit" disabled={aFechar}>
          {aFechar ? textos.fecho.aFechar : textos.fecho.fechar}
        </Button>
        {/* A ação visivelmente restrita da Q7: diz **a quem pertence** e não
            impede ninguém. É daqui que sai a pergunta "a Ana podia ter feito
            isto? e apagar?" — com um botão desativado, não havia pergunta. */}
        <p className="flex items-center gap-1 text-xs text-muted-foreground">
          <Lock aria-hidden="true" className="size-3 shrink-0" />
          {textos.fecho.soOPapelFecha(fecho.closing_role)}
        </p>
      </div>

      {erroDoServidor === null ? null : (
        <p role="alert" className="flex items-start gap-1.5 text-sm text-danger">
          <CircleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
          <span>{mensagemDeErro(erroDoServidor)}</span>
        </p>
      )}
    </form>
  );
}
