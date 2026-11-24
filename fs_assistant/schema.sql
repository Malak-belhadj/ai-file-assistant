-- =====================================================================
--  Database schema of the AI File System Assistant (SQLite)
-- =====================================================================
--  4 tables linked with FOREIGN KEYS:
--
--    users 1 ──< N conversations 1 ──< N messages 1 ──── 0..1 actions
--
--  * users          : who talks to the assistant (terminal or Telegram)
--  * conversations  : one chat, like a ChatGPT conversation you can reopen
--  * messages       : every message in a chat (user and assistant)
--  * actions        : the file operation the AI chose for a user message
--
--  This file is executed by fs_assistant/database.py every time the app
--  starts ("IF NOT EXISTS" means existing data is never deleted).
-- =====================================================================

PRAGMA foreign_keys = ON;   -- SQLite only checks foreign keys when this is ON


-- ---------------------------------------------------------------------
-- Table 1: users
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    user_id           INTEGER PRIMARY KEY AUTOINCREMENT,      -- PK
    display_name      TEXT    NOT NULL,
    source            TEXT    NOT NULL CHECK (source IN ('terminal', 'telegram')),
    telegram_user_id  INTEGER UNIQUE,                         -- NULL for the terminal user
    created_at        TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);


-- ---------------------------------------------------------------------
-- Table 2: conversations   (one user has many conversations)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS conversations (
    conversation_id   INTEGER PRIMARY KEY AUTOINCREMENT,      -- PK
    user_id           INTEGER NOT NULL,                       -- FK -> users
    title             TEXT    NOT NULL DEFAULT 'New chat',
    created_at        TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at        TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
);


-- ---------------------------------------------------------------------
-- Table 3: messages   (one conversation has many messages)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS messages (
    message_id        INTEGER PRIMARY KEY AUTOINCREMENT,      -- PK
    conversation_id   INTEGER NOT NULL,                       -- FK -> conversations
    role              TEXT    NOT NULL CHECK (role IN ('user', 'assistant')),
    content           TEXT    NOT NULL,
    created_at        TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (conversation_id) REFERENCES conversations (conversation_id) ON DELETE CASCADE
);


-- ---------------------------------------------------------------------
-- Table 4: actions   (a user message produces at most one action)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS actions (
    action_id         INTEGER PRIMARY KEY AUTOINCREMENT,      -- PK
    message_id        INTEGER NOT NULL UNIQUE,                -- FK -> messages (1-to-1)
    action_type       TEXT    NOT NULL,                       -- create_file, delete_file, ... or error
    path              TEXT,                                   -- file/folder concerned
    model_json        TEXT,                                   -- the JSON the AI produced
    success           INTEGER NOT NULL CHECK (success IN (0, 1)),
    result            TEXT    NOT NULL,                       -- message shown to the user
    duration_ms       INTEGER,                                -- time taken (AI + disk)
    model             TEXT,                                   -- e.g. qwen3.5:4b
    created_at        TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (message_id) REFERENCES messages (message_id) ON DELETE CASCADE
);


-- Indexes make the JOINs on foreign keys fast.
CREATE INDEX IF NOT EXISTS idx_conversations_user  ON conversations (user_id);
CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages (conversation_id);
CREATE INDEX IF NOT EXISTS idx_actions_type        ON actions (action_type);


-- ---------------------------------------------------------------------
-- A VIEW: a saved query that joins the 4 tables into one readable table
-- ---------------------------------------------------------------------
CREATE VIEW IF NOT EXISTS chat_history AS
SELECT u.display_name,
       u.source,
       c.conversation_id,
       c.title            AS chat_title,
       m.message_id,
       m.created_at,
       m.role,
       m.content,
       a.action_type,
       a.path,
       a.success
FROM users u
JOIN conversations c ON c.user_id = u.user_id
JOIN messages m      ON m.conversation_id = c.conversation_id
LEFT JOIN actions a  ON a.message_id = m.message_id;
