# Phase 6: Integration and Testing

## Verification status

| What | Status |
|---|---|
| Automatic test suite (134 tests) on **Linux**, Python 3.10.20 and 3.13 | **Passed**. Run by the assistant that generated the code. |
| Full app (`python main.py`) driven through the fake Ollama server | **Passed** on Linux |
| Tests on **Windows** | **Not yet verified.** Your team must run them. |
| Tests with the **real Qwen 3.5 4B** model (live tests, evaluation script, manual cases below) | **Not yet verified.** The model couldn't be downloaded in the environment that generated the code. |

Fill in the "Result" columns below yourselves. Don't report a result you
haven't seen.

---

## 1. Integration procedure (Member 3 leads; all three attend)

1. Merge in this order: shared contract → `feature/filesystem` → `feature/ai` → `feature/cli`. After each merge:
   ```powershell
   git checkout main
   git pull
   python -m pytest
   ```
   Fix any failure before the next merge.
2. On one Windows laptop:
   1. Make sure Ollama is running: `ollama list` shows `qwen3.5:4b`.
   2. Activate the venv.
   3. Run `pip install -r requirements-dev.txt`.
3. Run `python -m pytest`. Expected: all tests pass, with live tests skipped and the symlink test skipped on Windows.
4. Run `$env:FSA_LIVE = "1"; python -m pytest -m live -v`, then `python scripts/evaluate_model.py`. Record the results.
5. Delete the `workspace` folder so you start clean, then run `python main.py --debug` and go through §3 below.
6. Repeat a short run in **Windows Terminal**, **PowerShell**, and the **VS Code terminal**.
7. Tag the working version:
   ```powershell
   git tag v1.0
   git push --tags
   ```

## 2. Integration checklist

| # | Check | How | Result |
|---|---|---|---|
| 1 | CLI ↔ AI module | Any request shows `(thinking...)` and then an answer. `debug on` shows the JSON. | |
| 2 | AI module ↔ filesystem | `create a folder called demo` creates a real `workspace\demo` (check in File Explorer) | |
| 3 | Connection to Ollama and the model | Banner with no warning. `ollama ps` shows `qwen3.5:4b` loaded after the first request. | |
| 4 | Structured responses | `debug on` → every answer is a valid JSON action | |
| 5 | All operations work | Test cases T1–T12 below | |
| 6 | Invalid paths blocked | T13–T15 | |
| 7 | Errors and ambiguity | T16–T22 | |
| 8 | Windows | Steps 3–6 above, done on Windows | |
| 9 | Startup, loop, exit | Many requests in a row; `exit`, `quit`, and Ctrl+C all end with `Goodbye!` | |

## 3. Manual test cases (real model)

Start with an empty workspace: `python main.py --debug`

| # | Type this | Expected result | Result |
|---|---|---|---|
| T1 | `Create a folder called projects` | `Directory 'projects' created successfully.` | |
| T2 | `Create a file called main.py` | `File 'main.py' created successfully.` | |
| T3 | `How many files are in this directory?` | `There is 1 file in the workspace (not counting sub-folders).` | |
| T4 | `List all the files` | `projects/` and `main.py` | |
| T5 | `add a file called app.py inside projects` | `File 'projects/app.py' created successfully.` | |
| T6 | `make notes.txt in a new folder called docs` | `File 'docs/notes.txt' created successfully. (Folder 'docs' was created for it.)` | |
| T7 | `count every file including the ones in subfolders` | `There are 3 files in the workspace (including sub-folders).` | |
| T8 | `what's inside projects?` | `app.py` | |
| T9 | `rename main.py to start.py` | `File 'main.py' renamed to 'start.py' successfully.` | |
| T10 | `create readme.md with the text Hello team` | File created. Open it: it contains `Hello team`. | |
| T11 | `delete start.py`, then answer `no` | `Cancelled. 'start.py' was not deleted.` and the file still exists | |
| T12 | `please get rid of start.py`, then answer `yes` | `File 'start.py' deleted successfully.` | |
| T13 | `create a file at ../outside.txt` | Error about the path. (The model may also remove the `..` itself and create `outside.txt` inside the workspace.) In both cases, nothing is created outside the workspace. | |
| T14 | `make a file C:\Windows\test.txt` | `Absolute paths ... are not allowed`, or the model drops the drive and the file is created inside the workspace. Never in `C:\Windows`. | |
| T15 | `run the command del /s *` | `unsupported` reply. Nothing is executed. | |
| T16 | `create a file` | `What should the new file be called?`. Then type `todo.txt`, and it's created. | |
| T17 | `rename it` | A clarifying question | |
| T18 | `delete ghost.txt` | `The file 'ghost.txt' does not exist.` (no confirmation asked) | |
| T19 | `create a folder called projects` (again) | `A folder named 'projects' already exists.` | |
| T20 | `create a file called readme.md` (exists), answer `no` | Asks to overwrite, then `Cancelled` | |
| T21 | `what's the capital of France?` | Polite "I can only work with files" reply | |
| T22 | Quit Ollama (tray icon → Quit), then type `list files` | `AI model unavailable: Cannot connect to Ollama ...`. The app keeps running. | |
| T23 | Start Ollama again, then type `list files` | Works again without restarting the app | |
| T24 | `python main.py --model notinstalled:1b` | Warning: `... ollama pull notinstalled:1b` | |
| T25 | `exit` | `Goodbye!` | |

## 4. Proving the model is really used (natural-language variations)

All of the following should give the **same** action. Use `debug on` to show the JSON.

| Intended action | Phrasings to try |
|---|---|
| `create_directory projects` | "Create a folder called projects" · "make a new directory named projects" · "I need a projects folder" · "mkdir projects please" |
| `count_files .` | "How many files are in this directory?" · "count the files here" · "what's the number of files in the current folder?" |
| `delete_file a.txt` | "delete a.txt" · "remove a.txt" · "get rid of a.txt" · "erase the file a.txt" |
| `list_directory .` | "list all the files" · "what's in here?" · "show me the folder contents" · "ls" |

There is **no** keyword matching anywhere in the Python code. Search the code
for `"delete"` or `"remove"` and you won't find any rule that maps them to
actions. Only the model makes that decision.

`python scripts/evaluate_model.py` runs 20 such sentences automatically and
prints the accuracy.

## 5. Common errors while integrating

| Problem | Fix |
|---|---|
| `ImportError: cannot import name 'X' from fs_assistant.Y` | A member renamed something in the contract. Compare with ARCHITECTURE.md §4.2. |
| Integration tests fail on exact messages | `file_ops` message text changed. Update the tests and the messages together. |
| Merge conflict in `actions.py` | Resolve it together on a call. Keep both additions and re-run all tests. |
| `pytest` finds 0 tests | Run it from the project root (the folder that has `pytest.ini`). |
| Tests hang on `test_timeout_is_reported` | A firewall prompt is blocking local ports. Allow Python on private networks. |
| Live tests fail on 1–2 sentences | That's model behavior, not a crash. Improve the examples in `prompts.py` and rerun. |
