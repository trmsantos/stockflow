"""`agents_extraction`: uma linha por **chamada** ao modelo (ADR 0021, decisão 4).

Guarda o que o modelo devolveu, **verbatim**, em JSON, e o custo da chamada. É
prova e não configuração — e é essa a distinção que torna este `JSONField`
legítimo onde a ADR 0011 proíbe os outros: o que ela proíbe é um JSON de
**configuração**, valores em que o produto ramifica, invisíveis ao `schema.yml` e
ao gate de diff do `types.ts`. Aqui é o oposto: texto não confiável guardado para
se poder voltar a ele, **nunca comparado num `if`**, nunca interpolado em SQL,
nunca renderizado sem escape (CLAUDE.md, SECURITY.md §6).

O que o produto lê são as colunas tipadas da linha de receção, que são a verdade
da pessoa — e essas são da fatia 2.

## O `document_id` é um `UUIDField` e não uma FK

A secção 7 do `ARCHITECTURE.md` nomeia o `agents` como o candidato óbvio a sair
para serviço próprio e promete que *"a extração é mecânica"*. Uma FK para a
tabela do `purchasing` quebra essa promessa ao nível do esquema, e uma promessa
que só se descobre falsa no dia da extração não vale nada (ADR 0021, decisão 5).

O preço está nomeado, como no `tenant_id` da outbox: nada impede uma linha com um
`document_id` que já não existe. Para uma tabela de rasto é o preço certo — e o
descarte de um documento é suave, logo o caso normal nem acontece.

## E a tabela **não** é append-only

`started_at`, `finished_at`, `cost_eur` e `status` são `UPDATE`s da **mesma**
chamada (ADR 0021, decisão 4). O `APPEND_ONLY` do `tests/test_db_roles.py` não
ganha entrada nenhuma nesta fatia: a primeira da sua história é o
`inventory_stockmovement`, na fatia 3.

Nenhum destes modelos é registado no admin (ADR 0007).

## As duas tabelas do chat sobre stock (ADR 0027, decisão 1)

`agents_conversation` e `agents_chatmessage`, **uma linha por turno** — pergunta e
resposta na mesma linha, como a `Extraction` é uma linha por chamada. Herdam
`TenantModel` e nascem com política de RLS na `0002`; dependem só do `accounts`.
Também não são append-only: `started_at`, `answer`, `tool_calls` e `cost_eur` são
`UPDATE`s do mesmo turno, e o `DELETE` da conversa é real (purga aos 90 dias). O
`APPEND_ONLY` e o `SEM_POLITICA` do `tests/test_db_roles.py` não mexem.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from apps.agents.rasto import chamadas_validas
from apps.shared.models import TenantModel

__all__ = [
    "JANELA_DA_RESPOSTA",
    "TURNOS_POR_CONVERSA",
    "ChatMessage",
    "CodigoDeErroDaMensagem",
    "Conversation",
    "EstadoDaExtracao",
    "EstadoDaMensagem",
    "Extraction",
]

#: Quanto tempo um turno pode estar `pendente`/`a_responder` antes de se **ler**
#: como `erro/tempo_esgotado` — por derivação, nunca por escrita (ADR 0027,
#: decisão 3; é o relógio da `JANELA_DA_EXTRACAO`). Dois minutos: seis chamadas
#: de trinta segundos no pior caso são três, e o cliente desiste aos noventa
#: segundos de qualquer forma.
JANELA_DA_RESPOSTA = timedelta(minutes=2)

#: Turnos por conversa (ADR 0027, decisão 9). Ao trigésimo o `POST` recusa com
#: `conversa_cheia`, e a pessoa abre outra.
TURNOS_POR_CONVERSA = 30


class EstadoDaExtracao(models.TextChoices):
    """O estado de uma chamada: os quatro da decisão 7 da ADR 0021.

    Os valores são **os mesmos** do `EstadoDaLeitura` do `purchasing.api`, que é
    o vocabulário em que o resultado atravessa a fronteira. São duas listas
    fechadas em dois módulos — esta porque é o `choices` de uma coluna, aquela
    porque é o tipo do porto — e a igualdade entre elas é um teste
    (`tests/test_extracao.py`), que falha nos dois sentidos. Importar a de lá
    para aqui era deixar o `choices` de uma coluna deste módulo ser decidido por
    outro; duplicar sem teste era deixá-las divergir em silêncio.
    """

    PENDENTE = "pendente", "a chamada começou e não acabou"
    LIDO = "lido", "o modelo respondeu e a resposta valida"
    ILEGIVEL = "ilegivel", "o modelo respondeu e a resposta não valida"
    ERRO = "erro", "a chamada falhou"


class Extraction(TenantModel):
    """Uma chamada ao modelo, do pedido ao custo.

    Herda de `TenantModel`: chave UUID, `tenant_id` que a política compara, os
    dois timestamps e o índice `(tenant_id, -created_at)`. A migração que cria a
    tabela traz o bloco de RLS (CLAUDE.md).

    ## `attempt`, e porque é que cada abertura acrescenta uma linha

    *"Cada abertura acrescenta uma linha de extração em vez de sobrepor a
    anterior"* (ADR 0021, decisão 9). Logo a unicidade é
    `(tenant, document_id, attempt)` e não `(tenant, document_id)`: o histórico
    das tentativas é o que permite responder a "porque é que este documento foi
    lido duas vezes" sem um log.

    ## `idempotency_key`, e porque é única **globalmente**

    O `ARCHITECTURE.md` §6 exige-a em cada chamada a um modelo. É derivada de
    `(document_id, attempt)` e portanto determinística: uma retentativa da
    **mesma** tentativa colide em vez de duplicar, e o que se paga por uma
    chamada é pago uma vez. Única global e não por tenant, como o `token_hash` do
    `Invitation`: não é um oráculo entre clientes porque nenhum cliente a escolhe,
    e a unicidade global é a rede contra a mesma chave em dois estabelecimentos.

    ## `error` não está na tabela da ADR, e faz falta

    A decisão 7 enumera as colunas *"que não são óbvias"* e não é uma lista
    exaustiva. Um `status=erro` sem razão legível manda quem o vê ler os logs do
    worker, e hoje o erro é **sempre** o mesmo (não há modelo configurado), o que
    torna a ausência da frase especialmente absurda. Segue o precedente do
    `last_error` da outbox: **só a classe e a mensagem da excepção, nunca o
    traceback** — o `DETAIL` de um erro do Postgres leva os valores da linha em
    conflito (SECURITY.md §1).

    E a razão **não** vai no `payload`: o `payload` é o que o modelo devolveu,
    verbatim. Escrever lá uma frase nossa era corromper a única coluna cujo valor
    inteiro é ser verbatim.
    """

    document_id = models.UUIDField(editable=False, verbose_name="documento")
    attempt = models.PositiveSmallIntegerField(editable=False, verbose_name="tentativa")
    model = models.CharField(
        max_length=100,
        blank=True,
        default="",
        editable=False,
        verbose_name="modelo chamado",
    )
    prompt_version = models.CharField(
        max_length=50,
        blank=True,
        default="",
        editable=False,
        verbose_name="versão do prompt",
    )
    idempotency_key = models.CharField(
        max_length=200,
        editable=False,
        verbose_name="chave de idempotência",
    )
    started_at = models.DateTimeField(
        null=True,
        blank=True,
        default=None,
        editable=False,
        verbose_name="começou em",
    )
    finished_at = models.DateTimeField(
        null=True,
        blank=True,
        default=None,
        editable=False,
        verbose_name="acabou em",
    )
    input_tokens = models.PositiveIntegerField(
        default=0, editable=False, verbose_name="tokens de entrada"
    )
    output_tokens = models.PositiveIntegerField(
        default=0, editable=False, verbose_name="tokens de saída"
    )
    #: Seis casas decimais e não duas. É dinheiro, e a regra da ADR 0021 para
    #: dinheiro é `Decimal(12,2)` — mas uma chamada a um modelo custa fracções de
    #: cêntimo, e a duas casas **todas** as chamadas custariam 0,00 €. É a mesma
    #: correcção que a adenda da ADR 0021 fez ao custo unitário ("guarda-se a
    #: seis casas"), pela mesma aritmética. Nunca `float` (CLAUDE.md).
    cost_eur = models.DecimalField(
        max_digits=12,
        decimal_places=6,
        default=0,
        editable=False,
        verbose_name="custo em euros",
    )
    status = models.CharField(
        max_length=20,
        choices=EstadoDaExtracao.choices,
        default=EstadoDaExtracao.PENDENTE,
        editable=False,
        verbose_name="estado",
    )
    #: Entre 0 e 1, três casas. Validadores no modelo **e** `CheckConstraint` na
    #: base de dados: o validador do Django não corre num `update()` nem num
    #: `bulk_create`, e uma confiança de 42 chegava ao ecrã como 4200 %.
    confidence = models.DecimalField(
        max_digits=4,
        decimal_places=3,
        null=True,
        blank=True,
        default=None,
        editable=False,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
        verbose_name="confiança",
    )
    payload = models.JSONField(
        default=dict,
        editable=False,
        verbose_name="resposta do modelo, verbatim",
    )
    error = models.TextField(
        blank=True,
        default="",
        editable=False,
        verbose_name="razão legível de um erro",
    )

    class Meta(TenantModel.Meta):
        verbose_name = "extração"
        verbose_name_plural = "extrações"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "document_id", "attempt"],
                name="extraction_documento_tentativa_uniq",
            ),
            models.UniqueConstraint(
                fields=["idempotency_key"],
                name="extraction_idempotency_key_uniq",
            ),
            models.CheckConstraint(
                condition=models.Q(confidence__isnull=True)
                | models.Q(confidence__gte=0, confidence__lte=1),
                name="extraction_confidence_entre_0_e_1",
            ),
        ]
        indexes = [
            *TenantModel.Meta.indexes,
            # A query do porto: a última tentativa de cada documento, em lote.
            # Sem este índice é uma varredura por listagem de documentos.
            models.Index(
                fields=["tenant", "document_id", "-attempt"],
                name="extraction_doc_attempt_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.document_id} #{self.attempt} ({self.status})"


class EstadoDaMensagem(models.TextChoices):
    """O estado de um turno: os quatro da decisão 1 da ADR 0027.

    `pendente` é a linha acabada de criar pelo `POST`; `a_responder` é a tarefa
    a correr, com `started_at` escrito; `respondida` e `erro` são terminais. O
    quinto estado que o cliente vê — `tempo_esgotado` — não está aqui porque é
    derivado (ver `ChatMessage.estado_derivado`).
    """

    PENDENTE = "pendente", "à espera de um worker"
    A_RESPONDER = "a_responder", "o modelo está a responder"
    RESPONDIDA = "respondida", "respondida"
    ERRO = "erro", "a resposta falhou"


class CodigoDeErroDaMensagem(models.TextChoices):
    """Porque é que um turno falhou (ADR 0027, decisão 4). Lista fechada."""

    TETO_DE_ITERACOES = "teto_de_iteracoes", "o modelo chamou tools demasiadas vezes"
    TETO_DE_CUSTO = "teto_de_custo", "o orçamento diário do estabelecimento esgotou-se"
    TEMPO_ESGOTADO = "tempo_esgotado", "o modelo não respondeu a tempo"
    RESPOSTA_INVALIDA = "resposta_invalida", "a resposta do modelo não se lê"
    ERRO_DO_MODELO = "erro_do_modelo", "o fornecedor do modelo recusou a chamada"
    PERTENCA_REVOGADA = "pertenca_revogada", "quem perguntou já não pertence ao estabelecimento"


class Conversation(TenantModel):
    """Uma conversa com o assistente. É **da pessoa**, não do estabelecimento.

    A resposta foi calculada com as permissões de quem perguntou, e partilhar
    transcrições no tenant mostraria a um `staff` números que só um `owner`
    pode pedir — logo os selectors filtram `created_by` ao lado da política, e
    nesta fatia nem o `owner` lê as dos outros (ADR 0027, decisão 2).

    `created_by_name` é a cópia que sobrevive à conta ser apagada, como no
    `StockMovement`. `title` é a primeira pergunta cortada a 120. `last_message_at`
    é o que ordena a lista e o que a purga compara.
    """

    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="+",
        db_index=False,
        verbose_name="criada por",
    )
    created_by_name = models.CharField(
        max_length=150, blank=True, default="", verbose_name="criada por (nome)"
    )
    title = models.CharField(max_length=120, verbose_name="título")
    last_message_at = models.DateTimeField(verbose_name="última mensagem em")

    class Meta(TenantModel.Meta):
        verbose_name = "conversa"
        verbose_name_plural = "conversas"
        indexes = [
            *TenantModel.Meta.indexes,
            # A listagem: as conversas de uma pessoa, mais recentes primeiro.
            models.Index(
                fields=["tenant", "created_by", "-last_message_at"],
                name="conversation_autor_recente_idx",
            ),
        ]

    def __str__(self) -> str:
        return self.title


class ChatMessage(TenantModel):
    """Um turno: a pergunta, a resposta, o rasto das tools e o que custou.

    ## `tool_calls` é JSON verbatim, e é lido como o `payload` da extração

    Nome, argumentos, número de linhas, truncado, milissegundos e `ok` de cada
    tool chamada, gravados à medida que acontecem. Validado **à leitura**
    (`chamadas_validadas`) e nunca comparado num `if`: é prova de como o número
    foi obtido — o rodapé "Fontes" do ecrã — e não configuração (ADR 0021,
    decisão 4; ADR 0027, decisão 1).

    ## `idempotency_key`, única globalmente

    `chat:<id da mensagem>`: a linha é a chave, logo uma segunda entrega da mesma
    tarefa encontra a linha já fora de `pendente` e não paga outra vez. Por
    chamada ao modelo a tarefa deriva `chat:<mensagem>:<iteração>` e grava-a no
    log — é registo nosso, não um contrato com a API (ADR 0027, decisão 9).

    ## `role_at_time`

    O papel de quem perguntou **no momento** da pergunta. É por ele que a lista
    de tools oferecida ao modelo é filtrada (decisão 8), e fica gravado para a
    resposta continuar explicável depois de o papel mudar.
    """

    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="messages",
        db_index=False,
        verbose_name="conversa",
    )
    position = models.PositiveSmallIntegerField(editable=False, verbose_name="posição")
    asked_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="+",
        db_index=False,
        verbose_name="perguntado por",
    )
    asked_by_name = models.CharField(
        max_length=150, blank=True, default="", verbose_name="perguntado por (nome)"
    )
    role_at_time = models.CharField(max_length=20, verbose_name="papel no momento")
    question = models.CharField(max_length=2000, verbose_name="pergunta")
    #: Um dos códigos de `LANGUAGES`: o `request.LANGUAGE_CODE` do `POST`. O
    #: prompt manda responder nesta língua (ADR 0027, decisões 1 e 4).
    language = models.CharField(max_length=10, verbose_name="língua da pergunta")
    answer = models.TextField(blank=True, default="", verbose_name="resposta")
    tool_calls = models.JSONField(
        default=list, editable=False, verbose_name="tools chamadas, verbatim"
    )
    model = models.CharField(
        max_length=100, blank=True, default="", editable=False, verbose_name="modelo chamado"
    )
    prompt_version = models.CharField(
        max_length=50, blank=True, default="", editable=False, verbose_name="versão do prompt"
    )
    idempotency_key = models.CharField(
        max_length=200, editable=False, verbose_name="chave de idempotência"
    )
    status = models.CharField(
        max_length=20,
        choices=EstadoDaMensagem.choices,
        default=EstadoDaMensagem.PENDENTE,
        editable=False,
        verbose_name="estado",
    )
    error_code = models.CharField(
        max_length=40,
        blank=True,
        default="",
        choices=CodigoDeErroDaMensagem.choices,
        editable=False,
        verbose_name="código do erro",
    )
    #: Classe e mensagem da excepção, nunca o traceback (SECURITY.md §1).
    error = models.TextField(blank=True, default="", editable=False, verbose_name="razão do erro")
    input_tokens = models.PositiveIntegerField(
        default=0, editable=False, verbose_name="tokens de entrada"
    )
    output_tokens = models.PositiveIntegerField(
        default=0, editable=False, verbose_name="tokens de saída"
    )
    iterations = models.PositiveSmallIntegerField(
        default=0, editable=False, verbose_name="chamadas ao modelo"
    )
    #: Seis casas, pela razão do `Extraction.cost_eur`: a duas, todas as
    #: chamadas custariam 0,00 €. Nunca `float` (CLAUDE.md).
    cost_eur = models.DecimalField(
        max_digits=12, decimal_places=6, default=0, editable=False, verbose_name="custo em euros"
    )
    started_at = models.DateTimeField(
        null=True, blank=True, default=None, editable=False, verbose_name="começou em"
    )
    finished_at = models.DateTimeField(
        null=True, blank=True, default=None, editable=False, verbose_name="acabou em"
    )

    class Meta(TenantModel.Meta):
        verbose_name = "mensagem do assistente"
        verbose_name_plural = "mensagens do assistente"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "conversation", "position"],
                name="chatmessage_conversa_posicao_uniq",
            ),
            models.UniqueConstraint(
                fields=["idempotency_key"],
                name="chatmessage_idempotency_key_uniq",
            ),
        ]
        indexes = [
            *TenantModel.Meta.indexes,
            # Os dois tetos diários (ADR 0027, decisão 9): perguntas por pessoa
            # e por dia, e o custo por tenant e dia — este serve-se do índice
            # herdado `(tenant, -created_at)`.
            models.Index(
                fields=["tenant", "asked_by", "-created_at"],
                name="chatmessage_autor_dia_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"turno {self.position} ({self.status})"

    @property
    def esgotou_o_tempo(self) -> bool:
        """Ainda não acabou e já passou a `JANELA_DA_RESPOSTA`.

        Conta a partir de `started_at` ou, se a tarefa nunca chegou a começar, do
        `created_at` da linha: é o caso do worker morto entre o commit e o broker,
        que de outra forma ficava `pendente` para sempre.
        """
        if self.status not in (EstadoDaMensagem.PENDENTE, EstadoDaMensagem.A_RESPONDER):
            return False
        desde = self.started_at or self.created_at
        return desde is not None and timezone.now() - desde > JANELA_DA_RESPOSTA

    @property
    def estado_derivado(self) -> str:
        """O `status` que o cliente vê: `erro` quando o relógio passou."""
        if self.esgotou_o_tempo:
            return str(EstadoDaMensagem.ERRO)
        return str(self.status)

    @property
    def codigo_de_erro_derivado(self) -> str | None:
        """O `error_code` que o cliente vê, com o `tempo_esgotado` derivado."""
        if self.esgotou_o_tempo:
            return str(CodigoDeErroDaMensagem.TEMPO_ESGOTADO)
        return self.error_code or None

    @property
    def chamadas_validadas(self) -> list[dict[str, Any]]:
        """O `tool_calls` revalidado à leitura: só as entradas com a forma certa."""
        return chamadas_validas(self.tool_calls)
