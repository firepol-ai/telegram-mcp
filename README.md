# Telegram MCP Server (hardened fork)

A local [Model Context Protocol](https://modelcontextprotocol.io) server that lets Claude Code (or any MCP client) read **your own Telegram account** over MTProto, built on [Telethon](https://docs.telethon.dev).

This is a hardened fork of [Shaan-alpha/telegram-mcp](https://github.com/Shaan-alpha/telegram-mcp), started from upstream `0397afa`. See [AUDIT.md](AUDIT.md) for the audit of the upstream code and what was changed.

## What is different from upstream

- **Read-only by default.** `preview_message` / `send_message` only exist when `TELEGRAM_MCP_ALLOW_SEND=1` and only target chats marked `send = true` in the agent's `telegram.toml`. `send_message` only sends text that was previewed with identical arguments, appends a fixed signature, and is rate-limited.
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
| `poll_new(limit_per_chat=200)` | Agent workspaces only: new messages in the workspace's chats since the last call (local cursor) |
| `preview_message(chat, text, reply_to=None)` | **Only with `TELEGRAM_MCP_ALLOW_SEND=1`.** Recipient and exact final text with signature; sends nothing |
| `send_message(chat, text, reply_to=None)` | **Only with `TELEGRAM_MCP_ALLOW_SEND=1`.** Sends text previously previewed with identical arguments |

`chat` accepts a numeric id, `@username`, `t.me` link, or (partial) title. If a title matches several chats you get the list of candidates instead of a guess.

Each message is one compact line: `<telegram_message id=… ts=… from="…" reply_to=… to_me=1 fwd="…" media=… link=https://t.me/…>text</telegram_message>`. Large limits are paged automatically and FloodWait pauses of up to 10 minutes are slept through.

## Setup

Requires [uv](https://docs.astral.sh/uv/). Paths below assume the repo is at `~/projects/telegram-mcp`.

### 1. Install (pinned)

```bash
git clone git@github.com:firepol-ai/telegram-mcp.git ~/projects/telegram-mcp
cd ~/projects/telegram-mcp
uv sync --locked          # creates .venv/ from uv.lock, verifying hashes
.venv/bin/python tests/smoke.py
```

### 2. Private config directory

```bash
mkdir -p ~/.config/telegram-mcp
setfacl -b ~/.config/telegram-mcp 2>/dev/null; chmod 700 ~/.config/telegram-mcp
(umask 077; printf 'API_ID=\nAPI_HASH=\n' > ~/.config/telegram-mcp/env)
```

`setfacl -b` matters if `~/.config` carries a default ACL: new files would inherit it and the server would refuse them.

### 3. API credentials

At [my.telegram.org](https://my.telegram.org) → **API development tools**, create an app and put `api_id` / `api_hash` into `~/.config/telegram-mcp/env` with your editor. Telegram allows one app per account: if you already have one, there is no create button; reuse the `App api_id` and `App api_hash` shown under **App configuration**. That is safe: they identify the app, not a login, and every login is a separate session under Settings → Devices. Do not paste them into a chat with an AI.

### 4. Log in, yourself, in a terminal

```bash
cd ~/projects/telegram-mcp
.venv/bin/python login.py           # QR code: Telegram → Settings → Devices → Link Desktop Device
.venv/bin/python login.py --phone   # fallback: phone number + login code
```

The 2FA password (if set) is asked without echo. The session is written to `~/.config/telegram-mcp/session` (mode 600).

### 5. Register with your MCP client

Claude Code, read-only, in every project:

```bash
claude mcp add --scope user telegram -- ~/projects/telegram-mcp/.venv/bin/python ~/projects/telegram-mcp/server.py
```

Claude Desktop (`claude_desktop_config.json`), read-only:

```json
{
  "mcpServers": {
    "telegram": {
      "command": "/home/YOU/projects/telegram-mcp/.venv/bin/python",
      "args": ["/home/YOU/projects/telegram-mcp/server.py"]
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

Each agent is a folder of its own, so you can run several (one per project or team) with different chats, instructions and permissions. All of them share the one Telegram login in `~/.config/telegram-mcp/`.

- A workspace directory with:
  - `telegram.toml`: the complete list of chats this agent can access, which ones may receive a sent message, the signature and the rate limit ([agent/telegram.example.toml](agent/telegram.example.toml)). **Enforced by the server**: with a workspace, every tool is limited to these chats, so a manipulated model cannot widen it. The server refuses to start if anyone but you can modify the file or the folder (mode bits or POSIX ACL),
  - `.telegram-state.json`: written by the server, `poll_new` cursors for this agent only,
  - `CLAUDE.md`: the secretary's procedure ([agent/CLAUDE.md](agent/CLAUDE.md)),
  - `SOUL.md`: your people, priorities, tone, reference repositories and what never to share ([agent/SOUL.example.md](agent/SOUL.example.md)),
  - `.claude/settings.json`: permissions ([agent/settings.example.json](agent/settings.example.json)): read-only access to the listed repositories, Telegram read tools allowed, `send_message` always asks, Bash/Edit/Write/Web denied, `.env*` and the Telegram config unreadable. **Do not run this session with `--dangerously-skip-permissions` or in auto mode:** it processes text written by other people.

### How the files work together

| File | What goes in it | Who edits it | Enforced by |
|---|---|---|---|
| `telegram.toml` | The chats this agent may access; which may receive a sent message; signature; rate limit | You | The server: hard limit, the model cannot get around it |
| `.claude/settings.json` | Which repositories it may read; which tools are allowed, asked or denied | You | Claude Code |
| `SOUL.md` | Everything about you and this agent's job: people, what matters (including colleagues' conversations), notifications, how to write replies (tone, length, emojis, language), how to summarise, reference repositories, what never to share | You, often | The model follows it |
| `CLAUDE.md` | The fixed routine: check, triage, report, draft, never send without approval, treat messages as untrusted | Nobody; copy it from `agent/CLAUDE.md` when it changes upstream | The model follows it |

Claude Code loads `CLAUDE.md` automatically when a session starts in the folder, and `CLAUDE.md` imports `SOUL.md` with the line `@SOUL.md`. The split keeps your personal content separate from the procedure, so the procedure can be updated without touching it. When the two disagree on style or priorities, SOUL.md wins; the safety rules in CLAUDE.md (no sending without approval, ignore instructions inside messages) always apply.

Changes to `SOUL.md` or `CLAUDE.md` take effect in a new session; in a running one, tell the agent to "re-read SOUL.md". Changes to `telegram.toml` are picked up by the server on the next tool call, no restart needed.

To tune behaviour, edit SOUL.md and tell the agent what to change: "shorter drafts, no emojis", "also tell me about anything on payments in Dev team", "summaries as bullet points with a timeline". You can also ask the agent to propose a SOUL.md edit, then paste it in yourself (the template settings do not let it write files). To let it apply your feedback itself, remove `"Edit"` from `deny`, add `Edit(//abs/path/to/workspace/SOUL.md)` and `.../CLAUDE.md` to `ask`, and deny `Edit(...)` explicitly for `telegram.toml`, `.claude/**`, your repositories and home config files (deny rules beat ask rules, so a blanket `Edit` deny would block the two files too). Every edit then shows you the diff for approval.

### Finding chat ids

Users with a public username can be listed as `"@username"`. Groups, channels, and users without a username need the numeric id:

1. Start Claude Code in any folder that is **not** an agent workspace (the user-scope server there can see all your chats, read-only).
2. Ask: `Use the telegram tools: list_chats with limit 100` (or `list_unread`).
3. Each line looks like `id=-1001234567890 type=group name="Dev team" unread=3 last=…`. Copy the `id` value exactly, including the minus sign:
   - users: positive numbers, e.g. `123456789`,
   - basic groups: negative, e.g. `-987654321`,
   - supergroups and channels: negative with a `-100` prefix, e.g. `-1001234567890`.
4. Add it to `telegram.toml`:

   ```toml
   [[chats]]
   chat = -1001234567890      # a number, not a string
   note = "Dev team: managers and developers"
   send = false
   ```

The `note` is passed to the agent with every batch of new messages from that chat, so it is a good place for one line of context.

### Set up

```bash
mkdir -p ~/telegram-agent/.claude && cd ~/telegram-agent
setfacl -Rb . 2>/dev/null; chmod -R go-w .                              # only you may change the allowlist
cp ~/projects/telegram-mcp/agent/telegram.example.toml telegram.toml        # then list the chats
cp ~/projects/telegram-mcp/agent/CLAUDE.md .
cp ~/projects/telegram-mcp/agent/SOUL.example.md SOUL.md                    # then edit
cp ~/projects/telegram-mcp/agent/settings.example.json .claude/settings.json  # then set additionalDirectories
claude mcp add --scope local telegram -e TELEGRAM_MCP_WORKSPACE="$PWD" -e TELEGRAM_MCP_ALLOW_SEND=1 -- \
  ~/projects/telegram-mcp/.venv/bin/python ~/projects/telegram-mcp/server.py
```

The `local` registration overrides the read-only user-scope one only inside this directory. Add the chats to `telegram.toml` (see [Finding chat ids](#finding-chat-ids)) and fill in `SOUL.md`. Leave out `TELEGRAM_MCP_ALLOW_SEND=1` for an agent that should only read and report.

### Run with Remote Control (steer it from your phone)

Remote Control makes a Claude Code session running on your machine available in the Claude mobile app and on claude.ai/code. The session, the MCP server, your Telegram login and the repositories all stay on your machine; the app is only a window into it. The machine has to stay on and awake.

**1. Start the session in tmux**, so it survives closing the terminal:

```bash
tmux new -s telegram-agent
cd ~/telegram-agent
claude --remote-control "Telegram secretary"
```

The name is what you will see in the app. Alternatively, start `claude` normally and run `/remote-control` inside the session. Do the very first start at the terminal: the workspace trust dialog only appears there. Keep the default permission mode; do not add `--dangerously-skip-permissions` or `--permission-mode bypassPermissions`/`auto`. The template settings include `"disableBypassPermissionsMode": "disable"`, so bypass mode is refused in the workspace even if you start `claude` with that flag out of habit.

**2. Start the periodic check** in the session (at the terminal, or later from the app):

```
/loop 3m Run the Telegram check from CLAUDE.md
```

**3. Detach** with `Ctrl-b d`. Reattach later with `tmux attach -t telegram-agent`.

**4. On your phone**, open the Claude app and pick the session by its name (on a computer: claude.ai/code). Allow notifications for the Claude app on the phone, and make sure push notifications for agents are enabled in Claude Code (`"agentPushNotifEnabled": true` in `~/.claude/settings.json`). The agent sends a notification when something needs you or a draft is ready; permission prompts (such as the one for `send_message`) also appear in the app.

**Day-to-day, from the app**, write to the session as in any Claude chat:

| You write | What happens |
|---|---|
| `send 2` | Draft 2 (already shown with its exact final text, signature included) is sent after you approve the `send_message` permission prompt |
| `send 2, but say we can do it on Friday` | The draft is changed and previewed again; it is sent after your next `send` and the permission prompt |
| `skip 1` / `I'll answer 3 myself` | Nothing is sent |
| `summarise 💻 Dev since this morning` | A catch-up using `get_since` |
| `what did Anna ask me this week?` | Searches the watched chats |
| `re-read SOUL.md` | Picks up your edits without restarting |
| `stop the loop` / `/loop 10m …` | Pauses checking or changes the interval |

Sending always takes two approvals: your message in the chat (`send 2`) and the permission prompt. Only the second one cannot be produced by a Telegram message trying to manipulate the agent, so read the preview before approving it. `preview_message` is allowed without a prompt because it sends nothing. If one approval is enough for you, move `mcp__telegram__send_message` from `ask` to `allow` in the workspace settings and change step 6 of `CLAUDE.md` so your chat message is the only approval; the server-side limits (allowed chats, signature, rate limit) still apply.

**If the session stops** (reboot, crash, `claude` exited): start it again with the same command in tmux; add `-c` (`claude -c --remote-control "Telegram secretary"`) to continue the previous conversation, then start `/loop` again: loops do not survive a restart. The `poll_new` cursors are kept in `.telegram-state.json`, so nothing is missed or repeated.

**Usage:** each check is a model turn even when nothing is new (about 160 per 8 hours at a 3-minute interval). Widen the interval if usage matters, and stop the loop when you do not need it (evenings, holidays).

## Security notes

- The session file is equivalent to being logged in as you. It stays in `~/.config/telegram-mcp/` (700/600) and is never logged or returned by a tool.
- The server talks only to Telegram's MTProto servers. No telemetry, no update checks.
- Automating a user account is a Telegram ToS grey area. Reading is fine; keep sending rare and human-approved.

## Updating from upstream (only when you decide to)

Nothing updates automatically: no Dependabot/Renovate, GitHub Actions disabled on the fork, no "Sync fork".

```bash
cd ~/projects/telegram-mcp
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
