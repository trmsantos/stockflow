"""Queries de leitura do `accounts`. Quatro, e cada uma corre dentro de um âmbito.

A primeira é a do caminho crítico: o `TenantMiddleware` corre o
`membership_no_ambito` **uma vez por pedido**, como primeira e única instrução
dentro do âmbito antes de entregar o pedido (ADR 0007). Vive aqui e não no
middleware porque o caminho do login e o da troca de tenant fazem exatamente a
mesma pergunta, e duas escritas da mesma query são duas oportunidades de uma
delas se esquecer do `is_active`.

As duas seguintes são dos convites (ADR 0010), e a diferença entre elas vale ser
dita: a da listagem corre no âmbito que a **sessão** escolheu, e a da activação
corre no âmbito que o **link** escolheu. A política é a mesma nos dois casos, e é
ela que concede — nenhuma destas funções filtra por tenant em Python.

A quarta é a projecção do menu (ADR 0009 e ADR 0011), e é a única que faz mais
do que uma query: junta a configuração do tenant ao registo de rotas que vive em
código, e filtra pelo papel de quem pede. Está aqui e não em `services.py`
porque não escreve nada — e é usada pelos dois lados, pelo `menu` do `SessaoOut`
e pela resposta do `PUT /menu`.
"""

from __future__ import annotations

from uuid import UUID

from django.db.models import QuerySet

from apps.accounts.menu import ItemDeMenu, rota_do_registo
from apps.accounts.models import (
    Invitation,
    Membership,
    RotaDeMenu,
    TenantMenuItem,
)

__all__ = [
    "convite_por_token_hash",
    "convites_do_ambito",
    "itens_de_menu_do_ambito",
    "membership_no_ambito",
    "projeccao_de_menu",
]


def membership_no_ambito(*, user_id: UUID, tenant_id: UUID) -> Membership | None:
    """A pertença ativa de (utilizador, âmbito), ou `None` se a política não a der.

    ## Porque é que `None` não distingue "não existe" de "não é meu"

    Não pode distinguir, e é essa a propriedade que fecha o caminho de leitura
    entre tenants. A query leva `user_id = <o do pedido>` no `WHERE` e corre
    dentro de `tenant_scope(tenant_id)`, onde as políticas do
    `accounts_membership` e do `accounts_tenant` filtram por `app.tenant_id`.
    Um `tenant_id` forjado na sessão escolhe um âmbito onde esta query não
    devolve nada — e **nenhuma linha do tenant alheio é lida** no caminho, nem
    para ser descartada depois em Python.

    ## `select_related("tenant")` não é só performance

    É o que traz o `name` do tenant para o `TenantContext` sem uma segunda
    query, mas é também uma segunda verificação de graça: o FK não é nulável,
    logo o Django emite um `INNER JOIN` e a linha só aparece se as **duas**
    políticas casarem. Um `Membership` que aponte para um tenant que o âmbito
    não mostra desaparece, em vez de produzir um contexto com o nome a `None`.

    ## `get()` e não `first()`

    `first()` numa queryset sem `order_by` acrescenta `ORDER BY id`, que troca
    a leitura direta pelo índice único `(user_id, tenant_id)` por uma ordenação
    de um resultado de uma linha. `get()` não ordena.
    """
    try:
        return Membership.objects.select_related("tenant").get(
            user_id=user_id,
            tenant_id=tenant_id,
            is_active=True,
        )
    except Membership.DoesNotExist:
        return None


def convite_por_token_hash(token_hash: str) -> Invitation | None:
    """O convite deste token **dentro do âmbito aberto**, ou `None`.

    É a leitura que a ADR 0010 põe no centro: corre dentro do
    `tenant_scope(uuid que vem do link)`, onde a política do
    `accounts_invitation` filtra por `app.tenant_id`. Um uuid forjado escolhe um
    âmbito onde este `token_hash` não existe — zero linhas, sem erro, e nenhuma
    linha de outro estabelecimento é lida no caminho, nem para ser descartada
    depois em Python.

    ## Sem `select_related("tenant")`, e é a parte que não é performance

    O `membership_no_ambito` abaixo usa-o, e aqui a ausência é deliberada. A
    ordem das leituras é parte da decisão: casa-se o convite **primeiro** e o
    nome do estabelecimento só se lê depois de a pertença existir, pelo caminho
    normal da sessão. Trazer o `Tenant` no mesmo `JOIN` punha o nome à mão de
    quem escrevesse a mensagem de erro seguinte — e "foste convidado para a
    Pastelaria Aurora" sobre um uuid adivinhado é um oráculo de enumeração de
    clientes.

    ## `filter().first()` e não `get()`

    Ao contrário do `membership_no_ambito`, aqui a ausência de linha é o caminho
    **esperado** e não a excepção: qualquer link velho, revogado ou forjado passa
    por ela. Um `try/except DoesNotExist` em volta do caminho normal lê pior, e o
    `first()` ordena por uma chave única de uma linha — o `ORDER BY` que ele
    acrescenta é sobre um resultado de uma linha encontrado pelo índice
    `invitation_token_hash_uniq`.
    """
    return Invitation.objects.filter(token_hash=token_hash).first()


def convites_do_ambito(*, tenant_id: UUID) -> QuerySet[Invitation]:
    """Os convites deste estabelecimento, mais recentes primeiro.

    O filtro por `tenant_id` é o segundo controlo e não o primeiro: quem isola é
    a política, e isto é o `get_queryset` filtrado que o CLAUDE.md e o
    `SECURITY.md` §1 exigem **ao lado** dela. Com os dois, uma política desligada
    por acidente não é travessia de tenant, e um filtro esquecido também não.

    A ordem é a do índice `(tenant_id, -created_at)` que o `TenantModel` dá a
    todas as tabelas de tenant, pelo que a listagem paginada não ordena nada em
    memória.

    Sem `select_related`: nada do que o `ConviteOutSerializer` emite atravessa
    uma relação. O `invited_by` existe na tabela e **não** está no contrato
    (ver o modelo), e é essa ausência que faz com que uma lista de 50 convites
    seja uma query e não 51.
    """
    return Invitation.objects.filter(tenant_id=tenant_id).order_by("-created_at")


def itens_de_menu_do_ambito(*, tenant_id: UUID) -> QuerySet[TenantMenuItem]:
    """As linhas de configuração do menu deste tenant. **Pode não haver nenhuma.**

    Zero linhas é o estado normal de um tenant que nunca abriu o painel: os
    defaults vivem em código e a linha nasce na primeira escrita (ADR 0011).
    Quem precisa do menu não chama isto, chama o `projeccao_de_menu` abaixo —
    esta função existe separada porque a substituição total do `PUT` precisa da
    queryset para a apagar, e é a mesma pergunta ("as linhas deste tenant").

    O filtro por `tenant_id` é o segundo controlo e não o primeiro: quem isola é
    a política. Com os dois, uma política desligada por acidente não é travessia
    de tenant, e um filtro esquecido também não (`SECURITY.md` §1).

    Sem `order_by`: quem ordena é a projecção, pela `ordem` já resolvida, e
    ordenar aqui era ordenar duas vezes um resultado que tem, no máximo, tantas
    linhas quantas o registo de rotas tem ids.
    """
    return TenantMenuItem.objects.filter(tenant_id=tenant_id)


def projeccao_de_menu(*, tenant_id: UUID, papel: str | None = None) -> tuple[ItemDeMenu, ...]:
    """O menu **efectivo** deste tenant: registo, configuração por cima, e filtro.

    É a projecção da ADR 0009 — uma lista com um nível de agrupamento, nunca uma
    árvore — e a sua forma é a tupla `(route_id, grupo, ordem, visivel, rotulo)`.

    ## Três coisas acontecem aqui, e nenhuma é cosmética

    **1. Os defaults vêm do registo, não da tabela.** Um tenant sem linhas
    nenhumas recebe o menu completo, pela ordem do registo (ADR 0011: "os
    defaults vivem em código e a linha nasce na primeira escrita"). Uma rota
    ausente da tabela e uma rota ausente do corpo de um `PUT` significam a mesma
    coisa, e é essa equivalência que faz "repor o default" ser um `PUT` sem o
    item em vez de uma coluna a mais.

    **2. Uma linha com um `route_id` que o registo não conhece é ignorada.** É
    inalcançável por construção — o `ChoiceField` do serializer valida contra o
    mesmo enum — e deixa de o ser no intervalo de um rolling deploy, onde uma
    linha escrita pela versão nova é lida pela antiga. Ignorá-la é o
    comportamento certo aí: uma entrada a mais não é razão para o menu não
    montar. É a mesma escolha que o `montarMenu` do shell faz.

    **3. O filtro por papel é autorização e não preferência.** ADR 0011, com
    estas palavras: "a configuração é por tenant, a resposta é por
    (tenant, papel), porque esconder um item que um `staff` não pode usar é
    autorização e não preferência". O que o registo declara é um **conjunto** de
    papéis permitidos e não um mínimo — não há ordem entre papéis neste projeto,
    e inventá-la era responder à Q7 (ver `apps/accounts/menu.py`).

    `papel=None` **não** é "todos os papéis" por acaso: é o caso do `PUT`, cuja
    resposta tem de ser a configuração inteira. Um `PUT` de substituição total
    que devolvesse uma lista filtrada era um footgun de perda de dados — quem
    lesse a resposta e a voltasse a enviar apagava a configuração dos itens que
    o seu papel não vê. O filtro aplica-se onde o menu é **consumido**, que é o
    `menu` do `SessaoOut`.

    ## `visivel = False` não é filtrado aqui

    Sai na projecção com o seu valor, e quem o esconde é o cliente. Duas razões:
    esconder é apresentação e a rota continua a funcionar por deep link
    (ADR 0009), e o painel de configuração precisa de ver o que está escondido
    para o poder mostrar outra vez. Filtrar no servidor transformava "esconder"
    num controlo de acesso falso — exactamente o que a ADR 0009 recusa.

    ## Uma query, e a ordenação é em Python

    A `ordem` efectiva não existe na base de dados para as rotas sem linha, logo
    ordenar em SQL obrigava a um `COALESCE` sobre um `VALUES` com os defaults —
    SQL construído a partir de um registo de código, que é o oposto do que se
    quer. O conjunto tem, no máximo, tantos elementos quantos o registo tem ids.
    O desempate é o `route_id`: duas rotas com a mesma `ordem` não podem trocar
    de lugar entre pedidos.
    """
    configuracao = {linha.route_id: linha for linha in itens_de_menu_do_ambito(tenant_id=tenant_id)}

    itens = []
    for route_id in RotaDeMenu.values:
        registo = rota_do_registo(route_id)
        if registo is None or (papel is not None and papel not in registo.papeis):
            continue
        linha = configuracao.get(route_id)
        itens.append(
            ItemDeMenu(
                route_id=route_id,
                # `""` na coluna é "sem sobreposição", e o contrato diz isso
                # com `null` — a tradução é aqui e num sítio só (ver o modelo).
                # **Vale para o `grupo` e para o `rotulo`**: os dois são copy do
                # produto, e copy não viaja no arame (ADR 0019, decisão 5).
                grupo=(linha.grupo or None) if linha is not None else None,
                ordem=linha.ordem if linha is not None else registo.ordem_default,
                visivel=linha.visivel if linha is not None else True,
                rotulo=(linha.rotulo or None) if linha is not None else None,
            )
        )
    return tuple(sorted(itens, key=lambda item: (item.ordem, item.route_id)))
