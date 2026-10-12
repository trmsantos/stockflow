"""`manage.py semear_demonstracao` — o estabelecimento de demonstração (ADR 0018).

## O que este comando é, e o que ainda não é

Cria o estabelecimento, a pertença, e — quando existem tabelas — os artigos,
fornecedores e localizações do catálogo. De fatia em fatia, o semeador cresce.

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

A semente é **fixa**: os mesmos artigos, validades e movimentos em cada corrida,
para um screenshot de hoje valer amanhã. Os UUIDs (artigos `a17e0000-…`, localizações
`c0ca0000-…`) são estáveis e fixos.

## Reinicializar nunca apaga nada

Correr isto outra vez cria um estabelecimento novo e **revoga a pertença aos
demos anteriores desta pessoa**. O caminho normal não apaga: o
`inventory_stockmovement` nasce com `REVOKE UPDATE, DELETE` ao role da app
(`SECURITY.md` §3), logo a app não consegue limpar um ledger — e é bom que não
consiga. Limpar os órfãos é tarefa de operador com o `stockflow_owner`.
"""

from decimal import Decimal
from typing import Any
from uuid import UUID

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.accounts.api import semear_demonstracao
from apps.catalog.api import (
    criar_fornecedor,
    criar_produto,
)
from apps.inventory.api import criar_localizacao

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


# ---------------------------------------------------------------------------
# Dados do catálogo (Aurora)
# ---------------------------------------------------------------------------
def _id_de_artigo(n: int) -> UUID:
    """UUID estável para artigo (a17e0000-…)."""
    return UUID(f"a17e0000-0000-4000-8000-{str(n).zfill(12)}")


def _id_de_localizacao(n: int) -> UUID:
    """UUID estável para localização (c0ca0000-…)."""
    return UUID(f"c0ca0000-0000-4000-8000-{str(n).zfill(12)}")


def _nif_valido_para_seq(n: int) -> str:
    """Gerar um NIF válido e único para a sequência de fornecedores.

    Usa a sequência 500000000 + n, calcula o dígito de controlo mod 11.
    """
    # Começa em 500000000 + n
    base = 500000000 + n
    nif_str = str(base)[:8]  # 8 dígitos

    # Calcular dígito de controlo: pesos 9..2 nos 8 primeiros, mod 11
    digitos = [int(d) for d in nif_str]
    pesos = list(range(9, 1, -1))  # [9, 8, 7, 6, 5, 4, 3, 2]
    soma = sum(d * p for d, p in zip(digitos, pesos, strict=True))
    resto = soma % 11
    digito_controlo = 11 - resto
    if digito_controlo >= 10:
        digito_controlo = 0

    return nif_str + str(digito_controlo)


def _semear_catalog(tenant_id: UUID) -> dict:
    """Semeador do catálogo: artigos, embalagens, fornecedores, localizações."""

    # Dados do aurora.ts adaptados
    artigos_dados = [
        (1, "Farinha T65", "g", "kg", 1000, None, "ambient"),
        (2, "Açúcar branco", "g", "kg", 1000, None, "ambient"),
        (3, "Ovo líquido", "g", "g", 1, None, "chilled"),
        (4, "Ovos M", "un", "un", 1, None, "ambient"),
        (5, "Manteiga", "g", "kg", 1000, "use_by", "chilled"),
        (6, "Nata 35%", "ml", "L", 1000, None, "chilled"),
        (7, "Leite UHT", "ml", "L", 1000, None, "ambient"),
        (8, "Café em grão", "g", "kg", 1000, None, "ambient"),
        (9, "Massa folhada", "g", "kg", 1000, None, "frozen"),
        (10, "Chocolate 54%", "g", "kg", 1000, None, "ambient"),
        (11, "Amêndoa laminada", "g", "g", 1, None, "ambient"),
        (12, "Morango", "g", "kg", 1000, "use_by", "chilled"),
        (13, "Fermento fresco", "g", "g", 1, None, "ambient"),
        (14, "Queijo flamengo", "g", "kg", 1000, None, "chilled"),
        (15, "Fiambre da perna", "g", "kg", 1000, None, "chilled"),
        (16, "Rissóis", "un", "un", 1, None, "frozen"),
        (17, "Óleo de fritar", "ml", "L", 1000, None, "ambient"),
        (18, "Água 0,33 L", "un", "un", 1, None, "ambient"),
        (19, "Caixas de bolo", "un", "un", 1, None, "ambient"),
        (20, "Saquetas de açúcar", "un", "un", 1, None, "ambient"),
        (21, "Bacalhau", "g", "kg", 1000, None, "frozen"),
        (22, "Pastéis de nata", "un", "un", 1, None, "ambient"),
    ]

    produtos = {}
    for n, nome, unit_base, unit_apres, fator, expiry_kind, conservacao in artigos_dados:
        produtos[n] = criar_produto(
            tenant_id=tenant_id,
            short_name=nome,
            base_unit=unit_base,
            display_unit=unit_apres,
            display_factor=Decimal(str(fator)),
            track_lots=(expiry_kind is not None),
            expiry_kind=expiry_kind or "",
            conservation=conservacao,
            id=_id_de_artigo(n),
        )

    # Fornecedores (6 no total)
    fornecedores_dados = [
        ("Makro", _nif_valido_para_seq(1)),
        ("Salsicharia Rodrigues", _nif_valido_para_seq(2)),
        ("Lacticínios Açores", _nif_valido_para_seq(3)),
        ("Frutas & Legumes", _nif_valido_para_seq(4)),
        ("Equipamentos Cozinha", _nif_valido_para_seq(5)),
        ("Chocolates Premium", _nif_valido_para_seq(6)),
    ]

    fornecedores = {}
    for i, (nome, nif) in enumerate(fornecedores_dados, 1):
        # UUIDs para fornecedores: reusamos de forma simples
        forn_uuid = UUID(f"00000000-0000-4000-8000-{str(i).zfill(12)}")
        fornecedores[i] = criar_fornecedor(
            tenant_id=tenant_id,
            name=nome,
            nif=nif,
            id=forn_uuid,
        )

    # Localizações (3 no total)
    localizacoes_dados = [
        ("Loja Centro", 0),
        ("Loja Mercado", 1),
        ("Cozinha", 2),
    ]

    localizacoes = {}
    for i, (nome, pos) in enumerate(localizacoes_dados, 1):
        localizacoes[i] = criar_localizacao(
            tenant_id=tenant_id,
            name=nome,
            position=pos,
            id=_id_de_localizacao(i),
        )

    return {
        "produtos": produtos,
        "fornecedores": fornecedores,
        "localizacoes": localizacoes,
    }


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

        # Semear o catálogo
        self.stdout.write("")
        self.stdout.write("  Semeando catálogo...")
        try:
            catalog_data = _semear_catalog(resultado.tenant.id)
            self.stdout.write(
                self.style.SUCCESS(
                    f"    {len(catalog_data['produtos'])} artigos, "
                    f"{len(catalog_data['fornecedores'])} fornecedores, "
                    f"{len(catalog_data['localizacoes'])} localizações"
                )
            )
        except Exception as erro:
            self.stdout.write(
                self.style.ERROR(f"  Erro ao semear catálogo: {erro}")
            )
            raise CommandError(f"Erro ao semear catálogo: {erro}") from erro
