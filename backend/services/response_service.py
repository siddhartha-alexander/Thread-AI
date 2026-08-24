from sqlalchemy.orm import Session

from backend import models
from backend.services.llm_service import LLMService


async def create_chat_response(
    db: Session,
    llm: LLMService,
    message: str,
    user: models.User,
    conversation_id: str | None = None,
) -> models.AIResponse:
    response_text = await llm.generate_main_response(message)
    if conversation_id:
        conversation = (
            db.query(models.Conversation)
            .filter(models.Conversation.id == conversation_id, models.Conversation.user_id == user.id)
            .first()
        )
        if conversation is None:
            raise LookupError("conversation not found")
    else:
        conversation = models.Conversation(title=message[:120], user_id=user.id)
        db.add(conversation)
        db.flush()
    response = models.AIResponse(conversation_id=conversation.id, user_query=message, response_text=response_text)
    db.add(response)
    db.commit()
    db.refresh(response)
    return response
