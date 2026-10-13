from fastapi import APIRouter, Depends, Response

from app.api.deps import Actor, get_current_actor
from app.core.csrf import generate_csrf_token, set_csrf_cookie
from app.schemas.csrf import CSRFResponse

router = APIRouter(tags=["csrf"])


@router.get("/csrf", response_model=CSRFResponse)
async def issue_csrf_token(response: Response, actor: Actor = Depends(get_current_actor)):
    """Mints a fresh csrf_token cookie for any authenticated actor (solver, admin, or customer).
    Solvers/admins already get one at login; this exists for customers, who authenticate via the
    separate customer service and never hit our login flow, so never get one otherwise.
    """
    set_csrf_cookie(response, generate_csrf_token())
    return CSRFResponse(detail="CSRF cookie set")
