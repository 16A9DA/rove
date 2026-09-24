import logging
from functools import lru_cache

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()
logging.basicConfig(level=logging.INFO)

from app import paused_runs
from app.agents import AgentRuntime, orchestrator_runtime
from app.controllers import BrowserController, NativeComputerController
from app.help_request import HelpRequest
from app.keyboard_watcher import InputInterruptWatcher
from app.memory import MemoryService
from app.providers import AnthropicProvider, LLMProvider, LLMProviderError
from app.schemas import (
    ActionSummaryResponse,
    AgentMessageRequest,
    AgentMessageResponse,
    AgentResumeRequest,
    AgentRunRequest,
    AgentRunResponse,
    ToolCallResponse,
    TranscribeResponse,
)
from app.stt import MoonshineSTT, SpeechToTextProvider, STTError

app = FastAPI(title="Rove Agent API")

# Local desktop app only (Electron/localhost frontend calling a 127.0.0.1 backend),
# never exposed publicly — allow-all is fine and avoids per-origin config.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@lru_cache
def get_provider() -> LLMProvider:
    try:
        return AnthropicProvider()
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


@lru_cache
def get_memory_service() -> MemoryService:
    return MemoryService()


# Not lru_cache'd — a fresh watcher per request, but FastAPI caches it within that one
# request's dependency graph, so get_orchestrator and agent_run share the same instance.
def get_input_watcher(native: NativeComputerController = Depends(get_native_controller)) -> InputInterruptWatcher:
    return InputInterruptWatcher(native.source_state_id)


# Not lru_cache'd, same reasoning as get_input_watcher — fresh per request/resume so a
# resolved blocker doesn't stay "pending" forever, but shared within one request's graph.
def get_help_request() -> HelpRequest:
    return HelpRequest()


def get_orchestrator(
    provider: LLMProvider = Depends(get_provider),
    browser: BrowserController = Depends(get_browser_controller),
    native: NativeComputerController = Depends(get_native_controller),
    memory: MemoryService = Depends(get_memory_service),
    watcher: InputInterruptWatcher = Depends(get_input_watcher),
    help_request: HelpRequest = Depends(get_help_request),
) -> AgentRuntime:
    return orchestrator_runtime(
        provider, browser=browser, native=native, memory=memory, cancel_check=watcher.is_interrupted, help_request=help_request
    )


def _run_response(result) -> AgentRunResponse:
    return AgentRunResponse(
        task_id=result.task_id,
        success=result.success,
        final_message=result.final_message,
        actions=[ActionSummaryResponse(tool_name=a.tool_name, arguments=a.arguments, result=a.result, is_error=a.is_error) for a in result.actions],
        error=result.error,
        question=result.question,
    )


@app.post("/api/agent/run", response_model=AgentRunResponse)
def agent_run(
    request: AgentRunRequest,
    runtime: AgentRuntime = Depends(get_orchestrator),
    watcher: InputInterruptWatcher = Depends(get_input_watcher),
    help_request: HelpRequest = Depends(get_help_request),
) -> AgentRunResponse:
    watcher.start()
    try:
        result = runtime.run(request.goal, cancel_check=watcher.is_interrupted, question_check=help_request.question)
    finally:
        watcher.stop()
    return _run_response(result)


@app.post("/api/agent/resume", response_model=AgentRunResponse)
def agent_resume(
    request: AgentResumeRequest,
    runtime: AgentRuntime = Depends(get_orchestrator),
    watcher: InputInterruptWatcher = Depends(get_input_watcher),
    help_request: HelpRequest = Depends(get_help_request),
) -> AgentRunResponse:
    messages = paused_runs.pop(request.task_id)
    if messages is None:
        raise HTTPException(status_code=404, detail="no paused run for that task_id")
    watcher.start()
    try:
        result = runtime.run(
            task_id=request.task_id, resume_messages=messages, cancel_check=watcher.is_interrupted, question_check=help_request.question
        )
    finally:
        watcher.stop()
    return _run_response(result)


@lru_cache
def get_stt_provider() -> SpeechToTextProvider:
    return MoonshineSTT()


@app.post("/api/stt/start")
def stt_start(stt: SpeechToTextProvider = Depends(get_stt_provider)) -> dict[str, str]:
    try:
        stt.start_recording()
    except STTError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "recording"}


@app.post("/api/stt/stop", response_model=TranscribeResponse)
def stt_stop(stt: SpeechToTextProvider = Depends(get_stt_provider)) -> TranscribeResponse:
    try:
        transcript = stt.stop_recording()
    except STTError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return TranscribeResponse(transcript=transcript)
