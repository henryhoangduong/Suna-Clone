import os
import uuid

from services import redis
from services.supabase import DBConnection
from utils.logger import logger
from typing import Optional
from dramatiq.brokers.rabbitmq import RabbitmqBroker
import dramatiq
from dotenv import load_dotenv
load_dotenv()
rabbitmq_host = os.getenv('RABBITMQ_HOST', 'localhost')
rabbitmq_port = int(os.getenv('RABBITMQ_PORT', 5672))
rabbitmq_broker = RabbitmqBroker(host=rabbitmq_host, port=rabbitmq_port, middleware=[
                                 dramatiq.middleware.AsyncIO()])
dramatiq.set_broker(rabbitmq_broker)
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


@dramatiq.actor
async def run_agent_background(
    agent_run_id: str,
    thread_id: str,
    instance_id: str,  # Use the global instance ID passed during initialization
    project_id: str,
    model_name: str,
    enable_thinking: Optional[bool],
    reasoning_effort: Optional[str],
    stream: bool,
    enable_context_manager: bool,
    agent_config: Optional[dict] = None,
    is_agent_builder: Optional[bool] = False,
    target_agent_id: Optional[str] = None
):
    try:
        await initialize()
    except Exception as e:
        logger.critical(f"Failed to initialize Redis connection: {e}")
        raise e
