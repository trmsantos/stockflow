import { Check, EyeOff } from "lucide-react";
import { useId, useState, type FormEvent } from "react";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { formatMoney } from "@/lib/format";

import type { LinhaDeContagem } from "../schemas";
import { textoDeQuantidade } from "../vocabulario";

/**
 * Uma linha de contagem: nome · **campo numérico grande** · unidade em que ele
 * conta · e o esperado, quando a zona não é cega (guião §1).
 *
 * **Isto não é "quantidade editável".** A proibição nº 1 do guião §4 é um lápis
 * ao lado do número no ecrã de **Stock**, e continua a valer: lá o número é
 * leitura. Aqui o campo é o ponto do ecrã — uma contagem é uma observação da
 * prateleira, e ao fechar entra no ledger como `adjustment` com justificação.
 * Nada aqui reescreve um nível, e é por isso que as duas coisas cabem no mesmo
 * produto.
 *
 * O campo tem `inputMode="decimal"`: no telemóvel abre o **teclado numérico**
 * ao primeiro toque, sem passar por um stepper nem por um seletor. O
 * `enterKeyHint="next"` põe "seguinte" na tecla de ação e o submit salta para o
 * campo por contar que vem depois — é assim que o teclado fica aberto do
 * princípio ao fim da zona, que é o que "teclado já aberto" quer dizer em pé,
 * com uma mão. Não há `autoFocus`: num ecrã de nove campos, o que a página faz
 * ao abrir é fazer *scroll* para o campo que roubou o foco, e perde-se o topo
 * com o progresso.
 *
 * O `<label>` fica **ao lado** e não acima, contra o default do DESIGN.md §3:
 * nove rótulos empilhados sobre nove campos são dezoito linhas, e o orçamento
 * do guião §0 são sete. O rótulo continua a ser um `<label htmlFor>` a sério —
 * clicável, lido por áudio, com a unidade em `aria-describedby`.
 */

/** A mesma forma que o `decimal` do contrato, sem sinal: não se conta negativo. */
const DECIMAL_POSITIVO = /^\d+$|^\d+\.\d+$/;

export function LinhaDeContagem({
  linha,
  aRegistar,
  aoRegistar,
  idDoCampo,
  idDoCampoSeguinte,
}: {
  readonly linha: LinhaDeContagem;
  /** Esta linha tem um pedido a sair. */
  readonly aRegistar: boolean;
  readonly aoRegistar: (quantidade: string) => void;
  readonly idDoCampo: string;
  /** O campo por contar que vem a seguir, para onde o Enter salta. */
  readonly idDoCampoSeguinte: string | undefined;
}) {
  const idDaUnidade = useId();
  const idDoErro = useId();
  const [erro, setErro] = useState<string | null>(null);

  const contado = linha.counted?.display ?? "";
  const diferenca = linha.difference;
  const diferencaEmEuros = linha.difference_eur;

  // O sinal da diferença decide a tinta, e o sinal está no próprio número ("−")
  // mais a palavra em `sr-only`, logo a cor nunca comunica sozinha.
  const base = diferenca?.base;
  const emFalta = base?.startsWith("-") ?? false;
  const semDiferenca = base !== undefined && Number(base) === 0;
  const corDaDiferenca = semDiferenca
    ? "text-muted-foreground"
    : emFalta
      ? "text-danger"
      : "text-success";

  function aoSubmeter(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    const formulario = evento.currentTarget;
    const escrito = new FormData(formulario).get("quantidade");
    // A vírgula decimal é como se escreve em português; o contrato quer ponto.
    // É normalização de locale, não conversão de unidades — essa é do servidor.
    const valor = (typeof escrito === "string" ? escrito : "").trim().replace(",", ".");

    if (valor === "") {
      // Apagar o campo não "descontar" a linha: o contrato não tem como voltar
      // atrás numa observação, e um campo vazio com um número guardado no
      // servidor era o ecrã a contradizer-se. O `reset()` devolve o valor
      // confirmado, que é o que a linha ao lado continua a dizer.
      setErro(null);
      formulario.reset();
      return;
    }
    if (!DECIMAL_POSITIVO.test(valor)) {
      setErro(`Escreva quantos ${linha.count_unit} estão na prateleira.`);
      return;
    }

    setErro(null);
    aoRegistar(valor);
  }

  return (
    // O `scroll-mt-16` é o header *sticky* de 48px do shell: sem ele, o campo
    // que recebe o foco ao saltar de linha em linha pode parar debaixo dele.
    <li className="scroll-mt-16 border-b border-border last:border-b-0">
      <form onSubmit={aoSubmeter} className="flex flex-col gap-1 px-4 py-2">
        <div className="flex items-center gap-3">
          <Label htmlFor={idDoCampo} className="min-w-0 flex-1 truncate font-medium">
            {linha.short_name}
          </Label>

          <Input
            id={idDoCampo}
            key={linha.counted_at ?? "por-contar"}
            name="quantidade"
            type="text"
            inputMode="decimal"
            autoComplete="off"
            spellCheck={false}
            enterKeyHint={idDoCampoSeguinte === undefined ? "done" : "next"}
            // Sem `value`: o campo é **não controlado** e o `key` acima remonta-o
            // quando o servidor confirma outro número. Um input controlado
            // obrigava a reconciliar o que ele está a escrever com o que a cache
            // acabou de revalidar, e é assim que um dígito desaparece a meio.
            defaultValue={contado}
            placeholder="—"
            aria-describedby={erro === null ? idDaUnidade : `${idDaUnidade} ${idDoErro}`}
            aria-invalid={erro === null ? undefined : true}
            data-numeric
            className="h-11 w-20 shrink-0 scroll-mt-16 text-base"
            onBlur={(evento) => {
              // Sair do campo vale como escrever: quem conta com o telemóvel
              // numa mão toca no campo seguinte em vez de carregar em "seguinte".
              if (evento.target.value.trim().replace(",", ".") === contado) return;
              evento.target.form?.requestSubmit();
            }}
          />
          <span id={idDaUnidade} className="w-8 shrink-0 text-sm text-muted-foreground">
            {linha.count_unit}
          </span>
        </div>

        <p className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs">
          {linha.expected === null ? (
            <span className="flex items-center gap-1 text-muted-foreground">
              <EyeOff aria-hidden="true" className="size-3.5 shrink-0" />
              contagem cega: o esperado só aparece ao fechar
            </span>
          ) : (
            <span className="text-muted-foreground">
              esperado <span data-numeric>{textoDeQuantidade(linha.expected)}</span>
            </span>
          )}

          {diferenca === null || diferencaEmEuros === null ? null : (
            <span className={`flex items-center gap-1 ${corDaDiferenca}`}>
              {semDiferenca ? (
                <>
                  <Check aria-hidden="true" className="size-3.5 shrink-0" />
                  confere
                </>
              ) : (
                <>
                  {/* O sinal é um **carácter**, não uma cor: "−0,600 kg" lê-se
                      igual a preto e branco. A palavra vai em `sr-only` para
                      quem ouve a linha não ter de interpretar o sinal. */}
                  <span data-numeric>{textoDeQuantidade(diferenca)}</span>
                  <span className="sr-only">{emFalta ? "a menos" : "a mais"}</span>
                  <span aria-hidden="true">·</span>
                  <span data-numeric>{formatMoney(diferencaEmEuros)}</span>
                </>
              )}
            </span>
          )}

          {aRegistar ? <span className="text-muted-foreground">a guardar…</span> : null}
        </p>

        {erro === null ? null : (
          <p id={idDoErro} className="text-sm text-danger">
            {erro}
          </p>
        )}
      </form>
    </li>
  );
}
