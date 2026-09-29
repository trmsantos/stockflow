"""No admin registam-se só modelos **sem** política de RLS (ADR 0007).

Ou seja: o `User` e os do Django. O `Tenant` e o `Membership` **não** são
registados, e não é "registados e vazios" — o admin não tem âmbito de tenant,
pelo que uma changelist de `Tenant` mostraria zero linhas e alguém concluiria
que o cliente não tem dados. A não-inscrição diz a verdade; uma lista vazia é
uma armadilha operacional.

Acesso operacional a dados de um tenant é por comando `manage.py` com
`--tenant`, que abre `tenant_scope` explicitamente e cujo `tenant_id` sai nos
logs pelo `ContextVar` (ADR 0005). Dar um seletor de tenant ao admin seria
impersonation sem registo, que é o oposto do que se quer — a impersonation de
suporte, com motivo, expiração e registo, é uma feature com ADR própria.

`is_staff` é o que abre esta porta, e é só para operadores do StockFlow: um
`Membership` com papel `owner` não tem relação nenhuma com ele. O admin vive num
path não óbvio, atrás de IP/VPN, e exige MFA (SECURITY.md §5).
"""

from __future__ import annotations

from django.contrib import admin
from django.http import HttpRequest

from apps.accounts.models import User

__all__ = ["UserAdmin"]


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    """O `User` em leitura, com as flags e as permissões do Django editáveis.

    Duas ausências deliberadas:

    * **a password não aparece**, nem como hash. O admin não define nem mostra
      credenciais: quem precisa de uma password usa o caminho do reset, que
      passa por email. O que se mostra é só se a conta *tem* password
      utilizável, que é o que responde a "porque é que não consigo entrar?";
    * **não se criam utilizadores aqui.** Um operador nasce de um
      `createsuperuser`; um cliente nasce do registo. Um formulário de criação
      no admin sem campo de password produzia contas com um hash vazio — nem
      utilizável nem marcado como inutilizável — e essa ambiguidade acabaria
      num relatório de bug.

    O `tenant_ids` é mostrado em leitura porque é a primeira coisa a ver quando
    alguém não vê o seu estabelecimento no seletor: é um índice, e um índice
    pode ter um uuid morto de um tenant apagado.
    """

    list_display = ("email", "is_active", "is_staff", "is_superuser", "last_login")
    list_filter = ("is_active", "is_staff", "is_superuser")
    search_fields = ("email",)
    ordering = ("email",)
    filter_horizontal = ("groups", "user_permissions")
    readonly_fields = (
        "id",
        "tem_password_utilizavel",
        "tenant_ids",
        "last_login",
        "created_at",
        "updated_at",
    )
    fields = (
        "id",
        "email",
        "is_active",
        "is_staff",
        "is_superuser",
        "groups",
        "user_permissions",
        "tem_password_utilizavel",
        "tenant_ids",
        "last_login",
        "created_at",
        "updated_at",
    )

    @admin.display(boolean=True, description="tem password utilizável")
    def tem_password_utilizavel(self, obj: User) -> bool:
        return obj.has_usable_password()

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False
