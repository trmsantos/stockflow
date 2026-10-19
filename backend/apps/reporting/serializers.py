"""Os três payloads do painel. **Só saída** — este módulo não recebe corpo nenhum.

Os nomes dos campos são os da ADR 0013 decisão 5, letra por letra, porque o
cliente já está escrito contra eles (`frontend/src/features/reporting/`). Duas
convenções que vêm da ADR e não do DRF:

* **dinheiro é `string`** (`DecimalField`, `COERCE_DECIMAL_TO_STRING`), porque
  nenhuma conta se faz em `number` no cliente. É também por isso que o `share`
  e o `scale_max_eur` existem: com eles a única aritmética do SVG é
  `share × píxeis`;
* **nenhum rótulo viaja no arame.** O servidor manda ids de uniões fechadas
  (`ChoiceField`, que entram no `schema.yml` como enum e no `types.ts` como
  união) e as palavras vivem no `vocabulario.ts` da feature, onde o `Record`
  sobre a união falha nos dois sentidos.

E uma que vem da ADR 0029: **o que não se sabe é `null` e nunca `"0.00"`.** Um
zero em euros é um facto e o painel desenha-o; `null` é a palavra "não sei". O
porquê viaja uma vez, no `unavailable` do bloco de qualidade.
"""

from __future__ import annotations

from rest_framework import serializers

__all__ = [
    "FechoDoMesOutSerializer",
    "RecusaDoPainelOutSerializer",
    "ResumoDoPeriodoOutSerializer",
    "SeriesDoPeriodoOutSerializer",
]

#: As uniões fechadas do contrato. Listas e não enums importados: o `reporting`
#: só pode importar `api.py`s (ARCHITECTURE.md §3), e nenhuma destas uniões
#: pertence a outro módulo — são do painel.
PERIODOS = ["today", "7d", "30d", "month", "prev_month"]
IDS_DE_CUSTO = ["purchases", "goods_consumed", "waste", "unknown_shrinkage", "payroll", "other"]
IDS_DE_SERIE = ["revenue", "purchases"]
IDS_DE_PARTE_DE_SALARIOS = [
    "base",
    "social_security",
    "subsidies",
    "meal_allowance",
    "insurance",
]
MOTIVOS_DE_QUEBRA = ["expired", "spoiled", "prep_loss", "breakage", "other"]
ORIGENS_DA_RECEITA = ["none", "manual", "pos"]
BASES_DA_RECEITA = ["gross", "net"]
BASES_DOS_SALARIOS = ["employer_cost", "gross"]
ORIGENS_DOS_SALARIOS = ["contractual", "actual"]
CATEGORIAS_DE_OUTRO_CUSTO = [
    "rent",
    "energy",
    "water",
    "gas",
    "card_fees",
    "licences",
    "accounting",
    "other",
]
EXCLUSOES_DO_RESULTADO = ["depreciation", "financing", "income_tax", "owner_compensation"]
GRANULARIDADES = ["day", "week"]
#: O que o painel não sabe, em ids (ADR 0029, decisão 1).
INDISPONIVEIS = ["revenue", "payroll", "other_costs"]
#: O regime, para o ecrã **rotular** — não para corrigir nada (ADR 0014).
#:
#: Escrito outra vez e não importado: a fronteira de módulos não deixa o
#: `reporting` ver o `RegimeDeIva` do `accounts` (ARCHITECTURE.md §3). **Os
#: rótulos têm de ser os mesmos letra por letra**, e não é cosmética: o
#: drf-spectacular identifica um enum pelo par (valor, rótulo), logo uma
#: diferença aqui parte o `VatRegimeEnum` em dois componentes — e isso é um
#: warning, que com `--fail-on-warn` é exit 1 no `pnpm gen:api`. A divergência
#: falha alto, que é o que se quer de uma cópia.
REGIMES_DE_IVA = [
    ("normal", "Regime normal"),
    ("isento_art_53", "Isento (art. 53.º)"),
]


def _euros(**kwargs) -> serializers.DecimalField:
    """Um montante em euros: duas casas, string no arame."""
    return serializers.DecimalField(max_digits=14, decimal_places=2, **kwargs)


def _share(**kwargs) -> serializers.DecimalField:
    """Uma proporção de 0 a 1 com três casas. Nunca se soma no ecrã."""
    return serializers.DecimalField(max_digits=7, decimal_places=3, **kwargs)


def _pontos_percentuais(**kwargs) -> serializers.DecimalField:
    """Um rácio em pontos percentuais, com uma casa. `null` quando não há denominador."""
    return serializers.DecimalField(max_digits=7, decimal_places=1, **kwargs)


class PeriodoResolvidoOutSerializer(serializers.Serializer):
    """O período como o servidor o resolveu: mostrar a fronteira, não escondê-la."""

    key = serializers.ChoiceField(choices=PERIODOS)
    since = serializers.DateTimeField()
    #: `min(fim da janela, agora)` — um período a correr não promete o futuro.
    until = serializers.DateTimeField()
    #: `"04:00"`, a hora a que o dia de negócio deste estabelecimento começa.
    business_day_starts_at = serializers.CharField()


class ComponenteDeCustoOutSerializer(serializers.Serializer):
    """Uma parcela de custo: o servidor decide o que soma e quem contém quem."""

    id = serializers.ChoiceField(choices=IDS_DE_CUSTO)
    amount_eur = _euros()
    share = _share()
    is_part_of_total = serializers.BooleanField()
    part_of = serializers.ChoiceField(choices=IDS_DE_CUSTO, allow_null=True)


class DesperdicioPorMotivoOutSerializer(serializers.Serializer):
    """Quanto se perdeu por motivo. Ordenada pelo servidor, a maior primeiro."""

    reason = serializers.ChoiceField(choices=MOTIVOS_DE_QUEBRA)
    amount_eur = _euros()
    share = _share()
    #: "foram 3 vezes" é accionável de outra maneira do que "foram 40 €".
    movements = serializers.IntegerField()


class QualidadeDosDadosOutSerializer(serializers.Serializer):
    """O painel declara o que não sabe, e a declaração é parte do contrato."""

    consumption_registered = serializers.BooleanField()
    purchases_awaiting_invoice_eur = _euros()
    #: `null` = nunca houve contagem fechada. Um zero sem contagem é mentira.
    last_count_at = serializers.DateTimeField(allow_null=True)
    revenue_source = serializers.ChoiceField(choices=ORIGENS_DA_RECEITA)
    #: Porque é que há campos a `null`, uma vez e em ids (ADR 0029, decisão 1).
    unavailable = serializers.ListField(
        child=serializers.ChoiceField(choices=INDISPONIVEIS)
    )
    #: Para o ecrã escrever "valores sem IVA" onde isso muda a leitura. O painel
    #: **não corrige** nada com este campo (ADR 0014).
    vat_regime = serializers.ChoiceField(choices=REGIMES_DE_IVA)


class ResumoDoPeriodoOutSerializer(serializers.Serializer):
    """`GET /reporting/summary`. **Sem total de gastos e sem resultado**, de propósito.

    Os dois vivem só no `/month`: um total com a mercadoria discriminada ao lado
    dá a folha salarial por subtracção (ADR 0013, decisão 6). Hoje o painel
    inteiro é do dono e não há ninguém a quem isso exponha nada — o invariante
    fica para o dia em que um bloco se abrir ao encarregado.
    """

    period = PeriodoResolvidoOutSerializer()
    #: Os três a `null`: não há módulo de vendas. Ver `unavailable`.
    revenue_net_eur = _euros(allow_null=True)
    revenue_gross_eur = _euros(allow_null=True)
    revenue_basis = serializers.ChoiceField(choices=BASES_DA_RECEITA, allow_null=True)
    purchases_eur = _euros()
    goods_consumed_eur = _euros()
    #: `purchases − goods_consumed − unknown_shrinkage`, dos já arredondados.
    stock_change_eur = _euros()
    waste_eur = _euros()
    #: Positivo = quebra; negativo = excedente de contagem.
    unknown_shrinkage_eur = _euros()
    goods_cost_ratio_pct = _pontos_percentuais(allow_null=True)
    stock_value_eur = _euros()
    #: O valor de stock é **instantâneo**: esta é a hora a que foi lido.
    stock_value_as_of = serializers.DateTimeField()
    costs = ComponenteDeCustoOutSerializer(many=True)
    waste_by_reason = DesperdicioPorMotivoOutSerializer(many=True)
    data_quality = QualidadeDosDadosOutSerializer()


class IntervaloOutSerializer(serializers.Serializer):
    """O intervalo de um ponto. Viaja uma vez, não por série."""

    since = serializers.DateTimeField()
    until = serializers.DateTimeField()


class PontoDaSerieOutSerializer(serializers.Serializer):
    """Um ponto: o valor e a altura da barra (`value / scale_max`)."""

    value_eur = _euros()
    share = _share()


class SerieOutSerializer(serializers.Serializer):
    """Uma série do gráfico."""

    id = serializers.ChoiceField(choices=IDS_DE_SERIE)
    unit = serializers.CharField()
    total_eur = _euros()
    points = PontoDaSerieOutSerializer(many=True)


class SeriesDoPeriodoOutSerializer(serializers.Serializer):
    """`GET /reporting/series`. Hoje com **uma** série, e a legenda diz porquê."""

    period = PeriodoResolvidoOutSerializer()
    #: Derivada do período pelo servidor, nunca escolhida no cliente.
    granularity = serializers.ChoiceField(choices=GRANULARIDADES)
    buckets = IntervaloOutSerializer(many=True)
    #: O máximo do eixo vem do servidor; sem ele o cliente dividia euros.
    scale_max_eur = _euros()
    series = SerieOutSerializer(many=True)


class ParteDeSalariosOutSerializer(serializers.Serializer):
    """Uma parcela do custo-empresa. **Lista vazia nesta fatia** (sem `people`)."""

    id = serializers.ChoiceField(choices=IDS_DE_PARTE_DE_SALARIOS)
    amount_eur = _euros()


class CustoPorCargoOutSerializer(serializers.Serializer):
    """O custo de um cargo — que não é o papel de acesso. Lista vazia nesta fatia."""

    role_id = serializers.UUIDField()
    name = serializers.CharField()
    headcount = serializers.IntegerField()
    payroll_eur = _euros()
    share = _share()


class OutroCustoOutSerializer(serializers.Serializer):
    """Um custo fixo mensal. Lista vazia nesta fatia (sem `purchasing_othercost`)."""

    category = serializers.ChoiceField(choices=CATEGORIAS_DE_OUTRO_CUSTO)
    amount_eur = _euros()
    note = serializers.CharField(allow_null=True)


class FechoDoMesOutSerializer(serializers.Serializer):
    """`GET /reporting/month`. A palavra "lucro" não aparece: o campo é `result_eur`.

    Metade dos campos vai a `null` e as quatro listas vêm vazias, e é a decisão
    1 da ADR 0029: sem `people` não há salários e sem salários não há total de
    gastos nem resultado. Servir zeros era desenhar barras a zero e um rácio a
    0% — o painel optimista que a decisão 7 da ADR 0013 nomeia.
    """

    month = serializers.CharField()
    since = serializers.DateTimeField()
    until = serializers.DateTimeField()
    business_day_starts_at = serializers.CharField()
    closed = serializers.BooleanField()
    #: Um mês a correr ao dia 9 não se compara com um fechado, e o `closed`
    #: sozinho não evita a leitura errada.
    days_elapsed = serializers.IntegerField()
    days_in_month = serializers.IntegerField()

    revenue_net_eur = _euros(allow_null=True)
    revenue_gross_eur = _euros(allow_null=True)
    revenue_basis = serializers.ChoiceField(choices=BASES_DA_RECEITA, allow_null=True)
    purchases_eur = _euros()
    goods_consumed_eur = _euros()
    stock_change_eur = _euros()
    waste_eur = _euros()
    unknown_shrinkage_eur = _euros()
    stock_value_eur = _euros()
    stock_value_as_of = serializers.DateTimeField()

    payroll_eur = _euros(allow_null=True)
    payroll_basis = serializers.ChoiceField(choices=BASES_DOS_SALARIOS, allow_null=True)
    payroll_source = serializers.ChoiceField(choices=ORIGENS_DOS_SALARIOS, allow_null=True)
    payroll_breakdown = ParteDeSalariosOutSerializer(many=True)
    roles = CustoPorCargoOutSerializer(many=True)
    other_costs = OutroCustoOutSerializer(many=True)
    costs = ComponenteDeCustoOutSerializer(many=True)
    #: Só aqui, porque só aqui haveria salários — e hoje `null`, porque não há.
    cost_total_eur = _euros(allow_null=True)
    result_eur = _euros(allow_null=True)
    #: Vazia: uma lista de exclusões de um número que não existe é ruído.
    result_excludes = serializers.ListField(
        child=serializers.ChoiceField(choices=EXCLUSOES_DO_RESULTADO)
    )
    goods_cost_ratio_pct = _pontos_percentuais(allow_null=True)
    labour_cost_ratio_pct = _pontos_percentuais(allow_null=True)
    prime_cost_pct = _pontos_percentuais(allow_null=True)
    waste_by_reason = DesperdicioPorMotivoOutSerializer(many=True)
    data_quality = QualidadeDosDadosOutSerializer()


class RecusaDoPainelOutSerializer(serializers.Serializer):
    """O corpo de um 403 ou de um 400: **só `detail`, sem `code` novo** (ADR 0013, d6).

    É a forma exacta que o DRF já devolve. Não reutiliza o `ErroOutSerializer`
    do `accounts` — esse não é importável de fora do módulo —, e não tem `code`
    porque este endpoint não tem ramos de recusa para o cliente distinguir: ou
    é dono, ou não é.
    """

    detail = serializers.CharField()
