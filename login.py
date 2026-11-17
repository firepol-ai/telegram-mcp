"""One-time interactive Telegram login. Run it yourself, in a terminal:

    .venv/bin/python login.py           # QR code: Telegram → Settings → Devices → Link Desktop Device
    .venv/bin/python login.py --phone   # fallback: phone number + login code

API_ID / API_HASH are read from ~/.config/telegram-mcp/env (fill them in first).
The 2FA password, if any, is read without echo. The session is written to
~/.config/telegram-mcp/session with mode 600. Nothing secret is printed.
"""

import asyncio
import sys
from getpass import getpass

import qrcode
from telethon.errors import SessionPasswordNeededError

import tg_common as tc


def show_qr(url: str) -> None:
    qr = qrcode.QRCode(border=2)
    qr.add_data(url)
    qr.print_ascii(invert=True)
    print("Scan with Telegram → Settings → Devices → Link Desktop Device (code refreshes every ~30 s).")


async def qr_login(client) -> None:
    qr = await client.qr_login()
    while True:
        show_qr(qr.url)
        try:
            await qr.wait(timeout=30)
            return
        except asyncio.TimeoutError:
            await qr.recreate()
        except SessionPasswordNeededError:
            await client.sign_in(password=getpass("2FA password (not echoed): "))
            return


async def phone_login(client) -> None:
    await client.start(
        phone=lambda: input("Phone number (international format, e.g. +44...): "),
        code_callback=lambda: input("Login code sent by Telegram: "),
        password=lambda: getpass("2FA password (not echoed): "),
    )


async def main() -> None:
    tc.check_all()
    client = tc.make_client(tc.read_session())
    await client.connect()
    try:
        if not await client.is_user_authorized():
            await (phone_login(client) if "--phone" in sys.argv else qr_login(client))
        me = await client.get_me()
        tc.write_private(tc.SESSION_FILE, client.session.save())
        print(f"\nLogged in as {me.first_name} (@{me.username}). Session saved to {tc.SESSION_FILE} (mode 600).")
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
