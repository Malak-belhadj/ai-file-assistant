"""The assistant "engine", shared by the terminal (cli.py) and Telegram.

For one user message it:
  1. saves the message in the database (table `messages`)
  2. loads the earlier messages of the same chat (context for the AI)
  3. asks the AI model what to do (Interpreter -> Ollama -> JSON action)
  4. runs the action safely (Executor -> FileSystemOperations)
  5. saves the answer (table `messages`) and the action (table `actions`)
  6. returns the text to show to the user

The terminal and the Telegram bot only differ in HOW they read text and
show answers; everything else happens here, so both behave identically.
"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass, field
from typing import Callable

from .actions import CLARIFY, UNSUPPORTED, Action
from .config import Settings
from .database import ChatDatabase
from .executor import Executor
from .interpreter import InterpretationError, Interpreter
from .ollama_client import OllamaError
from .web_search import SearchError, WebSearcher, format_answer

ConfirmFunction = Callable[[str], bool]
CONTEXT_TURNS = 6          # how many earlier user messages the AI sees


@dataclass
class Reply:
    """What the user should see after one request."""

    text: str
    details: list[str] = field(default_factory=list)
    action: Action | None = None
    success: bool = False

    def full_text(self) -> str:
        """Text + details on separate lines (used by Telegram)."""
        return "\n".join([self.text, *self.details])


class AssistantService:
    def __init__(self, settings: Settings, interpreter: Interpreter, executor: Executor,
                 database: ChatDatabase | None = None, searcher: WebSearcher | None = None):
        self.settings = settings
        self.interpreter = interpreter
        self.executor = executor
        self.database = database
        self.searcher = searcher
        self.database_warning: str | None = None   # set if saving failed (shown once by the CLI)

    def handle(self, conversation_id: int | None, text: str, confirm: ConfirmFunction) -> Reply:
        started = time.perf_counter()
        user_message_id: int | None = None
        context: list[dict[str, str]] | None = None

        if self.database is not None and conversation_id is not None:
            try:
                context = self.database.get_context(conversation_id, CONTEXT_TURNS)
                user_message_id = self.database.add_message(conversation_id, "user", text)
            except sqlite3.Error as exc:
                self.database_warning = f"could not save to the database ({exc})"
                context = None

        try:
            action = self.interpreter.interpret(text, context)
        except OllamaError as exc:
            reply = Reply(f"AI model unavailable: {exc}")
            self._save(conversation_id, user_message_id, reply, "error", None, None, started)
            return reply
        except InterpretationError as exc:
            reply = Reply(str(exc))
            self._save(conversation_id, user_message_id, reply, "error",
                       self.interpreter.last_raw_reply or None, None, started)
            return reply

        result = self.executor.execute(action, confirm)
        show_error_prefix = not result.success and action.action not in (CLARIFY, UNSUPPORTED)
        reply = Reply(("Error: " if show_error_prefix else "") + result.message,
                      list(result.details), action, result.success)
        has_path = action.action not in (CLARIFY, UNSUPPORTED)
        self._save(conversation_id, user_message_id, reply, action.action,
                   json.dumps(action.to_dict()), action.path if has_path else None, started)
        return reply

    def search(self, conversation_id: int | None, query: str) -> Reply:
        """The /search command: internet search + short AI answer with sources."""
        started = time.perf_counter()
        user_message_id: int | None = None
        if self.database is not None and conversation_id is not None:
            try:
                user_message_id = self.database.add_message(conversation_id, "user", f"/search {query}")
            except sqlite3.Error as exc:
                self.database_warning = f"could not save to the database ({exc})"
        if self.searcher is None:
            reply = Reply("Internet search is not available.")
        else:
            try:
                summary, results = self.searcher.answer(query)
                text, details = format_answer(summary, results)
                reply = Reply(text, details, None, True)
            except SearchError as exc:
                reply = Reply(f"Error: {exc}")
        self._save(conversation_id, user_message_id, reply, "web_search",
                   json.dumps({"action": "web_search", "query": query}), None, started)
        return reply

    def _save(self, conversation_id, user_message_id, reply: Reply, action_type: str,
              model_json: str | None, path: str | None, started: float) -> None:
        if self.database is None or conversation_id is None or user_message_id is None:
            return
        try:
            self.database.add_action(
                user_message_id, action_type, reply.success, reply.text, path=path,
                model_json=model_json, duration_ms=int((time.perf_counter() - started) * 1000),
                model=self.settings.model,
            )
            self.database.add_message(conversation_id, "assistant", reply.full_text())
        except sqlite3.Error as exc:
            self.database_warning = f"could not save to the database ({exc})"
