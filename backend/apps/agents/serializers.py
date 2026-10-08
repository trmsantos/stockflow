"""O schema da resposta do modelo. **A única coluna em que nada se confia.**

A decisão 4 da ADR 0021 pede duas validações do `payload`: uma **à escrita** (e um
`status=ilegivel` quando falha) e outra **à leitura** (*"porque é a única coluna
do sistema em que nada se confia"*). Este ficheiro é as duas — a mesma classe
corre nos dois momentos, que é o que garante que não divergem.

## Serializer do DRF e não Pydantic

A ADR escreve "schema Pydantic", herdado do `ARCHITECTURE.md` §6. **O Pydantic
não é uma dependência deste projecto** e esta sessão não acrescenta dependências,
logo o schema é um `Serializer` do DRF — que é a ferramenta de validação que o
repositório já tem, no sítio onde a usa, e que faz exactamente o que a ADR pede
da validação (campos tipados, `max_length`, `Decimal`, recusa com erro por
campo). O que se perde é o `model_validate` de um modelo tipado em Python; o que
se ganha é zero dependências novas e uma ferramenta só para validar entrada.

## Tudo é opcional, e isso é a decisão central

Um modelo que não consiga ler o número da fatura devolve um documento **sem**
número, e isso é um resultado legítimo que a revisão humana resolve — não um
payload ilegível. O que torna um payload ilegível é ter a **forma** errada: um
`total` que não é um número, uma data que não é uma data, `lines` que não é uma
lista. É essa a fronteira entre `lido` e `ilegivel`, e está aqui e não num `if`
espalhado.

**Nada do que é validado aqui escolhe uma entidade.** Não há `product_id`, não há
`location_id`, não há `packaging_id`: uma string extraída nunca vira uma chave
estrangeira sem uma pessoa a confirmar (CLAUDE.md), e a forma de garantir isso é
o schema não ter onde a pôr.

E `doc_type` é uma string livre e **não** um enum: o papel ganha sempre (ADR
0021, adenda), e um `ChoiceField` aqui recusava uma fatura verdadeira com um tipo
que não antecipámos. O enum fechado nasce na fatia 2, na coluna que uma pessoa
confirma.
"""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from apps.purchasing.api import LeituraDeDocumento, LinhaLida

__all__ = [
    "LeituraDeFaturaSerializer",
    "LinhaDeFaturaSerializer",
    "leitura_do_payload",
    "leitura_validada",
]


class LinhaDeFaturaSerializer(serializers.Serializer):
    """Uma linha como o modelo a leu. Campos listados um a um, nunca `__all__`.

    Os `max_digits`/`decimal_places` são os da ADR 0021 (decisão 7): quantidades
    `(12,3)`, custos `(12,4)`, dinheiro `(12,2)`, taxas `(6,3)`. Um número com
    mais casas do que isto é um payload ilegível e não um arredondamento
    silencioso — arredondar aqui era inventar um valor que o papel não tem.

    `position` não tem default: é o que dá ordem às linhas, e uma lista de linhas
    sem ordem não se pode mostrar ao lado de uma fatura.
    """

    position = serializers.IntegerField(min_value=1, max_value=1000)
    description = serializers.CharField(max_length=500, allow_blank=True, default="")
    quantity = serializers.DecimalField(
        max_digits=12, decimal_places=3, allow_null=True, default=None
    )
    unit = serializers.CharField(max_length=20, allow_blank=True, default="")
    unit_price = serializers.DecimalField(
        max_digits=12, decimal_places=4, allow_null=True, default=None
    )
    vat_rate = serializers.DecimalField(
        max_digits=6, decimal_places=3, allow_null=True, default=None
    )
    line_total = serializers.DecimalField(
        max_digits=12, decimal_places=2, allow_null=True, default=None
    )
    confidence = serializers.DecimalField(
        max_digits=4,
        decimal_places=3,
        min_value=0,
        max_value=1,
        allow_null=True,
        default=None,
    )


class LeituraDeFaturaSerializer(serializers.Serializer):
    """O cabeçalho e as linhas, como o modelo os leu.

    O cabeçalho está aqui **e** fica nomeado que, a partir do dia em que o QR for
    descodificado, deixa de ser a melhor fonte: o QR de uma fatura portuguesa traz
    os dois NIF, o tipo, o estado, a data, o ATCUD, o espaço fiscal e as bases e o
    IVA por taxa, sem erro de OCR (ADR 0021, adenda). **O QR é a verdade do
    cabeçalho e o LLM só serve para as linhas** — e o que falta para isso é a
    biblioteca que lê o QR, não este schema.
    """

    confidence = serializers.DecimalField(
        max_digits=4,
        decimal_places=3,
        min_value=0,
        max_value=1,
        allow_null=True,
        default=None,
    )
    supplier_name = serializers.CharField(max_length=200, allow_blank=True, default="")
    supplier_nif = serializers.CharField(max_length=20, allow_blank=True, default="")
    doc_type = serializers.CharField(max_length=20, allow_blank=True, default="")
    doc_number = serializers.CharField(max_length=100, allow_blank=True, default="")
    issued_at = serializers.DateField(allow_null=True, default=None)
    customer_nif = serializers.CharField(max_length=20, allow_blank=True, default="")
    total = serializers.DecimalField(
        max_digits=12, decimal_places=2, allow_null=True, default=None
    )
    lines = LinhaDeFaturaSerializer(many=True, default=list)


def leitura_do_payload(payload: Any) -> LeituraDeFaturaSerializer:
    """O serializer já ligado a um payload, pronto a `is_valid()`.

    Função e não `LeituraDeFaturaSerializer(data=payload)` escrito em três sítios:
    o `data=` de um serializer com um valor que não é um `dict` levanta
    `AttributeError` em vez de falhar a validação — um modelo que devolva uma
    lista, ou uma string, não deve rebentar a tarefa. Aqui um payload que não é um
    objecto JSON passa a ser um erro de validação como qualquer outro, e o
    documento fica `ilegivel`.
    """
    if not isinstance(payload, dict):
        return LeituraDeFaturaSerializer(data={"lines": "nao-e-um-objecto"})
    return LeituraDeFaturaSerializer(data=payload)


def leitura_validada(payload: Any) -> LeituraDeDocumento | None:
    """O payload como `LeituraDeDocumento`, ou `None` se não validar.

    É a validação **à leitura**: corre em cada resposta que serve um documento
    lido, e não uma vez na escrita. Parece desperdício e não é — é o que impede
    uma linha gravada por uma versão anterior do schema, ou mexida à mão na base
    de dados, de chegar ao cliente como se fosse boa.

    Devolve `None` e nunca levanta: quem chama decide o que mostrar, e nesta fatia
    a decisão é `ilegivel`.
    """
    serializer = leitura_do_payload(payload)
    if not serializer.is_valid():
        return None
    dados = serializer.validated_data
    return LeituraDeDocumento(
        # O `state` é de quem chama: este ficheiro valida a forma e não decide o
        # estado da chamada.
        state="",
        confidence=dados["confidence"],
        supplier_name=dados["supplier_name"],
        supplier_nif=dados["supplier_nif"],
        doc_type=dados["doc_type"],
        doc_number=dados["doc_number"],
        issued_at=dados["issued_at"],
        customer_nif=dados["customer_nif"],
        total=dados["total"],
        lines=tuple(
            LinhaLida(
                position=linha["position"],
                description=linha["description"],
                quantity=linha["quantity"],
                unit=linha["unit"],
                unit_price=linha["unit_price"],
                vat_rate=linha["vat_rate"],
                line_total=linha["line_total"],
                confidence=linha["confidence"],
            )
            for linha in sorted(dados["lines"], key=lambda linha: linha["position"])
        ),
    )
