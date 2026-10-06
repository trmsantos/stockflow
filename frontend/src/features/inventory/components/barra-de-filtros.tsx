import { Search } from "lucide-react";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

import type { Localizacao } from "../schemas";

/**
 * A barra *sticky* do topo: procurar e escolher a localização.
 *
 * É a única coisa que fica colada ao ecrã quando a lista corre, porque é a
 * ação principal do guião §1 — e porque o orçamento de 360×640 não paga mais
 * do que uma linha colada. Os três números e a lista correm por baixo dela.
 *
 * **O seletor de localização é a parte operacional da Q2** ("uma loja ou
 * várias"): ver consolidado ou separado, e observar qual é que ele procura. As
 * opções vêm dos dados — das localizações que aparecem em `by_location` —, não
 * de uma lista de lojas guardada no frontend: um catálogo de lojas no cliente
 * seria uma segunda fonte de verdade que só sabe ficar desactualizada. O preço
 * está nomeado no relatório: uma localização sem nenhum movimento não aparece
 * aqui, porque não há (ainda) endpoint que liste localizações.
 *
 * O guião põe este seletor no header. O header é do shell, e o shell não
 * conhece domínios (ADR 0008, decisão 2) — por isso vive aqui, à mão do
 * polegar, colado ao campo de procurar.
 */

/** Radix reserva a string vazia; "todas" é o sentinela só do seletor. */
const TODAS = "todas";

export function BarraDeFiltros({
  termo,
  aoProcurar,
  localizacoes,
  lojaAtiva,
  aoEscolherLoja,
}: {
  readonly termo: string;
  readonly aoProcurar: (valor: string) => void;
  readonly localizacoes: readonly Localizacao[];
  readonly lojaAtiva: string | undefined;
  readonly aoEscolherLoja: (id: string | undefined) => void;
}) {
  const semLocalizacoes = localizacoes.length === 0;

  // Uma localização que o URL pede mas que não está nos dados (um `?loja=` de
  // outro estabelecimento, ou um id que já não existe) cairia num seletor sem
  // rótulo nenhum. Mostra-se "Todas", que é também o que o servidor faz com um
  // âmbito que não reconhece: o ecrã e a resposta dizem o mesmo.
  const lojaConhecida = localizacoes.some((local) => local.id === lojaAtiva)
    ? lojaAtiva
    : undefined;

  return (
    // `top-cabecalho` e não `top-12`: a barra de topo do shell passou a ter os
    // 56px que o DESIGN.md §2 lhe dá (`--spacing-cabecalho`) — tinha 48px do
    // orçamento de ecrã da sessão 0, que a ADR 0009 retirou. Com o número
    // antigo esta barra ficava 8px por baixo do cabeçalho e desaparecia-lhe por
    // trás ao deslizar. Agora é o mesmo token nos dois sítios.
    <div className="sticky top-cabecalho z-10 flex items-center gap-2 border-b border-border bg-background px-4 py-2">
      {/* `role="search"` e não um `<form>`: não há submissão — o filtro aplica-se
          a cada tecla e o estado vive no URL, logo não há nada para enviar. */}
      <div role="search" className="relative min-w-0 flex-1">
        <Label htmlFor="procurar-artigo" className="sr-only">
          Procurar artigo
        </Label>
        <Search
          aria-hidden="true"
          className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground"
        />
        <Input
          id="procurar-artigo"
          name="q"
          type="search"
          value={termo}
          onChange={(evento) => {
            aoProcurar(evento.target.value);
          }}
          placeholder="Procurar artigo…"
          autoComplete="off"
          spellCheck={false}
          enterKeyHint="search"
          className="pl-8"
        />
      </div>

      <Select
        value={lojaConhecida ?? TODAS}
        onValueChange={(valor) => {
          aoEscolherLoja(valor === TODAS ? undefined : valor);
        }}
        disabled={semLocalizacoes}
      >
        <SelectTrigger
          aria-label="Localização"
          title="Ver uma localização ou o total consolidado"
          className="w-28 shrink-0 sm:w-40"
        >
          <SelectValue placeholder="Todas" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={TODAS}>Todas</SelectItem>
          {localizacoes.map((localizacao) => (
            <SelectItem key={localizacao.id} value={localizacao.id}>
              {localizacao.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
