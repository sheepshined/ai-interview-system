import hashlib
import io
import json
from pathlib import Path

import pytest

import model_manager


def _manifest(path: Path, payload: bytes) -> Path:
    manifest = path / "manifest.json"
    manifest.write_text(json.dumps({"version": 1, "models": [{
        "name": "fixture", "url": "https://example.test/model.bin",
        "destination": "models/fixture.bin", "size": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }]}), encoding="utf-8")
    return manifest


class Response(io.BytesIO):
    def __init__(self, payload, status=200):
        super().__init__(payload)
        self.status = status

    def getcode(self):
        return self.status


def test_fetch_skips_verified_existing_file(tmp_path, monkeypatch):
    payload = b"verified-model"
    manifest = _manifest(tmp_path, payload)
    monkeypatch.setattr(model_manager, "BASE_DIR", tmp_path)
    target = tmp_path / "models" / "fixture.bin"
    target.parent.mkdir(parents=True)
    target.write_bytes(payload)
    result = model_manager.fetch_models(manifest, output=lambda _: None)
    assert result[0]["status"] == "skipped"


def test_download_resumes_part_file_and_renames_atomically(tmp_path, monkeypatch):
    payload = b"0123456789abcdef"
    manifest = _manifest(tmp_path, payload)
    monkeypatch.setattr(model_manager, "BASE_DIR", tmp_path)
    part = tmp_path / "models" / "fixture.bin.part"
    part.parent.mkdir(parents=True)
    part.write_bytes(payload[:5])
    seen_range = []

    def opener(request, timeout):
        seen_range.append(request.headers.get("Range"))
        return Response(payload[5:], status=206)

    monkeypatch.setattr(model_manager.urllib.request, "urlopen", opener)
    result = model_manager.fetch_models(manifest, output=lambda _: None)
    assert seen_range == ["bytes=5-"]
    assert result[0]["status"] == "downloaded"
    assert (tmp_path / "models" / "fixture.bin").read_bytes() == payload
    assert not part.exists()


def test_bad_hash_keeps_part_and_reports_error(tmp_path, monkeypatch):
    payload = b"expected"
    manifest = _manifest(tmp_path, payload)
    monkeypatch.setattr(model_manager, "BASE_DIR", tmp_path)
    monkeypatch.setattr(
        model_manager.urllib.request, "urlopen",
        lambda request, timeout: Response(b"corrupt"),
    )
    with pytest.raises(RuntimeError, match="校验失败"):
        model_manager.fetch_models(manifest, output=lambda _: None)
    assert (tmp_path / "models" / "fixture.bin.part").exists()
    assert not (tmp_path / "models" / "fixture.bin").exists()


def test_manifest_rejects_parent_traversal(tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"models": [{
        "name": "bad", "url": "https://example.test/x", "destination": "../x",
        "size": 1, "sha256": "0" * 64,
    }]}), encoding="utf-8")
    with pytest.raises(ValueError, match="非法模型目标路径"):
        model_manager.load_manifest(manifest)
