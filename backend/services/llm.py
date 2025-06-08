import asyncio
import json
import os
from typing import Any, AsyncGenerator, Dict, List, Optional, Union

import litellm
from openai import OpenAIError

from utils.config import config
from utils.logger import logger

# litellm.set_verbose=True
litellm.modify_params = True
MAX_RETRIES = 2
RATE_LIMIT_DELAY = 30
RETRY_DELAY = 0.1


class LLMError(Exception):
    pass


class LLMRetryError(LLMError):
    pass


def setup_api_keys() -> None:
    providers = ["OPENAI", "ANTHROPIC", "GROQ", "OPENROUTER"]
    for provider in providers:
        key = getattr(config, f"{provider}_API_KEY")
        if key:
            logger.debug(f"API key set for provider: {provider}")
        else:
            logger.warning(f"No API key found for provider: {provider}")

    if config.OPENROUTER_API_KEY and config.OPENROUTER_API_BASE:
        os.environ["OPENROUTER_API_BASE"] = config.OPENROUTER_API_BASE
        logger.debug(f"Set OPENROUTER_API_BASE to {config.OPENROUTER_API_BASE}")
    aws_access_key = config.AWS_ACCESS_KEY_ID
    aws_secret_key = config.AWS_SECRET_ACCESS_KEY
    aws_region = config.AWS_REGION_NAME
    if aws_access_key and aws_secret_key and aws_region:
        logger.debug(f"AWS credentials set for Bedrock in region: {aws_region}")
        os.environ["AWS_ACCESS_KEY_ID"] = aws_access_key
        os.environ["AWS_SECRET_ACCESS_KEY"] = aws_secret_key
        os.environ["AWS_REGION_NAME"] = aws_region
    else:
        logger.warning(
            f"Missing AWS credentials for Bedrock integration - access_key: {bool(aws_access_key)}, secret_key: {bool(aws_secret_key)}, region: {aws_region}"
        )


async def handle_error(error: Exception, attempt: int, max_attempts: int) -> None:
    delay = (
        RATE_LIMIT_DELAY
        if isinstance(error, litellm.exceptions.RateLimitError)
        else RETRY_DELAY
    )
    logger.warning(f"Error on attempt {attempt + 1}/{max_attempts}: {str(error)}")
    logger.debug(f"Waiting {delay} seconds before retry...")
    await asyncio.sleep(delay)


def prepare_params(
    messages: List[Dict[str, Any]],
    model_name: str,
    temperature: float = 0,
    max_tokens: Optional[int] = None,
    response_format: Optional[Any] = None,
    tools: Optional[List[Dict[str, Any]]] = None,
    tool_choice: str = "auto",
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    stream: bool = False,
    top_p: Optional[float] = None,
    model_id: Optional[str] = None,
    enable_thinking: Optional[bool] = False,
    reasoning_effort: Optional[str] = "low",
):

    params = {
        "model": model_name,
        "messages": messages,
        "temperature": temperature,
        "response_format": response_format,
        "top_p": top_p,
        "stream": stream,
    }
    if api_key:
        params["api_key"] = api_key
    if api_base:
        params["api_base"] = api_base
    if model_id:
        params["model_id"] = model_id
    if max_tokens is not None:
        if model_name.startswith("bedrock/") and "claude-3-7" in model_name:
            logger.debug(f"Skipping max_tokens for Claude 3.7 model: {model_name}")
        else:
            param_name = "max_completion_tokens" if "o1" in model_name else "max_tokens"
            params[param_name] = max_tokens
    if tools:
        params.update({"tools": tools, "tool_choice": tool_choice})
        logger.debug(f"Added {len(tools)} tools to API parameters")
    if "claude" in model_name.lower() or "anthropic" in model_name.lower():
        params["extra_headers"] = {
            # "anthropic-beta": "max-tokens-3-5-sonnet-2024-07-15"
            "anthropic-beta": "output-128k-2025-02-19"
        }
        logger.debug("Added Claude-specific headers")
    if model_name.startswith("openrouter/"):
        logger.debug(f"Preparing OpenRouter parameters for model: {model_name}")
        site_url = config.OR_SITE_URL
        app_name = config.OR_APP_NAME
        if site_url or app_name:
            extra_headers = params.get("extra_headers", {})
            if site_url:
                extra_headers["HTTP-Referer"] = site_url
            if app_name:
                extra_headers["X-Title"] = app_name
            params["extra_headers"] = extra_headers
            logger.debug(f"Added OpenRouter site URL and app name to headers")
    if model_name.startswith("bedrock/"):
        logger.debug(f"Preparing AWS Bedrock parameters for model: {model_name}")

        if not model_id and "anthropic.claude-3-7-sonnet" in model_name:
            params["model_id"] = (
                "arn:aws:bedrock:us-west-2:935064898258:inference-profile/us.anthropic.claude-3-7-sonnet-20250219-v1:0"
            )
            logger.debug(
                f"Auto-set model_id for Claude 3.7 Sonnet: {params['model_id']}"
            )
    # Use model from params if set, else original
    effective_model_name = params.get("model", model_name)
    if (
        "claude" in effective_model_name.lower()
        or "anthropic" in effective_model_name.lower()
    ):
        messages = params["messages"]
        if not isinstance(messages, list):
            return params
        if messages and messages[0].get("role") == "system":
            content = messages[0].get("content")
            if isinstance(content, str):
                messages[0]["content"] = [
                    {
                        "type": "text",
                        "text": content,
                        "cache_control": {"type": "ephemeral"},
                    }
                ]
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        if "cache_control" not in item:
                            item["cache_control"] = {"type": "ephemeral"}
                            break  # Apply to the first text block only for system prompt
        last_user_idx = -1
        second_last_user_idx = -1
        last_assistant_idx = -1
        for i in range(len(messages) - 1, -1, -1):
            role = messages[i].get("role")
            if role == "user":
                if last_user_idx == -1:
                    last_user_idx = i
                elif second_last_user_idx == -1:
                    second_last_user_idx = i
            elif role == "assistant":
                if last_assistant_idx == -1:
                    last_assistant_idx = i

            if (
                last_user_idx != -1
                and second_last_user_idx != -1
                and last_assistant_idx != -1
            ):
                break

        def apply_cache_control(message_idx: int, message_role: str):
            if message_idx == -1:
                return

            message = messages[message_idx]
            content = message.get("content")

            if isinstance(content, str):
                message["content"] = [
                    {
                        "type": "text",
                        "text": content,
                        "cache_control": {"type": "ephemeral"},
                    }
                ]
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        if "cache_control" not in item:
                            item["cache_control"] = {"type": "ephemeral"}

        apply_cache_control(last_user_idx, "last user")
        apply_cache_control(second_last_user_idx, "second last user")
        apply_cache_control(last_assistant_idx, "last assistant")
    use_thinking = enable_thinking if enable_thinking is not None else False
    is_anthropic = (
        "anthropic" in effective_model_name.lower()
        or "claude" in effective_model_name.lower()
    )

    if is_anthropic and use_thinking:
        effort_level = reasoning_effort if reasoning_effort else "low"
        params["reasoning_effort"] = effort_level
        # Required by Anthropic when reasoning_effort is used
        params["temperature"] = 1.0
        logger.info(
            f"Anthropic thinking enabled with reasoning_effort='{effort_level}'"
        )

    return params


async def make_llm_api_call(
    messages: List[Dict[str, Any]],
    model_name: str,
    response_format: Optional[Any] = None,
    temperature: float = 0,
    max_tokens: Optional[int] = None,
    tools: Optional[List[Dict[str, Any]]] = None,
    tool_choice: str = "auto",
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    stream: bool = False,
    top_p: Optional[float] = None,
    model_id: Optional[str] = None,
    enable_thinking: Optional[bool] = False,
    reasoning_effort: Optional[str] = "low",
) -> Union[Dict[str, Any], AsyncGenerator]:
    logger.info(
        f"Making LLM API call to model: {model_name} (Thinking: {enable_thinking}, Effort: {reasoning_effort})"
    )
    logger.info(f"📡 API Call: Using model {model_name}")
    params = prepare_params(
        messages=messages,
        model_name=model_name,
        temperature=temperature,
        max_tokens=max_tokens,
        response_format=response_format,
        tools=tools,
        tool_choice=tool_choice,
        api_key=api_key,
        api_base=api_base,
        stream=stream,
        top_p=top_p,
        model_id=model_id,
        enable_thinking=enable_thinking,
        reasoning_effort=reasoning_effort,
    )
    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            logger.debug(f"Attempt {attempt + 1}/{MAX_RETRIES}")

            response = await litellm.acompletion(**params)
            logger.debug(f"Successfully received API response from {model_name}")
            logger.debug(f"Response: {response}")
            return response

        except (
            litellm.exceptions.RateLimitError,
            OpenAIError,
            json.JSONDecodeError,
        ) as e:
            last_error = e
            await handle_error(e, attempt, MAX_RETRIES)

        except Exception as e:
            logger.error(f"Unexpected error during API call: {str(e)}", exc_info=True)
            raise LLMError(f"API call failed: {str(e)}")

    error_msg = f"Failed to make API call after {MAX_RETRIES} attempts"
    if last_error:
        error_msg += f". Last error: {str(last_error)}"
    logger.error(error_msg, exc_info=True)
    raise LLMRetryError(error_msg)


setup_api_keys()
