#!/usr/bin/env python3
"""
Telethon Authorization Script - Step 2: Sign in with code
"""

import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

API_ID = int(os.environ.get('TELEGRAM_API_ID', 0))
API_HASH = os.environ.get('TELEGRAM_API_HASH', '')
PHONE = '+380959845497'
CODE = '14483'
SESSION_FILE = ROOT_DIR / 'telethon_session'

async def main():
    print("=== Completing Authorization ===")
    
    client = TelegramClient(str(SESSION_FILE), API_ID, API_HASH)
    await client.connect()
    
    try:
        await client.sign_in(PHONE, CODE)
        me = await client.get_me()
        print(f"\n✅ Successfully authorized as: {me.first_name} (@{me.username})")
        print(f"Session saved!")
        
    except SessionPasswordNeededError:
        print("\n⚠️ Two-factor authentication is enabled.")
        print("Please provide your 2FA password.")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
    
    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
