# Security audit

## Baseline

- Upstream: `https://github.com/Shaan-alpha/telegram-mcp`, branch `main`
- Starting commit: `0397afa0c41d1d6560ec0f56fc40ce7a3929e464` ("docs: make the documented install actually work")
- Audited on 2026-11-17 by Claude Code (GitHub user `firepol-ai`)
- Files audited (all tracked files): `.env.example`, `.gitignore`, `LICENSE`, `README.md`, `login.py` (51 lines), `requirements.txt` (3 lines), `server.py` (236 lines)

Tags: **OK** = no action needed, **RISK** = worth knowing, accepted or mitigated elsewhere, **FIX** = to be changed on the `hardened` branch.

## Auto-update / sync

- **OK** No `.github/` directory, no Dependabot, Renovate or GitHub Actions workflows in the repo.
- **OK** No self-update, version check or remote-config code in `server.py` or `login.py`.
- **OK** Fork settings: Dependabot security updates `enabled:false`, vulnerability alerts off, auto-merge off.
- **FIX** Fork settings: GitHub Actions is `enabled:true, allowed_actions:all`. No workflows exist today, but a workflow merged from upstream later would run. Disable Actions on the fork.

## Network

- **OK** `server.py:8-18` and `login.py:10-15` import only stdlib (`logging`, `os`, `pathlib`), `telethon`, `mcp`, `dotenv`. No `requests`, `httpx`, `urllib`, `socket`, `subprocess`, `eval`, `exec`, `__import__`, `importlib`, base64 or obfuscated strings anywhere in the repo.
- **OK** The only URLs are human-readable text: `login.py:5`, `login.py:30` (my.telegram.org instructions).
- **OK** `server.py:236` `mcp.run()` uses the default stdio transport; no HTTP listener is opened.
- **OK** Telethon 1.45.0 source checked: network only via its MTProto sender (`telethon/network/`). The only HTTP client is an optional `aiohttp` import in `telethon/client/downloads.py:16` for downloading web documents; `aiohttp` is not installed and that code path is never called. No subprocess/eval/exec.
- **RISK** The `mcp` SDK pulls an HTTP stack (`httpx`, `starlette`, `uvicorn`, `sse-starlette`) for its SSE/HTTP transports and `HttpResource` (`mcp/server/fastmcp/resources/types.py:160`). None of it runs with stdio and no HTTP resource is registered, but it is installed code surface. Accepted: the official SDK hard-depends on it.

## Credentials / session

- **FIX** `server.py:20`, `login.py:17`: `api_id`, `api_hash` and `SESSION_STRING` live in `.env` inside the repo directory. The repo directory here carries a default POSIX ACL granting another local user access, so files created in it inherit that access. Move to `~/.config/telegram-mcp/`.
- **FIX** `login.py:42`: `Path.write_text` with umask `0022` creates `.env` as `0644` (world-readable) plus any inherited ACL. The session string is equivalent to being logged in. Write with `0600` via `os.open(..., O_CREAT|O_EXCL, 0o600)`.
- **FIX** No permission checks anywhere. The server should refuse to start if the config dir, env file or session file is group/other accessible, not owned by the running user, or carries a POSIX ACL. Note `~/.config` itself had a default ACL for another local user on the audit machine, so a plain `mkdir` there would inherit it; the setup must strip it (`setfacl -b`) and the server must detect it.
- **FIX** `server.py:34` `load_dotenv` exports the secrets into `os.environ`, where any child process would inherit them. Parse the file into a local dict instead; this also drops `python-dotenv` as a direct dependency.
- **OK** Secrets are never logged, printed or returned: `server.py:41` names only the missing key; `login.py:40` prints first name and username only.
- **FIX** `server.py:110` `get_me` returns your phone number to the model. Not needed; remove.
- **RISK** `login.py:24` reads `api_id`/`api_hash` with `input()` (echoed on screen). Low impact, but the hardened login will read them only from the env file the user fills in.
- **OK** `.gitignore:2-5` ignores `.env`, `*.session`, `*.session-journal`. Will be extended for the new layout as a safety net.

## Dependencies

- **FIX** `requirements.txt:1-3` is unpinned (`telethon>=1.44`, `mcp>=1.28,<2`, `python-dotenv>=1.0`) with no hashes. Replace with `pyproject.toml` + `uv.lock` (exact versions + sha256 hashes) and a `.venv` in the repo.
- Resolved tree today (Python 3.14), 33 packages. Direct: `telethon`, `mcp`. All are long-established PyPI projects; none look typosquatted.

| Package | Version | Pulled in by | Note |
|---|---|---|---|
| telethon | 1.45.0 | direct | expected |
| pyaes | 1.6.1 | telethon | pure-Python AES fallback; old (2017) but Telethon's official dep |
| rsa | 4.9.1 | telethon | |
| pyasn1 | 0.6.5 | rsa | |
| mcp | 1.30.0 | direct | expected, official SDK |
| anyio | 4.16.0 | mcp | |
| httpx | 0.28.1 | mcp | HTTP transports only |
| httpcore | 1.0.9 | httpx | |
| httpx-sse | 0.4.3 | mcp | |
| h11 | 0.16.0 | httpcore, uvicorn | |
| certifi | 2026.10.23 | httpx | |
| idna | 3.20 | anyio, httpx | |
| starlette | 1.10.0 | mcp | HTTP transports only |
| sse-starlette | 3.7.0 | mcp | HTTP transports only |
| uvicorn | 0.54.0 | mcp | HTTP transports only |
| click | 8.5.1 | uvicorn | |
| python-multipart | 0.0.34 | mcp | |
| pydantic | 2.14.3 | mcp | |
| pydantic-core | 2.50.4 | pydantic | compiled wheel |
| pydantic-settings | 2.16.3 | mcp | |
| python-dotenv | 1.2.4 | pydantic-settings | stays transitive even after removing it as a direct dep |
| annotated-types | 0.8.0 | pydantic | |
| typing-extensions | 4.16.0 | several | |
| typing-inspection | 0.4.5 | mcp, pydantic | |
| jsonschema | 4.26.0 | mcp | |
| jsonschema-specifications | 2025.9.1 | jsonschema | |
| referencing | 0.37.0 | jsonschema | |
| rpds-py | 2026.9.1 | jsonschema | compiled wheel |
| attrs | 26.1.0 | jsonschema | |
| pyjwt | 2.15.1 | mcp | OAuth for HTTP transports |
| cryptography | 50.0.2 | pyjwt | compiled wheel |
| cffi | 2.1.1 | cryptography | |
| pycparser | 3.12 | cffi | |

## Login flow

- **OK** `login.py:37` uses Telethon's interactive terminal login (phone, code, 2FA via `input`/`getpass`). No MCP tool handles login, codes or passwords.
- **OK** `server.py:52-53` only checks `is_user_authorized()` and raises; it never prompts.
- **FIX** Add QR-code login as the preferred path (Telegram → Settings → Devices → Link Desktop Device), with phone login as fallback. 2FA password via `getpass` (not echoed).

## Tools exposed

| Tool | Line | Effect | Tag |
|---|---|---|---|
| `get_me` | `server.py:101` | read; returns phone | **FIX** drop phone |
| `list_chats` | `server.py:114` | read; includes 200-char last message | **FIX** wrap untrusted text |
| `get_history` | `server.py:137` | read | **FIX** wrap untrusted text |
| `search_messages` | `server.py:149` | read | **FIX** wrap untrusted text |
| `search_all` | `server.py:182` | read, global search | **FIX** wrap untrusted text |
| `send_message` | `server.py:217` | **write**, sends immediately, always registered, no confirmation | **FIX** gate behind `TELEGRAM_MCP_ALLOW_SEND=1` + preview/confirm |

- **OK** No edit, delete, join, leave, forward or mark-as-read calls. Nothing calls `send_read_acknowledge`/`mark_read`; `iter_messages`, `iter_dialogs` and `SearchGlobalRequest` do not change read state.
- **FIX** `server.py:71-73` display-name resolution returns the *first* partial match, so "Dev" could silently pick the wrong chat (and with `send_message`, send to it). Must error on ambiguity.
- **FIX** `server.py:66-69` `except Exception: pass` swallows everything from `get_entity`, including `FloodWaitError`.
- **RISK** `get_entity` with a string resolves arbitrary public `@usernames` and `t.me` links via Telegram (read-only lookups, no joins). Acceptable.

## Prompt injection

- **FIX** `server.py:97`, `server.py:130`, `server.py:211`: other people's message text is returned as a bare `text` field, indistinguishable from instructions. Wrap in `<telegram_message>` delimiters, neutralise any delimiter text inside the content, and state in every tool description that the content is untrusted third-party data.

## Errors

- **OK** Exceptions propagate to FastMCP, which returns `str(exc)` to the model. Telethon RPC errors contain the error name and request type, never the auth key or session string. `server.py:40-42` names only the missing variable.
- **RISK** `server.py:23` Telethon logs at WARNING to stderr (Claude Code's MCP log). Telethon does not log secrets at that level. Keep.
- **FIX** No FloodWait handling beyond Telethon's default auto-sleep of up to 60 s. Raise `flood_sleep_threshold` so long catch-up reads sleep and retry instead of failing.
