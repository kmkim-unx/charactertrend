"""TTS 엔진 - edge-tts(무료) 또는 Google Cloud TTS"""
from __future__ import annotations
import asyncio
import io
import logging
import numpy as np
from pathlib import Path

logger = logging.getLogger(__name__)


class BaseTTSEngine:
    """TTS 엔진 베이스 클래스"""

    async def synthesize(self, text: str) -> tuple[np.ndarray, int]:
        """
        텍스트를 음성으로 변환합니다.
        Returns:
            (audio_array, samplerate) - float32 numpy 배열과 샘플레이트
        """
        raise NotImplementedError

    @staticmethod
    def _decode_mp3_bytes(mp3_bytes: bytes, target_sr: int = 24000) -> tuple[np.ndarray, int]:
        """MP3 바이트를 numpy float32 배열로 변환합니다."""
        try:
            import soundfile as sf
            buf = io.BytesIO(mp3_bytes)
            data, sr = sf.read(buf, dtype="float32")
        except Exception:
            # soundfile이 없으면 pydub 시도
            try:
                from pydub import AudioSegment
                buf = io.BytesIO(mp3_bytes)
                seg = AudioSegment.from_mp3(buf)
                seg = seg.set_frame_rate(target_sr).set_channels(1)
                raw = np.frombuffer(seg.raw_data, dtype=np.int16).astype(np.float32)
                data = raw / 32768.0
                sr = target_sr
            except Exception as e:
                raise RuntimeError(f"MP3 디코딩 실패: {e}")
        # 스테레오 → 모노
        if data.ndim > 1:
            data = data.mean(axis=1)
        return data, sr


class EdgeTTSEngine(BaseTTSEngine):
    """
    edge-tts 기반 무료 TTS 엔진.
    Microsoft Edge의 TTS 서비스를 사용합니다 (API 키 불필요).
    """

    def __init__(self, cfg: dict):
        tts_cfg = cfg.get("tts", {}).get("edge_tts", {})
        self.voice = tts_cfg.get("voice", "ko-KR-SunHiNeural")
        self.rate = tts_cfg.get("rate", "+0%")
        self.pitch = tts_cfg.get("pitch", "+0Hz")
        self.volume = tts_cfg.get("volume", "+0%")

    async def synthesize(self, text: str) -> tuple[np.ndarray, int]:
        try:
            import edge_tts
        except ImportError:
            raise ImportError("edge-tts가 없습니다: pip install edge-tts")

        communicate = edge_tts.Communicate(
            text=text,
            voice=self.voice,
            rate=self.rate,
            pitch=self.pitch,
            volume=self.volume,
        )

        mp3_chunks = []
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                mp3_chunks.append(chunk["data"])

        if not mp3_chunks:
            logger.warning("TTS: 빈 오디오 응답")
            return np.zeros(1000, dtype=np.float32), 24000

        mp3_bytes = b"".join(mp3_chunks)
        return self._decode_mp3_bytes(mp3_bytes)

    @classmethod
    async def list_voices(cls, locale: str = "ko-KR") -> list[str]:
        """사용 가능한 한국어 음성 목록"""
        import edge_tts
        voices = await edge_tts.list_voices()
        return [v["ShortName"] for v in voices if locale in v.get("Locale", "")]


class GoogleCloudTTSEngine(BaseTTSEngine):
    """Google Cloud TTS 엔진 (고품질, API 키 필요)"""

    def __init__(self, cfg: dict):
        tts_cfg = cfg.get("tts", {}).get("google", {})
        self.voice_name = tts_cfg.get("voice_name", "ko-KR-Wavenet-A")
        self.speaking_rate = tts_cfg.get("speaking_rate", 1.0)
        self.pitch = tts_cfg.get("pitch", 0.0)
        credentials = tts_cfg.get("credentials", "")
        if credentials:
            import os
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials

    async def synthesize(self, text: str) -> tuple[np.ndarray, int]:
        try:
            from google.cloud import texttospeech
        except ImportError:
            raise ImportError(
                "google-cloud-texttospeech가 없습니다: "
                "pip install google-cloud-texttospeech"
            )

        client = texttospeech.TextToSpeechAsyncClient()
        synthesis_input = texttospeech.SynthesisInput(text=text)
        voice = texttospeech.VoiceSelectionParams(
            language_code="ko-KR",
            name=self.voice_name,
        )
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.LINEAR16,
            speaking_rate=self.speaking_rate,
            pitch=self.pitch,
        )

        response = await client.synthesize_speech(
            input=synthesis_input,
            voice=voice,
            audio_config=audio_config,
        )

        # LINEAR16 → float32
        raw = np.frombuffer(response.audio_content, dtype=np.int16).astype(np.float32)
        audio = raw / 32768.0
        return audio, 24000


def create_tts_engine(cfg: dict) -> BaseTTSEngine:
    """설정에 따라 적절한 TTS 엔진을 생성합니다."""
    provider = cfg.get("tts", {}).get("provider", "edge-tts")
    if provider == "edge-tts":
        return EdgeTTSEngine(cfg)
    elif provider == "google":
        return GoogleCloudTTSEngine(cfg)
    else:
        raise ValueError(f"지원하지 않는 TTS provider: {provider}")
