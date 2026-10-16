# Reviewing and confirming receipt lines

Screen: **Receive → the receipt** (`/receber/<id>`), or the filtered list at
`/receber?estado=revisao`.

Each document line needs four things before it can enter stock:

- **the catalogue item** it corresponds to (the system suggests one from the
  supplier code it has already learned);
- **the quantity received**, which may be less than the quantity invoiced;
- **the lot**, if the item requires lots;
- **the expiry date**, if the item carries an expiry label.

The lot and the expiry date are **on the packaging**, not on the document: type
them exactly as printed.

A line can be confirmed or left out. A line left out creates no movement at all —
its goods do not appear in stock.

If the delivery contains chilled or frozen goods, record the delivery
temperature for each class present.

Finally, "Confirm and book in" writes the incoming movements with the lot, the
expiry date and the author. Nothing is rewritten afterwards: to correct, record
a new movement.
