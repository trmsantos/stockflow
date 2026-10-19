# Suppliers

Screen: **Receive** (`/receber`) — a supplier shows up on receipts.

A supplier has a name and, where known, a tax number. The tax number is there to
recognise it on a document; the assistant never discloses it.

On a receipt, the supplier can be there in two ways:

- **linked to the catalogue** — the receipt points at the supplier, and so it
  counts towards the price history and the code memory;
- **printed only** — the name came on the document and nobody has linked it yet.
  The receipt still shows up, but it stays out of that supplier's history.

**Code memory.** When a receipt is confirmed, the pair (supplier, item code on
the document) is stored. On the next receipt from the same supplier, the lines
come pre-suggested.

**Prices.** An item's price history is per supplier and per month, built only
from confirmed receipts and net of VAT. Delivery notes carry no price; credit
and debit notes are corrections and stay out of the average.
