"""Telegram bot: control the assistant from your phone.

How it works:
  1. You create a bot with @BotFather in Telegram and get a TOKEN.
  2. You start this program on your PC:   python main.py --telegram
  3. The program asks Telegram "any new messages?" every few seconds
     (this is called long polling: no website or open port is needed).
  4. When you write "create a folder test on my desktop" to your bot, the
     message goes Phone -> Telegram servers -> this program on your PC
     -> AI model (Ollama) -> real folder on your Desktop.
  5. The answer is sent back to your phone.

Security:
  * ONLY the Telegram user IDs listed in TELEGRAM_ALLOWED_USERS can use the
    bot. Anyone else gets "not allowed" and their ID is printed in the
    terminal (that is how you find YOUR ID the first time).
  * Deleting or overwriting still asks for confirmation: reply "yes"/"no".
  * Keep the token secret: it is stored in the .env file, which is NOT
    uploaded to GitHub (.gitignore).

Telegram commands:
  /start or /help   how to use the bot
  /new              start a new chat
  /chats            list your previous chats
  /open 3           continue chat number 3
  /history          messages of the current chat
  /search <text>    search the internet
"""

from __future__ import annotations

import threading
import time
from typing import Callable

import requests

from .database import ChatDatabase
from .service import AssistantService

TELEGRAM_API = "https://api.telegram.org"
MAX_MESSAGE_LENGTH = 4000          # Telegram's limit is 4096 characters
CONFIRM_TIMEOUT_SECONDS = 120
YES_ANSWERS = {"y", "yes", "oui", "ok", "yes please"}

HELP_TEXT = """Hello! I am your AI File System Assistant.
Write what you want in normal English, for example:
- create a folder test on my desktop
- make a folder m on the desktop with files a and b
- what's on my desktop?
- delete notes.txt (I will ask you to confirm)

Commands:
/new - start a new chat
/chats - your previous chats
/open 3 - continue chat number 3
/history - messages of this chat
/search <question> - search the internet
/help - this message"""


class TelegramError(Exception):
    """Problem talking to Telegram (bad token, no internet...)."""


class TelegramAPI:
    """The two Telegram Bot API methods we need, called with `requests`."""

    def __init__(self, token: str, base_url: str = TELEGRAM_API, timeout: int = 30):
        self.url = f"{base_url.rstrip('/')}/bot{token}"
        self.timeout = timeout

    def _call(self, method: str, payload: dict, timeout: float) -> object:
        try:
            response = requests.post(f"{self.url}/{method}", json=payload, timeout=timeout)
        except requests.exceptions.RequestException as exc:
            raise TelegramError(f"Cannot reach Telegram ({exc.__class__.__name__}). "
                                "Check your internet connection.") from exc
        try:
            data = response.json()
        except ValueError as exc:
            raise TelegramError(f"Telegram returned HTTP {response.status_code}.") from exc
        if response.status_code == 401 or data.get("error_code") == 401:
            raise TelegramError("The bot token is wrong. Copy it again from @BotFather into .env.")
        if not data.get("ok"):
            raise TelegramError(f"Telegram error: {data.get('description', 'unknown')}")
        return data.get("result")

    def get_me(self) -> dict:
        return self._call("getMe", {}, timeout=15)

    def get_updates(self, offset: int | None, timeout: int | None = None) -> list[dict]:
        wait = self.timeout if timeout is None else timeout
        payload = {"timeout": wait, "allowed_updates": ["message"]}
        if offset is not None:
            payload["offset"] = offset
        return self._call("getUpdates", payload, timeout=wait + 10) or []

    def send_message(self, chat_id: int, text: str) -> None:
        text = text if len(text) <= MAX_MESSAGE_LENGTH else text[:MAX_MESSAGE_LENGTH - 20] + "\n...(truncated)"
        self._call("sendMessage", {"chat_id": chat_id, "text": text}, timeout=15)


class TelegramBot:
    def __init__(self, api: TelegramAPI, service: AssistantService, database: ChatDatabase,
                 allowed_user_ids: set[int], log: Callable[[str], None] = print):
        self.api = api
        self.service = service
        self.database = database
        self.allowed = set(allowed_user_ids)
        self.log = log
        self.offset: int | None = None
        self.backlog: list[dict] = []                  # received updates not handled yet
        self.current_chat: dict[int, int] = {}          # telegram user id -> conversation_id
        self.confirm_timeout = CONFIRM_TIMEOUT_SECONDS

    # -- receiving --------------------------------------------------------------
    def _fetch(self, timeout: int | None = None) -> list[dict]:
        updates = self.api.get_updates(self.offset, timeout)
        if updates:
            self.offset = max(u["update_id"] for u in updates) + 1
        return updates

    def poll_once(self, timeout: int | None = None) -> int:
        """Get new messages and handle them one by one. Returns how many were handled."""
        if not self.backlog:
            self.backlog = self._fetch(timeout)
        handled = 0
        while self.backlog:
            update = self.backlog.pop(0)     # the rest stays queued (a "yes" may be in it)
            self.handle_update(update)
            handled += 1
        return handled

    def run_forever(self, stop: threading.Event | None = None, show_ctrl_c: bool = True) -> None:
        """Keep checking for messages until `stop` is set (or Ctrl+C)."""
        stop = stop or threading.Event()
        me = self.api.get_me()
        self.log(f"Telegram bot @{me.get('username', '?')} is running. Send it a message from your phone.")
        if not self.allowed:
            self.log("No allowed users yet: write to the bot once, then put the ID it shows "
                     "into TELEGRAM_ALLOWED_USERS in the .env file and restart.")
        if show_ctrl_c:
            self.log("Press Ctrl+C to stop.")
        while not stop.is_set():
            try:
                self.poll_once()
            except TelegramError as exc:
                self.log(f"Warning: {exc} Retrying in 5 seconds...")
                stop.wait(5)

    # -- handling one message -------------------------------------------------------
    def handle_update(self, update: dict) -> None:
        message = update.get("message") or {}
        text = (message.get("text") or "").strip()
        chat_id = (message.get("chat") or {}).get("id")
        sender = message.get("from") or {}
        user_tg_id = sender.get("id")
        if chat_id is None or user_tg_id is None:
            return
        name = sender.get("first_name") or sender.get("username") or str(user_tg_id)

        if user_tg_id not in self.allowed:
            self.log(f"Refused a message from {name} (Telegram user ID {user_tg_id}).")
            self.api.send_message(chat_id, "Sorry, you are not allowed to use this assistant.\n"
                                           f"Your Telegram user ID is {user_tg_id}. The owner must add it to "
                                           "TELEGRAM_ALLOWED_USERS in the .env file.")
            return
        if not text:
            self.api.send_message(chat_id, "Please send a text message.")
            return

        user_id = self.database.get_or_create_user(name, "telegram", user_tg_id)
        self.log(f"[Telegram] {name}: {text}")

        command, _, argument = text.partition(" ")
        command = command.lower().split("@")[0]          # "/open@MyBot" -> "/open"
        if command in ("/start", "/help"):
            self.api.send_message(chat_id, HELP_TEXT)
            return
        if command == "/new":
            self.current_chat[user_tg_id] = self.database.create_conversation(user_id)
            self.api.send_message(chat_id, "Started a new chat.")
            return
        if command == "/chats":
            self.api.send_message(chat_id, self._chat_list(user_id, user_tg_id))
            return
        if command == "/open":
            self.api.send_message(chat_id, self._open(user_id, user_tg_id, argument))
            return
        if command == "/history":
            self.api.send_message(chat_id, self._history(user_id, user_tg_id))
            return

        conversation_id = self._conversation_for(user_id, user_tg_id)
        if command == "/search":
            self.api.send_message(chat_id, "Searching the internet...")
            reply = self.service.search(conversation_id, argument.strip())
            self.log(f"[Telegram] Assistant: {reply.text}")
            self.api.send_message(chat_id, reply.full_text())
            return
        reply = self.service.handle(conversation_id, text,
                                    lambda question: self._confirm(chat_id, user_tg_id, question))
        self.log(f"[Telegram] Assistant: {reply.text}")
        self.api.send_message(chat_id, reply.full_text())

    # -- yes/no confirmation over Telegram ---------------------------------------------
    def _confirm(self, chat_id: int, user_tg_id: int, question: str) -> bool:
        self.api.send_message(chat_id, f"{question}\nReply yes or no.")
        deadline = time.monotonic() + self.confirm_timeout
        while True:
            # The answer may already be waiting in the queue...
            for index, update in enumerate(self.backlog):
                message = update.get("message") or {}
                if (message.get("from") or {}).get("id") == user_tg_id and message.get("text"):
                    self.backlog.pop(index)
                    return message["text"].strip().lower() in YES_ANSWERS
            if time.monotonic() >= deadline:
                break
            # ...otherwise ask Telegram for new messages (other people's stay queued).
            wait = max(1, min(10, int(deadline - time.monotonic())))
            self.backlog.extend(self._fetch(timeout=wait))
        self.api.send_message(chat_id, "No answer received, so I cancelled it.")
        return False

    # -- chats --------------------------------------------------------------------
    def _conversation_for(self, user_id: int, user_tg_id: int) -> int:
        """Continue the current chat; after a restart, continue the latest one."""
        if user_tg_id not in self.current_chat:
            latest = self.database.latest_conversation(user_id)
            self.current_chat[user_tg_id] = (latest.conversation_id if latest
                                             else self.database.create_conversation(user_id))
        return self.current_chat[user_tg_id]

    def _chat_list(self, user_id: int, user_tg_id: int) -> str:
        chats = self.database.list_conversations(user_id, limit=15)
        if not chats:
            return "You have no saved chats yet. Just write a request to start one."
        current = self.current_chat.get(user_tg_id)
        lines = ["Your chats (newest first). Send /open <number> to continue one:"]
        for chat in chats:
            mark = "  <- current" if chat.conversation_id == current else ""
            lines.append(f"[{chat.conversation_id}] {chat.title} ({chat.message_count} messages){mark}")
        return "\n".join(lines)

    def _open(self, user_id: int, user_tg_id: int, argument: str) -> str:
        if not argument.strip().isdigit():
            return "Send the chat number, for example: /open 3"
        chat = self.database.get_conversation(int(argument), user_id)
        if chat is None:
            return f"There is no chat number {argument}. Send /chats to see your chats."
        self.current_chat[user_tg_id] = chat.conversation_id
        lines = [f"Opened chat [{chat.conversation_id}] {chat.title}. Last messages:"]
        for msg in self.database.get_messages(chat.conversation_id, limit=6):
            who = "You" if msg.role == "user" else "Assistant"
            lines.append(f"{who}: {msg.content}")
        lines.append("Continue writing to carry on with this chat.")
        return "\n".join(lines)

    def _history(self, user_id: int, user_tg_id: int) -> str:
        conversation_id = self.current_chat.get(user_tg_id)
        if conversation_id is None:
            latest = self.database.latest_conversation(user_id)
            conversation_id = latest.conversation_id if latest else None
        if conversation_id is None:
            return "This chat has no messages yet."
        lines = [f"Messages of chat [{conversation_id}]:"]
        for msg in self.database.get_messages(conversation_id, limit=20):
            who = "You" if msg.role == "user" else "Assistant"
            lines.append(f"{who}: {msg.content}")
        return "\n".join(lines)
