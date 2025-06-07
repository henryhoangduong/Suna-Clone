import asyncio
import os
from typing import Any, List

import redis.asyncio as redis
from dotenv import load_dotenv

from utils.logger import logger

client: redis.Redis | None = None
_initialized = False
_init_lock = asyncio.Lock()
REDIS_KEY_TTL = 3600 * 24


def initialize():
    global client
    load_dotenv()

    redis_host = os.getenv("REDIS_HOST", "redis")
    redis_port = int(os.getenv("REDIS_PORT", 6379))
    redis_password = os.getenv("REDIS_PASSWORD", "")
    redis_ssl_str = os.getenv("REDIS_SSL", "False")
    redis_ssl = redis_ssl_str.lower() == "true"

    logger.info(f"Initializing Redis connection to {redis_host}:{redis_port}")

    # Create Redis client with basic configuration
    client = redis.Redis(
        host=redis_host,
        port=redis_port,
        password=redis_password,
        ssl=redis_ssl,
        decode_responses=True,
        socket_timeout=5.0,
        socket_connect_timeout=5.0,
        retry_on_timeout=True,
        health_check_interval=30,
    )

    return client


async def initialize_async(force: bool = False):
    global client, _initialized
    async with _init_lock:
        if _initialized and force:
            logger.info(
                "Redis connection already initialized, closing and re-initializing"
            )
            _initialized = False
            try:
                await close()
            except Exception as e:
                logger.warning(
                    f"Failed to close Redis connection, proceeding with re-initialization anyway: {e}"
                )
        if not _initialized:
            logger.info("Initializing Redis connection")
            initialize()

            try:
                await client.ping()
                logger.info("Successfully connected to Redis")
                _initialized = True
            except Exception as e:
                logger.error(f"Failed to connect to Redis: {e}")
                client = None
                raise


async def close():
    global client, _initialized
    if client:
        logger.info("Closing Redis connection")
        await client.aclose()
        client = None
        _initialized = False
        logger.info("Redis connection closed")
