"""Integration tests: the WHOLE application (CLI -> Interpreter -> real HTTP
client -> fake Ollama server -> Executor -> real files), driven by a
scripted user. Only the language model itself is simulated.
"""

import json
from pathlib import Path

from fs_assistant.config import Settings
from main import build_app, build_settings
from tests.fake_ollama import FakeOllama, unused_url

# What the fake "model" answers for each user sentence.
MODEL_ANSWERS = {
    "Create a folder called projects": {"action": "create_directory", "path": "projects"},
    "Create a file called main.py": {"action": "create_file", "path": "main.py"},
    "How many files are in this directory?": {"action": "count_files", "path": ".", "recursive": False},
    "List all the files": {"action": "list_directory", "path": "."},
    "put app.py in projects": {"action": "create_file", "path": "projects/app.py"},
    "rename main.py to start.py": {"action": "rename_file", "path": "main.py", "new_name": "start.py"},
    "delete start.py": {"action": "delete_file", "path": "start.py"},
    "make a file": {"action": "clarify", "question": "What should the new file be called?"},
    "todo.txt": {"action": "create_file", "path": "todo.txt"},
    "write to ../../outside.txt": {"action": "create_file", "path": "../../outside.txt"},
    "use the shell": {"action": "run_command", "command": "del /s *"},
    "what is 2+2": {"action": "unsupported", "message": "I can only manage files."},
    "create a folder m with files a and b": {"action": "create_directory", "path": "m", "files": ["a", "b"]},
}


def fake_model(user_text: str) -> str:
    answer = MODEL_ANSWERS.get(user_text)
    if answer is None:          # e.g. a correction request after a bad answer
        return '{"action": "unsupported", "message": "Not a file request."}'
    return json.dumps(answer)


def run_session(url, workspace, lines, model="qwen3.5:4b"):
    """Run the app with scripted input; return everything it printed."""
    inputs = iter(lines)
    output = []
    settings = Settings(model=model, ollama_url=url, workspace=workspace, timeout_seconds=5,
                        db_path=Path(workspace).parent / "history.db")

    def fake_input(prompt):
        output.append(prompt)
        try:
            return next(inputs)
        except StopIteration:
            raise EOFError

    app = build_app(settings, input_fn=fake_input, output_fn=output.append)
    app.run()
    return "\n".join(output)


def test_example_session_from_the_brief(tmp_path):
    ws = tmp_path / "workspace"
    with FakeOllama(fake_model) as fake:
        out = run_session(fake.url, ws, [
            "Create a folder called projects",
            "Create a file called main.py",
            "How many files are in this directory?",
            "List all the files",
            "exit",
        ])
    assert "AI FILE SYSTEM ASSISTANT" in out
    assert "Directory 'projects' created successfully." in out
    assert "File 'main.py' created successfully." in out
    assert "There is 1 file in the workspace (not counting sub-folders)." in out
    assert "main.py" in out and "projects/" in out
    assert out.rstrip().endswith("Goodbye!")
    assert (ws / "projects").is_dir() and (ws / "main.py").is_file()


def test_full_feature_walkthrough(tmp_path):
    ws = tmp_path / "workspace"
    with FakeOllama(fake_model) as fake:
        out = run_session(fake.url, ws, [
            "Create a folder called projects",
            "put app.py in projects",
            "Create a file called main.py",
            "rename main.py to start.py",
            "delete start.py", "no",           # cancelled
            "delete start.py", "yes",          # confirmed
            "make a file", "todo.txt",         # clarification round
            "quit",
        ])
    assert "File 'projects/app.py' created successfully." in out
    assert "renamed to 'start.py'" in out
    assert "Cancelled. 'start.py' was not deleted." in out
    assert "File 'start.py' deleted successfully." in out
    assert "What should the new file be called?" in out
    assert "File 'todo.txt' created successfully." in out
    assert sorted(p.name for p in ws.iterdir()) == ["projects", "todo.txt"]
    # The clarification answer was sent to the model together with the question.
    last_messages = [m["content"] for m in fake.requests[-1]["messages"]]
    assert "make a file" in last_messages and "todo.txt" in last_messages


def test_unsafe_model_output_never_touches_disk(tmp_path):
    ws = tmp_path / "workspace"
    with FakeOllama(fake_model) as fake:
        out = run_session(fake.url, ws, [
            "write to ../../outside.txt",
            "use the shell",
            "what is 2+2",
            "exit",
        ])
    assert "outside the workspace" in out
    assert "I can only manage files." in out
    assert not (tmp_path / "outside.txt").exists()
    assert list(ws.iterdir()) == []


def test_ollama_not_running_does_not_crash(tmp_path):
    out = run_session(unused_url(), tmp_path / "ws", ["list files", "exit"])
    assert "Warning: Cannot connect to Ollama" in out
    assert "AI model unavailable" in out
    assert "Goodbye!" in out


def test_model_not_installed_message(tmp_path):
    with FakeOllama(fake_model, models=["something-else:1b"]) as fake:
        out = run_session(fake.url, tmp_path / "ws", ["List all the files", "exit"])
    assert "ollama pull qwen3.5:4b" in out
    assert "Goodbye!" in out


def test_malformed_model_output_is_handled(tmp_path):
    with FakeOllama(lambda text: "Sure, I created the folder for you!") as fake:
        out = run_session(fake.url, tmp_path / "ws", ["Create a folder called x", "exit"])
    assert "could not understand" in out
    assert len(fake.requests) == 2              # first try + one retry
    assert not (tmp_path / "ws" / "x").exists()


def test_help_debug_and_empty_input_do_not_call_the_model(tmp_path):
    with FakeOllama(fake_model) as fake:
        out = run_session(fake.url, tmp_path / "ws", ["", "help", "debug on", "List all the files", "exit"])
    assert "Other commands" in out
    assert '[debug] model action: {"action": "list_directory", "path": "."}' in out
    assert len(fake.requests) == 1


def test_ctrl_c_style_end_of_input_exits_cleanly(tmp_path):
    with FakeOllama(fake_model) as fake:
        out = run_session(fake.url, tmp_path / "ws", [])     # immediate EOF
    assert "Goodbye!" in out


def test_command_line_flags(monkeypatch):
    monkeypatch.delenv("FSA_MODEL", raising=False)
    settings, args = build_settings(["--model", "qwen3.5:2b", "--workspace", "sandbox",
                                     "--url", "http://127.0.0.1:9999/", "--debug", "--telegram"])
    assert args.telegram is True
    assert settings.model == "qwen3.5:2b"
    assert str(settings.workspace) == "sandbox"
    assert settings.ollama_url == "http://127.0.0.1:9999"
    assert settings.debug is True
    assert build_settings([])[0].model == "qwen3.5:4b"


def test_folder_with_files_in_one_request(tmp_path):
    ws = tmp_path / "workspace"
    with FakeOllama(fake_model) as fake:
        out = run_session(fake.url, ws, ["create a folder m with files a and b", "exit"])
    assert "Folder 'm' is ready with 2 new file(s)." in out
    assert "File 'm/a' created successfully." in out
    assert sorted(p.name for p in (ws / "m").iterdir()) == ["a", "b"]
