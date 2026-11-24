# Database diagram

Open this file in VS Code and press **Ctrl+Shift+V** to see the drawing. This needs the extension "Markdown Preview Mermaid Support".

```mermaid
erDiagram
    users ||--o{ conversations : "has"
    conversations ||--o{ messages : "contains"
    messages ||--o| actions : "produces"

    users {
        INTEGER user_id PK
        TEXT display_name
        TEXT source "terminal or telegram"
        INTEGER telegram_user_id UK "NULL for terminal"
        TEXT created_at
    }
    conversations {
        INTEGER conversation_id PK
        INTEGER user_id FK "REFERENCES users(user_id)"
        TEXT title
        TEXT created_at
        TEXT updated_at
    }
    messages {
        INTEGER message_id PK
        INTEGER conversation_id FK "REFERENCES conversations(conversation_id)"
        TEXT role "user or assistant"
        TEXT content
        TEXT created_at
    }
    actions {
        INTEGER action_id PK
        INTEGER message_id FK,UK "REFERENCES messages(message_id)"
        TEXT action_type
        TEXT path
        TEXT model_json
        INTEGER success "0 or 1"
        TEXT result
        INTEGER duration_ms
        TEXT model
        TEXT created_at
    }
```

The SQL that creates these tables is in `fs_assistant/schema.sql`. Queries that join them are in `queries.sql`.
