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
import { formatMoney, formatTime } from "@/lib/format";

import type { FechoDeContagem } from "../schemas";
import { textos } from "../textos";
import { textoDeQuantidade } from "../vocabulario";

/**
 * O fecho da contagem: as diferenças **em quantidade e em euros**, o que fica
 * por contar, e a justificação (guião §1).
 *
 * Três regras que se tocam e não são a mesma:
 *
 *  - **fechar com diferenças tem de ser possível.** Bloquear é a Q1, e o shell
 *    não responde por ela (guião §4, proibição 3). O botão nunca fica desativado
 *    por haver desvios, e não há modal a perguntar se tem a certeza;
 *  - **fechar com linhas por contar também.** Uma linha nunca contada **não
 *    gera movimento**: ausência de observação não é diferença de zero, e o stock
 *    dela fica exactamente como está. O botão di-lo — "Fechar com 3 por contar"
 *    — em vez de se apagar, e o ecrã mostra **quais** são: "3 por contar" não
 *    diz se faltou a farinha ou as saquetas de açúcar, e só uma das duas faz
 *    alguém voltar ao armazém;
 *  - **a justificação é obrigatória, sempre e sem limiar** (ADR 0030, segunda
 *    ronda, nº 5 — o dono preferiu a disciplina de uma frase em todas as
 *    contagens ao limiar de 50 €, que era uma hipótese por calibrar). Quem
 *    recusa é o servidor, com 400 por campo; o ecrã pede-a antes para não
 *    deixar sair um pedido que já se sabe recusado.
 */

/**
 * Um total em euros, **ao cêntimo**.
 *
 * Os outros ecrãs arredondam na régua, e lá está certo: o valor de stock de uma
 * loja são milhares, e os cêntimos são ruído numa figura que se lê de dois
 * metros. Aqui não — este é o número que o botão por baixo vai escrever no
 * ledger, e uma régua a dizer "2 €" sobre uma perda de 1,50 € é a figura
 * principal do ecrã a discordar da linha que está logo abaixo.
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
      <CorpoDoContador campo={rotulo} figura={formatMoney(valor)} tinta={cor} />
    </div>
  );
}

export function ResumoDoFecho({ fecho }: { readonly fecho: FechoDeContagem }) {
  const porContar = fecho.uncounted_lines;

  return (
    <section className="flex flex-col gap-3">
      {/* O **líquido primeiro**, ao contrário dos outros ecrãs, e por uma razão
          de 360px: a régua empacota à esquerda e desliza por dentro: num
          telemóvel cabem dois campos e o terceiro fica fora do ecrã. Aqui o
          terceiro era o número que decide se se fecha ou não, e os dois
          visíveis eram as parcelas dele. Em desktop cabem os três e a ordem
          lê-se na mesma: total, e depois de onde vem. */}
      <ReguaDeContadores>
        <Total rotulo={textos.fecho.totalLiquido} valor={fecho.net_eur} cor="" />
        <Total rotulo={textos.fecho.totalEmFalta} valor={fecho.loss_eur} cor="text-danger" />
        <Total rotulo={textos.fecho.totalAMais} valor={fecho.gain_eur} cor="text-success" />
      </ReguaDeContadores>

      <p className="px-celula-x text-xs text-muted-foreground">
        <span data-numeric>{fecho.counted_lines}</span> {textos.contagem.de}{" "}
        <span data-numeric>{fecho.total_lines}</span> {textos.fecho.linhasContadas}
        {porContar.count === 0 ? "" : textos.fecho.porContarSemAjuste}
      </p>

      {porContar.count === 0 ? null : (
        // Aviso **suave**, no fluxo: fechar sem contar tudo é legítimo (ninguém
        // conta as saquetas de açúcar) e o que o ecrã faz é dizer o que
        // acontece e **sobre o quê**, não impedir.
        <div className="max-w-3xl px-celula-x">
          <Alert className="border-warning-border bg-warning-surface">
            <TriangleAlert aria-hidden="true" className="text-warning" />
            <AlertTitle>
              {textos.fecho.ficam} <span data-numeric>{porContar.count}</span>{" "}
              {textos.fecho.linhasPorContar}
            </AlertTitle>
            <AlertDescription className="flex flex-col gap-1.5">
              <span>{textos.fecho.porContarCorpo}</span>
              {/* Os nomes, e não só o número. Uma lista e não uma frase com
                  vírgulas: a 360px uma frase de dez nomes é um parágrafo que
                  ninguém lê, e o que se procura aqui é **um** nome. */}
              <ul className="flex flex-col gap-0.5">
                {porContar.names.map((nome) => (
                  <li key={nome} className="truncate text-xs">
                    {nome}
                  </li>
                ))}
              </ul>
            </AlertDescription>
          </Alert>
        </div>
      )}

      {fecho.differences.length === 0 ? (
        <p className="px-celula-x text-sm text-muted-foreground">{textos.fecho.semDiferencas}</p>
      ) : (
        <div className="flex flex-col">
          <h2 className="bg-surface-2 px-celula-x py-1 text-xs font-medium text-muted-foreground">
            {textos.fecho.diferencasTitulo}
          </h2>
          <ul className="flex flex-col">
            {fecho.differences.map((linha) => {
              const emFalta = linha.difference?.base.startsWith("-") ?? false;
              const tinta = emFalta ? "text-danger" : "text-success";
              // Ausente (quem não vê euros) e `null` (por contar) são o mesmo
              // para quem desenha: não há número. Ver `linhaDeContagemSchema`.
              const emEuros = linha.difference_eur ?? null;
              return (
                <li
                  key={linha.id}
                  className="flex min-h-14 flex-col justify-center gap-0.5 border-b border-border px-celula-x py-2"
                >
                  <span className="flex items-baseline gap-3">
                    <span className="min-w-0 flex-1 truncate font-medium">
                      {linha.short_name}
                    </span>
                    <span data-numeric className={`shrink-0 text-sm ${tinta}`}>
                      {linha.difference === null ? "" : textoDeQuantidade(linha.difference)}
                    </span>
                    <span className="sr-only">
                      {emFalta ? textos.accoes.aMenos : textos.accoes.aMais}
                    </span>
                    {/* Os euros só existem para quem os vê. Este ecrã é de
                        `owner|manager`, logo chegam sempre — e a guarda fica
                        porque o contrato os declara ausentes ou nulos, e um
                        traço no lugar do dinheiro seria uma afirmação falsa. */}
                    {emEuros === null ? null : (
                      <span data-numeric className={`w-20 shrink-0 text-sm ${tinta}`}>
                        {formatMoney(emEuros)}
                      </span>
                    )}
                  </span>
                  <span className="truncate text-xs text-muted-foreground">
                    {textos.fecho.contadoPrefixo}{" "}
                    <span data-numeric>
                      {linha.counted === null ? "" : textoDeQuantidade(linha.counted)}
                    </span>
                    {linha.expected === null ? null : (
                      <>
                        {` · ${textos.fecho.esperadoPrefixo} `}
                        <span data-numeric>{textoDeQuantidade(linha.expected)}</span>
                      </>
                    )}
                    {/* Quem contou viaja com a linha e é o que responde a "quem
                        é que viu isto?" na hora de assinar um ajuste
                        irreversível. */}
                    {linha.counted_by === null ? null : (
                      <>
                        {` · ${linha.counted_by}`}
                        {linha.counted_at === null ? null : (
                          <>
                            <span aria-hidden="true">{" · "}</span>
                            <span className="sr-only">{` ${textos.contagem.as} `}</span>
                            <span data-numeric>{formatTime(linha.counted_at)}</span>
                          </>
                        )}
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
  readonly aoFechar: (motivo: string) => void;
}) {
  const idMotivo = useId();
  const idAjuda = useId();
  const idErro = useId();
  const [erro, setErro] = useState<string | null>(null);

  const porContar = fecho.uncounted_lines.count;

  function aoSubmeter(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    const escrito = new FormData(evento.currentTarget).get("motivo");
    const motivo = (typeof escrito === "string" ? escrito : "").trim();

    // Sempre obrigatória, sem limiar. O servidor recusa um corpo sem ela com
    // 400 por campo; pedi-la aqui poupa a ida e põe o erro debaixo do campo,
    // que é onde um erro de campo pertence (DESIGN.md §3).
    if (motivo === "") {
      setErro(textos.fecho.motivoObrigatorio);
      const campo = document.getElementById(idMotivo);
      if (campo instanceof HTMLInputElement) campo.focus();
      return;
    }

    setErro(null);
    aoFechar(motivo);
  }

  return (
    <form onSubmit={aoSubmeter} className="flex flex-col gap-3 px-celula-x">
      <div className="flex flex-col gap-1.5">
        <Label htmlFor={idMotivo}>{textos.fecho.oQueAconteceu}</Label>
        <Input
          id={idMotivo}
          name="motivo"
          type="text"
          autoComplete="off"
          required
          maxLength={200}
          placeholder={textos.fecho.exemploDeMotivo}
          aria-describedby={erro === null ? idAjuda : `${idAjuda} ${idErro}`}
          aria-invalid={erro === null ? undefined : true}
          // A 360px fecha-se a contagem onde ela foi feita: o campo cresce para
          // o tamanho do dedo e volta ao controlo de 40px em desktop. O `max-w`
          // é o cap de leitura do DESIGN.md §4 — um campo de texto a 1000px é
          // uma linha que o olho não acompanha.
          className="h-12 max-w-2xl text-base md:h-controlo"
          onChange={() => {
            setErro(null);
          }}
        />
        <p id={idAjuda} className="text-xs text-muted-foreground">
          {textos.fecho.ajudaObrigatoria}
        </p>
        {erro === null ? null : (
          <p id={idErro} className="text-sm text-danger">
            {erro}
          </p>
        )}
      </div>

      <div className="flex flex-col items-start gap-1.5">
        {/* O botão **diz** o que vai acontecer em vez de se desligar: fechar com
            linhas por contar é legítimo, e um botão apagado faz quem conta
            inventar números para o acender. */}
        <Button type="submit" disabled={aFechar}>
          {aFechar
            ? textos.fecho.aFechar
            : porContar === 0
              ? textos.fecho.fechar
              : textos.fecho.fecharComPorContar(porContar)}
        </Button>
        {/* A ação visivelmente restrita da Q7: diz **a quem pertence**. Quem não
            tem o papel nem chega aqui — o `GET` desta pré-visualização responde
            403 —, e o rótulo continua a valer para quem chega. */}
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
