import { MailPlus, ShieldAlert } from "lucide-react";
import { useRef, useState, type ReactNode } from "react";

import { ErroAoCarregar } from "@/components/erro-ao-carregar";
import { EstadoVazio } from "@/components/estado-vazio";
import { Button } from "@/components/ui/button";

import {
  useConvidar,
  useConvites,
  usePodeConvidar,
  useReenviarConvite,
  useRevogarConvite,
  useSessao,
} from "../api";
import { Aviso } from "../components/aviso";
import { FormularioDeConvite } from "../components/formulario-de-convite";
import { SegredoDoConvite, type SegredoEmitido } from "../components/segredo-do-convite";
import { EsqueletoDeConvites, TabelaDeConvites } from "../components/tabela-de-convites";
import { CODIGO_CONVITE_NAO_PENDENTE, codigoDaRecusa, mensagemDaRecusa } from "../erros";
import { nomeDoPapel, type Convite, type Papel } from "../schemas";

/**
 * `/convites` — "quem tem acesso a este estabelecimento, e quem está por
 * entrar?".
 *
 * Até hoje convidava-se por `curl`. O ecrã existe porque o fluxo inteiro da ADR
 * 0010 — criar, entregar o link, reenviar, revogar — era inutilizável sem ele, e
 * é o primeiro ecrã do repositório a nascer contra um backend **que já existe**:
 * os quatro endpoints estão feitos, os tipos estão gerados, e o comportamento
 * que está aqui foi medido contra o `runserver` em vez de deduzido do contrato.
 *
 * ## A assimetria que define o ecrã
 *
 * O `ConviteCriadoOut` do POST traz o `fragmento`; o `ConviteOut` da listagem
 * **não traz token nenhum, nem forma de o ter** — a tabela guarda um SHA-256 e um
 * token mostrável depois teria de ser guardado em claro (ADR 0010). O segredo sai
 * **uma vez**, como uma chave de API. Toda a estrutura deste ecrã é consequência
 * disso:
 *
 *  - os segredos emitidos **acumulam-se numa pilha** em vez de se substituírem.
 *    Criar dois convites seguidos com um painel único fazia o primeiro link
 *    desaparecer antes de alguém o entregar — e esse link não se recupera, só se
 *    substitui por um reenvio, que invalida o antigo;
 *  - vivem em **estado de componente** e em mais nada: nem cache de query, nem
 *    `localStorage` (proibido pelo SECURITY.md §7 e pelo linter), nem URL. Sair
 *    do ecrã perde-os, e essa é a propriedade certa — um segredo de uso único não
 *    deve sobreviver à página que o mostrou;
 *  - a consequência está **escrita** no painel, não implícita, porque é a frase
 *    que diz o que fazer no dia em que já aconteceu.
 *
 * ## Não há email, e o ecrã não finge que há
 *
 * Zero eventos e zero Celery no v1, porque não há consumidor da outbox (ADR
 * 0010). Quem convida entrega o link à mão. O verbo do contrato é "reenviar" e
 * essa palavra promete um email que não existe — por isso o painel diz o que de
 * facto acontece ("cria um link novo e invalida o anterior") em vez de repetir o
 * nome do endpoint.
 *
 * ## O papel
 *
 * Só o `owner` convida e só o `owner` lista (ADR 0010, com a razão: é a resposta
 * que não pode estar errada enquanto a Q7 — o conjunto de papéis — está por
 * confirmar com um utilizador real). Uma comparação por **igualdade** com um
 * papel, nunca uma ordem: não existe ordem entre papéis e a ADR diz para não a
 * inventar.
 *
 * Quem autoriza é o servidor — medido: `GET` e `POST /api/v1/convites` com sessão
 * de um `staff` respondem 403, com `detail` e **sem `code`**. O que este ecrã faz
 * com o papel é apresentação: não dispara um pedido que já sabe recusado, e
 * **diz** a quem chegou aqui por deep link o que se passa. A rota continua a
 * funcionar para todos, porque esconder é apresentação e não autorização (ADR
 * 0009) e um marcador guardado não deve dar 404.
 */

/**
 * O prefixo dos ids deste ecrã.
 *
 * O `FormularioDeConvite` gera os seus com `useId` quando ninguém lhe dá um; aqui
 * dá-se-lhe um estável por uma razão concreta e não por gosto: o estado vazio tem
 * de ter uma **acção** (é o contrato do `EstadoVazio`: "um vazio sem saída é um
 * beco"), e a acção deste ecrã é o campo que já está no topo. Para o botão do
 * vazio poder pôr o foco lá, o id tem de ser conhecido dos dois lados.
 */
const PREFIXO_DO_FORMULARIO = "convite";
const ID_DO_CAMPO_DE_EMAIL = `${PREFIXO_DO_FORMULARIO}-email`;

export function EcraDeConvites() {
  const sessao = useSessao();
  const podeConvidar = usePodeConvidar();

  const convites = useConvites(podeConvidar);
  const convidar = useConvidar();
  const reenviar = useReenviarConvite();
  const revogar = useRevogarConvite();

  /**
   * Os segredos emitidos **nesta visita ao ecrã**, do mais recente para o mais
   * antigo.
   */
  const [segredos, setSegredos] = useState<readonly SegredoEmitido[]>([]);

  /**
   * A chave de React de cada painel de segredo, num contador monótono.
   *
   * Não é o `id` do convite, e a diferença importa: um reenvio emite um segredo
   * novo para o **mesmo** convite, e com o `id` como chave o painel do link
   * anterior era substituído em vez de ficar ao lado do novo — que é precisamente
   * o acidente que esta pilha existe para impedir. Um `useRef` e não um `useState`
   * porque isto não é estado que se renderiza: é um nome, e mudá-lo não deve
   * provocar um render.
   */
  const proximaChave = useRef(0);

  /** O convite cuja mutação está a sair, para a linha certa ficar `aria-busy`. */
  const [idEmCurso, setIdEmCurso] = useState<string | null>(null);

  /**
   * O que acabou de acontecer, para quem lê por áudio.
   *
   * Existe por uma assimetria concreta: **criar e reenviar anunciam-se sozinhos**
   * (o painel do segredo nasce dentro de uma região `aria-live`, logo é lido), mas
   * **revogar não produz nada novo na página** — a linha muda de badge e dois
   * botões trocam de sítio, o que para um leitor de ecrã é silêncio total. Sem
   * isto, quem confirma uma revogação não tem como saber se ela aconteceu, e a
   * acção é final.
   *
   * Uma frase e não `role="status"` no `<tbody>`: uma região viva sobre uma tabela
   * inteira faz reler linhas que não mudaram a cada invalidação.
   */
  const [ultimoResultado, setUltimoResultado] = useState("");

  function guardarSegredo(convite: Convite, fragmento: string, origem: SegredoEmitido["origem"]) {
    proximaChave.current += 1;
    const chave = `${convite.id}-${String(proximaChave.current)}`;
    setSegredos((anteriores) => [{ chave, convite, fragmento, origem }, ...anteriores]);
  }

  function esquecerSegredo(chave: string) {
    setSegredos((anteriores) => anteriores.filter((segredo) => segredo.chave !== chave));
  }

  if (sessao.isPending) {
    return (
      <Pagina>
        <EsqueletoDeConvites />
      </Pagina>
    );
  }

  if (sessao.isError) {
    // Falhar a ler a sessão não é "não tem permissão": é **não saber**. Mostrar a
    // recusa de papel aqui era afirmar uma coisa sobre o papel de alguém sem ter
    // lido nenhum — e, pior, sem saída.
    return (
      <Pagina>
        <div className="px-celula-x py-6">
          <ErroAoCarregar
            titulo="Não foi possível ler a sessão"
            mensagem={mensagemDaRecusa(sessao.error)}
            aoTentarOutraVez={() => {
              void sessao.refetch();
            }}
          />
        </div>
      </Pagina>
    );
  }

  if (!podeConvidar) {
    return (
      <Pagina>
        <SemPermissao papel={sessao.data.tenant_ativo?.papel ?? null} />
      </Pagina>
    );
  }

  // O 409 `convite_nao_pendente` é a recusa que não se "melhora": é um estado que
  // mudou debaixo dos pés de quem tinha a página aberta, e o `api.ts` já releu a
  // lista por baixo deste banner — quando a frase acaba de ser lida, a linha já
  // mostra o estado novo. O que fica para dizer é o que aconteceu, com o `detail`
  // do servidor sem reescrita.
  const erroDeGestao: unknown = reenviar.error ?? revogar.error;
  const estadoMudou = codigoDaRecusa(erroDeGestao) === CODIGO_CONVITE_NAO_PENDENTE;

  const pagina = convites.data;
  const linhas = pagina?.results ?? [];
  const truncada = pagina !== undefined && pagina.count > pagina.results.length;

  return (
    <Pagina>
      <BarraDoEcra total={pagina?.count ?? null} />

      {/* A região viva do ecrã. Fica fora do fluxo visual (`sr-only`) porque o
          que ela diz já está à vista na linha — o que falta é dizê-lo a quem não
          a vê mudar. */}
      <p aria-live="polite" className="sr-only">
        {ultimoResultado}
      </p>

      <div className="flex flex-col gap-ritmo px-celula-x py-4">
        <FormularioDeConvite
          prefixoDeId={PREFIXO_DO_FORMULARIO}
          aSubmeter={convidar.isPending}
          erroDoServidor={convidar.error}
          aoSubmeter={(novo, aoConseguir) => {
            convidar.mutate(novo, {
              onSuccess: (criado) => {
                guardarSegredo(criado.convite, criado.fragmento, "criado");
                aoConseguir();
              },
            });
          }}
        />

        {segredos.length === 0 ? null : (
          // `aria-live="polite"`: o link aparece sem roubar o foco a quem acabou
          // de submeter, e quem lê por áudio é avisado de que há um segredo novo
          // na página. `assertive` seria interromper a leitura a meio, e isto não
          // é uma emergência — é um resultado.
          <ul aria-live="polite" className="flex flex-col gap-3">
            {segredos.map((segredo) => (
              <SegredoDoConvite
                key={segredo.chave}
                segredo={segredo}
                aoGuardar={() => {
                  esquecerSegredo(segredo.chave);
                }}
              />
            ))}
          </ul>
        )}

        {erroDeGestao === null ? null : (
          <Aviso
            tom={estadoMudou ? "warning" : "danger"}
            titulo={
              estadoMudou
                ? "O estado deste convite mudou"
                : "Não foi possível concluir essa operação"
            }
            mensagem={mensagemDaRecusa(erroDeGestao)}
          />
        )}

        {convites.isPending ? <EsqueletoDeConvites /> : null}

        {convites.isError ? (
          <ErroAoCarregar
            titulo="Não foi possível carregar os convites"
            mensagem={mensagemDaRecusa(convites.error)}
            aoTentarOutraVez={() => {
              void convites.refetch();
            }}
          />
        ) : null}

        {pagina === undefined ? null : linhas.length === 0 ? (
          <ListaVazia />
        ) : (
          <div className="flex flex-col gap-2">
            <TabelaDeConvites
              convites={linhas}
              aReenviar={reenviar.isPending ? idEmCurso : null}
              aRevogar={revogar.isPending ? idEmCurso : null}
              aoReenviar={(id) => {
                setIdEmCurso(id);
                reenviar.mutate(id, {
                  onSuccess: (criado) => {
                    guardarSegredo(criado.convite, criado.fragmento, "reenviado");
                  },
                  onSettled: () => {
                    setIdEmCurso(null);
                  },
                });
              }}
              aoRevogar={(convite) => {
                setIdEmCurso(convite.id);
                revogar.mutate(convite.id, {
                  onSuccess: (revogado) => {
                    setUltimoResultado(
                      `Convite de ${revogado.email} revogado. O link deixou de funcionar.`,
                    );
                  },
                  onSettled: () => {
                    setIdEmCurso(null);
                  },
                });
              }}
            />
            {/* A regra de ordenação e o TTL ficam no fim, onde não pagam pixéis
                acima da dobra: quem chega ao fundo da lista é quem precisa de
                saber porque é que ela não está por ordem alfabética, e quanto
                tempo dura um link. */}
            <p className="text-xs text-muted-foreground">
              {linhas.length === 1 ? "1 convite" : `${String(linhas.length)} convites`}
              {truncada ? ` de ${String(pagina.count)}` : ""} · mais recentes primeiro · um link de
              convite é válido 7&nbsp;dias
            </p>
          </div>
        )}
      </div>
    </Pagina>
  );
}

/**
 * A moldura do ecrã: **largura toda**, sem cap.
 *
 * O DESIGN.md §4 manda tabelas usarem a largura toda da área de conteúdo, e os
 * quatro ecrãs antigos continuam em `42rem` por dívida deliberada que o próprio
 * §4 nomeia. Este é novo e não a herda — é por isso que não há `max-w` nenhum
 * aqui. Um cap de `72rem` numa tabela de ERP é espaço desperdiçado à direita, e é
 * o §4 a dizê-lo.
 */
function Pagina({ children }: { readonly children: ReactNode }) {
  return (
    <section className="flex w-full flex-col">
      {/* O nome do ecrã já está na barra de topo do shell ("Equipa / Convites").
          O documento continua a ter um `h1`, para quem navega por cabeçalhos — e
          é `sr-only` pela mesma razão que nos outros ecrãs de lista: repeti-lo em
          grande custava uma linha de tabela. */}
      <h1 className="sr-only">Convites — quem tem acesso a este estabelecimento</h1>
      {children}
    </section>
  );
}

/**
 * A barra do ecrã: o que ele responde, e o total.
 *
 * Sticky a `top-cabecalho` — o mesmo token que dá a altura à barra do shell, e
 * não um número: com um número à mão esta barra ficava uns pixéis por baixo do
 * cabeçalho e desaparecia-lhe por trás ao deslizar, que é um defeito que este
 * repositório já teve uma vez.
 *
 * É também o que fica à vista quando a tabela rola, porque o `thead` não é sticky
 * (a razão, que é de CSS, está no `tabela-de-convites.tsx`).
 */
function BarraDoEcra({ total }: { readonly total: number | null }) {
  return (
    <div className="sticky top-cabecalho z-10 flex items-center justify-between gap-2 border-b border-border bg-background px-celula-x py-2">
      <p className="text-pretty text-sm text-muted-foreground">
        Quem tem acesso, e quem está por entrar. O acesso é sempre por convite.
      </p>
      {total === null ? null : (
        <p className="shrink-0 text-xs text-muted-foreground">
          <span data-numeric className="text-sm text-foreground">
            {total}
          </span>{" "}
          no total
        </p>
      )}
    </div>
  );
}

/**
 * O vazio, **com acção** — e a acção é o campo que já está no topo do ecrã.
 *
 * O `EstadoVazio` exige uma acção por construção ("um vazio sem saída é um
 * beco"). Aqui ela não é um segundo formulário nem um link para outro ecrã: é um
 * botão que põe o foco no campo de email que está acima. Dois caminhos para a
 * mesma acção num ecrã com um formulário de três campos é um a mais, mas um vazio
 * que só *descreve* a acção obriga quem lê por teclado a voltar atrás à mão.
 */
function ListaVazia() {
  return (
    <div className="rounded-xl border border-border bg-surface">
      <EstadoVazio
        icone={MailPlus}
        titulo="Ainda não convidou ninguém"
        descricao="Só quem tem um convite consegue entrar neste estabelecimento. O link aparece aqui uma vez, e é entregue por você — não é enviado nenhum email."
      >
        <div className="flex flex-col items-start gap-2">
          <Button
            type="button"
            variant="outline"
            className="h-controlo"
            onClick={() => {
              document.getElementById(ID_DO_CAMPO_DE_EMAIL)?.focus();
            }}
          >
            <MailPlus aria-hidden="true" />
            Convidar alguém
          </Button>
          <p className="text-xs text-muted-foreground">
            Um convite é válido 7&nbsp;dias e pode ser revogado a qualquer momento.
          </p>
        </div>
      </EstadoVazio>
    </div>
  );
}

/**
 * Quem não é `owner` — o ramo que a ADR 0009 obriga a desenhar.
 *
 * "Esconder é apresentação, não autorização": a entrada do menu não aparece para
 * quem não convida, mas a **rota continua a funcionar** porque a árvore de rotas
 * é código e não dados, e um marcador guardado não deve dar 404. Então alguém
 * chega aqui — por deep link, por um URL colado, ou porque o seu papel mudou com
 * a página aberta — e o que vê tem de dizer o que se passa.
 *
 * O que ele **não** faz é redireccionar em silêncio para o início: quem clica num
 * link e aterra noutro ecrã não aprende nada e vai tentar outra vez. E não
 * dispara o `GET /convites` só para mostrar o 403 do servidor, porque a resposta
 * já se sabe e um pedido recusado por visita não é diagnóstico.
 *
 * O papel actual está à vista porque é a informação que falta a quem acha que
 * devia poder: muitas vezes o que está errado é a conta, não a permissão.
 */
function SemPermissao({ papel }: { readonly papel: Papel | null }) {
  return (
    <div className="flex flex-col gap-3 px-celula-x py-6">
      <Aviso
        tom="warning"
        titulo="Só o dono do estabelecimento gere convites"
        mensagem={
          papel === null
            ? "Esta sessão não tem um papel neste estabelecimento. Recarregue a página e tente outra vez."
            : `Neste estabelecimento o seu papel é ${nomeDoPapel(papel)}, e convidar é do dono. Peça a quem o administra para criar o convite.`
        }
      >
        <p className="flex items-center gap-2 text-xs text-muted-foreground">
          <ShieldAlert aria-hidden="true" className="size-3.5 shrink-0" />
          Quem decide isto é o servidor, não este ecrã.
        </p>
      </Aviso>
    </div>
  );
}
