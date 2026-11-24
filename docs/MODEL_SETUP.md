# Phase 1: Model Verification and Setup

*Checked on 27 October 2026 against the Ollama model library and Ollama's own announcement.*

## 1. Does "Qwen 3.5 4B" exist in Ollama?

**Yes.** The exact Ollama identifier is:

```
qwen3.5:4b
```

| Property | Value (from ollama.com/library/qwen3.5:4b) |
|---|---|
| Parameters | 4.21 B (language model) + 334 M vision projector |
| Quantization | Q4_K_M (language model), BF16 (projector) |
| Download size | **3.3 GB** (2.6 GB model + 676 MB projector) |
| Capabilities | tools, thinking, vision |
| License | Apache 2.0 |
| Default sampling | temperature 1, top_p 0.95, top_k 20, presence_penalty 1.5 (our app overrides temperature to 0) |
| Other sizes in the family | `0.8b`, `2b`, `9b`, `27b`, `35b`, `122b` |

Ollama announced the small Qwen 3.5 models with the commands
`ollama run qwen3.5:9b / 4b / 2b / 0.8b`. It said that all of them support
tool calling, thinking, and multimodal input.

**Not verified:**

- **Minimum Ollama version.** The library page doesn't state one. Install the latest Ollama. If a pull or run fails with an architecture or version error, update Ollama.
- **Context window and exact RAM use** for the 4B tag. The library page doesn't list them, and secondary sources disagree. Check the real memory use with `ollama ps` while the model is loaded.

## 2. Commands

### Install Ollama (Windows)

1. Download **OllamaSetup.exe** from <https://ollama.com/download> and run it.
   Or, in PowerShell: `winget install Ollama.Ollama`.
2. Ollama starts automatically in the background. You'll see a llama icon in the system tray.
3. Check it:

```powershell
ollama --version
```

### Download and test the model

```powershell
ollama pull qwen3.5:4b          # downloads 3.3 GB, once per computer
ollama list                     # must show qwen3.5:4b
ollama run qwen3.5:4b           # interactive chat. Type /bye to leave.
ollama ps                       # while the model is loaded: shows memory use and CPU/GPU split
```

### Check the HTTP API that Python will use

PowerShell:

```powershell
Invoke-RestMethod http://localhost:11434/api/tags      # lists installed models
```

If you see `Unable to connect`, Ollama isn't running. Start the Ollama app, or run
`ollama serve` in a separate terminal and leave it open.

## 3. Hardware

| | Minimum (works) | Recommended |
|---|---|---|
| RAM | 8 GB | 16 GB |
| Free disk | 4 GB | 10 GB |
| CPU | Any 64-bit CPU from the last 6–7 years | 4+ cores |
| GPU | Not required | NVIDIA or AMD GPU with ≥ 4 GB VRAM, for faster answers |
| OS | Windows 10/11, macOS, Linux | |

On CPU only, expect the **first** request to take noticeably longer while the
model loads into memory. Later requests are faster. These are estimates: measure
your own laptops with `python scripts/evaluate_model.py`, which prints the
average time per request.

## 4. Is the model suitable for this task?

Yes, with these design choices:

1. **Structured output.** Ollama's `/api/chat` accepts a `format` field
   containing a JSON schema, and it constrains the model to produce JSON that
   matches it. That removes most "the model answered in prose" problems.
2. **Thinking disabled.** Qwen 3.5 has a "thinking" mode that writes long
   reasoning before answering. We send `"think": false` because it's faster
   and we only need the JSON. You can turn it back on with `$env:FSA_THINK = "1"`.
3. **Temperature 0.** This makes answers as repeatable as possible.
4. **Few-shot prompt.** The system prompt in `fs_assistant/prompts.py` contains
   14 example requests with their correct JSON.
5. **Validation and one retry.** Python never trusts the JSON. It checks the
   action name, field types, lengths, and paths. If the reply is invalid, the
   model gets one more chance with the error message.

**Known limitations of a 4B model:**

- It can still choose the wrong action for unusual phrasing, or drop a folder
  name ("in projects" → `main.py` instead of `projects/main.py`). Debug mode
  makes this visible, and the confirmations limit the damage.
- File names containing spaces or unusual punctuation are less reliable.
- One request means one action. "Create three files" or "delete all .txt
  files" are deliberately out of scope.
- Answers are usually the same for the same input at temperature 0, but this
  isn't guaranteed across Ollama or model versions.
- The model is multimodal, but we only use its text abilities. The vision
  projector still takes up 676 MB of the download.

**If the 4B model turns out to be too slow on your laptops**, `qwen3.5:2b` is
the smaller model in the same family. Switching is a team decision. It's a
one-line change (`DEFAULT_MODEL` in `fs_assistant/config.py`) or the
`--model` flag, so decide together and re-run the evaluation script.

## Sources

- [Ollama library: qwen3.5:4b](https://ollama.com/library/qwen3.5:4b)
- [Ollama library: qwen3.5:4b-q4_K_M](https://ollama.com/library/qwen3.5:4b-q4_K_M)
- [Ollama announcement of the Qwen 3.5 small models (X)](https://x.com/ollama/status/2028510184788926567)
- [How to use Qwen 3.5 with Ollama (DEV Community)](https://dev.to/preecha/how-to-use-qwen-35-with-ollama-20a0)
