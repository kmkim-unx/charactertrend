"""
캐릭터 이미지 URL 추출
- OG 이미지 fetch (character.url 에서)
- Naver/Ridi/Kakao CDN 패턴 매칭
- 실패 시 None 반환
"""
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
}


def fetch_og_image(url: str, timeout: int = 5) -> str | None:
    """URL에서 OG:image 메타태그 추출"""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        # og:image
        og = soup.find("meta", property="og:image") or soup.find("meta", attrs={"name": "og:image"})
        if og and og.get("content"):
            return og["content"]
        # twitter:image
        tw = soup.find("meta", attrs={"name": "twitter:image"})
        if tw and tw.get("content"):
            return tw["content"]
    except Exception:
        pass
    return None


def get_naver_webtoon_thumbnail(title_id: str) -> str | None:
    """네이버 웹툰 썸네일 URL 구성"""
    # 네이버 웹툰 API에서 썸네일 직접 조회
    try:
        resp = requests.get(
            f"https://comic.naver.com/api/webtoon/titlelist/search?keyword=&titleId={title_id}",
            headers=HEADERS, timeout=5
        )
        # 공개 API에서 thumbnailUrl 추출 시도
        data = resp.json()
        items = data.get("titleList", {}).get("items", [])
        if items:
            return items[0].get("thumbnailUrl")
    except Exception:
        pass
    return None


def get_ridi_cover(book_id: str) -> str:
    """리디 표지 URL (CDN 패턴)"""
    return f"https://img.ridicdn.net/cover/{book_id}/large"


def enrich_images(characters, timeout: int = 5) -> list:
    """캐릭터 목록에 이미지 URL 보강"""
    import logging
    logger = logging.getLogger(__name__)
    for char in characters:
        if char.image_url:
            continue  # 이미 있으면 스킵
        # 소스별 처리
        if char.source == "naver_webtoon":
            tid = char.id.replace("naver_", "")
            img = get_naver_webtoon_thumbnail(tid)
            if img:
                char.image_url = img
                continue
        if char.source == "ridi":
            bid = char.id.replace("ridi_", "")
            char.image_url = get_ridi_cover(bid)
            continue
        # OG 이미지 fetch (URL 있으면)
        if char.url and char.url.startswith("http"):
            img = fetch_og_image(char.url, timeout=timeout)
            if img:
                char.image_url = img
                logger.debug(f"[ImageFetcher] {char.name}: {img[:60]}")
    return characters
