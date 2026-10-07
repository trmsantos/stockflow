import { useMemo, useState } from "react";
import {
  ArrowDown,
  ArrowUp,
  CircleAlert,
  Eye,
  EyeOff,
  FlaskConical,
  RotateCcw,
  Save,
} from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
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
import {
  CLASSE_CELULA,
  CLASSE_LINHA,
  EsqueletoDeTabela,
  MolduraDeTabela,
  TrilhoDaLinha,
  type ColunaDeTabela,
} from "@/components/tabela";
import { mensagemDeErro } from "@/lib/api/errors";

import {
  useConfiguracaoDoEstabelecimento,
  useGuardarEstabelecimento,
  useGuardarMenu,
  useRotasDeMenu,
  useSessao,
} from "../api";
import {
  nomeDoPapel,
  type ConfiguracaoDoEstabelecimento,
  type ItemDeMenuParaGuardar,
  type Papel,
  type RegimeDeIva,
  type RotaDeMenu,
} from "../schemas";

/**
 * `/configuracao` — as definições **da empresa** (ADR 0017).
 *
 * É o segundo dos dois ecrãs que a ADR 0017 separou, e a separação é de
 * autorização e não de arrumação: um `staff` muda o seu tema no `/preferencias`
 * e não muda nada aqui. O que torna isso legível **no menu** é que esta rota
 * entra no registo com `papeis = {owner}` — a um `staff` o item simplesmente não
 * existe, em vez de existir e levar a um 403.
 *
 * ## O que está aqui hoje: o menu, que é a configuração que já existe
 *
 * A ADR 0011 decidiu que a configuração por tenant existe em três formas e que
 * **não** há motor genérico de configuração. Deste ecrã, a forma que já está
 * implementada ponta a ponta é a terceira: a projecção por tenant sobre o
 * registo de rotas, com `GET /menu/rotas` e `PUT /menu` — dois endpoints que
 * existem desde essa ADR e que **nunca tiveram consumidor**. Este ecrã é esse
 * consumidor, e o `MenuView` do backend já tinha escrito o que ele precisava de
 * fazer ("invalidar `queryKeys.sessao()` no `onSuccess` do `PUT`").
 *
 * ## Como se compõe a lista a editar, e a consequência que a ADR nomeia
 *
 * **Não há `GET /menu`, e é decisão e não esquecimento**: o menu efectivo viaja
 * no `GET /auth/sessao` e o registo no `GET /menu/rotas`, logo um terceiro
 * endpoint seria uma terceira fonte para a mesma lista. A lista editável nasce
 * do cruzamento dos dois: o registo diz **o que existe** (com os defaults) e a
 * sessão diz **o que esta empresa decidiu**.
 *
 * A consequência está escrita na ADR 0017 e repete-se aqui porque é deste ecrã:
 * o `menu` da sessão **é** filtrado pelo papel, pelo que um `owner` só configura
 * as rotas que o papel dele vê. Hoje coincide — as três rotas restritas são
 * todas restritas **ao** `owner` —, e no dia em que uma rota for visível a um
 * papel que quem configura não tem, este ecrã passa a precisar de um `GET /menu`
 * sem filtro. É um gatilho, não uma dívida a pagar agora.
 *
 * ## A identidade da casa, e o que cada campo decide
 *
 * O `nome`, o regime de IVA e a hora a que o dia de negócio começa vêm do
 * `GET /estabelecimento`. Os dois últimos não são preferências: **decidem
 * cálculos**, e o ecrã diz o que decidem em vez de os apresentar como opções.
 *
 * O **regime de IVA** decide se o IVA de uma compra é custo — em regime normal é
 * dedutível e o custo é a base tributável; no art. 53.º não é dedutível e o custo
 * é o total da fatura. O rótulo é "Regime de IVA" e nunca "Regime", porque o que
 * um dono chama "simplificado" é o regime de **IRS** e metade das respostas seria
 * sobre outro imposto (`domain-expert`, 2026-10-07).
 *
 * A **hora a que o dia de negócio começa** decide a que dia pertence um
 * movimento e onde começa o mês. O aviso de que mudá-la **recalcula** os dias
 * passados aparece antes de gravar e não depois: é retroactivo de propósito (a
 * alternativa, histórico da hora, parte o invariante `Σ(dias) == mês` da ADR
 * 0013), e o efeito real limita-se aos movimentos registados entre as duas horas.
 * E diz-se o que ela **não** decide, porque é o erro que alguém escreveria: as
 * validades são a data impressa na embalagem e não se deslocam com este relógio.
 *
 * ## O que **não** está aqui, e porquê
 *
 * **O horizonte de validade não entra, e é uma decisão e não falta de tempo.** É
 * literalmente o campo de que a proibição nº 7 do guião da sessão 0 fala — mostrar
 * um limiar remove o sinal que diz qual é o default certo —, é o único destes cujo
 * default ninguém consegue dar sem um utilizador real, e um número único por casa
 * é estruturalmente errado: a 3 dias, o pastel de nata e o morango ficam em alerta
 * permanente desde que entram e a farinha é avisada 3 dias antes de um DDM a 9
 * meses. A forma certa é por família de produto, com queda para a casa, e a ADR
 * 0017 já a pôs **num endpoint separado** — logo omiti-la aqui custa zero em
 * arquitectura. O critério que ficou escrito: *mostra-se o valor em vigor quando
 * ele explica um número que o utilizador já viu acontecer; não se mostra um valor
 * que ele ainda não viu agir.* A hora passa esse teste (o rótulo "desde as 04:00"
 * dos Alertas já a mostrou a agir); o limiar não.
 *
 * O **NIF** também não: exige `nif_encrypted` + `nif_hmac` com pepper fora da base
 * de dados (`SECURITY.md` §3) e tem a questão do NIF duplicado em aberto desde a
 * ADR 0007. É sessão própria.
 *
 * A configuração do `inventory` (limiares, unidades) não está aqui e não é por
 * falta de tempo: a tabela não existe e o conteúdo dela é do `inventory`. Quando
 * existir, este ecrã lê-a pela porta pré-aprovada da ADR 0008
 * (`@/features/inventory/api`), que é a única aresta entre features que o
 * `eslint.config.js` permite.
 *
 * As unidades e os mínimos **nunca** vêm para cá: são colunas do artigo (ADR
 * 0011, forma 1), editadas na linha do artigo. Pô-los num ecrã de configurações
 * é o armazém chave/valor indexado por `product_id` que a ADR 0011 recusou, com
 * passos a mais.
 */

/** Os dois regimes por extenso, e **o que cada um faz ao custo**. */
const REGIMES: Record<RegimeDeIva, { readonly nome: string; readonly efeito: string }> = {
  normal: {
    nome: "Regime normal",
    efeito: "O IVA das compras é dedutível, logo o custo de um artigo é o valor sem IVA.",
  },
  isento_art_53: {
    nome: "Isento (art. 53.º)",
    efeito: "O IVA das compras não é dedutível, logo é custo: entra no valor do stock.",
  },
};

const REGIMES_POR_NOME = new Map(Object.entries(REGIMES));

function BlocoDoEstabelecimento() {
  const configuracao = useConfiguracaoDoEstabelecimento(true);
  const guardar = useGuardarEstabelecimento();

  /**
   * O rascunho. `null` até haver resposta, pela razão do rascunho do menu: com um
   * objecto vazio por omissão, o botão de guardar ficava activo sobre campos que
   * ninguém viu.
   */
  const [rascunho, setRascunho] = useState<ConfiguracaoDoEstabelecimento | null>(null);

  if (configuracao.isPending) {
    return (
      <div aria-busy="true" className="flex max-w-xl flex-col gap-4">
        <span className="sr-only">A carregar a configuração do estabelecimento…</span>
        <Skeleton className="h-9 w-full" />
        <Skeleton className="h-9 w-full" />
        <Skeleton className="h-9 w-40" />
      </div>
    );
  }

  if (configuracao.isError) {
    return (
      <Alert variant="destructive">
        <CircleAlert aria-hidden="true" />
        <AlertTitle>Não foi possível ler a configuração</AlertTitle>
        <AlertDescription>{mensagemDeErro(configuracao.error)}</AlertDescription>
      </Alert>
    );
  }

  const actual = configuracao.data;
  const valores = rascunho ?? actual;
  const mexido = rascunho !== null;
  const horaMudou = valores.business_day_starts_at !== actual.business_day_starts_at;

  function mudar(mudanca: Partial<ConfiguracaoDoEstabelecimento>) {
    setRascunho({ ...valores, ...mudanca });
  }

  return (
    <div className="flex max-w-xl flex-col gap-4">
      {actual.demonstracao ? (
        <Alert>
          <FlaskConical aria-hidden="true" />
          <AlertTitle>Este é o estabelecimento de demonstração</AlertTitle>
          <AlertDescription>
            Os dados foram semeados para experimentar e não são de um negócio real. O nome não se
            altera aqui; o resto da configuração muda como em qualquer casa.
          </AlertDescription>
        </Alert>
      ) : null}

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="nome-do-estabelecimento">Nome</Label>
        <Input
          id="nome-do-estabelecimento"
          value={valores.nome}
          maxLength={200}
          disabled={guardar.isPending || actual.demonstracao}
          onChange={(evento) => {
            mudar({ nome: evento.target.value });
          }}
        />
        <p className="text-xs text-muted-foreground">
          Como aparece no seletor de estabelecimento e no topo dos ecrãs.
        </p>
      </div>

      <div className="flex flex-col gap-1.5">
        {/* "Regime de IVA" e nunca "Regime": o que um dono chama "simplificado"
            é o regime de IRS, e metade das respostas seria sobre outro imposto. */}
        <Label htmlFor="regime-de-iva">Regime de IVA</Label>
        <Select
          value={valores.vat_regime}
          disabled={guardar.isPending}
          onValueChange={(escolhido) => {
            const regime = REGIMES_POR_NOME.has(escolhido)
              ? (escolhido as RegimeDeIva)
              : valores.vat_regime;
            mudar({ vat_regime: regime });
          }}
        >
          <SelectTrigger id="regime-de-iva" className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {Object.entries(REGIMES).map(([valor, { nome }]) => (
              <SelectItem key={valor} value={valor}>
                {nome}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <p className="text-xs text-pretty text-muted-foreground">
          {REGIMES_POR_NOME.get(valores.vat_regime)?.efeito}
        </p>
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="dia-de-negocio">O dia de negócio começa às</Label>
        {/* `type="time"` com `step={60}`: o controlo nativo é o que dá o teclado
            certo no telemóvel e o formato local. O `step` tira os segundos do
            picker, que o contrato não transporta. */}
        <Input
          id="dia-de-negocio"
          type="time"
          step={60}
          className="w-32"
          value={valores.business_day_starts_at}
          disabled={guardar.isPending}
          onChange={(evento) => {
            mudar({ business_day_starts_at: evento.target.value });
          }}
        />
        <p className="text-xs text-pretty text-muted-foreground">
          É a hora que separa um dia do seguinte nos totais e nos alertas. Com{" "}
          {actual.business_day_starts_at}, o que acontece à 01:30 conta no dia anterior, e o mês vai
          do dia 1 às {actual.business_day_starts_at} ao dia 1 do mês seguinte à mesma hora — não é
          o mês fiscal. <strong>As validades não mudam com esta hora</strong>: são a data impressa
          na embalagem.
        </p>
        {horaMudou ? (
          // O aviso aparece **antes** de gravar e só quando a hora mudou. É
          // retroactivo de propósito (a alternativa parte o invariante do mês da
          // ADR 0013), e dizê-lo é o que separa uma decisão de uma surpresa.
          <Alert>
            <CircleAlert aria-hidden="true" />
            <AlertTitle>Mudar esta hora recalcula os dias e os meses já passados</AlertTitle>
            <AlertDescription>
              Só mudam de dia os movimentos registados entre as{" "}
              {actual.business_day_starts_at} e as {valores.business_day_starts_at}.
            </AlertDescription>
          </Alert>
        ) : null}
      </div>

      {guardar.isError ? (
        <Alert variant="destructive">
          <CircleAlert aria-hidden="true" />
          <AlertTitle>A configuração não ficou guardada</AlertTitle>
          <AlertDescription>
            {mensagemDeErro(guardar.error)} O que está no ecrã é o que escreveu, e continua por
            guardar.
          </AlertDescription>
        </Alert>
      ) : null}

      <span className="flex gap-2">
        <Button
          type="button"
          disabled={!mexido || guardar.isPending}
          aria-busy={guardar.isPending}
          onClick={() => {
            guardar.mutate(
              {
                nome: valores.nome,
                vat_regime: valores.vat_regime,
                business_day_starts_at: valores.business_day_starts_at,
              },
              { onSuccess: () => { setRascunho(null); } },
            );
          }}
        >
          <Save aria-hidden="true" />
          {guardar.isPending ? "A guardar…" : "Guardar"}
        </Button>
        <Button
          type="button"
          variant="ghost"
          disabled={!mexido || guardar.isPending}
          onClick={() => {
            setRascunho(null);
          }}
        >
          <RotateCcw aria-hidden="true" />
          Desfazer
        </Button>
      </span>
    </div>
  );
}

/** Uma linha a editar: o registo, com o que esta empresa decidiu por cima. */
interface LinhaDeMenu {
  readonly rota: RotaDeMenu;
  readonly grupo: string;
  readonly ordem: number;
  readonly visivel: boolean;
  /** `null` é "usa o rótulo do registo". Nunca `""` — ver o schema. */
  readonly rotulo: string | null;
}

const COLUNAS: readonly ColunaDeTabela[] = [
  { chave: "rota", rotulo: "Rota", classe: "w-[14rem]" },
  { chave: "rotulo", rotulo: "Nome no menu" },
  { chave: "grupo", rotulo: "Grupo", classe: "w-[12rem]" },
  { chave: "quem", rotulo: "Quem vê", classe: "w-[10rem]" },
  { chave: "estado", rotulo: "No menu", classe: "w-[7rem]" },
  { chave: "mover", rotulo: "Ordem", classe: "w-[6rem] text-right" },
];

/**
 * Cruza o registo com a configuração da sessão, pela ordem em que o menu as
 * mostra.
 *
 * A ordem de saída é a **configurada** e não a do registo: é esta lista que se
 * reordena com as setas, e mostrá-la na ordem do registo fazia as setas mexer
 * linhas que já estavam onde o utilizador as tinha posto. Com `ordem` igual
 * desempata o registo, que é a ordem que o servidor também usa.
 */
function linhasDe(
  rotas: readonly RotaDeMenu[],
  configurado: readonly { route_id: string; grupo: string; ordem: number; visivel: boolean; rotulo: string | null }[],
): readonly LinhaDeMenu[] {
  const porId = new Map(configurado.map((item) => [item.route_id, item]));

  return rotas
    .map((rota, indiceNoRegisto) => {
      const item = porId.get(rota.route_id);
      return {
        linha: {
          rota,
          grupo: item?.grupo ?? rota.grupo_default,
          ordem: item?.ordem ?? (indiceNoRegisto + 1) * 10,
          visivel: item?.visivel ?? true,
          rotulo: item?.rotulo ?? null,
        },
        indiceNoRegisto,
      };
    })
    .sort((a, b) => a.linha.ordem - b.linha.ordem || a.indiceNoRegisto - b.indiceNoRegisto)
    .map(({ linha }) => linha);
}

/**
 * Renumera de dez em dez depois de uma troca.
 *
 * Não é cosmética: `ordem` é o que o servidor guarda, e duas linhas trocadas com
 * as ordens originais (10 e 20 → 20 e 10) funcionam até alguém inserir uma rota
 * nova a meio. De dez em dez, inserir não obriga a renumerar — é a mesma razão
 * pela qual o registo do backend usa 10, 15, 20.
 */
function renumeradas(linhas: readonly LinhaDeMenu[]): readonly LinhaDeMenu[] {
  return linhas.map((linha, indice) => ({ ...linha, ordem: (indice + 1) * 10 }));
}

function trocadas(linhas: readonly LinhaDeMenu[], de: number, para: number): readonly LinhaDeMenu[] {
  if (para < 0 || para >= linhas.length) return linhas;
  const copia = [...linhas];
  const [movida] = copia.splice(de, 1);
  if (movida === undefined) return linhas;
  copia.splice(para, 0, movida);
  return renumeradas(copia);
}

function QuemVe({ papeis }: { readonly papeis: readonly Papel[] }) {
  // Três de três é "todos" e não uma lista de três palavras: o que a coluna
  // responde é "isto é restrito?", e enumerar os três papéis dá a mesma resposta
  // com três vezes o texto.
  if (papeis.length >= 3) return <span className="text-muted-foreground">todos</span>;

  return (
    <span className="font-semibold">
      só o {papeis.map((papel) => nomeDoPapel(papel)).join(", ")}
    </span>
  );
}

function LinhaEditavel({
  linha,
  indice,
  total,
  aGuardar,
  aMudar,
  aMover,
}: {
  readonly linha: LinhaDeMenu;
  readonly indice: number;
  readonly total: number;
  readonly aGuardar: boolean;
  readonly aMudar: (mudanca: Partial<LinhaDeMenu>) => void;
  readonly aMover: (passo: -1 | 1) => void;
}) {
  const restrita = linha.rota.papeis_permitidos.length < 3;

  return (
    <tr className={CLASSE_LINHA}>
      {/* O trilho acende nas rotas **restritas**, e é a leitura de dois metros
          desta tabela: numa lista de oito linhas, as que não são de todos
          vêem-se sem se ler. Uma linha normal não tem trilho nenhum — é a regra
          de cor do `tabela.tsx` e é por isso que o trilho continua a significar
          uma coisa só. */}
      <TrilhoDaLinha tinta={restrita ? "bg-primary" : ""} />

      {/* O id em mono, e **não** o ícone da rota. O ícone vive no
          `shell/registo-de-rotas.ts` e a fronteira do `eslint.config.js` recusa a
          uma feature importar do shell — medido, exit 1 à primeira tentativa. É a
          regra certa (uma feature é produto, não conhece o invólucro) e a
          alternativa seria descer o registo para `src/components/`, que é uma
          mudança de arquitectura sem ADR para a sustentar.

          O que fica é melhor do que parece: o id é o que **não** muda, é por ele
          que se fala desta rota num bug, e o nome editável está na coluna
          seguinte — mostrar o ícone ao lado dava duas identidades à mesma linha. */}
      <td className={CLASSE_CELULA}>
        <span className="font-mono text-xs">{linha.rota.route_id}</span>
      </td>

      <td className={CLASSE_CELULA}>
        <Input
          aria-label={`Nome de ${linha.rota.rotulo_default} no menu`}
          value={linha.rotulo ?? ""}
          placeholder={linha.rota.rotulo_default}
          maxLength={50}
          disabled={aGuardar}
          onChange={(evento) => {
            aMudar({ rotulo: evento.target.value });
          }}
        />
      </td>

      <td className={CLASSE_CELULA}>
        <Input
          aria-label={`Grupo de ${linha.rota.rotulo_default}`}
          value={linha.grupo}
          maxLength={50}
          disabled={aGuardar}
          onChange={(evento) => {
            aMudar({ grupo: evento.target.value });
          }}
        />
      </td>

      <td className={CLASSE_CELULA}>
        <QuemVe papeis={linha.rota.papeis_permitidos} />
      </td>

      <td className={CLASSE_CELULA}>
        {/* Um botão que **diz o estado e a acção**, e não um switch: "Visível" /
            "Escondida" com o ícone a dobrar a palavra. O estado nunca é só a
            cor nem só o ícone (DESIGN.md §2). */}
        <Button
          type="button"
          variant="ghost"
          size="sm"
          aria-pressed={linha.visivel}
          disabled={aGuardar}
          onClick={() => {
            aMudar({ visivel: !linha.visivel });
          }}
        >
          {linha.visivel ? (
            <Eye aria-hidden="true" />
          ) : (
            <EyeOff aria-hidden="true" className="text-muted-foreground" />
          )}
          <span className={linha.visivel ? "" : "text-muted-foreground"}>
            {linha.visivel ? "Visível" : "Escondida"}
          </span>
        </Button>
      </td>

      <td className={`${CLASSE_CELULA} text-right`}>
        <span className="inline-flex gap-0.5">
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            title={`Subir ${linha.rota.rotulo_default}`}
            disabled={aGuardar || indice === 0}
            onClick={() => {
              aMover(-1);
            }}
          >
            <ArrowUp aria-hidden="true" />
            <span className="sr-only">Subir {linha.rota.rotulo_default}</span>
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            title={`Descer ${linha.rota.rotulo_default}`}
            disabled={aGuardar || indice === total - 1}
            onClick={() => {
              aMover(1);
            }}
          >
            <ArrowDown aria-hidden="true" />
            <span className="sr-only">Descer {linha.rota.rotulo_default}</span>
          </Button>
        </span>
      </td>
    </tr>
  );
}

/**
 * As duas secções do dono, num componente próprio **para poderem ser
 * remontadas por chave**.
 *
 * Os dois rascunhos deste ecrã — o da casa e o do menu — são estado local sobre
 * dados de um estabelecimento. Trocar de estabelecimento no pé da sidebar sem os
 * limpar deixava o rascunho do anterior por cima da configuração do novo, e o
 * primeiro campo é o **nome da casa**: seria visível e errado ao mesmo tempo.
 *
 * A limpeza é uma `key` no sítio onde este componente é usado e não um
 * `useEffect(() => setRascunho(null), [id])`. As duas formas funcionam e só uma
 * é a recomendada: o `react-hooks/set-state-in-effect` do `eslint.config.js`
 * recusa a segunda — "calling setState synchronously within an effect can
 * trigger cascading renders" —, e esta casa não suprime lint. A forma que o
 * linter obriga a usar é também a que não tem de enumerar o estado a limpar: a
 * `key` limpa **todo** o estado deste componente, incluindo o que alguém
 * acrescentar amanhã e se esquecesse de pôr no efeito.
 */
function ConfiguracaoDoOwner() {
  const sessao = useSessao();
  const rotas = useRotasDeMenu(true);
  const guardar = useGuardarMenu();

  /**
   * O rascunho. `null` até haver dados, e é o que distingue "ainda não carregou"
   * de "carregou e está igual ao servidor" — com um array vazio por omissão, o
   * botão de guardar ficaria activo sobre uma lista que ninguém viu.
   *
   * O estado é do ecrã e não do URL: um menu meio reordenado não é uma vista
   * partilhável, e pô-lo em search params dava um link que recria um rascunho
   * que o servidor nunca aceitou.
   */
  const [rascunho, setRascunho] = useState<readonly LinhaDeMenu[] | null>(null);

  const doServidor = useMemo(
    () => linhasDe(rotas.data ?? [], sessao.data?.menu ?? []),
    [rotas.data, sessao.data?.menu],
  );
  const linhas = rascunho ?? doServidor;
  const mexido = rascunho !== null;

  function mudarLinha(indice: number, mudanca: Partial<LinhaDeMenu>) {
    setRascunho(
      linhas.map((linha, i) => (i === indice ? { ...linha, ...mudanca } : linha)),
    );
  }

  return (
    <>
      <section aria-labelledby="titulo-da-casa" className="flex flex-col gap-3">
        <div className="flex flex-col gap-1">
          <h2
            id="titulo-da-casa"
            className="text-xs font-bold tracking-microrotulo text-muted-foreground uppercase"
          >
            Esta casa
          </h2>
          <p className="max-w-prose text-sm text-muted-foreground">
            O nome por que ela aparece, e as duas coisas que decidem contas: o regime de IVA e a
            hora a que o dia de negócio começa.
          </p>
        </div>
        <BlocoDoEstabelecimento />
      </section>

      <section aria-labelledby="titulo-do-menu" className="flex flex-col gap-3">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div className="flex flex-col gap-1">
            <h2
              id="titulo-do-menu"
              className="text-xs font-bold tracking-microrotulo text-muted-foreground uppercase"
            >
              Menu desta casa
            </h2>
            <p className="max-w-prose text-sm text-muted-foreground">
              O nome, o grupo e a ordem de cada ecrã na barra lateral. Esconder um ecrã tira-o do
              menu e <strong>não</strong> retira o acesso — quem souber o endereço continua a
              entrar. Quem decide o acesso é o papel, na coluna «Quem vê».
            </p>
          </div>

          <span className="flex shrink-0 gap-2">
            <Button
              type="button"
              variant="ghost"
              disabled={!mexido || guardar.isPending}
              onClick={() => {
                setRascunho(null);
              }}
            >
              <RotateCcw aria-hidden="true" />
              Desfazer
            </Button>
            <Button
              type="button"
              disabled={!mexido || guardar.isPending}
              aria-busy={guardar.isPending}
              onClick={() => {
                const corpo: ItemDeMenuParaGuardar[] = linhas.map((linha) => ({
                  route_id: linha.rota.route_id,
                  grupo: linha.grupo,
                  ordem: linha.ordem,
                  visivel: linha.visivel,
                  rotulo: linha.rotulo,
                }));
                guardar.mutate(corpo, {
                  // O rascunho só desaparece quando o servidor confirma: a
                  // resposta é a configuração como ficou, e deixar de o mostrar
                  // antes disso punha no ecrã a lista antiga durante o pedido.
                  onSuccess: () => {
                    setRascunho(null);
                  },
                });
              }}
            >
              <Save aria-hidden="true" />
              {guardar.isPending ? "A guardar…" : "Guardar menu"}
            </Button>
          </span>
        </div>

        {guardar.isError ? (
          <Alert variant="destructive">
            <CircleAlert aria-hidden="true" />
            <AlertTitle>O menu não ficou guardado</AlertTitle>
            <AlertDescription>
              {mensagemDeErro(guardar.error)} O que está no ecrã é o que escreveu, e continua por
              guardar.
            </AlertDescription>
          </Alert>
        ) : null}

        {rotas.isPending ? (
          <EsqueletoDeTabela
            colunas={COLUNAS}
            larguraMinima="min-w-[60rem]"
            rotulo="A carregar as rotas do menu…"
            comTrilho
            linhas={7}
          />
        ) : rotas.isError ? (
          <Alert variant="destructive">
            <CircleAlert aria-hidden="true" />
            <AlertTitle>Não foi possível ler as rotas</AlertTitle>
            <AlertDescription>{mensagemDeErro(rotas.error)}</AlertDescription>
          </Alert>
        ) : (
          <MolduraDeTabela
            colunas={COLUNAS}
            larguraMinima="min-w-[60rem]"
            rotulo="Configuração do menu desta casa"
            comTrilho
          >
            <tbody>
              {linhas.map((linha, indice) => (
                <LinhaEditavel
                  key={linha.rota.route_id}
                  linha={linha}
                  indice={indice}
                  total={linhas.length}
                  aGuardar={guardar.isPending}
                  aMudar={(mudanca) => {
                    mudarLinha(indice, mudanca);
                  }}
                  aMover={(passo) => {
                    setRascunho(trocadas(linhas, indice, indice + passo));
                  }}
                />
              ))}
            </tbody>
          </MolduraDeTabela>
        )}
      </section>
    </>
  );
}


export function EcraDeConfiguracao() {
  const sessao = useSessao();
  const ePatrao = sessao.data?.tenant_ativo?.papel === "owner";
  const tenant = sessao.data?.tenant_ativo?.id;

  return (
    <div className="flex flex-col gap-6 p-4">
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold text-balance">Configuração</h1>
        <p className="max-w-prose text-sm text-muted-foreground">
          São desta empresa e valem para toda a equipa. As suas definições pessoais — a paleta — são
          no ecrã de preferências, no pé da barra lateral.
        </p>
      </header>

      {ePatrao ? (
        // A `key` é o que limpa os dois rascunhos ao trocar de estabelecimento.
        // A razão inteira está no docstring do `ConfiguracaoDoOwner`.
        <ConfiguracaoDoOwner key={tenant} />
      ) : (
        // O papel vem na sessão, logo o ecrã sabe isto **antes** de pedir, e não
        // dispara nenhum pedido que já se saiba recusado. O 403 do servidor
        // continua a ser a rede do deep link e da pertença revogada a meio — não
        // é isto que autoriza (ADR 0017, decisão 3).
        <Alert>
          <CircleAlert aria-hidden="true" />
          <AlertTitle>Só o dono do estabelecimento altera estas definições</AlertTitle>
          <AlertDescription>
            Fale com quem administra esta casa. As suas definições pessoais continuam a ser suas, no
            ecrã de preferências.
          </AlertDescription>
        </Alert>
      )}
    </div>
  );
}
