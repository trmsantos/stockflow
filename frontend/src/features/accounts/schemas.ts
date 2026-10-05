import { z } from "zod";

/**
 * O contrato de autenticação e de activação, em Zod (ADR 0010).
 *
 * Ao contrário dos schemas de `inventory` e `purchasing`, estes **não** são o
 * rascunho de um contrato por escrever: os endpoints existem, o `schema.yml`
 * está gerado e os tipos estão em `src/lib/api/types.ts` (`SessaoOut`,
 * `EstadoEnum`, `TenantOut`, `UtilizadorOut`, `ErroOut`). Este ficheiro é o
 * **verificador em runtime** desses tipos, que é o que o `types.ts` não pode
 * ser: um tipo do TypeScript não existe depois de compilar, e o
 * `SECURITY.md` §4 pede Zod em todas as respostas.
 *
 * Por isso a regra de manutenção é diferente das outras features: se o
 * `pnpm gen:api` mudar um destes nomes, este ficheiro muda com ele — não é ele
 * que propõe a forma.
 *
 * Nomes em português nos tipos de saída (`Sessao`, `Estabelecimento`) e os
 * **campos** com o nome que vem do servidor (`tenant_ativo`, `estado`): o
 * campo é contrato, o tipo é nosso.
 */

/** O papel de quem vê, no par (utilizador, estabelecimento). `PapelEnum`. */
export const papelSchema = z.enum(["owner", "manager", "staff"]);

/**
 * Um estabelecimento como o seletor o mostra. `TenantOut`.
 *
 * Serve as duas posições da resposta — `tenant_ativo` e cada entrada de
 * `tenants` — porque são a mesma coisa em dois estados.
 */
export const estabelecimentoSchema = z.object({
  id: z.uuid(),
  nome: z.string().min(1),
  papel: papelSchema,
});

/**
 * Quem está autenticado. `UtilizadorOut`.
 *
 * O `email` é validado como **string não vazia** e não com `z.email()`, de
 * propósito: isto é uma *resposta*, e quem define o que é um email válido é o
 * `EmailField` do Django que já o guardou. Um validador mais apertado aqui
 * recusava a sessão de alguém cuja conta o servidor aceita — e o modo de falha
 * seria não conseguir entrar na aplicação, com um `ResponseShapeError` a dizer
 * que o servidor devolveu algo inesperado quando não foi isso que aconteceu.
 */
export const utilizadorSchema = z.object({
  id: z.uuid(),
  email: z.string().min(1),
});

/**
 * Os quatro fins de login da ADR 0007, como `estado` da sessão. `EstadoEnum`.
 *
 * Não há `mfa_pendente`: um valor de enum que nada produz é uma promessa que
 * ninguém cumpre, e entra no dia em que existir um segundo factor — que é
 * precisamente a propriedade que o campo de estado compra (ADR 0010).
 */
export const estadoDaSessaoSchema = z.enum([
  "anonimo",
  "sem_estabelecimento",
  "escolha_pendente",
  "ativa",
]);

/**
 * `SessaoOut` — a resposta dos **quatro** endpoints de autenticação, sempre
 * nesta forma. Uma forma só é o que permite ao cliente guardar as quatro numa
 * entrada de cache em vez de ter quatro ramos de Zod.
 *
 * `utilizador` e `tenant_ativo` são `null` e não ausentes: o servidor sabe
 * sempre, e um campo que às vezes não existe obrigava o cliente a distinguir
 * "não sei" de "não há".
 *
 * ## O invariante, verificado e não assumido
 *
 * A ADR 0010 diz que `estado === "ativa"` ⟺ `tenant_ativo !== null` está
 * **testado no backend**. O `.refine` abaixo não duvida do teste: transforma a
 * suposição num controlo na fronteira, que é a diferença entre "sabemos" e
 * "medimos" nesta casa. O que ele compra é o modo de falha certo se a ligação
 * alguma vez se quebrar — um `ResponseShapeError` alto, no ecrã de entrada, em
 * vez de um `AppShell` montado sem estabelecimento a dar 403 em cada pedido
 * seguinte, que é o sintoma a dois passos de distância da causa.
 *
 * `menu` viaja vazio e **sem forma de item declarada** até a ADR 0009 existir
 * em código: `z.array(z.unknown())` é a forma honesta de "há uma lista aqui e
 * eu ainda não sei o que ela leva". Declarar a tupla dela aqui era inventar o
 * contrato de outra ADR.
 */
export const sessaoSchema = z
  .object({
    estado: estadoDaSessaoSchema,
    utilizador: utilizadorSchema.nullable(),
    tenant_ativo: estabelecimentoSchema.nullable(),
    tenants: z.array(estabelecimentoSchema),
    menu: z.array(z.unknown()),
  })
  .refine(
    (sessao) => (sessao.estado === "ativa") === (sessao.tenant_ativo !== null),
    "A sessão diz-se ativa sem estabelecimento, ou o contrário: o invariante da ADR 0010 não se verifica nesta resposta.",
  );

/**
 * O corpo do `POST /auth/login`. `LoginInRequest`.
 *
 * O email exige só uma string não vazia e a password também, e **a força não
 * se valida aqui** — nem no login nem em sítio nenhum do cliente. No login,
 * dizer a quem escreve que "essa password não poderia ser a desta conta" é um
 * oráculo barato sobre a política de passwords do sistema; e quem define o que
 * é um email válido é o Django, que devolve um 400 por campo que o formulário
 * mostra ao lado do input. Duas definições de "email válido" divergiriam na
 * primeira pessoa com um domínio invulgar.
 *
 * As mensagens estão aqui e não no ecrã porque este schema tem **dois** papéis:
 * valida o que o formulário submete (e aí as frases aparecem debaixo do input)
 * e valida o corpo antes de ele sair (e aí nunca aparecem, porque o que chega a
 * este segundo papel já passou pelo primeiro). Dois schemas para os dois papéis
 * eram duas definições de "credenciais preenchidas", e a de cá divergiria na
 * primeira correção.
 *
 * O `.trim()` no email é parte do contrato e não cosmética: um teclado de
 * telemóvel acrescenta um espaço depois de uma palavra completada, e o DRF corta
 * o email por omissão — cortá-lo aqui é mandar o mesmo valor que o servidor ia
 * usar. Na password **não** há trim, no cliente nem no servidor
 * (`trim_whitespace=False`): um espaço final é um carácter da password de quem
 * o escreveu.
 */
export const credenciaisSchema = z.object({
  email: z.string().trim().min(1, "Escreva o email da sua conta.").max(254),
  password: z.string().min(1, "Escreva a sua password."),
});

/**
 * O formulário de activação: a password **e a sua repetição**.
 *
 * ## A repetição é uma decisão desta sessão, e não vem de nenhuma ADR
 *
 * A reposição de password é dívida nomeada da ADR 0010 e ainda não existe.
 * Enquanto não existir, uma password escrita com um erro de dedo não é um
 * incómodo: é uma conta inacessível, que só se recupera com um convite novo de
 * quem administra o estabelecimento. O segundo campo custa dez segundos e fecha
 * esse caminho. No dia em que houver reposição, isto pode voltar a ser um campo
 * só — e aí é uma decisão de UX e não de recuperabilidade.
 *
 * A comparação vive **no schema** e não num `if` no ecrã por duas razões, e as
 * duas valem: é onde vive toda a outra validação deste repositório, e o
 * `security/detect-possible-timing-attacks` do `eslint.config.js` acusa — por
 * construção, só dentro de um `if` e só com um identificador chamado `password`
 * — qualquer `if (x === password)`. Aqui o aviso seria falso (são duas strings
 * que a mesma pessoa acabou de escrever no mesmo ecrã, não uma verificação de
 * credencial), e a casa não suprime lint: muda-se a forma, que neste caso é a
 * forma melhor.
 *
 * A **força** continua a não ser validada aqui. Quem a impõe são os
 * `AUTH_PASSWORD_VALIDATORS` do servidor, que respondem 400 por campo com as
 * mensagens todas de uma vez; reimplementá-la dava duas definições de "password
 * forte", e a de cá ficaria desatualizada no dia em que a política mudasse.
 */
export const formularioDeAtivacaoSchema = z
  .object({
    password: z.string().min(1, "Escolha uma password para activar a sua conta."),
    confirmacao: z.string(),
  })
  .refine((campos) => campos.confirmacao === campos.password, {
    error: "As duas passwords não são iguais.",
    path: ["confirmacao"],
  });

/**
 * O corpo do `POST /auth/tenant-ativo`. `TenantAtivoInRequest`.
 *
 * É um **argumento e não uma credencial** (ADR 0007): quem verifica a pertença
 * é a política de RLS, dentro do `tenant_scope` que o service abre. O `z.uuid()`
 * só garante que o valor é um uuid, e serve para o pedido não sair com um valor
 * que o servidor vai recusar por forma.
 */
export const escolhaDeEstabelecimentoSchema = z.object({
  tenant_id: z.uuid(),
});

/**
 * O corpo do `POST /auth/ativar`. `AtivacaoInRequest`.
 *
 * ## O fragmento é **opaco** e o cliente não o divide
 *
 * `<uuid-do-tenant>.<token>` é o que vem depois do `#` no link, e viaja
 * inteiro: quem o divide é o service, logo o formato do segredo tem **uma**
 * definição e ela vive no servidor (ADR 0010). Por isso não há aqui um regex a
 * exigir o ponto, nem um `z.uuid()` sobre a primeira metade — validar o formato
 * aqui era conhecê-lo, e o dia em que ele mudasse eram dois sítios a mudar.
 *
 * ## A password é opcional porque **o servidor é que sabe** se é precisa
 *
 * Uma conta que já tem password utilizável **não** a redefine ao aceitar um
 * convite: a password é global e a pertença é por tenant, pelo que "convite +
 * definir password" dava a quem pode convidar a tomada de uma conta existente.
 * Nesse caso a activação recusa com `convite_exige_sessao` e este campo é
 * ignorado — não é o cliente que decide qual dos dois casos é.
 */
export const ativacaoSchema = z.object({
  fragmento: z.string().min(1),
  password: z.string().min(1).optional(),
});

export type Papel = z.output<typeof papelSchema>;
export type Estabelecimento = z.output<typeof estabelecimentoSchema>;
export type Utilizador = z.output<typeof utilizadorSchema>;
export type EstadoDaSessao = z.output<typeof estadoDaSessaoSchema>;
export type Sessao = z.output<typeof sessaoSchema>;
export type Credenciais = z.output<typeof credenciaisSchema>;
export type FormularioDeAtivacao = z.output<typeof formularioDeAtivacaoSchema>;
export type EscolhaDeEstabelecimento = z.output<typeof escolhaDeEstabelecimentoSchema>;
export type Ativacao = z.output<typeof ativacaoSchema>;

/**
 * Os papéis por extenso, para o seletor de estabelecimento.
 *
 * Duas formas da mesma tabela, e as duas são precisas:
 *
 *  - o **`Record` sobre a união gerada** é o que faz o `pnpm typecheck` falhar
 *    nos **dois** sentidos no dia em que o `PapelEnum` do backend ganhar um
 *    quarto valor: um papel a mais aqui não compila, um papel a menos também
 *    não. É a mesma mecânica que a ADR 0009 usa para o registo de rotas, e é a
 *    alternativa a um `default: "colaborador"` que mostrava o papel errado em
 *    silêncio;
 *  - o **`Map`** é por onde se lê, porque o `security/detect-object-injection`
 *    do `eslint.config.js` recusa — e bem — um `OBJETO[chave]` com chave
 *    dinâmica, e esta casa não suprime lint (CLAUDE.md). O `?? papel` é
 *    inalcançável por construção (o `Map` nasce do `Record` exaustivo) e existe
 *    porque `Map.get` devolve `undefined` no tipo.
 */
const NOME_DO_PAPEL: Record<Papel, string> = {
  owner: "dono",
  manager: "gerente",
  staff: "colaborador",
};

const NOMES_DOS_PAPEIS = new Map<string, string>(Object.entries(NOME_DO_PAPEL));

export function nomeDoPapel(papel: Papel): string {
  return NOMES_DOS_PAPEIS.get(papel) ?? papel;
}
