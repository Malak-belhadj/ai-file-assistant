"""Measure how well the real model understands different phrasings.

This does NOT touch any files: it only asks the model to interpret each
sentence and compares the chosen action/path with the expected one.

Run (with Ollama running and the model installed):
    python scripts/evaluate_model.py
    python scripts/evaluate_model.py --model qwen3.5:2b

Use the printed accuracy table in your report/presentation to show that the
application really relies on the language model (many phrasings, one action).
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fs_assistant.config import Settings  # noqa: E402
from fs_assistant.interpreter import InterpretationError, Interpreter  # noqa: E402
from fs_assistant.ollama_client import OllamaClient, OllamaError  # noqa: E402

# (user sentence, expected action, expected path or None to skip the path check)
CASES = [
    ("Create a folder called projects", "create_directory", "projects"),
    ("make a new directory named photos", "create_directory", "photos"),
    ("I need a folder for my music, call it music", "create_directory", "music"),
    ("Create a file called main.py", "create_file", "main.py"),
    ("please make an empty text file notes.txt", "create_file", "notes.txt"),
    ("put a file named app.js in the projects folder", "create_file", "projects/app.js"),
    ("inside src create utils.py", "create_file", "src/utils.py"),
    ("List all the files", "list_directory", "."),
    ("what's in this folder?", "list_directory", "."),
    ("show me what is inside projects", "list_directory", "projects"),
    ("How many files are in this directory?", "count_files", "."),
    ("count the files in projects", "count_files", "projects"),
    ("how many files are there in total, including subfolders?", "count_files", "."),
    ("Rename main.py to app.py", "rename_file", "main.py"),
    ("change the name of notes.txt to todo.txt", "rename_file", "notes.txt"),
    ("Delete notes.txt", "delete_file", "notes.txt"),
    ("get rid of the file old.log", "delete_file", "old.log"),
    ("Create a file", "clarify", None),
    ("rename the file", "clarify", None),
    ("What's the weather today?", "unsupported", None),
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", help="Ollama model to evaluate")
    args = parser.parse_args()

    settings = Settings.from_env()
    if args.model:
        settings.model = args.model
    client = OllamaClient(settings.ollama_url, settings.model, settings.timeout_seconds,
                          settings.temperature, settings.think)
    try:
        client.check_ready()
    except OllamaError as exc:
        print(f"Cannot evaluate: {exc}")
        return 1

    print(f"Evaluating model '{settings.model}' on {len(CASES)} sentences...\n")
    passed = 0
    total_time = 0.0
    for sentence, expected_action, expected_path in CASES:
        interpreter = Interpreter(client)        # fresh: no clarification memory
        start = time.perf_counter()
        try:
            action = interpreter.interpret(sentence)
            got = action.to_dict()
        except (InterpretationError, OllamaError) as exc:
            got = {"error": str(exc)}
        elapsed = time.perf_counter() - start
        total_time += elapsed

        ok = got.get("action") == expected_action
        if ok and expected_path is not None:
            ok = got.get("path", "").strip("./") == expected_path.strip("./")
        passed += ok
        mark = "PASS" if ok else "FAIL"
        print(f"[{mark}] ({elapsed:4.1f}s) {sentence!r}\n        -> {got}")

    print(f"\nResult: {passed}/{len(CASES)} correct "
          f"({100 * passed / len(CASES):.0f}%), average {total_time / len(CASES):.1f}s per request.")
    return 0 if passed == len(CASES) else 2


if __name__ == "__main__":
    sys.exit(main())
