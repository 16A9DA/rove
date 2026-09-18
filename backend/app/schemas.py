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
