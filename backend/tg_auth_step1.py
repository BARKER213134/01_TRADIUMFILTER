#!/usr/bin/env python3
"""Telethon auth - step 1: send code"""
import asyncio
from pathlib import Path
from dotenv import load_dotenv
import os
from telethon import TelegramClient

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env', override=True)

API_ID = int(os.environ.get('TELEGRAM_API_ID', 0))
API_HASH = os.environ.get('TELEGRAM_API_HASH', '')
PHONE = '+380959845497'
SESSION = ROOT_DIR / 'telethon_session'

async def main():
    client = TelegramClient(str(SESSION), API_ID, API_HASH)
    await client.connect()
    
    if await client.is_user_authorized():
        me = await client.get_me()
        print(f"ALREADY AUTHORIZED: {me.first_name} {me.phone}")
        await client.disconnect()
        return
    
    result = await client.send_code_request(PHONE)
    print(f"CODE SENT! phone_code_hash={result.phone_code_hash}")
    
    # Save hash for step 2
    with open('/tmp/tg_hash.txt', 'w') as f:
        f.write(result.phone_code_hash)
    
    await client.disconnect()
    print("Now run step 2 with the OTP code")

asyncio.run(main())
