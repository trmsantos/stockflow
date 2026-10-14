"""A porta do módulo `accounts` (ARCHITECTURE.md §3).

É o único ficheiro do `accounts` que outro módulo pode importar. Expõe quatro
coisas e nada mais:

1. **Os DTOs do contexto do pedido.** `request.tenant` é o `TenantContext`
   congelado daqui e **não** a instância do modelo (ADR 0007): nenhum módulo
   deve ser tentado a atravessar relações a partir dele — um `request.tenant`
   que fosse um `Tenant` dava-lhe acesso a tudo o que aponta para o tenant, a
   partir de qualquer view.
2. **As classes de permissão**, reexportadas de `accounts/permissions.py`.
   Escrever `obj.tenant_id == request.tenant.id` à mão em nove módulos é como
   um deles a escreve mal — e é precisamente a comparação que o SECURITY.md §5
   exige antes de qualquer outra regra.
3. **O mecanismo da dispensa de âmbito.** A dispensa é declarada na *view* e
   nunca numa lista de paths nas settings, e o default é ter âmbito: uma view
   que não declare nada é servida com âmbito, uma que não o consiga obter leva
   403 antes de o `get_response()` correr. Quem lê a declaração é o
   `TenantMiddleware`; quem a escreve usa `tenant_scope_exempt` daqui.
4. **A forma canónica de um email.** `normalizar_email` é a definição de "a
   mesma conta" (a unicidade é insensível à caixa — ver `models.py`), e é
   pública porque há um consumidor fora do módulo: o `AXES_USERNAME_CALLABLE`
   em `config/lockout.py`, que tem de contar as tentativas de login na mesma
   chave em que a conta existe. Uma segunda definição em qualquer outro sítio é
   um bug à espera de acontecer.

O que este ficheiro **não** expõe, de propósito: pesquisa de utilizadores. O
`accounts_user` é a tabela sem política (ADR 0007) e um endpoint que aceite um
email e diga se existe é um oráculo de enumeração de contas. As únicas leituras
suportadas são por `pk` do próprio (`utilizador_atual`) e, no login, por email —
que vive na view do login e não aqui.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from functools import wraps
from typing import TYPE_CHECKING, Any
from uuid import UUID

from django.http import HttpRequest

from apps.accounts.models import Papel, UserManager
from apps.accounts.permissions import PertenceAoTenant, TemPapel
from apps.accounts.selectors import membership_no_ambito
from apps.shared.db import TenantScopeConflict, current_tenant

if TYPE_CHECKING:
    # Só para o verificador: em runtime isto seria o ciclo que o
    # `semear_demonstracao` (no fim do ficheiro) descreve.
    from apps.accounts.services import DemonstracaoSemeada

__all__ = [
    "MembershipInfo",
    "Papel",
    "PertenceAoTenant",
    "TemPapel",
    "TenantContext",
    "TenantOption",
    "UserOut",
    "criar_tenant",
    "criar_usuario",
    "criar_membership",
    "obter_usuario_por_papel",
    "dispensa_declarada",
    "dispensar_ambito",
    "inicio_do_dia_de_negocio",
    "membership_atual",
    "normalizar_email",
    "opcao_de_tenant",
    "semear_demonstracao",
    "tenant_scope_exempt",
    "utilizador_atual",
]

#: Nome do atributo que declara a dispensa, igual ao do `TenantTask` da ADR
#: 0005 de propósito: é o mesmo conceito nos dois lados (pedido e tarefa) e
#: procura-se com um `grep` só.
ATRIBUTO_DE_DISPENSA = "tenant_scope_exempt"

#: Onde o `TenantMiddleware` publica o contexto. Constantes e não literais
#: espalhados: quem lê deve usar `membership_atual(request)`.
ATRIBUTO_TENANT = "tenant"
ATRIBUTO_MEMBERSHIP = "membership"


# ---------------------------------------------------------------------------
# DTOs. Congelados e com `slots`: um contexto de pedido que se pudesse mutar a
# meio do pedido é uma decisão de autorização a mudar debaixo dos pés de quem
# já a tomou.
# ---------------------------------------------------------------------------
@dataclass(frozen=True, kw_only=True, slots=True)
class TenantContext:
    """O âmbito **ativo** do pedido: é isto que `request.tenant` é.

    Três campos, os da ADR 0007. O `role` está aqui porque é o par
    (tenant, papel) que decide o que o pedido pode fazer, e ir buscá-lo outra
    vez em cada view seria uma segunda query por pedido.

    ## E **não** tem `demonstracao`, que é a decisão 1 da ADR 0018 feita tipo

    O estabelecimento de demonstração "é um tenant como qualquer outro, e nenhum
    endpoint sabe que ele existe: zero ramos, zero parâmetros". Isso é uma regra
    que se cumpre ou não se cumpre — a menos que a bandeira não esteja ao alcance
    de quem escreve uma view. Aqui está a diferença: `request.tenant.demonstracao`
    **não existe**, logo um `if` sobre ele não compila, e o dia em que alguém
    precisar de o escrever tem de acrescentar o campo a este DTO — que é um diff
    visível com esta secção ao lado a dizer porque não devia.
    
    O critério que decide o que entra aqui é o mesmo de sempre: **os campos que
    decidem autorização.** Que tipo de estabelecimento isto é não decide nada; é
    cromado, e vai no `TenantOption`, que é o que o seletor mostra.
    """

    id: UUID
    name: str
    role: str


@dataclass(frozen=True, kw_only=True, slots=True)
class TenantOption:
    """Um âmbito que o utilizador **pode tentar**, já confirmado pela política.

    Distinto do `TenantContext` por não ser o âmbito ativo: é uma das opções do
    seletor de estabelecimento. Quem o produz é o caminho do login e o da troca
    de tenant, que confirmam cada candidato do `User.tenant_ids` no **seu**
    `tenant_scope` (é lá que o nome do tenant é legível, porque o
    `accounts_tenant` tem política) — e esses endpoints entram na sessão da
    autenticação. A forma fica fixada aqui para o contrato não nascer no
    frontend.

    `demonstracao` entrou com a ADR 0018 e é a **única** diferença visível de um
    estabelecimento de demonstração. Vive aqui e não no `TenantContext` por uma
    razão que é a decisão 1 dessa ADR: o que isto alimenta é **cromado** — a
    faixa permanente da barra de topo e o item marcado no seletor —, e nenhum
    service ramifica nele. A secção correspondente do `TenantContext` explica o
    outro lado.
    """

    id: UUID
    name: str
    role: str
    demonstracao: bool


@dataclass(frozen=True, kw_only=True, slots=True)
class UserOut:
    """O utilizador como os outros módulos o veem: credencial e flags.

    Sem nome e sem telefone — esses vivem no `Membership` e saem no
    `MembershipInfo`. Não há aqui nada que uma ligação sem âmbito não pudesse
    já ler, o que é a consequência assumida de o `accounts_user` não ter
    política.
    """

    id: UUID
    email: str
    is_active: bool
    is_staff: bool
    #: A paleta que esta pessoa prefere (ADR 0016). Entra aqui e não num DTO
    #: próprio porque o `SessaoOut` já carrega o `UserOut` e o tema tem de chegar
    #: ao cliente no mesmo pedido que resolve a sessão — a primeira pintura
    #: depende dele e um round trip extra no caminho crítico era o relâmpago de
    #: volta. É o mesmo argumento com que a ADR 0011 pôs o menu na sessão.
    tema: str


@dataclass(frozen=True, kw_only=True, slots=True)
class MembershipInfo:
    """A pertença do pedido em curso: quem, onde, com que papel e que nome.

    É o que um módulo usa para carimbar um registo com o autor ("contado por
    Ana Silva") sem ir ao `accounts_user` e sem guardar o nome na sua própria
    tabela.
    """

    user_id: UUID
    tenant_id: UUID
    role: str
    display_name: str


# ---------------------------------------------------------------------------
# Dispensa de âmbito
# ---------------------------------------------------------------------------
def tenant_scope_exempt(vista: Any) -> Any:
    """Declara que esta view é servida **sem** âmbito de tenant.

    Aplica-se a uma função de view, a uma classe (Django ou DRF) ou, em último
    recurso, escreve-se `tenant_scope_exempt = True` no corpo da classe — o
    middleware lê os três. Devolve o que recebeu, para poder ser usado como
    decorador::

        @tenant_scope_exempt
        class LoginView(APIView):
            ...

    O que uma view dispensada **não** ganha é um âmbito por acidente: se toca
    em dados de um tenant, abre o `tenant_scope` ela mesma — é o que o login e
    a troca de tenant fazem, uma transação curta por candidato.
    """
    setattr(vista, ATRIBUTO_DE_DISPENSA, True)
    return vista


def dispensa_declarada(vista: Any) -> bool:
    """A view (ou a sua classe) declara dispensa de âmbito?

    Três sítios porque há três formas de uma view chegar ao resolver: a função
    decorada, o `view_class` que o `as_view()` do Django lá põe, e o `cls` que o
    `as_view()` do DRF lá põe. O default é `False` — o esquecimento falha
    fechado.
    """
    candidatos = (
        vista,
        getattr(vista, "view_class", None),
        getattr(vista, "cls", None),
    )
    return any(getattr(c, ATRIBUTO_DE_DISPENSA, False) for c in candidatos if c is not None)


def dispensar_ambito(urls: Any) -> Any:
    """Declara a dispensa numa árvore de URLs **já construída**, e devolve-a.

    Existe por uma razão só: o admin do Django. As suas views não são nossas
    para lhes pôr um atributo no sítio onde são escritas, e a alternativa —
    reconhecer o path do admin dentro do middleware — era a lista de paths nas
    settings que a ADR 0007 rejeita, agora escondida num `startswith`. Isto
    marca as views, que é onde a declaração tem de viver::

        path(settings.ADMIN_URL, dispensar_ambito(admin.site.urls))

    Aceita o trio `(patterns, app_namespace, instance_namespace)` que o
    `AdminSite.urls` devolve ou uma lista de patterns, e desce pelos
    `include()` aninhados (cada `ModelAdmin` é um deles). Marca os objetos que o
    resolver vai usar — o mesmo `get_urls()` não é chamado outra vez.
    """
    patterns = urls[0] if isinstance(urls, tuple) else urls
    _marcar(patterns)
    return urls


def _marcar(patterns: Iterable[Any]) -> None:
    for pattern in patterns:
        aninhados = getattr(pattern, "url_patterns", None)
        if aninhados is not None:
            _marcar(aninhados)
            continue
        try:
            tenant_scope_exempt(pattern.callback)
        except (AttributeError, TypeError):
            # Um método ligado não aceita atributos, e o `AdminSite.get_urls`
            # registra dois deles sem invólucro (`self.login`,
            # `self.autocomplete_view`). Aqui envolve-se o método num
            # invólucro marcado e é ele que passa a ser o callback do pattern:
            # marcar `Metodo.__func__` funcionaria mas escrevia numa classe do
            # Django, para todas as instâncias de `AdminSite` do processo.
            pattern.callback = tenant_scope_exempt(_involucro(pattern.callback))


def _involucro(callback: Any) -> Any:
    """Uma função que chama `callback` e a que se pode pôr um atributo."""

    @wraps(callback)
    def vista(*args: Any, **kwargs: Any) -> Any:
        return callback(*args, **kwargs)

    return vista


# ---------------------------------------------------------------------------
# O contexto do pedido
# ---------------------------------------------------------------------------
def membership_atual(request: HttpRequest) -> MembershipInfo | None:
    """A pertença que o `TenantMiddleware` confirmou para este pedido.

    Não faz query: o middleware já pagou a única que há, e é por isso que os
    módulos devem chamar esta função em vez de ir buscar o `Membership` outra
    vez. `None` só numa view dispensada de âmbito — nas outras, o middleware
    respondeu 403 antes de a view correr.
    """
    valor = getattr(request, ATRIBUTO_MEMBERSHIP, None)
    return valor if isinstance(valor, MembershipInfo) else None


def utilizador_atual(request: HttpRequest) -> UserOut | None:
    """O utilizador autenticado do pedido, sem query e sem PII do tenant.

    `None` para um pedido anónimo. Quem quer o nome da pessoa usa o
    `display_name` do `membership_atual`: é o nome dela **naquele** tenant.
    """
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return None
    return UserOut(
        id=user.pk,
        email=user.email,
        is_active=user.is_active,
        is_staff=user.is_staff,
        tema=user.tema,
    )


def opcao_de_tenant(user_id: UUID, tenant_id: UUID) -> TenantOption | None:
    """Confirma a pertença **dentro do âmbito já aberto** e devolve a opção.

    É a função que o login e a troca de estabelecimento usam depois de abrirem
    `tenant_scope(tenant_id)`: a sessão escolhe o âmbito, a política concede-o.
    `None` significa "a política não devolveu linha nenhuma" — o utilizador não
    tem pertença ativa nesse tenant, ou o tenant não existe.

    Exige que o âmbito aberto seja **o mesmo** `tenant_id`, e levanta se não
    for. Sem essa guarda, chamá-la fora de âmbito devolvia `None` por a
    política filtrar tudo, e o erro aparecia como "não tem acesso" em vez de
    como o bug que é.

    ## Chamava-se `tenant_context` e devolvia `TenantContext`, até 2026-10-07

    O nome era o errado e o tipo também, e só se viu quando a ADR 0018 pediu um
    campo. Os **dois** chamadores — a troca de estabelecimento e a lista de
    candidatos — convertiam o resultado num `TenantOption` na linha seguinte;
    quem constrói o `TenantContext` a sério é o `TenantMiddleware`, a partir da
    pertença, e nunca passou por aqui.

    Importa porque a alternativa era acrescentar `demonstracao` ao
    `TenantContext` para o fazer chegar ao seletor — isto é, pôr a bandeira do
    demo no contexto de autorização de **todos** os pedidos, que é exactamente a
    afordância que a decisão 1 da ADR 0018 não pode ter. Um campo no sítio errado
    é uma regra que passa a depender de disciplina.
    """
    ativo = current_tenant()
    if ativo != tenant_id:
        raise TenantScopeConflict(
            f"opcao_de_tenant({tenant_id}) com o âmbito em {ativo}: a pertença "
            "só é legível dentro de tenant_scope(tenant_id) — as políticas do "
            "accounts_membership e do accounts_tenant filtram por ele "
            "(ADR 0007)."
        )
    membership = membership_no_ambito(user_id=user_id, tenant_id=tenant_id)
    if membership is None:
        return None
    return TenantOption(
        id=membership.tenant_id,
        name=membership.tenant.name,
        role=membership.role,
        demonstracao=membership.tenant.is_demo,
    )



# ---------------------------------------------------------------------------
# A forma canónica de um email
# ---------------------------------------------------------------------------
def normalizar_email(valor: str | None) -> str:
    """A forma canónica de um email: é a definição de "a mesma conta".

    A unicidade do email é insensível à caixa (`models.py`), pelo que `Ana@x.pt`
    e `ana@x.pt` normalizam para o mesmo valor. A implementação é o
    `UserManager.normalize_email` e este é só a porta — a implementação fica
    onde o Django a chama, para não haver duas definições a divergir.

    É um `classmethod` por baixo: não toca na base de dados nem precisa do
    âmbito de tenant. Isso é requisito de quem a chama de fora, não detalhe —
    o `AXES_USERNAME_CALLABLE` corre no caminho crítico do login, de dentro da
    construção da query das tentativas, onde uma query a mais é uma recursão
    (ver o docstring de `config/lockout.py`).

    Não é um validador: um valor que não seja um email sai normalizado da mesma
    forma. Quem valida a forma é o `EmailField` do modelo ou o serializer.
    """
    return UserManager.normalize_email(valor)


# ---------------------------------------------------------------------------
# A porta do semeador de demonstração (ADR 0018)
# ---------------------------------------------------------------------------
def semear_demonstracao(
    *, email: str, nome: str, display_name: str
) -> DemonstracaoSemeada:
    """Cria um estabelecimento de demonstração e dá-o a uma conta que já existe.

    **É o import-linter que obriga a esta função existir, e é esse o ponto.** O
    `apps/demo/` é um módulo de fora, logo não pode importar
    `apps.accounts.services` — só esta porta. A ADR 0018 escolheu pôr o semeador
    num módulo próprio exactamente para isso: de dentro do `accounts` ele podia
    escrever nos `models.py` à mão, e de fora **tem** de entrar por aqui.

    ## Um invólucro com o import dentro do corpo, e não uma reexportação no topo

    O `services.py` importa deste ficheiro (os DTOs de contexto e as permissões),
    logo um `from apps.accounts.services import …` no topo seria um ciclo. A
    primeira versão disto era um import no fim do ficheiro com um `# noqa: E402`
    ao lado — e o `CLAUDE.md` proíbe `# noqa` no código, sem excepção. A regra
    está certa: a supressão escondia que havia uma forma sem ela.

    O import vive no corpo, que é o quebra-ciclos idiomático, e o tipo de retorno
    resolve-se pelo `from __future__ import annotations` (a anotação é uma string
    até alguém a avaliar) mais o `TYPE_CHECKING` no topo. Zero supressões.

    A regra de negócio inteira — não criar contas, um demo por pessoa, revogar os
    anteriores sem nunca tocar num estabelecimento a sério — está no service, que
    é onde vive a lógica (CLAUDE.md). Aqui está a porta e mais nada.
    """
    from apps.accounts.services import semear_demonstracao as _semear

    return _semear(email=email, nome=nome, display_name=display_name)


# ---------------------------------------------------------------------------
# Criação de dados para o semeador de demonstração
# ---------------------------------------------------------------------------
def criar_tenant(*, name: str, id: UUID | None = None) -> object:
    """Cria um novo tenant. Consumidor: `apps/demo`."""
    from apps.accounts.models import Tenant

    return Tenant.objects.create(
        id=id,
        name=name,
        is_demo=True,
    )


def criar_usuario(*, email: str, password: str, is_active: bool = True) -> object:
    """Cria um novo usuário. Consumidor: `apps/demo`."""
    from apps.accounts.models import User

    return User.objects.create_user(
        email=email,
        password=password,
        is_active=is_active,
    )


def criar_membership(
    *,
    user_id: UUID,
    tenant_id: UUID,
    role: str,
    display_name: str,
    is_active: bool = True,
) -> object:
    """Cria uma membership. Consumidor: `apps/demo`."""
    from apps.accounts.models import Membership, Tenant, User

    user = User.objects.get(id=user_id)
    tenant = Tenant.objects.get(id=tenant_id)

    return Membership.objects.create(
        user=user,
        tenant=tenant,
        role=role,
        display_name=display_name,
        is_active=is_active,
    )


def obter_usuario_por_papel(*, tenant_id: UUID, role: str) -> object:
    """Obtém um usuário de um tenant por papel. Consumidor: `apps/demo`."""
    from apps.accounts.models import User

    return User.objects.get(memberships__tenant_id=tenant_id, memberships__role=role)


# ---------------------------------------------------------------------------
# Configuração do estabelecimento
# ---------------------------------------------------------------------------
def inicio_do_dia_de_negocio(*, tenant_id: UUID) -> object:
    """A hora de início do dia de negócio, para o `/receipts/summary`.

    Lê do estabelecimento ativo e devuelve um objeto `time`.
    """
    from apps.accounts.models import Tenant

    tenant = Tenant.objects.get(id=tenant_id)
    return tenant.business_day_starts_at
