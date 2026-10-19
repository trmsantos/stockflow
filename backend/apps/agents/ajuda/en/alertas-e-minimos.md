# Alerts and minimums

Screen: **Alerts** (`/alertas`), with three views in the URL: `?ver=expira`,
`?ver=falta` and `?ver=desperdicio`.

**What is expiring.** Lots **with stock** expiring in the next seven days,
including those already expired. The date is the one printed on the packaging,
on the civil calendar. "Use by" is a legal limit; "best before" is minimum
durability — they are not the same thing.

**What is missing.** Items whose balance summed across all locations is below
the item's minimum. The minimum belongs to the **item**, not to a store: three
stores with 400 g each, against a 1 kg minimum, raise no alert.

An item that has never entered stock raises nothing: you are not warned about
the absence of something that never existed.

**What was thrown away.** Waste for the business day or the last seven days
(`?periodo=hoje` or `?periodo=semana`), by item and reason.

Minimums are set on the item. While an item's minimum is zero it has no minimum
and never appears in the "missing" view.
