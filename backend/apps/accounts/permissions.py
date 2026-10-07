"""As duas classes de permissão do projeto, e vivem aqui uma vez só.

O SECURITY.md §5 exige que toda a view que receba um `pk` verifique
`obj.tenant_id == request.tenant.id` **antes** de qualquer outra regra.
Escrever essa comparação à mão em nove módulos é como um deles a escreve mal —
e o que se escreve mal numa comparação de isolamento é travessia de tenant. Por
isso a comparação existe num sítio só, e os módulos importam-na do
`apps/accounts/api.py`, que a reexporta.

## Isto é a segunda rede, não a primeira

A primeira é a RLS: dentro de `tenant_scope(A)` a linha de B **não é legível**,
pelo que um `get_object()` sobre o `pk` de B levanta `DoesNotExist` e o DRF
responde 404 — e 404 é a resposta certa, porque 403 confirmaria a existência do
objeto a quem não o pode ver. Estas classes são o controlo aplicacional que o
SECURITY.md §1 exige **ao lado** da RLS, para o caso de uma queryset construída
fora do âmbito, de um objeto carregado num pedido anterior ou de uma política
desligada por acidente.
"""

from __future__ import annotations

from typing import Any, ClassVar

from django.core.exceptions import ImproperlyConfigured
from django.http import HttpRequest
from rest_framework.permissions import BasePermission
from rest_framework.views import APIView

from apps.accounts.models import Papel

__all__ = ["PertenceAoTenant", "TemPapel"]


def _contexto(request: HttpRequest) -> Any:
    """O `TenantContext` que o `TenantMiddleware` publicou, ou `None`.

    `None` numa view dispensada de âmbito — e aí estas permissões negam, que é
    o que se quer: uma view sem âmbito não tem objetos de tenant para proteger.
    """
    return getattr(request, "tenant", None)


class PertenceAoTenant(BasePermission):
    """O objeto é do tenant do pedido. A comparação do SECURITY.md §5.

    Um objeto sem `tenant_id` nenhum nega, e não é conservadorismo: os dados de
    referência partilhados (catálogo global EAN→descrição, fornecedores comuns)
    não têm `tenant_id` por desenho (ADR 0005) e não se protegem por esta
    classe — protegem-se por serem read-only. Se um deles aparecer aqui, é um
    engano de configuração da view e o silêncio seria pior.
    """

    message = "Este registo não pertence ao estabelecimento ativo."

    def has_permission(self, request: HttpRequest, view: APIView) -> bool:
        return _contexto(request) is not None

    def has_object_permission(self, request: HttpRequest, view: APIView, obj: Any) -> bool:
        contexto = _contexto(request)
        if contexto is None:
            return False
        tenant_do_objeto = getattr(obj, "tenant_id", None)
        return tenant_do_objeto is not None and tenant_do_objeto == contexto.id


class TemPapel(BasePermission):
    """O papel do pedido está na lista exigida pela view.

    Usa-se sempre pela fábrica, que valida os nomes na importação do módulo::

        permission_classes = [PertenceAoTenant, TemPapel.exige(Papel.OWNER)]

    O papel vem do `TenantContext` — ou seja, do `Membership` que o middleware
    confirmou **neste** pedido, dentro do âmbito. Não vem da sessão nem de um
    campo do `User`: é por tenant, porque a mesma pessoa é dona de um
    estabelecimento e colaboradora noutro.
    """

    papeis: ClassVar[frozenset[str]] = frozenset()
    message = "O seu papel neste estabelecimento não permite esta operação."

    @classmethod
    def exige(cls, *valores: str) -> type[TemPapel]:
        """Uma subclasse desta, com a lista de papéis fechada.

        Levanta em vez de aceitar um papel inventado: uma permissão que nunca
        concede nada porque o valor está mal escrito é indistinguível de uma
        regra de negócio, e descobre-se num relatório de bug.
        """
        exigidos = frozenset(str(v) for v in valores)
        if not exigidos:
            raise ValueError("TemPapel.exige() sem papéis não concede nada a ninguém.")
        validos = {p.value for p in Papel}
        desconhecidos = sorted(exigidos - validos)
        if desconhecidos:
            raise ValueError(
                f"papéis desconhecidos: {desconhecidos}; válidos: {sorted(validos)}"
            )
        nome = f"TemPapel_{'_'.join(sorted(exigidos))}"
        return type(nome, (cls,), {"papeis": exigidos})

    def has_permission(self, request: HttpRequest, view: APIView) -> bool:
        contexto = _contexto(request)
        if not self.papeis:
            raise ImproperlyConfigured(
                "TemPapel usado diretamente em permission_classes: usa "
                "TemPapel.exige(...). Sem papéis, esta classe negaria tudo em "
                "silêncio."
            )
        return contexto is not None and contexto.role in self.papeis

    def has_object_permission(self, request: HttpRequest, view: APIView, obj: Any) -> bool:
        """O papel é do par (utilizador, tenant), logo não depende do objeto.

        Reimplementado de propósito: o default do DRF devolve `True` e um leitor
        que veja só `has_permission` podia concluir que o papel não é verificado
        no caminho do objeto.
        """
        return self.has_permission(request, view)
