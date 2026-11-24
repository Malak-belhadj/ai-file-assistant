"""Tests for the relational SQLite database (schema.sql + database.py)."""

import json
import sqlite3
from pathlib import Path

import pytest

from fs_assistant.database import ChatDatabase
from tests.fake_ollama import FakeOllama, unused_url
from tests.test_integration import fake_model, run_session

QUERIES_FILE = Path(__file__).resolve().parent.parent / "queries.sql"


@pytest.fixture
def db(tmp_path):
    database = ChatDatabase(tmp_path / "test.db")
    yield database
    database.close()


def fill(db):
    """One user, one chat, one request with its action and the answer."""
    user = db.get_or_create_user("Malak", "terminal")
    chat = db.create_conversation(user)
    msg = db.add_message(chat, "user", "make a folder m on my desktop")
    db.add_action(msg, "create_directory", True, "Directory 'Desktop/m' created successfully.",
                  path="Desktop/m", model_json='{"action": "create_directory", "path": "Desktop/m"}',
                  duration_ms=1500, model="qwen3.5:4b")
    db.add_message(chat, "assistant", "Directory 'Desktop/m' created successfully.")
    return user, chat, msg


# ---- structure: tables, primary keys, foreign keys ---------------------------
def test_four_tables_and_a_view_exist(db):
    names = {r[0] for r in db.connection.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')")}
    assert {"users", "conversations", "messages", "actions", "chat_history"} <= names


@pytest.mark.parametrize("table, pk", [("users", "user_id"), ("conversations", "conversation_id"),
                                       ("messages", "message_id"), ("actions", "action_id")])
def test_every_table_has_a_primary_key(db, table, pk):
    columns = {row[1]: row[5] for row in db.connection.execute(f"PRAGMA table_info({table})")}
    assert columns[pk] == 1


@pytest.mark.parametrize("table, column, parent", [("conversations", "user_id", "users"),
                                                   ("messages", "conversation_id", "conversations"),
                                                   ("actions", "message_id", "messages")])
def test_foreign_keys_link_the_tables(db, table, column, parent):
    fks = {(row[3], row[2]) for row in db.connection.execute(f"PRAGMA foreign_key_list({table})")}
    assert (column, parent) in fks


def test_foreign_key_is_enforced(db):
    """A message cannot point to a chat that does not exist."""
    with pytest.raises(sqlite3.IntegrityError):
        db.add_message(999, "user", "hello")


def test_delete_cascades_to_messages_and_actions(db):
    user, chat, _msg = fill(db)
    assert db.count("messages") == 2 and db.count("actions") == 1
    assert db.delete_conversation(chat, user)
    assert db.count("messages") == 0 and db.count("actions") == 0


def test_check_constraints(db):
    user = db.get_or_create_user("x", "terminal")
    chat = db.create_conversation(user)
    with pytest.raises(sqlite3.IntegrityError):
        db.add_message(chat, "robot", "bad role")
    with pytest.raises(sqlite3.IntegrityError):
        db.connection.execute("INSERT INTO users (display_name, source) VALUES ('y', 'fax')")


# ---- users and chats ------------------------------------------------------------
def test_users_are_created_once(db):
    a = db.get_or_create_user("Terminal user", "terminal")
    b = db.get_or_create_user("Terminal user", "terminal")
    t = db.get_or_create_user("Malak", "telegram", telegram_user_id=12345)
    assert a == b and t != a
    assert db.get_or_create_user("Malak (renamed)", "telegram", telegram_user_id=12345) == t


def test_first_message_becomes_the_chat_title(db):
    user, chat, _ = fill(db)
    assert db.get_conversation(chat).title == "make a folder m on my desktop"
    db.add_message(chat, "user", "second message")
    assert db.get_conversation(chat).title == "make a folder m on my desktop"


def test_list_conversations_newest_first_with_counts(db):
    user = db.get_or_create_user("u", "terminal")
    first = db.create_conversation(user)
    second = db.create_conversation(user)
    db.add_message(second, "user", "hi")
    db.add_message(first, "user", "later message")          # first is now the most recent
    chats = db.list_conversations(user)
    assert [c.conversation_id for c in chats] == [first, second]
    assert chats[0].message_count == 1


def test_users_cannot_open_each_others_chats(db):
    alice = db.get_or_create_user("alice", "terminal")
    bob = db.get_or_create_user("bob", "telegram", telegram_user_id=1)
    chat = db.create_conversation(alice)
    assert db.get_conversation(chat, alice) is not None
    assert db.get_conversation(chat, bob) is None


def test_context_gives_the_model_previous_exchanges(db):
    _user, chat, _ = fill(db)
    context = db.get_context(chat)
    assert context == [
        {"role": "user", "content": "make a folder m on my desktop"},
        {"role": "assistant", "content": '{"action": "create_directory", "path": "Desktop/m"}'},
    ]


def test_context_is_limited_to_recent_turns(db):
    user = db.get_or_create_user("u", "terminal")
    chat = db.create_conversation(user)
    for i in range(10):
        db.add_message(chat, "user", f"request {i}")
    context = db.get_context(chat, max_turns=3)
    assert [m["content"] for m in context] == ["request 7", "request 8", "request 9"]


def test_data_survives_reopening(tmp_path):
    first = ChatDatabase(tmp_path / "keep.db")
    fill(first)
    first.close()
    second = ChatDatabase(tmp_path / "keep.db")
    assert second.count("conversations") == 1 and second.count("messages") == 2
    second.close()


def test_sql_injection_is_stored_as_plain_text(db):
    user = db.get_or_create_user("u", "terminal")
    chat = db.create_conversation(user)
    evil = "x'); DROP TABLE messages; --"
    db.add_message(chat, "user", evil)
    assert db.get_messages(chat)[0].content == evil
    assert db.count("messages") == 1


def test_every_example_query_runs(db):
    fill(db)
    text = QUERIES_FILE.read_text(encoding="utf-8")
    code = "\n".join(line for line in text.splitlines() if not line.strip().startswith("--"))
    statements = [s.strip() for s in code.split(";") if s.strip()]
    assert len(statements) >= 12
    for statement in statements:
        db.connection.execute(statement).fetchall()


# ---- inside the real application ---------------------------------------------------
def open_db(tmp_path):
    return ChatDatabase(tmp_path / "history.db")


def test_app_saves_chat_messages_and_actions(tmp_path):
    with FakeOllama(fake_model) as fake:
        run_session(fake.url, tmp_path / "workspace",
                    ["Create a folder called projects", "delete start.py", "help", "exit"])
    db = open_db(tmp_path)
    assert db.count("conversations") == 1
    messages = db.get_messages(1)
    assert [m.role for m in messages] == ["user", "assistant", "user", "assistant"]   # 'help' not saved
    rows = db.connection.execute("SELECT action_type, success, path, model_json FROM actions ORDER BY action_id").fetchall()
    db.close()
    assert rows[0]["action_type"] == "create_directory" and rows[0]["success"] == 1
    assert json.loads(rows[0]["model_json"]) == {"action": "create_directory", "path": "projects"}
    assert rows[1]["action_type"] == "delete_file" and rows[1]["success"] == 0


def test_errors_are_saved_too(tmp_path):
    run_session(unused_url(), tmp_path / "ws", ["list files", "exit"])
    db = open_db(tmp_path)
    row = db.connection.execute("SELECT action_type, success, result FROM actions").fetchone()
    db.close()
    assert row["action_type"] == "error" and row["success"] == 0
    assert "Cannot connect to Ollama" in row["result"]


def test_continue_an_old_chat_like_chatgpt(tmp_path):
    ws = tmp_path / "workspace"
    with FakeOllama(fake_model) as fake:
        run_session(fake.url, ws, ["Create a folder called projects", "exit"])          # session 1 = chat 1
        out = run_session(fake.url, ws, ["chats", "open 1", "Create a file called main.py",
                                         "history", "exit"])                              # a new session
        last_request = fake.requests[-1]["messages"]
    assert "[1] Create a folder called projects" in out
    assert "Opened chat [1]" in out
    contents = [m["content"] for m in last_request]
    assert "Create a folder called projects" in contents        # the AI saw the old chat
    db = open_db(tmp_path)
    assert db.count("conversations") == 1                       # continued, not a new chat
    assert len(db.get_messages(1)) == 4
    db.close()


def test_new_chat_command(tmp_path):
    with FakeOllama(fake_model) as fake:
        out = run_session(fake.url, tmp_path / "ws", ["Create a folder called projects", "new",
                                                       "Create a file called main.py", "chats", "exit"])
        last_request = fake.requests[-1]["messages"]
    assert "Started a new chat." in out
    assert "[2] Create a file called main.py" in out and "[1] Create a folder called projects" in out
    assert "Create a folder called projects" not in [m["content"] for m in last_request]


def test_open_unknown_chat(tmp_path):
    with FakeOllama(fake_model) as fake:
        out = run_session(fake.url, tmp_path / "ws", ["open 42", "open abc", "exit"])
    assert "There is no chat number 42" in out
    assert "Please give the chat number" in out


def test_charts_and_diagram_commands(tmp_path):
    pytest.importorskip("matplotlib")
    with FakeOllama(fake_model) as fake:
        out = run_session(fake.url, tmp_path / "ws",
                          ["Create a folder called projects", "charts", "diagram", "exit"])
    assert "I drew 5 image(s)" in out and "I drew 1 image(s)" in out
    assert (tmp_path / "charts" / "dashboard.png").is_file()
    assert (tmp_path / "charts" / "database_diagram.png").is_file()
