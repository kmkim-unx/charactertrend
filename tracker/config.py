import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TrackerConfig:
    # OpenAI
    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    openai_model: str = "gpt-4o-mini"

    # Notion
    notion_api_key: str = field(default_factory=lambda: os.getenv("NOTION_API_KEY", ""))
    notion_database_id: str = field(default_factory=lambda: os.getenv("NOTION_DATABASE_ID", ""))

    # Scraping
    top_n: int = 20          # 스크래핑할 캐릭터 수
    top_k: int = 5           # 최종 아카이빙할 후보 수
    request_timeout: int = 15
    request_delay: float = 1.0  # 요청 간 딜레이(초)

    # Output
    output_dir: str = "output"
    error_log: str = "output/error_log.json"
    result_file: str = "output/latest_result.json"

    # Source selection
    enabled_sources: list = field(default_factory=lambda: ["zeta", "crack", "naver_webtoon", "ridi", "kakaopage", "sample"])


def load_config() -> TrackerConfig:
    return TrackerConfig()
