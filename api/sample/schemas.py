from pydantic import BaseModel

class EchoPayload(BaseModel):
  content: str
