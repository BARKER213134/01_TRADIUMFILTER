#!/usr/bin/env python3
"""
Telethon Step 1 - Request code only
"""

import asyncio
import os
import json
from pathlib import Path
from dotenv import load_dotenv
from telethon import TelegramClient

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

API_ID = int(os.environ.get('TELEGRAM_API_ID', 0))
API_HASH = os.environ.get('TELEGRAM_API_HASH', '')
PHONE = '+380959845497'
SESSION_FILE = ROOT_DIR / 'telethon_session'
HASH_FILE = ROOT_DIR / 'code_hash.txt'

async def main():
    client = TelegramClient(str(SESSION_FILE), API_ID, API_HASH)
    await client.connect()
    
    if await client.is_user_authorized():
        me = await client.get_me()
        print(f"ALREADY_AUTHORIZED:{me.first_name}")
        await client.disconnect()
        return
    
    sent = await client.send_code_request(PHONE)
    
    # Save hash for step 2
    with open(HASH_FILE, 'w') as f:
        f.write(sent.phone_code_hash)
    
    print(f"CODE_SENT:{sent.phone_code_hash}")
    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
