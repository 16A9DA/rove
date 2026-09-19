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


class ActionSummaryResponse(BaseModel):
    tool_name: str
    arguments: str
    result: str
    is_error: bool


class AgentRunResponse(BaseModel):
    task_id: str
    success: bool
    final_message: str | None
    actions: list[ActionSummaryResponse]
    error: str | None = None


class TranscribeResponse(BaseModel):
    transcript: str
