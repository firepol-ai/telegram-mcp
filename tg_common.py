"""Config, secrets and permission checks shared by server.py and login.py.

Secrets live in one private directory (default ~/.config/telegram-mcp/), shared by all agents:

    env           API_ID / API_HASH, filled in by hand        mode 600
    session       Telethon StringSession, written by login.py mode 600

Per-agent settings live in the agent's workspace (TELEGRAM_MCP_WORKSPACE, set in the local MCP
registration of that folder):

    telegram.toml          allowed chats, send allowlist, signature, rate limit
    .telegram-state.json   poll_new() cursors (written by the server, mode 600)

Without a workspace the server is unrestricted read-only and cannot send.

Secrets are parsed into a dict and never put into os.environ.
"""

import json
import os
import stat
import tomllib
from pathlib import Path

from telethon import TelegramClient
from telethon.sessions import StringSession

CONFIG_DIR = Path(os.environ.get("TELEGRAM_MCP_CONFIG_DIR", "~/.config/telegram-mcp")).expanduser()
ENV_FILE = CONFIG_DIR / "env"
SESSION_FILE = CONFIG_DIR / "session"
_ws = os.environ.get("TELEGRAM_MCP_WORKSPACE")
WORKSPACE = Path(_ws).expanduser().resolve() if _ws else None
CONFIG_FILE = WORKSPACE / "telegram.toml" if WORKSPACE else None
STATE_FILE = WORKSPACE / ".telegram-state.json" if WORKSPACE else None

# Sleep through FloodWait errors up to this many seconds instead of failing.
FLOOD_SLEEP_SECONDS = 600

_ACL_XATTRS = ("system.posix_acl_access", "system.posix_acl_default")


class InsecureConfig(RuntimeError):
    pass


def check_private(path: Path, forbidden_bits: int = 0o077) -> None:
    """Refuse a path that other users could access: wrong owner, forbidden group/other bits, or a POSIX ACL.

    forbidden_bits 0o077 = nobody else may read or write (secrets); 0o022 = nobody else may write (policy).
    """
    st = path.stat()
    problems = []
    if st.st_uid != os.geteuid():
        problems.append(f"owned by uid {st.st_uid}, not {os.geteuid()}")
    if st.st_mode & forbidden_bits:
        problems.append(f"mode {stat.filemode(st.st_mode)} has group/other bits")
    try:
        acls = [a for a in os.listxattr(path) if a in _ACL_XATTRS]
    except OSError:
        acls = []  # filesystem without xattr support: mode bits are authoritative
    if acls:
        problems.append("has a POSIX ACL")
    if problems:
        want = ("700" if path.is_dir() else "600") if forbidden_bits == 0o077 else "go-w"
        raise InsecureConfig(
            f"Refusing to use {path}: {'; '.join(problems)}. "
            f"Fix with: setfacl -b {path}; chmod {want} {path}"
        )


def check_all() -> None:
    """Check the config dir and every private file that exists in it."""
    if not CONFIG_DIR.is_dir():
        raise InsecureConfig(f"{CONFIG_DIR} does not exist. See README → Setup.")
    check_private(CONFIG_DIR)
    if not ENV_FILE.is_file():
        raise InsecureConfig(f"{ENV_FILE} does not exist. See README → Setup.")
    for path in (ENV_FILE, SESSION_FILE):
        if path.exists():
            check_private(path)
    if WORKSPACE:
        if not CONFIG_FILE.is_file():
            raise InsecureConfig(f"TELEGRAM_MCP_WORKSPACE is set but {CONFIG_FILE} does not exist.")
        # The allowlist is enforced by the server, so nobody else may be able to change it.
        check_private(WORKSPACE, 0o022)
        check_private(CONFIG_FILE, 0o022)
        if STATE_FILE.exists():
            check_private(STATE_FILE)


def load_env() -> dict[str, str]:
    """Parse KEY=VALUE lines. Comments and blank lines are ignored."""
    values = {}
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip("'\"")
    return values


def load_config() -> dict:
    if not CONFIG_FILE:
        return {}
    with CONFIG_FILE.open("rb") as f:
        return tomllib.load(f)


def write_private(path: Path, text: str) -> None:
    """Atomically write a mode-600 file (never briefly readable by others)."""
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.unlink(missing_ok=True)
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def read_session() -> str:
    return SESSION_FILE.read_text(encoding="utf-8").strip() if SESSION_FILE.exists() else ""


def load_state() -> dict:
    return json.loads(STATE_FILE.read_text(encoding="utf-8")) if STATE_FILE.exists() else {}


def save_state(state: dict) -> None:
    write_private(STATE_FILE, json.dumps(state, indent=1, sort_keys=True))


def make_client(session: str) -> TelegramClient:
    env = load_env()
    try:
        api_id = int(env["API_ID"])
        api_hash = env["API_HASH"]
    except (KeyError, ValueError) as e:
        raise RuntimeError(f"API_ID / API_HASH missing or invalid in {ENV_FILE}.") from e
    if not api_hash:
        raise RuntimeError(f"API_HASH is empty in {ENV_FILE}.")
    return TelegramClient(
        StringSession(session), api_id, api_hash, flood_sleep_threshold=FLOOD_SLEEP_SECONDS
    )
