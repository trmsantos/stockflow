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
  accoes: {
    guardar: "Save",
    aGuardar: "Saving…",
    desfazer: "Undo",
    aSair: "Signing out…",
    naoGuardado: "What is on the screen is what you wrote, and it is still unsaved.",
  },

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

  definicoes: {
    titulo: "Settings",
    subtitulo:
      "Appearance is yours and follows your account. The rest belongs to this establishment and applies to the whole team.",
    regua: "Settings sections",
  },

  aparencia: {
    rotulo: "Palette",
    explicacao: "Choosing applies it straight away. The whole application changes colour.",
    aCarregar: "Loading your preferences…",
    erroTitulo: "The palette was not saved",
    erroCorpo: "The colours went back to the previous palette. Try again.",
    emUso: "in use",
  },

  estabelecimento: {
    aCarregar: "Loading the establishment configuration…",
    erroDeLeitura: "Could not read the configuration",
    erroAoGuardar: "The configuration was not saved",
    demoTitulo: "This is the demonstration establishment",
    demoCorpo:
      "The data was seeded so you can experiment and does not belong to a real business. The name cannot be changed here; the rest of the configuration changes as in any establishment.",
    nome: "Name",
    nomeExplicacao: "How it appears in the establishment selector and at the top of the screens.",
    regimeDeIva: "VAT regime",
    regimes: {
      normal: {
        nome: "Standard regime",
        efeito:
          "VAT on purchases is deductible, so an item costs the amount before VAT.",
      },
      isento_art_53: {
        nome: "Exempt (art. 53)",
        efeito: "VAT on purchases is not deductible, so it is a cost: it enters the stock value.",
      },
    },
    diaDeNegocio: "The business day starts at",
    diaDeNegocioExplicacao: (hora: string) =>
      `This is the hour that separates one day from the next in the totals and the alerts. With ${hora}, what happens at 01:30 counts towards the previous day, and the month runs from the 1st at ${hora} to the 1st of the next month at the same hour — it is not the fiscal month.`,
    validadesEnfase: "Expiry dates do not change with this hour",
    validadesFim: ": they are the date printed on the packaging.",
    avisoRetroactivoTitulo: "Changing this hour recalculates past days and months",
    avisoRetroactivoCorpo: (antes: string, depois: string) =>
      `Only movements recorded between ${antes} and ${depois} change day.`,
  },

  navegacao: {
    explicacaoInicio:
      "The name, the group and the order of each screen in the sidebar. Hiding a screen takes it out of the menu and does",
    enfaseNao: "not",
    explicacaoFim:
      "take away access — anyone who knows the address still gets in. Access is decided by the role, in the «Who sees» column. Leaving a name or a group blank uses what the application ships.",
    colunas: {
      rota: "Route",
      rotulo: "Name in the menu",
      grupo: "Group",
      quem: "Who sees",
      estado: "In the menu",
      mover: "Order",
    },
    todos: "everyone",
    soO: (papeis: string) => `only the ${papeis}`,
    nomeNoMenuDe: (rota: string) => `Name of ${rota} in the menu`,
    grupoDe: (rota: string) => `Group of ${rota}`,
    subir: (rota: string) => `Move ${rota} up`,
    descer: (rota: string) => `Move ${rota} down`,
    visivel: "Visible",
    escondida: "Hidden",
    erroAoGuardar: "The menu was not saved",
    aCarregar: "Loading the menu routes…",
    erroDeLeitura: "Could not read the routes",
    tabela: "Navigation for this establishment",
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
