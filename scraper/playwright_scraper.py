"""
Playwright 기반 실제 스크래퍼

- Zeta AI (https://zeta-ai.io/ko?tab=ranking): DOM 파싱
- Crack AI (https://crack.wrtn.ai/characters): DOM 파싱
- Rofan AI (https://rofan.ai/?tab=ranking&period=real_time&gender=all): API 직접 호출

설치:
    pip install playwright && playwright install chromium
"""
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Optional

import requests

logger = logging.getLogger(__name__)


@dataclass
class Character:
    id: str
    name: str
    source: str          # "zeta" | "crack" | "rofan"
    description: str = ""
    tags: list = field(default_factory=list)
    interaction_count: int = 0  # 대화수 (만 단위 파싱 후 정수)
    image_url: str = ""
    url: str = ""
    rank: int = 0
    raw: dict = field(default_factory=dict)


# ──────────────────────────────────────────────────────────────
# 유틸리티
# ──────────────────────────────────────────────────────────────

def _parse_count(s: str) -> int:
    """
    대화수 문자열 파싱.
    '4.1만' → 41000, '28.3만' → 283000, '11M' → 11000000, '6.7M' → 6700000
    """
    if not s:
        return 0
    s = s.strip().replace(",", "").replace(" ", "")
    try:
        if "만" in s:
            num = float(s.replace("만", "").strip())
            return int(num * 10_000)
        if "천" in s:
            num = float(s.replace("천", "").strip())
            return int(num * 1_000)
        if s.upper().endswith("M"):
            num = float(s[:-1])
            return int(num * 1_000_000)
        if s.upper().endswith("K"):
            num = float(s[:-1])
            return int(num * 1_000)
        return int(float(s))
    except Exception:
        return 0


# ──────────────────────────────────────────────────────────────
# Zeta AI — Playwright DOM 파싱
# ──────────────────────────────────────────────────────────────

def scrape_zeta(top_n: int = 20) -> list[Character]:
    """
    Zeta AI 랭킹 페이지 스크래핑.
    https://zeta-ai.io/ko?tab=ranking

    img 태그의 alt 속성 패턴: "username의 캐릭터명" → 의 뒤부분이 캐릭터명
    이미지 URL: https://image.zeta-ai.io/...
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.warning("[Zeta] playwright 미설치. pip install playwright && playwright install chromium")
        return []

    url = "https://zeta-ai.io/ko?tab=ranking"
    logger.info(f"[Zeta] 스크래핑 시작: {url}")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                locale="ko-KR",
                viewport={"width": 1280, "height": 900},
            )
            page = context.new_page()

            try:
                page.goto(url, wait_until="networkidle", timeout=30000)
            except Exception:
                page.goto(url, wait_until="domcontentloaded", timeout=20000)

            page.wait_for_timeout(3000)

            # 나이인증 모달 처리
            for sel in [
                "button:has-text('확인')",
                "button:has-text('동의')",
                "button:has-text('계속')",
                "button:has-text('입장')",
                "button:has-text('18세 이상')",
                "[role='dialog'] button",
            ]:
                try:
                    if page.locator(sel).count() > 0:
                        page.locator(sel).first.click()
                        page.wait_for_timeout(1500)
                        logger.info(f"[Zeta] 모달 dismiss: {sel}")
                        break
                except Exception:
                    pass

            # 스크롤로 lazy load 트리거
            for i in range(4):
                page.evaluate(f"window.scrollTo(0, {(i + 1) * 500})")
                page.wait_for_timeout(800)
            page.evaluate("window.scrollTo(0, 0)")
            page.wait_for_timeout(500)

            # JS로 이미지 태그 기반 데이터 추출
            # alt 패턴: "username의 캐릭터명" → "의 " 뒤가 캐릭터명
            raw_items = page.evaluate("""
                () => {
                    const imgs = [...document.querySelectorAll('img')].filter(
                        img => img.src && img.src.includes('image.zeta-ai.io')
                    );
                    return imgs.map(img => {
                        const alt = img.alt || '';
                        // "username의 캐릭터명" 패턴에서 캐릭터명 추출
                        const matchKo = alt.match(/의\\s+(.+)$/);
                        const charName = matchKo ? matchKo[1].trim() : alt;

                        // 가장 가까운 카드 컨테이너 탐색
                        let card = img.closest('li') || img.closest('article') || img.closest('[class*="card"]') || img.parentElement;
                        for (let i = 0; i < 5 && card; i++) {
                            if (card.querySelectorAll('img').length >= 1 && card.textContent.trim().length > 5) break;
                            card = card.parentElement;
                        }

                        let desc = '';
                        let tags = [];
                        let countStr = '';
                        let rankNum = '';
                        let href = '';

                        if (card) {
                            // 설명 텍스트
                            const descEl = card.querySelector('p, [class*="desc"], [class*="intro"], [class*="subtitle"]');
                            desc = descEl ? descEl.textContent.trim() : '';

                            // 태그 추출
                            tags = [...card.querySelectorAll('[class*="tag"], [class*="badge"]')]
                                .map(t => t.textContent.trim())
                                .filter(t => t.startsWith('#') || (t.length > 0 && t.length < 20));

                            // 대화수
                            const countEl = card.querySelector('[class*="count"], [class*="chat"], [class*="talk"]');
                            countStr = countEl ? countEl.textContent.trim() : '';

                            // 순위
                            const rankEl = card.querySelector('[class*="rank"], [class*="number"]');
                            rankNum = rankEl ? rankEl.textContent.trim().replace(/[^0-9]/g, '') : '';

                            // URL
                            const linkEl = card.querySelector('a[href]');
                            href = linkEl ? linkEl.href : '';
                        }

                        return {
                            name: charName,
                            image: img.src,
                            desc: desc,
                            tags: tags.slice(0, 5),
                            count: countStr,
                            rank: rankNum,
                            href: href,
                        };
                    }).filter(item => item.name && item.name.length > 0);
                }
            """)

            browser.close()

            result = []
            seen_names = set()
            for i, d in enumerate(raw_items[:top_n]):
                name = d.get("name", "").strip()
                if not name or name in seen_names:
                    continue
                seen_names.add(name)

                rank_num = i + 1
                raw_rank = d.get("rank", "")
                if raw_rank and raw_rank.isdigit():
                    rank_num = int(raw_rank)

                result.append(Character(
                    id=f"zeta_{i}_{name[:15]}",
                    name=name,
                    source="zeta",
                    description=d.get("desc", "")[:300],
                    tags=d.get("tags", []),
                    interaction_count=_parse_count(d.get("count", "0")),
                    image_url=d.get("image", ""),
                    url=d.get("href", "") or f"https://zeta-ai.io/ko?tab=ranking",
                    rank=rank_num,
                    raw=d,
                ))

            logger.info(f"[Zeta] {len(result)}개 수집 완료")
            return result

    except Exception as e:
        logger.error(f"[Zeta] 스크래핑 실패: {e}")
        return []


# ──────────────────────────────────────────────────────────────
# Crack AI — Playwright DOM 파싱
# ──────────────────────────────────────────────────────────────

def scrape_crack(top_n: int = 20) -> list[Character]:
    """
    Crack AI 캐릭터 랭킹 스크래핑.
    https://crack.wrtn.ai/characters

    img 태그: alt = 캐릭터명, src = CloudFront URL (d394jeh9729epj.cloudfront.net/...)
    각 카드에서 lines 순서: 대화수(e.g. "11M", "6.7M"), 이름, 설명 텍스트
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.warning("[Crack] playwright 미설치. pip install playwright && playwright install chromium")
        return []

    url = "https://crack.wrtn.ai/characters"
    logger.info(f"[Crack] 스크래핑 시작: {url}")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                locale="ko-KR",
                viewport={"width": 1440, "height": 900},
            )
            page = context.new_page()

            try:
                page.goto(url, wait_until="networkidle", timeout=30000)
            except Exception:
                page.goto(url, wait_until="domcontentloaded", timeout=20000)

            page.wait_for_timeout(3000)

            # "신작 랭킹" 탭 클릭 시도
            for sel in [
                "text=신작 랭킹",
                "[role='tab']:has-text('신작 랭킹')",
                "button:has-text('신작 랭킹')",
                "text=랭킹",
            ]:
                try:
                    if page.locator(sel).count() > 0:
                        page.locator(sel).first.click()
                        page.wait_for_timeout(2000)
                        logger.info(f"[Crack] 탭 클릭: {sel}")
                        break
                except Exception:
                    pass

            # 스크롤
            for i in range(4):
                page.evaluate(f"window.scrollTo(0, {(i + 1) * 400})")
                page.wait_for_timeout(800)

            # CloudFront 이미지 기반으로 카드 추출
            # alt 속성이 캐릭터명
            raw_items = page.evaluate("""
                () => {
                    const imgs = [...document.querySelectorAll('img')].filter(
                        img => img.src && img.src.includes('cloudfront.net')
                    );
                    return imgs.map((img, idx) => {
                        const charName = img.alt || '';

                        // 가장 가까운 카드 컨테이너
                        let card = img.closest('li') || img.closest('article') || img.closest('[class*="card"]') || img.parentElement;
                        for (let i = 0; i < 6 && card; i++) {
                            const txt = card.textContent.trim();
                            if (txt.length > 10 && card.querySelectorAll('img').length >= 1) break;
                            card = card.parentElement;
                        }

                        let desc = '';
                        let tags = [];
                        let countStr = '';
                        let href = '';

                        if (card) {
                            // 카드의 텍스트 라인들 수집 (대화수, 이름, 설명 순서)
                            const allText = [...card.querySelectorAll('*')]
                                .filter(el => el.children.length === 0 && el.textContent.trim().length > 0)
                                .map(el => el.textContent.trim())
                                .filter(t => t.length > 0 && t.length < 200);

                            // 대화수 패턴 탐지: "11M", "6.7M", "4.1만" 등
                            const countPattern = /^\d+(\.\d+)?(M|K|만|천)$/i;
                            for (const t of allText) {
                                if (countPattern.test(t)) {
                                    countStr = t;
                                    break;
                                }
                            }

                            // 설명 (긴 텍스트)
                            const descEl = card.querySelector('p, [class*="desc"], [class*="intro"], [class*="description"]');
                            desc = descEl ? descEl.textContent.trim() : '';

                            // 태그
                            tags = [...card.querySelectorAll('[class*="tag"], [class*="badge"], [class*="genre"]')]
                                .map(t => t.textContent.trim())
                                .filter(t => t.length > 0 && t.length < 20);

                            const linkEl = card.querySelector('a[href]');
                            href = linkEl ? linkEl.href : '';
                        }

                        return {
                            name: charName,
                            image: img.src,
                            desc: desc,
                            tags: tags.slice(0, 5),
                            count: countStr,
                            rank: idx + 1,
                            href: href,
                        };
                    }).filter(item => item.name && item.name.length > 0);
                }
            """)

            browser.close()

            result = []
            seen_names = set()
            for i, d in enumerate(raw_items[:top_n]):
                name = d.get("name", "").strip()
                if not name or name in seen_names:
                    continue
                seen_names.add(name)

                result.append(Character(
                    id=f"crack_{i}_{name[:15]}",
                    name=name,
                    source="crack",
                    description=d.get("desc", "")[:300],
                    tags=d.get("tags", []),
                    interaction_count=_parse_count(d.get("count", "0")),
                    image_url=d.get("image", ""),
                    url=d.get("href", "") or f"https://crack.wrtn.ai/characters",
                    rank=i + 1,
                    raw=d,
                ))

            logger.info(f"[Crack] {len(result)}개 수집 완료")
            return result

    except Exception as e:
        logger.error(f"[Crack] 스크래핑 실패: {e}")
        return []


# ──────────────────────────────────────────────────────────────
# Rofan AI — API 직접 호출 (브라우저 불필요)
# ──────────────────────────────────────────────────────────────

ROFAN_API = "https://rofan.ai/api/bot/GetNewRankingBotList"
ROFAN_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Content-Type": "application/json",
    "Referer": "https://rofan.ai/?tab=ranking&period=real_time&gender=all",
    "Origin": "https://rofan.ai",
    "Accept": "application/json, */*",
    "Accept-Language": "ko-KR,ko;q=0.9",
}


def scrape_rofan(top_n: int = 20) -> list[Character]:
    """
    Rofan AI 실시간 랭킹 API 직접 호출.
    POST https://rofan.ai/api/bot/GetNewRankingBotList
    Body: {"period": "real_time", "gender": "all", "page": 1, "pageSize": 20}
    이미지: https://img.rofan.ai/bot-assets/{uuid}/{hash}.webp
    """
    logger.info("[Rofan] API 직접 호출 시작")

    all_chars: list[Character] = []
    page = 1
    page_size = min(top_n, 20)

    while len(all_chars) < top_n:
        try:
            resp = requests.post(
                ROFAN_API,
                headers=ROFAN_HEADERS,
                json={
                    "period": "real_time",
                    "gender": "all",
                    "page": page,
                    "pageSize": page_size,
                },
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning(f"[Rofan] API 호출 실패 (page={page}): {e}")
            break

        # 응답 구조 탐색: data, bots, list, items, result 등
        items = (
            data.get("data")
            or data.get("bots")
            or data.get("list")
            or data.get("items")
            or data.get("result")
            or (data if isinstance(data, list) else [])
        )
        if not items or not isinstance(items, list):
            logger.warning(f"[Rofan] 빈 응답 (page={page}), 응답 키: {list(data.keys()) if isinstance(data, dict) else type(data)}")
            break

        for i, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            name = (
                item.get("name") or item.get("botName") or
                item.get("characterName") or item.get("title") or ""
            )
            if not name:
                continue

            cid = str(
                item.get("id") or item.get("botId") or
                item.get("characterId") or item.get("_id") or f"rofan_{page}_{i}"
            )
            desc = (
                item.get("description") or item.get("intro") or
                item.get("greeting") or item.get("synopsis") or
                item.get("persona") or ""
            )

            # 이미지 URL 구성
            # 형식: https://img.rofan.ai/bot-assets/{uuid}/{hash}.webp
            image_url = (
                item.get("imageUrl") or item.get("image") or
                item.get("thumbnailUrl") or item.get("profileImageUrl") or
                item.get("botImageUrl") or item.get("coverUrl") or ""
            )
            if not image_url:
                # uuid 기반 이미지 URL 직접 구성 시도
                bot_uuid = item.get("uuid") or item.get("botUuid") or cid
                img_hash = item.get("imageHash") or item.get("hash") or ""
                if img_hash:
                    image_url = f"https://img.rofan.ai/bot-assets/{bot_uuid}/{img_hash}.webp"

            tags_raw = item.get("tags") or item.get("categories") or item.get("genres") or []
            tags = [t if isinstance(t, str) else t.get("name", "") for t in tags_raw if t]

            chat_count = (
                item.get("chatCount") or item.get("talkCount") or
                item.get("interactionCount") or item.get("viewCount") or 0
            )
            rank_num = item.get("rank") or (len(all_chars) + 1)

            all_chars.append(Character(
                id=f"rofan_{cid}",
                name=name,
                source="rofan",
                description=desc[:300],
                tags=tags[:5],
                interaction_count=int(chat_count) if isinstance(chat_count, (int, float)) else 0,
                image_url=image_url,
                url=f"https://rofan.ai/character/{cid}",
                rank=int(rank_num) if str(rank_num).isdigit() else len(all_chars),
                raw=item,
            ))

        logger.info(f"[Rofan] page={page} → {len(items)}개 수집, 누적 {len(all_chars)}개")

        if len(items) < page_size:
            break  # 마지막 페이지
        page += 1

    result = all_chars[:top_n]
    logger.info(f"[Rofan] 최종 {len(result)}개 수집 완료")
    return result


# ──────────────────────────────────────────────────────────────
# 통합 진입점
# ──────────────────────────────────────────────────────────────

def scrape_all(
    sources: list[str] | None = None,
    top_n: int = 20,
    delay: float = 1.5,
) -> list[Character]:
    """
    모든 소스에서 캐릭터 수집.

    Args:
        sources: ["zeta", "crack", "rofan"] 중 선택 (None이면 전체)
        top_n: 소스당 최대 수집 수
        delay: 소스 간 딜레이(초)

    Returns:
        수집된 Character 목록 (중복 제거 없음, rank 순 정렬)
    """
    if sources is None:
        sources = ["zeta", "crack", "rofan"]

    all_chars: list[Character] = []

    if "zeta" in sources:
        chars = scrape_zeta(top_n=top_n)
        all_chars.extend(chars)
        if chars:
            time.sleep(delay)

    if "crack" in sources:
        chars = scrape_crack(top_n=top_n)
        all_chars.extend(chars)
        if chars:
            time.sleep(delay)

    if "rofan" in sources:
        chars = scrape_rofan(top_n=top_n)
        all_chars.extend(chars)

    logger.info(f"[ScrapeAll] 총 {len(all_chars)}개 캐릭터 수집 완료")
    return all_chars


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    chars = scrape_all(sources=["rofan"], top_n=10)
    for c in chars:
        print(f"[{c.source}] #{c.rank} {c.name} | {c.interaction_count:,}회 | {c.image_url[:60]}")
