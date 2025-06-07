import base64
import uuid
from datetime import datetime
from typing import Optional

from supabase import AsyncClient, create_async_client
from utils.config import config
from utils.logger import logger


class DBConnection:
    _instance: Optional["DBConnection"] = None
    _initialized = False
    _client: Optional[AsyncClient] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        pass

    async def initialize(self):
        if self._initialized:
            return

        try:
            supabase_url = config.SUPABASE_URL
            # Use service role key preferentially for backend operations
            supabase_key = config.SUPABASE_SERVICE_ROLE_KEY or config.SUPABASE_ANON_KEY

            if not supabase_url or not supabase_key:
                logger.error(
                    "Missing required environment variables for Supabase connection"
                )
                raise RuntimeError(
                    "SUPABASE_URL and a key (SERVICE_ROLE_KEY or ANON_KEY) environment variables must be set."
                )

            logger.debug("Initializing Supabase connection")
            self._client = await create_async_client(supabase_url, supabase_key)
            self._initialized = True
            key_type = (
                "SERVICE_ROLE_KEY" if config.SUPABASE_SERVICE_ROLE_KEY else "ANON_KEY"
            )
            logger.debug(
                f"Database connection initialized with Supabase using {key_type}"
            )
        except Exception as e:
            logger.error(f"Database initialization error: {e}")
            raise RuntimeError(f"Failed to initialize database connection: {str(e)}")

    @property
    async def client(self) -> AsyncClient:
        if not self._initialized:
            logger.debug("Supabase client not initialized, initializing now")
            await self.initialize()
        if not self._client:
            logger.error("Database client is None after initialization")
            raise RuntimeError("Database not initialized")
        return self._client
