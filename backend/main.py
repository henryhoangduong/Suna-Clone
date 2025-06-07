import logging
import sys
from collections import OrderedDict
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agent import api as agent_api
from sandbox import api as sandbox_api
from services.supabase import DBConnection
from utils.config import config

db = DBConnection()

logger = logging.getLogger(__name__)
load_dotenv()
instance_id = "single"
ip_tracker = OrderedDict()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        f"Starting up FastAPI application with instance ID: {instance_id} in {config.ENV_MODE.value} mode"
    )
    try:
        await db.initialize()
        agent_api.initialize(db, instance_id)
        sandbox_api.initialize(db)
        from services import redis
        try:
            await redis.initialize_async()
            logger.info("Redis connection initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Redis connection: {e}")
        yield
    except Exception as e:
        logger.error(f"Error during application startup: {e}")
        raise


allowed_origins = ["https://www.suna.so",
                   "https://suna.so", "http://localhost:3000"]
allow_origin_regex = None

app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=allow_origin_regex,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)
if __name__ == "__main__":
    import uvicorn

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    workers = 1

    logger.info(f"Starting server on 0.0.0.0:8000 with {workers} workers")
    uvicorn.run("api:app", host="0.0.0.0", port=8000,
                workers=workers, loop="asyncio")
