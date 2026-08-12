#!/usr/bin/env python3
"""
🔐 Generate Telethon String Session
Run this ONCE locally or on Railway to login.
Saves session string to a file.
"""

import asyncio, os

API_ID = int(os.environ.get("TELEGRAM_API_ID", "35812449"))
API_HASH = os.environ.get("TELEGRAM_API_HASH", "099cfed535a5b2dcd8e43f157d30e3ce")

async def main():
    from telethon import TelegramClient
    from telethon.sessions import StringSession
    
    print("=" * 50)
    print("🔐 Telegram Login — String Session Generator")
    print("=" * 50)
    
    client = TelegramClient(StringSession(), API_ID, API_HASH)
    await client.connect()
    
    if not await client.is_user_authorized():
        phone = input("\n📱 Phone (with country code): ")
        await client.send_code_request(phone)
        code = input("📲 OTP: ")
        try:
            await client.sign_in(phone, code)
        except Exception as e:
            if "password" in str(e).lower():
                pwd = input("🔒 2FA password: ")
                await client.sign_in(password=pwd)
            else:
                raise
    
    me = await client.get_me()
    session_str = client.session.save()
    
    print(f"\n✅ Logged in as: {me.first_name} (@{me.username or 'N/A'}) [ID: {me.id}]")
    print(f"\n📋 YOUR SESSION STRING:")
    print("=" * 50)
    print(session_str)
    print("=" * 50)
    print(f"\nSet as TELEGRAM_SESSION env var on Railway")
    
    await client.disconnect()

asyncio.run(main())
