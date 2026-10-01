"""O contrato HTTP da autenticação, dos convites e da activação (ADR 0010).

Leitura e escrita em classes separadas, e os campos de escrita listados um a um
— nunca `fields = "__all__"` (CLAUDE.md, `SECURITY.md` §4). Aqui a separação
sai de graça: **nenhum destes serializers é um `ModelSerializer`**. Os de
escrita não têm modelo por trás (um pedido de login não cria uma linha, e o
convite é criado pelo service a partir de três campos), e os de leitura
serializam ou os dataclasses congelados de `services.py` e do `api.py`, ou — no
caso do `ConviteOutSerializer` — um `Invitation`, com **todos** os campos
declarados à mão. Não há, portanto, nenhum caminho por onde um campo novo de um
modelo apareça sozinho numa resposta: o `token_hash` não está na lista e não
pode passar a estar por acidente.

## Os nomes dos campos são portugueses, e é uma decisão

As respostas de domínio do projeto usam nomes ingleses (`base_unit`,
`display_unit`), porque espelham campos de modelos. Aqui o topo do contrato está
fixado em português pela ADR 0010 — `estado`, `utilizador`, `tenant_ativo`,
`tenants`, `menu` — e misturar os dois dentro do **mesmo** objeto (`estado` ao
lado de `name`) era o pior dos dois mundos. Logo os campos aninhados seguem o
topo: `nome` e `papel`, por `source=` sobre o `name` e o `role` dos dataclasses.
A fronteira entre as duas convenções passa a ser o módulo, que é uma fronteira
que se vê, e não o nível de aninhamento, que não se vê.

## O que **não** está aqui

A normalização do email. `Ana@x.pt` e `ana@x.pt` são a mesma conta, e quem o
decide é o `UserManager.get_by_natural_key` (pelo índice funcional
`LOWER(email)`) e o `AXES_USERNAME_CALLABLE` para o contador de tentativas. Um
`.lower()` neste serializer seria uma terceira definição de "a mesma conta" a
divergir com o tempo — e a que menos se vê.
"""

from __future__ import annotations

from rest_framework import serializers

from apps.accounts.models import EstadoDoConvite, Papel
from apps.accounts.services import LIMITE_DO_FRAGMENTO, EstadoDaSessao

__all__ = [
    "AtivacaoInSerializer",
    "ConviteCriadoOutSerializer",
    "ConviteInSerializer",
    "ConviteOutSerializer",
    "ErroOutSerializer",
    "LoginInSerializer",
    "SessaoOutSerializer",
    "TenantAtivoInSerializer",
    "TenantOutSerializer",
    "UtilizadorOutSerializer",
]


# ---------------------------------------------------------------------------
# Escrita
# ---------------------------------------------------------------------------
class LoginInSerializer(serializers.Serializer):
    """O corpo do `POST /auth/login`: um email e uma password, e nada mais.

    O `max_length` do email é o do `EmailField` do modelo (254, o limite do
    RFC 5321) e o da password é um teto de sanidade, não uma regra de força: a
    força é dos `AUTH_PASSWORD_VALIDATORS`, e **não** se valida aqui. Validar a
    força no login seria dizer a quem tenta entrar que a password que escreveu
    não poderia ser a desta conta — um oráculo barato sobre a política de
    passwords do sistema e, pior, uma recusa diferente da recusa genérica.

    `trim_whitespace=False` na password: um espaço final é um carácter da
    password de quem o escreveu, e o DRF corta-o por omissão nos `CharField`.
    No email o default (cortar) é o que se quer — ninguém tem um email com
    espaços nas pontas e um teclado de telemóvel acrescenta-os.
    """

    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(
        max_length=128,
        trim_whitespace=False,
        style={"input_type": "password"},
    )


class TenantAtivoInSerializer(serializers.Serializer):
    """O corpo do `POST /auth/tenant-ativo`: o estabelecimento a activar.

    É um **argumento e não uma credencial** (ADR 0007). O que este serializer
    garante é só que o valor é um UUID — quem verifica se quem pede tem pertença
    ativa lá é a política, dentro do `tenant_scope` que o service abre. Um
    `PrimaryKeyRelatedField` sobre `Tenant.objects` seria errado por duas razões
    e vale dizê-las: a queryset corre **fora** de âmbito, logo a política
    devolveria zero linhas e nenhum uuid passaria nunca; e com âmbito devolveria
    uma mensagem de validação a distinguir "não existe" de "não é teu".
    """

    tenant_id = serializers.UUIDField()


class ConviteInSerializer(serializers.Serializer):
    """O corpo do `POST /convites`: quem, com que papel, e com que nome.

    Os três campos são os que o `Membership` precisa no dia em que nascer, e
    nenhum deles é o token: quem gera o token é o service, com `secrets`, e um
    token que viesse do cliente era um token escolhido pelo cliente.

    O `nome` é o `display_name` **neste** estabelecimento — a mesma pessoa é
    "Ana Silva (contabilidade)" num e "Ana" noutro —, e quem o sabe é quem
    convida. Por isso viaja aqui e não no corpo da activação: quem aceita não
    escolhe como aparece na lista de membros de quem o convidou.

    Não há validação de duplicados aqui, e é deliberado: "já existe um convite
    pendente para este email" e "esta pessoa já é membro" são leituras à base de
    dados dentro do âmbito do pedido, logo pertencem ao service, que é quem tem
    a transação e quem as escreve. Validá-las aqui dava duas verificações, e a
    de cá nunca é a que a corrida perde.
    """

    email = serializers.EmailField(max_length=254)
    papel = serializers.ChoiceField(source="role", choices=Papel.choices)
    nome = serializers.CharField(source="display_name", max_length=150)


class AtivacaoInSerializer(serializers.Serializer):
    """O corpo do `POST /auth/ativar`: o fragmento do link e, talvez, a password.

    ## Um campo opaco, e o cliente não o divide

    O `fragmento` é o que vem depois do `#` no link — `<uuid-do-tenant>.<token>`
    — e viaja inteiro. A SPA lê-o do `location.hash` e põe-no no corpo sem o
    interpretar: quem o divide é o service, logo o formato do segredo tem **uma**
    definição e ela vive no servidor. Um contrato com `tenant_id` e `token`
    separados obrigava o cliente a conhecer o formato, e o dia em que ele mudasse
    eram dois sítios a mudar.

    O fragmento não chega ao servidor por acidente nenhum: não entra no log de
    acesso do proxy, não viaja em `Referer`, e um pre-fetch do cliente de email
    não consegue queimar um token de uso único (ADR 0010). É o POST que o traz.

    ## A password é opcional **porque o servidor é que sabe** se é precisa

    `required=False` e não `required=True`: uma conta que já tem password
    utilizável **não** a redefine ao aceitar um convite (ADR 0010) — a password é
    global e a pertença é por tenant, pelo que "convite + definir password" dava
    a quem pode convidar a tomada de uma conta existente, com os outros
    estabelecimentos dela lá dentro. Nesse caso a activação exige sessão e este
    campo é ignorado.

    `required=False` e **não** `default=""`, e a diferença é toda no cliente
    gerado: um campo com `default` chega ao `types.ts` como `password: string`
    (obrigatório, com um valor por omissão), e um campo sem ele chega como
    `password?: string`, que é a verdade — a activação de quem já tem conta não
    manda password nenhuma. O preço é um `.get("password", "")` na view, que é
    uma palavra.

    Quem decide é o service, depois de casar o convite, porque só aí se sabe que
    email está em jogo. A força da password também é validada lá, pelos
    `AUTH_PASSWORD_VALIDATORS` — e não aqui, porque o
    `UserAttributeSimilarityValidator` precisa do email do convite, que este
    serializer não pode ver sem ser o oráculo que a ADR fecha.

    `trim_whitespace=False` na password, como no login: um espaço final é um
    carácter da password de quem o escreveu.
    """

    fragmento = serializers.CharField(max_length=LIMITE_DO_FRAGMENTO)
    password = serializers.CharField(
        max_length=128,
        required=False,
        allow_blank=True,
        trim_whitespace=False,
        style={"input_type": "password"},
    )


# ---------------------------------------------------------------------------
# Leitura
# ---------------------------------------------------------------------------
class UtilizadorOutSerializer(serializers.Serializer):
    """Quem está autenticado: id e email, e mais nada.

    O `UserOut` do `api.py` traz também `is_active` e `is_staff`, e os dois
    ficam de fora. O `is_active` porque uma conta inativa não autentica, logo o
    campo só poderia valer `true` — um campo constante é ruído no contrato. O
    `is_staff` porque não há nada no frontend que dele dependa: o admin é uma
    aplicação à parte, num path próprio, e o que decide o que um pedido pode
    fazer é o papel do `Membership` (ADR 0007), nunca esta flag.

    O nome da pessoa também não está aqui: vive no `Membership`, é por
    estabelecimento ("Ana Silva (contabilidade)" num, "Ana" noutro) e entra no
    contrato quando houver um ecrã que o mostre.
    """

    id = serializers.UUIDField()
    email = serializers.EmailField()


class TenantOutSerializer(serializers.Serializer):
    """Um estabelecimento como o seletor o mostra: id, nome e o papel de quem vê.

    Serve as duas posições da resposta — o `tenant_ativo` e cada entrada de
    `tenants` — porque são a mesma coisa em dois estados, e duas classes
    idênticas davam dois componentes iguais no OpenAPI.

    O `papel` é o do par (utilizador, estabelecimento) e vem do `Membership`
    confirmado pela política: a mesma pessoa é dona de um e colaboradora noutro.
    Sai como enum fechado no OpenAPI, logo a união chega ao `types.ts`.
    """

    id = serializers.UUIDField()
    nome = serializers.CharField(source="name", max_length=200)
    papel = serializers.ChoiceField(source="role", choices=Papel.choices)


class SessaoOutSerializer(serializers.Serializer):
    """A resposta dos quatro endpoints de autenticação. Sempre esta forma.

    Uma forma só para login, logout, leitura da sessão e troca de
    estabelecimento: o cliente guarda-a numa entrada de cache e qualquer das
    quatro respostas a substitui, em vez de quatro formas e quatro ramos de Zod.

    `utilizador` e `tenant_ativo` são `null` em vez de ausentes, e isso é
    deliberado: um campo que às vezes não existe obriga o cliente a distinguir
    "não sei" de "não há", e aqui o servidor sabe sempre.
    """

    estado = serializers.ChoiceField(choices=EstadoDaSessao.choices)
    utilizador = UtilizadorOutSerializer(allow_null=True)
    tenant_ativo = TenantOutSerializer(allow_null=True)
    tenants = TenantOutSerializer(many=True)
    # Sempre `[]` hoje, e **sem** forma de item declarada: a projecção do menu
    # por estabelecimento é da ADR 0009 e a tabela dela não existe. Declarar
    # agora a tupla `(route_id, grupo, ordem, visivel, rotulo)` era inventar o
    # contrato de outra ADR, e o `route_id` só vale como enum fechado vindo do
    # backend — é isso que torna o registo de rotas do frontend exaustivo nos
    # dois sentidos. Até lá o campo chega ao `types.ts` como uma lista de
    # `unknown`, o que é exactamente a verdade: existe, está vazio, e a sua
    # forma ainda não é contrato.
    menu = serializers.ListField(child=serializers.JSONField())


class ConviteOutSerializer(serializers.Serializer):
    """Um convite como a listagem o mostra. **Sem token, e sem forma de o ter.**

    O token sai **uma vez**, na resposta do POST que o criou, como uma chave de
    API (ADR 0010): um token mostrável depois teria de ser guardado em claro, e
    o que esta tabela guarda é só o SHA-256. Esta classe é o sítio onde isso se
    vê — a lista de campos é explícita e o `token_hash` não está nela. Não é um
    `ModelSerializer`, logo nem um campo novo no modelo nem um `fields =
    "__all__"` distraído o podem pôr aqui.

    O `estado` é derivado dos três timestamps (ver `EstadoDoConvite`) e sai como
    enum fechado no OpenAPI, pelo que a união chega ao `types.ts` e o `switch`
    do frontend não pode esquecer um ramo. É o que o ecrã precisa para decidir
    que botão mostrar: `reenviar` num pendente ou expirado, `revogar` em tudo o
    que não foi aceite.

    O `expira_em` vai como data e não como "faltam 3 dias": o cliente formata o
    que quiser, e um número de dias calculado no servidor fica errado no ecrã de
    quem o deixou aberto.
    """

    id = serializers.UUIDField()
    email = serializers.EmailField()
    papel = serializers.ChoiceField(source="role", choices=Papel.choices)
    nome = serializers.CharField(source="display_name", max_length=150)
    estado = serializers.ChoiceField(choices=EstadoDoConvite.choices)
    expira_em = serializers.DateTimeField(source="expires_at")
    criado_em = serializers.DateTimeField(source="created_at")


class ConviteCriadoOutSerializer(serializers.Serializer):
    """A resposta de `criar` e de `reenviar`: o convite **e** o segredo, uma vez.

    Duas peças e não uma, porque têm tempos de vida diferentes: o `convite` é o
    que a listagem volta a mostrar sempre, e o `fragmento` é a única vez que
    este valor existe fora da cabeça do servidor. A separação diz isso ao
    cliente sem um comentário.

    O `fragmento` é `<uuid-do-tenant>.<token>` e é o que vai **depois do `#`**:
    o link é `${origin}/ativar#${fragmento}`. Quem o compõe é o frontend, porque
    é quem conhece a sua origem — o backend devolver um URL absoluto obrigava-o
    a conhecer o domínio da SPA, que é configuração que ele não tem e que em dev,
    em CI e em produção é diferente.

    E é o fragmento e não o path, por três razões que a ADR 0010 fixa: o
    fragmento não chega ao servidor, logo não entra no log de acesso do proxy;
    não viaja em `Referer`; e um pre-fetch do cliente de email não queima um
    token de uso único.
    """

    convite = ConviteOutSerializer()
    fragmento = serializers.CharField(max_length=LIMITE_DO_FRAGMENTO)


class ErroOutSerializer(serializers.Serializer):
    """O corpo de uma recusa: `code` estável para ramificar, `detail` para ler.

    É a mesma forma que o `TenantMiddleware` já devolve (`sem_sessao`,
    `tenant_desconhecido`, `tenant_divergente`), e está aqui para entrar no
    `schema.yml`: sem isto, o cliente gerado conhecia as respostas de sucesso e
    tratava as recusas como `unknown`, que é precisamente onde o frontend tem de
    ramificar.

    O `code` é uma string e não um enum fechado de propósito: o conjunto de
    códigos é **por endpoint** (`credenciais_invalidas` só no login,
    `conta_bloqueada` só no 429) e um enum único com a união de todos sugeria ao
    frontend ramos que aquele endpoint nunca devolve. Os códigos de cada resposta
    estão nos docstrings do `views.py`.
    """

    code = serializers.CharField()
    detail = serializers.CharField()
