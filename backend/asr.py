"""asr.py — 本地语音识别 (SenseVoice int8 ONNX + Silero VAD, sherpa-onnx, 完全离线)

模型文件位于 backend/models/ (gitignore, 换机器时从 DSH 用户目录
~/.dsh/speech-to-text/ 拷贝, 见 .gitignore 注释):
  models/sensevoice/model.int8.onnx  识别主模型 (阿里 SenseVoice, int8)
  models/sensevoice/tokens.txt       词表
  models/silero/silero_vad.onnx      Silero VAD (判静音/按停顿切段)

流水线: WAV → 单声道 float → 重采样 16k → Silero VAD 切语音段 →
逐段 SenseVoice 解码 → 拼接。VAD 的作用: 对静音/噪声段直接不出文本
(SenseVoice 对非语音音频会"幻听"出填充词, DSH 插件同款做法), 并把
长录音按停顿切成句, 避免超出单次解码上限。

对外只暴露:
  available() -> bool                  模型文件是否就绪
  transcribe_wav_bytes(data) -> dict   WAV 字节流 → {text, duration, sample_rate}

线程安全: OfflineRecognizer 非线程安全, 懒加载单例 + 解码互斥锁;
FastAPI 侧经 run_in_threadpool 调用, 并发时串行解码 (单句亚秒级, 足够)。
"""
import io
import importlib.util
import os
import re
import threading
import wave

import numpy as np

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.environ.get("ASR_MODELS_DIR", os.path.join(BASE_DIR, "models"))
SENSEVOICE_MODEL_PATH = os.path.join(MODELS_DIR, "sensevoice", "model.int8.onnx")
TOKENS_PATH = os.path.join(MODELS_DIR, "sensevoice", "tokens.txt")
VAD_MODEL_PATH = os.path.join(MODELS_DIR, "silero", "silero_vad.onnx")

# sherpa-onnx fbank 特征按 16kHz 提取, 前端/测试音频统一重采样到该率
TARGET_SR = 16000
# 单次识别时长上限 (秒): 面试回答场景足够, 同时防止超大音频长时间占用 CPU
MAX_DURATION_S = 120

_recognizer = None
_vad = None
_lock = threading.Lock()


def available() -> bool:
    """运行时是否具备识别能力 (模型文件与 sherpa-onnx 均就绪)。"""
    return (
        importlib.util.find_spec("sherpa_onnx") is not None
        and os.path.isfile(SENSEVOICE_MODEL_PATH)
        and os.path.isfile(TOKENS_PATH)
    )


def _get_recognizer():
    global _recognizer
    if _recognizer is None:
        with _lock:
            if _recognizer is None:  # 双重检查, 避免并发请求重复加载
                import sherpa_onnx

                _recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
                    model=SENSEVOICE_MODEL_PATH,
                    tokens=TOKENS_PATH,
                    num_threads=4,
                    use_itn=True,  # 口语数字转阿拉伯数字 ("两点" → "2点")
                )
    return _recognizer


def _get_vad():
    """Silero VAD 单例; 模型缺失时返回 None (退化为整段识别)。"""
    global _vad
    if _vad is None and os.path.isfile(VAD_MODEL_PATH):
        with _lock:
            if _vad is None:
                import sherpa_onnx

                cfg = sherpa_onnx.VadModelConfig()
                cfg.sample_rate = TARGET_SR
                cfg.silero_vad.model = VAD_MODEL_PATH
                cfg.silero_vad.min_silence_duration = 0.3   # 停顿 ≥0.3s 切句
                cfg.silero_vad.min_speech_duration = 0.15   # 短于此的段丢弃 (咳嗽等)
                _vad = sherpa_onnx.VoiceActivityDetector(cfg, buffer_size_in_seconds=MAX_DURATION_S + 2)
    return _vad


def _wav_to_float_mono(data: bytes):
    """WAV 字节 → (float32 单声道波形, 原采样率, 时长秒)。

    支持 8/16/32 位整型 PCM (浏览器与 SAPI 测试音频均覆盖),
    多声道取平均混为单声道; 不接受非 PCM (float/压缩) 格式。
    """
    with wave.open(io.BytesIO(data)) as w:
        sr = w.getframerate()
        n_channels = w.getnchannels()
        sampwidth = w.getsampwidth()
        n_frames = w.getnframes()
        raw = w.readframes(n_frames)

    duration = n_frames / float(sr) if sr else 0.0
    if duration > MAX_DURATION_S:
        raise ValueError(f"音频过长 ({duration:.0f}s), 单次最多 {MAX_DURATION_S} 秒")

    if sampwidth == 1:  # 8-bit 为无符号数, 中心在 128
        samples = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    elif sampwidth == 2:
        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    elif sampwidth == 4:
        samples = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f"不支持的 WAV 位深: {sampwidth * 8} bit (仅支持 8/16/32 位 PCM)")

    if n_channels > 1:
        samples = samples.reshape(-1, n_channels).mean(axis=1)
    return samples, sr, duration


def _resample_to_16k(samples: np.ndarray, src_sr: int) -> np.ndarray:
    """线性插值重采样到 16kHz (语音识别对插值精度不敏感, 无需 scipy)。"""
    if src_sr == TARGET_SR or samples.size < 2:
        return samples.astype(np.float32)
    n_out = int(round(samples.size / src_sr * TARGET_SR))
    t_src = np.arange(samples.size, dtype=np.float64) / src_sr
    t_out = np.arange(n_out, dtype=np.float64) / TARGET_SR
    return np.interp(t_out, t_src, samples).astype(np.float32)


def _is_cjk(ch: str) -> bool:
    return "\u4e00" <= ch <= "\u9fff"


def _join_segments(texts) -> str:
    """拼接各语音段的识别结果: 中日韩边界直接相连, 其余 (英/数字边界) 补空格。"""
    out = ""
    for t in texts:
        t = (t or "").strip()
        if not t:
            continue
        if out and _is_cjk(out[-1]) and _is_cjk(t[0]):
            out += t
        else:
            out += (" " if out else "") + t
    return out


def clean_transcript(text: str) -> str:
    """Remove decoder control tokens, filler, and obvious repeated output."""
    compact = re.sub(r"<\|[^|>]+\|>", "", (text or ""))
    compact = re.sub(r"\s+", " ", compact).strip()
    if not compact:
        return ""
    fillers = {"谢谢观看", "感谢观看", "请不吝点赞订阅转发打赏支持明镜与点点栏目"}
    if compact.strip("。！!，, ") in fillers:
        return ""
    match = re.fullmatch(r"(.{1,24}?)(?:[，,。.!！ ]*\1){2,}[，,。.!！ ]*", compact)
    return match.group(1).strip() if match else compact


def _detect_speech_segments(samples: np.ndarray):
    """Silero VAD 切出语音段; 无 VAD 模型时退化为整段一个。

    必须按窗口分块流式喂入并即时消费片段: 一次性倒入后再 flush
    只能得到残缺片段 (实测), 与官方示例的流式用法保持一致。
    """
    vad = _get_vad()
    if vad is None:
        return [samples]
    segments = []
    with _lock:
        vad.reset()
        window = 512  # silero_vad.window_size
        for i in range(0, samples.size, window):
            vad.accept_waveform(samples[i:i + window])
            while not vad.empty():
                segments.append(np.asarray(vad.front.samples, dtype=np.float32))
                vad.pop()
        vad.flush()
        while not vad.empty():
            segments.append(np.asarray(vad.front.samples, dtype=np.float32))
            vad.pop()
    return segments


def transcribe_wav_bytes(data: bytes) -> dict:
    """识别 WAV 字节流, 返回 {text, duration, sample_rate}。

    采样率不为 16k 时先重采样; VAD 判定无语音 (静音/噪声) 返回空文本。
    """
    samples, src_sr, duration = _wav_to_float_mono(data)
    if samples.size == 0:
        return {"text": "", "duration": 0.0, "sample_rate": src_sr}

    samples = _resample_to_16k(samples, src_sr)
    segments = _detect_speech_segments(samples)
    if not segments:
        return {"text": "", "duration": round(duration, 2), "sample_rate": src_sr}

    recognizer = _get_recognizer()
    texts = []
    with _lock:
        for seg in segments:
            stream = recognizer.create_stream()
            stream.accept_waveform(TARGET_SR, seg)
            recognizer.decode_stream(stream)
            texts.append(stream.result.text)

    return {
        "text": clean_transcript(_join_segments(texts)),
        "duration": round(duration, 2),
        "sample_rate": src_sr,
    }
