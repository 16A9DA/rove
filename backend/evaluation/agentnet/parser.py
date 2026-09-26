from __future__ import annotations

import ast
from typing import Any

from .schema import RoveAction

_CLICK_TYPES = {"click": "single", "doubleClick": "double", "tripleClick": "triple", "rightClick": "right"}


def parse_code(code: str | None, description: str | None) -> RoveAction:
    target = {"description": description} if description else None

    if not code or not code.strip():
        return RoveAction(action="unsupported", target=target, raw_code=code, reason="missing code")

    calls: list[tuple[str, dict[str, Any]]] = []
    for line in code.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            calls.append(_parse_call(line))
        except (SyntaxError, ValueError) as exc:
            return RoveAction(action="unsupported", target=target, raw_code=code, reason=f"unparseable code: {exc}")

    if not calls:
        return RoveAction(action="unsupported", target=target, raw_code=code, reason="empty code")

    # A moveTo immediately followed by a dragTo in the same step is one semantic drag.
    if len(calls) == 2 and calls[0][0] == "moveTo" and calls[1][0] == "dragTo":
        (_, move_kwargs), (_, drag_kwargs) = calls
        return RoveAction(
            action="drag", target=target, coordinate={"from": _xy(move_kwargs), "to": _xy(drag_kwargs)}, raw_code=code
        )

    func, kwargs = calls[-1]
    return _to_rove_action(func, kwargs, target, code)


def _parse_call(line: str) -> tuple[str, dict[str, Any]]:
    tree = ast.parse(line, mode="eval")
    if not isinstance(tree.body, ast.Call):
        raise ValueError(f"not a call: {line!r}")
    call = tree.body
    func = call.func
    name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
    if name is None:
        raise ValueError(f"unrecognized function in: {line!r}")

    # literal_eval, never eval/exec — `code` is untrusted text from an external dataset
    kwargs: dict[str, Any] = {f"pos{i}": ast.literal_eval(arg) for i, arg in enumerate(call.args)}
    kwargs.update({kw.arg: ast.literal_eval(kw.value) for kw in call.keywords if kw.arg is not None})
    return name, kwargs


def _xy(kwargs: dict[str, Any]) -> dict[str, Any]:
    return {"x": kwargs.get("x", kwargs.get("pos0")), "y": kwargs.get("y", kwargs.get("pos1"))}


def _as_keys(value: Any) -> list[str]:
    return list(value) if isinstance(value, (list, tuple)) else [value]


def _to_rove_action(func: str, kwargs: dict[str, Any], target: dict[str, Any] | None, code: str) -> RoveAction:
    if func in _CLICK_TYPES:
        return RoveAction(action="click", target=target, click_type=_CLICK_TYPES[func], coordinate=_xy(kwargs), raw_code=code)
    if func == "moveTo":
        return RoveAction(action="move", target=target, coordinate=_xy(kwargs), raw_code=code)
    if func == "dragTo":
        return RoveAction(action="drag", target=target, coordinate={"to": _xy(kwargs)}, raw_code=code)
    if func == "write":
        return RoveAction(action="type", target=target, text=kwargs.get("message", kwargs.get("pos0")), raw_code=code)
    if func == "press":
        return RoveAction(action="keypress", target=target, keys=_as_keys(kwargs.get("pos0")), raw_code=code)
    if func == "hotkey":
        keys = kwargs.get("pos0")
        if isinstance(keys, (list, tuple)):
            all_keys = list(keys)
        else:
            all_keys = [v for k, v in sorted(kwargs.items()) if k.startswith("pos")]
        return RoveAction(action="hotkey", target=target, keys=all_keys, raw_code=code)
    if func == "scroll":
        return RoveAction(action="scroll", target=target, amount=kwargs.get("pos0"), raw_code=code)
    if func == "wait":
        return RoveAction(action="wait", target=target, raw_code=code)
    if func == "terminate":
        return RoveAction(action="finish", target=target, success=kwargs.get("status") == "success", raw_code=code)
    return RoveAction(action="unsupported", target=target, raw_code=code, reason=f"unsupported function: {func}")
