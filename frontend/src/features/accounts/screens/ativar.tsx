import { Link, useLocation, useNavigate } from "@tanstack/react-router";
import { ArrowRight, KeyRound } from "lucide-react";
import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";

import { useAtivarConvite, useSessao } from "../api";
import { Aviso, type TomDoAviso } from "../components/aviso";
import { BotaoDeSair } from "../components/botao-de-sair";
import { CampoDeTexto } from "../components/campo-de-texto";
import {
  CODIGO_CONVITE_DE_OUTRA_CONTA,
  CODIGO_CONVITE_EXIGE_SESSAO,
  CODIGO_CONVITE_INVALIDO,
  codigoDaRecusa,
  errosDeValidacao,
  errosPorCampo,
  mensagemDaRecusa,
} from "../erros";
import { formularioDeAtivacaoSchema } from "../schemas";
import { textos } from "../textos";

/**
 * `/ativar` — aceitar um convite, com o segredo no **fragmento** do URL.
 *
 * O link é `/ativar#<uuid-do-tenant>.<token>` e o fragmento é a única coisa
 * entre um estranho e um `Membership` (ADR 0010). Está no fragmento e não no
 * path por três razões: não chega ao servidor, logo não entra no log de acesso
 * do proxy; não viaja em `Referer`; e um pre-fetch do cliente de email não
 * consegue queimar um token de uso único. Este ecrã lê-o do `location.hash`,
 * tira o `#` e põe-no **inteiro e opaco** no corpo do POST — quem o divide é o
 * service, logo o formato do segredo tem uma definição e ela vive no servidor.
 *
 * ## A mensagem única, e porque não se melhora
 *
 * `convite_invalido` (400) é o **mesmo** código e o **mesmo** corpo para seis
 * causas: expirado, usado, revogado, inexistente, uuid de tenant forjado e
 * fragmento mal formado. Isso é deliberado e fecha um oráculo: distinguir dizia
 * a quem experimenta um link se aquele estabelecimento existe e se aquele
 * convite já foi usado. **Este ecrã não lhe acrescenta detalhe**, e em
 * particular não tenta adivinhar a razão a partir da forma do fragmento — seria
 * reabrir pelo cliente o oráculo que o servidor fechou.
 *
 * ## O campo de password aparece, e desaparece
 *
 * Em repouso há password (o caso comum é uma conta nova). Quando a resposta é
 * **409 `convite_exige_sessao`** — o email convidado já tem conta com password —
 * o campo desaparece, porque a activação **nunca** define password numa conta
 * que já tem uma: a password é global e a pertença é por tenant, pelo que
 * "convite + definir password" dava a quem pode convidar a tomada de uma conta
 * existente, com os outros estabelecimentos dela lá dentro. O que resta é
 * entrar primeiro e voltar ao link.
 *
 * Nota medida, porque é a assimetria mais fácil de "corrigir" para o lado
 * errado: a activação **recusa** uma sessão de outra conta quando a conta
 * convidada já existe com password, e **aceita** quando a conta não existe. Não
 * é incoerência: a recusa existe para proteger uma credencial que já existe, e
 * no segundo caso não existe nenhuma.
 */
export function EcraDeAtivacao() {
  const hash = useLocation({ select: (localizacao) => localizacao.hash });
  // O `location.hash` do router vem **sem** o `#` (medido no `router-core`); o
  // `replace` é a rede para a outra convenção, que é a do `window.location`.
  const fragmento = hash.replace(/^#/, "");

  if (fragmento === "") return <LinkIncompleto />;
  return <FormularioDeAtivacao fragmento={fragmento} />;
}

/**
 * A frase única, para o caso que o servidor nunca vê: um `/ativar` sem
 * fragmento nenhum.
 *
 * Diz **exactamente** o mesmo que o `detail` de `convite_invalido` e nada mais.
 * Existe em texto nosso porque não há resposta do servidor para mostrar — não
 * vale a pena fazer um POST com o fragmento vazio só para obter uma frase, e
 * esse POST levaria um 400 por campo, que é outra forma e não esta.
 */
const FRASE_DE_CONVITE_INVALIDO =
  textos.ativar.conviteInvalidoCorpo;

function LinkIncompleto() {
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">{textos.ativar.conviteInvalidoTitulo}</h1>
      </div>
      <Aviso tom="danger" titulo={textos.ativar.linkNaoServe} mensagem={FRASE_DE_CONVITE_INVALIDO} />
      <Button asChild variant="outline" className="h-controlo w-fit">
        <Link to="/entrar">
          {textos.ativar.irParaEntrada}
          <ArrowRight aria-hidden="true" />
        </Link>
      </Button>
    </div>
  );
}

/** O par (tom, título) de cada recusa da activação. */
function avisoDaRecusa(codigo: string | null): { tom: TomDoAviso; titulo: string } {
  switch (codigo) {
    case CODIGO_CONVITE_EXIGE_SESSAO:
      // Não é uma falha: é uma instrução em dois passos, e o convite continua
      // válido. Tom de aviso e uma saída.
      return { tom: "warning", titulo: textos.ativar.contaJaExiste };
    case CODIGO_CONVITE_DE_OUTRA_CONTA:
      return { tom: "warning", titulo: textos.ativar.conviteDeOutraConta };
    case CODIGO_CONVITE_INVALIDO:
      return { tom: "danger", titulo: textos.ativar.conviteNaoServe };
    default:
      return { tom: "danger", titulo: textos.ativar.erroAoActivar };
  }
}

/**
 * Os campos deste formulário. O `confirmacao` só existe no cliente — o corpo do
 * `POST /auth/ativar` leva `fragmento` e `password` e mais nada —, por isso a
 * lista que vai ao `errosPorCampo` (os erros do servidor) é **só** `password`:
 * o servidor nunca tem nada a dizer sobre um campo que não recebeu.
 */
const CAMPOS_DO_SERVIDOR = ["password"] as const;
const CAMPOS_LOCAIS = ["password", "confirmacao"] as const;

type CampoLocal = (typeof CAMPOS_LOCAIS)[number];

function FormularioDeAtivacao({ fragmento }: { readonly fragmento: string }) {
  const navegar = useNavigate();
  const sessao = useSessao();
  const ativar = useAtivarConvite();

  const [password, setPassword] = useState("");
  const [confirmacao, setConfirmacao] = useState("");
  const [errosLocais, setErrosLocais] = useState(() => new Map<CampoLocal, string>());

  // `?? null` e não `?.`: enquanto a sessão não responde o `data` é
  // `undefined`, e "ainda não sei" e "não há ninguém" mostram a mesma coisa
  // aqui — nada. Uma linha a piscar ao fim de meio segundo é pior que não a ter.
  const utilizador = sessao.data?.utilizador ?? null;
  const codigo = codigoDaRecusa(ativar.error);
  const errosDoServidor = errosPorCampo(ativar.error, CAMPOS_DO_SERVIDOR);
  const temErroDeCampo = errosDoServidor.size > 0;
  const aviso = avisoDaRecusa(codigo);

  // O campo de password **só** quando não há um dos três códigos estáveis: nos
  // três, escrever uma password não muda nada do que o servidor vai responder.
  const comPassword =
    codigo !== CODIGO_CONVITE_EXIGE_SESSAO &&
    codigo !== CODIGO_CONVITE_DE_OUTRA_CONTA &&
    codigo !== CODIGO_CONVITE_INVALIDO;

  function submeter(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault();

    // A validação local é o `formularioDeAtivacaoSchema`, com as mensagens e a
    // comparação das duas passwords lá dentro — incluindo a razão pela qual há
    // duas, que é uma decisão desta sessão e não de nenhuma ADR.
    const analise = formularioDeAtivacaoSchema.safeParse({ password, confirmacao });
    if (!analise.success) {
      setErrosLocais(errosDeValidacao(analise.error, CAMPOS_LOCAIS));
      return;
    }
    setErrosLocais(new Map());

    ativar.mutate(
      { fragmento, password: analise.data.password },
      {
        onSuccess: () => {
          // O servidor faz `login()` e devolve a sessão já ativa. Ir para a
          // raiz **sem** o fragmento: o token acabou de ser queimado e não tem
          // nada que fazer na barra de endereço nem no histórico.
          void navegar({ to: "/", replace: true });
        },
      },
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">{textos.ativar.titulo}</h1>
        {/* A frase de abertura só vale quando há formulário. Com um dos três
            códigos estáveis não há password a escolher, e manter "escolha uma
            password" por cima de um ecrã sem campo nenhum é a contradição que
            faz quem lê duvidar do resto do ecrã. */}
        {comPassword ? (
          <p className="text-pretty text-sm text-muted-foreground">
            {textos.ativar.subtitulo}
          </p>
        ) : null}
      </div>

      {ativar.isError && !temErroDeCampo ? (
        <Aviso tom={aviso.tom} titulo={aviso.titulo} mensagem={mensagemDaRecusa(ativar.error)}>
          {codigo === CODIGO_CONVITE_EXIGE_SESSAO ? (
            // Entrar e **voltar ao link**: o `destino` é um caminho e viaja na
            // search param; o token continua no fragmento, que não chega ao
            // servidor. Levá-lo na query string para o trazer de volta punha-o
            // no log de acesso do proxy, que é a propriedade que a ADR 0010
            // existe para preservar.
            <Button asChild variant="outline" className="h-controlo">
              <Link to="/entrar" search={{ destino: "/ativar" }} hash={fragmento}>
                {textos.ativar.entrarComEstaConta}
                <ArrowRight aria-hidden="true" />
              </Link>
            </Button>
          ) : null}
          {codigo === CODIGO_CONVITE_DE_OUTRA_CONTA ? (
            <BotaoDeSair rotulo={textos.ativar.sairEEntrarComAConvidada} />
          ) : null}
          {codigo === CODIGO_CONVITE_INVALIDO ? (
            // Não há retry que valha: o convite não melhora à segunda
            // tentativa, e é por isso que o formulário desaparece. O que há é
            // uma **saída** — um estado sem saída é um beco, e quem tem um link
            // morto na mão tem de poder ir a algum sítio.
            <Button asChild variant="outline" className="h-controlo">
              <Link to="/entrar">
                {textos.ativar.irParaEntrada}
                <ArrowRight aria-hidden="true" />
              </Link>
            </Button>
          ) : null}
        </Aviso>
      ) : null}

      {comPassword ? (
        <form noValidate onSubmit={submeter} className="flex flex-col gap-4">
          <CampoDeTexto
            id="password"
            rotulo="Password"
            tipo="password"
            valor={password}
            aoMudar={setPassword}
            erro={errosLocais.get("password") ?? errosDoServidor.get("password")}
            // A pista diz a regra **antes** de se escrever, em vez de a
            // ensinar por tentativa. Quem a impõe são os
            // `AUTH_PASSWORD_VALIDATORS` do servidor, e o cliente não a
            // reimplementa: duas definições de "password forte" divergiriam na
            // primeira vez que a política mudasse.
            pista={textos.ativar.regraDaPassword}
            autoComplete="new-password"
            desativado={ativar.isPending}
          />
          <CampoDeTexto
            id="confirmacao"
            rotulo={textos.ativar.repitaAPassword}
            tipo="password"
            valor={confirmacao}
            aoMudar={setConfirmacao}
            erro={errosLocais.get("confirmacao")}
            autoComplete="new-password"
            desativado={ativar.isPending}
          />
          <Button
            type="submit"
            className="h-controlo w-full"
            disabled={ativar.isPending}
            aria-busy={ativar.isPending}
          >
            <KeyRound aria-hidden="true" />
            {ativar.isPending ? textos.ativar.aActivar : textos.ativar.activarEEntrar}
          </Button>
        </form>
      ) : null}

      {utilizador === null ? null : (
        // De quem é a sessão. Numa página de activação isto não é decoração: o
        // `convite_de_outra_conta` acontece **por** ser outra conta, e ver o
        // email é como quem está à frente do ecrã percebe qual.
        <p className="text-xs text-muted-foreground">
          {textos.ativar.sessaoDe} <span className="font-mono">{utilizador.email}</span>
        </p>
      )}
    </div>
  );
}
