import { Ban, RefreshCw } from "lucide-react";
import { useState } from "react";

import {
  CLASSE_CELULA,
  CLASSE_LINHA,
  EsqueletoDeTabela,
  MolduraDeTabela,
  type ColunaDeTabela,
} from "@/components/tabela";
import { Button } from "@/components/ui/button";
import { formatDate, formatDayMonth } from "@/lib/format";

import { nomeDoEstadoDoConvite, nomeDoPapel, type Convite } from "../schemas";
import { BadgeDeEstadoDoConvite } from "./badge-de-estado-do-convite";
import { ValidadeDoConvite } from "./validade-do-convite";

/**
 * A tabela de convites — **o primeiro ecrã deste repositório com a largura toda**
 * (DESIGN.md §4).
 *
 * Os quatro ecrãs de produto anteriores abrem com um cap de `42rem` por dívida
 * deliberada (§4: foram desenhados para 360px quando o produto era mobile-first,
 * e alargar o cap sem passar as linhas a tabela densa é pior do que o que está).
 * Este ecrã é novo, logo não herda a dívida: é uma `<table>` a sério, densa,
 * linha a `h-linha` (44px), cabeçalho em `surface-2` com os microrótulos em caixa
 * alta, e réguas verticais de 1px entre colunas — que é o cromado contado que o
 * §2 descreve.
 *
 * ## Uma `<table>` e não uma lista de divs
 *
 * Sete colunas com cabeçalho é uma tabela de dados, e a semântica paga-se a
 * quem navega por áudio: um leitor de ecrã anuncia "Papel: dono" ao entrar na
 * célula, o que uma grelha de `<div>`s com `role="row"` só consegue imitando
 * seis atributos à mão. O `scope="col"` é o que liga cada célula ao seu
 * cabeçalho.
 *
 * ## O que **não** está aqui: o cabeçalho sticky
 *
 * O DESIGN.md §3 pede "cabeçalho sticky" nas tabelas, e este não o tem. A razão
 * é de CSS e não de esquecimento: a 360px a tabela desliza na horizontal (o §4
 * aceita-o e manda declará-lo para rotas que não são de campo), e o invólucro que
 * faz isso — `overflow-x-auto` — torna-se o *scrollport* do `position: sticky`.
 * Como esse invólucro não tem altura própria e não rola na vertical, um `thead`
 * sticky ficaria colado ao topo de um contentor que nunca se move: a classe
 * existiria e o efeito não. Entre uma afirmação falsa no código e uma
 * declaração verdadeira, fica a declaração — e o que de facto acompanha o scroll
 * é a barra do ecrã, que é sticky a `top-cabecalho`. Está no relatório como
 * desvio nomeado, com a alternativa (dar altura própria à região da tabela) por
 * decidir com o dono à frente.
 *
 * ## As acções seguem o estado, e o estado vem do servidor
 *
 * Medido contra o backend a correr, porque a prosa sobre isto divergia em dois
 * sítios do repositório:
 *
 *  - **reenviar** é aceite num `pendente` **ou `expirado`**; dá 409
 *    `convite_nao_pendente` num `aceite` e num `revogado`;
 *  - **revogar** é aceite em tudo o que não foi `aceite`, e é **idempotente**:
 *    revogar um já revogado devolve 200 com a linha como está, sem escrita. O 409
 *    é só sobre um aceite, porque aí a pertença já existe e quem a retira é outro
 *    caminho.
 *
 * A UI oferece **menos** do que o servidor aceita, e isso é a decisão: os botões
 * só existem onde fazem efeito (`pendente` e `expirado`). A diferença é uma
 * linha — "Revogar" num convite que já diz "revogado" seria aceite pelo servidor
 * e não mudaria nada, logo é um botão que promete o que não cumpre. A razão
 * completa, e o caso do `expirado` que **não** é redundante, estão no
 * `estaVivo` da linha.
 *
 * Um botão que não faz sentido **não está lá**, em vez de estar `disabled`: um
 * botão desactivado numa tabela densa é uma pergunta ("porquê?") em cada linha,
 * e a resposta já está na coluna do estado. Os que lá estão ficam `disabled` com
 * `aria-busy` enquanto o pedido sai.
 */

/** As sete colunas, e o que cada uma é. Uma lista só, usada pelas três formas. */
const COLUNAS: readonly ColunaDeTabela[] = [
  { chave: "email", rotulo: "Email" },
  { chave: "nome", rotulo: "Nome" },
  { chave: "papel", rotulo: "Papel" },
  { chave: "estado", rotulo: "Estado" },
  { chave: "validade", rotulo: "Link" },
  { chave: "criado", rotulo: "Criado", classe: "text-right" },
  { chave: "accoes", rotulo: "Acções", classe: "text-right" },
];

/**
 * A moldura, as classes de célula e de linha e o esqueleto vêm de
 * `@/components/tabela`.
 *
 * **Viviam aqui**, e desceram a 2026-10-06 quando o ecrã Stock passou de lista
 * de cartões a tabela densa: as convenções do cromado — altura de linha, réguas
 * verticais, cabeçalho em `surface-2`, microrótulo em caixa alta — passaram a ser
 * precisas em duas features, e a descida é a que a ADR 0008 (decisão 2) deixou
 * pré-aprovada para o primeiro caso real. O argumento não é reutilização: duas
 * tabelas com a mesma intenção em dois ficheiros divergem na primeira correção
 * feita só num deles.
 *
 * `min-w-4xl` (56rem) é o que garante que as sete colunas não se esmagam. A
 * 1280px a área de conteúdo tem ~1024px (64rem), logo não há scroll nenhum em
 * desktop; a 360px há, e isso é o que o §4 declara em vez de tratar como
 * defeito. Esconder colunas em mobile foi a alternativa rejeitada: numa lista de
 * quem tem acesso a uma casa, a coluna que se esconde é a que faltava.
 */
const LARGURA_MINIMA = "min-w-4xl";

const ROTULO = "Convites enviados, do mais recente para o mais antigo";

export function TabelaDeConvites({
  convites,
  aReenviar,
  aRevogar,
  aoReenviar,
  aoRevogar,
}: {
  readonly convites: readonly Convite[];
  /** O `id` do convite cujo reenvio está a sair, ou `null`. */
  readonly aReenviar: string | null;
  /** O `id` do convite cuja revogação está a sair, ou `null`. */
  readonly aRevogar: string | null;
  readonly aoReenviar: (id: string) => void;
  readonly aoRevogar: (convite: Convite) => void;
}) {
  return (
    <MolduraDeTabela colunas={COLUNAS} larguraMinima={LARGURA_MINIMA} rotulo={ROTULO}>
      <tbody>
        {convites.map((convite) => (
          <LinhaDeConvite
            key={convite.id}
            convite={convite}
            aReenviar={aReenviar === convite.id}
            aRevogar={aRevogar === convite.id}
            inerte={aReenviar !== null || aRevogar !== null}
            aoReenviar={aoReenviar}
            aoRevogar={aoRevogar}
          />
        ))}
      </tbody>
    </MolduraDeTabela>
  );
}

function LinhaDeConvite({
  convite,
  aReenviar,
  aRevogar,
  inerte,
  aoReenviar,
  aoRevogar,
}: {
  readonly convite: Convite;
  readonly aReenviar: boolean;
  readonly aRevogar: boolean;
  /** Há **alguma** mutação a sair: as outras linhas também ficam quietas. */
  readonly inerte: boolean;
  readonly aoReenviar: (id: string) => void;
  readonly aoRevogar: (convite: Convite) => void;
}) {
  /**
   * A revogação pede confirmação **na própria linha**, em dois passos.
   *
   * Revogar é final — "um convite revogado não ressuscita" (ADR 0010, ponto 5) —
   * e uma acção final a um clique numa tabela densa de linhas de 44px é um
   * acidente à espera do rato errado. A confirmação é inline e não um diálogo
   * por duas razões: não há primitivo de diálogo instalado (há `sheet`, que é
   * outra coisa) e um diálogo modal tira o contexto a quem precisa de confirmar
   * **qual** das linhas está a revogar. Em dois passos, a linha continua à
   * vista, o email continua à esquerda, e o segundo clique é deliberado.
   *
   * O estado é local à linha de propósito: só uma pode estar a perguntar, porque
   * confirmar fecha-a, e cada linha esquece a pergunta ao mudar de estado.
   */
  const [aConfirmarRevogacao, setAConfirmarRevogacao] = useState(false);

  /**
   * O convite ainda **faz** alguma coisa? — e é esta a pergunta, não "o servidor
   * aceitaria?".
   *
   * As duas respostas não coincidem, e é deliberado mostrar a mais apertada:
   *
   *  - o servidor aceita **revogar** em tudo o que não foi aceite, e isso inclui
   *    um convite **já revogado** — medido: devolve 200 e a linha como está, sem
   *    escrita. É idempotência certa no servidor (é o que um duplo clique precisa)
   *    e um botão inútil na UI: oferecer "Revogar" numa linha que diz "revogado"
   *    é prometer uma mudança que não acontece;
   *  - **reenviar** um revogado dá 409 (medido), porque revogar é final e um
   *    convite revogado não ressuscita (ADR 0010, ponto 5).
   *
   * Logo os dois botões vivem exactamente onde fazem efeito: `pendente` e
   * `expirado`. E revogar um **expirado** não é redundante — um convite expirado
   * continua a bloquear um convite novo para o mesmo email (medido: 400 "Já existe
   * um convite para este email"), e revogá-lo é o que desbloqueia. É por isso que
   * o par de botões é o mesmo nos dois estados.
   *
   * O estado é a autoridade e vem do servidor (ADR 0010: derivado dos três
   * timestamps). Esta linha é o que uma união fechada compra: um estado novo no
   * backend não chega aqui sem alguém decidir o que fazer com ele.
   */
  const estaVivo = convite.estado === "pendente" || convite.estado === "expirado";

  return (
    <tr className={`${CLASSE_LINHA} transition-colors hover:bg-surface`}>
      {/* O email é o que identifica a linha: é ele o `th` da linha, não uma
          célula qualquer, e é em mono porque é um dado que se compara carácter a
          carácter (DESIGN.md §2). */}
      <th scope="row" className={`${CLASSE_CELULA} max-w-0 text-left font-normal`}>
        {/* `translate="no"`: um email é um identificador. A tradução automática
            do browser já transformou domínios em palavras, e um email traduzido
            numa lista de acessos é uma pessoa que não se encontra. */}
        <span className="block truncate font-mono" translate="no" title={convite.email}>
          {convite.email}
        </span>
      </th>
      <td className={`${CLASSE_CELULA} max-w-0`}>
        <span className="block truncate" title={convite.nome}>
          {convite.nome}
        </span>
      </td>
      <td className={CLASSE_CELULA}>{nomeDoPapel(convite.papel)}</td>
      <td className={CLASSE_CELULA}>
        <BadgeDeEstadoDoConvite estado={convite.estado} />
      </td>
      <td className={CLASSE_CELULA}>
        <ValidadeDoConvite convite={convite} />
      </td>
      {/* `data-numeric` dá mono, `tabular-nums` e alinhamento à direita de uma
          vez (`base.css`): uma coluna de datas só se lê de relance se os dígitos
          tiverem todos a mesma largura. */}
      <td data-numeric className={CLASSE_CELULA} title={formatDate(convite.criado_em)}>
        {formatDayMonth(convite.criado_em)}
      </td>
      <td className={`${CLASSE_CELULA} text-right`}>
        {!estaVivo ? (
          // `aceite` ou `revogado`: não há nada a fazer com este convite. A
          // palavra do estado diz porquê, em vez de dois botões desactivados a
          // fazer a pergunta ("porquê?") em cada linha de uma tabela densa.
          <span className="text-muted-foreground">
            {nomeDoEstadoDoConvite(convite.estado).rotulo}
          </span>
        ) : aConfirmarRevogacao ? (
          // O segundo passo. O "Reenviar" sai de vista enquanto a pergunta está
          // no ar: dois botões lado a lado, um deles final, é como se confirma a
          // coisa errada.
          <span className="flex items-center justify-end gap-1">
            <span className="mr-1 hidden text-xs text-muted-foreground lg:inline">
              Revogar é final.
            </span>
            <Button
              type="button"
              variant="destructive"
              size="sm"
              disabled={inerte}
              aria-busy={aRevogar}
              onClick={() => {
                setAConfirmarRevogacao(false);
                aoRevogar(convite);
              }}
            >
              <Ban aria-hidden="true" />
              {aRevogar ? "A revogar…" : "Confirmar"}
              <span className="sr-only"> a revogação do convite de {convite.email}</span>
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              disabled={inerte}
              onClick={() => {
                setAConfirmarRevogacao(false);
              }}
            >
              Cancelar
              <span className="sr-only"> a revogação do convite de {convite.email}</span>
            </Button>
          </span>
        ) : (
          // O par de botões, e é sempre o par: nos dois estados em que esta
          // célula tem acções (`pendente` e `expirado`) as duas fazem efeito.
          <span className="flex items-center justify-end gap-1">
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={inerte}
              aria-busy={aReenviar}
              title="Cria um link novo e invalida o anterior"
              onClick={() => {
                aoReenviar(convite.id);
              }}
            >
              <RefreshCw aria-hidden="true" />
              {aReenviar ? "A reenviar…" : "Reenviar"}
              {/* O email no nome acessível: numa tabela de dez linhas, dez
                  botões chamados "Reenviar" são dez botões indistinguíveis
                  para quem navega por lista de controlos. */}
              <span className="sr-only"> o convite de {convite.email}</span>
            </Button>
            <Button
              type="button"
              variant="destructive"
              size="sm"
              disabled={inerte}
              title="Cancela o convite. Pede confirmação, e é final."
              onClick={() => {
                setAConfirmarRevogacao(true);
              }}
            >
              <Ban aria-hidden="true" />
              Revogar
              <span className="sr-only"> o convite de {convite.email}</span>
            </Button>
          </span>
        )}
      </td>
    </tr>
  );
}

/**
 * O estado pendente: **skeleton e não spinner** (DESIGN.md §3), e com a forma da
 * tabela que vem a seguir.
 *
 * O cabeçalho é o verdadeiro — as sete colunas já estão lá — e o que pulsa são as
 * células. É isso que faz o layout não saltar quando os dados chegarem, e é a
 * razão pela qual isto vive no mesmo ficheiro que a tabela: duas definições das
 * sete colunas divergiam na primeira coluna acrescentada.
 */
export function EsqueletoDeConvites({ linhas = 3 }: { readonly linhas?: number }) {
  return (
    <EsqueletoDeTabela
      colunas={COLUNAS}
      larguraMinima={LARGURA_MINIMA}
      rotulo="A carregar os convites…"
      linhas={linhas}
    />
  );
}
