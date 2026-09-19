from app.memory import MemoryCategory, MemoryService


def test_remember_and_recall_roundtrip(tmp_path) -> None:
    memory = MemoryService(tmp_path / "test.db")

    memory.remember(MemoryCategory.PERSONAL, "likes dark mode")
    memory.remember(MemoryCategory.WORKFLOW, "always saves to Desktop")

    rows = memory.recall()

    assert rows == [("personal", "likes dark mode"), ("workflow", "always saves to Desktop")]


def test_format_context_empty_when_nothing_remembered(tmp_path) -> None:
    memory = MemoryService(tmp_path / "test.db")

    assert memory.format_context() == ""


def test_format_context_lists_oldest_first(tmp_path) -> None:
    memory = MemoryService(tmp_path / "test.db")
    memory.remember(MemoryCategory.EPISODIC, "booked a flight")

    context = memory.format_context()

    assert "What you remember from previous tasks:" in context
    assert "- [episodic] booked a flight" in context
