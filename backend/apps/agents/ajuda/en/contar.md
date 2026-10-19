# Counting stock

Screen: **Count** (`/contar`).

A count compares what is on the shelf with what the system says.

1. Choose the store and tap "Start count".
2. The count walks the store by **zones**, in physical order (counter, fridge,
   freezer, storeroom). The zone filter lives in the URL (`/contar?zona=...`).
3. On each line you type how many are on the shelf. A line with no value is
   **not counted yet** — zero means "I counted and there was none", which is a
   different thing.
4. In a blind zone the expected quantity only shows at the end.

**Closing.** With everything counted, the closing screen shows the differences
and writes one adjustment movement for each, with the author and the
justification. Before closing, a count **does not touch stock**.

Each line's expected quantity is a snapshot from when the count was opened: in
an old count it may no longer be today's balance.

A closed count is never rewritten — you count again.
