import type { PT } from "./textos.pt";

/**
 * A copy do módulo `accounts`, em **inglês**, anotada com o tipo do português.
 *
 * Não é servida a ninguém hoje — a lista de línguas tem um elemento — e é
 * verificada pelo compilador mesmo assim: o `tsconfig` inclui `src/` e o
 * `typeof PT` é o contrato. Medido com uma sonda no catálogo do shell.
 *
 * ## Três escolhas de vocabulário
 *
 * **"Establishment"** para `estabelecimento`, como no shell: é a palavra do
 * contrato e distingue-se de **loja** (`Location`, ADR 0005).
 *
 * **"Sign in"/"Sign out"** e não "Log in"/"Log out": é a forma que o resto das
 * mensagens do backend usa ("Too many failed sign-in attempts"), e duas formas
 * para o mesmo gesto no mesmo produto é o que faz uma app parecer montada por
 * duas pessoas que não falaram.
 *
 * **"Activate"** para `activar`: a palavra é a do contrato (`/ativar`,
 * `AtivacaoView`) e descreve o que o link faz — dá acesso a uma conta que já
 * existe, não a cria.
 */
export const EN: typeof PT = {
  entrar: {
    titulo: "Sign in",
    subtitulo: "Use the email you were invited with.",
    aEntrar: "Signing in…",
    semConta:
      "No account? Access is by invitation: ask whoever administers your establishment for a link.",
    escolhaTitulo: "Choose the establishment",
    escolhaSubtitulo: "Your account has access to more than one. Choose where to work now.",
    semEstabelecimentoTitulo: "Account with no establishment",
    semEstabelecimentoCorpo:
      "This account is not linked to any establishment. Ask whoever administers it for an invitation: the invitation arrives as a single-use link, and it is that link that grants access.",
    jaTemSessaoTitulo: "You are already signed in",
    jaTemSessaoCorpo: "Your session is open.",
    abrirApp: "Open StockFlow",
    sessaoDe: "Signed in as",
    erroDeRede: "Could not reach the server",
    contaBloqueada: "Account temporarily locked",
    erroAoEntrar: "Could not sign in",
    erroAoAbrirEstabelecimento: "Could not open that establishment",
    terminarSessao: "Sign out",
  },

  ativar: {
    titulo: "Activate your account",
    subtitulo:
      "You have been invited to an establishment on StockFlow. Choose a password to activate your access — this link only works once.",
    aActivar: "Activating…",
    activarEEntrar: "Activate and sign in",
    regraDaPassword: "At least 12 characters. It cannot be a common password or digits only.",
    repitaAPassword: "Repeat the password",
    conviteInvalidoTitulo: "Invalid invitation",
    linkNaoServe: "This link does not work",
    conviteNaoServe: "This invitation does not work",
    conviteInvalidoCorpo:
      "This invitation is not valid. Ask whoever administers the establishment for a new one.",
    contaJaExiste: "This account already exists",
    conviteDeOutraConta: "This invitation is for another account",
    erroAoActivar: "Could not activate the invitation",
    entrarComEstaConta: "Sign in with this account",
    sairEEntrarComAConvidada: "Sign out and sign in with the invited account",
    irParaEntrada: "Go to sign in",
    sessaoDe: "Signed in as",
  },

  formularios: {
    escrevaOEmail: "Enter your account email.",
    escrevaAPassword: "Enter your password.",
    escolhaUmaPassword: "Choose a password to activate your account.",
    passwordsDiferentes: "The two passwords do not match.",
    escrevaOEmailDeQuemConvida: "Enter the email of the person you want to invite.",
    escrevaONome: "Enter this person's name in this establishment.",
    nomeDemasiadoLongo: "The name cannot be longer than 150 characters.",
  },
};
