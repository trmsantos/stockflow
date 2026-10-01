import { useLayoutEffect, useRef, useState } from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { contrastRatio, formatRatio, resolveColor, type ResolvedColor } from "@/dev/color";
import {
  ALL_TOKENS,
  CONTRAST_CHECKS,
  MINIMUM,
  SWATCH_CLASS,
  TOKEN_GROUPS,
  type TokenName,
} from "@/dev/tokens";

/**
 * As medidas da identidade — **medidas, não presumidas**.
 *
 * Isto não lê uma tabela de números escrita à mão: lê as dezoito variáveis como
 * o browser as resolve dentro do invólucro (`getComputedStyle` de um elemento
 * que está lá dentro, porque uma propriedade personalizada herda-se já
 * resolvida), projeta cada `oklch()` em sRGB, reduz o croma se o valor não
 * couber no gamut — e diz que o fez — e calcula o contraste WCAG 2.1. Se eu
 * mudar um valor no `identidades.css` e me esquecer de mudar o número aqui, não
 * há número aqui para esquecer.
 *
 * A matriz de pares é a **mesma** que a `/dev/tokens` usa (`CONTRAST_CHECKS` do
 * `dev/tokens.ts`): os papéis vêm do nome do token, as barras são 4.5:1 para
 * texto e 3:1 para fronteira de componente, e a medição é contra as três
 * superfícies e não só contra a melhor. O `--color-border` entra marcado como
 * isento, porque um separador decorativo entre superfícies está fora da regra
 * dos 3:1 — e aparece na lista para a isenção ser visível em vez de silenciosa.
 *
 * Um valor fora do gamut sRGB é distorcido pelo browser em silêncio, e a partir
 * daí o contraste que se mede não é o contraste que se vê. Por isso o gamut é
 * uma coluna e não uma nota de pé.
 */

type Leitura = Readonly<Record<TokenName, ResolvedColor | null>>;

function lerTokens(elemento: HTMLElement): Leitura {
  const computado = getComputedStyle(elemento);
  const entradas = ALL_TOKENS.map(
    (token) => [token, resolveColor(computado.getPropertyValue(`--color-${token}`))] as const,
  );
  return Object.fromEntries(entradas) as Leitura;
}

interface Medida {
  readonly chave: string;
  readonly tinta: TokenName;
  readonly fundo: TokenName;
  readonly papel: string;
  readonly minimo: number;
  readonly razao: number | null;
  readonly isento: boolean;
  readonly passa: boolean;
}

function medir(leitura: Leitura): readonly Medida[] {
  return CONTRAST_CHECKS.map((par) => {
    const tinta = leitura[par.foreground];
    const fundo = leitura[par.background];
    const minimo = MINIMUM[par.requirement];
    const isento = par.requirement === "exempt";
    const razao =
      tinta === null || fundo === null ? null : contrastRatio(tinta.luminance, fundo.luminance);
    return {
      chave: `${par.foreground}-sobre-${par.background}-${par.role}`,
      tinta: par.foreground,
      fundo: par.background,
      papel: par.role,
      minimo,
      razao,
      isento,
      passa: isento || (razao !== null && razao >= minimo),
    };
  });
}

function Amostra({ token }: { readonly token: TokenName }) {
  return (
    <span
      aria-hidden="true"
      className={`inline-block size-3.5 shrink-0 rounded-sm border border-border-strong ${SWATCH_CLASS[token]}`}
    />
  );
}

function Paleta({ leitura }: { readonly leitura: Leitura }) {
  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      {TOKEN_GROUPS.map((grupo) => (
        <div key={grupo.title} data-painel className="flex flex-col gap-2 p-4">
          <h3 className="font-heading text-base font-semibold">{grupo.title}</h3>
          <p className="text-xs text-muted-foreground">{grupo.note}</p>
          <ul className="flex flex-col gap-1.5">
            {grupo.tokens.map((token) => {
              const cor = leitura[token];
              return (
                <li key={token} className="flex items-center gap-2 text-xs">
                  <Amostra token={token} />
                  <code translate="no" className="min-w-0 flex-1 truncate font-mono">
                    --color-{token}
                  </code>
                  <span data-numeric className="shrink-0 text-muted-foreground">
                    {cor?.hex ?? "—"}
                  </span>
                  {cor?.clamped === true ? (
                    <span className="shrink-0 font-medium text-danger">fora do gamut</span>
                  ) : null}
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </div>
  );
}

function TabelaDeMedidas({ medidas }: { readonly medidas: readonly Medida[] }) {
  // As falhas primeiro: se houver uma, é o que interessa ver, e uma identidade
  // bonita que falha contraste não é uma opção.
  const ordenadas = [...medidas].sort((primeira, segunda) => {
    if (primeira.passa !== segunda.passa) return primeira.passa ? 1 : -1;
    return 0;
  });

  return (
    <div data-painel className="overflow-x-auto">
      <table className="w-full border-collapse text-xs">
        <caption className="sr-only">
          Contraste WCAG 2.1 medido por par de tokens, com a barra que cada papel exige.
        </caption>
        <thead>
          <tr className="border-b border-border">
            {["Tinta", "Sobre", "Papel", "Medido", "Mínimo", "Veredicto"].map((rotulo, indice) => (
              <th
                key={rotulo}
                scope="col"
                data-numeric={indice === 3 || indice === 4 ? "" : undefined}
                className="px-3 py-2 text-left font-medium text-muted-foreground"
              >
                {rotulo}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {ordenadas.map((medida) => (
            <tr key={medida.chave} className="border-b border-border last:border-b-0">
              <td className="px-3 py-1.5">
                <span className="flex items-center gap-2">
                  <Amostra token={medida.tinta} />
                  <code translate="no" className="font-mono">
                    {medida.tinta}
                  </code>
                </span>
              </td>
              <td className="px-3 py-1.5">
                <span className="flex items-center gap-2">
                  <Amostra token={medida.fundo} />
                  <code translate="no" className="font-mono">
                    {medida.fundo}
                  </code>
                </span>
              </td>
              <td className="px-3 py-1.5 text-muted-foreground">{medida.papel}</td>
              <td data-numeric className="px-3 py-1.5">
                {medida.razao === null ? "—" : formatRatio(medida.razao)}
              </td>
              <td data-numeric className="px-3 py-1.5 text-muted-foreground">
                {medida.isento ? "—" : formatRatio(medida.minimo)}
              </td>
              <td className="px-3 py-1.5">
                {/* Nunca só a cor: a palavra diz o mesmo que a tinta. */}
                {medida.isento ? (
                  <span className="text-muted-foreground">isento</span>
                ) : medida.passa ? (
                  <span className="text-success">passa</span>
                ) : (
                  <span className="font-medium text-danger">falha</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Medidas() {
  const ancora = useRef<HTMLDivElement>(null);
  const [leitura, setLeitura] = useState<Leitura | null>(null);

  // `useLayoutEffect` e não `useEffect`: o valor lê-se do estilo computado, o
  // que exige o nó no documento, e ler depois da pintura daria um salto visível
  // entre o esqueleto e a tabela.
  useLayoutEffect(() => {
    const elemento = ancora.current;
    if (elemento !== null) setLeitura(lerTokens(elemento));
  }, []);

  const medidas = leitura === null ? null : medir(leitura);
  const falhas = medidas?.filter((medida) => !medida.passa) ?? [];
  const foraDoGamut =
    leitura === null
      ? []
      : ALL_TOKENS.filter((token) => leitura[token]?.clamped === true);
  const margem = medidas
    ?.filter((medida) => !medida.isento && medida.razao !== null)
    .reduce(
      (pior, medida) => Math.min(pior, (medida.razao ?? 0) - medida.minimo),
      Number.POSITIVE_INFINITY,
    );

  return (
    <section ref={ancora} data-ritmo className="flex flex-col">
      <div className="flex flex-col gap-1">
        <h2 className="font-heading text-xl font-semibold">Medidas desta paleta</h2>
        <p className="max-w-prose text-sm text-muted-foreground">
          Lidas do invólucro com <code translate="no" className="font-mono">getComputedStyle</code> e calculadas
          aqui: projeção em sRGB, gamut e contraste WCAG 2.1 contra as três superfícies. Os papéis
          vêm do nome do token, como no gate do <code translate="no" className="font-mono">pnpm lint</code>.
        </p>
      </div>

      {leitura === null || medidas === null ? (
        <div data-painel className="flex flex-col gap-2 p-4" aria-busy="true">
          <span className="sr-only">A medir a paleta…</span>
          {[0, 1, 2, 3, 4, 5].map((indice) => (
            <Skeleton key={indice} className="h-4 w-full" />
          ))}
        </div>
      ) : (
        <>
          <p
            aria-live="polite"
            className={`text-sm ${falhas.length === 0 && foraDoGamut.length === 0 ? "" : "text-danger"}`}
          >
            <span data-numeric>{medidas.length}</span> pares medidos ·{" "}
            <span data-numeric>{falhas.length}</span> abaixo da barra ·{" "}
            <span data-numeric>{foraDoGamut.length}</span> tokens fora do gamut sRGB · pior margem{" "}
            <span data-numeric>
              {margem === undefined || !Number.isFinite(margem) ? "—" : `+${margem.toFixed(3)}`}
            </span>
          </p>

          <Paleta leitura={leitura} />
          <TabelaDeMedidas medidas={medidas} />
        </>
      )}
    </section>
  );
}
