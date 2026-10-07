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
  /**
   * Os verbos que aparecem em mais do que uma secção, definidos **uma vez**.
   *
   * Não é uma gaveta de sobras: é a regra de escrita do DESIGN.md — uma acção
   * mantém o mesmo nome em todo o produto —, e três secções com três chaves
   * `guardar` eram três sítios onde ela se podia perder. A frase do erro entra
   * pela mesma razão: o que ela diz ("o que está no ecrã continua por guardar")
   * é verdade de qualquer gravação falhada, e não desta.
   */
  accoes: {
    guardar: "Guardar",
    aGuardar: "A guardar…",
    desfazer: "Desfazer",
    aSair: "A sair…",
    naoGuardado: "O que está no ecrã é o que escreveu, e continua por guardar.",
  },

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
    aTrabalharEm: (nome: string) => `Está a trabalhar em ${nome}.`,
    abrirApp: "Abrir o StockFlow",
    sessaoDe: "Sessão de",
    erroDeRede: "Não foi possível falar com o servidor",
    contaBloqueada: "Conta temporariamente bloqueada",
    erroAoEntrar: "Não foi possível entrar",
    erroAoAbrirEstabelecimento: "Não foi possível abrir esse estabelecimento",
    terminarSessao: "Terminar sessão",
  },

  definicoes: {
    titulo: "Definições",
    subtitulo:
      "A aparência é sua e segue a sua conta. O resto é desta casa e vale para toda a equipa.",
    regua: "Secções das definições",
  },

  aparencia: {
    rotulo: "Paleta",
    explicacao: "Escolher aplica logo. A aplicação inteira muda de cor.",
    aCarregar: "A carregar as suas preferências…",
    erroTitulo: "A paleta não ficou guardada",
    erroCorpo: "As cores voltaram à paleta anterior. Tente outra vez.",
    emUso: "em uso",
  },

  estabelecimento: {
    aCarregar: "A carregar a configuração do estabelecimento…",
    erroDeLeitura: "Não foi possível ler a configuração",
    erroAoGuardar: "A configuração não ficou guardada",
    demoTitulo: "Este é o estabelecimento de demonstração",
    demoCorpo:
      "Os dados foram semeados para experimentar e não são de um negócio real. O nome não se altera aqui; o resto da configuração muda como em qualquer casa.",
    nome: "Nome",
    nomeExplicacao: "Como aparece no seletor de estabelecimento e no topo dos ecrãs.",
    regimeDeIva: "Regime de IVA",
    /**
     * Os dois regimes por extenso, e **o que cada um faz ao custo**. Ficam aqui
     * com as chaves do contrato (`normal`, `isento_art_53`) porque é copy; o
     * `Record<RegimeDeIva, …>` que as consome vive no componente, logo um regime
     * novo no contrato continua a não compilar sem passar por aqui.
     */
    regimes: {
      normal: {
        nome: "Regime normal",
        efeito: "O IVA das compras é dedutível, logo o custo de um artigo é o valor sem IVA.",
      },
      isento_art_53: {
        nome: "Isento (art. 53.º)",
        efeito: "O IVA das compras não é dedutível, logo é custo: entra no valor do stock.",
      },
    },
    diaDeNegocio: "O dia de negócio começa às",
    /**
     * A frase longa do dia de negócio, **uma função** porque interpola a hora em
     * vigor duas vezes. É o que o `typeof PT` compra sobre um
     * `Record<Chave, string>`: a assinatura faz parte do contrato, logo mudar
     * `(hora: string)` numa língua e não na outra não compila.
     */
    diaDeNegocioExplicacao: (hora: string) =>
      `É a hora que separa um dia do seguinte nos totais e nos alertas. Com ${hora}, o que acontece à 01:30 conta no dia anterior, e o mês vai do dia 1 às ${hora} ao dia 1 do mês seguinte à mesma hora — não é o mês fiscal.`,
    /**
     * A ênfase fica em partes nomeadas e não numa string só, porque a frase tem
     * um `<strong>` no meio e o DESIGN.md §2 escolheu-o: é a parte que alguém a
     * ler em diagonal tem de levar. Juntá-las perdia o negrito; pô-las numa
     * string com HTML pedia um `dangerouslySetInnerHTML`, que o
     * `eslint.config.js` proíbe.
     */
    validadesEnfase: "As validades não mudam com esta hora",
    validadesFim: ": são a data impressa na embalagem.",
    avisoRetroactivoTitulo: "Mudar esta hora recalcula os dias e os meses já passados",
    avisoRetroactivoCorpo: (antes: string, depois: string) =>
      `Só mudam de dia os movimentos registados entre as ${antes} e as ${depois}.`,
  },

  navegacao: {
    /**
     * A frase da secção, em três partes porque tem um `<strong>` no meio. A
     * ênfase é a parte que não se pode perder — é ela que diz que esconder um
     * ecrã **não** é retirar o acesso — e por isso não se dissolve numa string
     * única.
     */
    explicacaoInicio:
      "O nome, o grupo e a ordem de cada ecrã na barra lateral. Esconder um ecrã tira-o do menu e",
    enfaseNao: "não",
    explicacaoFim:
      "retira o acesso — quem souber o endereço continua a entrar. Quem decide o acesso é o papel, na coluna «Quem vê». Deixar um nome ou um grupo em branco usa o que a aplicação traz.",
    colunas: {
      rota: "Rota",
      rotulo: "Nome no menu",
      grupo: "Grupo",
      quem: "Quem vê",
      estado: "No menu",
      mover: "Ordem",
    },
    todos: "todos",
    soO: (papeis: string) => `só o ${papeis}`,
    nomeNoMenuDe: (rota: string) => `Nome de ${rota} no menu`,
    grupoDe: (rota: string) => `Grupo de ${rota}`,
    subir: (rota: string) => `Subir ${rota}`,
    descer: (rota: string) => `Descer ${rota}`,
    visivel: "Visível",
    escondida: "Escondida",
    erroAoGuardar: "O menu não ficou guardado",
    aCarregar: "A carregar as rotas do menu…",
    erroDeLeitura: "Não foi possível ler as rotas",
    tabela: "Navegação desta casa",
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
  /**
   * Os rótulos dos campos. Uma secção própria porque os mesmos aparecem na
   * entrada e na activação, e porque nenhum deles tem acento — ou seja, nenhum
   * deles é visto pelo `check-textos.mjs` (regra 1b, cobertura parcial). Estão
   * aqui porque alguém os leu, não porque um gate os apanhou.
   */
  /**
   * Os nomes e as perguntas das quatro secções das Definições.
   *
   * Em chaves planas e não em dois `Record` aninhados, porque é o componente que
   * guarda os `Record<SecaoDeDefinicoes, string>` — e é ele que não compila se
   * aparecer uma quinta secção. O catálogo guarda palavras; a exaustividade é do
   * `secoes.ts`.
   */
  secoes: {
    aparenciaRotulo: "Aparência",
    aparenciaPergunta: "Como é que a aplicação se vê?",
    estabelecimentoRotulo: "Estabelecimento",
    estabelecimentoPergunta: "Como é que esta casa está configurada?",
    navegacaoRotulo: "Navegação",
    navegacaoPergunta: "Que ecrãs é que a equipa vê, e com que nomes?",
    equipaRotulo: "Equipa",
    equipaPergunta: "Quem tem acesso, e quem está por entrar?",
  },

  /** As duas recusas que a autenticação escreve por si (ver o `erros.ts`). */
  recusas: {
    semToken: "A página perdeu o token de segurança. Recarregue e tente outra vez.",
    semServidor: "Não foi possível falar com o servidor. Verifique a ligação e tente outra vez.",
  },

  /**
   * A validade de um convite, em linguagem de prazo e não de data: o que quem lê
   * a lista quer saber é se ainda dá tempo.
   */
  validade: {
    expirouHoje: "expirou hoje",
    expirouQuando: (quando: string) => `expirou ${quando}`,
    acabaHoje: "acaba hoje",
    expiraQuando: (quando: string) => `expira ${quando}`,
    validoAte: (data: string) => `válido até ${data}`,
    semPrazo: "sem prazo",
    /** No `title`: a data exacta, para quem quer o dia e não o prazo. */
    linkExpiraA: (data: string) => `O link expira a ${data}`,
  },

  /**
   * O vocabulário do domínio das contas: os papéis e os estados de um convite.
   *
   * Em chaves planas, como no `secoes`: os `Record` sobre as uniões geradas ficam
   * no `schemas.ts`, que é onde um valor novo no contrato tem de deixar de
   * compilar. O catálogo guarda palavras.
   */
  convite: {
    criar: "Criar convite",
    aCriar: "A criar…",
    erroAoCriar: "Não foi possível criar o convite",
    nome: "Nome",
    nomePista: "Como aparece na lista de membros deste estabelecimento.",
    papel: "Papel",
    /**
     * Os dois `placeholder` são **exemplos**, e por isso traduzem-se: um
     * `pessoa@exemplo.pt` num ecrã inglês lê-se como um endereço real de um
     * domínio português. O nome segue a mesma regra.
     */
    exemploDeEmail: "pessoa@exemplo.pt",
    exemploDeNome: "Ana Silva",
  },

  segredo: {
    criado: "Convite criado. Entregue este link a quem convidou.",
    reenviado: "Link novo. O link anterior deixou de funcionar.",
    /**
     * A frase do destinatário, em três partes porque o email vai em mono e com
     * `translate="no"`: um email traduzido pelo browser é uma pessoa que não se
     * encontra, e dissolver a frase numa string só tirava-lhe esse invólucro.
     */
    para: "Para",
    como: ", como",
    semEmail: ". Não é enviado nenhum email: copie o link e entregue-o a essa pessoa.",
    linkDeActivacao: "Link de activação",
    copiado: "Copiado",
    copiarLink: "Copiar link",
    /**
     * O atalho leva espaços que não quebram (`\u00a0`): um "Ctrl + C" partido ao
     * fim da linha deixa de ser um atalho e passa a ser duas letras perdidas.
     */
    copiaFalhou:
      "O browser não deixou copiar automaticamente. Seleccione o texto do campo e copie com Ctrl\u00a0+\u00a0C.",
    naoVoltaAAparecer: "Este link não volta a aparecer.",
    seOPerderInicio: "Se o perder, use",
    seOPerderFim: "na linha do convite — isso cria um link novo e invalida este.",
    jaGuardei: "Já guardei",
  },

  convites: {
    colunas: {
      email: "Email",
      nome: "Nome",
      papel: "Papel",
      estado: "Estado",
      validade: "Link",
      criado: "Criado",
      accoes: "Acções",
    },
    tabela: "Convites enviados, do mais recente para o mais antigo",
    aCarregar: "A carregar os convites…",
    revogarEFinal: "Revogar é final.",
    confirmar: "Confirmar",
    aRevogar: "A revogar…",
    cancelar: "Cancelar",
    /**
     * O que estes `sr-only` acrescentam ao nome acessível do botão: numa tabela
     * de dez linhas, dez botões chamados "Reenviar" são dez botões
     * indistinguíveis para quem navega por lista de controlos. Começam com
     * espaço porque continuam o texto do botão.
     */
    daRevogacaoDe: (email: string) => ` a revogação do convite de ${email}`,
    doConviteDe: (email: string) => ` o convite de ${email}`,
    reenviar: "Reenviar",
    aReenviar: "A reenviar…",
    reenviarPista: "Cria um link novo e invalida o anterior",
    revogar: "Revogar",
    revogarPista: "Cancela o convite. Pede confirmação, e é final.",
  },

  equipa: {
    erroDaSessao: "Não foi possível ler a sessão",
    estadoMudou: "O estado deste convite mudou",
    erroDaOperacao: "Não foi possível concluir esta operação",
    erroAoCarregar: "Não foi possível carregar os convites",
    acessoPorConvite: "O acesso é sempre por convite.",
    noTotal: "no total",
    revogado: (email: string) => `Convite de ${email} revogado. O link deixou de funcionar.`,
    /**
     * O pé da lista: quantos, de quantos, a ordem e o prazo.
     *
     * Uma função e não quatro chaves porque a frase **é** uma: muda de forma no
     * singular, e o "de N" só aparece quando a página está truncada. Os
     * `\u00a0` são espaços que não quebram — o `7 dias` não se separa no fim de
     * uma linha —, e escrevem-se assim porque um `&nbsp;` numa string é texto e
     * não uma entidade: só o JSX o interpreta.
     */
    rodapeDaLista: (quantos: number, total: number | null) => {
      const contagem = quantos === 1 ? "1 convite" : `${String(quantos)} convites`;
      const de = total === null ? "" : ` de ${String(total)}`;
      return `${contagem}${de} · mais recentes primeiro · um link de convite é válido 7\u00a0dias`;
    },
    vazioTitulo: "Ainda não convidou ninguém",
    vazioCorpo:
      "Só quem tem um convite consegue entrar neste estabelecimento. O link aparece aqui uma vez, e é entregue por si — não é enviado nenhum email.",
    convidarAlguem: "Convidar alguém",
    vazioPrazo: "Um convite é válido 7\u00a0dias e pode ser revogado a qualquer momento.",
    semPermissaoTitulo: "Só o dono do estabelecimento gere convites",
    semPapel:
      "Esta sessão não tem um papel neste estabelecimento. Recarregue a página e tente outra vez.",
    papelNaoConvida: (papel: string) =>
      `Neste estabelecimento o seu papel é ${papel}, e convidar é do dono. Peça a quem o administra para criar o convite.`,
    decideOServidor: "Quem decide isto é o servidor, não este ecrã.",
  },

  vocabulario: {
    papelOwner: "dono",
    papelManager: "gerente",
    papelStaff: "colaborador",
    estadoPendente: "pendente",
    estadoPendenteExplicacao: "O link está válido e à espera de ser usado.",
    estadoExpirado: "expirado",
    estadoExpiradoExplicacao: "Passaram os 7 dias. Reenviar cria um link novo.",
    estadoAceite: "aceite",
    estadoAceiteExplicacao:
      "Esta pessoa já entrou e já é membro. O convite não tem mais nada a fazer.",
    estadoRevogado: "revogado",
    estadoRevogadoExplicacao:
      "Foi cancelado e não volta atrás. Para dar acesso, convide outra vez.",
    estadoDesconhecido: "estado desconhecido",
    estadoDesconhecidoExplicacao:
      "Este estado é mais novo do que esta versão da aplicação. Recarregue a página.",
  },

  campos: {
    email: "Email",
    password: "Password",
  },

  formularios: {
    horaMalEscrita: "A hora escreve-se como HH:MM, por exemplo 04:00.",
    escrevaONomeDoEstabelecimento: "Escreva o nome do estabelecimento.",
    nomeDoEstabelecimentoLongo: "O nome não pode ter mais de 200 caracteres.",
    nomeDoGrupoLongo: "O nome do grupo não pode ter mais de 50 caracteres.",
    ordemInteira: "A ordem é um número inteiro.",
    ordemNegativa: "A ordem não pode ser negativa.",
    ordemGrande: "A ordem não pode passar de 32767.",
    rotuloLongo: "O rótulo não pode ter mais de 50 caracteres.",
    rotaRepetida: "Há uma rota repetida na configuração. Cada rota aparece uma vez.",
    escrevaOEmail: "Escreva o email da sua conta.",
    escrevaAPassword: "Escreva a sua password.",
    escolhaUmaPassword: "Escolha uma password para activar a sua conta.",
    passwordsDiferentes: "As duas passwords não são iguais.",
    escrevaOEmailDeQuemConvida: "Escreva o email de quem quer convidar.",
    escrevaONome: "Escreva o nome desta pessoa neste estabelecimento.",
    nomeDemasiadoLongo: "O nome não pode ter mais de 150 caracteres.",
  },
};
