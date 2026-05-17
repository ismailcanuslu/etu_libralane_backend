from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.db import init_db
from app.routes.ai import router as ai_router
from app.routes.jobs import router as jobs_router
from app.routes.run import router as run_router
from app.routes.tools import router as tools_router
from app.routes.files import router as files_router
from app.routes.terminal import router as terminal_router
from app.routes.layout import router as layout_router
from app.routes.autonom import router as autonom_router
from app.routes.system import router as system_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    from app.services.tool_runner import reconcile_stale_jobs

    await reconcile_stale_jobs()
    yield


app = FastAPI(title="Chip AI Tool Backend", lifespan=lifespan, redirect_slashes=False)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tools_router)
app.include_router(run_router)
app.include_router(jobs_router)
app.include_router(ai_router)
app.include_router(files_router)
app.include_router(terminal_router)
app.include_router(layout_router)
app.include_router(autonom_router)
app.include_router(system_router)


@app.get("/")
def root():
    return {"status": "backend running", "service": "etu-libralane-backend"}


@app.get("/health")
def health():
    return {"status": "ok"}
