"""Interactive terminal interface (the part the user sees).

Loop:  read a line -> built-in commands (exit, help, chats, open, new, ...)
       -> AssistantService (AI + disk + database) -> print the answer

Chats work like ChatGPT: every conversation is saved in the database.
`chats` lists them, `open 3` reopens chat number 3 and you continue where
you stopped (the AI sees the earlier messages), `new` starts a new chat.

`input_fn` and `output_fn` are injectable so tests can simulate a user.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from .config import Settings
from .database import ChatDatabase
from .ollama_client import OllamaClient, OllamaError
from .service import AssistantService

EXIT_COMMANDS = {"exit", "quit", "q", "bye", "goodbye"}
HELP_COMMANDS = {"help", "?", "h"}
YES_ANSWERS = {"y", "yes"}
TERMINAL_USER = "Terminal user"

HELP_TEXT = """You can type requests in normal English, for example:
  - Create a folder called projects on my desktop
  - Make a folder m on the desktop with files a and b
  - What's on my desktop?
  - How many files are on my desktop? (add "including subfolders" to count recursively)
  - Rename notes.txt to ideas.txt
  - Delete old.txt                   (you will be asked to confirm)
Internet:
  /search <question>  search the web, e.g. /search capital of Australia
Chats (saved in the database, like ChatGPT):
  chats        list your previous chats
  open <id>    reopen a chat and continue it, e.g. open 3
  new          start a new chat
  history      show the messages of the current chat
Other commands:
  charts       draw the database queries as charts (PNG files in charts/)
  diagram      draw the database diagram (tables, primary and foreign keys)
  debug on/off show or hide the JSON action chosen by the AI model
  help         show this message
  exit         quit the assistant"""


class AssistantCLI:
    def __init__(
        self,
        settings: Settings,
        client: OllamaClient,
        service: AssistantService,
        input_fn: Callable[[str], str] = input,
        output_fn: Callable[[str], None] = print,
    ):
        self.settings = settings
        self.client = client
        self.service = service
        self.database: ChatDatabase | None = service.database
        self.input_fn = input_fn
        self.output_fn = output_fn
        self.user_id: int | None = None
        self.conversation_id: int | None = None     # created on the first message
        self._warning_shown = False
        if self.database is not None:
            self.user_id = self.database.get_or_create_user(TERMINAL_USER, "terminal")

    # -- output helpers -----------------------------------------------------
    def say(self, text: str = "") -> None:
        self.output_fn(text)

    def assistant(self, text: str) -> None:
        self.say(f"Assistant: {text}")

    def show_banner(self) -> None:
        line = "=" * 40
        self.say(line)
        self.say("     AI FILE SYSTEM ASSISTANT")
        self.say(line)
        self.say(f"AI Model: {self.settings.model_display_name} ({self.settings.model})")
        self.say("Runtime: Ollama")
        self.say("Language: Python")
        if self.database is not None:
            self.say(f"Database: {Path(self.database.db_path).resolve()}")
        self.say()
        self.say(f"Workspace: {Path(self.settings.workspace).resolve()}")
        self.say("(Desktop, Documents and Downloads are inside it. Nothing outside can be changed.)")
        self.say("Type 'help' for examples, 'chats' to continue an old chat, or 'exit' to quit.")
        self.say()

    def check_ollama(self) -> bool:
        """Startup check. Returns False (with advice) instead of crashing."""
        try:
            self.client.check_ready()
            return True
        except OllamaError as exc:
            self.say(f"Warning: {exc}")
            self.say("The assistant will keep running; fix the problem and try your request again.")
            self.say()
            return False

    def confirm(self, question: str) -> bool:
        """Ask a yes/no question. Only 'y' or 'yes' counts as yes."""
        try:
            answer = self.input_fn(f"Assistant: {question} (yes/no) > ")
        except (EOFError, KeyboardInterrupt):
            self.say()
            return False
        return answer.strip().lower() in YES_ANSWERS

    # -- chat commands ----------------------------------------------------------
    def _need_database(self) -> bool:
        if self.database is None or self.user_id is None:
            self.assistant("The database is turned off (started with --no-history).")
            return False
        return True

    def new_chat(self) -> None:
        self.conversation_id = None          # the chat is created with the next message
        self.service.interpreter.reset()
        self.assistant("Started a new chat.")

    def list_chats(self) -> None:
        if not self._need_database():
            return
        chats = self.database.list_conversations(self.user_id, limit=20)
        if not chats:
            self.assistant("You have no saved chats yet.")
            return
        self.assistant("Your chats (newest first). Type 'open <id>' to continue one:")
        for chat in chats:
            current = "  <- current" if chat.conversation_id == self.conversation_id else ""
            self.say(f"  [{chat.conversation_id}] {chat.title}  "
                     f"({chat.message_count} messages, last used {chat.updated_at}){current}")

    def open_chat(self, argument: str) -> None:
        if not self._need_database():
            return
        if not argument.strip().isdigit():
            self.assistant("Please give the chat number, e.g. 'open 3'. Type 'chats' to see them.")
            return
        chat = self.database.get_conversation(int(argument), self.user_id)
        if chat is None:
            self.assistant(f"There is no chat number {argument}. Type 'chats' to see your chats.")
            return
        self.conversation_id = chat.conversation_id
        self.service.interpreter.reset()
        self.assistant(f"Opened chat [{chat.conversation_id}] {chat.title}. Last messages:")
        self._print_messages(limit=10)
        self.say("  (continue typing to carry on with this chat)")

    def show_history(self) -> None:
        if not self._need_database():
            return
        if self.conversation_id is None:
            self.assistant("This chat has no messages yet.")
            return
        self.assistant(f"Messages of chat [{self.conversation_id}]:")
        self._print_messages(limit=None)

    def _print_messages(self, limit: int | None) -> None:
        for msg in self.database.get_messages(self.conversation_id, limit):
            who = "You" if msg.role == "user" else "Assistant"
            first, *rest = msg.content.splitlines() or [""]
            self.say(f"  {msg.created_at}  {who}: {first}")
            for line in rest:
                self.say(f"      {line}")

    def draw(self, what: str) -> None:
        if not self._need_database():
            return
        out_dir = Path(self.database.db_path).resolve().parent / "charts"
        if what == "charts":
            from .charts import ChartError, draw_all          # matplotlib is optional
            try:
                files = draw_all(self.database.db_path, out_dir)
            except ChartError as exc:
                self.assistant(f"Error: {exc}")
                return
        else:
            from .erd import ChartError, draw_erd
            try:
                files = [draw_erd(self.database.db_path, out_dir / "database_diagram.png")]
            except ChartError as exc:
                self.assistant(f"Error: {exc}")
                return
        self.assistant(f"I drew {len(files)} image(s):")
        for path in files:
            self.say(f"  {path}")
        self.say("  Open them in VS Code (click the file) or in File Explorer.")

    # -- main loop ----------------------------------------------------------
    def handle(self, text: str) -> bool:
        """Process one line. Returns False when the app should stop."""
        command = text.strip()
        lowered = command.lower()
        if not command:
            return True
        if lowered in EXIT_COMMANDS:
            return False
        if lowered in HELP_COMMANDS:
            self.say(HELP_TEXT)
            return True
        if lowered in ("debug on", "debug off"):
            self.settings.debug = lowered == "debug on"
            self.assistant(f"Debug mode {'enabled' if self.settings.debug else 'disabled'}.")
            return True
        if lowered in ("new", "new chat"):
            self.new_chat()
            return True
        if lowered in ("chats", "list chats", "my chats"):
            self.list_chats()
            return True
        if lowered.startswith("open ") or lowered == "open":
            self.open_chat(command[4:].strip())
            return True
        if lowered in ("history", "show history"):
            self.show_history()
            return True
        if lowered in ("charts", "chart", "draw charts"):
            self.draw("charts")
            return True
        if lowered in ("diagram", "erd", "draw diagram"):
            self.draw("diagram")
            return True

        if self.database is not None and self.conversation_id is None:
            self.conversation_id = self.database.create_conversation(self.user_id)

        if lowered == "/search" or lowered.startswith("/search "):
            self.say("(searching the internet...)")
            reply = self.service.search(self.conversation_id, command[len("/search"):].strip())
        else:
            self.say("(thinking...)")
            reply = self.service.handle(self.conversation_id, command, self.confirm)
        if self.settings.debug and reply.action is not None:
            self.say(f"[debug] model action: {json.dumps(reply.action.to_dict())}")
        self.assistant(reply.text)
        for line in reply.details:
            self.say(f"  {line}")
        if self.service.database_warning and not self._warning_shown:
            self.say(f"Warning: {self.service.database_warning}")
            self._warning_shown = True
        return True

    def run(self, before_loop: Callable[[], None] | None = None) -> None:
        self.show_banner()
        self.check_ollama()
        if before_loop is not None:
            before_loop()          # e.g. start the Telegram bot in the background
        self.say("What would you like me to do?")
        while True:
            try:
                text = self.input_fn("> ")
            except (EOFError, KeyboardInterrupt):
                self.say()
                break
            self.say()
            try:
                keep_running = self.handle(text)
            except KeyboardInterrupt:
                self.assistant("Cancelled.")
                keep_running = True
            except Exception as exc:  # last safety net: never crash the session
                self.assistant(f"Unexpected error: {exc}")
                keep_running = True
            if not keep_running:
                break
            self.say()
        self.say("Goodbye!")
