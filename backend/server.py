from fastapi import FastAPI, APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone, timedelta
import asyncio
import re
import json
import ccxt
import pandas as pd
import ta
from openai import AsyncOpenAI
from auth_routes import auth_router


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env', override=True)


INSTANCE_ID = str(uuid.uuid4())[:8]
LEADER_TTL = 45


mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]


exchange = ccxt.kraken({'enableRateLimit': True})


app = FastAPI()
api_router = APIRouter(prefix="/api")


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
