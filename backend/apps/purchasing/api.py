"""A porta do módulo `purchasing` (ARCHITECTURE.md §3).

Único ficheiro deste módulo que outro módulo pode importar. Hoje tem **um**
consumidor — o `apps/agents/`, pela aresta `agents -> purchasing.api` que o
import-linter já declara — e expõe exactamente o que ele precisa:

1. **As páginas de um documento como DTO congelado**, que é a forma em que o
   `agents` recebe trabalho: *"o `agents` nunca vê um PDF, nunca corre poppler e
   entra pelo `purchasing.api`, que lhe dá páginas como DTO congelado"* (ADR
   0020, decisão 6);
2. **A forma de "o que o modelo leu"** — `LeituraDeDocumento`, `LinhaLida` e o
   `EstadoDaLeitura` —, que é o vocabulário em que a resposta do modelo chega
   deste lado;
3. **O porto da extração**, que é a inversão de dependência que faz o `state` e o
   `extraction` do `DocumentoOut` existirem sem o `purchasing` importar o
   `agents`. A razão inteira está no topo de `apps/purchasing/extracao.py`, e é
   onde deve ser lida antes de alguém mexer nisto.

Reexportação e não definição: cada nome vive no ficheiro onde pertence
(`models.py`, `extracao.py`, `selectors.py`) e este é só a porta. Assim não há
duas versões da mesma coisa, e o que está fora do `__all__` não é público por
acidente.

**E o `__all__` tem oito nomes porque são oito os que têm consumidor.** O
`EstadoDoDocumento`, a `OrigemDoDocumento` e os três relógios ficaram de fora
apesar de parecerem "o contrato do documento": nada fora do `purchasing` os lê, e
o `services.py` do `accounts` já escreveu a razão por extenso — *"um DTO público
sem consumidor é um contrato público escrito ao contrário"*. O dia em que um
módulo precisar de um deles, a subida é uma linha.
"""

from __future__ import annotations

from apps.purchasing.extracao import (
    FronteiraDaExtracao,
    LeituraDeDocumento,
    LinhaLida,
    PaginaDoDocumento,
    fronteira_da_extracao,
    ligar_fronteira_da_extracao,
)
from apps.purchasing.models import EstadoDaLeitura
from apps.purchasing.selectors import paginas_do_documento

__all__ = [
    "EstadoDaLeitura",
    "FronteiraDaExtracao",
    "LeituraDeDocumento",
    "LinhaLida",
    "PaginaDoDocumento",
    "fronteira_da_extracao",
    "ligar_fronteira_da_extracao",
    "paginas_do_documento",
]
