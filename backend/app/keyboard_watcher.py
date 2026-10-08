from __future__ import annotations

import threading

import Quartz

_INTERRUPT_MASK = (
    Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown)
    | Quartz.CGEventMaskBit(Quartz.kCGEventLeftMouseDown)
    | Quartz.CGEventMaskBit(Quartz.kCGEventRightMouseDown)
    | Quartz.CGEventMaskBit(Quartz.kCGEventOtherMouseDown)
    | Quartz.CGEventMaskBit(Quartz.kCGEventScrollWheel)
    | Quartz.CGEventMaskBit(Quartz.kCGEventMouseMoved)
)


class InputInterruptWatcher:
    """Global (listen-only) event tap that flags any real mouse/keyboard touch
    (move, click, scroll, keypress) so an in-progress agent run pauses instead of
    fighting the user for control. Ignores events tagged with `own_source_state_id`
    so Rove's own synthetic input (NativeComputerController) never self-pauses a run."""

    def __init__(self, own_source_state_id: int | None = None) -> None:
        self._own_source_state_id = own_source_state_id
        self._interrupted = threading.Event()
        self._run_loop = None
        self._thread: threading.Thread | None = None

    def is_interrupted(self) -> bool:
        return self._interrupted.is_set()

    def _callback(self, proxy, event_type, event, refcon):
        source_id = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGEventSourceStateID)
        if source_id != self._own_source_state_id:
            self._interrupted.set()
        return event

    def start(self) -> None:
        def _run() -> None:
            tap = Quartz.CGEventTapCreate(
                Quartz.kCGSessionEventTap,
                Quartz.kCGHeadInsertEventTap,
                Quartz.kCGEventTapOptionListenOnly,
                _INTERRUPT_MASK,
                self._callback,
                None,
            )
            if tap is None:
                # No Input Monitoring/Accessibility grant — pause-on-touch just won't
                # fire; the run still stops normally on timeout/finish/max_steps.
                return
            source = Quartz.CFMachPortCreateRunLoopSource(None, tap, 0)
            self._run_loop = Quartz.CFRunLoopGetCurrent()
            Quartz.CFRunLoopAddSource(self._run_loop, source, Quartz.kCFRunLoopCommonModes)
            Quartz.CGEventTapEnable(tap, True)
            Quartz.CFRunLoopRun()

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._run_loop is not None:
            Quartz.CFRunLoopStop(self._run_loop)
        if self._thread is not None:
            self._thread.join(timeout=1.0)


_COMMAND_MASK = Quartz.CGEventMaskBit(Quartz.kCGEventFlagsChanged) | Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown)


class CommandKeyWatcher:
    # A bare Command hold (no other key pressed) for `hold_seconds` fires on_hold; releasing
    # Command after that fires on_release. Cmd+C and friends are chords, so they never fire.
    def __init__(self, on_hold, on_release, own_source_state_id: int | None = None, hold_seconds: float = 0.35) -> None:
        self._on_hold = on_hold
        self._on_release = on_release
        self._own_source_state_id = own_source_state_id
        self._hold_seconds = hold_seconds
        self._lock = threading.Lock()
        self._cmd_down = False
        self._chord = False
        self._active = False
        self._timer: threading.Timer | None = None
        self._run_loop = None
        self._thread: threading.Thread | None = None

    def _fire(self) -> None:
        with self._lock:
            if not self._cmd_down or self._chord:
                return
            self._active = True
        self._on_hold()

    def _callback(self, proxy, event_type, event, refcon):
        if Quartz.CGEventGetIntegerValueField(event, Quartz.kCGEventSourceStateID) == self._own_source_state_id:
            return event
        release = False
        with self._lock:
            if event_type == Quartz.kCGEventKeyDown:
                self._chord = True
                if self._timer is not None:
                    self._timer.cancel()
            else:
                cmd = bool(Quartz.CGEventGetFlags(event) & Quartz.kCGEventFlagMaskCommand)
                if cmd and not self._cmd_down:
                    self._cmd_down = True
                    self._chord = False
                    self._timer = threading.Timer(self._hold_seconds, self._fire)
                    self._timer.start()
                elif not cmd and self._cmd_down:
                    self._cmd_down = False
                    if self._timer is not None:
                        self._timer.cancel()
                    release, self._active = self._active, False
        if release:
            self._on_release()
        return event

    def start(self) -> bool:
        ready = threading.Event()
        created: list[bool] = []

        def _run() -> None:
            tap = Quartz.CGEventTapCreate(
                Quartz.kCGSessionEventTap,
                Quartz.kCGHeadInsertEventTap,
                Quartz.kCGEventTapOptionListenOnly,
                _COMMAND_MASK,
                self._callback,
                None,
            )
            created.append(tap is not None)
            ready.set()
            if tap is None:
                return
            source = Quartz.CFMachPortCreateRunLoopSource(None, tap, 0)
            self._run_loop = Quartz.CFRunLoopGetCurrent()
            Quartz.CFRunLoopAddSource(self._run_loop, source, Quartz.kCFRunLoopCommonModes)
            Quartz.CGEventTapEnable(tap, True)
            Quartz.CFRunLoopRun()

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()
        ready.wait(timeout=2.0)
        return bool(created and created[0])

    def stop(self) -> None:
        if self._run_loop is not None:
            Quartz.CFRunLoopStop(self._run_loop)
        if self._thread is not None:
            self._thread.join(timeout=1.0)
