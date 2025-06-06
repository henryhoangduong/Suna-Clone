import logging
from collections import OrderedDict
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from utils.config import config
import sys
logger = logging.getLogger(__name__)
load_dotenv()
instance_id = "single"
ip_tracker = OrderedDict()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        f"Starting up FastAPI application with instance ID: {instance_id} in {config.ENV_MODE.value} mode"
    )

app = FastAPI(lifespan=lifespan)
if __name__ == "__main__":
    import uvicorn

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    workers = 1

    logger.info(f"Starting server on 0.0.0.0:8000 with {workers} workers")
    uvicorn.run(
        "api:app",
        host="0.0.0.0",
        port=8000,
        workers=workers,
        loop="asyncio"
    )
