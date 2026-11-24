# AI File System Assistant

A terminal (CLI) application that lets you manage files and folders by typing
plain English. A local language model, **Qwen 3.5 4B** running in **Ollama**,
reads the request and turns it into a structured JSON action. **Python** checks
that action and carries it out safely inside a sandbox folder.

```
========================================
     AI FILE SYSTEM ASSISTANT
========================================
AI Model: Qwen 3.5 4B (qwen3.5:4b)
Runtime: Ollama
Language: Python

Workspace: workspace
Type 'help' for examples or 'exit' to quit.

What would you like me to do?
> Create a folder called projects

(thinking...)
Assistant: Directory 'projects' created successfully.

> Create a file called main.py

(thinking...)
Assistant: File 'main.py' created successfully.

> How many files are in this directory?

(thinking...)
Assistant: There is 1 file in the workspace (not counting sub-folders).

> exit

Goodbye!
```

## Features

| Feature | Example request |
|---|---|
| Create a file | `Create a file called main.py` |
| Create a file with text in it | `Make readme.md containing Hello world` |
| Create a file in a folder (the folder is created if it doesn't exist) | `Put app.py inside the projects folder` |
| Create a folder | `Make a new directory named photos` |
| List contents | `What's in projects?` |
| Count files | `How many files are here?` counts only the top level. `...including subfolders` counts recursively. |
| Rename a file | `Change the name of notes.txt to ideas.txt` |
| Delete a file | `Remove old.log`. The app always asks you to confirm first. |
| Clarification | `Create a file` → *"What should the new file be called?"* → `notes.txt` |
| Built-in commands | `help`, `debug on` / `debug off` (shows the model's JSON), `exit` / `quit` |

**Where files go:** by default the assistant works in **your user folder** (for example `C:\Users\MALAK`), so it can create real files you can see on your **Desktop**, in **Documents**, **Downloads** and so on. Say "on my desktop" or "in documents". It finds the real Desktop even when Windows keeps it inside OneDrive.

| Example | Result |
|---|---|
| `make a folder m on my desktop with files a and b` | `Desktop\m\a` and `Desktop\m\b` |
| `put notes.txt in documents` | `Documents\notes.txt` |
| `what's on my desktop?` | lists your Desktop |

**Safety rules:**

- The app can only change things inside your user folder. `C:\Windows`, other drives, `..`, the hidden `AppData` settings folder, symlinks that point outside, and Windows reserved names are all blocked.
- It never runs shell commands.
- Deleting a file and overwriting an existing file always need a `yes` from you.
- It only deletes files. It never deletes folders.

---

## 1. Requirements

| What | Why | Version |
|---|---|---|
| Python | Runs the application | 3.10 or newer (tested on 3.10 and 3.13) |
| Ollama | Runs the language model locally | latest from ollama.com |
| `qwen3.5:4b` model | Understands the requests | 3.3 GB download |
| `requests` (pip) | Lets Python send HTTP requests to Ollama | ≥ 2.31 |
| `pytest` (pip, only for development) | Runs the automated tests | ≥ 8.0 |
| `matplotlib` (pip, only for charts) | Draws the database queries as charts | ≥ 3.8 |

**Hardware:**

- About **4 GB free disk** for the model.
- **8 GB RAM** as a practical minimum, **16 GB recommended**.
- No GPU needed. A GPU makes answers much faster.

## 2. Installation on Windows (every team member does this once)

Open **PowerShell** (or the VS Code terminal).

```powershell
# 2.1  Python: install from https://www.python.org/downloads/ (tick "Add python.exe to PATH")
py --version                      # should print Python 3.10+  (or: python --version)

# 2.2  Ollama: download and run the installer from https://ollama.com/download
#      (or: winget install Ollama.Ollama). After installing, Ollama runs in the background.
ollama --version

# 2.3  Download the model (3.3 GB, one time per computer)
ollama pull qwen3.5:4b
ollama list                       # qwen3.5:4b must appear in the list
ollama run qwen3.5:4b "Say hello" # quick test. Exits after answering.

# 2.4  Get the project (see docs/TEAM_PLAN.md for the Git workflow)
git clone https://github.com/<your-team>/ai-file-assistant.git
cd ai-file-assistant

# 2.5  Create and activate a virtual environment
py -m venv .venv
.venv\Scripts\Activate.ps1        # CMD: .venv\Scripts\activate.bat
#   If PowerShell says "running scripts is disabled", run once:
#   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned

# 2.6  Install the Python dependencies
pip install -r requirements-dev.txt
```

On macOS or Linux, use `python3 -m venv .venv` and `source .venv/bin/activate`.

## 3. Running the application

```powershell
python main.py                      # normal use
python main.py --debug              # also shows the JSON action the model chose
python main.py --workspace demo     # limit it to one sandbox folder (safer for testing)
python main.py --model qwen3.5:2b   # try another installed model
```

You can also set the same options with environment variables: `FSA_MODEL`,
`FSA_OLLAMA_URL`, `FSA_WORKSPACE`, `FSA_TIMEOUT`, `FSA_THINK`, `FSA_DEBUG`.
For example, in PowerShell: `$env:FSA_MODEL = "qwen3.5:2b"`.

## 4. Chats, database and Telegram (new)

- **Saved chats, like ChatGPT.** Type `chats` to list your chats, `open 3` to continue chat 3, and `new` to start a new one. The AI sees the earlier messages of the chat.
- **Relational database.** It has 4 tables linked with primary and foreign keys (`users`, `conversations`, `messages`, `actions`). See [docs/DATABASE.md](docs/DATABASE.md) and `fs_assistant/schema.sql`.
- **Drawn.** `python scripts/draw_erd.py` draws the database diagram. `python scripts/draw_charts.py` draws the query results.
- **Telegram + terminal together.** `python main.py` runs the terminal chat and the Telegram bot at the same time (once `.env` has a bot token). Setup is in [docs/TELEGRAM.md](docs/TELEGRAM.md). Use `--no-telegram` for the terminal only, or `--telegram` for the bot only.
- **Internet search.** Type `/search <question>`, in the terminal or on Telegram. It searches DuckDuckGo (or Wikipedia as a backup), and the local AI writes a short answer with numbered sources. Web pages can never trigger file actions.

## 4b. The database file (SQLite)

Every chat is saved in a **SQLite** database, the file `assistant.db` in the folder you start the app from. SQLite is built into Python, so there's nothing extra to install.

- Type `history` in the app to see the messages of the current chat.
- `python main.py --no-history` turns saving off. `--db other.db` uses another file.

**Running SQL queries in VS Code:**

1. Install the VS Code extension **SQLite** (by *alexcvzz*): Extensions panel (Ctrl+Shift+X), search "SQLite", and install.
2. Run the app once so that `assistant.db` exists.
3. Press **Ctrl+Shift+P**, type **SQLite: Open Database**, and choose `assistant.db`.
4. Open `queries.sql`. It has 12 ready-made queries: success rate, failed requests, files created on the Desktop, average AI response time, and more.
5. Highlight one query, right-click, and choose **Run Selected Query**. The result appears as a table.
6. Optional: browse the tables in the **SQLITE EXPLORER** section at the bottom of the Explorer side bar.

**Seeing the queries drawn as charts:**

```powershell
python scripts/draw_charts.py
```

You can also type `charts` inside the assistant. This runs 4 SQL queries and saves PNG images in the `charts` folder. Click them in VS Code to view them:

- `1_requests_per_action.png`: bar chart, `SELECT action, COUNT(*) ... GROUP BY action`
- `2_success_rate.png`: succeeded vs failed
- `3_response_time.png`: average AI response time per action
- `4_requests_per_day.png`: activity per day
- `dashboard.png`: all four charts on one page, good for a slide

Each image shows the SQL query that produced it. This needs `matplotlib`, which is installed by `pip install -r requirements-dev.txt`.

The table structure is documented at the top of `fs_assistant/database.py`. All inserts use `?` placeholders, so text you type can't change the SQL (protection against SQL injection).

## 5. Running the tests

```powershell
python -m pytest                    # all automatic tests. No Ollama needed (uses a fake server).
python -m pytest -v tests/test_workspace.py   # just one file

# Optional: tests against the REAL model (Ollama must be running)
$env:FSA_LIVE = "1"; python -m pytest -m live -v
python scripts/evaluate_model.py    # accuracy report over 20 different phrasings
```

## 6. Project structure

```
ai-file-assistant/
├── main.py                  # entry point: reads options, connects all modules, starts the CLI
├── requirements.txt         # runtime dependency (requests)
├── requirements-dev.txt     # + pytest
├── pytest.ini               # test settings
├── fs_assistant/
│   ├── config.py            # all settings (model name, URL, workspace, limits)
│   ├── actions.py           # SHARED CONTRACT: allowed actions, JSON schema, validation
│   ├── workspace.py         # sandbox: converts paths to safe absolute paths
│   ├── file_ops.py          # the real file/folder operations (pathlib only)
│   ├── ollama_client.py     # HTTP communication with Ollama
│   ├── prompts.py           # system prompt + examples for the model
│   ├── interpreter.py       # text -> model -> JSON -> validated Action
│   ├── executor.py          # runs an Action, asks for confirmations
│   ├── database.py          # SQLite history of every request (assistant.db)
│   ├── charts.py            # turns query results into charts
│   └── cli.py               # banner, input loop, printing results
├── queries.sql              # example SQL queries to run in VS Code
├── scripts/draw_charts.py   # draws the queries as charts (PNG) in charts/
├── scripts/evaluate_model.py
├── tests/                   # unit + integration tests, plus a fake Ollama server
└── docs/                    # setup, architecture, team plan, testing, presentation
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for how these parts fit together.

## 7. Troubleshooting

| Message / problem | Cause | Fix |
|---|---|---|
| `Cannot connect to Ollama at http://localhost:11434` | Ollama isn't running | Open the Ollama app from the Start menu, or run `ollama serve` in another terminal. |
| `The model 'qwen3.5:4b' is not installed` | Model not downloaded | `ollama pull qwen3.5:4b`, then `ollama list` |
| `ollama` is not recognized as a command | PATH wasn't refreshed after install | Close and reopen the terminal or VS Code. Reinstall Ollama if it still fails. |
| Pull or run fails with an "unsupported / unknown architecture" or "requires a newer version" message | Ollama is too old for Qwen 3.5 | Install the latest Ollama from ollama.com. |
| `The model did not answer within 180 seconds` | The first request loads the model, and CPUs are slow | Try again. Close other apps or raise the timeout: `$env:FSA_TIMEOUT = "300"`. |
| `python` opens the Microsoft Store | Windows app alias | Use `py` instead, or turn off the alias under *Settings → Apps → App execution aliases*. |
| `running scripts is disabled on this system` | PowerShell policy | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| `ModuleNotFoundError: requests` | venv not active, or dependencies not installed | `.venv\Scripts\Activate.ps1`, then `pip install -r requirements-dev.txt` |
| `ModuleNotFoundError: fs_assistant` | Started from the wrong folder | `cd` into the project folder, then run `python main.py`. |
| The model picks the wrong action | Small models make mistakes | Rephrase the request. Use `debug on` to see the JSON. Add an example to `fs_assistant/prompts.py`. |
| `SQLite: Open Database` is missing in VS Code | The extension isn't installed or enabled | Install "SQLite" by alexcvzz, then reload VS Code. |
| No `assistant.db` file | The app hasn't saved anything yet | Run `python main.py` and make at least one request. |
| `Permission denied` | File is open in another program | Close the file (for example in Excel or Word) and try again. |

## 8. Documentation

- [docs/MODEL_SETUP.md](docs/MODEL_SETUP.md): Phase 1, model verification, hardware, and limitations
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): Phase 2, design, data flow, and interfaces
- [docs/TEAM_PLAN.md](docs/TEAM_PLAN.md): Phases 3–4, work division and Git workflow
- [docs/TESTING.md](docs/TESTING.md): Phase 6, integration checklist and manual test cases
- [docs/PRESENTATION.md](docs/PRESENTATION.md): Phase 7, demo plan and likely questions with answers
