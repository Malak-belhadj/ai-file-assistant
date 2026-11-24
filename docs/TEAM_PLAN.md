# Phases 3–4: Team Plan and Collaboration

## 0. How the work was divided

The application has three natural layers:

- the **disk** (paths and file operations)
- the **AI** (talking to the model)
- the **user-facing application** (the terminal and running actions)

Each member owns one layer from start to finish: code, tests, Windows testing,
and the matching part of the presentation. The shared contract
(`actions.py` + `config.py`) is created **together** on day 1.

| | Member 1: Filesystem & Security | Member 2: AI Integration | Member 3: Application & Integration Lead |
|---|---|---|---|
| Source files | `workspace.py`, `file_ops.py`, `schema.sql`, `database.py`, `queries.sql`, `erd.py`, `charts.py` | `ollama_client.py`, `prompts.py`, `interpreter.py`, `service.py` (chat context), `scripts/evaluate_model.py` | `executor.py`, `cli.py`, `telegram_bot.py`, `main.py` |
| Tests | `test_workspace.py`, `test_file_ops.py`, `test_database.py` | `fake_ollama.py`, `test_ollama_client.py`, `test_interpreter.py`, `test_live_ollama.py` | `test_executor.py`, `test_integration.py` |
| Docs | Security section of PRESENTATION | MODEL_SETUP, AI section | README, TESTING, final merge |
| Hardest part | Path-traversal edge cases on Windows | Prompt tuning with the real model | Confirmations, error flow, integration |
| Lines (source + tests) | ~320 + ~340 | ~420 + ~330 | ~330 + ~260, plus README and integration |

Shared (all three, at the kick-off meeting): `config.py`, `actions.py`,
`__init__.py`, `requirements*.txt`, `pytest.ini`, `.gitignore`,
`tests/conftest.py`, `tests/__init__.py`, `tests/test_actions.py`.

**How we use the provided code:** the complete reference implementation is in
this repository. Each member builds their own files *in their own branch*,
reads every line, makes sure they can explain it, runs the tests, and does the
"own work" tasks (real-model testing, Windows testing, prompt tuning,
documentation). Your professor will ask each of you about your part, so
**understanding beats copying**.

---

## 1. One-time setup

### 1.1 Every member, on their own computer

1. Install **Python 3.10+** from python.org (tick *Add python.exe to PATH*), then run `py --version`.
2. Install **Git** from git-scm.com (accept the defaults), then run `git --version`.
3. Tell Git who you are (once per computer):
   ```powershell
   git config --global user.name "Your Name"
   git config --global user.email "you@university.edu"
   ```
4. Create a free **GitHub** account and send your username to Member 3.
5. Install **Ollama** and pull the model (see `docs/MODEL_SETUP.md`):
   ```powershell
   ollama pull qwen3.5:4b
   ollama list
   ```
6. Install **VS Code** with the *Python* extension (recommended).

### 1.2 Only once for the whole team (Member 3 does this)

1. On github.com, click **New repository**. Name it `ai-file-assistant` and make it **Private**. Tick *Add a README*.
2. Go to **Settings → Collaborators → Add people** and add Members 1 and 2.
3. Optional: go to **Settings → Branches → Add rule** for `main` and tick *Require a pull request before merging*.
4. Clone the repository, add the shared contract files, and push:
   ```powershell
   git clone https://github.com/<user>/ai-file-assistant.git
   cd ai-file-assistant
   # create the shared files listed above (copy from the reference implementation)
   git add .
   git commit -m "Add shared contract: config, actions, test setup"
   git push origin main
   ```

### 1.3 Every member, after the repository exists

```powershell
git clone https://github.com/<user>/ai-file-assistant.git
cd ai-file-assistant
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
python -m pytest tests/test_actions.py     # the contract tests must pass on everyone's machine
```

---

## 2. Git workflow for beginners

**Branches:** `main` always works. Each member works on their own branch:

| Member | Branch |
|---|---|
| 1 | `feature/filesystem` |
| 2 | `feature/ai` |
| 3 | `feature/cli` |

**Daily cycle:**

```powershell
git checkout main
git pull                                   # get the newest main
git checkout -b feature/filesystem         # FIRST time only (later: git checkout feature/filesystem)
git merge main                             # bring merged work from teammates into your branch
# ... edit files ...
python -m pytest                           # tests must pass before committing
git status                                 # see what changed
git add fs_assistant/workspace.py tests/test_workspace.py
git commit -m "Block absolute Windows paths in workspace.resolve"
git push -u origin feature/filesystem      # -u only the first time
```

**When your part is ready:**

1. On GitHub, go to **Pull requests → New** and choose your branch → `main`.
2. Another member reviews it, runs your branch locally, and clicks **Approve**:
   ```powershell
   git fetch
   git checkout feature/filesystem
   python -m pytest
   ```
3. Click **Merge**. Then everyone runs `git checkout main` and `git pull`.

**Rules that prevent conflicts:**

- Only edit files you own. If you need a change in someone else's file, ask them, or open an issue.
- `actions.py` and `config.py` change only after all three agree. The person making the change announces it in the group chat.
- Commit small and often, with clear messages.
- Never commit `.venv/` or `workspace/`. The `.gitignore` already excludes them.
- If you get a merge conflict:
  1. Open the file in VS Code and pick *Accept Current / Incoming / Both*.
  2. Run the tests.
  3. Run `git add <file>`, then `git commit`.

**Merge order:**

1. Shared contract (day 1)
2. `feature/filesystem`
3. `feature/ai`
4. `feature/cli`

Member 3's executor uses Member 1's `file_ops`. Member 3 can still develop in
parallel by working on `cli.py` first and testing it with fake objects
(`ScriptedConfirm` and `FakeOllama`).

**Suggested timeline:**

| Day / week | Milestone |
|---|---|
| 1 | Kick-off: everyone does the setup, reads ARCHITECTURE.md, and creates the shared files together |
| 1–4 | Parallel development in branches. Each member's own tests pass. |
| 5 | Merge M1, then M2. Full test suite on `main`. |
| 6 | Merge M3. Integration session with all three on one Windows laptop (TESTING.md checklist). |
| 7 | Fix issues, tune the prompt, rehearse the presentation |

---

## 3. Member 1: Filesystem & Security Engineer

### 3.1 Objective and responsibilities

Make every file operation **correct** and **impossible to abuse**. You own the
sandbox that stops the AI (or the user) from touching anything outside
`./workspace`.

### 3.2 Files

| Create | Do not modify |
|---|---|
| `fs_assistant/workspace.py`, `fs_assistant/file_ops.py`, `tests/test_workspace.py`, `tests/test_file_ops.py` | `actions.py`, `config.py` |

### 3.3 Steps

1. `git checkout -b feature/filesystem`
2. Create `workspace.py`:
   1. Define `WorkspaceError`, `INVALID_CHARS`, `RESERVED_NAMES`.
   2. Implement `Workspace.__init__` (store `Path(root).resolve()`) and `ensure_exists()`.
   3. Implement `validate_name()`. It rejects empty names, `..`, the characters `<>:"|?*`, control characters, trailing dots or spaces, and reserved names such as `CON` and `NUL`.
   4. Implement `resolve()`:
      1. Normalize `\` to `/` and strip `./`.
      2. Reject absolute paths (`/`, `~`, `C:`).
      3. Validate each part.
      4. Join with `root` and call `.resolve()`.
      5. Check `is_relative_to(root)`.
   5. Implement `relative()`.
3. Write `tests/test_workspace.py` and run `python -m pytest tests/test_workspace.py -v`.
4. Create `file_ops.py`:
   1. Define the exceptions: `FileOperationError`, `PathNotFoundError`, `AlreadyExistsError(message, path, is_file)`, `WrongTypeError`.
   2. Implement `create_file`. Remember: no overwrite unless `overwrite=True`. Create missing parent folders and mention that in the message.
   3. Implement `create_directory` (duplicates are an error).
   4. Implement `list_directory`: folders first, a trailing `/` on folders, and a summary line.
   5. Implement `count_files`: count files only. The message must say whether the count is recursive.
   6. Implement `rename_file`: same-folder rename, overwrite protection, and the destination must stay inside the workspace.
   7. Implement `delete_file`: files only, never folders.
5. Write `tests/test_file_ops.py` with at least one success test and one failure test per operation.
5b. Create `database.py`: a `history` table created with `CREATE TABLE IF NOT EXISTS`, plus `record()`, `recent()`, `count()` and `stats()`, always using `?` placeholders. Write `queries.sql` with the example queries and `tests/test_database.py`. Demo the queries in VS Code with the SQLite extension.
6. **Own work:**
   1. Run all your tests **on Windows**.
   2. Try to break the sandbox by hand in a Python shell: `py`, then `from fs_assistant.workspace import Workspace; w=Workspace("workspace"); w.resolve("..\\..\\Windows")`.
   3. Write down every attack you tried for the presentation.
7. Push your branch and open a pull request. Member 3 reviews it.

### 3.4 Deliverables and functionality

- Safe path resolution.
- All six operations, with exact messages:
  - `"File 'x' created successfully."`
  - `"Directory 'x' created successfully."`
  - `"There is 1 file in the workspace (not counting sub-folders)."`
  - …
- At least 60 passing tests.

### 3.5 Interfaces you must follow

See `ARCHITECTURE.md` §4.2. Every method returns `ActionResult` or raises a
`FileOperationError` subclass. **Never** call `print()` or `input()` in your
modules: the executor and the CLI handle all communication with the user.

### 3.6 Coordination

- Member 3's `executor.py` relies on:
  - `AlreadyExistsError.path` and `.is_file`
  - `file_exists()`
  - the `overwrite=` parameters
- Tell Member 3 if any message text changes. The integration tests check exact messages.

### 3.7 Tests and done criteria

```powershell
python -m pytest tests/test_workspace.py tests/test_file_ops.py -v
```

You're done when:

- 0 tests fail on Windows. The symlink test is skipped on Windows, which is expected.
- No traversal attempt you tried escapes the workspace.

### 3.8 Hand-over

- Merged PR.
- A list of the attacks you tested. Member 3 will put it into TESTING.md.
- 2–3 slides on security.

### 3.9 Integration procedure

After merging, run:

```powershell
git checkout main
git pull
python -m pytest
```

Then tell Member 3 that `feature/filesystem` is merged.

---

## 4. Member 2: AI Integration Engineer

### 4.1 Objective and responsibilities

Turn natural language into a **valid JSON action** using Qwen 3.5 4B through
Ollama, and make the app survive every Ollama failure. You are the team
expert on the model: prompt quality, accuracy, speed, and limitations.

### 4.2 Files

| Create | Do not modify |
|---|---|
| `fs_assistant/ollama_client.py`, `fs_assistant/prompts.py`, `fs_assistant/interpreter.py`, `scripts/evaluate_model.py`, `tests/fake_ollama.py`, `tests/test_ollama_client.py`, `tests/test_interpreter.py`, `tests/test_live_ollama.py` | `actions.py` (agree on any change) |

### 4.3 Steps

1. `git checkout -b feature/ai`
2. Explore Ollama by hand first:
   ```powershell
   ollama run qwen3.5:4b "Reply only with JSON: {\"action\": ...} for: make a folder called test"
   Invoke-RestMethod http://localhost:11434/api/tags
   ```
3. Create `ollama_client.py`:
   1. Define the exception classes.
   2. Implement `list_models()`, which calls `GET /api/tags`.
   3. Implement `check_ready()`. It compares names, treating `name` and `name:latest` as the same model.
   4. Implement `chat()`:
      1. Send a POST to `/api/chat` with `model`, `messages`, `stream: false`, `format`, `think`, and `options.temperature`.
      2. Translate failures: connection error → `OllamaConnectionError`, 404 → `ModelNotFoundError`, timeout → `OllamaTimeoutError`, any other non-200 or bad JSON → `OllamaResponseError`.
4. Create `tests/fake_ollama.py`, a small `http.server` that imitates Ollama. Then write `tests/test_ollama_client.py`.
5. Create `prompts.py`: a short system prompt, the rules, and 14 examples (one or two per action).
6. Create `interpreter.py`:
   1. `parse_model_json()`: strip code fences and extract the `{...}` part.
   2. `Interpreter.interpret()`: messages, then `chat`, then parse, then `validate_action`. Retry once with `CORRECTION_PROMPT`. A `MissingFieldError` becomes a `clarify` action.
   3. Clarification memory: `_pending` keeps the last question and answer so that the user's next reply is understood in context.
7. Write `tests/test_interpreter.py` using a `ScriptedClient` (a fake model with fixed replies).
8. Create `scripts/evaluate_model.py` with at least 20 phrasings.
9. **Own work (the most important part):**
   1. Run `python scripts/evaluate_model.py` with the real model.
   2. For every FAIL, add or adjust an example in `prompts.py` and run it again.
   3. Record the accuracy and the average time per request before and after your changes. This is strong presentation material.
   4. Run `$env:FSA_LIVE="1"; python -m pytest -m live -v`.
10. Push your branch and open a pull request. Member 1 reviews it.

### 4.4 Deliverables and functionality

- A working Ollama connection with friendly errors.
- An interpreter with retry and clarification.
- An evaluation report: a table of the 20 sentences with the accuracy and the average time per request.

### 4.5 Interfaces

- `OllamaClient.chat(messages, json_schema) -> str`
- `Interpreter.interpret(text) -> Action`
- Raise only `OllamaError` subclasses or `InterpretationError`, and make every message understandable to the end user.
- Don't print anything. Return or raise instead.

### 4.6 Coordination

- You use `ACTION_JSON_SCHEMA` and `validate_action` from `actions.py`.
- Member 3's CLI catches your exceptions, so keep the class names exactly as specified.
- If you add a new action to the prompt, all three members must update the contract together.

### 4.7 Tests and done criteria

```powershell
python -m pytest tests/test_ollama_client.py tests/test_interpreter.py -v
python scripts/evaluate_model.py
```

You're done when:

- All non-live tests pass.
- The app reports clearly when Ollama is stopped. Test this: quit Ollama from the tray icon.
- The evaluation script gets at least 85% of sentences right (aim for 100%).

### 4.8 Hand-over

- Merged PR.
- The evaluation results, before and after prompt tuning.
- A short note on how long the first and later requests take on your laptop.
- 2–3 slides on Ollama and Qwen.

### 4.9 Integration procedure

Merge after Member 1. Then run `python -m pytest` on `main`, plus one live run:

```powershell
python -c "from fs_assistant.ollama_client import OllamaClient as C; print(C('http://localhost:11434','qwen3.5:4b').chat([{'role':'user','content':'hi'}]))"
```

---

## 5. Member 3: Application & Integration Lead

### 5.1 Objective and responsibilities

Build what the user sees and the safety gate that runs actions:

- the terminal loop
- confirmations
- error display
- wiring the modules together in `main.py`

You also own the repository, the README, and the final integration.

### 5.2 Files

| Create | Do not modify |
|---|---|
| `fs_assistant/executor.py`, `fs_assistant/cli.py`, `main.py`, `tests/test_executor.py`, `tests/test_integration.py`, `README.md`, `docs/TESTING.md` | other members' modules |

### 5.3 Steps

1. Create the GitHub repository and push the shared files (§1.2).
2. `git checkout -b feature/cli`
3. Create `executor.py`:
   1. A dispatch table mapping each action name to a handler method (never `eval` or `getattr` on model text).
   2. `_create_file`: on `AlreadyExistsError`, ask `confirm(...)` and then retry with `overwrite=True`.
   3. `_delete_file`: check `file_exists()` first, **always** ask `confirm(...)`, and delete only if the answer is yes.
   4. `_rename_file`: confirm before replacing an existing file.
   5. `_clarify` and `_unsupported` handlers.
   6. `execute()` catches `FileOperationError`, `PermissionError`, and `OSError`, and turns them into `ActionResult(False, ...)`.
4. Write `tests/test_executor.py` with a fake `confirm`: `ScriptedConfirm` in `conftest.py`.
5. Create `cli.py`:
   1. Banner, `help` text, exit commands, and `debug on/off`.
   2. `check_ollama()` at startup. It warns but doesn't exit.
   3. `confirm()`: only `y` or `yes` counts as yes. Ctrl+C or EOF counts as no.
   4. `handle()`: interpreter, then executor, then print. Catch `OllamaError` and `InterpretationError`.
   5. `run()`: the loop. A final `except Exception` safety net, and `Goodbye!` on exit.
6. Create `main.py`: `argparse` flags, `build_settings()`, `build_app()`, `main()`.
7. Write `tests/test_integration.py`. Run the whole app with scripted input against `FakeOllama`.
8. **Own work:**
   1. Write the README.
   2. Run the integration checklist in `TESTING.md` with the real model on Windows Terminal, PowerShell, and the VS Code terminal.
   3. Record a backup demo video.
9. Open a pull request. Member 2 reviews it. Merge last.

### 5.4 Deliverables and functionality

- A running application (`python main.py`) with all features working end to end.
- The README.
- The integration test report.

### 5.5 Interfaces

- `Executor.execute(action, confirm) -> ActionResult` never raises an exception.
- `AssistantCLI(settings, client, interpreter, executor, input_fn, output_fn)`.
- `main.build_app(settings, input_fn, output_fn)` is used by the tests.

### 5.6 Coordination

- You depend on Member 1's exceptions and messages and on Member 2's exceptions.
- Until their branches are merged, test against the reference files or against fakes.
- You schedule the integration session.

### 5.7 Tests and done criteria

```powershell
python -m pytest -v
```

You're done when:

- The whole suite passes on `main`.
- Every item in the TESTING.md checklist is ticked on a Windows machine with the real model.

### 5.8 Hand-over

- The final `main` branch.
- The README and TESTING report.
- The demo script and the backup video.
- 2–3 slides: introduction, architecture, and the live demo.

### 5.9 Integration procedure

See `docs/TESTING.md` §1.
