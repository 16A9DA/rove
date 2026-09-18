import logging
from functools import lru_cache

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException

load_dotenv()
logging.basicConfig(level=logging.INFO)

from app.agent import AgentRuntime
from app.environment import ComputerEnvironment
from app.providers import LLMProvider, LLMProviderError, GroqProvider
from app.schemas import (
    ActionSummaryResponse,
    AgentMessageRequest,
    AgentMessageResponse,
    AgentRunRequest,
    AgentRunResponse,
    ToolCallResponse,
)

app = FastAPI(title="Rove Agent API")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@lru_cache
def get_provider() -> LLMProvider:
    try:
        return GroqProvider()
    except LLMProviderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@app.post("/api/agent/message", response_model=AgentMessageResponse)
def agent_message(
    request: AgentMessageRequest,
    provider: LLMProvider = Depends(get_provider),
) -> AgentMessageResponse:
    try:
        result = provider.complete([m.model_dump() for m in request.messages])
    except LLMProviderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    return AgentMessageResponse(
        content=result.content,
        tool_calls=[ToolCallResponse(id=tc.id, name=tc.name, arguments=tc.arguments) for tc in result.tool_calls],
    )


@lru_cache
def get_environment() -> ComputerEnvironment:
    return ComputerEnvironment()


def get_agent_runtime(
    provider: LLMProvider = Depends(get_provider),
    environment: ComputerEnvironment = Depends(get_environment),
) -> AgentRuntime:
    return AgentRuntime(provider, environment)


@app.post("/api/agent/run", response_model=AgentRunResponse)
def agent_run(request: AgentRunRequest, runtime: AgentRuntime = Depends(get_agent_runtime)) -> AgentRunResponse:
    result = runtime.run(request.goal)
    return AgentRunResponse(
        task_id=result.task_id,
        success=result.success,
        final_message=result.final_message,
        actions=[ActionSummaryResponse(tool_name=a.tool_name, arguments=a.arguments, result=a.result, is_error=a.is_error) for a in result.actions],
        error=result.error,
    )
