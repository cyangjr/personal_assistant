from pathlib import Path

from assistant.auth import is_allowed
from assistant.llm import GroqAssistant
from assistant.memory import MemoryStore


def test_allowlist():
    assert is_allowed(1, [1, 2])
    assert not is_allowed(3, [1, 2])


def test_memory_roundtrip(tmp_path: Path):
    store = MemoryStore(tmp_path / "test.db")
    store.add_message(42, "user", "hello")
    store.add_message(42, "model", "hi there")
    store.set_profile_note(42, "cards", "Chase Sapphire Preferred")

    history = store.get_recent_messages(42, 10)
    assert history == [
        {"role": "user", "content": "hello"},
        {"role": "model", "content": "hi there"},
    ]
    assert store.get_profile_notes(42)["cards"] == "Chase Sapphire Preferred"

    store.clear_messages(42)
    assert store.get_recent_messages(42, 10) == []
    assert store.delete_profile_note(42, "cards")
    assert store.get_profile_notes(42) == {}


def test_should_use_search():
    assistant = GroqAssistant(
        groq_api_key="unused",
        tavily_api_key="unused",
        model="llama-3.3-70b-versatile",
    )
    assert assistant.should_use_search("What are my Costco Executive benefits?")
    assert assistant.should_use_search("Does Chase Sapphire have travel credit?")
    assert not assistant.should_use_search("What's a good pasta recipe?")
