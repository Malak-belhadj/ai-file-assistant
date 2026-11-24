# The Database

The project uses **SQLite**. It's built into Python, and the whole database is one file: `assistant.db`.

## Tables and keys

The tables are defined in [`fs_assistant/schema.sql`](../fs_assistant/schema.sql). Open it in VS Code to see the `CREATE TABLE`, `PRIMARY KEY` and `FOREIGN KEY ... REFERENCES` statements.

```
users 1 ──< N conversations 1 ──< N messages 1 ──── 0..1 actions
```

| Table | Primary key | Foreign key | What one row is |
|---|---|---|---|
| `users` | `user_id` | none | a person: the terminal user or a Telegram user |
| `conversations` | `conversation_id` | `user_id → users` | one chat, like a ChatGPT conversation |
| `messages` | `message_id` | `conversation_id → conversations` | one message (`role` = user or assistant) |
| `actions` | `action_id` | `message_id → messages` (UNIQUE: one-to-one) | the file operation the AI chose for a user message |

**Other SQL features used:**

- `CHECK` constraints: `role` must be `user` or `assistant`, and `success` must be 0 or 1.
- `UNIQUE`: one Telegram ID per user, and at most one action per message.
- `ON DELETE CASCADE`: deleting a chat also deletes its messages and actions.
- Indexes on the foreign keys, to make JOINs fast.
- A **VIEW**, `chat_history`, that joins all 4 tables.
- `PRAGMA foreign_keys = ON`, so SQLite really checks the foreign keys.

## Seeing it

| What | How |
|---|---|
| The diagram of tables and keys | `python scripts/draw_erd.py`, then open `charts/database_diagram.png` (or type `diagram` in the app) |
| Query results as charts | `python scripts/draw_charts.py`, then open the `charts/` folder (or type `charts` in the app) |
| Run SQL queries yourself | Open `queries.sql` in VS Code with the "SQLite" extension (alexcvzz). Highlight a query, right-click, choose **Run Selected Query** |

## Continuing old chats (like ChatGPT)

| Terminal | Telegram | What it does |
|---|---|---|
| `chats` | `/chats` | list your chats |
| `open 3` | `/open 3` | reopen chat 3 and continue it |
| `new` | `/new` | start a new chat |
| `history` | `/history` | show this chat's messages |

When you continue a chat, the app reads its earlier messages from the database (`ChatDatabase.get_context`) and sends them to the AI with your new message. So "now delete it" understands which file "it" means.
