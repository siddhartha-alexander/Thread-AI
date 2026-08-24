from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


def not_blank(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("value cannot be empty")
    return cleaned


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    conversation_id: str | None = None

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        return not_blank(value)


class ChatResponse(BaseModel):
    conversation_id: str
    response_id: str
    user_query: str
    response_text: str


class PromptEnhanceRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=8000)

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, value: str) -> str:
        return not_blank(value)


class PromptEnhanceResponse(BaseModel):
    original_prompt: str
    enhanced_prompt: str


class UserRead(BaseModel):
    id: str
    email: str
    name: str | None = None
    avatar_url: str | None = None


class AuthStatusResponse(BaseModel):
    authenticated: bool
    user: UserRead | None = None


class AuthConfigResponse(BaseModel):
    google_configured: bool
    dev_auth_enabled: bool


class ThreadCreateRequest(BaseModel):
    response_id: str
    selected_text: str = Field(min_length=1, max_length=4000)
    start_offset: int = Field(ge=0)
    end_offset: int = Field(gt=0)
    surrounding_context: str = Field(min_length=1, max_length=12000)
    question: str = Field(min_length=1, max_length=8000)

    @field_validator("selected_text", "surrounding_context", "question")
    @classmethod
    def validate_text(cls, value: str) -> str:
        return not_blank(value)

    @field_validator("end_offset")
    @classmethod
    def validate_offsets(cls, value: int, info) -> int:
        start = info.data.get("start_offset")
        if start is not None and value <= start:
            raise ValueError("end_offset must be greater than start_offset")
        return value


class FollowUpRequest(BaseModel):
    question: str = Field(min_length=1, max_length=8000)

    @field_validator("question")
    @classmethod
    def validate_question(cls, value: str) -> str:
        return not_blank(value)


class ThreadAnswerResponse(BaseModel):
    thread_id: str
    answer: str


class ThreadMessageRead(BaseModel):
    id: str
    role: str
    content: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ThreadRead(BaseModel):
    id: str
    response_id: str
    selected_text: str
    start_offset: int
    end_offset: int
    surrounding_context: str
    created_at: datetime
    updated_at: datetime
    messages: list[ThreadMessageRead] = []

    model_config = ConfigDict(from_attributes=True)


class HealthResponse(BaseModel):
    status: str
    llm_configured: bool
