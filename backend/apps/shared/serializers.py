"""As primitivas de contrato que mais do que um módulo serve.

São o **quarteto de uma quantidade** e as **duas direcções da sua conversão**.
Estão aqui — e não em `inventory/serializers.py`, onde nasceram — por uma razão
de **nome de componente** e uma de **definição única**, não de arrumação.

O `recipes` não pode importar `apps.inventory.serializers` (a aresta permitida é
`recipes -> inventory.api`, ARCHITECTURE.md §3) e a ficha técnica serve
quantidades: `batch_size`, `quantity` e `quantity_real` são todas o mesmo
quarteto que o `/stock/levels` já publica. Declará-lo outra vez do lado do
`recipes` dava um **segundo componente** no OpenAPI — `QuantidadeDaReceitaOut`
ao lado de `QuantidadeOut`, com os mesmos quatro campos — e portanto um segundo
tipo no `types.ts` e um segundo schema Zod escrito à mão. É a mesma divergência
de vocabulário que o `ESTADOS_DO_CUSTO` evita do lado das palavras do custo
(ADR 0032), e evita-se do mesmo modo: uma definição, importada pelos dois.

A segunda razão é a conversão. `em_unidade_pedida` é a regra que diz que a
unidade de entrada tem de ser o `base_unit` ou o `display_unit` **daquele
artigo** e que qualquer outra é 400 — não existe motor genérico de conversão
(ADR 0011). A ficha técnica aceita "500 g de farinha" pelas mesmas regras que
uma linha de contagem aceita "24 kg", e escrevê-la outra vez do lado do
`recipes` era uma **segunda definição** da mesma decisão: a que um dia só se
corrige num dos sítios. `quantidade_bruta` é a direcção inversa e vive ao lado
porque as duas direcções da mesma conversão são a mesma decisão.

`apps.shared` é a camada de base e é importável por todos (`apps.** ->
apps.shared.**` no import-linter); não importa módulo nenhum, e continua a não
importar — só o `rest_framework` e o `django.utils`.

O que **não** está aqui: tudo o que precise de uma query. Estas são funções
puras sobre um objecto com `base_unit`, `display_unit` e `display_factor` — um
`Product`, um `ProdutoResumo` ou uma linha de `values()`.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

__all__ = [
    "DETALHE_QUANTIDADE_GRANDE",
    "DETALHE_UNIDADE_DESCONHECIDA",
    "MAXIMO_DA_QUANTIDADE",
    "QuantidadeOutSerializer",
    "em_unidade_pedida",
    "quantidade_bruta",
]

#: O tecto de uma coluna `Decimal(12,3)` na unidade **base**. É o do
#: `StockCountLine` e o do `RecipeLineItem`, que é a mesma coluna duas vezes.
#: Vive aqui e não nos serviços porque é aqui que a conversão faz o número
#: crescer: 12 dígitos na unidade de quem escreve podem ser 15 em base.
MAXIMO_DA_QUANTIDADE = Decimal("999999999.999")

DETALHE_QUANTIDADE_GRANDE = _("This amount is too large for a count.")
DETALHE_UNIDADE_DESCONHECIDA = _(
    "Use the base unit or the display unit of this product."
)


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


def quantidade_bruta(
    valor: Decimal, *, base_unit: str, display_unit: str, display_factor: Decimal | None
) -> dict[str, Any]:
    """O quarteto, a partir das três colunas soltas em vez de um objecto.

    Existe na forma solta porque os selectors do painel devolvem linhas de
    `values()` e não instâncias: o trio que converte vem como três chaves, e
    materializar um `Product` por linha só para ler três atributos era uma
    query por artigo.

    `display_factor` é quantas unidades base cabem numa de apresentação (1 kg =
    1000 g), logo a de mostrar é a base **dividida** por ele. Dividir no cliente
    é o que o domínio proíbe (`inventory-domain` §2), e é por isso que as duas
    viajam juntas.
    """
    factor = display_factor or Decimal("1")
    return {
        "base": valor,
        "base_unit": base_unit,
        "display": (valor / factor).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP),
        "display_unit": display_unit,
    }


def em_unidade_pedida(valor: Decimal, *, unidade: str, produto: Any) -> Decimal:
    """Converte `valor` da unidade pedida para a do ledger. Outra unidade é 400.

    A unidade tem de ser o `base_unit` ou o `display_unit` **daquele artigo**:
    não existe motor genérico de conversão (ADR 0011) e inventar um aqui era
    aceitar "l" num artigo que se conta às unidades. A conversão é do servidor,
    nunca do cliente (ADR 0030, decisão 1, e `inventory-domain` §2).

    O tecto da coluna é verificado **aqui**, porque é aqui que o número cresce:
    o serializer valida 12 dígitos na unidade de quem escreve e a multiplicação
    pode pô-los a 15.

    `produto` a `None` devolve o valor como veio: quem não existe é recusado
    por quem chama, com o 404 ou o 400 por campo, e não aqui com um
    `AttributeError`.
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
