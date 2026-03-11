#!/bin/bash
# AI VTuber 설치 스크립트 (macOS / Apple Silicon)
set -e

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  AI VTuber (MotionPNGTuber 기반) 설치"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── 1. Python 버전 확인 ──────────────────────────────
echo ""
echo "[1/5] Python 확인..."
PYTHON_CMD=""
for cmd in python3.11 python3.10 python3 python; do
    if command -v "$cmd" &>/dev/null; then
        VER=$("$cmd" --version 2>&1)
        echo "  사용: $VER ($cmd)"
        PYTHON_CMD="$cmd"
        break
    fi
done
if [ -z "$PYTHON_CMD" ]; then
    echo "  [오류] Python을 찾을 수 없습니다. Python 3.10 이상을 설치하세요."
    exit 1
fi

# ── 2. 가상환경 생성 ─────────────────────────────────
echo ""
echo "[2/5] 가상환경 생성..."
if [ ! -d ".venv" ]; then
    $PYTHON_CMD -m venv .venv
    echo "  .venv 생성 완료"
else
    echo "  .venv 이미 존재함"
fi
source .venv/bin/activate

# ── 3. 의존성 설치 ──────────────────────────────────
echo ""
echo "[3/5] 의존성 설치..."
pip install --upgrade pip -q
pip install -r requirements.txt

echo ""
echo "  MotionPNGTuber 추가 의존성..."
pip install scipy>=1.10.0

# ── 4. MotionPNGTuber 다운로드 (선택사항) ────────────
echo ""
echo "[4/5] MotionPNGTuber 도구 설치 여부 확인..."
echo "  MotionPNGTuber를 클론하면 고급 입 추적 도구를 사용할 수 있습니다."
echo "  (입 제거 영상 생성, 고급 감정 분석 등)"
read -p "  MotionPNGTuber 클론? (y/N): " clone_mpng
if [[ "$clone_mpng" =~ ^[Yy]$ ]]; then
    if [ ! -d "MotionPNGTuber" ]; then
        git clone https://github.com/rotejin/MotionPNGTuber.git
        echo "  MotionPNGTuber 클론 완료"
    else
        echo "  MotionPNGTuber 이미 존재함"
    fi
fi

# ── 5. 에셋 폴더 및 샘플 확인 ──────────────────────
echo ""
echo "[5/5] 에셋 폴더 준비..."
mkdir -p assets/character
mkdir -p assets/mouth/{neutral,happy,sad,angry,surprised}

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  설치 완료!"
echo ""
echo "  다음 단계:"
echo ""
echo "  1. API 키 설정"
echo "     export OPENAI_API_KEY=your_openai_key"
echo ""
echo "  2. 캐릭터 영상 추가"
echo "     → assets/character/idle.mp4  (루프 영상)"
echo ""
echo "  3. 입 스프라이트 추가 (MotionPNGTuber 형식)"
echo "     → assets/mouth/neutral/closed.png"
echo "     → assets/mouth/neutral/half.png"
echo "     → assets/mouth/neutral/open.png"
echo "     → assets/mouth/neutral/u.png"
echo "     → assets/mouth/neutral/e.png"
echo "     (happy, sad, angry, surprised 폴더도 동일한 구조)"
echo ""
echo "  4. 설정 편집 (선택사항)"
echo "     → config/character.yaml"
echo ""
echo "  5. 실행"
echo "     source .venv/bin/activate"
echo "     python main.py"
echo ""
echo "  [도움말] python main.py --help"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
