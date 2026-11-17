"""Pushes a Solver's matching-relevant facts to match-service (docs/solver-sync-contract.md in that repo).

Called after the commit of anything that changes whether/where/how a Solver can receive jobs: admin
approve/reject/suspend/ban/activate and profile edits. It must never break the action that triggered it:
every failure is logged and swallowed. A push that is lost for good is repaired by the next change or by
scripts/sync_solvers_to_match.py.

Only these fields cross the boundary. The Solver's phone is included because the customer who PICKS this Solver
must be able to call them; match-service shows it only to that customer, only while the job is in progress. Never
sent: email, address, ID documents, bank details.
"""
import asyncio
import logging
import uuid
from datetime import timezone

import httpx
from sqlalchemy import select

from app.core.categories import resolve_category
from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.solver_profile import SolverProfile
from app.models.user import AccountStatus, User, UserRole
from app.services.storage import build_public_url

logger = logging.getLogger("app.match_sync")

_TIMEOUT = httpx.Timeout(5.0)
# Pause before the 2nd and 3rd attempt (seconds). Network errors, 5xx, 408 and 429 are retried; any other
# 4xx is a bug on our side (bad key, bad payload) and retrying can't fix it.
RETRY_DELAYS = (0.5, 2.0)


def sync_enabled() -> bool:
    return bool(settings.MATCH_SERVICE_URL and settings.MATCH_INTERNAL_API_KEY)


def build_payload(user: User, profile: SolverProfile) -> dict:
    """The body of PUT /api/v1/internal/solvers/{id}."""
    category = resolve_category(profile.category)
    # Version stamp: any change to the user or profile row bumps updated_at, so the latest of them orders
    # our pushes; match-service ignores anything older than what it already holds.
    stamp = max(t for t in (user.updated_at, user.status_changed_at, profile.updated_at) if t is not None)
    return {
        # Verified = approved and in good standing. Pending, rejected, suspended and banned are all false.
        "verified": user.account_status == AccountStatus.ACTIVE,
        "display_name": user.full_name,
        "profile_image_url": build_public_url(profile.profile_image_key) if profile.profile_image_key else None,
        # The official category slug, or None when the registered text matches nothing on the list.
        "category": category.slug if category else None,
        "state": profile.state,
        # Shown by match-service only to the customer who selects this Solver. None when the Solver has none.
        "phone": user.phone_number,
        "latitude": profile.latitude,
        "longitude": profile.longitude,
        "radius_km": profile.radius_km,
        "source_updated_at": stamp.astimezone(timezone.utc).isoformat(),
    }


async def put_to_match(user_id: uuid.UUID, payload: dict) -> bool:
    """One Solver, up to 3 attempts. True when match-service answered 200."""
    url = f"{settings.MATCH_SERVICE_URL.rstrip('/')}/api/v1/internal/solvers/{user_id}"
    headers = {"X-Internal-Key": settings.MATCH_INTERNAL_API_KEY}

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        for attempt in range(len(RETRY_DELAYS) + 1):
            if attempt:
                await asyncio.sleep(RETRY_DELAYS[attempt - 1])
            try:
                resp = await client.put(url, json=payload, headers=headers)
            except httpx.HTTPError:
                logger.warning("match-service sync network error", extra={"user_id": str(user_id), "attempt": attempt + 1})
                continue

            if resp.status_code == 200:
                body = resp.json()
                if payload["verified"] and not body.get("category_matched", True):
                    logger.warning("Solver category not accepted by match-service", extra={"user_id": str(user_id)})
                return True
            if resp.status_code in (408, 429) or resp.status_code >= 500:
                logger.warning(
                    "match-service sync will retry",
                    extra={"user_id": str(user_id), "status": resp.status_code, "attempt": attempt + 1},
                )
                continue
            logger.error(
                "match-service rejected the sync, not retrying",
                extra={"user_id": str(user_id), "status": resp.status_code, "body": resp.text[:300]},
            )
            return False

    logger.error("match-service sync gave up after retries", extra={"user_id": str(user_id)})
    return False


async def push_solver_to_match(user_id: uuid.UUID) -> bool:
    """Load the Solver fresh (after the caller's commit) and push. Never raises."""
    if not sync_enabled():
        return False
    try:
        async with AsyncSessionLocal() as db:
            user = await db.get(User, user_id)
            if user is None or user.role != UserRole.SOLVER:
                return False
            profile = (
                await db.execute(select(SolverProfile).where(SolverProfile.user_id == user_id))
            ).scalar_one_or_none()
            if profile is None:  # still mid-registration: nothing to tell match-service yet
                return False
            payload = build_payload(user, profile)
        return await put_to_match(user_id, payload)
    except Exception:
        logger.error("match-service sync failed", extra={"user_id": str(user_id)}, exc_info=True)
        return False
