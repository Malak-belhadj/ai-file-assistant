# Telegram Bot Setup

With the bot, you write on your phone "create test on desktop" and the folder appears on your PC.

```
Phone (Telegram) -> Telegram servers -> python main.py --telegram (your PC) -> Qwen (Ollama) -> Desktop\test
                                                                    |
                                                                    +-> saved in assistant.db
```

Your PC must be **on**, with the program **running** and **Ollama** running.

**One command for everything:** `python main.py` starts the terminal chat **and** the Telegram bot together, when `.env` has a token. You can type in PowerShell and on your phone at the same time. Use `python main.py --no-telegram` for the terminal only, or `python main.py --telegram` for the bot only. The bot uses *long polling*: the program keeps asking Telegram "any new message?". You don't need a website, a server or an open port.

## Setup (once)

1. On your phone, open Telegram and search for **@BotFather** (it has a blue check mark).
2. Send `/newbot`.
3. Choose a name, for example `Malak File Assistant`.
4. Choose a username ending in `bot`, for example `malak_files_bot`.
5. BotFather sends you a **token** like `1234567890:AAH...`. Keep it secret.
6. On your PC, in the project folder, copy `.env.example` and rename the copy to `.env`.
7. Open `.env` in VS Code and paste your token after `TELEGRAM_BOT_TOKEN=`.
8. Save the file.
9. In PowerShell, in the project folder, run `.venv\Scripts\Activate.ps1`.
10. Run `python main.py`.
11. On your phone, open your new bot and send `hello`.
12. The bot answers "not allowed" and shows **your Telegram user ID** (a number).
13. Put that number in `.env` after `TELEGRAM_ALLOWED_USERS=`.
14. Save, then stop the program with **Ctrl+C**.
15. Run `python main.py` again.

## Use it

- Send `create test on desktop`, and the folder appears on your Desktop.
- Send `make a folder m on my desktop with files a and b`.
- Send `what's on my desktop?`.
- Send `delete notes.txt`. The bot asks for confirmation, and you reply `yes` or `no`.

**Commands:**

| Command | What it does |
|---|---|
| `/new` | start a new chat |
| `/chats` | list your saved chats |
| `/open 3` | continue chat number 3 |
| `/history` | show this chat's messages |
| `/search <question>` | search the internet, for example `/search capital of Australia` |
| `/help` | show help |

Telegram chats are saved in the same database as terminal chats, with `source = 'telegram'` in the `users` table.

## Security

- Only the user IDs in `TELEGRAM_ALLOWED_USERS` can use the bot. Everyone else is refused before the AI is even called.
- The same safety rules apply as in the terminal: user folder only, no `AppData`, no shell commands, and confirmation before deleting or overwriting.
- `.env` is in `.gitignore`, so the token is never uploaded to GitHub.
- If your token leaks, send `/revoke` to @BotFather to get a new one.

## Problems

| Problem | Fix |
|---|---|
| "No Telegram bot token found" | Create `.env` (steps 6–8). Check the file is named exactly `.env` and not `.env.txt`. |
| "The bot token is wrong" | Copy the token again from @BotFather. |
| "Cannot reach Telegram" | Check your internet. Antivirus HTTPS scanning (Avast) can block it, so turn it off. |
| The bot doesn't answer | Check that `python main.py` is still running on the PC, and look for `[Telegram]` lines in PowerShell. |
| "AI model unavailable" | Start Ollama on the PC. |
