#!/usr/bin/env python3
"""
Telethon Authorization Script - Step 1: Send code request
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
SESSION_FILE = ROOT_DIR / 'telethon_session'

async def main():
    print("=== Telegram Authorization ===")
    print(f"Phone: {PHONE}")
    
    client = TelegramClient(str(SESSION_FILE), API_ID, API_HASH)
    await client.connect()
    
    if not await client.is_user_authorized():
        print("Sending code request...")
        await client.send_code_request(PHONE)
        print("\n✅ Code sent to your Telegram!")
        print("Check your Telegram app for the code.")
        
        # Save client state
        print("\nWaiting for code...")
    else:
        me = await client.get_me()
        print(f"\n✅ Already authorized as: {me.first_name}")
    
    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
