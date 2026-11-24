# Phase 7: Presentation Guide

Suggested length: 12–15 minutes, then questions. Each member presents their
own layer.

## 1. Slide plan

| # | Slide | Presenter | Key message |
|---|---|---|---|
| 1 | Title and team | M3 | AI File System Assistant: Python + Ollama + Qwen 3.5 4B |
| 2 | Problem and objective | M3 | Terminal file commands are hard for beginners. Let people type plain English instead, safely and offline. |
| 3 | Live demo, part 1 | M3 | Create, list, count, rename, delete (with confirmation) |
| 4 | Architecture diagram | M3 | CLI → Interpreter → Ollama/Qwen → validation → Executor → file_ops → disk |
| 5 | What is Ollama? What is Qwen? | M2 | A local model server plus a 4-billion-parameter open model. No internet or API key, and data never leaves the laptop. |
| 6 | Natural language → JSON | M2 | System prompt, JSON schema, `debug on` demo, retry, clarification |
| 7 | Model evaluation | M2 | 20 phrasings: accuracy and speed, before and after prompt tuning |
| 8 | Safety layers | M1 | Fixed action list, validation, sandbox, no shell, confirmations |
| 9 | Attack demo | M1 | `../`, `C:\Windows`, "run del /s" all blocked |
| 10 | Testing | M1 | 134 automated tests, a fake Ollama server, and live tests |
| 11 | Limitations and future work | M2 | Small-model mistakes, one action per request, speed on CPU |
| 12 | Conclusion | M3 | What we learned |

## 2. Explaining the project simply

**Objective:** a terminal assistant that understands requests like "make a
folder called photos" and really does them. It uses an AI model that runs on
our own computer.

**The three roles:**

- **Qwen 3.5 4B (the brain).** A language model trained on large amounts of
  text. It's good at understanding *what someone means*. We ask it to
  translate a sentence into a small JSON instruction. It never touches files.
- **Ollama (the engine).** A program that loads the model into memory and
  offers it through a local web address (`http://localhost:11434`). Any
  program can send it a question over HTTP and get the answer back.
- **Python (the hands and the security guard).** It reads what you type, asks
  Ollama, checks the JSON very strictly, and then creates or changes the files
  itself using safe library functions.

**How Python talks to Ollama:** the `requests` library sends an HTTP POST to
`/api/chat`. The body contains:

- the model name
- the conversation (our instructions + examples + the user's sentence)
- a **JSON schema** in the `format` field, which forces Ollama to answer in our format
- `temperature: 0`, for consistent answers
- `think: false`, so the model answers directly without writing out its reasoning

Ollama answers with JSON, and the model's reply is in `message.content`.

**From sentence to action:**

```
"could you make me a folder named photos?"
   ↓ Qwen (guided by the prompt + schema)
{"action": "create_directory", "path": "photos"}
   ↓ validate_action()  → known action? path is text? not too long?
Action(action="create_directory", path="photos")
   ↓ workspace.resolve("photos") → C:\...\workspace\photos (inside the sandbox? yes)
   ↓ Path.mkdir()
"Directory 'photos' created successfully."
```

## 3. Why structured outputs (JSON)?

- **Predictable.** The program knows exactly which fields to read. Free text
  like "Sure! I'll create that folder for you!" can't be processed reliably.
- **Checkable.** We can verify every field before doing anything.
- **Safe.** The model can only *choose* from 8 actions. It can't invent a new
  command, and the model's text is never executed.
- **Testable.** We can simulate the model by returning fixed JSON in tests.
- **Enforced.** Ollama's `format` parameter makes the model generate JSON that
  matches our schema, so malformed answers are rare. If one happens anyway,
  we retry once.

## 4. Safety mechanisms (8 layers)

1. **A fixed list of actions.** Anything not in `ALLOWED_ACTIONS` is rejected.
2. **Type and length validation** of every field (`validate_action`).
3. **No shell.** All work is done with Python's `pathlib`. There is no `os.system`, `subprocess`, or `eval` anywhere in the code.
4. **The workspace sandbox.** `..`, absolute paths (`C:\`, `/`, `~`), symlinks that escape, invalid characters, and Windows reserved names are all blocked. The final path is checked with `is_relative_to(workspace)`.
5. **Delete only after `yes`.** Any other answer, including Ctrl+C, means no.
6. **No silent overwrite.** Creating or renaming onto an existing file asks first.
7. **Folders are never deleted,** and the workspace itself can't be renamed or deleted.
8. **Graceful errors.** Every expected error becomes a friendly message, and a final safety net keeps the session alive.

## 5. Demo script (about 5 minutes)

Preparation:

1. Restart the laptop. Start Ollama.
2. Run `ollama run qwen3.5:4b "hi"` once, so the model is already loaded and the first answer isn't slow.
3. Delete the `workspace` folder.
4. Increase the terminal font size.
5. Have the backup video ready.

```
python main.py
> Create a folder called projects
> Create a file called main.py
> How many files are in this directory?
> List all the files
> put a file called app.py inside projects          (nested path)
> could you count all files, including subfolders?   (recursive count, different phrasing)
> change the name of main.py to start.py             (rename)
> debug on                                           (show the JSON)
> get rid of start.py   → no   → then again → yes     (confirmation)
> create a file                                      (clarification) → notes.txt
> create a file called ../../hack.txt                 (sandbox)
> what's the weather like?                           (unsupported)
> exit
```

To show the error handling, quit Ollama from the tray icon, type `list files`,
restart Ollama, and type it again.

## 6. Limitations to mention honestly

- A 4B model sometimes picks the wrong action or path for unusual sentences. Debug mode, validation, and confirmations limit the impact.
- It's slow on CPU-only laptops, especially the first request.
- One action per request. There are no batch operations ("delete all .txt files"), no moving between folders, and no deleting folders. These are deliberate safety choices.
- No memory beyond the current clarification. "Delete the file I just created" may not work.
- Model output isn't 100% deterministic across Ollama or model versions.

**Future work:**

- a `cd` command (current folder)
- an undo action
- batch operations with a preview
- reading file contents
- an optional GUI on top of the same modules

## 7. Questions the professor might ask

**Q1. Why run the model locally instead of using ChatGPT or an API?**
It's free, works offline, needs no API key, and the user's file names never
leave the computer. It also shows that we understand how to deploy a model,
not just call a cloud service.

**Q2. Why Qwen 3.5 4B?**
It's an open (Apache 2.0) model that is officially in the Ollama library as
`qwen3.5:4b`, and at 3.3 GB it runs on normal student laptops. It also
supports structured output. A bigger model would be more accurate but too
slow without a GPU, and a smaller one makes more mistakes.

**Q3. What happens if the model returns something dangerous, like `rm -rf /`?**
Nothing. The model can only output JSON with one of 8 action names.
"run_command" or "rm" isn't an allowed action, so validation rejects it.
Even a valid action with the path `../../Windows` is blocked by the sandbox.
And we never execute text as a command.

**Q4. How do you prevent path traversal?**
`Workspace.resolve()` rejects absolute paths and `..` parts, then builds the
full path, resolves it (which also follows symlinks), and checks that it is
still inside the workspace with `is_relative_to`. We have tests for each attack.

**Q5. How do you know the model is really used and not just keyword matching?**
The Python code contains no keyword rules. We show different phrasings that
produce the same JSON in debug mode, and our evaluation script measures
accuracy over 20 phrasings. If you stop Ollama, the app can't do anything.

**Q6. What is a JSON schema and why does Ollama need it?**
It's a description of the allowed JSON shape: field names, types, and the list
of allowed actions. Ollama uses it to constrain the model's output while it's
being generated, so the reply is always parseable.

**Q7. What's temperature, and why 0?**
Temperature controls randomness. At 0 the model always picks its most likely
answer, which makes behavior more predictable and testable.

**Q8. What if Ollama crashes during a request?**
`ollama_client.py` turns connection, timeout, and HTTP errors into friendly
messages. The CLI prints them and keeps running, so the user can retry once
Ollama is back.

**Q9. How did you test without the model?**
We built a fake Ollama server (`tests/fake_ollama.py`) that speaks the same
HTTP API. That tests our real HTTP code, the whole application, and the error
cases (server down, model missing, garbage output) quickly and repeatably.
Separate live tests use the real model.

**Q10. How did you divide the work?**
By layer:

- Member 1 built the filesystem and security layer.
- Member 2 built the AI integration.
- Member 3 built the CLI, the executor, and the integration.

We agreed on a shared contract (`actions.py`) first, so everyone could work in
parallel. Then we merged through GitHub pull requests.

**Q11. What would you improve with more time?**
A `cd` command, undo, batch operations with a preview, and fine-tuning or a
larger model for better accuracy.

**Q12. What is "thinking mode", and why turn it off?**
Qwen 3.5 can write out its reasoning before it answers. That's useful for hard
problems, but for a short JSON reply it only adds time, so we send
`think: false`.

**Q13. Is the app deterministic?**
The Python part is. The model part is mostly consistent at temperature 0, but
it isn't guaranteed. That's why we validate everything and ask for
confirmation before risky actions.
