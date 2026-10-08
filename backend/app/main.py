import json
import logging
import queue
import uuid
from contextlib import asynccontextmanager
from functools import lru_cache

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

load_dotenv()
logging.basicConfig(level=logging.INFO)

from app import paused_runs
from app.activity import Activity, ActivityBus
from agents import AgentRuntime, orchestrator_runtime
from app.controllers import BrowserController, NativeComputerController
from app.help_request import HelpRequest
from app.keyboard_watcher import CommandKeyWatcher, InputInterruptWatcher
from app.memory import MemoryService
from app.providers import (
    AnthropicProvider,
    LLMProvider,
    LLMProviderError,
    OpenAIProvider,
    list_anthropic_models,
    list_openai_models,
)
from app.schemas import (
    ActionSummaryResponse,
    AgentMessageRequest,
    AgentMessageResponse,
    AgentResumeRequest,
    AgentRunRequest,
    AgentRunResponse,
    AppSettingsResponse,
    AppSettingsUpdate,
    ModelInfo,
    ModelListResponse,
    ToolCallResponse,
    TranscribeResponse,
)
from app.quick_command import QuickCommand
from app.settings_store import SettingsStore
from app.stt import MoonshineSTT, SpeechToTextProvider, STTError

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    quick = get_quick_command()
    watcher = CommandKeyWatcher(quick.on_hold, quick.on_release, get_native_controller().source_state_id)
    if not watcher.start():
        log.warning("Command push-to-talk unavailable: grant Input Monitoring/Accessibility to this process")
    yield
    watcher.stop()


app = FastAPI(title="Rove Agent API", lifespan=lifespan)

# Local desktop app only (Electron/localhost frontend calling a 127.0.0.1 backend),
# never exposed publicly — allow-all is fine and avoids per-origin config.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def get_settings_store() -> SettingsStore:
    return SettingsStore()


# Not lru_cache'd — provider/model/key are user-editable via Settings, so each request
# must read the current choice rather than freezing the first one ever constructed.
def get_provider(settings: SettingsStore = Depends(get_settings_store)) -> LLMProvider:
    saved = settings.get()
    try:
        if saved["provider"] == "openai":
            return OpenAIProvider(api_key=saved.get("openai_api_key"), model=saved.get("model"))
        return AnthropicProvider(api_key=saved.get("anthropic_api_key"), model=saved.get("model"))
    except LLMProviderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


def _settings_response(saved: dict) -> AppSettingsResponse:
    return AppSettingsResponse(
        provider=saved["provider"],
        model=saved.get("model"),
        has_anthropic_key=bool(saved.get("anthropic_api_key")),
        has_openai_key=bool(saved.get("openai_api_key")),
    )


@app.get("/api/settings", response_model=AppSettingsResponse)
def get_app_settings(settings: SettingsStore = Depends(get_settings_store)) -> AppSettingsResponse:
    return _settings_response(settings.get())


@app.put("/api/settings", response_model=AppSettingsResponse)
def update_app_settings(request: AppSettingsUpdate, settings: SettingsStore = Depends(get_settings_store)) -> AppSettingsResponse:
    return _settings_response(settings.update(request.model_dump(exclude_none=True)))


@app.get("/api/models", response_model=ModelListResponse)
def list_models(provider: str, settings: SettingsStore = Depends(get_settings_store)) -> ModelListResponse:
    saved = settings.get()
    key = saved.get("openai_api_key") if provider == "openai" else saved.get("anthropic_api_key")
    if not key:
        raise HTTPException(status_code=400, detail=f"no {provider} API key saved")
    try:
        models = list_openai_models(key) if provider == "openai" else list_anthropic_models(key)
    except LLMProviderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ModelListResponse(models=[ModelInfo(**m) for m in models])


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


@lru_cache
def get_activity_bus() -> ActivityBus:
    return ActivityBus()


# Same per-request pattern as the watcher/help request: the route binds the task id,
# the orchestrator emits through it, and Stop (via the bus) folds into the cancel check.
def get_activity(
    bus: ActivityBus = Depends(get_activity_bus), watcher: InputInterruptWatcher = Depends(get_input_watcher)
) -> Activity:
    return Activity(bus, watcher.is_interrupted)


def get_orchestrator(
    provider: LLMProvider = Depends(get_provider),
    browser: BrowserController = Depends(get_browser_controller),
    native: NativeComputerController = Depends(get_native_controller),
    memory: MemoryService = Depends(get_memory_service),
    activity: Activity = Depends(get_activity),
    help_request: HelpRequest = Depends(get_help_request),
) -> AgentRuntime:
    return orchestrator_runtime(
        provider,
        browser=browser,
        native=native,
        memory=memory,
        cancel_check=activity.cancel_check,
        help_request=help_request,
        on_event=activity.emit,
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


def _finish_run(result, activity: Activity):
    # A Stop looks like a pause to the loop (state saved); drop that state so it can't be resumed.
    if result.error == "paused" and activity.stopped():
        paused_runs.pop(result.task_id)
        result.error = "cancelled"
        result.question = None
    activity.clear_stop()
    if result.error == "paused":
        status = "paused"
    elif result.error == "cancelled":
        status = "cancelled"
    else:
        status = "ok" if result.success else "error"
    activity.emit({"type": "run_finished", "status": status, "message": result.question or result.final_message or result.error or ""})
    return _run_response(result)


@app.post("/api/agent/run", response_model=AgentRunResponse)
def agent_run(
    request: AgentRunRequest,
    runtime: AgentRuntime = Depends(get_orchestrator),
    watcher: InputInterruptWatcher = Depends(get_input_watcher),
    help_request: HelpRequest = Depends(get_help_request),
    activity: Activity = Depends(get_activity),
) -> AgentRunResponse:
    task_id = request.task_id or str(uuid.uuid4())
    activity.bind(task_id)
    activity.emit({"type": "run_started", "label": "Starting"})
    watcher.start()
    try:
        result = runtime.run(request.goal, cancel_check=activity.cancel_check, question_check=help_request.question, task_id=task_id)
    finally:
        watcher.stop()
    return _finish_run(result, activity)


@app.post("/api/agent/resume", response_model=AgentRunResponse)
def agent_resume(
    request: AgentResumeRequest,
    runtime: AgentRuntime = Depends(get_orchestrator),
    watcher: InputInterruptWatcher = Depends(get_input_watcher),
    help_request: HelpRequest = Depends(get_help_request),
    activity: Activity = Depends(get_activity),
) -> AgentRunResponse:
    messages = paused_runs.pop(request.task_id)
    if messages is None:
        raise HTTPException(status_code=404, detail="no paused run for that task_id")
    activity.bind(request.task_id)
    activity.emit({"type": "run_started", "label": "Resuming"})
    watcher.start()
    try:
        result = runtime.run(
            task_id=request.task_id, resume_messages=messages, cancel_check=activity.cancel_check, question_check=help_request.question
        )
    finally:
        watcher.stop()
    return _finish_run(result, activity)


@app.post("/api/agent/{task_id}/stop")
def agent_stop(task_id: str, bus: ActivityBus = Depends(get_activity_bus)) -> dict[str, str]:
    bus.request_stop(task_id)
    return {"status": "stopping"}


@app.get("/api/agent/{task_id}/events")
def agent_events(task_id: str, after: int = 0, bus: ActivityBus = Depends(get_activity_bus)) -> StreamingResponse:
    def stream():
        backlog, q = bus.subscribe(task_id, after)
        try:
            for event in backlog:
                yield f"data: {json.dumps(event)}\n\n"
                if event["type"] == "run_finished":
                    return
            while True:
                try:
                    event = q.get(timeout=15)
                except queue.Empty:
                    yield ": keepalive\n\n"
                    continue
                yield f"data: {json.dumps(event)}\n\n"
                if event["type"] == "run_finished":
                    return
        finally:
            bus.unsubscribe(task_id, q)

    return StreamingResponse(stream(), media_type="text/event-stream")


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


def _run_quick_goal(goal: str, on_step) -> tuple[bool, str]:
    try:
        provider = get_provider(get_settings_store())
    except HTTPException as exc:
        return False, str(exc.detail)
    native = get_native_controller()
    watcher = InputInterruptWatcher(native.source_state_id)
    help_request = HelpRequest()
    activity = Activity(get_activity_bus(), watcher.is_interrupted)
    task_id = str(uuid.uuid4())
    activity.bind(task_id)

    def on_event(event: dict) -> None:
        activity.emit(event)
        if event["type"] == "step" and event["status"] == "running":
            on_step(event["label"])

    runtime = orchestrator_runtime(
        provider,
        browser=get_browser_controller(),
        native=native,
        memory=get_memory_service(),
        cancel_check=watcher.is_interrupted,
        help_request=help_request,
        on_event=on_event,
    )
    watcher.start()
    try:
        result = runtime.run(goal, cancel_check=watcher.is_interrupted, question_check=help_request.question, task_id=task_id)
    finally:
        watcher.stop()
    if result.question:
        return False, result.question
    if result.error == "paused":
        return False, "Paused: mouse or keyboard touched."
    return result.success, result.final_message or result.error or ""


@lru_cache
def get_quick_command() -> QuickCommand:
    return QuickCommand(get_stt_provider(), _run_quick_goal)


@app.get("/api/quick/events")
def quick_events(quick: QuickCommand = Depends(get_quick_command)) -> StreamingResponse:
    def stream():
        q = quick.subscribe()
        try:
            while True:
                try:
                    yield f"data: {json.dumps(q.get(timeout=15))}\n\n"
                except queue.Empty:
                    yield ": keepalive\n\n"
        finally:
            quick.unsubscribe(q)

    return StreamingResponse(stream(), media_type="text/event-stream")
