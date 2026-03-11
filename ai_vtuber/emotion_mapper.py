"""텍스트 → 감정 레이블 매핑"""
from __future__ import annotations
import re


class EmotionMapper:
    """
    AI 응답 텍스트에서 감정을 감지하여 MotionPNGTuber 입 스프라이트 폴더를 결정합니다.
    키워드 기반 + 간단한 규칙 기반 분석을 사용합니다.
    """

    def __init__(self, cfg: dict):
        emotion_cfg = cfg.get("emotion", {})
        self.enabled = emotion_cfg.get("enabled", True)
        self.default = emotion_cfg.get("default", "neutral")
        self.keywords: dict[str, list[str]] = emotion_cfg.get("keywords", {})
        self.mouth_dir_mapping: dict[str, str] = emotion_cfg.get(
            "mouth_dir_mapping", {}
        )
        # 감정 우선순위 (여러 감정이 감지될 때 먼저 오는 것 선택)
        self._priority = ["angry", "surprised", "excited", "happy", "sad", "neutral"]

    def detect(self, text: str) -> str:
        """
        텍스트에서 감정을 감지합니다.
        Returns: 감정 레이블 (happy, sad, angry, surprised, excited, neutral)
        """
        if not self.enabled:
            return self.default

        text_lower = text.lower()
        found: list[str] = []

        for emotion, kw_list in self.keywords.items():
            if not kw_list:
                continue
            for kw in kw_list:
                if kw in text:  # 한국어는 대소문자 구분 없이
                    found.append(emotion)
                    break

        if not found:
            return self._heuristic_detect(text)

        # 우선순위에 따라 선택
        for p in self._priority:
            if p in found:
                return p
        return found[0]

    def _heuristic_detect(self, text: str) -> str:
        """키워드 미감지 시 간단한 규칙으로 감정 추정"""
        # 느낌표가 많으면 excited
        exclamation_count = text.count("!") + text.count("！")
        if exclamation_count >= 2:
            return "excited"

        # 물음표가 많으면 surprised
        question_count = text.count("?") + text.count("？")
        if question_count >= 2:
            return "surprised"

        # 이모지 패턴 감지
        emoji_pattern = re.compile(
            "["
            "\U0001F600-\U0001F64F"  # 감정 이모지
            "\U0001F300-\U0001F5FF"  # 기타 기호
            "\U0001F680-\U0001F6FF"  # 교통 기호
            "\U0001F1E0-\U0001F1FF"  # 국기
            "\U00002700-\U000027BF"  # 장식 기호
            "\U0001F900-\U0001F9FF"  # 추가 이모지
            "]+",
            flags=re.UNICODE,
        )
        emojis = emoji_pattern.findall(text)
        if emojis:
            return "happy"

        return self.default

    def get_mouth_dir(self, emotion: str) -> str:
        """감정 레이블에 해당하는 입 스프라이트 폴더 이름을 반환합니다."""
        return self.mouth_dir_mapping.get(emotion, "neutral")

    def emotion_to_hud(self, emotion: str) -> str:
        """감정을 HUD 표시용 텍스트로 변환합니다."""
        emoji_map = {
            "happy": "😊 happy",
            "sad": "😢 sad",
            "angry": "😠 angry",
            "surprised": "😲 surprised",
            "excited": "🎉 excited",
            "neutral": "😐 neutral",
        }
        return emoji_map.get(emotion, f"😐 {emotion}")
