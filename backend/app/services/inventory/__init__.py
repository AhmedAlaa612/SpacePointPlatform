"""Inventory services (I1-2).

`move()` is the single write path for anything physical: it records one
ledger row and updates the denormalised position (`kits.current_*`,
`stock_levels.qty`) in the same transaction, so the two can never disagree.

Completeness is computed, never stored — the legacy system stored it and it
went stale in production.
"""

from app.services.inventory.completeness import is_complete, kit_shortages, shortages_for_kits
from app.services.inventory.movements import MOVEMENT_REASONS, confirm, move, overdue
from app.services.inventory.stock import adjust_stock

__all__ = [
    "kit_shortages",
    "is_complete",
    "shortages_for_kits",
    "move",
    "confirm",
    "overdue",
    "MOVEMENT_REASONS",
    "adjust_stock",
]
