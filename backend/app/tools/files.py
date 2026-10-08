from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from pydantic import BaseModel, Field

from app.help_request import HelpRequest
from app.tools.base import ASK_FOR_HELP_DESCRIPTION, AskForHelpParams, FinishParams, Tool, ToolError, ToolRegistry, ToolRiskLevel, finish, make_ask_for_help

if TYPE_CHECKING:
    from app.permissions import PermissionGate

MAX_READ_BYTES = 20_000
MAX_WRITE_CHARS = 200_000
MAX_LIST = 200
MAX_SEARCH_RESULTS = 50
MAX_SEARCH_DEPTH = 6


def allowed_roots() -> list[Path]:
    # ROVE_FILE_ROOTS (":"-separated) replaces the defaults; roots are resolved so a symlinked root can't widen scope.
    configured = os.environ.get("ROVE_FILE_ROOTS")
    raw = configured.split(":") if configured else [str(Path.home() / d) for d in ("Desktop", "Documents", "Downloads")]
    return [Path(r).expanduser().resolve() for r in raw if r]


def resolve_path(raw: str) -> Path:
    path = Path(raw).expanduser()
    if not path.is_absolute():
        raise ToolError("use an absolute path (or one starting with ~)")
    # resolve() follows symlinks and ".." so the containment check is on the real location
    real = path.resolve(strict=False)
    for root in allowed_roots():
        if real == root or root in real.parents:
            if any(part.startswith(".") for part in real.relative_to(root).parts):
                raise ToolError("hidden files and folders are off limits")
            return real
    raise ToolError("path is outside the folders Rove may access (Desktop, Documents, Downloads)")


class PathParams(BaseModel):
    path: str


class ReadFileParams(BaseModel):
    path: str


class WriteFileParams(BaseModel):
    path: str
    content: str = Field(max_length=MAX_WRITE_CHARS)
    overwrite: bool = False


class TwoPathParams(BaseModel):
    source: str
    destination: str


class SearchParams(BaseModel):
    root: str
    name_contains: str = Field(min_length=1)


def _list_dir(params: BaseModel) -> dict[str, Any]:
    assert isinstance(params, PathParams)
    directory = resolve_path(params.path)
    if not directory.is_dir():
        raise ToolError("not a directory")
    entries = []
    for child in sorted(directory.iterdir(), key=lambda p: p.name.lower()):
        if child.name.startswith("."):
            continue
        entries.append({"name": child.name, "type": "dir" if child.is_dir() else "file", "size": child.stat().st_size if child.is_file() else None})
        if len(entries) >= MAX_LIST:
            break
    return {"path": str(directory), "entries": entries}


def _read_file(params: BaseModel) -> dict[str, Any]:
    assert isinstance(params, ReadFileParams)
    path = resolve_path(params.path)
    if not path.is_file():
        raise ToolError("not a file")
    data = path.read_bytes()[:MAX_READ_BYTES]
    try:
        return {"content": data.decode("utf-8")}
    except UnicodeDecodeError:
        raise ToolError("not a text file") from None


def _make_write(gate: PermissionGate | None) -> Callable[[BaseModel], dict[str, Any]]:
    def handler(params: BaseModel) -> dict[str, Any]:
        assert isinstance(params, WriteFileParams)
        path = resolve_path(params.path)
        if path.exists():
            if not params.overwrite:
                raise ToolError("file already exists; set overwrite=true to replace it")
            if gate is not None:
                gate.require("write_file", {"path": str(path)}, f"overwrite {path.name}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(params.content, encoding="utf-8")
        return {"written": str(path), "chars": len(params.content)}

    return handler


def _make_dir(params: BaseModel) -> dict[str, Any]:
    assert isinstance(params, PathParams)
    path = resolve_path(params.path)
    path.mkdir(parents=True, exist_ok=True)
    return {"created": str(path)}


def _move(params: BaseModel) -> dict[str, Any]:
    assert isinstance(params, TwoPathParams)
    source, destination = resolve_path(params.source), resolve_path(params.destination)
    if not source.exists():
        raise ToolError("source does not exist")
    if destination.is_dir():
        destination = destination / source.name
    if destination.exists():
        raise ToolError("destination already exists; nothing was overwritten")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(destination))
    return {"moved": str(destination)}


def _copy(params: BaseModel) -> dict[str, Any]:
    assert isinstance(params, TwoPathParams)
    source, destination = resolve_path(params.source), resolve_path(params.destination)
    if not source.exists():
        raise ToolError("source does not exist")
    if destination.is_dir():
        destination = destination / source.name
    if destination.exists():
        raise ToolError("destination already exists; nothing was overwritten")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, destination)
    else:
        shutil.copy2(source, destination)
    return {"copied": str(destination)}


def _make_trash(gate: PermissionGate | None) -> Callable[[BaseModel], dict[str, Any]]:
    def handler(params: BaseModel) -> dict[str, Any]:
        assert isinstance(params, PathParams)
        path = resolve_path(params.path)
        if not path.exists():
            raise ToolError("path does not exist")
        if gate is not None:
            gate.require("trash", {"path": str(path)}, f"move {path.name} to the Trash")
        from Foundation import NSFileManager, NSURL

        ok, _, error = NSFileManager.defaultManager().trashItemAtURL_resultingItemURL_error_(NSURL.fileURLWithPath_(str(path)), None, None)
        if not ok:
            raise ToolError(f"could not move to Trash: {error}")
        return {"trashed": str(path)}

    return handler


def _search(params: BaseModel) -> dict[str, Any]:
    assert isinstance(params, SearchParams)
    root = resolve_path(params.root)
    if not root.is_dir():
        raise ToolError("not a directory")
    needle = params.name_contains.lower()
    matches: list[str] = []
    for current, dirs, files in os.walk(root):
        depth = len(Path(current).relative_to(root).parts)
        dirs[:] = [d for d in dirs if not d.startswith(".")] if depth < MAX_SEARCH_DEPTH else []
        for name in dirs + files:
            if needle in name.lower() and not name.startswith("."):
                matches.append(str(Path(current) / name))
                if len(matches) >= MAX_SEARCH_RESULTS:
                    return {"matches": matches, "truncated": True}
    return {"matches": matches, "truncated": False}


def files_registry(help_request: HelpRequest, gate: PermissionGate | None = None) -> ToolRegistry:
    registry = ToolRegistry()
    for tool in (
        Tool("list_directory", "List the files and folders in a directory (Desktop, Documents, Downloads only).", PathParams, ToolRiskLevel.LOW, _list_dir),
        Tool("read_file", "Read a text file (first 20,000 bytes).", ReadFileParams, ToolRiskLevel.LOW, _read_file),
        Tool("search_files", "Find files/folders whose name contains some text, under a root folder.", SearchParams, ToolRiskLevel.LOW, _search),
        Tool("make_directory", "Create a folder (and parents).", PathParams, ToolRiskLevel.LOW, _make_dir),
        Tool("write_file", "Write a text file. Replacing an existing file needs overwrite=true and the user's approval.", WriteFileParams, ToolRiskLevel.LOW, _make_write(gate)),
        Tool("move_file", "Move or rename a file/folder. Never overwrites.", TwoPathParams, ToolRiskLevel.LOW, _move),
        Tool("copy_file", "Copy a file/folder. Never overwrites.", TwoPathParams, ToolRiskLevel.LOW, _copy),
        Tool("trash_file", "Move a file/folder to the Trash. Needs the user's approval.", PathParams, ToolRiskLevel.LOW, _make_trash(gate)),
        Tool("ask_for_help", ASK_FOR_HELP_DESCRIPTION, AskForHelpParams, ToolRiskLevel.LOW, make_ask_for_help(help_request)),
        Tool("finish", "Report the subtask as complete with a result.", FinishParams, ToolRiskLevel.LOW, finish),
    ):
        registry.register(tool)
    return registry
