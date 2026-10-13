from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity_log import ActivityAction, ActivityLog
from app.models.user import User

ACTIVITY_TITLES = {
    ActivityAction.KYC_APPROVED: "KYC Approved",
    ActivityAction.KYC_REJECTED: "KYC Rejected",
    ActivityAction.SUSPENDED: "Account Suspended",
    ActivityAction.BANNED: "Account Banned",
    ActivityAction.ACTIVATED: "Account Activated",
    ActivityAction.POST_DELETED: "Post Removed",
}


def _build_description(action: ActivityAction, target: User, reason: str | None) -> str:
    name = target.full_name or target.email
    if action == ActivityAction.KYC_APPROVED:
        return f"{name} verified as Solver"
    if action == ActivityAction.KYC_REJECTED:
        return f"{name} KYC rejected: {reason}"
    if action == ActivityAction.SUSPENDED:
        return f"{name} suspended for {reason}"
    if action == ActivityAction.BANNED:
        return f"{name} banned for {reason}"
    if action == ActivityAction.ACTIVATED:
        return f"{name} reactivated"
    if action == ActivityAction.POST_DELETED:
        return f"{name}'s post removed: {reason}"
    return f"{name} — {action.value}"


async def log_activity(
    db: AsyncSession, actor: User, target: User, action: ActivityAction, reason: str | None = None
) -> None:
    entry = ActivityLog(
        actor_id=actor.id,
        target_user_id=target.id,
        action=action,
        description=_build_description(action, target, reason),
    )
    db.add(entry)