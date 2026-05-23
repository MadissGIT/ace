from fastapi import APIRouter

from backend.app.api.routes import (
    users, login, tournaments,
    sex, categories, regions,
    trainers, news, participants,
    transactions, uploads, healthcheck,
    groups, playoff, max_registration, vk_registration,
)

api_router = APIRouter()
api_router.include_router(
    healthcheck.router, tags=["healthcheck"]
)
api_router.include_router(
    users.router, tags=["users"], prefix="/users"
)
api_router.include_router(
    login.router, tags=["login"], prefix="/login"
)
api_router.include_router(
    transactions.router, tags=["transactions"], prefix="/transactions"
)
api_router.include_router(
    uploads.router, tags=["uploads"], prefix="/uploads"
)
api_router.include_router(
    tournaments.router, tags=["tournaments"], prefix="/tournaments"
)
api_router.include_router(
    participants.router, tags=["participants"], prefix="/participants"
)
api_router.include_router(
    sex.router, tags=["sex"], prefix="/sex"
)
api_router.include_router(
    categories.router, tags=["categories"], prefix="/categories"
)
api_router.include_router(
    regions.router, tags=["regions"], prefix="/regions"
)
api_router.include_router(
    trainers.router, tags=["trainers"], prefix="/trainers"
)
api_router.include_router(
    news.router, tags=["news"], prefix="/news"
)
api_router.include_router(
    groups.router, tags=["groups"], prefix="/groups"
)
api_router.include_router(
    playoff.router, tags=["playoffs"], prefix="/playoffs"
)
api_router.include_router(
    max_registration.router, tags=["max-registration"], prefix="/max/registration"
)
api_router.include_router(
    vk_registration.router, tags=["vk-registration"], prefix="/vk/registration"
)
