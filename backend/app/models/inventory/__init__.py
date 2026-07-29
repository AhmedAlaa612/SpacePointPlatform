"""Inventory domain (I1-1).

Eight tables, one CHECK constraint in total, no state machines. Owner of
locations, the item catalogue, kit templates and their bill of materials,
serialised kits and their contents, loose stock levels, and the single
movement ledger everything physical passes through.

Nothing here references `contacts` — custody keys on `users`, because
everyone who can hold a kit or a vest is staff with a login and needs one to
see "my kits" at all. So `MERGE_FK_REGISTRY` in services/spine/identity.py is
deliberately untouched by this domain. If that decision is ever reversed,
every new contact FK must be registered there or a contact merge will
silently orphan the rows.
"""

from app.models.inventory.item import Item
from app.models.inventory.kit import Kit, KitItem
from app.models.inventory.kit_template import KitTemplate, KitTemplateItem
from app.models.inventory.location import Location
from app.models.inventory.movement import Movement
from app.models.inventory.session_kit import KitCheck, SessionKit
from app.models.inventory.stock import StockLevel

__all__ = [
    "Location",
    "Item",
    "KitTemplate",
    "KitTemplateItem",
    "Kit",
    "KitItem",
    "StockLevel",
    "Movement",
    "SessionKit",
    "KitCheck",
]
