from fastapi import APIRouter
from api.sample.controllers import router as sample_router

api_router = APIRouter()

# Include all sub-routers
api_router.include_router(sample_router)