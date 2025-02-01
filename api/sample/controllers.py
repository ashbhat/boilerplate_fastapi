from fastapi import APIRouter
from api.sample.schemas import EchoPayload
from api.sample import services

router = APIRouter(
    prefix="/sample",
    tags=["sample"],
)

@router.get("/")
async def echo():
    return "hello"

@router.post("/echo")
async def echo(payload: EchoPayload):
    return await services.echo(payload)
