#!/usr/bin/env python3
"""
Telethon Authorization Script
Run this once to authorize and create session file
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
SESSION_FILE = ROOT_DIR / 'telethon_session'

async def main():
    print("=== Telegram Authorization ===")
    print(f"API ID: {API_ID}")
    print(f"Session file: {SESSION_FILE}")
    print()
    
    client = TelegramClient(str(SESSION_FILE), API_ID, API_HASH)
    
    await client.start()
    
    me = await client.get_me()
    print(f"\n✅ Authorized as: {me.first_name} (@{me.username})")
    print(f"Phone: {me.phone}")
    print(f"\nSession saved to: {SESSION_FILE}.session")
    
    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
