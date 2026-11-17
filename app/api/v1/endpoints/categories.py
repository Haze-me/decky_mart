from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.categories import CATEGORIES, resolve_category
from app.core.limiter import limiter
from app.db.session import get_db
from app.models.solver_profile import SolverProfile
from app.models.user import AccountStatus, User, UserRole
from app.schemas.category import CategoryItem, CategoryListResponse

router = APIRouter(prefix="/auth", tags=["categories"])


@router.get("/categories/all", response_model=CategoryListResponse)
@limiter.limit("120/minute")
async def list_all_categories(request: Request, response: Response) -> CategoryListResponse:
    """Every official category, whether or not a Solver holds it yet. Public. Use it ONLY for the Solver
    registration / profile dropdown. Customers must use GET /auth/categories."""
    response.headers["Cache-Control"] = "public, max-age=300"
    return CategoryListResponse(items=[CategoryItem(slug=c.slug, name=c.name) for c in CATEGORIES])


@router.get("/categories", response_model=CategoryListResponse)
@limiter.limit("120/minute")
async def list_categories(
    request: Request, response: Response, db: AsyncSession = Depends(get_db)
) -> CategoryListResponse:
    """The categories customers can choose from: only those that at least one ACTIVE (approved, not suspended or banned) Solver
    registered with, in dropdown order. Public. Use it for the customer "What service do you need?"
    dropdown so nobody is offered a category no one can serve.
    """
    labels = (
        await db.execute(
            select(SolverProfile.category)
            .join(User, User.id == SolverProfile.user_id)
            .where(User.role == UserRole.SOLVER, User.account_status == AccountStatus.ACTIVE)
            .distinct()
        )
    ).scalars().all()

    # Legacy free text ("plumber ", "Automobile Electrician") is folded onto the official list;
    # text that matches nothing is ignored here (scripts/category_audit.py reports it).
    held = {c.slug for c in map(resolve_category, labels) if c}
    response.headers["Cache-Control"] = "public, max-age=60"
    return CategoryListResponse(items=[CategoryItem(slug=c.slug, name=c.name) for c in CATEGORIES if c.slug in held])
