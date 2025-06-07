import os
import urllib.parse
from typing import Optional

from fastapi import APIRouter

from services.supabase import DBConnection
from utils.logger import logger

router = APIRouter(tags=["sandbox"])
db = None


def initialize(_db: DBConnection):
    """Initialize the sandbox API with resources from the main API."""
    global db
    db = _db
    logger.info("Initialized sandbox API with database connection")
