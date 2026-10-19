# Items, SKU and packagings

An item has two units: the **base** unit it is counted in (g, ml, un) and the
**display** unit it is talked about in (kg, L, un). A factor links them: 1 kg =
1000 g. Quantities are always stored in the base unit.

Other fields of an item:

- **SKU** — the internal code, unique in this establishment;
- **minimum** — in the base unit; zero means "no minimum";
- **requires lot** — whether every delivery must carry a lot;
- **expiry label** — "use by" or "best before";
- **conservation** — ambient, chilled or frozen, which is what decides whether a
  delivery asks for a temperature.

**Packagings.** An item can have several ("25 kg sack", "box of 12"), each with
its quantity in the base unit and, where known, a barcode. They let the receipt
know how much "2 boxes" is.

**Supplier codes.** Each supplier calls the item whatever it likes. When a
receipt is confirmed, the system learns the code and suggests the item next
time.

Screen: each item's card lives at **Stock → the item** (`/stock/<artigo>`).
