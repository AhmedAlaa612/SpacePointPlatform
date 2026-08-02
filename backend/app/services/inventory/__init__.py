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
    kit_sessions,
    outstanding_post_checks,
    record_check,
    unassign_kit,
)
from app.services.inventory.cohort_kits import (
    cohort_kit_ids,
    cohort_kits,
    materialize_session_kits,
    remove_cohort_kit,
    resolve_session_kits,
    set_cohort_kits,
)
from app.services.inventory.completeness import is_complete, kit_shortages, shortages_for_kits
from app.services.inventory.custody import (
    held_by_user,
    issue_merch,
    return_merch,
)
from app.services.inventory.equipment import (
    mark_equipment_return_later,
    pickup_warehouse,
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
from app.services.inventory.holdings import (
    default_kit_return_warehouse,
    my_held_items,
    return_own_item,
    return_own_kit,
)
from app.services.inventory.movements import MOVEMENT_REASONS, confirm, count_kit, move, overdue
from app.services.inventory.session_kits import (
    confirm_kit_returns,
    mark_kits_received,
    mark_kits_returned,
)
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
    "count_kit",
    # session loop (I2-1/I2-2)
    "assign_kits",
    "unassign_kit",
    "assigned_kits",
    "expected_counts",
    "record_check",
    "outstanding_post_checks",
    "check_history",
    "CHECK_PHASES",
    # kits are assigned to a session, received and returned — no custody leg
    "mark_kits_received",
    "mark_kits_returned",
    "confirm_kit_returns",
    # cohort-level kit defaults (Phase 3 follow-up)
    "set_cohort_kits",
    "cohort_kit_ids",
    "cohort_kits",
    "remove_cohort_kit",
    "resolve_session_kits",
    "materialize_session_kits",
    # merch (I2-4)
    "issue_merch",
    "return_merch",
    "held_by_user",
    # equipment pickup (I2-7)
    "pickup_warehouse",
    "search_equipment",
    "take_equipment",
    "session_equipment",
    "return_equipment",
    "mark_equipment_return_later",
    # holdings — self-serve returns (2026-08-01)
    "my_held_items",
    "return_own_kit",
    "return_own_item",
    "default_kit_return_warehouse",
    # storekeeper fulfilment (I3-1)
    "fulfilment_queue",
    "fulfil_kit",
    "set_awaiting_parts",
]
