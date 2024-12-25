from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional

class BaseSchema(BaseModel):
    """Base schema with common configuration."""
    model_config = ConfigDict(from_attributes=True)

class TimestampedSchema(BaseSchema):
    """Base schema with timestamp fields."""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
