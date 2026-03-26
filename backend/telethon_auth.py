#!/usr/bin/env python3
"""
Telethon Full Authorization
"""

import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv
from telethon import TelegramClient

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

API_ID = int(os.environ.get('TELEGRAM_API_ID', 0))
API_HASH = os.environ.get('TELEGRAM_API_HASH', '')
PHONE = '+380959845497'
SESSION_FILE = ROOT_DIR / 'telethon_session'

async def main():
    print("=== Telegram Authorization ===")
    
    client = TelegramClient(str(SESSION_FILE), API_ID, API_HASH)
    
    # Start with phone number, will prompt for code
    await client.start(phone=PHONE)
    
    me = await client.get_me()
    print(f"\n✅ Authorized as: {me.first_name} (@{me.username})")
    print(f"Phone: {me.phone}")
    print("Session saved successfully!")
    
    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
