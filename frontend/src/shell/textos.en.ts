import type { PT } from "./textos.pt";

/**
 * A copy do invólucro, em **inglês**, anotada com o tipo do português.
 *
 * `typeof PT` é o contrato inteiro: uma chave a faltar dá `TS2741`, uma a mais
 * dá `TS2353`, e uma função de interpolação com outra assinatura também não
 * compila. É mais forte do que qualquer biblioteca de i18n, cuja garantia é um
 * aviso na consola em runtime (ADR 0019, decisão 3).
 *
 * **Este ficheiro é servido desde 2026-10-07**, a um browser que peça inglês. Foi
 * o commit em que a última linha da lista fechada do `check-textos.mjs` saiu — a
 * condição que a ADR 0019 (decisão 9) fixou —, e a partir dele **todo** o
 * catálogo precisa da entrada inglesa, porque o `escolher` é um `Record` sobre a
 * união das línguas.
 *
 * ## Duas escolhas de vocabulário que não são óbvias
 *
 * **"Establishment"** para `estabelecimento`: é a palavra do contrato e do
 * domínio (a casa física — restaurante, pastelaria, café), e "site" ou "location"
 * diriam outra coisa num produto que já distingue estabelecimento de **loja**
 * (`Location`, ADR 0005).
 *
 * **"Overview"** para o grupo `Painel` e **"Management"** para a rota `painel`:
 * em português a mesma palavra serve o grupo das perguntas da manhã e o ecrã do
 * dono, e em inglês "Dashboard" para os dois era a mesma ambiguidade sem a
 * desculpa de ser herdada.
 */
export const EN: typeof PT = {
  marca: "StockFlow",

  saltarParaConteudo: "Skip to content",

  cabecalho: {
    demonstracao: "Demo establishment",
    demonstracaoCurta: "Demo",
    dadosDeDemonstracao: "demo data",
  },

  gaveta: {
    abrir: "Open the menu",
    fechar: "Close the menu",
    descricao: "Choose a StockFlow screen.",
  },

  navegacao: {
    principal: "Main navigation",
    expandir: "Expand the menu",
    recolher: "Collapse the menu",
    semItens: "This establishment has no menu items configured.",
    irParaInicio: "Go to Home",
  },

  rodape: {
    estabelecimento: "Establishment",
    sufixoDeDemonstracao: " (demo)",
    estabelecimentoRecolhido: (nome: string) => `Establishment: ${nome}`,
    trocar: "Switch establishment",
    definicoes: "Settings",
    terminarSessao: "Sign out",
    terminarSessaoDe: (email: string) => `Sign out (${email})`,
    aSair: "Signing out…",
  },

  estados: {
    aCarregar: "Loading…",
    erroTitulo: "This screen could not be opened.",
    erroGenerico: "Unexpected error. Check your connection and try again.",
    tentarOutraVez: "Try again",
    naoEncontradoTitulo: "This screen does not exist",
    naoEncontradoCorpo: "The address you opened does not match any StockFlow screen.",
    voltarAoInicio: "Back to Home",
  },

  publico: {
    tagline: "Stock, expiry and purchasing management for food service.",
    erroTitulo: "Could not continue",
    erroCorpo: "Check your connection and try again.",
  },

  grupos: {
    painel: "Overview",
    inventario: "Inventory",
    compras: "Purchasing",
  },

  rotas: {
    inicio: { rotulo: "Home", pergunta: "What do I have to do today?" },
    painel: {
      rotulo: "Management",
      pergunta: "How much came in, how much went out, and how did the month close?",
    },
    alertas: {
      rotulo: "Alerts",
      pergunta: "What is expiring? What is missing? How much did I throw away?",
    },
    stock: { rotulo: "Stock", pergunta: "What do I have, and how much?" },
    contar: {
      rotulo: "Count",
      pergunta: "Is what is on the shelf what the system says?",
    },
    receber: { rotulo: "Receive", pergunta: "What arrived, and is it correct?" },
  },
};
