from fastapi import FastAPI
from api.routers.schedule import router as schedule_router

app = FastAPI(
    title="Scheduling API",
    version="1.0.0",
)

@app.get("/health")
def health_check():
    return {"status": "ok"}

app.include_router(schedule_router)