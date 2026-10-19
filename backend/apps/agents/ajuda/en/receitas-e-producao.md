# Recipes and production

A recipe states what is needed to produce **one display unit** of the finished
item: one kilo of dough, one custard tart.

**Yield (`yield_factor`).** It is what is left after preparation losses. With a
90 % yield, obtaining 1 kg of finished goods consumes ingredients for 1.11 kg.
That is why the recipe card has two columns: the **list** quantity (what the
recipe writes) and the **real consumption** (list divided by the yield), which
is what leaves stock.

**Producing.** A production consumes ingredients from the lots that expire first
and books in the finished item, all in one ledger entry. The production cost is
the cost of the ingredients that actually left, stored at that moment.

**Costs.** The card shows two numbers and they are different: the **theoretical**
one (what it would cost today, from each ingredient's current average cost) and
the **real cost of the last production** (what it actually cost). Euro figures
are for the owner and the manager.

An inactive recipe cannot be produced.

In this version production has **no screen of its own**: the assistant reads
recipes and productions, and the movements show in the item's history
(`/stock/<artigo>`).
