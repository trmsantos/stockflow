/**
 * A copy do `src/lib/`, em pt-PT: as frases de erro que a camada de rede escreve,
 * e os nomes das paletas.
 *
 * ## Porque é que uma frase de erro da rede é copy
 *
 * O `mensagemDeErro` tem três ramos e o terceiro é uma frase nossa; o segundo
 * devolve o `message` de um `Error`, que no caso do `ResponseShapeError` também
 * é uma frase nossa. Nenhuma delas vem do servidor, logo nenhuma se traduz
 * sozinha — e as três aparecem debaixo de um `<Alert>` como qualquer outra copy.
 *
 * O que fica **fora** daqui, por não ser lido por ninguém, está declarado no
 * `NAO_E_COPY` do `check-textos.mjs`: as mensagens de Zod sobre a forma da
 * resposta, que vivem no `cause` e nunca no ecrã.
 */
export const PT = {
  erros: {
    tenantDivergente: "O estabelecimento do pedido não é o da sessão.",
    /**
     * O caminho entra na frase porque é o que distingue dois contratos partidos
     * no mesmo ecrã, e quem a lê é quem vai abrir um bug com ela na mão.
     */
    respostaInesperada: (caminho: string) => `A resposta de ${caminho} não tem a forma esperada.`,
    semLigacao: "Verifique a ligação e tente outra vez.",
    csrfAusente: "Esta sessão não tem token CSRF. Recarregue a página e tente outra vez.",
  },

  /**
   * Os nomes e as descrições das três paletas.
   *
   * A descrição não é decoração: um nome de paleta sozinho não diz a quem
   * escolhe o que vai ver, e "meio termo" é precisamente o que ninguém adivinha.
   */
  temas: {
    escuroNome: "Escuro",
    escuroDescricao: "Superfícies quase negras. É o default, e é a paleta desenhada para a copa.",
    meioTermoNome: "Meio termo",
    meioTermoDescricao:
      "Grafite com texto claro. Sobe as superfícies para um monitor com sol ao lado.",
    claroNome: "Claro",
    claroDescricao: "Cinzento frio com tela em cima. Para o escritório e para imprimir um ecrã.",
    desconhecidoNome: "Tema desconhecido",
    desconhecidoDescricao:
      "Esta paleta é mais nova do que esta versão da aplicação. Recarregue a página.",
  },
};
