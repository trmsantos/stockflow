import {
  linhaDeRececaoSchema,
  rececaoSchema,
  resumoDeRececoesSchema,
  revisaoDeLinhaSchema,
  temperaturaSchema,
  type Conservacao,
  type EspecieDeLinha,
  type EstadoDeLinha,
  type HistoricoDePreco,
  type LinhaDeRececao,
  type Localizacao,
  type Rececao,
  type TipoDeDocumento,
  type TipoValidade,
  type TotalDeIva,
} from "../src/features/purchasing/schemas.ts";
import { paginated } from "../src/lib/api/pagination.ts";
import { AUTORES, dataEmDias, diasAte, horaDeHoje, horaDeOntem } from "./aurora.ts";
import {
  centimosDe,
  decimilesimosDe,
  milesimosDe,
  stringDeCentimos,
  stringDeMilesimos,
} from "./decimal.ts";
import {
  INICIO_DO_DIA,
  LOTES,
  acrescentar,
  artigoDe,
  inicioDoDiaDeNegocio,
  ledger,
  localizacaoDe,
  loteDe,
  quantidade,
  registarLote,
  type Loja,
} from "./ledger.ts";
import { resposta, type Contexto, type Rota } from "./servidor.ts";

/**
 * dados-falsos-stockflow — o recurso `receipts` do módulo `purchasing`: a
 * entrada de mercadoria.
 *
 * Este ficheiro existe para encarnar **uma** regra, e tudo nele se explica por
 * ela: "toda a extração de fatura passa por revisão humana antes de gerar
 * movimentos" (CLAUDE.md). Logo uma receção é um **rascunho** e não toca no
 * ledger até alguém a confirmar — e isso aqui não é uma convenção de UI, é a
 * forma do estado: as receções vivem numa lista própria, as linhas guardam o
 * que o documento diz, e a única função que escreve no ledger é a
 * `confirmarRececao`. Antes dela, o nível do artigo no ecrã de Stock não muda;
 * depois dela, muda. É medível com dois `curl`, e foi medido.
 *
 * As receções **já confirmadas** não guardam quantidade nenhuma: lêem-na do
 * movimento que criaram (`movimentoDaLinha`). É isso que as torna vistas do
 * mesmo ledger em vez de um estado paralelo — e um seed que divirja do ledger
 * rebenta alto no arranque, em vez de passar por bom (ver `resolverMovimentos`).
 *
 * O que o guião §2 marca como prática portuguesa está na **forma dos dados**, e
 * não em texto de ecrã:
 *  - nenhuma receção referencia uma encomenda, porque não há encomendas: a do
 *    Makro é uma ida de carrinha com fatura simplificada, e a parcial
 *    representa-se como divergência entre o faturado e o recebido;
 *  - a guia de remessa dos lácteos entra **sem fatura** e sem preços
 *    (`awaiting_invoice`), porque a fatura vem a fim de mês;
 *  - o IVA está em cada linha e nunca no artigo;
 *  - o vasilhame é linha com valor e sem stock;
 *  - o queijo e o fiambre vêm pesados peça a peça.
 *
 * Apagabilidade: no dia em que o Django servir `/api/v1/receipts`, apaga-se
 * este ficheiro e a sua linha no `servidor.ts`.
 */

/**
 * O NIF da Pastelaria Aurora, e o do sócio.
 *
 * Os dois existem por causa da Q10: a fatura simplificada do Makro foi emitida
 * ao **NIF pessoal do sócio**, porque é o que acontece quando se vai ao cash &
 * carry e se dá o número que se sabe de cor. O ecrã extrai isso num badge
 * discreto — ninguém oferece esta informação em abstracto, e um badge põe-na à
 * frente dele em dois segundos.
 *
 * São números fictícios com a forma certa (nove dígitos; `5` de pessoa
 * coletiva, `2` de pessoa singular) e nada mais: não são NIFs válidos nem
 * pertencem a ninguém.
 */
const NIF_DA_EMPRESA = "509123456";
const NOME_DA_EMPRESA = "Pastelaria Aurora, Lda";
const NIF_DO_SOCIO = "234567891";
const NOME_DO_SOCIO = "Sofia M. Aurora";

/** Acima disto, a variação de preço de uma linha aparece no ecrã. */
const LIMIAR_DE_PRECO_EM_PONTOS = 10;

interface LinhaFalsa {
  readonly id: string;
  /** O `n` do artigo em `aurora.ts`. `null` = a fatura traz o que o catálogo não tem. */
  readonly artigo: number | null;
  /** A descrição **como vem na fatura**, em maiúsculas como os sistemas a imprimem. */
  readonly descricao: string;
  readonly loja: Loja;
  readonly especie: EspecieDeLinha;
  readonly conservacao: Conservacao;
  /** O substantivo da unidade impressa: "caixa", "bloco", "kg", "un". */
  readonly unidade: string;
  /** O nome da embalagem do catálogo a que a linha foi associada, se houver. */
  readonly embalagem: string | null;
  /** Quantas unidades base vale **uma** unidade de fatura. */
  readonly basePorUnidade: number;
  readonly faturada: string;
  /** O que entrou. `null` = o mesmo que foi faturado. */
  readonly recebida: string | null;
  readonly precoUnitario: string | null;
  /** A taxa como vem na linha, em fração. `null` = a linha não traz taxa. */
  readonly iva: string | null;
  readonly pesoVariavel: boolean;
  /** O lote, enquanto não há movimento que o diga. */
  lote: string | null;
  /** A validade escrita por quem recebeu, em dias relativos a hoje. */
  validadeEmDias: number | null;
  estado: EstadoDeLinha;
  autor: string | null;
  quando: string | null;
  /** O movimento que esta linha criou no ledger. */
  movimento: string | null;
}

interface RececaoFalsa {
  readonly id: string;
  readonly fornecedor: string;
  readonly nifDoFornecedor: string | null;
  readonly tipo: TipoDeDocumento;
  readonly numero: string | null;
  /** A referência com que os movimentos desta receção vivem no ledger. */
  readonly referencia: string;
  readonly recebida: string;
  /** O adquirente impresso no documento. */
  readonly nomeDoAdquirente: string;
  readonly nifDoAdquirente: string;
  /** Entrou por guia e a fatura vem a fim de mês. */
  readonly aguardaFatura: boolean;
  /** O total impresso, quando **não** é a soma das linhas. */
  readonly totalImpresso: string | null;
  readonly linhas: readonly LinhaFalsa[];
  temperatura: string | null;
  confirmada: string | null;
  autorDaConfirmacao: string | null;
}

function idDeRececao(n: number): string {
  return `d0c50000-0000-4000-8000-${String(n).padStart(12, "0")}`;
}

function idDeLinha(rececao: number, linha: number): string {
  const sufixo = `${String(rececao).padStart(6, "0")}${String(linha).padStart(6, "0")}`;
  return `d1a50000-0000-4000-8000-${sufixo}`;
}

interface Semente {
  readonly artigo: number | null;
  readonly descricao: string;
  readonly loja: Loja;
  readonly unidade: string;
  readonly embalagem?: string;
  readonly basePorUnidade: number;
  readonly faturada: string;
  readonly recebida?: string;
  readonly preco?: string;
  readonly iva?: string;
  readonly especie?: EspecieDeLinha;
  readonly conservacao?: Conservacao;
  readonly pesoVariavel?: boolean;
  readonly lote?: string;
  readonly validadeEmDias?: number;
  readonly estado?: EstadoDeLinha;
  readonly revisor?: string;
  readonly revista?: string;
}

function linha(rececao: number, posicao: number, semente: Semente): LinhaFalsa {
  return {
    id: idDeLinha(rececao, posicao),
    artigo: semente.artigo,
    descricao: semente.descricao,
    loja: semente.loja,
    especie: semente.especie ?? "goods",
    conservacao: semente.conservacao ?? "ambient",
    unidade: semente.unidade,
    embalagem: semente.embalagem ?? null,
    basePorUnidade: semente.basePorUnidade,
    faturada: semente.faturada,
    recebida: semente.recebida ?? null,
    precoUnitario: semente.preco ?? null,
    iva: semente.iva ?? null,
    pesoVariavel: semente.pesoVariavel ?? false,
    lote: semente.lote ?? null,
    validadeEmDias: semente.validadeEmDias ?? null,
    estado: semente.estado ?? "confirmed",
    autor: semente.revisor ?? null,
    quando: semente.revista ?? null,
    movimento: null,
  };
}

// ---------------------------------------------------------------------------
// O seed. Sete documentos, e cada um está aqui por uma razão nomeada no guião.
// ---------------------------------------------------------------------------

/**
 * **O rascunho** — a receção que precisa de revisão, e o ecrã que interessa.
 *
 * Cinco linhas, duas por rever: a manteiga, que chegou **21 % mais cara do
 * que nas últimas compras** e ainda não tem lote nem validade escritos, e um
 * artigo que a fatura traz e o catálogo não tem. As outras três já foram
 * revistas pela gerência às 07:5x, e é por isso que o badge da lista diz "2
 * linhas" e não "5": conta o que falta, não o que existe.
 *
 * O total impresso (204,40 €) **não bate** com a soma das linhas (201,90 €) —
 * falta um desconto ou portes que não foram lidos. O ecrã avisa e deixa
 * confirmar: bloquear é a Q1, e o shell não responde por ela.
 *
 * Traz congelados e refrigerados, logo pede temperatura à entrega. O campo está
 * vazio de propósito.
 */
const RASCUNHO: RececaoFalsa = {
  id: idDeRececao(1),
  fornecedor: "Alimentar Norte, Lda",
  nifDoFornecedor: "503214789",
  tipo: "FT",
  numero: "FT 2026/4531",
  referencia: "FT 2026/4531",
  recebida: horaDeHoje(7, 45),
  nomeDoAdquirente: NOME_DA_EMPRESA,
  nifDoAdquirente: NIF_DA_EMPRESA,
  aguardaFatura: false,
  totalImpresso: "204.40",
  temperatura: null,
  confirmada: null,
  autorDaConfirmacao: null,
  linhas: [
    linha(1, 0, {
      artigo: 5,
      descricao: "MANTEIGA S/ SAL 82% BLOCO 2,5KG",
      loja: "cozinha",
      // Faturada ao quilo, que é como o dono pensa manteiga e como esta linha
      // vem impressa. A embalagem (bloco de 2,5 kg) está na descrição, e a
      // conversão que o ecrã mostra é a do quilo para o grama do ledger.
      unidade: "kg",
      basePorUnidade: 1000,
      faturada: "5.000",
      preco: "9.40",
      iva: "0.060",
      conservacao: "chilled",
      estado: "needs_review",
    }),
    linha(1, 1, {
      artigo: 21,
      descricao: "BACALHAU LOMBOS ULTRACONGELADOS CX 5KG",
      loja: "cozinha",
      unidade: "caixa",
      embalagem: "caixa 5 kg",
      basePorUnidade: 5000,
      faturada: "1",
      preco: "60.50",
      iva: "0.060",
      conservacao: "frozen",
      lote: "L-BAC-1002",
      validadeEmDias: 300,
      revisor: AUTORES.dono,
      revista: horaDeHoje(7, 52),
    }),
    linha(1, 2, {
      artigo: 10,
      descricao: "CHOCOLATE COBERTURA 54% SACO 5KG",
      loja: "cozinha",
      unidade: "saco",
      embalagem: "saco 5 kg",
      basePorUnidade: 5000,
      faturada: "1",
      preco: "44.50",
      iva: "0.230",
      revisor: AUTORES.dono,
      revista: horaDeHoje(7, 53),
    }),
    linha(1, 3, {
      artigo: 19,
      descricao: "CX CARTAO BOLO 28CM PCT 50UN",
      loja: "cozinha",
      unidade: "pacote",
      embalagem: "pacote 50 un",
      basePorUnidade: 50,
      faturada: "2",
      preco: "7.90",
      iva: "0.230",
      revisor: AUTORES.dono,
      revista: horaDeHoje(7, 54),
    }),
    linha(1, 4, {
      // O artigo novo na fatura (guião §2). Sem artigo não há conversão nem
      // movimento possível, e o ecrã não inventa nenhum dos dois.
      artigo: null,
      descricao: "PAPEL VEGETAL 40x60 PCT 500 FL",
      loja: "cozinha",
      unidade: "pacote",
      basePorUnidade: 1,
      faturada: "1",
      preco: "11.20",
      iva: "0.230",
      estado: "needs_review",
    }),
  ],
};

/**
 * A **nota de crédito** das duas grades vazias devolvidas (guião §2).
 *
 * Confirmada, e **não gerou movimento nenhum**: vasilhame retornável é linha de
 * fatura com valor e não é stock consumível. É o caso que mostra que confirmar
 * um documento não é o mesmo que dar entrada de mercadoria — e é por isso que
 * está no seed em vez de num comentário.
 *
 * Os valores são negativos porque uma nota de crédito credita.
 */
const NOTA_DE_CREDITO: RececaoFalsa = {
  id: idDeRececao(2),
  fornecedor: "Makro",
  nifDoFornecedor: null,
  tipo: "NC",
  numero: "NC 2026/115 002",
  referencia: "NC 2026/115002",
  recebida: horaDeHoje(9, 20),
  nomeDoAdquirente: NOME_DO_SOCIO,
  nifDoAdquirente: NIF_DO_SOCIO,
  aguardaFatura: false,
  totalImpresso: null,
  temperatura: null,
  confirmada: horaDeHoje(9, 25),
  autorDaConfirmacao: AUTORES.dono,
  linhas: [
    linha(2, 0, {
      artigo: null,
      descricao: "TARA GRADE 24 RETORNAVEL - DEVOLUCAO",
      loja: "centro",
      especie: "deposit",
      unidade: "grade",
      basePorUnidade: 1,
      faturada: "2",
      preco: "-4.80",
      revisor: AUTORES.dono,
      revista: horaDeHoje(9, 25),
    }),
  ],
};

/**
 * A **fatura manuscrita** da frutaria (guião §2): sem número, escrita à mão no
 * mercado às sete da manhã. Entrou hoje e foi confirmada hoje.
 */
const MANUSCRITA: RececaoFalsa = {
  id: idDeRececao(3),
  fornecedor: "Frutaria do Mercado",
  nifDoFornecedor: "212345678",
  tipo: "FS",
  // Sem número: é manuscrita. O ecrã diz "sem número" em vez de um espaço em
  // branco, e a referência do ledger é a que o movimento já tem.
  numero: null,
  referencia: "Fatura manuscrita",
  recebida: horaDeHoje(7, 5),
  nomeDoAdquirente: NOME_DA_EMPRESA,
  nifDoAdquirente: NIF_DA_EMPRESA,
  aguardaFatura: false,
  totalImpresso: null,
  temperatura: "6.0",
  confirmada: horaDeHoje(7, 10),
  autorDaConfirmacao: AUTORES.rui,
  linhas: [
    linha(3, 0, {
      artigo: 12,
      descricao: "MORANGO NACIONAL CX 2KG",
      loja: "cozinha",
      unidade: "caixa",
      embalagem: "caixa 2 kg (8×250 g)",
      basePorUnidade: 2000,
      faturada: "1",
      preco: "11.00",
      iva: "0.060",
      conservacao: "chilled",
      revisor: AUTORES.rui,
      revista: horaDeHoje(7, 10),
    }),
  ],
};

/**
 * A **receção parcial** (guião §2): cinco rolos faturados, três entregues.
 *
 * É assim que uma parcial se representa **sem encomenda**: a divergência é
 * entre o documento e a prateleira, não entre uma encomenda e a entrega. A
 * fatura cobra os cinco — e é essa a conversa que esta linha abre.
 *
 * Chegou ontem e só foi confirmada hoje de manhã, precisamente porque alguém
 * teve de ir confirmar que só vieram três.
 */
const CONGELADOS: RececaoFalsa = {
  id: idDeRececao(4),
  fornecedor: "Congelados Atlântico",
  nifDoFornecedor: "505472310",
  tipo: "FT",
  numero: "FT 2026/4502",
  referencia: "FT 2026/4502",
  recebida: horaDeOntem(8, 40),
  nomeDoAdquirente: NOME_DA_EMPRESA,
  nifDoAdquirente: NIF_DA_EMPRESA,
  aguardaFatura: false,
  totalImpresso: null,
  temperatura: "-19.0",
  confirmada: horaDeHoje(8, 20),
  autorDaConfirmacao: AUTORES.dono,
  linhas: [
    linha(4, 0, {
      artigo: 9,
      descricao: "MASSA FOLHADA ROLO 2KG",
      loja: "cozinha",
      unidade: "rolo",
      embalagem: "rolo 2 kg",
      basePorUnidade: 2000,
      faturada: "5",
      recebida: "3",
      preco: "8.20",
      iva: "0.230",
      conservacao: "frozen",
      revisor: AUTORES.dono,
      revista: horaDeHoje(8, 20),
    }),
    linha(4, 1, {
      artigo: 11,
      descricao: "AMENDOA LAMINADA SC 1KG",
      loja: "cozinha",
      unidade: "saco",
      embalagem: "saco 1 kg",
      basePorUnidade: 1000,
      faturada: "2",
      preco: "13.50",
      iva: "0.230",
      revisor: AUTORES.dono,
      revista: horaDeHoje(8, 20),
    }),
    linha(4, 2, {
      artigo: 10,
      descricao: "CHOCOLATE COBERTURA 54% SC 5KG",
      loja: "cozinha",
      unidade: "saco",
      embalagem: "saco 5 kg",
      basePorUnidade: 5000,
      faturada: "1",
      preco: "44.50",
      iva: "0.230",
      revisor: AUTORES.dono,
      revista: horaDeHoje(8, 20),
    }),
  ],
};

/**
 * A **guia de remessa sem fatura** (guião §2, prática 2): os lácteos entram
 * antes de existir fatura, e a fatura de fim de mês reconcilia N entregas.
 *
 * Não traz preços nenhuns — nem preço unitário, nem IVA, nem total. É o caso
 * que obriga os três campos a serem anuláveis no contrato, e não um caso
 * excepcional: é o normal de quem compra a distribuidores.
 */
const GUIA: RececaoFalsa = {
  id: idDeRececao(5),
  fornecedor: "Lacticínios da Serra",
  nifDoFornecedor: "501998742",
  tipo: "GR",
  numero: "Guia 4471",
  referencia: "Guia 4471",
  recebida: horaDeOntem(8, 5),
  nomeDoAdquirente: NOME_DA_EMPRESA,
  nifDoAdquirente: NIF_DA_EMPRESA,
  aguardaFatura: true,
  totalImpresso: null,
  temperatura: "5.0",
  confirmada: horaDeOntem(8, 10),
  autorDaConfirmacao: AUTORES.rui,
  linhas: [
    linha(5, 0, {
      artigo: 6,
      descricao: "NATA UHT 35% M/G CX 12x1L",
      loja: "cozinha",
      unidade: "caixa",
      embalagem: "caixa 12×1 L",
      basePorUnidade: 12000,
      faturada: "1",
      conservacao: "chilled",
      revisor: AUTORES.rui,
      revista: horaDeOntem(8, 10),
    }),
    linha(5, 1, {
      artigo: 7,
      descricao: "LEITE UHT M/G CX 12x1L",
      loja: "cozinha",
      unidade: "caixa",
      embalagem: "caixa 12×1 L",
      basePorUnidade: 12000,
      faturada: "2",
      revisor: AUTORES.rui,
      revista: horaDeOntem(8, 10),
    }),
  ],
};

/**
 * A **ida ao Makro** (guião §2, prática 1 e Q10): fatura simplificada, sem
 * encomenda e sem guia, a mercadoria trazida na carrinha — e emitida ao **NIF
 * pessoal do sócio**.
 *
 * Tem quase tudo o que o guião pede num documento só: duas bolas de queijo
 * **pesadas uma a uma** e uma peça de fiambre ao quilo (peso variável), uma
 * linha de **vasilhame** ao lado das grades de água, o artigo que ninguém vai
 * contar, e mercadoria que ficou em **duas lojas diferentes** na mesma viagem —
 * é daí que vem o stock repartido da Q2.
 */
const MAKRO: RececaoFalsa = {
  id: idDeRececao(6),
  fornecedor: "Makro",
  nifDoFornecedor: null,
  tipo: "FS",
  numero: "FS 2026/114 570",
  referencia: "FS 2026/114570",
  recebida: horaDeOntem(9, 10),
  nomeDoAdquirente: NOME_DO_SOCIO,
  nifDoAdquirente: NIF_DO_SOCIO,
  aguardaFatura: false,
  totalImpresso: null,
  temperatura: "7.0",
  confirmada: horaDeOntem(9, 30),
  autorDaConfirmacao: AUTORES.dono,
  linhas: [
    linha(6, 0, {
      artigo: 8,
      descricao: "CAFE GRAO SUPERIOR BLEND 1KG",
      loja: "centro",
      unidade: "kg",
      basePorUnidade: 1000,
      faturada: "4",
      preco: "18.00",
      iva: "0.230",
      revisor: AUTORES.ana,
      revista: horaDeOntem(9, 30),
    }),
    linha(6, 1, {
      artigo: 14,
      descricao: "QUEIJO FLAMENGO BOLA (PESO VARIAVEL)",
      loja: "centro",
      unidade: "kg",
      basePorUnidade: 1000,
      faturada: "3.480",
      preco: "7.90",
      iva: "0.060",
      conservacao: "chilled",
      pesoVariavel: true,
      revisor: AUTORES.ana,
      revista: horaDeOntem(9, 30),
    }),
    linha(6, 2, {
      // A segunda bola, pesada à parte e ficou na outra loja. Duas linhas do
      // mesmo artigo na mesma fatura: é o que peso variável quer dizer.
      artigo: 14,
      descricao: "QUEIJO FLAMENGO BOLA (PESO VARIAVEL)",
      loja: "mercado",
      unidade: "kg",
      basePorUnidade: 1000,
      faturada: "2.960",
      preco: "7.90",
      iva: "0.060",
      conservacao: "chilled",
      pesoVariavel: true,
      revisor: AUTORES.dono,
      revista: horaDeOntem(9, 30),
    }),
    linha(6, 3, {
      artigo: 15,
      descricao: "FIAMBRE PERNA EXTRA PECA (PESO VARIAVEL)",
      loja: "centro",
      unidade: "kg",
      basePorUnidade: 1000,
      faturada: "4.120",
      preco: "9.20",
      iva: "0.230",
      conservacao: "chilled",
      pesoVariavel: true,
      revisor: AUTORES.ana,
      revista: horaDeOntem(9, 30),
    }),
    linha(6, 4, {
      artigo: 16,
      descricao: "RISSOIS DE CARNE CX 100UN",
      loja: "centro",
      unidade: "caixa",
      embalagem: "caixa 100 un",
      basePorUnidade: 100,
      faturada: "2",
      preco: "18.00",
      iva: "0.230",
      conservacao: "frozen",
      revisor: AUTORES.ana,
      revista: horaDeOntem(9, 30),
    }),
    linha(6, 5, {
      artigo: 17,
      descricao: "OLEO ALIMENTAR FRITAR GARRAFAO 5L",
      loja: "cozinha",
      unidade: "garrafão",
      embalagem: "garrafão 5 L",
      basePorUnidade: 5000,
      faturada: "2",
      preco: "9.50",
      iva: "0.230",
      revisor: AUTORES.ana,
      revista: horaDeOntem(9, 30),
    }),
    linha(6, 6, {
      artigo: 18,
      descricao: "AGUA 0,33L VIDRO GRADE 24UN",
      loja: "centro",
      unidade: "grade",
      embalagem: "grade 24 un",
      basePorUnidade: 24,
      faturada: "4",
      preco: "5.76",
      iva: "0.230",
      revisor: AUTORES.ana,
      revista: horaDeOntem(9, 30),
    }),
    linha(6, 7, {
      // A tara das quatro grades: valor sim, stock não (guião §2, prática 5).
      artigo: null,
      descricao: "TARA GRADE 24 RETORNAVEL",
      loja: "centro",
      especie: "deposit",
      unidade: "grade",
      basePorUnidade: 1,
      faturada: "4",
      preco: "4.80",
      revisor: AUTORES.ana,
      revista: horaDeOntem(9, 30),
    }),
    linha(6, 8, {
      // No Makro foram à unidade; o distribuidor vende ao pacote de 50. É o
      // mesmo artigo comprado em duas embalagens, que é o caso do açúcar no
      // guião §2 a aparecer onde ninguém o encomendou.
      artigo: 19,
      descricao: "CX CARTAO BOLO 28CM",
      loja: "centro",
      unidade: "un",
      basePorUnidade: 1,
      faturada: "60",
      preco: "0.16",
      iva: "0.230",
      revisor: AUTORES.ana,
      revista: horaDeOntem(9, 30),
    }),
    linha(6, 9, {
      artigo: 20,
      descricao: "SAQUETA ACUCAR 8G CX 1000UN",
      loja: "centro",
      unidade: "caixa",
      embalagem: "caixa 1 000 un",
      basePorUnidade: 1000,
      faturada: "1",
      preco: "12.00",
      iva: "0.230",
      revisor: AUTORES.ana,
      revista: horaDeOntem(9, 30),
    }),
    linha(6, 10, {
      artigo: 21,
      descricao: "BACALHAU LOMBOS ULTRACONG. CX 5KG",
      loja: "centro",
      unidade: "caixa",
      embalagem: "caixa 5 kg",
      basePorUnidade: 5000,
      faturada: "1",
      preco: "60.50",
      iva: "0.060",
      conservacao: "frozen",
      revisor: AUTORES.ana,
      revista: horaDeOntem(9, 30),
    }),
  ],
};

/**
 * A fatura do distribuidor de ontem de manhã. Está aqui por duas razões: é de
 * onde sai o **histórico de preço** da manteiga (7,80 €/kg, contra os 9,40 € do
 * rascunho), e é a única receção confirmada **sem** temperatura registada — num
 * ecrã onde as outras a têm, um campo vazio é mais perguntável do que um campo
 * que não existe.
 */
const DISTRIBUIDOR: RececaoFalsa = {
  id: idDeRececao(7),
  fornecedor: "Alimentar Norte, Lda",
  nifDoFornecedor: "503214789",
  tipo: "FT",
  numero: "FT 2026/4471",
  referencia: "FT 2026/4471",
  recebida: horaDeOntem(7, 20),
  nomeDoAdquirente: NOME_DA_EMPRESA,
  nifDoAdquirente: NIF_DA_EMPRESA,
  aguardaFatura: false,
  totalImpresso: null,
  temperatura: null,
  confirmada: horaDeOntem(7, 30),
  autorDaConfirmacao: AUTORES.rui,
  linhas: [
    linha(7, 0, {
      artigo: 1,
      descricao: "FARINHA T65 SACO 25KG",
      loja: "cozinha",
      unidade: "saco",
      embalagem: "saco 25 kg",
      basePorUnidade: 25000,
      faturada: "2",
      preco: "17.50",
      iva: "0.060",
      revisor: AUTORES.rui,
      revista: horaDeOntem(7, 30),
    }),
    linha(7, 1, {
      artigo: 2,
      descricao: "ACUCAR BRANCO GRANULADO SC 25KG",
      loja: "cozinha",
      unidade: "saco",
      embalagem: "saco 25 kg",
      basePorUnidade: 25000,
      faturada: "1",
      preco: "22.50",
      iva: "0.230",
      revisor: AUTORES.rui,
      revista: horaDeOntem(7, 30),
    }),
    linha(7, 2, {
      artigo: 3,
      descricao: "OVO LIQUIDO PASTEURIZADO CX 6x1KG",
      loja: "cozinha",
      unidade: "caixa",
      embalagem: "caixa 6×1 kg",
      basePorUnidade: 6000,
      faturada: "1",
      preco: "19.20",
      iva: "0.060",
      conservacao: "chilled",
      revisor: AUTORES.rui,
      revista: horaDeOntem(7, 30),
    }),
    linha(7, 3, {
      artigo: 4,
      descricao: "OVOS FRESCOS CLASSE M PLATEAU 30UN",
      loja: "cozinha",
      unidade: "plateau",
      embalagem: "plateau 30 un",
      basePorUnidade: 30,
      faturada: "6",
      preco: "6.30",
      iva: "0.060",
      revisor: AUTORES.rui,
      revista: horaDeOntem(7, 30),
    }),
    linha(7, 4, {
      artigo: 5,
      descricao: "MANTEIGA S/ SAL 82% BLOCO 2,5KG",
      loja: "cozinha",
      unidade: "kg",
      basePorUnidade: 1000,
      faturada: "7.500",
      preco: "7.80",
      iva: "0.060",
      conservacao: "chilled",
      revisor: AUTORES.rui,
      revista: horaDeOntem(7, 30),
    }),
    linha(7, 5, {
      artigo: 13,
      descricao: "FERMENTO FRESCO PADEIRO BLOCO 500G",
      loja: "cozinha",
      unidade: "bloco",
      embalagem: "bloco 500 g",
      basePorUnidade: 500,
      faturada: "2",
      preco: "2.15",
      iva: "0.060",
      conservacao: "chilled",
      revisor: AUTORES.rui,
      revista: horaDeOntem(7, 30),
    }),
  ],
};

const rececoes: RececaoFalsa[] = [
  RASCUNHO,
  NOTA_DE_CREDITO,
  MANUSCRITA,
  CONGELADOS,
  GUIA,
  MAKRO,
  DISTRIBUIDOR,
];

// ---------------------------------------------------------------------------
// Derivação. Tudo o que o ecrã vê sai destas funções.
// ---------------------------------------------------------------------------

function recebidaDe(linhaFalsa: LinhaFalsa): string {
  return linhaFalsa.recebida ?? linhaFalsa.faturada;
}

/** O que esta linha vale na unidade base, em milésimos. */
function milesimosDaLinha(linhaFalsa: LinhaFalsa): number {
  return milesimosDe(recebidaDe(linhaFalsa)) * linhaFalsa.basePorUnidade;
}

function movimentoDoId(id: string) {
  return ledger().find((mov) => mov.id === id);
}

/**
 * O lote desta linha: o do **movimento** quando já há movimento, e o que está
 * escrito na linha enquanto não há.
 *
 * A ordem importa: depois de confirmada, a verdade do lote é a do ledger, e
 * ler primeiro a linha deixaria as duas divergirem em silêncio.
 */
function codigoDoLote(linhaFalsa: LinhaFalsa): string | null {
  const mov = linhaFalsa.movimento === null ? undefined : movimentoDoId(linhaFalsa.movimento);
  return mov?.lote ?? linhaFalsa.lote;
}

/**
 * Se este artigo exige lote, e qual dos dois rótulos de validade usa — as duas
 * coisas **derivadas dos lotes do seed**, que é onde o domínio já as afirmou.
 *
 * Em produção são campos do artigo (`track_lots`, e o rótulo da validade);
 * aqui derivam-se para não haver uma segunda lista a dizer o contrário do que o
 * ledger já diz. Um artigo sem lotes no seed é um artigo que não os exige — é o
 * caso do açúcar, do café e das caixas de cartão.
 */
function exigeLote(artigo: number | null): boolean {
  return artigo !== null && LOTES.some((lote) => lote.artigo === artigo);
}

function tipoDeValidadeDoArtigo(artigo: number | null): TipoValidade | null {
  if (artigo === null) return null;
  return LOTES.find((lote) => lote.artigo === artigo)?.tipo ?? null;
}

/** A validade da linha, em dias relativos a hoje. `null` = por preencher. */
function diasDeValidade(linhaFalsa: LinhaFalsa): number | null {
  const codigo = codigoDoLote(linhaFalsa);
  if (codigo === null) return linhaFalsa.validadeEmDias;
  return loteDe(codigo)?.dias ?? linhaFalsa.validadeEmDias;
}

/** O total da linha, em cêntimos: a fatura cobra o que **faturou**. */
function centimosDaLinha(linhaFalsa: LinhaFalsa): number | null {
  if (linhaFalsa.precoUnitario === null) return null;
  return centimosDe(
    milesimosDe(linhaFalsa.faturada),
    decimilesimosDe(linhaFalsa.precoUnitario),
  );
}

/**
 * O preço desta linha contra o da última compra do mesmo artigo noutro
 * documento **já confirmado**.
 *
 * Só compara o que é comparável: mesmo artigo e mesma unidade de compra. Um
 * preço por caixa contra um preço por quilo dá uma percentagem que não quer
 * dizer nada, e um aviso que não quer dizer nada é pior do que nenhum. Só
 * devolve algo acima do limiar — é o servidor que decide o que é um desvio,
 * como decide o que é "baixo" no ecrã de Stock.
 */
function historicoDePreco(
  rececao: RececaoFalsa,
  linhaFalsa: LinhaFalsa,
): HistoricoDePreco | null {
  if (linhaFalsa.precoUnitario === null || linhaFalsa.artigo === null) return null;

  const anteriores = rececoes
    .filter((outra) => outra.id !== rececao.id && outra.confirmada !== null)
    .filter((outra) => outra.recebida < rececao.recebida)
    .sort((a, b) => b.recebida.localeCompare(a.recebida));

  for (const outra of anteriores) {
    const igual = outra.linhas.find(
      (candidata) =>
        candidata.artigo === linhaFalsa.artigo &&
        candidata.basePorUnidade === linhaFalsa.basePorUnidade &&
        candidata.precoUnitario !== null,
    );
    if (igual?.precoUnitario === undefined || igual.precoUnitario === null) continue;

    const antes = decimilesimosDe(igual.precoUnitario);
    const agora = decimilesimosDe(linhaFalsa.precoUnitario);
    if (antes <= 0) return null;

    // Pontos percentuais inteiros, por aritmética de inteiros: uma variação de
    // preço com casas decimais convida a discutir a casa decimal.
    const pontos = Math.round(((agora - antes) * 100) / antes);
    if (Math.abs(pontos) < LIMIAR_DE_PRECO_EM_PONTOS) return null;

    return {
      last_price: igual.precoUnitario,
      unit_label: igual.embalagem ?? igual.unidade,
      change_pct: pontos,
      reference: outra.numero ?? outra.referencia,
      threshold_pct: LIMIAR_DE_PRECO_EM_PONTOS,
    };
  }

  return null;
}

function serializarLinha(rececao: RececaoFalsa, linhaFalsa: LinhaFalsa, posicao: number): LinhaDeRececao {
  const artigo = linhaFalsa.artigo === null ? undefined : artigoDe(linhaFalsa.artigo);
  const dias = diasDeValidade(linhaFalsa);
  const mov = linhaFalsa.movimento === null ? undefined : movimentoDoId(linhaFalsa.movimento);

  // A quantidade de stock é a do **movimento** quando já houve confirmação, e a
  // previsão do que vai entrar enquanto não houve. Uma linha que não é
  // mercadoria, ou que não tem artigo, não tem quantidade nenhuma — e `null`
  // aqui é ausência real, não zero.
  const milesimos = mov === undefined ? milesimosDaLinha(linhaFalsa) : mov.milesimos;
  const stock =
    artigo === undefined || linhaFalsa.especie !== "goods"
      ? null
      : quantidade(artigo, milesimos);

  const centimos = centimosDaLinha(linhaFalsa);

  return {
    id: linhaFalsa.id,
    position: posicao,
    description: linhaFalsa.descricao,
    product: artigo?.id ?? null,
    product_name: artigo?.nomeCurto ?? null,
    kind: linhaFalsa.especie,
    status: linhaFalsa.estado,
    conservation: linhaFalsa.conservacao,
    location: localizacaoDe(linhaFalsa.loja),
    invoice_unit: linhaFalsa.unidade,
    quantity_invoiced: stringDeMilesimos(milesimosDe(linhaFalsa.faturada)),
    quantity_received: stringDeMilesimos(milesimosDe(recebidaDe(linhaFalsa))),
    packaging:
      linhaFalsa.embalagem === null
        ? null
        : {
            label: linhaFalsa.embalagem,
            base_quantity: stringDeMilesimos(linhaFalsa.basePorUnidade * 1000),
            base_unit: artigo?.unidadeBase ?? "un",
          },
    stock_quantity: stock,
    variable_weight: linhaFalsa.pesoVariavel,
    unit_price: linhaFalsa.precoUnitario,
    vat_rate: linhaFalsa.iva,
    line_total: centimos === null ? null : stringDeCentimos(centimos),
    price_history: historicoDePreco(rececao, linhaFalsa),
    requires_lot: exigeLote(linhaFalsa.artigo),
    lot_code: codigoDoLote(linhaFalsa),
    expires_at: dias === null ? null : dataEmDias(dias),
    expiry_kind: tipoDeValidadeDoArtigo(linhaFalsa.artigo),
    reviewed_by: linhaFalsa.autor,
    reviewed_at: linhaFalsa.quando,
    movement: linhaFalsa.movimento,
  };
}

function linhasSerializadas(rececao: RececaoFalsa): LinhaDeRececao[] {
  return rececao.linhas.map((linhaFalsa, posicao) =>
    serializarLinha(rececao, linhaFalsa, posicao),
  );
}

interface Totais {
  readonly base: number;
  readonly iva: number;
  readonly porTaxa: TotalDeIva[];
}

/**
 * Os totais do documento: a base e o IVA **por taxa**, como vêm no rodapé.
 *
 * O IVA é calculado por taxa sobre a base agregada, e não somando o IVA de cada
 * linha: é assim que uma fatura portuguesa o imprime, e a diferença de
 * arredondamento entre as duas formas é precisamente o cêntimo que faz um total
 * "não bater" por razões que não interessam a ninguém.
 *
 * `null` quando o documento não traz preços — a guia de remessa.
 */
function totais(rececao: RececaoFalsa): Totais | null {
  const comPreco = rececao.linhas.filter((linhaFalsa) => linhaFalsa.precoUnitario !== null);
  if (comPreco.length === 0) return null;

  const porTaxa = new Map<string, number>();
  let base = 0;

  for (const linhaFalsa of comPreco) {
    const centimos = centimosDaLinha(linhaFalsa) ?? 0;
    base += centimos;
    if (linhaFalsa.iva === null) continue;
    porTaxa.set(linhaFalsa.iva, (porTaxa.get(linhaFalsa.iva) ?? 0) + centimos);
  }

  const linhasDeIva: TotalDeIva[] = [];
  let iva = 0;
  for (const [taxa, baseDaTaxa] of [...porTaxa.entries()].sort((a, b) =>
    a[0].localeCompare(b[0]),
  )) {
    const valor = Math.round((baseDaTaxa * decimilesimosDe(taxa)) / 10_000);
    iva += valor;
    linhasDeIva.push({
      rate: taxa,
      base: stringDeCentimos(baseDaTaxa),
      vat: stringDeCentimos(valor),
    });
  }

  return { base, iva, porTaxa: linhasDeIva };
}

function localizacoesDe(rececao: RececaoFalsa): Localizacao[] {
  const vistas = new Map<string, Localizacao>();
  for (const linhaFalsa of rececao.linhas) {
    const local = localizacaoDe(linhaFalsa.loja);
    vistas.set(local.id, local);
  }
  return [...vistas.values()];
}

function serializar(rececao: RececaoFalsa): Rececao {
  const soma = totais(rececao);
  const total = soma === null ? null : stringDeCentimos(soma.base + soma.iva);

  return {
    id: rececao.id,
    supplier: { name: rececao.fornecedor, nif: rececao.nifDoFornecedor },
    doc_type: rececao.tipo,
    doc_number: rececao.numero,
    received_at: rececao.recebida,
    confirmed_at: rececao.confirmada,
    confirmed_by: rececao.autorDaConfirmacao,
    status: rececao.confirmada === null ? "needs_review" : "confirmed",
    lines_to_review: rececao.linhas.filter((linhaFalsa) => linhaFalsa.estado === "needs_review")
      .length,
    line_count: rececao.linhas.length,
    customer_name: rececao.nomeDoAdquirente,
    customer_nif: rececao.nifDoAdquirente,
    company_name: NOME_DA_EMPRESA,
    company_nif: NIF_DA_EMPRESA,
    awaiting_invoice: rececao.aguardaFatura,
    document_total: rececao.totalImpresso ?? total,
    lines_total: total,
    vat_breakdown: soma?.porTaxa ?? [],
    temperature_c: rececao.temperatura,
    cold_chain: rececao.linhas.some((linhaFalsa) => linhaFalsa.conservacao !== "ambient"),
    locations: localizacoesDe(rececao),
    reference: rececao.referencia,
  };
}

/**
 * "O que precisa de atenção primeiro, depois o mais recente" — a mesma ordem
 * de todos os outros ecrãs desta API, decidida no servidor para o cliente não
 * ganhar uma segunda definição dela.
 */
function ordenadas(lista: readonly RececaoFalsa[]): RececaoFalsa[] {
  return [...lista].sort((a, b) => {
    const porRever = (a.confirmada === null ? 0 : 1) - (b.confirmada === null ? 0 : 1);
    if (porRever !== 0) return porRever;
    return b.recebida.localeCompare(a.recebida);
  });
}

function confirmadaHoje(rececao: RececaoFalsa): boolean {
  if (rececao.confirmada === null) return false;
  return new Date(rececao.confirmada).getTime() >= inicioDoDiaDeNegocio().getTime();
}

function listaPedida(ctx: Contexto): RececaoFalsa[] {
  const estado = ctx.parametros.get("estado");
  const todas = ordenadas(rececoes);
  if (estado === "revisao") return todas.filter((rececao) => rececao.confirmada === null);
  // "hoje" e não "confirmadas": o número do topo conta o **dia de negócio**, e
  // um contador que não dá as linhas de baixo é a primeira coisa que faz o dono
  // desconfiar do ecrã.
  if (estado === "hoje") return todas.filter(confirmadaHoje);
  return todas;
}

function resumo() {
  const porRever = rececoes.filter((rececao) => rececao.confirmada === null);

  return {
    needs_review_count: porRever.length,
    needs_review_lines: porRever.reduce(
      (soma, rececao) =>
        soma + rececao.linhas.filter((linhaFalsa) => linhaFalsa.estado === "needs_review").length,
      0,
    ),
    confirmed_today_count: rececoes.filter(confirmadaHoje).length,
    business_day_starts_at: INICIO_DO_DIA,
    confirmed_since: inicioDoDiaDeNegocio().toISOString(),
  };
}

// ---------------------------------------------------------------------------
// A ligação ao ledger, nos dois sentidos.
// ---------------------------------------------------------------------------

/**
 * Liga cada linha já confirmada ao movimento que ela criou — e **rebenta** se
 * não encontrar, ou se a quantidade não bater.
 *
 * É o que torna estas receções vistas do mesmo ledger em vez de um estado
 * paralelo: as confirmadas não guardam quantidade nenhuma, lêem-na do
 * movimento. Falha no arranque do `pnpm dev`, alto, porque um seed de receções
 * que não corresponda ao `ledger.ts` ensinaria exactamente o contrário do que
 * este ecrã existe para mostrar — e passaria por bom, que é pior.
 */
function resolverMovimentos(): void {
  for (const rececao of rececoes) {
    if (rececao.confirmada === null) continue;
    for (const linhaFalsa of rececao.linhas) {
      if (linhaFalsa.especie !== "goods" || linhaFalsa.artigo === null) continue;

      const mov = ledger().find(
        (candidato) =>
          candidato.tipo === "receipt" &&
          candidato.referencia === rececao.referencia &&
          candidato.artigo === linhaFalsa.artigo &&
          candidato.loja === linhaFalsa.loja,
      );
      if (mov === undefined) {
        throw new Error(
          `Fixture de receções: a linha "${linhaFalsa.descricao}" de ${rececao.referencia} ` +
            `(artigo ${String(linhaFalsa.artigo)}, ${linhaFalsa.loja}) não tem movimento no ledger.`,
        );
      }

      const previsto = milesimosDaLinha(linhaFalsa);
      if (mov.milesimos !== previsto) {
        throw new Error(
          `Fixture de receções: ${rececao.referencia} / "${linhaFalsa.descricao}" dá ` +
            `${String(previsto)} e o movimento do ledger tem ${String(mov.milesimos)}.`,
        );
      }

      linhaFalsa.movimento = mov.id;
    }
  }
}

resolverMovimentos();

/**
 * Confirmar a receção: **a única escrita deste ficheiro que toca no ledger**.
 *
 * Cria um movimento de entrada por cada linha de mercadoria confirmada, com o
 * lote e a validade que alguém escreveu, e `occurred_at` na hora a que a
 * mercadoria **chegou** (do documento) e não na hora em que se carregou no
 * botão — é por isso que `received_at` e `confirmed_at` são dois campos.
 *
 * O que **não** gera movimento, e cada caso por uma razão de domínio: uma linha
 * por rever (não houve revisão humana), uma linha deixada de fora, uma linha
 * sem artigo no catálogo, o vasilhame e os encargos (não são stock consumível).
 * Nenhum destes casos impede a confirmação do documento.
 */
function confirmarRececao(ctx: Contexto) {
  const rececao = rececaoPedida(ctx);
  if (!rececao) return resposta(404, NAO_ENCONTRADA);
  // Idempotente: um duplo toque não dá entrada duas vezes à mesma mercadoria.
  if (rececao.confirmada !== null) return resposta(200, serializar(rececao), rececaoSchema);

  const quando = new Date().toISOString();
  for (const linhaFalsa of rececao.linhas) {
    if (linhaFalsa.especie !== "goods") continue;
    if (linhaFalsa.estado !== "confirmed") continue;
    if (linhaFalsa.artigo === null) continue;

    const codigo = linhaFalsa.lote;
    const dias = linhaFalsa.validadeEmDias;
    const tipo = tipoDeValidadeDoArtigo(linhaFalsa.artigo);
    if (codigo !== null && dias !== null && tipo !== null) {
      // O lote que estava escrito na linha passa a existir no ledger: é dele
      // que os alertas e o FEFO vão falar a partir de agora.
      registarLote({ codigo, artigo: linhaFalsa.artigo, dias, tipo });
    }

    const mov = acrescentar({
      tipo: "receipt",
      artigo: linhaFalsa.artigo,
      loja: linhaFalsa.loja,
      lote: codigo,
      milesimos: milesimosDaLinha(linhaFalsa),
      sinal: null,
      motivo: null,
      // Quem confirma a fatura é quem a lança. É a sonda da Q7: a linha do
      // histórico no ecrã de Stock vai dizer o nome.
      autor: AUTORES.dono,
      quando: rececao.recebida,
      referencia: rececao.referencia,
    });
    linhaFalsa.movimento = mov.id;
  }

  rececao.confirmada = quando;
  rececao.autorDaConfirmacao = AUTORES.dono;

  return resposta(201, serializar(rececao), rececaoSchema);
}

// ---------------------------------------------------------------------------
// Escrita.
// ---------------------------------------------------------------------------

const NAO_ENCONTRADA = {
  code: "nao_encontrada",
  detail: "Esta receção não existe neste estabelecimento.",
};

function rececaoPedida(ctx: Contexto): RececaoFalsa | undefined {
  const id = ctx.variaveis.get("rececao");
  return rececoes.find((rececao) => rececao.id === id);
}

/**
 * A revisão humana de **uma** linha.
 *
 * Três recusas, e nenhuma delas é um bloqueio de negócio: uma linha sem artigo
 * no catálogo não pode ser confirmada (não há nada em que entre), e um artigo
 * que exige lote não pode entrar sem lote nem sem validade (`inventory-domain`
 * §3). Em todos os casos a saída existe e está ao lado: `skip` deixa a linha
 * fora desta entrada, e **o documento confirma-se de qualquer maneira**. O que
 * o guião §4 nº 3 proíbe é impedir o ato; isto é a validação de um formulário,
 * como "escreva quantos kg estão na prateleira" no ecrã de contagem.
 */
function revisarLinha(ctx: Contexto) {
  const rececao = rececaoPedida(ctx);
  if (!rececao) return resposta(404, NAO_ENCONTRADA);
  if (rececao.confirmada !== null) {
    return resposta(409, {
      code: "rececao_confirmada",
      detail: "Esta receção já foi confirmada. Um documento confirmado não se edita.",
    });
  }

  const linhaFalsa = rececao.linhas.find(
    (candidata) => candidata.id === ctx.variaveis.get("linha"),
  );
  if (!linhaFalsa) return resposta(404, NAO_ENCONTRADA);

  const corpo = revisaoDeLinhaSchema.safeParse(ctx.corpo ?? {});
  if (!corpo.success) {
    return resposta(400, {
      code: "invalido",
      detail: "O corpo do pedido não tem a forma de uma revisão de linha.",
    });
  }

  const posicao = rececao.linhas.indexOf(linhaFalsa);

  if (corpo.data.skip === true) {
    linhaFalsa.estado = "skipped";
    linhaFalsa.autor = AUTORES.dono;
    linhaFalsa.quando = new Date().toISOString();
    return resposta(201, serializarLinha(rececao, linhaFalsa, posicao), linhaDeRececaoSchema);
  }
  if (corpo.data.skip === false) {
    linhaFalsa.estado = "needs_review";
    return resposta(201, serializarLinha(rececao, linhaFalsa, posicao), linhaDeRececaoSchema);
  }

  if (corpo.data.lot_code !== undefined) linhaFalsa.lote = corpo.data.lot_code;
  if (corpo.data.expires_at !== undefined) {
    linhaFalsa.validadeEmDias = diasAte(corpo.data.expires_at);
  }

  // Vasilhame e encargos confirmam-se sem artigo e sem lote: são linhas de
  // valor que não são stock, e exigir-lhes um artigo era obrigar a inventar um.
  if (linhaFalsa.especie !== "goods") {
    linhaFalsa.estado = "confirmed";
    linhaFalsa.autor = AUTORES.dono;
    linhaFalsa.quando = new Date().toISOString();
    return resposta(201, serializarLinha(rececao, linhaFalsa, posicao), linhaDeRececaoSchema);
  }

  if (linhaFalsa.artigo === null) {
    return resposta(400, {
      code: "sem_artigo",
      detail:
        "Esta linha não corresponde a nenhum artigo do catálogo. Deixe-a fora desta entrada ou crie o artigo primeiro.",
    });
  }
  if (exigeLote(linhaFalsa.artigo) && linhaFalsa.lote === null) {
    return resposta(400, {
      code: "lote_obrigatorio",
      detail: "Escreva o lote que está na embalagem antes de confirmar a linha.",
    });
  }
  if (exigeLote(linhaFalsa.artigo) && linhaFalsa.validadeEmDias === null) {
    return resposta(400, {
      code: "validade_obrigatoria",
      detail: "Escreva a validade que está na embalagem antes de confirmar a linha.",
    });
  }

  linhaFalsa.estado = "confirmed";
  linhaFalsa.autor = AUTORES.dono;
  linhaFalsa.quando = new Date().toISOString();

  return resposta(201, serializarLinha(rececao, linhaFalsa, posicao), linhaDeRececaoSchema);
}

/** A temperatura à entrega. Um registo da receção; não é um movimento. */
function registarTemperatura(ctx: Contexto) {
  const rececao = rececaoPedida(ctx);
  if (!rececao) return resposta(404, NAO_ENCONTRADA);

  const corpo = temperaturaSchema.safeParse(ctx.corpo);
  if (!corpo.success) {
    return resposta(400, {
      code: "invalido",
      detail: "Escreva a temperatura em graus, por exemplo -18 ou 4,5.",
    });
  }

  rececao.temperatura = corpo.data.celsius;
  return resposta(201, serializar(rececao), rececaoSchema);
}

// ---------------------------------------------------------------------------
// As rotas.
// ---------------------------------------------------------------------------

const PAGINA_VAZIA = { count: 0, next: null, previous: null, results: [] };

export const ROTAS_DE_RECECOES: readonly Rota[] = [
  {
    metodo: "GET",
    caminho: "/api/v1/receipts/summary",
    // Carrega acima da dobra, como os resumos dos outros ecrãs: atraso menor
    // para o skeleton dos números não durar mais do que a lista atrás dele.
    atrasoMs: 150,
    responder: () => resposta(200, resumo(), resumoDeRececoesSchema),
    vazio: () =>
      resposta(
        200,
        {
          needs_review_count: 0,
          needs_review_lines: 0,
          confirmed_today_count: 0,
          business_day_starts_at: INICIO_DO_DIA,
          confirmed_since: inicioDoDiaDeNegocio().toISOString(),
        },
        resumoDeRececoesSchema,
      ),
  },
  {
    metodo: "GET",
    caminho: "/api/v1/receipts",
    responder: (ctx) => {
      const lista = listaPedida(ctx).map(serializar);
      return resposta(
        200,
        { count: lista.length, next: null, previous: null, results: lista },
        paginated(rececaoSchema),
      );
    },
    // Sem receção nenhuma: é o estado vazio do ecrã Receber, e a ação que ele
    // oferece é a mesma do ecrã cheio — fotografar a fatura.
    vazio: () => resposta(200, PAGINA_VAZIA, paginated(rececaoSchema)),
  },
  {
    metodo: "GET",
    caminho: "/api/v1/receipts/:rececao/lines",
    responder: (ctx) => {
      const rececao = rececaoPedida(ctx);
      if (!rececao) return resposta(404, NAO_ENCONTRADA);
      const linhas = linhasSerializadas(rececao);
      return resposta(
        200,
        { count: linhas.length, next: null, previous: null, results: linhas },
        paginated(linhaDeRececaoSchema),
      );
    },
    vazio: () => resposta(200, PAGINA_VAZIA, paginated(linhaDeRececaoSchema)),
  },
  {
    metodo: "POST",
    caminho: "/api/v1/receipts/:rececao/lines/:linha/confirmation",
    atrasoMs: 120,
    responder: revisarLinha,
  },
  {
    metodo: "POST",
    caminho: "/api/v1/receipts/:rececao/temperature",
    atrasoMs: 120,
    responder: registarTemperatura,
  },
  {
    metodo: "POST",
    caminho: "/api/v1/receipts/:rececao/confirmation",
    responder: confirmarRececao,
  },
];
