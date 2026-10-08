"""Request/response models for the agent API."""

from pydantic import BaseModel


class AgentMessage(BaseModel):
    role: str
    content: str


class AgentMessageRequest(BaseModel):
    messages: list[AgentMessage]


class ToolCallResponse(BaseModel):
    id: str
    name: str
    arguments: str


class AgentMessageResponse(BaseModel):
    content: str | None
    tool_calls: list[ToolCallResponse]


class AgentRunRequest(BaseModel):
    goal: str
    task_id: str | None = None


class FeedbackRequest(BaseModel):
    rating: str  # "up" | "down"


class AgentResumeRequest(BaseModel):
    task_id: str
    decision: str | None = None  # "approve" | "deny" when the run paused for an approval


class ActionSummaryResponse(BaseModel):
    tool_name: str
    arguments: str
    result: str
    is_error: bool


class ApprovalResponse(BaseModel):
    tool: str
    summary: str


class AgentRunResponse(BaseModel):
    task_id: str
    success: bool
    final_message: str | None
    actions: list[ActionSummaryResponse]
    error: str | None = None
    question: str | None = None
    approval: ApprovalResponse | None = None


class TranscribeResponse(BaseModel):
    transcript: str


class AppSettingsResponse(BaseModel):
    provider: str
    model: str | None
    has_anthropic_key: bool
    has_openai_key: bool


class AppSettingsUpdate(BaseModel):
    provider: str | None = None
    model: str | None = None
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None


class ModelInfo(BaseModel):
    id: str
    display_name: str


class ModelListResponse(BaseModel):
    models: list[ModelInfo]
