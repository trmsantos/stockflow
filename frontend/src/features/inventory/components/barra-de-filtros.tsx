import { Search } from "lucide-react";
import { useEffect, useState } from "react";

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
import { textos } from "../textos";

/**
 * A barra *sticky* do topo: procurar e escolher a localização.
 *
 * É a única coisa que fica colada ao ecrã quando a tabela corre, e é também o
 * único cabeçalho que acompanha de facto o scroll: um `thead` sticky não
 * funciona dentro do invólucro que desliza na horizontal, e a razão está escrita
 * no `components/tabela.tsx`.
 *
 * **Não tem título.** O nome do ecrã está no header do shell, com o grupo
 * ("Inventário / Stock"), e um segundo título aqui era a mesma palavra duas
 * vezes a 40px de distância. O peso visual deste ecrã vive nas figuras da régua
 * de contadores, que são mono e são o que se compara — não num cabeçalho grande,
 * que é o tratamento default de qualquer página gerada.
 *
 * O campo de procura tem um tecto de 320px (`sm:max-w-xs`). Sem ele esticava até
 * aos ~1024px da área de conteúdo em desktop, o que é uma caixa de texto da
 * largura de um monitor para escrever "acucar".
 *
 * **O seletor de localização é a parte operacional da Q2** ("uma loja ou
 * várias"): ver consolidado ou separado, e observar qual é que ele procura. As
 * opções vêm do servidor — `GET /locations` —, nunca de uma lista de lojas
 * guardada no frontend, que seria uma segunda fonte de verdade que só sabe
 * ficar desactualizada. Vinham das localizações que apareciam em `by_location`,
 * e mudaram de fonte quando os filtros passaram para o servidor (ADR 0034): com
 * a lista filtrada, as opções do seletor encolhiam à medida que se procurava.
 * Pelo caminho sai o preço que estava nomeado aqui — uma localização sem
 * movimento nenhum já aparece.
 *
 * ## A procura espera 300ms, e isso é consequência de a filtragem ser do servidor
 *
 * Enquanto `?q=` se aplicava em JavaScript, escrever não custava rede nenhuma.
 * Agora cada valor distinto é um `WHERE`, e escrever "açúcar" sem travão são
 * seis pedidos em voo — numa cozinha com Wi-Fi mau é a resposta que interessa a
 * chegar em último. O campo responde à tecla (o rascunho é local) e o **URL**,
 * que é o estado do ecrã, só muda quando a pessoa pára de escrever.
 *
 * O guião põe este seletor no header. O header é do shell, e o shell não
 * conhece domínios (ADR 0008, decisão 2) — por isso vive aqui, colado ao campo
 * de procurar: os dois definem o **âmbito** do que a tabela mostra, e controlos
 * que fazem a mesma coisa ficam juntos.
 */

/** Radix reserva a string vazia; "todas" é o sentinela só do seletor. */
const TODAS = "todas";

/**
 * O travão da procura. 300ms é o intervalo entre teclas de quem escreve
 * depressa e a espera que ninguém nota — mais do que isto e o ecrã parece
 * lento, menos e volta a haver um pedido por tecla.
 */
const ATRASO_DA_PROCURA_MS = 300;

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
  // O rascunho do campo, local, para a tecla aparecer no instante em que é
  // premida. O `termo` continua a ser a verdade (vem do URL): quando ele muda
  // por fora — "Limpar filtros", o botão de voltar, um link partilhado — o
  // rascunho acompanha-o. É o ajuste-durante-o-render que o React documenta
  // para derivar estado de propriedades, e não um `useEffect` de sincronização:
  // com efeito, o campo pintava uma vez com o valor velho.
  const [rascunho, setRascunho] = useState(termo);
  const [termoVisto, setTermoVisto] = useState(termo);
  if (termo !== termoVisto) {
    setTermoVisto(termo);
    setRascunho(termo);
  }

  useEffect(() => {
    if (rascunho === termo) return undefined;
    const relogio = setTimeout(() => {
      aoProcurar(rascunho);
    }, ATRASO_DA_PROCURA_MS);
    return () => {
      clearTimeout(relogio);
    };
  }, [rascunho, termo, aoProcurar]);

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
    <div className="sticky top-cabecalho z-10 flex items-center gap-2 border-b border-border bg-background px-celula-x py-2">
      {/* `role="search"` e não um `<form>`: não há submissão — o filtro aplica-se
          a cada tecla e o estado vive no URL, logo não há nada para enviar. */}
      <div role="search" className="relative min-w-0 flex-1 sm:max-w-xs">
        <Label htmlFor="procurar-artigo" className="sr-only">
          {textos.filtros.procurar}
        </Label>
        <Search
          aria-hidden="true"
          className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground"
        />
        <Input
          id="procurar-artigo"
          name="q"
          type="search"
          value={rascunho}
          onChange={(evento) => {
            setRascunho(evento.target.value);
          }}
          placeholder={textos.filtros.procurarPista}
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
          aria-label={textos.filtros.localizacao}
          title={textos.filtros.localizacaoPista}
          className="w-28 shrink-0 sm:w-40"
        >
          <SelectValue placeholder={textos.filtros.todas} />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={TODAS}>{textos.filtros.todas}</SelectItem>
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
