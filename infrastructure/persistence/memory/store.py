"""In-memory implementation of the State Store contract."""

from core.domain import ProductId
from core.state import StateSnapshot


class InMemoryStateStore:
    """Store the latest immutable product snapshots in process memory."""

    def __init__(self) -> None:
        """Create an empty in-memory State Store."""
        self._snapshots: dict[ProductId, StateSnapshot] = {}

    def load(self, product_id: ProductId) -> StateSnapshot | None:
        """Load the latest snapshot for a product identifier."""
        if not isinstance(product_id, ProductId):
            raise TypeError("product_id must be a ProductId")
        return self._snapshots.get(product_id)

    def save(self, snapshot: StateSnapshot) -> None:
        """Save a snapshot using its product identifier as the unique key."""
        if not isinstance(snapshot, StateSnapshot):
            raise TypeError("snapshot must be a StateSnapshot")
        self._snapshots[snapshot.product.id] = snapshot
