from fastapi import APIRouter
from app.api.endpoints import healthcheck
from app.api.endpoints import embedding

api_router = APIRouter()
api_router.include_router(healthcheck.router, prefix="/healthcheck", tags=["healthcheck"])
api_router.include_router(embedding.router, prefix="/embedding", tags=["embedding"])