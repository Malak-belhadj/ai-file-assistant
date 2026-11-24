"""Tests for the HTTP client, using the fake Ollama server (no real model needed)."""

import pytest

from fs_assistant.actions import ACTION_JSON_SCHEMA
from fs_assistant.ollama_client import (
    ModelNotFoundError,
    OllamaClient,
    OllamaConnectionError,
    OllamaResponseError,
    OllamaTimeoutError,
)
from tests.fake_ollama import FakeOllama, unused_url

MODEL = "qwen3.5:4b"


def test_chat_returns_model_text_and_sends_correct_payload():
    with FakeOllama(lambda text: '{"action": "list_directory", "path": "."}') as fake:
        client = OllamaClient(fake.url, MODEL, timeout=5)
        reply = client.chat([{"role": "user", "content": "list"}], json_schema=ACTION_JSON_SCHEMA)
    assert reply == '{"action": "list_directory", "path": "."}'
    sent = fake.requests[0]
    assert sent["model"] == MODEL
    assert sent["stream"] is False
    assert sent["format"] == ACTION_JSON_SCHEMA
    assert sent["think"] is False
    assert sent["options"]["temperature"] == 0.0


def test_check_ready_succeeds_when_model_installed():
    with FakeOllama(lambda t: "{}", models=["qwen3.5:4b", "llama3:latest"]) as fake:
        OllamaClient(fake.url, MODEL).check_ready()
        OllamaClient(fake.url, "llama3").check_ready()   # ':latest' is implied


def test_check_ready_reports_missing_model_with_pull_command():
    with FakeOllama(lambda t: "{}", models=["other:1b"]) as fake:
        with pytest.raises(ModelNotFoundError) as info:
            OllamaClient(fake.url, MODEL).check_ready()
    assert "ollama pull qwen3.5:4b" in str(info.value)


def test_chat_with_missing_model_raises_model_not_found():
    with FakeOllama(lambda t: "{}", models=[]) as fake:
        with pytest.raises(ModelNotFoundError):
            OllamaClient(fake.url, MODEL).chat([{"role": "user", "content": "hi"}])


def test_ollama_not_running():
    client = OllamaClient(unused_url(), MODEL, timeout=2)
    with pytest.raises(OllamaConnectionError) as info:
        client.check_ready()
    assert "ollama serve" in str(info.value)
    with pytest.raises(OllamaConnectionError):
        client.chat([{"role": "user", "content": "hi"}])


def test_server_error_is_reported():
    with FakeOllama(lambda t: "{}", chat_status=500) as fake:
        with pytest.raises(OllamaResponseError) as info:
            OllamaClient(fake.url, MODEL).chat([{"role": "user", "content": "hi"}])
    assert "500" in str(info.value)


def test_timeout_is_reported():
    import time

    def slow(_text):
        time.sleep(1.5)
        return "{}"

    with FakeOllama(slow) as fake:
        with pytest.raises(OllamaTimeoutError):
            OllamaClient(fake.url, MODEL, timeout=0.5).chat([{"role": "user", "content": "hi"}])
