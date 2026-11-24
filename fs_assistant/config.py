"""Application settings.

All tunable values live here so that the team only has to change ONE place
(for example to switch to a different Ollama model).

Every setting can also be overridden with an environment variable or a
command-line flag (see main.py), e.g. in PowerShell:

    $env:FSA_MODEL = "qwen3.5:2b"
    python main.py
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
DEFAULT_MODEL = "qwen3.5:4b"          # exact Ollama identifier (verified in Phase 1)
DEFAULT_MODEL_DISPLAY_NAME = "Qwen 3.5 4B"
DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_WORKSPACE = str(Path.home())  # your user folder, e.g. C:\Users\MALAK (Desktop, Documents...)
DEFAULT_DB_PATH = "assistant.db"     # SQLite history file, created in the folder you run from
DEFAULT_TIMEOUT_SECONDS = 180         # first request loads the model; can be slow on CPU
DEFAULT_TEMPERATURE = 0.0             # 0 = most predictable output
DEFAULT_THINK = False                 # disable Qwen "thinking" mode: faster, cleaner JSON

# Limits that protect the application from unreasonable model output.
MAX_PATH_LENGTH = 200
MAX_CONTENT_LENGTH = 10_000
MAX_LIST_ENTRIES = 200
MAX_CLARIFICATION_ROUNDS = 3
MAX_FILES_PER_REQUEST = 50
MAX_RECURSIVE_COUNT = 20_000      # stop counting after this many entries (big folders are slow)


def load_env_file(path: Path | str = ".env") -> None:
    """Read KEY=VALUE lines from a .env file into the environment.

    Used for secrets such as the Telegram bot token, so they are not written
    in the code. Values already set in the environment are kept.
    """
    env_path = Path(path)
    if not env_path.is_file():
        return
    for raw in env_path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def parse_user_ids(text: str) -> set[int]:
    """'123, 456' -> {123, 456} (anything that is not a number is ignored)."""
    ids = set()
    for part in text.replace(";", ",").split(","):
        part = part.strip()
        if part.lstrip("-").isdigit():
            ids.add(int(part))
    return ids


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Settings:
    """Runtime configuration shared by every module."""

    model: str = DEFAULT_MODEL
    model_display_name: str = DEFAULT_MODEL_DISPLAY_NAME
    ollama_url: str = DEFAULT_OLLAMA_URL
    workspace: Path = Path(DEFAULT_WORKSPACE)
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    temperature: float = DEFAULT_TEMPERATURE
    think: bool = DEFAULT_THINK
    debug: bool = False               # when True the CLI prints the model's JSON action
    db_path: Path | None = Path(DEFAULT_DB_PATH)   # None = do not save history
    telegram_token: str = ""                       # from @BotFather, kept in .env
    telegram_allowed_users: set[int] = field(default_factory=set)
    telegram_api_url: str = "https://api.telegram.org"

    @classmethod
    def from_env(cls) -> "Settings":
        """Build settings from defaults + optional FSA_* environment variables
        (and the .env file in the current folder, if there is one)."""
        load_env_file()
        model = os.environ.get("FSA_MODEL", DEFAULT_MODEL)
        display = os.environ.get(
            "FSA_MODEL_NAME",
            DEFAULT_MODEL_DISPLAY_NAME if model == DEFAULT_MODEL else model,
        )
        return cls(
            model=model,
            model_display_name=display,
            ollama_url=os.environ.get("FSA_OLLAMA_URL", DEFAULT_OLLAMA_URL).rstrip("/"),
            workspace=Path(os.environ.get("FSA_WORKSPACE", DEFAULT_WORKSPACE)),
            timeout_seconds=float(os.environ.get("FSA_TIMEOUT", DEFAULT_TIMEOUT_SECONDS)),
            think=_env_bool("FSA_THINK", DEFAULT_THINK),
            debug=_env_bool("FSA_DEBUG", False),
            db_path=Path(os.environ.get("FSA_DB", DEFAULT_DB_PATH)),
            telegram_token=os.environ.get("TELEGRAM_BOT_TOKEN", "").strip(),
            telegram_allowed_users=parse_user_ids(os.environ.get("TELEGRAM_ALLOWED_USERS", "")),
            telegram_api_url=os.environ.get("TELEGRAM_API_URL", "https://api.telegram.org"),
        )
