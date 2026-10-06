import { Check, EyeOff } from "lucide-react";
import { useId, useState, type FormEvent } from "react";

import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
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

/**
 * A grelha da linha, **e a do cabeçalho de colunas**, numa constante só.
 *
 * Duas definições divergiam na primeira coluna que mudasse de largura, e aí o
 * cabeçalho deixava de estar em cima da coluna que nomeia — um defeito que se vê
 * e que nenhum gate apanha.
 *
 * ## Porque é uma grelha e não uma `<table>`
 *
 * Este ecrã ficou de fora da conversão a tabelas densas e o dono do produto
 * apanhou-o: continuava a `max-w-2xl` com o cromado antigo, parecia de outro
 * produto. A minha razão para o deixar fora era que isto é um **formulário** e
 * não uma lista — o que é verdade —, mas tinha um pressuposto escondido: assumi
 * que uma tabela obriga a uma largura mínima grande e que isso partia os 360px.
 * Com poucas colunas não obriga.
 *
 * O que **de facto** não cabe é a informação toda a 360px: seis colunas pedem
 * 640px, e a contagem faz-se de pé no armazém, com uma mão. Uma `<table>` com
 * `overflow-x-auto` punha fora do ecrã o campo que se está a escrever, que é o
 * oposto do que este ecrã existe para fazer.
 *
 * Daí uma grelha responsiva com **um só** `<input>` no DOM: cinco colunas em
 * desktop (a leitura de tabela que o resto da app tem) e duas linhas a 360, com
 * os mesmos elementos. O `md:contents` faz o `<p>` da segunda linha desaparecer
 * da grelha em desktop e promove os três filhos dele a células — é o que evita
 * duplicar o campo em dois layouts, que seria duplicar o foco, o `key` de
 * remontagem e o `onBlur`.
 *
 * A ordem do DOM serve as duas larguras sem um único `order-*`: nome, campo,
 * esperado, diferença, quem. E pôr o campo **logo depois do nome** não é só
 * conveniência de layout — encurta o percurso do olho entre o que se lê na
 * prateleira e onde se escreve, e numa zona cega o esperado nem existe.
 */
const GRELHA_DA_LINHA =
  "grid-cols-[minmax(0,1fr)_auto] items-center gap-x-celula-x gap-y-1 px-celula-x md:grid-cols-[minmax(0,1fr)_11rem_7rem_9rem_7rem] md:gap-y-0";

/**
 * O cabeçalho de colunas, **só onde há colunas**.
 *
 * A 360px a linha são duas linhas empilhadas, e um cabeçalho sobre elas nomearia
 * uma grelha que não está lá — daí `hidden md:grid`. Usa a **mesma** constante da
 * linha: duas definições divergiam na primeira coluna que mudasse de largura, e
 * aí o rótulo deixava de estar em cima da coluna que nomeia.
 *
 * `aria-hidden`: cada campo da linha já tem o seu nome acessível — o `<label>` no
 * nome do artigo, o `aria-describedby` da unidade, as palavras "esperado" e "a
 * menos"/"a mais". Um cabeçalho de grelha sem `role="columnheader"` não liga a
 * nada para quem ouve o ecrã, e fingir que liga era pior do que não o anunciar.
 */
export function CabecalhoDaContagem() {
  return (
    <div
      aria-hidden="true"
      className={`hidden h-8 border-b border-border bg-surface-2 text-xs font-bold tracking-microrotulo text-muted-foreground uppercase md:grid ${GRELHA_DA_LINHA}`}
    >
      <span>Artigo</span>
      <span>Contado</span>
      <span className="text-right">Esperado</span>
      <span className="text-right">Diferença</span>
      <span>Quem</span>
    </div>
  );
}

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
    // O `scroll-mt-16` (64px) desconta a barra de topo do shell — 56px desde
    // que ela passou a ter os `--spacing-cabecalho` que o DESIGN.md §2 lhe dá —
    // mais uma folga. Sem ele, o campo que recebe o foco ao saltar de linha em
    // linha pode parar debaixo dela.
    <li className="scroll-mt-16 border-b border-border last:border-b-0 transition-colors hover:bg-surface-2">
      <form onSubmit={aoSubmeter} className={`grid ${GRELHA_DA_LINHA} py-2 md:h-linha md:py-0`}>
        <Label htmlFor={idDoCampo} className="min-w-0 truncate font-medium">
          {linha.short_name}
        </Label>

        <div className="flex shrink-0 items-center gap-2">
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

        {/* `md:contents`: em desktop este `<p>` desaparece da grelha e os três
            filhos passam a células próprias. A 360px continua a ser uma segunda
            linha a atravessar as duas colunas, que é o que cabe. */}
        <p className="col-span-2 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs md:contents">
          {linha.expected === null ? (
            // Em desktop a coluna tem 7rem e o cabeçalho dela já diz "Esperado",
            // logo a frase longa fica para 360px, onde não há cabeçalho nenhum.
            // O `title` leva-a nas duas.
            <span
              className="flex items-center gap-1 text-muted-foreground md:truncate"
              title="Contagem cega: o esperado só aparece ao fechar"
            >
              <EyeOff aria-hidden="true" className="size-3.5 shrink-0" />
              <span className="md:hidden">contagem cega: o esperado só aparece ao fechar</span>
              <span className="hidden md:inline">cega</span>
            </span>
          ) : (
            <span className="text-muted-foreground md:text-right">
              <span className="md:hidden">esperado </span>
              <span data-numeric>{textoDeQuantidade(linha.expected)}</span>
            </span>
          )}

          {diferenca === null || diferencaEmEuros === null ? (
            // Uma célula vazia em desktop mantém o campo "Quem" na sua coluna:
            // sem ela a grelha fechava o buraco e a linha por contar desalinhava
            // da linha contada acima.
            <span aria-hidden="true" className="hidden md:block" />
          ) : (
            <span className={`flex items-center gap-1 md:justify-end ${corDaDiferenca}`}>
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

          {/* Quem contou — nunca esteve à vista, e o contrato tem-no desde o
              princípio (`counted_by`). Numa contagem repartida por zonas entre
              duas pessoas é a sonda da Q7 outra vez: numa coluna vê-se de
              relance quem fez o quê. Escondido a 360px, e isso é uma excepção
              argumentada à regra do §4 de não esconder colunas em mobile: ali a
              coluna que se esconde era "a que faltava", e aqui o que se esconde é
              a **proveniência** — quem está a contar ao telemóvel é quem conta. */}
          <span className="hidden truncate text-muted-foreground md:block">
            {aRegistar ? "a guardar…" : (linha.counted_by ?? "")}
          </span>
          {aRegistar ? (
            <span className="text-muted-foreground md:hidden">a guardar…</span>
          ) : null}
        </p>

        {erro === null ? null : (
          <p id={idDoErro} className="col-span-2 text-sm text-danger md:col-span-5">
            {erro}
          </p>
        )}
      </form>
    </li>
  );
}

/**
 * O pendente da lista de contagem: a **mesma** grelha, com barras nas células.
 *
 * Usava o `EsqueletoDaLista` dos outros ecrãs, que desenha cartões de 56px — e
 * com a linha a passar a grelha de 44px isso era um salto de layout no momento
 * em que as linhas chegam. O cabeçalho entra a sério, porque o cromado não
 * precisa de carregar.
 */
export function EsqueletoDaContagem({ linhas = 5 }: { readonly linhas?: number }) {
  return (
    <div aria-busy="true">
      <span className="sr-only">A carregar as linhas…</span>
      <CabecalhoDaContagem />
      {Array.from({ length: linhas }, (_, indice) => indice).map((indice) => (
        <div
          key={indice}
          className={`grid ${GRELHA_DA_LINHA} border-b border-border py-2 md:h-linha md:py-0`}
        >
          <Skeleton className="h-4 w-32" />
          <Skeleton className="h-9 w-20" />
          <Skeleton className="col-span-2 h-3 w-24 md:col-span-1 md:ml-auto" />
          <Skeleton className="hidden h-3 w-20 md:block md:ml-auto" />
          <Skeleton className="hidden h-3 w-16 md:block" />
        </div>
      ))}
    </div>
  );
}
