from django.apps import AppConfig


class AgentsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.agents"
    verbose_name = "Agentes de IA: extração de faturas, chat sobre stock, previsões"

    def ready(self) -> None:
        """Duas ligações, e as duas são o mesmo princípio em direções opostas.

        1. **A subscrição do `DocumentoFechado`** (`handlers.py`), que é o sítio
           que o `ARCHITECTURE.md` §3 nomeia para isto. Substituiu a metade
           `pedir` do porto da extração no dia em que a outbox passou a ter
           consumidor — era a condição escrita no topo de
           `apps/purchasing/extracao.py`.
        2. **O adaptador do porto**, que serve a outra metade (`leituras`) e
           continua a ser necessário: o `DocumentoOut` precisa da última leitura
           de cada documento no instante em que serve a resposta, e isso é uma
           pergunta e não um aviso.

        Import no corpo do `ready()` e não no topo do ficheiro: os dois módulos
        importam models, e um `apps.py` que importe models é um
        `AppRegistryNotReady` no arranque.
        """
        from apps.agents.fronteira import FronteiraLocalDaExtracao
        from apps.agents.handlers import registar_handlers
        from apps.purchasing.api import ligar_fronteira_da_extracao

        registar_handlers()
        ligar_fronteira_da_extracao(FronteiraLocalDaExtracao())
