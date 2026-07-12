# Hermes Tool Manifest Format

Hermes tools are small reusable local capabilities. A tool must declare what it
does, how it runs, what it can read/write, and what outputs it promises.

## Minimal manifest

```json
{
  "schema_version": 1,
  "name": "telegram-report-watcher",
  "version": "0.1.0",
  "description": "Watch Telegram reports and create reviewer prompts.",
  "type": "cli",
  "entrypoint": "main.py",
  "inputs": [
    {
      "name": "chat_id",
      "type": "string",
      "required": true
    }
  ],
  "outputs": [
    "report.md",
    "telegram_message"
  ],
  "permissions": {
    "filesystem_read": [
      "reports/**"
    ],
    "filesystem_write": [
      "reports/**"
    ],
    "network": [
      "telegram"
    ],
    "shell": false
  },
  "providers": [
    "gemini",
    "ollama",
    "openrouter"
  ]
}
```

## Required fields

| Field | Meaning |
| --- | --- |
| `schema_version` | Manifest schema version. Start with `1`. |
| `name` | Stable tool id. Use lowercase kebab-case. |
| `version` | Tool version. |
| `description` | One sentence explaining the tool. |
| `type` | `cli`, `worker`, `telegram`, `gui`, or `library`. |
| `entrypoint` | File to run or import. |
| `inputs` | Declared input parameters. |
| `outputs` | Declared output artifacts or message types. |
| `permissions` | Filesystem, network, and shell permissions. |

## Permission defaults

If a field is missing, Hermes should assume the safer value:

- no shell access
- no network access
- read-only filesystem
- writes only inside the tool output folder

## Future commands

```cmd
python scripts\hermes_tool.py list
python scripts\hermes_tool.py create telegram-report-watcher
python scripts\hermes_tool.py run telegram-report-watcher --chat-id 5069349064
python scripts\hermes_tool.py export telegram-report-watcher
```
