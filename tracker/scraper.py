"""
캐릭터 스크래퍼

우선순위:
  1차: Zeta AI (Character.AI) / Crack AI
  2차 (한국 폴백): 네이버 웹툰 인기순위 / 리디북스 베스트셀러 / 카카오페이지 인기
  3차: 큐레이션 샘플 (파이프라인 테스트용)
"""
import time
import json
import logging
import re
import ssl
import urllib3
from dataclasses import dataclass, field
from datetime import datetime

import requests
from bs4 import BeautifulSoup

from tracker.config import TrackerConfig

logger = logging.getLogger(__name__)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/html,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}


@dataclass
class Character:
    id: str
    name: str
    source: str          # "zeta" | "crack" | "naver_webtoon" | "ridi" | "kakaopage" | "sample"
    description: str = ""
    tags: list = field(default_factory=list)
    interaction_count: int = 0
    creator: str = ""
    image_url: str = ""
    url: str = ""
    raw: dict = field(default_factory=dict)


# ──────────────────────────────────────────────
# 1차: Zeta AI (Character.AI)
# ──────────────────────────────────────────────
class ZetaScraper:
    BASE = "https://character.ai"
    API_CANDIDATES = [
        "https://plus.character.ai/chat/characters/trending/?page_size=20",
        "https://character.ai/api/v1/characters/search/?query=&page_size=20&sort=trending",
        "https://neo.character.ai/recommendation/v1/featured",
    ]

    def __init__(self, cfg: TrackerConfig):
        self.cfg = cfg
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def fetch(self) -> list[Character]:
        for url in self.API_CANDIDATES:
            try:
                result = self._try_endpoint(url)
                if result:
                    logger.info(f"[Zeta] 성공: {url}")
                    return result[: self.cfg.top_n]
            except Exception as e:
                logger.debug(f"[Zeta] 실패 ({url}): {e}")
        try:
            result = self._fetch_via_html()
            if result:
                return result[: self.cfg.top_n]
        except Exception as e:
            logger.debug(f"[Zeta] HTML 실패: {e}")
        logger.warning("[Zeta] 수집 실패")
        return []

    def _try_endpoint(self, url: str) -> list[Character]:
        resp = self.session.get(url, timeout=self.cfg.request_timeout)
        resp.raise_for_status()
        data = resp.json()
        items = (
            data.get("characters")
            or data.get("result", {}).get("data", {}).get("json", {}).get("characters", [])
            or data.get("data", {}).get("characters", [])
            or (data if isinstance(data, list) else [])
        )
        if not items:
            return []
        return [
            Character(
                id=item.get("external_id", item.get("id", "")),
                name=item.get("name", ""),
                source="zeta",
                description=item.get("description", "") or item.get("title", ""),
                tags=item.get("genres", item.get("categories", [])),
                interaction_count=item.get("num_interactions", item.get("chat_count", 0)),
                creator=item.get("user__username", item.get("creator", "")),
                image_url=item.get("avatar_file_name", item.get("image", "")),
                url=f"{self.BASE}/chat/{item.get('external_id', item.get('id', ''))}",
                raw=item,
            )
            for item in items
        ]

    def _fetch_via_html(self) -> list[Character]:
        for path in ["/search", "/explore", "/"]:
            try:
                resp = self.session.get(f"{self.BASE}{path}", timeout=self.cfg.request_timeout)
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")
                result = []
                for sel in ["[data-testid='character-card']", ".character-card", ".CharacterCard"]:
                    cards = soup.select(sel)
                    if cards:
                        for card in cards[: self.cfg.top_n]:
                            name_el = card.select_one("h3, h2, .name, [class*='name']")
                            desc_el = card.select_one("p, .description, [class*='desc']")
                            link_el = card.select_one("a[href]")
                            result.append(Character(
                                id=link_el["href"].split("/")[-1] if link_el else "",
                                name=name_el.get_text(strip=True) if name_el else "",
                                source="zeta",
                                description=desc_el.get_text(strip=True) if desc_el else "",
                                url=self.BASE + link_el["href"] if link_el else "",
                            ))
                        return result
            except Exception:
                continue
        return []


# ──────────────────────────────────────────────
# 1차: Crack AI
# ──────────────────────────────────────────────
class CrackScraper:
    BASE = "https://crack.ai"
    API_CANDIDATES = [
        "https://crack.ai/api/characters/trending",
        "https://crack.ai/api/v1/characters/trending",
        "https://api.crack.ai/characters/trending",
    ]

    def __init__(self, cfg: TrackerConfig):
        self.cfg = cfg
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.session.headers.update({"Referer": "https://crack.ai/", "Origin": "https://crack.ai"})
        self.session.verify = False

    def fetch(self) -> list[Character]:
        for url in self.API_CANDIDATES:
            try:
                result = self._try_api(url)
                if result:
                    logger.info(f"[Crack] 성공: {url}")
                    return result[: self.cfg.top_n]
            except Exception as e:
                logger.debug(f"[Crack] API 실패 ({url}): {e}")
        for path in ["/trending", "/explore", "/"]:
            try:
                result = self._try_html(f"{self.BASE}{path}")
                if result:
                    return result[: self.cfg.top_n]
            except Exception as e:
                logger.debug(f"[Crack] HTML 실패 ({path}): {e}")
        logger.warning("[Crack] 수집 실패")
        return []

    def _try_api(self, url: str) -> list[Character]:
        resp = self.session.get(url, params={"limit": self.cfg.top_n}, timeout=self.cfg.request_timeout)
        resp.raise_for_status()
        data = resp.json()
        items = data if isinstance(data, list) else data.get("data", data.get("characters", []))
        if not items:
            return []
        return [
            Character(
                id=str(item.get("id", item.get("_id", ""))),
                name=item.get("name", ""),
                source="crack",
                description=item.get("description", "") or item.get("intro", ""),
                tags=item.get("tags", item.get("categories", [])),
                interaction_count=item.get("chat_count", item.get("interactions", 0)),
                creator=item.get("creator", item.get("author", "")),
                image_url=item.get("image", item.get("avatar", "")),
                url=f"{self.BASE}/character/{item.get('id', '')}",
                raw=item,
            )
            for item in items
        ]

    def _try_html(self, url: str) -> list[Character]:
        resp = self.session.get(url, timeout=self.cfg.request_timeout)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        result = []
        for sel in [".character-card", "[class*='CharacterCard']", "[class*='character-item']"]:
            cards = soup.select(sel)
            if cards:
                for card in cards[: self.cfg.top_n]:
                    name_el = card.select_one("h2, h3, .name, [class*='name']")
                    desc_el = card.select_one("p, .desc, [class*='desc']")
                    link_el = card.select_one("a[href]")
                    result.append(Character(
                        id=link_el["href"].split("/")[-1] if link_el else "",
                        name=name_el.get_text(strip=True) if name_el else "",
                        source="crack",
                        description=desc_el.get_text(strip=True) if desc_el else "",
                        url=(self.BASE + link_el["href"] if link_el and link_el["href"].startswith("/") else (link_el["href"] if link_el else "")),
                    ))
                return result
        return []


# ──────────────────────────────────────────────
# 2차 한국 폴백: 네이버 웹툰 인기 순위
# ──────────────────────────────────────────────
class NaverWebtoonScraper:
    """네이버 웹툰 인기순위 → 주인공 캐릭터 추출"""
    API = "https://comic.naver.com/api/webtoon/titlelist/ranking"
    BASE = "https://comic.naver.com"

    def __init__(self, cfg: TrackerConfig):
        self.cfg = cfg
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.session.headers.update({"Referer": "https://comic.naver.com/"})

    def fetch(self) -> list[Character]:
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            resp = self.session.get(
                self.API,
                params={"rankingDate": today, "page": 1, "pageSize": self.cfg.top_n, "webtoonType": "WEBTOON"},
                timeout=self.cfg.request_timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            items = data.get("titleList", {}).get("items", [])
            if not items:
                # titleList가 없으면 다른 구조 시도
                items = data.get("webtoonList", data.get("items", []))
            result = []
            for item in items:
                title = item.get("titleName", item.get("title", ""))
                synopsis = item.get("synopsis", item.get("description", ""))
                genre = item.get("genre", item.get("genreTypes", ["웹툰"]))
                if isinstance(genre, list):
                    genre = ", ".join(genre) if genre else "웹툰"
                authors = item.get("author", item.get("authors", []))
                if isinstance(authors, list):
                    creator = ", ".join(
                        a.get("name", a) if isinstance(a, dict) else str(a)
                        for a in authors
                    )
                else:
                    creator = str(authors)
                tid = str(item.get("titleId", item.get("id", "")))
                result.append(Character(
                    id=f"naver_{tid}",
                    name=title,
                    source="naver_webtoon",
                    description=synopsis or f"{genre} 장르 네이버 인기 웹툰",
                    tags=[genre] if isinstance(genre, str) else genre,
                    interaction_count=item.get("favoriteCount", item.get("viewCount", 0)),
                    creator=creator,
                    url=f"{self.BASE}/webtoon/detail?titleId={tid}",
                    raw=item,
                ))
            logger.info(f"[NaverWebtoon] {len(result)}개 수집")
            return result[: self.cfg.top_n]
        except Exception as e:
            logger.warning(f"[NaverWebtoon] 실패: {e}")
            return []


# ──────────────────────────────────────────────
# 2차 한국 폴백: 리디북스 베스트셀러 (웹소설)
# ──────────────────────────────────────────────
class RidiScraper:
    """리디북스 웹소설 베스트셀러 순위"""
    # 장르별 베스트: genre_id 로맨스=1, 로맨스판타지=2, BL=3, 판타지=4, 무협=5
    BESTSELLER_URLS = [
        ("https://ridibooks.com/romance/bestsellers", "로맨스"),
        ("https://ridibooks.com/romance-fantasy/bestsellers", "로맨스판타지"),
        ("https://ridibooks.com/fantasy/bestsellers", "판타지"),
    ]
    BASE = "https://ridibooks.com"

    def __init__(self, cfg: TrackerConfig):
        self.cfg = cfg
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.session.headers.update({"Referer": "https://ridibooks.com/"})

    def fetch(self) -> list[Character]:
        result = []
        for url, genre in self.BESTSELLER_URLS:
            if len(result) >= self.cfg.top_n:
                break
            try:
                chars = self._fetch_page(url, genre)
                result.extend(chars)
            except Exception as e:
                logger.debug(f"[Ridi] {genre} 실패: {e}")
        if result:
            logger.info(f"[Ridi] {len(result)}개 수집")
        else:
            logger.warning("[Ridi] 수집 실패")
        return result[: self.cfg.top_n]

    def _fetch_page(self, url: str, genre: str) -> list[Character]:
        resp = self.session.get(url, timeout=self.cfg.request_timeout)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # JSON-LD 또는 __NEXT_DATA__ 에서 구조화 데이터 추출 시도
        next_data_tag = soup.find("script", {"id": "__NEXT_DATA__"})
        if next_data_tag:
            try:
                nd = json.loads(next_data_tag.string)
                books = (
                    nd.get("props", {}).get("pageProps", {})
                    .get("fallback", {})
                )
                # fallback은 dict이므로 첫번째 키의 값에서 books 추출
                for v in books.values():
                    if isinstance(v, dict) and "books" in v:
                        return self._parse_ridi_books(v["books"], genre)
            except Exception:
                pass

        # HTML 직접 파싱
        result = []
        selectors = [
            "li[class*='bestseller']",
            "li[class*='book-item']",
            ".book-list-item",
            "li[data-book-id]",
        ]
        for sel in selectors:
            items = soup.select(sel)
            if items:
                for item in items[:self.cfg.top_n]:
                    title_el = item.select_one("strong, .title, [class*='title']")
                    author_el = item.select_one(".author, [class*='author']")
                    link_el = item.select_one("a[href]")
                    desc_el = item.select_one(".description, [class*='desc'], p")
                    if title_el:
                        href = link_el["href"] if link_el else ""
                        book_id = href.split("/")[-1] if href else ""
                        result.append(Character(
                            id=f"ridi_{book_id}",
                            name=title_el.get_text(strip=True),
                            source="ridi",
                            description=desc_el.get_text(strip=True) if desc_el else f"{genre} 장르 리디 베스트셀러",
                            tags=[genre, "웹소설"],
                            creator=author_el.get_text(strip=True) if author_el else "",
                            url=self.BASE + href if href.startswith("/") else href,
                        ))
                return result
        return result

    def _parse_ridi_books(self, books: list, genre: str) -> list[Character]:
        result = []
        for book in books:
            bid = str(book.get("id", book.get("b_id", "")))
            result.append(Character(
                id=f"ridi_{bid}",
                name=book.get("title", ""),
                source="ridi",
                description=book.get("description", f"{genre} 리디 베스트셀러"),
                tags=[genre, "웹소설"],
                creator=book.get("author", ""),
                url=f"{self.BASE}/books/{bid}",
                raw=book,
            ))
        return result


# ──────────────────────────────────────────────
# 2차 한국 폴백: 카카오페이지 인기 순위
# ──────────────────────────────────────────────
class KakaopageScraper:
    """카카오페이지 웹소설/웹툰 인기 순위"""
    # 카카오페이지 공개 API (메뉴별 인기)
    API = "https://page.kakao.com/graphql"
    BASE = "https://page.kakao.com"

    # 카카오페이지 메뉴 ID (웹소설 로맨스=10011, 웹소설 판타지=10010, 웹툰=10003)
    SECTION_URLS = [
        "https://page.kakao.com/menu/10011/screen/14",   # 웹소설 로맨스 인기
        "https://page.kakao.com/menu/10010/screen/14",   # 웹소설 판타지 인기
    ]

    def __init__(self, cfg: TrackerConfig):
        self.cfg = cfg
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.session.headers.update({"Referer": "https://page.kakao.com/"})

    def fetch(self) -> list[Character]:
        result = []
        for url in self.SECTION_URLS:
            if len(result) >= self.cfg.top_n:
                break
            try:
                chars = self._fetch_page(url)
                result.extend(chars)
            except Exception as e:
                logger.debug(f"[Kakaopage] {url} 실패: {e}")

        if result:
            logger.info(f"[Kakaopage] {len(result)}개 수집")
        else:
            logger.warning("[Kakaopage] 수집 실패")
        return result[: self.cfg.top_n]

    def _fetch_page(self, url: str) -> list[Character]:
        resp = self.session.get(url, timeout=self.cfg.request_timeout)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # __NEXT_DATA__ JSON 추출
        next_data_tag = soup.find("script", {"id": "__NEXT_DATA__"})
        if next_data_tag:
            try:
                nd = json.loads(next_data_tag.string)
                # 구조 탐색
                page_props = nd.get("props", {}).get("pageProps", {})
                # 다양한 키 시도
                for key in ["initialState", "dehydratedState", "data"]:
                    data = page_props.get(key, {})
                    if data:
                        chars = self._extract_from_kakao_state(data)
                        if chars:
                            return chars
            except Exception as e:
                logger.debug(f"[Kakaopage] JSON 파싱 실패: {e}")

        # HTML 직접 파싱 (React 빌드라 어렵지만 시도)
        result = []
        for sel in ["[class*='item_']", "[class*='content_']", "li[class*='list']"]:
            items = soup.select(sel)
            if len(items) > 3:
                for item in items[:self.cfg.top_n]:
                    title_el = item.select_one("[class*='title'], strong, h3, h4")
                    link_el = item.select_one("a[href]")
                    if title_el and title_el.get_text(strip=True):
                        result.append(Character(
                            id=f"kakao_{link_el['href'].split('/')[-1] if link_el else ''}",
                            name=title_el.get_text(strip=True),
                            source="kakaopage",
                            description="카카오페이지 인기 웹소설",
                            tags=["웹소설"],
                            url=self.BASE + link_el["href"] if link_el and link_el["href"].startswith("/") else "",
                        ))
                if result:
                    return result
        return result

    def _extract_from_kakao_state(self, state: dict, depth: int = 0) -> list[Character]:
        if depth > 5:
            return []
        result = []
        if isinstance(state, dict):
            # contentList 또는 items 키 탐색
            for key in ["contentList", "items", "list", "contents"]:
                items = state.get(key, [])
                if isinstance(items, list) and items:
                    for item in items[:self.cfg.top_n]:
                        if isinstance(item, dict) and item.get("title"):
                            cid = str(item.get("id", item.get("contentId", "")))
                            result.append(Character(
                                id=f"kakao_{cid}",
                                name=item.get("title", ""),
                                source="kakaopage",
                                description=item.get("description", item.get("synopsis", "카카오페이지 인기 작품")),
                                tags=item.get("tags", ["웹소설"]),
                                creator=item.get("author", item.get("authorName", "")),
                                interaction_count=item.get("viewCount", 0),
                                url=f"{self.BASE}/content/{cid}",
                                raw=item,
                            ))
                    if result:
                        return result
            # 재귀
            for v in state.values():
                if isinstance(v, (dict, list)):
                    sub = self._extract_from_kakao_state(v, depth + 1)
                    if sub:
                        return sub
        elif isinstance(state, list):
            for item in state:
                sub = self._extract_from_kakao_state(item, depth + 1)
                if sub:
                    return sub
        return result


# ──────────────────────────────────────────────
# 3차 최종 폴백: 큐레이션 샘플
# ──────────────────────────────────────────────
SAMPLE_CHARACTERS = [
    # 실제 인기 한국 웹소설/웹툰 캐릭터 기반 큐레이션
    Character(id="s01", name="나 혼자만 레벨업 - 성진우", source="sample",
              description="죽음의 문턱에서 단독 플레이어가 된 헌터. 한국 판타지 웹소설 역대급 인기 캐릭터.",
              tags=["판타지", "헌터", "성장"], interaction_count=9800000,
              url="https://page.kakao.com/content/53870139"),
    Character(id="s02", name="재혼 황후 - 나비예", source="sample",
              description="황후 자리를 스스로 버리고 적국 황제에게 청혼한 여성. 로맨스판타지 정점.",
              tags=["로맨스판타지", "황후", "역하렘"], interaction_count=8400000,
              url="https://page.kakao.com/content/52186105"),
    Character(id="s03", name="전지적 독자 시점 - 김독자", source="sample",
              description="소설 속 세계에 들어온 유일한 독자. 서사와 메타 구조가 독보적인 캐릭터.",
              tags=["판타지", "메타픽션", "아포칼립스"], interaction_count=7600000,
              url="https://series.naver.com/novel/detail?productNo=4686253"),
    Character(id="s04", name="내 남편과 결혼해줘 - 강지원", source="sample",
              description="죽어서 과거로 돌아온 여자가 남편의 내연녀에게 복수하는 회귀 로맨스.",
              tags=["로맨스판타지", "회귀", "복수"], interaction_count=7200000,
              url="https://page.kakao.com/content/58266261"),
    Character(id="s05", name="외과의사 엘리제 - 엘리제", source="sample",
              description="현대 외과의사가 처형될 귀족 영애로 빙의. 의학+판타지 장르 퓨전의 선구자.",
              tags=["로맨스판타지", "빙의", "의학"], interaction_count=6900000,
              url="https://ridibooks.com/books/3518000003"),
    Character(id="s06", name="사내맞선 - 강태무", source="sample",
              description="재벌 3세와 평범한 여성의 사내 맞선 로맨스. 드라마화된 인기 캐릭터.",
              tags=["현대로맨스", "재벌", "사내연애"], interaction_count=6500000,
              url="https://page.kakao.com/content/55918597"),
    Character(id="s07", name="랭커의 귀환 - 하진호", source="sample",
              description="최강 랭커가 초보자로 돌아와 다시 정점을 향해 달리는 게임판타지.",
              tags=["게임판타지", "회귀", "성장"], interaction_count=6100000,
              url="https://series.naver.com/novel/detail?productNo=6768520"),
    Character(id="s08", name="황제와 여기사 - 리아나", source="sample",
              description="황제를 지키는 여기사. 강인함과 내면의 상처가 공존하는 복잡한 캐릭터성.",
              tags=["로맨스판타지", "기사", "황실"], interaction_count=5800000,
              url="https://ridibooks.com/romance-fantasy/bestsellers"),
    Character(id="s09", name="템빨 - 류한빈", source="sample",
              description="아이템 스펙으로만 최강이 된 남자. 한국 게임판타지 밈 캐릭터의 원조.",
              tags=["게임판타지", "아이템", "코믹"], interaction_count=5500000,
              url="https://comic.naver.com/webtoon/list?titleId=557672"),
    Character(id="s10", name="여신강림 - 임주경", source="sample",
              description="메이크업으로 외모 콤플렉스를 극복한 소녀. 네이버 웹툰 누적 조회 1위권.",
              tags=["로맨스", "학원", "성장"], interaction_count=9200000,
              url="https://comic.naver.com/webtoon/list?titleId=703847"),
]


# ──────────────────────────────────────────────
# 통합 진입점
# ──────────────────────────────────────────────
def scrape_all(cfg: TrackerConfig) -> list["Character"]:
    """기존 호환성을 위한 래퍼 - run_pipeline.py의 _scrape_with_sources를 사용 권장"""
    all_chars: list[Character] = []

    logger.info("[Scraper] Zeta AI 스크래핑 시작...")
    zeta_chars = ZetaScraper(cfg).fetch()
    logger.info(f"[Scraper] Zeta: {len(zeta_chars)}개 수집 완료")
    all_chars.extend(zeta_chars)
    time.sleep(cfg.request_delay)

    logger.info("[Scraper] Crack AI 스크래핑 시작...")
    crack_chars = CrackScraper(cfg).fetch()
    logger.info(f"[Scraper] Crack: {len(crack_chars)}개 수집 완료")
    all_chars.extend(crack_chars)

    if len(all_chars) < cfg.top_k:
        logger.info("[Scraper] 1차 수집 부족 → 한국 플랫폼 폴백")
        time.sleep(cfg.request_delay)
        naver_chars = NaverWebtoonScraper(cfg).fetch()
        all_chars.extend(naver_chars)
        if len(all_chars) < cfg.top_k:
            time.sleep(cfg.request_delay)
            ridi_chars = RidiScraper(cfg).fetch()
            all_chars.extend(ridi_chars)
        if len(all_chars) < cfg.top_k:
            time.sleep(cfg.request_delay)
            kakao_chars = KakaopageScraper(cfg).fetch()
            all_chars.extend(kakao_chars)

    if not all_chars:
        logger.warning("[Scraper] 모든 수집 실패 → 큐레이션 샘플 사용")
        all_chars = SAMPLE_CHARACTERS[: cfg.top_n]

    logger.info(f"[Scraper] 최종 {len(all_chars)}개 캐릭터 수집 완료")
    return all_chars
