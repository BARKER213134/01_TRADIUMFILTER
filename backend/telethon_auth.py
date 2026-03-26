#!/usr/bin/env python3
"""
Telethon Full Authorization with 2FA - programmatic code input
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
CODE = os.environ.get('TG_CODE', '')
PASSWORD_2FA = '1240Maxim'
SESSION_FILE = ROOT_DIR / 'telethon_session'

async def main():
    print("=== Telegram Authorization ===")
    print(f"Code: {CODE}")
    
    client = TelegramClient(str(SESSION_FILE), API_ID, API_HASH)
    await client.connect()
    
    if not await client.is_user_authorized():
        print("Sending code request...")
        sent = await client.send_code_request(PHONE)
        print(f"Code sent! Hash: {sent.phone_code_hash[:10]}...")
        
        if CODE:
            try:
                await client.sign_in(PHONE, CODE, phone_code_hash=sent.phone_code_hash)
                print("Signed in with code!")
            except SessionPasswordNeededError:
                print("2FA required, entering password...")
                await client.sign_in(password=PASSWORD_2FA)
                print("2FA passed!")
        else:
            print("\n⚠️ No code provided. Set TG_CODE environment variable.")
            await client.disconnect()
            return
    
    me = await client.get_me()
    print(f"\n✅ Authorized as: {me.first_name} (@{me.username})")
    print("Session saved!")
    
    # Test cvizor_bot
    try:
        entity = await client.get_entity('@cvizor_bot')
        print(f"✅ Found: {entity.first_name}")
    except Exception as e:
        print(f"⚠️ cvizor_bot: {e}")
    
    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
