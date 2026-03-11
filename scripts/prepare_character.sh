#!/bin/bash
# 캐릭터 영상에서 입 추적 데이터를 생성합니다 (MotionPNGTuber 사용)
# 사용법: ./scripts/prepare_character.sh assets/character/idle.mp4

set -e

VIDEO="${1:-assets/character/idle.mp4}"
MPNG_DIR="./MotionPNGTuber"

if [ ! -d "$MPNG_DIR" ]; then
    echo "[오류] MotionPNGTuber가 없습니다. setup.sh에서 클론하거나:"
    echo "  git clone https://github.com/rotejin/MotionPNGTuber.git"
    exit 1
fi

if [ ! -f "$VIDEO" ]; then
    echo "[오류] 영상 파일 없음: $VIDEO"
    exit 1
fi

source .venv/bin/activate

echo "입 추적 GUI를 실행합니다..."
echo "영상: $VIDEO"
cd "$MPNG_DIR"
python mouth_track_gui.py
