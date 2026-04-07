#!/usr/bin/env python3
"""Telethon auth routes for web-based authorization"""
from fastapi import APIRouter, HTTPException
from pathlib import Path
import os
import logging

logger = logging.getLogger(__name__)
auth_router = APIRouter(prefix="/api/auth")
ROOT_DIR = Path(__file__).parent

_auth_client = None
_auth_phone = None


@auth_router.post("/start")
async def auth_start(data: dict):
    """Step 1: Send phone number to start auth"""
    global _auth_client, _auth_phone
    phone = data.get("phone")
    if not phone:
        raise HTTPException(status_code=400, detail="phone required")
    api_id = int(os.environ.get('TELEGRAM_API_ID', 0))
    api_hash = os.environ.get('TELEGRAM_API_HASH', '')
    if not api_id or not api_hash:
        raise HTTPException(status_code=500, detail="TELEGRAM_API_ID/HASH not set")
    from telethon import TelegramClient
    from telethon.sessions import StringSession
    _auth_client = TelegramClient(StringSession(), api_id, api_hash)
    await _auth_client.connect()
    _auth_phone = phone
    result = await _auth_client.send_code_request(phone)
    logger.info(f"Code sent to {phone}")
    return {"status": "code_sent", "phone": phone}


@auth_router.post("/verify")
async def auth_verify(data: dict):
    """Step 2: Verify SMS code"""
    global _auth_client, _auth_phone
    code = data.get("code")
    password = data.get("password")
    if not code or not _auth_client:
        raise HTTPException(status_code=400, detail="code required or auth not started")
    try:
        await _auth_client.sign_in(_auth_phone, code)
    except Exception as e:
        err = str(e)
        if "password" in err.lower() or "two" in err.lower():
            if password:
                await _auth_client.sign_in(password=password)
            else:
                return {"status": "need_2fa", "message": "2FA required, send password"}
        else:
            raise HTTPException(status_code=400, detail=err)

    from telethon.sessions import StringSession
    session_string = _auth_client.session.save()
    session_path = ROOT_DIR / 'session_string.txt'
    session_path.write_text(session_string)
    logger.info("Telethon authorized successfully!")
    await _auth_client.disconnect()
    return {
        "status": "authorized",
        "session_string": session_string,
        "message": "Authorization successful! Copy SESSION_STRING to Railway variables."
    }


@auth_router.get("/status")
async def auth_status():
    """Check authorization status"""
    session_file = ROOT_DIR / 'telethon_session.session'
    session_str_file = ROOT_DIR / 'session_string.txt'
    env_session = os.environ.get('SESSION_STRING', '')
    return {
        "session_file_exists": session_file.exists(),
        "session_string_saved": session_str_file.exists(),
        "env_session_set": bool(env_session),
        "session_preview": session_str_file.read_text()[:30] + "..." if session_str_file.exists() else None
    }
