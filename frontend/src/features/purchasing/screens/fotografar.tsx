import { Link, useNavigate, useSearch } from "@tanstack/react-router";
import { ArrowLeft, FilePlus2, Truck } from "lucide-react";
import { useState } from "react";

import { ErroAoCarregar } from "@/components/erro-ao-carregar";
import { EstadoVazio } from "@/components/estado-vazio";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
// A **única** porta para outra feature (ADR 0008, decisão 2): o `api.ts` do
// `accounts`. É de lá que vem a resposta a "em que estabelecimento é que esta
// sessão está?" e a troca de âmbito que o código QR pode pedir — e não de um
// pedido novo escrito aqui, que seria uma segunda forma de trocar de casa.
import { useEscolherEstabelecimento, useSessao } from "@/features/accounts/api";
import { formatTime } from "@/lib/format";
import {
  useAbrirDocumentoComFicheiro,
  useAbrirSlotDeCaptura,
  useAnexarFicheiro,
  useDescartarDocumento,
  useDocumento,
  useDocumentos,
  useFecharDocumento,
} from "../api-de-documentos";
import { PainelDeLeitura } from "../components/painel-de-leitura";
import { PainelDoDocumento } from "../components/painel-do-documento";
import { PonteDeCaptura } from "../components/ponte-de-captura";
import {
  EsqueletoDaTabelaDeDocumentos,
  TabelaDeDocumentos,
} from "../components/tabela-de-documentos";
import { TrocaDeEstabelecimento } from "../components/troca-de-estabelecimento";
import { ZonaDeFicheiro } from "../components/zona-de-ficheiro";
import { urlDaPonte } from "../ponte-de-captura";
// `fraseDaRecusa` e não o `mensagemDeErro` do `lib/api/errors` em **nenhum** dos
// quatro sítios, e foi medido: com o `mensagemDeErro`, um 500 sem corpo JSON
// punha "500 em /documents" dentro do banner de erro deste ecrã. O leitor desta
// feature é o que sabe que uma recusa sem `detail` tem de virar uma frase de
// produto.
import { desenhoDaRecusa, fraseDaRecusa, statusDaRecusaDeDocumento } from "../recusas-de-documento";
import { textos } from "../textos";

/**
 * `/receber/fotografar` — a entrada do documento de fornecedor.
 *
 * ## O que este ecrã era, e porque deixou de o ser
 *
 * Era um placeholder de 117 linhas a dizer que não havia câmara nem envio de
 * ficheiro, e a razão escrita nele era boa: *"tirar a fotografia e não acontecer
 * nada é a única coisa pior do que não ter o botão"*. A fatia 1 da ADR 0021
 * removeu essa razão — os endpoints existem, o documento entra, é guardado e é
 * lido — e um ecrã que continuasse a dizer que não há caminho passava a ser ele
 * a mentir.
 *
 * ## A zona de ficheiro resolve as duas pontas, e é por isso que é uma só
 *
 * Um `<input type="file" capture="environment">`: no computador abre o
 * explorador e aceita o PDF que o fornecedor mandou por email; num telemóvel
 * abre a câmara de trás. Uma rota, não duas (ADR 0020, decisão 7), e o que varia
 * com a largura é ordem e ênfase — layout, nunca routing (ADR 0008, decisão 1).
 *
 * ## Dois caminhos de entrada, e o segundo existe por uma razão do backend
 *
 * Um ficheiro **fecha-se a si mesmo**: um PDF de dez páginas é um documento
 * completo e o número de páginas sabe-se do ficheiro (ADR 0021, decisão 9), logo
 * `POST /documents` com ficheiro nasce fechado e não aceita um segundo. Isso
 * resolve o computador num gesto e **não** resolve uma fatura de duas folhas
 * fotografada folha a folha — que é precisamente o caso de campo deste ecrã.
 * Para esse existe o slot: `POST /documents` vazio nasce aberto, cada fotografia
 * é um `POST .../files`, e uma pessoa diz quando acabou.
 *
 * É também o que torna os oito estados **alcançáveis**: sem abrir um slot não há
 * `aguarda_captura`, não há `expirado`, e as recusas `documento_sem_paginas` e
 * `paginas_excedidas` não têm como acontecer. Um ramo que nada exercita é um ramo
 * que ninguém sabe se funciona.
 *
 * ## A ponte computador→telemóvel, construída a 2026-10-08
 *
 * Onde estava **uma linha a dizer que o bloco do QR não existia e porquê** está
 * agora o bloco. A razão que lá estava era verdadeira — faltava escolher a
 * biblioteca — e deixou de ser: é o `uqr`, zero dependências, e o código é
 * desenhado a partir da matriz dele com os tokens desta casa
 * (`components/codigo-de-captura.tsx`).
 *
 * O fluxo é o da ADR 0020 (decisão 1 do corpo, restaurada pela adenda 2):
 * o computador abre um **slot** → o código leva este mesmo caminho com dois
 * uuids em search params → o ecrã sonda o documento a 2 s → cada página que o
 * telemóvel envia aparece na lista de páginas → quem está com o telemóvel diz
 * *"acabei"* e o documento fecha. **Não há segredo no código**: o telemóvel entra
 * uma vez com a conta de quem o usa, e quem chegar ao link sem sessão passa pelo
 * `/entrar` e volta, pelo mesmo *login com retorno* que o `/ativar` já usa.
 *
 * ## O mesmo ecrã serve as duas pontas, e o que varia é o que se esconde
 *
 * Um telemóvel que chegue **pelo código** traz o `?estabelecimento=`, e é esse o
 * sinal — não o tamanho do ecrã, não o `user agent`. A quem chega assim, este
 * ecrã mostra a captura e pouco mais: esconde o bloco do código (seria o
 * telemóvel a convidar-se a si próprio), a lista de documentos, o painel de
 * leitura e os três caminhos de entrada, que são conteúdo de escritório. É
 * apresentação e não routing (ADR 0008, decisão 1): uma rota, dois enquadramentos.
 *
 * O que **não** se esconde é o botão do documento de várias folhas. Se o código
 * expirou enquanto a pessoa atravessava o armazém, abrir um documento ali e
 * fotografar as duas folhas é precisamente o fluxo de campo — esconder isso dava
 * um beco sem saída no sítio onde há menos paciência para um.
 *
 * ## E o uuid do estabelecimento tem trabalho
 *
 * Se o âmbito activo da sessão do telemóvel não é o do código, o ecrã **pede** a
 * troca com um toque e nunca a faz em silêncio (ADR 0020, decisão 2b). Enquanto
 * ela não acontecer o documento não é pedido: lê-lo no âmbito errado dava um 404
 * genérico — a resposta certa do servidor — e o ecrã diria *"este documento já
 * não está aqui"* a quem está a olhar para o código que o abriu.
 *
 * ## E a terceira via continua escrita
 *
 * Os três caminhos por onde a mercadoria entra numa cozinha portuguesa ficam no
 * fundo, onde não pagam pixéis acima da dobra: *"um escritório sem ficheiro
 * nenhum usa a terceira via que o ecrã já descreve hoje: a receção à mão"* (ADR
 * 0020, decisão 7). É conteúdo de sessão 0 e é a lista que se quer que o dono
 * corrija.
 *
 * ## Dois erros em dois sítios, e porque não um só
 *
 * As escritas deste ecrã são cinco e dividem-se em duas famílias: as que levam
 * **um ficheiro** (abrir com ficheiro, anexar) e as que agem **sobre o
 * documento** (abrir slot, fechar, descartar). Uma recusa da primeira família
 * pertence ao campo; uma da segunda pertence ao painel. Um `erro` só no topo
 * mandava alguém procurar o problema do ficheiro no sítio errado — e é
 * exactamente a distinção que os quatro códigos do servidor pedem.
 */
export function EcraDeFotografar() {
  const busca = useSearch({ from: "/app/receber/fotografar" });
  // `from` é o **caminho** da rota e não o id dela: o `useSearch` acima lê por
  // id (`/app/...`) e o `useNavigate` tipa-se pelo caminho. Dois nomes para a
  // mesma rota, e o compilador diz qual é qual.
  const navegar = useNavigate({ from: "/receber/fotografar" });
  const escolhido = busca.documento ?? null;

  /**
   * O que repõe o `<input type="file">`.
   *
   * Um input de ficheiro guarda o que foi escolhido, e sem o remontar escolher
   * **o mesmo** ficheiro outra vez não dispara `change` — que é exactamente o
   * que alguém faz depois de uma falha de rede. Conta-se aqui, e não dentro da
   * zona, porque é o ecrã que sabe quando uma escrita acabou.
   */
  const [envios, setEnvios] = useState(0);

  /**
   * De onde veio o pedido de abrir um slot, para a recusa aparecer **ao lado do
   * botão que a provocou**.
   *
   * Há dois botões que abrem a mesma coisa — o do documento de várias folhas, na
   * coluna do ficheiro, e o da ponte — e eles estão visíveis ao mesmo tempo num
   * computador. Com uma frase de erro só, derivada de `abrirSlot.isError`, a
   * recusa aparecia nos **dois** sítios: a mesma frase duas vezes, uma delas a
   * dois dedos de um botão que ninguém tocou. É a mesma razão pela qual este ecrã
   * já separa o erro do ficheiro do erro do documento.
   */
  const [ondeAbriu, setOndeAbriu] = useState<"campo" | "ponte">("campo");

  /**
   * O estabelecimento que o código QR nomeia, ou `null` quando se chegou aqui
   * pelo menu.
   *
   * É também o sinal de "cheguei pelo código", e é um sinal **do URL** e não do
   * aparelho: ramificar por largura ou por `user agent` era o que a decisão 1 da
   * ADR 0008 recusa.
   */
  const doCodigo = busca.estabelecimento ?? null;

  const sessao = useSessao();
  const estabelecimentoAtivo = sessao.data?.tenant_ativo ?? null;
  const trocar = useEscolherEstabelecimento();

  /**
   * A troca de âmbito que o código pede, ou `null` quando não há nada a pedir.
   *
   * Um objecto e não um booleano, para os dois nomes virem **com** a condição:
   * um `precisaDeTrocar` separado obrigava a reafirmar os mesmos três testes no
   * JSX para o compilador saber que o estabelecimento activo não é nulo, e três
   * testes repetidos divergem.
   *
   * Só é verdade quando se sabem **as duas** coisas: o código diz uma casa e a
   * sessão já disse em qual está. Enquanto a sessão não chegou não se afirma nada
   * — e na prática ela já chegou, porque o `beforeLoad` do invólucro não monta
   * este ecrã sem ela.
   */
  const troca =
    doCodigo !== null && estabelecimentoAtivo !== null && estabelecimentoAtivo.id !== doCodigo
      ? {
          doCodigo,
          atual: estabelecimentoAtivo.nome,
          /** O nome da casa do código, ou `null` se esta conta não pertencer a ela. */
          nome: sessao.data?.tenants.find((candidato) => candidato.id === doCodigo)?.nome ?? null,
        }
      : null;

  const documentos = useDocumentos();
  // Não se pede o documento enquanto o âmbito for o errado: o pedido levava um
  // 404 genérico e o ecrã respondia à pergunta errada.
  const { consulta: consultaDoDocumento, desistiu } = useDocumento(
    troca === null ? escolhido : null,
  );
  const documento = consultaDoDocumento.data;

  const abrirComFicheiro = useAbrirDocumentoComFicheiro();
  const abrirSlot = useAbrirSlotDeCaptura();
  const anexar = useAnexarFicheiro();
  const fechar = useFecharDocumento();
  const descartar = useDescartarDocumento();

  /**
   * O slot **ainda está vazio**: zero páginas e dentro dos quinze minutos. É o
   * único estado em que o `expires_at` quer dizer algo.
   */
  const aVazio = documento?.state === "aguarda_captura";

  /**
   * O documento **aceita mais páginas**, e isto é `closed_at` e não um estado.
   *
   * ## O defeito que esta linha corrige, medido ponta a ponta
   *
   * Era `documento.state === "aguarda_captura"`, aqui e no painel, e parecia
   * certo — é o estado que o ecrã chama "aberto". **Não é**: o servidor deriva
   * `aguarda_captura` de *zero páginas* (`models.estado_do_documento`, ramo 2), e
   * no instante em que a primeira folha chega o documento passa a
   * `a_normalizar` com `closed_at` ainda nulo. Com o predicado antigo, nessa
   * mesma fracção de segundo:
   *
   *  - a zona de ficheiro voltava a dizer "ficheiro do documento" em vez de
   *    "juntar a página seguinte", logo a **segunda folha abria um documento
   *    novo** em vez de ser a página 2;
   *  - o botão *"Acabei — não vêm mais páginas"* desaparecia, logo **ninguém
   *    conseguia fechar o documento** pelo ecrã;
   *  - e o código QR desaparecia a meio da captura.
   *
   * Isto é, a fatura de duas folhas — o caso que o slot existe para servir (ADR
   * 0020, decisão 1) — não era possível pela interface. Apanhado com uma sonda
   * que abre um slot, envia uma página pelos endpoints normais e lê o DOM do
   * computador cinco segundos depois, sem recarregar nada: o estado mudava para
   * "a preparar" e o botão de terminar ia-se.
   *
   * O que o contrato dá é o `closed_at`, e é ele que diz "não vêm mais páginas"
   * (`models.InvoiceDocument`: *"`closed_at` é «não vêm mais páginas», e é o que
   * dispara a extração"*). Os dois estados que não têm `closed_at` e também não
   * aceitam escrita ficam fora à mão: `expirado` (slot vazio passados os quinze
   * minutos) e `descartado` (alguém disse que não interessa).
   */
  const aceitaPaginas =
    documento?.closed_at === null &&
    documento.state !== "expirado" &&
    documento.state !== "descartado";
  const noTeto = documento !== undefined && documento.page_count >= documento.page_limit;

  // A recusa de uma escrita **com ficheiro**: ou se está a abrir um documento, ou
  // se está a anexar a um que já está aberto, nunca as duas.
  const erroDoFicheiro: unknown = aceitaPaginas ? anexar.error : abrirComFicheiro.error;
  const desenhoDoFicheiro = desenhoDaRecusa(erroDoFicheiro);

  // A recusa de uma escrita **sobre o documento**. O `reset` cruzado em cada
  // acção é o que garante que há no máximo uma a falar: sem ele, um erro de
  // ficheiro de há dois minutos continuava no ecrã debaixo de um fecho que
  // correu bem.
  const erroDoDocumento: unknown = fechar.error ?? descartar.error;
  const desenhoDoDocumento = desenhoDaRecusa(erroDoDocumento);

  const documentoPerdido =
    desenhoDoFicheiro === "documento_perdido" || desenhoDoDocumento === "documento_perdido";

  /**
   * O endereço que o código QR transporta, ou `null` quando não há nada para
   * apontar.
   *
   * O estabelecimento é o **da sessão** e nunca o do search param: o código tem
   * de nomear a casa que é de facto dona do documento, e quando os dois
   * divergem o ecrã nem chega aqui — pede a troca primeiro.
   *
   * Sem um `documento !== undefined` à frente, e isso não é descuido: o `aberto`
   * é um alias de `documento?.state === "aguarda_captura"`, e o TypeScript
   * estreita o `documento` a partir dele (análise de condições com alias). O
   * `pnpm lint` recusa o teste redundante — e tem razão, porque um teste que é
   * sempre verdadeiro lê-se como se pudesse ser falso.
   */
  const urlDaCaptura =
    aceitaPaginas && estabelecimentoAtivo !== null
      ? urlDaPonte({
          origem: window.location.origin,
          estabelecimento: estabelecimentoAtivo.id,
          documento: documento.id,
        })
      : null;

  function escolher(id: string) {
    void navegar({ search: (anterior) => ({ ...anterior, documento: id }) });
  }

  /**
   * Limpa a escolha **omitindo** a chave em vez de a pôr a `undefined`: com
   * `exactOptionalPropertyTypes` as duas coisas não são a mesma, e o filtro do
   * `/receber` tem de sobreviver — é ele que o link de voltar leva.
   *
   * O `estabelecimento` sobrevive pela razão oposta e igualmente concreta: quem
   * chegou pelo código e abre outro documento continua a ser alguém com um
   * telemóvel na mão a fotografar uma fatura. Deixá-lo cair devolvia-lhe o ecrã
   * de escritório inteiro — a lista, o painel de leitura, os três caminhos de
   * entrada — a meio da tarefa.
   */
  function limparEscolha() {
    void navegar({
      search: (anterior) => ({
        ...(anterior.estado === undefined ? {} : { estado: anterior.estado }),
        ...(anterior.estabelecimento === undefined
          ? {}
          : { estabelecimento: anterior.estabelecimento }),
      }),
    });
  }

  /** Abrir um slot, e lembrar **qual** dos dois botões o pediu. */
  function abrirSlotDe(onde: "campo" | "ponte") {
    setOndeAbriu(onde);
    abrirSlot.mutate(undefined, {
      onSuccess: (criado) => {
        escolher(criado.id);
      },
    });
  }

  function aoEscolherFicheiro(ficheiro: File) {
    fechar.reset();
    descartar.reset();
    const terminar = () => {
      setEnvios((anteriores) => anteriores + 1);
    };

    if (aceitaPaginas && escolhido !== null) {
      anexar.mutate({ documento: escolhido, ficheiro }, { onSettled: terminar });
      return;
    }
    abrirComFicheiro.mutate(ficheiro, {
      onSuccess: (criado) => {
        escolher(criado.id);
      },
      onSettled: terminar,
    });
  }

  const linhas = documentos.data?.results;
  const total = documentos.data?.count ?? 0;
  const truncada = documentos.data !== undefined && total > documentos.data.results.length;

  /**
   * Chegou-se aqui **pelo código QR**, logo este ecrã é a captura e pouco mais.
   *
   * É um sinal do URL e não do aparelho. Um computador com este parâmetro no
   * endereço vê o mesmo enquadramento, e isso é a propriedade certa: quem o tem
   * no URL está a fazer o trabalho que o código começou.
   */
  const soCaptura = doCodigo !== null;

  return (
    // Sem `max-w`: as duas tabelas deste ecrã usam a largura toda da área de
    // conteúdo (DESIGN.md §4), e as regiões encostam às arestas e separam-se por
    // réguas de 1px. A prosa que existe leva `max-w-prose` por dentro.
    <section className="flex w-full min-w-0 flex-1 flex-col">
      <div className="flex flex-col gap-1 px-celula-x py-3">
        <Button asChild variant="ghost" className="-ml-2 self-start">
          <Link to="/receber" search={{ estado: busca.estado }}>
            <ArrowLeft aria-hidden="true" />
            {textos.comuns.receber}
          </Link>
        </Button>
        <h1 className="text-2xl font-semibold text-balance">{textos.comuns.novoDocumento}</h1>
        {/* A pergunta do ecrã muda com a ponta em que se está: num escritório é
            "por onde é que o documento entra"; com o telemóvel na mão, depois de
            ler o código, é "fotografe folha a folha e diga quando acabou". A
            mesma frase nas duas pontas falava do explorador de ficheiros a quem
            está a segurar uma caixa. */}
        <p className="max-w-prose text-pretty text-sm text-muted-foreground">
          {soCaptura ? textos.documento.ponte.noTelemovel : textos.fotografar.pergunta}
        </p>
      </div>

      {/* O âmbito errado bloqueia tudo o que vem abaixo, e por isso é o único
          que aparece: sem a troca, a zona de ficheiro abria um documento **na
          casa errada** em vez de juntar uma página ao que o código nomeia. */}
      {troca === null ? null : (
        <div className="px-celula-x py-4">
          <TrocaDeEstabelecimento
            nomeDoCodigo={troca.nome}
            nomeAtual={troca.atual}
            aTrocar={trocar.isPending}
            erro={trocar.isError ? fraseDaRecusa(trocar.error) : null}
            aoTrocar={() => {
              trocar.mutate({ tenant_id: troca.doCodigo });
            }}
          />
        </div>
      )}

      {/* **A troca de âmbito esconde tudo o que escreve.** Sem ela, a zona de
          ficheiro abria um documento na casa errada em vez de juntar uma
          página ao documento que o código nomeia — e um documento aberto na
          casa errada é trabalho perdido que ninguém vê perder-se. */}
      {troca !== null ? null : (
        <>
          {/* As duas entradas, em **duas bandas de largura inteira** e não em
              duas colunas. A zona de ficheiro primeiro, a um ecrã de distância
              de nada; a ponte logo abaixo, separada pela mesma régua de 1px.
              O que varia com a largura é ordem e ênfase — layout e nunca routing
              (ADR 0020, adenda 2, a corrigir o `hidden md:block` da decisão 7:
              um tablet de balcão em retrato é mais estreito que `md` e é
              precisamente onde mais se quer a ponte).
              **Foi uma grelha de duas colunas durante uma fotografia**, com a
              ponte num `19rem` à direita, e a fotografia mostrou porque não
              serve: com um documento aberto, o bloco da ponte mede ~570px e a
              zona de ficheiro ~125px, logo a coluna da esquerda ficava com 460px
              de `surface` vazia e uma régua vertical a correr ao lado dela — um
              ecrã que se lê como inacabado. Duas bandas não têm esse problema
              porque cada uma tem a altura do seu conteúdo, e a ponte usa a
              largura que tem: o código à esquerda e o texto ao lado dele. */}
          <div className="flex flex-col border-y border-border bg-surface">
            <div className="flex flex-col gap-3 px-celula-x py-4">
              <ZonaDeFicheiro
                paraDocumentoAberto={aceitaPaginas}
                aEnviar={abrirComFicheiro.isPending || anexar.isPending}
                desativado={desenhoDoFicheiro === "limite" || (aceitaPaginas && noTeto)}
                limiteAtingido={
                  (desenhoDoFicheiro === "limite" || (aceitaPaginas && noTeto)) &&
                  documento !== undefined
                    ? documento.page_limit
                    : null
                }
                erro={
                  desenhoDoFicheiro === "campo" || desenhoDoFicheiro === "limite"
                    ? fraseDaRecusa(erroDoFicheiro)
                    : null
                }
                chave={envios}
                aoEscolher={aoEscolherFicheiro}
              />

              {/* `documento_fechado` e `documento_descartado`: o documento aberto
                deixou de aceitar escrita, logo o erro não é do campo e a única saída
                é abrir outro. */}
              {documentoPerdido ? (
                <Alert className="border-danger-border bg-danger-surface">
                  <AlertTitle>{textos.documento.painel.abrirOutro}</AlertTitle>
                  <AlertDescription className="flex flex-col items-start gap-2">
                    <span className="text-pretty">
                      {fraseDaRecusa(
                        desenhoDoFicheiro === "documento_perdido" ? erroDoFicheiro : erroDoDocumento,
                      )}
                    </span>
                    <Button variant="outline" onClick={limparEscolha}>
                      {textos.documento.painel.abrirOutro}
                    </Button>
                  </AlertDescription>
                </Alert>
              ) : null}

              {desenhoDoFicheiro === "generico" && erroDoFicheiro !== null ? (
                <Alert className="border-danger-border bg-danger-surface">
                  <AlertTitle>{textos.documento.zona.erroTitulo}</AlertTitle>
                  <AlertDescription className="text-pretty">
                    {fraseDaRecusa(erroDoFicheiro)}
                  </AlertDescription>
                </Alert>
              ) : null}

              {/* O segundo caminho de entrada. Só aparece quando não há documento
                aberto: com um aberto, o botão abriria um segundo e deixava o
                primeiro a expirar sozinho. */}
              {aceitaPaginas ? null : (
                <div className="flex flex-col gap-1.5 border-t border-border pt-3">
                  <Button
                    variant="outline"
                    className="self-start"
                    disabled={abrirSlot.isPending}
                    onClick={() => {
                      abrirSlotDe("campo");
                    }}
                  >
                    <FilePlus2 aria-hidden="true" />
                    {abrirSlot.isPending ? textos.documento.slot.aAbrir : textos.documento.slot.abrir}
                  </Button>
                  <p className="max-w-prose text-pretty text-xs text-muted-foreground">
                    {textos.documento.slot.explicacao}
                  </p>
                  {ondeAbriu === "campo" && abrirSlot.isError ? (
                    <p role="alert" className="text-sm text-danger">
                      {fraseDaRecusa(abrirSlot.error)}
                    </p>
                  ) : null}
                </div>
              )}
            </div>

            {/* O bloco da ponte, onde até 2026-10-08 havia uma linha a dizer que ele
                não existia e porquê.
                **Escondido a quem chegou pelo código** — seria o telemóvel a
                convidar-se a si próprio —, e visível em todas as outras larguras sem
                excepção: o `hidden md:block` da decisão 7 caiu na adenda 2 porque um
                tablet de balcão em retrato é mais estreito que `md` e é precisamente
                onde mais se quer um segundo telemóvel a fotografar. */}
            {soCaptura ? null : (
              <PonteDeCaptura
                url={urlDaCaptura}
                // O `expires_at` vem do servidor e só quer dizer algo no
                // `aguarda_captura`: é o mesmo relógio que o estado deriva (ADR
                // 0020, decisão 2), e não um segundo contado aqui.
                expiraAs={aVazio ? formatTime(documento.expires_at) : null}
                paginas={documento?.page_count ?? 0}
                expirado={documento?.state === "expirado"}
                aCarregar={escolhido !== null && consultaDoDocumento.isPending}
                aAbrir={abrirSlot.isPending}
                erroAoAbrir={
                  ondeAbriu === "ponte" && abrirSlot.isError ? fraseDaRecusa(abrirSlot.error) : null
                }
                aoAbrir={() => {
                  abrirSlotDe("ponte");
                }}
              />
            )}
          </div>
        </>
      )}

      {/* O documento escolhido: o estado, as páginas, os ficheiros, e o que o
          modelo leu. Só existe quando há um no URL — e **não** enquanto o âmbito
          for o errado, porque aí ele não foi pedido: um esqueleto sobre uma
          consulta desactivada pulsa para sempre, que é a mentira mais fácil de
          escrever (`painel-do-documento.tsx` diz o mesmo da pré-visualização). */}
      {escolhido === null || troca !== null ? null : (
        <div className="flex flex-col gap-ritmo px-celula-x py-4">
          {consultaDoDocumento.isPending ? (
            <div aria-busy="true" className="flex flex-col gap-2">
              <span className="sr-only">{textos.documento.painel.aCarregar}</span>
              {/* A forma do que vem: o cabeçalho do painel e a régua de campos. */}
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-16 w-full" />
            </div>
          ) : null}

          {/* 404 tem uma saída própria — o endereço aponta para um documento que
              não existe neste estabelecimento — e tudo o resto é uma falha a
              tentar outra vez. Confundidos, davam um botão de retry sobre um
              documento que nunca vai responder. */}
          {consultaDoDocumento.isError ? (
            statusDaRecusaDeDocumento(consultaDoDocumento.error) === 404 ? (
              <EstadoVazio
                icone={FilePlus2}
                titulo={textos.documento.painel.naoExisteTitulo}
                descricao={textos.documento.painel.naoExisteCorpo}
              >
                <Button variant="outline" onClick={limparEscolha}>
                  {textos.documento.painel.abrirOutro}
                </Button>
              </EstadoVazio>
            ) : (
              <ErroAoCarregar
                titulo={textos.documento.painel.erroAoCarregar}
                mensagem={fraseDaRecusa(consultaDoDocumento.error)}
                aoTentarOutraVez={() => {
                  void consultaDoDocumento.refetch();
                }}
              />
            )
          ) : null}

          {documento === undefined ? null : (
            <>
              <PainelDoDocumento
                documento={documento}
                aceitaPaginas={aceitaPaginas}
                desistiu={desistiu}
                aFechar={fechar.isPending}
                aDescartar={descartar.isPending}
                recusaDoFecho={
                  erroDoDocumento === null || desenhoDoDocumento === "documento_perdido"
                    ? null
                    : fraseDaRecusa(erroDoDocumento)
                }
                aoFechar={() => {
                  abrirComFicheiro.reset();
                  anexar.reset();
                  fechar.mutate(documento.id);
                }}
                aoDescartar={() => {
                  abrirComFicheiro.reset();
                  anexar.reset();
                  descartar.mutate(documento.id, { onSuccess: limparEscolha });
                }}
              />

              {/* O painel existe sempre, com extração ou sem ela: é ele que
                  responde a "o que o modelo leu", incluindo quando a resposta é
                  "ainda nada".
                  **Excepto a quem chegou pelo código**: a revisão do que o
                  modelo leu é trabalho de escritório — é a fatia 2, e é num
                  computador que ela se faz. Quem está no armazém a fotografar
                  não precisa de rolar por uma tabela de linhas lidas para chegar
                  ao botão de terminar. */}
              {soCaptura ? null : <PainelDeLeitura extracao={documento.extraction} />}
            </>
          )}
        </div>
      )}

      {/* **A lista e os três caminhos de entrada são conteúdo de escritório**,
          e não aparecem a quem chegou pelo código: a lista responde a "o que
          é que já entrou?", que é a pergunta do dono ao computador, e os três
          caminhos são prosa de sessão 0. Num telemóvel, com uma caixa na
          outra mão, as duas estão entre a fotografia e o botão de terminar. */}
      {soCaptura ? null : (
        <>
          {/* A lista do que entrou. Fica abaixo do painel porque a pergunta dela é a
              segunda: primeiro "o que é que acabei de enviar?", depois "o que é que
              já entrou?". */}
          <div className="flex min-w-0 flex-col border-t border-border">
            <h2 className="px-celula-x py-3 text-sm font-semibold">{textos.documento.lista.titulo}</h2>

            {documentos.isPending ? <EsqueletoDaTabelaDeDocumentos /> : null}

            {documentos.isError ? (
              <ErroAoCarregar
                titulo={textos.documento.lista.erroAoCarregar}
                mensagem={fraseDaRecusa(documentos.error)}
                aoTentarOutraVez={() => {
                  void documentos.refetch();
                }}
              />
            ) : null}

            {linhas === undefined ? null : linhas.length === 0 ? (
              <EstadoVazio
                icone={Truck}
                titulo={textos.documento.lista.vazioTitulo}
                descricao={textos.documento.lista.vazioCorpo}
              >
                <Button asChild variant="outline">
                  <Link to="/receber" search={() => ({})}>
                    {textos.comuns.verAsRececoes}
                  </Link>
                </Button>
              </EstadoVazio>
            ) : (
              <>
                <TabelaDeDocumentos documentos={linhas} escolhido={escolhido} aoEscolher={escolher} />
                <p className="px-celula-x py-3 text-xs text-muted-foreground">
                  {textos.documento.lista.rodape(linhas.length, truncada ? total : null)}
                </p>
              </>
            )}
          </div>

          {/* Os três caminhos por onde a mercadoria entra. Fica no fim: é conteúdo de
              sessão 0 e não a acção do ecrã.
              Cada frase em duas partes nomeadas — o nome do documento vai no `<span>`
              com peso, e juntá-las numa string perdia essa ênfase. Pôr HTML numa
              string pedia um `dangerouslySetInnerHTML`, que o `eslint.config.js`
              proíbe. */}
          <div className="flex flex-col gap-2 border-t border-border px-celula-x py-4">
            <h2 className="text-sm font-semibold">{textos.fotografar.porOndeEntra}</h2>
            <ul className="flex max-w-prose flex-col gap-2 text-sm text-muted-foreground">
              {/* A regra, não a hipótese: a receção existe sem encomenda e sem
                  fatura (guião §5). Se o modelo exigir uma encomenda para receber,
                  está errado para o mercado português. */}
              <li className="text-pretty">
                <span className="font-medium text-foreground">{textos.fotografar.faturaEnfase}</span>
                {textos.fotografar.faturaFim}
              </li>
              <li className="text-pretty">
                <span className="font-medium text-foreground">{textos.fotografar.guiaEnfase}</span>
                {textos.fotografar.guiaFim}
              </li>
              <li className="text-pretty">
                <span className="font-medium text-foreground">
                  {textos.fotografar.semDocumentoEnfase}
                </span>
                {textos.fotografar.semDocumentoFim}
              </li>
            </ul>
          </div>
        </>
      )}
    </section>
  );
}
