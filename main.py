from fastapi import FastAPI
from api.routers.schedule import router as schedule_router
from api.routers.recommendation import router as recommendation_router

app = FastAPI(
    title="Scheduling API",
    version="1.0.0",
)

@app.get("/health")
def health_check():
    return {"status": "ok"}

app.include_router(schedule_router, prefix="/api", tags=["schedule"])
app.include_router(recommendation_router, prefix="/api", tags=["recommendation"])