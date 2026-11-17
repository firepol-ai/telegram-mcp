# Telegram MCP Server (hardened fork)

A local [Model Context Protocol](https://modelcontextprotocol.io) server that lets Claude Code (or any MCP client) read **your own Telegram account** over MTProto, built on [Telethon](https://docs.telethon.dev).

This is a hardened fork of [Shaan-alpha/telegram-mcp](https://github.com/Shaan-alpha/telegram-mcp), started from upstream `0397afa`. See [AUDIT.md](AUDIT.md) for the audit of the upstream code and what was changed.

## What is different from upstream

- **Read-only by default.** `send_message` only exists when `TELEGRAM_MCP_ALLOW_SEND=1`, only targets chats marked `send = true` in `config.toml`, always returns a preview first, needs a second `confirm=true` call with identical arguments, appends a fixed signature, and is rate-limited.
- **Never marks anything as read.** Your unread state in the Telegram apps stays as it was.
- **Secrets out of the repo and out of MCP configs.** Everything lives in `~/.config/telegram-mcp/`. The server refuses to start if that directory or any file in it is accessible to group/others, has a POSIX ACL, or is owned by another user.
- **Untrusted content is marked.** Message text is wrapped in `<telegram_message>` tags (delimiters inside messages are neutralised) and every tool description says it is third-party data, not instructions.
- **Catch-up tools** for summarising long chats, and `poll_new` for a periodic agent.
- **Pinned dependencies** with hashes (`uv.lock`), QR-code login, a smoke test.

## Tools

| Tool | Description |
|---|---|
| `get_me()` | The logged-in account (id, username, name) |
| `list_chats(limit=30)` | Recent chats with ids, type, unread counts |
| `list_unread()` | Chats with unread messages or unread @mentions, newest first |
| `get_history(chat, limit=50)` | Latest messages, oldest→newest |
| `get_unread(chat, limit=2000)` | Unread messages, oldest→newest (does not mark read) |
| `get_since(chat, since_iso, limit=2000)` | Messages since a date, oldest→newest |
| `get_mentions(chat=None, limit=200)` | Messages that @mention me or reply to me; all chats if `chat` is omitted |
| `search_messages(chat, query, limit=50)` | Search in one chat |
| `search_all(query, limit=50)` | Search across all chats |
| `poll_new(limit_per_chat=200)` | New messages in the chats listed in `config.toml` since the last call (local cursor) |
| `send_message(chat, text, reply_to=None, confirm=False)` | **Only with `TELEGRAM_MCP_ALLOW_SEND=1`.** Preview, then send after approval |

`chat` accepts a numeric id, `@username`, `t.me` link, or (partial) title. If a title matches several chats you get the list of candidates instead of a guess.

Each message is one compact line: `<telegram_message id=… ts=… from="…" reply_to=… to_me=1 fwd="…" media=… link=https://t.me/…>text</telegram_message>`. Large limits are paged automatically and FloodWait pauses of up to 10 minutes are slept through.

## Setup

Requires [uv](https://docs.astral.sh/uv/). Paths below assume the repo is at `~/src/telegram-mcp`.

### 1. Install (pinned)

```bash
git clone git@github.com:firepol-ai/telegram-mcp.git ~/src/telegram-mcp
cd ~/src/telegram-mcp
uv sync --locked          # creates .venv/ from uv.lock, verifying hashes
.venv/bin/python tests/smoke.py
```

### 2. Private config directory

```bash
mkdir -p ~/.config/telegram-mcp
setfacl -b ~/.config/telegram-mcp 2>/dev/null; chmod 700 ~/.config/telegram-mcp
(umask 077; printf 'API_ID=\nAPI_HASH=\n' > ~/.config/telegram-mcp/env)
(umask 077; cp config.example.toml ~/.config/telegram-mcp/config.toml)
```

`setfacl -b` matters if `~/.config` carries a default ACL: new files would inherit it and the server would refuse them.

### 3. API credentials

At [my.telegram.org](https://my.telegram.org) → **API development tools**, create an app and put `api_id` / `api_hash` into `~/.config/telegram-mcp/env` with your editor. Do not paste them into a chat with an AI.

### 4. Log in, yourself, in a terminal

```bash
cd ~/src/telegram-mcp
.venv/bin/python login.py           # QR code: Telegram → Settings → Devices → Link Desktop Device
.venv/bin/python login.py --phone   # fallback: phone number + login code
```

The 2FA password (if set) is asked without echo. The session is written to `~/.config/telegram-mcp/session` (mode 600).

### 5. Register with your MCP client

Claude Code, read-only, in every project:

```bash
claude mcp add --scope user telegram -- ~/src/telegram-mcp/.venv/bin/python ~/src/telegram-mcp/server.py
```

Claude Desktop (`claude_desktop_config.json`), read-only:

```json
{
  "mcpServers": {
    "telegram": {
      "command": "/home/YOU/src/telegram-mcp/.venv/bin/python",
      "args": ["/home/YOU/src/telegram-mcp/server.py"]
    }
  }
}
```

No secrets go into either config.

### Example

> Use the telegram tools: summarise unread in 'Dev team': decisions, things asked of me, open issues, links shared, short timeline with message links.

## Secretary agent mode

A long-running Claude Code session that watches selected chats, tells you what needs your attention, and drafts replies for you to approve, steered from the Claude mobile app via Remote Control.

### Pieces

- `~/.config/telegram-mcp/config.toml`: which chats `poll_new` watches, which ones may receive a sent message, the signature and the rate limit. **Enforced by the server**, so a manipulated model cannot widen it. See [config.example.toml](config.example.toml).
- A workspace directory with:
  - `CLAUDE.md`: the secretary's procedure ([agent/CLAUDE.md](agent/CLAUDE.md)),
  - `SOUL.md`: your people, priorities, tone, reference repositories and what never to share ([agent/SOUL.example.md](agent/SOUL.example.md)),
  - `.claude/settings.json`: permissions ([agent/settings.example.json](agent/settings.example.json)): read-only access to the listed repositories, Telegram read tools allowed, `send_message` always asks, Bash/Edit/Write/Web denied, `.env*` and the Telegram config unreadable. **Do not run this session with `--dangerously-skip-permissions` or in auto mode:** it processes text written by other people.

### Set up

```bash
mkdir -p ~/telegram-agent/.claude && cd ~/telegram-agent
cp ~/src/telegram-mcp/agent/CLAUDE.md .
cp ~/src/telegram-mcp/agent/SOUL.example.md SOUL.md                    # then edit
cp ~/src/telegram-mcp/agent/settings.example.json .claude/settings.json  # then set additionalDirectories
claude mcp add --scope local telegram -e TELEGRAM_MCP_ALLOW_SEND=1 -- \
  ~/src/telegram-mcp/.venv/bin/python ~/src/telegram-mcp/server.py
```

The `local` registration overrides the read-only user-scope one only inside this directory. Get chat ids with `list_chats` and add them to `config.toml` as `[[chats]]`.

### Run

```bash
tmux new -s telegram-agent
cd ~/telegram-agent && claude
```

Inside the session: accept the workspace trust dialog, run `/remote-control` (give it a title), then `/loop 3m Run the Telegram check from CLAUDE.md`. Detach with `Ctrl-b d`. On your phone, open the session in the Claude app: you get notified when something needs you; answer `send 1` to approve a draft, then approve the `send_message` permission prompt.

Each check is a model turn even when nothing is new (about 160 per 8 hours at a 3-minute interval); widen the interval if usage matters.

## Security notes

- The session file is equivalent to being logged in as you. It stays in `~/.config/telegram-mcp/` (700/600) and is never logged or returned by a tool.
- The server talks only to Telegram's MTProto servers. No telemetry, no update checks.
- Automating a user account is a Telegram ToS grey area. Reading is fine; keep sending rare and human-approved.

## Updating from upstream (only when you decide to)

Nothing updates automatically: no Dependabot/Renovate, GitHub Actions disabled on the fork, no "Sync fork".

```bash
cd ~/src/telegram-mcp
git fetch upstream
git log --oneline hardened..upstream/main          # what is new upstream
git diff 0397afa upstream/main                     # upstream changes since our base
```

1. Review the diff with the checklist in [AUDIT.md](AUDIT.md): network, credentials/session, dependencies, login flow, tools (especially writes and read-state), prompt injection, errors.
2. Merge by hand on a branch, resolving conflicts in favour of the hardened behaviour: `git switch -c merge-upstream hardened && git merge upstream/main`.
3. Re-lock deliberately and review what changed: `uv lock --upgrade` (or keep the current lock), `git diff uv.lock`, `uv sync --locked`.
4. `.venv/bin/python tests/smoke.py`.
5. Record the new upstream base commit in AUDIT.md, merge into `hardened`, `git push origin hardened`.

## Stopping / revoking

1. Telegram → Settings → Devices: terminate the session for this app.
2. `claude mcp remove telegram -s user` (and `-s local` in the agent workspace).
3. `rm -rf ~/.config/telegram-mcp/`.
4. Optionally delete the app at my.telegram.org.

## License

[MIT](LICENSE). Original work © 2026 Shaan Satsangi.
