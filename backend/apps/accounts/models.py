"""Identidade, tenants e pertenças — as três tabelas da ADR 0007.

Três tabelas, três respostas diferentes à mesma pergunta ("o que é que uma
ligação sem âmbito consegue ler?"), e nenhuma delas é "confia no código":

| Tabela                | Política RLS                  | Porquê                     |
|-----------------------|-------------------------------|----------------------------|
| `accounts_tenant`     | sim, sobre **`id`**           | a tabela *é* o tenant      |
| `accounts_membership` | sim, sobre `tenant_id`        | é a tabela da autorização  |
| `accounts_user`       | **não** — lista fechada       | o login lê antes do âmbito |

O bootstrap de identidade é circular por natureza: resolver o tenant é ler o
`Membership`, o `Membership` tem política, e uma leitura sem âmbito devolve
zero linhas — mas o âmbito não pode abrir antes de se saber o tenant. A ADR
0007 parte o ciclo com exatamente **um** bit legível fora de âmbito,
`User.tenant_ids`, que **propõe** âmbitos e não concede nenhum: a sessão
escolhe o âmbito, a política concede-o.

## Porque é que o `User` é tão pequeno

O `accounts_user` não tem política e não é por não ter `tenant_id`: é porque a
única query que corre antes de existir identidade nenhuma — o `WHERE email = %s`
do login — precisaria de uma porta na política, e uma política com uma porta
para o login não é uma política. A resposta é **encolher a tabela** em vez de
fingir que está protegida: o que fica legível por qualquer ligação da app é um
email e um hash de password, não um perfil. O nome exibido e o papel vivem no
`Membership`, que tem política — e é também o desenho certo, porque a mesma
pessoa é "Ana Silva (contabilidade)" num tenant e outra coisa noutro.

## O que estas tabelas **não** guardam, e onde isso está decidido

* **NIF do tenant** — entra na sessão da encriptação de campo (`nif_encrypted` +
  `nif_hmac` com pepper, SECURITY.md §3). Não é um campo a acrescentar depois
  sem essa decisão tomada: uma fatia dos clientes são ENI e faturam com o NIF
  pessoal do dono, logo é PII de pessoa singular.
* **Segredo TOTP** — a ADR 0007 põe-no nesta tabela, mas guardá-lo em claro é
  pior do que não o ter; entra com a mesma ADR de encriptação de campo.
* **Localizações de um membro** — vivem no `inventory`, numa tabela com
  `tenant_id` e política. Um FK de `accounts` para lá invertia o grafo de
  dependências (ARCHITECTURE.md §6b). O `accounts` sabe o papel, o `inventory`
  sabe as localizações.

## Escrever aqui

Nenhuma escrita passa por fora de `services.py` (CLAUDE.md). Em particular, o
`tenant_ids` do `User` e o `Membership` são escritos **na mesma transação** —
é o que mantém o array a espelhar as pertenças ativas — e quem o garante são as
duas funções de `apps/accounts/services.py`.
"""

from __future__ import annotations

from uuid import uuid4

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.contrib.postgres.fields import ArrayField
from django.db import models

from apps.shared.models import TenantModel

__all__ = ["Membership", "Papel", "Tenant", "User", "UserManager"]


class Papel(models.TextChoices):
    """O papel de um membro dentro de **um** tenant.

    Vive ao nível do módulo (e não aninhado no `Membership`) porque é um valor
    que atravessa a fronteira: o `apps/accounts/api.py` reexporta-o para as
    classes de permissão dos outros módulos poderem nomear um papel sem
    importar `models` (ARCHITECTURE.md §3).

    Não tem relação nenhuma com o `is_staff` do `User` — ver o docstring do
    `User`. `owner` é o dono do restaurante; `is_staff` é um operador do
    StockFlow.
    """

    OWNER = "owner", "dono"
    MANAGER = "manager", "gerente"
    STAFF = "staff", "colaborador"


class Tenant(models.Model):
    """Um cliente do StockFlow: um restaurante, uma pastelaria, um café.

    Tenant = NIF (decisão de domínio já registada): o dono de três pastelarias
    é **um** tenant com três localizações, porque recebe uma fatura de
    fornecedor que cobre entregas em duas lojas e transfere stock entre elas
    todos os dias. A localização é autorização por `Membership`, nunca política
    de RLS (ADR 0005).

    ## A política é sobre `id`, e a consequência para quem cria um tenant

    Esta tabela é a única cuja política compara `id` em vez de `tenant_id` —
    porque a tabela *é* o tenant. Não herda de `TenantModel` por isso mesmo: um
    FK para si própria não diria nada.

    Como não há `WITH CHECK` separado, o Postgres usa a expressão do `USING`
    também nas escritas. Logo criar um tenant é: gerar o UUID em Python, abrir
    `tenant_scope(esse uuid)` e inserir — `id = app.tenant_id` é verdade e a
    linha entra. Inserir com outro `id` de dentro desse âmbito é recusado pela
    própria política, e está provado em `tests/test_rls_isolation.py`.

    ## Sem `Meta.indexes`

    O índice do filtro por tenant é a chave primária: o predicado da política é
    `id = app.tenant_id`. Um índice composto `(tenant, -created_at)` — que é a
    forma de todas as listagens nas tabelas de domínio — aqui seria um índice
    sobre uma tabela que, dentro de um âmbito, tem no máximo uma linha visível.
    """

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    name = models.CharField(max_length=200, verbose_name="nome")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="criado em")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="atualizado em")

    class Meta:
        verbose_name = "tenant"
        verbose_name_plural = "tenants"

    def __str__(self) -> str:
        return self.name


class UserManager(BaseUserManager["User"]):
    """Criação de utilizadores com `email` como `USERNAME_FIELD`.

    Existe para o `createsuperuser` e para os services: o `BaseUserManager` do
    Django não traz `create_user` nem `create_superuser` (isso é do
    `UserManager` do `auth`, que assume `username`).

    Nenhum destes métodos escreve numa tabela com política, pelo que correm
    fora de âmbito — é o que o `createsuperuser` precisa.
    """

    def create_user(self, email: str, password: str | None = None, **extra: object) -> User:
        """Um utilizador com email normalizado e password em Argon2id.

        `password=None` deixa a conta sem password utilizável
        (`set_unusable_password`), que é a forma certa de criar uma conta por
        convite: quem a ativa define a password pelo caminho do reset.
        """
        if not email:
            raise ValueError("um utilizador precisa de email: é o USERNAME_FIELD.")
        user = self.model(email=self.normalize_email(email), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email: str, password: str | None = None, **extra: object) -> User:
        """Um operador do StockFlow. Ver o docstring do `User` sobre `is_staff`."""
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        if extra["is_staff"] is not True or extra["is_superuser"] is not True:
            raise ValueError("um superuser tem de ter is_staff e is_superuser a True.")
        return self.create_user(email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    """Credencial e flags, e mais nada (ADR 0007).

    O nome exibido, o telefone e o papel **não** estão aqui: vivem no
    `Membership`, que tem política RLS. O que uma ligação sem âmbito lê desta
    tabela é um email e um hash, não um perfil. O resto fecha-se na API, que é
    onde tem de se fechar: o `apps/accounts/api.py` não expõe pesquisa de
    utilizadores, e o convite e o reset de password respondem exatamente o
    mesmo para um email que existe e para um que não existe — sem isso, uma
    tabela global com `email` único é um oráculo de enumeração de contas.

    ## `is_staff` é para operadores do StockFlow e nunca para clientes

    Não tem relação nenhuma com `Membership(role="owner")`. O dono de uma
    pastelaria é `Papel.OWNER` no seu tenant e `is_staff = False`; quem tem
    `is_staff = True` é quem trabalha no StockFlow, entra no admin (com MFA,
    SECURITY.md §5) e vê apenas modelos **sem** política. Confundir os dois dava
    o admin a um cliente.

    ## `tenant_ids` é índice, não autorização

    É o único bit legível fora de âmbito, e é o que parte a circularidade do
    bootstrap: **propõe** os âmbitos que este utilizador pode tentar, e a
    política é que os concede. Consequências deliberadas:

    * é coluna e não tabela. Uma tabela de índice teria `tenant_id` sem
      política, que é a forma que o gate do `tests/test_db_roles.py` nunca pode
      deixar passar; uma coluna numa tabela que já não tem política não
      introduz forma nova;
    * não tem integridade referencial com o `accounts_tenant`, logo um tenant
      apagado deixa lá um uuid morto. Resolve-se num 403 ou numa ausência no
      login — benigno, precisamente porque o array não concede nada;
    * espelha as pertenças **ativas** e é escrito na mesma transação que
      qualquer `Membership` (`apps/accounts/services.py`). Não é recalculável
      por varredura: dentro de `tenant_scope(A)` a política só mostra os
      `Membership` de A, pelo que a manutenção é incremental por desenho.

    `editable=False` para não aparecer em `ModelForm` nenhum: é um espelho, não
    um campo de formulário.

    ## `PermissionsMixin`, e porque é que ele não é um perfil

    Traz `is_superuser`, `groups` e `user_permissions` — flags e duas tabelas de
    junção, que é o que o admin do Django precisa para decidir `has_perm`. Sem
    ele, `is_staff` não abria nada e o admin respondia com `AttributeError`. As
    duas tabelas de junção não têm `tenant_id` nem política, e estão na lista
    fechada do `tests/test_db_roles.py`.

    ## Uma decisão que **não** está tomada

    A unicidade do email é a do Postgres: sensível a maiúsculas. `Ana@x.pt` e
    `ana@x.pt` são duas contas, e o `normalize_email` do Django só normaliza o
    domínio. Se o produto quiser dobrar a caixa, é um
    `UniqueConstraint(Lower("email"))` e uma decisão sobre contas já existentes
    — conversa da sessão da autenticação, não desta.
    """

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    email = models.EmailField(unique=True, verbose_name="email")
    is_active = models.BooleanField(default=True, verbose_name="ativo")
    is_staff = models.BooleanField(
        default=False,
        verbose_name="operador do StockFlow",
        help_text="Acesso ao admin. Nunca para clientes — ver o papel no Membership.",
    )
    tenant_ids = ArrayField(
        models.UUIDField(),
        default=list,
        blank=True,
        editable=False,
        verbose_name="âmbitos que pode tentar",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="criado em")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="atualizado em")

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        verbose_name = "utilizador"
        verbose_name_plural = "utilizadores"

    def __str__(self) -> str:
        return self.email


class Membership(TenantModel):
    """Quem trabalha onde, e com que papel. É a tabela da autorização.

    Herda de `TenantModel` (`apps/shared/models.py`), que é o que lhe dá a
    chave UUID, o `tenant_id` que a política compara, os timestamps e o índice
    composto `(tenant_id, -created_at)` das listagens. Herdar daqui é também a
    declaração de que esta é uma tabela de dados de um tenant e que a migração
    que a cria tem de trazer o bloco de RLS.

    ## O `UniqueConstraint(user, tenant)` é também o índice do middleware

    A query do `TenantMiddleware` — uma por pedido, sem cache — é
    `WHERE user_id = %s AND tenant_id = %s AND is_active`, e resolve-se pelo
    índice único desta constraint. A constraint não é só integridade: é o plano
    de execução do caminho crítico.

    ## `is_active` em vez de apagar a linha

    Revogar um acesso é `is_active = False`, e a verificação é **por pedido**:
    a sessão guarda um UUID que o utilizador já conhece e zero autorização,
    pelo que revogar corta o acesso no pedido **seguinte** sem ninguém tocar em
    sessões. Apagar a linha teria o mesmo efeito e perdia o histórico de quem
    teve acesso a quê.

    ## `display_name` vive aqui e não no `User`

    A mesma pessoa é "Ana Silva (contabilidade)" num tenant e "Ana" noutro, e o
    `accounts_user` não tem política — um nome lá seria perfil legível por
    qualquer ligação da app. Aqui é um dado do tenant, protegido pela política.
    """

    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="memberships",
        verbose_name="utilizador",
    )
    role = models.CharField(
        max_length=20,
        choices=Papel.choices,
        verbose_name="papel",
    )
    is_active = models.BooleanField(default=True, verbose_name="ativa")
    display_name = models.CharField(max_length=150, verbose_name="nome exibido")

    class Meta(TenantModel.Meta):
        verbose_name = "pertença"
        verbose_name_plural = "pertenças"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "tenant"],
                name="membership_user_tenant_uniq",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.display_name} ({self.role})"
