"""As únicas escritas do `accounts` (CLAUDE.md: nenhuma escrita fora de services).

Quatro famílias de funções, e vale a pena separá-las na cabeça antes de ler o
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

**A família dos convites** — `criar_convite`, `reenviar_convite`,
`revogar_convite`, `ativar_convite` (ADR 0010). As três primeiras correm
**dentro** do âmbito do pedido, como as pertenças, porque os endpoints de gestão
de convites são endpoints normais, com âmbito e só para o `owner`. A quarta é a
excepção que dá nome à decisão: corre **antes** de existir sessão, e o âmbito
que ela abre vem do **link** e não da sessão — o link escolhe o âmbito, a
política concede-o.

**A família do menu** — uma função só, `guardar_menu` (ADR 0009 e ADR 0011).
Corre **dentro** do âmbito do pedido, como as pertenças, e é a única escrita do
módulo que é de *configuração* e não de identidade. A fronteira transacional é a
mais simples das quatro e ainda assim é a razão de a função existir: a
substituição é **total** porque reordenar um menu é uma intenção só, e N
escritas parciais deixam um menu meio ordenado se uma delas falhar.

Nenhuma destas funções emite um evento de domínio, e a ADR 0010 fecha a questão
em vez de a deixar em aberto: **zero eventos e zero tarefas no v1**, porque não
existe consumidor da outbox e um evento sem subscritor é um contrato público
escrito ao contrário. É também a razão pela qual **não há email a enviar**: o
token sai uma vez, na resposta do POST que o criou, e quem convida entrega o
link pelo meio que quiser. O que ainda não tem endpoint — a reposição de
password — é a tarefa seguinte da mesma ADR, e é ela que traz a única tabela
deste módulo sem política de RLS.

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

## E porque é que a aceitação de um convite leva uma, e é o caso contrário

O `ativar_convite` é a mesma mecânica usada ao contrário, e vale dizer as duas
ao lado uma da outra para ninguém "corrigir" uma pela outra. A descoberta de
estabelecimentos **não pode** ter uma transação por fora porque visita N
âmbitos; a aceitação de um convite visita **um** — o que o link nomeia — e
escreve três coisas lá dentro (a password, o `Membership` e o `accepted_at`).
Essas três vão **numa** transação dentro do âmbito, como a ADR 0010 diz
explicitamente: ou a conta fica com password, pertença e convite queimado, ou
fica como estava. Escrever no `accounts_user` de dentro de um âmbito é já o
normal e está justificado no `_espelhar` daqui.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.password_validation import validate_password
from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ValidationError
from django.db import IntegrityError, models, transaction
from django.db.models import F, Func, Value
from django.db.models.functions import Lower
from django.http import HttpRequest
from django.utils import timezone

from apps.accounts.api import (
    TenantOption,
    UserOut,
    normalizar_email,
    tenant_context,
    utilizador_atual,
)
from apps.accounts.menu import ItemDeMenu
from apps.accounts.middleware import CODIGO_DESCONHECIDO, SESSION_TENANT_KEY
from apps.accounts.models import (
    EstadoDoConvite,
    Invitation,
    Membership,
    Papel,
    Tenant,
    TenantMenuItem,
    User,
)
from apps.accounts.selectors import (
    convite_por_token_hash,
    itens_de_menu_do_ambito,
    membership_no_ambito,
    projeccao_de_menu,
)
from apps.shared.db import TenantScopeConflict, current_tenant, tenant_scope

__all__ = [
    "BACKEND_DE_SESSAO",
    "CODIGOS_DE_RECUSA",
    "CODIGOS_DE_RECUSA_DE_CONVITE",
    "CODIGO_CONVITE_DE_OUTRA_CONTA",
    "CODIGO_CONVITE_EXIGE_SESSAO",
    "CODIGO_CONVITE_INVALIDO",
    "CODIGO_CONVITE_NAO_PENDENTE",
    "CODIGO_CREDENCIAIS_INVALIDAS",
    "LIMITE_DO_FRAGMENTO",
    "VALIDADE_DO_CONVITE",
    "ConviteCriado",
    "EstadoDaSessao",
    "PrimeiroDono",
    "Recusa",
    "RecusaDeConvite",
    "RecusaDeSessao",
    "SessaoOut",
    "ativar_convite",
    "conceder_pertenca",
    "criar_convite",
    "criar_tenant",
    "criar_tenant_com_dono",
    "escolher_tenant_ativo",
    "guardar_menu",
    "iniciar_sessao",
    "reenviar_convite",
    "revogar_convite",
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

# ---------------------------------------------------------------------------
# Os convites (ADR 0010). Quatro códigos estáveis, e o primeiro é o mais
# importante dos quatro: é **um** código e **um** corpo para cinco situações
# diferentes.
# ---------------------------------------------------------------------------

#: Convite que não serve, por qualquer razão (400). Expirado, já usado,
#: revogado, inexistente e **uuid de tenant forjado** dão todos este código e o
#: mesmo `detail`: distinguir dizia a quem tem um link se aquele
#: estabelecimento existe, se aquele convite já foi aceite, ou se o link é
#: velho. O que mantém a propriedade verdadeira não é a disciplina de escrever o
#: mesmo literal cinco vezes — é o `_convite_invalido()`, que constrói a única
#: recusa que estes cinco caminhos levantam.
CODIGO_CONVITE_INVALIDO = "convite_invalido"

DETALHE_CONVITE_INVALIDO = "Este convite não é válido. Peça um convite novo."

#: O email convidado já tem uma conta com password utilizável (409). A
#: activação **não** define password numa conta que já tem uma — a password é
#: global e a pertença é por tenant, pelo que "convite + definir password" dava
#: a quem pode convidar a tomada de uma conta existente, com os outros
#: estabelecimentos dela lá dentro (ADR 0010). O cliente manda entrar primeiro.
CODIGO_CONVITE_EXIGE_SESSAO = "convite_exige_sessao"

DETALHE_CONVITE_EXIGE_SESSAO = (
    "Esta conta já existe. Inicie sessão e abra o link outra vez para aceitar."
)

#: A sessão é de outra conta (403). Nunca uma concessão à conta errada: a
#: pertença que este convite cria é para o email do convite e para mais nenhum.
CODIGO_CONVITE_DE_OUTRA_CONTA = "convite_de_outra_conta"

DETALHE_CONVITE_DE_OUTRA_CONTA = (
    "Este convite é para outra conta. Termine a sessão e entre com a conta convidada."
)

#: Reenviar ou revogar um convite que já não está em estado de o permitir (409).
#: É o único código desta família que **não** aparece na activação: vive nos
#: endpoints de gestão, onde quem chama vê a lista e portanto vê o estado.
CODIGO_CONVITE_NAO_PENDENTE = "convite_nao_pendente"

#: Os códigos que uma `RecusaDeConvite` pode transportar, em lista fechada, com
#: o mesmo gate que a família da sessão: o `views.py` dá-lhes status e um teste
#: afirma que os dois conjuntos são iguais nos dois sentidos.
CODIGOS_DE_RECUSA_DE_CONVITE: frozenset[str] = frozenset(
    {
        CODIGO_CONVITE_INVALIDO,
        CODIGO_CONVITE_EXIGE_SESSAO,
        CODIGO_CONVITE_DE_OUTRA_CONTA,
        CODIGO_CONVITE_NAO_PENDENTE,
    }
)

#: Quanto tempo vale um convite. Sete dias é o que a ADR 0010 fixa, e é um dos
#: três controlos que limitam um link roubado — os outros dois são o uso único e
#: a revogação. Não há um quarto, e o risco residual está nomeado: **um email de
#: convite roubado é uma pertença**.
VALIDADE_DO_CONVITE = timedelta(days=7)

#: Bytes de `secrets` no token. 32 = 256 bits, que é também a razão pela qual o
#: hash é SHA-256 e não Argon2id: um segredo com 256 bits de entropia não é
#: adivinhável por dicionário, logo o fator de trabalho de um KDF não compra
#: nada e paga-se em cada activação.
BYTES_DO_TOKEN = 32

#: O que separa o uuid do tenant do token dentro do fragmento. Um ponto porque
#: não ocorre em nenhuma das duas metades: um UUID canónico não o tem, e o
#: alfabeto do `token_urlsafe` é base64url (letras, dígitos, `-` e `_`).
SEPARADOR_DO_FRAGMENTO = "."

#: Comprimento **exato** do fragmento: 36 (UUID canónico) + 1 (separador) + 43
#: (`token_urlsafe(32)`, que são 32 bytes em base64url sem padding). Serve de
#: `max_length` no serializer da activação, e não é um teto arredondado de
#: propósito — há um teste que afirma que um fragmento real tem este
#: comprimento, logo mexer no `BYTES_DO_TOKEN` sem mexer aqui fica vermelho em
#: vez de truncar segredos em silêncio.
LIMITE_DO_FRAGMENTO = 80

#: O backend com que a activação abre a sessão de uma conta nova. Vai explícito
#: porque **tem** de ir: com dois `AUTHENTICATION_BACKENDS`, o `login()` do
#: Django levanta `ValueError` se ninguém disser qual foi — e o primeiro da
#: lista é o `AxesStandaloneBackend`, cujo `get_user` herdado devolve `None`, o
#: que deixaria a sessão escrita e o pedido seguinte anónimo. É o mesmo valor
#: que os testes passam ao `force_login`, e há um teste que afirma que ele
#: continua a estar nos `AUTHENTICATION_BACKENDS`.
BACKEND_DE_SESSAO = "django.contrib.auth.backends.ModelBackend"


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
    _exigir_ambito(tenant_id, tabela="accounts_membership")
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
    _exigir_ambito(tenant_id, tabela="accounts_membership")

    with transaction.atomic():
        revogadas = Membership.objects.filter(
            user=user,
            tenant_id=tenant_id,
            is_active=True,
        ).update(is_active=False, updated_at=timezone.now())
        _espelhar(user, tenant_id, pertence=False)
    return revogadas > 0


def _exigir_ambito(tenant_id: UUID, *, tabela: str) -> None:
    """O âmbito aberto tem de ser o deste tenant, senão a política recusaria.

    Não é uma verificação defensiva a mais: sem âmbito, o `INSERT` levaria
    `new row violates row-level security policy` e o `UPDATE` ou o `DELETE`
    afetariam zero linhas **sem erro** — que é a forma silenciosa do mesmo bug.

    O nome da tabela é **obrigatório** e não tem default, porque quem lê a
    mensagem está a depurar uma escrita concreta: esta guarda nasceu nas
    pertenças e protege hoje três tabelas, e um default nomearia a errada em
    duas delas. Explícito, o pior caso é não compilar na cabeça de quem lê.
    """
    ativo = current_tenant()
    if ativo != tenant_id:
        raise TenantScopeConflict(
            f"escrita em {tabela} para {tenant_id} com o âmbito em "
            f"{ativo}: a política filtra por app.tenant_id e a escrita afetaria "
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
    #: A projecção do menu do **estabelecimento ativo**, já filtrada pelo papel
    #: de quem pede (ADR 0009 e ADR 0011). Viaja aqui e não num endpoint próprio
    #: porque "resolve-se com exactamente o que a sessão já resolveu — o tenant
    #: activo —, pelo que não custa um round trip no caminho crítico do primeiro
    #: paint da sidebar" (ADR 0011).
    #:
    #: Vazio quando não há estabelecimento ativo, e isso não é um caso
    #: degenerado: sem tenant não há configuração por tenant, e os estados
    #: `anonimo`, `sem_estabelecimento` e `escolha_pendente` são precisamente os
    #: três em que o cliente não mostra sidebar nenhuma. O tipo deixou de ser
    #: `object` — a forma do item é agora contrato (`ItemDeMenuOut`), que é o
    #: que a ADR 0010 deixou em dívida à espera desta ADR.
    menu: tuple[ItemDeMenu, ...] = ()


class Recusa(Exception):
    """Recusa com um `code` estável no corpo, que é o que o cliente ramifica.

    O status HTTP não basta e isso já está escrito no `TenantMiddleware`: o
    `SessionAuthentication` do DRF também responde 403 a anónimos. Quem traduz
    este código em status é o `views.py` — o mapa vive lá porque é transporte,
    e um service que soubesse status HTTP era um service a saber HTTP.

    Não se levanta esta classe: levantam-se as duas subclasses abaixo. São duas
    e não uma porque o conjunto de códigos é **por família de endpoints**, cada
    uma com a sua lista fechada e o seu mapa de status fechado contra ela por um
    teste — um `except` que apanhasse as duas misturava os dois contratos e o
    primeiro código em falta no mapa aparecia como um 500.
    """

    def __init__(self, codigo: str, detalhe: str) -> None:
        super().__init__(detalhe)
        self.codigo = codigo
        self.detalhe = detalhe


class RecusaDeSessao(Recusa):
    """Recusa dos quatro endpoints da autenticação de sessão."""


class RecusaDeConvite(Recusa):
    """Recusa da activação e dos endpoints de gestão de convites."""


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

    ## O menu custa uma transação curta, e só quando há estabelecimento ativo

    A tabela do menu tem política (ADR 0011), logo a leitura corre dentro de
    `tenant_scope(ativo.id)` — como a confirmação de cada candidato, e pela
    mesma razão. É a transação **N+1** de um login com N estabelecimentos, e
    não há nenhuma quando não há tenant ativo: é o único sítio onde o custo do
    menu na sessão aparece, e a ADR 0011 aceita-o explicitamente ("não custa um
    round trip no caminho crítico do primeiro paint da sidebar").

    Esta função é chamada **sempre fora** de qualquer `tenant_scope` — o login,
    a troca de estabelecimento e a activação fecham o seu bloco antes de a
    chamar —, e o `tenant_scope` é reentrante para o mesmo tenant, pelo que
    chamá-la de dentro do âmbito do próprio `ativo` também funciona. De dentro
    do âmbito de **outro** tenant levantaria `TenantScopeConflict`, que é o que
    se quer: o menu de A não se lê no âmbito de B.

    O papel vem do `TenantOption` que a política já confirmou neste pedido, e
    não da sessão nem de um campo do `User`: é por tenant (ADR 0007).
    """
    utilizador = utilizador_atual(request)
    if ativo is not None:
        estado = EstadoDaSessao.ATIVA
    elif tenants:
        estado = EstadoDaSessao.ESCOLHA_PENDENTE
    else:
        estado = EstadoDaSessao.SEM_ESTABELECIMENTO
    menu: tuple[ItemDeMenu, ...] = ()
    if ativo is not None:
        with tenant_scope(ativo.id):
            menu = projeccao_de_menu(tenant_id=ativo.id, papel=ativo.role)
    return SessaoOut(
        estado=estado,
        utilizador=utilizador,
        tenant_ativo=ativo,
        tenants=tenants,
        menu=menu,
    )


# ---------------------------------------------------------------------------
# Os convites (ADR 0010).
#
# Três funções com âmbito (criar, reenviar, revogar) e uma que **abre** o
# âmbito a partir do link (activar). A assimetria é a decisão: convidar é uma
# operação de dentro de um estabelecimento, e activar é a única coisa neste
# módulo que precisa de escolher um âmbito sem ter sessão.
# ---------------------------------------------------------------------------
@dataclass(frozen=True, kw_only=True, slots=True)
class ConviteCriado:
    """O resultado de criar ou reenviar: a linha, e o segredo que sai uma vez.

    Duas peças e não uma porque têm tempos de vida diferentes — o `convite` é o
    que a listagem volta a mostrar sempre, e o `fragmento` só existe neste
    objeto e na resposta que o leva. Não há caminho para o recuperar depois: o
    que a tabela guarda é o SHA-256.

    Congelado, como os outros DTOs: é o resultado de uma decisão e não um
    acumulador.
    """

    convite: Invitation
    fragmento: str


def criar_convite(
    *,
    tenant_id: UUID,
    email: str,
    role: str,
    display_name: str,
    convidado_por: User,
) -> ConviteCriado:
    """Cria um convite para este estabelecimento e devolve o segredo, uma vez.

    Corre **dentro** do âmbito do pedido: criar um convite é escrever numa
    tabela com política, e o `_exigir_ambito` recusa fazê-lo com o âmbito noutro
    sítio — sem ele o `INSERT` levaria `new row violates row-level security
    policy`, que é o mesmo bug com pior mensagem.

    ## O que recusa, e porque é uma recusa por campo e não um código estável

    Duas situações, e as duas são afirmações sobre o **email que foi submetido**:
    já existe um convite não aceite para ele neste estabelecimento, ou a pessoa
    já é membro ativo daqui. Saem como erro de validação do campo `email`
    (400, `{"email": ["..."]}`), que é a forma que um formulário mostra ao lado
    do input — e não como `code` estável, que é a forma para o cliente
    **ramificar**. Nenhuma das duas mensagens diz nada sobre outro
    estabelecimento: "já é membro **deste** estabelecimento" só é verdade dentro
    do âmbito de quem pergunta, e nenhuma delas revela se o email tem conta no
    StockFlow.

    A verificação está aqui e não no serializer porque é uma leitura à base de
    dados dentro da transação do pedido, e porque a **constraint é a rede**: o
    índice parcial `invitation_pendente_uniq` apanha a corrida entre dois
    convites simultâneos, e o `IntegrityError` dela sai como a mesma recusa. Sem
    a verificação, a corrida perdida dava 500; sem a constraint, dava duas
    linhas pendentes para o mesmo email.

    ## Um convite expirado continua a ocupar o lugar

    A condição do índice é `accepted_at IS NULL AND revoked_at IS NULL` e não
    pode incluir `expires_at > now()`, porque `now()` não é imutável e o
    Postgres recusa-o num índice. A consequência é deliberada e é a mais simples
    de explicar a quem usa: **criar nunca mexe num convite que já existe.** Quem
    quer um token novo para o mesmo email usa o `reenviar_convite`, que é o único
    sítio onde um token roda — e o ecrã mostra-lhe o estado `expirado` ao lado do
    botão. A alternativa (criar a substituir em silêncio um convite pendente)
    trocava o papel e o nome de uma pessoa sem o dizer a ninguém.

    ## O papel

    `owner` é o único papel que pode convidar hoje (a view impõe-o com
    `TemPapel.exige`), e é o papel mais alto, pelo que a regra da ADR 0010
    "nenhum convite concede papel acima do de quem convida" é verdadeira por
    construção e **não tem mecanismo próprio**. Não o inventei de propósito: uma
    ordem entre papéis é a Q7 do `SESSION-CONTEXT.md`, está marcada como "não
    inventes default sem falar com um utilizador real", e um `Papel` hierárquico
    escrito aqui era a resposta dela dada por um agente.
    """
    _exigir_ambito(tenant_id, tabela="accounts_invitation")
    if role not in {p.value for p in Papel}:
        raise ValueError(f"papel desconhecido: {role!r}")

    email = normalizar_email(email)
    _exigir_email_convidavel(tenant_id=tenant_id, email=email)
    token, token_hash = _novo_token()

    try:
        with transaction.atomic():
            convite = Invitation.objects.create(
                tenant_id=tenant_id,
                email=email,
                role=role,
                display_name=display_name,
                token_hash=token_hash,
                expires_at=timezone.now() + VALIDADE_DO_CONVITE,
                invited_by_id=convidado_por.pk,
            )
    except IntegrityError as erro:
        # A única violação alcançável é o índice parcial: o `token_hash` é de 256
        # bits e o FK do tenant foi verificado pelo `_exigir_ambito`.
        raise _email_ja_convidado() from erro

    logger.info("convite criado", extra={"event": "convite_criado", "outcome": "ok"})
    return ConviteCriado(convite=convite, fragmento=_fragmento(tenant_id, token))


def reenviar_convite(*, convite: Invitation) -> ConviteCriado:
    """Roda o token e a validade do convite, e devolve o segredo novo.

    É o **único** sítio onde um token roda, e rodar invalida o anterior: o
    `token_hash` é substituído, logo um link antigo passa a não casar com nada.
    Isso é uma propriedade e não um efeito lateral — reenviar a quem perdeu o
    email não deixa dois links vivos.

    Só sobre um convite que ainda não foi aceite nem revogado (`pendente` ou
    `expirado`). Um convite revogado **não** ressuscita: revogar é final, e quem
    quer convidar outra vez cria um convite novo — o que é possível porque a
    condição do índice parcial deixa de cobrir a linha revogada.

    O `UPDATE` é condicional (`accepted_at IS NULL AND revoked_at IS NULL`) e é
    ele que decide, não a verificação em Python: o estado lido antes pode ter
    mudado entre a leitura e a escrita, e é a base de dados que resolve a
    corrida — zero linhas afetadas é a mesma recusa.
    """
    _exigir_ambito(convite.tenant_id, tabela="accounts_invitation")
    token, token_hash = _novo_token()
    agora = timezone.now()

    with transaction.atomic():
        atualizadas = (
            Invitation.objects.filter(
                pk=convite.pk,
                accepted_at__isnull=True,
                revoked_at__isnull=True,
            )
            # `updated_at` é `auto_now`, logo **não** é escrito por
            # `QuerySet.update()`: vai à mão (docstring do `TenantModel`).
            .update(
                token_hash=token_hash,
                expires_at=agora + VALIDADE_DO_CONVITE,
                updated_at=agora,
            )
        )
        if not atualizadas:
            raise _convite_nao_pendente("reenviado")

    convite.refresh_from_db(fields=["token_hash", "expires_at", "updated_at"])
    logger.info("convite reenviado", extra={"event": "convite_reenviado", "outcome": "ok"})
    return ConviteCriado(convite=convite, fragmento=_fragmento(convite.tenant_id, token))


def revogar_convite(*, convite: Invitation) -> Invitation:
    """Revoga o convite. Idempotente, e nunca sobre um convite já aceite.

    Um convite aceite não se revoga: a pertença já existe e quem a retira é o
    `revogar_pertenca`. Revogar aqui dava a impressão de ter cortado um acesso
    que continuava lá — a pior forma de falhar que uma operação de segurança
    tem.

    Revogar um convite já revogado devolve-o como está, sem escrever: é a mesma
    escolha do `conceder_pertenca`, e é o que um duplo clique num botão precisa.

    Quem decide é o `UPDATE` condicional, e o `refresh_from_db` a seguir é o que
    distingue os dois casos de "zero linhas afetadas" sem uma segunda
    verificação em Python a correr sobre dados velhos.
    """
    _exigir_ambito(convite.tenant_id, tabela="accounts_invitation")
    agora = timezone.now()

    with transaction.atomic():
        Invitation.objects.filter(
            pk=convite.pk,
            accepted_at__isnull=True,
            revoked_at__isnull=True,
        ).update(revoked_at=agora, updated_at=agora)

    convite.refresh_from_db(fields=["accepted_at", "revoked_at", "updated_at"])
    if convite.accepted_at is not None:
        raise _convite_nao_pendente("revogado")

    logger.info("convite revogado", extra={"event": "convite_revogado", "outcome": "ok"})
    return convite


def ativar_convite(request: HttpRequest, *, fragmento: str, password: str) -> SessaoOut:
    """Aceita um convite a partir do link, e é aqui que vive a decisão da ADR 0010.

    ## O link escolhe o âmbito, a política concede-o

    O fragmento é `<uuid-do-tenant>.<token>`. O uuid é **argumento e não
    credencial**: esta função abre `tenant_scope(uuid que vem do link)` e lê o
    convite **lá dentro**, onde a política do `accounts_invitation` filtra por
    `app.tenant_id`. Forjá-lo escolhe um âmbito onde nenhum `token_hash` existe —
    a leitura devolve zero linhas e a recusa é a genérica. É a inversão da ADR
    0007 na letra, com o link no lugar da sessão, e é ela que permite à tabela
    dos convites ter política normal em vez de entrar na lista das tabelas
    legíveis sem âmbito.

    ## A ordem das leituras é parte da decisão

    Casa-se o convite **primeiro**. O nome do estabelecimento não é lido nesta
    função em sítio nenhum — chega à resposta pelo `_tenants_confirmados`, que
    só corre **depois** de a pertença existir, e cada candidato é lido no seu
    âmbito. Sem esta ordem, um uuid adivinhado devolvia "foste convidado para a
    Pastelaria Aurora" sem token nenhum, que é um oráculo de enumeração de
    clientes. É também por isso que o selector do convite **não** leva
    `select_related("tenant")`: a comodidade de ter o nome à mão era a única
    forma de o fazer sair por acidente.

    ## A aceitação nunca define password numa conta que já tem uma

    A password é global e a pertença é por tenant, pelo que "convite + definir
    password" dava a quem pode convidar a **tomada de uma conta existente**, com
    os outros estabelecimentos dela lá dentro. Logo há dois caminhos, e o
    servidor é que decide qual, depois de casar o convite:

    * **a conta não existe, ou existe sem password utilizável** (é o que o
      `criar_estabelecimento` e um convite anterior deixam) — quem activa define
      a password, que passa pelos `AUTH_PASSWORD_VALIDATORS`, e a sessão abre
      aqui;
    * **a conta já tem password utilizável** — a password do corpo é ignorada e
      não há caminho por onde ela chegue ao `set_password`: a variável que a
      transporta é `None` neste ramo. A activação exige sessão
      (`convite_exige_sessao`), e uma sessão de outra conta é recusada
      (`convite_de_outra_conta`). Nunca uma concessão à conta errada.

    A assimetria entre os dois ramos é principiada e não acidental: a recusa
    existe para proteger uma **credencial que já existe**, e no primeiro ramo não
    existe nenhuma — quem tem o link está a estabelecer a identidade, não a
    assumir uma.

    Uma conta com `is_active = False` leva a recusa genérica: activar dava
    pertença a uma conta que não consegue entrar, e dizer ao portador do link
    que a conta está desativada não lhe serve para nada.

    ## Uma transação dentro do âmbito, e o uso único é um `UPDATE` condicional

    Password, `Membership` e `accepted_at` vão numa transação só (ADR 0010). O
    uso único não é a verificação em Python que está mais acima — é o
    `_marcar_aceite`, um `UPDATE ... WHERE accepted_at IS NULL AND revoked_at IS
    NULL` que o Postgres serializa: duas activações simultâneas do mesmo link
    dão uma pertença e uma recusa, e uma revogação a competir com uma activação
    resolve-se do mesmo modo. A validação da password corre **antes** da marca,
    para uma password fraca não queimar o convite.

    ## A sessão fica fora do âmbito

    Como no `escolher_tenant_ativo`: a sessão é escrita pelo `SessionMiddleware`
    depois de a transação fechar (ADR 0005). O `login()` só corre quando a
    sessão não é já a da conta convidada — nesse caso a chave de sessão **não**
    roda, pela razão da ADR 0007: a rotação é um controlo de fixação ligado à
    autenticação, e esta sessão já tinha acesso a esta conta antes e depois.

    E o estabelecimento novo só fica ativo se a sessão não tiver nenhum. É a
    regra do login ("um candidato confirmado escreve-se na sessão") aplicada a um
    terceiro ponto de entrada; trocar o estabelecimento ativo de quem já estava
    a trabalhar noutro seria escolher em nome de quem tem de escolher.
    """
    tenant_id, token = _partir_fragmento(fragmento)

    with tenant_scope(tenant_id):
        convite = convite_por_token_hash(_hash_do_token(token))
        if convite is None or convite.estado != EstadoDoConvite.PENDENTE:
            raise _recusa_registada(_convite_invalido())

        user = _conta_do_email(convite.email)
        if user is not None and not user.is_active:
            raise _recusa_registada(_convite_invalido())

        # Lido antes de qualquer escrita: é o `request.user` que o pedido
        # trouxe, e é o que decide se há `login()` no fim.
        sessao_e_do_convidado = _sessao_e_desta_conta(request, user)

        if user is None or not user.has_usable_password():
            password_a_definir = _validar_password(password, email=convite.email)
        else:
            # O ramo em que a password do corpo não existe para esta função.
            password_a_definir = None
            if not sessao_e_do_convidado:
                raise _recusa_registada(_exige_a_propria_conta(request))

        with transaction.atomic():
            if not _marcar_aceite(convite):
                raise _recusa_registada(_convite_invalido())
            if user is None:
                user = User.objects.create_user(convite.email, password_a_definir)
            elif password_a_definir is not None:
                user.set_password(password_a_definir)
                user.save(update_fields=["password", "updated_at"])
            conceder_pertenca(
                user=user,
                tenant_id=tenant_id,
                role=convite.role,
                display_name=convite.display_name,
            )
            logger.info(
                "convite aceite",
                extra={"event": "convite_aceite", "outcome": "ok"},
            )

    if not sessao_e_do_convidado:
        login(request, user, backend=BACKEND_DE_SESSAO)

    tenants = _tenants_confirmados(user)
    ativo = _ativo_da_sessao(request, tenants)
    if ativo is None and len(tenants) == 1:
        ativo = tenants[0]
        request.session[SESSION_TENANT_KEY] = str(ativo.id)
    return _sessao(request, tenants=tenants, ativo=ativo)


# ---------------------------------------------------------------------------
# O token, e o fragmento que o transporta
# ---------------------------------------------------------------------------
def _novo_token() -> tuple[str, str]:
    """Um token novo e o seu SHA-256: o primeiro sai, o segundo fica.

    `token_urlsafe` e não `token_hex`: o valor viaja num URL e base64url dá 43
    caracteres para os mesmos 32 bytes que o hexadecimal daria em 64.
    """
    token = secrets.token_urlsafe(BYTES_DO_TOKEN)
    return token, _hash_do_token(token)


def _hash_do_token(token: str) -> str:
    """O que a coluna `token_hash` guarda. Uma definição, dois chamadores.

    Não há comparação em tempo constante, e não é esquecimento: o que se compara
    é o **hash**, por igualdade num índice único, e o segredo tem 256 bits de
    entropia. Um canal temporal sobre um índice B-tree não aproxima ninguém de
    adivinhar 2^256 valores; o que o contorna é ter o token, e quem o tem não
    precisa de medir nada.
    """
    return hashlib.sha256(token.encode()).hexdigest()


def _fragmento(tenant_id: UUID, token: str) -> str:
    """`<uuid-do-tenant>.<token>` — o que vai depois do `#` no link.

    O uuid vai no link e não no corpo de um email por uma razão só, e é a que
    torna a política de RLS possível nesta tabela: sem ele, a activação não
    saberia que âmbito abrir e a tabela teria de ser legível sem âmbito nenhum.
    """
    return f"{tenant_id}{SEPARADOR_DO_FRAGMENTO}{token}"


def _partir_fragmento(fragmento: str) -> tuple[UUID, str]:
    """As duas metades do fragmento, ou a recusa genérica.

    Um fragmento mal formado dá exatamente a mesma resposta que um token que não
    existe: é mais uma forma de "este link não serve", e distingui-la dizia a
    quem experimenta que o formato está certo e só o segredo está errado.
    """
    bruto, separador, token = fragmento.partition(SEPARADOR_DO_FRAGMENTO)
    if not separador or not token:
        raise _recusa_registada(_convite_invalido())
    try:
        return UUID(bruto), token
    except ValueError as erro:
        raise _recusa_registada(_convite_invalido()) from erro


# ---------------------------------------------------------------------------
# As recusas, construídas num sítio só
# ---------------------------------------------------------------------------
def _convite_invalido() -> RecusaDeConvite:
    """A recusa genérica da activação: **uma** função, logo **um** corpo.

    As cinco situações que a levantam — fragmento mal formado, uuid de tenant
    forjado, token inexistente, convite expirado, convite já usado ou revogado —
    passam todas por aqui. É isso que torna "o mesmo código e o mesmo corpo" uma
    propriedade do código e não uma coincidência entre cinco literais, e é por
    isso que o teste que compara os corpos dos cinco caminhos tem alguma coisa
    para medir.
    """
    return RecusaDeConvite(CODIGO_CONVITE_INVALIDO, DETALHE_CONVITE_INVALIDO)


def _exige_a_propria_conta(request: HttpRequest) -> RecusaDeConvite:
    """Sem sessão é 409; com a sessão de outra conta é 403.

    As duas são distinguíveis de propósito, porque o cliente faz coisas
    diferentes com elas: a primeira manda entrar, a segunda manda sair e entrar
    com outra conta. Nenhuma das duas diz que conta é — quem tem o link sabe o
    email que convidou, e o resto não lhe é devido.
    """
    if utilizador_atual(request) is None:
        return RecusaDeConvite(CODIGO_CONVITE_EXIGE_SESSAO, DETALHE_CONVITE_EXIGE_SESSAO)
    return RecusaDeConvite(CODIGO_CONVITE_DE_OUTRA_CONTA, DETALHE_CONVITE_DE_OUTRA_CONTA)


def _convite_nao_pendente(operacao: str) -> RecusaDeConvite:
    """O convite já foi aceite (ou revogado) e não pode ser `operacao`."""
    return RecusaDeConvite(
        CODIGO_CONVITE_NAO_PENDENTE,
        f"Este convite já não pode ser {operacao}: o seu estado mudou. "
        "Recarregue a lista de convites.",
    )


def _email_ja_convidado() -> ValidationError:
    """Erro de validação do campo `email`, não um `code` estável. Ver `criar_convite`."""
    return ValidationError(
        {
            "email": [
                "Já existe um convite para este email neste estabelecimento. "
                "Reenvie-o ou revogue-o."
            ]
        }
    )


def _recusa_registada(recusa: RecusaDeConvite) -> RecusaDeConvite:
    """Escreve a linha de log da recusa e devolve-a para ser levantada.

    O log tem de levar o código — distinguir no log é o que permite a quem opera
    saber se um link falhou por estar velho ou por ser forjado, que é a
    informação que a **resposta** não dá de propósito. Sem PII: o email do
    convite não entra, e a `message` é uma constante (`config/log.py`).
    """
    logger.warning(
        "activação de convite recusada",
        extra={"event": "convite_aceite", "outcome": recusa.codigo},
    )
    return recusa


# ---------------------------------------------------------------------------
# As peças da aceitação
# ---------------------------------------------------------------------------
def _conta_do_email(email: str) -> User | None:
    """A conta deste email, ou `None`. Lida de dentro do âmbito, e pode ser.

    O `accounts_user` não tem política (ADR 0007), logo esta leitura funciona
    dentro ou fora de âmbito — e lê-se aqui dentro porque é aqui que ela é
    necessária, depois de o convite ter casado. Pelo `get_by_natural_key`, que é
    onde vive a definição de "a mesma conta" (insensível à caixa, pelo índice
    funcional `LOWER(email)`): um `filter(email=...)` era uma segunda definição a
    divergir com o tempo.
    """
    try:
        return User.objects.get_by_natural_key(email)
    except User.DoesNotExist:
        return None


def _sessao_e_desta_conta(request: HttpRequest, user: User | None) -> bool:
    """A sessão do pedido é da conta convidada?

    `False` para um anónimo e para uma sessão de outra conta — a distinção entre
    esses dois casos é do `_exige_a_propria_conta`, e aqui o que interessa é só
    se há `login()` a fazer no fim.
    """
    atual = utilizador_atual(request)
    return atual is not None and user is not None and atual.id == user.pk


def _validar_password(password: str, *, email: str) -> str:
    """A password de quem activa, pelas regras do `AUTH_PASSWORD_VALIDATORS`.

    Corre **depois** de o convite casar, e tem de ser assim: o
    `UserAttributeSimilarityValidator` compara a password com o email da conta, e
    o email vem do convite. Validá-la antes obrigava o serializer a conhecer o
    email, que é precisamente o que o token esconde.

    Sai como erro de validação do campo `password` nos dois casos — em falta e
    fraca — porque é a forma que um formulário mostra ao lado do input. O
    `ValidationError` do `validate_password` vem sem dicionário, e é embrulhado
    aqui para o `views.py` ter sempre a mesma forma para serializar.
    """
    if not password:
        raise ValidationError(
            {"password": ["Escolha uma password para activar a sua conta."]}
        )
    try:
        # O `User` por gravar é só para o validador de semelhança poder comparar
        # a password com o email, como no `criar_tenant_com_dono`.
        validate_password(password, user=User(email=email))
    except ValidationError as erro:
        raise ValidationError({"password": erro.messages}) from erro
    return password


def _marcar_aceite(convite: Invitation) -> bool:
    """Queima o convite, e é este `UPDATE` que faz o uso único.

    Condicional de propósito: o estado lido antes desta linha pode ter mudado —
    uma segunda activação do mesmo link, ou uma revogação a competir. O Postgres
    serializa os dois `UPDATE` sobre a mesma linha e o segundo reavalia a
    condição, pelo que "zero linhas afetadas" é a resposta certa e não precisa de
    um `SELECT ... FOR UPDATE` à frente.
    """
    agora = timezone.now()
    return (
        Invitation.objects.filter(
            pk=convite.pk,
            accepted_at__isnull=True,
            revoked_at__isnull=True,
        ).update(accepted_at=agora, updated_at=agora)
        == 1
    )


def _exigir_email_convidavel(*, tenant_id: UUID, email: str) -> None:
    """Recusa convidar quem já é membro ativo, ou quem já tem convite aberto.

    As duas leituras são dentro do âmbito e sobre tabelas com política, logo não
    conseguem ver nada de outro estabelecimento mesmo que estas linhas estivessem
    mal escritas. O email chega já normalizado.
    """
    user = _conta_do_email(email)
    ja_e_membro = user is not None and (
        membership_no_ambito(user_id=user.pk, tenant_id=tenant_id) is not None
    )
    if ja_e_membro:
        raise ValidationError(
            {"email": ["Esta pessoa já é membro deste estabelecimento."]}
        )

    # A mesma condição do índice parcial `invitation_pendente_uniq`, incluindo o
    # `LOWER(email)`: se a regra em código e a rede na base de dados não
    # coincidirem, uma delas recusa o que a outra aceita.
    ja_convidado = (
        Invitation.objects.annotate(email_canonico=Lower("email"))
        .filter(
            email_canonico=email,
            accepted_at__isnull=True,
            revoked_at__isnull=True,
        )
        .exists()
    )
    if ja_convidado:
        raise _email_ja_convidado()


# ---------------------------------------------------------------------------
# O menu por tenant (ADR 0009 e ADR 0011).
#
# Uma função, porque é **um** caso de uso: "o menu deste estabelecimento passa
# a ser este". A ADR 0009 é explícita sobre a razão de não haver aqui uma função
# por item — reordenar é uma intenção só, e N escritas parciais deixam um menu
# meio ordenado se uma falhar.
#
# Escreve e não emite nada: zero eventos e zero tarefas neste módulo (ADR 0010),
# porque não existe consumidor da outbox e um evento sem subscritor é um
# contrato público escrito ao contrário.
# ---------------------------------------------------------------------------
@transaction.atomic
def guardar_menu(*, tenant_id: UUID, itens: list[dict[str, Any]]) -> tuple[ItemDeMenu, ...]:
    """Substitui **toda** a configuração de menu deste estabelecimento.

    ## Substituição total, e não um `PATCH` por item

    É a decisão da ADR 0009, e a razão não é de gosto de API: reordenar um menu
    é **uma** intenção, e N pedidos parciais deixam o menu meio ordenado se um
    deles falhar — com o cliente sem forma de saber quais passaram. Aqui, ou o
    menu novo entra inteiro ou fica o antigo: o `@transaction.atomic` é um
    savepoint dentro da transação do pedido (ADR 0005), e o `DELETE` e o
    `INSERT` vão nele.

    ## Apagar e reinserir, e não um diff

    "Substituição total" escreve-se assim em duas instruções e sem algoritmo:
    uma rota ausente do corpo volta ao default, que é exactamente o que a
    ausência de linha significa (ADR 0011, e ver o modelo). Um diff — manter o
    que não mudou, actualizar o resto — dava o mesmo resultado com um caminho a
    mais para se enganar, e `created_at` de uma linha de configuração não é um
    dado de que alguém dependa.

    O preço é nomeado: um cliente antigo que envie as rotas que **ele** conhece
    repõe o default das que não conhece. É inerente à substituição total e o
    recíproco — ignorar as ausentes — tornava impossível repor um default.

    ## Um corpo vazio é legítimo

    `[]` quer dizer "sem configuração nenhuma", ou seja o menu de defaults. É o
    botão "repor tudo" e não um caso degenerado — e **não** é "esconder tudo",
    que se escreve com `visivel: false` em cada item.

    ## O que esta função não faz

    Não valida o `route_id` contra o registo: quem o faz é o `ChoiceField` do
    serializer, contra o mesmo enum, e repeti-lo aqui dava duas verificações com
    uma a tornar-se a única que importa. Também não procura duplicados — é uma
    afirmação sobre a forma do corpo, não uma leitura à base de dados, e vive no
    `ListSerializer` (ver `serializers.py`). O que **é** daqui é a transação, o
    âmbito e a resposta.

    Devolve a projecção **inteira e sem filtro de papel**: é a configuração como
    ficou, que é o que o painel precisa de voltar a mostrar. Ver o
    `projeccao_de_menu`, onde está escrito porque é que filtrá-la aqui era um
    caminho para perder configuração.
    """
    _exigir_ambito(tenant_id, tabela="accounts_tenantmenuitem")

    # Dentro do âmbito, o `DELETE` só alcança as linhas deste tenant — pela
    # política **e** pelo filtro do selector, que são os dois controlos que o
    # `SECURITY.md` §1 exige lado a lado.
    itens_de_menu_do_ambito(tenant_id=tenant_id).delete()
    TenantMenuItem.objects.bulk_create(
        [
            TenantMenuItem(
                tenant_id=tenant_id,
                route_id=item["route_id"],
                grupo=item["grupo"],
                ordem=item["ordem"],
                visivel=item["visivel"],
                # `None` do contrato e `""` na coluna são a mesma ausência, e a
                # coluna não é nulável de propósito (ver o modelo).
                rotulo=item.get("rotulo") or "",
            )
            for item in itens
        ]
    )

    logger.info(
        "menu guardado",
        extra={"event": "menu", "outcome": "ok", "count": len(itens)},
    )
    return projeccao_de_menu(tenant_id=tenant_id)
