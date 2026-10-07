import { z } from "zod";

import { TEMAS } from "@/lib/tema";

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
 * A paleta que esta pessoa prefere. `TemaEnum` (ADR 0015 e ADR 0016).
 *
 * ## `z.enum(TEMAS)` e não uma lista escrita aqui, ao contrário do `route_id`
 *
 * A decisão do `itemDeMenuSchema` foi a oposta — lá o id é `z.string()` — e vale
 * a pena dizer porque, senão isto lê-se como incoerência. Lá, um id que este
 * bundle não conhecesse derrubava a resposta **inteira** do `GET /auth/sessao`,
 * isto é, a aplicação não arrancava: o caso é o intervalo de um rolling deploy,
 * com um backend novo a servir um sétimo id a um bundle antigo, e um menu com um
 * item a menos é degradação enquanto uma sessão que não parseia é a app fechada.
 *
 * Aqui o risco inverte-se, e por uma razão de forma: o `tema` é um campo
 * **escalar e obrigatório** do `utilizador`, não um elemento de uma lista que se
 * possa ignorar. Um `z.string()` aqui deixaria passar para o `<html>` um valor
 * que nenhuma paleta reconhece — e o cliente é quem o escreve no DOM. A queda
 * para o default existe e está no `temaDe` do `lib/tema.ts`, que é por onde o
 * valor passa antes de ser aplicado; o que este schema recusa é guardar na cache
 * uma sessão cujo tema não é um dos três.
 *
 * A lista vem do `TEMAS`, que é derivado do `Record<Tema, …>` sobre o
 * `TemaEnum` **gerado**: não há uma segunda lista de paletas em runtime, que é
 * exactamente a dívida que a decisão do `route_id` nomeia.
 */
export const temaSchema = z.enum(TEMAS);

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
  tema: temaSchema,
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
 * `ItemDeMenuOut` — uma linha do menu, **já resolvida pelo servidor** (ADR 0009
 * e ADR 0011).
 *
 * É a tupla que a ADR 0009 fixa — `(route_id, grupo, ordem, visivel, rotulo)` —,
 * uma lista com um nível de agrupamento e nunca uma árvore. Quem a compõe é o
 * `selectors.projeccao_de_menu` do backend: o registo de rotas que vive em
 * código, a configuração do tenant por cima, e o filtro pelo papel de quem pede.
 *
 * O **mesmo** `ItemDeMenu` existe com outro significado no `shell/menu.ts`: lá é
 * o item já casado com o registo de rotas (com caminho, ícone e pergunta). Este
 * é a linha de configuração que chega por HTTP, e é a `EntradaDaProjeccao` que
 * ele satisfaz — o encaixe é verificado em `routes/involucro.tsx`, que é a única
 * camada que pode importar os dois lados (ADR 0008, decisão 2).
 *
 * ## `route_id` é `z.string()` e **não** o enum fechado, e é decisão desta sessão
 *
 * O id é um enum fechado do backend e chega ao `types.ts` como união
 * (`RotaIdEnum`); é essa união que o `Record<RotaId, EntradaDoRegisto>` do
 * `shell/registo-de-rotas.ts` verifica — medido, **nos dois sentidos**. A
 * garantia está lá, e repeti-la aqui com um `z.enum([...])` custava mais do que
 * dava:
 *
 *  - era uma **segunda lista dos seis ids em runtime**, sem nada que a casasse
 *    com a primeira — exactamente a dívida que o `campo` duplicado já tem
 *    nomeada (está nos dois registos e nada falha se divergirem);
 *  - e, sobretudo, um id que **este bundle** não conhece derrubava a resposta
 *    inteira do `GET /auth/sessao` — ou seja, a aplicação não arrancava. O caso
 *    não é hipotético: é o intervalo de um rolling deploy, com um backend novo a
 *    servir um sétimo id a um bundle antigo. O backend decidiu explicitamente o
 *    contrário para o caso simétrico ("uma entrada a mais não é razão para o
 *    menu não montar", `selectors.projeccao_de_menu`) e o `montarMenu` do shell
 *    já ignora o id que o registo não tem. Um menu com um item a menos é
 *    degradação; uma sessão que não parseia é a app fechada.
 *
 * Logo o que se valida aqui é a **forma**, e o resto da linha é estrito: um
 * `grupo` vazio é um cabeçalho de grupo sem nome e uma `ordem` que não é inteiro
 * não ordena nada — os dois seriam defeitos do servidor, e falham alto.
 *
 * Que o `min(1)` nunca recusa uma resposta legítima foi **medido** no `PUT`, que
 * é o único escritor: `grupo: ""` e `rotulo: ""` levam 400 por campo e não
 * escrevem linha nenhuma. E um `route_id` inventado também leva 400 — o que
 * confirma que a única origem possível de um id desconhecido é um **servidor
 * mais novo**, que é exactamente o caso que a decisão acima protege.
 *
 * `ordem` não leva os limites do serializer (`0..32767`): aqui é só a chave de
 * ordenação do `montarMenu`, e quem recusa um valor fora de limites é o `PUT`,
 * que é onde ele entra. `rotulo` é `null` quando o tenant não sobrepôs nada e
 * nunca `""` — a coluna guarda a ausência como `""` e a tradução para `null`
 * acontece num sítio só (`selectors.projeccao_de_menu`).
 */
export const itemDeMenuSchema = z.object({
  route_id: z.string().min(1),
  grupo: z.string().min(1),
  ordem: z.number().int(),
  visivel: z.boolean(),
  rotulo: z.string().min(1).nullable(),
});

/**
 * O regime de IVA. `VatRegimeEnum` (ADR 0017).
 *
 * Enum fechado em runtime, ao contrário do `route_id` e pela mesma razão do
 * `temaSchema`: é um valor **escalar** de um objecto obrigatório, não um elemento
 * de uma lista que se possa ignorar. E tem uma razão própria, mais forte: é um
 * valor que decide **dinheiro** — se o IVA de uma compra é custo. Um terceiro
 * valor que este bundle não conheça não deve ser mostrado como se fosse
 * conhecido; deve derrubar a leitura e aparecer como erro, porque o ecrã que o
 * mostrasse estaria a dizer ao dono que a sua margem foi calculada com uma regra
 * que ele não escolheu.
 *
 * Os dois valores e a razão de serem dois estão no `RegimeDeIva` do backend, que
 * é quem fala com a lei. Aqui só se verifica que a resposta é um deles.
 */
export const regimeDeIvaSchema = z.enum(["normal", "isento_art_53"]);

/**
 * A hora a que o dia de negócio começa, como `"HH:MM"` (ADR 0017).
 *
 * String e não um `Date`: é uma **hora de parede local**, sem dia e sem fuso, e
 * um `Date` obrigaria a escolher um dia para a ancorar — que é exactamente o erro
 * que a consulta ao domínio nomeou (os *buckets* calculam-se por data+hora local
 * e nunca somando 24 h, senão a noite da mudança de hora duplica uma hora de
 * movimentos em outubro e perde uma em março).
 *
 * O regex é `^([01]\d|2[0-3]):[0-5]\d$` e não `/^\d{2}:\d{2}$/`: o segundo
 * aceita `"99:99"`. **A janela 00:00–06:00 não é validada aqui** — quem a recusa
 * é o servidor (serializer, com a frase; `CheckConstraint`, como rede), e uma
 * terceira definição no cliente seria a que fica desactualizada no dia em que o
 * domínio a alargar. O que este schema garante é que a resposta é uma hora.
 */
export const horaDoDiaSchema = z
  .string()
  .regex(/^([01]\d|2[0-3]):[0-5]\d$/, "A hora escreve-se como HH:MM, por exemplo 04:00.");

/**
 * `EstabelecimentoOut` — a configuração da empresa (ADR 0017).
 *
 * **Não é o `estabelecimentoSchema`**, e os dois existem de propósito: aquele
 * descreve o estabelecimento como o **seletor** o mostra (id, nome e o papel de
 * quem está a ver) e viaja em cada resposta de sessão; este descreve a
 * **entidade** — o que ela é e como está configurada —, sem papel nenhum, porque
 * a configuração não muda com quem olha. Juntá-los punha o regime de IVA em cada
 * `GET /auth/sessao` de cada colaborador.
 *
 * `demonstracao` é só de leitura e não está no corpo de escrita: marcar um
 * estabelecimento real como demonstração era esconder dados reais atrás de um
 * aviso de "isto é de brincar", e desmarcar o de demonstração era promover dados
 * semeados a dados de negócio sem ninguém os ter introduzido.
 */
export const configuracaoDoEstabelecimentoSchema = z.object({
  id: z.uuid(),
  nome: z.string().min(1),
  vat_regime: regimeDeIvaSchema,
  business_day_starts_at: horaDoDiaSchema,
  demonstracao: z.boolean(),
});

/**
 * `EstabelecimentoInRequest` — o corpo do `PATCH /estabelecimento`.
 *
 * Os três campos configuráveis. O `nome` leva o limite do serializer (200) e as
 * mensagens vivem aqui porque este schema tem os **dois** papéis do
 * `credenciaisSchema`: valida o que o formulário submete (e aí as frases
 * aparecem debaixo do input) e valida o corpo antes de ele sair.
 *
 * A janela do dia de negócio continua a não ser validada aqui — ver o
 * `horaDoDiaSchema`. O que o cliente recusa é uma hora que não é uma hora; o que
 * o servidor recusa é uma hora que não serve, com a frase que explica porquê.
 */
export const estabelecimentoParaGuardarSchema = z.object({
  nome: z
    .string()
    .trim()
    .min(1, "Escreva o nome do estabelecimento.")
    .max(200, "O nome não pode ter mais de 200 caracteres."),
  vat_regime: regimeDeIvaSchema,
  business_day_starts_at: horaDoDiaSchema,
});

/**
 * `RotaDeMenuOut` — uma rota do **registo**: o que existe para configurar.
 *
 * É a resposta do `GET /menu/rotas` e o que ela descreve é **código**, não dados
 * de um tenant: a lista fechada de rotas que o menu pode nomear, com o rótulo e
 * o grupo por omissão, quem as pode ver, e se foram desenhadas para 360px.
 * Nenhuma linha de base de dados é lida para a produzir.
 *
 * Serve um ecrã só — o `/configuracao` — e é por isso que carrega os defaults:
 * são eles que permitem mostrar "o que esta rota se chama se ninguém lhe mexer",
 * que é a informação que falta a quem está a decidir se lhe mexe.
 *
 * `route_id` é `z.string()` pela razão do `itemDeMenuSchema`, e aqui a
 * consequência é ainda mais benigna: uma rota que este bundle não conheça
 * aparece na lista de configuração sem ícone nem caminho (o `REGISTO_DE_ROTAS`
 * do shell não a tem) e o ecrã salta-a. Um `z.enum` derrubava a lista inteira
 * durante o intervalo de um rolling deploy.
 *
 * `papeis_permitidos` **é** um enum fechado, e a diferença é de forma: é um
 * conjunto de papéis e os papéis são três desde a ADR 0007, enquanto as rotas
 * crescem a cada feature. Um papel novo é uma decisão de produto (a Q7), não um
 * efeito secundário de um deploy.
 */
export const rotaDeMenuSchema = z.object({
  route_id: z.string().min(1),
  rotulo_default: z.string().min(1),
  grupo_default: z.string().min(1),
  papeis_permitidos: z.array(papelSchema),
  campo: z.boolean(),
});

/**
 * `ItemDeMenuInRequest` — uma linha do corpo do `PUT /menu`.
 *
 * Os quatro campos configuráveis e nada mais. **Não** há `campo`, e isso é
 * estrutural: se a forma que a configuração transporta o tivesse, uma empresa
 * promovia uma rota de escritório para o telemóvel escrevendo `campo: true` — e
 * o predicado que diz "este ecrã foi desenhado para 360px" é código (ADR 0009,
 * adenda 2). Também não há `caminho` nem `icone`: a árvore de rotas é código, e
 * um menu que nomeasse caminhos punha o deep link a depender da configuração.
 *
 * Os limites são os do serializer — grupo e rótulo a 50, ordem em `0..32767` —,
 * **lidos de lá e não adivinhados**, porque são eles que decidem se o 400 vem
 * daqui com a frase pronta ou do servidor a meio de uma submissão de oito linhas.
 *
 * `rotulo` é `null` para "usa o default" e nunca `""`: a coluna guarda a ausência
 * como `""` e a tradução entre as duas formas acontece num sítio só, no servidor.
 * Daí o `.transform`: o que um `<input>` vazio dá é `""`, e mandá-lo tal e qual
 * era um 400 por `allow_blank=False` em vez de um rótulo reposto ao default.
 */
export const itemDeMenuParaGuardarSchema = z.object({
  route_id: z.string().min(1),
  grupo: z
    .string()
    .trim()
    .min(1, "Escreva o nome do grupo.")
    .max(50, "O nome do grupo não pode ter mais de 50 caracteres."),
  ordem: z
    .number()
    .int("A ordem é um número inteiro.")
    .min(0, "A ordem não pode ser negativa.")
    .max(32767, "A ordem não pode passar de 32767."),
  visivel: z.boolean(),
  rotulo: z
    .string()
    .trim()
    .max(50, "O rótulo não pode ter mais de 50 caracteres.")
    .nullable()
    .transform((valor) => (valor === "" ? null : valor)),
});

/**
 * O corpo inteiro do `PUT /menu` — um array no topo, e a lista **é** a entidade.
 *
 * `PUT` de substituição total e não N `PATCH`: reordenar é uma intenção, e N
 * pedidos deixam um menu meio ordenado se um deles falhar, com o cliente sem
 * saber quais passaram (ADR 0009).
 *
 * O `.refine` repete a única validação que o `MenuInListSerializer` faz sobre a
 * lista como um todo — nenhuma rota duas vezes — e repeti-la aqui não é
 * duplicação inútil: sem ela, a recusa chega em `non_field_errors` depois de a
 * pessoa ter arrastado oito linhas, e o ecrã tem de a mostrar longe da causa.
 * Com ela, o botão nem submete. Quem **impõe** continua a ser o servidor, com a
 * unicidade na base de dados por baixo como rede.
 */
export const menuParaGuardarSchema = z
  .array(itemDeMenuParaGuardarSchema)
  .refine(
    (itens) => new Set(itens.map((item) => item.route_id)).size === itens.length,
    "Há uma rota repetida na configuração. Cada rota aparece uma vez.",
  );

/**
 * `SessaoOut` — a resposta dos **cinco** endpoints de autenticação, sempre
 * nesta forma. Uma forma só é o que permite ao cliente guardar as cinco numa
 * entrada de cache em vez de ter cinco ramos de Zod. O quinto é o
 * `PATCH /auth/preferencias` (ADR 0016), que devolve a sessão inteira em vez de
 * uma forma própria por este mesmo argumento.
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
 * ## `menu` deixou de ser `unknown[]` a 2026-10-06
 *
 * Era `z.array(z.unknown())` — "há uma lista aqui e eu ainda não sei o que ela
 * leva" —, porque a tabela da ADR 0011 não existia e declarar a tupla dela aqui
 * era inventar o contrato de outra ADR. Agora existe, o `ItemDeMenuOut` está no
 * `types.ts` e esta lista é a **fonte real do menu**: é por aqui que a sidebar
 * sabe o que mostrar, em que ordem, com que nome e para que papel. Medido contra
 * o backend: um `owner` recebe seis itens, um `staff` do mesmo estabelecimento
 * recebe cinco (sem `convites`).
 *
 * Uma lista **vazia** é um estado normal e não um erro, em dois casos medidos:
 * uma sessão sem estabelecimento activo (`escolha_pendente` traz `menu: []`, e
 * aí o `beforeLoad` nem monta o invólucro) e um estabelecimento que esconda tudo
 * o que o papel de quem pede pode ver.
 */
export const sessaoSchema = z
  .object({
    estado: estadoDaSessaoSchema,
    utilizador: utilizadorSchema.nullable(),
    tenant_ativo: estabelecimentoSchema.nullable(),
    tenants: z.array(estabelecimentoSchema),
    menu: z.array(itemDeMenuSchema),
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
 * O corpo do `PATCH /auth/preferencias`. `PreferenciasInRequest` (ADR 0016).
 *
 * Um campo, e **não** há `user_id` — a escrita é sempre sobre quem faz o pedido.
 * Não é uma verificação que o cliente faz: é um argumento que não existe, logo
 * não há caminho para a preferência de outra pessoa. O backend tem o mesmo campo
 * e os mesmos três valores, e o 400 por campo está medido.
 *
 * O `tema` é obrigatório apesar de o método ser `PATCH`, e isso é contrato e não
 * descuido: as views desta casa não validam com `partial=True`, pelo que um
 * corpo vazio é 400. O `COMPONENT_SPLIT_PATCH` do drf-spectacular está desligado
 * para o `types.ts` dizer o mesmo — sem isso, o cliente compilava um `{}` que o
 * servidor recusa.
 */
export const preferenciasSchema = z.object({
  tema: temaSchema,
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

/* ---------------------------------------------------------------------------
 * Convites — o contrato da gestão, que é **outro** do contrato da activação.
 *
 * A activação (acima) é pública e anónima; isto é um recurso com âmbito, só do
 * `owner`, e o que o distingue de tudo o resto deste ficheiro é a assimetria do
 * segredo: o `ConviteCriadoOut` do POST traz o `fragmento` e o `ConviteOut` da
 * listagem **não traz token nenhum, nem forma de o ter** (ADR 0010). Os dois
 * schemas abaixo são essa assimetria escrita: se um dia a listagem começar a
 * devolver um token, é aqui que se vê que ela não devia.
 * ------------------------------------------------------------------------ */

/**
 * O estado de um convite. `ConviteOutEstadoEnum`.
 *
 * **Derivado no servidor dos três timestamps, nunca guardado** (ADR 0010), e é
 * por isso que chega como união fechada: é ele que diz que acções fazem sentido,
 * e um `switch` sobre uma união fechada não pode esquecer um ramo.
 *
 * Medido contra o backend a correr, porque a prosa sobre isto divergia em dois
 * sítios: `reenviar` é aceite num `pendente` **e num `expirado`**; `revogar` é
 * **idempotente** e aceite em tudo o que não foi aceite (incluindo um já
 * revogado, que volta como está, sem escrita). O 409 `convite_nao_pendente` só
 * acontece sobre um convite **aceite** — e, no reenviar, também sobre um
 * revogado. Os detalhes estão no relatório da sessão.
 */
export const estadoDoConviteSchema = z.enum(["pendente", "expirado", "aceite", "revogado"]);

/**
 * `ConviteOut` — um convite como a listagem o mostra. **Sem token.**
 *
 * ## `z.iso.datetime({ offset: true })` e não `z.iso.datetime()`
 *
 * Não é zelo: é a diferença entre este ecrã funcionar e não funcionar, e foi
 * medida. O backend tem `TIME_ZONE = "Europe/Lisbon"` e o DRF serializa
 * `2026-10-13T11:08:06.340331+01:00`; o `z.iso.datetime()` do Zod 4 recusa um
 * offset que não seja `Z` (medido: `false` sem a opção, `true` com ela). Um
 * schema sem o `offset: true` transformava a listagem num `ResponseShapeError`
 * em cada resposta — e a mensagem ("o servidor devolveu algo inesperado") não
 * apontaria para o fuso horário.
 *
 * O `email` é validado como string não vazia e não com `z.email()`, pela razão
 * do `utilizadorSchema`: isto é uma **resposta**, e quem define o que é um email
 * válido é o `EmailField` que já o guardou.
 */
export const conviteSchema = z.object({
  id: z.uuid(),
  email: z.string().min(1),
  papel: papelSchema,
  nome: z.string().min(1),
  estado: estadoDoConviteSchema,
  expira_em: z.iso.datetime({ offset: true }),
  criado_em: z.iso.datetime({ offset: true }),
});

/**
 * `ConviteCriadoOut` — a resposta de criar e de reenviar: o convite **e** o
 * segredo, uma vez.
 *
 * Duas peças porque têm tempos de vida diferentes: o `convite` é o que a
 * listagem volta a mostrar sempre, e o `fragmento` é a única vez que este valor
 * existe fora da cabeça do servidor.
 *
 * O `fragmento` é `<uuid-do-tenant>.<token>` e é **opaco** aqui, como é no corpo
 * da activação: não há regex a exigir o ponto nem `z.uuid()` sobre a primeira
 * metade. Quem compõe o link é o cliente (`${origin}/ativar#${fragmento}`),
 * porque quem conhece a origem da SPA é a SPA; quem conhece o **formato** do
 * segredo é o servidor, e validá-lo aqui era passar a conhecê-lo nos dois sítios.
 */
export const conviteCriadoSchema = z.object({
  convite: conviteSchema,
  fragmento: z.string().min(1),
});

/**
 * `ConviteInRequest` — o corpo do `POST /convites`: quem, com que papel, e com
 * que nome.
 *
 * Tem os **dois** papéis do `credenciaisSchema`, e é por isso que as mensagens
 * vivem aqui: valida o que o formulário submete (e aí as frases aparecem debaixo
 * do input) e valida o corpo antes de ele sair (e aí nunca aparecem, porque o
 * que chega ao segundo papel já passou pelo primeiro).
 *
 * Só **presença e comprimento**, e os dois limites são os do serializer (email
 * 254, nome 150) — medidos, não adivinhados. O **formato** do email não se
 * valida aqui, pela razão de sempre: tem uma definição e é a do Django, que
 * responde 400 por campo com a frase pronta. Duas definições de "email válido"
 * divergiriam na primeira pessoa com um domínio invulgar.
 *
 * E não se valida aqui **nada** sobre duplicados: "já existe um convite para
 * este email" e "esta pessoa já é membro" são leituras à base de dados dentro do
 * âmbito do pedido (ADR 0010, ponto 4) e chegam como erro do campo `email`. Uma
 * verificação local seria a que a corrida perde.
 *
 * O `.trim()` está no email e no nome porque é o que o DRF faz por omissão aos
 * dois: cortá-los aqui é mandar o mesmo valor que o servidor ia usar.
 */
export const conviteParaCriarSchema = z.object({
  email: z.string().trim().min(1, "Escreva o email de quem quer convidar.").max(254),
  nome: z
    .string()
    .trim()
    .min(1, "Escreva o nome desta pessoa neste estabelecimento.")
    .max(150, "O nome não pode ter mais de 150 caracteres."),
  papel: papelSchema,
});

export type Papel = z.output<typeof papelSchema>;
export type Preferencias = z.output<typeof preferenciasSchema>;
export type Estabelecimento = z.output<typeof estabelecimentoSchema>;
export type Utilizador = z.output<typeof utilizadorSchema>;
export type EstadoDaSessao = z.output<typeof estadoDaSessaoSchema>;
export type ItemDeMenu = z.output<typeof itemDeMenuSchema>;
export type RotaDeMenu = z.output<typeof rotaDeMenuSchema>;
export type RegimeDeIva = z.output<typeof regimeDeIvaSchema>;
export type ConfiguracaoDoEstabelecimento = z.output<
  typeof configuracaoDoEstabelecimentoSchema
>;
export type EstabelecimentoParaGuardar = z.input<typeof estabelecimentoParaGuardarSchema>;
export type ItemDeMenuParaGuardar = z.input<typeof itemDeMenuParaGuardarSchema>;
export type MenuParaGuardar = z.input<typeof menuParaGuardarSchema>;
export type Sessao = z.output<typeof sessaoSchema>;
export type Credenciais = z.output<typeof credenciaisSchema>;
export type FormularioDeAtivacao = z.output<typeof formularioDeAtivacaoSchema>;
export type EscolhaDeEstabelecimento = z.output<typeof escolhaDeEstabelecimentoSchema>;
export type Ativacao = z.output<typeof ativacaoSchema>;
export type EstadoDoConvite = z.output<typeof estadoDoConviteSchema>;
export type Convite = z.output<typeof conviteSchema>;
export type ConviteCriado = z.output<typeof conviteCriadoSchema>;
export type ConviteParaCriar = z.output<typeof conviteParaCriarSchema>;

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

/**
 * O papel que convida — **um**, e uma igualdade, nunca uma ordem.
 *
 * A ADR 0010 fixa "convidar é só do `owner` no v1" e diz porquê: o conjunto de
 * papéis é a Q7, está marcado como "não inventes default sem falar com um
 * utilizador real", e escrever uma **ordem** entre papéis na implementação dos
 * convites era responder à Q7 sem ninguém ter perguntado. Por isso isto é uma
 * constante e uma comparação por igualdade, e não um `>=` sobre um índice de
 * hierarquia: no dia em que um `manager` puder convidar, isto passa a ser um
 * conjunto de dois valores e continua a não haver ordem nenhuma.
 *
 * `satisfies Papel` e não `: Papel`: o tipo fica o literal `"owner"`, logo a
 * comparação abaixo é verificada contra o `PapelEnum` gerado — se o backend
 * alguma vez deixar de ter `owner`, isto não compila.
 */
export const PAPEL_QUE_CONVIDA = "owner" satisfies Papel;

/**
 * Este papel convida?
 *
 * **Não é autorização, e é por isso que aceita `null`/`undefined`.** Quem
 * autoriza é o servidor: o `GET /api/v1/convites` responde 403 a quem não é
 * `owner` — medido, com `detail` e **sem `code`**. Isto é a mesma verdade usada
 * para duas coisas de apresentação: esconder a entrada do menu (ADR 0009:
 * "esconder é apresentação, não autorização") e dizer a quem chega por deep link
 * o que se passa, em vez de disparar um pedido que já se sabe recusado.
 *
 * Enquanto a sessão não chegou o papel é `undefined` e a resposta é `false`: o
 * item do menu aparece quando a sessão aparece. Na prática é imediato, porque o
 * `beforeLoad` da rota do shell já leu a sessão antes de montar o invólucro.
 */
export function podeConvidar(papel: Papel | null | undefined): boolean {
  return papel === PAPEL_QUE_CONVIDA;
}

/**
 * Os estados de um convite por extenso, e **o que cada um quer dizer**.
 *
 * O mesmo par `Record`/`Map` do `NOME_DO_PAPEL`, pelas mesmas duas razões: o
 * `Record` sobre a união gerada falha o `pnpm typecheck` nos dois sentidos se o
 * `ConviteOutEstadoEnum` ganhar ou perder um valor, e o `Map` é por onde se lê
 * porque o `security/detect-object-injection` recusa — e bem — um `OBJETO[chave]`
 * com chave dinâmica.
 *
 * A `explicacao` existe porque o `estado` é a coluna que decide que botões a
 * linha tem, e quatro palavras sozinhas não dizem porquê: "aceite" não explica
 * que já não há nada a reenviar. É texto e não um `title`, para estar à vista de
 * quem lê e de quem ouve.
 */
interface NomeDoEstado {
  readonly rotulo: string;
  readonly explicacao: string;
}

const NOME_DO_ESTADO: Record<EstadoDoConvite, NomeDoEstado> = {
  pendente: {
    rotulo: "pendente",
    explicacao: "O link está válido e à espera de ser usado.",
  },
  expirado: {
    rotulo: "expirado",
    explicacao: "Passaram os 7 dias. Reenviar cria um link novo.",
  },
  aceite: {
    rotulo: "aceite",
    explicacao: "Esta pessoa já entrou e já é membro. O convite não tem mais nada a fazer.",
  },
  revogado: {
    rotulo: "revogado",
    explicacao: "Foi cancelado e não volta atrás. Para dar acesso, convide outra vez.",
  },
};

const NOMES_DOS_ESTADOS = new Map<string, NomeDoEstado>(Object.entries(NOME_DO_ESTADO));

const ESTADO_DESCONHECIDO: NomeDoEstado = {
  rotulo: "estado desconhecido",
  explicacao: "Este estado é mais novo do que esta versão da aplicação. Recarregue a página.",
};

export function nomeDoEstadoDoConvite(estado: EstadoDoConvite): NomeDoEstado {
  return NOMES_DOS_ESTADOS.get(estado) ?? ESTADO_DESCONHECIDO;
}
