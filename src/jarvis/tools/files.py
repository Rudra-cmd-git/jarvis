"""File and folder tools.

Read operations are low risk. Every mutation requires confirmation, and deletes
go to the Recycle Bin rather than being permanent. All paths are checked
against the user's allowed folders.
"""
from __future__ import annotations

import ctypes
import fnmatch
import os
import shutil
from datetime import datetime
from ctypes import wintypes
from pathlib import Path

from jarvis.ai.prompts import wrap_untrusted
from jarvis.core.errors import ToolError
from jarvis.core.util import format_bytes, truncate
from jarvis.security.permissions import Risk
from jarvis.tools.context import ToolContext
from jarvis.tools.registry import ToolSpec

TEXT_EXTENSIONS = {
    ".txt", ".md", ".markdown", ".rst", ".log", ".csv", ".tsv", ".json", ".jsonl",
    ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".xml", ".html", ".htm",
    ".py", ".pyw", ".js", ".ts", ".tsx", ".jsx", ".java", ".c", ".h", ".cpp", ".hpp",
    ".cs", ".go", ".rs", ".rb", ".php", ".sh", ".ps1", ".bat", ".cmd", ".sql",
    ".css", ".scss", ".vue", ".kt", ".swift", ".r", ".m", ".lua", ".pl", ".env",
}
_SKIP_DIRS = {
    "node_modules", ".git", ".svn", "__pycache__", "windows", "program files",
    "program files (x86)", "programdata", "$recycle.bin", "system volume information",
    "appdata", ".cache", ".gradle", ".m2", "venv", ".venv", "site-packages",
}
_MAX_READ_BYTES = 2 * 1024 * 1024
_MAX_SEARCH_BYTES = 400 * 1024

_CATEGORY_MAP = {
    "Documents": {".pdf", ".doc", ".docx", ".txt", ".md", ".rtf", ".odt", ".xls", ".xlsx", ".ppt", ".pptx", ".csv"},
    "Images": {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg", ".ico", ".tiff"},
    "Video": {".mp4", ".mkv", ".mov", ".avi", ".wmv", ".webm", ".flv"},
    "Audio": {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma"},
    "Archives": {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz"},
    "Code": {".py", ".js", ".ts", ".java", ".c", ".cpp", ".cs", ".go", ".rs", ".rb", ".php", ".html", ".css", ".json"},
    "Executables": {".exe", ".msi", ".bat", ".cmd", ".ps1", ".sh", ".dll"},
}


class _ShellFileOpW(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("wFunc", wintypes.UINT),
        ("pFrom", wintypes.LPCWSTR),
        ("pTo", wintypes.LPCWSTR),
        ("fFlags", wintypes.UINT),
        ("fAnyOperationsAborted", wintypes.BOOL),
        ("hNameMappings", ctypes.c_void_p),
        ("lpszProgressTitle", wintypes.LPCWSTR),
    ]


# --------------------------------------------------------------------- helpers
def _require(ctx: ToolContext, path: str) -> Path:
    resolved = Path(path).expanduser()
    if not resolved.is_absolute():
        resolved = (Path.home() / resolved).resolve()
    return ctx.policy.require_path(resolved)


def _is_text(path: Path) -> bool:
    return path.suffix.lower() in TEXT_EXTENSIONS


def _walk(root: Path, max_depth: int = 6):
    root = Path(root)
    if not root.exists() or not root.is_dir():
        return
    base_depth = len(root.parts)
    for current, dirs, files in os.walk(root):
        depth = len(Path(current).parts) - base_depth
        if depth >= max_depth:
            dirs[:] = []
        dirs[:] = [d for d in dirs if d.lower() not in _SKIP_DIRS and not d.startswith(".")]
        yield Path(current), files


def _entry(path: Path) -> dict:
    stat = path.stat()
    return {
        "path": str(path),
        "name": path.name,
        "size": stat.st_size,
        "size_human": format_bytes(stat.st_size),
        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
    }


def _recycle(path: Path) -> None:
    if ctypes.windll is None:  # pragma: no cover
        raise ToolError("Recycle Bin deletion requires Windows")
    operation = _ShellFileOpW()
    operation.wFunc = 0x0003  # FO_DELETE
    operation.pFrom = str(path) + "\0\0"
    operation.fFlags = 0x0040 | 0x0010 | 0x0004 | 0x0400  # ALLOWUNDO | NO CONFIRM | SILENT | NO ERROR UI
    result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(operation))
    if result != 0:
        raise ToolError(f"Windows could not move '{path.name}' to the Recycle Bin (code {result}).")


def _unique_destination(destination: Path) -> Path:
    if not destination.exists():
        return destination
    stem, suffix = destination.stem, destination.suffix
    counter = 1
    while True:
        candidate = destination.with_name(f"{stem} ({counter}){suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


# ----------------------------------------------------------------------- tools
def _list_directory(ctx: ToolContext, path: str, limit: int = 200) -> dict:
    target = _require(ctx, path)
    if not target.exists():
        raise ToolError(f"Folder does not exist: {target}")
    if not target.is_dir():
        raise ToolError(f"Not a folder: {target}")
    entries = []
    for child in sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name.lower())):
        if len(entries) >= max(1, limit):
            break
        try:
            if child.is_dir():
                entries.append({"path": str(child), "name": child.name, "type": "folder"})
            else:
                data = _entry(child)
                data["type"] = "file"
                entries.append(data)
        except OSError:
            continue
    return {"path": str(target), "entries": entries, "count": len(entries)}


def _search_files(
    ctx: ToolContext,
    query: str,
    root: str | None = None,
    limit: int = 40,
    max_depth: int = 6,
) -> dict:
    if not query or not query.strip():
        raise ToolError("Provide a filename or pattern to search for.")
    roots = [Path(root)] if root else [Path(p) for p in ctx.config.allowed_roots]
    pattern = query.strip().lower()
    has_wildcard = any(ch in pattern for ch in "*?[")
    results: list[dict] = []
    for base in roots:
        allowed = _require(ctx, str(base))
        for _current, files in _walk(allowed, max(1, max_depth)):
            for file_name in files:
                if (fnmatch.fnmatch(file_name.lower(), pattern) if has_wildcard else pattern in file_name.lower()):
                    path = _current / file_name
                    try:
                        results.append(_entry(path))
                    except OSError:
                        continue
                    if len(results) >= max(1, limit):
                        return {
                            "query": query,
                            "count": len(results),
                            "results": results,
                            "truncated": True,
                        }
    return {"query": query, "count": len(results), "results": results, "truncated": False}


def _find_duplicates(ctx: ToolContext, root: str | None = None, limit: int = 100) -> dict:
    base = _require(ctx, root) if root else None
    roots = [base] if base else [Path(p) for p in ctx.config.allowed_roots]
    names: dict[str, list[str]] = {}
    for allowed_root in roots:
        for _current, files in _walk(allowed_root):
            for file_name in files:
                key = file_name.lower()
                names.setdefault(key, []).append(str(_current / file_name))
    duplicates = {name: paths for name, paths in names.items() if len(paths) > 1}
    items = [
        {"name": name, "count": len(paths), "paths": paths}
        for name, paths in sorted(duplicates.items(), key=lambda kv: -len(kv[1]))
    ][: max(1, limit)]
    return {"scanned": len(names), "duplicate_groups": len(duplicates), "groups": items}


def _read_text_file(ctx: ToolContext, path: str, max_chars: int = 20000) -> str:
    target = _require(ctx, path)
    if not target.exists() or not target.is_file():
        raise ToolError(f"File does not exist: {target}")
    if target.stat().st_size > _MAX_READ_BYTES:
        raise ToolError(
            f"File is larger than {format_bytes(_MAX_READ_BYTES)}. Split it or ask for a specific section."
        )
    try:
        raw = target.read_bytes()
    except OSError as exc:
        raise ToolError(f"Could not read file: {exc}") from exc
    text = raw.decode("utf-8-sig", errors="replace")
    if target.suffix.lower() not in TEXT_EXTENSIONS:
        text = "[Binary or unsupported file type; showing a best-effort decode]\n" + text
    return wrap_untrusted(f"file {target}", truncate(text, max(50, min(max_chars, 60000))))


def _get_file_info(ctx: ToolContext, path: str) -> dict:
    target = _require(ctx, path)
    if not target.exists():
        raise ToolError(f"Path does not exist: {target}")
    if target.is_dir():
        files = sum(1 for p in target.rglob("*") if p.is_file())
        return {"path": str(target), "type": "folder", "files": files}
    data = _entry(target)
    data["type"] = "file"
    data["extension"] = target.suffix.lower()
    return data


def _create_file(ctx: ToolContext, path: str, content: str = "", overwrite: bool = False) -> str:
    target = _require(ctx, path)
    if target.exists() and not overwrite:
        raise ToolError(f"'{target}' already exists. Pass overwrite=true to replace it.")
    if target.exists() and target.is_dir():
        raise ToolError(f"'{target}' is a folder, not a file.")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"Created file {target} ({len(content)} characters)."


def _append_to_file(ctx: ToolContext, path: str, content: str) -> str:
    target = _require(ctx, path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(content)
    return f"Appended {len(content)} characters to {target}."


def _create_folder(ctx: ToolContext, path: str) -> str:
    target = _require(ctx, path)
    target.mkdir(parents=True, exist_ok=True)
    return f"Folder ready: {target}"


def _rename_path(ctx: ToolContext, source: str, destination: str) -> str:
    src = _require(ctx, source)
    dst = _require(ctx, destination)
    if not src.exists():
        raise ToolError(f"Source does not exist: {src}")
    if dst.exists():
        raise ToolError(f"Destination already exists: {dst}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    src.rename(dst)
    return f"Renamed '{src.name}' to '{dst}'."


def _move_path(ctx: ToolContext, source: str, destination: str) -> str:
    src = _require(ctx, source)
    dst = _require(ctx, destination)
    if not src.exists():
        raise ToolError(f"Source does not exist: {src}")
    if dst.exists():
        raise ToolError(f"Destination already exists: {dst}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    if src.exists():
        raise ToolError(f"Move reported success but '{src}' still exists.")
    return f"Moved '{src.name}' to '{dst}'."


def _copy_path(ctx: ToolContext, source: str, destination: str) -> str:
    src = _require(ctx, source)
    dst = _require(ctx, destination)
    if not src.exists():
        raise ToolError(f"Source does not exist: {src}")
    if dst.exists():
        raise ToolError(f"Destination already exists: {dst}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        shutil.copytree(src, dst)
    else:
        shutil.copy2(src, dst)
    return f"Copied '{src.name}' to '{dst}'."


def _delete_path(ctx: ToolContext, path: str) -> str:
    target = _require(ctx, path)
    if not target.exists():
        raise ToolError(f"Path does not exist: {target}")
    if target == Path.home():
        raise ToolError("Refusing to delete the user's home folder.")
    _recycle(target)
    if target.exists():
        raise ToolError("Deletion was not confirmed by the shell.")
    return f"Moved '{target.name}' to the Recycle Bin (recoverable)."


def _organize_folder(ctx: ToolContext, path: str, by: str = "type") -> str:
    target = _require(ctx, path)
    if not target.is_dir():
        raise ToolError(f"Not a folder: {target}")
    if by != "type":
        raise ToolError("Only 'type' organization is supported right now.")
    moved = 0
    for child in list(target.iterdir()):
        if not child.is_file():
            continue
        category = next(
            (name for name, extensions in _CATEGORY_MAP.items() if child.suffix.lower() in extensions),
            "Other",
        )
        bucket = target / category
        bucket.mkdir(exist_ok=True)
        destination = _unique_destination(bucket / child.name)
        child.rename(destination)
        moved += 1
    return f"Organized {moved} files into typed subfolders inside {target}."


def _search_in_documents(
    ctx: ToolContext, query: str, root: str | None = None, limit: int = 30
) -> dict:
    if not query or not query.strip():
        raise ToolError("Provide a search term.")
    needle = query.strip().lower()
    base = _require(ctx, root) if root else None
    roots = [base] if base else [Path(p) for p in ctx.config.allowed_roots]
    matches: list[dict] = []
    for allowed_root in roots:
        for current, files in _walk(allowed_root):
            for file_name in files:
                path = current / file_name
                if not _is_text(path):
                    continue
                try:
                    if path.stat().st_size > _MAX_SEARCH_BYTES:
                        continue
                    content = path.read_text(encoding="utf-8-sig", errors="replace")
                except OSError:
                    continue
                for number, line in enumerate(content.splitlines(), start=1):
                    if needle in line.lower():
                        matches.append(
                            {"path": str(path), "line": number, "text": truncate(line.strip(), 240)}
                        )
                        if len(matches) >= max(1, limit):
                            return {"query": query, "count": len(matches), "matches": matches}
    return {"query": query, "count": len(matches), "matches": matches}


def build_specs() -> list[ToolSpec]:
    return [
        ToolSpec(
            name="list_directory",
            description="List the files and folders inside an allowed directory.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute folder path"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 1000},
                },
                "required": ["path"],
                "additionalProperties": False,
            },
            handler=_list_directory,
            risk=Risk.LOW,
            category="files",
        ),
        ToolSpec(
            name="search_files",
            description="Search allowed folders for a filename or wildcard pattern such as '*.pdf'.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "root": {"type": "string", "description": "Optional folder to search in"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 200},
                    "max_depth": {"type": "integer", "minimum": 1, "maximum": 12},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
            handler=_search_files,
            risk=Risk.LOW,
            category="files",
        ),
        ToolSpec(
            name="find_duplicate_filenames",
            description="Find files that share the same filename across allowed folders.",
            parameters={
                "type": "object",
                "properties": {
                    "root": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 300},
                },
                "additionalProperties": False,
            },
            handler=_find_duplicates,
            risk=Risk.LOW,
            category="files",
        ),
        ToolSpec(
            name="read_text_file",
            description="Read a text/code document so it can be summarized or explained.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "max_chars": {"type": "integer", "minimum": 50, "maximum": 60000},
                },
                "required": ["path"],
                "additionalProperties": False,
            },
            handler=_read_text_file,
            risk=Risk.LOW,
            category="files",
        ),
        ToolSpec(
            name="get_file_info",
            description="Show path, size, modified time and type for a file or folder.",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
                "additionalProperties": False,
            },
            handler=_get_file_info,
            risk=Risk.LOW,
            category="files",
        ),
        ToolSpec(
            name="create_file",
            description="Create a new text file with content. Requires confirmation.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                    "overwrite": {"type": "boolean"},
                },
                "required": ["path"],
                "additionalProperties": False,
            },
            handler=_create_file,
            risk=Risk.MEDIUM,
            category="files",
        ),
        ToolSpec(
            name="append_to_file",
            description="Append text to an existing file. Requires confirmation.",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                "required": ["path", "content"],
                "additionalProperties": False,
            },
            handler=_append_to_file,
            risk=Risk.MEDIUM,
            category="files",
        ),
        ToolSpec(
            name="create_folder",
            description="Create a folder (including parents). Requires confirmation.",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
                "additionalProperties": False,
            },
            handler=_create_folder,
            risk=Risk.MEDIUM,
            category="files",
        ),
        ToolSpec(
            name="rename_path",
            description="Rename a file or folder. Requires confirmation.",
            parameters={
                "type": "object",
                "properties": {"source": {"type": "string"}, "destination": {"type": "string"}},
                "required": ["source", "destination"],
                "additionalProperties": False,
            },
            handler=_rename_path,
            risk=Risk.MEDIUM,
            category="files",
        ),
        ToolSpec(
            name="move_path",
            description="Move a file or folder. Requires confirmation.",
            parameters={
                "type": "object",
                "properties": {"source": {"type": "string"}, "destination": {"type": "string"}},
                "required": ["source", "destination"],
                "additionalProperties": False,
            },
            handler=_move_path,
            risk=Risk.MEDIUM,
            category="files",
        ),
        ToolSpec(
            name="copy_path",
            description="Copy a file or folder. Requires confirmation.",
            parameters={
                "type": "object",
                "properties": {"source": {"type": "string"}, "destination": {"type": "string"}},
                "required": ["source", "destination"],
                "additionalProperties": False,
            },
            handler=_copy_path,
            risk=Risk.MEDIUM,
            category="files",
        ),
        ToolSpec(
            name="delete_path",
            description="Move a file or folder to the Recycle Bin. Recoverable, but requires confirmation.",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
                "additionalProperties": False,
            },
            handler=_delete_path,
            risk=Risk.HIGH,
            category="files",
        ),
        ToolSpec(
            name="organize_folder",
            description="Sort the files in an allowed folder into typed subfolders. Requires confirmation.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "by": {"type": "string", "enum": ["type"]},
                },
                "required": ["path"],
                "additionalProperties": False,
            },
            handler=_organize_folder,
            risk=Risk.MEDIUM,
            category="files",
        ),
        ToolSpec(
            name="search_in_documents",
            description="Search inside text documents under allowed folders and return matching lines.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "root": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
            handler=_search_in_documents,
            risk=Risk.LOW,
            category="files",
        ),
    ]