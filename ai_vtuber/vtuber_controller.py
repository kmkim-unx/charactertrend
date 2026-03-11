"""
AI VTuber 메인 컨트롤러

전체 파이프라인:
  사용자 메시지 → AI 응답 생성 → 감정 분류 → TTS → 립싱크 렌더링
"""
from __future__ import annotations

import asyncio
import logging

import numpy as np

from .ai_engine import AIEngine
from .tts_engine import BaseTTSEngine, create_tts_engine
from .emotion_mapper import EmotionMapper
from .lipsync_bridge import LipsyncBridge

logger = logging.getLogger(__name__)


class VTuberController:
    """AI VTuber의 전체 파이프라인을 조율합니다."""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.ai = AIEngine(cfg)
        self.tts: BaseTTSEngine = create_tts_engine(cfg)
        self.emotion = EmotionMapper(cfg)
        self.bridge = LipsyncBridge(cfg)
        self._speaking_lock = asyncio.Lock()

    def start(self):
        """렌더 루프를 시작합니다."""
        self.bridge.start()
        logger.info("VTuber 컨트롤러 시작됨")

    def stop(self):
        """모든 컴포넌트를 정지합니다."""
        self.bridge.stop()
        logger.info("VTuber 컨트롤러 정지됨")

    async def respond(self, user_message: str) -> str:
        """
        사용자 메시지에 AI가 응답하고, TTS + 립싱크를 실행합니다.

        Args:
            user_message: 시청자 채팅 메시지 등 입력 텍스트

        Returns:
            AI가 생성한 응답 텍스트
        """
        logger.info(f"사용자: {user_message}")

        # 1. AI 응답 생성
        response_text = await self.ai.chat(user_message)
        logger.info(f"AI: {response_text}")

        # 2. 감정 분류
        detected_emotion = self.emotion.detect(response_text)
        logger.info(f"감정: {detected_emotion}")

        # 3. TTS + 립싱크 (직렬 실행 - 동시에 여러 발화 방지)
        async with self._speaking_lock:
            await self._speak(response_text, detected_emotion)

        return response_text

    async def respond_stream(self, user_message: str):
        """
        스트리밍 방식으로 응답합니다.
        텍스트 청크가 쌓이면 TTS로 먼저 발화하여 응답 지연을 줄입니다.

        Yields:
            (text_chunk, is_final) 튜플
        """
        logger.info(f"사용자: {user_message}")
        buffer = ""
        full_text = ""

        # 문장 구분자
        sentence_endings = {".", "!", "?", "。", "！", "？", "\n"}

        async def flush_buffer(text: str, is_final: bool = False):
            nonlocal full_text
            if not text.strip():
                return
            emotion = self.emotion.detect(text)
            full_text += text
            async with self._speaking_lock:
                await self._speak(text, emotion)

        async for chunk in self.ai.stream_chat(user_message):
            buffer += chunk
            yield chunk, False

            # 문장이 완성되면 TTS 발화
            if any(c in buffer for c in sentence_endings) and len(buffer) > 10:
                asyncio.create_task(flush_buffer(buffer))
                buffer = ""

        # 남은 버퍼 발화
        if buffer.strip():
            asyncio.create_task(flush_buffer(buffer, is_final=True))

        yield "", True
        logger.info(f"AI (전체): {full_text}")

    async def speak_text(self, text: str, emotion: str | None = None):
        """
        텍스트를 직접 발화합니다 (AI 응답 없이).
        스트리밍 채팅 등 외부 TTS 제어 시 사용합니다.
        """
        if emotion is None:
            emotion = self.emotion.detect(text)
        async with self._speaking_lock:
            await self._speak(text, emotion)

    def set_emotion(self, emotion: str):
        """현재 감정을 강제로 변경합니다."""
        self.bridge.set_emotion(emotion)

    def reset_history(self):
        """AI 대화 기록을 초기화합니다."""
        self.ai.reset_history()

    # ------------------------------------------------------------------

    async def _speak(self, text: str, emotion: str):
        """TTS로 오디오를 생성하고 브리지에 공급합니다."""
        try:
            audio, sr = await self.tts.synthesize(text)
            self.bridge.feed_audio(audio, sr, emotion=emotion)
        except Exception as e:
            logger.error(f"TTS 실패: {e}")


# ------------------------------------------------------------------
# 스트리밍 플랫폼 채팅 리더 (선택적)
# ------------------------------------------------------------------

class TikTokChatReader:
    """TikTok Live 채팅을 읽어 VTuber에게 전달합니다."""

    def __init__(self, username: str, controller: VTuberController):
        self.username = username
        self.controller = controller

    async def run(self):
        try:
            from TikTokLive import TikTokLiveClient
            from TikTokLive.events import CommentEvent
        except ImportError:
            raise ImportError(
                "TikTokLive 패키지가 필요합니다: pip install TikTokLive"
            )

        client = TikTokLiveClient(unique_id=self.username)

        @client.on(CommentEvent)
        async def on_comment(event: CommentEvent):
            msg = f"{event.user.nickname}: {event.comment}"
            logger.info(f"TikTok 채팅: {msg}")
            await self.controller.respond(event.comment)

        logger.info(f"TikTok Live 연결 중: @{self.username}")
        await client.start()
