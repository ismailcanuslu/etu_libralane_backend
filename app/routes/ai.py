from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.ai_service import analyze_log, chat_reply

router = APIRouter(prefix="/ai")


class AIRequest(BaseModel):
    log: str


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    history: list[ChatMessage] = Field(default_factory=list)


@router.post("/analyze")
def analyze(request: AIRequest):
    result = analyze_log(request.log)
    return {"analysis": result}


@router.post("/chat")
def chat(request: ChatRequest):
    result = chat_reply(
        request.message,
        [{"role": item.role, "content": item.content} for item in request.history],
    )
    return {"reply": result}
