#!/usr/bin/env python3
"""
AI VTuber - 메인 진입점

macOS 제약으로 인해 cv2.imshow는 메인 스레드에서만 실행 가능합니다.
구조:
  메인 스레드  → 렌더 루프 (render_tick @ 30fps)
  백그라운드   → asyncio 이벤트 루프 (AI 응답 + TTS + stdin)

사용법:
    python main.py                       # 터미널 대화 모드
    python main.py --speak "안녕하세요!" # 발화 테스트
    python main.py --tiktok 아이디       # TikTok Live 연동
    python main.py --list-voices         # 음성 목록 확인
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import threading
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def parse_args():
    p = argparse.ArgumentParser(description="AI VTuber (MotionPNGTuber 기반)")
    p.add_argument("--config", default="config/character.yaml")
    p.add_argument("--tiktok", metavar="USERNAME")
    p.add_argument("--speak", metavar="TEXT")
    p.add_argument("--list-voices", action="store_true")
    p.add_argument("--no-preview", action="store_true")
    p.add_argument("--debug", action="store_true")
    return p.parse_args()


# ── 비동기 태스크들 (백그라운드 스레드의 asyncio 루프에서 실행) ──────────────

async def run_interactive(controller):
    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  AI VTuber 대화 모드")
    print("  종료: Ctrl+C 또는 'quit' 입력")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

    loop = asyncio.get_event_loop()
    while True:
        try:
            user_input = await loop.run_in_executor(
                None, lambda: input("You> ").strip()
            )
        except (EOFError, KeyboardInterrupt):
            break

        if not user_input or user_input.lower() in ("quit", "exit", "종료"):
            break

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
    from ai_vtuber.vtuber_controller import TikTokChatReader
    reader = TikTokChatReader(username=username, controller=controller)
    print(f"\nTikTok Live 연결 중: @{username}")
    print("종료: Ctrl+C\n")
    await reader.run()


async def list_voices_async():
    from ai_vtuber.tts_engine import EdgeTTSEngine
    voices = await EdgeTTSEngine.list_voices("ko-KR")
    print("\n[edge-tts 한국어 음성 목록]")
    for v in voices:
        print(f"  {v}")
    print()


# ── 메인 ────────────────────────────────────────────────────────────────────

def main():
    args = parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.list_voices:
        asyncio.run(list_voices_async())
        return

    # 설정 로드
    from ai_vtuber.config import load_config
    cfg = load_config(args.config)

    if args.no_preview:
        cfg.setdefault("lipsync", {}).setdefault("output", {})["preview_window"] = False

    # API 키 확인
    ai_cfg = cfg.get("ai", {})
    if not ai_cfg.get("api_key"):
        print("[오류] AI API 키가 없습니다.")
        print("  → export OPENAI_API_KEY=sk-proj-...")
        print("     또는 config/character.yaml의 ai.api_key에 입력")
        sys.exit(1)

    # VTuber 컨트롤러 + 브리지 초기화
    from ai_vtuber.vtuber_controller import VTuberController
    controller = VTuberController(cfg)
    bridge = controller.bridge
    bridge.start()  # 렌더 스레드 없이 초기화만

    # ── 비동기 태스크를 백그라운드 스레드에서 실행 ──────────────────────────
    loop = asyncio.new_event_loop()
    stop_event = threading.Event()

    async def async_task():
        if args.speak:
            await controller.speak_text(args.speak)
            await asyncio.sleep(6)
        elif args.tiktok:
            await run_tiktok(controller, args.tiktok)
        else:
            await run_interactive(controller)

    def run_async():
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(async_task())
        except Exception as e:
            logger.error(f"비동기 오류: {e}")
        finally:
            stop_event.set()

    async_thread = threading.Thread(target=run_async, daemon=True, name="async-loop")
    async_thread.start()

    # ── 렌더 루프 (메인 스레드, macOS 필수) ────────────────────────────────
    frame_dt = 1.0 / bridge._render_fps
    try:
        while bridge.running and not stop_event.is_set():
            t0 = time.perf_counter()

            if not bridge.render_tick():   # q키 누르면 False
                break

            elapsed = time.perf_counter() - t0
            sleep_t = frame_dt - elapsed
            if sleep_t > 0:
                time.sleep(sleep_t)

    except KeyboardInterrupt:
        print("\n종료합니다...")
    finally:
        bridge.stop()
        stop_event.set()
        async_thread.join(timeout=1)


if __name__ == "__main__":
    main()
