import { z } from "zod";

/**
 * A search param de `/entrar`: para onde voltar depois de entrar.
 *
 * Um campo só, e é o campo mais perigoso de toda a árvore de rotas — um
 * parâmetro de URL que acaba num `navigate()` é a forma canónica de uma
 * **redirecção aberta**: `/entrar?destino=https://phishing.example/stockflow`
 * dava uma página de login no domínio verdadeiro a mandar a pessoa, depois de
 * entrar, para um clone. A validação aqui não é higiene de tipos, é o controlo.
 *
 * Três condições, e cada uma fecha uma forma do mesmo ataque:
 *
 *  1. **começa por `/`** — um destino absoluto (`https://…`) ou um esquema
 *     (`javascript:…`) não casa, e cai no default;
 *  2. **não começa por `//`** — `//phishing.example` é um URL
 *     *protocol-relative*: o browser trata-o como outro host e o `startsWith("/")`
 *     sozinho deixava-o passar. É a aresta que quase todas as implementações
 *     ingénuas desta verificação têm;
 *  3. **não é o próprio `/entrar`** — não é segurança, é não dar um salto a
 *     mais: `?destino=/entrar` mandava quem acabou de entrar de volta ao ecrã de
 *     entrada, que o reencaminharia outra vez.
 *
 * O `.catch(undefined)` é o que faz um destino recusado **degradar para o
 * default** (a raiz) em vez de explodir dentro do ecrã — a razão decisiva pela
 * qual a ADR 0008 escolheu este router. E é `.optional().catch(undefined)` e não
 * um `.default("/")` pela razão medida no `busca-de-stock.ts`: ausente *é* o
 * default, logo `/entrar` continua a ser um URL limpo, e um campo
 * `.optional().catch(undefined)` devolve a chave **presente** com valor
 * `undefined`, o que garante que o valor cru do URL nunca sobrevive à fusão que
 * o router faz entre a search crua e a saída do validador.
 *
 * O `max(512)` não é uma regra de negócio: é um teto para um parâmetro que vai
 * para o histórico do browser e para o log de acesso do proxy. Um caminho da
 * aplicação com filtros não passa dos 200 caracteres.
 *
 * ## O que **não** viaja aqui
 *
 * O fragmento do convite. Quando o `/ativar` manda entrar primeiro
 * (`convite_exige_sessao`), o que vem nesta search param é só `/ativar` — o
 * token continua no `location.hash`, que não chega ao servidor, não entra no log
 * de acesso do proxy e não viaja em `Referer` (ADR 0010). Pô-lo aqui para o
 * trazer de volta destruía a propriedade inteira, e seria a forma mais fácil de
 * o fazer sem dar por isso.
 */
const CAMINHO_DE_ENTRADA = "/entrar";

export const buscaDeEntradaSchema = z.object({
  destino: z
    .string()
    .max(512)
    .refine((valor) => valor.startsWith("/"), "o destino tem de ser um caminho desta aplicação")
    .refine((valor) => !valor.startsWith("//"), "um caminho protocol-relative aponta para outro host")
    .refine((valor) => !valor.startsWith(CAMINHO_DE_ENTRADA), "o destino não pode ser a entrada")
    .optional()
    .catch(undefined),
});

export type BuscaDeEntrada = z.output<typeof buscaDeEntradaSchema>;
