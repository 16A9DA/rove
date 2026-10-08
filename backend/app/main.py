import json
import logging
import queue
import uuid
from contextlib import asynccontextmanager
from functools import lru_cache

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse

load_dotenv()
logging.basicConfig(level=logging.INFO)

from app import paused_runs, permissions
from app.activity import Activity, ActivityBus
from agents import AgentRuntime, orchestrator_runtime
from app.controllers import BrowserController, NativeComputerController
from app.help_request import HelpRequest
from app.learning import learn_from_run, record_feedback
from app.keyboard_watcher import CommandKeyWatcher, InputInterruptWatcher
from app.memory import MemoryService
from app.permissions import PermissionGate
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
    ApprovalResponse,
    FeedbackRequest,
    SpeakRequest,
    ModelInfo,
    ModelListResponse,
    ToolCallResponse,
    TranscribeResponse,
)
from app.quick_command import QuickCommand
from app.settings_store import SettingsStore
from app.task_store import TaskStore
from app.tts import MacSayTTS, TextToSpeechProvider, TTSError
from app.stt import MoonshineSTT, SpeechToTextProvider, STTError

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    store = get_task_store()
    paused_runs.configure(store)
    permissions.audit_sink = store.log_permission
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
        speak_results=bool(saved.get("speak_results", True)),
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
def get_task_store() -> TaskStore:
    return TaskStore()


@lru_cache
def get_activity_bus() -> ActivityBus:
    return ActivityBus(sink=get_task_store().record_event)


# Same per-request pattern as the watcher/help request: the route binds the task id,
# the orchestrator emits through it, and Stop (via the bus) folds into the cancel check.
def get_activity(
    bus: ActivityBus = Depends(get_activity_bus), watcher: InputInterruptWatcher = Depends(get_input_watcher)
) -> Activity:
    return Activity(bus, watcher.is_interrupted)


def get_permission_gate(help_request: HelpRequest = Depends(get_help_request)) -> PermissionGate:
    return PermissionGate(help_request)


def get_orchestrator(
    provider: LLMProvider = Depends(get_provider),
    browser: BrowserController = Depends(get_browser_controller),
    native: NativeComputerController = Depends(get_native_controller),
    memory: MemoryService = Depends(get_memory_service),
    activity: Activity = Depends(get_activity),
    help_request: HelpRequest = Depends(get_help_request),
    gate: PermissionGate = Depends(get_permission_gate),
) -> AgentRuntime:
    return orchestrator_runtime(
        provider,
        browser=browser,
        native=native,
        memory=memory,
        cancel_check=activity.cancel_check,
        help_request=help_request,
        on_event=activity.emit,
        gate=gate,
    )


def _run_response(result) -> AgentRunResponse:
    approval = permissions.pending(result.task_id)
    return AgentRunResponse(
        approval=ApprovalResponse(tool=approval.tool, summary=approval.summary) if approval else None,
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
    if result.error not in ("paused", "cancelled") and activity.task_id:
        try:
            learn_from_run(get_memory_service(), get_task_store(), activity.task_id, result.success, result.final_message)
        except Exception as exc:
            log.warning("learning from run failed: %s", type(exc).__name__)
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
    gate: PermissionGate = Depends(get_permission_gate),
) -> AgentRunResponse:
    task_id = request.task_id or str(uuid.uuid4())
    get_task_store().start_run(task_id, request.goal)
    activity.bind(task_id)
    gate.bind(task_id)
    activity.emit({"type": "run_started", "label": "Starting"})
    watcher.start()
    try:
        result = runtime.run(request.goal, cancel_check=activity.cancel_check, question_check=help_request.question, task_id=task_id)
    finally:
        watcher.stop()
    response = _finish_run(result, activity)
    if request.voice and result.error not in ("paused", "cancelled") and SettingsStore().get().get("speak_results", True):
        try:
            get_tts_provider().speak(response.final_message or response.error or "")
        except TTSError as exc:
            log.warning("could not speak result: %s", exc)
    return response


@app.post("/api/agent/resume", response_model=AgentRunResponse)
def agent_resume(
    request: AgentResumeRequest,
    runtime: AgentRuntime = Depends(get_orchestrator),
    watcher: InputInterruptWatcher = Depends(get_input_watcher),
    help_request: HelpRequest = Depends(get_help_request),
    activity: Activity = Depends(get_activity),
    gate: PermissionGate = Depends(get_permission_gate),
) -> AgentRunResponse:
    approval = permissions.pending(request.task_id)
    if approval is not None and request.decision not in ("approve", "deny"):
        raise HTTPException(status_code=400, detail="this run is waiting for an approve/deny decision")
    messages = paused_runs.pop(request.task_id)
    if messages is None:
        raise HTTPException(status_code=404, detail="no paused run for that task_id")
    if approval is not None:
        approved = request.decision == "approve"
        permissions.resolve(request.task_id, approved)
        messages.append(
            {
                "role": "user",
                "content": f"The user {'approved' if approved else 'denied'}: {approval.summary}. "
                + ("You may now perform it." if approved else "Do not do it; choose another way or finish."),
            }
        )
    activity.bind(request.task_id)
    gate.bind(request.task_id)
    activity.emit({"type": "run_started", "label": "Resuming"})
    watcher.start()
    try:
        result = runtime.run(
            task_id=request.task_id, resume_messages=messages, cancel_check=activity.cancel_check, question_check=help_request.question
        )
    finally:
        watcher.stop()
    return _finish_run(result, activity)


@app.get("/api/tasks")
def list_tasks(store: TaskStore = Depends(get_task_store)) -> list[dict]:
    return store.list_tasks()


@app.get("/api/tasks/{task_id}")
def get_task(task_id: str, store: TaskStore = Depends(get_task_store)) -> dict:
    task = store.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="no such task")
    return task


@app.delete("/api/tasks/{task_id}")
def delete_task(task_id: str, store: TaskStore = Depends(get_task_store)) -> dict[str, str]:
    if not store.delete_task(task_id):
        raise HTTPException(status_code=404, detail="no such task")
    return {"status": "deleted"}


@app.post("/api/tasks/{task_id}/feedback")
def task_feedback(
    task_id: str,
    request: FeedbackRequest,
    store: TaskStore = Depends(get_task_store),
    memory: MemoryService = Depends(get_memory_service),
) -> dict[str, str]:
    if request.rating not in ("up", "down"):
        raise HTTPException(status_code=400, detail='rating must be "up" or "down"')
    if not record_feedback(memory, store, task_id, request.rating):
        raise HTTPException(status_code=404, detail="no such task")
    return {"status": "recorded"}


@app.get("/api/memories")
def list_memories(memory: MemoryService = Depends(get_memory_service)) -> list[dict]:
    return memory.list_all()


@app.delete("/api/memories/{memory_id}")
def delete_memory(memory_id: int, memory: MemoryService = Depends(get_memory_service)) -> dict[str, str]:
    if not memory.delete(memory_id):
        raise HTTPException(status_code=404, detail="no such memory")
    return {"status": "deleted"}


@app.post("/api/agent/{task_id}/stop")
def agent_stop(task_id: str, bus: ActivityBus = Depends(get_activity_bus)) -> dict[str, str]:
    bus.request_stop(task_id)
    return {"status": "stopping"}


@app.get("/api/agent/{task_id}/frame")
def agent_frame(task_id: str, bus: ActivityBus = Depends(get_activity_bus)) -> Response:
    image = bus.get_frame(task_id)
    if image is None:
        raise HTTPException(status_code=404, detail="no preview frame for that task_id")
    return Response(content=image, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


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
    gate = PermissionGate(help_request)
    gate.bind(task_id)
    get_task_store().start_run(task_id, goal)

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
        gate=gate,
    )
    watcher.start()
    try:
        result = runtime.run(goal, cancel_check=watcher.is_interrupted, question_check=help_request.question, task_id=task_id)
    finally:
        watcher.stop()
    if result.error not in ("paused", "cancelled"):
        try:
            learn_from_run(get_memory_service(), get_task_store(), task_id, result.success, result.final_message)
        except Exception as exc:
            log.warning("learning from run failed: %s", type(exc).__name__)
    if result.question:
        return False, result.question
    if result.error == "paused":
        return False, "Paused: mouse or keyboard touched."
    return result.success, result.final_message or result.error or ""


@lru_cache
def get_tts_provider() -> TextToSpeechProvider:
    return MacSayTTS()


@app.post("/api/tts/speak")
def tts_speak(request: SpeakRequest, tts: TextToSpeechProvider = Depends(get_tts_provider)) -> dict[str, str]:
    try:
        tts.speak(request.text)
    except TTSError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "speaking"}


@app.post("/api/tts/stop")
def tts_stop(tts: TextToSpeechProvider = Depends(get_tts_provider)) -> dict[str, str]:
    tts.stop()
    return {"status": "stopped"}


@lru_cache
def get_quick_command() -> QuickCommand:
    return QuickCommand(
        get_stt_provider(), _run_quick_goal, get_tts_provider(), lambda: bool(SettingsStore().get().get("speak_results", True))
    )


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
