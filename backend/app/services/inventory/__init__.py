"""Inventory services (I1-2).

`move()` is the single write path for anything physical: it records one
ledger row and updates the denormalised position (`kits.current_*`,
`stock_levels.qty`) in the same transaction, so the two can never disagree.

Completeness is computed, never stored — the legacy system stored it and it
went stale in production.
"""

from app.services.inventory.checks import (
    CHECK_PHASES,
    assign_kits,
    assigned_kits,
    check_history,
    expected_counts,
    outstanding_post_checks,
    record_check,
    unassign_kit,
)
from app.services.inventory.completeness import is_complete, kit_shortages, shortages_for_kits
from app.services.inventory.custody import (
    confirm_collected,
    held_by_user,
    issue_merch,
    issue_session_kits,
    return_merch,
    return_session_kits,
    unconfirmed_handovers,
)
from app.services.inventory.equipment import (
    pickup_location,
    return_equipment,
    search_equipment,
    session_equipment,
    take_equipment,
)
from app.services.inventory.fulfilment import (
    fulfil_kit,
    fulfilment_queue,
    set_awaiting_parts,
)
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
    # session loop (I2-1/I2-2)
    "assign_kits",
    "unassign_kit",
    "assigned_kits",
    "expected_counts",
    "record_check",
    "outstanding_post_checks",
    "check_history",
    "CHECK_PHASES",
    # custody + merch (I2-3/I2-4)
    "issue_session_kits",
    "confirm_collected",
    "return_session_kits",
    "issue_merch",
    "return_merch",
    "held_by_user",
    "unconfirmed_handovers",
    # equipment pickup (I2-7)
    "pickup_location",
    "search_equipment",
    "take_equipment",
    "session_equipment",
    "return_equipment",
    # storekeeper fulfilment (I3-1)
    "fulfilment_queue",
    "fulfil_kit",
    "set_awaiting_parts",
]
