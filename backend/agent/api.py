import uuid

from services.supabase import DBConnection
from utils.logger import logger


def initialize(_db: DBConnection, _instance_id: str = None):
    global db, instance_id
    db = _db

    if _instance_id:
        instance_id = _instance_id
    else:
        instance_id = str(uuid.uuid4())[:8]

    logger.info(f"Initialized agent API with instance ID: {instance_id}")
