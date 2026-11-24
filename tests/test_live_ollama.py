"""OPTIONAL tests against the REAL model. Skipped unless you enable them:

    PowerShell:  $env:FSA_LIVE = "1"; python -m pytest -m live -v
    Windows CMD: set FSA_LIVE=1 && python -m pytest -m live -v

They need Ollama running and the configured model installed. Because a
language model is not 100% deterministic across versions, a failure here
means "improve the prompt / try again", not necessarily a code bug.
"""

import os

import pytest

from fs_assistant.config import Settings
from fs_assistant.interpreter import Interpreter
from fs_assistant.ollama_client import OllamaClient, OllamaError

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(os.environ.get("FSA_LIVE") != "1", reason="set FSA_LIVE=1 to run live model tests"),
]


@pytest.fixture(scope="module")
def interpreter():
    s = Settings.from_env()
    client = OllamaClient(s.ollama_url, s.model, s.timeout_seconds, s.temperature, s.think)
    try:
        client.check_ready()
    except OllamaError as exc:
        pytest.skip(str(exc))
    return Interpreter(client)


@pytest.mark.parametrize("sentence, action, path", [
    ("Make a folder called projects", "create_directory", "projects"),
    ("I'd like a new directory named photos please", "create_directory", "photos"),
    ("Create a file called main.py", "create_file", "main.py"),
    ("put a file named app.js in the projects folder", "create_file", "projects/app.js"),
    ("what's in here?", "list_directory", "."),
    ("How many files are inside the current folder?", "count_files", "."),
    ("rename notes.txt to ideas.txt", "rename_file", "notes.txt"),
    ("please remove old.log", "delete_file", "old.log"),
])
def test_model_understands_phrasings(interpreter, sentence, action, path):
    interpreter.reset()
    result = interpreter.interpret(sentence)
    assert result.action == action
    assert result.path.strip("./") == path.strip("./")


def test_model_asks_for_missing_name(interpreter):
    interpreter.reset()
    assert interpreter.interpret("create a file").action == "clarify"
