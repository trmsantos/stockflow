import { Link, useNavigate, useSearch } from "@tanstack/react-router";
import { ArrowLeft, ClipboardList, Lock, Search, TriangleAlert } from "lucide-react";
import { useState } from "react";

import { EstadoVazio } from "@/components/estado-vazio";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ApiError, mensagemDeErro } from "@/lib/api/errors";
import { formatDate, formatTime } from "@/lib/format";

import {
  useContagensAbertas,
  useIniciarContagem,
  useLinhasDeContagem,
  usePodeFecharContagens,
  useRegistarContagemDeLinha,
  useUltimaContagemFechada,
} from "../api";
import {
  AbrirContagem,
  ContagensAbertas,
  EsqueletoDasContagensAbertas,
} from "../components/contagens-abertas";
import { ErroDaLista } from "../components/estados-da-lista";
import {
  CabecalhoDaContagem,
  EsqueletoDaContagem,
  LinhaDeContagem,
  type RecusaDaLinha,
} from "../components/linha-de-contagem";
import {
  EsqueletoDoProgresso,
  ProgressoDaContagem,
} from "../components/progresso-da-contagem";
import {
  CODIGO_CONTAGEM_FECHADA,
  CODIGO_CONTAGEM_JA_ABERTA,
  codigoDaRecusaDeContagem,
  contagemDoConflito,
  erroDaQuantidade,
  erroDoArtigo,
} from "../recusas-de-contagem";
import type { Contagem, Localizacao } from "../schemas";
import { textos } from "../textos";

/**
 * O ecrã Contar — "o que está na prateleira é o que o sistema diz?".
 *
 * Progresso e localização no topo, uma linha por artigo com o campo numérico, e
 * as linhas **na ordem do servidor**. O cliente não reordena: uma segunda noção
 * de ordem aqui seria uma segunda regra.
 *
 * **O campo numérico deste ecrã não é a "quantidade editável" proibida.** A
 * proibição nº 1 do guião §4 é um lápis ao lado do número no ecrã de Stock, e
 * continua de pé: lá o número é leitura. Aqui escreve-se o que está na
 * prateleira, e ao fechar cada diferença entra no ledger como um `adjustment`
 * com justificação. O ledger continua append-only (ADR 0006) e nenhum nível é
 * reescrito em sítio nenhum.
 *
 * ## O ecrã tem duas faces, e a fronteira é o `?contagem=` (ADR 0033)
 *
 * Havia **uma** contagem aberta por estabelecimento, e por isso este ecrã era o
 * ecrã dela: encontrava-a com um `results.find(status === "open")` e contava-a.
 * Com a exclusividade a passar a ser **por localização**, a arca e a despensa
 * são duas contagens legítimas ao mesmo tempo e aquela selecção ficou errada de
 * duas maneiras — assumia unicidade e dependia da paginação.
 *
 *  - **sem `?contagem=`**, o ecrã é a lista das abertas, com o que começa outra
 *    por baixo. Escolher uma delas por ele seria repor no cliente a
 *    arbitrariedade que a ADR tirou do servidor — e escolher automaticamente a
 *    **única** aberta seria pior ainda: escondia o botão de abrir exactamente de
 *    quem chega para contar outra localização, que é o caso que esta fatia
 *    existe para desbloquear ("às 7h não se conta a despensa porque a câmara
 *    fria ainda está aberta");
 *  - **com `?contagem=`**, é a contagem daquela localização, e um recarregamento
 *    ou um bloqueio de ecrã devolve a mesma (ADR 0008).
 *
 * ## As três coisas que o contrato traz, e onde elas se veem
 *
 *  1. **há uma contagem aberta por localização**, e a segunda tentativa sobre a
 *     **mesma** localização responde 409 com o `id` da que já está aberta. Isso
 *     não é um erro: é um atalho, e o botão do banner leva lá;
 *  2. **abrir e contar são de toda a gente; fechar é de `owner|manager`.** Não é
 *     o ecrã que decide — o servidor impõe-o em `permission_classes` —, mas
 *     desenhar um botão que vai dar 403 é mentir a quem o vê. Esconder é
 *     apresentação, não autorização (ADR 0009);
 *  3. **os euros não são de toda a gente**, e por isso a linha não desenha um
 *     traço onde eles estariam: a quantidade da diferença continua lá, inteira.
 *
 * Fechar com linhas por contar **é possível** e o botão di-lo em vez de se
 * desligar: bloquear é a Q1, e um botão apagado faz quem conta inventar números
 * para o acender (guião §4, proibição 3).
 */

/** O `id` do campo de uma linha, estável entre renderizações e entre zonas. */
function campoDe(produto: string): string {
  return `contagem-${produto}`;
}

/** O que o 409 de `contagem_ja_aberta` deixa no ecrã: a frase e o atalho. */
interface Conflito {
  /** A localização que a pessoa escolheu. A frase nomeia-a. */
  readonly localizacao: string;
  /** A contagem que já estava aberta ali, quando o corpo do 409 a traz. */
  readonly contagem: string | null;
}

/**
 * O índice: **as contagens a decorrer**, o que começa outra, e o resultado da
 * última fechada.
 *
 * Era um estado vazio ("não há contagem a decorrer") porque não havia mais nada
 * que pudesse estar a acontecer. Agora pode haver três, e a lista é o ecrã; o
 * estado vazio é o caso em que ela está vazia, e continua a ter a mesma acção.
 */
function IndiceDasContagens({
  abertas,
  aComecar,
  recusa,
  conflito,
  aoComecar,
  contagemPerdida,
}: {
  readonly abertas: readonly Contagem[];
  readonly aComecar: boolean;
  readonly recusa: string | null;
  readonly conflito: Conflito | null;
  readonly aoComecar: (localizacao: Localizacao) => void;
  /** O `?contagem=` aponta para uma contagem que já não está aberta. */
  readonly contagemPerdida: boolean;
}) {
  const ultima = useUltimaContagemFechada();

  return (
    <>
      {/* O endereço aponta para uma contagem que já não está a decorrer — outra
          pessoa fechou-a, ou é um atalho guardado no telemóvel. Não é erro e
          não é beco: a lista das que estão a decorrer está logo por baixo. */}
      {contagemPerdida ? (
        <div className="px-celula-x pt-3">
          <Alert className="border-warning-border bg-warning-surface">
            <TriangleAlert aria-hidden="true" className="text-warning" />
            <AlertTitle>{textos.contagem.naoEstaAbertaTitulo}</AlertTitle>
            <AlertDescription>{textos.contagem.naoEstaAbertaCorpo}</AlertDescription>
          </Alert>
        </div>
      ) : null}

      {conflito === null ? null : (
        <div className="px-celula-x pt-3">
          <Alert className="border-warning-border bg-warning-surface">
            <TriangleAlert aria-hidden="true" className="text-warning" />
            <AlertTitle>{textos.contagem.jaHaviaAbertaTitulo}</AlertTitle>
            <AlertDescription className="flex flex-col items-start gap-2">
              {textos.contagem.jaHaviaAbertaCorpo(conflito.localizacao)}
              {/* O `id` do corpo do 409 **passou a ter leitor** (ADR 0033): com
                  várias abertas, reler a lista já não leva a lado nenhum — traz
                  três, e nenhuma delas é "a" contagem. Sem `id` legível fica a
                  frase, e a contagem está na lista por baixo. */}
              {conflito.contagem === null ? null : (
                <Button asChild variant="outline" size="sm">
                  <Link to="/contar" search={{ contagem: conflito.contagem }}>
                    {textos.contagem.irParaEssaContagem}
                  </Link>
                </Button>
              )}
            </AlertDescription>
          </Alert>
        </div>
      )}

      {abertas.length === 0 ? (
        <EstadoVazio
          icone={ClipboardList}
          titulo={textos.contagem.semContagemTitulo}
          descricao={textos.contagem.semContagemCorpo}
        >
          <AbrirContagem aComecar={aComecar} aoComecar={aoComecar} />
        </EstadoVazio>
      ) : (
        <>
          <ContagensAbertas contagens={abertas} />
          <div className="flex flex-col items-start gap-3 px-celula-x py-4">
            <AbrirContagem
              titulo={textos.contagem.contarOutra}
              aComecar={aComecar}
              aoComecar={aoComecar}
            />
          </div>
        </>
      )}

      {recusa === null ? null : (
        <p role="alert" className="px-celula-x text-sm text-danger">
          {recusa}
        </p>
      )}

      {/* A última contagem fechada continua a valer como registo: é o que
          responde a "então e a de hoje de manhã?" sem obrigar a abrir outra. */}
      {ultima.data === null || ultima.data === undefined ? null : (
        <div className="flex flex-col items-start gap-2 border-t border-border px-celula-x py-4">
          <h2 className="text-sm font-semibold">{textos.contagem.ultimaFechada}</h2>
          <p className="text-sm text-muted-foreground">
            {ultima.data.location.name} ·{" "}
            {ultima.data.closed_at === null
              ? ""
              : textos.contagem.dataEHora(
                  formatDate(ultima.data.closed_at),
                  formatTime(ultima.data.closed_at),
                )}{" "}
            · <span data-numeric>{ultima.data.counted_lines}</span> {textos.contagem.de}{" "}
            <span data-numeric>{ultima.data.total_lines}</span> {textos.contagem.linhas}
            {ultima.data.closing_reason === null
              ? ""
              : textos.contagem.justificacao(ultima.data.closing_reason)}
          </p>
          <Button asChild variant="outline">
            <Link to="/contar/fechar" search={{ contagem: ultima.data.id }}>
              {textos.contagem.verAsDiferencas}
            </Link>
          </Button>
        </div>
      )}
    </>
  );
}

export function EcraDeContar() {
  const busca = useSearch({ from: "/app/contar" });
  // `from` é o **caminho** da rota e não o id dela: o `useSearch` acima lê por
  // id (`/app/…`) e o `useNavigate` tipa-se pelo caminho.
  const navegar = useNavigate({ from: "/contar" });

  const contagens = useContagensAbertas();
  const abertas = contagens.data?.results;
  const aberta =
    busca.contagem === undefined
      ? null
      : (abertas?.find((contagem) => contagem.id === busca.contagem) ?? null);
  // Só depois de a lista chegar: enquanto ela não chegou, "não está lá" é
  // indistinguível de "ainda não se sabe", e o banner piscava a cada visita.
  const contagemPerdida = busca.contagem !== undefined && abertas !== undefined && aberta === null;

  const podeFechar = usePodeFecharContagens();
  const linhas = useLinhasDeContagem(aberta?.id, busca.zona);
  const registar = useRegistarContagemDeLinha();
  const iniciar = useIniciarContagem();

  // O 409 de `contagem_ja_aberta` não é um erro: é um atalho para a contagem
  // que já está aberta naquela localização. Fica em estado porque sobrevive à
  // invalidação da lista — o `onError` da mutação relê as abertas, e sem isto a
  // frase desaparecia no instante em que a contagem aparecesse na lista.
  const [conflito, setConflito] = useState<Conflito | null>(null);

  const resultados = linhas.data?.results;
  const porContar = aberta === null ? 0 : aberta.total_lines - aberta.counted_lines;
  const contagemFechouAMeio =
    registar.isError && codigoDaRecusaDeContagem(registar.error) === CODIGO_CONTAGEM_FECHADA;

  // O campo por contar que vem **depois** deste, na ordem em que estão no ecrã:
  // é para onde o foco salta depois de guardar, e é o que mantém o teclado
  // aberto de cima a baixo da lista.
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

  /**
   * A recusa **desta** linha, com o registo certo.
   *
   * Vive na linha e não num banner no topo, porque é sobre um artigo e não sobre
   * a contagem — num banner, quem a lesse ia procurar o problema no sítio
   * errado. As três formas que o servidor manda, por ordem de especificidade:
   *
   *  1. `{"product": [...]}` — um artigo com controlo por lotes e sem lote
   *     registado. A frase manda fazer a receção: é **orientação**, não falha de
   *     quem está a contar, e por isso o registo é âmbar e não vermelho;
   *  2. `{"quantity": [...]}` — o número não serve (negativo, ou grande de mais
   *     para a coluna depois de convertido). É uma falha de entrada e lê-se como
   *     tal;
   *  3. tudo o resto, incluindo o que não tem corpo JSON nenhum — uma falha de
   *     rede, que num armazém é o caso mais provável. Aí a frase é do catálogo:
   *     o `message` de um `ApiError` sem `detail` é `"500 em /stock/counts/…"`,
   *     que é texto de diagnóstico e não de produto.
   */
  function recusaDaLinha(produto: string): RecusaDaLinha | null {
    if (!registar.isError || contagemFechouAMeio) return null;
    if (registar.variables.product !== produto) return null;

    const orientacao = erroDoArtigo(registar.error);
    if (orientacao !== null) return { frase: orientacao, orientacao: true };

    const doCampo = erroDaQuantidade(registar.error);
    if (doCampo !== null) return { frase: doCampo, orientacao: false };

    const semDetalhe = registar.error instanceof ApiError && registar.error.detail === null;
    return {
      frase: semDetalhe ? textos.contagem.naoFoiGuardado : mensagemDeErro(registar.error),
      orientacao: false,
    };
  }

  return (
    // Sem `max-w-2xl` desde 2026-10-06: o dono do produto apanhou este ecrã a
    // parecer de outro produto ao lado dos outros, e tinha razão. O que mudou foi
    // a largura e o cromado; as linhas **continuam a ser um formulário** e não
    // uma tabela, porque a 360px cinco colunas pedem 640px e um `overflow-x-auto`
    // punha fora do ecrã o campo que se está a escrever. A razão inteira, e o
    // pressuposto escondido que me fez deixá-lo de fora, estão no
    // `GRELHA_DA_LINHA` do `linha-de-contagem.tsx`.
    <section className="flex w-full flex-col">
      {/* O nome do ecrã já está no header do shell; repeti-lo em grande custava
          uma das sete linhas do orçamento de 360×640. */}
      <h1 className="sr-only">{textos.contagem.titulo}</h1>

      {contagens.isPending ? (
        busca.contagem === undefined ? (
          <EsqueletoDasContagensAbertas />
        ) : (
          <>
            <EsqueletoDoProgresso />
            <EsqueletoDaContagem />
          </>
        )
      ) : null}

      {contagens.isError ? (
        <ErroDaLista
          titulo={textos.contagem.erroDaContagem}
          mensagem={mensagemDeErro(contagens.error)}
          aoTentarOutraVez={() => {
            void contagens.refetch();
          }}
        />
      ) : null}

      {abertas === undefined ? null : aberta === null ? (
        <IndiceDasContagens
          abertas={abertas}
          aComecar={iniciar.isPending}
          contagemPerdida={contagemPerdida}
          conflito={conflito}
          recusa={
            iniciar.isError && codigoDaRecusaDeContagem(iniciar.error) !== CODIGO_CONTAGEM_JA_ABERTA
              ? mensagemDeErro(iniciar.error)
              : null
          }
          aoComecar={(localizacao) => {
            setConflito(null);
            iniciar.mutate(
              { location: localizacao.id },
              {
                // Abrir **leva lá**: o `id` da contagem nova entra no URL, e a
                // pessoa que carregou no botão está a contar no toque seguinte.
                onSuccess: (nova) => {
                  void navegar({ to: "/contar", search: { contagem: nova.id } });
                },
                onError: (erro) => {
                  if (codigoDaRecusaDeContagem(erro) !== CODIGO_CONTAGEM_JA_ABERTA) return;
                  setConflito({
                    localizacao: localizacao.name,
                    contagem: contagemDoConflito(erro),
                  });
                },
              },
            );
          }}
        />
      ) : (
        <>
          {/* O caminho de volta à lista — e é por aqui que se abre a contagem de
              **outra** localização sem fechar esta. Sem ele, quem entrou numa
              contagem ficava lá fechado. */}
          <Button asChild variant="ghost" className="self-start">
            <Link to="/contar" search={() => ({})}>
              <ArrowLeft aria-hidden="true" />
              {textos.contagem.aDecorrer}
            </Link>
          </Button>

          <ProgressoDaContagem contagem={aberta} zonaAtiva={busca.zona} />

          {linhas.isPending ? <EsqueletoDaContagem /> : null}

          {linhas.isError ? (
            <ErroDaLista
              titulo={textos.contagem.erroDasLinhas}
              mensagem={mensagemDeErro(linhas.error)}
              aoTentarOutraVez={() => {
                void linhas.refetch();
              }}
            />
          ) : null}

          {resultados === undefined ? null : resultados.length === 0 ? (
            <EstadoVazio
              icone={Search}
              titulo={textos.contagem.zonaVaziaTitulo}
              descricao={textos.contagem.zonaVaziaCorpo}
            >
              <Button asChild variant="outline">
                <Link to="/contar" search={{ contagem: aberta.id }}>
                  {textos.contagem.verTudo}
                </Link>
              </Button>
            </EstadoVazio>
          ) : (
            <>
              <CabecalhoDaContagem />
              <ul className="flex flex-col">
                {resultados.map((linha, indice) => (
                  <LinhaDeContagem
                    key={linha.id}
                    linha={linha}
                    idDoCampo={campoDe(linha.product)}
                    idDoCampoSeguinte={campoSeguinte(indice)}
                    aRegistar={registar.isPending && registar.variables.product === linha.product}
                    recusa={recusaDaLinha(linha.product)}
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

              {/* A contagem fechou debaixo dos pés de quem estava a contar: é
                  sobre a contagem toda e não sobre uma linha, logo é aqui e não
                  lá. O número que ela acabou de escrever **não entrou**. */}
              {contagemFechouAMeio ? (
                <div className="px-celula-x py-3">
                  <Alert className="border-danger-border bg-danger-surface">
                    <TriangleAlert aria-hidden="true" className="text-danger" />
                    <AlertTitle>{textos.contagem.fechouAMeioTitulo}</AlertTitle>
                    <AlertDescription>{textos.contagem.fechouAMeioCorpo}</AlertDescription>
                  </Alert>
                </div>
              ) : null}

              {/* O fecho fica no fim da lista, onde se chega depois de contar, e
                  não colado ao ecrã numa barra fixa: ela tapava a última linha,
                  que é precisamente a que falta contar. A razão sobrevive à
                  saída da tab bar (ADR 0009) — o que tapava a linha era a barra
                  fixa, não o que estava por baixo dela. */}
              <div className="flex flex-col items-start gap-1.5 border-t border-border px-celula-x py-4">
                {podeFechar ? (
                  <Button asChild>
                    <Link to="/contar/fechar" search={{ contagem: aberta.id }}>
                      {porContar === 0
                        ? textos.fecho.fechar
                        : textos.fecho.fecharComPorContar(porContar)}
                    </Link>
                  </Button>
                ) : null}
                <p className="flex items-center gap-1 text-xs text-muted-foreground">
                  <Lock aria-hidden="true" className="size-3 shrink-0" />
                  {textos.contagem.soOPapelFecha(aberta.closing_role)}
                </p>
              </div>
            </>
          )}
        </>
      )}
    </section>
  );
}
