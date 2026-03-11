"""AI 응답 생성 엔진 (OpenAI / Anthropic)"""
from __future__ import annotations
import logging
from typing import AsyncGenerator

logger = logging.getLogger(__name__)


class AIEngine:
    """AI 응답을 생성하는 엔진 (OpenAI 또는 Anthropic)"""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        ai = cfg.get("ai", {})
        self.provider = ai.get("provider", "openai")
        self.model = ai.get("model", "gpt-4o-mini")
        self.api_key = ai.get("api_key", "")
        self.max_tokens = ai.get("max_tokens", 150)
        self.temperature = ai.get("temperature", 0.8)
        self.persona = cfg.get("character", {}).get("persona", "당신은 AI VTuber입니다.")
        self._history: list[dict] = []
        self._client = None
        self._init_client()

    def _init_client(self):
        if self.provider == "openai":
            try:
                from openai import AsyncOpenAI
                self._client = AsyncOpenAI(api_key=self.api_key)
            except ImportError:
                logger.error("openai 패키지가 없습니다: pip install openai")
                raise
        elif self.provider == "anthropic":
            try:
                import anthropic
                self._client = anthropic.AsyncAnthropic(api_key=self.api_key)
            except ImportError:
                logger.error("anthropic 패키지가 없습니다: pip install anthropic")
                raise
        else:
            raise ValueError(f"지원하지 않는 AI provider: {self.provider}")

    async def chat(self, user_message: str) -> str:
        """사용자 메시지에 대한 AI 응답을 생성합니다."""
        self._history.append({"role": "user", "content": user_message})

        if self.provider == "openai":
            response = await self._openai_chat()
        else:
            response = await self._anthropic_chat()

        self._history.append({"role": "assistant", "content": response})
        # 최근 10개 대화만 유지
        if len(self._history) > 20:
            self._history = self._history[-20:]

        return response

    async def _openai_chat(self) -> str:
        messages = [{"role": "system", "content": self.persona}] + self._history[:-1]
        messages.append(self._history[-1])

        resp = await self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )
        return resp.choices[0].message.content.strip()

    async def _anthropic_chat(self) -> str:
        resp = await self._client.messages.create(
            model=self.model,
            system=self.persona,
            messages=self._history[:-1] + [self._history[-1]],
            max_tokens=self.max_tokens,
        )
        return resp.content[0].text.strip()

    async def stream_chat(self, user_message: str) -> AsyncGenerator[str, None]:
        """스트리밍 방식으로 AI 응답을 생성합니다 (첫 청크가 빨리 나옴)."""
        self._history.append({"role": "user", "content": user_message})
        full_response = ""

        if self.provider == "openai":
            messages = [{"role": "system", "content": self.persona}] + self._history
            async with self._client.chat.completions.stream(
                model=self.model,
                messages=messages,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
            ) as stream:
                async for chunk in stream:
                    delta = chunk.choices[0].delta.content or ""
                    full_response += delta
                    yield delta
        else:
            # Anthropic streaming
            messages = self._history
            async with self._client.messages.stream(
                model=self.model,
                system=self.persona,
                messages=messages,
                max_tokens=self.max_tokens,
            ) as stream:
                async for text in stream.text_stream:
                    full_response += text
                    yield text

        self._history.append({"role": "assistant", "content": full_response})
        if len(self._history) > 20:
            self._history = self._history[-20:]

    def reset_history(self):
        """대화 기록을 초기화합니다."""
        self._history = []
