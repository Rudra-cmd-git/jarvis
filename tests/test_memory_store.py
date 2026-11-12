import asyncio

import pytest

from jarvis.memory.store import Store


def test_conversation_and_messages(store: Store) -> None:
    cid = store.create_conversation("First")
    store.add_message(cid, "user", "hello")
    store.add_message(cid, "assistant", "hi")
    messages = store.list_messages(cid)
    assert [m["content"] for m in messages] == ["hello", "hi"]
    assert "hello" in store.search_messages("hello")[0]["content"]
    store.delete_conversation(cid)
    assert store.get_conversation(cid) is None


def test_memory_rejects_secrets(store: Store) -> None:
    store.add_memory("prefers dark mode", kind="preference")
    assert len(store.list_memories()) == 1
    with pytest.raises(ValueError):
        store.add_memory("api key: sk-ABCDEFGHIJKLMNOP1234")
    with pytest.raises(ValueError):
        store.add_memory("password = hunter2")


def test_memory_edit_delete_clear(store: Store) -> None:
    entry = store.add_memory("uses VS Code")
    store.update_memory(entry["id"], "uses Neovim")
    assert store.list_memories()[0]["content"] == "uses Neovim"
    store.delete_memory(entry["id"])
    assert store.list_memories() == []
    store.add_memory("one")
    store.add_memory("two")
    store.clear_memories()
    assert store.list_memories() == []


def test_todos_and_reminders(store: Store) -> None:
    todo = store.add_todo("Write tests")
    assert len(store.list_todos()) == 1
    store.complete_todo(todo["id"])
    assert store.list_todos()[0]["done"] == 1
    reminder = store.add_reminder("Stretch", "2099-01-01T09:00:00")
    assert store.list_reminders()[0]["text"] == "Stretch"
    store.complete_reminder(reminder["id"])
    assert store.list_reminders() == []


def test_notes_and_actions(store: Store) -> None:
    note = store.add_note("Idea", "Build a robot")
    assert store.search_notes("robot")[0]["id"] == note["id"]
    store.update_note(note["id"], "Idea 2", "Better robot")
    assert store.get_note(note["id"])["title"] == "Idea 2"
    store.delete_note(note["id"])
    store.log_action("open_app", "low", True, "opened notepad")
    actions = store.recent_actions()
    assert actions[0]["tool"] == "open_app"


def test_workflows_and_timers(store: Store) -> None:
    saved = store.save_workflow("Study", "focus", [{"tool": "start_timer", "args": {"minutes": 25}}])
    assert saved["name"] == "Study"
    assert store.get_workflow("Study")["steps"][0]["tool"] == "start_timer"
    timer = store.start_timer("Focus", 60)
    assert store.active_timer()["id"] == timer["id"]
    store.complete_timer(timer["id"])
    assert store.active_timer() is None