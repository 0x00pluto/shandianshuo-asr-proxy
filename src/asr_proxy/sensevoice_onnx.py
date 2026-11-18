"""SenseVoice Small ONNX 转写（FunASR 导出契约：speech / speech_lengths / language / textnorm）。"""

from __future__ import annotations

import io
import json
import wave
from pathlib import Path
from typing import Any

LID = {"auto": 0, "zh": 3, "en": 4, "yue": 7, "ja": 11, "ko": 12, "nospeech": 13}
TN = {"withitn": 14, "woitn": 15}


def apply_lfr(inputs: Any, lfr_m: int = 7, lfr_n: int = 6) -> Any:
    import numpy as np

    left = np.tile(inputs[0], ((lfr_m - 1) // 2, 1))
    padded = np.vstack((left, inputs))
    total = padded.shape[0]
    count = int(np.ceil(inputs.shape[0] / lfr_n))
    pieces = []
    for index in range(count):
        start = index * lfr_n
        if lfr_m <= total - start:
            pieces.append(padded[start : start + lfr_m].reshape(1, -1))
        else:
            frame = padded[start:].reshape(-1)
            missing = lfr_m - (total - start)
            for _ in range(missing):
                frame = np.hstack((frame, padded[-1]))
            pieces.append(frame)
    return np.vstack(pieces).astype(np.float32)


def decode_tokens(token_ids: list[int], tokens: list[str]) -> str:
    pieces = []
    for token_id in token_ids:
        if token_id < 0 or token_id >= len(tokens):
            continue
        piece = tokens[token_id]
        if piece.startswith("<|") and piece.endswith("|>"):
            continue
        pieces.append(piece)
    text = "".join(pieces).replace("\u2581", " ")
    return " ".join(text.split())


def wav_bytes_to_float32(wav: bytes, *, expect_rate: int = 16000) -> Any:
    import numpy as np

    with wave.open(io.BytesIO(wav), "rb") as handle:
        if handle.getnchannels() != 1 or handle.getsampwidth() != 2:
            raise RuntimeError("SenseVoice 需要 16-bit 单声道 WAV")
        rate = handle.getframerate()
        frames = handle.readframes(handle.getnframes())
    pcm = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    if rate == expect_rate:
        return pcm
    if rate <= 0:
        raise RuntimeError(f"非法采样率：{rate}")
    # 线性重采样到 16 kHz（避免强制依赖 librosa）
    duration = pcm.shape[0] / float(rate)
    target_len = max(1, int(round(duration * expect_rate)))
    if target_len == pcm.shape[0]:
        return pcm
    x_old = np.linspace(0.0, 1.0, num=pcm.shape[0], endpoint=False)
    x_new = np.linspace(0.0, 1.0, num=target_len, endpoint=False)
    return np.interp(x_new, x_old, pcm).astype(np.float32)


def compute_fbank(waveform: Any) -> Any:
    import kaldi_native_fbank as knf
    import numpy as np

    opts = knf.FbankOptions()
    opts.frame_opts.samp_freq = 16000
    opts.frame_opts.dither = 0.0
    opts.frame_opts.window_type = "hamming"
    opts.frame_opts.frame_shift_ms = 10.0
    opts.frame_opts.frame_length_ms = 25.0
    opts.frame_opts.snip_edges = True
    opts.mel_opts.num_bins = 80
    opts.energy_floor = 0
    computer = knf.OnlineFbank(opts)
    computer.accept_waveform(16000, (waveform * (1 << 15)).tolist())
    frames = computer.num_frames_ready
    if frames <= 0:
        raise RuntimeError("SenseVoice：无有效音频帧")
    mat = np.empty((frames, 80), dtype=np.float32)
    for index in range(frames):
        mat[index] = computer.get_frame(index)
    return mat


class SenseVoiceEngine:
    """启动时加载一次；请求线程内复用 session。"""

    def __init__(self, model_dir: Path):
        import numpy as np
        import onnxruntime as ort

        self._np = np
        self.model_dir = Path(model_dir)
        tokens_path = self.model_dir / "tokens.json"
        self.tokens = json.loads(tokens_path.read_text(encoding="utf-8"))
        if not isinstance(self.tokens, list) or not self.tokens:
            raise RuntimeError(f"tokens.json 无效：{tokens_path}")
        self.session = ort.InferenceSession(
            str(self.model_dir / "model.onnx"),
            providers=["CPUExecutionProvider"],
        )

    def transcribe(self, wav: bytes, language: str = "zh") -> str:
        np = self._np
        waveform = wav_bytes_to_float32(wav)
        feat = apply_lfr(compute_fbank(waveform))
        speech = feat[np.newaxis, :, :]
        length = np.array([feat.shape[0]], dtype=np.int32)
        lid_key = language if language in LID else "zh"
        if language in ("zh", "chinese", "zh-cn", "zh_cn"):
            lid_key = "zh"
        language_t = np.array([LID.get(lid_key, LID["zh"])], dtype=np.int32)
        textnorm = np.array([TN["withitn"]], dtype=np.int32)
        logits, out_lens = self.session.run(
            None,
            {
                "speech": speech,
                "speech_lengths": length,
                "language": language_t,
                "textnorm": textnorm,
            },
        )
        used = int(out_lens[0])
        ids = np.argmax(logits[0, :used], axis=-1)
        keep = np.concatenate(([True], np.diff(ids) != 0))
        ids = ids[keep]
        ids = ids[ids != 0]
        return decode_tokens(ids.tolist(), self.tokens)
