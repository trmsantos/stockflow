"""Serializers para o inventory (ADR 0021, fatia 2; ADR 0022; ADR 0030,
contagens; ADR 0034, os sete recursos de `/stock`).

Leitura e escrita em classes separadas, campos listados um a um.
Sem `fields = "__all__"` (CLAUDE.md, SECURITY.md §4).
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, ClassVar

from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from apps.accounts.api import SemEurosParaQuemNaoVe
from apps.inventory.count_services import (
    MOTIVO_OBRIGATORIO_ACIMA_DE_EUR,
    ROTULO_DE_QUEM_FECHA,
)
from apps.inventory.models import StockMovement
from apps.inventory.selectors import (
    CUSTO_CONHECIDO,
    CUSTO_DESCONHECIDO,
    CUSTO_ESTIMADO,
    ESTADOS_DO_CUSTO,
    ESTADOS_DO_NIVEL,
    GRAVIDADES,
    TIPOS_DE_VALIDADE,
    e_lote_sintetico,
)

#: O tecto da coluna `Decimal(12,3)` do `StockCountLine`, na unidade **base**.
#: Vive aqui e não no serviço porque é aqui que a conversão faz o número crescer.
MAXIMO_DA_QUANTIDADE = Decimal("999999999.999")

DETALHE_QUANTIDADE_GRANDE = _("This amount is too large for a count.")
DETALHE_UNIDADE_DESCONHECIDA = _(
    "Use the base unit or the display unit of this product."
)

#: As uniões fechadas do contrato, lidas **do modelo** e não copiadas à mão: o
#: `StockMovement` é o dono dos nove tipos e dos cinco motivos, e uma segunda
#: lista aqui divergia da primeira no dia em que uma delas crescesse.
TIPOS_DE_MOVIMENTO: tuple[str, ...] = tuple(
    codigo for codigo, _rotulo in StockMovement.MOVEMENT_TYPES
)
MOTIVOS_DE_MOVIMENTO: tuple[str, ...] = tuple(
    codigo for codigo, _rotulo in StockMovement.REASON_CHOICES
)

#: As duas razões por que uma linha está na lista de alertas — o vocabulário do
#: cliente (`motivoDeAlertaSchema`), e o mesmo que o `selectors` produz.
MOTIVOS_DE_ALERTA: tuple[str, str] = ("expiry", "missing")

__all__ = [
    "AjusteInSerializer",
    "AlertaOutSerializer",
    "DesperdicioOutSerializer",
    "LocalizacaoInSerializer",
    "LocalizacaoOutSerializer",
    "LocalizacaoPatchInSerializer",
    "MovimentoOutSerializer",
    "NivelDeStockOutSerializer",
    "NivelPorLocalizacaoOutSerializer",
    "QuebraInSerializer",
    "RespostaDeQuebraOutSerializer",
    "ResumoDeAlertasOutSerializer",
    "ResumoDeStockOutSerializer",
    "TransferenciaInSerializer",
    "ValidadeProximaOutSerializer",
    "StockMovementResponseSerializer",
    "StockTransferResponseSerializer",
    "MovimentoDeStockOutSerializer",
    "PernaDeTransferenciaOutSerializer",
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
    "compor_alerta",
    "compor_contagem",
    "compor_desperdicio",
    "compor_fecho",
    "compor_linha",
    "compor_movimento",
    "compor_movimento_do_ledger",
    "compor_nivel",
    "em_unidade_base",
    "em_unidade_pedida",
    "estado_do_custo",
    "quantidade",
    "quantidade_bruta",
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


# ===========================================================================
# As primitivas partilhadas. Vivem no topo porque **todas** as respostas deste
# módulo as compõem: uma quantidade é sempre um quarteto, uma localização é
# sempre `{id, name}`, e uma validade é sempre a data, os dias e a gravidade.
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


class LocalizacaoReferenciaSerializer(serializers.Serializer):
    """`{id, name}` — a localização como o cliente a lê em todo o lado."""

    id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(read_only=True)


class ValidadeProximaOutSerializer(serializers.Serializer):
    """O lote que vence primeiro, com a data, os dias e **a gravidade**.

    Três formas que mudaram com a ADR 0034 e que o cliente valida à chegada:

    * `expires_at` é uma **data** e não um instante (defeito (a)): um instante
      tem fuso e a data impressa na embalagem não muda com quem a lê;
    * `kind` é **nulável**: o `expiry_kind` do `catalog` é `""` por omissão e o
      `tipoValidadeSchema` do cliente não aceita `""`, logo traduz-se para
      `null` e a gravidade lê-se pela coluna estrita da tabela da decisão 9;
    * `lot_code` é **nulável**: um lote sintético (`__<uuid>__`) existe para o
      ledger ter uma chave e não para alguém o ler. Sem isto, a primeira
      produção de receita rebentava o ecrã de Alertas.

    A `severity` é nova e é o que fecha a quarta definição de gravidade: sem
    ela o cliente é **obrigado** a recalcular a cor para pintar o trilho (ADR
    0034, decisão 9). A palavra continua a ser dele, porque i18n é dele; a cor
    e a urgência passam a ser do servidor.
    """

    lot_id = serializers.UUIDField(read_only=True)
    lot_code = serializers.CharField(read_only=True, allow_null=True)
    expires_at = serializers.DateField(read_only=True)
    days_away = serializers.IntegerField(
        read_only=True, help_text="Dias até à validade; negativo se já passou."
    )
    kind = serializers.ChoiceField(
        choices=TIPOS_DE_VALIDADE,
        read_only=True,
        allow_null=True,
        help_text="`null` num artigo sem rótulo de validade.",
    )
    severity = serializers.ChoiceField(choices=GRAVIDADES, read_only=True)


# ===========================================================================
# Os sete recursos de `/stock` (ADR 0034). O dinheiro sai por papel, campo a
# campo, pelo `SemEurosParaQuemNaoVe` do `accounts.api` — **chave ausente**,
# nunca zero (uma afirmação falsa sobre o preço) e nunca `null` (que o ecrã
# imprime como "—", e isso é outro facto).
# ===========================================================================


class NivelPorLocalizacaoOutSerializer(serializers.Serializer):
    """Quanto deste artigo está em cada prateleira. Sem euros, de propósito.

    A repartição é **o produto**: é ela que responde a "onde está?" e é dela
    que o selector de loja do ecrã tira as opções. Localizações a zero não
    entram — uma loja sem nada deste artigo não é um sítio onde ele está.
    """

    location = LocalizacaoReferenciaSerializer(read_only=True)
    quantity = QuantidadeOutSerializer(read_only=True)


class NivelDeStockOutSerializer(SemEurosParaQuemNaoVe, serializers.Serializer):
    """Uma linha do `GET /stock/levels`: **um artigo**, somado sobre os lotes.

    Era o `/stock/summary` do servidor e mudou de casa na ADR 0034, decisão 1 —
    o caminho `/stock/summary` ficou livre para os quatro números do cliente. O
    grão de lote vivia no `by-location`/`by-product`, que morreram inteiros por
    não terem consumidor nenhum.

    ## O que sai por papel, e o que nunca sai

    `unit_cost` e `total_value` só vão a `owner|manager` (ADR 0032, decisão 1),
    e vão **os dois juntos**: um reconstrói o outro com a quantidade que já
    está no payload, logo esconder um só é teatro.

    O que fica para toda a gente: a quantidade (as quantidades são o produto),
    o mínimo, o estado, a validade mais próxima, a repartição, e a
    **cobertura** — `quantity_without_cost` é quantidade e não euro, e é o que
    diz se o valor está subestimado em 5 % ou em 95 %.

    A invariante da ADR 0032 continua a fechar ao cêntimo:
    `unit_cost × (quantity − quantity_without_cost) == total_value`, com as
    duas pontas do divisor servidas a quem não vê euros.

    ## `status` e `min_quantity` são **do estabelecimento**, também com `?loja=`

    O mínimo é por artigo (ADR 0024) e compará-lo contra o saldo de uma loja
    inventava faltas. O `?loja=` escopa só `quantity`, `by_location`,
    `nearest_expiry` e o valor. **O ecrã tem de escrever "mínimo do
    estabelecimento"**, senão "0,4 kg · ok" lê-se como erro de cálculo.
    """

    CAMPOS_DE_DINHEIRO: ClassVar[tuple[str, ...]] = ("unit_cost", "total_value")

    product = serializers.UUIDField(read_only=True)
    short_name = serializers.CharField(read_only=True)
    quantity = QuantidadeOutSerializer(read_only=True)
    min_quantity = QuantidadeOutSerializer(
        read_only=True, help_text="Do **artigo**, logo do estabelecimento inteiro."
    )
    status = serializers.ChoiceField(choices=ESTADOS_DO_NIVEL, read_only=True)
    by_location = NivelPorLocalizacaoOutSerializer(many=True, read_only=True)
    nearest_expiry = ValidadeProximaOutSerializer(read_only=True, allow_null=True)
    quantity_without_cost = QuantidadeOutSerializer(
        read_only=True,
        help_text=(
            "Quanta desta quantidade está em níveis sem preço registado. Zero "
            "é cobertura total; igual ao `quantity` é não haver preço nenhum."
        ),
    )
    unit_cost = serializers.DecimalField(
        max_digits=12,
        decimal_places=6,
        read_only=True,
        allow_null=True,
        help_text=(
            "Custo médio ponderado da quantidade **com** preço — nunca diluído "
            "pela parte sem preço. NULL quando nenhuma tem. Ausente para quem "
            "não vê euros."
        ),
    )
    total_value = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        read_only=True,
        help_text="Ausente para quem não vê euros.",
    )


class ResumoDeStockOutSerializer(SemEurosParaQuemNaoVe, serializers.Serializer):
    """Os quatro números do topo do ecrã de Stock (`GET /stock/summary`).

    `below_min_count` e `expiring_count` são, por construção, o `count` de
    `/stock/levels?filtro=falta` e de `?filtro=validade` no mesmo âmbito — ver
    `selectors.resumo_de_stock`. O `expiring_within_days` viaja com o número
    para o ecrã poder mostrar o limiar em vez de o esconder num painel de
    configurações.

    O `expiring_count` daqui conta **artigos**; o do `/stock/alerts/summary`
    conta **linhas da lista de alertas**. São dois factos com dois rótulos.
    """

    CAMPOS_DE_DINHEIRO: ClassVar[tuple[str, ...]] = ("stock_value_eur",)

    below_min_count = serializers.IntegerField(read_only=True)
    expiring_count = serializers.IntegerField(read_only=True)
    expiring_within_days = serializers.IntegerField(read_only=True)
    stock_value_eur = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        read_only=True,
        help_text=(
            "Σ do valor dos artigos com saldo positivo — um saldo negativo não "
            "baixa o valor do stock. Ausente para quem não vê euros."
        ),
    )


class MovimentoOutSerializer(SemEurosParaQuemNaoVe, serializers.Serializer):
    """Uma linha do ledger: `GET /stock/movements` e o 201 da quebra.

    **A mesma forma nas duas portas**, de propósito: o que o 201 devolve é o
    que a lista vai mostrar a seguir, e duas formas do mesmo facto são duas
    oportunidades de divergirem.

    `quantity` vem **com sinal** — entradas positivas, saídas negativas —,
    porque aqui a linha é o ledger e o sinal é o facto. (Na lista de
    desperdício vem positiva: lá a pergunta é "quanto se perdeu".)

    `unit_cost` só sai a `owner|manager`, e vem `null` quando o custo é
    desconhecido: zero não é um preço de zero euros (ADR 0024, decisão 5).

    ## Os dois campos novos da referência, e o uuid que o ecrã não imprime

    O `reference` de um ajuste de fecho é o **id cru da contagem** e o ecrã
    dizia "texto curto, para mostrar". Não se muda o que se grava — há um
    índice parcial e dois lookups por essa string —, servem-se
    `reference_kind` e `reference_label`, e o ecrã imprime o rótulo. O que vier
    de fora deste módulo fica sem rótulo, e sem rótulo o ecrã não imprime nada.
    """

    CAMPOS_DE_DINHEIRO: ClassVar[tuple[str, ...]] = ("unit_cost",)

    id = serializers.UUIDField(read_only=True)
    movement_type = serializers.ChoiceField(choices=TIPOS_DE_MOVIMENTO, read_only=True)
    quantity = QuantidadeOutSerializer(read_only=True)
    location = LocalizacaoReferenciaSerializer(read_only=True)
    lot_code = serializers.CharField(
        read_only=True, allow_null=True, help_text="`null` num lote sintético."
    )
    reason = serializers.ChoiceField(
        choices=MOTIVOS_DE_MOVIMENTO,
        read_only=True,
        allow_blank=True,
        help_text="`\"\"` quando o movimento não tem motivo.",
    )
    created_by = serializers.CharField(
        read_only=True,
        allow_null=True,
        help_text=(
            "O `display_name` da pertença, nunca o email. `null` quando quem "
            "agiu já não tem nome aqui."
        ),
    )
    occurred_at = serializers.DateTimeField(read_only=True)
    reference = serializers.CharField(read_only=True, allow_null=True)
    reference_kind = serializers.CharField(read_only=True, allow_null=True)
    reference_label = serializers.CharField(read_only=True, allow_null=True)
    cost_status = serializers.ChoiceField(choices=ESTADOS_DO_CUSTO, read_only=True)
    unit_cost = serializers.DecimalField(
        max_digits=12,
        decimal_places=6,
        read_only=True,
        allow_null=True,
        help_text="Ausente para quem não vê euros.",
    )


class RespostaDeQuebraOutSerializer(serializers.Serializer):
    """O 201 de `POST /stock/movements/waste`: **sempre uma lista**.

    Mesmo com um lote só. Uma resposta que é objecto no caso normal e lista no
    caso raro é um cliente que funciona até ao dia em que o lote acaba a meio
    (ADR 0034, decisão 8) — e é a forma que o 201 da transferência já tem.

    Sem mixin próprio: o dinheiro está nas linhas, e o `context` chega-lhes
    pelo `root`.
    """

    movements = MovimentoOutSerializer(many=True, read_only=True)


class AlertaOutSerializer(SemEurosParaQuemNaoVe, serializers.Serializer):
    """Uma linha do `GET /stock/alerts`: duas perguntas, **uma** lista.

    O `id` não é um uuid: é `expiry:<lot_id>:<location_id>` ou
    `missing:<product_id>`. A localização entra na chave porque um lote
    transferido tem saldo em duas prateleiras e `expiry:<lot_id>` produzia
    **dois ids iguais** — o painel expandia a linha errada. Agregar por lote
    não era alternativa: o `location` passava a `null` e o `POST` de quebra da
    linha levaria `""`, que é 400.

    `value_eur` só vai a `owner|manager`. Num alerta de validade é o valor em
    risco; num de falta é o que custa voltar ao mínimo — e o ecrã diz qual dos
    dois é. O `cost_status` fica para todos: é qualidade de dados e não um euro.
    """

    CAMPOS_DE_DINHEIRO: ClassVar[tuple[str, ...]] = ("value_eur",)

    id = serializers.CharField(read_only=True)
    product = serializers.UUIDField(read_only=True)
    short_name = serializers.CharField(read_only=True)
    reason = serializers.ChoiceField(choices=MOTIVOS_DE_ALERTA, read_only=True)
    severity = serializers.ChoiceField(choices=GRAVIDADES, read_only=True)
    location = LocalizacaoReferenciaSerializer(
        read_only=True,
        allow_null=True,
        help_text="`null` numa falta: o mínimo é do artigo e vale sobre o consolidado.",
    )
    quantity = QuantidadeOutSerializer(read_only=True)
    lot = ValidadeProximaOutSerializer(read_only=True, allow_null=True)
    threshold_days = serializers.IntegerField(read_only=True, allow_null=True)
    min_quantity = QuantidadeOutSerializer(read_only=True, allow_null=True)
    cost_status = serializers.ChoiceField(choices=ESTADOS_DO_CUSTO, read_only=True)
    value_eur = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True,
        help_text="Ausente para quem não vê euros.",
    )


class ResumoDeAlertasOutSerializer(SemEurosParaQuemNaoVe, serializers.Serializer):
    """Os contadores do topo do ecrã de Alertas (`GET /stock/alerts/summary`).

    Endpoint e não derivação da lista (ADR 0034, decisão 5): a lista vem
    paginada a 50 e os dois agregados do desperdício são janelas de dia de
    negócio que a lista de alertas não contém.

    ## O `staff` perde dois euros e ganha quatro contagens

    `wasted_today_eur` e `wasted_week_eur` continuam ausentes para quem não vê
    euros. Em troca, `wasted_*_count` e `wasted_*_lines_without_cost` estão
    **presentes para os três papéis** — são contagens e não euros, e um
    `COUNT(id)` não tem numerador nem denominador, logo nenhuma sequência de
    observações reconstrói um custo unitário a partir dele (ADR 0034, d10).

    A razão é de **navegação**: os dois números em euros eram as duas únicas
    portas para a lista de desperdício, e a decisão 4 diz expressamente que
    essa lista tem de chegar ao `staff`. Sem contador, a rota existia sem ter
    quem lá entrasse.

    A cobertura entra pela régua da ADR 0032: "7 quebras hoje" e "7 quebras
    hoje, 4 sem preço conhecido" não são a mesma frase.
    """

    CAMPOS_DE_DINHEIRO: ClassVar[tuple[str, ...]] = (
        "wasted_today_eur",
        "wasted_week_eur",
    )

    expiring_count = serializers.IntegerField(
        read_only=True, help_text="Linhas da lista de alertas de validade."
    )
    expiring_within_days = serializers.IntegerField(read_only=True)
    missing_count = serializers.IntegerField(read_only=True)
    business_day_starts_at = serializers.CharField(
        read_only=True, help_text='`"04:00"`, hora local do estabelecimento.'
    )
    wasted_since = serializers.DateTimeField(read_only=True)
    wasted_today_eur = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True,
        help_text="Ausente para quem não vê euros.",
    )
    wasted_week_eur = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True,
        help_text="Ausente para quem não vê euros.",
    )
    wasted_today_count = serializers.IntegerField(read_only=True)
    wasted_week_count = serializers.IntegerField(read_only=True)
    wasted_today_lines_without_cost = serializers.IntegerField(read_only=True)
    wasted_week_lines_without_cost = serializers.IntegerField(read_only=True)


class DesperdicioOutSerializer(SemEurosParaQuemNaoVe, serializers.Serializer):
    """Uma linha do `GET /stock/alerts/waste`: o que se deitou fora, e quem.

    É do `inventory` e não do `reporting`, e a fronteira está escrita: *o
    `reporting` agrega o negócio num período e é do dono; o `inventory` lista o
    ledger para quem age sobre ele* (ADR 0034, decisão 4). Esta lista fica ao
    lado do botão que a cria e tem de chegar ao `staff` — por isso o que lhe
    falta é só o `value_eur`.

    `quantity` vem **positiva**: o sinal do ledger já foi lido, e "perdeste −2
    kg" não é uma frase.
    """

    CAMPOS_DE_DINHEIRO: ClassVar[tuple[str, ...]] = ("value_eur",)

    id = serializers.UUIDField(read_only=True)
    product = serializers.UUIDField(read_only=True)
    short_name = serializers.CharField(read_only=True)
    lot_code = serializers.CharField(read_only=True, allow_null=True)
    quantity = QuantidadeOutSerializer(read_only=True)
    reason = serializers.ChoiceField(
        choices=MOTIVOS_DE_MOVIMENTO, read_only=True, allow_blank=True
    )
    location = LocalizacaoReferenciaSerializer(read_only=True)
    created_by = serializers.CharField(read_only=True, allow_null=True)
    occurred_at = serializers.DateTimeField(read_only=True)
    cost_status = serializers.ChoiceField(choices=ESTADOS_DO_CUSTO, read_only=True)
    value_eur = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True,
        help_text="Ausente para quem não vê euros.",
    )


# ---------------------------------------------------------------------------
# Os corpos de entrada dos três `POST /stock/movements/*`.
#
# **Sem os sufixos `_id`**, nos três e não só na quebra: duas convenções no
# mesmo ViewSet é como se escreve o 400 seguinte (ADR 0034). Os nomes são os
# que o cliente já envia — `product`, `location`, `lot`, `from_location`,
# `to_location` — e as mensagens de recusa do serviço nomeiam os mesmos campos.
# ---------------------------------------------------------------------------


class QuebraInSerializer(serializers.Serializer):
    """`POST /stock/movements/waste`: o que se perdeu, onde, e em que unidade.

    ## O `unit` é obrigatório, e isso fechou um buraco medido

    A versão aprovada da ADR 0034 escrevia *"quantity: Decimal>0 (unidade
    BASE)"* contra um formulário que apresenta a **unidade mostrada** ao lado
    do campo e só normaliza a vírgula decimal. Entre `g` e `kg` há um factor de
    1000, o destino é um ledger append-only (ADR 0006: sem `UPDATE`, sem
    `DELETE`) e o erro não tem botão de desfazer. Um número sem unidade
    explícita num corpo de escrita é uma convenção, e convenções não sobrevivem
    a dois ecrãs (decisão 11).

    A unidade tem de ser a **base** ou a de **apresentação daquele artigo** —
    qualquer outra é 400, e não existe motor genérico de conversão (ADR 0011).
    A conversão é do servidor, nunca do cliente.

    ## O `lot` é opcional, e omiti-lo é o caso normal

    Sem lote, o servidor escolhe por FEFO na localização pedida e reparte por
    quantos forem precisos. Com lote — o caso do ecrã de Alertas, onde o alerta
    **é** sobre um lote —, sai tudo desse. O campo era `lot_code` e passou a
    `lot`: um código não é chave e obrigava o servidor a resolvê-lo.
    """

    product = serializers.UUIDField(help_text="UUID do artigo")
    location = serializers.UUIDField(help_text="UUID da localização")
    quantity = serializers.DecimalField(
        max_digits=12,
        decimal_places=3,
        min_value=Decimal("0.001"),
        help_text="Quantidade > 0, na unidade de `unit`.",
    )
    unit = serializers.CharField(
        max_length=20,
        help_text="`base_unit` ou `display_unit` **daquele artigo**. Outra é 400.",
    )
    reason = serializers.ChoiceField(choices=MOTIVOS_DE_MOVIMENTO)
    lot = serializers.UUIDField(
        required=False,
        allow_null=True,
        help_text="Omitido, o servidor escolhe por FEFO na localização pedida.",
    )
    reason_detail = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=500,
        help_text="Texto livre que acompanha o motivo.",
    )


class AjusteInSerializer(serializers.Serializer):
    """`POST /stock/movements/adjustment`: a correcção, com sinal.

    A quantidade continua a ser em unidade **base**: a decisão 11 da ADR 0034
    deu o `unit` à quebra, que é a que o ecrã serve, e esta rota não tem ecrã
    nenhum nesta fatia. Está nomeado aqui para a assimetria ser visível a quem
    lhe der um.
    """

    product = serializers.UUIDField(help_text="UUID do artigo")
    location = serializers.UUIDField(help_text="UUID da localização")
    quantity = serializers.DecimalField(
        max_digits=12,
        decimal_places=3,
        help_text="Quantidade ± em unidade base (positivo = entrada).",
    )
    lot = serializers.UUIDField(required=False, allow_null=True)
    reason = serializers.ChoiceField(choices=MOTIVOS_DE_MOVIMENTO)
    reason_detail = serializers.CharField(
        required=False, allow_blank=True, max_length=500
    )

    def validate_quantity(self, value):
        """Quantidade não pode ser zero: um ajuste de nada não é um ajuste."""
        if value == Decimal("0"):
            raise serializers.ValidationError(_("Quantity cannot be zero."))
        return value


class TransferenciaInSerializer(serializers.Serializer):
    """`POST /stock/movements/transfer`: de onde, para onde, quanto.

    Quantidade em unidade **base**, pela mesma razão do `AjusteInSerializer`.
    """

    product = serializers.UUIDField(help_text="UUID do artigo")
    from_location = serializers.UUIDField(help_text="UUID da localização de origem")
    to_location = serializers.UUIDField(help_text="UUID da localização de destino")
    quantity = serializers.DecimalField(
        max_digits=12,
        decimal_places=3,
        min_value=Decimal("0.001"),
        help_text="Quantidade > 0 em unidade base.",
    )
    lot = serializers.UUIDField(required=False, allow_null=True)


class MovimentoDeStockOutSerializer(SemEurosParaQuemNaoVe, serializers.Serializer):
    """A parte comum dos 201 de `stock/movements/*`: o que o movimento escreveu.

    **`unit_cost` só sai a `owner|manager`** (ADR 0032). O resto é trabalho de
    campo e fica: que artigo, onde, que lote e quanto — o cliente precisa deles
    para desenhar a confirmação, e nenhum deles diz um preço.

    `cost_status` lê o `cost_is_estimate` do movimento, que é o campo certo para
    a pergunta — mas os três serviços manuais gravam-no sempre a `False`, porque
    lêem o custo do **nível** e um nível não guarda a proveniência do preço. A
    dívida está escrita por extenso no `ESTADOS_DO_CUSTO`; o que importa é que
    `estimado` é a palavra que lá estará, e não uma quarta inventada nesse dia.
    """

    CAMPOS_DE_DINHEIRO: ClassVar[tuple[str, ...]] = ("unit_cost",)

    movement_id = serializers.UUIDField(read_only=True)
    product_name = serializers.CharField(read_only=True)
    location_name = serializers.CharField(read_only=True)
    lot_code = serializers.CharField(read_only=True, allow_null=True)
    quantity = serializers.DecimalField(
        max_digits=12,
        decimal_places=3,
        read_only=True,
    )
    cost_status = serializers.ChoiceField(
        choices=ESTADOS_DO_CUSTO,
        read_only=True,
        help_text="Qualidade do custo com que o movimento foi avaliado.",
    )
    unit_cost = serializers.DecimalField(
        max_digits=12,
        decimal_places=6,
        read_only=True,
        help_text="Ausente para quem não vê euros.",
    )


class StockMovementResponseSerializer(MovimentoDeStockOutSerializer):
    """O 201 de `POST /stock/movements/{waste,adjustment}`.

    Até 2026-10-21 este serializer **não serializava nada**: estava declarado no
    `extend_schema` e a view devolvia um `dict` montado à mão, logo o contrato
    descrevia uma resposta que ninguém produzia e nenhum mixin lhe chegava (ADR
    0032, decisão 4). Agora a resposta passa por aqui.
    """

    created_at = serializers.DateTimeField(read_only=True)


class PernaDeTransferenciaOutSerializer(MovimentoDeStockOutSerializer):
    """Uma das duas pernas de uma transferência: a saída e a entrada.

    `type` diz qual é (`transfer_out` / `transfer_in`), e as duas trazem a
    localização **de cada uma** — é o par que conta a história, e é por isso que
    o `unit_cost` tinha de desaparecer nas **duas**: escondê-lo só numa delas
    dava o mesmo número pelo outro lado.
    """

    type = serializers.ChoiceField(
        choices=["transfer_out", "transfer_in"],
        read_only=True,
    )


class StockTransferResponseSerializer(serializers.Serializer):
    """O 201 de `POST /stock/movements/transfer` — e é novo porque **não existia**.

    O `extend_schema` desta rota apontava para o `StockMovementResponseSerializer`,
    que descreve **um** movimento: o schema prometia `movement_id` e
    `product_name` no topo e o corpo que sai tem `transfer_id` e `movements`. O
    cliente gerado estava errado desde que a rota nasceu (ADR 0025) e ninguém
    reparou porque nada serializava a resposta (ADR 0032, decisão 4).

    Sem mixin próprio: o dinheiro está nas pernas, e o `context` chega-lhes pelo
    `root` — é o serializer de topo que tem de ser instanciado com ele.
    """

    transfer_id = serializers.UUIDField(read_only=True, allow_null=True)
    movements = PernaDeTransferenciaOutSerializer(many=True, read_only=True)
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


class LinhaDeContagemOutSerializer(SemEurosParaQuemNaoVe, serializers.Serializer):
    """Uma linha: o que o sistema diz, o que se contou e a diferença.

    **`difference_eur` passou de `null` a ausente** a 2026-10-21 (ADR 0032,
    decisão 5). A ADR 0030 escolhera `null` e nomeara o preço: *"`null` passa a
    dizer duas coisas — ainda não contado e não te é mostrado"*. A chave ausente
    diz a segunda sem apagar a primeira — `difference` presente com
    `difference_eur` ausente é inequívoco — e é a forma que o resto do sistema
    já usa, incluindo o módulo ao lado. Duas formas da mesma política dentro do
    mesmo módulo era o que a decisão 4 desta ADR acabara de desfazer.

    O que o colaborador continua a receber: a lista inteira, o esperado, o
    contado, a diferença em quantidade, quem contou e quando.
    """

    CAMPOS_DE_DINHEIRO: ClassVar[tuple[str, ...]] = ("difference_eur",)

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
    """O fecho: as diferenças em quantidade e em euros, antes e depois de escrever.

    ## Sem mixin, e isso é uma decisão: aqui o **recurso** é dinheiro

    As duas rotas de `/closing` são de `owner|manager` em `permission_classes` —
    é a assimetria da ADR 0030 — e esses são exactamente os
    `PAPEIS_QUE_VEEM_EUROS`. Quem não vê euros leva 403 antes de este serializer
    correr, logo não há payload a filtrar. O teste
    `test_o_limiar_do_fecho_nao_chega_a_quem_nao_ve_euros` prende as duas listas
    uma à outra e falha no dia em que alguém alargar a rota.

    **Porque é que isto importa, e não é só o `loss_eur`:** o
    `reason_required_above_eur` é hoje `0` e o `reason_required` é por isso
    sempre `True` — um par morto, que não informa nada. Com um limiar ≠ 0 e
    estes dois campos à vista de quem conta, **cada linha passa a limitar um
    custo**: "esta contagem exigiu justificação" é "a diferença vale mais de X
    €", e repetido artigo a artigo é uma busca binária sobre o preço sem nenhuma
    chave de dinheiro no payload. Se um dia o fecho se abrir a quem conta, o
    limiar e a bandeira têm de sair com os euros — não são metadados de
    configuração, são o euro por outro nome.
    """

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
def estado_do_custo(*, unit_cost: Decimal, estimado: bool) -> str:
    """As três palavras do custo, lidas de um **movimento**.

    Zero é "preço desconhecido" (ADR 0024, decisão 5, caso 3) e ganha a tudo: um
    custo estimado de zero continua a ser um custo que ninguém sabe. Fora disso
    manda o `cost_is_estimate` do ledger — guia de remessa sem fatura é
    `estimado`, fatura conferida é `conhecido` (ADR 0023).

    As palavras vêm do `selectors.ESTADOS_DO_CUSTO`, que é o sítio onde se
    explica porque são estas três e não uma quarta.
    """
    if Decimal(unit_cost) == 0:
        return CUSTO_DESCONHECIDO
    return CUSTO_ESTIMADO if estimado else CUSTO_CONHECIDO


def compor_movimento(movimento: Any) -> dict[str, Any]:
    """Um movimento como os 201 de `stock/movements/*` o mostram.

    A quantidade sai **positiva**: uma saída está no ledger a negativo porque é
    uma saída, e "perdeste −2 kg" não é uma frase (é a mesma leitura de sinal do
    `desperdicio_por_artigo_e_motivo`). O sinal lê-se aqui, uma vez — e antes
    disto cada uma das três rotas o lia à sua maneira, com a perna de entrada da
    transferência a ser a única sem o `abs()`.

    O `unit_cost` vem **sempre** daqui; quem o tira é o mixin, no serializer.
    """
    return {
        "movement_id": movimento.id,
        "product_name": movimento.product.short_name,
        "location_name": movimento.location.name,
        "lot_code": movimento.lot.code if movimento.lot else None,
        "quantity": abs(movimento.quantity),
        "cost_status": estado_do_custo(
            unit_cost=movimento.unit_cost, estimado=movimento.cost_is_estimate
        ),
        "unit_cost": movimento.unit_cost,
    }


def quantidade_bruta(
    valor: Decimal, *, base_unit: str, display_unit: str, display_factor: Decimal | None
) -> dict[str, Any]:
    """O quarteto, a partir das três colunas soltas em vez de um objecto.

    Existe porque os selectors do painel devolvem linhas de `values()` e não
    instâncias: o trio que converte vem como três chaves, e materializar um
    `Product` por linha só para ler três atributos era uma query por artigo.
    O `quantidade()` daqui ao lado é a mesma função com um objecto à frente.
    """
    factor = display_factor or Decimal("1")
    return {
        "base": valor,
        "base_unit": base_unit,
        "display": (valor / factor).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP),
        "display_unit": display_unit,
    }


def quantidade(valor: Decimal, *, produto: Any) -> dict[str, Any]:
    """Uma quantidade da unidade base para as duas formas que o cliente lê.

    `display_factor` é quantas unidades base cabem numa de apresentação (1 kg =
    1000 g), logo a de mostrar é a base **dividida** por ele. Dividir no cliente
    é o que o domínio proíbe, e é por isso que as duas viajam juntas.
    """
    return quantidade_bruta(
        valor,
        base_unit=produto.base_unit,
        display_unit=produto.display_unit,
        display_factor=produto.display_factor,
    )


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
    contagem: Any, *, counted_lines: int, total_lines: int, ve_euros: bool = True
) -> dict[str, Any]:
    """O cabeçalho de uma contagem, igual na lista e na resposta do `POST`.

    `current_zone` é a zona enquanto houver linhas por contar e `null` quando não
    houver — é o que o ecrã lê para saber onde está.

    O `closing_reason` só sai a quem **vê euros**. É texto livre escrito por
    quem fechou, e na prática cita o valor ("faltaram 750 g, 0,90 €") — o mesmo
    euro que o `difference_eur` nega ao colaborador. Esconder a diferença e
    deixar passar a frase que a descreve era uma fronteira a fingir (revisão de
    segurança de 2026-10-19, decisão do dono no mesmo dia). O que o colaborador
    continua a ver: que a contagem foi fechada, quando, e por quem.
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
        "closing_reason": (contagem.closing_reason or None) if ve_euros else None,
    }


def compor_linha(
    linha: Any,
    *,
    position: int,
    zona: dict[str, Any],
    difference_eur: Decimal | None,
    esperado: Decimal | None = None,
) -> dict[str, Any]:
    """Uma linha de contagem. `counted` a `null` é **por contar**, nunca zero.

    `difference` só existe quando há as duas pontas: sem observação não há
    diferença, e escrever zero ali era inventar uma.

    O `esperado` é um **recurso e não um valor por omissão**: sem ele mostra-se
    o `quantity_expected` da linha, que é o número que esteve à frente de quem
    contou. O `GET /closing` de uma contagem aberta passa a base do cut-off
    (ADR 0033), porque aí a pergunta é outra — "contra que número é que isto vai
    ser escrito no ledger" — e as duas só divergem quando um documento entra
    depois de se contar com data anterior. Mostrar o esperado da linha nesse
    caso era a pré-visualização a dizer `+10` e o fecho a escrever `−10`, e a
    ADR 0030, decisão 5, promete que o `GET` **é** a decisão.
    """
    produto = linha.product
    contado = linha.quantity_counted
    base = linha.quantity_expected if esperado is None else esperado
    return {
        "id": linha.id,
        "product": linha.product_id,
        "short_name": produto.short_name,
        "zone": zona,
        "position": position,
        "count_unit": produto.display_unit,
        "expected": quantidade(base, produto=produto),
        "counted": None if contado is None else quantidade(contado, produto=produto),
        "difference": (
            None if contado is None else quantidade(contado - base, produto=produto)
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

    "Com diferença" mede-se contra a base do **plano** (`base_por_linha`, o
    cut-off da ADR 0033) e não contra o `quantity_expected`: é o plano que o
    `POST` executa, e uma linha que vai gerar movimento tem de aparecer aqui.
    Numa contagem já fechada o plano não se recalcula e o mapa vem vazio — aí a
    base é o esperado da linha, que é o que ficou escrito.
    """
    contagem = previsto.contagem
    zona = zona_da_localizacao(contagem.location)
    posicoes = {linha.id: indice for indice, linha in enumerate(previsto.linhas)}

    def base_de(linha: Any) -> Decimal:
        return previsto.base_por_linha.get(linha.id, linha.quantity_expected)

    com_diferenca = [
        linha
        for linha in previsto.linhas
        if linha.quantity_counted is not None
        and linha.quantity_counted != base_de(linha)
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
                esperado=base_de(linha),
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


# ---------------------------------------------------------------------------
# Composição dos sete recursos de `/stock` (ADR 0034).
#
# Os selectors devolvem linhas com quantidades em unidade base e o trio que as
# converte; estas funções transformam-nas na forma do contrato. A fronteira é a
# mesma de sempre: o selector não sabe o que é um quarteto de quantidade, e o
# serializer não sabe fazer uma query.
# ---------------------------------------------------------------------------
def em_unidade_pedida(valor: Decimal, *, unidade: str, produto: Any) -> Decimal:
    """Converte `valor` da unidade pedida para a do ledger. Outra unidade é 400.

    A unidade tem de ser o `base_unit` ou o `display_unit` **daquele artigo**:
    não existe motor genérico de conversão (ADR 0011) e inventar um aqui era
    aceitar "l" num artigo que se conta às unidades. A conversão é do servidor,
    nunca do cliente (ADR 0030, decisão 1, e `inventory-domain` §2).

    O tecto da coluna é verificado **aqui**, porque é aqui que o número cresce:
    o serializer valida 12 dígitos na unidade de quem escreve e a multiplicação
    pode pô-los a 15.
    """
    if produto is None:
        return valor
    if unidade == produto.base_unit:
        em_base = valor
    elif unidade == produto.display_unit:
        factor = produto.display_factor or Decimal("1")
        em_base = (valor * factor).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
    else:
        raise serializers.ValidationError({"unit": [DETALHE_UNIDADE_DESCONHECIDA]})
    if em_base > MAXIMO_DA_QUANTIDADE:
        raise serializers.ValidationError({"quantity": [DETALHE_QUANTIDADE_GRANDE]})
    return em_base


def _unidades(linha: dict[str, Any]) -> dict[str, Any]:
    """As três chaves que o `quantidade_bruta` precisa, tiradas de uma linha."""
    return {
        "base_unit": linha["base_unit"],
        "display_unit": linha["display_unit"],
        "display_factor": linha["display_factor"],
    }


def compor_nivel(linha: dict[str, Any]) -> dict[str, Any]:
    """Uma linha do `GET /stock/levels`, do selector para o contrato."""
    unidades = _unidades(linha)
    return {
        "product": linha["product"],
        "short_name": linha["short_name"],
        "quantity": quantidade_bruta(linha["quantidade"], **unidades),
        "min_quantity": quantidade_bruta(linha["min_quantity"], **unidades),
        "status": linha["status"],
        "by_location": [
            {
                "location": {
                    "id": parcela["location_id"],
                    "name": parcela["location_name"],
                },
                "quantity": quantidade_bruta(parcela["quantidade"], **unidades),
            }
            for parcela in linha["by_location"]
        ],
        "nearest_expiry": linha["nearest_expiry"],
        "quantity_without_cost": quantidade_bruta(
            linha["quantity_without_cost"], **unidades
        ),
        "unit_cost": linha["unit_cost"],
        "total_value": linha["total_value"],
    }


def compor_alerta(alerta: dict[str, Any]) -> dict[str, Any]:
    """Uma linha do `GET /stock/alerts`, do selector para o contrato."""
    unidades = _unidades(alerta)
    localizacao = None
    if alerta["location_id"] is not None:
        localizacao = {
            "id": alerta["location_id"],
            "name": alerta["location_name"],
        }
    minimo = alerta["min_quantity"]
    return {
        "id": alerta["id"],
        "product": alerta["product"],
        "short_name": alerta["short_name"],
        "reason": alerta["reason"],
        "severity": alerta["severity"],
        "location": localizacao,
        "quantity": quantidade_bruta(alerta["quantidade"], **unidades),
        "lot": alerta["lot"],
        "threshold_days": alerta["threshold_days"],
        "min_quantity": (
            None if minimo is None else quantidade_bruta(minimo, **unidades)
        ),
        "cost_status": alerta["cost_status"],
        "value_eur": alerta["value_eur"],
    }


def _custo_do_movimento(movimento: Any) -> Decimal | None:
    """O custo de uma linha do ledger, ou `None` quando é desconhecido.

    Zero é "preço desconhecido" por convenção da casa (ADR 0024, decisão 5,
    caso 3) e servi-lo como `0,000000` era uma afirmação sobre o preço. A
    palavra ao lado (`cost_status`) diz a mesma coisa por extenso.
    """
    return movimento.unit_cost if movimento.unit_cost else None


def compor_movimento_do_ledger(
    movimento: Any, *, rotulos: Mapping[str, tuple[str, str]] | None = None
) -> dict[str, Any]:
    """Uma linha do `GET /stock/movements` e do 201 da quebra.

    A quantidade vai **com sinal**: aqui a linha é o ledger, e o sinal é o
    facto. O `reference` vai cru (há quem o deduplique por ele) com o par
    `reference_kind`/`reference_label` ao lado, que é o que o ecrã imprime.
    """
    tipo, rotulo = (rotulos or {}).get(movimento.reference, (None, None))
    return {
        "id": movimento.id,
        "movement_type": movimento.movement_type,
        "quantity": quantidade(movimento.quantity, produto=movimento.product),
        "location": {"id": movimento.location_id, "name": movimento.location.name},
        "lot_code": _codigo_de_lote(movimento),
        "reason": movimento.reason,
        "created_by": movimento.created_by_name or None,
        "occurred_at": movimento.occurred_at,
        "reference": movimento.reference or None,
        "reference_kind": tipo,
        "reference_label": rotulo,
        "cost_status": estado_do_custo(
            unit_cost=movimento.unit_cost, estimado=movimento.cost_is_estimate
        ),
        "unit_cost": _custo_do_movimento(movimento),
    }


def _codigo_de_lote(movimento: Any) -> str | None:
    """O código do lote, ou `None` num sintético. Quem o mostra diz "sem lote"."""
    if movimento.lot is None or e_lote_sintetico(movimento.lot.code):
        return None
    return movimento.lot.code


def compor_desperdicio(movimento: Any) -> dict[str, Any]:
    """Uma linha do `GET /stock/alerts/waste`.

    A quantidade e o valor vêm **positivos**: uma quebra está no ledger a
    negativo porque é uma saída, e aqui a pergunta é "quanto se perdeu". É a
    mesma leitura de sinal do `desperdicio_por_artigo_e_motivo`.
    """
    return {
        "id": movimento.id,
        "product": movimento.product_id,
        "short_name": movimento.product.short_name,
        "lot_code": _codigo_de_lote(movimento),
        "quantity": quantidade(abs(movimento.quantity), produto=movimento.product),
        "reason": movimento.reason,
        "location": {"id": movimento.location_id, "name": movimento.location.name},
        "created_by": movimento.created_by_name or None,
        "occurred_at": movimento.occurred_at,
        "cost_status": estado_do_custo(
            unit_cost=movimento.unit_cost, estimado=movimento.cost_is_estimate
        ),
        "value_eur": abs(movimento.quantity * movimento.unit_cost).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        ),
    }
