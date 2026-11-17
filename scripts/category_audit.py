"""READ-ONLY audit of the category text Solvers registered with, against the official list.

    python scripts/category_audit.py

Run it from the project root with your normal .env (it only runs SELECTs). It prints, per account status,
each distinct category text, how many Solvers have it, and which official category it maps to. Anything
marked UNMATCHED needs either an entry in CATEGORY_ALIASES (app/core/categories.py) or the Solver to pick
a category from the list. Nothing is changed in the database.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select  # noqa: E402

from app.core.categories import resolve_category  # noqa: E402
from app.db.session import AsyncSessionLocal, engine  # noqa: E402
from app.models.solver_profile import SolverProfile  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402


async def main() -> None:
    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                select(User.account_status, SolverProfile.category, func.count())
                .join(User, User.id == SolverProfile.user_id)
                .where(User.role == UserRole.SOLVER)
                .group_by(User.account_status, SolverProfile.category)
                .order_by(User.account_status, func.count().desc())
            )
        ).all()
    await engine.dispose()

    if not rows:
        print("No Solver profiles found.")
        return

    unmatched = 0
    print(f"{'STATUS':<28}{'COUNT':>6}  {'REGISTERED TEXT':<36}-> OFFICIAL CATEGORY")
    print("-" * 100)
    for account_status, category, count in rows:
        official = resolve_category(category)
        if official is None:
            unmatched += count
        status_text = account_status.value if hasattr(account_status, "value") else str(account_status)
        print(f"{status_text:<28}{count:>6}  {category!r:<36}-> {official.name if official else 'UNMATCHED'}")

    total = sum(r[2] for r in rows)
    print("-" * 100)
    print(f"{total} Solver profile(s), {unmatched} with a category that matches nothing in the official list.")


if __name__ == "__main__":
    asyncio.run(main())
