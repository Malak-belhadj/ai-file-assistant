"""Telegram bot tests: fake phone messages -> real bot code -> real files.

Uses a fake Telegram server and a fake Ollama server, so no internet,
no bot token and no AI model are needed.
"""

import json
from pathlib import Path

import pytest

from fs_assistant.config import Settings, load_env_file, parse_user_ids
from fs_assistant.telegram_bot import TelegramAPI, TelegramBot, TelegramError
from main import build_components
from tests.fake_ollama import FakeOllama
from tests.fake_telegram import TOKEN, FakeTelegram

OWNER = 111          # the allowed Telegram user
STRANGER = 999

ANSWERS = {
    "create test on desktop": {"action": "create_directory", "path": "Desktop/test"},
    "make a folder m on my desktop with files a and b":
        {"action": "create_directory", "path": "Desktop/m", "files": ["a", "b"]},
    "delete notes.txt": {"action": "delete_file", "path": "notes.txt"},
    "what's on my desktop": {"action": "list_directory", "path": "Desktop"},
}


def model(text):
    return json.dumps(ANSWERS.get(text, {"action": "unsupported", "message": "No."}))


@pytest.fixture
def setup(tmp_path):
    home = tmp_path / "home"
    (home / "Desktop").mkdir(parents=True)
    with FakeOllama(model) as ollama, FakeTelegram() as telegram:
        settings = Settings(ollama_url=ollama.url, workspace=home, timeout_seconds=5,
                            db_path=tmp_path / "bot.db")
        parts = build_components(settings)
        # Make "Desktop" point at the fake home's Desktop for this test.
        parts.service.executor.file_ops.workspace.aliases = {"desktop": (home / "Desktop").resolve()}
        api = TelegramAPI(TOKEN, base_url=telegram.url, timeout=0)
        logs = []
        bot = TelegramBot(api, parts.service, parts.database, {OWNER}, log=logs.append)
        bot.confirm_timeout = 1
        yield bot, telegram, home, parts.database, logs, ollama
        parts.database.close()


def test_phone_message_creates_folder_on_desktop(setup):
    bot, telegram, home, *_ = setup
    telegram.send_from_phone("create test on desktop", OWNER)
    assert bot.poll_once() == 1
    assert (home / "Desktop" / "test").is_dir()
    assert telegram.texts()[-1] == "Directory 'Desktop/test' created successfully."


def test_folder_with_files_from_phone(setup):
    bot, telegram, home, *_ = setup
    telegram.send_from_phone("make a folder m on my desktop with files a and b", OWNER)
    bot.poll_once()
    assert sorted(p.name for p in (home / "Desktop" / "m").iterdir()) == ["a", "b"]
    assert "Folder 'Desktop/m' is ready with 2 new file(s)." in telegram.texts()[-1]


def test_stranger_is_refused_and_nothing_happens(setup):
    bot, telegram, home, db, logs, ollama = setup
    telegram.send_from_phone("create test on desktop", STRANGER, first_name="Hacker")
    bot.poll_once()
    assert not (home / "Desktop" / "test").exists()
    assert "not allowed" in telegram.texts()[-1] and str(STRANGER) in telegram.texts()[-1]
    assert any(str(STRANGER) in line for line in logs)
    assert ollama.requests == []                  # the AI was never even asked


def test_delete_asks_for_confirmation_yes(setup):
    bot, telegram, home, *_ = setup
    (home / "notes.txt").write_text("x")
    telegram.send_from_phone("delete notes.txt", OWNER)
    telegram.send_from_phone("yes", OWNER)
    bot.poll_once()
    assert not (home / "notes.txt").exists()
    texts = telegram.texts()
    assert "Reply yes or no." in texts[0]
    assert texts[-1] == "File 'notes.txt' deleted successfully."


def test_delete_answer_no_keeps_the_file(setup):
    bot, telegram, home, *_ = setup
    (home / "notes.txt").write_text("x")
    telegram.send_from_phone("delete notes.txt", OWNER)
    telegram.send_from_phone("no", OWNER)
    bot.poll_once()
    assert (home / "notes.txt").exists()
    assert "Cancelled" in telegram.texts()[-1]


def test_no_answer_cancels_after_timeout(setup):
    bot, telegram, home, *_ = setup
    (home / "notes.txt").write_text("x")
    telegram.send_from_phone("delete notes.txt", OWNER)
    bot.poll_once()
    assert (home / "notes.txt").exists()
    assert "No answer received" in " ".join(telegram.texts())


def test_strangers_message_during_confirmation_is_not_taken_as_yes(setup):
    bot, telegram, home, *_ = setup
    (home / "notes.txt").write_text("x")
    telegram.send_from_phone("delete notes.txt", OWNER)
    telegram.send_from_phone("yes", STRANGER)          # must NOT count
    telegram.send_from_phone("no", OWNER)
    bot.poll_once()
    assert (home / "notes.txt").exists()
    assert any("not allowed" in t for t in telegram.texts())   # stranger handled afterwards


def test_telegram_chats_are_saved_and_can_be_continued(setup):
    bot, telegram, home, db, logs, ollama = setup
    telegram.send_from_phone("create test on desktop", OWNER)
    telegram.send_from_phone("/new", OWNER)
    telegram.send_from_phone("what's on my desktop", OWNER)
    telegram.send_from_phone("/chats", OWNER)
    bot.poll_once()
    chat_list = telegram.texts()[-1]
    assert "[1] create test on desktop" in chat_list and "[2] what's on my desktop" in chat_list

    telegram.send_from_phone("/open 1", OWNER)
    telegram.send_from_phone("what's on my desktop", OWNER)
    bot.poll_once()
    assert "Opened chat [1]" in telegram.texts()[-2]
    contents = [m["content"] for m in ollama.requests[-1]["messages"]]
    assert "create test on desktop" in contents        # the AI saw chat 1's history

    user = db.connection.execute("SELECT * FROM users WHERE telegram_user_id = ?", (OWNER,)).fetchone()
    assert user["source"] == "telegram" and user["display_name"] == "Malak"
    assert db.count("conversations") == 2


def test_help_and_history_commands(setup):
    bot, telegram, *_ = setup
    telegram.send_from_phone("/start", OWNER)
    telegram.send_from_phone("create test on desktop", OWNER)
    telegram.send_from_phone("/history", OWNER)
    bot.poll_once()
    assert "AI File System Assistant" in telegram.texts()[0]
    assert "You: create test on desktop" in telegram.texts()[-1]


def test_wrong_token_gives_clear_error():
    with FakeTelegram() as telegram:
        api = TelegramAPI("wrong-token", base_url=telegram.url, timeout=0)
        with pytest.raises(TelegramError, match="token is wrong"):
            api.get_me()


def test_no_internet_gives_clear_error():
    from tests.fake_ollama import unused_url
    with pytest.raises(TelegramError, match="Cannot reach Telegram"):
        TelegramAPI(TOKEN, base_url=unused_url(), timeout=0).get_me()


def test_long_answers_are_cut_to_telegram_limit():
    with FakeTelegram() as telegram:
        TelegramAPI(TOKEN, base_url=telegram.url).send_message(1, "x" * 10_000)
        assert len(telegram.sent[0]["text"]) <= 4096


# ---- configuration (.env) ------------------------------------------------------------
def test_env_file_and_allowed_users(tmp_path, monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_ALLOWED_USERS", raising=False)
    env = tmp_path / ".env"
    env.write_text('# my secrets\nTELEGRAM_BOT_TOKEN="123:abc"\nTELEGRAM_ALLOWED_USERS=111, 222\n')
    load_env_file(env)
    import os
    assert os.environ["TELEGRAM_BOT_TOKEN"] == "123:abc"
    assert parse_user_ids(os.environ["TELEGRAM_ALLOWED_USERS"]) == {111, 222}
    assert parse_user_ids("abc, 5;6") == {5, 6}


def test_main_without_token_explains_setup(tmp_path, monkeypatch, capsys):
    import main
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.chdir(tmp_path)
    code = main.main(["--telegram", "--workspace", str(tmp_path / "ws"), "--db", str(tmp_path / "x.db"),
                      "--url", "http://127.0.0.1:1"])
    assert code == 1
    assert "@BotFather" in capsys.readouterr().out
    assert Path(tmp_path / "x.db").exists()
