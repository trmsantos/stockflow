import { CircleAlert, CircleCheck, Clock, PackageOpen, Plus, RotateCcw } from "lucide-react";
import type { FormEvent, ReactNode } from "react";
import { useCallback, useRef, useState, useSyncExternalStore } from "react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { contrastRatio, formatRatio, resolveColor, type ResolvedColor } from "@/dev/color";
import {
  escolherTema,
  ROTULO_DO_TEMA,
  subscreverTema,
  temaActual,
  temaDe,
  TEMAS,
} from "@/dev/tema";
import { formatCount, formatDaysAway, formatMoney, formatQuantity } from "@/lib/format";
import {
  ALL_TOKENS,
  CONTRAST_CHECKS,
  MINIMUM,
  SWATCH_CLASS,
  TOKEN_GROUPS,
  type TokenName,
} from "@/dev/tokens";

/**
 * `/dev/tokens` — a página que torna o sistema visual verificável.
 *
 * Não é UI de produto e não entra no build de produção: o `App` só a carrega
 * sob `import.meta.env.DEV`, com `lazy()`, para o chunk ser eliminado em
 * `pnpm build`.
 *
 * O que aqui se vê e não se consegue ver de outra forma: os 18 tokens como o
 * browser os resolve (não como estão escritos), o contraste real de cada par,
 * os três papéis de cada cor de estado, e as duas bordas lado a lado.
 */

type Snapshot = Readonly<Record<TokenName, ResolvedColor | null>>;

function readSnapshot(): Snapshot {
  const computed = getComputedStyle(document.documentElement);
  const entries = ALL_TOKENS.map(
    (token) => [token, resolveColor(computed.getPropertyValue(`--color-${token}`))] as const,
  );
  return Object.fromEntries(entries) as Snapshot;
}

/**
 * Os valores resolvidos dos tokens são estado *externo* ao React: vivem no
 * CSSOM. Por isso `useSyncExternalStore` e não um `useState` dentro de um
 * efeito — e o snapshot é memorizado, para o React o poder comparar por
 * identidade em vez de voltar a ler o CSSOM a cada render.
 *
 * **A subscrição voltou a 2026-10-07, e agora tem algo real para ouvir.** Entre
 * 2026-10-01 e aqui não tinha: havia uma paleta só, escura, e ela não mudava em
 * runtime. Com três paletas (ADR 0015) o que muda os valores é a troca do
 * `data-tema` no `<html>` — não o `prefers-color-scheme`, que foi o listener
 * que de lá saiu e que deixou de selecionar o que quer que seja. O cache é
 * invalidado na troca, senão a tabela media a paleta anterior e dizia que
 * estava medida.
 */
let cacheDeSnapshot: Snapshot | null = null;

function snapshotMemorizado(): Snapshot {
  cacheDeSnapshot ??= readSnapshot();
  return cacheDeSnapshot;
}

function subscreverAoTema(aoMudar: () => void): () => void {
  return subscreverTema(() => {
    cacheDeSnapshot = null;
    aoMudar();
  });
}

function useTokenSnapshot(): Snapshot {
  return useSyncExternalStore(subscreverAoTema, snapshotMemorizado, snapshotMemorizado);
}

/**
 * O selector de tema — **um interruptor de desenvolvimento, não a
 * funcionalidade**. Escreve o `data-tema` no `<html>` e não guarda nada: a
 * persistência é a preferência da pessoa no servidor (ADR 0016) e o lugar dela
 * é o pé da sidebar (ADR 0017), com casa decidida e por construir. Até aí isto
 * é a única forma de ver as três paletas a correr, e ver é o que faltava.
 */
function SelectorDeTema() {
  const tema = useSyncExternalStore(subscreverAoTema, temaActual, temaActual);

  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor="selector-de-tema">Paleta</Label>
      <Select
        value={tema}
        onValueChange={(valor) => {
          escolherTema(temaDe(valor));
        }}
      >
        <SelectTrigger id="selector-de-tema" className="w-full sm:w-80">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {TEMAS.map((nome) => (
            <SelectItem key={nome} value={nome}>
              {ROTULO_DO_TEMA[nome]}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <p className="max-w-2xl text-sm text-muted-foreground">
        Troca a paleta em vigor e volta a medir tudo o que está abaixo. Não persiste: uma recarga
        volta ao escuro, que é o default e a identidade aprovada.
      </p>
    </div>
  );
}

function Section({
  id,
  title,
  children,
}: {
  id: string;
  title: string;
  children: ReactNode;
}) {
  return (
    <section aria-labelledby={`${id}-titulo`} className="border-t border-border pt-6">
      <h2 id={`${id}-titulo`} className="scroll-mt-6 text-lg font-semibold">
        {title}
      </h2>
      <div className="mt-4">{children}</div>
    </section>
  );
}

function Swatch({ token, color }: { token: TokenName; color: ResolvedColor | null }) {
  return (
    <div className="flex items-center gap-3 rounded-lg border border-border bg-surface p-2">
      <div
        aria-hidden="true"
        className={`size-10 shrink-0 rounded-md border border-border ${SWATCH_CLASS[token]}`}
      />
      <div className="min-w-0">
        <p className="truncate font-mono text-xs">--color-{token}</p>
        <p className="truncate text-xs text-muted-foreground">
          {color ? color.value : "não resolvido"}
        </p>
        <p className="truncate text-xs text-muted-foreground">
          <span data-numeric>{color?.hex ?? "—"}</span>
          {color?.clamped === true ? " · fora do gamut sRGB, croma reduzido" : ""}
        </p>
      </div>
    </div>
  );
}

function ColorSection({ snapshot }: { snapshot: Snapshot }) {
  return (
    <div className="flex flex-col gap-6">
      {TOKEN_GROUPS.map((group) => (
        <div key={group.title}>
          <h3 className="text-sm font-medium">{group.title}</h3>
          <p className="mt-1 max-w-2xl text-sm text-muted-foreground">{group.note}</p>
          <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {group.tokens.map((token) => (
              <Swatch key={token} token={token} color={snapshot[token]} />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function ContrastSection({ snapshot }: { snapshot: Snapshot }) {
  const rows = CONTRAST_CHECKS.map((check) => {
    const foreground = snapshot[check.foreground];
    const background = snapshot[check.background];
    const ratio =
      foreground && background ? contrastRatio(foreground.luminance, background.luminance) : null;
    const minimum = MINIMUM[check.requirement];
    const passes = ratio === null ? false : ratio >= minimum;
    return { check, ratio, minimum, passes };
  });

  const failures = rows.filter((row) => row.check.requirement !== "exempt" && !row.passes);

  return (
    <div className="flex flex-col gap-3">
      {failures.length === 0 ? (
        <Alert className="border-success-border bg-success-surface">
          <CircleCheck aria-hidden="true" className="text-success" />
          <AlertTitle>Todos os pares obrigatórios passam</AlertTitle>
          <AlertDescription>
            {rows.length} pares medidos na paleta em vigor: nenhum abaixo do mínimo.
          </AlertDescription>
        </Alert>
      ) : (
        <Alert className="border-danger-border bg-danger-surface">
          <CircleAlert aria-hidden="true" className="text-danger" />
          <AlertTitle>
            {failures.length} par(es) abaixo do mínimo — é um bug de token, não de ecrã
          </AlertTitle>
          <AlertDescription>
            Corrigir em <span className="font-mono">src/styles/tokens.css</span> e reportar ao
            DESIGN.md.
          </AlertDescription>
        </Alert>
      )}

      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full border-collapse text-sm">
          <caption className="sr-only">
            Contraste WCAG 2.1 de cada par de tokens, medido na paleta em vigor
          </caption>
          <thead className="sticky top-0 bg-surface-2">
            <tr>
              <th scope="col" className="px-3 py-2 text-left font-medium">
                Frente
              </th>
              <th scope="col" className="px-3 py-2 text-left font-medium">
                Fundo
              </th>
              <th scope="col" className="px-3 py-2 text-left font-medium">
                Papel
              </th>
              <th scope="col" className="px-3 py-2 text-right font-medium">
                Medido
              </th>
              <th scope="col" className="px-3 py-2 text-right font-medium">
                Mínimo
              </th>
              <th scope="col" className="px-3 py-2 text-left font-medium">
                Estado
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map(({ check, ratio, minimum, passes }) => (
              <tr
                key={`${check.foreground}-${check.background}-${check.role}`}
                className="border-t border-border"
              >
                <td className="px-3 py-1.5 font-mono text-xs">{check.foreground}</td>
                <td className="px-3 py-1.5 font-mono text-xs">{check.background}</td>
                <td className="px-3 py-1.5 text-muted-foreground">{check.role}</td>
                <td className="px-3 py-1.5" data-numeric>
                  {ratio === null ? "—" : formatRatio(ratio)}
                </td>
                <td className="px-3 py-1.5" data-numeric>
                  {check.requirement === "exempt" ? "—" : formatRatio(minimum)}
                </td>
                <td className="px-3 py-1.5">
                  {check.requirement === "exempt" ? (
                    <span className="text-muted-foreground">isento</span>
                  ) : passes ? (
                    <span className="text-success">passa</span>
                  ) : (
                    <span className="text-danger">falha</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/** Os três papéis de cada cor de estado, e o semáforo de validade completo. */
function StateRolesSection() {
  const rows = [
    {
      state: "success" as const,
      texto: "text-success",
      banner: "border-success-border bg-success-surface",
      solido: "bg-success text-primary-foreground",
      icon: CircleCheck,
      etiqueta: "Validade folgada",
      prazo: `expira ${formatDaysAway(24)}`,
    },
    {
      state: "warning" as const,
      texto: "text-warning",
      banner: "border-warning-border bg-warning-surface",
      solido: "bg-warning text-primary-foreground",
      icon: Clock,
      etiqueta: "A expirar",
      prazo: `expira ${formatDaysAway(2)}`,
    },
    {
      state: "danger" as const,
      texto: "text-danger",
      banner: "border-danger-border bg-danger-surface",
      solido: "bg-danger text-primary-foreground",
      icon: CircleAlert,
      etiqueta: "Expirado",
      prazo: `expirou ${formatDaysAway(-1)}`,
    },
  ];

  return (
    <div className="flex flex-col gap-6">
      <p className="max-w-2xl text-sm text-pretty text-muted-foreground">
        A cor nunca comunica sozinha: cada linha tem ícone e texto. É a diferença entre uma
        etiqueta que se lê com daltonismo e uma que não.
      </p>

      {rows.map((row) => (
        <div key={row.state} className="flex flex-col gap-2">
          <h3 className="font-mono text-xs text-muted-foreground">--color-{row.state}</h3>
          <div className="grid grid-cols-1 gap-2 lg:grid-cols-3">
            <div className="rounded-lg border border-border bg-surface p-3">
              <p className="text-xs text-muted-foreground">1. texto e ícone</p>
              <p className={`mt-2 flex items-center gap-1.5 text-sm font-medium ${row.texto}`}>
                <row.icon aria-hidden="true" className="size-4" />
                {row.etiqueta}
              </p>
              <p className="mt-1 text-sm">
                Iogurte natural · <span data-numeric>{formatCount(12, "un")}</span> ·{" "}
                <span className={row.texto}>{row.prazo}</span>
              </p>
            </div>

            <Alert className={row.banner}>
              <row.icon aria-hidden="true" />
              <AlertTitle>2. preenchimento suave</AlertTitle>
              <AlertDescription>
                Texto em <span className="font-mono">foreground</span>, borda em{" "}
                <span className="font-mono">{row.state}-border</span>.
              </AlertDescription>
            </Alert>

            <div className="flex flex-col gap-2 rounded-lg border border-border bg-surface p-3">
              <p className="text-xs text-muted-foreground">3. preenchimento sólido</p>
              <Button className={row.solido}>Marcar como {row.etiqueta.toLowerCase()}</Button>
            </div>
          </div>
        </div>
      ))}

      <div className="flex flex-wrap items-center gap-2">
        <Badge className="bg-success-surface text-foreground">
          <CircleCheck aria-hidden="true" className="text-success" />
          Folgada
        </Badge>
        <Badge className="bg-warning-surface text-foreground">
          <Clock aria-hidden="true" className="text-warning" />
          {formatDaysAway(2)}
        </Badge>
        <Badge className="bg-danger-surface text-foreground">
          <CircleAlert aria-hidden="true" className="text-danger" />
          Expirado
        </Badge>
      </div>
    </div>
  );
}

function BordersSection() {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
      <div className="rounded-lg border border-border bg-surface p-4">
        <p className="font-mono text-xs">--color-border</p>
        <p className="mt-1 text-sm text-muted-foreground">
          Separador decorativo. ~1.3:1 de propósito — está fora da regra dos 3:1, que se aplica a
          fronteiras que identificam componentes.
        </p>
        <div className="mt-3 divide-y divide-border rounded-md border border-border">
          <p className="px-3 py-2 text-sm">Farinha T65</p>
          <p className="px-3 py-2 text-sm">Manteiga sem sal</p>
          <p className="px-3 py-2 text-sm">Ovos classe M</p>
        </div>
      </div>

      <div className="rounded-lg border border-border bg-surface p-4">
        <p className="font-mono text-xs">--color-border-strong</p>
        <p className="mt-1 text-sm text-muted-foreground">
          Fronteira de componente: 3.2:1. Um input delimitado com o separador decorativo é um bug
          de acessibilidade — o `border-input` do shadcn aponta para aqui.
        </p>
        <div className="mt-3 flex flex-col gap-1.5">
          <Label htmlFor="demo-borda">Quantidade recebida</Label>
          <Input
            id="demo-borda"
            name="quantidade"
            type="text"
            inputMode="decimal"
            autoComplete="off"
            placeholder="ex.: 12,5"
            className="font-mono tabular-nums"
          />
        </div>
      </div>
    </div>
  );
}

function TypographySection() {
  const escala = [
    { classe: "text-xs", rem: "0.8125rem" },
    { classe: "text-sm", rem: "0.9375rem" },
    { classe: "text-base", rem: "1rem" },
    { classe: "text-lg", rem: "1.125rem" },
    { classe: "text-xl", rem: "1.25rem" },
    { classe: "text-2xl", rem: "1.5rem" },
    { classe: "text-3xl", rem: "2rem" },
    { classe: "text-4xl", rem: "2.5rem" },
    { classe: "text-5xl", rem: "3.25rem" },
  ];

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-2">
        <p className="max-w-2xl text-sm text-muted-foreground">
          Archivo (500/600/700 — a família não tem 400) e IBM Plex Mono (400), servidas do
          bundle. Se isto aparecer em Helvetica ou system-ui, as fontes não carregaram.
        </p>
        <div className="rounded-lg border border-border bg-surface p-4">
          <p className="text-2xl font-medium">O que falta comprar hoje</p>
          <p className="text-2xl font-semibold">O que falta comprar hoje</p>
          <p className="text-2xl font-bold tracking-microrotulo uppercase">Rótulo de coluna</p>
        </div>
      </div>

      <div className="flex flex-col gap-1 rounded-lg border border-border bg-surface p-4">
        {escala.map((passo) => (
          <div key={passo.classe} className="flex items-baseline justify-between gap-4">
            <span className={passo.classe}>Stock mínimo</span>
            <span className="shrink-0 font-mono text-xs text-muted-foreground">
              {passo.classe} · {passo.rem}
            </span>
          </div>
        ))}
      </div>

      <div className="rounded-lg border border-border bg-surface p-4">
        <p className="text-sm text-muted-foreground">
          Quantidades e dinheiro em mono, tabulares, alinhados à direita, com unidade visível:
        </p>
        <table className="mt-2 w-full text-sm">
          <caption className="sr-only">Exemplo de alinhamento numérico</caption>
          <thead>
            <tr className="border-b border-border">
              <th scope="col" className="py-1 text-left font-medium">
                Artigo
              </th>
              <th scope="col" className="py-1 text-right font-medium">
                Quantidade
              </th>
              <th scope="col" className="py-1 text-right font-medium">
                Custo
              </th>
            </tr>
          </thead>
          <tbody>
            <tr className="border-b border-border">
              <td className="py-1">Farinha T65</td>
              <td className="py-1" data-numeric>
                {formatQuantity(125, "kg")}
              </td>
              <td className="py-1" data-numeric>
                {formatMoney("78.40")}
              </td>
            </tr>
            <tr className="border-b border-border">
              <td className="py-1">Manteiga sem sal</td>
              <td className="py-1" data-numeric>
                {formatQuantity("8.5", "kg")}
              </td>
              <td className="py-1" data-numeric>
                {formatMoney("61.20")}
              </td>
            </tr>
            <tr>
              <td className="py-1">Ovos classe M</td>
              <td className="py-1" data-numeric>
                {formatCount(360, "un")}
              </td>
              <td className="py-1" data-numeric>
                {formatMoney("43.20")}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}

function SpacingShapeSection() {
  const passos = [1, 2, 3, 4, 6, 8, 12, 16, 24, 32];
  const larguras: Readonly<Record<number, string>> = {
    1: "w-1",
    2: "w-2",
    3: "w-3",
    4: "w-4",
    6: "w-6",
    8: "w-8",
    12: "w-12",
    16: "w-16",
    24: "w-24",
    32: "w-32",
  };

  return (
    <div className="flex flex-col gap-6">
      <div className="rounded-lg border border-border bg-surface p-4">
        <h3 className="text-sm font-medium">Espaçamento: grelha de 4px</h3>
        <div className="mt-3 flex flex-col gap-1">
          {passos.map((passo) => (
            <div key={passo} className="flex items-center gap-3">
              <span className="w-20 shrink-0 font-mono text-xs text-muted-foreground">
                {passo} · {passo * 4}px
              </span>
              <span
                aria-hidden="true"
                className={`h-3 rounded-xs bg-primary ${larguras[passo] ?? "w-1"}`}
              />
            </div>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="rounded-lg border border-border bg-surface p-4">
          <h3 className="text-sm font-medium">Forma: 4 · 6 · 8 · 12px</h3>
          <div className="mt-3 flex items-end gap-3">
            <div className="flex flex-col items-center gap-1">
              <div aria-hidden="true" className="size-14 rounded-md border border-border bg-surface-2" />
              <span className="font-mono text-xs text-muted-foreground">md · 6px</span>
            </div>
            <div className="flex flex-col items-center gap-1">
              <div aria-hidden="true" className="size-14 rounded-lg border border-border bg-surface-2" />
              <span className="font-mono text-xs text-muted-foreground">base · 8px</span>
            </div>
            <div className="flex flex-col items-center gap-1">
              <div aria-hidden="true" className="size-14 rounded-xl border border-border bg-surface-2" />
              <span className="font-mono text-xs text-muted-foreground">xl · 12px</span>
            </div>
          </div>
        </div>

        <div className="rounded-lg border border-border bg-surface p-4">
          <h3 className="text-sm font-medium">Sombra: dois níveis</h3>
          <div className="mt-3 flex flex-wrap items-center gap-4">
            <div className="rounded-lg border border-border bg-surface p-3 shadow-sm">
              <p className="text-sm">shadow-sm</p>
              <p className="text-xs text-muted-foreground">cards</p>
            </div>
            <div className="rounded-lg border border-border bg-surface p-3 shadow-lg">
              <p className="text-sm">shadow-lg</p>
              <p className="text-xs text-muted-foreground">popovers</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function ComponentStatesSection() {
  const [submetido, setSubmetido] = useState(false);
  const [aGravar, setAGravar] = useState(false);
  const [quantidade, setQuantidade] = useState("");
  const campoQuantidade = useRef<HTMLInputElement>(null);

  const erro = submetido && quantidade.trim() === "" ? "Indica a quantidade recebida." : null;

  const aoSubmeter = useCallback(
    (evento: FormEvent<HTMLFormElement>) => {
      evento.preventDefault();
      setSubmetido(true);
      // O foco vai para o primeiro campo com erro: quem submete de telemóvel
      // não tem como saber onde falhou se o foco ficar no botão.
      if (quantidade.trim() === "") campoQuantidade.current?.focus();
    },
    [quantidade],
  );

  return (
    <div className="flex flex-col gap-6">
      <div className="rounded-lg border border-border bg-surface p-4">
        <h3 className="text-sm font-medium">Botões</h3>
        <p className="mt-1 text-sm text-muted-foreground">
          Hover com o rato, Tab para ver o anel de foco. Em ecrã de toque todos passam a 44px de
          altura mínima.
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          <Button>Receber fatura</Button>
          <Button variant="secondary">Guardar rascunho</Button>
          <Button variant="outline">Cancelar</Button>
          <Button variant="ghost">Ver histórico</Button>
          <Button variant="destructive">Anular receção</Button>
          <Button disabled>Indisponível</Button>
          <Button
            aria-busy={aGravar}
            disabled={aGravar}
            onClick={() => {
              setAGravar(true);
            }}
          >
            {aGravar ? "A gravar…" : "Gravar"}
          </Button>
          <Button size="icon" aria-label="Adicionar linha">
            <Plus aria-hidden="true" />
          </Button>
        </div>
      </div>

      <form
        onSubmit={aoSubmeter}
        noValidate
        className="flex max-w-md flex-col gap-3 rounded-lg border border-border bg-surface p-4"
      >
        <h3 className="text-sm font-medium">Formulário: label acima, erro abaixo em texto</h3>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="quantidade">Quantidade recebida (kg)</Label>
          <Input
            ref={campoQuantidade}
            id="quantidade"
            name="quantidade"
            type="text"
            inputMode="decimal"
            autoComplete="off"
            spellCheck={false}
            placeholder="ex.: 12,5"
            value={quantidade}
            onChange={(evento) => {
              setQuantidade(evento.target.value);
            }}
            aria-invalid={erro !== null}
            {...(erro === null ? {} : { "aria-describedby": "quantidade-erro" })}
            className="font-mono tabular-nums"
          />
          {erro === null ? (
            <p className="text-xs text-muted-foreground">
              Aceita vírgula decimal. A unidade vem do artigo.
            </p>
          ) : (
            <p id="quantidade-erro" className="flex items-center gap-1.5 text-xs text-danger">
              <CircleAlert aria-hidden="true" className="size-3.5" />
              {erro}
            </p>
          )}
        </div>
        <div className="flex gap-2">
          <Button type="submit">Confirmar receção</Button>
          <Button
            type="reset"
            variant="ghost"
            onClick={() => {
              setSubmetido(false);
              setQuantidade("");
            }}
          >
            Limpar
          </Button>
        </div>
      </form>

      <div className="rounded-lg border border-border bg-surface p-4">
        <h3 className="text-sm font-medium">Etiquetas</h3>
        <div className="mt-3 flex flex-wrap gap-2">
          <Badge>Rascunho</Badge>
          <Badge variant="secondary">Confirmado</Badge>
          <Badge variant="outline">Sem stock</Badge>
          <Badge variant="destructive">Divergente</Badge>
        </div>
      </div>
    </div>
  );
}

type EstadoDeDados = "loading" | "empty" | "error" | "ready";

function DataStatesSection() {
  const [estado, setEstado] = useState<EstadoDeDados>("loading");

  const opcoes: readonly { valor: EstadoDeDados; etiqueta: string }[] = [
    { valor: "loading", etiqueta: "A carregar" },
    { valor: "empty", etiqueta: "Vazio" },
    { valor: "error", etiqueta: "Erro" },
    { valor: "ready", etiqueta: "Com dados" },
  ];

  return (
    <div className="flex flex-col gap-3">
      <div role="group" aria-label="Estado da lista" className="flex flex-wrap gap-2">
        {opcoes.map((opcao) => (
          <Button
            key={opcao.valor}
            variant={estado === opcao.valor ? "default" : "outline"}
            aria-pressed={estado === opcao.valor}
            onClick={() => {
              setEstado(opcao.valor);
            }}
          >
            {opcao.etiqueta}
          </Button>
        ))}
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Validades a expirar</CardTitle>
          <CardDescription>Os quatro estados que toda a lista tem de ter.</CardDescription>
        </CardHeader>
        <CardContent>
          {estado === "loading" && (
            <div className="flex flex-col gap-2" aria-busy="true" aria-live="polite">
              <span className="sr-only">A carregar…</span>
              {Array.from({ length: 3 }, (_, index) => (
                <div key={index} className="flex items-center justify-between gap-4">
                  <Skeleton className="h-4 w-48" />
                  <Skeleton className="h-4 w-20" />
                </div>
              ))}
            </div>
          )}

          {estado === "empty" && (
            <div className="flex flex-col items-start gap-2 py-4">
              <PackageOpen aria-hidden="true" className="size-6 text-muted-foreground" />
              <p className="text-sm font-medium">Nada a expirar nos próximos 7 dias.</p>
              <p className="text-sm text-muted-foreground">
                Quando receberes mercadoria com validade, os lotes aparecem aqui.
              </p>
              <Button>Receber fatura</Button>
            </div>
          )}

          {estado === "error" && (
            <Alert className="border-danger-border bg-danger-surface">
              <CircleAlert aria-hidden="true" className="text-danger" />
              <AlertTitle>Não foi possível carregar as validades</AlertTitle>
              <AlertDescription className="flex flex-col items-start gap-2">
                <span>A ligação falhou a meio. Os dados não se perderam.</span>
                <Button
                  variant="outline"
                  onClick={() => {
                    setEstado("loading");
                  }}
                >
                  <RotateCcw aria-hidden="true" />
                  Tentar outra vez
                </Button>
              </AlertDescription>
            </Alert>
          )}

          {estado === "ready" && (
            <table className="w-full text-sm">
              <caption className="sr-only">Lotes a expirar</caption>
              <thead>
                <tr className="border-b border-border">
                  <th scope="col" className="py-1 text-left font-medium">
                    Lote
                  </th>
                  <th scope="col" className="py-1 text-right font-medium">
                    Stock
                  </th>
                  <th scope="col" className="py-1 text-left font-medium">
                    Validade
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr className="border-b border-border">
                  <td className="py-1.5">Iogurte natural · L2291</td>
                  <td className="py-1.5" data-numeric>
                    {formatCount(12, "un")}
                  </td>
                  <td className="py-1.5">
                    <span className="flex items-center gap-1.5 text-danger">
                      <CircleAlert aria-hidden="true" className="size-3.5" />
                      expirou {formatDaysAway(-1)}
                    </span>
                  </td>
                </tr>
                <tr className="border-b border-border">
                  <td className="py-1.5">Nata 35% · L1180</td>
                  <td className="py-1.5" data-numeric>
                    {formatCount(6, "un")}
                  </td>
                  <td className="py-1.5">
                    <span className="flex items-center gap-1.5 text-warning">
                      <Clock aria-hidden="true" className="size-3.5" />
                      expira {formatDaysAway(2)}
                    </span>
                  </td>
                </tr>
                <tr>
                  <td className="py-1.5">Farinha T65 · L0043</td>
                  <td className="py-1.5" data-numeric>
                    {formatQuantity(125, "kg")}
                  </td>
                  <td className="py-1.5">
                    <span className="flex items-center gap-1.5 text-success">
                      <CircleCheck aria-hidden="true" className="size-3.5" />
                      expira {formatDaysAway(24)}
                    </span>
                  </td>
                </tr>
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export default function TokensPage() {
  const snapshot = useTokenSnapshot();

  return (
    // Desde o ADR 0008 esta página é um ecrã dentro do `AppShell`, e não uma
    // página solta: o `<main id="conteudo">` e o atalho "saltar para o
    // conteúdo" são do shell. Dois landmarks `main` na mesma página, e dois
    // elementos com o mesmo `id`, são um defeito de acessibilidade — e seria o
    // defeito mais irónico possível na página que mede a acessibilidade.
    <section className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-4 py-6">
      <header className="flex flex-col gap-2">
        <p className="font-mono text-xs text-muted-foreground">/dev/tokens</p>
        <h1 className="text-3xl font-semibold text-balance">Sistema visual</h1>
        <p className="max-w-2xl text-sm text-pretty text-muted-foreground">
          Ferramenta de desenvolvimento, não UI de produto. Mostra os tokens do DESIGN.md §2 tal
          como o browser os resolve e mede o contraste real de cada par. Não entra no build de
          produção.
        </p>
        <p className="max-w-2xl text-sm">
          Identidade <strong className="font-medium">«Cabine»</strong>, em{" "}
          <strong className="font-medium">três paletas</strong> (ADR 0015):{" "}
          <span className="font-mono">escuro</span> — o default e a identidade aprovada —,{" "}
          <span className="font-mono">claro</span> e <span className="font-mono">meio_termo</span>.
          Cada uma tem os 18 tokens de cor e as duas sombras, e cada uma passa a sua própria medição
          contra a sua pior superfície. Nas três, essa superfície é o{" "}
          <span className="font-mono">surface-2</span>: é o degrau mais afastado da tela, no escuro
          por ser o mais claro dos três pretos e no claro por ser o mais escuro dos três cinzentos.
        </p>
        <SelectorDeTema />
      </header>

      <Section id="cor" title="Cor — 18 tokens">
        <ColorSection snapshot={snapshot} />
      </Section>

      <Section id="contraste" title="Contraste medido">
        <ContrastSection snapshot={snapshot} />
      </Section>

      <Section id="estados" title="Os três papéis de cada estado">
        <StateRolesSection />
      </Section>

      <Section id="bordas" title="As duas bordas, lado a lado">
        <BordersSection />
      </Section>

      <Section id="tipografia" title="Tipografia">
        <TypographySection />
      </Section>

      <Section id="forma" title="Espaçamento, forma e sombra">
        <SpacingShapeSection />
      </Section>

      <Section id="componentes" title="Estados dos componentes">
        <ComponentStatesSection />
      </Section>

      <Section id="dados" title="Estados de dados">
        <DataStatesSection />
      </Section>
    </section>
  );
}
