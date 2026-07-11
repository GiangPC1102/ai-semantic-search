from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import api_router
from app.core.config import settings
from app.core.database import connect_db, disconnect_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Kết nối / ngắt kết nối database theo vòng đời app."""
    await connect_db()
    yield
    await disconnect_db()


app = FastAPI(
    title="AICore",
    version="0.1.0",
    lifespan=lifespan,
    # Nginx mounts API under /api — Swagger must fetch /api/openapi.json
    root_path=settings.ROOT_PATH,
)
app.include_router(api_router)
