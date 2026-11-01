"""v1.1 本地语音识别测试: WAV 解码/重采样管道 + SenseVoice 端到端 + /api/asr 接口。

真语音用 Windows 自带 SAPI TTS 离线合成 (tests/_gen_speech.ps1), 不联网;
模型未就绪 (backend/models/ 缺失) 或非 Windows 时, 端到端用例自动跳过。
"""
import io
import itertools
import math
import os
import struct
import subprocess
import sys
import wave

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import asr  # noqa: E402

from server import app  # noqa: E402

client = TestClient(app)

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))

# /api/asr 各用例各注册独立用户 (conftest 将 AUTH_DB_PATH 隔离到临时目录)
_user_counter = itertools.count()


def test_clean_transcript_filters_decoder_hallucinations():
    assert asr.clean_transcript("<|zh|>你好") == "你好"
    assert asr.clean_transcript("谢谢观看") == ""
    assert asr.clean_transcript("你好你好你好你好") == "你好"
    assert asr.clean_transcript("我使用 Python 完成了接口开发") == "我使用 Python 完成了接口开发"


def test_available_requires_sherpa_runtime(monkeypatch):
    """模型文件存在但推理运行时缺失时，不应把 ASR 标成可用。"""
    monkeypatch.setattr(asr.importlib.util, "find_spec", lambda name: None)
    assert asr.available() is False


def _make_wav(samples, sr=16000, sampwidth=2, n_channels=1):
    """把 float 波形打包成 WAV 字节, 用于管道单元测试 (n_channels>1 时逐样本交织)。"""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(n_channels)
        w.setsampwidth(sampwidth)
        w.setframerate(sr)
        if n_channels > 1:
            samples = [s for s in samples for _ in range(n_channels)]
        if sampwidth == 1:
            frames = b"".join(struct.pack("<B", min(255, max(0, int(s * 128) + 128)))
                              for s in samples)
        elif sampwidth == 2:
            frames = b"".join(struct.pack("<h", int(max(-1.0, min(1.0, s)) * 32767))
                              for s in samples)
        else:
            frames = b"".join(struct.pack("<i", int(max(-1.0, min(1.0, s)) * 2147483647))
                              for s in samples)
        w.writeframes(frames)
    return buf.getvalue()


def _sine(freq=440.0, seconds=0.3, sr=16000):
    n = int(sr * seconds)
    return [0.3 * math.sin(2 * math.pi * freq * i / sr) for i in range(n)]


@pytest.fixture(scope="module")
def sapi_wav_bytes():
    """SAPI 合成一段中文测试语音 (模块级一次, 各用例复用)。"""
    text = "请介绍一下Transformer的注意力机制"
    out = os.path.join(_TESTS_DIR, "_audio", "pytest_t1.wav")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    r = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
         "-File", os.path.join(_TESTS_DIR, "_gen_speech.ps1"),
         "-OutFile", out, "-Text", text],
        capture_output=True, timeout=60,
    )
    if r.returncode != 0 or not os.path.isfile(out):
        pytest.skip(f"SAPI 语音合成不可用: {r.stderr.decode(errors='ignore')[:120]}")
    with open(out, "rb") as f:
        return f.read()


# ---------- 管道单元测试 (不依赖模型, 但统一跟随模型可用性跳过) ----------

@pytest.mark.skipif(not asr.available(), reason="SenseVoice 模型未就绪 (backend/models/)")
class TestWavPipeline:
    def test_16k_mono_sine(self):
        r = asr.transcribe_wav_bytes(_make_wav(_sine()))
        assert r["text"] == ""          # 正弦波无语音 → 空文本而非报错
        assert r["duration"] == pytest.approx(0.3, abs=0.02)
        assert r["sample_rate"] == 16000

    def test_48k_resample(self):     # 浏览器 AudioContext 常见 48kHz
        r = asr.transcribe_wav_bytes(_make_wav(_sine(seconds=0.3, sr=48000), sr=48000))
        assert r["text"] == ""
        assert r["duration"] == pytest.approx(0.3, abs=0.02)

    def test_stereo_and_8bit_32bit(self):
        for sr, sw, ch in [(22050, 1, 1), (44100, 4, 2), (16000, 2, 2)]:
            r = asr.transcribe_wav_bytes(_make_wav(_sine(seconds=0.2, sr=sr), sr=sr,
                                                   sampwidth=sw, n_channels=ch))
            assert r["text"] == "" and r["duration"] == pytest.approx(0.2, abs=0.05)

    def test_empty_audio(self):
        r = asr.transcribe_wav_bytes(_make_wav([], sr=16000))
        assert r["text"] == "" and r["duration"] == 0.0

    def test_too_long_rejected(self):
        with pytest.raises(ValueError, match="音频过长"):
            asr.transcribe_wav_bytes(_make_wav(_sine(seconds=130, sr=1000), sr=1000))

    def test_unsupported_bitdepth(self):
        with pytest.raises(ValueError, match="位深"):
            asr.transcribe_wav_bytes(_make_wav(_sine(), sampwidth=3))


# ---------- 端到端: SAPI 合成中文语音 → SenseVoice 识别 ----------

@pytest.mark.skipif(not asr.available(), reason="SenseVoice 模型未就绪 (backend/models/)")
class TestSenseVoiceE2E:
    def test_chinese_speech_recognized(self, sapi_wav_bytes):
        r = asr.transcribe_wav_bytes(sapi_wav_bytes)
        assert "注意力机制" in r["text"]
        assert "transformer" in r["text"].lower()
        assert r["duration"] > 1.0

    def test_short_silence_returns_empty(self):
        r = asr.transcribe_wav_bytes(_make_wav([0.0] * 16000))  # 1s 静音
        assert r["text"] == ""


# ---------- /api/asr HTTP 接口 ----------

@pytest.mark.skipif(not asr.available(), reason="SenseVoice 模型未就绪 (backend/models/)")
class TestAsrApi:
    @pytest.fixture(autouse=True)
    def _headers(self):
        username = f"asruser{next(_user_counter)}"
        resp = client.post("/api/register",
                           json={"username": username, "password": "pass12345"})
        assert resp.status_code == 200, resp.text
        self.headers = {"Authorization": f"Bearer {resp.json()['token']}"}




    def test_recognize_ok(self, sapi_wav_bytes):
        resp = client.post("/api/asr", headers=self.headers,
                           files={"file": ("voice.wav", sapi_wav_bytes, "audio/wav")})
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert "注意力机制" in body["text"]

    def test_requires_auth(self, sapi_wav_bytes):
        resp = client.post("/api/asr", files={"file": ("voice.wav", sapi_wav_bytes, "audio/wav")})
        assert resp.status_code == 401

    def test_empty_file(self):
        resp = client.post("/api/asr", headers=self.headers,
                           files={"file": ("voice.wav", b"", "audio/wav")})
        assert resp.status_code == 200
        assert resp.json()["success"] is False

    def test_bad_wav(self):
        resp = client.post("/api/asr", headers=self.headers,
                           files={"file": ("voice.wav", b"not a wav file", "audio/wav")})
        assert resp.status_code == 200
        assert resp.json()["success"] is False
