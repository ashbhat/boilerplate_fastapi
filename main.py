from fastapi import FastAPI
from api.router import api_router

app = FastAPI()
app.include_router(api_router)

@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.get("/healthz", include_in_schema=False)
async def health():
    return {"status": "ok"}
