from fastapi import APIRouter

from app.api.v1.endpoints import admin, auth, comments, csrf, notifications, posts, profile, reactions, registration

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(registration.router)
api_router.include_router(profile.router)
api_router.include_router(admin.router)
api_router.include_router(posts.router)
api_router.include_router(comments.router)
api_router.include_router(reactions.router)
api_router.include_router(notifications.router)
api_router.include_router(csrf.router)