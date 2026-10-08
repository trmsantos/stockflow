from django.apps import AppConfig


class PurchasingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.purchasing"
    verbose_name = "Compras: encomendas, faturas, receções"

    def ready(self) -> None:
        """Registra os handlers deste módulo no registo do `apps.shared`.

        É o sítio que o `ARCHITECTURE.md` §3 nomeia para as subscrições de
        eventos (*"é onde as subscrições de eventos (`handlers.py`) se registam
        no `ready()`"*), e é a inversão que o consumidor da outbox precisa: o
        `apps.shared` é infraestrutura e não importa módulos, logo é cada módulo
        que se dá a conhecer.

        Import no corpo do `ready()` e não no topo do ficheiro: o `handlers.py`
        importa o `models.py`, e um `apps.py` que importe models é um
        `AppRegistryNotReady` no arranque. É o mesmo padrão do `AgentsConfig`.
        """
        from apps.purchasing.handlers import registar_handlers

        registar_handlers()
