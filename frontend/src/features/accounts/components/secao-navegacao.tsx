import { useMemo, useState } from "react";
import { ArrowDown, ArrowUp, CircleAlert, Eye, EyeOff, RotateCcw, Save } from "lucide-react";

import {
  CLASSE_CELULA,
  CLASSE_LINHA,
  EsqueletoDeTabela,
  MolduraDeTabela,
  TrilhoDaLinha,
  type ColunaDeTabela,
} from "@/components/tabela";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { mensagemDeErro } from "@/lib/api/errors";

import { useGuardarMenu, useRotasDeMenu, useSessao } from "../api";
import { nomeDoPapel, type ItemDeMenuParaGuardar, type Papel, type RotaDeMenu } from "../schemas";
import { textos } from "../textos";

/**
 * A secção **Navegação** das Definições: que ecrãs a equipa vê, com que nomes e
 * em que ordem.
 *
 * "Navegação" e **não "Menu"**, que numa app de restauração se lê como a ementa.
 *
 * ## Consome dois endpoints que existiam e nunca tiveram consumidor
 *
 * O `GET /menu/rotas` (o registo: o que existe para configurar) e o `PUT /menu`
 * (a configuração inteira) existem desde a ADR 0011, testados e no
 * `schema.yaml`, e até este ecrã nascer nada os chamava. O `MenuView` do backend
 * já tinha escrito o que o painel precisava de fazer — "invalidar
 * `queryKeys.sessao()` no `onSuccess` do `PUT`" — e é o que o `useGuardarMenu` faz.
 *
 * ## Os defaults entram por prop, e é a fronteira que o obriga
 *
 * O nome e o grupo por omissão de cada rota vivem no **registo do shell**
 * (`shell/registo-de-rotas.ts`), porque são copy do produto e é lá que se
 * traduzem (ADR 0019, decisão 5). Uma feature não importa do `shell` — a
 * fronteira do `eslint.config.js` recusa-o, e recusou-o à primeira tentativa
 * deste ecrã. Logo esta secção **declara** o que precisa (`DefaultDaRota`) e quem
 * a satisfaz é a rota, que é a única camada que pode importar os dois lados. É a
 * mesma inversão de dependência do `SessaoDoShell` e da `EntradaDaProjeccao`, e
 * o `pnpm typecheck` confronta os dois lados num ponto só.
 *
 * Até 2026-10-07 estes dois valores vinham no `GET /menu/rotas`
 * (`rotulo_default`, `grupo_default`) e saíram do contrato: eram uma segunda
 * fonte para a mesma palavra, servida numa língua só.
 *
 * ## O que a tabela mostra, e o trilho
 *
 * O trilho de 4px acende nas rotas **restritas**, que é a leitura de dois metros
 * desta tabela: numa lista de seis linhas, as que não são de todos vêem-se sem se
 * ler. Uma linha normal não tem trilho nenhum — é a regra de cor do `tabela.tsx`,
 * e é o que faz o trilho continuar a significar uma coisa só.
 */

/**
 * O que esta secção precisa do registo de rotas do shell, **declarado aqui**.
 *
 * Três campos e nada mais: o id para casar com a projecção, e o nome e o grupo
 * por omissão para mostrar "o que esta rota se chama se ninguém lhe mexer" — que
 * é a informação que falta a quem está a decidir se lhe mexe.
 *
 * **Não tem `caminho` nem `icone`**, e isso é a fronteira a trabalhar e não uma
 * omissão: uma feature não conhece o encaminhamento, e um ícone aqui dava duas
 * identidades à mesma linha (o id em mono já é o que não muda).
 */
export interface DefaultDaRota {
  readonly route_id: string;
  readonly rotulo: string;
  readonly grupo: string;
}
/**
 * Uma linha a editar: a rota, o que esta empresa decidiu por cima, e os dois
 * valores por omissão que vêm do registo do shell.
 *
 * `rotulo` e `grupo` são `null` quando a empresa não sobrepôs nada — nunca `""`,
 * que é a forma como a coluna guarda a mesma ausência (ver o schema). Os dois
 * `PorOmissao` estão aqui e não resolvidos nos primeiros porque o `<input>` tem
 * de mostrar um **placeholder** com o default e um **valor** vazio: resolvê-los
 * fazia a primeira gravação devolver o default como sobreposição explícita, e no
 * dia em que ele mudasse a empresa ficava presa ao antigo sem nunca ter
 * escolhido nada.
 */
interface LinhaDeMenu {
  readonly rota: RotaDeMenu;
  readonly grupo: string | null;
  readonly ordem: number;
  readonly visivel: boolean;
  readonly rotulo: string | null;
  readonly rotuloPorOmissao: string;
  readonly grupoPorOmissao: string;
}

const COLUNAS: readonly ColunaDeTabela[] = [
  { chave: "rota", rotulo: textos.navegacao.colunas.rota, classe: "w-[14rem]" },
  { chave: "rotulo", rotulo: textos.navegacao.colunas.rotulo },
  { chave: "grupo", rotulo: textos.navegacao.colunas.grupo, classe: "w-[12rem]" },
  { chave: "quem", rotulo: textos.navegacao.colunas.quem, classe: "w-[10rem]" },
  { chave: "estado", rotulo: textos.navegacao.colunas.estado, classe: "w-[7rem]" },
  { chave: "mover", rotulo: textos.navegacao.colunas.mover, classe: "w-[6rem] text-right" },
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
interface ItemConfigurado {
  readonly route_id: string;
  readonly grupo: string | null;
  readonly ordem: number;
  readonly visivel: boolean;
  readonly rotulo: string | null;
}

function linhasDe(
  rotas: readonly RotaDeMenu[],
  configurado: readonly ItemConfigurado[],
  porOmissao: ReadonlyMap<string, DefaultDaRota>,
): readonly LinhaDeMenu[] {
  const porId = new Map(configurado.map((item) => [item.route_id, item]));

  return rotas
    .map((rota, indiceNoRegisto) => {
      const item = porId.get(rota.route_id);
      const defaults = porOmissao.get(rota.route_id);
      return {
        linha: {
          rota,
          grupo: item?.grupo ?? null,
          ordem: item?.ordem ?? (indiceNoRegisto + 1) * 10,
          visivel: item?.visivel ?? true,
          rotulo: item?.rotulo ?? null,
          // O `?? rota.route_id` é a queda de uma rota que o **bundle** não
          // conhece: o servidor é mais novo e serve um id a mais. É o caso do
          // rolling deploy, e o id em mono é melhor do que uma linha vazia.
          rotuloPorOmissao: defaults?.rotulo ?? rota.route_id,
          grupoPorOmissao: defaults?.grupo ?? "",
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
  if (papeis.length >= 3)
    return <span className="text-muted-foreground">{textos.navegacao.todos}</span>;

  return (
    <span className="font-semibold">
      {textos.navegacao.soO(papeis.map((papel) => nomeDoPapel(papel)).join(", "))}
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
          aria-label={textos.navegacao.nomeNoMenuDe(linha.rotuloPorOmissao)}
          value={linha.rotulo ?? ""}
          placeholder={linha.rotuloPorOmissao}
          maxLength={50}
          disabled={aGuardar}
          onChange={(evento) => {
            aMudar({ rotulo: evento.target.value });
          }}
        />
      </td>

      <td className={CLASSE_CELULA}>
        <Input
          aria-label={textos.navegacao.grupoDe(linha.rotuloPorOmissao)}
          value={linha.grupo ?? ""}
          placeholder={linha.grupoPorOmissao}
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
            {linha.visivel ? textos.navegacao.visivel : textos.navegacao.escondida}
          </span>
        </Button>
      </td>

      <td className={`${CLASSE_CELULA} text-right`}>
        <span className="inline-flex gap-0.5">
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            title={textos.navegacao.subir(linha.rotuloPorOmissao)}
            disabled={aGuardar || indice === 0}
            onClick={() => {
              aMover(-1);
            }}
          >
            <ArrowUp aria-hidden="true" />
            <span className="sr-only">{textos.navegacao.subir(linha.rotuloPorOmissao)}</span>
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            title={textos.navegacao.descer(linha.rotuloPorOmissao)}
            disabled={aGuardar || indice === total - 1}
            onClick={() => {
              aMover(1);
            }}
          >
            <ArrowDown aria-hidden="true" />
            <span className="sr-only">{textos.navegacao.descer(linha.rotuloPorOmissao)}</span>
          </Button>
        </span>
      </td>
    </tr>
  );
}


/**
 * A secção. O rascunho é estado do ecrã e **não** do URL: um menu meio
 * reordenado não é uma vista partilhável, e pô-lo em search params dava um link
 * que recria um estado que o servidor nunca aceitou.
 *
 * A limpeza do rascunho ao trocar de estabelecimento é uma `key` no sítio onde
 * esta secção é usada, e não um `useEffect` — o `react-hooks/set-state-in-effect`
 * recusa a segunda forma, e a `key` tem a propriedade melhor: limpa **todo** o
 * estado, incluindo o que alguém acrescentar amanhã.
 */
export function SecaoNavegacao({ defaults }: { readonly defaults: readonly DefaultDaRota[] }) {
  const sessao = useSessao();
  const rotas = useRotasDeMenu(true);
  const guardar = useGuardarMenu();
  const [rascunho, setRascunho] = useState<readonly LinhaDeMenu[] | null>(null);

  const porOmissao = useMemo(
    () => new Map(defaults.map((d) => [d.route_id, d])),
    [defaults],
  );

  const doServidor = useMemo(
    () => linhasDe(rotas.data ?? [], sessao.data?.menu ?? [], porOmissao),
    [rotas.data, sessao.data?.menu, porOmissao],
  );
  const linhas = rascunho ?? doServidor;
  const mexido = rascunho !== null;

  function mudarLinha(indice: number, mudanca: Partial<LinhaDeMenu>) {
    setRascunho(linhas.map((linha, i) => (i === indice ? { ...linha, ...mudanca } : linha)));
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <p className="max-w-prose text-sm text-muted-foreground">
          {textos.navegacao.explicacaoInicio} <strong>{textos.navegacao.enfaseNao}</strong>{" "}
          {textos.navegacao.explicacaoFim}
        </p>

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
            {textos.accoes.desfazer}
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
                onSuccess: () => {
                  setRascunho(null);
                },
              });
            }}
          >
            <Save aria-hidden="true" />
            {guardar.isPending ? textos.accoes.aGuardar : textos.accoes.guardar}
          </Button>
        </span>
      </div>

      {guardar.isError ? (
        <Alert variant="destructive">
          <CircleAlert aria-hidden="true" />
          <AlertTitle>{textos.navegacao.erroAoGuardar}</AlertTitle>
          <AlertDescription>
            {mensagemDeErro(guardar.error)} {textos.accoes.naoGuardado}
          </AlertDescription>
        </Alert>
      ) : null}

      {rotas.isPending ? (
        <EsqueletoDeTabela
          colunas={COLUNAS}
          larguraMinima="min-w-[60rem]"
          rotulo={textos.navegacao.aCarregar}
          comTrilho
          linhas={6}
        />
      ) : rotas.isError ? (
        <Alert variant="destructive">
          <CircleAlert aria-hidden="true" />
          <AlertTitle>{textos.navegacao.erroDeLeitura}</AlertTitle>
          <AlertDescription>{mensagemDeErro(rotas.error)}</AlertDescription>
        </Alert>
      ) : (
        <MolduraDeTabela
          colunas={COLUNAS}
          larguraMinima="min-w-[60rem]"
          rotulo={textos.navegacao.tabela}
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
    </div>
  );
}
