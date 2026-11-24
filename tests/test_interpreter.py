"""Tests for natural language -> Action conversion, with a scripted fake model."""

import pytest

from fs_assistant.interpreter import InterpretationError, Interpreter, parse_model_json
from fs_assistant.actions import ActionValidationError
from fs_assistant.ollama_client import OllamaConnectionError


class ScriptedClient:
    """Stands in for OllamaClient: returns pre-written replies in order."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []   # list of message lists sent to the "model"

    def chat(self, messages, json_schema=None):
        self.calls.append([dict(m) for m in messages])
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


# ---- parse_model_json --------------------------------------------------------
def test_parse_plain_json():
    assert parse_model_json('{"action": "list_directory"}') == {"action": "list_directory"}


def test_parse_json_in_code_fence():
    assert parse_model_json('```json\n{"action": "count_files"}\n```') == {"action": "count_files"}


def test_parse_json_with_extra_text():
    text = 'Sure! Here it is: {"action": "create_file", "path": "a.txt"} Hope this helps.'
    assert parse_model_json(text)["path"] == "a.txt"


@pytest.mark.parametrize("bad", ["", "   ", "I will create the file now.", "{broken json", "[1, 2]"])
def test_parse_rejects_non_json(bad):
    with pytest.raises(ActionValidationError):
        parse_model_json(bad)


# ---- Interpreter -------------------------------------------------------------
def test_interpret_valid_reply():
    client = ScriptedClient(['{"action": "create_directory", "path": "projects"}'])
    action = Interpreter(client).interpret("Make a folder called projects")
    assert action.action == "create_directory"
    assert action.path == "projects"
    assert client.calls[0][0]["role"] == "system"
    assert client.calls[0][-1] == {"role": "user", "content": "Make a folder called projects"}


def test_malformed_reply_is_retried_once_then_succeeds():
    client = ScriptedClient(["not json at all", '{"action": "list_directory", "path": "."}'])
    action = Interpreter(client).interpret("list files")
    assert action.action == "list_directory"
    assert len(client.calls) == 2
    assert "not valid" in client.calls[1][-1]["content"]   # correction message sent


def test_unknown_action_is_retried():
    client = ScriptedClient(['{"action": "run_shell", "path": "rm -rf /"}',
                             '{"action": "unsupported", "message": "No."}'])
    assert Interpreter(client).interpret("delete everything with rm").action == "unsupported"


def test_two_bad_replies_raise_interpretation_error():
    client = ScriptedClient(["nope", "still nope"])
    with pytest.raises(InterpretationError):
        Interpreter(client).interpret("do something")


def test_missing_field_becomes_clarification():
    client = ScriptedClient(['{"action": "create_file", "path": ""}'])
    action = Interpreter(client).interpret("create a file")
    assert action.action == "clarify"
    assert action.question == "What should the new file be called?"


def test_clarification_context_is_sent_with_next_request():
    client = ScriptedClient([
        '{"action": "clarify", "question": "What should the new file be called?"}',
        '{"action": "create_file", "path": "notes.txt"}',
    ])
    interpreter = Interpreter(client)
    assert interpreter.interpret("create a file").action == "clarify"
    action = interpreter.interpret("notes.txt")
    assert action.path == "notes.txt"
    second_call = client.calls[1]
    contents = [m["content"] for m in second_call]
    assert "create a file" in contents                  # original request remembered
    assert any("What should the new file be called?" in c for c in contents)


def test_context_is_cleared_after_a_real_action():
    client = ScriptedClient([
        '{"action": "clarify", "question": "Which file?"}',
        '{"action": "delete_file", "path": "a.txt"}',
        '{"action": "list_directory", "path": "."}',
    ])
    interpreter = Interpreter(client)
    interpreter.interpret("delete it")
    interpreter.interpret("a.txt")
    interpreter.interpret("list files")
    assert len(client.calls[2]) == 2          # only system prompt + new request


def test_ollama_errors_are_passed_to_the_cli():
    client = ScriptedClient([OllamaConnectionError("down")])
    with pytest.raises(OllamaConnectionError):
        Interpreter(client).interpret("list files")
