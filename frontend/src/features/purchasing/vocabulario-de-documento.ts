import type { EstadoDaLeitura, EstadoDoDocumento, OrigemDoDocumento } from "./schemas-de-documento";
import { textos } from "./textos";

/**
 * O vocabulário do **documento**: os oito estados em palavras, e a tinta deles.
 *
 * Ao lado do `vocabulario.ts` e do `tinta-do-estado.ts` por simetria com os
 * schemas: aqueles dois falam do contrato das receções (o rascunho), este fala
 * do contrato do documento (o que existe). O que **não** muda é a regra —
 * `Map`s sobre as uniões geradas, e não objectos indexados por variável, porque
 * o `security/detect-object-injection` recusa — e bem — um `OBJETO[chave]` com
 * chave dinâmica.
 *
 * ## Os oito estados são oito ramos, e não um `default`
 *
 * O enum vem do `schema.yaml` e as funções abaixo são exaustivas por
 * construção: um valor novo no contrato deixa de ter entrada no `Map` e o
 * fallback devolve o próprio identificador — que é feio no ecrã **de propósito**,
 * porque é a forma de um estado sem palavra doer antes de chegar a um cliente.
 * Um `default` com uma frase genérica era a forma de nunca doer.
 *
 * ## A tinta: uma urgência, e cinco estados sem tinta nenhuma
 *
 * É a mesma doutrina do `tinta-do-estado.ts`, aplicada a outro enum. **Nada aqui
 * é grave:** um documento que não se conseguiu ler continua a ser um documento, e
 * a entrada de mercadoria tem sempre o caminho humano à frente (a revisão da
 * fatia 2, que é obrigatória). O que custa dinheiro é confirmar mercadoria
 * errada, e isso não acontece neste ecrã.
 *
 * Logo há **três** estados em âmbar e cinco a nada:
 *
 *  - `expirado`, `ilegivel` e `erro` são âmbar porque exigem **outra acção de
 *    uma pessoa** — abrir outro documento, fotografar melhor, ler à mão. É a
 *    definição de aviso deste produto;
 *  - `aguarda_captura`, `a_normalizar` e `a_extrair` não têm tinta porque estão
 *    a correr. O sinal deles é o **indicador de carga** (os três traços do
 *    DESIGN.md §3), que diz "está a acontecer" onde não há forma a reservar;
 *  - `lido` não tem tinta porque é o estado saudável, e um visto verde em
 *    quinze linhas esconde as três que importam;
 *  - `descartado` não tem tinta porque é uma **decisão** de alguém e não um
 *    problema a resolver — exactamente como o `skipped` de uma linha.
 *
 * E a cor nunca comunica sozinha: quem a usa põe sempre a palavra ao lado, que é
 * o que o DESIGN.md §3 manda e o que faz um estado ser legível a preto e branco.
 */

/**
 * A palavra do estado, curta o suficiente para uma célula de 44px.
 *
 * "a preparar" e não "a normalizar": normalizar é o verbo do nosso worker, não o
 * de quem está à espera de ver a fatura. "a ler" e não "a extrair", pela mesma
 * razão — extração é o nome da tarefa, ler é o que a pessoa vê a acontecer.
 */
const ESTADO_DO_DOCUMENTO = new Map<EstadoDoDocumento, string>([
  ["aguarda_captura", textos.documento.estados.aguardaCaptura],
  ["expirado", textos.documento.estados.expirado],
  ["a_normalizar", textos.documento.estados.aNormalizar],
  ["a_extrair", textos.documento.estados.aExtrair],
  ["lido", textos.documento.estados.lido],
  ["ilegivel", textos.documento.estados.ilegivel],
  ["erro", textos.documento.estados.erro],
  ["descartado", textos.documento.estados.descartado],
]);

export function rotuloDeEstadoDoDocumento(estado: EstadoDoDocumento): string {
  return ESTADO_DO_DOCUMENTO.get(estado) ?? estado;
}

/**
 * A frase do estado: o que aconteceu, e o que a pessoa faz a seguir.
 *
 * Uma por estado, e nenhuma partilhada. Foi a tentação mais forte deste ficheiro
 * — `ilegivel` e `erro` acabam os dois em "lê-se à mão" — e juntá-las apagava a
 * diferença que decide o passo seguinte: num caso a fotografia não serve (vale a
 * pena repetir), no outro o problema é nosso (repetir não muda nada).
 */
const FRASE_DO_ESTADO = new Map<EstadoDoDocumento, string>([
  ["aguarda_captura", textos.documento.frases.aguardaCaptura],
  ["expirado", textos.documento.frases.expirado],
  ["a_normalizar", textos.documento.frases.aNormalizar],
  ["a_extrair", textos.documento.frases.aExtrair],
  ["lido", textos.documento.frases.lido],
  ["ilegivel", textos.documento.frases.ilegivel],
  ["erro", textos.documento.frases.erro],
  ["descartado", textos.documento.frases.descartado],
]);

export function fraseDeEstadoDoDocumento(estado: EstadoDoDocumento): string {
  return FRASE_DO_ESTADO.get(estado) ?? "";
}

/** Os três estados que pedem outra acção de uma pessoa. */
const COM_AVISO = new Set<EstadoDoDocumento>(["expirado", "ilegivel", "erro"]);

/** Primeiro papel do DESIGN.md §2: a cor de estado como **cor de texto**. */
export function tintaDoTextoDoDocumento(estado: EstadoDoDocumento): string {
  return COM_AVISO.has(estado) ? "text-warning" : "";
}

/** O trilho de 4px é preenchimento sem nada por cima: não leva frente. */
export function tintaDoTrilhoDoDocumento(estado: EstadoDoDocumento): string {
  return COM_AVISO.has(estado) ? "bg-warning" : "";
}

/**
 * `true` nos estados em que há trabalho a decorrer do lado do servidor.
 *
 * É o predicado que decide se o **indicador** aparece — e é a razão de
 * `aguarda_captura` estar aqui apesar de o `api-de-documentos.ts` não o sondar:
 * do ponto de vista de quem olha, um slot aberto está à espera de uma página, e
 * isso é "está a acontecer". O que não há é nada a sondar enquanto a página vem
 * deste mesmo ecrã.
 */
export function estaAAcontecer(estado: EstadoDoDocumento): boolean {
  return estado === "aguarda_captura" || estado === "a_normalizar" || estado === "a_extrair";
}

/**
 * De onde vieram os bytes, em palavra.
 *
 * Aparece na lista porque responde a uma pergunta que o dono vai fazer — "este
 * entrou pelo computador ou pelo telemóvel?" — e porque a origem é **derivada**
 * pelo servidor, logo é informação e não uma escolha de quem enviou.
 */
const ORIGEM = new Map<OrigemDoDocumento, string>([
  ["upload", textos.documento.origens.upload],
  ["capture", textos.documento.origens.capture],
]);

export function rotuloDeOrigem(origem: OrigemDoDocumento): string {
  return ORIGEM.get(origem) ?? origem;
}

/**
 * O estado da leitura, em palavra. Quatro, e não oito: a leitura é uma tentativa
 * do modelo e não o documento.
 */
const ESTADO_DA_LEITURA = new Map<EstadoDaLeitura, string>([
  ["pendente", textos.documento.leitura.pendente],
  // As três últimas partilham a palavra com o estado do documento de propósito:
  // é a mesma coisa dita do grão da tentativa em vez do grão do documento, e
  // duas palavras para ela divergiriam na primeira correcção feita só numa.
  ["lido", textos.documento.estados.lido],
  ["ilegivel", textos.documento.estados.ilegivel],
  ["erro", textos.documento.estados.erro],
]);

export function rotuloDeEstadoDaLeitura(estado: EstadoDaLeitura): string {
  return ESTADO_DA_LEITURA.get(estado) ?? estado;
}
