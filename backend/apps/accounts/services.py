"""As únicas escritas do `accounts` (CLAUDE.md: nenhuma escrita fora de services).

Duas famílias de funções, e vale a pena separá-las na cabeça antes de ler o
código, porque a fronteira transacional de cada uma é diferente.

**A família das pertenças** — `criar_tenant`, `criar_tenant_com_dono`,
`conceder_pertenca`, `revogar_pertenca`. O que as junta é **um invariante**, não
um caso de uso: o `User.tenant_ids` espelha as pertenças ativas e é escrito na
mesma transação que qualquer `Membership` (ADR 0007). Um invariante sem um único
escritor é um comentário; com um, é verificável — e está verificado em
`tests/test_rls_isolation.py`.

**A família da sessão** — `iniciar_sessao`, `terminar_sessao`, `sessao_atual`,
`escolher_tenant_ativo` (ADR 0010). O que escrevem é a **sessão**, e a sessão é
a única coisa neste módulo que escolhe um âmbito sem o conceder: a política é
que o concede (ADR 0007). Estão aqui, e não nas views, porque o que elas
contêm é precisamente a parte que não pode ser escrita de outra ordem — ver
`iniciar_sessao`.

Nenhuma destas funções emite um evento de domínio, e a ADR 0010 fecha a questão
em vez de a deixar em aberto: **zero eventos e zero tarefas no v1**, porque não
existe consumidor da outbox e um evento sem subscritor é um contrato público
escrito ao contrário. O que ainda não tem endpoint — convite, aceitação,
reposição de password — é a tarefa seguinte da mesma ADR.

## Por que razão o `tenant_ids` não é recalculável

A tentação é `tenant_ids = [m.tenant_id for m in user.memberships.filter(is_active=True)]`.
Não funciona, e falha em silêncio: o `accounts_membership` tem política, logo
dentro de `tenant_scope(A)` essa varredura só vê as pertenças de A e o array
passava a ter **uma** entrada, apagando as outras. A manutenção é incremental
por desenho — junta-se um uuid ao conceder, retira-se ao revogar — e é a razão
pela qual as duas funções que tocam num `Membership` são também as duas que
tocam no array.

## Quem abre a transação

`criar_tenant` e `criar_tenant_com_dono` **são** a fronteira: abrem o
`tenant_scope` elas mesmas, porque são chamadas de fora de um pedido com âmbito
(um comando `manage.py`) e porque criar um tenant é, literalmente, gerar o UUID
em Python e inserir de dentro do âmbito desse UUID — a política do
`accounts_tenant` compara `id`, não há `WITH CHECK` separado, e
`id = app.tenant_id` é verdade (ADR 0007).

`conceder_pertenca` e `revogar_pertenca` correm **dentro** de um âmbito já
aberto (o do pedido, ou o que a criação do tenant acabou de abrir) e o seu
`transaction.atomic()` é um savepoint, como manda a ADR 0005. Nenhuma delas abre
`tenant_scope`: um `tenant_scope` dentro de uma transação que não é sua deixa o
GUC colado a essa transação depois de fechar. É também por isso que
`criar_tenant` **não** leva um `transaction.atomic()` por fora — isso punha a
transação antes do `set_config`.

## E porque é que as funções da sessão não levam `@transaction.atomic`

Esta é a excepção à regra da casa ("uma função por caso de uso, com
`@transaction.atomic`"), e não é preguiça: é o mecanismo da ADR 0005 a tornar a
regra impossível aqui. A descoberta de estabelecimentos confirma **cada**
candidato no **seu** `tenant_scope`, e o `tenant_scope` não é reentrante para
outro tenant (um `set_config` local dentro de um savepoint vive até ao fim da
transação de topo). Com um `@transaction.atomic` por fora, o primeiro candidato
abriria o âmbito e o segundo levantaria `TenantScopeConflict` — ou seja, um
utilizador com dois estabelecimentos não conseguiria entrar. São N transações
curtas, fechadas uma antes de a seguinte abrir, e N é 1 para quase todos
(ADR 0007).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID, uuid4

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.password_validation import validate_password
from django.contrib.postgres.fields import ArrayField
from django.db import models, transaction
from django.db.models import F, Func, Value
from django.http import HttpRequest
from django.utils import timezone

from apps.accounts.api import TenantOption, UserOut, tenant_context, utilizador_atual
from apps.accounts.middleware import CODIGO_DESCONHECIDO, SESSION_TENANT_KEY
from apps.accounts.models import Membership, Papel, Tenant, User
from apps.shared.db import TenantScopeConflict, current_tenant, tenant_scope

__all__ = [
    "CODIGOS_DE_RECUSA",
    "CODIGO_CREDENCIAIS_INVALIDAS",
    "EstadoDaSessao",
    "PrimeiroDono",
    "RecusaDeSessao",
    "SessaoOut",
    "conceder_pertenca",
    "criar_tenant",
    "criar_tenant_com_dono",
    "escolher_tenant_ativo",
    "iniciar_sessao",
    "revogar_pertenca",
    "sessao_atual",
    "terminar_sessao",
]

logger = logging.getLogger(__name__)

#: Código estável de credenciais recusadas (400). A ADR 0010 fixa-o, e o corpo
#: é o **mesmo** para um email que não existe, uma password errada e uma conta
#: inativa: dizer "este email não existe" confirma a um estranho quais os
#: emails são clientes, e o `accounts_user` é a tabela sem política (ADR 0007).
CODIGO_CREDENCIAIS_INVALIDAS = "credenciais_invalidas"

#: A frase genérica que acompanha o código acima. Uma constante e não um
#: literal em três sítios: a propriedade que interessa é que seja **uma** frase.
DETALHE_CREDENCIAIS_INVALIDAS = "Email ou password incorretos."

#: A frase do 403 da troca de estabelecimento. Reutiliza o código que o
#: `TenantMiddleware` já definiu (`tenant_desconhecido`) de propósito: é a mesma
#: condição — a política não devolveu pertença ativa — e o frontend já sabe o
#: que fazer com ela (limpar o estabelecimento ativo e voltar ao seletor).
DETALHE_TENANT_DESCONHECIDO = "Não tem acesso ativo a este estabelecimento."

#: Os códigos que uma `RecusaDeSessao` pode transportar, em lista fechada. Quem
#: lhes dá um status HTTP é o `views.py`, e há um teste que afirma que os dois
#: conjuntos são iguais — nos dois sentidos. Sem ele, um código novo sem status
#: dava `KeyError` na view (500 numa recusa de login) e um status a mais ficava
#: lá a dizer que existe um código que não existe.
CODIGOS_DE_RECUSA: frozenset[str] = frozenset(
    {CODIGO_CREDENCIAIS_INVALIDAS, CODIGO_DESCONHECIDO}
)


def criar_tenant(*, name: str) -> Tenant:
    """Cria um tenant, abrindo o âmbito dele para o poder inserir.

    O UUID é gerado aqui e não pela base de dados: é preciso conhecê-lo
    **antes** do `INSERT` para o poder pôr no `app.tenant_id`, que é o que faz a
    linha passar a própria política que a vai proteger.
    """
    tenant_id = uuid4()
    with tenant_scope(tenant_id):
        return Tenant.objects.create(id=tenant_id, name=name)


@dataclass(frozen=True, kw_only=True, slots=True)
class PrimeiroDono:
    """O resultado de `criar_tenant_com_dono`, para quem o chama poder relatar.

    `utilizador_criado` é `False` quando o email já existia: nesse caso a
    password **não** foi tocada, e quem corre o comando tem de saber disso — ver
    o docstring de `criar_tenant_com_dono`.
    """

    tenant: Tenant
    user: User
    utilizador_criado: bool


def criar_tenant_com_dono(
    *,
    nome: str,
    email: str,
    display_name: str,
    password: str | None,
) -> PrimeiroDono:
    """Cria um estabelecimento e a sua primeira pertença `owner`, numa transação.

    É o caso de uso que a ADR 0010 dá ao operador: **o tenant nasce por
    operador e não por registo self-service no v1**, por três razões que não são
    de conveniência — o que fazer com um NIF já existente está em aberto, o NIF
    do tenant exige encriptação de campo com pepper (`SECURITY.md` §3), e o
    `billing` é fase 3, pelo que um formulário aberto cria tenants sem limite.

    ## Uma transação, e porque é que não chama `criar_tenant`

    As três escritas — `accounts_tenant`, `accounts_user` e
    `accounts_membership` — correm dentro de **um** `tenant_scope`, logo ou
    acontecem as três ou nenhuma. Chamar `criar_tenant` aqui daria duas
    transações (ele abre e fecha o âmbito dele), e uma falha no meio deixava um
    estabelecimento sem pertença nenhuma: inerte e invisível, mas lá. O
    `Tenant.objects.create` repetido é o preço, e é uma linha.

    Escrever no `accounts_user` de dentro de um âmbito é o normal e não é fuga
    de âmbito: a tabela não tem política (ADR 0007) e é o que o `_espelhar` já
    faz.

    ## A password de uma conta que já existe não se toca

    Se o email já existir, esta função **não** lhe mexe na password e devolve
    `utilizador_criado=False`. A razão é a mesma que a ADR 0010 dá à aceitação
    de convites: a password é global e a pertença é por tenant, pelo que
    "criar um estabelecimento e definir a password do dono" daria a quem corre o
    comando a tomada de uma conta existente — com os outros estabelecimentos
    dela lá dentro.

    `password=None` cria a conta com `set_unusable_password()`, que é a forma
    certa de uma conta por convite (ver o `UserManager`). Quem exige uma
    password utilizável é o comando `manage.py`, porque hoje não há caminho de
    activação nenhum — e isso é requisito do fluxo do operador, não desta
    função.
    """
    if password is not None:
        # As regras do `AUTH_PASSWORD_VALIDATORS` (mínimo 12 caracteres, não
        # comum, não numérica) valem aqui e não só na API: a primeira conta do
        # sistema é a que abre tudo, e um comando que as salte seria a porta
        # mais fraca da casa. O `User` por gravar é só para o
        # `UserAttributeSimilarityValidator` poder comparar com o email.
        validate_password(password, user=User(email=email))

    tenant_id = uuid4()
    with tenant_scope(tenant_id):
        tenant = Tenant.objects.create(id=tenant_id, name=nome)
        # Pelo `get_by_natural_key` e não por um `filter(email=...)`: é lá que
        # vive a definição de "a mesma conta" (insensível à caixa, pelo índice
        # funcional `LOWER(email)`), e duas definições divergem com o tempo.
        try:
            user = User.objects.get_by_natural_key(email)
            utilizador_criado = False
        except User.DoesNotExist:
            user = User.objects.create_user(email, password)
            utilizador_criado = True
        conceder_pertenca(
            user=user,
            tenant_id=tenant_id,
            role=Papel.OWNER,
            display_name=display_name,
        )
        # Dentro do âmbito, para a linha de log levar o `tenant_id` pelo
        # `ContextVar` (`config/log.py`): é o único identificador que liga esta
        # operação ao estabelecimento que ela criou.
        logger.info(
            "estabelecimento criado por operador",
            extra={"event": "tenant_criado", "outcome": "ok"},
        )

    return PrimeiroDono(tenant=tenant, user=user, utilizador_criado=utilizador_criado)


def conceder_pertenca(
    *,
    user: User,
    tenant_id: UUID,
    role: str,
    display_name: str,
) -> Membership:
    """Dá (ou reativa) a pertença de um utilizador a este tenant.

    Idempotente pelo `UniqueConstraint(user, tenant)`: conceder duas vezes
    atualiza o papel e o nome exibido em vez de levantar. É o comportamento que
    um convite reenviado precisa.
    """
    _exigir_ambito(tenant_id)
    if role not in {p.value for p in Papel}:
        raise ValueError(f"papel desconhecido: {role!r}")

    with transaction.atomic():
        membership, _ = Membership.objects.update_or_create(
            user=user,
            tenant_id=tenant_id,
            defaults={"role": role, "display_name": display_name, "is_active": True},
        )
        _espelhar(user, tenant_id, pertence=True)
    return membership


def revogar_pertenca(*, user: User, tenant_id: UUID) -> bool:
    """Desativa a pertença e retira o âmbito da lista de candidatos.

    Devolve se havia alguma coisa para revogar. O array é podado nas duas
    situações: se não há pertença ativa neste tenant, o uuid não pode ficar lá —
    é isso que "espelha as pertenças ativas" quer dizer.

    A sessão de quem for revogado não é tocada: ela guarda um UUID e zero
    autorização, e o pedido seguinte leva 403 do `TenantMiddleware`.
    """
    _exigir_ambito(tenant_id)

    with transaction.atomic():
        revogadas = Membership.objects.filter(
            user=user,
            tenant_id=tenant_id,
            is_active=True,
        ).update(is_active=False, updated_at=timezone.now())
        _espelhar(user, tenant_id, pertence=False)
    return revogadas > 0


def _exigir_ambito(tenant_id: UUID) -> None:
    """O âmbito aberto tem de ser o deste tenant, senão a política recusaria.

    Não é uma verificação defensiva a mais: sem âmbito, o `INSERT` levaria
    `new row violates row-level security policy` e o `UPDATE` afetaria zero
    linhas **sem erro** — que é a forma silenciosa do mesmo bug.
    """
    ativo = current_tenant()
    if ativo != tenant_id:
        raise TenantScopeConflict(
            f"escrita em accounts_membership para {tenant_id} com o âmbito em "
            f"{ativo}: a política filtra por app.tenant_id e o UPDATE afetaria "
            "zero linhas sem erro (ADR 0005, ADR 0007)."
        )


def _espelhar(user: User, tenant_id: UUID, *, pertence: bool) -> None:
    """Junta ou retira o âmbito do `tenant_ids`, na transação da chamada.

    Escreve-se no `accounts_user`, que não tem política: uma escrita de dentro
    de `tenant_scope(A)` numa tabela sem política é normal e não é uma fuga de
    âmbito — o que a coluna diz é "este utilizador pode *tentar* A", e tentar
    não concede nada.

    ## `array_append` no Postgres, e não ler-modificar-escrever em Python

    A versão óbvia — `user.tenant_ids = sorted({*user.tenant_ids, tenant_id})`
    seguido de `save()` — é uma leitura, uma modificação e uma escrita em três
    passos, e a contabilista que é convidada para dois tenants ao mesmo tempo
    perde uma das entradas: a segunda transação escreve por cima do array que
    leu antes de a primeira commitar. É uma atualização perdida clássica, e o
    sintoma é benigno mas confuso — falta um estabelecimento no seletor, sem
    erro nenhum em sítio nenhum.

    Numa instrução só não há janela: o `array_append`/`array_remove` corre
    sobre o valor que a linha tem no momento do `UPDATE`, e o
    `exclude(tenant_ids__contains=...)` (o `@>` do Postgres) é o que torna a
    operação idempotente sem um `SELECT` à frente. O `refresh_from_db` a seguir
    é o que mantém a instância em memória de acordo com a linha — sem ele, o
    chamador ficava com um array velho.

    `updated_at` é `auto_now`, logo **não** é atualizado por
    `QuerySet.update()`: vai à mão, como manda o docstring do `TenantModel`.
    """
    valor = Value(tenant_id, output_field=models.UUIDField())
    campo = ArrayField(models.UUIDField())
    linhas = User.objects.filter(pk=user.pk)
    if pertence:
        linhas = linhas.exclude(tenant_ids__contains=[tenant_id])
        funcao = "array_append"
    else:
        linhas = linhas.filter(tenant_ids__contains=[tenant_id])
        funcao = "array_remove"

    alteradas = linhas.update(
        tenant_ids=Func(F("tenant_ids"), valor, function=funcao, output_field=campo),
        updated_at=timezone.now(),
    )
    if alteradas:
        user.refresh_from_db(fields=["tenant_ids", "updated_at"])


# ---------------------------------------------------------------------------
# A sessão (ADR 0010). O que estas quatro funções escrevem é a sessão, e a
# sessão escolhe o âmbito sem o conceder: a política é que o concede (ADR 0007).
# ---------------------------------------------------------------------------
class EstadoDaSessao(models.TextChoices):
    """Em que ponto da entrada está quem faz o pedido.

    A ADR 0010 pede um campo de **estado** na resposta, e a razão é de desenho
    e não de cosmética: com ele, um segundo factor passa a ser mais um estado no
    mesmo endpoint em vez de um endpoint novo (MFA é dívida nomeada do
    `SECURITY.md` §5). Os quatro valores de hoje são os quatro que a ADR 0007
    descreve para o fim do login, e **não** há um quinto para MFA — um valor de
    enum que nada produz é uma promessa no `types.ts` do frontend que ninguém
    cumpre.

    É um `TextChoices` para o `ChoiceField` do serializer o emitir como enum no
    OpenAPI: a união chega ao `types.ts` commitado e o `switch` do frontend
    deixa de poder esquecer um ramo.
    """

    ANONIMO = "anonimo", "sem sessão"
    SEM_ESTABELECIMENTO = "sem_estabelecimento", "sem estabelecimento associado"
    ESCOLHA_PENDENTE = "escolha_pendente", "à espera da escolha do estabelecimento"
    ATIVA = "ativa", "sessão com estabelecimento ativo"


@dataclass(frozen=True, kw_only=True, slots=True)
class SessaoOut:
    """O que os quatro endpoints de autenticação devolvem. Sempre o mesmo.

    Uma forma só para login, logout, leitura e troca de estabelecimento: o
    cliente guarda-a numa entrada de cache e qualquer das quatro respostas a
    substitui, em vez de haver quatro formas e quatro ramos de Zod.

    Congelado, como os DTOs do `api.py`: isto é o resultado de uma decisão de
    autorização e não um acumulador.
    """

    estado: str
    utilizador: UserOut | None
    tenant_ativo: TenantOption | None
    tenants: tuple[TenantOption, ...]
    #: Sempre vazio hoje, e de propósito. A projecção do menu por tenant é da
    #: ADR 0009 e a tabela dela não existe; o campo vai na resposta desde o
    #: primeiro dia para o cliente não ter de mudar de forma quando ela nascer,
    #: e vai **sem** forma de item declarada, porque declarar a tupla
    #: `(route_id, grupo, ordem, visivel, rotulo)` agora era inventar o
    #: contrato de outra ADR — e o `route_id` só vale como enum fechado vindo do
    #: backend, que é o que torna o registo do frontend exaustivo.
    menu: tuple[object, ...] = ()


class RecusaDeSessao(Exception):
    """Recusa com um `code` estável no corpo, que é o que o cliente ramifica.

    O status HTTP não basta e isso já está escrito no `TenantMiddleware`: o
    `SessionAuthentication` do DRF também responde 403 a anónimos. Quem traduz
    este código em status é o `views.py` — o mapa vive lá porque é transporte,
    e um service que soubesse status HTTP era um service a saber HTTP.
    """

    def __init__(self, codigo: str, detalhe: str) -> None:
        super().__init__(detalhe)
        self.codigo = codigo
        self.detalhe = detalhe


def iniciar_sessao(request: HttpRequest, *, email: str, password: str) -> SessaoOut:
    """Autentica, abre a sessão e descobre os estabelecimentos. Nesta ordem.

    A ordem é a parte que não pode ser escrita de outra maneira, e é por isso
    que esta função existe em vez de três linhas numa view (ADR 0007):

    1. `authenticate()`, com o `AxesStandaloneBackend` à frente — é ele que
       recusa quando a conta está em lockout, **antes** de qualquer verificação
       de password;
    2. `login()`, que roda a chave de sessão (`cycle_key()`, ou `flush()` se a
       sessão anterior era de outro utilizador) e o token de CSRF
       (`rotate_token`);
    3. só depois o tenant. Escrever o `tenant_id` na sessão **antes** do
       `login()` perdia-o em silêncio no caminho do `flush`, deixando uma sessão
       autenticada sem estabelecimento — e o sintoma aparecia a dois pedidos de
       distância, como um 403 `sem_sessao` inexplicável.

    ## O `request` é o `HttpRequest` do Django e não o `Request` do DRF

    Não é detalhe: o `Request` do DRF proxia as **leituras** de atributo para o
    pedido por baixo, mas uma escrita fica no invólucro. O axes marca o lockout
    com `request.axes_locked_out = True` e o `AxesMiddleware` lê esse atributo
    no `HttpRequest` — passar aqui o `Request` do DRF fazia a decisão de lockout
    ser tomada e a resposta 429 ser **perdida**, com o cliente a receber o 400
    de credenciais como se nada fosse. Quem resolve qual é o objeto é o
    `views.py`, porque é transporte.

    ## A recusa é genérica, e o 429 vem de outro lado

    Email inexistente, password errada e conta inativa dão o **mesmo** 400
    `credenciais_invalidas`: distinguir confirmava a um estranho quais os emails
    são clientes. O 429 do lockout não é levantado aqui — o `AxesMiddleware`
    substitui a resposta desta view quando o axes marcou o pedido, e o corpo
    JSON desse 429 está em `config/lockout.py`.
    """
    user = authenticate(request, email=email, password=password)
    if user is None:
        # Sem o email na mensagem nem nos `%`-args: a `message` não passa pela
        # allowlist do `config/log.py` e um email ali era PII em claro. Quem
        # conta tentativas por conta é o axes, que já tem o valor.
        logger.warning(
            "login recusado",
            extra={"event": "login", "outcome": CODIGO_CREDENCIAIS_INVALIDAS},
        )
        raise RecusaDeSessao(CODIGO_CREDENCIAIS_INVALIDAS, DETALHE_CREDENCIAIS_INVALIDAS)

    login(request, user)

    try:
        tenants = _tenants_confirmados(user)
    except Exception:
        # "Se a descoberta falhar, a view faz `flush()`" (ADR 0007): nunca fica
        # uma sessão autenticada com um estabelecimento que não se confirmou.
        # O `raise` nu mantém o erro — isto não é tratamento, é limpeza.
        request.session.flush()
        raise

    # "Um candidato confirmado escreve-se na sessão" (ADR 0007). Com vários, a
    # sessão fica sem estabelecimento até haver escolha: adivinhar qual seria
    # escolher o âmbito em nome de quem tem de o escolher.
    ativo = tenants[0] if len(tenants) == 1 else None
    if ativo is not None:
        request.session[SESSION_TENANT_KEY] = str(ativo.id)

    logger.info(
        "sessão iniciada",
        extra={"event": "login", "outcome": "ok", "count": len(tenants)},
    )
    return _sessao(request, tenants=tenants, ativo=ativo)


def terminar_sessao(request: HttpRequest) -> SessaoOut:
    """Fecha a sessão e devolve a forma de sempre, já no estado `anonimo`.

    O `logout()` do Django faz `flush()`: apaga a linha do `django_session` e
    gera uma chave nova, logo o `tenant_id` que lá estava desaparece com o
    resto. Não há nada para limpar à mão.

    Devolve `SessaoOut` em vez de 204 por uma razão de cliente: a resposta cabe
    na mesma entrada de cache que as outras três, e o frontend fecha a sessão
    com um pedido só em vez de um POST seguido de um GET.
    """
    logout(request)
    logger.info("sessão terminada", extra={"event": "logout", "outcome": "ok"})
    return SessaoOut(
        estado=EstadoDaSessao.ANONIMO,
        utilizador=None,
        tenant_ativo=None,
        tenants=(),
    )


def sessao_atual(request: HttpRequest) -> SessaoOut:
    """A sessão como ela é agora: quem, onde, e onde mais poderia estar.

    É o endpoint que a SPA chama no arranque, e faz duas coisas:

    * **relata.** Um pedido anónimo devolve 200 com `estado = anonimo` e não
      403: o cliente tem de poder perguntar "há sessão?" sem ter sessão, senão o
      arranque da aplicação depende de distinguir dois 403 diferentes;
    * **repara, e só repara.** Se a sessão nomear um estabelecimento que a
      política já não concede — pertença revogada, estabelecimento apagado —, a
      chave sai da sessão aqui. Não é uma escolha: é não devolver uma resposta
      que se contradiz, porque a alternativa era um `tenant_ativo` a `null` ao
      lado de uma sessão que continua a nomeá-lo e a dar 403 em todos os outros
      endpoints.

    **Reparar não é escolher.** Com um candidato só e sem estabelecimento ativo,
    esta função não o activa: quem escolhe o âmbito é o `login` (que o faz uma
    vez, na entrada) e o `escolher_tenant_ativo`. Ter um `GET` a escolher
    âmbitos dava dois escritores para a mesma decisão, e o frontend não ganhava
    nada — o caminho "um candidato, nenhum ativo" é o mesmo POST que o caminho
    de vários.
    """
    utilizador = utilizador_atual(request)
    if utilizador is None:
        return SessaoOut(
            estado=EstadoDaSessao.ANONIMO,
            utilizador=None,
            tenant_ativo=None,
            tenants=(),
        )

    tenants = _tenants_confirmados(request.user)
    ativo = _ativo_da_sessao(request, tenants)
    return _sessao(request, tenants=tenants, ativo=ativo)


def escolher_tenant_ativo(request: HttpRequest, *, tenant_id: UUID) -> SessaoOut:
    """Põe este estabelecimento como ativo na sessão, se a política o conceder.

    É a inversão da ADR 0007 no sítio onde ela é mais fácil de escrever ao
    contrário: o `tenant_id` que vem no corpo é **argumento e não credencial**.
    Quem o verifica é a política, dentro de `tenant_scope(tenant_id)`, contra a
    pertença de quem pede — não o `tenant_ids` do utilizador, que apenas
    *propõe* âmbitos e cuja falha documentada é propor um que a política depois
    recusa. Filtrar por ele aqui tornava um índice em fonte de autorização.

    Um uuid forjado escolhe um âmbito onde a query — que leva
    `user_id = <o de quem pede>` no `WHERE` — não devolve nada, e nenhuma linha
    do estabelecimento alheio é lida no caminho.

    ## O que não acontece

    A chave de sessão **não** roda (ADR 0007): a rotação é um controlo de
    fixação ligado à autenticação, e esta sessão já tinha acesso a esta conta
    antes e depois. O que a troca precisa é de registo, e é o que leva.

    A escrita na sessão fica **fora** do `tenant_scope`: a sessão é escrita pelo
    `SessionMiddleware` depois de a transação do pedido fechar (ADR 0005), e
    atribuí-la dentro do bloco só sugeria o contrário a quem lê.

    ## Chamada sem utilizador autenticado, se um dia acontecer

    Quem exige autenticação é a view (`IsAuthenticated`). Se uma view futura se
    esquecer, o `request.user` é o `AnonymousUser`, o `pk` é `None`, e a query
    da pertença fica com `user_id IS NULL` numa coluna `NOT NULL`: zero linhas,
    e a recusa de sempre. O esquecimento falha fechado, que é o comportamento
    que esta casa escolhe — mas é a view que tem de declarar a regra, não este
    acidente de tipos.
    """
    with tenant_scope(tenant_id):
        contexto = tenant_context(request.user.pk, tenant_id)
        if contexto is None:
            logger.warning(
                "troca de estabelecimento recusada",
                extra={"event": "tenant_ativo", "outcome": CODIGO_DESCONHECIDO},
            )
            raise RecusaDeSessao(CODIGO_DESCONHECIDO, DETALHE_TENANT_DESCONHECIDO)
        escolhido = TenantOption(id=contexto.id, name=contexto.name, role=contexto.role)
        logger.info(
            "estabelecimento ativo escolhido",
            extra={"event": "tenant_ativo", "outcome": "ok"},
        )

    request.session[SESSION_TENANT_KEY] = str(escolhido.id)
    return _sessao(request, tenants=_tenants_confirmados(request.user), ativo=escolhido)


def _tenants_confirmados(user: User) -> tuple[TenantOption, ...]:
    """Os estabelecimentos deste utilizador, cada um confirmado no seu âmbito.

    O `tenant_ids` dá os **candidatos** e mais nada; o que confirma cada um é a
    política, dentro de `tenant_scope(candidato)` — e é lá que o nome do
    estabelecimento é legível, porque o `accounts_tenant` também tem política
    (ADR 0007).

    São N transações curtas, uma por candidato, fechadas antes de a seguinte
    abrir: o `tenant_scope` não é reentrante para outro tenant. N é 1 para quase
    todos e é o custo aceite da ADR 0007 — a alternativa (um disjunto de sistema
    na política do `Membership`) punha um privilégio de leitura cross-tenant no
    caminho do login, onde um `filter` esquecido despeja a tabela de pertenças
    inteira.

    Ordenado por nome: é uma lista que uma pessoa lê num seletor, e a ordem de
    inserção do array não quer dizer nada para ela. O `str(id)` é o desempate,
    para dois estabelecimentos com o mesmo nome não trocarem de lugar entre
    pedidos.

    O `dict.fromkeys` é barato e tira duplicados: o `_espelhar` não os produz,
    mas um array com um uuid repetido dava duas entradas iguais no seletor e uma
    transação a mais.
    """
    confirmados = []
    for candidato in dict.fromkeys(user.tenant_ids):
        with tenant_scope(candidato):
            contexto = tenant_context(user.pk, candidato)
        if contexto is not None:
            confirmados.append(
                TenantOption(id=contexto.id, name=contexto.name, role=contexto.role)
            )
    return tuple(sorted(confirmados, key=lambda opcao: (opcao.name, str(opcao.id))))


def _ativo_da_sessao(
    request: HttpRequest, tenants: tuple[TenantOption, ...]
) -> TenantOption | None:
    """O estabelecimento que a sessão nomeia, **se** estiver entre os confirmados.

    Não é uma segunda verificação de autorização: os `tenants` já vêm todos
    confirmados pela política, logo isto é só a interseção entre "o que a sessão
    diz" e "o que a política concede". Quando a interseção é vazia e a sessão
    dizia alguma coisa, a chave sai — ver `sessao_atual`.
    """
    nomeado = request.session.get(SESSION_TENANT_KEY)
    if not nomeado:
        return None
    for opcao in tenants:
        if str(opcao.id) == str(nomeado):
            return opcao
    del request.session[SESSION_TENANT_KEY]
    logger.info(
        "estabelecimento ativo limpo da sessão",
        extra={"event": "tenant_ativo", "outcome": CODIGO_DESCONHECIDO},
    )
    return None


def _sessao(
    request: HttpRequest,
    *,
    tenants: tuple[TenantOption, ...],
    ativo: TenantOption | None,
) -> SessaoOut:
    """Monta o `SessaoOut` de um pedido autenticado, com o estado derivado.

    O estado é **derivado** e nunca passado: se fosse argumento, haveria quatro
    sítios a decidi-lo e um deles a decidi-lo mal.

    O utilizador vem do `utilizador_atual` do `api.py` — a única construção do
    `UserOut` no módulo. No caminho do login isso depende de o `login()` do
    Django pôr `request.user = user`, o que ele faz; e há um teste que afirma o
    email na resposta do login, logo a suposição falha em vermelho se deixar de
    ser verdade.
    """
    utilizador = utilizador_atual(request)
    if ativo is not None:
        estado = EstadoDaSessao.ATIVA
    elif tenants:
        estado = EstadoDaSessao.ESCOLHA_PENDENTE
    else:
        estado = EstadoDaSessao.SEM_ESTABELECIMENTO
    return SessaoOut(
        estado=estado,
        utilizador=utilizador,
        tenant_ativo=ativo,
        tenants=tenants,
    )
