#!/usr/bin/env python3
"""
Telethon Step 2 - Sign in with code
"""

import asyncio
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

API_ID = int(os.environ.get('TELEGRAM_API_ID', 0))
API_HASH = os.environ.get('TELEGRAM_API_HASH', '')
PHONE = '+380959845497'
PASSWORD_2FA = '1240Maxim'
SESSION_FILE = ROOT_DIR / 'telethon_session'
HASH_FILE = ROOT_DIR / 'code_hash.txt'

async def main(code):
    # Read saved hash
    with open(HASH_FILE, 'r') as f:
        phone_code_hash = f.read().strip()
    
    client = TelegramClient(str(SESSION_FILE), API_ID, API_HASH)
    await client.connect()
    
    try:
        await client.sign_in(PHONE, code, phone_code_hash=phone_code_hash)
        print("CODE_OK")
    except SessionPasswordNeededError:
        print("2FA_REQUIRED")
        await client.sign_in(password=PASSWORD_2FA)
        print("2FA_OK")
    
    me = await client.get_me()
    print(f"SUCCESS:{me.first_name}:{me.username}")
    
    # Test cvizor_bot access
    try:
        entity = await client.get_entity('@cvizor_bot')
        print(f"BOT_FOUND:{entity.first_name}")
    except Exception as e:
        print(f"BOT_ERROR:{e}")
    
    await client.disconnect()

if __name__ == "__main__":
    code = sys.argv[1] if len(sys.argv) > 1 else ''
    if not code:
        print("ERROR:No code provided")
        sys.exit(1)
    asyncio.run(main(code))
