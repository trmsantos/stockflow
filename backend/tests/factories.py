"""Factories para criar dados de teste, idempotentes e reutilizáveis.

Usa pytest fixtures, não factory_boy, para manter a simplicidade e ligação
direta à estrutura de modelos do projeto. Cada factory é uma função que
retorna uma instância do modelo ou um dataclass com os dados criados.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from django.utils import timezone

from apps.accounts.models import Invitation, Membership, Papel, Tenant, User
from apps.accounts.services import criar_tenant
from apps.catalog.models import (
    Conservacao,
    Product,
    Supplier,
    SupplierProductCode,
    UnidadeBase,
)
from apps.inventory.models import Location, Lot, StockLevel, StockMovement
from apps.purchasing.models import InvoiceDocument, OrigemDoDocumento, Receipt, ReceiptLine
from apps.shared.db import tenant_scope

__all__ = [
    "CREDENCIAL_POR_OMISSAO",
    "TenantFactory",
    "UserFactory",
    "ProductFactory",
    "LocationFactory",
    "LotFactory",
    "StockLevelFactory",
    "StockMovementFactory",
    "SupplierFactory",
    "ReceiptFactory",
]


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------


#: A password com que `UserFactory` cria contas quando não lhe dão outra. É
#: pública para os testes que iniciam sessão pelo endpoint de login a poderem
#: usar — a forma de `CREDENCIAL` em `tests/test_stock_panel.py`.
CREDENCIAL_POR_OMISSAO = "TestPassword123"


def TenantFactory(
    *,
    name: str = "Demo Resto",
    is_demo: bool = True,
    **kwargs: Any,
) -> Tenant:
    """Cria um tenant (restaurante, pastelaria, café).

    Pelo serviço, e não por `Tenant(...).save()`: o `accounts_tenant` tem
    política e a coluna do tenant é o `id` (ADR 0007), logo o `INSERT` só passa
    dentro do âmbito do próprio tenant — é `criar_tenant` que gera o UUID antes
    de inserir e abre esse âmbito. A configuração que o serviço não aceita
    (`is_demo` e o resto) escreve-se a seguir, dentro do mesmo âmbito.

    Por omissão é marcado como demonstração.
    """
    tenant = criar_tenant(name=name)
    configuracao = {"is_demo": is_demo, **kwargs}
    with tenant_scope(tenant.id):
        for campo, valor in configuracao.items():
            setattr(tenant, campo, valor)
        tenant.save(update_fields=[*configuracao, "updated_at"])
    return tenant


def UserFactory(
    *,
    email: str = "user@demo.pt",
    password: str | None = None,
    is_active: bool = True,
    **kwargs: Any,
) -> User:
    """Cria um utilizador, com `CREDENCIAL_POR_OMISSAO` se não lhe derem password."""
    if password is None:
        password = CREDENCIAL_POR_OMISSAO
    user = User.objects.create_user(
        email=email,
        password=password,
        is_active=is_active,
        **kwargs,
    )
    return user


def MembershipFactory(
    *,
    user: User,
    tenant: Tenant,
    role: str = Papel.STAFF,
    display_name: str = "Staff",
    is_active: bool = True,
    **kwargs: Any,
) -> Membership:
    """Cria uma pertença (membro de um estabelecimento)."""
    membership = Membership.objects.create(
        user=user,
        tenant=tenant,
        role=role,
        display_name=display_name,
        is_active=is_active,
        **kwargs,
    )
    return membership


def InvitationFactory(
    *,
    tenant: Tenant,
    email: str = "invited@demo.pt",
    role: str = Papel.STAFF,
    display_name: str = "Convidado",
    **kwargs: Any,
) -> Invitation:
    """Cria um convite para um estabelecimento."""
    import hashlib
    import secrets

    token = secrets.token_hex(16)  # 32 bytes em hex
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    invitation = Invitation.objects.create(
        tenant=tenant,
        email=email,
        role=role,
        display_name=display_name,
        token_hash=token_hash,
        expires_at=timezone.now() + timedelta(days=7),
        **kwargs,
    )
    return invitation


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------


def ProductFactory(
    *,
    tenant: Tenant,
    short_name: str = "Farinha T65",
    base_unit: str = UnidadeBase.GRAMA,
    display_unit: str = "kg",
    display_factor: Decimal = Decimal("1000"),
    track_lots: bool = False,
    expiry_kind: str = "",
    conservation: str = Conservacao.AMBIENT,
    **kwargs: Any,
) -> Product:
    """Cria um produto no catálogo."""
    with tenant_scope(tenant.id):
        product = Product.objects.create(
            tenant=tenant,
            short_name=short_name,
            base_unit=base_unit,
            display_unit=display_unit,
            display_factor=display_factor,
            track_lots=track_lots,
            expiry_kind=expiry_kind,
            conservation=conservation,
            **kwargs,
        )
    return product


def SupplierFactory(
    *,
    tenant: Tenant,
    name: str = "Fornecedor A",
    nif: str = "500000001",
    **kwargs: Any,
) -> Supplier:
    """Cria um fornecedor."""
    with tenant_scope(tenant.id):
        supplier = Supplier.objects.create(
            tenant=tenant,
            name=name,
            nif=nif,
            **kwargs,
        )
    return supplier


def SupplierProductCodeFactory(
    *,
    supplier: Supplier,
    product: Product,
    supplier_code: str = "SKU001",
    **kwargs: Any,
) -> SupplierProductCode:
    """Cria uma ligação entre fornecedor e produto."""
    with tenant_scope(supplier.tenant_id):
        spc = SupplierProductCode.objects.create(
            supplier=supplier,
            product=product,
            supplier_code=supplier_code,
            **kwargs,
        )
    return spc


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------


def LocationFactory(
    *,
    tenant: Tenant,
    name: str = "Armazém",
    position: int = 0,
    is_active: bool = True,
    **kwargs: Any,
) -> Location:
    """Cria uma localização (loja, armazém, cozinha)."""
    with tenant_scope(tenant.id):
        location = Location.objects.create(
            tenant=tenant,
            name=name,
            position=position,
            is_active=is_active,
            **kwargs,
        )
    return location


def LotFactory(
    *,
    tenant: Tenant,
    product: Product,
    code: str = "LOTE001",
    expires_at: datetime | None = None,
    received_at: datetime | None = None,
    **kwargs: Any,
) -> Lot:
    """Cria um lote de produto."""
    if received_at is None:
        received_at = timezone.now()
    if expires_at is None:
        expires_at = timezone.now() + timedelta(days=30)

    with tenant_scope(tenant.id):
        lot = Lot.objects.create(
            tenant=tenant,
            product=product,
            code=code,
            expires_at=expires_at,
            received_at=received_at,
            **kwargs,
        )
    return lot


def StockLevelFactory(
    *,
    tenant: Tenant,
    product: Product,
    location: Location,
    quantity: Decimal = Decimal("100"),
    unit_cost: Decimal = Decimal("1.50"),
    lot: Lot | None = None,
    **kwargs: Any,
) -> StockLevel:
    """Cria um nível de stock (projeção de estado)."""
    with tenant_scope(tenant.id):
        stock_level = StockLevel.objects.create(
            tenant=tenant,
            product=product,
            location=location,
            lot=lot,
            quantity=quantity,
            unit_cost=unit_cost,
            **kwargs,
        )
    return stock_level


def StockMovementFactory(
    *,
    tenant: Tenant,
    product: Product,
    location: Location,
    movement_type: str = "receipt",
    quantity: Decimal = Decimal("100"),
    unit_cost: Decimal = Decimal("1.50"),
    lot: Lot | None = None,
    created_by: User | None = None,
    occurred_at: datetime | None = None,
    reference: str | None = None,
    reason: str | None = None,
    **kwargs: Any,
) -> StockMovement:
    """Cria um movimento de stock (ledger)."""
    if occurred_at is None:
        occurred_at = timezone.now()

    created_by_name = created_by.email if created_by else "system"

    with tenant_scope(tenant.id):
        movement = StockMovement.objects.create(
            tenant=tenant,
            product=product,
            location=location,
            lot=lot,
            movement_type=movement_type,
            quantity=quantity,
            unit_cost=unit_cost,
            cost_is_estimate=False,
            reason=reason,
            reference=reference,
            occurred_at=occurred_at,
            created_by=created_by,
            created_by_name=created_by_name,
            **kwargs,
        )
    return movement


# ---------------------------------------------------------------------------
# Purchasing
# ---------------------------------------------------------------------------


def InvoiceDocumentFactory(
    *,
    tenant: Tenant,
    source: str = OrigemDoDocumento.UPLOAD,
    **kwargs: Any,
) -> InvoiceDocument:
    """Cria um documento de fatura. `source` é a origem (`upload` ou `capture`)."""
    with tenant_scope(tenant.id):
        doc = InvoiceDocument.objects.create(
            tenant=tenant,
            source=source,
            **kwargs,
        )
    return doc


def ReceiptFactory(
    *,
    tenant: Tenant,
    supplier: Supplier,
    document: InvoiceDocument | None = None,
    location: Location | None = None,
    **kwargs: Any,
) -> Receipt:
    """Cria uma receção (rascunho de compra), recebida agora salvo indicação.

    A localização é obrigatória no modelo (é onde a mercadoria entra): sem uma,
    cria-se a de omissão da `LocationFactory`.
    """
    if document is None:
        document = InvoiceDocumentFactory(tenant=tenant)
    if location is None:
        location = LocationFactory(tenant=tenant)
    kwargs.setdefault("received_at", timezone.now())

    with tenant_scope(tenant.id):
        receipt = Receipt.objects.create(
            tenant=tenant,
            supplier=supplier,
            document=document,
            location=location,
            **kwargs,
        )
    return receipt


def ReceiptLineFactory(
    *,
    receipt: Receipt,
    product: Product,
    quantity: Decimal = Decimal("100"),
    unit_price: Decimal = Decimal("1.50"),
    **kwargs: Any,
) -> ReceiptLine:
    """Cria uma linha de receção (linha de compra)."""
    with tenant_scope(receipt.tenant_id):
        line = ReceiptLine.objects.create(
            receipt=receipt,
            product=product,
            quantity=quantity,
            unit_price=unit_price,
            **kwargs,
        )
    return line
