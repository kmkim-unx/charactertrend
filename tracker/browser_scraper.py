"""
Playwright 기반 브라우저 스크래퍼
- Zeta AI: https://zeta-ai.io/ko?tab=ranking
- Crack AI: https://crack.wrtn.ai/characters (신작 랭킹 탭)
- Rofan AI: https://rofan.ai/?tab=ranking&period=real_time&gender=all

JS 렌더링이 필요한 React/Next.js SPA 사이트 전용.
"""
import json
import logging
import time
from pathlib import Path

from tracker.config import TrackerConfig
from tracker.scraper import Character

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path("output")


def _get_page_screenshot(page, name: str):
    """디버그용 스크린샷 저장"""
    try:
        OUTPUT_DIR.mkdir(exist_ok=True)
        page.screenshot(path=str(OUTPUT_DIR / f"debug_{name}.png"), full_page=True)
        logger.info(f"[Browser] 스크린샷 저장: output/debug_{name}.png")
    except Exception:
        pass


def _extract_nextjs_data(page) -> dict:
    """Next.js __NEXT_DATA__ 추출"""
    try:
        data = page.evaluate("() => window.__NEXT_DATA__ ? JSON.stringify(window.__NEXT_DATA__) : null")
        if data:
            return json.loads(data)
    except Exception:
        pass
    return {}


def scrape_zeta_ranking(cfg: TrackerConfig) -> list[Character]:
    """
    Zeta AI 랭킹 스크래핑
    URL: https://zeta-ai.io/ko?tab=ranking
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.warning("[Zeta Browser] playwright 미설치. pip install playwright && python3 -m playwright install chromium")
        return []

    url = "https://zeta-ai.io/ko?tab=ranking"
    logger.info(f"[Zeta Browser] 브라우저 스크래핑 시작: {url}")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
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
            try:
                modal_selectors = [
                    "button:has-text('확인')",
                    "button:has-text('동의')",
                    "button:has-text('계속')",
                    "button:has-text('입장')",
                    "button:has-text('18세 이상')",
                    "[class*='confirm']",
                    "[class*='modal'] button",
                    "[role='dialog'] button",
                ]
                for sel in modal_selectors:
                    if page.locator(sel).count() > 0:
                        page.locator(sel).first.click()
                        page.wait_for_timeout(1500)
                        logger.info(f"[Zeta Browser] 모달 dismiss: {sel}")
                        break
            except Exception as e:
                logger.debug(f"[Zeta Browser] 모달 처리 실패 (계속): {e}")

            # 스크롤해서 lazy load 트리거
            for i in range(3):
                page.evaluate(f"window.scrollTo(0, {(i+1) * 400})")
                page.wait_for_timeout(1000)

            # 스크린샷 저장
            _get_page_screenshot(page, "zeta_ranking")

            # 1. Next.js 데이터 시도
            nd = _extract_nextjs_data(page)
            if nd:
                chars = _parse_zeta_nextjs(nd, cfg)
                if chars:
                    browser.close()
                    logger.info(f"[Zeta Browser] Next.js 데이터 수집: {len(chars)}개")
                    return chars

            # 2. JavaScript DOM 추출 시도
            chars = _extract_zeta_dom(page, cfg)
            if chars:
                browser.close()
                logger.info(f"[Zeta Browser] DOM 추출 성공: {len(chars)}개")
                return chars

            # 3. 페이지 텍스트 기반 파싱
            chars = _extract_zeta_text(page, cfg)
            browser.close()
            logger.info(f"[Zeta Browser] 텍스트 파싱: {len(chars)}개")
            return chars

    except Exception as e:
        logger.error(f"[Zeta Browser] 실패: {e}")
        return []


def _parse_zeta_nextjs(nd: dict, cfg: TrackerConfig) -> list[Character]:
    """Next.js 데이터에서 캐릭터 추출"""
    result = []

    def search(obj, depth=0):
        if depth > 8 or len(result) >= cfg.top_n:
            return
        if isinstance(obj, list):
            for item in obj:
                if isinstance(item, dict):
                    # 캐릭터 판별: name + (image 또는 description) 있어야
                    name = item.get("name") or item.get("title") or item.get("characterName")
                    if name and len(name) > 1:
                        desc = (item.get("description") or item.get("intro") or
                                item.get("greeting") or item.get("subtitle") or "")
                        image = (item.get("imageUrl") or item.get("image") or
                                 item.get("thumbnailUrl") or item.get("avatar") or
                                 item.get("coverUrl") or "")
                        cid = str(item.get("id") or item.get("characterId") or item.get("_id") or name)
                        tags_raw = item.get("tags") or item.get("categories") or item.get("genres") or []
                        tags = [t if isinstance(t, str) else t.get("name", "") for t in tags_raw if t]
                        chat_count = (item.get("chatCount") or item.get("interactionCount") or
                                      item.get("viewCount") or item.get("num_interactions") or 0)
                        result.append(Character(
                            id=f"zeta_{cid}",
                            name=name,
                            source="zeta",
                            description=desc[:300] if desc else "",
                            tags=tags[:5],
                            interaction_count=int(chat_count) if chat_count else 0,
                            image_url=image,
                            url=f"https://zeta-ai.io/ko/character/{cid}",
                            raw=item,
                        ))
                    else:
                        search(item, depth + 1)
        elif isinstance(obj, dict):
            for v in obj.values():
                if isinstance(v, (dict, list)):
                    search(v, depth + 1)

    search(nd)
    return result[:cfg.top_n]


def _extract_zeta_dom(page, cfg: TrackerConfig) -> list[Character]:
    """DOM 요소에서 직접 캐릭터 카드 추출"""
    # 여러 selector 시도
    selectors = [
        "[class*='character-card']",
        "[class*='CharacterCard']",
        "[class*='character_card']",
        "[class*='rankItem']",
        "[class*='rank-item']",
        "[class*='RankItem']",
        "[class*='cardItem']",
        "[class*='card-item']",
        "li[class*='character']",
        "div[class*='character'][class*='item']",
    ]

    for sel in selectors:
        try:
            count = page.locator(sel).count()
            if count >= 3:
                logger.info(f"[Zeta Browser] 셀렉터 매칭: {sel} ({count}개)")
                cards_data = page.evaluate(f"""
                    () => {{
                        const cards = document.querySelectorAll('{sel}');
                        return Array.from(cards).slice(0, 20).map(card => {{
                            const img = card.querySelector('img');
                            const name = card.querySelector('h1,h2,h3,h4,[class*="name"],[class*="title"]');
                            const desc = card.querySelector('p,[class*="desc"],[class*="intro"],[class*="subtitle"]');
                            const tags = Array.from(card.querySelectorAll('[class*="tag"]')).map(t => t.textContent.trim()).filter(t => t.startsWith('#') || t.length < 20);
                            const count_el = card.querySelector('[class*="count"],[class*="chat"],[class*="view"]');
                            const link = card.querySelector('a[href]');
                            return {{
                                name: name ? name.textContent.trim() : '',
                                desc: desc ? desc.textContent.trim() : '',
                                image: img ? (img.src || img.dataset.src || '') : '',
                                tags: tags.slice(0,5),
                                count: count_el ? count_el.textContent.trim() : '0',
                                href: link ? link.href : '',
                            }};
                        }}).filter(c => c.name && c.name.length > 0);
                    }}
                """)
                if cards_data and len(cards_data) >= 3:
                    result = []
                    for i, d in enumerate(cards_data):
                        # count 파싱 (만 단위 변환)
                        count_str = d.get("count", "0").replace(",", "").replace(" ", "")
                        count_val = _parse_korean_number(count_str)
                        result.append(Character(
                            id=f"zeta_{i}_{d['name'][:10]}",
                            name=d["name"],
                            source="zeta",
                            description=d.get("desc", "")[:300],
                            tags=d.get("tags", []),
                            interaction_count=count_val,
                            image_url=d.get("image", ""),
                            url=d.get("href", f"https://zeta-ai.io/ko"),
                            raw=d,
                        ))
                    return result[:cfg.top_n]
        except Exception as e:
            logger.debug(f"[Zeta Browser] 셀렉터 {sel} 실패: {e}")
            continue
    return []


def _extract_zeta_text(page, cfg: TrackerConfig) -> list[Character]:
    """페이지 전체 텍스트에서 캐릭터 이름/설명 추출 (최후 수단)"""
    try:
        # 이미지 URL 모두 수집
        imgs = page.evaluate("""
            () => Array.from(document.querySelectorAll('img[src]'))
                .map(i => i.src)
                .filter(s => s.startsWith('http') && !s.includes('icon') && !s.includes('logo') && !s.includes('svg'))
        """)

        # 텍스트 블록 수집 (짧은 텍스트 = 이름, 긴 텍스트 = 설명)
        texts = page.evaluate("""
            () => {
                const result = [];
                const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
                let node;
                while (node = walker.nextNode()) {
                    const tag = node.tagName;
                    if (['H1','H2','H3','H4','SPAN','P','DIV'].includes(tag)) {
                        const text = node.innerText?.trim();
                        const children = node.children.length;
                        if (text && text.length > 2 && text.length < 50 && children < 3) {
                            result.push({text, tag, cls: node.className});
                        }
                    }
                }
                return result.slice(0, 100);
            }
        """)

        if not texts:
            return []

        # 제목처럼 보이는 텍스트 필터링 (로그인, 홈 등 UI 텍스트 제외)
        ui_words = {
            "로그인", "홈", "랭킹", "마이페이지", "검색", "트렌딩", "베스트", "신작",
            "캐릭터", "대화", "제작", "이미지", "전체", "Zeta", "일상/로맨스", "학원물",
            "집착/피페", "로맨스 판타지", "BL", "현대 판타지", "무협",
        }
        bad_patterns = ["@", "http", "www.", ".com", ".io", "contents-"]
        candidates = [
            t["text"] for t in texts
            if t["text"] not in ui_words
            and not any(p in t["text"] for p in bad_patterns)
            and not t["text"].startswith("[")
            and not t["text"].isdigit()
            and "만" not in t["text"][:3]  # "4.2만" 같은 숫자 제외
            and len(t["text"]) >= 2
            and len(t["text"]) <= 30
        ]

        result = []
        for i, name in enumerate(candidates[:cfg.top_n]):
            img_url = imgs[i] if i < len(imgs) else ""
            result.append(Character(
                id=f"zeta_text_{i}",
                name=name,
                source="zeta",
                description="Zeta AI 인기 캐릭터 (텍스트 파싱)",
                image_url=img_url,
                url="https://zeta-ai.io/ko?tab=ranking",
                raw={"raw_text": name},
            ))
        return result
    except Exception as e:
        logger.debug(f"[Zeta Browser] 텍스트 파싱 실패: {e}")
        return []


def scrape_crack_ranking(cfg: TrackerConfig) -> list[Character]:
    """
    Crack AI 캐릭터 랭킹 스크래핑
    URL: https://crack.wrtn.ai/characters → 신작 랭킹 탭
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.warning("[Crack Browser] playwright 미설치")
        return []

    url = "https://crack.wrtn.ai/characters"
    logger.info(f"[Crack Browser] 브라우저 스크래핑 시작: {url}")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
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
            try:
                tab_selectors = [
                    "text=신작 랭킹",
                    "[role='tab']:has-text('신작 랭킹')",
                    "button:has-text('신작 랭킹')",
                ]
                for sel in tab_selectors:
                    if page.locator(sel).count() > 0:
                        page.locator(sel).first.click()
                        page.wait_for_timeout(2000)
                        logger.info("[Crack Browser] '신작 랭킹' 탭 클릭 완료")
                        break
            except Exception as e:
                logger.debug(f"[Crack Browser] 탭 클릭 실패: {e}")

            # 스크롤
            for i in range(4):
                page.evaluate(f"window.scrollTo(0, {(i+1) * 400})")
                page.wait_for_timeout(800)

            _get_page_screenshot(page, "crack_ranking")

            # Next.js 데이터 시도
            nd = _extract_nextjs_data(page)
            if nd:
                chars = _parse_crack_nextjs(nd, cfg)
                if chars:
                    browser.close()
                    logger.info(f"[Crack Browser] Next.js 수집: {len(chars)}개")
                    return chars

            # DOM 추출
            chars = _extract_crack_dom(page, cfg)
            browser.close()
            logger.info(f"[Crack Browser] DOM 추출: {len(chars)}개")
            return chars

    except Exception as e:
        logger.error(f"[Crack Browser] 실패: {e}")
        return []


def _parse_crack_nextjs(nd: dict, cfg: TrackerConfig) -> list[Character]:
    """Crack AI Next.js 데이터 파싱"""
    result = []

    def search(obj, depth=0):
        if depth > 8 or len(result) >= cfg.top_n:
            return
        if isinstance(obj, list):
            for item in obj:
                if isinstance(item, dict):
                    name = item.get("name") or item.get("title") or item.get("characterName")
                    if name and len(name) > 1:
                        cid = str(item.get("id") or item.get("_id") or item.get("characterId") or name)
                        desc = item.get("description") or item.get("intro") or item.get("greeting") or ""
                        image = (item.get("imageUrl") or item.get("image") or item.get("thumbnailUrl") or
                                 item.get("profileImage") or item.get("coverImage") or "")
                        tags_raw = item.get("tags") or item.get("categories") or []
                        tags = [t if isinstance(t, str) else t.get("name","") for t in tags_raw if t]
                        result.append(Character(
                            id=f"crack_{cid}",
                            name=name,
                            source="crack",
                            description=desc[:300],
                            tags=tags[:5],
                            interaction_count=int(item.get("chatCount") or item.get("viewCount") or 0),
                            image_url=image,
                            url=f"https://crack.wrtn.ai/characters/{cid}",
                            raw=item,
                        ))
                    else:
                        search(item, depth + 1)
        elif isinstance(obj, dict):
            for v in obj.values():
                if isinstance(v, (dict, list)):
                    search(v, depth + 1)

    search(nd)
    return result[:cfg.top_n]


def _extract_crack_dom(page, cfg: TrackerConfig) -> list[Character]:
    """Crack DOM 추출"""
    selectors = [
        "[class*='character-card']", "[class*='CharacterCard']", "[class*='character_card']",
        "[class*='characterItem']", "[class*='character-item']",
        "li[class*='character']", "[class*='cardItem']",
        "[data-testid*='character']", "[class*='rankCard']",
    ]

    for sel in selectors:
        try:
            count = page.locator(sel).count()
            if count >= 3:
                cards_data = page.evaluate(f"""
                    () => {{
                        const cards = document.querySelectorAll('{sel}');
                        return Array.from(cards).slice(0, 20).map(card => {{
                            const img = card.querySelector('img');
                            const name = card.querySelector('h1,h2,h3,h4,[class*="name"],[class*="title"],[class*="characterName"]');
                            const desc = card.querySelector('p,[class*="desc"],[class*="intro"],[class*="greeting"]');
                            const tags = Array.from(card.querySelectorAll('[class*="tag"],[class*="badge"]')).map(t => t.textContent.trim()).filter(t => t.length < 20 && t.length > 0);
                            const link = card.querySelector('a[href]');
                            return {{
                                name: name ? name.textContent.trim() : '',
                                desc: desc ? desc.textContent.trim() : '',
                                image: img ? img.src : '',
                                tags: tags.slice(0,5),
                                href: link ? link.href : '',
                            }};
                        }}).filter(c => c.name && c.name.length > 1);
                    }}
                """)
                if cards_data and len(cards_data) >= 3:
                    result = []
                    for i, d in enumerate(cards_data):
                        result.append(Character(
                            id=f"crack_{i}_{d['name'][:10]}",
                            name=d["name"],
                            source="crack",
                            description=d.get("desc", "")[:300],
                            tags=d.get("tags", []),
                            image_url=d.get("image", ""),
                            url=d.get("href", "https://crack.wrtn.ai/characters"),
                            raw=d,
                        ))
                    return result[:cfg.top_n]
        except Exception as e:
            logger.debug(f"[Crack Browser] 셀렉터 {sel}: {e}")
    return []


def scrape_rofan_ranking(cfg: TrackerConfig) -> list[Character]:
    """
    Rofan AI 실시간 랭킹 스크래핑
    URL: https://rofan.ai/?tab=ranking&period=real_time&gender=all
    네트워크 응답 인터셉트 → DOM 추출 → 텍스트 파싱 순서로 시도
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.warning("[Rofan Browser] playwright 미설치")
        return []

    url = "https://rofan.ai/?tab=ranking&period=real_time&gender=all"
    logger.info(f"[Rofan Browser] 브라우저 스크래핑 시작: {url}")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                locale="ko-KR",
                viewport={"width": 1280, "height": 900},
            )
            page = context.new_page()

            # ── 네트워크 응답 인터셉트 ─────────────────────────
            api_responses: list[dict] = []

            def on_response(response):
                url_lower = response.url.lower()
                if any(k in url_lower for k in ["ranking", "character", "popular", "bot", "rank"]):
                    try:
                        ct = response.headers.get("content-type", "")
                        if "json" in ct:
                            data = response.json()
                            api_responses.append({"url": response.url, "data": data})
                    except Exception:
                        pass

            page.on("response", on_response)

            try:
                page.goto(url, wait_until="networkidle", timeout=30000)
            except Exception:
                page.goto(url, wait_until="domcontentloaded", timeout=20000)

            page.wait_for_timeout(3000)

            # 스크롤로 lazy load
            for i in range(4):
                page.evaluate(f"window.scrollTo(0, {(i+1) * 500})")
                page.wait_for_timeout(800)

            page.evaluate("window.scrollTo(0, 0)")
            page.wait_for_timeout(500)

            _get_page_screenshot(page, "rofan_ranking")

            # 1. 인터셉트된 API 응답 파싱
            if api_responses:
                logger.info(f"[Rofan Browser] 인터셉트된 API 응답: {len(api_responses)}개")
                for resp in api_responses:
                    chars = _parse_rofan_nextjs(resp["data"], cfg)
                    if chars:
                        browser.close()
                        logger.info(f"[Rofan Browser] API 인터셉트 수집: {len(chars)}개 ({resp['url'][:60]})")
                        return chars

            # 2. Next.js 데이터 시도
            nd = _extract_nextjs_data(page)
            if nd:
                chars = _parse_rofan_nextjs(nd, cfg)
                if chars:
                    browser.close()
                    logger.info(f"[Rofan Browser] Next.js 수집: {len(chars)}개")
                    return chars

            # 3. DOM 추출
            chars = _extract_rofan_dom(page, cfg)
            if chars:
                browser.close()
                logger.info(f"[Rofan Browser] DOM 추출: {len(chars)}개")
                return chars

            # 4. 텍스트 파싱 (필터 강화)
            chars = _extract_rofan_api(page, cfg)
            browser.close()
            logger.info(f"[Rofan Browser] 텍스트 파싱: {len(chars)}개")
            return chars

    except Exception as e:
        logger.error(f"[Rofan Browser] 실패: {e}")
        return []


def _parse_rofan_nextjs(nd: dict, cfg: TrackerConfig) -> list[Character]:
    """Rofan API/Next.js 데이터 파싱 - 다양한 응답 구조 처리"""
    result = []

    def is_character(item: dict) -> bool:
        """캐릭터 데이터인지 판별"""
        name = (item.get("name") or item.get("title") or
                item.get("characterName") or item.get("displayName") or
                item.get("botName") or "")
        return bool(name and 1 < len(name) <= 30 and
                    (item.get("imageUrl") or item.get("image") or
                     item.get("thumbnailUrl") or item.get("profileImageUrl") or
                     item.get("description") or item.get("intro")))

    def extract_char(item: dict, idx: int) -> Character:
        name = (item.get("name") or item.get("title") or
                item.get("characterName") or item.get("displayName") or
                item.get("botName") or "")
        cid = str(item.get("id") or item.get("characterId") or item.get("botId") or
                  item.get("_id") or f"rofan_{idx}")
        desc = (item.get("description") or item.get("intro") or
                item.get("greeting") or item.get("synopsis") or
                item.get("persona") or "")
        image = (item.get("imageUrl") or item.get("image") or
                 item.get("thumbnailUrl") or item.get("coverUrl") or
                 item.get("profileImageUrl") or item.get("botImageUrl") or "")
        tags_raw = item.get("tags") or item.get("categories") or item.get("genres") or []
        tags = [t if isinstance(t, str) else t.get("name", "") for t in tags_raw if t]
        chat_count = (item.get("chatCount") or item.get("interactionCount") or
                      item.get("viewCount") or item.get("talkCount") or 0)
        return Character(
            id=f"rofan_{cid}",
            name=name,
            source="rofan",
            description=desc[:300],
            tags=tags[:5],
            interaction_count=int(chat_count) if isinstance(chat_count, (int, float)) else 0,
            image_url=image,
            url=f"https://rofan.ai/character/{cid}",
            raw=item,
        )

    def search(obj, depth=0):
        if depth > 10 or len(result) >= cfg.top_n:
            return
        if isinstance(obj, list):
            # 3개 이상의 캐릭터처럼 보이는 리스트 발견
            char_items = [i for i in obj if isinstance(i, dict) and is_character(i)]
            if len(char_items) >= 2:
                for idx, item in enumerate(char_items[:cfg.top_n]):
                    result.append(extract_char(item, idx))
                return
            # 아니면 재귀
            for item in obj:
                search(item, depth + 1)
        elif isinstance(obj, dict):
            # 직접 캐릭터인 경우
            if is_character(obj):
                result.append(extract_char(obj, len(result)))
                return
            # 알려진 키 우선 탐색
            priority_keys = ["bots", "characters", "items", "list", "data", "results",
                             "ranking", "rankingList", "characterList", "botList"]
            for key in priority_keys:
                if key in obj:
                    search(obj[key], depth + 1)
                    if len(result) >= 3:
                        return
            # 나머지 키 재귀
            for v in obj.values():
                if isinstance(v, (dict, list)):
                    search(v, depth + 1)

    search(nd)
    return result[:cfg.top_n]


def _extract_rofan_dom(page, cfg: TrackerConfig) -> list[Character]:
    """Rofan DOM 카드 추출"""
    selectors = [
        "[class*='character-card']", "[class*='CharacterCard']",
        "[class*='rankCard']", "[class*='rank-card']",
        "[class*='characterItem']", "[class*='character-item']",
        "[class*='rankItem']", "[class*='rank-item']",
        "li[class*='character']", "article[class*='character']",
        # Rofan 특화
        "[class*='RankCharacter']", "[class*='rankCharacter']",
    ]

    for sel in selectors:
        try:
            count = page.locator(sel).count()
            if count >= 3:
                logger.info(f"[Rofan Browser] 셀렉터 매칭: {sel} ({count}개)")
                cards_data = page.evaluate(f"""
                    () => {{
                        const cards = document.querySelectorAll('{sel}');
                        return Array.from(cards).slice(0, 20).map((card, idx) => {{
                            const imgs = card.querySelectorAll('img');
                            // 가장 큰 이미지 선택
                            let bestImg = '';
                            imgs.forEach(img => {{
                                const src = img.src || img.dataset.src || img.dataset.lazySrc || '';
                                if (src && src.startsWith('http') && !src.includes('icon') && !src.includes('logo')) {{
                                    bestImg = src;
                                }}
                            }});
                            const name = card.querySelector('h1,h2,h3,h4,strong,[class*="name"],[class*="title"],[class*="character-name"]');
                            const desc = card.querySelector('p,[class*="desc"],[class*="intro"],[class*="subtitle"],[class*="synopsis"]');
                            const tags = Array.from(card.querySelectorAll('[class*="tag"],[class*="badge"],[class*="category"]'))
                                .map(t => t.textContent.trim())
                                .filter(t => t.length > 0 && t.length < 20);
                            const countEl = card.querySelector('[class*="count"],[class*="chat"],[class*="view"],[class*="comment"]');
                            const link = card.querySelector('a[href]');
                            const rankEl = card.querySelector('[class*="rank"],[class*="number"],[class*="badge"]');
                            return {{
                                rank: rankEl ? rankEl.textContent.trim() : String(idx + 1),
                                name: name ? name.textContent.trim() : '',
                                desc: desc ? desc.textContent.trim() : '',
                                image: bestImg,
                                tags: tags.slice(0, 5),
                                count: countEl ? countEl.textContent.trim() : '0',
                                href: link ? link.href : '',
                            }};
                        }}).filter(c => c.name && c.name.length > 1 && c.name.length < 50);
                    }}
                """)
                if cards_data and len(cards_data) >= 3:
                    result = []
                    for i, d in enumerate(cards_data):
                        count_val = _parse_korean_number(d.get("count", "0"))
                        result.append(Character(
                            id=f"rofan_{i}_{d['name'][:10]}",
                            name=d["name"],
                            source="rofan",
                            description=d.get("desc", "")[:300],
                            tags=d.get("tags", []),
                            interaction_count=count_val,
                            image_url=d.get("image", ""),
                            url=d.get("href", "https://rofan.ai"),
                            raw=d,
                        ))
                    return result[:cfg.top_n]
        except Exception as e:
            logger.debug(f"[Rofan Browser] 셀렉터 {sel}: {e}")
    return []


def _extract_rofan_api(page, cfg: TrackerConfig) -> list[Character]:
    """Rofan 페이지에서 이미지와 텍스트 최대한 추출"""
    try:
        data = page.evaluate("""
            () => {
                // 모든 이미지 수집
                const imgs = Array.from(document.querySelectorAll('img'))
                    .map(i => ({
                        src: i.src || i.dataset.src || '',
                        alt: i.alt || '',
                        width: i.naturalWidth || i.width,
                        height: i.naturalHeight || i.height,
                    }))
                    .filter(i => i.src.startsWith('http') && i.width > 50 && !i.src.includes('icon'));

                // 짧은 텍스트 (이름) 수집 - 1~30자
                const names = new Set();
                document.querySelectorAll('h1,h2,h3,h4,strong').forEach(el => {
                    const t = el.textContent.trim();
                    if (t.length > 1 && t.length < 30) names.add(t);
                });

                // 설명 텍스트 수집
                const descs = [];
                document.querySelectorAll('p,[class*="desc"],[class*="intro"]').forEach(el => {
                    const t = el.textContent.trim();
                    if (t.length > 10 && t.length < 200) descs.push(t);
                });

                return {imgs: imgs.slice(0, 30), names: Array.from(names).slice(0, 30), descs: descs.slice(0, 30)};
            }
        """)

        names = data.get("names", [])
        imgs = data.get("imgs", [])
        descs = data.get("descs", [])

        # UI 텍스트 필터
        ui_words = {"로그인", "홈", "랭킹", "마이페이지", "검색", "추천", "신작", "카테고리", "태그",
                    "실시간", "일간", "주간", "월간", "전체", "인기순", "Rofan AI", "Rofan",
                    "남성", "여성", "성별", "팔로우", "팔로잉", "대화", "R ONLY"}
        names = [
            n for n in names
            if n not in ui_words
            and not n.startswith("[")       # [R ONLY], [추가 설정] 등
            and ":" not in n               # "신청 링크:" 등
            and not n.isdigit()            # 순수 숫자
            and len(n) >= 2
            and len(n) <= 20              # 너무 긴 건 설명문
        ]

        result = []
        for i, name in enumerate(names[:cfg.top_n]):
            img_url = imgs[i]["src"] if i < len(imgs) else ""
            desc = descs[i] if i < len(descs) else "Rofan AI 인기 캐릭터"
            result.append(Character(
                id=f"rofan_text_{i}",
                name=name,
                source="rofan",
                description=desc[:300],
                image_url=img_url,
                url="https://rofan.ai/?tab=ranking",
                raw={"extracted": name},
            ))
        return result
    except Exception as e:
        logger.debug(f"[Rofan Browser] API 추출 실패: {e}")
        return []


def _parse_korean_number(s: str) -> int:
    """한국어 숫자 파싱: '4.1만' → 41000, '28.3만' → 283000"""
    try:
        s = s.strip().replace(",", "")
        if "만" in s:
            num = float(s.replace("만", "").strip())
            return int(num * 10000)
        if "천" in s:
            num = float(s.replace("천", "").strip())
            return int(num * 1000)
        return int(float(s))
    except Exception:
        return 0
