from fastapi import APIRouter
from app.api.endpoints import healthcheck
from app.api.endpoints import embedding
from app.api.endpoints import query_understand

api_router = APIRouter()
api_router.include_router(healthcheck.router, prefix="/healthcheck", tags=["healthcheck"])
api_router.include_router(embedding.router, prefix="/embedding", tags=["embedding"])
api_router.include_router(query_understand.router,prefix="/query-understand",tags=["query-understand"])