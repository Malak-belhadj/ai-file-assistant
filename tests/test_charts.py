"""Tests for drawing the database queries as charts."""

import pytest

from fs_assistant.charts import QUERIES, ChartError, run_queries
from fs_assistant.database import ChatDatabase

matplotlib = pytest.importorskip("matplotlib")   # skipped if matplotlib is not installed

from fs_assistant.charts import draw_all  # noqa: E402


@pytest.fixture
def filled_db(tmp_path):
    path = tmp_path / "history.db"
    db = ChatDatabase(path)
    user = db.get_or_create_user("u", "terminal")
    chat = db.create_conversation(user)
    for text, action, ok, ms in [("make folder m", "create_directory", True, 2500),
                                 ("make file a", "create_file", True, 1800),
                                 ("delete a", "delete_file", False, 900),
                                 ("list files", "error", False, None)]:
        msg = db.add_message(chat, "user", text)
        db.add_action(msg, action, ok, "result", duration_ms=ms)
    db.close()
    return path


def test_queries_return_expected_numbers(filled_db):
    results = run_queries(filled_db)
    assert dict(results["actions"]) == {"create_directory": 1, "create_file": 1, "delete_file": 1, "error": 1}
    assert results["success"] == [(2, 2)]
    assert len(results["speed"]) == 3            # 'error' has no timing
    assert results["per_chat"] == [(1, "make folder m", 4)]          # JOIN conversations-messages


def test_draw_all_creates_png_images(filled_db, tmp_path):
    files = draw_all(filled_db, tmp_path / "charts")
    names = sorted(p.name for p in files)
    assert names == ["1_requests_per_action.png", "2_success_rate.png", "3_response_time.png",
                     "4_messages_per_chat.png", "dashboard.png"]
    for path in files:
        assert path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"     # real PNG files


def test_missing_database_gives_friendly_error(tmp_path):
    with pytest.raises(ChartError, match="No database found"):
        run_queries(tmp_path / "nothing.db")


def test_empty_history_gives_friendly_error(tmp_path):
    ChatDatabase(tmp_path / "empty.db").close()
    with pytest.raises(ChartError, match="history is empty"):
        run_queries(tmp_path / "empty.db")


def test_chart_queries_are_in_queries_sql():
    from pathlib import Path
    text = (Path(__file__).resolve().parent.parent / "queries.sql").read_text(encoding="utf-8")
    normalized = " ".join(text.split())
    for sql in QUERIES.values():
        if "duration_ms IS NOT NULL" in sql:     # the speed chart filters rows without timing
            continue
        assert " ".join(sql.split()).rstrip(";") in normalized


def test_erd_reads_keys_and_draws(tmp_path, filled_db):
    from fs_assistant.erd import draw_erd, read_schema
    tables = {t.name: t for t in read_schema(filled_db)}
    assert set(tables) == {"users", "conversations", "messages", "actions"}
    fk = {c.name: c.fk for c in tables["messages"].columns if c.fk}
    assert fk == {"conversation_id": ("conversations", "conversation_id")}
    assert [c.name for c in tables["users"].columns if c.is_pk] == ["user_id"]
    out = draw_erd(filled_db, tmp_path / "erd.png")
    assert out.read_bytes()[:4] == b"\x89PNG"


def test_erd_works_without_a_database_file(tmp_path):
    from fs_assistant.erd import draw_erd
    out = draw_erd(tmp_path / "missing.db", tmp_path / "erd.png")
    assert out.is_file()
    assert not (tmp_path / "missing.db").exists()
