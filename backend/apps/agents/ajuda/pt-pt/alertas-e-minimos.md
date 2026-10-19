# Alertas e mínimos

Ecrã: **Alertas** (`/alertas`), com três vistas no URL: `?ver=expira`,
`?ver=falta` e `?ver=desperdicio`.

**O que expira.** Os lotes **com saldo** que vencem nos próximos sete dias, os
já vencidos incluídos. A data é a impressa na embalagem, no calendário civil.
"Consumir até" é um limite legal; "consumir de preferência antes de" é
durabilidade mínima — e são coisas diferentes.

**O que falta.** Os artigos cujo saldo somado em todas as localizações está
abaixo do mínimo do artigo. O mínimo é **do artigo** e não de uma loja: três
lojas com 400 g cada, contra um mínimo de 1 kg, não dão alerta.

Um artigo que nunca entrou em stock não alarma: não se avisa da falta do que
nunca houve.

**O que se deitou fora.** O desperdício do dia de negócio ou dos últimos sete
dias (`?periodo=hoje` ou `?periodo=semana`), por artigo e motivo.

Os mínimos definem-se no artigo. Enquanto um artigo tiver mínimo zero, não tem
mínimo e nunca aparece na vista "falta".
