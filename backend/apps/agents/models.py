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
"""

from __future__ import annotations

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.shared.models import TenantModel

__all__ = ["EstadoDaExtracao", "Extraction"]


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
