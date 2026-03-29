from fastapi import APIRouter
from pydantic import BaseModel
from app.services.tool_runner import run_command

router = APIRouter(prefix="/run")

class RunRequest(BaseModel):
    action: str
    project_path: str

@router.post("/")
def run(request: RunRequest):
    return run_command(
        request.action,
        request.project_path
    )
