import { Link } from "@tanstack/react-router";

import {
  CLASSE_CELULA,
  CLASSE_LINHA,
  EsqueletoDeTabela,
  MolduraDeTabela,
  TrilhoDaLinha,
  type ColunaDeTabela,
} from "@/components/tabela";
import { Button } from "@/components/ui/button";
import { formatMoney } from "@/lib/format";

import type { Alerta, MotivoQuebra } from "../schemas";
import { textos } from "../textos";
import { tintaDoTextoDeGravidade, tintaDoTrilhoDeGravidade } from "../tinta-do-estado";
import { MOTIVOS_DE_DESPERDICIO, rotuloDeMotivo, textoDeQuantidade } from "../vocabulario";
import { TextoDeValidade } from "./validade";

/**
 * Os alertas como tabela densa, com a mesma linguagem do ecrã de Stock.
 *
 * ## O que a conversão arrumou, para além da largura
 *
 * A lista antiga punha sete factos em três linhas empilhadas de 56px, e os
 * quatro últimos num rodapé juntos por pontos médios: "lote L-AMD-0928 · aviso a
 * 3 dias · mínimo 3,000 kg · Copa". Quatro coisas diferentes a fingir que eram
 * uma lista — o cromado de template que o `frontend-design` nomeia como tell, e
 * que aqui custava mais do que estética: para comparar o lote de duas linhas
 * tinha de se ler as duas.
 *
 * Em colunas, cada um desses factos tem sítio fixo e compara-se na vertical. E
 * dois deles deixaram de ser coluna de propósito, porque informam **onde estão**
 * e não isolados: o limiar de dias entra na frase da validade ("expira amanhã,
 * aviso a 3 dias") e o mínimo entra na frase da falta ("abaixo do mínimo de
 * 3,000 kg"). Uma coluna "MÍNIMO" estaria vazia em metade das linhas, porque um
 * alerta de validade não tem mínimo e um de falta não tem limiar — e uma coluna
 * meia vazia numa tabela de ERP é uma pergunta por linha.
 *
 * ## O trilho quer dizer outra coisa aqui, e vale dizê-lo
 *
 * No Stock o trilho distingue "precisa de atenção" de "está bem". Neste ecrã
 * **todas** as linhas são alertas, logo o trilho distingue **urgência**: um
 * `info` não leva trilho porque é um alerta que não se quer ver de dois metros.
 * A tinta vem do mesmo módulo que a do Stock (`tinta-do-estado.ts`), para um
 * "baixo" e o alerta que ele gera não terem cores diferentes.
 *
 * ## A acção mudou de sítio, e ficou mais correcta
 *
 * A linha inteira era um `<button>` nos alertas de validade e um `<Link>` nos de
 * falta — duas coisas com o mesmo aspecto e comportamentos diferentes. Num
 * `<table>` nenhuma das duas é possível, e a forma certa apareceu por
 * consequência: **o nome é sempre um link** para o artigo (como no Stock) e a
 * acção vive na sua coluna, onde existe só nas linhas em que faz efeito. Não se
 * deita fora o que não há, logo uma falta não tem botão — e não tem um botão
 * `disabled`, que numa tabela densa é uma pergunta em cada linha.
 *
 * Os dois toques mantêm-se: o primeiro abre os motivos, o segundo regista. Um
 * movimento é append-only (ADR 0006), logo deitar fora ao primeiro toque era um
 * movimento irreversível por acidente.
 */

/**
 * As sete colunas, com as larguras medidas e não estimadas.
 *
 * **A primeira distribuição estava errada e viu-se num screenshot.** Com o
 * `Porquê` flexível ele ficava com 174px e truncava exactamente a informação que
 * justifica o alerta: "sem stock de 12,0…", "perde qualidade e…", "abaixo do
 * mínimo …". Uma coluna que corta a razão do alerta é pior do que não a ter.
 *
 * Agora o `Porquê` tem largura própria e generosa (240px, o que paga "perde
 * qualidade em 2 dias" por extenso) e é o **artigo** que fica flexível — um nome
 * truncado lê-se mesmo assim, e o nome completo está no link que se segue.
 */
const COLUNA_DO_VALOR: ColunaDeTabela = {
  chave: "valor",
  rotulo: textos.colunas.valor,
  classe: "w-24 text-right",
};

/**
 * As colunas, **com ou sem a do valor**.
 *
 * O `value_eur` chega ausente a quem não vê euros (ADR 0032, decisão 1), e com
 * a chave fora do JSON sai a **coluna inteira** — não uma célula vazia nem um
 * traço, que seriam uma pergunta por linha sobre um número que não é para
 * aquela pessoa. É a mesma decisão das colunas de dinheiro da receção.
 *
 * Duas listas e não uma com um `filter` por render: são duas formas estáveis, e
 * é esta constante que o esqueleto também usa — um esqueleto com mais colunas
 * do que a tabela é um salto de layout no instante em que os dados chegam.
 */
function colunasDe(comValor: boolean): readonly ColunaDeTabela[] {
  return [
    { chave: "artigo", rotulo: textos.colunas.artigo },
    { chave: "quantidade", rotulo: textos.colunas.quantidade, classe: "w-36 text-right" },
    ...(comValor ? [COLUNA_DO_VALOR] : []),
    { chave: "porque", rotulo: textos.colunas.porque, classe: "w-60" },
    { chave: "lote", rotulo: textos.colunas.lote, classe: "w-32" },
    { chave: "onde", rotulo: textos.colunas.onde, classe: "w-24" },
    { chave: "accao", rotulo: textos.colunas.accao, classe: "w-32" },
  ];
}

/**
 * Este payload trouxe euros? Pergunta-se ao **payload** e não ao papel da
 * sessão: o papel seria uma segunda definição da política, escrita onde
 * ninguém a mantém, e no dia em que o dono a mudar o ecrã muda com ela sem um
 * diff. É o mesmo critério do `euros-do-papel.ts` do `purchasing`.
 *
 * Um `some` e não um `every`: a lista vazia não prova nada sobre quem olha, e
 * nesse caso não há colunas a desenhar de qualquer forma.
 */
function mostraEuros(alertas: readonly Alerta[]): boolean {
  return alertas.some((alerta) => alerta.value_eur !== undefined);
}

const LARGURA_MINIMA = "min-w-4xl";
const ROTULO = textos.alertas.tabela;

/**
 * A frase de uma falta. Três palavras e não duas: um stock **negativo** não é
 * "sem stock", é um ledger a dizer que saiu mais do que entrou — e é a sonda da
 * Q1 (a nata a −2 L depois de uma quebra registada sem stock). Chamar-lhe "sem
 * stock" apagava a pergunta.
 *
 * **O valor do mínimo saiu desta frase** e passou a uma segunda linha da célula
 * da quantidade. Duas razões, e a segunda é a que decide: "abaixo do mínimo de
 * 4,000 kg" não cabia na coluna e truncava a parte que importa; e o sítio certo
 * para o mínimo é **ao lado da quantidade**, que é o número contra o qual ele se
 * lê. É a mesma decisão que a coluna "Mínimo" do ecrã de Stock, aqui sem gastar
 * uma coluna que estaria vazia em metade das linhas — um alerta de validade não
 * tem mínimo.
 */
function fraseDaFalta(alerta: Alerta): string {
  return alerta.quantity.base.startsWith("-")
    ? textos.alertas.stockNegativo
    : Number(alerta.quantity.base) === 0
      ? textos.alertas.semStock
      : textos.alertas.abaixoDoMinimo;
}

function LinhaDeAlerta({
  alerta,
  aberto,
  aoAlternar,
  aoDeitarFora,
  aRegistar,
  erro,
  idDoPainel,
  totalDeColunas,
}: {
  readonly alerta: Alerta;
  readonly aberto: boolean;
  readonly aoAlternar: () => void;
  readonly aoDeitarFora: (motivo: MotivoQuebra) => void;
  readonly aRegistar: boolean;
  readonly erro: string | null;
  readonly idDoPainel: string;
  readonly totalDeColunas: number;
}) {
  const deValidade = alerta.reason === "expiry";
  // Duas frases inteiras e não uma com um buraco: um alerta de falta não tem
  // lote, e uma frase montada por pedaços não se traduz. O lote sintético — o
  // que a produção de uma receita cria — não tem código, e aí a frase é a
  // mesma de uma falta: nomear "o lote null" era pior do que não o nomear.
  const quantidade = textoDeQuantidade(alerta.quantity);
  const codigoDoLote = alerta.lot?.lot_code ?? null;
  const rotuloDaAccao =
    codigoDoLote === null
      ? textos.alertas.deitarForaAccao(alerta.short_name, quantidade)
      : textos.alertas.deitarForaAccaoComLote(alerta.short_name, codigoDoLote, quantidade);

  return (
    <>
      <tr className={`group ${CLASSE_LINHA} transition-colors hover:bg-surface-2`}>
        <TrilhoDaLinha tinta={tintaDoTrilhoDeGravidade(alerta.severity)} />

        <th scope="row" className={`${CLASSE_CELULA} max-w-0 text-left font-medium`}>
          <Link
            to="/stock/$artigo"
            params={{ artigo: alerta.product }}
            search={{}}
            className="block truncate hover:underline group-hover:underline"
          >
            {alerta.short_name}
          </Link>
        </th>

        <td data-numeric className={`${CLASSE_CELULA} w-36 text-right`}>
          {textoDeQuantidade(alerta.quantity)}
          {/* O mínimo, onde ele se lê: debaixo do número que ele julga. */}
          {alerta.min_quantity === null ? null : (
            <span className="block text-xs text-muted-foreground">
              {textos.alertas.minimoAbreviado} {textoDeQuantidade(alerta.min_quantity)}
            </span>
          )}
        </td>

        {/* A coluna existe ou não existe — nunca com um traço lá dentro.
            Dentro dela, um custo **desconhecido** diz-se por extenso: o
            servidor serve `0.00` quando não há preço nenhum, e imprimir
            "0,00 €" é afirmar que aquele lote não vale nada. É a palavra que
            a tabela de linhas de fatura já usa para o mesmo facto. */}
        {alerta.value_eur === undefined ? null : (
          <td data-numeric className={`${CLASSE_CELULA} w-24 text-right`}>
            {alerta.cost_status === "desconhecido" ? (
              <span className="text-xs text-muted-foreground">{textos.alertas.semPreco}</span>
            ) : (
              formatMoney(alerta.value_eur)
            )}
          </td>
        )}

        <td className={`${CLASSE_CELULA} w-60`}>
          {alerta.lot === null ? (
            <span className={`block truncate ${tintaDoTextoDeGravidade(alerta.severity)}`}>
              {fraseDaFalta(alerta)}
            </span>
          ) : (
            <>
              <span className="block truncate">
                <TextoDeValidade
                  validade={alerta.lot}
                  limiarEmDias={alerta.threshold_days ?? 0}
                />
              </span>
              {/* O limiar fica **aqui** e não na coluna do lote, e não é
                  arrumação: na coluna do lote ele partia em duas linhas de 13px
                  e punha aquelas linhas a 62px numa tabela de 44 — media-se e
                  via-se, o ritmo da tabela desfeito em metade das linhas. Ao
                  lado da frase da validade ele também informa melhor, porque é a
                  frase que ele explica: "expira amanhã" com "aviso a 3 dias"
                  debaixo é a razão completa, e é assim que o dono a contesta em
                  voz alta em vez de a ir mudar num painel (guião §4, nº 7). */}
              {alerta.threshold_days === null ? null : (
                <span className="block text-xs text-muted-foreground">
                  {textos.alertas.avisoAInicio}{" "}
                  <span data-numeric>{alerta.threshold_days}</span>{" "}
                  {textos.alertas.avisoAFim}
                </span>
              )}
            </>
          )}
        </td>

        {/* Vazia num lote sintético (`lot_code: null`): ali não há código
            nenhum para imprimir, e "—" afirmaria que o lote não existe. */}
        <td data-numeric className={`${CLASSE_CELULA} w-32 text-left text-muted-foreground`}>
          {codigoDoLote ?? ""}
        </td>

        {/* "todas" e não "todas as lojas": o cabeçalho da coluna já diz "Onde",
            logo a palavra "lojas" é a pergunta repetida na resposta — e era ela
            que obrigava a coluna a ter 128px numa tabela onde o espaço faltava à
            coluna do porquê. */}
        <td className={`${CLASSE_CELULA} w-24 text-muted-foreground`}>
          <span className="block truncate">
            {alerta.location?.name ?? (deValidade ? "" : textos.alertas.todasAsLojas)}
          </span>
        </td>

        {/* A acção só existe onde faz efeito. Uma falta não tem botão — nem um
            `disabled`, que numa tabela densa é uma pergunta em cada linha e a
            resposta já está na coluna do porquê. */}
        <td className={`${CLASSE_CELULA} w-32`}>
          {deValidade ? (
            // `whitespace-nowrap`: sem isto "Deitei fora" partia em duas linhas
            // dentro do botão e a linha da tabela crescia com ele.
            <Button
              variant="outline"
              size="sm"
              className="whitespace-nowrap"
              onClick={aoAlternar}
              aria-expanded={aberto}
              aria-controls={idDoPainel}
              aria-label={rotuloDaAccao}
            >
              {textos.alertas.deitarFora}
            </Button>
          ) : null}
        </td>
      </tr>

      {aberto ? (
        // Segundo toque: o motivo. Cinco botões e não um `<select>` — escolher
        // num menu nativo com a mão suja é dois gestos e um scroll, e o motivo é
        // obrigatório (`inventory-domain` §8), logo é o passo e não um extra.
        <tr className="border-b border-border">
          <td aria-hidden="true" className="w-trilho p-0 bg-surface-2" />
          <td id={idDoPainel} colSpan={totalDeColunas} className="bg-surface-2 px-celula-x py-3">
            <div className="flex flex-col gap-2">
              <p className="text-sm">
                {textos.alertas.deitarForaInicio}{" "}
                <span data-numeric>{textoDeQuantidade(alerta.quantity)}</span>
                {codigoDoLote === null ? "" : textos.alertas.doLote(codigoDoLote)}
                {textos.alertas.deitarForaPorque}
              </p>
              <div className="flex flex-wrap gap-2">
                {MOTIVOS_DE_DESPERDICIO.map((motivo) => (
                  <Button
                    key={motivo}
                    variant="outline"
                    size="sm"
                    disabled={aRegistar}
                    onClick={() => {
                      aoDeitarFora(motivo);
                    }}
                  >
                    {rotuloDeMotivo(motivo)}
                  </Button>
                ))}
                <Button variant="ghost" size="sm" disabled={aRegistar} onClick={aoAlternar}>
                  {textos.alertas.cancelar}
                </Button>
                {aRegistar ? (
                  <span className="self-center text-sm text-muted-foreground">
                    {textos.accoes.aRegistar}
                  </span>
                ) : null}
              </div>
              {erro === null ? null : (
                <p role="alert" className="text-sm text-danger">
                  {erro}
                </p>
              )}
            </div>
          </td>
        </tr>
      ) : null}
    </>
  );
}

export function TabelaDeAlertas({
  alertas,
  abertaEm,
  aoAlternar,
  aoDeitarFora,
  produtoARegistar,
  erro,
}: {
  readonly alertas: readonly Alerta[];
  /** O `id` do alerta com o painel de motivos aberto, ou `null`. */
  readonly abertaEm: string | null;
  readonly aoAlternar: (id: string) => void;
  readonly aoDeitarFora: (alerta: Alerta, motivo: MotivoQuebra) => void;
  /** O `product` cujo registo está a sair, ou `null`. */
  readonly produtoARegistar: string | null;
  readonly erro: string | null;
}) {
  const colunas = colunasDe(mostraEuros(alertas));

  return (
    <MolduraDeTabela
      colunas={colunas}
      larguraMinima={LARGURA_MINIMA}
      comTrilho
      rotulo={ROTULO}
    >
      <tbody>
        {alertas.map((alerta) => (
          <LinhaDeAlerta
            key={alerta.id}
            alerta={alerta}
            totalDeColunas={colunas.length}
            idDoPainel={`motivos-${alerta.id}`}
            aberto={abertaEm === alerta.id}
            aoAlternar={() => {
              aoAlternar(alerta.id);
            }}
            aRegistar={produtoARegistar === alerta.product}
            erro={abertaEm === alerta.id ? erro : null}
            aoDeitarFora={(motivo) => {
              aoDeitarFora(alerta, motivo);
            }}
          />
        ))}
      </tbody>
    </MolduraDeTabela>
  );
}

/**
 * O pendente desenha **com** a coluna do valor, porque é a forma mais larga e
 * porque quem ainda não recebeu a lista não sabe se ela traz euros. Para quem
 * não os vê, a coluna sai quando os dados chegam — uma coluna a menos é um
 * reflow para a esquerda, que é menos violento do que o contrário.
 */
export function EsqueletoDaTabelaDeAlertas() {
  return (
    <EsqueletoDeTabela
      colunas={colunasDe(true)}
      larguraMinima={LARGURA_MINIMA}
      comTrilho
      rotulo={textos.alertas.aCarregar}
    />
  );
}
