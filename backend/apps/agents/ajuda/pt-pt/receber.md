# Receber mercadoria

Ecrã: **Receber** (`/receber`).

Toda a mercadoria entra por um documento do fornecedor: uma fatura, uma fatura
simplificada do cash & carry ou uma guia de remessa. Sem documento também se
recebe — o documento aparece depois.

Como se faz:

1. Em Receber, abre "Fotografar" para enviar o documento: o PDF no computador,
   a fotografia no telemóvel. Pode ter várias páginas.
2. O sistema lê o documento e propõe as linhas. **O que ele leu não é a
   verdade**: é uma proposta para alguém rever.
3. A receção fica na lista com o filtro "por rever" (`/receber?estado=revisao`).
   Abre-a e revê linha a linha (ver o tema "rever-linhas").
4. Só o botão "Confirmar e dar entrada" cria os movimentos de stock.

Filtros da lista: "por rever" mostra o que ainda não deu entrada; "hoje" mostra
o que foi confirmado desde o início do dia de negócio deste estabelecimento.

Enquanto uma receção não estiver confirmada, o stock é o mesmo que era antes de
a mercadoria chegar.
