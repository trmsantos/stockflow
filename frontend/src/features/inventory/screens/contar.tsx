import { Link, useSearch } from "@tanstack/react-router";
import { ClipboardCheck, ClipboardList, Lock, Search } from "lucide-react";
import { useMemo, useState } from "react";

import { EstadoVazio } from "@/components/estado-vazio";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { mensagemDeErro } from "@/lib/api/errors";
import { formatDate, formatTime } from "@/lib/format";

import {
  useContagemAberta,
  useIniciarContagem,
  useLinhasDeContagem,
  useNiveisDeStock,
  useRegistarContagemDeLinha,
  useUltimaContagemFechada,
} from "../api";
import { ErroDaLista, EsqueletoDaLista } from "../components/estados-da-lista";
import { LinhaDeContagem } from "../components/linha-de-contagem";
import {
  EsqueletoDoProgresso,
  ProgressoDaContagem,
} from "../components/progresso-da-contagem";
import type { Localizacao, NivelDeStock } from "../schemas";

/**
 * O ecrã Contar — "o que está na prateleira é o que o sistema diz?".
 *
 * Progresso e zona actual no topo, uma linha por artigo com o campo numérico, e
 * **a ordem é a do percurso físico**: Balcão → Frigorífico → Arca → Armazém,
 * decidida no servidor. Nunca alfabética, e isto é regra e não preferência
 * (guião §1) — quem conta anda pela cozinha.
 *
 * **O campo numérico deste ecrã não é a "quantidade editável" proibida.** A
 * proibição nº 1 do guião §4 é um lápis ao lado do número no ecrã de Stock, e
 * continua de pé: lá o número é leitura. Aqui escreve-se o que está na
 * prateleira, e ao fechar cada diferença entra no ledger como um `adjustment`
 * com justificação. O ledger continua append-only (ADR 0006) e nenhum nível é
 * reescrito em sítio nenhum.
 *
 * **A contagem cega está nas duas variantes ao mesmo tempo**, porque é assim
 * que a pergunta se faz: uma zona mostra o esperado, outra esconde-o, e é o
 * servidor que decide qual (guião §3). A hipótese marcada no §5 é "esperado
 * visível", por isso é essa a maioria; o shell não resolve a pergunta, mostra
 * as duas.
 *
 * Fechar com diferenças **é possível** — bloquear é a Q1 e o shell não responde
 * por ela. O que é obrigatório acima de um limiar é a justificação, e o limiar
 * aparece no ecrã do fecho.
 */

/** O `id` do campo de uma linha, estável entre renderizações e entre zonas. */
function campoDe(produto: string): string {
  return `contagem-${produto}`;
}

/**
 * As localizações onde se pode começar a contar, tiradas dos dados — o mesmo
 * que a barra de filtros do Stock faz, e com o mesmo preço nomeado: uma
 * localização sem movimento nenhum não aparece, porque não há (ainda) endpoint
 * que liste localizações. Ordem alfabética, que aqui é a certa: é uma lista de
 * escolhas, não a fila de problemas da manhã.
 */
function localizacoesDe(niveis: readonly NivelDeStock[] | undefined): readonly Localizacao[] {
  const porId = new Map<string, Localizacao>();
  for (const nivel of niveis ?? []) {
    for (const parcela of nivel.by_location) {
      porId.set(parcela.location.id, parcela.location);
    }
  }
  return [...porId.values()].sort((a, b) => a.name.localeCompare(b.name, "pt-PT"));
}

/** O estado vazio: não há contagem a decorrer, e a ação é começar uma. */
function SemContagem() {
  const consolidado = useNiveisDeStock();
  const localizacoes = useMemo(() => localizacoesDe(consolidado.data?.results), [consolidado.data]);
  const [escolhida, setEscolhida] = useState("");
  const iniciar = useIniciarContagem();
  const ultima = useUltimaContagemFechada();

  const local = escolhida === "" ? localizacoes[0]?.id : escolhida;

  return (
    <>
      <EstadoVazio
        icone={ClipboardList}
        titulo="Nenhuma contagem a decorrer"
        descricao="Uma contagem percorre uma loja por zonas, na ordem física: Balcão, Frigorífico, Arca, Armazém. Escolha onde quer contar."
      >
        <div className="flex w-full max-w-xs flex-col gap-1.5">
          <Label htmlFor="contagem-localizacao">Onde quer contar</Label>
          <Select
            value={local ?? ""}
            onValueChange={setEscolhida}
            disabled={localizacoes.length === 0}
          >
            <SelectTrigger id="contagem-localizacao" className="w-full">
              <SelectValue placeholder="Escolha a loja" />
            </SelectTrigger>
            <SelectContent>
              {localizacoes.map((localizacao) => (
                <SelectItem key={localizacao.id} value={localizacao.id}>
                  {localizacao.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <Button
          disabled={local === undefined || iniciar.isPending}
          onClick={() => {
            if (local === undefined) return;
            iniciar.mutate({ location: local });
          }}
        >
          <ClipboardCheck aria-hidden="true" />
          {iniciar.isPending ? "A começar…" : "Começar contagem"}
        </Button>
      </EstadoVazio>

      {iniciar.isError ? (
        <p role="alert" className="px-4 text-sm text-danger">
          {mensagemDeErro(iniciar.error)}
        </p>
      ) : null}

      {/* A última contagem fechada continua a valer como registo: é o que
          responde a "então e a de hoje de manhã?" sem obrigar a abrir outra. */}
      {ultima.data === null || ultima.data === undefined ? null : (
        <div className="flex flex-col items-start gap-2 border-t border-border px-4 py-4">
          <h2 className="text-sm font-semibold">Última contagem fechada</h2>
          <p className="text-sm text-muted-foreground">
            {ultima.data.location.name} ·{" "}
            {ultima.data.closed_at === null
              ? ""
              : `${formatDate(ultima.data.closed_at)} às ${formatTime(ultima.data.closed_at)}`}{" "}
            · <span data-numeric>{ultima.data.counted_lines}</span> de{" "}
            <span data-numeric>{ultima.data.total_lines}</span> linhas
            {ultima.data.closing_reason === null ? "" : ` · «${ultima.data.closing_reason}»`}
          </p>
          <Button asChild variant="outline">
            <Link to="/contar/fechar" search={{ contagem: ultima.data.id }}>
              Ver as diferenças
            </Link>
          </Button>
        </div>
      )}
    </>
  );
}

export function EcraDeContar() {
  const busca = useSearch({ from: "/app/contar" });
  const contagem = useContagemAberta();
  const aberta = contagem.data ?? null;

  const linhas = useLinhasDeContagem(aberta?.id, busca.zona);
  const registar = useRegistarContagemDeLinha();

  const resultados = linhas.data?.results;

  // O campo por contar que vem **depois** deste, na ordem em que estão no ecrã:
  // é para onde o foco salta depois de guardar, e é o que mantém o teclado
  // aberto de cima a baixo da zona.
  function campoSeguinte(indice: number): string | undefined {
    const seguinte = resultados?.slice(indice + 1).find((linha) => linha.counted === null);
    return seguinte === undefined ? undefined : campoDe(seguinte.product);
  }

  function focar(id: string | undefined) {
    if (id === undefined) return;
    const campo = document.getElementById(id);
    // Por `id` e não por `ref`: os primitivos do shadcn são funções que
    // espalham props e nesta versão do React um `ref` passado a uma função não
    // chega ao DOM — ficaria um foco que ninguém mede e que não acontece.
    if (campo instanceof HTMLInputElement) campo.focus();
  }

  return (
    <section className="flex w-full max-w-2xl flex-col">
      {/* O nome do ecrã já está no header do shell; repeti-lo em grande custava
          uma das sete linhas do orçamento de 360×640. */}
      <h1 className="sr-only">Contar — o que está na prateleira é o que o sistema diz?</h1>

      {contagem.isPending ? (
        <>
          <EsqueletoDoProgresso />
          <EsqueletoDaLista rotulo="A carregar a contagem…" linhas={5} />
        </>
      ) : null}

      {contagem.isError ? (
        <ErroDaLista
          titulo="Não foi possível carregar a contagem"
          mensagem={mensagemDeErro(contagem.error)}
          aoTentarOutraVez={() => {
            void contagem.refetch();
          }}
        />
      ) : null}

      {contagem.data === undefined ? null : aberta === null ? (
        <SemContagem />
      ) : (
        <>
          <ProgressoDaContagem contagem={aberta} zonaAtiva={busca.zona} />

          {linhas.isPending ? <EsqueletoDaLista rotulo="A carregar as linhas…" linhas={5} /> : null}

          {linhas.isError ? (
            <ErroDaLista
              titulo="Não foi possível carregar as linhas"
              mensagem={mensagemDeErro(linhas.error)}
              aoTentarOutraVez={() => {
                void linhas.refetch();
              }}
            />
          ) : null}

          {resultados === undefined ? null : resultados.length === 0 ? (
            <EstadoVazio
              icone={Search}
              titulo="Esta zona não tem nada para contar"
              descricao="Nenhum artigo desta contagem está nesta zona. As outras zonas continuam no topo."
            >
              <Button asChild variant="outline">
                <Link to="/contar" search={() => ({})}>
                  Ver todas as zonas
                </Link>
              </Button>
            </EstadoVazio>
          ) : (
            <>
              <ul className="flex flex-col">
                {resultados.map((linha, indice) => (
                  <LinhaDeContagem
                    key={linha.id}
                    linha={linha}
                    idDoCampo={campoDe(linha.product)}
                    idDoCampoSeguinte={campoSeguinte(indice)}
                    aRegistar={registar.isPending && registar.variables.product === linha.product}
                    aoRegistar={(quantidade) => {
                      const seguinte = campoSeguinte(indice);
                      registar.mutate(
                        { contagem: aberta.id, product: linha.product, quantity: quantidade },
                        {
                          onSuccess: () => {
                            focar(seguinte ?? campoDe(linha.product));
                          },
                        },
                      );
                    }}
                  />
                ))}
              </ul>

              {registar.isError ? (
                <p role="alert" className="px-4 py-2 text-sm text-danger">
                  {mensagemDeErro(registar.error)}
                </p>
              ) : null}

              {/* O fecho fica no fim da lista, onde se chega depois de contar, e
                  não colado ao ecrã numa barra fixa: ela tapava a última linha,
                  que é precisamente a que falta contar. A razão sobrevive à
                  saída da tab bar (ADR 0009) — o que tapava a linha era a barra
                  fixa, não o que estava por baixo dela. */}
              <div className="flex flex-col items-start gap-1.5 border-t border-border px-4 py-4">
                <Button asChild>
                  <Link to="/contar/fechar" search={{ contagem: aberta.id }}>
                    Fechar contagem
                  </Link>
                </Button>
                <p className="flex items-center gap-1 text-xs text-muted-foreground">
                  <Lock aria-hidden="true" className="size-3 shrink-0" />
                  só o {aberta.closing_role} fecha a contagem · as diferenças aparecem antes
                </p>
              </div>
            </>
          )}
        </>
      )}
    </section>
  );
}
