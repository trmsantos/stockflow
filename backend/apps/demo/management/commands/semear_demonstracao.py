"""`manage.py semear_demonstracao` — o estabelecimento de demonstração (ADR 0018).

## O que este comando é, e o que ainda não é

Hoje cria o estabelecimento e a pertença, e mais nada — **porque mais nada
existe**: o `catalog`, o `inventory`, o `purchasing` e o `recipes` são conchas
(zero models, zero migrações). Os artigos, os lotes, as validades, os movimentos,
a contagem com divergência e o desperdício com motivo entram quando as tabelas
entrarem, e entram **por aqui**, pela porta da frente de cada módulo.

Isso é decisão da ADR 0018 e não uma limitação temporária que se contorna: um
semeador que escreva `StockLevel` à mão produz um estabelecimento que **ensina um
produto que não existe** — stock sem ledger, lotes sem FEFO, custo sem CMP. O que
o import-linter garante é que, quando chegar a hora, não há atalho: de fora, este
módulo só alcança os `api.py`.

## O que falta antes dos dados, e é uma consulta e não código

Os valores do semeador são **afirmações de domínio** — que artigos, em que
unidades, com que validades, a que preços de fornecedor — e a ADR 0018 manda
consultar o `domain-expert` para eles. Um demo que mostre números que um pasteleiro
não reconhece é pior do que não ter demo. A consulta faz-se quando houver tabelas
onde pôr as respostas.

## Determinismo

Quando houver dados, a semente é **fixa**: os mesmos artigos, validades e
movimentos em cada corrida, para um screenshot de hoje valer amanhã. Hoje a única
coisa não determinística é o uuid do estabelecimento, e é de propósito —
reinicializar é criar outro (ver abaixo).

## Reinicializar nunca apaga nada

Correr isto outra vez cria um estabelecimento novo e **revoga a pertença aos
demos anteriores desta pessoa**. O caminho normal não apaga: o
`inventory_stockmovement` nasce com `REVOKE UPDATE, DELETE` ao role da app
(`SECURITY.md` §3), logo a app não consegue limpar um ledger — e é bom que não
consiga. Limpar os órfãos é tarefa de operador com o `stockflow_owner`.
"""

from typing import Any

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.accounts.api import semear_demonstracao

#: O nome por omissão. **É um exemplo e não uma decisão** — a ADR 0018 deixa o
#: nome "por decidir" porque é copy e é do dono do produto.
#:
#: O que o valor tem de cumprir está decidido: a decisão 8 diz que o que limita
#: alguém a registar no demo uma quebra que era a sério é "a faixa permanente, o
#: seletor marcado e o facto de o demo **ter um nome que não é o do
#: estabelecimento da pessoa**". Daí a palavra no nome, e daí o
#: `/configuracao` recusar alterá-lo num demo.
NOME_POR_OMISSAO = "Pastelaria de Demonstração"

#: O nome da pessoa **neste** estabelecimento. A mesma pessoa tem outro no seu.
RESPONSAVEL_POR_OMISSAO = "A experimentar"


class Command(BaseCommand):
    help = (
        "Cria um estabelecimento de demonstração e dá-o a uma conta que já existe. "
        "Correr outra vez cria um novo e revoga a pertença aos anteriores."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--email",
            required=True,
            help=(
                "Email de quem vai experimentar. A conta tem de existir — o demo "
                "não cria contas (ADR 0018, decisão 6)."
            ),
        )
        parser.add_argument(
            "--nome",
            default=NOME_POR_OMISSAO,
            help=f"Nome do estabelecimento no seletor. Por omissão: {NOME_POR_OMISSAO!r}.",
        )
        parser.add_argument(
            "--responsavel",
            default=RESPONSAVEL_POR_OMISSAO,
            help=(
                "Nome desta pessoa **neste** estabelecimento. Por omissão: "
                f"{RESPONSAVEL_POR_OMISSAO!r}."
            ),
        )

    def handle(self, *args: Any, **options: Any) -> None:
        try:
            resultado = semear_demonstracao(
                email=options["email"],
                nome=options["nome"],
                display_name=options["responsavel"],
            )
        except ValidationError as erro:
            # `CommandError` e não traceback: um email que não existe é entrada
            # do operador a ser recusada, não um defeito.
            raise CommandError("; ".join(erro.messages)) from erro

        self.stdout.write(
            self.style.SUCCESS(f"Demonstração semeada: {resultado.tenant.name}")
        )
        self.stdout.write(f"  tenant_id: {resultado.tenant.id}")
        self.stdout.write(f"  conta:     {resultado.user.email}")

        for revogado in resultado.revogados:
            self.stdout.write(
                self.style.WARNING(f"  revogado:  {revogado} (demo anterior desta conta)")
            )
        if resultado.revogados:
            self.stdout.write(
                "  Os anteriores ficam inalcançáveis (403 no TenantMiddleware) e as "
                "linhas ficam lá até um operador as limpar."
            )

        self.stdout.write("")
        self.stdout.write(
            self.style.WARNING(
                "  Sem dados de domínio: o catalog, o inventory e o purchasing ainda "
                "não têm tabelas. O estabelecimento abre vazio."
            )
        )
