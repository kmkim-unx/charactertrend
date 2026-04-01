#!/usr/bin/env python3
"""
UNX Character Tracker — 메인 파이프라인

실행:
    python run_pipeline.py
    python run_pipeline.py --sources naver,ridi,kakaopage
    python run_pipeline.py --sources all --no-notion --open

환경변수 (.env 또는 export):
    OPENAI_API_KEY      필수 (G3/G4/G5 분석)
    NOTION_API_KEY      필수 (노션 아카이빙)
    NOTION_DATABASE_ID  필수 (대상 DB ID)
"""
import argparse
import json
import logging
import os
import sys
import traceback
import webbrowser
from datetime import datetime
from pathlib import Path
from dataclasses import asdict

# .env 자동 로드 (python-dotenv 설치 시)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from tracker.config import load_config
from tracker.scraper import scrape_all, Character
from tracker.analyzer import analyze_and_rank, ScoredCharacter
from tracker.archiver import archive_to_notion

# ──────────────────────────────────────────────
# 로깅 설정
# ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

VALID_SOURCES = ["zeta", "crack", "rofan", "naver_webtoon", "ridi", "kakaopage", "sample"]


def _parse_sources(sources_arg: str) -> list[str]:
    """--sources 인수 파싱: 'all' 또는 콤마 구분 소스명"""
    if not sources_arg or sources_arg.strip().lower() == "all":
        return list(VALID_SOURCES)
    result = []
    for s in sources_arg.split(","):
        s = s.strip().lower()
        # naver → naver_webtoon 별칭 처리
        if s == "naver":
            s = "naver_webtoon"
        if s == "kakao":
            s = "kakaopage"
        if s in VALID_SOURCES:
            result.append(s)
        else:
            logger.warning(f"알 수 없는 소스 무시: {s!r} (유효: {VALID_SOURCES})")
    return result or list(VALID_SOURCES)


def _save_error(error_log_path: str, stage: str, error: Exception) -> None:
    Path(error_log_path).parent.mkdir(parents=True, exist_ok=True)
    existing: list = []
    if Path(error_log_path).exists():
        try:
            existing = json.loads(Path(error_log_path).read_text(encoding="utf-8"))
        except Exception:
            existing = []
    existing.append(
        {
            "timestamp": datetime.now().isoformat(),
            "stage": stage,
            "error": str(error),
            "traceback": traceback.format_exc(),
        }
    )
    Path(error_log_path).write_text(
        json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _char_to_dict(sc: ScoredCharacter) -> dict:
    c = sc.character
    return {
        "name": c.name,
        "source": c.source,
        "description": c.description,
        "tags": c.tags,
        "interaction_count": c.interaction_count,
        "url": c.url,
        "image_url": c.image_url,
        "g3": sc.g3,
        "g4": sc.g4,
        "g5": sc.g5,
        "total": sc.total,
        "reason": sc.reason,
        "unx_fit": sc.unx_fit,
    }


def _scrape_with_sources(cfg, enabled_sources: list[str]) -> list[Character]:
    """enabled_sources 목록에 따라 선택적 스크래핑"""
    import time
    from tracker.scraper import (
        ZetaScraper, CrackScraper, NaverWebtoonScraper,
        RidiScraper, KakaopageScraper, SAMPLE_CHARACTERS
    )

    all_chars: list[Character] = []

    if "zeta" in enabled_sources:
        logger.info("[Scraper] Zeta AI 브라우저 스크래핑 시작...")
        try:
            from tracker.browser_scraper import scrape_zeta_ranking
            zeta_chars = scrape_zeta_ranking(cfg)
            if not zeta_chars:
                # 브라우저 실패 시 기존 스크래퍼 폴백
                from tracker.scraper import ZetaScraper
                zeta_chars = ZetaScraper(cfg).fetch()
        except Exception as e:
            logger.warning(f"[Zeta] 브라우저 실패, 기존 방식 시도: {e}")
            from tracker.scraper import ZetaScraper
            zeta_chars = ZetaScraper(cfg).fetch()
        logger.info(f"[Scraper] Zeta: {len(zeta_chars)}개")
        all_chars.extend(zeta_chars)
        time.sleep(cfg.request_delay)

    if "crack" in enabled_sources:
        logger.info("[Scraper] Crack AI 브라우저 스크래핑 시작...")
        try:
            from tracker.browser_scraper import scrape_crack_ranking
            crack_chars = scrape_crack_ranking(cfg)
            if not crack_chars:
                from tracker.scraper import CrackScraper
                crack_chars = CrackScraper(cfg).fetch()
        except Exception as e:
            logger.warning(f"[Crack] 브라우저 실패, 기존 방식 시도: {e}")
            from tracker.scraper import CrackScraper
            crack_chars = CrackScraper(cfg).fetch()
        logger.info(f"[Scraper] Crack: {len(crack_chars)}개")
        all_chars.extend(crack_chars)
        time.sleep(cfg.request_delay)

    if "rofan" in enabled_sources:
        logger.info("[Scraper] Rofan AI 랭킹 브라우저 스크래핑...")
        try:
            from tracker.browser_scraper import scrape_rofan_ranking
            rofan_chars = scrape_rofan_ranking(cfg)
        except Exception as e:
            logger.warning(f"[Rofan] 브라우저 스크래핑 실패: {e}")
            rofan_chars = []
        logger.info(f"[Scraper] Rofan: {len(rofan_chars)}개")
        all_chars.extend(rofan_chars)
        time.sleep(cfg.request_delay)

    if "naver_webtoon" in enabled_sources:
        logger.info("[Scraper] 네이버 웹툰 인기순위 스크래핑...")
        naver_chars = NaverWebtoonScraper(cfg).fetch()
        logger.info(f"[Scraper] 네이버 웹툰: {len(naver_chars)}개")
        all_chars.extend(naver_chars)
        time.sleep(cfg.request_delay)

    if "ridi" in enabled_sources:
        logger.info("[Scraper] 리디북스 베스트셀러 스크래핑...")
        ridi_chars = RidiScraper(cfg).fetch()
        logger.info(f"[Scraper] 리디: {len(ridi_chars)}개")
        all_chars.extend(ridi_chars)
        time.sleep(cfg.request_delay)

    if "kakaopage" in enabled_sources:
        logger.info("[Scraper] 카카오페이지 인기순위 스크래핑...")
        kakao_chars = KakaopageScraper(cfg).fetch()
        logger.info(f"[Scraper] 카카오페이지: {len(kakao_chars)}개")
        all_chars.extend(kakao_chars)

    # sample: 아무것도 없거나 명시적으로 지정된 경우
    if not all_chars or "sample" in enabled_sources:
        if not all_chars:
            logger.warning("[Scraper] 모든 수집 실패 → 한국 웹소설 큐레이션 샘플 사용")
        elif "sample" in enabled_sources:
            logger.info("[Scraper] 샘플 캐릭터 추가...")
        all_chars.extend(SAMPLE_CHARACTERS[: cfg.top_n])

    logger.info(f"[Scraper] 최종 {len(all_chars)}개 캐릭터 수집 완료")
    return all_chars


def main() -> int:
    parser = argparse.ArgumentParser(description="UNX Character Tracker 파이프라인")
    parser.add_argument(
        "--sources",
        default="all",
        help="수집 소스 (콤마 구분): zeta,crack,naver,ridi,kakaopage,sample 또는 'all' (기본값: all)",
    )
    parser.add_argument(
        "--no-notion",
        action="store_true",
        help="노션 아카이빙 건너뜀",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        help="완료 후 브라우저에서 dashboard.html 자동 오픈",
    )
    args = parser.parse_args()

    cfg = load_config()
    enabled_sources = _parse_sources(args.sources)
    cfg.enabled_sources = enabled_sources
    Path(cfg.output_dir).mkdir(parents=True, exist_ok=True)

    logger.info("=" * 60)
    logger.info("UNX Character Tracker 파이프라인 시작")
    logger.info(f"날짜: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"소스: {', '.join(enabled_sources)}")
    logger.info("=" * 60)

    # ── Step 1: 스크래핑 ──────────────────────────────────────
    logger.info("\n[Step 1] 스크래핑")
    try:
        characters = _scrape_with_sources(cfg, enabled_sources)
    except Exception as e:
        logger.error(f"스크래핑 전체 실패: {e}")
        _save_error(cfg.error_log, "scraping", e)
        return 1

    if not characters:
        logger.error("수집된 캐릭터가 없습니다. 파이프라인 중단.")
        _save_error(cfg.error_log, "scraping", ValueError("0 characters collected"))
        return 1

    # ── Step 1.5: 이미지 보강 ────────────────────────────────
    logger.info(f"\n[Step 1.5] 이미지 URL 보강")
    try:
        from tracker.image_fetcher import enrich_images
        characters = enrich_images(characters, timeout=5)
        img_count = sum(1 for c in characters if c.image_url)
        logger.info(f"[ImageFetcher] 이미지 보강 완료: {img_count}/{len(characters)}개")
    except Exception as e:
        logger.warning(f"이미지 보강 실패 (계속 진행): {e}")

    # ── Step 2: G3/G4/G5 분석 ────────────────────────────────
    logger.info(f"\n[Step 2] G3/G4/G5 분석 ({len(characters)}개 → Top-{cfg.top_k})")
    try:
        top_k = analyze_and_rank(characters, cfg)
    except Exception as e:
        logger.error(f"분석 실패: {e}")
        _save_error(cfg.error_log, "analysis", e)
        return 1

    # ── Step 3: 노션 아카이빙 ─────────────────────────────────
    archive_ok = True
    if args.no_notion:
        logger.info(f"\n[Step 3] 노션 아카이빙 건너뜀 (--no-notion)")
    else:
        logger.info(f"\n[Step 3] 노션 아카이빙 (Top-{cfg.top_k})")
        try:
            notion_ids = archive_to_notion(top_k, cfg)
            logger.info(f"노션 등록 완료: {len(notion_ids)}건")
        except Exception as e:
            logger.error(f"노션 아카이빙 실패: {e}")
            _save_error(cfg.error_log, "archiving", e)
            archive_ok = False  # 아카이빙 실패해도 결과 파일은 저장

    # ── 결과 파일 저장 ────────────────────────────────────────
    result = {
        "generated_at": datetime.now().isoformat(),
        "total_scraped": len(characters),
        "sources_used": enabled_sources,
        "top_k": [_char_to_dict(sc) for sc in top_k],
        "archive_success": archive_ok,
    }
    Path(cfg.result_file).write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info(f"\n결과 저장: {cfg.result_file}")

    # 날짜별 히스토리 저장
    from datetime import date
    date_str = date.today().isoformat()
    history_dir = Path("public/data")
    history_dir.mkdir(parents=True, exist_ok=True)

    dated_file = history_dir / f"{date_str}.json"
    dated_file.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # index.json 업데이트
    index_file = history_dir / "index.json"
    index_data: list = []
    if index_file.exists():
        try:
            index_data = json.loads(index_file.read_text(encoding="utf-8"))
        except Exception:
            index_data = []

    # 오늘 항목 업데이트 or 추가
    today_entry = {
        "date": date_str,
        "total_scraped": result["total_scraped"],
        "sources_used": result["sources_used"],
        "top5": [
            {
                "rank": i + 1,
                "name": c["name"],
                "source": c["source"],
                "image_url": c["image_url"],
                "total": c["total"],
                "g3": c["g3"],
                "g4": c["g4"],
                "g5": c["g5"],
            }
            for i, c in enumerate(result["top_k"])
        ],
    }
    # 기존 오늘 항목 교체 또는 새로 추가
    index_data = [e for e in index_data if e.get("date") != date_str]
    index_data.insert(0, today_entry)  # 최신 날짜가 맨 앞
    index_file.write_text(
        json.dumps(index_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info(f"히스토리 저장: {dated_file}")

    # ── Step 4: HTML 대시보드 생성 ───────────────────────────
    logger.info(f"\n[Step 4] HTML 대시보드 생성")
    try:
        from tracker.reporter import generate_html
        run_meta = {
            "generated_at": result["generated_at"],
            "sources_used": enabled_sources,
        }
        generate_html(top_k, characters, cfg, run_meta)
        dashboard_path = Path(cfg.output_dir) / "dashboard.html"
        logger.info(f"Dashboard: {dashboard_path} ({dashboard_path.stat().st_size:,} bytes)")
    except Exception as e:
        logger.error(f"HTML 생성 실패: {e}")
        _save_error(cfg.error_log, "html_generation", e)

    logger.info("\n" + "=" * 60)
    logger.info("파이프라인 완료")
    logger.info("=" * 60)

    # ── 브라우저 자동 오픈 ───────────────────────────────────
    if args.open:
        dashboard_path = Path(cfg.output_dir) / "dashboard.html"
        if dashboard_path.exists():
            webbrowser.open(dashboard_path.resolve().as_uri())
            logger.info(f"브라우저 오픈: {dashboard_path.resolve()}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
