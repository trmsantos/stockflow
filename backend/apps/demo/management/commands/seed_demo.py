"""`manage.py seed_demo` — semear dados de teste para Increment 1.

Cria um tenant, utilizadores, 50 produtos, localizações, 10 movimentos de stock,
2 receções (1 confirmada, 1 em revisão) com dados reais para validar endpoints.

Uso:
    uv run manage.py seed_demo --create-tenant                 # Cria tenant novo
    uv run manage.py seed_demo --tenant-id <uuid>              # Usa tenant existente
    uv run manage.py seed_demo --list                          # Lista tenants e seus IDs

Determinismo: os UUIDs, nomes e quantidades são fixos para reprodutibilidade.
Idempotência: não cria duplicados (procura por tenant_id primeiro).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.utils import timezone

from apps.accounts.models import Membership, Papel, Tenant, User
from apps.catalog.models import Conservacao, Product, Supplier, UnidadeBase
from apps.inventory.models import Location, StockLevel, StockMovement
from apps.purchasing.models import InvoiceDocument, Receipt, ReceiptLine
from apps.shared.db import tenant_scope

__all__ = ["Command"]


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
    """Django command para semear dados de teste."""

    help = "Semeia dados de teste: tenant, users, produtos, movimentos, receções"

    def add_arguments(self, parser: CommandParser) -> None:
        """Argumentos do comando."""
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument(
            "--create-tenant",
            action="store_true",
            help="Cria um tenant novo com UUID gerado aleatoriamente",
        )
        group.add_argument(
            "--tenant-id",
            type=str,
            help="Usa um tenant existente (passa o UUID)",
        )
        group.add_argument(
            "--list",
            action="store_true",
            help="Lista todos os tenants de demonstração",
        )

        parser.add_argument(
            "--name",
            default="Demo Resto",
            help="Nome do tenant (só com --create-tenant). Padrão: 'Demo Resto'",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Handler principal do comando."""
        if options["list"]:
            self._listar_tenants()
            return

        try:
            if options["create_tenant"]:
                tenant_id = uuid4()
                result = self._semear_novo(
                    tenant_id=tenant_id,
                    nome=options["name"],
                )
            else:
                tenant_id = UUID(options["tenant_id"])
                result = self._semear_existente(tenant_id=tenant_id)

            self._imprimir_resultado(result)
        except Exception as erro:
            raise CommandError(f"Erro ao semear: {erro}") from erro

    # -----------------------------------------------------------------------
    # Semear novo tenant
    # -----------------------------------------------------------------------

    def _semear_novo(self, *, tenant_id: UUID, nome: str) -> SeedResult:
        """Cria tenant novo, users e todos os dados de teste."""
        # 1. Criar tenant
        tenant = Tenant.objects.create(
            id=tenant_id,
            name=nome,
            is_demo=True,
        )
        self.stdout.write(f"✓ Tenant criado: {tenant.id} ({nome})")

        # 2. Criar users
        owner = User.objects.create_user(
            email="owner@demo.pt",
            password="DemoPassword123!",
            is_active=True,
        )
        staff = User.objects.create_user(
            email="staff@demo.pt",
            password="DemoPassword123!",
            is_active=True,
        )
        self.stdout.write("✓ Users criados: owner@demo.pt, staff@demo.pt")

        # 3. Criar memberships
        with tenant_scope(tenant.id):
            Membership.objects.create(
                user=owner,
                tenant=tenant,
                role=Papel.OWNER,
                display_name="Dono",
                is_active=True,
            )
            Membership.objects.create(
                user=staff,
                tenant=tenant,
                role=Papel.STAFF,
                display_name="Colaborador",
                is_active=True,
            )
            self.stdout.write("✓ Memberships criados")

        # 4. Semear resto
        return self._semear_existente(tenant_id=tenant.id)

    def _semear_existente(self, *, tenant_id: UUID) -> SeedResult:
        """Semeia dados de teste num tenant existente."""
        try:
            tenant = Tenant.objects.get(id=tenant_id)
        except Tenant.DoesNotExist as erro:
            raise CommandError(f"Tenant {tenant_id} não existe") from erro

        # Pegar users
        owner_user = User.objects.get(memberships__tenant=tenant, memberships__role=Papel.OWNER)
        staff_user = User.objects.get(memberships__tenant=tenant, memberships__role=Papel.STAFF)

        with tenant_scope(tenant.id):
            # 5. Semear catálogo: 50 produtos (30 ingredientes, 10 pratos, 10 bebidas)
            product_ids = self._semear_produtos(tenant)
            self.stdout.write(f"✓ {len(product_ids)} produtos criados")

            # 6. Semear 3 localizações
            location_ids = self._semear_localizacoes(tenant)
            self.stdout.write(f"✓ {len(location_ids)} localizações criadas")

            # 7. Semear 3 fornecedores
            supplier_ids = self._semear_fornecedores(tenant)
            self.stdout.write(f"✓ {len(supplier_ids)} fornecedores criados")

            # 8. Semear 10 movimentos de stock (entrada/saída)
            stock_movement_ids = self._semear_movimentos(tenant, product_ids, location_ids, owner_user)
            self.stdout.write(f"✓ {len(stock_movement_ids)} movimentos criados")

            # 9. Semear 2 receções (1 confirmada, 1 em revisão)
            receipt_ids = self._semear_receções(tenant, product_ids, supplier_ids, owner_user)
            self.stdout.write(f"✓ {len(receipt_ids)} receções criadas")

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

    def _semear_produtos(self, tenant: Tenant) -> list[UUID]:
        """Semeia 50 produtos: 30 ingredientes, 10 pratos, 10 bebidas."""
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
        for idx, (nome, unit_base, unit_apres, fator, expiry, conservacao) in enumerate(
            produtos_dados, 1
        ):
            # UUID estável para produto
            product_id = UUID(f"a17e0000-0000-4000-8000-{str(idx).zfill(12)}")

            # Verificar se já existe
            if Product.objects.filter(id=product_id, tenant=tenant).exists():
                product_ids.append(product_id)
                continue

            product = Product.objects.create(
                id=product_id,
                tenant=tenant,
                short_name=nome,
                base_unit=unit_base,
                display_unit=unit_apres,
                display_factor=Decimal(str(fator)),
                track_lots=(expiry != ""),
                expiry_kind=expiry,
                conservation=conservacao,
                min_quantity=Decimal("10"),
            )
            product_ids.append(product.id)

        return product_ids

    def _semear_localizacoes(self, tenant: Tenant) -> list[UUID]:
        """Semeia 3 localizações: Armazém, Cozinha, Sala."""
        localizacoes = [
            ("Armazém", 0),
            ("Cozinha", 1),
            ("Sala", 2),
        ]

        location_ids = []
        for idx, (nome, posicao) in enumerate(localizacoes, 1):
            location_id = UUID(f"c0ca0000-0000-4000-8000-{str(idx).zfill(12)}")

            if Location.objects.filter(id=location_id, tenant=tenant).exists():
                location_ids.append(location_id)
                continue

            location = Location.objects.create(
                id=location_id,
                tenant=tenant,
                name=nome,
                position=posicao,
                is_active=True,
            )
            location_ids.append(location.id)

        return location_ids

    def _semear_fornecedores(self, tenant: Tenant) -> list[UUID]:
        """Semeia 3 fornecedores com NIFs válidos."""
        fornecedores = [
            ("Makro Portugal", "500000001"),
            ("Salsicharia Rodrigues", "500000002"),
            ("Lacticínios Açores", "500000003"),
        ]

        supplier_ids = []
        for idx, (nome, nif) in enumerate(fornecedores, 1):
            supplier_id = UUID(f"f0ff0000-0000-4000-8000-{str(idx).zfill(12)}")

            if Supplier.objects.filter(id=supplier_id, tenant=tenant).exists():
                supplier_ids.append(supplier_id)
                continue

            supplier = Supplier.objects.create(
                id=supplier_id,
                tenant=tenant,
                name=nome,
                nif=nif,
            )
            supplier_ids.append(supplier.id)

        return supplier_ids

    def _semear_movimentos(
        self,
        tenant: Tenant,
        product_ids: list[UUID],
        location_ids: list[UUID],
        user: User,
    ) -> list[UUID]:
        """Semeia 10 movimentos de stock (entrada/saída)."""
        movement_ids = []
        now = timezone.now()

        for idx in range(10):
            product_id = product_ids[idx % len(product_ids)]
            location_id = location_ids[idx % len(location_ids)]
            product = Product.objects.get(id=product_id, tenant=tenant)
            location = Location.objects.get(id=location_id, tenant=tenant)

            movement_type = "receipt" if idx % 2 == 0 else "consumption"
            quantity = Decimal("100" if idx % 2 == 0 else "-50")
            unit_cost = Decimal("1.50") if idx % 2 == 0 else Decimal("2.00")
            reference = f"DOC-{idx:04d}" if movement_type == "receipt" else None
            occurred_at = now - timedelta(days=9 - idx)

            movement = StockMovement.objects.create(
                tenant=tenant,
                product=product,
                location=location,
                movement_type=movement_type,
                quantity=quantity,
                unit_cost=unit_cost,
                cost_is_estimate=False,
                reference=reference,
                occurred_at=occurred_at,
                created_by=user,
                created_by_name=user.email,
            )
            movement_ids.append(movement.id)

            # Criar StockLevel para este (product, location)
            StockLevel.objects.get_or_create(
                tenant=tenant,
                product=product,
                location=location,
                lot=None,
                defaults={
                    "quantity": quantity,
                    "unit_cost": unit_cost,
                },
            )

        return movement_ids

    def _semear_receções(
        self,
        tenant: Tenant,
        product_ids: list[UUID],
        supplier_ids: list[UUID],
        user: User,
    ) -> list[UUID]:
        """Semeia 2 receções: 1 confirmada, 1 em revisão."""
        receipt_ids = []

        for receipt_idx in range(2):
            # Criar documento de fatura
            doc = InvoiceDocument.objects.create(
                tenant=tenant,
                origin="upload",
            )

            # Criar receção
            supplier_id = supplier_ids[receipt_idx % len(supplier_ids)]
            supplier = Supplier.objects.get(id=supplier_id, tenant=tenant)

            receipt = Receipt.objects.create(
                tenant=tenant,
                supplier=supplier,
                document=doc,
                status="draft" if receipt_idx == 1 else "confirmed",
            )
            receipt_ids.append(receipt.id)

            # Adicionar 2-3 linhas por receção
            for line_idx in range(2 + receipt_idx):
                product_id = product_ids[(receipt_idx * 2 + line_idx) % len(product_ids)]
                product = Product.objects.get(id=product_id, tenant=tenant)

                ReceiptLine.objects.create(
                    receipt=receipt,
                    product=product,
                    quantity=Decimal("50") * (line_idx + 1),
                    unit_price=Decimal("1.50") + Decimal(line_idx),
                    description=f"Linha {line_idx + 1} de {product.short_name}",
                )

        return receipt_ids

    # -----------------------------------------------------------------------
    # Listar e imprimir
    # -----------------------------------------------------------------------

    def _listar_tenants(self) -> None:
        """Lista todos os tenants de demonstração."""
        tenants = Tenant.objects.filter(is_demo=True).order_by("-created_at")

        if not tenants.exists():
            self.stdout.write("Nenhum tenant de demonstração encontrado.")
            return

        self.stdout.write(self.style.WARNING("Tenants de demonstração:"))
        for tenant in tenants:
            memberships = Membership.objects.filter(tenant=tenant, is_active=True).select_related(
                "user"
            )
            emails = ", ".join(m.user.email for m in memberships)
            self.stdout.write(f"  {tenant.id}  {tenant.name}")
            self.stdout.write(f"    Memberships: {emails}")

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
