-- =====================================================================
--  SQL queries for the AI File System Assistant database (assistant.db)
-- =====================================================================
--  The tables are created in fs_assistant/schema.sql:
--    users (PK user_id)
--      1 --< N  conversations (PK conversation_id, FK user_id -> users)
--                 1 --< N  messages (PK message_id, FK conversation_id -> conversations)
--                            1 --- 0..1  actions (PK action_id, FK message_id -> messages)
--
--  How to run a query in VS Code (extension "SQLite" by alexcvzz):
--    1. Run the app at least once (python main.py) so assistant.db exists.
--    2. Ctrl+Shift+P -> "SQLite: Open Database" -> choose assistant.db
--    3. Highlight ONE query below with the mouse
--    4. Right-click -> "Run Selected Query"   (or Ctrl+Shift+Q)
--  To see them DRAWN:
--    python scripts/draw_erd.py      -> diagram of the tables and keys
--    python scripts/draw_charts.py   -> queries 6, 7, 8 and 3 as charts
-- =====================================================================


-- 1. All chats with their owner (JOIN users <-> conversations through the foreign key)
SELECT c.conversation_id, c.title, u.display_name, u.source, c.created_at, c.updated_at
FROM conversations c
JOIN users u ON u.user_id = c.user_id
ORDER BY c.updated_at DESC;


-- 2. The full conversation of chat number 1 (change the number), in order
SELECT m.created_at, m.role, m.content
FROM messages m
WHERE m.conversation_id = 1
ORDER BY m.message_id;


-- 3. Number of messages in each chat, top 8 (JOIN + GROUP BY)
SELECT c.conversation_id, c.title, COUNT(m.message_id) AS messages
FROM conversations c
JOIN messages m ON m.conversation_id = c.conversation_id
GROUP BY c.conversation_id
ORDER BY messages DESC
LIMIT 8;


-- 4. Every user message with the action the AI chose for it (LEFT JOIN messages <-> actions)
SELECT m.message_id, m.content AS user_said, a.action_type, a.path, a.success
FROM messages m
LEFT JOIN actions a ON a.message_id = m.message_id
WHERE m.role = 'user'
ORDER BY m.message_id DESC;


-- 5. Join of ALL 4 tables: who asked what, in which chat, and what happened
SELECT u.display_name, c.title AS chat, m.content AS request, a.action_type, a.result
FROM users u
JOIN conversations c ON c.user_id = u.user_id
JOIN messages m      ON m.conversation_id = c.conversation_id
JOIN actions a       ON a.message_id = m.message_id
ORDER BY a.action_id DESC;


-- 6. How many times each action was used
SELECT action_type, COUNT(*) AS times
FROM actions
GROUP BY action_type
ORDER BY times DESC;


-- 7. Success rate of the assistant
SELECT SUM(success) AS succeeded,
       COUNT(*) - SUM(success) AS failed
FROM actions;


-- 8. Average response time per action (milliseconds)
SELECT action_type, ROUND(AVG(duration_ms)) AS avg_ms
FROM actions
WHERE duration_ms IS NOT NULL
GROUP BY action_type
ORDER BY avg_ms DESC;


-- 9. Failed or cancelled requests, with the chat they belong to
SELECT c.title AS chat, m.content AS request, a.result
FROM actions a
JOIN messages m      ON m.message_id = a.message_id
JOIN conversations c ON c.conversation_id = m.conversation_id
WHERE a.success = 0
ORDER BY a.action_id DESC;


-- 10. Activity per user: chats and messages (terminal vs Telegram)
SELECT u.display_name, u.source,
       COUNT(DISTINCT c.conversation_id) AS chats,
       COUNT(m.message_id) AS messages
FROM users u
LEFT JOIN conversations c ON c.user_id = u.user_id
LEFT JOIN messages m      ON m.conversation_id = c.conversation_id
GROUP BY u.user_id;


-- 11. Everything created on the Desktop
SELECT a.created_at, a.action_type, a.path
FROM actions a
WHERE a.path LIKE 'Desktop%'
  AND a.action_type IN ('create_file', 'create_directory')
  AND a.success = 1;


-- 12. The ready-made VIEW that joins the 4 tables (defined in schema.sql)
SELECT * FROM chat_history ORDER BY message_id DESC LIMIT 20;


-- 13. Show the structure of the database itself
SELECT name, type FROM sqlite_master WHERE type IN ('table', 'view', 'index') ORDER BY type, name;


-- 14. (Optional) Delete chat number 1. Thanks to ON DELETE CASCADE its
--     messages and actions are deleted automatically. Careful: no undo!
-- DELETE FROM conversations WHERE conversation_id = 1;
