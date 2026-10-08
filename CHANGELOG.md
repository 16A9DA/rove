# Changelog

## 0.2.0 (not released, not verified)

Everything below was built without running tests, lint, type checks or a live session. Run `scripts/e2e_smoke.py` and the test suites before relying on it.

Added

* Command hold push to talk with a floating popover and menu bar status.
* Live agent activity (step feed over server sent events), Stop, and a live preview of the screen or page.
* Permission gate for risky clicks and keypresses, with Approve and Cancel in the app and an audit log.
* Files specialist limited to Desktop, Documents and Downloads, with Trash instead of delete.
* Clipboard and window tools for tasks that span several apps.
* Loop and failure recovery, browser crash recovery, empty reply handling.
* Prompt injection defenses: untrusted content wrapping, http(s) only browsing, no private network fetches.
* Task persistence in SQLite with resumable paused runs and a permission audit trail.
* Memory that learns episodes and workflows from finished runs, ratings, a recall tool, and a memory list in Settings.
* Spoken results through macOS `say`.
* Keyboard shortcuts, accessibility labels, task deletion, backend down and loading states.
* Local API token required on every `/api` call; Electron sandbox and navigation lockdown.
* The desktop app starts and stops the backend.
* Typed chat now runs the real agent (the simulated loop is gone).

Changed

* Task history and memory use SQLite instead of the PostgreSQL named in the original plan.

Not done

* Packaged installer. Bundling the Python backend and PyTorch is not solved.
* Approving a permission request from the Command hold popover.
* Following popups and new browser tabs.

## 0.1.0

Initial scaffold, desktop shell, tool framework, browser and native controllers, multi agent orchestration, memory, voice input, provider settings (Claude and ChatGPT), accessibility grounded native clicks.
