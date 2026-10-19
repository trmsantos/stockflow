"""Serializers para o inventory (ADR 0021, fatia 2; ADR 0022; ADR 0024, fatia 4;
ADR 0030, contagens).

Leitura e escrita em classes separadas, campos listados um a um.
Sem `fields = "__all__"` (CLAUDE.md, SECURITY.md §4).
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from apps.inventory.count_services import (
    MOTIVO_OBRIGATORIO_ACIMA_DE_EUR,
    ROTULO_DE_QUEM_FECHA,
)

#: O tecto da coluna `Decimal(12,3)` do `StockCountLine`, na unidade **base**.
#: Vive aqui e não no serviço porque é aqui que a conversão faz o número crescer.
MAXIMO_DA_QUANTIDADE = Decimal("999999999.999")

DETALHE_QUANTIDADE_GRANDE = _("This amount is too large for a count.")

__all__ = [
    "LocalizacaoInSerializer",
    "LocalizacaoOutSerializer",
    "LocalizacaoPatchInSerializer",
    "StockSummarySerializer",
    "StockDetailSerializer",
    "AlertSerializer",
    "WasteSerializer",
    "AdjustmentSerializer",
    "TransferSerializer",
    "StockMovementResponseSerializer",
    "ConflitoDeContagemOutSerializer",
    "ContagemInSerializer",
    "ContagemOutSerializer",
    "FechoDeContagemInSerializer",
    "FechoDeContagemOutSerializer",
    "LinhaDeContagemInSerializer",
    "LinhaDeContagemOutSerializer",
    "LocalizacaoReferenciaSerializer",
    "PorContarOutSerializer",
    "ProgressoDeZonaOutSerializer",
    "QuantidadeOutSerializer",
    "ZonaOutSerializer",
    "compor_contagem",
    "compor_fecho",
    "compor_linha",
    "em_unidade_base",
    "quantidade",
    "zona_da_localizacao",
]


class LocalizacaoInSerializer(serializers.Serializer):
    """Localização nova."""

    name = serializers.CharField(
        max_length=60,
        min_length=1,
        help_text="Nome único por tenant (sem caixa)",
    )
    position = serializers.IntegerField(
        required=False,
        allow_null=True,
        help_text="Posição (ordem). Default: fim da lista",
    )

    def validate_position(self, value):
        """Position: positivo pequeno ou None."""
        if value is not None:
            if value < 0 or value > 32767:
                raise serializers.ValidationError(
                    _("Position must be between 0 and 32767.")
                )
        return value


class LocalizacaoOutSerializer(serializers.Serializer):
    """Localização lida (GET, POST 201, PATCH 200)."""

    id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(read_only=True)
    position = serializers.IntegerField(read_only=True)
    is_active = serializers.BooleanField(read_only=True)


class LocalizacaoPatchInSerializer(serializers.Serializer):
    """Localização PATCH."""

    name = serializers.CharField(
        max_length=60,
        min_length=1,
        required=False,
    )
    position = serializers.IntegerField(required=False)
    is_active = serializers.BooleanField(required=False)

    def validate_position(self, value):
        """Position: positivo pequeno."""
        if value is not None:
            if value < 0 or value > 32767:
                raise serializers.ValidationError(
                    _("Position must be between 0 and 32767.")
                )
        return value


class StockSummarySerializer(serializers.Serializer):
    """Resumo de stock agregado por produto (painel, fatia 4)."""

    product_id = serializers.UUIDField(read_only=True)
    product_name = serializers.CharField(read_only=True)
    quantity = serializers.DecimalField(
        max_digits=12,
        decimal_places=3,
        read_only=True,
        help_text="Quantidade total em unidade base",
    )
    unit_cost = serializers.DecimalField(
        max_digits=12,
        decimal_places=6,
        read_only=True,
        allow_null=True,
        help_text="Custo unitário (NULL se zero)",
    )
    total_value = serializers.SerializerMethodField(read_only=True)

    def get_total_value(self, obj) -> Decimal | None:
        """Quantidade × custo unitário."""
        quantity = obj.get("total_quantity")
        unit_cost = obj.get("avg_unit_cost")
        if quantity and unit_cost:
            return quantity * unit_cost
        return None


class StockDetailSerializer(serializers.Serializer):
    """Detalhe de stock por (product, lot) ou (location, lot) (fatia 4)."""

    product_id = serializers.UUIDField(read_only=True)
    product_name = serializers.CharField(read_only=True)
    location_id = serializers.UUIDField(read_only=True, allow_null=True)
    location_name = serializers.CharField(read_only=True, allow_null=True)
    lot_code = serializers.CharField(read_only=True, allow_null=True)
    expires_at = serializers.DateTimeField(
        read_only=True,
        allow_null=True,
        help_text="Data de validade (NULL se sem data)",
    )
    quantity = serializers.DecimalField(
        max_digits=12,
        decimal_places=3,
        read_only=True,
        help_text="Quantidade em unidade base",
    )
    unit_cost = serializers.DecimalField(
        max_digits=12,
        decimal_places=6,
        read_only=True,
        allow_null=True,
        help_text="Custo unitário (NULL se zero)",
    )
    total_value = serializers.SerializerMethodField(read_only=True)

    def get_total_value(self, obj) -> Decimal | None:
        """Quantidade × custo unitário."""
        quantity = obj.get("quantity") or obj.get("total_quantity")
        unit_cost = obj.get("unit_cost")
        if quantity and unit_cost:
            return quantity * unit_cost
        return None


class AlertSerializer(serializers.Serializer):
    """Alerta de stock (falta, validade a vencer, vencida) (fatia 4)."""

    alert_type = serializers.CharField(
        read_only=True,
        help_text="shortage|expiring_soon|expired",
    )
    severity = serializers.CharField(
        read_only=True,
        help_text="critical|warning|info",
    )
    product_id = serializers.UUIDField(read_only=True)
    product_name = serializers.CharField(read_only=True)
    location_id = serializers.UUIDField(read_only=True, allow_null=True)
    location_name = serializers.CharField(read_only=True, allow_null=True)
    lot_code = serializers.CharField(read_only=True, allow_null=True)
    expires_at = serializers.DateTimeField(
        read_only=True,
        allow_null=True,
        help_text="Data de validade (NULL se sem data)",
    )


class WasteSerializer(serializers.Serializer):
    """Entrada de desperdício (POST /stock/movements/waste)."""

    product_id = serializers.UUIDField(
        help_text="UUID do produto"
    )
    location_id = serializers.UUIDField(
        help_text="UUID da localização"
    )
    quantity = serializers.DecimalField(
        max_digits=12,
        decimal_places=3,
        min_value=Decimal("0.001"),
        help_text="Quantidade > 0 (em unidade base)",
    )
    lot_id = serializers.UUIDField(
        required=False,
        allow_null=True,
        help_text="UUID do lote (obrigatório se product.track_lots=True)",
    )
    reason = serializers.ChoiceField(
        choices=["expired", "spoiled", "prep_loss", "breakage", "other"],
        help_text="Motivo do desperdício",
    )
    reason_detail = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=500,
        help_text="Detalhes opcionais se reason='other'",
    )


class AdjustmentSerializer(serializers.Serializer):
    """Entrada de ajuste (POST /stock/movements/adjustment)."""

    product_id = serializers.UUIDField(
        help_text="UUID do produto"
    )
    location_id = serializers.UUIDField(
        help_text="UUID da localização"
    )
    quantity = serializers.DecimalField(
        max_digits=12,
        decimal_places=3,
        help_text="Quantidade ± (positivo = entrada, negativo = saída)",
    )
    lot_id = serializers.UUIDField(
        required=False,
        allow_null=True,
        help_text="UUID do lote (obrigatório se product.track_lots=True)",
    )
    reason = serializers.ChoiceField(
        choices=["expired", "spoiled", "prep_loss", "breakage", "other"],
        help_text="Motivo do ajuste",
    )
    reason_detail = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=500,
        help_text="Detalhes opcionais se reason='other'",
    )

    def validate_quantity(self, value):
        """Quantidade não pode ser zero."""
        if value == Decimal("0"):
            raise serializers.ValidationError(
                _("Quantity cannot be zero.")
            )
        return value


class TransferSerializer(serializers.Serializer):
    """Entrada de transferência (POST /stock/movements/transfer)."""

    product_id = serializers.UUIDField(
        help_text="UUID do produto"
    )
    from_location_id = serializers.UUIDField(
        help_text="UUID da localização de origem"
    )
    to_location_id = serializers.UUIDField(
        help_text="UUID da localização de destino"
    )
    quantity = serializers.DecimalField(
        max_digits=12,
        decimal_places=3,
        min_value=Decimal("0.001"),
        help_text="Quantidade > 0 (em unidade base)",
    )
    lot_id = serializers.UUIDField(
        required=False,
        allow_null=True,
        help_text="UUID do lote (obrigatório se product.track_lots=True)",
    )


class StockMovementResponseSerializer(serializers.Serializer):
    """Resposta de um movimento de stock criado (201)."""

    movement_id = serializers.UUIDField(read_only=True)
    product_name = serializers.CharField(read_only=True)
    location_name = serializers.CharField(read_only=True)
    lot_code = serializers.CharField(read_only=True, allow_null=True)
    quantity = serializers.DecimalField(
        max_digits=12,
        decimal_places=3,
        read_only=True,
    )
    unit_cost = serializers.DecimalField(
        max_digits=12,
        decimal_places=6,
        read_only=True,
    )
    created_at = serializers.DateTimeField(read_only=True)




# ===========================================================================
# Contagem física (ADR 0030). As formas são as dos schemas Zod do cliente —
# `contagemSchema`, `linhaDeContagemSchema` e `fechoDeContagemSchema` — porque
# a ADR resolveu as divergências a favor do cliente: `counted`/`expected`/
# `difference`, quantidades como objecto base+apresentação, e entrada por
# `product` e não por `sku`.
#
# A composição vive aqui, em funções, e não na view: a view escolhe o serviço e
# o estado HTTP, a forma da resposta é desta camada. Os serializers lêem
# dicionários e não modelos, pela mesma razão — o que atravessa o fio é um
# contrato e não uma tabela.
# ===========================================================================


class QuantidadeOutSerializer(serializers.Serializer):
    """Uma quantidade nas duas formas: a do ledger e a de mostrar.

    O ledger guarda sempre a unidade **base** (g, ml, un) e o ecrã mostra a de
    apresentação (kg, l, un). A conversão é do servidor: converter unidades no
    cliente é a fonte nº 1 de bugs de stock (`inventory-domain` §2), e sem o par
    o ecrã mostra "3400,000 g" a quem diz "3,4 kg".
    """

    base = serializers.DecimalField(max_digits=12, decimal_places=3, read_only=True)
    base_unit = serializers.CharField(read_only=True)
    display = serializers.DecimalField(max_digits=12, decimal_places=3, read_only=True)
    display_unit = serializers.CharField(read_only=True)


class ZonaOutSerializer(serializers.Serializer):
    """Uma zona da contagem. Nesta fatia a zona **é** a localização (ADR 0030, d3).

    `blind` é facto e não marcador de lugar: nenhuma zona é cega porque a
    contagem cega não existe — é sonda do guião §3 e fica fora de âmbito.
    """

    slug = serializers.CharField(read_only=True)
    name = serializers.CharField(read_only=True)
    position = serializers.IntegerField(read_only=True)
    blind = serializers.BooleanField(read_only=True)


class ProgressoDeZonaOutSerializer(ZonaOutSerializer):
    """A mesma zona com o progresso. Vive na contagem, não repetida em cada linha."""

    counted_lines = serializers.IntegerField(read_only=True)
    total_lines = serializers.IntegerField(read_only=True)


class LocalizacaoReferenciaSerializer(serializers.Serializer):
    """`{id, name}` — a localização como o cliente a lê em todo o lado."""

    id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(read_only=True)


class ContagemInSerializer(serializers.Serializer):
    """`POST /stock/counts`: contar é sempre contar **uma** localização."""

    location = serializers.UUIDField(help_text="UUID da localização a contar")


class ContagemOutSerializer(serializers.Serializer):
    """Uma contagem como a lista e o cabeçalho do ecrã a mostram."""

    id = serializers.UUIDField(read_only=True)
    location = LocalizacaoReferenciaSerializer(read_only=True)
    status = serializers.ChoiceField(choices=["open", "closed"], read_only=True)
    started_at = serializers.DateTimeField(read_only=True)
    closed_at = serializers.DateTimeField(read_only=True, allow_null=True)
    counted_lines = serializers.IntegerField(read_only=True)
    total_lines = serializers.IntegerField(read_only=True)
    current_zone = ProgressoDeZonaOutSerializer(read_only=True, allow_null=True)
    zones = ProgressoDeZonaOutSerializer(many=True, read_only=True)
    closing_role = serializers.CharField(
        read_only=True, help_text="Rótulo de quem pode fechar. Não é a permissão."
    )
    closing_reason = serializers.CharField(read_only=True, allow_null=True)


class LinhaDeContagemInSerializer(serializers.Serializer):
    """`POST /stock/counts/{id}/lines`: o artigo e quanto lá está.

    Sem `sku` (morreu com o contrato do servidor) e sem `unit` — o `unit` era
    pior que morto: era aceite e **silenciosamente ignorado** pelo serviço.
    """

    product = serializers.UUIDField(help_text="UUID do artigo contado")
    quantity = serializers.DecimalField(
        max_digits=12,
        decimal_places=3,
        min_value=Decimal("0"),
        help_text=(
            "Quantidade contada, na unidade de contagem da linha "
            "(`count_unit`, que é a de apresentação do artigo: kg, L, un). "
            "O servidor converte para a unidade base — converter no cliente é "
            "o que o domínio proíbe."
        ),
    )


class LinhaDeContagemOutSerializer(serializers.Serializer):
    """Uma linha: o que o sistema diz, o que se contou e a diferença.

    `difference_eur` vem a `null` para o `staff` — é a regra dos euros da ADR
    0029 —, e o preço é que `null` passa a dizer duas coisas ("ainda não
    contado" e "não te é mostrado"). É o menor dos males contra negar a lista a
    quem conta.
    """

    id = serializers.UUIDField(read_only=True)
    product = serializers.UUIDField(read_only=True)
    short_name = serializers.CharField(read_only=True)
    zone = ZonaOutSerializer(read_only=True)
    position = serializers.IntegerField(read_only=True)
    count_unit = serializers.CharField(read_only=True)
    expected = QuantidadeOutSerializer(read_only=True, allow_null=True)
    counted = QuantidadeOutSerializer(read_only=True, allow_null=True)
    difference = QuantidadeOutSerializer(read_only=True, allow_null=True)
    difference_eur = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True, allow_null=True
    )
    counted_by = serializers.CharField(read_only=True, allow_null=True)
    counted_at = serializers.DateTimeField(read_only=True, allow_null=True)


class PorContarOutSerializer(serializers.Serializer):
    """As linhas que ficam por contar: quantas e quais.

    Existe para o ecrã poder dizer "Fechar com 3 por contar" em vez de desligar
    o botão: fechar uma contagem imperfeita tem de ser possível, senão quem
    conta inventa números para o botão acender (guião §4).
    """

    count = serializers.IntegerField(read_only=True)
    names = serializers.ListField(child=serializers.CharField(), read_only=True)


class FechoDeContagemInSerializer(serializers.Serializer):
    """`POST /stock/counts/{id}/closing`: a justificação, **sempre obrigatória**.

    Texto livre e não um enum: uma contagem não cai nos cinco motivos de um
    desperdício, e a razão de uma diferença é quase sempre uma frase ("faltou
    lançar a transferência"). Sem limiar, por decisão do dono (ADR 0030,
    segunda ronda, nº 5).
    """

    reason = serializers.CharField(
        max_length=200,
        trim_whitespace=True,
        allow_blank=False,
        help_text="Porque é que esta contagem fecha. Obrigatória.",
    )


class FechoDeContagemOutSerializer(serializers.Serializer):
    """O fecho: as diferenças em quantidade e em euros, antes e depois de escrever."""

    count = serializers.UUIDField(read_only=True)
    status = serializers.ChoiceField(choices=["open", "closed"], read_only=True)
    counted_lines = serializers.IntegerField(read_only=True)
    total_lines = serializers.IntegerField(read_only=True)
    differences = LinhaDeContagemOutSerializer(many=True, read_only=True)
    uncounted_lines = PorContarOutSerializer(read_only=True)
    loss_eur = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    gain_eur = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    net_eur = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    reason_required_above_eur = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )
    reason_required = serializers.BooleanField(read_only=True)
    closing_role = serializers.CharField(read_only=True)
    closing_reason = serializers.CharField(read_only=True, allow_null=True)


class ConflitoDeContagemOutSerializer(serializers.Serializer):
    """O corpo de um 409: `code` para ramificar, `detail` para ler, `id` para navegar.

    O `id` é o que distingue este 409 de uma mensagem de erro: com ele o ecrã
    leva quem tentou abrir a segunda contagem até à que já está aberta.
    """

    code = serializers.CharField(read_only=True)
    detail = serializers.CharField(read_only=True)
    id = serializers.UUIDField(read_only=True, allow_null=True)


# ---------------------------------------------------------------------------
# Composição das respostas. Funções e não métodos de view: a view escolhe o
# serviço e o estado HTTP; a forma do que sai é desta camada.
# ---------------------------------------------------------------------------
def quantidade(valor: Decimal, *, produto: Any) -> dict[str, Any]:
    """Uma quantidade da unidade base para as duas formas que o cliente lê.

    `display_factor` é quantas unidades base cabem numa de apresentação (1 kg =
    1000 g), logo a de mostrar é a base **dividida** por ele. Dividir no cliente
    é o que o domínio proíbe, e é por isso que as duas viajam juntas.
    """
    factor = produto.display_factor or Decimal("1")
    return {
        "base": valor,
        "base_unit": produto.base_unit,
        "display": (valor / factor).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP),
        "display_unit": produto.display_unit,
    }


def em_unidade_base(valor: Decimal, *, produto: Any) -> Decimal:
    """O inverso do `quantidade()`: da unidade **de contagem** para a do ledger.

    Quem conta escreve "24" ao lado de um rótulo que diz `kg`, porque é esse o
    `count_unit` que a linha serve (`produto.display_unit`). O ledger guarda
    gramas. Sem esta multiplicação o `POST /lines` lia aqueles 24 como 24 g e o
    fecho gravava um `adjustment` de −24,976 kg — num ledger append-only, onde
    uma linha errada não se corrige, corrige-se com outra.

    Vive **ao lado do `quantidade()` e não no serviço**, de propósito: as duas
    direcções da mesma conversão são a mesma decisão, e o serviço fala sempre em
    unidade base (é o que os seus testes afirmam). O que esta camada faz é
    traduzir o contrato HTTP, que fala na unidade de quem conta.

    `produto` a `None` devolve o valor como veio: quem não existe é recusado
    pelo serviço com o 400 por campo, e não aqui com um `AttributeError`.

    O tecto é o da coluna, `Decimal(12,3)`, e é verificado **aqui** porque é aqui
    que o número cresce: o serializer valida 12 dígitos na unidade de contagem e
    a multiplicação por 1000 pode pô-los a 15. Sem esta linha, um valor absurdo
    saía como 500 do Postgres em vez de 400 por campo.
    """
    if produto is None:
        return valor
    factor = produto.display_factor or Decimal("1")
    em_base = (valor * factor).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
    if em_base > MAXIMO_DA_QUANTIDADE:
        raise serializers.ValidationError({"quantity": [DETALHE_QUANTIDADE_GRANDE]})
    return em_base


def zona_da_localizacao(localizacao: Any) -> dict[str, Any]:
    """A zona desta fatia: a localização contada, com o `slug` do nome.

    Um `slug` vazio (um nome só de símbolos) cai para o `id`, que é feio mas é
    único — e o `?zona=` compara strings, logo nunca pode ficar sem valor.
    """
    return {
        "slug": slugify(localizacao.name) or str(localizacao.id),
        "name": localizacao.name,
        "position": 0,
        "blind": False,
    }


def _progresso_de_zona(
    localizacao: Any, *, counted_lines: int, total_lines: int
) -> dict[str, Any]:
    """A zona com o progresso: é a contagem inteira, porque a zona é uma só."""
    return {
        **zona_da_localizacao(localizacao),
        "counted_lines": counted_lines,
        "total_lines": total_lines,
    }


def compor_contagem(
    contagem: Any, *, counted_lines: int, total_lines: int
) -> dict[str, Any]:
    """O cabeçalho de uma contagem, igual na lista e na resposta do `POST`.

    `current_zone` é a zona enquanto houver linhas por contar e `null` quando não
    houver — é o que o ecrã lê para saber onde está.
    """
    zona = _progresso_de_zona(
        contagem.location, counted_lines=counted_lines, total_lines=total_lines
    )
    return {
        "id": contagem.id,
        "location": {"id": contagem.location_id, "name": contagem.location.name},
        "status": contagem.status,
        "started_at": contagem.started_at,
        "closed_at": contagem.closed_at,
        "counted_lines": counted_lines,
        "total_lines": total_lines,
        "current_zone": zona if counted_lines < total_lines else None,
        "zones": [zona],
        "closing_role": str(ROTULO_DE_QUEM_FECHA),
        "closing_reason": contagem.closing_reason or None,
    }


def compor_linha(
    linha: Any, *, position: int, zona: dict[str, Any], difference_eur: Decimal | None
) -> dict[str, Any]:
    """Uma linha de contagem. `counted` a `null` é **por contar**, nunca zero.

    `difference` só existe quando há as duas pontas: sem observação não há
    diferença, e escrever zero ali era inventar uma.
    """
    produto = linha.product
    contado = linha.quantity_counted
    return {
        "id": linha.id,
        "product": linha.product_id,
        "short_name": produto.short_name,
        "zone": zona,
        "position": position,
        "count_unit": produto.display_unit,
        "expected": quantidade(linha.quantity_expected, produto=produto),
        "counted": None if contado is None else quantidade(contado, produto=produto),
        "difference": (
            None
            if contado is None
            else quantidade(contado - linha.quantity_expected, produto=produto)
        ),
        "difference_eur": difference_eur,
        "counted_by": linha.counted_by_name or None,
        "counted_at": linha.counted_at,
    }


def compor_fecho(previsto: Any) -> dict[str, Any]:
    """O corpo do `GET` e do `POST` de `/closing`, que é o mesmo nos dois.

    `differences` são só as linhas contadas **com** diferença, a maior em euros
    primeiro; `loss_eur` e `gain_eur` são os dois positivos e o `net_eur` é
    `ganho − perda`, com sinal.
    """
    contagem = previsto.contagem
    zona = zona_da_localizacao(contagem.location)
    posicoes = {linha.id: indice for indice, linha in enumerate(previsto.linhas)}
    com_diferenca = [
        linha
        for linha in previsto.linhas
        if linha.quantity_counted is not None
        and linha.quantity_counted != linha.quantity_expected
    ]
    com_diferenca.sort(
        key=lambda linha: (
            -abs(previsto.valor_por_linha.get(linha.id, Decimal("0"))),
            linha.product.short_name,
        )
    )
    return {
        "count": contagem.id,
        "status": contagem.status,
        "counted_lines": previsto.counted_lines,
        "total_lines": previsto.total_lines,
        "differences": [
            compor_linha(
                linha,
                position=posicoes[linha.id],
                zona=zona,
                difference_eur=previsto.valor_por_linha.get(linha.id, Decimal("0")),
            )
            for linha in com_diferenca
        ],
        "uncounted_lines": {
            "count": len(previsto.por_contar),
            "names": list(previsto.por_contar),
        },
        "loss_eur": previsto.loss_eur,
        "gain_eur": previsto.gain_eur,
        "net_eur": previsto.net_eur,
        "reason_required_above_eur": MOTIVO_OBRIGATORIO_ACIMA_DE_EUR,
        "reason_required": previsto.reason_required,
        "closing_role": str(ROTULO_DE_QUEM_FECHA),
        "closing_reason": contagem.closing_reason or None,
    }
