"""One-off (and repair) back-fill: push every Solver to match-service.

    python scripts/sync_solvers_to_match.py            # DRY RUN: shows what would be sent, sends nothing
    python scripts/sync_solvers_to_match.py --apply    # actually pushes

Run from the project root with your .env (it needs MATCH_SERVICE_URL and MATCH_INTERNAL_API_KEY for --apply).
Safe to re-run: match-service ignores a push that is older than what it already holds, and re-applies an
equal one. Only Solvers that have a profile are pushed. The output lists ids, never emails or phones.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.core.categories import resolve_category  # noqa: E402
from app.db.session import AsyncSessionLocal, engine  # noqa: E402
from app.models.solver_profile import SolverProfile  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402
from app.services.match_sync import build_payload, put_to_match, sync_enabled  # noqa: E402


async def main(apply: bool) -> None:
    if apply and not sync_enabled():
        sys.exit("Set MATCH_SERVICE_URL and MATCH_INTERNAL_API_KEY in .env first (or run without --apply).")

    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                select(User, SolverProfile)
                .join(SolverProfile, SolverProfile.user_id == User.id)
                .where(User.role == UserRole.SOLVER)
                .order_by(User.created_at)
            )
        ).all()
        payloads = [(user.id, user.account_status.value, profile.category, build_payload(user, profile)) for user, profile in rows]
    await engine.dispose()

    print(f"{'MODE':<8}{'SOLVER ID':<38}{'STATUS':<24}{'VERIFIED':<10}CATEGORY")
    print("-" * 110)
    ok = failed = no_category = 0
    for user_id, account_status, category_text, payload in payloads:
        official = resolve_category(category_text)
        if official is None:
            no_category += 1
        shown = official.slug if official else f"UNMATCHED ({category_text!r})"
        mode = "DRY RUN"
        if apply:
            sent = await put_to_match(user_id, payload)
            ok += sent
            failed += not sent
            mode = "SENT" if sent else "FAILED"
        print(f"{mode:<8}{str(user_id):<38}{account_status:<24}{str(payload['verified']):<10}{shown}")

    print("-" * 110)
    print(f"{len(payloads)} Solver(s). {no_category} with a category that matches nothing in the official list.")
    if apply:
        print(f"Sent: {ok}. Failed: {failed}.")
    else:
        print("Dry run only. Re-run with --apply to push.")


if __name__ == "__main__":
    asyncio.run(main("--apply" in sys.argv))
