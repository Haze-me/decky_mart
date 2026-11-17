"""The official service categories. The Solver service owns this list: registration validates against it,
GET /auth/categories/all serves it (Solver registration dropdown) and GET /auth/categories serves the
ones an ACTIVE Solver actually holds (customer "What service do you need?" dropdown).

`slug` is the stable key other services use (match-service stores it on jobs); `name` is the display text
and is what we store in solver_profiles.category. Never rename a slug.
"""
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Category:
    slug: str
    name: str


# Dropdown order.
CATEGORIES: tuple[Category, ...] = (
    Category("vulcanizer", "Vulcanizer"),
    Category("auto-electrician", "Auto Electrician"),
    Category("auto-mechanic", "Auto Mechanic"),
    Category("plumber", "Plumber"),
    Category("home-cabinet", "Home Cabinet"),
    Category("house-electrician", "House Electrician"),
    Category("laundry-service", "Laundry Service"),
    Category("tilers-service", "Tilers Service"),
    Category("event-planning", "Event Planning"),
    Category("air-conditioner-repair", "Air-Conditioner Repair"),
    Category("fashion-designer", "Fashion Designer"),
    Category("hair-stylist", "Hair Stylist"),
    Category("fridge-repair", "Fridge Repair"),
    Category("pop-service", "POP Service"),
    Category("washing-machine-repair-service", "Washing Machine Repair Service"),
)

# Spellings Solvers already registered with (free text before this list existed) -> official slug.
# Key = normalized text. Add entries when scripts/category_audit.py shows an unmatched label.
CATEGORY_ALIASES: dict[str, str] = {
    "automobile electrician": "auto-electrician",
}


def normalize(text: str) -> str:
    """Case-, spacing- and hyphen/underscore-insensitive form used to compare category text."""
    return re.sub(r"[\s_\-]+", " ", text.strip().lower())


_BY_KEY: dict[str, Category] = {}
for _c in CATEGORIES:
    _BY_KEY[normalize(_c.name)] = _c
    _BY_KEY[normalize(_c.slug)] = _c
_BY_SLUG = {c.slug: c for c in CATEGORIES}


def resolve_category(text: str | None) -> Category | None:
    """Map free text (a registration value, an old label) to an official category, or None."""
    if not text or not text.strip():
        return None
    key = normalize(text)
    alias_slug = CATEGORY_ALIASES.get(key)
    if alias_slug:
        return _BY_SLUG[alias_slug]
    return _BY_KEY.get(key)
