"""
G3/G4/G5 기준으로 캐릭터를 분석하고 Top-K를 선정한다.

G3 익숙함 : 기존 인기 장르 참조 여부, 검증된 감정선, 직관적 이해
G4 신선함 : 물리적으로 불가능한 존재 형태, AI만 가능한 조합, 신선함
G5 트랙   : 트렌드 이후에도 팬이 붙을 이유 존재 여부
"""
import json
import logging
from dataclasses import dataclass, field

from openai import OpenAI

from tracker.config import TrackerConfig
from tracker.scraper import Character

logger = logging.getLogger(__name__)

ANALYSIS_PROMPT = """\
당신은 AI 버추얼 캐릭터 기획 전문가입니다.
아래 캐릭터를 세 가지 기준으로 0~10점 채점하고 JSON으로 반환하세요.

채점 기준:
- G3 (익숙함): 기존 인기 장르/감정선 참조 여부, 대중이 직관적으로 이해할 수 있는 정도
- G4 (신선함): 물리적으로 불가능한 존재 형태, AI만 가능한 조합과 신선한 차별점
- G5 (트랙): 트렌드가 지나도 팬이 붙을 수 있는 장기적 매력/세계관/서사 여부

반환 형식 (JSON만, 설명 없이):
{{
  "g3": <0-10>,
  "g4": <0-10>,
  "g5": <0-10>,
  "total": <g3+g4+g5>,
  "reason": "<한국어로 2-3문장 이유>",
  "unx_fit": "<UNX 라이브 AI에 적합한 이유 1문장>"
}}

캐릭터 정보:
이름: {name}
출처: {source}
설명: {description}
태그: {tags}
누적 대화 수: {interaction_count}
"""


@dataclass
class ScoredCharacter:
    character: Character
    g3: int = 0
    g4: int = 0
    g5: int = 0
    total: int = 0
    reason: str = ""
    unx_fit: str = ""


def _extract_json(raw: str) -> dict:
    """응답에서 JSON 객체를 안전하게 추출한다 (마크다운 코드 펜스 등 처리)."""
    import re
    # 마크다운 코드 블록 제거: ```json ... ``` 또는 ``` ... ```
    raw = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`").strip()
    # 첫 { 부터 마지막 } 까지 슬라이싱
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and end >= start:
        raw = raw[start : end + 1]
    return json.loads(raw)


def _safe_int(val, default: int = 0) -> int:
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def _score_one(client: OpenAI, cfg: TrackerConfig, char: Character) -> ScoredCharacter:
    prompt = ANALYSIS_PROMPT.format(
        name=char.name,
        source=char.source,
        description=char.description[:400],
        tags=", ".join(str(t) for t in char.tags[:10]),
        interaction_count=char.interaction_count,
    )
    resp = client.chat.completions.create(
        model=cfg.openai_model,
        messages=[
            {
                "role": "system",
                "content": "You are a JSON-only responder. Always return valid JSON.",
            },
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.3,
        max_tokens=400,
    )
    raw = resp.choices[0].message.content or "{}"
    logger.debug(f"[Analyzer] 원본 응답: {raw[:200]}")

    try:
        data = _extract_json(raw)
    except json.JSONDecodeError as e:
        logger.warning(f"[Analyzer] JSON 파싱 실패 ({e}) — 원본: {raw[:100]}")
        data = {}

    g3 = _safe_int(data.get("g3", 0))
    g4 = _safe_int(data.get("g4", 0))
    g5 = _safe_int(data.get("g5", 0))

    return ScoredCharacter(
        character=char,
        g3=g3,
        g4=g4,
        g5=g5,
        total=_safe_int(data.get("total", g3 + g4 + g5)),
        reason=data.get("reason", ""),
        unx_fit=data.get("unx_fit", ""),
    )


def analyze_and_rank(
    characters: list[Character],
    cfg: TrackerConfig,
) -> list[ScoredCharacter]:
    if not cfg.openai_api_key:
        raise ValueError("OPENAI_API_KEY 환경변수가 설정되지 않았습니다.")

    client = OpenAI(api_key=cfg.openai_api_key)
    scored: list[ScoredCharacter] = []

    for i, char in enumerate(characters, 1):
        logger.info(f"[Analyzer] ({i}/{len(characters)}) 분석 중: {char.name} ({char.source})")
        try:
            result = _score_one(client, cfg, char)
            scored.append(result)
        except Exception as e:
            logger.warning(f"[Analyzer] '{char.name}' 분석 실패: {e}")
            scored.append(ScoredCharacter(character=char))

    # total 기준 내림차순 → 동점이면 g4(신선함) 우선
    scored.sort(key=lambda x: (x.total, x.g4), reverse=True)

    top_k = scored[: cfg.top_k]
    logger.info(f"[Analyzer] Top-{cfg.top_k} 선정 완료")
    for rank, sc in enumerate(top_k, 1):
        logger.info(
            f"  #{rank} {sc.character.name} | G3={sc.g3} G4={sc.g4} G5={sc.g5} 합={sc.total}"
        )
    return top_k
