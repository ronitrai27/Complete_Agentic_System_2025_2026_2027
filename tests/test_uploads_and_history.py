import sqlite3

from src.tools import conversation_store
from src.utils import uploads


def test_store_upload_sanitizes_and_deduplicates(tmp_path, monkeypatch):
    monkeypatch.setattr(uploads, "UPLOAD_ROOT", tmp_path)
    payload = b"safe text content"

    first = uploads.store_upload("../../unsafe name.txt", payload, "conversation/1")
    second = uploads.store_upload("../../unsafe name.txt", payload, "conversation/1")

    assert first.safe_name == "unsafe_name.txt"
    assert first.document_id == second.document_id
    assert first.created is True
    assert second.created is False
    assert first.path.startswith(str(tmp_path))


def test_rejects_spoofed_pdf():
    try:
        uploads.validate_upload("report.pdf", b"this is not a pdf")
    except ValueError as exc:
        assert "valid PDF" in str(exc)
    else:
        raise AssertionError("Spoofed PDF should be rejected")


def test_conversation_turns_are_idempotent_and_ordered(tmp_path, monkeypatch):
    db_path = tmp_path / "conversations.db"
    monkeypatch.setattr(conversation_store, "DB_DIR", str(tmp_path))
    monkeypatch.setattr(conversation_store, "DB_PATH", str(db_path))
    conversation_store.init_db()

    conversation_store.record_conversation_turn(
        "conv-1", "turn-1", "Hello", "Hi there", "direct"
    )
    conversation_store.record_conversation_turn(
        "conv-1", "turn-1", "Hello", "Hi there", "direct"
    )
    conversation_store.record_conversation_turn(
        "conv-1", "turn-2", "What did I say?", "You said hello.", "direct"
    )

    history = conversation_store.get_recent_conversation_history("conv-1")
    assert history == [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there"},
        {"role": "user", "content": "What did I say?"},
        {"role": "assistant", "content": "You said hello."},
    ]

    with sqlite3.connect(db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 4
