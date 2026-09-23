from __future__ import annotations

import threading

import Quartz

_Q_KEYCODE = 0x0C  # ANSI-US 'q'


class QuitKeyWatcher:
    """Global (listen-only) event tap that flags a physical 'q' keypress so an
    in-progress agent run can be cancelled mid-task. Ignores keystrokes tagged with
    `own_source_state_id` so Rove's own synthetic typing (NativeComputerController)
    never self-cancels a run."""

    def __init__(self, own_source_state_id: int | None = None) -> None:
        self._own_source_state_id = own_source_state_id
        self._cancelled = threading.Event()
        self._run_loop = None
        self._thread: threading.Thread | None = None

    def is_cancelled(self) -> bool:
        return self._cancelled.is_set()

    def _callback(self, proxy, event_type, event, refcon):
        if event_type == Quartz.kCGEventKeyDown:
            keycode = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode)
            source_id = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGEventSourceStateID)
            if keycode == _Q_KEYCODE and source_id != self._own_source_state_id:
                self._cancelled.set()
        return event

    def start(self) -> None:
        def _run() -> None:
            tap = Quartz.CGEventTapCreate(
                Quartz.kCGSessionEventTap,
                Quartz.kCGHeadInsertEventTap,
                Quartz.kCGEventTapOptionListenOnly,
                Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown),
                self._callback,
                None,
            )
            if tap is None:
                # No Input Monitoring/Accessibility grant — cancel-by-key just won't
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
