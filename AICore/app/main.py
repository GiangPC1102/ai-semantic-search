from fastapi import FastAPI

from app.api.routes import api_router

app = FastAPI(title="AICore", version="0.1.0")
app.include_router(api_router)
