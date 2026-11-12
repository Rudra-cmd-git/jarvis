import asyncio
from pathlib import Path

from jarvis.tools.builtin import build_registry
from jarvis.security.permissions import PermissionPolicy


def _reg():
    return build_registry()


def _run(coro):
    return asyncio.run(coro)


def test_create_read_and_list(ctx) -> None:
    reg = _reg()
    target = Path(ctx.config.allowed_roots[0]) / "note.txt"
    created = _run(reg.execute("create_file", {"path": str(target), "content": "hello jarvis"}, ctx))
    assert created.ok, created.error
    assert target.exists()

    read = _run(reg.execute("read_text_file", {"path": str(target)}, ctx))
    assert read.ok
    assert "hello jarvis" in read.output
    assert "UNTRUSTED" in read.output

    listing = _run(reg.execute("list_directory", {"path": ctx.config.allowed_roots[0]}, ctx))
    assert listing.ok
    assert any(item["name"] == "note.txt" for item in listing.output["entries"])


def test_search_files_and_duplicates(ctx) -> None:
    reg = _reg()
    root = Path(ctx.config.allowed_roots[0])
    (root / "a.txt").write_text("a", encoding="utf-8")
    (root / "sub").mkdir()
    (root / "sub" / "a.txt").write_text("b", encoding="utf-8")
    (root / "sub" / "b.md").write_text("c", encoding="utf-8")

    found = _run(reg.execute("search_files", {"query": "*.txt"}, ctx))
    assert found.ok
    assert found.output["count"] >= 2

    duplicates = _run(reg.execute("find_duplicate_filenames", {"root": str(root)}, ctx))
    assert duplicates.ok
    assert duplicates.output["duplicate_groups"] == 1


def test_move_rename_copy(ctx) -> None:
    reg = _reg()
    root = Path(ctx.config.allowed_roots[0])
    source = root / "source.txt"
    source.write_text("data", encoding="utf-8")

    renamed = _run(reg.execute("rename_path", {"source": str(source), "destination": str(root / "renamed.txt")}, ctx))
    assert renamed.ok and (root / "renamed.txt").exists()

    copied = _run(reg.execute("copy_path", {"source": str(root / "renamed.txt"), "destination": str(root / "copy.txt")}, ctx))
    assert copied.ok and (root / "copy.txt").exists()

    moved = _run(reg.execute("move_path", {"source": str(root / "copy.txt"), "destination": str(root / "nested" / "moved.txt")}, ctx))
    assert moved.ok and (root / "nested" / "moved.txt").exists()


def test_delete_uses_recycle_bin(ctx) -> None:
    ctx.config.allow_high_risk = True
    reg = _reg()
    target = Path(ctx.config.allowed_roots[0]) / "trash.txt"
    target.write_text("delete me", encoding="utf-8")
    result = _run(reg.execute("delete_path", {"path": str(target)}, ctx))
    assert result.ok, result.error
    assert not target.exists()


def test_organize_folder(ctx) -> None:
    reg = _reg()
    root = Path(ctx.config.allowed_roots[0]) / "messy"
    root.mkdir()
    (root / "a.txt").write_text("1", encoding="utf-8")
    (root / "b.png").write_bytes(b"\x89PNG")
    result = _run(reg.execute("organize_folder", {"path": str(root)}, ctx))
    assert result.ok, result.error
    assert (root / "Documents" / "a.txt").exists()
    assert (root / "Images" / "b.png").exists()


def test_search_inside_documents(ctx) -> None:
    reg = _reg()
    root = Path(ctx.config.allowed_roots[0])
    (root / "doc.txt").write_text("the secret project plan\nsecond line", encoding="utf-8")
    result = _run(reg.execute("search_in_documents", {"query": "project"}, ctx))
    assert result.ok
    assert result.output["count"] == 1


def test_path_outside_allowed_roots_is_blocked(ctx) -> None:
    reg = _reg()
    result = _run(reg.execute("list_directory", {"path": "C:\\Windows"}, ctx))
    assert result.ok is False
    assert "outside" in result.error.lower() or "allowed" in result.error.lower()


def test_file_info(ctx) -> None:
    reg = _reg()
    target = Path(ctx.config.allowed_roots[0]) / "info.txt"
    target.write_text("abc", encoding="utf-8")
    result = _run(reg.execute("get_file_info", {"path": str(target)}, ctx))
    assert result.ok
    assert result.output["type"] == "file"
    assert result.output["size"] == 3