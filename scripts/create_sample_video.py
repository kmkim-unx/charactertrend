#!/usr/bin/env python3
"""
테스트용 샘플 캐릭터 영상을 생성합니다 (실제 영상이 없을 때).
단색 배경에 캐릭터 아웃라인을 그린 루프 영상입니다.
"""
from pathlib import Path
import numpy as np
import cv2

OUTPUT = "assets/character/idle.mp4"
FPS = 30
DURATION_SEC = 3
WIDTH, HEIGHT = 1280, 720


def create_character_frame(frame_idx: int, total_frames: int) -> np.ndarray:
    """간단한 캐릭터 프레임 생성 (bounce 애니메이션)"""
    img = np.full((HEIGHT, WIDTH, 3), (40, 30, 25), dtype=np.uint8)

    # 배경 그라디언트
    for y in range(HEIGHT):
        alpha = y / HEIGHT
        img[y] = (
            int(40 + 20 * alpha),
            int(30 + 15 * alpha),
            int(25 + 10 * alpha),
        )

    # 바운스 오프셋 (부드러운 호흡 효과)
    bounce = np.sin(frame_idx / total_frames * 2 * np.pi) * 8

    cx = WIDTH // 2
    cy = int(HEIGHT // 2 + bounce)

    # 몸통 (타원)
    cv2.ellipse(img, (cx, cy + 120), (180, 240), 0, 0, 360, (100, 80, 160), -1)

    # 얼굴 (원)
    cv2.circle(img, (cx, cy - 40), 140, (230, 200, 180), -1)

    # 머리카락
    cv2.ellipse(img, (cx, cy - 100), (155, 100), 0, 180, 360, (50, 30, 80), -1)
    cv2.ellipse(img, (cx, cy - 40), (155, 155), 0, 200, 340, (50, 30, 80), 20)

    # 눈
    eye_blink = 1.0 if frame_idx % total_frames > 5 else 0.1
    eye_h = max(2, int(15 * eye_blink))
    cv2.ellipse(img, (cx - 50, cy - 50), (20, eye_h), 0, 0, 360, (60, 40, 100), -1)
    cv2.ellipse(img, (cx + 50, cy - 50), (20, eye_h), 0, 0, 360, (60, 40, 100), -1)
    # 눈동자
    if eye_blink > 0.5:
        cv2.circle(img, (cx - 50, cy - 50), 8, (20, 15, 30), -1)
        cv2.circle(img, (cx + 50, cy - 50), 8, (20, 15, 30), -1)

    # 입 영역 (스프라이트가 합성될 위치 표시)
    mouth_cx = cx
    mouth_cy = cy + 30
    cv2.ellipse(img, (mouth_cx, mouth_cy), (30, 8), 0, 0, 180, (180, 100, 100), -1)

    # 텍스트
    cv2.putText(
        img, "AI VTuber Sample",
        (WIDTH // 2 - 150, HEIGHT - 30),
        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (180, 180, 180), 2
    )

    return img


def main():
    output_path = Path(OUTPUT)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    total_frames = FPS * DURATION_SEC
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(output_path), fourcc, FPS, (WIDTH, HEIGHT))

    print(f"샘플 영상 생성 중: {output_path}")
    for i in range(total_frames):
        frame = create_character_frame(i, total_frames)
        writer.write(frame)
        if i % FPS == 0:
            print(f"  {i}/{total_frames} 프레임...")

    writer.release()
    print(f"\n완료: {output_path}")
    print(f"  크기: {WIDTH}x{HEIGHT}, {FPS}fps, {DURATION_SEC}초")
    print("\n실제 캐릭터 영상으로 교체: assets/character/idle.mp4")


if __name__ == "__main__":
    main()
