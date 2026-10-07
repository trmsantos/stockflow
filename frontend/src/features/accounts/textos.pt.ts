/**
 * A copy do módulo `accounts`, em **pt-PT**. É a fonte; o inglês é anotado com
 * `typeof PT` e não compila se divergir (ADR 0019, decisão 3).
 *
 * Por feature e não num ficheiro central, pela razão da ADR 0013 (decisão 5): a
 * copy vive ao lado do `vocabulario.ts` da feature que a usa, e um catálogo
 * central de 800 linhas é um ficheiro que todos os agentes tocam ao mesmo tempo.
 *
 * ## Inclui as mensagens dos formulários, que o gate não vê
 *
 * As frases dos `z.string().min(1, "…")` dos `schemas.ts` são **visíveis** — são
 * o que aparece debaixo de um input — e o `check-textos.mjs` não as apanha: o
 * critério dele é prosa em JSX ou num `title`/`aria-label`, e uma mensagem de Zod
 * é um argumento de função. Está dito aqui em vez de prometido no gate.
 *
 * Elas vêm para cá e não ficam lá por uma razão de forma: o `schemas.ts` tem
 * **dois** papéis para cada uma (valida o que o formulário submete, e valida o
 * corpo antes de sair), e o segundo papel nunca mostra a frase. Traduzi-la num
 * sítio só mantém a propriedade que o docstring do `credenciaisSchema` descreve:
 * uma definição de "credenciais preenchidas", não duas.
 */
export const PT = {
  entrar: {
    titulo: "Entrar",
    subtitulo: "Use o email com que foi convidado para o seu estabelecimento.",
    aEntrar: "A entrar…",
    semConta:
      "Não tem conta? O acesso é por convite: peça um link a quem administra o seu estabelecimento.",
    escolhaTitulo: "Escolha o estabelecimento",
    escolhaSubtitulo:
      "A sua conta tem acesso a mais do que um. Escolha onde quer trabalhar agora.",
    semEstabelecimentoTitulo: "Conta sem estabelecimento",
    semEstabelecimentoCorpo:
      "Esta conta não está associada a nenhum estabelecimento. Peça um convite a quem o administra: o convite chega como um link de uso único, e é esse link que dá o acesso.",
    jaTemSessaoTitulo: "Já tem sessão aberta",
    jaTemSessaoCorpo: "A sua sessão está aberta.",
    abrirApp: "Abrir o StockFlow",
    sessaoDe: "Sessão de",
    erroDeRede: "Não foi possível falar com o servidor",
    contaBloqueada: "Conta temporariamente bloqueada",
    erroAoEntrar: "Não foi possível entrar",
    erroAoAbrirEstabelecimento: "Não foi possível abrir esse estabelecimento",
    terminarSessao: "Terminar sessão",
  },

  ativar: {
    titulo: "Activar a sua conta",
    subtitulo:
      "Foi convidado para um estabelecimento no StockFlow. Escolha uma password para activar o acesso — este link só serve uma vez.",
    aActivar: "A activar…",
    activarEEntrar: "Activar e entrar",
    regraDaPassword:
      "Pelo menos 12 caracteres. Não pode ser uma password comum nem só dígitos.",
    repitaAPassword: "Repita a password",
    conviteInvalidoTitulo: "Convite inválido",
    linkNaoServe: "Este link não serve",
    conviteNaoServe: "Este convite não serve",
    conviteInvalidoCorpo:
      "Este convite não é válido. Peça um convite novo a quem administra o estabelecimento.",
    contaJaExiste: "Esta conta já existe",
    conviteDeOutraConta: "Este convite é de outra conta",
    erroAoActivar: "Não foi possível activar o convite",
    entrarComEstaConta: "Entrar com esta conta",
    sairEEntrarComAConvidada: "Sair e entrar com a conta convidada",
    irParaEntrada: "Ir para a entrada",
    sessaoDe: "Sessão de",
  },

  /**
   * As mensagens de validação dos formulários. Ver o docstring do módulo: são
   * visíveis e o gate não as apanha.
   *
   * A **força** da password não está aqui e não vai estar: quem a impõe são os
   * `AUTH_PASSWORD_VALIDATORS` do servidor, que respondem 400 por campo com as
   * frases todas de uma vez. Reimplementá-la dava duas definições de "password
   * forte", e a de cá ficava desactualizada no dia em que a política mudasse.
   */
  formularios: {
    escrevaOEmail: "Escreva o email da sua conta.",
    escrevaAPassword: "Escreva a sua password.",
    escolhaUmaPassword: "Escolha uma password para activar a sua conta.",
    passwordsDiferentes: "As duas passwords não são iguais.",
    escrevaOEmailDeQuemConvida: "Escreva o email de quem quer convidar.",
    escrevaONome: "Escreva o nome desta pessoa neste estabelecimento.",
    nomeDemasiadoLongo: "O nome não pode ter mais de 150 caracteres.",
  },
};
