#!/usr/bin/env python3
"""
Tradium Signal Monitor v2
Reads trade setups from Tradium [WORKSPACE] topic 3204
AI extracts DCA #4 level from chart images
Saves silently — no notifications
"""


import asyncio
import os
import re
import json
import logging
import base64
import shutil
from datetime import datetime, timezone
from pathlib import Path


from dotenv import load_dotenv
from telethon import TelegramClient, events


from openai import AsyncOpenAI


from motor.motor_asyncio import AsyncIOMotorClient


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env', override=True)


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Config
API_ID = int(os.environ.get('TELEGRAM_API_ID', 0))
