"""Smoke test: start the server against a throwaway config and list its tools. No Telegram login needed.

    .venv/bin/python tests/smoke.py

Checks that:
  - without TELEGRAM_MCP_ALLOW_SEND no write tool is registered,
  - with TELEGRAM_MCP_ALLOW_SEND=1 only preview_message and send_message are added,
  - the server refuses to start when the env file or config dir is readable by others.
"""

import asyncio
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parent.parent
SERVER = str(ROOT / "server.py")
READ_TOOLS = {
    "get_me", "list_chats", "list_unread", "get_history", "get_unread",
    "get_since", "get_mentions", "search_messages", "search_all", "poll_new",
}
WRITE_TOOLS = {"preview_message", "send_message"}


def base_env(config_dir: Path) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith("TELEGRAM_MCP_")}
    env["TELEGRAM_MCP_CONFIG_DIR"] = str(config_dir)
    return env


async def list_tools(env: dict) -> dict:
    params = StdioServerParameters(command=sys.executable, args=[SERVER], env=env)
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        return {t.name: t.description for t in (await session.list_tools()).tools}


def refuses_with(env: dict, needle: str) -> bool:
    r = subprocess.run([sys.executable, SERVER], env=env, input="", capture_output=True, text=True, timeout=30)
    return r.returncode != 0 and needle in r.stderr


def refuses(env: dict) -> bool:
    return refuses_with(env, "Refusing")


async def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        cfg = Path(tmp) / "telegram-mcp"
        cfg.mkdir(mode=0o700)
        os.chmod(cfg, 0o700)
        env_file = cfg / "env"
        env_file.write_text("API_ID=1\nAPI_HASH=dummy\n")
        os.chmod(env_file, 0o600)
        subprocess.run(["setfacl", "-b", str(cfg), str(env_file)], check=False, capture_output=True)
        env = base_env(cfg)

        tools = await list_tools(env)
        assert set(tools) == READ_TOOLS, f"read-only tool set wrong: {sorted(tools)}"
        assert all("untrusted" in d.lower() or "third-party" in d.lower() for d in tools.values()), \
            "every read tool must warn about untrusted content"
        print(f"ok  read-only by default: {len(tools)} tools, no write tools")

        tools = await list_tools({**env, "TELEGRAM_MCP_ALLOW_SEND": "1"})
        assert set(tools) == READ_TOOLS | WRITE_TOOLS, f"send-enabled tool set wrong: {sorted(tools)}"
        print("ok  TELEGRAM_MCP_ALLOW_SEND=1 adds only preview_message and send_message")

        os.chmod(env_file, 0o640)
        assert refuses(env), "server must refuse a group-readable env file"
        os.chmod(env_file, 0o600)
        os.chmod(cfg, 0o750)
        assert refuses(env), "server must refuse a group-accessible config dir"
        os.chmod(cfg, 0o700)
        acl = subprocess.run(["setfacl", "-m", f"u:{os.getuid()}:r", str(env_file)], capture_output=True)
        if acl.returncode == 0:
            assert refuses(env), "server must refuse an env file with a POSIX ACL"
            subprocess.run(["setfacl", "-b", str(env_file)], check=True)
        print("ok  refuses to start with loose permissions" + ("" if acl.returncode == 0 else " (ACL case skipped: no setfacl)"))

        ws = Path(tmp) / "agent"
        ws.mkdir()
        os.chmod(ws, 0o755)
        subprocess.run(["setfacl", "-b", str(ws)], check=False, capture_output=True)
        ws_env = {**env, "TELEGRAM_MCP_WORKSPACE": str(ws), "TELEGRAM_MCP_ALLOW_SEND": "1"}
        assert refuses_with(ws_env, "does not exist"), "workspace without telegram.toml must be refused"
        toml = ws / "telegram.toml"
        toml.write_text('[[chats]]\nchat = "@example"\nsend = true\n')
        os.chmod(toml, 0o644)
        subprocess.run(["setfacl", "-b", str(toml)], check=False, capture_output=True)
        tools = await list_tools(ws_env)
        assert set(tools) == READ_TOOLS | WRITE_TOOLS, f"workspace tool set wrong: {sorted(tools)}"
        os.chmod(toml, 0o664)
        assert refuses(ws_env), "server must refuse a group-writable telegram.toml"
        os.chmod(toml, 0o644)
        os.chmod(ws, 0o775)
        assert refuses(ws_env), "server must refuse a group-writable workspace"
        os.chmod(ws, 0o755)
        print("ok  workspace: telegram.toml required, refused when others can modify it")
    print("smoke test passed")


if __name__ == "__main__":
    asyncio.run(main())
