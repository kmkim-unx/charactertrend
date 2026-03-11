# AI VTuber 사용 가이드

MotionPNGTuber 기반 커스텀 AI VTuber 시스템 완전 가이드

---

## 목차

1. [시스템 구조 이해](#1-시스템-구조-이해)
2. [최초 설치](#2-최초-설치)
3. [에셋 준비](#3-에셋-준비)
4. [설정 파일 편집](#4-설정-파일-편집)
5. [실행 방법](#5-실행-방법)
6. [실행 중 명령어](#6-실행-중-명령어)
7. [OBS 연동 (방송용)](#7-obs-연동-방송용)
8. [TikTok Live 채팅 연동](#8-tiktok-live-채팅-연동)
9. [입 스프라이트 만들기](#9-입-스프라이트-만들기)
10. [트러블슈팅](#10-트러블슈팅)

---

## 1. 시스템 구조 이해

```
시청자 채팅 (또는 직접 입력)
        │
        ▼
┌─────────────────┐
│  AI 엔진        │  → OpenAI gpt-4o-mini 등으로 응답 생성
│  ai_engine.py   │
└────────┬────────┘
         │ 응답 텍스트
         ▼
┌─────────────────┐
│  감정 분류기    │  → 텍스트 키워드로 happy/sad/angry... 판별
│  emotion_mapper │
└────────┬────────┘
         │ 감정 레이블
         ▼
┌─────────────────┐
│  TTS 엔진       │  → 텍스트 → 음성 오디오(numpy array)
│  tts_engine.py  │
└────────┬────────┘
         │ 오디오 데이터
         ▼
┌─────────────────────────────────────┐
│  립싱크 브리지  lipsync_bridge.py   │
│                                     │
│  ① 스피커로 오디오 출력             │
│  ② 오디오 에너지 분석              │
│     → closed / half / open / u / e │
│  ③ 캐릭터 영상 위에 입 이미지 합성 │
│  ④ 화면 출력 or 가상 카메라(OBS)   │
└─────────────────────────────────────┘
```

**핵심 파일 구조:**
```
aivtuber/
├── main.py                     ← 실행 진입점
├── config/
│   └── character.yaml          ← 모든 설정 (여기만 수정하면 됨)
├── ai_vtuber/
│   ├── ai_engine.py            ← OpenAI/Anthropic API
│   ├── tts_engine.py           ← TTS (edge-tts / Google)
│   ├── emotion_mapper.py       ← 텍스트→감정 분류
│   ├── lipsync_bridge.py       ← 핵심 립싱크 렌더러
│   └── vtuber_controller.py    ← 전체 파이프라인 조율
├── assets/
│   ├── character/
│   │   └── idle.mp4            ← 캐릭터 루프 영상 (직접 준비)
│   └── mouth/
│       ├── neutral/            ← 입 스프라이트 5종
│       ├── happy/
│       ├── sad/
│       ├── angry/
│       └── surprised/
└── scripts/
    ├── create_sample_sprites.py  ← 테스트용 샘플 스프라이트 생성
    └── create_sample_video.py    ← 테스트용 샘플 영상 생성
```

---

## 2. 최초 설치

### 2-1. 프로젝트 폴더로 이동

터미널을 열고 이 프로젝트 폴더로 이동합니다.

```bash
cd ~/aivtuber
```

### 2-2. 자동 설치 스크립트 실행

```bash
./setup.sh
```

스크립트가 자동으로:
- Python 가상환경 `.venv` 생성
- 필요한 패키지 설치 (`requirements.txt`)
- `assets/` 폴더 구조 생성
- MotionPNGTuber 클론 여부 물어봄 (고급 입 추적 도구 필요 시 y)

### 2-3. 가상환경 활성화

**설치 후, 실행할 때마다 반드시 이 명령어를 먼저 실행해야 합니다:**

```bash
source .venv/bin/activate
```

활성화되면 터미널 프롬프트 앞에 `(.venv)` 가 붙습니다:
```
(.venv) kimkwangmin@MacBook ~/aivtuber %
```

### 2-4. API 키 설정

**OpenAI 사용 시 (기본값):**

```bash
export OPENAI_API_KEY=sk-proj-xxxxxxxxxxxxxxxx
```

매번 입력하기 번거로우면 셸 설정 파일에 영구 저장:
```bash
echo 'export OPENAI_API_KEY=sk-proj-xxxxxxxx' >> ~/.zshrc
source ~/.zshrc
```

**Anthropic 사용 시:**
```bash
export ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxxxxx
```

> API 키를 `config/character.yaml` 파일 안에 직접 써도 됩니다.
> 단, 파일을 GitHub 등에 올리면 유출되므로 환경변수 방식을 권장합니다.

---

## 3. 에셋 준비

시스템이 동작하려면 두 가지 에셋이 필요합니다:
1. **캐릭터 영상** (`assets/character/idle.mp4`)
2. **입 스프라이트** (`assets/mouth/*/`)

### 방법 A: 테스트용 샘플 에셋 생성 (바로 시작하고 싶을 때)

실제 캐릭터가 없어도 테스트할 수 있도록 간단한 에셋을 자동 생성합니다.

```bash
# 가상환경 활성화 확인 후
source .venv/bin/activate

# 샘플 캐릭터 영상 생성 (assets/character/idle.mp4)
python scripts/create_sample_video.py

# 샘플 입 스프라이트 생성 (assets/mouth/*/closed.png 등)
python scripts/create_sample_sprites.py
```

### 방법 B: 실제 캐릭터 에셋 사용

#### 캐릭터 영상 준비

- **파일 위치:** `assets/character/idle.mp4`
- **권장 사양:** 1280×720, 30fps, 루프 가능한 영상
- **내용:** 입 부분이 보이는 캐릭터의 대기(idle) 애니메이션
- **포맷:** MP4 (H.264 코덱)

> **팁:** Live2D나 VRoid 캐릭터 영상, 혹은 AI 이미지 생성 후 AnimateDiff 등으로 만든 루프 영상을 사용할 수 있습니다.

#### 입 스프라이트 준비

MotionPNGTuber 형식으로 5종류의 입 이미지가 필요합니다:

```
assets/mouth/
├── neutral/
│   ├── closed.png   ← 입 다문 상태
│   ├── half.png     ← 입 반쯤 벌린 상태
│   ├── open.png     ← 입 크게 벌린 상태
│   ├── u.png        ← "우" 발음 (입술 모아짐)
│   └── e.png        ← "이" 발음 (입 옆으로 당김)
├── happy/           ← 같은 5종, 웃는 입 모양
├── sad/             ← 같은 5종, 슬픈 입 모양
├── angry/           ← 같은 5종, 화난 입 모양
└── surprised/       ← 같은 5종, 놀란 입 모양
```

- **포맷:** PNG (투명 배경, RGBA 권장)
- **크기:** 캐릭터 영상 크기에 맞게 (보통 100~200px 너비)

> **팁:** MotionPNGTuber의 `mouth_sprite_extractor_gui.py` 도구로 기존 캐릭터 이미지에서 입 부분을 추출할 수 있습니다.
> ```bash
> cd MotionPNGTuber
> python mouth_sprite_extractor_gui.py
> ```

---

## 4. 설정 파일 편집

모든 설정은 `config/character.yaml` 한 파일에서 관리합니다.
텍스트 에디터로 열어 수정하세요.

```bash
open config/character.yaml        # macOS 기본 에디터
# 또는
code config/character.yaml        # VSCode
```

### 꼭 확인해야 할 설정들

#### 캐릭터 이름과 성격

```yaml
character:
  name: "내 캐릭터 이름"
  persona: |
    당신은 ○○○입니다.
    항상 한국어로 대화하며, ○○한 성격입니다.
    응답은 2~3문장 이내로 간결하게 합니다.
```

#### AI 모델 선택

```yaml
ai:
  provider: "openai"       # openai 또는 anthropic
  model: "gpt-4o-mini"    # 저렴하고 빠름 (권장)
  # model: "gpt-4o"       # 더 좋은 응답 (비쌈)
  # model: "claude-haiku-4-5-20251001"  # Anthropic 사용 시
```

#### TTS 목소리 변경

```bash
# 사용 가능한 한국어 음성 목록 확인
python main.py --list-voices
```

```yaml
tts:
  provider: "edge-tts"
  edge_tts:
    voice: "ko-KR-SunHiNeural"    # 여성 (기본값)
    # voice: "ko-KR-InJoonNeural" # 남성
    rate: "+10%"                   # 약간 빠르게
    pitch: "+2Hz"                  # 약간 높게
```

#### 립싱크 민감도 조정

말할 때 입이 잘 안 움직이면 임계값을 낮추세요:

```yaml
lipsync:
  silence_gate: 0.001     # 낮을수록 작은 소리도 감지
  talk_threshold: 0.008   # 낮출수록 입이 더 잘 움직임
  half_threshold: 0.020
  open_threshold: 0.045
```

#### 감정 키워드 추가

내 캐릭터가 자주 쓰는 표현을 키워드에 추가합니다:

```yaml
emotion:
  keywords:
    happy: ["ㅋㅋ", "ㅎㅎ", "좋아", "재미있", "신나", "행복"]
    sad:   ["슬프", "속상", "아쉬워", "힘들"]
    # ... 더 추가
```

---

## 5. 실행 방법

항상 프로젝트 폴더(`~/aivtuber`)에서, 가상환경을 활성화한 상태로 실행하세요.

```bash
cd ~/aivtuber
source .venv/bin/activate
```

### 모드 1: 터미널 대화 모드 (기본)

```bash
python main.py
```

실행하면:
1. OpenCV 창이 열리며 캐릭터 영상 재생 시작
2. 터미널에 `You>` 프롬프트 표시
3. 메시지 입력 → Enter → AI가 응답하며 입이 움직임

```
You> 안녕하세요!
VTuber> 안녕하세요! 오늘도 방문해 주셔서 너무 반가워요~ 😊

You> 오늘 날씨 어때요?
VTuber> 오늘은 정말 화창한 날씨네요! 이런 날에는 산책하고 싶어지죠?
```

### 모드 2: 단일 발화 테스트

특정 텍스트를 발화하고 바로 종료합니다. 설정 테스트에 유용합니다.

```bash
python main.py --speak "안녕하세요! 저는 AI VTuber입니다."
```

### 모드 3: TikTok Live 채팅 연동

라이브 방송 중 시청자 채팅에 자동으로 반응합니다.

```bash
# 먼저 TikTokLive 패키지 설치
pip install TikTokLive

# 실행 (@ 없이 사용자명만)
python main.py --tiktok 내TikTok아이디
```

### 추가 옵션

```bash
# 미리보기 창 숨기기 (백그라운드 실행 시)
python main.py --no-preview

# 디버그 로그 출력 (문제 발생 시)
python main.py --debug

# 다른 설정 파일 사용
python main.py --config config/character2.yaml

# 사용 가능한 음성 목록
python main.py --list-voices
```

---

## 6. 실행 중 명령어

터미널 대화 모드에서 입력 가능한 특수 명령어:

| 명령어 | 동작 |
|--------|------|
| `/emotion happy` | 감정을 강제로 happy로 변경 |
| `/emotion sad` | 감정을 강제로 sad로 변경 |
| `/emotion neutral` | 감정을 neutral로 초기화 |
| `/emotion angry` | 감정을 angry로 변경 |
| `/emotion surprised` | 감정을 surprised로 변경 |
| `/reset` | AI 대화 기록 초기화 (새 대화 시작) |
| `quit` 또는 `종료` | 프로그램 종료 |
| `Ctrl+C` | 강제 종료 |

예시:
```
You> /emotion happy
[감정 변경] → happy

You> 오늘 너무 좋은 일이 있었어!
VTuber> 정말요?! 저도 덩달아 기분이 좋아지는데요~ 무슨 일이었어요?
```

---

## 7. OBS 연동 (방송용)

### 방법 A: 미리보기 창을 OBS에서 캡처 (간단)

1. `python main.py` 실행 → "AI VTuber" 제목의 OpenCV 창이 열림
2. OBS Studio 실행
3. OBS → 소스 추가 → **창 캡처**
4. 창 목록에서 "AI VTuber" 선택
5. 필요에 따라 크로마키 또는 크기 조정

### 방법 B: 가상 카메라 사용 (권장, 품질 우수)

#### 1단계: BlackHole 설치 (macOS 가상 오디오, 선택사항)

TTS 음성을 OBS에서도 캡처하고 싶다면:
```bash
brew install blackhole-2ch
```

#### 2단계: pyvirtualcam 설치

```bash
pip install pyvirtualcam
```

#### 3단계: 가상 카메라 드라이버 설치

macOS:
```bash
brew install obs-mac-virtualcam
```
또는 OBS Studio의 내장 가상 카메라 사용 (OBS 26+ 버전)

#### 4단계: 설정 파일에서 활성화

`config/character.yaml`:
```yaml
lipsync:
  output:
    preview_window: false   # OpenCV 창 숨기기 (선택사항)
    virtual_cam: true       # 가상 카메라 활성화
    window_size: [1280, 720]
```

#### 5단계: 실행 및 OBS 연결

```bash
python main.py
```

OBS → 소스 추가 → **비디오 캡처 장치** → "OBS Virtual Camera" 선택

---

## 8. TikTok Live 채팅 연동

### 설치

```bash
pip install TikTokLive
```

### 실행

```bash
python main.py --tiktok 내TikTok아이디
```

### 동작 방식

- TikTok Live 방송 중 시청자가 채팅을 입력하면
- AI VTuber가 자동으로 읽고 응답
- 응답을 TTS로 발화하며 캐릭터 입이 움직임

> **주의:** TikTokLive는 비공식 라이브러리입니다. TikTok 정책 변경으로 작동이 안 될 수 있습니다.

---

## 9. 입 스프라이트 만들기

### MotionPNGTuber GUI 도구 사용 (권장)

setup.sh에서 MotionPNGTuber를 클론한 경우:

#### 입 스프라이트 추출기

캐릭터 이미지에서 입 부분만 잘라내는 GUI 도구:

```bash
source .venv/bin/activate
cd MotionPNGTuber

# 의존성 추가 설치
pip install -r requirements.txt  # 또는 uv sync

# 실행
python mouth_sprite_extractor_gui.py
```

GUI에서:
1. 캐릭터 이미지 선택
2. 입 영역 마우스로 드래그해서 선택
3. 각 입 모양 (closed/half/open/u/e) 저장
4. 저장된 파일을 `assets/mouth/neutral/` 등 해당 폴더로 이동

#### 캐릭터 영상 입 제거 (고급)

원본 영상에서 입을 지운 버전을 만들어야 합니다:
1. `python MotionPNGTuber/mouth_track_gui.py` 실행
2. 영상 파일 선택
3. "입 추적 + 보정" 실행
4. "입 제거 영상 생성" 실행
5. 생성된 `*_mouthless.mp4` → `assets/character/idle.mp4`로 복사

### 직접 만들기

Photoshop, Clip Studio, GIMP 등으로 PNG 파일 직접 제작:
- 배경: 투명 (알파 채널 포함)
- 크기: 캐릭터 영상의 입 크기에 맞게
- 파일명: 반드시 `closed.png`, `half.png`, `open.png`, `u.png`, `e.png`

---

## 10. 트러블슈팅

### "AI API 키가 없습니다" 오류

```bash
# 현재 세션에 환경변수 설정
export OPENAI_API_KEY=sk-proj-xxxxx

# 영구 설정
echo 'export OPENAI_API_KEY=sk-proj-xxxxx' >> ~/.zshrc
source ~/.zshrc
```

### 창이 열리지 않음 / 화면이 검음

캐릭터 영상이 없거나 경로가 틀린 경우입니다:

```bash
# 샘플 영상 생성
python scripts/create_sample_video.py

# 영상 파일 확인
ls -la assets/character/
```

### 입이 움직이지 않음

입 스프라이트가 없거나 립싱크 임계값 문제입니다:

```bash
# 샘플 스프라이트 생성
python scripts/create_sample_sprites.py

# 스프라이트 파일 확인
ls assets/mouth/neutral/
```

`config/character.yaml`에서 임계값 낮추기:
```yaml
lipsync:
  silence_gate: 0.001
  talk_threshold: 0.005
```

### TTS 소리가 안 남

sounddevice 관련 문제입니다:

```bash
# 사용 가능한 오디오 장치 확인
python -c "import sounddevice; print(sounddevice.query_devices())"
```

macOS에서 마이크/스피커 권한이 필요할 수 있습니다:
- 시스템 설정 → 개인정보 및 보안 → 마이크 → 터미널 허용

### "ModuleNotFoundError" 오류

가상환경이 활성화되지 않은 경우입니다:

```bash
source .venv/bin/activate
# (.venv)가 프롬프트에 보이는지 확인
```

또는 패키지 재설치:
```bash
pip install -r requirements.txt
```

### edge-tts 연결 실패

인터넷 연결 문제이거나 일시적 서버 오류입니다:

```bash
# 직접 테스트
python -c "import asyncio; import edge_tts; asyncio.run(edge_tts.list_voices())"
```

실패하면 잠시 후 다시 시도하거나 Google TTS로 전환:
```yaml
tts:
  provider: "google"
```

### OpenCV 창이 응답 없음

macOS에서 OpenCV GUI는 메인 스레드에서만 동작합니다.
창을 클릭하거나 `q` 키를 누르면 닫힙니다.

---

## 빠른 참조

```bash
# 프로젝트 폴더로 이동
cd ~/aivtuber

# 가상환경 활성화 (매번 실행 전 필수)
source .venv/bin/activate

# API 키 설정
export OPENAI_API_KEY=sk-...

# 기본 실행 (터미널 대화 모드)
python main.py

# 발화 테스트
python main.py --speak "테스트 메시지입니다"

# TikTok 연동
python main.py --tiktok 내아이디

# 음성 목록 확인
python main.py --list-voices

# 디버그 모드
python main.py --debug

# 종료: Ctrl+C 또는 quit 입력
```
