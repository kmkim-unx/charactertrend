#!/usr/bin/env python3
"""
샘플 입 스프라이트를 생성합니다 (실제 캐릭터 이미지가 없을 때 테스트용).
각 감정 폴더에 간단한 원형 입 이미지를 생성합니다.
"""
from pathlib import Path
import numpy as np
import cv2

EMOTIONS = ["neutral", "happy", "sad", "angry", "surprised"]
SPRITE_SIZE = (120, 60)  # width x height

# 감정별 색상 (B, G, R)
EMOTION_COLORS = {
    "neutral":   (200, 180, 160),
    "happy":     (100, 200, 100),
    "sad":       (200, 100, 100),
    "angry":     (60,  60,  220),
    "surprised": (50,  200, 220),
}

def make_mouth_sprite(shape: str, color_bgr: tuple, size: tuple) -> np.ndarray:
    """입 모양 스프라이트 생성 (BGRA)"""
    w, h = size
    img = np.zeros((h, w, 4), dtype=np.uint8)

    cx, cy = w // 2, h // 2
    b, g, r = color_bgr

    if shape == "closed":
        # 얇은 선
        cv2.ellipse(img, (cx, cy), (w//3, 4), 0, 0, 180, (b, g, r, 255), 3)

    elif shape == "half":
        # 반쯤 벌린 타원
        cv2.ellipse(img, (cx, cy), (w//3, h//4), 0, 0, 180, (b, g, r, 255), -1)
        cv2.ellipse(img, (cx, cy), (w//3, h//4), 0, 0, 180, (b, g, r, 100), 2)

    elif shape == "open":
        # 크게 벌린 타원
        cv2.ellipse(img, (cx, cy), (w//3, h//2 - 4), 0, 0, 360, (b, g, r, 255), -1)

    elif shape == "u":
        # u 발음 (좁고 앞으로 내민)
        cv2.ellipse(img, (cx, cy), (w//5, h//3), 0, 0, 360, (b, g, r, 255), -1)

    elif shape == "e":
        # e 발음 (넓고 평평)
        cv2.ellipse(img, (cx, cy), (w//2 - 5, h//5), 0, 0, 360, (b, g, r, 255), -1)

    return img


def main():
    base = Path("assets/mouth")
    for emotion in EMOTIONS:
        folder = base / emotion
        folder.mkdir(parents=True, exist_ok=True)
        color = EMOTION_COLORS.get(emotion, (180, 180, 180))

        for shape in ["closed", "half", "open", "u", "e"]:
            sprite = make_mouth_sprite(shape, color, SPRITE_SIZE)
            out_path = folder / f"{shape}.png"
            cv2.imwrite(str(out_path), sprite)
            print(f"  생성: {out_path}")

    print("\n샘플 스프라이트 생성 완료!")
    print("실제 캐릭터 스프라이트로 교체하려면 assets/mouth/{emotion}/*.png 파일을 교체하세요.")


if __name__ == "__main__":
    main()
