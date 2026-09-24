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
