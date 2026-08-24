from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, selectinload

from backend import models
from backend.auth import get_current_user
from backend.database import get_db
from backend.schemas import ChatRequest, ChatResponse, ConversationRead, ConversationSummary, PromptEnhanceRequest, PromptEnhanceResponse
from backend.services.llm_service import LLMService
from backend.services.response_service import create_chat_response
from backend.config import get_settings

router = APIRouter(prefix="/api", tags=["chat"])


def get_llm() -> LLMService:
    return LLMService(get_settings())


@router.post("/chat", response_model=ChatResponse, status_code=201)
async def chat(
    payload: ChatRequest,
    db: Session = Depends(get_db),
    llm: LLMService = Depends(get_llm),
    user: models.User = Depends(get_current_user),
) -> ChatResponse:
    try:
        response = await create_chat_response(db, llm, payload.message, user, payload.conversation_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Conversation not found.") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return ChatResponse(
        conversation_id=response.conversation_id,
        response_id=response.id,
        user_query=response.user_query,
        response_text=response.response_text,
    )


@router.post("/enhance-prompt", response_model=PromptEnhanceResponse)
async def enhance_prompt(
    payload: PromptEnhanceRequest,
    llm: LLMService = Depends(get_llm),
    user: models.User = Depends(get_current_user),
) -> PromptEnhanceResponse:
    try:
        enhanced = await llm.enhance_prompt(payload.prompt)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return PromptEnhanceResponse(original_prompt=payload.prompt, enhanced_prompt=enhanced)


@router.get("/conversations", response_model=list[ConversationSummary])
def list_conversations(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> list[models.Conversation]:
    return (
        db.query(models.Conversation)
        .filter(models.Conversation.user_id == user.id)
        .order_by(models.Conversation.updated_at.desc(), models.Conversation.created_at.desc())
        .all()
    )


@router.get("/conversations/{conversation_id}", response_model=ConversationRead)
def get_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> models.Conversation:
    conversation = (
        db.query(models.Conversation)
        .options(
            selectinload(models.Conversation.responses)
            .selectinload(models.AIResponse.threads)
            .selectinload(models.Thread.messages)
        )
        .filter(models.Conversation.id == conversation_id, models.Conversation.user_id == user.id)
        .first()
    )
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return conversation
