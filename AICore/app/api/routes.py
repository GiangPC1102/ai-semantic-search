from fastapi import APIRouter
from app.api.endpoints import collection, embedding, healthcheck, query_understand, search

api_router = APIRouter()
api_router.include_router(healthcheck.router, prefix="/healthcheck", tags=["healthcheck"])
api_router.include_router(embedding.router, prefix="/embedding", tags=["embedding"])
api_router.include_router(collection.router, prefix="/collection", tags=["collection"])
api_router.include_router(query_understand.router, prefix="/query_understand", tags=["query_understand"])
api_router.include_router(search.router, tags=["search"])