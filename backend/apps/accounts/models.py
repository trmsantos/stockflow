"""Identidade, tenants, pertenças, convites e o menu (ADR 0007, 0010 e 0011).

Cinco tabelas, e a mesma pergunta respondida de três maneiras ("o que é que
uma ligação sem âmbito consegue ler?"). Nenhuma das respostas é "confia no
código":

| Tabela                      | Política RLS            | Porquê                    |
|-----------------------------|-------------------------|---------------------------|
| `accounts_tenant`           | sim, sobre **`id`**     | a tabela *é* o tenant     |
| `accounts_membership`       | sim, sobre `tenant_id`  | é a tabela da autorização |
| `accounts_invitation`       | sim, sobre `tenant_id`  | **o link nomeia o tenant**|
| `accounts_tenantmenuitem`   | sim, sobre `tenant_id`  | configuração de um tenant |
| `accounts_user`             | **não** — lista fechada | o login lê antes do âmbito|

A terceira linha é a que contraria o instinto, e é a decisão central da ADR
0010. Um convite é lido **antes** de existir sessão, como o login — logo o
reflexo é pô-lo na lista das tabelas sem política. Não é preciso: o link é
`/ativar#<uuid-do-tenant>.<token>`, a view de activação abre
`tenant_scope(uuid que vem do link)` e lê o convite **lá dentro**. É a inversão
da ADR 0007 com o link no lugar da sessão — **o link escolhe o âmbito, a
política concede-o** —, e o uuid é argumento e não credencial: forjá-lo escolhe
um âmbito onde nenhum `token_hash` existe. A alternativa punha email, papel e
`tenant_id` de todos os convites pendentes de **todos** os clientes legíveis por
qualquer ligação da app, ao preço evitável de não pôr um uuid no link.

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

from typing import Any
from uuid import uuid4

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone

from apps.shared.models import TenantModel

__all__ = [
    "EstadoDoConvite",
    "Invitation",
    "Membership",
    "Papel",
    "RotaDeMenu",
    "Tenant",
    "TenantMenuItem",
    "User",
    "UserManager",
]


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
    """Criação e **procura** de utilizadores com `email` como `USERNAME_FIELD`.

    Existe para o `createsuperuser` e para os services: o `BaseUserManager` do
    Django não traz `create_user` nem `create_superuser` (isso é do
    `UserManager` do `auth`, que assume `username`).

    Nenhum destes métodos toca numa tabela com política, pelo que correm fora
    de âmbito — é o que o `createsuperuser` e o login precisam.

    ## A caixa do email define-se aqui; os outros sítios delegam

    A unicidade do email é insensível à caixa (ver o docstring do `User`), o que
    exige as duas metades no mesmo sítio: **normalizar na escrita**
    (`normalize_email`, por onde `create_user` e `create_superuser` passam os
    dois) e **procurar sem caixa na autenticação** (`get_by_natural_key`, que é
    o que o `ModelBackend` chama). Faltar uma delas dá o pior dos dois mundos:
    criar `ana@x.pt` e não conseguir entrar com `Ana@x.pt`.

    Os outros três sítios que precisam da regra não a reimplementam: o
    `User.normalize_username` (formulários), o `accounts.api.normalizar_email`
    (porta pública) e o `AXES_USERNAME_CALLABLE` (contador de tentativas)
    chamam esta função. Um `.lower()` espalhado pelas views não serve — as views
    de autenticação ainda nem existem, e a que aparecer não pode ter de se
    lembrar disto.
    """

    @classmethod
    def normalize_email(cls, email: str | None) -> str:
        """A forma canónica de um email: tudo em minúsculas.

        O `normalize_email` do Django só normaliza o **domínio** (`x.PT` →
        `x.pt`) e deixa a parte local como veio, porque o RFC 5321 permite que
        um servidor a trate como sensível à caixa. Na prática nenhum fornecedor
        de email o faz, e a decisão do produto é que `Ana@x.pt` e `ana@x.pt` são
        a mesma conta — logo a parte local desce também.

        `lower()` e não `casefold()`: o índice único é sobre `LOWER(email)` no
        Postgres, e é com essa função que este valor tem de concordar. O
        `casefold()` do Python dobra mais do que o `lower()` do SQL (`ß` → `ss`)
        e as duas normalizações passariam a discordar — a constraint é a rede,
        mas uma rede que não coincide com a regra é uma fonte de bugs.
        """
        return super().normalize_email(email).lower()

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

    def get_by_natural_key(self, username: str) -> User:
        """O utilizador com este email, **sem** olhar à caixa.

        É a função que o `ModelBackend.authenticate` chama para achar a conta
        (`django/contrib/auth/backends.py:65`), e é por isso o sítio onde a
        autenticação fica insensível à caixa — não numa view, nem num
        serializer, nem num `.lower()` a cada chamador.

        O predicado é `LOWER(email) = %s`, e não `email = %s` sobre o valor
        normalizado, por duas razões:

        * é **a expressão do índice único** (`user_email_lower_uniq`), logo o
          Postgres resolve o login por esse índice em vez de varrer a tabela. Um
          `email__iexact` não serviria: o Django gera
          `UPPER(email::text) LIKE UPPER(%s)`, que o índice não cobre;
        * encontra a conta mesmo que a linha não esteja canónica. A normalização
          na escrita é a regra, mas o admin edita o `email` por `ModelForm` e o
          `User.normalize_username` é que o dobra lá — se um dia esse caminho
          mudar, o login continua a funcionar em vez de falhar como
          "credenciais inválidas".
        """
        return self._por_email(username).get()

    async def aget_by_natural_key(self, username: str) -> User:
        """A versão assíncrona, que o `ModelBackend.aauthenticate` usa.

        Existe para não haver uma segunda definição de "o mesmo email": sem a
        sobreposição, o caminho assíncrono do Django caía no
        `BaseUserManager.aget_by_natural_key`, que compara o email tal e qual e
        seria sensível à caixa — uma incoerência que só aparecia no dia em que
        alguém escrevesse uma view `async`.
        """
        return await self._por_email(username).aget()

    def _por_email(self, username: str) -> models.QuerySet[User]:
        """A queryset de um email na forma canónica. Uma linha, ou nenhuma."""
        return self.annotate(email_canonico=Lower("email")).filter(
            email_canonico=self.normalize_email(username)
        )


class Tema(models.TextChoices):
    """As três paletas, e a lista é a mesma do `tokens.css` (ADR 0015).

    Vive ao nível do módulo como o `Papel` e o `RotaDeMenu`, e pela mesma razão:
    é um valor que atravessa a fronteira do contrato. Chega ao `types.ts` como
    enum fechado do OpenAPI, logo o `Record` do cliente que traduz tema em
    rótulo é exaustivo contra **esta** lista, nos dois sentidos, sob
    `pnpm typecheck`.

    O `escuro` é o default porque é a identidade aprovada (DESIGN.md §1) e porque
    é a paleta que vive na `:root` sem atributo. Um valor fora desta lista no
    `data-tema` não selecciona bloco nenhum e dá o escuro — a queda é o default e
    não um ecrã sem cores, o que é o que torna o espelho local da ADR 0016
    seguro de escrever.
    """

    ESCURO = "escuro", "Escuro"
    MEIO_TERMO = "meio_termo", "Meio termo"
    CLARO = "claro", "Claro"


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
    `is_staff = True` é quem trabalha no StockFlow, entra no admin e vê apenas
    modelos **sem** política. Confundir os dois dava o admin a um cliente.

    O admin **não** exige MFA: não está implementada e é dívida nomeada no
    SECURITY.md §5. Esta docstring dizia que exigia, e a frase sobreviveu à
    limpeza que a tirou do `admin.py` e do §5 — uma afirmação falsa espalhada
    por quatro ficheiros precisa de ser caçada nos quatro.

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

    ## A unicidade do email é insensível à caixa

    `Ana@x.pt` e `ana@x.pt` são **a mesma conta**. Não era assim: o default do
    Postgres é sensível à caixa e o `normalize_email` do Django só dobra o
    domínio. A decisão foi tomada agora, com zero contas criadas, e a altura é
    a razão — mais tarde seria este índice mais uma política de reconciliação
    para as contas que já existissem, e essa política não tem resposta boa (qual
    das duas contas fica? o que acontece aos dados de cada uma?).

    Três peças, e são precisas as três:

    * `UniqueConstraint(Lower("email"))` — a regra na base de dados, que vale
      mesmo para uma escrita que não passe pelo manager (o admin, um
      `loaddata`, uma migração de dados). É a rede, como a RLS: o
      `email = %s` que o Postgres compara continua sensível à caixa, e o que
      torna a coluna única sem caixa é o índice funcional;
    * `UserManager.normalize_email` — a regra no código, na escrita;
    * `UserManager.get_by_natural_key` — a mesma regra na leitura da
      autenticação. Sem ela, criar `ana@x.pt` e tentar entrar com `Ana@x.pt`
      dava "credenciais inválidas", que é pior do que ter duas contas.

    E fora do Django, o contador de tentativas do `django-axes`: ele conta por
    conta usando o valor que vem do formulário, **sem** o normalizar, pelo que
    5 tentativas repartidas entre `ana@` e `Ana@` não trancavam nada. Está
    resolvido no `AXES_USERNAME_CALLABLE` (`config/lockout.py`).

    ### Porque é que o `unique=True` do campo fica

    Parece redundante — se `LOWER(email)` é único, `email` também é — e não é
    removível: o check `check_user_model` do Django exige que o `USERNAME_FIELD`
    seja único e só aceita `unique=True` no campo ou um `UniqueConstraint`
    **sobre o campo**. Um sobre uma expressão não conta: o
    `Options.total_unique_constraints` filtra `contains_expressions`
    (`options.py:973`) e é essa lista que o
    `django/contrib/auth/checks.py:71` consulta —
    `User._meta.total_unique_constraints` é `[]` com a constraint nova lá.
    Tirar o `unique=True` dava `auth.W004` (aviso, e não o `auth.E003`, porque
    os `AUTHENTICATION_BACKENDS` não são só o `ModelBackend` — o axes vem à
    frente), e o `check --deploy` sem avisos é um gate do SECURITY.md §9.

    A consequência prática é ter duas unicidades sobre a mesma coluna. O índice
    do campo não é desperdício puro: é o que serve a ordenação por email do
    admin, e é ele que a `0001_initial` já criou — o `unique=True` ficar
    poupa também um `AlterField` numa migração a uma tabela já aplicada.
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
    # A preferência de paleta (ADR 0016). **Uma coluna e não uma tabela**, pelo
    # precedente que a ADR 0007 escreveu para o `tenant_ids`: uma tabela de
    # índice teria `tenant_id` sem política, que é a forma que o gate nunca pode
    # deixar passar; uma coluna numa tabela que já não tem política não
    # introduz forma nova. As duas listas fechadas do `tests/test_db_roles.py`
    # não mexem, e é esse o sinal de que isto não abriu excepção.
    #
    # A ADR 0007 manda **encolher** esta tabela, porque é a que o role da app lê
    # sem âmbito nenhum — e essa regra é sobre o que um atacante aprende sobre
    # identidade e sobre o grafo de pertenças. "Esta conta prefere o claro" não
    # acrescenta nada a nenhum dos dois.
    #
    # `db_default` **além** do `default`, e não é redundância: o `default` é do
    # Django e só vale para escritas que passem pelo ORM desta versão do código.
    # Num deploy em rolling o código **antigo** continua a inserir linhas sem
    # esta coluna, e sem um default na base de dados esses inserts falhavam —
    # é o primeiro erro da checklist da skill de migrações, e o Django 5 tem
    # `db_default` precisamente para o fechar.
    tema = models.CharField(
        max_length=16,
        choices=Tema.choices,
        default=Tema.ESCURO,
        db_default=Tema.ESCURO,
        verbose_name="tema",
        help_text="A paleta que esta pessoa prefere. Preferência da pessoa, não da empresa.",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="criado em")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="atualizado em")

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        verbose_name = "utilizador"
        verbose_name_plural = "utilizadores"
        constraints = [
            # A unicidade insensível à caixa. Sobre uma expressão, logo o
            # Postgres implementa-a como índice único funcional e **não** como
            # constraint de tabela: `ADD CONSTRAINT ... UNIQUE USING INDEX` não
            # aceita índices de expressão. É por isso que a migração a cria com
            # um `CREATE UNIQUE INDEX CONCURRENTLY` dentro de um
            # `SeparateDatabaseAndState`, e não com o `AddConstraint` que o
            # `makemigrations` gera.
            models.UniqueConstraint(Lower("email"), name="user_email_lower_uniq"),
        ]

    def __str__(self) -> str:
        return self.email

    @classmethod
    def normalize_username(cls, username: Any) -> Any:
        """Dobra a caixa do `USERNAME_FIELD` em qualquer caminho de `ModelForm`.

        É o gancho que o `AbstractBaseUser.clean()` chama
        (`django/contrib/auth/base_user.py:75`), e o `clean()` corre em todo o
        `full_clean()` — ou seja, no formulário do admin, que é o único sítio
        onde hoje se edita um email fora do manager. O default do Django
        normaliza a forma Unicode (NFKC) e mais nada.

        Delega no `normalize_email` do manager para não haver duas definições de
        "a mesma conta" a divergir com o tempo. `Any` na assinatura porque é o
        que o gancho recebe de facto: o `clean()` corre **mesmo quando o
        `clean_fields()` já falhou**, logo o valor pode ser `None` ou outra
        coisa que o campo vai recusar. Nesse caso passa tal e qual, como no
        Django — normalizar um `None` para `""` trocava o erro de validação por
        outro.
        """
        if not isinstance(username, str):
            return username
        return UserManager.normalize_email(super().normalize_username(username))


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


class EstadoDoConvite(models.TextChoices):
    """Em que ponto da sua vida está um convite. **Derivado**, nunca guardado.

    Não é uma coluna, e isso não é economia: uma coluna de estado ao lado dos
    três timestamps que a determinam são duas fontes de verdade, e a que se
    esquece de ser atualizada é sempre a coluna. `expirado` fecha a questão —
    nenhum `UPDATE` acontece quando um convite expira, logo um estado guardado
    estaria errado sete dias depois de ter sido escrito.

    É um `TextChoices` para o `ChoiceField` do serializer o emitir como enum
    fechado no OpenAPI: a união chega ao `types.ts` commitado e o `switch` do
    frontend deixa de poder esquecer um ramo. A lista está fechada num teste.
    """

    PENDENTE = "pendente", "à espera de activação"
    EXPIRADO = "expirado", "expirou sem ser usado"
    ACEITE = "aceite", "aceite, com pertença criada"
    REVOGADO = "revogado", "revogado por quem convidou"


class Invitation(TenantModel):
    """Um convite para pertencer a **este** tenant, com um token ao portador.

    Herda de `TenantModel`, que lhe dá a chave UUID, o `tenant_id` que a
    política compara, os timestamps e o índice `(tenant_id, -created_at)` da
    listagem. Herdar daqui é também a declaração de que esta é uma tabela de
    dados de um tenant e que a migração que a cria traz o bloco de RLS — ver a
    tabela no topo do módulo para a decisão de a ter.

    ## O token é uma credencial ao portador, e o `tenant_id` da sessão não é

    A diferença obriga ao resto (ADR 0010). O `tenant_id` que a sessão guarda
    não concede nada e é um UUID que o utilizador já conhece; **este token é a
    única coisa entre um estranho e um `Membership`**. Logo: 32 bytes de
    `secrets`, guardado **só** como SHA-256, uso único, 7 dias, revogável, e no
    **fragmento** do URL.

    **SHA-256 e não Argon2id**, ao contrário da password do `User`: o segredo
    tem 256 bits de entropia e não é adivinhável por dicionário, pelo que o
    fator de trabalho de um KDF não compra nada e paga-o em cada activação. O
    que o hash entrega é a propriedade que interessa — quem lê a tabela (um
    backup, um `pg_dump`, o `stockflow_owner`) não consegue usar nenhum convite.

    **O hash é único, e a unicidade é global e atravessa a política de
    propósito.** É a rede contra a única forma de este desenho falhar: o mesmo
    token entregue a dois tenants. Não é um oráculo entre clientes porque
    nenhum cliente escolhe um `token_hash` — o valor é gerado no servidor, e
    quem activa manda o token em claro e nunca o hash. A unicidade dá também o
    índice que a ADR 0010 pede para esta coluna, sem o declarar duas vezes.

    ## `display_name` vem no convite, e não é adorno

    O `Membership` nasce na aceitação e pelo `conceder_pertenca`, que exige um
    `display_name` — o nome **neste** estabelecimento, que é um dado do tenant e
    vive na tabela com política (ver o `Membership`). Quem o sabe é quem
    convida, não quem aceita: é por isso que viaja no convite.

    ## Uma pertença não nasce aqui

    O convite não cria `Membership` nenhum (ADR 0010): seria uma concessão de
    acesso que ninguém reclamou, e um `tenant_ids` a propor um âmbito sem pessoa
    atrás. O que existe entre o convite e a aceitação é uma linha nesta tabela e
    mais nada.

    ## Três timestamps nulos, e o estado é a sua leitura

    `accepted_at`, `revoked_at` e `expires_at` determinam o `estado`. A
    unicidade do convite **pendente** por `(tenant, email)` é uma constraint
    parcial sobre os dois primeiros — `expires_at` não pode entrar na condição
    porque `now()` não é imutável e o Postgres recusa-o num índice. A
    consequência é deliberada e está no `services.criar_convite`: um convite
    expirado continua a ocupar o lugar, e a saída é reenviá-lo ou revogá-lo, não
    um segundo convite para o mesmo email no mesmo estabelecimento.

    ## `invited_by` não aparece na API

    Guarda quem convidou, porque é a única resposta persistida à pergunta "quem
    deu acesso a esta pessoa" — a ADR 0010 não o pede e os logs não são uma base
    de dados. Não entra no `ConviteOut`: mostrá-lo como nome exigia o
    `display_name` da pertença de quem convidou, que é um join que nenhum ecrã
    pediu. `SET_NULL` e não `CASCADE`: apagar a conta de quem convidou não pode
    apagar o registo de um convite que ela fez a outra pessoa.
    """

    email = models.EmailField(verbose_name="email convidado")
    role = models.CharField(
        max_length=20,
        choices=Papel.choices,
        verbose_name="papel",
    )
    display_name = models.CharField(max_length=150, verbose_name="nome exibido")
    token_hash = models.CharField(
        max_length=64,
        editable=False,
        verbose_name="SHA-256 do token",
    )
    expires_at = models.DateTimeField(verbose_name="expira em")
    accepted_at = models.DateTimeField(
        null=True,
        blank=True,
        editable=False,
        verbose_name="aceite em",
    )
    revoked_at = models.DateTimeField(
        null=True,
        blank=True,
        editable=False,
        verbose_name="revogado em",
    )
    invited_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        editable=False,
        verbose_name="convidado por",
    )

    class Meta(TenantModel.Meta):
        verbose_name = "convite"
        verbose_name_plural = "convites"
        constraints = [
            # Um convite pendente por (estabelecimento, email), com a caixa do
            # email dobrada pela mesma regra do `accounts_user`: `Ana@x.pt` e
            # `ana@x.pt` são a mesma conta (ver o `UserManager`), logo são também
            # o mesmo convite. Os `services.py` normalizam na escrita; isto é a
            # rede, como a RLS, e vale para uma escrita que não passe por lá.
            #
            # Expressões e `fields` são mutuamente exclusivos no
            # `UniqueConstraint`, por isso o `tenant` vai como expressão — o
            # Django converte a string em `F("tenant")`, que resolve para a
            # coluna `tenant_id`.
            models.UniqueConstraint(
                "tenant",
                Lower("email"),
                condition=models.Q(accepted_at__isnull=True, revoked_at__isnull=True),
                name="invitation_pendente_uniq",
            ),
            # O índice que a activação usa, e a rede contra o mesmo token em
            # dois estabelecimentos. É uma `UniqueConstraint` e **não**
            # `unique=True` no campo por uma razão medida: num campo de texto, o
            # `unique=True` faz o Django criar também um índice
            # `varchar_pattern_ops` para servir `LIKE`, e ninguém procura um
            # token por prefixo — era um segundo índice pago em cada convite
            # criado e em cada reenvio, para zero consultas.
            models.UniqueConstraint(
                fields=["token_hash"],
                name="invitation_token_hash_uniq",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.email} ({self.role})"

    @property
    def estado(self) -> str:
        """O `EstadoDoConvite` desta linha, lido dos três timestamps.

        A ordem dos ramos é a precedência: um convite aceite continua aceite
        depois de a data de expiração passar, e um revogado continua revogado.
        As duas primeiras condições são mutuamente exclusivas na base de dados —
        o `UPDATE` que aceita exige `revoked_at IS NULL` e o que revoga exige
        `accepted_at IS NULL`, ambos condicionais e portanto atómicos.
        """
        if self.accepted_at is not None:
            return EstadoDoConvite.ACEITE
        if self.revoked_at is not None:
            return EstadoDoConvite.REVOGADO
        if self.expires_at <= timezone.now():
            return EstadoDoConvite.EXPIRADO
        return EstadoDoConvite.PENDENTE


class RotaDeMenu(models.TextChoices):
    """A lista **fechada** de rotas que o menu de um tenant pode nomear.

    Vive ao nível do módulo como o `Papel`, e pela mesma razão: é um valor que
    atravessa a fronteira do contrato. Os defaults de cada rota — rótulo, grupo,
    ordem, papéis permitidos — não estão aqui, estão no `apps/accounts/menu.py`:
    isto é a lista de ids e aquilo é o registo, e separá-los é o que faz esta
    classe servir de `choices` de uma coluna sem arrastar metadados de
    apresentação para dentro de `models.py`.

    É um `TextChoices` para o `ChoiceField` do serializer o emitir como enum
    fechado no OpenAPI (`RotaIdEnum`, fixado em `SPECTACULAR_SETTINGS`): a união
    chega ao `types.ts` commitado e o `Record<RotaId, …>` do shell passa a ser
    exaustivo contra **a lista do backend**, nos dois sentidos, sob
    `pnpm typecheck`. É isso — e não a cardinalidade — que substitui a garantia
    dos "4 itens" que morreu com a tab bar (ADR 0009).

    Os sete ids são exactamente os do `frontend/src/shell/registo-de-rotas.ts`,
    que os escreveu primeiro (incluindo o `convites`, que entrou lá no mesmo dia
    em que esta tabela nasceu). Acrescentar um sétimo aqui **faz o
    `pnpm typecheck` do frontend falhar** até o `Record` dele o ter, e tirar um
    falha do mesmo modo pelo outro lado: é essa a propriedade que se compra, e é
    por isso que o id da rota do painel de configuração ainda não está nesta
    lista — a rota não existe na árvore da SPA.

    O valor é curto e estável de propósito: é uma chave de configuração guardada
    em linhas de clientes, e renomear um id é uma migração de dados.
    """

    INICIO = "inicio", "Início"
    PAINEL = "painel", "Painel de gestão"
    ALERTAS = "alertas", "Alertas"
    STOCK = "stock", "Stock"
    CONTAR = "contar", "Contar"
    RECEBER = "receber", "Receber"
    CONVITES = "convites", "Convites"


class TenantMenuItem(TenantModel):
    """A projecção do menu de **um** tenant sobre o registo de rotas (ADR 0011).

    Herda de `TenantModel`, que lhe dá a chave UUID, o `tenant_id` que a política
    compara, os timestamps e o índice `(tenant_id, -created_at)`. Herdar daqui é
    também a declaração de que esta é uma tabela de dados de um tenant e que a
    migração que a cria traz o bloco de RLS — e traz: `accounts_tenantmenuitem`
    aparece na varredura do `pg_class` do lado das tabelas **com** política e
    **não** entra em `SEM_POLITICA` (`tests/test_db_roles.py`, que falha nos dois
    sentidos). Esconder um item de menu é apresentação, mas a linha que o diz é
    configuração de um cliente, e configuração de um cliente não é legível por
    outro.

    ## Quatro colunas mutáveis, e porque é que isto não é um armazém chave/valor

    A ADR 0011 proíbe `chave`/`valor` e `JSONField` de settings, e a razão é um
    gate e não gosto: um blob geraria `Record<string, unknown>` no `types.ts` e o
    gate de diff do CI não veria nada — "um valor configurável que o TypeScript
    gerado não consegue nomear não é configuração, é um bug". Aqui cada coluna é
    tipada e aparece no `schema.yml`: `grupo` é texto, `ordem` é inteiro,
    `visivel` é booleano, `rotulo` é texto, e `route_id` é um enum fechado que o
    backend valida. O que esta tabela **não** tem é uma coluna onde caiba a
    próxima decisão adiada.

    ## A linha nasce na primeira escrita, e os defaults vivem em código

    ADR 0011, com estas palavras. Quem lê chama a projecção e recebe os defaults
    do `apps/accounts/menu.py` quando não há linha nenhuma — logo um tenant que
    nunca abriu o painel tem o menu completo, sem uma linha na tabela. O
    `accounts.criar_tenant` **não** as pode criar (o `accounts` não importa nada
    e nem precisaria de importar: criá-las seria escrever configuração que
    ninguém pediu, e um default guardado é um default que deixa de poder mudar),
    e fazê-lo por evento exigia o consumidor da outbox, que não existe.

    A consequência é que uma rota **ausente** da tabela e uma rota ausente do
    corpo de um `PUT` significam a mesma coisa: "este tenant não configurou
    isto". `visivel = False` é a forma de esconder, e é explícita.

    ## Unicidade `(tenant, route_id)`

    Uma rota tem uma configuração por tenant. Sem a constraint, duas linhas da
    mesma rota davam um menu com o item repetido e uma ordem que depende da
    ordem de leitura — e o `PUT` de substituição total não as consegue distinguir
    para as corrigir. É também o índice por onde a projecção filtra o tenant.

    ## Sem `REVOKE UPDATE, DELETE`, e sem registo no admin

    Isto não é um ledger: a configuração do menu é para mudar, e o `PUT` de
    substituição total apaga e reescreve as linhas do tenant numa transação. O
    `APPEND_ONLY` do `tests/test_db_roles.py` não muda (ADR 0006).

    E não entra no `admin.py`: o admin só registra modelos **sem** política
    (ADR 0007), e uma changelist desta tabela apareceria vazia a um operador
    sem `tenant_id` na sessão — "uma changelist vazia é uma armadilha
    operacional, onde alguém conclui que o cliente não tem dados".
    """

    route_id = models.CharField(
        max_length=32,
        choices=RotaDeMenu.choices,
        verbose_name="rota",
    )
    grupo = models.CharField(max_length=50, verbose_name="grupo")
    #: `PositiveSmallIntegerField` e não `IntegerField`: um menu com mais de
    #: 32767 posições não existe, e o teto na base de dados é a rede do
    #: `max_value` do serializer. Não é único — duas rotas com a mesma ordem
    #: desempatam pelo `route_id` na projecção, e obrigar a unicidade fazia
    #: reordenar exigir uma renumeração sem colisões intermédias, que é
    #: precisamente o problema que a `ordem` de dez em dez evita.
    ordem = models.PositiveSmallIntegerField(verbose_name="ordem")
    visivel = models.BooleanField(default=True, verbose_name="visível")
    #: Vazio — e nunca `NULL` — quer dizer "usa o rótulo do registo". Uma coluna
    #: de texto nulável é a armadilha que o `DJ001` do ruff nomeia: passava a
    #: haver dois valores para a mesma ausência. Quem traduz `""` para o `null`
    #: do contrato é a projecção, num sítio só.
    rotulo = models.CharField(max_length=50, blank=True, verbose_name="rótulo")

    class Meta(TenantModel.Meta):
        verbose_name = "item de menu"
        verbose_name_plural = "itens de menu"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "route_id"],
                name="tenantmenuitem_tenant_route_uniq",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.route_id} ({self.grupo}, {self.ordem})"
