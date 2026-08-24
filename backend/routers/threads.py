from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, selectinload

from backend import models
from backend.auth import get_current_user
from backend.database import get_db
from backend.routers.chat import get_llm
from backend.schemas import FollowUpRequest, ThreadAnswerResponse, ThreadCreateRequest, ThreadRead
from backend.services.llm_service import LLMService
from backend.services.thread_service import append_thread_question, create_or_continue_thread, get_thread_or_none

router = APIRouter(prefix="/api", tags=["threads"])


@router.post("/threads", response_model=ThreadAnswerResponse, status_code=201)
async def create_thread(
    payload: ThreadCreateRequest,
    db: Session = Depends(get_db),
    llm: LLMService = Depends(get_llm),
    user: models.User = Depends(get_current_user),
) -> ThreadAnswerResponse:
    try:
        thread, answer = await create_or_continue_thread(db, llm, payload, user)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Response not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return ThreadAnswerResponse(thread_id=thread.id, answer=answer)


@router.post("/threads/{thread_id}/messages", response_model=ThreadAnswerResponse)
async def follow_up(
    thread_id: str,
    payload: FollowUpRequest,
    db: Session = Depends(get_db),
    llm: LLMService = Depends(get_llm),
    user: models.User = Depends(get_current_user),
) -> ThreadAnswerResponse:
    thread = get_thread_or_none(db, thread_id, user)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found.")
    try:
        answer = await append_thread_question(db, llm, thread, payload.question)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return ThreadAnswerResponse(thread_id=thread.id, answer=answer)


@router.get("/threads/{thread_id}", response_model=ThreadRead)
def get_thread(thread_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)) -> models.Thread:
    thread = get_thread_or_none(db, thread_id, user)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found.")
    return thread


@router.get("/responses/{response_id}/threads", response_model=list[ThreadRead])
def get_response_threads(
    response_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> list[models.Thread]:
    response = (
        db.query(models.AIResponse)
        .join(models.Conversation)
        .filter(models.AIResponse.id == response_id, models.Conversation.user_id == user.id)
        .first()
    )
    if not response:
        raise HTTPException(status_code=404, detail="Response not found.")
    return (
        db.query(models.Thread)
        .options(selectinload(models.Thread.messages))
        .join(models.AIResponse)
        .join(models.Conversation)
        .filter(models.Thread.response_id == response_id)
        .filter(models.Conversation.user_id == user.id)
        .order_by(models.Thread.created_at)
        .all()
    )
