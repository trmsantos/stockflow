import { FlaskConical, MoveRight } from "lucide-react";

import { FatiaDeErp } from "@/dev/identidade/fatia-de-erp";
import { FICHAS, type ChaveDeIdentidade, type FichaDeIdentidade } from "@/dev/identidade/dados";
import { Medidas } from "@/dev/identidade/medidas";
import { TelaDeEntrar, type EstadoDaTela } from "@/dev/identidade/tela-de-entrar";

import "@/dev/identidades.css";

/**
 * `/dev/identidade-a` e `/dev/identidade-b` — duas propostas de identidade
 * visual **opostas**, para a escolha ser real. Não é produto e não entra no
 * build: as rotas e o `import()` vivem dentro do ramo `import.meta.env.DEV` do
 * `routes/router.tsx`, logo o Rollup elimina este chunk e o CSS que ele traz.
 *
 * As duas rotas renderizam **o mesmo JSX**, byte a byte — o mesmo ecrã de
 * login e a mesma fatia de ERP. O que muda é o `data-identidade` do invólucro,
 * e com ele as dezoito cores, a família e a escala de letra, o raio, a sombra,
 * a altura da linha, o ar da célula e o peso do cromado. Se o conteúdo
 * variasse, a diferença que se vê deixava de ser só a identidade.
 *
 * Porque é um invólucro e não dois `tokens.css`: o
 * `scripts/check-design-tokens.mjs` exige que o `tokens.css` e o `DESIGN.md` §2
 * sejam iguais token a token, e duas paletas não cabem as duas nessa igualdade.
 * A redefinição local deixa o gate intacto — e as duas paletas continuam a ser
 * medidas, na secção do fim de cada rota, com a mesma matriz de pares que a
 * `/dev/tokens` usa.
 *
 * **O `position: fixed` é deliberado e é uma dívida conhecida.** A rota raiz é
 * o `AppShell` (ADR 0008), por isso qualquer rota nasce dentro da barra lateral
 * e da tab bar actuais — que é precisamente o invólucro que estas propostas
 * substituem. Enquanto o ramo público da ADR 0010 não existir, a página tapa o
 * shell em vez de lhe escapar pela árvore de rotas. A alternativa era mexer na
 * raiz, que é trabalho da ADR 0010 e não deste ficheiro.
 */

function ParDeValores({
  titulo,
  pares,
}: {
  readonly titulo: string;
  readonly pares: readonly (readonly [string, string])[];
}) {
  return (
    <div className="flex flex-col gap-2">
      <h3 data-microrotulo className="text-xs font-medium text-muted-foreground">
        {titulo}
      </h3>
      <dl className="flex flex-col gap-1.5 text-sm">
        {pares.map(([chave, valor]) => (
          <div key={chave} className="flex flex-col gap-0.5 sm:flex-row sm:gap-3">
            <dt className="shrink-0 font-medium sm:w-56">{chave}</dt>
            <dd className="min-w-0 text-muted-foreground">{valor}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function Lista({ titulo, itens }: { readonly titulo: string; readonly itens: readonly string[] }) {
  return (
    <div className="flex flex-col gap-2">
      <h3 data-microrotulo className="text-xs font-medium text-muted-foreground">
        {titulo}
      </h3>
      <ul className="flex flex-col gap-1.5 text-sm">
        {itens.map((item) => (
          <li key={item} className="flex gap-2">
            <span aria-hidden="true" className="text-muted-foreground">
              —
            </span>
            <span className="min-w-0">{item}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Ficha({ ficha }: { readonly ficha: FichaDeIdentidade }) {
  return (
    <section data-painel data-ritmo className="flex flex-col p-6">
      <div className="flex flex-col gap-2">
        <p data-microrotulo className="text-xs font-medium text-muted-foreground">
          Identidade {ficha.chave.toUpperCase()}
        </p>
        <h2 translate="no" className="font-heading text-3xl font-semibold text-balance">
          {ficha.nome}
        </h2>
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-1">
            <h3 data-microrotulo className="text-xs font-medium text-muted-foreground">
              Referência
            </h3>
            <p className="font-medium">{ficha.referencia}</p>
            <p className="text-sm text-muted-foreground">{ficha.ecra}</p>
          </div>
          <div className="flex flex-col gap-1">
            <h3 data-microrotulo className="text-xs font-medium text-muted-foreground">
              Porque serve este público
            </h3>
            <p className="max-w-prose text-sm text-pretty">{ficha.razao}</p>
          </div>
          <div className="flex flex-col gap-1">
            <h3 data-microrotulo className="text-xs font-medium text-muted-foreground">
              O que recusa
            </h3>
            <p className="max-w-prose text-sm text-pretty text-muted-foreground">{ficha.recusa}</p>
          </div>
        </div>

        <div className="flex flex-col gap-6">
          <ParDeValores titulo="Tipografia" pares={ficha.tipografia} />
          <ParDeValores titulo="Forma, sombra e espaçamento" pares={ficha.forma} />
        </div>
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <Lista titulo="Consequência na densidade e no cromado" itens={ficha.consequencias} />
        <Lista titulo="O que custa, se for esta" itens={ficha.custos} />
      </div>
    </section>
  );
}

const ESTADOS_DA_TELA: readonly (readonly [EstadoDaTela, string])[] = [
  ["normal", "Em repouso"],
  ["erro", "Credenciais recusadas"],
  ["a-submeter", "A submeter"],
];

function Pagina({ chave }: { readonly chave: ChaveDeIdentidade }) {
  const ficha = FICHAS[chave];
  const outra = FICHAS[chave === "a" ? "b" : "a"];

  return (
    // `fixed` para tapar o shell actual — ver a nota no topo do ficheiro.
    <div className="fixed inset-0 z-30 overflow-y-auto overscroll-contain bg-background text-foreground">
      {/* A barra de desenvolvimento fica **fora** do invólucro e usa os tokens
          actuais do projeto, de propósito: é andaime, e não pode ser confundida
          com a proposta que está abaixo dela. */}
      <div className="sticky top-0 z-10 flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-border bg-surface px-4 py-2 text-sm">
        <span className="flex items-center gap-2 font-medium">
          <FlaskConical aria-hidden="true" className="size-4 shrink-0 text-muted-foreground" />
          Proposta {ficha.chave.toUpperCase()} · {ficha.nome}
        </span>
        <span className="text-muted-foreground">
          Rota de desenvolvimento. Maqueta estática: nada navega e nada submete.
        </span>
        <a
          href={`/dev/identidade-${outra.chave}`}
          className="ml-auto flex items-center gap-1.5 rounded-lg text-primary underline underline-offset-4 hover:text-foreground"
        >
          Ver a proposta {outra.chave.toUpperCase()} · {outra.nome}
          <MoveRight aria-hidden="true" className="size-4 shrink-0" />
        </a>
        <a
          href="/dev/tokens"
          className="text-primary underline underline-offset-4 hover:text-foreground"
        >
          Tokens em vigor
        </a>
      </div>

      <div data-identidade={chave} className="min-h-full">
        <div data-ritmo className="mx-auto flex w-full max-w-7xl flex-col p-4 md:p-6">
          <h1 className="sr-only">
            Identidade {ficha.chave.toUpperCase()} — {ficha.nome}
          </h1>

          <Ficha ficha={ficha} />

          {/* 1. O ecrã de login: rota pública (ADR 0010) e a primeira tela que
              o cliente vê. Os três estados lado a lado, para se verem sem
              interagir. */}
          <section data-ritmo className="flex flex-col">
            <div className="flex flex-col gap-1">
              <h2 className="font-heading text-xl font-semibold">Entrar</h2>
              <p className="max-w-prose text-sm text-muted-foreground">
                A primeira tela que o cliente vê. Rótulo acima do campo, erro abaixo em texto e não
                só em cor, botão a submeter desativado em vez de desaparecido. Sem autenticação
                ligada: a ADR 0010 explica porque é que o servidor de fixtures não finge uma sessão.
              </p>
            </div>
            <div className="flex flex-wrap gap-4">
              {ESTADOS_DA_TELA.map(([estado, rotulo]) => (
                <div key={estado} className="flex flex-col gap-2">
                  <p data-microrotulo className="text-xs font-medium text-muted-foreground">
                    {rotulo}
                  </p>
                  <TelaDeEntrar estado={estado} />
                </div>
              ))}
            </div>
          </section>

          {/* 2. A fatia do ERP: é na tabela densa que a densidade se vê. */}
          <section data-ritmo className="flex flex-col">
            <div className="flex flex-col gap-1">
              <h2 className="font-heading text-xl font-semibold">Uma fatia do ERP</h2>
              <p className="max-w-prose text-sm text-muted-foreground">
                Barra lateral com o menu agrupado (uma lista com um nível de agrupamento, como a
                projecção por tenant da ADR 0009), cabeçalho, barra de ecrã e dez linhas de stock
                com quantidade, unidade, estado e validade. Desenhada para 1280px, que é o portátil
                real.
              </p>
            </div>
            <FatiaDeErp />
          </section>

          {/* 3. As medidas, lidas do invólucro e calculadas em runtime. */}
          <Medidas />
        </div>
      </div>
    </div>
  );
}

export function IdentidadeA() {
  return <Pagina chave="a" />;
}

export function IdentidadeB() {
  return <Pagina chave="b" />;
}
