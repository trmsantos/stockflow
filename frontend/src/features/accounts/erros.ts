import type { ZodError } from "zod";

import { ApiError, mensagemDeErro } from "@/lib/api/errors";
import { erroDoCampo } from "@/lib/api/erros-por-campo";

import { textos } from "./textos";

/**
 * Ler uma recusa da autenticação — e **só** ler: nada aqui reescreve uma
 * mensagem do servidor.
 *
 * ## O 400 tem duas formas, e é por isso que este ficheiro existe
 *
 * O `views.py` do `accounts` diz-no por extenso: um corpo inválido sai na forma
 * normal do DRF, `{"email": ["..."]}`, **por campo** — é o que um formulário
 * mostra ao lado de cada input; e a recusa de credenciais sai em
 * `{code, detail}`, que é para o cliente **ramificar**. O mesmo status, duas
 * formas. O `errors.ts` já lê o `code` defensivamente (`string | null`) porque
 * nenhuma das duas é garantida por um status; o que falta é a outra metade: ler
 * os erros por campo sem assumir que estão lá.
 *
 * ## Os códigos são por endpoint, de propósito
 *
 * O `ErroOut` declara `code` como string e não como enum fechado porque o
 * conjunto de códigos é por endpoint (`credenciais_invalidas` só no login,
 * `conta_bloqueada` só no 429 do lockout). Não há aqui uma união de todos: cada
 * ecrã compara com os que o **seu** endpoint devolve, e um `code` desconhecido
 * cai sempre no ramo genérico.
 */

/** `credenciais_invalidas` — 400 do login. Genérico de propósito. */
export const CODIGO_CREDENCIAIS_INVALIDAS = "credenciais_invalidas";
/** `conta_bloqueada` — 429 do lockout do axes, com corpo JSON. */
export const CODIGO_CONTA_BLOQUEADA = "conta_bloqueada";
/** `tenant_desconhecido` — 403 do `tenant-ativo` e do `TenantMiddleware`. */
export const CODIGO_TENANT_DESCONHECIDO = "tenant_desconhecido";
/** `convite_invalido` — 400 da activação. O **mesmo** para seis causas. */
export const CODIGO_CONVITE_INVALIDO = "convite_invalido";
/** `convite_exige_sessao` — 409: o email convidado já tem conta com password. */
export const CODIGO_CONVITE_EXIGE_SESSAO = "convite_exige_sessao";
/** `convite_de_outra_conta` — 403: a sessão é de outra conta. */
export const CODIGO_CONVITE_DE_OUTRA_CONTA = "convite_de_outra_conta";
/**
 * `convite_nao_pendente` — 409 do reenviar e do revogar.
 *
 * O quarto código da ADR 0010, e o único que **não** é uma recusa de uma
 * credencial: é um estado que mudou debaixo dos pés de quem tinha a lista
 * aberta. Só existe nos endpoints de gestão, onde quem chama vê o estado na
 * lista — e é por isso que a reacção certa a ele é **reler a lista**, não só
 * mostrar a frase. Quem o faz é o `api.ts`.
 *
 * As recusas de **criação** não têm código: são erros de validação do campo
 * `email` (400 por campo), porque "já existe convite pendente" e "já é membro"
 * são afirmações sobre o email submetido (ADR 0010, ponto 4). Medido: as quatro
 * recusas de criação saem em `{"email": [...]}`, `{"nome": [...]}` e
 * `{"papel": [...]}`, nenhuma com `code`.
 */
export const CODIGO_CONVITE_NAO_PENDENTE = "convite_nao_pendente";

/**
 * O `code` de uma recusa, ou `null`.
 *
 * Nunca se assume presente só por o status ser 400 ou 429: o 429 tem **duas
 * origens** (o lockout do axes, com `code`, e o throttle do DRF, sem) e o 400
 * tem duas formas. Quem lê isto ramifica por igualdade e tem sempre um ramo
 * para `null`.
 */
export function codigoDaRecusa(erro: unknown): string | null {
  return erro instanceof ApiError ? erro.code : null;
}

/** O status HTTP, ou `null` se o erro não vier da API (rede, Zod). */
export function statusDaRecusa(erro: unknown): number | null {
  return erro instanceof ApiError ? erro.status : null;
}

/**
 * A frase para mostrar. O `detail` do servidor **não é reescrito**.
 *
 * O `mensagemDeErro` do `errors.ts` já faz o essencial: devolve o `detail`
 * quando ele existe, porque ele já vem pronto para mostrar e já diz o passo
 * seguinte. Falta-lhe um caso que a autenticação tem e os ecrãs de dados não
 * tinham: uma recusa **sem corpo JSON**, em que o `message` do `ApiError` é
 * `"403 em /auth/login"` — texto de diagnóstico, não de produto.
 *
 * O caso é real e está medido: um `POST /auth/login` sem o header `X-CSRFToken`
 * leva um 403 cuja resposta é **HTML** (a página de erro do Django), logo o
 * `code` e o `detail` são os dois `null`. Acontece a quem deixou o separador
 * aberto tempo suficiente para o cookie de CSRF expirar.
 *
 * Note-se o que isto **não** faz: não acrescenta detalhe a nenhuma recusa que
 * tenha `detail`. Em particular, `credenciais_invalidas` chega aqui com "Email
 * ou password incorretos." e sai exactamente assim — dizer "este email não
 * existe" confirmaria a um estranho quais os emails são clientes.
 */
export function mensagemDaRecusa(erro: unknown): string {
  if (erro instanceof ApiError && erro.detail === null) {
    if (erro.status === 403) {
      return textos.recusas.semToken;
    }
    return textos.recusas.semServidor;
  }
  return mensagemDeErro(erro);
}

/**
 * Os erros por campo de um 400 do DRF, para os campos que este formulário tem.
 *
 * Lê `{"email": ["..."], "password": ["...", "..."]}` do `payload` do
 * `ApiError` e devolve, por campo, as mensagens **já juntas numa frase** — a
 * activação devolve três de uma vez para uma password fraca ("tem de ter 12
 * caracteres", "é muito comum", "é inteiramente numérica"), e as três
 * interessam a quem está a escolher a password.
 *
 * A leitura de **um** campo desceu para `@/lib/api/erros-por-campo` quando as
 * contagens passaram a ser o terceiro módulo a precisar dela — era o gatilho
 * que o `purchasing` tinha escrito. O que fica aqui é a parte que é deste
 * módulo: a **lista** de campos, que é a do formulário.
 *
 * Só olha para os campos que lhe são **dados**: um `Object.keys(payload)` punha
 * no ecrã o nome de qualquer chave que o servidor inventasse, incluindo
 * `detail`, debaixo de um input que não existe.
 *
 * Devolve um `Map` e não um `Partial<Record>` por duas razões que coincidem: o
 * `security/detect-object-injection` do `eslint.config.js` acusa — e bem — tanto
 * a leitura como a **escrita** de `objeto[chave]` com chave dinâmica, e esta
 * casa não suprime lint (CLAUDE.md); e um `Map` é a forma que o resto do
 * repositório já usa para tabelas lidas por variável (`vocabulario.ts`). O
 * `.get()` devolve `string | undefined`, que é exactamente o tipo que o
 * `CampoDeTexto` quer no seu `erro`.
 */
export function errosPorCampo<Campo extends string>(
  erro: unknown,
  campos: readonly Campo[],
): Map<Campo, string> {
  const resultado = new Map<Campo, string>();
  for (const campo of campos) {
    const frase = erroDoCampo(erro, campo);
    if (frase !== null) resultado.set(campo, frase);
  }
  return resultado;
}

/**
 * Os erros de um `safeParse` falhado, por campo, na mesma forma que os do
 * servidor.
 *
 * **A mesma forma é o ponto**: o ecrã lê os erros locais e os do servidor com o
 * mesmo `.get("password")`, e um campo pode ter os dois em momentos diferentes
 * (o local quando está vazio, o do servidor quando é fraca). Duas formas davam
 * dois ramos de JSX por campo.
 *
 * Lê `error.issues` e compara o primeiro segmento do `path` com os campos
 * pedidos, em vez de indexar o `fieldErrors` do `z.flattenError` por uma
 * variável — que é a mesma injeção de chave dinâmica que o `errosPorCampo`
 * evita. Fica a **primeira** mensagem de cada campo: o Zod emite uma por check,
 * e a primeira é a que descreve o problema mais próximo do que a pessoa
 * escreveu.
 */
export function errosDeValidacao<Campo extends string>(
  erro: ZodError,
  campos: readonly Campo[],
): Map<Campo, string> {
  const resultado = new Map<Campo, string>();
  for (const problema of erro.issues) {
    const segmento = problema.path.at(0);
    if (typeof segmento !== "string") continue;
    const campo = campos.find((nome) => nome === segmento);
    if (campo === undefined || resultado.has(campo)) continue;
    resultado.set(campo, problema.message);
  }
  return resultado;
}
