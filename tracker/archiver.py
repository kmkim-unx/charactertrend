"""
Notion API를 사용해 Top-5 캐릭터를 데이터베이스에 아카이빙한다.
- DB 컬럼이 없으면 자동 생성 (_ensure_schema)
- 한국 노션 기본 title 필드명 "이름" 자동 감지
"""
import logging
import requests
from datetime import date

from tracker.config import TrackerConfig
from tracker.analyzer import ScoredCharacter

logger = logging.getLogger(__name__)

NOTION_VERSION = "2022-06-28"
NOTION_API_BASE = "https://api.notion.com/v1"

# 코드 내부에서 사용할 title 필드 키 (실제 Notion DB의 title 필드명과 매핑)
TITLE_FIELD = "이름"   # _ensure_schema 후 확정

SCHEMA_PROPERTIES = {
    # title 은 _ensure_schema 에서 기존 필드를 감지해 처리
    "Source":  {"select": {}},
    "G3":      {"number": {"format": "number"}},
    "G4":      {"number": {"format": "number"}},
    "G5":      {"number": {"format": "number"}},
    "Total":   {"number": {"format": "number"}},
    "Rank":    {"number": {"format": "number"}},
    "Reason":  {"rich_text": {}},
    "UNX_Fit": {"rich_text": {}},
    "URL":     {"url": {}},
    "Date":    {"date": {}},
}


class NotionArchiver:
    def __init__(self, cfg: TrackerConfig):
        self.cfg = cfg
        self.headers = {
            "Authorization": f"Bearer {cfg.notion_api_key}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        }
        self._title_field: str = TITLE_FIELD  # 실제 DB의 title 필드명

    # ── 스키마 자동 생성/보완 ──────────────────────────────────
    def _ensure_schema(self) -> None:
        """DB에 필요한 컬럼이 없으면 자동으로 추가한다."""
        # 1) 현재 DB 속성 조회
        resp = requests.get(
            f"{NOTION_API_BASE}/databases/{self.cfg.notion_database_id}",
            headers=self.headers,
            timeout=15,
        )
        resp.raise_for_status()
        db_data = resp.json()
        existing = db_data.get("properties", {})

        # 2) 현재 title 필드 이름 감지 (한국 노션은 "이름", 영어는 "Name")
        for field_name, field_def in existing.items():
            if field_def.get("type") == "title":
                self._title_field = field_name
                logger.info(f"[Archiver] title 필드 감지: '{field_name}'")
                break

        # 3) 없는 컬럼만 추가
        to_add = {
            k: v for k, v in SCHEMA_PROPERTIES.items()
            if k not in existing
        }
        if not to_add:
            logger.info("[Archiver] DB 스키마 이상 없음 (모든 컬럼 존재)")
            return

        logger.info(f"[Archiver] 컬럼 자동 생성: {list(to_add.keys())}")
        patch_resp = requests.patch(
            f"{NOTION_API_BASE}/databases/{self.cfg.notion_database_id}",
            headers=self.headers,
            json={"properties": to_add},
            timeout=15,
        )
        if patch_resp.status_code in (200, 201):
            logger.info("[Archiver] DB 스키마 업데이트 완료")
        else:
            logger.warning(
                f"[Archiver] 스키마 업데이트 실패 (무시하고 계속): "
                f"{patch_resp.status_code} {patch_resp.text[:200]}"
            )

    # ── 페이지 페이로드 빌드 ──────────────────────────────────
    def _build_page_payload(self, rank: int, sc: ScoredCharacter) -> dict:
        char = sc.character
        today = date.today().isoformat()

        payload = {
            "parent": {"database_id": self.cfg.notion_database_id},
            "properties": {
                self._title_field: {
                    "title": [{"text": {"content": f"#{rank} {char.name}"}}]
                },
                "Source":  {"select": {"name": char.source.upper()}},
                "G3":      {"number": sc.g3},
                "G4":      {"number": sc.g4},
                "G5":      {"number": sc.g5},
                "Total":   {"number": sc.total},
                "Rank":    {"number": rank},
                "Reason":  {"rich_text": [{"text": {"content": sc.reason[:2000]}}]},
                "UNX_Fit": {"rich_text": [{"text": {"content": sc.unx_fit[:2000]}}]},
                "URL":     {"url": char.url or None},
                "Date":    {"date": {"start": today}},
            },
            "children": self._build_page_children(sc),
        }

        # 커버 이미지 설정
        if char.image_url and char.image_url.startswith("http"):
            payload["cover"] = {
                "type": "external",
                "external": {"url": char.image_url},
            }

        return payload

    def _build_page_children(self, sc: ScoredCharacter) -> list[dict]:
        """페이지 본문 블록 구성"""
        char = sc.character
        children = []

        # 1. 캐릭터 이미지 블록
        if char.image_url and char.image_url.startswith("http"):
            children.append({
                "type": "image",
                "image": {
                    "type": "external",
                    "external": {"url": char.image_url},
                },
            })

        # 2. 캐릭터 기본 정보
        info_parts = []
        if char.source:
            info_parts.append(f"소스: {char.source.upper()}")
        if char.interaction_count:
            count = char.interaction_count
            if count >= 10000:
                count_str = f"{count/10000:.1f}만"
            elif count >= 1000:
                count_str = f"{count/1000:.1f}천"
            else:
                count_str = str(count)
            info_parts.append(f"대화수: {count_str}")
        if char.tags:
            info_parts.append(f"태그: {' '.join('#'+t for t in char.tags[:5] if t)}")
        if info_parts:
            children.append({
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"text": {"content": " | ".join(info_parts)}}],
                },
            })

        # 3. 캐릭터 설명
        if char.description:
            children.append({
                "type": "quote",
                "quote": {
                    "rich_text": [{"text": {"content": char.description[:1000]}}],
                    "color": "gray_background",
                },
            })

        # 4. G3/G4/G5 점수
        scores_text = f"G3 익숙함: {sc.g3}/10 | G4 신선함: {sc.g4}/10 | G5 트랙: {sc.g5}/10 | 합계: {sc.total}/30"
        children.append({
            "type": "callout",
            "callout": {
                "rich_text": [{"text": {"content": scores_text}}],
                "icon": {"type": "emoji", "emoji": "📊"},
                "color": "blue_background",
            },
        })

        # 5. GPT 분석 이유
        if sc.reason:
            children.append({"type": "heading_3", "heading_3": {"rich_text": [{"text": {"content": "GPT 분석"}}]}})
            children.append({
                "type": "paragraph",
                "paragraph": {"rich_text": [{"text": {"content": sc.reason[:2000]}}]},
            })

        # 6. UNX 적합 이유
        if sc.unx_fit:
            children.append({"type": "heading_3", "heading_3": {"rich_text": [{"text": {"content": "UNX 적합 이유"}}]}})
            children.append({
                "type": "callout",
                "callout": {
                    "rich_text": [{"text": {"content": sc.unx_fit[:2000]}}],
                    "icon": {"type": "emoji", "emoji": "⭐"},
                    "color": "yellow_background",
                },
            })

        return children

    # ── 메인 아카이빙 ─────────────────────────────────────────
    def archive(self, top_k: list[ScoredCharacter]) -> list[str]:
        if not self.cfg.notion_api_key:
            raise ValueError("NOTION_API_KEY 환경변수가 설정되지 않았습니다.")
        if not self.cfg.notion_database_id:
            raise ValueError("NOTION_DATABASE_ID 환경변수가 설정되지 않았습니다.")

        # 스키마 보장 (컬럼 없으면 생성)
        try:
            self._ensure_schema()
        except Exception as e:
            logger.warning(f"[Archiver] 스키마 확인 실패 (계속 진행): {e}")

        created_ids: list[str] = []
        for rank, sc in enumerate(top_k, 1):
            payload = self._build_page_payload(rank, sc)
            resp = requests.post(
                f"{NOTION_API_BASE}/pages",
                headers=self.headers,
                json=payload,
                timeout=15,
            )
            if resp.status_code in (200, 201):
                page_id = resp.json().get("id", "")
                created_ids.append(page_id)
                logger.info(
                    f"[Archiver] #{rank} '{sc.character.name}' 등록 완료 (id={page_id})"
                )
            else:
                logger.error(
                    f"[Archiver] #{rank} '{sc.character.name}' 등록 실패: "
                    f"{resp.status_code} {resp.text[:300]}"
                )
        return created_ids


def archive_to_notion(top_k: list[ScoredCharacter], cfg: TrackerConfig) -> list[str]:
    archiver = NotionArchiver(cfg)
    return archiver.archive(top_k)
