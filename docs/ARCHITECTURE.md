# Phase 2: Architecture

## 1. The idea in one sentence

**The model decides *what* to do. Python decides *whether* it's allowed and
*how* to do it.**

## 2. Diagram

```
 ┌──────────────────────────── YOUR COMPUTER ─────────────────────────────┐
 │                                                                        │
 │  User types:  "put a file called app.py in projects"                   │
 │        │                                                               │
 │        ▼                                                               │
 │  ┌──────────────┐   text    ┌────────────────┐  HTTP POST /api/chat    │
 │  │   cli.py     │ ────────► │ interpreter.py │ ──────────────────────┐ │
 │  │ (terminal UI)│           │ + prompts.py   │                       │ │
 │  └──────▲───────┘           └───────┬────────┘   ┌─────────────────┐ │ │
 │         │                           │            │     OLLAMA      │◄┘ │
 │         │                           │◄───────────│  (local server, │   │
 │         │                           │  JSON text │   port 11434)   │   │
 │         │                           │            │   runs Qwen 3.5 │   │
 │         │                    actions.py          │   4B model      │   │
 │         │                  validate_action()     └─────────────────┘   │
 │         │                           │ Action object                    │
 │         │                           ▼                                  │
 │         │                   ┌───────────────┐  "Are you sure?"         │
 │         │   ActionResult    │  executor.py  │ ─────► (asks via cli)    │
 │         └───────────────────│ safety gate   │                          │
 │                             └───────┬───────┘                          │
 │                                     ▼                                  │
 │                             ┌───────────────┐   ┌───────────────────┐  │
 │                             │  file_ops.py  │──►│  workspace.py     │  │
 │                             │ pathlib only  │   │ path sandbox      │  │
 │                             └───────┬───────┘   └───────────────────┘  │
 │                                     ▼                                  │
 │                             ./workspace/projects/app.py  (real file)   │
 └────────────────────────────────────────────────────────────────────────┘
```

## 3. Modules and owners

| Module | Purpose | Depends on | Owner |
|---|---|---|---|
| `config.py` | All settings in one place | none | shared |
| `actions.py` | Allowed actions, JSON schema, `validate_action()`, `Action`, `ActionResult` | config | shared |
| `workspace.py` | Turns a relative path into a safe absolute path, or raises `WorkspaceError` | none | Member 1 |
| `file_ops.py` | create, list, count, rename, and delete with `pathlib` | workspace, actions | Member 1 |
| `ollama_client.py` | HTTP calls to Ollama, with clear errors | `requests` | Member 2 |
| `prompts.py` | System prompt with examples | none | Member 2 |
| `interpreter.py` | text → model → parse JSON → validate → `Action`. Handles retries and clarifications. | client, prompts, actions | Member 2 |
| `executor.py` | Runs an `Action` with `FileSystemOperations`. Asks for confirmation before delete or overwrite. | file_ops, actions | Member 3 |
| `cli.py` | Banner, input loop, built-in commands, printing, saving history | interpreter, executor, client, database | Member 3 |
| `database.py` | SQLite history: one row per request (`assistant.db`), queried with `queries.sql` | `sqlite3` (built in) | Member 1 |
| `main.py` | Reads options, wires everything together, starts the app | all | Member 3 |

## 4. Shared interfaces (the contract)

Agree on these before writing other code. Changing them later needs agreement
from all three members.

### 4.1 Action JSON (model → Python)

```json
{"action": "create_file",      "path": "projects/main.py", "content": "optional text"}
{"action": "create_directory", "path": "projects"}
{"action": "list_directory",   "path": "."}
{"action": "count_files",      "path": ".", "recursive": false}
{"action": "rename_file",      "path": "notes.txt", "new_name": "ideas.txt"}
{"action": "delete_file",      "path": "old.log"}
{"action": "clarify",          "question": "What should the new file be called?"}
{"action": "unsupported",      "message": "I can only work with files and folders."}
```

**Path rules:**

- Paths are always relative to the workspace and use `/`.
- `"."` means the workspace itself.
- `count_files` counts files only (not folders). `recursive: false` means the top level only, and `true` includes all sub-folders.

### 4.2 Python interfaces

```python
# actions.py
@dataclass
class Action:            action: str; path=".", new_name="", content="", recursive=False, question="", message=""
@dataclass
class ActionResult:      success: bool; message: str; details: list[str] = []
def validate_action(data: dict) -> Action          # raises ActionValidationError / MissingFieldError

# workspace.py
class Workspace:
    def __init__(self, root)                         # root folder
    def ensure_exists(self) -> None
    def resolve(self, user_path: str, allow_root=True) -> Path   # raises WorkspaceError
    def relative(self, path: Path) -> str
    @staticmethod
    def validate_name(name: str) -> None

# file_ops.py   (every method returns ActionResult or raises a FileOperationError subclass)
class FileSystemOperations:
    def __init__(self, workspace: Workspace)
    def file_exists(self, user_path) -> bool
    def create_file(self, user_path, content="", overwrite=False) -> ActionResult  # AlreadyExistsError
    def create_directory(self, user_path) -> ActionResult
    def list_directory(self, user_path=".") -> ActionResult    # details = ["folder/", "file.txt"]
    def count_files(self, user_path=".", recursive=False) -> ActionResult
    def rename_file(self, user_path, new_name, overwrite=False) -> ActionResult
    def delete_file(self, user_path) -> ActionResult           # never deletes folders

# ollama_client.py
class OllamaClient:
    def __init__(self, base_url, model, timeout=180, temperature=0.0, think=False)
    def list_models(self) -> list[str]
    def check_ready(self) -> None                    # OllamaConnectionError / ModelNotFoundError
    def chat(self, messages: list[dict], json_schema: dict | None = None) -> str

# interpreter.py
class Interpreter:
    def __init__(self, client, max_retries=1)
    def interpret(self, user_text: str) -> Action    # InterpretationError / OllamaError
    def reset(self) -> None

# executor.py
class Executor:
    def __init__(self, file_ops: FileSystemOperations)
    def execute(self, action: Action, confirm: Callable[[str], bool]) -> ActionResult  # never raises

# cli.py
class AssistantCLI:
    def __init__(self, settings, client, interpreter, executor, input_fn=input, output_fn=print)
    def run(self) -> None
    def handle(self, text: str) -> bool              # False means exit
```

### 4.3 Error rules

| Layer | Raises | Caught by |
|---|---|---|
| workspace | `WorkspaceError` | file_ops (re-raised as `FileOperationError`) |
| file_ops | `FileOperationError` (`PathNotFoundError`, `AlreadyExistsError`, `WrongTypeError`) | executor → `ActionResult(False, msg)` |
| ollama_client | `OllamaError` (`OllamaConnectionError`, `ModelNotFoundError`, `OllamaTimeoutError`, `OllamaResponseError`) | cli |
| interpreter | `InterpretationError` | cli |
| anything unexpected | `Exception` | `cli.run()` safety net. The session never crashes. |

Every error message is written for the end user, so the CLI can print it as it is.

## 5. One request, step by step

1. `cli.py` reads `put a file called app.py in projects`.
2. `interpreter.py` builds the messages
   `[system prompt with examples, user text]` and calls `OllamaClient.chat()`
   with `ACTION_JSON_SCHEMA`.
3. `ollama_client.py` sends this POST to `http://localhost:11434/api/chat`:
   ```json
   {"model": "qwen3.5:4b", "messages": [...], "stream": false,
    "format": {...schema...}, "think": false, "options": {"temperature": 0}}
   ```
4. Ollama runs Qwen 3.5 4B and returns
   `{"message": {"content": "{\"action\":\"create_file\",\"path\":\"projects/app.py\"}"}}`.
5. `parse_model_json()` turns the text into a dict. `validate_action()` checks it
   and returns `Action(action="create_file", path="projects/app.py")`.
6. `executor.py` calls `file_ops.create_file("projects/app.py")`.
7. `workspace.resolve()` returns `C:\...\workspace\projects\app.py` after
   checking that the path is inside the workspace.
8. `pathlib` creates the folder and the file.
   The result is `ActionResult(True, "File 'projects/app.py' created successfully. (Folder 'projects' was created for it.)")`.
9. `cli.py` prints `Assistant: File 'projects/app.py' created ...`.

## 6. Why these design choices?

- **Plain JSON with a fixed list of actions**, not shell commands. The model can
  only *choose* from 8 safe operations. Anything else is rejected by validation.
- **`pathlib` instead of `os.system` or `subprocess`.** There's no shell
  involved, so nothing can be injected into one.
- **Dependency injection.** The CLI receives `input_fn` and `output_fn`, and the
  executor receives a `confirm` function. That's what makes every part testable
  without a keyboard or a real model.
- **A fake Ollama server in the tests.** It tests the real HTTP code without
  downloading 3.3 GB, so the tests run in seconds on any computer.
- **Only one third-party package (`requests`).** Python's built-in `urllib`
  could do the job too, but `requests` is easier for beginners to read.
