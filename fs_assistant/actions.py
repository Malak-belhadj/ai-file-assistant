"""The shared contract between all modules.

The language model produces a JSON object. This module turns that raw
dictionary into a validated `Action` object, or raises an error explaining
what is wrong. Nothing is executed here: this file only checks data.

Action JSON format (every field except "action" is optional in the JSON,
but some actions require certain fields - see REQUIRED_FIELDS):

    {
      "action":   one of ALLOWED_ACTIONS,
      "path":     relative path inside the workspace, e.g. "projects/main.py",
      "new_name": new name or relative path (rename_file only),
      "content":  text to write into a new file (create_file only, optional),
      "files":    list of file names to create inside the new folder
                  (create_directory only, optional), e.g. ["a.txt", "b.txt"],
      "recursive": true/false (count_files only),
      "question": clarifying question to ask the user (clarify only),
      "message":  short explanation (unsupported only)
    }
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .config import MAX_CONTENT_LENGTH, MAX_FILES_PER_REQUEST, MAX_PATH_LENGTH

# ---------------------------------------------------------------------------
# Action names
# ---------------------------------------------------------------------------
CREATE_FILE = "create_file"
CREATE_DIRECTORY = "create_directory"
LIST_DIRECTORY = "list_directory"
COUNT_FILES = "count_files"
RENAME_FILE = "rename_file"
DELETE_FILE = "delete_file"
CLARIFY = "clarify"
UNSUPPORTED = "unsupported"

ALLOWED_ACTIONS = (
    CREATE_FILE,
    CREATE_DIRECTORY,
    LIST_DIRECTORY,
    COUNT_FILES,
    RENAME_FILE,
    DELETE_FILE,
    CLARIFY,
    UNSUPPORTED,
)

# Fields that MUST be present (and non-empty) for each action.
REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    CREATE_FILE: ("path",),
    CREATE_DIRECTORY: ("path",),
    LIST_DIRECTORY: (),          # missing path means "." (workspace root)
    COUNT_FILES: (),             # missing path means "." (workspace root)
    RENAME_FILE: ("path", "new_name"),
    DELETE_FILE: ("path",),
    CLARIFY: ("question",),
    UNSUPPORTED: (),
}

# Question asked when the model chose an action but forgot a required field.
MISSING_FIELD_QUESTIONS: dict[tuple[str, str], str] = {
    (CREATE_FILE, "path"): "What should the new file be called?",
    (CREATE_DIRECTORY, "path"): "What should the new folder be called?",
    (RENAME_FILE, "path"): "Which file do you want to rename?",
    (RENAME_FILE, "new_name"): "What should the new name be?",
    (DELETE_FILE, "path"): "Which file do you want to delete?",
    (CLARIFY, "question"): "Could you describe what you want me to do in more detail?",
}

# JSON schema sent to Ollama's "format" parameter. Ollama uses it to force
# the model to answer with a JSON object of exactly this shape.
ACTION_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": list(ALLOWED_ACTIONS)},
        "path": {"type": "string"},
        "new_name": {"type": "string"},
        "content": {"type": "string"},
        "files": {"type": "array", "items": {"type": "string"}},
        "recursive": {"type": "boolean"},
        "question": {"type": "string"},
        "message": {"type": "string"},
    },
    "required": ["action"],
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass
class Action:
    """A validated instruction that the Executor can run."""

    action: str
    path: str = "."
    new_name: str = ""
    content: str = ""
    files: list[str] = field(default_factory=list)
    recursive: bool = False
    question: str = ""
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Return only the fields that matter for this action (for display)."""
        data: dict[str, Any] = {"action": self.action}
        if self.action in (CREATE_FILE, CREATE_DIRECTORY, LIST_DIRECTORY,
                           COUNT_FILES, RENAME_FILE, DELETE_FILE):
            data["path"] = self.path
        if self.action == RENAME_FILE:
            data["new_name"] = self.new_name
        if self.action == CREATE_FILE and self.content:
            data["content"] = self.content
        if self.action == CREATE_DIRECTORY and self.files:
            data["files"] = list(self.files)
        if self.action == COUNT_FILES:
            data["recursive"] = self.recursive
        if self.action == CLARIFY:
            data["question"] = self.question
        if self.action == UNSUPPORTED:
            data["message"] = self.message
        return data


@dataclass
class ActionResult:
    """What the Executor returns to the CLI after running an Action."""

    success: bool
    message: str
    details: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------
class ActionValidationError(ValueError):
    """The model's output is not a valid action (wrong type, unknown action...)."""


class MissingFieldError(ActionValidationError):
    """A required field is missing; `question` is what we should ask the user."""

    def __init__(self, action: str, field_name: str, question: str):
        super().__init__(f"Action '{action}' is missing the field '{field_name}'.")
        self.action = action
        self.field_name = field_name
        self.question = question


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def _clean_string(data: dict[str, Any], key: str, max_length: int) -> str:
    """Return data[key] as a stripped string ('' if absent). Reject non-strings."""
    value = data.get(key)
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ActionValidationError(f"Field '{key}' must be text, got {type(value).__name__}.")
    value = value.strip()
    if len(value) > max_length:
        raise ActionValidationError(f"Field '{key}' is too long (max {max_length} characters).")
    return value


def _clean_bool(data: dict[str, Any], key: str) -> bool:
    value = data.get(key, False)
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in ("true", "false"):
        return value.strip().lower() == "true"
    if value is None:
        return False
    raise ActionValidationError(f"Field '{key}' must be true or false.")


def _clean_file_list(data: dict[str, Any], key: str) -> list[str]:
    """Return data[key] as a list of non-empty, unique file names."""
    value = data.get(key)
    if value is None or value == "":
        return []
    if isinstance(value, str):          # small models sometimes send "a.txt, b.txt"
        value = [v for v in value.replace(";", ",").split(",")]
    if not isinstance(value, list):
        raise ActionValidationError(f"Field '{key}' must be a list of file names.")
    names: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ActionValidationError(f"Field '{key}' must contain only text.")
        item = item.strip()
        if not item:
            continue
        if len(item) > MAX_PATH_LENGTH:
            raise ActionValidationError(f"The file name '{item[:30]}...' is too long.")
        if item not in names:
            names.append(item)
    if len(names) > MAX_FILES_PER_REQUEST:
        raise ActionValidationError(f"Too many files in one request (max {MAX_FILES_PER_REQUEST}).")
    return names


def validate_action(data: Any) -> Action:
    """Convert the model's raw JSON dictionary into a safe `Action`.

    Raises:
        ActionValidationError: the data is not a usable action.
        MissingFieldError: the action is valid but a required field is empty.
    """
    if not isinstance(data, dict):
        raise ActionValidationError("The model's answer is not a JSON object.")

    name = data.get("action")
    if not isinstance(name, str) or not name.strip():
        raise ActionValidationError("The model's answer has no 'action' field.")
    name = name.strip().lower()
    if name not in ALLOWED_ACTIONS:
        raise ActionValidationError(f"Unknown action '{name}'.")

    action = Action(
        action=name,
        path=_clean_string(data, "path", MAX_PATH_LENGTH),
        new_name=_clean_string(data, "new_name", MAX_PATH_LENGTH),
        content=_clean_string(data, "content", MAX_CONTENT_LENGTH),
        files=_clean_file_list(data, "files"),
        recursive=_clean_bool(data, "recursive"),
        question=_clean_string(data, "question", 500),
        message=_clean_string(data, "message", 500),
    )

    for required in REQUIRED_FIELDS[name]:
        if not getattr(action, required):
            question = MISSING_FIELD_QUESTIONS.get(
                (name, required), "Could you give me more details?"
            )
            raise MissingFieldError(name, required, question)

    if name != CREATE_DIRECTORY:
        action.files = []                # only meaningful for create_directory

    if name in (LIST_DIRECTORY, COUNT_FILES) and not action.path:
        action.path = "."

    return action
