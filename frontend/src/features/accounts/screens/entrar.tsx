import { Link, useLocation, useNavigate, useSearch } from "@tanstack/react-router";
import { ArrowRight, LogIn } from "lucide-react";
import { useState, type FormEvent } from "react";

import { ErroAoCarregar } from "@/components/erro-ao-carregar";
import { EsqueletoDePainel } from "@/components/esqueleto-de-painel";
import { Button } from "@/components/ui/button";

import { useEntrar, useEscolherEstabelecimento, useSessao } from "../api";
import { Aviso, type TomDoAviso } from "../components/aviso";
import { BotaoDeSair } from "../components/botao-de-sair";
import { CampoDeTexto } from "../components/campo-de-texto";
import { SeletorDeEstabelecimento } from "../components/seletor-de-estabelecimento";
import {
  CODIGO_CONTA_BLOQUEADA,
  codigoDaRecusa,
  errosDeValidacao,
  errosPorCampo,
  mensagemDaRecusa,
} from "../erros";
import { credenciaisSchema, type Estabelecimento, type Sessao } from "../schemas";
import { textos } from "../textos";

/**
 * `/entrar` — **a primeira tela real do produto na identidade "Cabine"**.
 *
 * Um ecrã e quatro estados, porque a resposta de `GET /auth/sessao` tem quatro
 * e os quatro acontecem aqui (ADR 0010):
 *
 *  - `anonimo` → o formulário de email e password;
 *  - `escolha_pendente` → o seletor de estabelecimento, que a ADR 0007 deixou
 *    em aberto no cliente. É o caso de quem pertence a mais de um: o servidor
 *    **não adivinha** qual, porque adivinhar era escolher o âmbito em nome de
 *    quem o tem de escolher;
 *  - `sem_estabelecimento` → uma frase própria e uma saída, não um ecrã vazio;
 *  - `ativa` → não devia chegar aqui (o `beforeLoad` da rota redirecciona), e
 *    se chegar diz-se o que se passa em vez de se mostrar um formulário a quem
 *    já tem sessão.
 *
 * ## O que este ecrã **não** faz, e é deliberado
 *
 * Não reescreve nenhuma recusa do servidor. Em particular,
 * `credenciais_invalidas` chega com "Email ou password incorretos." e sai
 * exactamente assim: email inexistente, password errada e conta inativa dão o
 * **mesmo** corpo, porque distinguir confirmava a um estranho quais os emails
 * são clientes. Uma mensagem "mais útil" aqui é um oráculo de enumeração.
 *
 * Não tem link de "esqueci-me da password": os dois endpoints de reposição são
 * dívida nomeada da ADR 0010 e ainda não existem. Um link para um ecrã que não
 * existe é pior do que não ter link.
 *
 * Não tem registo. O tenant nasce por `manage.py criar_estabelecimento` e daí
 * em diante entra-se por convite — há três razões na ADR 0010 e nenhuma é de
 * conveniência.
 */
export function EcraDeEntrada() {
  const { destino } = useSearch({ from: "/publico/entrar" });
  const sessao = useSessao();

  if (sessao.isPending) return <EsqueletoDePainel />;

  if (sessao.isError) {
    // Falhar a ler a sessão não é "não tem sessão": é não saber. E sem este
    // pedido não há cookie `csrftoken`, logo o formulário também não
    // funcionaria — o `http.ts` recusa-se a enviar a escrita, de propósito.
    // Mostrar o formulário aqui era convidar a escrever uma password para um
    // pedido que não sai.
    return (
      <ErroAoCarregar
        titulo={textos.entrar.erroDeRede}
        mensagem={mensagemDaRecusa(sessao.error)}
        aoTentarOutraVez={() => {
          void sessao.refetch();
        }}
      />
    );
  }

  switch (sessao.data.estado) {
    case "anonimo":
      return <FormularioDeEntrada destino={destino ?? RAIZ} />;
    case "escolha_pendente":
      return <EscolhaDeEstabelecimento sessao={sessao.data} destino={destino ?? RAIZ} />;
    case "sem_estabelecimento":
      return <ContaSemEstabelecimento sessao={sessao.data} />;
    case "ativa":
      return <SessaoJaAtiva sessao={sessao.data} />;
  }
}

/**
 * O caminho da activação. O `/entrar` só arrasta o fragmento de volta para
 * **este** destino, e a razão é que o fragmento é um segredo: levá-lo para
 * qualquer outro sítio deixava um token de convite na barra de endereço depois
 * de a pessoa já estar dentro da aplicação.
 */
const ROTA_DE_ATIVACAO = "/ativar";

/**
 * O destino por omissão. A search param `destino` é **opcional** e ausente *é*
 * o default (`routes/busca-de-entrada.ts`): é isso que mantém `/entrar` um URL
 * limpo, e um `.default("/")` no schema punha `?destino=%2F` em todos os links
 * para o ecrã de entrada.
 */
const RAIZ = "/";

/**
 * Para onde se vai depois de entrar, **com o fragmento quando ele é devido**.
 *
 * O caso que isto resolve é o do convite para um email que já tem conta: o
 * servidor responde `convite_exige_sessao`, o `/ativar` manda entrar primeiro, e
 * depois do login tem de se **voltar ao link**. O `destino` viaja na search
 * param (é um caminho, não é segredo) e o token viaja onde sempre viajou — no
 * fragmento, que não chega ao servidor, não entra no log de acesso do proxy e
 * não viaja em `Referer` (ADR 0010).
 *
 * Pô-lo na search param para o trazer de volta destruía a propriedade inteira:
 * o token passava a estar na query string de um `GET /entrar`, que é uma linha
 * no log do proxy.
 */
function alvoDepoisDeEntrar(destino: string, hash: string): string {
  if (destino !== ROTA_DE_ATIVACAO) return destino;
  // O `location.hash` do router vem **sem** o `#` (medido no `router-core`); o
  // `replace` é a rede para a outra convenção, que é a do `window.location`.
  const fragmento = hash.replace(/^#/, "");
  return fragmento === "" ? destino : `${destino}#${fragmento}`;
}

/**
 * Os campos deste formulário, numa lista fechada. É ela que diz ao
 * `errosPorCampo` quais as chaves do 400 do DRF que têm um input onde aparecer —
 * sem ela, o nome de qualquer chave que o servidor inventasse ia para o ecrã.
 */
const CAMPOS_DE_ENTRADA = ["email", "password"] as const;

type CampoDeEntrada = (typeof CAMPOS_DE_ENTRADA)[number];

/** O par (tom, título) de uma recusa do login. */
function avisoDaRecusa(erro: unknown): { tom: TomDoAviso; titulo: string } {
  if (codigoDaRecusa(erro) === CODIGO_CONTA_BLOQUEADA) {
    // 429 do lockout do axes, com corpo JSON. É uma instrução ("tente mais
    // tarde") e não um beco: o tom certo é o de aviso.
    return { tom: "warning", titulo: textos.entrar.contaBloqueada };
  }
  return { tom: "danger", titulo: textos.entrar.erroAoEntrar };
}

function FormularioDeEntrada({ destino }: { readonly destino: string }) {
  const navegar = useNavigate();
  const hash = useLocation({ select: (localizacao) => localizacao.hash });
  const entrar = useEntrar();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [errosLocais, setErrosLocais] = useState(() => new Map<CampoDeEntrada, string>());

  // O 400 do DRF tem **duas** formas no mesmo status: por campo
  // (`{"email": [...]}`) e `{code, detail}`. As duas aparecem, em sítios
  // diferentes: a primeira debaixo do input, a segunda no banner.
  const errosDoServidor = errosPorCampo(entrar.error, CAMPOS_DE_ENTRADA);
  const temErroDeCampo = errosDoServidor.size > 0;

  const erroDoEmail = errosLocais.get("email") ?? errosDoServidor.get("email");
  const erroDaPassword = errosLocais.get("password") ?? errosDoServidor.get("password");
  const aviso = avisoDaRecusa(entrar.error);

  function submeter(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault();

    // A validação local é o `credenciaisSchema` — o **mesmo** schema que valida
    // o corpo antes de ele sair, com as mensagens dentro dele. Só de presença: a
    // força da password não se valida no cliente (seria um oráculo sobre a
    // política de passwords) e o formato do email tem uma definição, que é a do
    // Django. O `.trim()` do email é do schema, logo o que vai no pedido é o
    // mesmo valor que o servidor ia usar.
    const analise = credenciaisSchema.safeParse({ email, password });
    if (!analise.success) {
      setErrosLocais(errosDeValidacao(analise.error, CAMPOS_DE_ENTRADA));
      return;
    }
    setErrosLocais(new Map());

    entrar.mutate(analise.data, {
      onSuccess: () => {
        // `href` e não `to`: o destino vem do URL, já validado pelo
        // `validateSearch` como caminho relativo, e não é um literal que o
        // router conheça em tipo. `replace` para o ecrã de entrada não ficar no
        // histórico — o botão de voltar depois de entrar não deve voltar ao
        // login.
        void navegar({ href: alvoDepoisDeEntrar(destino, hash), replace: true });
      },
    });
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">Entrar</h1>
        <p className="text-sm text-muted-foreground">
          {textos.entrar.subtitulo}
        </p>
      </div>

      {entrar.isError && !temErroDeCampo ? (
        <Aviso tom={aviso.tom} titulo={aviso.titulo} mensagem={mensagemDaRecusa(entrar.error)} />
      ) : null}

      {/* `noValidate`: a validação é nossa, para a mensagem aparecer **abaixo do
          campo, em texto**, e não numa bolha nativa que o DESIGN.md não
          desenha e que desaparece ao primeiro clique. */}
      <form noValidate onSubmit={submeter} className="flex flex-col gap-4">
        <CampoDeTexto
          id="email"
          rotulo="Email"
          tipo="email"
          valor={email}
          aoMudar={setEmail}
          erro={erroDoEmail}
          autoComplete="username"
          desativado={entrar.isPending}
        />
        <CampoDeTexto
          id="password"
          rotulo="Password"
          tipo="password"
          valor={password}
          aoMudar={setPassword}
          erro={erroDaPassword}
          autoComplete="current-password"
          desativado={entrar.isPending}
        />
        <Button
          type="submit"
          className="h-controlo w-full"
          disabled={entrar.isPending}
          aria-busy={entrar.isPending}
        >
          <LogIn aria-hidden="true" />
          {entrar.isPending ? textos.entrar.aEntrar : textos.entrar.titulo}
        </Button>
      </form>

      <p className="text-pretty text-xs text-muted-foreground">
        {textos.entrar.semConta}
      </p>
    </div>
  );
}

/**
 * `escolha_pendente` — o seletor que a ADR 0007 deixou em aberto no cliente.
 *
 * O 403 `tenant_desconhecido` é um ramo normal aqui e não um defeito: acontece a
 * quem tinha esta lista aberta quando a sua pertença foi revogada. O que o
 * `api.ts` faz nesse caso é limpar o estabelecimento ativo e **reler a sessão**,
 * pelo que o item desaparece da lista em vez de ficar a dar o mesmo erro a cada
 * clique; o que este ecrã faz é dizer o que aconteceu.
 */
function EscolhaDeEstabelecimento({
  sessao,
  destino,
}: {
  readonly sessao: Sessao;
  readonly destino: string;
}) {
  const navegar = useNavigate();
  const hash = useLocation({ select: (localizacao) => localizacao.hash });
  const escolher = useEscolherEstabelecimento();
  const [emCurso, setEmCurso] = useState<string | null>(null);

  function escolherEstabelecimento(estabelecimento: Estabelecimento) {
    setEmCurso(estabelecimento.id);
    escolher.mutate(
      { tenant_id: estabelecimento.id },
      {
        onSuccess: () => {
          void navegar({ href: alvoDepoisDeEntrar(destino, hash), replace: true });
        },
        onSettled: () => {
          setEmCurso(null);
        },
      },
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">{textos.entrar.escolhaTitulo}</h1>
        <p className="text-sm text-muted-foreground">
          {textos.entrar.escolhaSubtitulo}
        </p>
      </div>

      {escolher.isError ? (
        <Aviso
          tom="danger"
          titulo={textos.entrar.erroAoAbrirEstabelecimento}
          mensagem={mensagemDaRecusa(escolher.error)}
        />
      ) : null}

      <SeletorDeEstabelecimento
        estabelecimentos={sessao.tenants}
        aEscolher={escolher.isPending}
        emCurso={emCurso}
        aoEscolher={escolherEstabelecimento}
      />

      <IdentidadeDaSessao sessao={sessao} />
      <BotaoDeSair rotulo={textos.entrar.terminarSessao} />
    </div>
  );
}

/**
 * `sem_estabelecimento` — a frase própria que esta conta merece.
 *
 * Um ecrã vazio aqui era o pior resultado possível: a pessoa acabou de acertar
 * na password e não tem como saber que o problema não é dela. A frase diz o que
 * se passa e quem resolve, e a única ação possível é sair — que está lá, porque
 * um estado sem saída é um beco.
 *
 * Acontece de duas maneiras, e nenhuma é rara: uma conta criada pelo
 * `manage.py` cujo convite ainda não foi aceite, e uma conta cuja última
 * pertença foi revogada.
 */
function ContaSemEstabelecimento({ sessao }: { readonly sessao: Sessao }) {
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">{textos.entrar.semEstabelecimentoTitulo}</h1>
        <p className="text-pretty text-sm text-muted-foreground">
          {textos.entrar.semEstabelecimentoCorpo}
        </p>
      </div>
      <IdentidadeDaSessao sessao={sessao} />
      <BotaoDeSair rotulo={textos.entrar.terminarSessao} />
    </div>
  );
}

/**
 * `ativa` — não devia acontecer, e por isso não se finge que não aconteceu.
 *
 * O `beforeLoad` da rota redirecciona quem já tem sessão, logo este ramo só se
 * vê numa corrida (dois separadores, o outro entrou primeiro). Mostrar o
 * formulário era convidar a entrar outra vez numa sessão que já está aberta; um
 * `navigate` num efeito era um ciclo de redireccionamento à espera de um erro
 * de rede. Uma frase e um link resolvem-no sem nenhum dos dois.
 */
function SessaoJaAtiva({ sessao }: { readonly sessao: Sessao }) {
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">{textos.entrar.jaTemSessaoTitulo}</h1>
        <p className="text-sm text-muted-foreground">
          {sessao.tenant_ativo === null
            ? textos.entrar.jaTemSessaoCorpo
            : `Está a trabalhar em ${sessao.tenant_ativo.nome}.`}
        </p>
      </div>
      <Button asChild className="h-controlo w-fit">
        <Link to="/">
          {textos.entrar.abrirApp}
          <ArrowRight aria-hidden="true" />
        </Link>
      </Button>
      <IdentidadeDaSessao sessao={sessao} />
      <BotaoDeSair rotulo={textos.entrar.terminarSessao} />
    </div>
  );
}

/**
 * De quem é a sessão. Uma linha, e não é decoração: quem chega ao seletor ou ao
 * `sem_estabelecimento` precisa de saber **em que conta** está antes de decidir
 * se o problema é a conta errada. O email é o campo de entrada da conta e é o
 * que a pessoa reconhece.
 *
 * Em `font-mono`, como qualquer dado que se compara carácter a carácter
 * (DESIGN.md §2): um email é código, não prosa.
 */
function IdentidadeDaSessao({ sessao }: { readonly sessao: Sessao }) {
  if (sessao.utilizador === null) return null;
  return (
    <p className="text-xs text-muted-foreground">
      {textos.entrar.sessaoDe} <span className="font-mono">{sessao.utilizador.email}</span>
    </p>
  );
}
