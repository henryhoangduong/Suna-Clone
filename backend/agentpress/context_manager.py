import json
from typing import List, Dict, Any, Optional

from litellm import token_counter, completion_cost
from services.supabase import DBConnection
from services.llm import make_llm_api_call
from utils.logger import logger

DEFAULT_TOKEN_THRESHOLD = 120000  # 80k tokens threshold for summarization
SUMMARY_TARGET_TOKENS = 10000    # Target ~10k tokens for the summary message
RESERVE_TOKENS = 5000            # Reserve tokens for new messages


class ContextManager:
    """Manages thread context including token counting and summarization."""

    def __init__(self, token_threshold: int = DEFAULT_TOKEN_THRESHOLD):
        """Initialize the ContextManager.

        Args:
            token_threshold: Token count threshold to trigger summarization
        """
        self.db = DBConnection()
        self.token_threshold = token_threshold

    async def get_thread_token_count(self, thread_id: str) -> int:
        logger.debug(f"Getting token count for thread {thread_id}")
        try:
            messages = await self.get_messages_for_summarization(thread_id)

            if not messages:
                logger.debug(f"No messages found for thread {thread_id}")
                return 0

            token_count = token_counter(model="gpt-4", messages=messages)

            logger.info(
                f"Thread {thread_id} has {token_count} tokens (calculated with litellm)")
            return token_count
        except Exception as e:
            logger.error(f"Error getting token count: {str(e)}")
            return 0
