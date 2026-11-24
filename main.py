"""Entry point.

    python main.py                 terminal chat + Telegram bot at the same time
                                   (the bot starts automatically when .env has a token)
    python main.py --no-telegram   terminal chat only
    python main.py --telegram      Telegram bot only (no terminal chat)

Optional flags:
    --workspace PATH   folder the assistant may modify (default: your user folder)
    --model NAME       Ollama model identifier   (default: qwen3.5:4b)
    --url URL          Ollama server address     (default: http://localhost:11434)
    --debug            show the JSON action produced by the model
    --db FILE          SQLite database file      (default: assistant.db)
    --no-history       do not use the database (no saved chats)
    --telegram         run ONLY the Telegram bot
    --no-telegram      do not start the Telegram bot
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import threading
from dataclasses import dataclass
from pathlib import Path

from fs_assistant.cli import AssistantCLI
from fs_assistant.config import Settings
from fs_assistant.database import ChatDatabase
from fs_assistant.executor import Executor
from fs_assistant.file_ops import FileSystemOperations
from fs_assistant.interpreter import Interpreter
from fs_assistant.ollama_client import OllamaClient, OllamaError
from fs_assistant.service import AssistantService
from fs_assistant.web_search import WebSearcher
from fs_assistant.workspace import Workspace


def build_settings(argv: list[str] | None = None) -> tuple[Settings, argparse.Namespace]:
    parser = argparse.ArgumentParser(description="AI File System Assistant (Python + Ollama)")
    parser.add_argument("--workspace", help="folder the assistant is allowed to modify")
    parser.add_argument("--model", help="Ollama model identifier, e.g. qwen3.5:4b")
    parser.add_argument("--url", help="Ollama server URL, e.g. http://localhost:11434")
    parser.add_argument("--debug", action="store_true", help="show the model's JSON action")
    parser.add_argument("--db", help="SQLite database file (default: assistant.db)")
    parser.add_argument("--no-history", action="store_true", help="do not use the database")
    parser.add_argument("--telegram", action="store_true", help="run ONLY the Telegram bot")
    parser.add_argument("--no-telegram", action="store_true", help="do not start the Telegram bot")
    args = parser.parse_args(argv)

    settings = Settings.from_env()
    if args.workspace:
        settings.workspace = Path(args.workspace)
    if args.model:
        settings.model = args.model
        settings.model_display_name = args.model
    if args.url:
        settings.ollama_url = args.url.rstrip("/")
    if args.debug:
        settings.debug = True
    if args.db:
        settings.db_path = Path(args.db)
    if args.no_history:
        settings.db_path = None
    return settings, args


@dataclass
class Components:
    client: OllamaClient
    service: AssistantService
    database: ChatDatabase | None


def build_components(settings: Settings) -> Components:
    """Create and connect every module (used by the terminal, Telegram and tests)."""
    workspace = Workspace(settings.workspace)
    workspace.ensure_exists()
    client = OllamaClient(
        base_url=settings.ollama_url,
        model=settings.model,
        timeout=settings.timeout_seconds,
        temperature=settings.temperature,
        think=settings.think,
    )
    database = ChatDatabase(settings.db_path) if settings.db_path else None
    service = AssistantService(settings, Interpreter(client),
                               Executor(FileSystemOperations(workspace)), database,
                               WebSearcher(client))
    return Components(client, service, database)


def build_app(settings: Settings, input_fn=input, output_fn=print) -> AssistantCLI:
    """The terminal application (also used by the integration tests)."""
    parts = build_components(settings)
    return AssistantCLI(settings, parts.client, parts.service, input_fn, output_fn)


def run_telegram(settings: Settings, parts: Components) -> int:
    from fs_assistant.telegram_bot import TelegramAPI, TelegramBot, TelegramError

    if not settings.telegram_token:
        print("No Telegram bot token found.")
        print("1. In Telegram, talk to @BotFather, send /newbot and copy the token.")
        print("2. Create a file named .env in this folder containing:")
        print("     TELEGRAM_BOT_TOKEN=123456:ABC-your-token")
        print("     TELEGRAM_ALLOWED_USERS=")
        print("See docs/TELEGRAM.md for the full guide.")
        return 1
    if parts.database is None:
        print("The Telegram bot needs the database (do not use --no-history).")
        return 1
    try:
        parts.client.check_ready()
    except OllamaError as exc:
        print(f"Warning: {exc}")
    print(f"Workspace: {Path(settings.workspace).resolve()}")
    print(f"Database:  {Path(parts.database.db_path).resolve()}")
    bot = TelegramBot(TelegramAPI(settings.telegram_token, base_url=settings.telegram_api_url),
                      parts.service, parts.database,
                      settings.telegram_allowed_users)
    try:
        bot.run_forever()
    except TelegramError as exc:
        print(f"Error: {exc}")
        return 1
    except KeyboardInterrupt:
        print("\nTelegram bot stopped. Goodbye!")
    return 0


def start_telegram_in_background(settings: Settings, log=print) -> threading.Event | None:
    """Start the bot in a background thread so the terminal chat keeps working.

    The bot builds its OWN components inside its thread (its own database
    connection), because a SQLite connection must not be shared between threads.
    Returns an Event to stop the bot, or None if there is no token.
    """
    from fs_assistant.telegram_bot import TelegramAPI, TelegramBot, TelegramError

    if not settings.telegram_token or settings.db_path is None:
        return None
    stop = threading.Event()

    def run() -> None:
        parts = None
        try:
            parts = build_components(settings)
            bot = TelegramBot(TelegramAPI(settings.telegram_token, base_url=settings.telegram_api_url),
                              parts.service, parts.database, settings.telegram_allowed_users,
                              log=lambda text: log("\n" + (text if text.startswith("[Telegram]")
                                                             else f"[Telegram] {text}")))
            bot.run_forever(stop, show_ctrl_c=False)
        except TelegramError as exc:
            log(f"\n[Telegram] The bot could not start: {exc} (the terminal chat still works)")
        except Exception as exc:            # never let the bot crash the terminal chat
            log(f"\n[Telegram] The bot stopped because of an error: {exc}")
        finally:
            if parts is not None and parts.database is not None:
                parts.database.close()

    threading.Thread(target=run, name="telegram-bot", daemon=True).start()
    return stop


def main(argv: list[str] | None = None) -> int:
    settings, args = build_settings(argv)
    try:
        parts = build_components(settings)
    except OSError as exc:
        print(f"Could not prepare the workspace folder '{settings.workspace}': {exc}")
        return 1
    except sqlite3.Error as exc:
        print(f"Could not open the database '{settings.db_path}': {exc}")
        print("Start with --no-history to run without it.")
        return 1
    background = None
    try:
        if args.telegram:
            return run_telegram(settings, parts)
        cli = AssistantCLI(settings, parts.client, parts.service)

        def start_bot() -> None:
            nonlocal background
            if args.no_telegram:
                return
            if not settings.telegram_token:
                cli.say("Telegram: off (no token in .env). See docs/TELEGRAM.md to turn it on.")
                return
            background = start_telegram_in_background(settings)
            if background is not None:
                cli.say("Telegram: the bot is starting in the background - you can use your phone "
                        "and this terminal at the same time.")
            cli.say()

        cli.run(before_loop=start_bot)
        return 0
    finally:
        if background is not None:
            background.set()   # the thread is a daemon: it ends with the program
        if parts.database is not None:
            parts.database.close()


if __name__ == "__main__":
    sys.exit(main())
