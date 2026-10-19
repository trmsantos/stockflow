# Losses, adjustments and transfers

Stock is a ledger: a number is never corrected by hand, a movement is added.

**Loss (throwing away).** Screen: **Stock → the item** (`/stock/<artigo>`), in
the "Record waste" form. Choose the location, the quantity in the base unit and
the reason (expired, spoiled, prep loss, breakage, other). On **Alerts**
(`/alertas`) each line has an "I threw it away" shortcut for the day's losses.

**Adjustment.** An adjustment comes from a count: when a count is closed, each
difference between counted and expected creates an adjustment movement. See the
topic "contar".

**Transfer between locations.** There is **no screen for it** in this version.
What exists is the out and in record in the item's history.

Each item's history lives at `/stock/<artigo>` and shows every receipt,
consumption, loss, adjustment, transfer and production, with the time, the
reason and who recorded it.
