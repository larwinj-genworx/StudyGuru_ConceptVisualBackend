from fastapi import APIRouter

from src.api.rest.routes import health, visuals

api_routers = APIRouter()
api_routers.include_router(health.router)
api_routers.include_router(visuals.router)
