from fastapi import FastAPI
from app.routes.run import router as run_router
from app.routes.jobs import router as jobs_router
from app.routes.ai import router as ai_router


app = FastAPI(title="Chip AI Tool Backend")

app.include_router(run_router)
app.include_router(jobs_router)
app.include_router(ai_router)

@app.get("/")
def root():
    return {"status": "backend running"}
