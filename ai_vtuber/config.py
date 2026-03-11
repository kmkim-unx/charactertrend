"""설정 파일 로더"""
from __future__ import annotations
import os
from pathlib import Path
import yaml


def load_config(path: str | Path = "config/character.yaml") -> dict:
    """YAML 설정 파일을 로드하고 환경변수로 빈 값을 채웁니다."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"설정 파일을 찾을 수 없습니다: {path}")

    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    # API 키를 환경변수에서 채우기
    ai_cfg = cfg.get("ai", {})
    if not ai_cfg.get("api_key"):
        if ai_cfg.get("provider") == "openai":
            ai_cfg["api_key"] = os.environ.get("OPENAI_API_KEY", "")
        elif ai_cfg.get("provider") == "anthropic":
            ai_cfg["api_key"] = os.environ.get("ANTHROPIC_API_KEY", "")

    # Google TTS 인증 환경변수
    tts_cfg = cfg.get("tts", {})
    google_cfg = tts_cfg.get("google", {})
    if not google_cfg.get("credentials"):
        google_cfg["credentials"] = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")

    return cfg


def get_mouth_dir(cfg: dict, emotion: str) -> Path:
    """감정에 해당하는 입 스프라이트 폴더 경로를 반환합니다."""
    base = Path(cfg["character"]["mouth_sprites_base"])
    emotion_cfg = cfg.get("emotion", {})
    mapping = emotion_cfg.get("mouth_dir_mapping", {})
    folder = mapping.get(emotion, "neutral")
    return base / folder
