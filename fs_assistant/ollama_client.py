"""Talks to the local Ollama server over HTTP.

Ollama runs a small web server on your computer (default
http://localhost:11434). We send it the conversation as JSON and it answers
with the model's reply. Two endpoints are used:

    GET  /api/tags   -> list of installed models (used for the startup check)
    POST /api/chat   -> ask the model a question

This module knows nothing about files or actions: it only sends messages and
returns the model's text, translating network problems into clear errors.
"""

from __future__ import annotations

from typing import Any

import requests


class OllamaError(Exception):
    """Base class: every message is written for the end user."""


class OllamaConnectionError(OllamaError):
    """Ollama is not installed, not running, or the URL is wrong."""


class ModelNotFoundError(OllamaError):
    """Ollama is running but the requested model has not been downloaded."""


class OllamaTimeoutError(OllamaError):
    """The model took too long to answer."""


class OllamaResponseError(OllamaError):
    """Ollama answered, but with an error or an unexpected format."""


def _same_model(requested: str, installed: str) -> bool:
    """'qwen3.5:4b' matches 'qwen3.5:4b'; 'llama3' matches 'llama3:latest'."""
    req = requested if ":" in requested else requested + ":latest"
    inst = installed if ":" in installed else installed + ":latest"
    return req.lower() == inst.lower()


class OllamaClient:
    def __init__(self, base_url: str, model: str, timeout: float = 180,
                 temperature: float = 0.0, think: bool | None = False):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.temperature = temperature
        self.think = think

    def _connect_timeout(self) -> float:
        """Seconds to wait for the connection itself (not for the answer)."""
        return min(5.0, self.timeout)

    def _connection_error(self) -> OllamaConnectionError:
        return OllamaConnectionError(
            f"Cannot connect to Ollama at {self.base_url}. "
            "Make sure Ollama is installed and running (open the Ollama app, "
            "or run 'ollama serve' in another terminal)."
        )

    def _missing_model_error(self) -> ModelNotFoundError:
        return ModelNotFoundError(
            f"The model '{self.model}' is not installed in Ollama. "
            f"Download it with:  ollama pull {self.model}"
        )

    # -- public API ---------------------------------------------------------
    def list_models(self) -> list[str]:
        """Return the names of the installed models."""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=(self._connect_timeout(), 10))
        except requests.exceptions.ConnectTimeout as exc:
            # Could not even open a connection: Ollama is not running/reachable.
            raise self._connection_error() from exc
        except requests.exceptions.Timeout as exc:
            raise OllamaTimeoutError("Ollama did not respond within 10 seconds.") from exc
        except requests.exceptions.RequestException as exc:
            raise self._connection_error() from exc
        if response.status_code != 200:
            raise OllamaResponseError(f"Ollama returned HTTP {response.status_code} for /api/tags.")
        try:
            data = response.json()
            return [m.get("name") or m.get("model", "") for m in data.get("models", [])]
        except (ValueError, AttributeError, TypeError) as exc:
            raise OllamaResponseError("Ollama returned an unreadable model list.") from exc

    def check_ready(self) -> None:
        """Raise an OllamaError if Ollama is unreachable or the model is missing."""
        installed = self.list_models()
        if not any(_same_model(self.model, name) for name in installed):
            raise self._missing_model_error()

    def chat(self, messages: list[dict[str, str]], json_schema: dict[str, Any] | None = None) -> str:
        """Send a conversation to the model and return its reply text.

        Args:
            messages: [{"role": "system"|"user"|"assistant", "content": "..."}]
            json_schema: if given, Ollama forces the reply to match this schema.
        """
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": self.temperature},
        }
        if json_schema is not None:
            payload["format"] = json_schema
        if self.think is not None:
            payload["think"] = self.think

        try:
            response = requests.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=(self._connect_timeout(), self.timeout),
            )
        except requests.exceptions.ConnectTimeout as exc:
            # On Windows a closed port can time out instead of refusing the
            # connection. Either way it means Ollama is not reachable.
            raise self._connection_error() from exc
        except requests.exceptions.Timeout as exc:
            raise OllamaTimeoutError(
                f"The model did not answer within {self.timeout:.0f} seconds. "
                "The first request can be slow while the model loads; please try again."
            ) from exc
        except requests.exceptions.RequestException as exc:
            raise self._connection_error() from exc

        if response.status_code == 404:
            raise self._missing_model_error()
        if response.status_code != 200:
            detail = ""
            try:
                detail = response.json().get("error", "")
            except ValueError:
                detail = response.text[:200]
            if "not found" in detail.lower() and "model" in detail.lower():
                raise self._missing_model_error()
            raise OllamaResponseError(f"Ollama returned HTTP {response.status_code}: {detail}".strip())

        try:
            data = response.json()
            content = data["message"]["content"]
        except (ValueError, KeyError, TypeError) as exc:
            raise OllamaResponseError("Ollama returned a response in an unexpected format.") from exc
        if not isinstance(content, str):
            raise OllamaResponseError("Ollama returned a non-text reply.")
        return content
