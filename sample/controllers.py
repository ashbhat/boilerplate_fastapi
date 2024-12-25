from fastapi import APIRouter
from sample.schemas import EchoPayload
from sample import services

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
