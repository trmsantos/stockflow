"""Serializers do `recipes` (ADR 0035, fatia A).

Leitura e escrita em classes separadas, campos listados um a um.
Sem `fields = "__all__"` (CLAUDE.md, SECURITY.md §4).

## O dinheiro sai por papel, e a chave fica **ausente**

Cinco chaves — `batch_cost`, `unit_cost` e `display_cost` no resumo, `unit_cost`
e `line_cost` na linha —, todas tiradas do payload pelo `SemEurosParaQuemNaoVe`
do `accounts.api` quando o papel não vê euros. **Nunca `0`**, que é uma afirmação
falsa sobre o preço. O `null` aqui é legítimo e quer dizer uma coisa só: *não há
número nenhum* (ADR 0035, decisão 10, degrau 5), e é o que o ecrã imprime como
"—". A diferença entre as duas é o que o cliente tem de distinguir, e é por isso
que os schemas Zod destes campos nascem `.optional().nullable()` e nunca só
`.nullable()`.

**A `ReceitaDetalheOutSerializer` NÃO redeclara o `CAMPOS_DE_DINHEIRO`** — ADR
0035, decisão 6, a citar a 0034, decisão 15: redeclará-lo é literalmente a porta
irmã por onde o dinheiro sai, e esta casa já lá caiu duas vezes (a ADR 0031
fechou os euros da receção e deixou o `ExtracaoOut` do documento aberto **sobre a
mesma fatura**). O guarda independente é o
`test_o_que_a_tabela_diz_que_o_mixin_esconde_esta_mesmo_no_mixin` do
`tests/test_receitas.py`, que lê o atributo **na subclasse**.

O que fica para os três papéis: as quantidades (as quantidades são o produto), a
fornada, o rendimento, o `cost_status` por linha e no agregado, e a cobertura
`ingredients_without_cost` — que é **contagem** e não euro.

## As quantidades e a conversão vêm do `apps.shared`

`QuantidadeOutSerializer`, `quantidade_bruta` e `em_unidade_pedida` vivem em
`apps/shared/serializers.py` e não aqui nem no `inventory`: o `recipes` serve as
mesmas quantidades que o `/stock/levels` e aceita as mesmas unidades, e declarar
gémeos dava um segundo componente OpenAPI e uma segunda definição da regra das
unidades. A aresta permitida é `recipes → inventory.api`, não
`recipes → inventory.serializers`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any, ClassVar

from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from apps.accounts.api import SemEurosParaQuemNaoVe
from apps.inventory.api import ESTADOS_DO_CUSTO
from apps.recipes.services import (
    CODIGO_RECEITA_JA_EXISTE,
    DETALHE_FORNADA,
    DETALHE_QUANTIDADE,
    DETALHE_RENDIMENTO,
    DETALHE_REPETIDO,
)
from apps.shared.serializers import QuantidadeOutSerializer, quantidade_bruta

__all__ = [
    "ConflitoDeReceitaOutSerializer",
    "LinhaDaReceitaInSerializer",
    "LinhaDaReceitaOutSerializer",
    "ReceitaDetalheOutSerializer",
    "ReceitaInSerializer",
    "ReceitaPatchInSerializer",
    "ReceitaResumoOutSerializer",
    "compor_ficha",
    "compor_resumo",
]

DETALHE_FORNADA_SEM_UNIDADE = _(
    "Send batch_size and batch_unit together: a number without a unit is not a "
    "batch."
)


# ---------------------------------------------------------------------------
# Saída
# ---------------------------------------------------------------------------
class LinhaDaReceitaOutSerializer(SemEurosParaQuemNaoVe, serializers.Serializer):
    """Um ingrediente da ficha: as duas quantidades e o custo dele.

    `quantity` é o que a receita escreve **para uma fornada**; `quantity_real` é
    `quantity ÷ yield_factor`, o que sai do stock. As duas são números diferentes
    e a confusão entre elas é o erro clássico do rendimento — por isso viajam as
    duas, e nenhuma se calcula no cliente.

    `ingredient_is_active` é do **artigo**: uma ficha activa pode conter um
    artigo arquivado e isso aceita-se, porque arquivar um artigo não pode partir
    a gravação de uma ficha que já o continha. Quem recusa é a produção, na
    fatia B — o sítio onde a decisão tem consequência é o movimento de stock, não
    o documento.

    `cost_status` vai para os três papéis e os dois euros não: a palavra diz
    *com que certeza*, e é o que fica para quem não vê o número.
    """

    CAMPOS_DE_DINHEIRO: ClassVar[tuple[str, ...]] = ("unit_cost", "line_cost")

    ingredient = serializers.UUIDField(read_only=True)
    short_name = serializers.CharField(read_only=True)
    sku = serializers.CharField(read_only=True)
    ingredient_is_active = serializers.BooleanField(read_only=True)
    quantity = QuantidadeOutSerializer(
        read_only=True, help_text="O que a ficha escreve, **por fornada**."
    )
    quantity_real = QuantidadeOutSerializer(
        read_only=True,
        help_text="`quantity ÷ yield_factor` — o que de facto sai do stock.",
    )
    cost_status = serializers.ChoiceField(choices=ESTADOS_DO_CUSTO, read_only=True)
    unit_cost = serializers.DecimalField(
        max_digits=12,
        decimal_places=6,
        read_only=True,
        allow_null=True,
        help_text=(
            "Custo de uma unidade **base** deste ingrediente, pela escada da "
            "ADR 0035, decisão 10. NULL quando não há número nenhum. Ausente "
            "para quem não vê euros."
        ),
    )
    line_cost = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        read_only=True,
        allow_null=True,
        help_text=(
            "`quantity_real × unit_cost`. NULL quando o ingrediente não tem "
            "custo. Ausente para quem não vê euros."
        ),
    )


class ReceitaResumoOutSerializer(SemEurosParaQuemNaoVe, serializers.Serializer):
    """Uma linha do `GET /recipes`: o acabado, a fornada e o custo dela.

    ## Os três euros saem juntos, e é por aritmética

    `line_cost ÷ quantity_real` devolve o `unit_cost` do ingrediente,
    `Σ(line_cost)` devolve o `batch_cost` e `batch_cost ÷ batch_size` devolve o
    `unit_cost` da receita. As quatro pontas da divisão — `quantity`,
    `quantity_real`, `yield_factor` e `batch_size` — estão no payload de quem
    **não** vê euros e continuam a estar, porque as quantidades são o produto
    (ADR 0032, decisão 2). Esconder um euro e deixar os outros era teatro.

    `display_cost` existe ao lado do `unit_cost` e não em vez dele: o
    `unit_cost` é por unidade **base**, como todo o ledger e como o
    `/stock/levels` — uma definição —, mas a pergunta do dono é literalmente
    *"quanto me custa um pastel"*, e um pastel é uma unidade de apresentação.
    Fazer o cliente multiplicar pelo `display_factor` é a conversão no cliente
    que a casa proíbe.

    **Nunca "custo do prato"** (ADR 0035, decisão 9): é o custo de
    **ingredientes**, o *food cost*. Numa pastelaria, chamar-lhe custo do prato
    é falso por um factor de 2 a 4, porque num produto com 20 cêntimos de
    matéria a mão-de-obra é o custo dominante.
    """

    CAMPOS_DE_DINHEIRO: ClassVar[tuple[str, ...]] = (
        "batch_cost",
        "unit_cost",
        "display_cost",
    )

    id = serializers.UUIDField(read_only=True)
    product = serializers.UUIDField(read_only=True)
    short_name = serializers.CharField(read_only=True)
    sku = serializers.CharField(read_only=True)
    base_unit = serializers.CharField(read_only=True)
    display_unit = serializers.CharField(read_only=True)
    display_factor = serializers.DecimalField(
        max_digits=12, decimal_places=3, read_only=True
    )
    is_active = serializers.BooleanField(read_only=True)
    batch_size = QuantidadeOutSerializer(
        read_only=True,
        help_text=(
            "Quanto acabado sai de **uma** fornada. Servido também em "
            "apresentação, senão o cozinheiro lê 2400 onde escreveu 2,4 kg."
        ),
    )
    yield_factor = serializers.DecimalField(
        max_digits=5,
        decimal_places=3,
        read_only=True,
        help_text=(
            "Rendimento do processo. Nasce a 1,000 porque a perda já está na "
            "fornada; não tem tecto de 1 (arroz cru → cozido é > 1)."
        ),
    )
    line_count = serializers.IntegerField(read_only=True)
    cost_status = serializers.ChoiceField(
        choices=ESTADOS_DO_CUSTO,
        read_only=True,
        help_text=(
            "O agregado: **nunca** `conhecido` se alguma linha não o for, e "
            "`desconhecido` só quando nenhuma linha tem custo — e aí os euros "
            "saem `null`."
        ),
    )
    ingredients_without_cost = serializers.IntegerField(
        read_only=True,
        help_text=(
            "Quantas linhas não têm custo nenhum. É **contagem** e não euro, "
            "logo vai para os três papéis. É uma cobertura mais fraca do que a "
            "`quantity_without_cost` do stock — um ingrediente em dez pode ser "
            "90 % do custo — e é por isso que o `cost_status` por linha existe."
        ),
    )
    batch_cost = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        read_only=True,
        allow_null=True,
        help_text="€ da **fornada** inteira. Ausente para quem não vê euros.",
    )
    unit_cost = serializers.DecimalField(
        max_digits=12,
        decimal_places=6,
        read_only=True,
        allow_null=True,
        help_text=(
            "`batch_cost ÷ batch_size` — € por unidade **base** do acabado. "
            "Ausente para quem não vê euros."
        ),
    )
    display_cost = serializers.DecimalField(
        max_digits=14,
        decimal_places=6,
        read_only=True,
        allow_null=True,
        help_text=(
            "`unit_cost × display_factor` — € por unidade de **apresentação**, "
            "que é a pergunta do dono. Ausente para quem não vê euros."
        ),
    )


class ReceitaDetalheOutSerializer(ReceitaResumoOutSerializer):
    """O corpo do `GET /recipes/<id>`: o resumo **mais as linhas**.

    Zero campos repetidos: os dezasseis do resumo herdam-se, e do lado do cliente
    também não nasce um segundo schema — é o `receitaResumoSchema.extend({
    lines })`.

    ## O `CAMPOS_DE_DINHEIRO` **não** se redeclara aqui

    Herda-se, e é a ADR 0035, decisão 6, por extenso. O contexto é o mesmo
    `get_serializer_context()` do `ReceitaViewSet`, e o seu default é **falso**:
    esquecê-lo esconde dinheiro a toda a gente, que é a direcção certa para
    falhar.
    """

    lines = LinhaDaReceitaOutSerializer(many=True, read_only=True)


class ConflitoDeReceitaOutSerializer(serializers.Serializer):
    """O 409 do `POST /recipes`: `code` para ramificar, `id` para navegar.

    O artigo já tem ficha, e a resposta leva o **id da que existe** para o ecrã
    levar lá quem tentou — em vez de lhe dizer "erro" e o mandar procurar à mão
    o que o servidor já sabia (precedente: o 409 da contagem já aberta).

    O `code` é `CharField` e não `ChoiceField`, como no
    `ConflitoDeContagemOutSerializer` e pela razão que o `base.py` escreve sobre
    o `TypeEnum`: um `ChoiceField` com um valor só emitia um componente chamado
    **`CodeEnum`** — o nome derivado do campo —, e o primeiro outro serializer
    com um `code` fechado colide com ele e o drf-spectacular resolve a colisão
    com um sufixo de hash, que é um nome que muda sozinho e um warning que é
    exit 1 no `pnpm gen:api`. O valor é `receita_ja_existe` e está no
    `help_text`, que é onde o cliente o lê sem pagar um componente por ele.
    """

    code = serializers.CharField(
        read_only=True,
        help_text=f"Hoje só `{CODIGO_RECEITA_JA_EXISTE}`.",
    )
    detail = serializers.CharField(read_only=True)
    id = serializers.UUIDField(read_only=True)


# ---------------------------------------------------------------------------
# Entrada
# ---------------------------------------------------------------------------
class LinhaDaReceitaInSerializer(serializers.Serializer):
    """Um ingrediente a gravar: o artigo, a quantidade e a **unidade dela**.

    O nome é `LinhaDaReceitaIn` e não `LinhaIn`, que é como a ADR 0035 lhe
    chama: o `purchasing` já tem um `LinhaInSerializer` (a linha de uma receção)
    e o nome do componente OpenAPI é o da classe — duas classes com o mesmo nome
    dão **um** `LinhaInRequest` com os campos de uma delas, que é um warning e
    portanto exit 1 no `spectacular --fail-on-warn`. Medido ao gerar.

    `unit` tem de ser o `base_unit` ou o `display_unit` **daquele ingrediente** e
    qualquer outra é 400: não existe motor genérico de conversão (ADR 0011). O
    pasteleiro escreve "500 g de farinha" num catálogo cujo artigo é base `g` e
    apresentação `kg`, e a conversão é do servidor — fazê-la no cliente é a fonte
    nº 1 de bugs de stock.

    Quem valida a unidade é a view, porque só ela pode ir buscar o artigo.
    """

    ingredient = serializers.UUIDField()
    quantity = serializers.DecimalField(max_digits=12, decimal_places=3)
    unit = serializers.CharField(max_length=16)

    def validate_quantity(self, value: Decimal) -> Decimal:
        """`> 0`, e a mensagem é a do serviço — uma frase, não duas."""
        if value <= Decimal("0"):
            raise serializers.ValidationError(DETALHE_QUANTIDADE)
        return value


class ReceitaInSerializer(serializers.Serializer):
    """O corpo do `POST /recipes`: a ficha inteira, linhas incluídas.

    As linhas viajam **dentro do corpo** e não num sub-recurso (ADR 0035,
    decisão 4): a contagem e a receção têm `POST /…/lines` porque são
    **percursos** — uma folha que se anda com o telemóvel na mão —, e uma ficha
    técnica escreve-se de uma vez, num formulário com um botão de gravar. Oito
    `POST` para oito ingredientes é uma receita meio gravada, e uma receita meio
    gravada é um custo errado que ninguém vê.
    """

    product = serializers.UUIDField(help_text="O artigo acabado. É a identidade da ficha.")
    batch_size = serializers.DecimalField(
        max_digits=12,
        decimal_places=3,
        help_text="Quanto acabado sai de uma fornada, na unidade `batch_unit`.",
    )
    batch_unit = serializers.CharField(
        max_length=16,
        help_text=(
            "A unidade base ou a de apresentação **do acabado**: \"2,4 kg\" ou "
            "\"2400 g\", e nada mais."
        ),
    )
    yield_factor = serializers.DecimalField(
        max_digits=5,
        decimal_places=3,
        required=False,
        default=Decimal("1.000"),
        help_text=(
            "Default `1.000`: o rendimento vive na fornada, e pôr também 0,9 "
            "conta a mesma perda duas vezes."
        ),
    )
    is_active = serializers.BooleanField(required=False, default=True)
    lines = LinhaDaReceitaInSerializer(many=True, allow_empty=False)

    def validate_batch_size(self, value: Decimal) -> Decimal:
        if value <= Decimal("0"):
            raise serializers.ValidationError(DETALHE_FORNADA)
        return value

    def validate_yield_factor(self, value: Decimal) -> Decimal:
        """`> 0` e **sem tecto de 1**: arroz 1 kg cru → 2,7 kg cozido é real."""
        if value <= Decimal("0"):
            raise serializers.ValidationError(DETALHE_RENDIMENTO)
        return value

    def validate_lines(self, value: Sequence[Mapping[str, Any]]) -> Any:
        """Ingrediente repetido é 400, nunca duas linhas somadas em silêncio."""
        ids = [linha["ingredient"] for linha in value]
        if len(set(ids)) != len(ids):
            raise serializers.ValidationError(DETALHE_REPETIDO)
        return value


class ReceitaPatchInSerializer(serializers.Serializer):
    """O corpo do `PATCH /recipes/<id>`. **Sem `product`**: é a identidade.

    `lines` **ausente** não toca nas linhas; `lines` **presente** substitui-as
    todas. Está escrito aqui e na ADR porque é a única parte do contrato que não
    se adivinha.

    Não há `DELETE`: uma receita não se apaga, arquiva-se com
    `PATCH {is_active: false}` — foi a ficha técnica de mercadoria que entrou no
    ledger. Uma receita inactiva continua a responder 200.
    """

    batch_size = serializers.DecimalField(
        max_digits=12, decimal_places=3, required=False
    )
    batch_unit = serializers.CharField(max_length=16, required=False)
    yield_factor = serializers.DecimalField(max_digits=5, decimal_places=3, required=False)
    is_active = serializers.BooleanField(required=False)
    lines = LinhaDaReceitaInSerializer(many=True, required=False, allow_empty=False)

    validate_batch_size = ReceitaInSerializer.validate_batch_size
    validate_yield_factor = ReceitaInSerializer.validate_yield_factor
    validate_lines = ReceitaInSerializer.validate_lines

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """A fornada e a unidade dela viajam **juntas**, ou não viajam.

        Um `batch_size` sozinho não se consegue interpretar — 2,4 é quilos ou
        gramas? — e escolher uma por omissão era inventar um número mil vezes
        errado. Um `batch_unit` sozinho não muda nada e é quase sempre um corpo
        mal montado; recusá-lo diz isso em vez de o ignorar.
        """
        if ("batch_size" in attrs) != ("batch_unit" in attrs):
            raise serializers.ValidationError(
                {"batch_unit": [DETALHE_FORNADA_SEM_UNIDADE]}
            )
        return attrs


# ---------------------------------------------------------------------------
# Composição: do DTO da porta para a forma do contrato
# ---------------------------------------------------------------------------
def _linha(ingrediente: Any) -> dict[str, Any]:
    unidades = {
        "base_unit": ingrediente.base_unit,
        "display_unit": ingrediente.display_unit,
        "display_factor": ingrediente.display_factor,
    }
    return {
        "ingredient": ingrediente.product_id,
        "short_name": ingrediente.product_name,
        "sku": ingrediente.sku,
        "ingredient_is_active": ingrediente.is_active,
        "quantity": quantidade_bruta(ingrediente.quantidade_lista, **unidades),
        "quantity_real": quantidade_bruta(ingrediente.quantidade_real, **unidades),
        "cost_status": ingrediente.cost_status,
        "unit_cost": ingrediente.unit_cost,
        "line_cost": ingrediente.line_cost,
    }


def compor_resumo(ficha: Any) -> dict[str, Any]:
    """Uma linha do `GET /recipes`, do DTO da porta para o contrato."""
    resumo = ficha.resumo
    custo = ficha.custo
    return {
        "id": resumo.id,
        "product": resumo.product_id,
        "short_name": resumo.product_name,
        "sku": resumo.sku,
        "base_unit": resumo.base_unit,
        "display_unit": resumo.display_unit,
        "display_factor": resumo.display_factor,
        "is_active": resumo.is_active,
        "batch_size": quantidade_bruta(
            resumo.batch_size,
            base_unit=resumo.base_unit,
            display_unit=resumo.display_unit,
            display_factor=resumo.display_factor,
        ),
        "yield_factor": resumo.yield_factor,
        "line_count": resumo.n_ingredientes,
        "cost_status": custo.cost_status,
        "ingredients_without_cost": custo.ingredients_without_cost,
        "batch_cost": custo.batch_cost,
        "unit_cost": custo.unit_cost,
        "display_cost": custo.display_cost,
    }


def compor_ficha(ficha: Any) -> dict[str, Any]:
    """O corpo do `GET /recipes/<id>`: o `compor_resumo` **mais as linhas**.

    Construído por cima do resumo e não ao lado dele: assim o cabeçalho da ficha
    **é** a linha da lista, por construção e não por coincidência. É o argumento
    da ADR 0034, adenda de 29, decisão 14, e o teste que compara os dois falha
    nos dois sentidos.
    """
    return {
        **compor_resumo(ficha),
        "lines": [_linha(ingrediente) for ingrediente in ficha.ingredientes],
    }
