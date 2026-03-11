#!/usr/bin/env python3
"""
AI VTuber - 메인 진입점

사용법:
    python main.py                          # 기본 대화 모드 (터미널 입력)
    python main.py --config config/character.yaml
    python main.py --tiktok @username       # TikTok Live 채팅 연동
    python main.py --speak "안녕하세요!"    # 단일 발화 테스트
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def parse_args():
    p = argparse.ArgumentParser(description="AI VTuber (MotionPNGTuber 기반)")
    p.add_argument(
        "--config", default="config/character.yaml",
        help="설정 파일 경로 (기본: config/character.yaml)"
    )
    p.add_argument("--tiktok", metavar="USERNAME", help="TikTok 사용자명 (@없이)")
    p.add_argument("--speak", metavar="TEXT", help="텍스트를 바로 발화하고 종료")
    p.add_argument("--list-voices", action="store_true", help="edge-tts 한국어 음성 목록 출력")
    p.add_argument("--no-preview", action="store_true", help="미리보기 창 숨기기")
    p.add_argument("--debug", action="store_true", help="디버그 로그 출력")
    return p.parse_args()


async def run_interactive(controller):
    """터미널에서 대화를 입력받는 인터랙티브 모드"""
    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  AI VTuber 대화 모드")
    print("  종료: Ctrl+C 또는 'quit' 입력")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

    loop = asyncio.get_event_loop()
    while True:
        try:
            # 비동기 stdin 읽기
            user_input = await loop.run_in_executor(
                None, lambda: input("You> ").strip()
            )
        except (EOFError, KeyboardInterrupt):
            break

        if not user_input or user_input.lower() in ("quit", "exit", "종료"):
            break

        # 감정 강제 변경 명령어
        if user_input.startswith("/emotion "):
            emotion = user_input.split(" ", 1)[1].strip()
            controller.set_emotion(emotion)
            print(f"[감정 변경] → {emotion}")
            continue

        if user_input == "/reset":
            controller.reset_history()
            print("[대화 기록 초기화]")
            continue

        response = await controller.respond(user_input)
        print(f"VTuber> {response}\n")


async def run_tiktok(controller, username: str):
    """TikTok Live 채팅 연동 모드"""
    from ai_vtuber.vtuber_controller import TikTokChatReader
    reader = TikTokChatReader(username=username, controller=controller)
    print(f"\nTikTok Live 연결 중: @{username}")
    print("종료: Ctrl+C\n")
    await reader.run()


async def list_voices():
    """edge-tts 한국어 음성 목록 출력"""
    from ai_vtuber.tts_engine import EdgeTTSEngine
    voices = await EdgeTTSEngine.list_voices("ko-KR")
    print("\n[edge-tts 한국어 음성 목록]")
    for v in voices:
        print(f"  {v}")
    print()


async def main():
    args = parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.list_voices:
        await list_voices()
        return

    # 설정 로드
    from ai_vtuber.config import load_config
    cfg = load_config(args.config)

    # 미리보기 창 끄기 옵션
    if args.no_preview:
        cfg.setdefault("lipsync", {}).setdefault("output", {})["preview_window"] = False

    # API 키 확인
    ai_cfg = cfg.get("ai", {})
    if not ai_cfg.get("api_key"):
        print(f"[오류] AI API 키가 없습니다.")
        print(f"  → 환경변수 설정: export OPENAI_API_KEY=your_key")
        print(f"     또는 config/character.yaml의 ai.api_key에 입력")
        sys.exit(1)

    # VTuber 컨트롤러 초기화 및 시작
    from ai_vtuber.vtuber_controller import VTuberController
    controller = VTuberController(cfg)
    controller.start()

    try:
        if args.speak:
            # 단일 발화 모드
            await controller.speak_text(args.speak)
            await asyncio.sleep(5)  # 발화 완료 대기
        elif args.tiktok:
            await run_tiktok(controller, args.tiktok)
        else:
            await run_interactive(controller)
    except KeyboardInterrupt:
        print("\n종료합니다...")
    finally:
        controller.stop()


if __name__ == "__main__":
    asyncio.run(main())
