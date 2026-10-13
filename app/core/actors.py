import uuid
from dataclasses import dataclass

from app.models.user import User, UserRole


@dataclass
class Actor:
    """A unified identity for anyone who can comment/react: a local solver/admin, or a customer
    verified via the separate customer service's token. `user` is only populated for the former —
    customers have no local row, so callers must not assume it's set.
    """

    actor_type: UserRole
    actor_id: uuid.UUID
    user: User | None = None
    # Cheap to populate (no extra query): local actors' full_name is already loaded on `user`;
    # customer actors' full_name/avatar_url come straight off their JWT claims (see customer
    # service's create_access_token). Solver/admin avatar_url is intentionally left unset here -
    # it needs a SolverProfile join, which isn't worth adding to this dependency's hot path.
    display_name: str | None = None
    avatar_url: str | None = None
