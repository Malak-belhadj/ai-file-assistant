"""Natural language -> validated Action, using the language model.

Steps for every user request:
  1. Build the message list: system prompt + (pending clarification) + request
  2. Ask the model through OllamaClient (JSON schema enforced by Ollama)
  3. Parse the reply text as JSON
  4. Validate it with actions.validate_action()
  5. If parsing/validation fails, ask the model ONCE more with the error
  6. If it still fails, raise InterpretationError

Clarification memory: when the model answers with "clarify", the question
and the original request are remembered, so the user's next answer
("notes.txt") is understood in context ("create a file" -> "notes.txt").
"""

from __future__ import annotations

import json
import re
from typing import Any

from .actions import (
    ACTION_JSON_SCHEMA,
    CLARIFY,
    Action,
    ActionValidationError,
    MissingFieldError,
    validate_action,
)
from .config import MAX_CLARIFICATION_ROUNDS
from .ollama_client import OllamaClient
from .prompts import CORRECTION_PROMPT, SYSTEM_PROMPT


class InterpretationError(Exception):
    """The model's answer could not be turned into a valid action."""


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def parse_model_json(text: str) -> dict[str, Any]:
    """Extract a JSON object from the model's reply.

    Handles the common small-model habits of wrapping JSON in ```json fences
    or adding a sentence before/after it.
    """
    if not isinstance(text, str) or not text.strip():
        raise ActionValidationError("The model returned an empty reply.")
    cleaned = _FENCE.sub("", text.strip()).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end <= start:
            raise ActionValidationError("The model's reply is not JSON.") from None
        try:
            data = json.loads(cleaned[start:end + 1])
        except json.JSONDecodeError:
            raise ActionValidationError("The model's reply is not valid JSON.") from None
    if not isinstance(data, dict):
        raise ActionValidationError("The model's reply is not a JSON object.")
    return data


class Interpreter:
    def __init__(self, client: OllamaClient, max_retries: int = 1):
        self.client = client
        self.max_retries = max_retries
        self._pending: list[dict[str, str]] = []   # messages of an open clarification
        self.last_raw_reply: str = ""                # useful for --debug and tests

    def reset(self) -> None:
        """Forget any open clarification."""
        self._pending = []

    def interpret(self, user_text: str, context: list[dict[str, str]] | None = None) -> Action:
        """Turn one user instruction into an Action.

        Args:
            user_text: what the user typed.
            context: earlier messages of the same chat, loaded from the
                database (user text + the JSON the model answered). When it
                is given, the in-memory clarification memory is not used,
                because the database already contains that exchange.

        Raises:
            InterpretationError: model output unusable even after a retry.
            OllamaError (and subclasses): Ollama unavailable, model missing...
        """
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(context if context is not None else self._pending)
        messages.append({"role": "user", "content": user_text})

        last_error = "unknown error"
        for _attempt in range(self.max_retries + 1):
            reply = self.client.chat(messages, json_schema=ACTION_JSON_SCHEMA)
            self.last_raw_reply = reply
            try:
                data = parse_model_json(reply)
                action = validate_action(data)
            except MissingFieldError as exc:
                # Not the model's fault in most cases: the user left out a detail.
                action = Action(action=CLARIFY, question=exc.question)
            except ActionValidationError as exc:
                last_error = str(exc)
                messages.append({"role": "assistant", "content": reply})
                messages.append({"role": "user", "content": CORRECTION_PROMPT.format(error=last_error)})
                continue

            if context is None:
                self._remember(user_text, action)
            return action

        self.reset()
        raise InterpretationError(
            "Sorry, I could not understand that request. "
            "Try rephrasing it, e.g. 'create a file called notes.txt'. "
            f"(Details: {last_error})"
        )

    def _remember(self, user_text: str, action: Action) -> None:
        if action.action != CLARIFY:
            self._pending = []
            return
        self._pending.append({"role": "user", "content": user_text})
        self._pending.append({"role": "assistant", "content": json.dumps(action.to_dict())})
        # Keep only the last few rounds so the prompt stays small.
        self._pending = self._pending[-2 * MAX_CLARIFICATION_ROUNDS:]
