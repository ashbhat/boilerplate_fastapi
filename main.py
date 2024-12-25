from fastapi import FastAPI
from sample.controllers import router as sample_router

app = FastAPI()
app.include_router(sample_router)

@app.get("/")
async def root():
    return {"message": "Hello World"}
