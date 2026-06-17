import json
import time
from typing import Any, AsyncGenerator, Callable, Optional

import httpx
import structlog
from pydantic import BaseModel

logger = structlog.get_logger(__name__)


class CircuitBreakerError(Exception):
    """Exception raised when the circuit breaker is open."""
    pass


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 60.0) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.state = 0  # 0 = CLOSED, 1 = OPEN, 2 = HALF_OPEN
        self.failure_count = 0
        self.last_failure_time = 0.0

    def record_success(self) -> None:
        self.state = 0
        self.failure_count = 0

    def record_failure(self) -> None:
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.state = 1
            logger.error("circuit_breaker_opened", failure_count=self.failure_count)

    def check_state(self) -> int:
        if self.state == 1:
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = 2
                logger.info("circuit_breaker_half_open")
        return self.state

    def before_call(self) -> None:
        state = self.check_state()
        if state == 1:
            raise CircuitBreakerError("Circuit breaker is OPEN. Fast failing LLM request.")


class LLMConfig(BaseModel):
    base_url: str = "https://api.tokenfactory.nebius.com/v1/"
    model: str = "moonshotai/Kimi-K2.5-fast"
    api_key: str
    max_retries: int = 3
    timeout: int = 120


class LLMResponse(BaseModel):
    content: str
    raw_response: dict[str, Any]
    usage: Optional[dict[str, Any]] = None


class LLMClient:
    def __init__(self, config: LLMConfig) -> None:
        self.config = config
        self.client = httpx.AsyncClient(
            base_url=config.base_url,
            timeout=config.timeout,
            headers={"Authorization": f"Bearer {config.api_key}"},
        )
        self.breaker = CircuitBreaker()

    async def close(self) -> None:
        await self.client.aclose()

    async def chat(
        self,
        messages: list[dict[str, str]],
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        self.breaker.before_call()
        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)

        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": full_messages,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens

        for attempt in range(self.config.max_retries):
            try:
                response = await self.client.post("chat/completions", json=payload)
                response.raise_for_status()
                data = response.json()

                self.breaker.record_success()

                content = data["choices"][0]["message"]["content"]
                return LLMResponse(
                    content=content,
                    raw_response=data,
                    usage=data.get("usage"),
                )
            except httpx.HTTPStatusError as e:
                if e.response.status_code >= 500 or e.response.status_code == 429:
                    self.breaker.record_failure()
                logger.warning(
                    "llm_http_error", attempt=attempt, status=e.response.status_code
                )
                if attempt == self.config.max_retries - 1:
                    raise
            except httpx.RequestError as e:
                self.breaker.record_failure()
                logger.warning("llm_request_error", attempt=attempt, error=str(e))
                if attempt == self.config.max_retries - 1:
                    raise

        raise RuntimeError("LLM request failed after all retries")

    async def chat_stream(
        self,
        messages: list[dict[str, str]],
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        on_token: Optional[Callable[[str], Any]] = None,
    ) -> AsyncGenerator[str, None]:
        self.breaker.before_call()
        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)

        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": full_messages,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
            "stream": True,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens

        try:
            async with self.client.stream(
                "POST", "chat/completions", json=payload
            ) as response:
                response.raise_for_status()
                self.breaker.record_success()
                accumulated_content = ""

                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                            delta = chunk.get("choices", [{}])[0].get("delta", {})
                            token = delta.get("content", "")
                            if token:
                                accumulated_content += token
                                if on_token:
                                    import inspect

                                    if inspect.iscoroutinefunction(on_token):
                                        await on_token(token)
                                    else:
                                        on_token(token)
                                yield token
                        except json.JSONDecodeError:
                            continue

                logger.info("llm_stream_complete", tokens=len(accumulated_content))
        except httpx.HTTPStatusError as e:
            if e.response.status_code >= 500 or e.response.status_code == 429:
                self.breaker.record_failure()
            logger.warning("llm_stream_http_error", status=e.response.status_code)
            raise
        except httpx.RequestError as e:
            self.breaker.record_failure()
            logger.warning("llm_stream_request_error", error=str(e))
            raise

    async def chat_json(
        self,
        messages: list[dict[str, str]],
        system_prompt: Optional[str] = None,
        response_model: Optional[type[BaseModel]] = None,
    ) -> dict[str, Any] | BaseModel:
        response = await self.chat(messages, system_prompt)
        content = response.content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        parsed = json.loads(content)

        if response_model:
            return response_model.model_validate(parsed)
        return parsed


def create_llm_client(api_key: str) -> LLMClient:
    return LLMClient(LLMConfig(api_key=api_key))

