from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    """Application settings."""
    APP_NAME: str = "FastAPI Boilerplate"
    DEBUG: bool = False
    API_V1_STR: str = "/api/v1"
    
    # Add your environment variables here
    DATABASE_URL: Optional[str] = None
    
    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()
