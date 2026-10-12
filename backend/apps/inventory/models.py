"""A `Location` — e só ela, nesta fatia (ADR 0021, fatia 2; ADR 0022).

O `inventory` é *"o que há e como mudou"*: localizações, lotes, movimentos e
projeções. Desta família só a localização entra agora, porque é a única de que a
receção precisa — o `location` de uma linha não é anulável no contrato — e as
outras três (`Lot`, `StockMovement`, `StockLevel`) são o ledger da fatia 3, que
o `CLAUDE.md` manda passar pelo `domain-expert` antes de existir migração.

Sem `slug`: o contrato manda `{id, name}` e o `?loja=` do ecrã de Stock passa a
ser o `id` (ADR 0021). Sem `kind`, sem "em trânsito", sem `parent` (§4.9) — a
sessão 0 decide, e uma coluna sem leitor numa migração que não se edita é um
compromisso tomado às escuras.

Nenhum destes modelos é registado no admin (ADR 0007).
"""

from __future__ import annotations

from django.db import models
from django.db.models.functions import Lower

from apps.shared.models import TenantModel

__all__ = ["Location"]


class Location(TenantModel):
    """Uma loja, um armazém, uma cozinha: onde a mercadoria está.

    `position` é a ordem em que as localizações aparecem — o `GET /locations`
    ordena por ela —, e o default ao criar é o fim da lista. Não é única: duas
    com a mesma posição desempatam pelo nome, e renumerar à mão é o caso raro
    que o `PATCH` cobre.

    `is_active` e nunca `DELETE`, pela razão do artigo: as linhas de receção e,
    na fatia 3, os movimentos apontam-lhe com `RESTRICT`. Uma localização
    inactiva recusa-se como destino (`localizacao_inativa`, §4.9).
    """

    name = models.CharField(max_length=60, verbose_name="nome")
    position = models.PositiveSmallIntegerField(verbose_name="ordem")
    is_active = models.BooleanField(default=True, verbose_name="ativa")

    class Meta(TenantModel.Meta):
        verbose_name = "localização"
        verbose_name_plural = "localizações"
        constraints = [
            models.UniqueConstraint(
                Lower("name"), "tenant", name="inventory_location_name_lower_uniq"
            ),
        ]

    def __str__(self) -> str:
        return self.name
