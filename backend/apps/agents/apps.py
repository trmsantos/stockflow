from django.apps import AppConfig


class AgentsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.agents"
    verbose_name = "Agentes de IA: extração de faturas, previsões"

    def ready(self) -> None:
        """Liga o adaptador do porto da extração ao `purchasing`.

        É o sítio que o `ARCHITECTURE.md` §3 nomeia para subscrições (*"é onde as
        subscrições de eventos (`handlers.py`) se registam no `ready()`"*), e isto
        é uma subscrição com outro nome — a que substitui, por agora, o
        `DocumentoFechado` da outbox que não tem consumidor. A razão inteira está
        no topo de `apps/purchasing/extracao.py`.

        Import no corpo do `ready()` e não no topo do ficheiro: o `fronteira.py`
        importa models dos dois módulos, e um `apps.py` que importe models é um
        `AppRegistryNotReady` no arranque.
        """
        from apps.agents.fronteira import FronteiraLocalDaExtracao
        from apps.purchasing.api import ligar_fronteira_da_extracao

        ligar_fronteira_da_extracao(FronteiraLocalDaExtracao())
