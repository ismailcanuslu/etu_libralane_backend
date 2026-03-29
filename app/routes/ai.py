from fastapi import APIRouter
from pydantic import BaseModel
from app.services.ai_service import analyze_log

router = APIRouter(prefix="/ai")

class AIRequest(BaseModel):
    log: str

@router.post("/analyze")
def analyze(request: AIRequest):
    result = analyze_log(request.log)
    return {"analysis": result}
