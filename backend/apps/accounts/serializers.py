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

from collections import Counter
from datetime import time
from typing import Any

from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from apps.accounts.models import EstadoDoConvite, Papel, RegimeDeIva, RotaDeMenu, Tema
from apps.accounts.services import (
    DIA_DE_NEGOCIO_MAXIMO,
    DIA_DE_NEGOCIO_MINIMO,
    LIMITE_DO_FRAGMENTO,
    EstadoDaSessao,
)

__all__ = [
    "AtivacaoInSerializer",
    "ConviteCriadoOutSerializer",
    "ConviteInSerializer",
    "ConviteOutSerializer",
    "ErroOutSerializer",
    "ItemDeMenuInSerializer",
    "ItemDeMenuOutSerializer",
    "LoginInSerializer",
    "MenuInListSerializer",
    "RotaDeMenuOutSerializer",
    "SessaoOutSerializer",
    "TenantAtivoInSerializer",
    "TenantOutSerializer",
    "UtilizadorOutSerializer",
]

#: O teto do `rotulo` e do `grupo`, igual ao das colunas (ver o modelo). Uma
#: constante e não dois literais repetidos em três serializers: o que interessa
#: é que o limite do contrato e o da coluna sejam **o mesmo** número, senão a
#: recusa vem do Postgres em vez de vir como erro de validação por campo.
LIMITE_DO_ROTULO = 50
LIMITE_DO_GRUPO = 50

#: O teto da `ordem`, que é o do `PositiveSmallIntegerField`. Sem ele, um 99999
#: passava a validação do DRF e estourava no `INSERT` como 500 em vez de 400.
ORDEM_MAXIMA = 32767


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


class PreferenciasInSerializer(serializers.Serializer):
    """O corpo do `PATCH /auth/preferencias`: o tema que esta pessoa prefere.

    **Não tem `user_id`, e isso é a decisão.** A escrita é sempre sobre o
    `request.user`, logo não existe objecto para autorizar nem caminho para a
    preferência de outra pessoa — a forma do contrato é o que torna o abuso
    impossível, em vez de uma verificação que alguém pode esquecer. É a mesma
    mecânica com que o `tenant-ativo` recusa ser uma credencial, aplicada ao
    contrário: ali o argumento existe e é verificado pela política, aqui o
    argumento não existe.

    `ChoiceField` sobre o `Tema`: um valor fora da lista é um 400 do DRF e nunca
    chega à coluna. Isso importa mais do que parece, porque o cliente guarda uma
    **cópia** deste nome em `localStorage` (ADR 0016, decisão 3) e lê-a antes de
    haver rede — o valor ser fechado a três é o que torna essa cópia segura de
    escrever.
    """

    tema = serializers.ChoiceField(choices=Tema.choices)


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


class MenuInListSerializer(serializers.ListSerializer):
    """A lista do `PUT /menu`, e o único sítio onde o corpo é visto como um todo.

    Existe por uma razão que um `ItemDeMenuInSerializer` sozinho não consegue
    cumprir: **nenhuma rota pode aparecer duas vezes**. É uma afirmação sobre a
    forma do corpo — não precisa de ler nada à base de dados — pelo que é
    validação de serializer e não de service, ao contrário das recusas dos
    convites ("já é membro", "já tem convite pendente"), que são leituras dentro
    do âmbito.

    Sem isto, a recusa vinha do `tenantmenuitem_tenant_route_uniq` como
    `IntegrityError`, ou seja 500 numa situação que é um erro de cliente. A
    unicidade na base de dados continua a ser a rede, como a RLS.

    O erro sai em `non_field_errors` e não por campo: a duplicação é uma
    propriedade da lista e não de um dos seus elementos, e apontá-la ao índice
    `n` escolhia arbitrariamente uma das duas ocorrências.

    Não tem `max_length`: a lista não consegue ser mais comprida do que o
    registo de rotas, porque cada `route_id` é validado contra o enum e nenhum
    se repete. O teto existe e é derivado, em vez de ser um número escrito à
    mão que alguém esquece de subir.
    """

    def validate(self, attrs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        vistos = Counter(str(item["route_id"]) for item in attrs)
        repetidos = sorted(rota for rota, quantas in vistos.items() if quantas > 1)
        if repetidos:
            raise serializers.ValidationError(
                _(
                    "Repeated routes in the menu: {rotas}. The PUT is a full "
                    "replacement and each route appears at most once."
                ).format(rotas=", ".join(repetidos))
            )
        return attrs


class ItemDeMenuInSerializer(serializers.Serializer):
    """Uma linha do corpo do `PUT /menu`: o que o tenant decidiu sobre uma rota.

    Os quatro campos configuráveis, e nada mais. **Não** há `campo`, e isso é
    estrutural e não uma omissão: se a forma que a configuração transporta
    tivesse esse campo, uma empresa conseguia promover uma rota de escritório
    para o telemóvel escrevendo `campo: true` — e o predicado que diz "este ecrã
    foi desenhado para 360px" é código (ADR 0009, adenda 2). Também não há
    `caminho` nem `icone`: a árvore de rotas é código, e um menu que nomeasse
    caminhos punha o deep link a depender da configuração.

    O `route_id` é um `ChoiceField` sobre o enum fechado do backend, e é essa
    linha que impede a tabela de ser um armazém chave/valor: um id inventado é
    400 por campo, não uma linha guardada que ninguém sabe ler.

    `rotulo` é opcional e pode vir `null`; os outros três são obrigatórios,
    porque o corpo é a configuração **inteira** e não um `PATCH` — "mantém o que
    estava" não é uma intenção que este endpoint consiga ter.

    `allow_blank=False` no `rotulo`: um rótulo vazio não é um rótulo. Quem quer
    o default manda `null` ou omite-o, e a coluna guarda `""` para essa ausência
    (ver o modelo) — um sítio só a traduzir as duas formas.
    """

    route_id = serializers.ChoiceField(choices=RotaDeMenu.choices)
    grupo = serializers.CharField(max_length=LIMITE_DO_GRUPO)
    ordem = serializers.IntegerField(min_value=0, max_value=ORDEM_MAXIMA)
    visivel = serializers.BooleanField()
    rotulo = serializers.CharField(
        max_length=LIMITE_DO_ROTULO,
        required=False,
        allow_null=True,
    )

    class Meta:
        list_serializer_class = MenuInListSerializer


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
    #: A paleta preferida (ADR 0016). `ChoiceField` e não `CharField` para o
    #: OpenAPI o emitir como **enum fechado**: a união chega ao `types.ts`
    #: commitado e o `Record<Tema, …>` do cliente passa a ser exaustivo contra a
    #: lista do backend, nos dois sentidos, sob `pnpm typecheck`. É a mesma
    #: mecânica do `route_id` e do papel.
    tema = serializers.ChoiceField(choices=Tema.choices)


class TenantOutSerializer(serializers.Serializer):
    """Um estabelecimento como o seletor o mostra: id, nome e o papel de quem vê.

    Serve as duas posições da resposta — o `tenant_ativo` e cada entrada de
    `tenants` — porque são a mesma coisa em dois estados, e duas classes
    idênticas davam dois componentes iguais no OpenAPI.

    O `papel` é o do par (utilizador, estabelecimento) e vem do `Membership`
    confirmado pela política: a mesma pessoa é dona de um e colaboradora noutro.
    Sai como enum fechado no OpenAPI, logo a união chega ao `types.ts`.

    `demonstracao` entrou com a ADR 0018 e é a **única** diferença visível de um
    estabelecimento de demonstração. Viaja aqui — e não num endpoint próprio —
    porque é exactamente o que o cromado precisa e porque chega de graça: esta
    forma já está no `tenant_ativo` e em cada entrada de `tenants`, que são os
    dois sítios onde a faixa e o item marcado o vão ler, sem um pedido novo.

    O nome é **duplo de propósito**: a coluna chama-se `is_demo` porque segue a
    convenção de booleano da sua tabela (`is_active`, `is_staff`) e o campo
    chama-se `demonstracao` porque segue o vocabulário português dos endpoints
    deste módulo (`papel`, `rotulo`, `visivel`). É o `source` que os casa, num
    sítio só.
    """

    id = serializers.UUIDField()
    nome = serializers.CharField(source="name", max_length=200)
    papel = serializers.ChoiceField(source="role", choices=Papel.choices)
    demonstracao = serializers.BooleanField()


class ItemDeMenuOutSerializer(serializers.Serializer):
    """Um item do menu **já resolvido**: o registo com a configuração por cima.

    A tupla da ADR 0009 — `(route_id, grupo, ordem, visivel, rotulo)` —, uma
    lista com um nível de agrupamento e nunca uma árvore ("esconder e reordenar
    uma árvore é um problema muito maior e 'cresce' não precisa dele").

    Serve as **duas** posições onde o menu aparece: o `menu` do `SessaoOut`
    (filtrado pelo papel de quem pede) e a resposta do `PUT /menu` (a
    configuração inteira, como ficou). Uma classe e não duas porque a forma é a
    mesma e duas idênticas davam dois componentes iguais no OpenAPI, logo dois
    esquemas de Zod a divergir. A diferença entre as duas posições é **o
    conjunto de linhas**, não a forma de cada uma, e está escrita no
    `selectors.projeccao_de_menu`.

    `visivel` vem com o seu valor e não filtrado: esconder é apresentação e a
    rota continua a funcionar por deep link (ADR 0009) — quem esconde é o
    cliente, e o painel precisa de ver o que está escondido para o poder mostrar
    outra vez. Filtrar aqui transformava "esconder" num controlo de acesso
    falso e um marcador guardado num 404.

    `rotulo` é `null` quando o tenant não sobrepôs nada, e **não** o rótulo do
    registo já resolvido: o cliente faz `rotulo ?? registo.rotulo`, que é o que
    o `montarMenu` do shell já escreve. O porquê está no `menu.ItemDeMenu` — em
    resumo, resolvê-lo aqui prendia o tenant a um default que ele nunca escolheu.

    **Não** leva `campo`: o que esta lista transporta é configuração, e o
    predicado de rota de campo é código (ADR 0009, adenda 2). Quem o quer pede
    `GET /menu/rotas`, que é o registo.
    """

    route_id = serializers.ChoiceField(choices=RotaDeMenu.choices)
    grupo = serializers.CharField(max_length=LIMITE_DO_GRUPO)
    ordem = serializers.IntegerField()
    visivel = serializers.BooleanField()
    rotulo = serializers.CharField(max_length=LIMITE_DO_ROTULO, allow_null=True)


class RotaDeMenuOutSerializer(serializers.Serializer):
    """Uma rota do **registo**: o que existe para configurar, e os seus defaults.

    É a resposta do `GET /menu/rotas`, e o que ela descreve é código e não dados
    de um tenant: a lista fechada de rotas que o menu pode nomear, com o rótulo
    e o grupo por omissão, quem as pode ver, e se foram desenhadas para 360px.
    Nenhuma linha de base de dados é lida para a produzir.

    Serve um ecrã só — o painel de configuração do menu — e é por isso que
    carrega o `rotulo_default` e o `grupo_default`: são o que permite mostrar "o
    default é este" ao lado de um valor que o estabelecimento sobrepôs, e o que
    dá sentido ao botão que repõe (um `PUT` sem aquele item).

    ## `papeis_permitidos`, e não `papel_minimo`

    A ADR 0011 escreve "o papel mínimo que o registo declara". **Um mínimo exige
    uma ordem entre papéis, e essa ordem não existe neste projeto** — é a Q7,
    marcada como "não inventes default sem falar com um utilizador real" — pelo
    que o registo declara um conjunto. Dá o mesmo poder de filtragem sem afirmar
    que `manager` > `staff`; ver o `apps/accounts/menu.py` para a decisão inteira
    e para o que ficou sem resposta.

    Sai como lista de enum fechado (`PapelEnum`), logo o cliente não consegue
    inventar um papel ao mostrar o filtro. A ordem é a da declaração do `Papel`,
    para o diff do `schema.yml` não depender da iteração de um `frozenset`.

    ## `ordem_default` não está aqui

    Não é esquecimento: a ordem por omissão chega ao cliente **já aplicada** na
    projecção (o `menu` do `SessaoOut` e a resposta do `PUT`), que é o único
    sítio onde serve. Um segundo número a dizer a mesma coisa noutra forma era
    uma segunda fonte para a ordenação do menu.
    """

    route_id = serializers.ChoiceField(choices=RotaDeMenu.choices)
    rotulo_default = serializers.CharField(max_length=LIMITE_DO_ROTULO)
    grupo_default = serializers.CharField(max_length=LIMITE_DO_GRUPO)
    papeis_permitidos = serializers.ListField(
        child=serializers.ChoiceField(choices=Papel.choices)
    )
    campo = serializers.BooleanField()


class EstabelecimentoOutSerializer(serializers.Serializer):
    """A resposta do `GET` e do `PATCH /estabelecimento` (ADR 0017).

    **Não é o `TenantOutSerializer`**, e a diferença é a razão de existirem os
    dois: aquele descreve o estabelecimento como o **seletor** o mostra — id,
    nome e o papel de quem está a ver — e viaja em cada resposta de sessão. Este
    descreve a **entidade**: o que ela é e como está configurada, sem papel
    nenhum, porque a configuração não muda com quem olha. Juntá-los punha o
    regime de IVA em cada `GET /auth/sessao` de cada colaborador.

    `business_day_starts_at` sai como `"04:00"` e não `"04:00:00"`: o `format`
    está explícito porque o default do DRF é `"%H:%M:%S"`, e o que o contrato da
    ADR 0017 fixa — e o que um `<input type="time">` consome — são horas e
    minutos. Os segundos seriam três caracteres que nunca são outra coisa que
    `00`.
    """

    id = serializers.UUIDField()
    nome = serializers.CharField()
    vat_regime = serializers.ChoiceField(choices=RegimeDeIva.choices)
    business_day_starts_at = serializers.TimeField(format="%H:%M")
    demonstracao = serializers.BooleanField()


class EstabelecimentoInSerializer(serializers.Serializer):
    """O corpo do `PATCH /estabelecimento`: os três campos configuráveis.

    **Não há `demonstracao` e não há `id`.** O primeiro é só de leitura (a razão
    está no modelo: marcar um estabelecimento real como demonstração era esconder
    dados reais atrás de um aviso de "isto é de brincar"); o segundo não existe
    porque qual é o estabelecimento decide-se no âmbito e não no corpo — é a
    mesma forma com que o `PreferenciasInSerializer` não tem `user_id`. Não é uma
    verificação que a view faz: é um argumento que não existe.

    ## `PATCH` com os três campos obrigatórios, e é coerente e não contraditório

    Hoje o corpo tem de os trazer todos, logo isto comporta-se como um `PUT`. O
    método é `PATCH` pelo que acontece **depois**: um quarto campo entra como
    `required=False` e nenhum cliente antigo tem de ser alterado, enquanto com
    `PUT` a semântica obrigava-o a reenviar tudo e um cliente que não conhecesse
    o campo novo apagava-o. É a mesma escolha do `/auth/preferencias`, e é
    compatível com o `COMPONENT_SPLIT_PATCH = False` das settings — nenhuma view
    desta casa valida com `partial=True`, pelo que o `types.ts` gerado diz que os
    três são obrigatórios, que é a verdade.

    ## A janela do dia de negócio é validada aqui **e** na base de dados

    O `TimeField` recusa `"25:00"` por forma, e o `validate_business_day_starts_at`
    recusa `"16:00"` por domínio — com a frase que aparece debaixo do campo. A
    `CheckConstraint` da migração 0009 é a **rede**: um dia de negócio às 16:00
    parte todos os dias em dois em silêncio, e a linha não deve conseguir existir
    venha de onde vier. É a mesma relação que o menu tem com a sua unicidade.
    """

    nome = serializers.CharField(max_length=200)
    vat_regime = serializers.ChoiceField(choices=RegimeDeIva.choices)
    business_day_starts_at = serializers.TimeField(
        # As duas formas que o contrato aceita à entrada, e **só** estas: a de
        # saída (`"04:00"`), que é a que o cliente devolve sem pensar, e a
        # completa, porque é o que um `curl` escrito à mão costuma mandar.
        input_formats=["%H:%M", "%H:%M:%S"],
    )

    def validate_business_day_starts_at(self, valor: time) -> time:
        if not DIA_DE_NEGOCIO_MINIMO <= valor <= DIA_DE_NEGOCIO_MAXIMO:
            raise serializers.ValidationError(
                _(
                    "The business day starts between {minimo} and {maximo}. This "
                    "hour separates one day from the next in the totals: outside "
                    "this window, an evening service would be split across two days."
                ).format(
                    minimo=f"{DIA_DE_NEGOCIO_MINIMO:%H:%M}",
                    maximo=f"{DIA_DE_NEGOCIO_MAXIMO:%H:%M}",
                )
            )
        return valor


class SessaoOutSerializer(serializers.Serializer):
    """A resposta dos cinco endpoints de autenticação. Sempre esta forma.

    Uma forma só para login, logout, leitura da sessão, troca de estabelecimento
    e preferências: o cliente guarda-a numa entrada de cache e qualquer das
    cinco respostas a substitui, em vez de cinco formas e cinco ramos de Zod.

    `utilizador` e `tenant_ativo` são `null` em vez de ausentes, e isso é
    deliberado: um campo que às vezes não existe obriga o cliente a distinguir
    "não sei" de "não há", e aqui o servidor sabe sempre.
    """

    estado = serializers.ChoiceField(choices=EstadoDaSessao.choices)
    utilizador = UtilizadorOutSerializer(allow_null=True)
    tenant_ativo = TenantOutSerializer(allow_null=True)
    tenants = TenantOutSerializer(many=True)
    # A projecção do menu do estabelecimento ativo, filtrada pelo papel de quem
    # pede (ADR 0009 e ADR 0011). Até esta feature existir, o campo era uma
    # `ListField(JSONField())` sempre vazia e **sem** forma de item declarada,
    # porque declarar a tupla desta ADR quando ela não existia era inventar o
    # contrato de outra (ADR 0010). Agora existe: o item é o `ItemDeMenuOut` e o
    # `route_id` dele é o enum fechado que torna o `Record<RotaId, …>` do shell
    # exaustivo contra a lista do backend, nos dois sentidos.
    menu = ItemDeMenuOutSerializer(many=True)


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
