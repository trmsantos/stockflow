"""`manage.py seed_demo` — dados de desenvolvimento para o frontend real.

Três lojas, com as mesmas três contas em todas — uma por papel — e, em cada
loja, 50 produtos, 3 localizações, 3 fornecedores, 10 movimentos de stock e
2 receções (1 confirmada, 1 em revisão).

Uso:
    uv run manage.py seed_demo --create-tenant        # as três lojas e as contas
    uv run manage.py seed_demo --tenant-id <uuid>     # só os dados, num tenant existente
    uv run manage.py seed_demo --list                 # as lojas das contas de demo

Contas (password `DemoPassword123!`, ou a de `--password` ao criar): owner@demo.pt (dono), manager@demo.pt
(gerente), staff@demo.pt (colaborador).

Idempotente nas lojas, contas, pertenças, produtos, localizações e fornecedores:
os UUIDs das lojas são fixos, as pertenças passam pelo `conceder_pertenca` (que
também espelha `User.tenant_ids` — sem isso o login não encontra a loja) e o
catálogo é procurado pelo nome antes de ser criado. Os movimentos e as receções
são um ledger e acrescentam-se a cada execução.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.utils import timezone

from apps.accounts.api import (
    Papel,
    criar_membership,
    criar_tenant,
    criar_usuario,
    obter_usuario_por_papel,
)
from apps.catalog.api import criar_fornecedor, criar_produto
from apps.inventory.api import MovementDTO, criar_localizacao, record_movements
from apps.purchasing.api import adicionar_linha_recepção, criar_receçao
from apps.shared.db import tenant_scope

__all__ = ["Command"]

#: (email, papel, nome exibido). As mesmas contas em todas as lojas.
CONTAS_DE_DEMO: tuple[tuple[str, str, str], ...] = (
    ("owner@demo.pt", Papel.OWNER, "Dono"),
    ("manager@demo.pt", Papel.MANAGER, "Gerente"),
    ("staff@demo.pt", Papel.STAFF, "Colaborador"),
)

LOJAS_DE_DEMO = ("Loja Chiado", "Loja Amoreiras", "Loja Colombo")


def _id_da_loja(indice: int) -> UUID:
    return UUID(f"00000000-0000-4000-8000-{indice + 1:012d}")


@dataclass
class SeedResult:
    """Resultado de uma semeação."""

    tenant_id: UUID
    owner_user_id: UUID
    staff_user_id: UUID
    product_ids: list[UUID]
    location_ids: list[UUID]
    supplier_ids: list[UUID]
    receipt_ids: list[UUID]
    stock_movement_ids: list[UUID]


class Command(BaseCommand):
    """Django command para semear dados de desenvolvimento."""

    help = "Semeia as lojas de demo: contas, pertenças, catálogo, movimentos e receções"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # `display_factor` por artigo, para converter o preço de apresentação
        # (por kg/L) em custo por unidade base (g/mL) — o que o ledger guarda.
        self._fator_de_apresentacao: dict[UUID, Decimal] = {}

    def add_arguments(self, parser: CommandParser) -> None:
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument(
            "--create-tenant",
            action="store_true",
            help="Cria (ou reutiliza) as três lojas de demo com as três contas",
        )
        group.add_argument(
            "--tenant-id",
            type=str,
            help="Semeia só os dados num tenant existente (passa o UUID)",
        )
        group.add_argument(
            "--list",
            action="store_true",
            help="Lista as lojas a que as contas de demo pertencem",
        )
        parser.add_argument(
            "--password",
            default="DemoPassword123!",
            help="Password das contas de demo quando são criadas (default: DemoPassword123!)",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        if options["list"]:
            self._listar_tenants()
            return

        try:
            if options["create_tenant"]:
                self._semear_lojas(password=options["password"])
            else:
                result = self._semear_existente(tenant_id=UUID(options["tenant_id"]))
                self._imprimir_resultado(result)
        except Exception as erro:
            raise CommandError(f"Erro ao semear: {erro}") from erro

    # -----------------------------------------------------------------------
    # As três lojas, com as mesmas contas
    # -----------------------------------------------------------------------

    def _semear_lojas(self, *, password: str) -> None:
        utilizadores = [
            (criar_usuario(email=email, password=password), papel, nome)
            for email, papel, nome in CONTAS_DE_DEMO
        ]
        self.stdout.write("✓ Contas: " + ", ".join(email for email, _, _ in CONTAS_DE_DEMO))

        for indice, nome_da_loja in enumerate(LOJAS_DE_DEMO):
            tenant = criar_tenant(name=nome_da_loja, id=_id_da_loja(indice))
            # Dentro do âmbito da loja: é a política de `accounts_membership` que
            # o exige, e o `conceder_pertenca` recusa escrever fora dele.
            with tenant_scope(tenant.id):
                for user, papel, display_name in utilizadores:
                    criar_membership(
                        user_id=user.id,
                        tenant_id=tenant.id,
                        role=papel,
                        display_name=display_name,
                    )
            result = self._semear_existente(tenant_id=tenant.id)
            self.stdout.write(
                f"✓ {nome_da_loja} ({tenant.id}): {len(result.product_ids)} produtos, "
                f"{len(result.location_ids)} localizações, {len(result.supplier_ids)} fornecedores, "
                f"+{len(result.stock_movement_ids)} movimentos, +{len(result.receipt_ids)} receções"
            )

    def _semear_existente(self, *, tenant_id: UUID) -> SeedResult:
        """Semeia os dados num tenant que já tem dono e colaborador."""
        from apps.accounts.models import Tenant

        with tenant_scope(tenant_id):
            try:
                tenant = Tenant.objects.get(id=tenant_id)
            except Tenant.DoesNotExist as erro:
                raise CommandError(f"Tenant {tenant_id} não existe") from erro

            owner_user = obter_usuario_por_papel(tenant_id=tenant_id, role=Papel.OWNER)
            staff_user = obter_usuario_por_papel(tenant_id=tenant_id, role=Papel.STAFF)

            product_ids = self._semear_produtos(tenant)
            location_ids = self._semear_localizacoes(tenant)
            supplier_ids = self._semear_fornecedores(tenant)
            stock_movement_ids = self._semear_movimentos(
                tenant, product_ids, location_ids, owner_user
            )
            receipt_ids = self._semear_receções(
                tenant, product_ids, supplier_ids, location_ids, owner_user
            )

            return SeedResult(
                tenant_id=tenant.id,
                owner_user_id=owner_user.id,
                staff_user_id=staff_user.id,
                product_ids=product_ids,
                location_ids=location_ids,
                supplier_ids=supplier_ids,
                receipt_ids=receipt_ids,
                stock_movement_ids=stock_movement_ids,
            )

    # -----------------------------------------------------------------------
    # Semear componentes
    # -----------------------------------------------------------------------

    def _semear_produtos(self, tenant) -> list[UUID]:
        """Semeia 50 produtos: 30 ingredientes, 10 pratos, 10 bebidas."""
        from apps.catalog.models import Conservacao, UnidadeBase

        produtos_dados = [
            # Ingredientes (30)
            ("Farinha T65", UnidadeBase.GRAMA, "kg", 1000, "", Conservacao.AMBIENT),
            ("Açúcar branco", UnidadeBase.GRAMA, "kg", 1000, "", Conservacao.AMBIENT),
            ("Ovo líquido", UnidadeBase.GRAMA, "g", 1, "", Conservacao.CHILLED),
            ("Ovos M", UnidadeBase.UNIDADE, "un", 1, "", Conservacao.AMBIENT),
            ("Manteiga", UnidadeBase.GRAMA, "kg", 1000, "use_by", Conservacao.CHILLED),
            ("Nata 35%", UnidadeBase.MILILITRO, "L", 1000, "", Conservacao.CHILLED),
            ("Leite UHT", UnidadeBase.MILILITRO, "L", 1000, "", Conservacao.AMBIENT),
            ("Café em grão", UnidadeBase.GRAMA, "kg", 1000, "", Conservacao.AMBIENT),
            ("Massa folhada", UnidadeBase.GRAMA, "kg", 1000, "", Conservacao.FROZEN),
            ("Chocolate 54%", UnidadeBase.GRAMA, "kg", 1000, "", Conservacao.AMBIENT),
            ("Amêndoa laminada", UnidadeBase.GRAMA, "g", 1, "", Conservacao.AMBIENT),
            ("Morango fresco", UnidadeBase.GRAMA, "kg", 1000, "use_by", Conservacao.CHILLED),
            ("Fermento fresco", UnidadeBase.GRAMA, "g", 1, "", Conservacao.AMBIENT),
            ("Queijo flamengo", UnidadeBase.GRAMA, "kg", 1000, "", Conservacao.CHILLED),
            ("Fiambre da perna", UnidadeBase.GRAMA, "kg", 1000, "", Conservacao.CHILLED),
            ("Óleo de fritar", UnidadeBase.MILILITRO, "L", 1000, "", Conservacao.AMBIENT),
            ("Água 0,33 L", UnidadeBase.UNIDADE, "un", 1, "", Conservacao.AMBIENT),
            ("Caixas de bolo", UnidadeBase.UNIDADE, "un", 1, "", Conservacao.AMBIENT),
            ("Saquetas de açúcar", UnidadeBase.UNIDADE, "un", 1, "", Conservacao.AMBIENT),
            ("Bacalhau", UnidadeBase.GRAMA, "kg", 1000, "", Conservacao.FROZEN),
            ("Sal fino", UnidadeBase.GRAMA, "kg", 1000, "", Conservacao.AMBIENT),
            ("Fermento em pó", UnidadeBase.GRAMA, "kg", 1000, "", Conservacao.AMBIENT),
            ("Baunilha", UnidadeBase.MILILITRO, "L", 1000, "", Conservacao.AMBIENT),
            ("Corante alimentar", UnidadeBase.MILILITRO, "L", 1000, "", Conservacao.AMBIENT),
            ("Calda de baunilha", UnidadeBase.MILILITRO, "L", 1000, "", Conservacao.AMBIENT),
            ("Cobertura de chocolate", UnidadeBase.GRAMA, "kg", 1000, "", Conservacao.AMBIENT),
            ("Canela em pó", UnidadeBase.GRAMA, "kg", 1000, "", Conservacao.AMBIENT),
            ("Essência de baunilha", UnidadeBase.MILILITRO, "L", 1000, "", Conservacao.AMBIENT),
            ("Nozes", UnidadeBase.GRAMA, "kg", 1000, "", Conservacao.AMBIENT),
            ("Passas", UnidadeBase.GRAMA, "kg", 1000, "use_by", Conservacao.AMBIENT),
            # Pratos (10)
            ("Pastel de Nata", UnidadeBase.UNIDADE, "un", 1, "use_by", Conservacao.FROZEN),
            ("Bolo de Chocolate", UnidadeBase.UNIDADE, "un", 1, "use_by", Conservacao.CHILLED),
            ("Croissant de Amêndoa", UnidadeBase.UNIDADE, "un", 1, "use_by", Conservacao.AMBIENT),
            ("Pão de Queijo", UnidadeBase.UNIDADE, "un", 1, "use_by", Conservacao.CHILLED),
            ("Tarte de Maçã", UnidadeBase.UNIDADE, "un", 1, "use_by", Conservacao.CHILLED),
            ("Éclair de Chocolate", UnidadeBase.UNIDADE, "un", 1, "use_by", Conservacao.CHILLED),
            ("Mousse de Frutos Vermelhos", UnidadeBase.UNIDADE, "un", 1, "use_by", Conservacao.CHILLED),
            ("Cheesecake", UnidadeBase.UNIDADE, "un", 1, "use_by", Conservacao.CHILLED),
            ("Brownie", UnidadeBase.UNIDADE, "un", 1, "use_by", Conservacao.AMBIENT),
            ("Muffin de Blueberry", UnidadeBase.UNIDADE, "un", 1, "use_by", Conservacao.AMBIENT),
            # Bebidas (10)
            ("Café Espresso", UnidadeBase.MILILITRO, "mL", 1, "", Conservacao.AMBIENT),
            ("Cappuccino", UnidadeBase.MILILITRO, "mL", 1, "", Conservacao.AMBIENT),
            ("Chá Preto", UnidadeBase.MILILITRO, "mL", 1, "", Conservacao.AMBIENT),
            ("Sumo de Laranja", UnidadeBase.MILILITRO, "L", 1000, "use_by", Conservacao.CHILLED),
            ("Sumo de Maçã", UnidadeBase.MILILITRO, "L", 1000, "use_by", Conservacao.AMBIENT),
            ("Água com Gás", UnidadeBase.MILILITRO, "L", 1000, "", Conservacao.AMBIENT),
            ("Refrigerante Cola", UnidadeBase.MILILITRO, "L", 1000, "", Conservacao.AMBIENT),
            ("Milkshake de Baunilha", UnidadeBase.MILILITRO, "L", 1000, "use_by", Conservacao.CHILLED),
            ("Smoothie de Frutas", UnidadeBase.MILILITRO, "L", 1000, "use_by", Conservacao.CHILLED),
            ("Vinho Tinto", UnidadeBase.MILILITRO, "L", 1000, "best_before", Conservacao.AMBIENT),
        ]

        product_ids = []
        for nome, unit_base, unit_apres, fator, expiry, conservacao in produtos_dados:
            # Criar via API (sem ID fixo para evitar conflitos)
            produto = criar_produto(
                tenant_id=tenant.id,
                short_name=nome,
                base_unit=unit_base,
                display_unit=unit_apres,
                display_factor=Decimal(str(fator)),
                track_lots=(expiry != ""),
                expiry_kind=expiry if expiry else None,
                conservation=conservacao,
                id=None,  # deixar gerar UUID automaticamente
            )
            product_ids.append(produto.id)
            self._fator_de_apresentacao[produto.id] = produto.display_factor

        return product_ids

    def _semear_localizacoes(self, tenant) -> list[UUID]:
        """Semeia 3 localizações: Armazém, Cozinha, Sala."""
        localizacoes = [
            ("Armazém", 0),
            ("Cozinha", 1),
            ("Sala", 2),
        ]

        location_ids = []
        for nome, posicao in localizacoes:
            # Criar via API (sem ID fixo)
            localizacao = criar_localizacao(
                tenant_id=tenant.id,
                name=nome,
                position=posicao,
                id=None,
            )
            location_ids.append(localizacao.id)

        return location_ids

    def _semear_fornecedores(self, tenant) -> list[UUID]:
        """Semeia 3 fornecedores com NIFs válidos."""
        fornecedores = [
            ("Makro Portugal", "500000001"),
            ("Salsicharia Rodrigues", "500000002"),
            ("Lacticínios Açores", "500000003"),
        ]

        supplier_ids = []
        for nome, nif in fornecedores:
            # Criar via API (sem ID fixo)
            fornecedor = criar_fornecedor(
                tenant_id=tenant.id,
                name=nome,
                nif=nif,
                id=None,
            )
            supplier_ids.append(fornecedor.id)

        return supplier_ids

    def _semear_movimentos(
        self,
        tenant,
        product_ids: list[UUID],
        location_ids: list[UUID],
        user,
    ) -> list[UUID]:
        """Semeia 10 movimentos de stock (entrada/saída)."""
        movement_ids = []
        now = timezone.now()

        for idx in range(10):
            product_id = product_ids[idx % len(product_ids)]
            location_id = location_ids[idx % len(location_ids)]

            movement_type = "receipt" if idx % 2 == 0 else "consumption"
            quantity = Decimal("100" if idx % 2 == 0 else "-50")
            # O preço é por unidade de apresentação (1,50 €/kg, 2,00 €/L); o ledger
            # guarda-o por unidade **base** (g, mL), senão 1,1 kg de farinha valem 1650 €.
            preco_de_apresentacao = Decimal("1.50") if idx % 2 == 0 else Decimal("2.00")
            fator = self._fator_de_apresentacao.get(product_id, Decimal("1"))
            unit_cost = (preco_de_apresentacao / fator).quantize(Decimal("0.000001"))
            reference = f"DOC-{idx:04d}" if movement_type == "receipt" else ""
            occurred_at = now - timedelta(days=9 - idx)

            # Criar movimento via API
            movimento = MovementDTO(
                product_id=product_id,
                location_id=location_id,
                lot_id=None,
                movement_type=movement_type,
                quantity=quantity,
                unit_cost=unit_cost,
                cost_is_estimate=False,
                reference=reference,
                occurred_at=occurred_at,
                created_by_id=user.id,
                created_by_name=user.email,
            )

            movement_ids_returned = record_movements(
                tenant_id=tenant.id,
                movements=[movimento],
            )
            movement_ids.extend(movement_ids_returned)

        return movement_ids

    def _semear_receções(
        self,
        tenant,
        product_ids: list[UUID],
        supplier_ids: list[UUID],
        location_ids: list[UUID],
        user,
    ) -> list[UUID]:
        """Semeia 2 receções: 1 confirmada, 1 em revisão."""
        receipt_ids = []

        for receipt_idx in range(2):
            # Criar receção via API
            supplier_id = supplier_ids[receipt_idx % len(supplier_ids)]
            status = "draft" if receipt_idx == 1 else "confirmed"

            receçao = criar_receçao(
                tenant_id=tenant.id,
                supplier_id=supplier_id,
                location_id=location_ids[0],
                status=status,
            )
            receipt_ids.append(receçao.id)

            # Adicionar 2-3 linhas por receção via API
            for line_idx in range(2 + receipt_idx):
                product_id = product_ids[(receipt_idx * 2 + line_idx) % len(product_ids)]

                # Obter nome do produto para a descrição
                from apps.catalog.api import produtos_por_id

                produtos = produtos_por_id(tenant_id=tenant.id, ids=[product_id])
                nome_produto = produtos[product_id].short_name if product_id in produtos else "Produto"

                adicionar_linha_recepção(
                    tenant_id=tenant.id,
                    receipt_id=receçao.id,
                    product_id=product_id,
                    quantity=Decimal("50") * (line_idx + 1),
                    unit_price=Decimal("1.50") + Decimal(line_idx),
                    description=f"Linha {line_idx + 1} de {nome_produto}",
                )

        return receipt_ids

    # -----------------------------------------------------------------------
    # Listar e imprimir
    # -----------------------------------------------------------------------

    def _listar_tenants(self) -> None:
        """As lojas das contas de demo, cada uma lida dentro do seu âmbito."""
        from apps.accounts.models import Membership, Tenant, User

        vistos: set[UUID] = set()
        for email, _, _ in CONTAS_DE_DEMO:
            try:
                user = User.objects.get_by_natural_key(email)
            except User.DoesNotExist:
                continue
            for tenant_id in user.tenant_ids:
                if tenant_id in vistos:
                    continue
                vistos.add(tenant_id)
                with tenant_scope(tenant_id):
                    tenant = Tenant.objects.get(pk=tenant_id)
                    emails = ", ".join(
                        Membership.objects.filter(tenant=tenant, is_active=True)
                        .order_by("role")
                        .values_list("user__email", flat=True)
                    )
                self.stdout.write(f"  {tenant.id}  {tenant.name}")
                self.stdout.write(f"    Pertenças: {emails}")

        if not vistos:
            self.stdout.write("Nenhuma loja de demo encontrada.")

    def _imprimir_resultado(self, result: SeedResult) -> None:
        """Imprime o resultado da semeação."""
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=== Semeação Concluída ==="))
        self.stdout.write(f"tenant_id:              {result.tenant_id}")
        self.stdout.write(f"owner_user_id:          {result.owner_user_id}")
        self.stdout.write(f"staff_user_id:          {result.staff_user_id}")
        self.stdout.write(f"products:               {len(result.product_ids)} criados")
        self.stdout.write(f"locations:              {len(result.location_ids)} criadas")
        self.stdout.write(f"suppliers:              {len(result.supplier_ids)} criados")
        self.stdout.write(f"stock_movements:        {len(result.stock_movement_ids)} criados")
        self.stdout.write(f"receipts:               {len(result.receipt_ids)} criadas")
        self.stdout.write("")
        self.stdout.write("Primeiro product_id:    " + str(result.product_ids[0]) if result.product_ids else "N/A")
        self.stdout.write("Primeiro location_id:   " + str(result.location_ids[0]) if result.location_ids else "N/A")
