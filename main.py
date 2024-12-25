from fastapi import FastAPI
from sample.controllers import router as sample_router
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Replace with your domain in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app = FastAPI()
app.include_router(sample_router)

@app.get("/")
async def root():
    return {"message": "Hello World"}
