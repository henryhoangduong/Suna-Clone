import uuid

from services import redis
from services.supabase import DBConnection
from utils.logger import logger

_initialized = False
db = DBConnection()
instance_id = "single"


async def initialize():
    """Initialize the agent API with resources from the main API."""
    global db, instance_id, _initialized
    if _initialized:
        try:
            await redis.client.ping()
        except Exception as e:
            logger.warning(f"Redis connection failed, re-initializing: {e}")
            await redis.initialize_async(force=True)
        return
    if not instance_id:
        # Generate instance ID
        instance_id = str(uuid.uuid4())[:8]
    await redis.initialize_async()
    await db.initialize()

    _initialized = True
    logger.info(f"Initialized agent API with instance ID: {instance_id}")
