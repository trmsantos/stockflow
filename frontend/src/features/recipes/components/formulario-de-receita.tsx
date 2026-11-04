import { Plus, Search, X } from "lucide-react";
import { useEffect, useId, useMemo, useState, type FormEvent } from "react";

import { useArtigos } from "@/features/catalog/api";
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
import { PAGE_SIZE } from "@/lib/api/pagination";
import { formatDecimalField } from "@/lib/format";

import type { LinhaParaGravar, ReceitaDetalhe } from "../schemas";
import { textos } from "../textos";

/**
 * O formulário da ficha técnica — **um** botão de gravar, para criar e para
 * editar.
 *
 * ## Porque é um documento e não uma colecção
 *
 * As linhas viajam dentro do corpo, por substituição total (ADR 0035, decisão
 * 4). A contagem e a receção têm sub-recurso de linhas porque são **percursos**
 * — uma folha que se anda com o telemóvel na mão, um papel que se confere linha
 * a linha contra uma palete. Uma ficha técnica escreve-se de uma vez: oito
 * `POST` para oito ingredientes é uma receita meio gravada, e uma receita meio
 * gravada é um custo errado que ninguém vê. Daí este formulário ter estado local
 * para a ficha inteira e uma só submissão.
 *
 * ## A fornada primeiro, o rendimento fora do caminho
 *
 * A ADR 0035 (decisão 8) fixa a ordem: pede-se a **fornada** — pré-preenchida a
 * 1 na unidade base, que é o prato sem fornada a passar a caso particular — e as
 * quantidades dos ingredientes são as **desta fornada**, não as de uma unidade.
 * Dividir pela fornada ao escrever arrasa os ingredientes pequenos, que são os
 * caros: 2 g de corante ÷ 400 são `0,005`, e a essência de baunilha numa fornada
 * grande é `0,000` — um ingrediente a zero desaparece do custo e do consumo.
 *
 * O `yield_factor` fica no fim e com a explicação ao lado: nasce a 1 porque a
 * perda já está na fornada, e pô-la aqui outra vez conta-a duas vezes.
 *
 * ## Nada se converte aqui
 *
 * A `unit` viaja explícita em cada linha e na fornada, e quem converte é o
 * **servidor** (ADR 0034, decisão 11; `inventory-domain` §2). As unidades
 * oferecidas são a base e a de apresentação **daquele** artigo, e nada mais:
 * qualquer outra é 400, porque não existe motor genérico de conversão (ADR
 * 0011). A de apresentação vem pré-escolhida — é a unidade em que a pessoa fala
 * ("500 g de farinha" num artigo base `g` e apresentação `kg`).
 *
 * ## A água e o sal, que é a primeira coisa que um pasteleiro tenta escrever
 *
 * A ADR 0035 (decisão 11) decide que não se listam, e decide também **onde** a
 * regra vive: no texto deste formulário, nunca numa lista negra de nomes no
 * servidor — "água das pedras" é um artigo de stock a sério num café, e um
 * filtro por nome recusaria o artigo certo pela palavra errada. A frase está no
 * catálogo e aparece por cima dos ingredientes.
 */

/** A mesma forma do `decimal` do contrato, sem sinal: uma quantidade é absoluta. */
const DECIMAL_POSITIVO = /^\d+$|^\d+\.\d+$/;

/**
 * Um artigo como este formulário precisa de o conhecer: o nome para mostrar e as
 * **duas** unidades que o servidor aceita para ele.
 *
 * Existe porque as duas fontes de artigos deste ecrã têm formas diferentes e
 * dizem a mesma coisa: o catálogo (`GET /products`) e a própria ficha que se
 * está a editar — cujas linhas trazem `short_name` e o par de unidades dentro da
 * `Quantidade`. Sem esta forma, editar uma ficha cujo ingrediente esteja fora da
 * primeira página do catálogo abria um seletor vazio por cima de uma linha que
 * existe.
 */
interface ArtigoDaFicha {
  readonly id: string;
  readonly nome: string;
  readonly base_unit: string;
  readonly display_unit: string;
}

/** Uma linha em edição. A `chave` é do React e nunca viaja no corpo. */
interface LinhaEmEdicao {
  readonly chave: string;
  readonly ingredient: string;
  readonly quantity: string;
  readonly unit: string;
}

/** O que este formulário entrega a quem o monta. A rota decide o verbo. */
export interface FichaGravavel {
  readonly product: string;
  readonly batch_size: string;
  readonly batch_unit: string;
  readonly yield_factor: string;
  readonly lines: readonly LinhaParaGravar[];
}

interface Erros {
  readonly acabado?: string;
  readonly fornada?: string;
  readonly rendimento?: string;
  readonly linhas?: string;
}

/** As unidades que o servidor aceita para um artigo, sem repetir quando coincidem. */
function unidadesDe(artigo: ArtigoDaFicha | undefined): readonly string[] {
  if (artigo === undefined) return [];
  return artigo.display_unit === artigo.base_unit
    ? [artigo.base_unit]
    : [artigo.display_unit, artigo.base_unit];
}

/** A vírgula decimal é como se escreve em português; o contrato quer ponto. */
function normalizar(valor: string): string {
  return valor.trim().replace(",", ".");
}

function valida(valor: string): boolean {
  const numero = normalizar(valor);
  return DECIMAL_POSITIVO.test(numero) && Number(numero) > 0;
}

let proximaChave = 0;
function novaChave(): string {
  proximaChave += 1;
  return `linha-${String(proximaChave)}`;
}

function linhasIniciais(ficha: ReceitaDetalhe | undefined): LinhaEmEdicao[] {
  if (ficha === undefined) {
    return [{ chave: novaChave(), ingredient: "", quantity: "", unit: "" }];
  }
  return ficha.lines.map((linha) => ({
    chave: novaChave(),
    ingredient: linha.ingredient,
    // A quantidade **por fornada**, na unidade de apresentação, que é a forma em
    // que ela foi escrita. `display` e não `base`: reabrir a ficha e ler "2400"
    // onde se escreveu "2,4" é o defeito que a decisão 8 existe para evitar.
    quantity: formatDecimalField(linha.quantity.display),
    unit: linha.quantity.display_unit,
  }));
}

function artigosDaFicha(ficha: ReceitaDetalhe | undefined): ArtigoDaFicha[] {
  if (ficha === undefined) return [];
  return [
    {
      id: ficha.product,
      nome: ficha.short_name,
      base_unit: ficha.base_unit,
      display_unit: ficha.display_unit,
    },
    ...ficha.lines.map((linha) => ({
      id: linha.ingredient,
      nome: linha.short_name,
      base_unit: linha.quantity.base_unit,
      display_unit: linha.quantity.display_unit,
    })),
  ];
}

/** O travão da procura, o mesmo da barra de filtros do Stock. */
const ATRASO_DA_PROCURA_MS = 300;

export function FormularioDeReceita({
  ficha,
  pendente,
  aoGravar,
  aoCancelar,
}: {
  /** A ficha a editar. Ausente = ficha nova, e aí o acabado escolhe-se. */
  readonly ficha?: ReceitaDetalhe;
  readonly pendente: boolean;
  readonly aoGravar: (valores: FichaGravavel) => void;
  readonly aoCancelar?: () => void;
}) {
  const prefixo = useId();
  const [procura, setProcura] = useState("");
  const [termo, setTermo] = useState("");
  const [acabado, setAcabado] = useState(ficha?.product ?? "");
  const [fornada, setFornada] = useState(
    ficha === undefined ? "1" : formatDecimalField(ficha.batch_size.display),
  );
  const [unidadeDaFornada, setUnidadeDaFornada] = useState(
    ficha?.batch_size.display_unit ?? "",
  );
  const [rendimento, setRendimento] = useState(
    ficha === undefined ? "1" : formatDecimalField(ficha.yield_factor),
  );
  const [linhas, setLinhas] = useState<readonly LinhaEmEdicao[]>(() => linhasIniciais(ficha));
  const [erros, setErros] = useState<Erros>({});
  // Os artigos que este formulário já viu. Acumula em vez de substituir: a
  // página do catálogo muda com a procura, e um artigo escolhido tem de
  // continuar a ter nome e unidades depois de a procura deixar de o devolver.
  const [conhecidos, setConhecidos] = useState<readonly ArtigoDaFicha[]>(() =>
    artigosDaFicha(ficha),
  );

  // A tecla aparece no instante em que é premida (o rascunho é local) e o
  // pedido só sai quando a pessoa pára de escrever: cada valor distinto é um
  // `WHERE` no servidor, e escrever "farinha" sem travão são sete pedidos em
  // voo.
  useEffect(() => {
    if (procura === termo) return undefined;
    const relogio = setTimeout(() => {
      setTermo(procura);
    }, ATRASO_DA_PROCURA_MS);
    return () => {
      clearTimeout(relogio);
    };
  }, [procura, termo]);

  const catalogo = useArtigos(termo);

  /**
   * As opções dos seletores: a página do catálogo **mais** o que já foi
   * escolhido, por id, sem duplicados e por ordem alfabética.
   *
   * O `Map` é o que garante o "sem duplicados" e o que dá a precedência à
   * resposta fresca do catálogo sobre a cópia guardada.
   */
  const opcoes = useMemo(() => {
    const porId = new Map<string, ArtigoDaFicha>();
    for (const artigo of conhecidos) porId.set(artigo.id, artigo);
    for (const artigo of catalogo.data?.results ?? []) {
      porId.set(artigo.id, {
        id: artigo.id,
        nome: artigo.short_name,
        base_unit: artigo.base_unit,
        display_unit: artigo.display_unit,
      });
    }
    return [...porId.values()].sort((a, b) => a.nome.localeCompare(b.nome));
  }, [conhecidos, catalogo.data]);

  const porId = useMemo(
    () => new Map(opcoes.map((artigo) => [artigo.id, artigo])),
    [opcoes],
  );

  const artigoAcabado = porId.get(acabado);
  const unidadesDoAcabado = unidadesDe(artigoAcabado);

  // O catálogo tem mais artigos do que os que cabem numa página? Dizê-lo é o que
  // impede alguém de concluir que o artigo não existe (é o defeito que o PR "o
  // artigo que a lista não alcança" fechou noutro ecrã). A saída é a procura,
  // que é um `WHERE` no servidor e alcança o catálogo inteiro.
  const truncado = (catalogo.data?.count ?? 0) > (catalogo.data?.results.length ?? 0);

  function escolherArtigo(id: string): ArtigoDaFicha | undefined {
    const artigo = porId.get(id);
    if (artigo !== undefined) {
      setConhecidos((anteriores) =>
        anteriores.some((conhecido) => conhecido.id === id)
          ? anteriores
          : [...anteriores, artigo],
      );
    }
    return artigo;
  }

  function mudarLinha(chave: string, mudanca: Partial<LinhaEmEdicao>) {
    setLinhas((anteriores) =>
      anteriores.map((linha) => (linha.chave === chave ? { ...linha, ...mudanca } : linha)),
    );
  }

  function aoSubmeter(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault();

    const preenchidas = linhas.filter((linha) => linha.ingredient !== "");
    const ids = preenchidas.map((linha) => linha.ingredient);
    const repetido = new Set(ids).size !== ids.length;
    // **Duas frases e não uma**, porque são dois enganos diferentes: uma linha
    // sem artigo escolhido e uma linha com a quantidade em branco ou a zero. Um
    // "escreva uma quantidade" por cima de um seletor vazio manda a pessoa
    // corrigir o campo errado.
    const semArtigo = linhas.some((linha) => linha.ingredient === "");
    const semQuantidade = linhas.some((linha) => !valida(linha.quantity));

    const problemas: Erros = {
      ...(acabado === "" ? { acabado: textos.formulario.erroAcabado } : {}),
      ...(valida(fornada) && unidadeDaFornada !== ""
        ? {}
        : { fornada: textos.formulario.erroFornada }),
      ...(valida(rendimento) ? {} : { rendimento: textos.formulario.erroRendimento }),
      ...(preenchidas.length === 0
        ? { linhas: textos.formulario.erroSemLinhas }
        : repetido
          ? { linhas: textos.formulario.erroRepetido }
          : semArtigo
            ? { linhas: textos.formulario.erroArtigoDaLinha }
            : semQuantidade
              ? { linhas: textos.formulario.erroQuantidade }
              : {}),
    };

    setErros(problemas);
    if (Object.keys(problemas).length > 0) {
      // Foco no primeiro campo errado, por `id` e não por `ref`: os primitivos
      // do shadcn espalham props e nesta versão do React um `ref` passado a uma
      // função não chega ao DOM — ficaria um foco que ninguém mede.
      const alvo = document.getElementById(
        problemas.acabado === undefined ? `${prefixo}-fornada` : `${prefixo}-acabado`,
      );
      if (alvo instanceof HTMLElement) alvo.focus();
      return;
    }

    aoGravar({
      product: acabado,
      batch_size: normalizar(fornada),
      batch_unit: unidadeDaFornada,
      yield_factor: normalizar(rendimento),
      lines: preenchidas.map((linha) => ({
        ingredient: linha.ingredient,
        quantity: normalizar(linha.quantity),
        unit: linha.unit,
      })),
    });
  }

  const grelha =
    "grid grid-cols-1 gap-2 sm:grid-cols-[minmax(0,1fr)_8rem_7rem_auto] sm:items-end";

  return (
    <form onSubmit={aoSubmeter} className="flex w-full max-w-6xl flex-col gap-ritmo px-celula-x">
      {/* O acabado. Em edição é texto e não um seletor: é a identidade da ficha
          e o `PATCH` nem sequer o aceita (decisão 4). Um campo desactivado
          convidava a tentar. */}
      <section className="flex flex-col gap-1.5">
        <Label htmlFor={`${prefixo}-acabado`}>{textos.formulario.acabado}</Label>
        {ficha === undefined ? (
          <>
            <Select
              value={acabado}
              onValueChange={(valor) => {
                const artigo = escolherArtigo(valor);
                setAcabado(valor);
                // A fornada nasce na unidade **base** do acabado (decisão 8): é
                // o "prato sem fornada" (batch_size = 1 unidade base) a ser o
                // caso particular, e não o contrário.
                setUnidadeDaFornada(artigo?.base_unit ?? "");
              }}
            >
              <SelectTrigger
                id={`${prefixo}-acabado`}
                className="w-full max-w-md"
                aria-invalid={erros.acabado === undefined ? undefined : true}
                aria-describedby={`${prefixo}-acabado-ajuda`}
              >
                <SelectValue placeholder={textos.formulario.escolherArtigo} />
              </SelectTrigger>
              <SelectContent>
                {opcoes.map((artigo) => (
                  <SelectItem key={artigo.id} value={artigo.id}>
                    {artigo.nome}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p id={`${prefixo}-acabado-ajuda`} className="text-xs text-muted-foreground">
              {textos.formulario.acabadoAjuda}
            </p>
            {erros.acabado === undefined ? null : (
              <p className="text-sm text-danger">{erros.acabado}</p>
            )}
          </>
        ) : (
          <>
            <p id={`${prefixo}-acabado`} className="text-base font-medium">
              {ficha.short_name}
            </p>
            <p className="text-xs text-muted-foreground">{textos.formulario.acabadoFixo}</p>
          </>
        )}
      </section>

      {/* A fornada: o número e a unidade lado a lado, porque são **uma**
          resposta. O par tem tecto de largura pela razão do formulário de
          desperdício — sem ele o campo estica até à largura do monitor e põe a
          unidade a um palmo do número que ela qualifica. */}
      <section className="flex flex-col gap-1.5">
        <Label htmlFor={`${prefixo}-fornada`}>{textos.formulario.fornada}</Label>
        <div className="flex max-w-sm items-end gap-2">
          <Input
            id={`${prefixo}-fornada`}
            name="fornada"
            type="text"
            inputMode="decimal"
            autoComplete="off"
            value={fornada}
            onChange={(evento) => {
              setFornada(evento.target.value);
            }}
            className="min-w-0 flex-1"
            aria-invalid={erros.fornada === undefined ? undefined : true}
            aria-describedby={`${prefixo}-fornada-ajuda`}
          />
          <Label htmlFor={`${prefixo}-fornada-unidade`} className="sr-only">
            {textos.formulario.unidade}
          </Label>
          <Select value={unidadeDaFornada} onValueChange={setUnidadeDaFornada}>
            <SelectTrigger id={`${prefixo}-fornada-unidade`} className="w-24 shrink-0">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {unidadesDoAcabado.map((unidade) => (
                <SelectItem key={unidade} value={unidade}>
                  {unidade}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <p id={`${prefixo}-fornada-ajuda`} className="max-w-2xl text-xs text-muted-foreground">
          {textos.formulario.fornadaAjuda}
        </p>
        {erros.fornada === undefined ? null : (
          <p className="text-sm text-danger">{erros.fornada}</p>
        )}
      </section>

      <section className="flex flex-col gap-3">
        <div className="flex flex-col gap-1.5">
          <h2 className="text-sm font-semibold">{textos.formulario.ingredientes}</h2>
          <p className="max-w-2xl text-xs text-muted-foreground">
            {textos.formulario.ingredientesAjuda}
          </p>
        </div>

        {/* A procura é um `WHERE` no servidor e alcança o catálogo inteiro — é a
            saída para o artigo que não cabe na primeira página. Filtra o que os
            seletores oferecem; o que já está escolhido fica lá, por construção
            (ver o `opcoes`). */}
        <div role="search" className="relative w-full max-w-xs">
          <Label htmlFor={`${prefixo}-procura`} className="sr-only">
            {textos.formulario.procurar}
          </Label>
          <Search
            aria-hidden="true"
            className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground"
          />
          <Input
            id={`${prefixo}-procura`}
            name="procurar-artigo"
            type="search"
            value={procura}
            onChange={(evento) => {
              setProcura(evento.target.value);
            }}
            placeholder={textos.formulario.procurarPista}
            autoComplete="off"
            spellCheck={false}
            enterKeyHint="search"
            className="pl-8"
          />
        </div>

        {/* O cabeçalho da grelha, com o mesmo tratamento do `<th>` da tabela.
            Só a partir de `sm`, onde a linha é uma linha; abaixo disso cada
            campo leva o seu rótulo visível. */}
        <div className={`${grelha} hidden sm:grid`}>
          <span className="text-xs font-bold tracking-microrotulo text-muted-foreground uppercase">
            {textos.colunas.ingrediente}
          </span>
          <span className="text-xs font-bold tracking-microrotulo text-muted-foreground uppercase">
            {textos.formulario.quantidade}
          </span>
          <span className="text-xs font-bold tracking-microrotulo text-muted-foreground uppercase">
            {textos.formulario.unidade}
          </span>
          <span className="sr-only">{textos.accoes.removerLinha}</span>
        </div>

        <ul className="flex flex-col gap-3 sm:gap-2">
          {linhas.map((linha) => {
            const artigo = porId.get(linha.ingredient);
            const unidades = unidadesDe(artigo);
            return (
              <li key={linha.chave} className={grelha}>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor={`${prefixo}-${linha.chave}-artigo`} className="sm:sr-only">
                    {textos.colunas.ingrediente}
                  </Label>
                  <Select
                    value={linha.ingredient}
                    onValueChange={(valor) => {
                      const escolhido = escolherArtigo(valor);
                      // A unidade acompanha o artigo: a de apresentação, que é a
                      // unidade em que a pessoa fala. Sem isto, trocar de artigo
                      // deixava um `kg` por cima de um artigo que se conta às
                      // unidades — e isso é 400 no servidor.
                      mudarLinha(linha.chave, {
                        ingredient: valor,
                        unit: escolhido?.display_unit ?? "",
                      });
                    }}
                  >
                    <SelectTrigger
                      id={`${prefixo}-${linha.chave}-artigo`}
                      className="w-full"
                    >
                      <SelectValue placeholder={textos.formulario.escolherArtigo} />
                    </SelectTrigger>
                    <SelectContent>
                      {opcoes.length === 0 ? (
                        <div className="px-2 py-1.5 text-sm text-muted-foreground">
                          {textos.formulario.semArtigos}
                        </div>
                      ) : (
                        opcoes.map((opcao) => (
                          <SelectItem key={opcao.id} value={opcao.id}>
                            {opcao.nome}
                          </SelectItem>
                        ))
                      )}
                    </SelectContent>
                  </Select>
                </div>

                <div className="flex flex-col gap-1.5">
                  <Label
                    htmlFor={`${prefixo}-${linha.chave}-quantidade`}
                    className="sm:sr-only"
                  >
                    {textos.formulario.quantidade}
                  </Label>
                  <Input
                    id={`${prefixo}-${linha.chave}-quantidade`}
                    name="quantidade"
                    type="text"
                    inputMode="decimal"
                    autoComplete="off"
                    value={linha.quantity}
                    onChange={(evento) => {
                      mudarLinha(linha.chave, { quantity: evento.target.value });
                    }}
                    data-numeric
                    className="text-right"
                  />
                </div>

                <div className="flex flex-col gap-1.5">
                  <Label htmlFor={`${prefixo}-${linha.chave}-unidade`} className="sm:sr-only">
                    {textos.formulario.unidade}
                  </Label>
                  <Select
                    value={linha.unit}
                    onValueChange={(valor) => {
                      mudarLinha(linha.chave, { unit: valor });
                    }}
                    disabled={unidades.length === 0}
                  >
                    <SelectTrigger id={`${prefixo}-${linha.chave}-unidade`} className="w-full">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {unidades.map((unidade) => (
                        <SelectItem key={unidade} value={unidade}>
                          {unidade}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  // A última linha não se remove: uma ficha sem ingredientes é
                  // 400 no servidor, e um formulário vazio não tem por onde se
                  // recomeçar.
                  disabled={linhas.length === 1}
                  onClick={() => {
                    setLinhas((anteriores) =>
                      anteriores.filter((outra) => outra.chave !== linha.chave),
                    );
                  }}
                >
                  <X aria-hidden="true" />
                  <span className="sr-only">
                    {textos.accoes.remover(artigo?.nome ?? textos.formulario.escolherArtigo)}
                  </span>
                </Button>
              </li>
            );
          })}
        </ul>

        <div className="flex flex-col gap-1.5">
          <Button
            type="button"
            variant="outline"
            className="self-start"
            onClick={() => {
              setLinhas((anteriores) => [
                ...anteriores,
                { chave: novaChave(), ingredient: "", quantity: "", unit: "" },
              ]);
            }}
          >
            <Plus aria-hidden="true" />
            {textos.accoes.acrescentar}
          </Button>
          {truncado ? (
            <p className="text-xs text-muted-foreground">
              {textos.formulario.tectoDoCatalogo(PAGE_SIZE)}
            </p>
          ) : null}
          {erros.linhas === undefined ? null : (
            <p className="text-sm text-danger">{erros.linhas}</p>
          )}
        </div>
      </section>

      {/* O rendimento, no fim e com a explicação: nasce a 1 porque a perda já
          está na fornada, e sem tecto de 1 — arroz 1 kg cru → 2,7 kg cozido é
          caso real, e o ganho é água da torneira, que não é artigo de stock. */}
      <section className="flex flex-col gap-1.5">
        <Label htmlFor={`${prefixo}-rendimento`}>{textos.formulario.rendimento}</Label>
        <Input
          id={`${prefixo}-rendimento`}
          name="rendimento"
          type="text"
          inputMode="decimal"
          autoComplete="off"
          value={rendimento}
          onChange={(evento) => {
            setRendimento(evento.target.value);
          }}
          data-numeric
          className="max-w-24 text-right"
          aria-invalid={erros.rendimento === undefined ? undefined : true}
          aria-describedby={`${prefixo}-rendimento-ajuda`}
        />
        <p id={`${prefixo}-rendimento-ajuda`} className="max-w-2xl text-xs text-muted-foreground">
          {textos.formulario.rendimentoAjuda}
        </p>
        {erros.rendimento === undefined ? null : (
          <p className="text-sm text-danger">{erros.rendimento}</p>
        )}
      </section>

      <div className="flex items-center gap-2">
        <Button type="submit" disabled={pendente}>
          {pendente
            ? textos.accoes.aGravar
            : ficha === undefined
              ? textos.accoes.gravar
              : textos.accoes.guardar}
        </Button>
        {aoCancelar === undefined ? null : (
          <Button type="button" variant="ghost" onClick={aoCancelar}>
            {textos.accoes.cancelar}
          </Button>
        )}
      </div>
    </form>
  );
}
