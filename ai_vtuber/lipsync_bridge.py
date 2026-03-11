"""
립싱크 브리지 - TTS 오디오를 MotionPNGTuber 렌더 엔진과 연결합니다.

동작 방식:
1. TTS가 생성한 오디오(numpy array)를 받습니다.
2. 오디오를 스피커로 출력하는 동시에 렌더 큐에 공급합니다.
3. 렌더 루프는 오디오 에너지를 분석해 입 모양을 결정하고 화면에 합성합니다.
4. 현재 감정에 따라 올바른 입 스프라이트 세트를 사용합니다.
"""
from __future__ import annotations

import logging
import queue
import sys
import threading
import time
from pathlib import Path

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# MotionPNGTuber 립싱크 파라미터 기본값
_DEFAULT_LIPSYNC = {
    "talk_threshold": 0.010,
    "half_threshold": 0.025,
    "open_threshold": 0.055,
    "silence_gate": 0.002,
    "render_fps": 30,
}

# 입 스프라이트 파일명 (MotionPNGTuber 규격)
MOUTH_SPRITES = ["closed", "half", "open", "u", "e"]


def _load_sprites(mouth_dir: Path) -> dict[str, np.ndarray | None]:
    """입 스프라이트 이미지를 로드합니다. 없는 파일은 None."""
    sprites = {}
    for name in MOUTH_SPRITES:
        for ext in (".png", ".webp", ".jpg"):
            p = mouth_dir / f"{name}{ext}"
            if p.exists():
                img = cv2.imread(str(p), cv2.IMREAD_UNCHANGED)
                sprites[name] = img
                break
        else:
            sprites[name] = None
    return sprites


def _alpha_blit(base: np.ndarray, overlay: np.ndarray, x: int, y: int) -> np.ndarray:
    """알파 채널이 있는 overlay를 base 위에 합성합니다."""
    if overlay is None:
        return base
    oh, ow = overlay.shape[:2]
    bh, bw = base.shape[:2]
    # 경계 클리핑
    x1, y1 = max(x, 0), max(y, 0)
    x2, y2 = min(x + ow, bw), min(y + oh, bh)
    if x2 <= x1 or y2 <= y1:
        return base

    ox1 = x1 - x
    oy1 = y1 - y
    region = base[y1:y2, x1:x2]
    patch = overlay[oy1 : oy1 + (y2 - y1), ox1 : ox1 + (x2 - x1)]

    if overlay.shape[2] == 4:
        alpha = patch[:, :, 3:4].astype(np.float32) / 255.0
        rgb = patch[:, :, :3].astype(np.float32)
        region_f = region[:, :, :3].astype(np.float32)
        blended = region_f * (1 - alpha) + rgb * alpha
        base[y1:y2, x1:x2, :3] = blended.astype(np.uint8)
    else:
        base[y1:y2, x1:x2, :3] = patch[:, :, :3]

    return base


class LipsyncBridge:
    """
    TTS 오디오 → MotionPNGTuber 스타일 실시간 립싱크 렌더러

    사용법:
        bridge = LipsyncBridge(cfg)
        bridge.start()
        audio, sr = tts_engine.synthesize("안녕하세요!")
        bridge.feed_audio(audio, sr, emotion="happy")
        ...
        bridge.stop()
    """

    def __init__(self, cfg: dict):
        self.cfg = cfg
        ls = cfg.get("lipsync", {})
        out = ls.get("output", {})
        self._params = {**_DEFAULT_LIPSYNC, **{k: ls.get(k, v) for k, v in _DEFAULT_LIPSYNC.items()}}
        self._render_fps: int = self._params["render_fps"]
        self._show_preview: bool = out.get("preview_window", True)
        self._window_title: str = out.get("window_title", "AI VTuber")
        self._window_size: tuple[int, int] = tuple(out.get("window_size", [1280, 720]))
        self._virtual_cam: bool = out.get("virtual_cam", False)
        self._audio_sr: int = ls.get("audio", {}).get("samplerate", 24000)

        char = cfg.get("character", {})
        self._idle_video_path: str = char.get("videos", {}).get("idle", "")
        self._mouth_base: Path = Path(char.get("mouth_sprites_base", "assets/mouth"))

        # 오디오 큐: 메인 스레드에서 추가, 렌더 스레드에서 소비
        self._audio_q: queue.Queue[np.ndarray] = queue.Queue(maxsize=4096)
        # 현재 감정
        self._emotion = "neutral"
        self._emotion_lock = threading.Lock()
        # 현재 로드된 스프라이트
        self._sprites: dict[str, np.ndarray | None] = {}
        self._sprite_lock = threading.Lock()
        # 렌더 스레드
        self._render_thread: threading.Thread | None = None
        self._running = False
        # 가상 카메라 (pyvirtualcam)
        self._vcam = None

    # ------------------------------------------------------------------
    # 퍼블릭 API
    # ------------------------------------------------------------------

    def start(self):
        """렌더 루프를 시작합니다."""
        if self._running:
            return
        self._load_sprites_for_emotion(self._emotion)
        self._running = True
        self._render_thread = threading.Thread(target=self._render_loop, daemon=True)
        self._render_thread.start()
        logger.info("LipsyncBridge 시작됨")

    def stop(self):
        """렌더 루프를 중지합니다."""
        self._running = False
        if self._render_thread:
            self._render_thread.join(timeout=3)
        if self._vcam:
            self._vcam.__exit__(None, None, None)
        if self._show_preview:
            cv2.destroyAllWindows()
        logger.info("LipsyncBridge 중지됨")

    def feed_audio(self, audio: np.ndarray, samplerate: int, emotion: str | None = None):
        """
        TTS 오디오를 브리지에 공급합니다.
        동시에 sounddevice로 스피커 출력합니다.

        Args:
            audio: float32 numpy 배열 (모노)
            samplerate: 오디오 샘플레이트
            emotion: 감정 레이블 (None이면 현재 감정 유지)
        """
        if emotion is not None:
            self.set_emotion(emotion)

        # 스피커 출력 (별도 스레드에서 비동기로)
        threading.Thread(
            target=self._play_audio,
            args=(audio, samplerate),
            daemon=True,
        ).start()

        # 렌더 큐에 청크 단위로 공급
        hop = max(1, samplerate // 100)  # 10ms 단위
        for i in range(0, len(audio), hop):
            chunk = audio[i : i + hop]
            try:
                self._audio_q.put_nowait(chunk)
            except queue.Full:
                pass  # 큐가 가득 차면 드롭

    def set_emotion(self, emotion: str):
        """현재 감정을 변경하고 스프라이트를 다시 로드합니다."""
        with self._emotion_lock:
            if self._emotion != emotion:
                self._emotion = emotion
                self._load_sprites_for_emotion(emotion)

    @property
    def is_speaking(self) -> bool:
        """현재 TTS 오디오를 처리 중인지 여부"""
        return not self._audio_q.empty()

    # ------------------------------------------------------------------
    # 내부 메서드
    # ------------------------------------------------------------------

    def _load_sprites_for_emotion(self, emotion: str):
        """해당 감정의 입 스프라이트를 로드합니다."""
        from .config import get_mouth_dir
        mouth_dir = get_mouth_dir(self.cfg, emotion)

        if not mouth_dir.exists():
            # neutral 폴더로 폴백
            mouth_dir = self._mouth_base / "neutral"

        if not mouth_dir.exists():
            logger.warning(f"입 스프라이트 폴더 없음: {mouth_dir}")
            with self._sprite_lock:
                self._sprites = {name: None for name in MOUTH_SPRITES}
            return

        sprites = _load_sprites(mouth_dir)
        with self._sprite_lock:
            self._sprites = sprites
        logger.debug(f"스프라이트 로드: {mouth_dir}")

    def _play_audio(self, audio: np.ndarray, samplerate: int):
        """sounddevice로 오디오를 스피커에 출력합니다."""
        try:
            import sounddevice as sd
            sd.play(audio, samplerate=samplerate, blocking=True)
        except Exception as e:
            logger.warning(f"오디오 출력 실패: {e}")

    def _get_mouth_shape(self, rms: float, centroid: float) -> str:
        """
        오디오 에너지(RMS)와 스펙트럼 중심으로 입 모양을 결정합니다.
        MotionPNGTuber의 로직을 따릅니다.
        """
        p = self._params
        if rms < p["silence_gate"]:
            return "closed"
        if rms < p["talk_threshold"]:
            return "closed"
        if rms < p["half_threshold"]:
            return "half"
        # 모음 구분 (centroid 기반)
        norm_sr = self._audio_sr / 2
        if norm_sr > 0:
            norm_c = centroid / norm_sr
            if norm_c < 0.15:   # 저주파 → "u" (ㅜ 발음)
                return "u"
            if norm_c > 0.55:   # 고주파 → "e" (ㅔ/ㅣ 발음)
                return "e"
        if rms < p["open_threshold"]:
            return "half"
        return "open"

    def _render_loop(self):
        """메인 렌더 루프 - 오디오 에너지 분석 → 입 합성 → 화면 출력"""
        cap = self._open_video()
        vcam = self._init_vcam()

        frame_dt = 1.0 / self._render_fps
        rms = 0.0
        centroid = 0.0
        alpha = 0.2  # one-pole 평활화 계수

        while self._running:
            t0 = time.perf_counter()

            # 비디오 프레임 읽기
            frame = self._read_video_frame(cap)

            # 오디오 에너지 업데이트
            audio_chunks = []
            try:
                while True:
                    audio_chunks.append(self._audio_q.get_nowait())
            except queue.Empty:
                pass

            if audio_chunks:
                buf = np.concatenate(audio_chunks)
                new_rms = float(np.sqrt(np.mean(buf**2)))
                # 스펙트럼 중심 계산
                fft = np.abs(np.fft.rfft(buf))
                freqs = np.fft.rfftfreq(len(buf), d=1.0 / self._audio_sr)
                fft_sum = fft.sum()
                new_centroid = float((fft * freqs).sum() / fft_sum) if fft_sum > 0 else 0.0
                rms = rms * (1 - alpha) + new_rms * alpha
                centroid = centroid * (1 - alpha) + new_centroid * alpha
            else:
                # 무음 감쇠
                rms *= 0.85
                centroid *= 0.85

            # 입 모양 결정
            mouth_shape = self._get_mouth_shape(rms, centroid)

            # 입 스프라이트 합성
            with self._sprite_lock:
                sprite = self._sprites.get(mouth_shape)

            if sprite is not None and frame is not None:
                h, w = frame.shape[:2]
                sh, sw = sprite.shape[:2]
                # 입 위치: 화면 하단 중앙
                x = (w - sw) // 2
                y = int(h * 0.65)
                frame = _alpha_blit(frame, sprite, x, y)

            # 감정 HUD 표시
            if frame is not None:
                with self._emotion_lock:
                    emotion_text = self._emotion
                cv2.putText(
                    frame,
                    f"[{emotion_text}]  RMS:{rms:.4f}  {mouth_shape}",
                    (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (200, 200, 200),
                    2,
                )

            # 출력
            if frame is not None:
                out_frame = cv2.resize(frame, self._window_size)
                if self._show_preview:
                    cv2.imshow(self._window_title, out_frame)
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        self._running = False
                        break

                if vcam is not None:
                    try:
                        rgb = cv2.cvtColor(out_frame, cv2.COLOR_BGR2RGB)
                        vcam.send(rgb)
                        vcam.sleep_until_next_frame()
                    except Exception:
                        pass

            # FPS 페이싱
            elapsed = time.perf_counter() - t0
            sleep_t = frame_dt - elapsed
            if sleep_t > 0:
                time.sleep(sleep_t)

        if cap:
            cap.release()

    def _open_video(self):
        """캐릭터 영상을 엽니다."""
        if not self._idle_video_path or not Path(self._idle_video_path).exists():
            logger.warning(f"캐릭터 영상 없음: {self._idle_video_path}")
            return None
        cap = cv2.VideoCapture(str(self._idle_video_path))
        if not cap.isOpened():
            logger.error(f"영상을 열 수 없음: {self._idle_video_path}")
            return None
        return cap

    def _read_video_frame(self, cap) -> np.ndarray | None:
        """비디오 캡처에서 프레임을 읽습니다. EOF 시 루프."""
        if cap is None:
            # 영상 없으면 검은 배경
            return np.zeros((self._window_size[1], self._window_size[0], 3), dtype=np.uint8)
        ret, frame = cap.read()
        if not ret:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = cap.read()
            if not ret:
                return None
        return frame

    def _init_vcam(self):
        """가상 카메라를 초기화합니다 (설정에서 활성화된 경우)."""
        if not self._virtual_cam:
            return None
        try:
            import pyvirtualcam
            w, h = self._window_size
            vcam = pyvirtualcam.Camera(width=w, height=h, fps=self._render_fps)
            logger.info(f"가상 카메라 활성화: {vcam.device}")
            return vcam
        except ImportError:
            logger.warning("pyvirtualcam 없음. 가상 카메라 비활성화.")
            return None
        except Exception as e:
            logger.warning(f"가상 카메라 초기화 실패: {e}")
            return None
