"""
립싱크 브리지 - TTS 오디오를 MotionPNGTuber 렌더 엔진과 연결합니다.

macOS 제약: cv2.imshow는 반드시 메인 스레드에서 호출해야 합니다.
따라서 렌더링은 start()가 아닌, 호출자가 render_tick()을 메인 스레드에서
주기적으로 호출하는 방식으로 동작합니다.
"""
from __future__ import annotations

import logging
import queue
import threading
import time
from pathlib import Path

import cv2
import numpy as np

logger = logging.getLogger(__name__)

_DEFAULT_LIPSYNC = {
    "talk_threshold": 0.010,
    "half_threshold": 0.025,
    "open_threshold": 0.055,
    "silence_gate": 0.002,
    "render_fps": 30,
}

MOUTH_SPRITES = ["closed", "half", "open", "u", "e"]


def _load_sprites(mouth_dir: Path) -> dict[str, np.ndarray | None]:
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
    if overlay is None:
        return base
    oh, ow = overlay.shape[:2]
    bh, bw = base.shape[:2]
    x1, y1 = max(x, 0), max(y, 0)
    x2, y2 = min(x + ow, bw), min(y + oh, bh)
    if x2 <= x1 or y2 <= y1:
        return base
    ox1, oy1 = x1 - x, y1 - y
    region = base[y1:y2, x1:x2]
    patch = overlay[oy1: oy1 + (y2 - y1), ox1: ox1 + (x2 - x1)]
    if overlay.shape[2] == 4:
        alpha = patch[:, :, 3:4].astype(np.float32) / 255.0
        blended = region[:, :, :3].astype(np.float32) * (1 - alpha) \
                  + patch[:, :, :3].astype(np.float32) * alpha
        base[y1:y2, x1:x2, :3] = blended.astype(np.uint8)
    else:
        base[y1:y2, x1:x2, :3] = patch[:, :, :3]
    return base


class LipsyncBridge:
    """
    TTS 오디오 → 실시간 립싱크 렌더러

    사용법 (main.py에서):
        bridge = LipsyncBridge(cfg)
        bridge.start()                          # 초기화만 수행
        # asyncio를 백그라운드 스레드에서 실행
        # 메인 스레드에서 render_tick()을 루프로 호출
        while bridge.running:
            bridge.render_tick()
            time.sleep(1/30)
        bridge.stop()
    """

    def __init__(self, cfg: dict):
        self.cfg = cfg
        ls = cfg.get("lipsync", {})
        out = ls.get("output", {})
        self._params = {**_DEFAULT_LIPSYNC,
                        **{k: ls.get(k, v) for k, v in _DEFAULT_LIPSYNC.items()}}
        self._render_fps: int = self._params["render_fps"]
        self._show_preview: bool = out.get("preview_window", True)
        self._window_title: str = out.get("window_title", "AI VTuber")
        self._window_size: tuple[int, int] = tuple(out.get("window_size", [1280, 720]))
        self._use_vcam: bool = out.get("virtual_cam", False)
        self._audio_sr: int = ls.get("audio", {}).get("samplerate", 24000)

        char = cfg.get("character", {})
        self._idle_video_path: str = char.get("videos", {}).get("idle", "")
        self._mouth_base: Path = Path(char.get("mouth_sprites_base", "assets/mouth"))

        self._audio_q: queue.Queue[np.ndarray] = queue.Queue(maxsize=4096)
        self._emotion = "neutral"
        self._emotion_lock = threading.Lock()
        self._sprites: dict[str, np.ndarray | None] = {}
        self._sprite_lock = threading.Lock()

        # 렌더 상태 (메인 스레드에서만 사용)
        self._cap = None
        self._vcam = None
        self._rms = 0.0
        self._centroid = 0.0
        self._alpha = 0.2   # one-pole smoothing

        self.running = False

    # ── 퍼블릭 API ─────────────────────────────────────────────────────

    def start(self):
        """초기화합니다. 렌더 스레드는 시작하지 않습니다."""
        if self.running:
            return
        self._load_sprites_for_emotion(self._emotion)
        self._cap = self._open_video()
        self._vcam = self._init_vcam()
        self.running = True
        logger.info("LipsyncBridge 시작됨")

    def stop(self):
        """리소스를 정리합니다."""
        if not self.running:
            return
        self.running = False
        if self._cap:
            self._cap.release()
            self._cap = None
        if self._vcam:
            try:
                self._vcam.__exit__(None, None, None)
            except Exception:
                pass
            self._vcam = None
        if self._show_preview:
            cv2.destroyAllWindows()
        logger.info("LipsyncBridge 중지됨")

    def render_tick(self) -> bool:
        """
        프레임 하나를 처리합니다.
        반드시 메인 스레드에서 호출해야 합니다 (macOS cv2.imshow 제약).
        Returns: False이면 종료 신호 (q 키 입력 등)
        """
        if not self.running:
            return False

        frame = self._read_video_frame(self._cap)
        self._process_audio()
        mouth_shape = self._get_mouth_shape(self._rms, self._centroid)

        # 입 스프라이트 합성
        if frame is not None:
            with self._sprite_lock:
                sprite = self._sprites.get(mouth_shape)
            if sprite is not None:
                h, w = frame.shape[:2]
                sh, sw = sprite.shape[:2]
                x = (w - sw) // 2
                y = int(h * 0.65)
                frame = _alpha_blit(frame, sprite, x, y)

            with self._emotion_lock:
                emotion_text = self._emotion
            cv2.putText(frame,
                        f"[{emotion_text}]  {mouth_shape}  RMS:{self._rms:.4f}",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 2)

            out_frame = cv2.resize(frame, self._window_size)

            if self._show_preview:
                cv2.imshow(self._window_title, out_frame)
                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    self.running = False
                    return False

            if self._vcam is not None:
                try:
                    rgb = cv2.cvtColor(out_frame, cv2.COLOR_BGR2RGB)
                    self._vcam.send(rgb)
                    self._vcam.sleep_until_next_frame()
                except Exception:
                    pass

        return True

    def feed_audio(self, audio: np.ndarray, samplerate: int, emotion: str | None = None):
        """TTS 오디오를 공급합니다. 스피커 출력 + 립싱크 큐에 추가."""
        if emotion is not None:
            self.set_emotion(emotion)
        threading.Thread(target=self._play_audio, args=(audio, samplerate), daemon=True).start()
        hop = max(1, samplerate // 100)
        for i in range(0, len(audio), hop):
            try:
                self._audio_q.put_nowait(audio[i: i + hop])
            except queue.Full:
                pass

    def set_emotion(self, emotion: str):
        with self._emotion_lock:
            if self._emotion != emotion:
                self._emotion = emotion
                self._load_sprites_for_emotion(emotion)

    @property
    def is_speaking(self) -> bool:
        return not self._audio_q.empty()

    # ── 내부 메서드 ────────────────────────────────────────────────────

    def _process_audio(self):
        """큐에서 오디오를 읽어 RMS/centroid를 업데이트합니다."""
        chunks = []
        try:
            while True:
                chunks.append(self._audio_q.get_nowait())
        except queue.Empty:
            pass

        if chunks:
            buf = np.concatenate(chunks)
            new_rms = float(np.sqrt(np.mean(buf ** 2)))
            fft = np.abs(np.fft.rfft(buf))
            freqs = np.fft.rfftfreq(len(buf), d=1.0 / self._audio_sr)
            s = fft.sum()
            new_centroid = float((fft * freqs).sum() / s) if s > 0 else 0.0
            self._rms = self._rms * (1 - self._alpha) + new_rms * self._alpha
            self._centroid = self._centroid * (1 - self._alpha) + new_centroid * self._alpha
        else:
            self._rms *= 0.85
            self._centroid *= 0.85

    def _get_mouth_shape(self, rms: float, centroid: float) -> str:
        p = self._params
        if rms < p["silence_gate"] or rms < p["talk_threshold"]:
            return "closed"
        if rms < p["half_threshold"]:
            return "half"
        # 한국어 음성 centroid 범위 기준 (sr=24000, 나이퀴스트=12000Hz)
        norm_sr = self._audio_sr / 2
        if norm_sr > 0:
            norm_c = centroid / norm_sr
            if norm_c < 0.10:   # < ~1200Hz → ㅜ/ㅗ
                return "u"
            if norm_c > 0.21:   # > ~2500Hz → ㅔ/ㅣ
                return "e"
        if rms < p["open_threshold"]:
            return "half"
        return "open"

    def _load_sprites_for_emotion(self, emotion: str):
        from .config import get_mouth_dir
        mouth_dir = get_mouth_dir(self.cfg, emotion)
        if not mouth_dir.exists():
            mouth_dir = self._mouth_base / "neutral"
        if not mouth_dir.exists():
            logger.warning(f"입 스프라이트 폴더 없음: {mouth_dir}")
            with self._sprite_lock:
                self._sprites = {name: None for name in MOUTH_SPRITES}
            return
        with self._sprite_lock:
            self._sprites = _load_sprites(mouth_dir)
        logger.debug(f"스프라이트 로드: {mouth_dir}")

    def _play_audio(self, audio: np.ndarray, samplerate: int):
        try:
            import sounddevice as sd
            sd.play(audio, samplerate=samplerate, blocking=True)
        except Exception as e:
            logger.warning(f"오디오 출력 실패: {e}")

    def _open_video(self):
        if not self._idle_video_path or not Path(self._idle_video_path).exists():
            logger.warning(f"캐릭터 영상 없음: {self._idle_video_path!r}")
            return None
        cap = cv2.VideoCapture(str(self._idle_video_path))
        if not cap.isOpened():
            logger.error(f"영상을 열 수 없음: {self._idle_video_path}")
            return None
        return cap

    def _read_video_frame(self, cap) -> np.ndarray | None:
        if cap is None:
            return np.zeros((self._window_size[1], self._window_size[0], 3), dtype=np.uint8)
        ret, frame = cap.read()
        if not ret:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = cap.read()
            if not ret:
                return None
        return frame

    def _init_vcam(self):
        if not self._use_vcam:
            return None
        try:
            import pyvirtualcam
            w, h = self._window_size
            vcam = pyvirtualcam.Camera(width=w, height=h, fps=self._render_fps)
            logger.info(f"가상 카메라 활성화: {vcam.device}")
            return vcam
        except ImportError:
            logger.warning("pyvirtualcam 없음. 가상 카메라 비활성화.")
        except Exception as e:
            logger.warning(f"가상 카메라 초기화 실패: {e}")
        return None
