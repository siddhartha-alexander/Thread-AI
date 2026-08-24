from sqlalchemy.orm import Session, selectinload

from backend import models
from backend.schemas import ThreadCreateRequest
from backend.services import anchor_service
from backend.services.llm_service import LLMService


def get_response_or_none(db: Session, response_id: str, user: models.User | None = None) -> models.AIResponse | None:
    query = db.query(models.AIResponse).join(models.Conversation).filter(models.AIResponse.id == response_id)
    if user is not None:
        query = query.filter(models.Conversation.user_id == user.id)
    return query.first()


def get_thread_or_none(db: Session, thread_id: str, user: models.User | None = None) -> models.Thread | None:
    query = (
        db.query(models.Thread)
        .options(selectinload(models.Thread.messages), selectinload(models.Thread.response))
        .join(models.AIResponse)
        .join(models.Conversation)
        .filter(models.Thread.id == thread_id)
    )
    if user is not None:
        query = query.filter(models.Conversation.user_id == user.id)
    return query.first()


async def create_or_continue_thread(db: Session, llm: LLMService, payload: ThreadCreateRequest, user: models.User) -> tuple[models.Thread, str]:
    response = get_response_or_none(db, payload.response_id, user)
    if not response:
        raise LookupError("response not found")
    start_offset, end_offset = anchor_service.resolve_anchor(response, payload.selected_text, payload.start_offset, payload.end_offset)
    thread = anchor_service.find_matching_thread(
        db,
        response_id=payload.response_id,
        selected_text=payload.selected_text,
        start_offset=start_offset,
        end_offset=end_offset,
    )
    if thread is None:
        thread = models.Thread(
            response_id=payload.response_id,
            selected_text=payload.selected_text,
            start_offset=start_offset,
            end_offset=end_offset,
            surrounding_context=_surrounding_context(response.response_text, start_offset, end_offset) or payload.surrounding_context,
        )
        db.add(thread)
        db.flush()
    answer = await append_thread_question(db, llm, thread, payload.question)
    return thread, answer


def _surrounding_context(response_text: str, start_offset: int, end_offset: int) -> str:
    left = max(0, start_offset - 260)
    right = min(len(response_text), end_offset + 260)
    return response_text[left:right]


async def append_thread_question(db: Session, llm: LLMService, thread: models.Thread, question: str) -> str:
    history = [{"role": m.role, "content": m.content} for m in thread.messages]
    user_message = models.ThreadMessage(thread_id=thread.id, role="user", content=question)
    db.add(user_message)
    db.flush()
    answer = await llm.generate_thread_response(
        original_question=thread.response.user_query,
        original_response=thread.response.response_text,
        selected_text=thread.selected_text,
        surrounding_context=thread.surrounding_context,
        history=history,
        current_question=question,
    )
    db.add(models.ThreadMessage(thread_id=thread.id, role="assistant", content=answer))
    db.commit()
    db.refresh(thread)
    return answer
