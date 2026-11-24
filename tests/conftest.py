"""Shared pytest fixtures."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make "fs_assistant" and "tests.fake_ollama" importable when running `pytest`
# from the project folder.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fs_assistant.file_ops import FileSystemOperations  # noqa: E402
from fs_assistant.workspace import Workspace  # noqa: E402


@pytest.fixture
def workspace(tmp_path: Path) -> Workspace:
    """A fresh, empty workspace folder for every test."""
    ws = Workspace(tmp_path / "workspace")
    ws.ensure_exists()
    return ws


@pytest.fixture
def ops(workspace: Workspace) -> FileSystemOperations:
    return FileSystemOperations(workspace)


class ScriptedConfirm:
    """Fake confirmation function: returns the given answer and records questions."""

    def __init__(self, answer: bool):
        self.answer = answer
        self.questions: list[str] = []

    def __call__(self, question: str) -> bool:
        self.questions.append(question)
        return self.answer


@pytest.fixture
def say_yes() -> ScriptedConfirm:
    return ScriptedConfirm(True)


@pytest.fixture
def say_no() -> ScriptedConfirm:
    return ScriptedConfirm(False)
