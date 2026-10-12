"""Os casos de uso do `inventory` nesta fatia: criar e editar uma localização.

Uma função por caso de uso, `@transaction.atomic`, e nenhuma escrita fora daqui.
Sem outbox: zero eventos nesta fatia (ADR 0022). O `record_movements` — a única
função deste módulo que vai escrever no ledger — é a fatia 3.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Max
from django.utils.translation import gettext_lazy as _

from apps.inventory.models import Location

__all__ = ["CAMPOS_DA_LOCALIZACAO", "actualizar_localizacao", "criar_localizacao"]

logger = logging.getLogger(__name__)

#: O que o `PATCH /locations/<id>` pode escrever.
CAMPOS_DA_LOCALIZACAO: frozenset[str] = frozenset({"name", "position", "is_active"})

#: O teto do `smallint` do Postgres, que é o tipo de `position`. Recusado aqui
#: com uma frase em vez de deixar o erro de intervalo subir como 500.
POSICAO_MAXIMA = 32767

DETALHE_NOME_DUPLICADO = _(
    "There is already a location with this name in this establishment."
)
DETALHE_OBRIGATORIO = _("This field is required.")
DETALHE_DEMASIADO_LONGO = _("At most {limite} characters.")
DETALHE_POSICAO = _("The position is a whole number between 0 and {limite}.")
DETALHE_CAMPO_FORA_DO_CONTRATO = _("This field cannot be changed here.")


@transaction.atomic
def criar_localizacao(
    *, tenant_id: UUID, name: str, position: int | None = None, id: UUID | None = None
) -> Location:
    """Uma localização. Sem `position`, vai para o fim da lista.

    "O fim" é o máximo actual mais um, lido **nesta** transação; dois pedidos
    simultâneos podem calcular o mesmo número, e isso é aceitável porque a
    posição não é única — desempatam pelo nome. O `id` opcional é o que o
    `apps/demo` usa para os uuid estáveis; com `id`, uma linha que já exista
    neste tenant é devolvida em vez de recriada.
    """
    if id is not None:
        existente = Location.objects.filter(tenant_id=tenant_id, pk=id).first()
        if existente is not None:
            return existente

    nome = _nome(name)
    ordem = _posicao(position) if position is not None else _fim_da_lista(tenant_id)
    if Location.objects.filter(tenant_id=tenant_id, name__iexact=nome).exists():
        raise ValidationError({"name": [DETALHE_NOME_DUPLICADO]})
    try:
        with transaction.atomic():
            localizacao = Location.objects.create(
                tenant_id=tenant_id,
                name=nome,
                position=ordem,
                **({"id": id} if id is not None else {}),
            )
    except IntegrityError as erro:
        logger.info(
            "localização recusada pela constraint",
            extra={"event": "inventario.localizacao", "outcome": "duplicado"},
        )
        raise ValidationError({"name": [DETALHE_NOME_DUPLICADO]}) from erro
    return localizacao


@transaction.atomic
def actualizar_localizacao(
    *, tenant_id: UUID, localizacao: Location, campos: Mapping[str, object]
) -> Location:
    """`PATCH`: `name`, `position`, `is_active`. Relido sob lock antes de escrever."""
    fora = sorted(set(campos) - CAMPOS_DA_LOCALIZACAO)
    if fora:
        raise ValidationError({campo: [DETALHE_CAMPO_FORA_DO_CONTRATO] for campo in fora})

    bloqueado = (
        Location.objects.select_for_update()
        .filter(tenant_id=tenant_id, pk=localizacao.pk)
        .get()
    )
    if "name" in campos:
        nome = _nome(str(campos["name"]))
        if (
            Location.objects.filter(tenant_id=tenant_id, name__iexact=nome)
            .exclude(pk=bloqueado.pk)
            .exists()
        ):
            raise ValidationError({"name": [DETALHE_NOME_DUPLICADO]})
        bloqueado.name = nome
    if "position" in campos:
        bloqueado.position = _posicao(campos["position"])
    if "is_active" in campos:
        bloqueado.is_active = bool(campos["is_active"])
    try:
        with transaction.atomic():
            bloqueado.save(update_fields=["name", "position", "is_active", "updated_at"])
    except IntegrityError as erro:
        raise ValidationError({"name": [DETALHE_NOME_DUPLICADO]}) from erro
    return bloqueado


def _fim_da_lista(tenant_id: UUID) -> int:
    maior = Location.objects.filter(tenant_id=tenant_id).aggregate(maior=Max("position"))["maior"]
    return 1 if maior is None else min(maior + 1, POSICAO_MAXIMA)


def _nome(valor: str | None) -> str:
    limpo = (valor or "").strip()
    if not limpo:
        raise ValidationError({"name": [DETALHE_OBRIGATORIO]})
    if len(limpo) > 60:
        raise ValidationError({"name": [DETALHE_DEMASIADO_LONGO.format(limite=60)]})
    return limpo


def _posicao(valor: object) -> int:
    if isinstance(valor, bool) or not isinstance(valor, int) or not 0 <= valor <= POSICAO_MAXIMA:
        raise ValidationError({"position": [DETALHE_POSICAO.format(limite=POSICAO_MAXIMA)]})
    return valor
