import logging
from functools import lru_cache

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException

load_dotenv()
logging.basicConfig(level=logging.INFO)

from app.agents import AgentRuntime, orchestrator_runtime
from app.controllers import BrowserController, NativeComputerController
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
def get_browser_controller() -> BrowserController:
    return BrowserController()


@lru_cache
def get_native_controller() -> NativeComputerController:
    return NativeComputerController()


def get_orchestrator(
    provider: LLMProvider = Depends(get_provider),
    browser: BrowserController = Depends(get_browser_controller),
    native: NativeComputerController = Depends(get_native_controller),
) -> AgentRuntime:
    return orchestrator_runtime(provider, browser=browser, native=native)


@app.post("/api/agent/run", response_model=AgentRunResponse)
def agent_run(request: AgentRunRequest, runtime: AgentRuntime = Depends(get_orchestrator)) -> AgentRunResponse:
    result = runtime.run(request.goal)
    return AgentRunResponse(
        task_id=result.task_id,
        success=result.success,
        final_message=result.final_message,
        actions=[ActionSummaryResponse(tool_name=a.tool_name, arguments=a.arguments, result=a.result, is_error=a.is_error) for a in result.actions],
        error=result.error,
    )
