from fastapi import APIRouter
from app.api.endpoints import healthcheck
from app.api.endpoints import embedding
from app.api.endpoints import query_understand
from app.api.endpoints import poi_filter
from app.api.endpoints import vector_search
from app.api.endpoints import tasco_search

api_router = APIRouter()
api_router.include_router(healthcheck.router, prefix="/healthcheck", tags=["healthcheck"])
api_router.include_router(embedding.router, prefix="/embedding", tags=["embedding"])
api_router.include_router(query_understand.router, prefix="/query-understand", tags=["query-understand"])
api_router.include_router(poi_filter.router, prefix="/poi", tags=["poi"])
api_router.include_router(vector_search.router, prefix="/vector", tags=["vector"])
api_router.include_router(tasco_search.router, prefix="/tasco", tags=["tasco"])
