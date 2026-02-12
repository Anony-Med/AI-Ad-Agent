"""Anthropic API client for the agentic orchestrator."""
import logging
from typing import List, Dict, Any, Optional
import anthropic
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)


class AnthropicClient:
    """
    Async client for Anthropic Messages API with tool use support.

    Used by the agentic orchestrator to communicate with Claude,
    which acts as the decision-making agent for ad creation.
    """

    def __init__(
        self,
        api_key: str,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
    ):
        """
        Initialize the Anthropic client.

        Args:
            api_key: Anthropic API key
            model: Claude model to use (defaults to settings.ANTHROPIC_MODEL)
            max_tokens: Maximum tokens in Claude's response
        """
        from app.config import settings
        self.client = anthropic.AsyncAnthropic(api_key=api_key)
        self.model = model or settings.ANTHROPIC_MODEL
        self.max_tokens = max_tokens or settings.ANTHROPIC_MAX_TOKENS

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=30),
        retry=retry_if_exception_type((
            anthropic.RateLimitError,
            anthropic.InternalServerError,
            anthropic.APIConnectionError,
        )),
        before_sleep=lambda retry_state: logger.warning(
            f"Anthropic API retry attempt {retry_state.attempt_number}: {retry_state.outcome.exception()}"
        ),
    )
    async def create_message(
        self,
        messages: List[Dict[str, Any]],
        system: str,
        tools: List[Dict[str, Any]],
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
    ) -> anthropic.types.Message:
        """
        Send a message to Claude with tool definitions.

        Args:
            messages: Conversation history (user/assistant/tool_result messages)
            system: System instruction for the agent
            tools: Tool definitions (Anthropic tool schema format)
            model: Override model for this call
            max_tokens: Override max_tokens for this call

        Returns:
            Anthropic Message object with content blocks (text and/or tool_use)
        """
        response = await self.client.messages.create(
            model=model or self.model,
            max_tokens=max_tokens or self.max_tokens,
            system=system,
            tools=tools,
            messages=messages,
        )

        logger.debug(
            f"Anthropic API response: stop_reason={response.stop_reason}, "
            f"usage=input={response.usage.input_tokens}/output={response.usage.output_tokens}"
        )

        return response
