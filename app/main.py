from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import psycopg
from app.core.config import settings
from app.api.v1 import health

app = FastAPI(
    title=settings.APP_NAME,
    debug=settings.DEBUG
)

# Disable CORS. Do not remove this for full-stack development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# Include API routers
app.include_router(health.router, prefix=settings.API_V1_STR)
